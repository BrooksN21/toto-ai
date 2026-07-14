import csv
import json
import re
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session
from typer.testing import CliRunner

import toto_ai.ev.backtest as backtest_module
from toto_ai.cli import _parse_csv_floats, _parse_csv_ints, app
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.ev.backtest import (
    EVBacktestConfig,
    load_frozen_holdout_ids,
    run_ev_backtest,
)
from toto_ai.ev.models import EVComponents, EVInput, EVSurface
from toto_ai.ev.package import rank_coupon_indices as production_rank_coupon_indices
from toto_ai.ev.reports import ev_backtest_report_paths, write_ev_backtest_reports
from toto_ai.ev.ternary import materialize_ev_surface as production_materialize

runner = CliRunner()


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


@pytest.fixture(autouse=True)
def tiny_complete_ranking(monkeypatch):
    def rank(surface):
        return np.argsort(surface.gross_ev, kind="stable")[::-1]

    monkeypatch.setattr(backtest_module, "rank_coupon_indices", rank)


def _surface_builder(values=(1.10, 1.00, 0.80), calls=None):
    def build(ev_input, progress_callback=None):
        if calls is not None:
            calls.append(ev_input.drawing_id)
        return EVSurface(
            gross_ev=np.asarray(values, dtype=np.float64),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    return build


def _add_drawing(
    session,
    drawing_id,
    *,
    number=None,
    results=None,
    event_count=15,
    bk=(60.0, 25.0, 15.0),
    pool=(50.0, 30.0, 20.0),
    pool_sum=1_000_000.0,
):
    number = number if number is not None else 1000 + drawing_id
    results = results if results is not None else ("1",) * event_count
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status="finished",
            pool_sum=pool_sum,
            jackpot=100_000.0,
            ended_at=f"2026-01-{drawing_id:02d}T00:00:00+00:00",
        )
    )
    for order in range(event_count):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=order,
                name=f"Match {order + 1}",
                result=results[order],
            )
        )
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=order,
                bk_win_1=bk[0],
                bk_draw=bk[1],
                bk_win_2=bk[2],
                pool_win_1=pool[0],
                pool_draw=pool[1],
                pool_win_2=pool[2],
            )
        )
    session.commit()


def _run(session, **overrides):
    arguments = {
        "last": 1,
        "banks": (60, 90),
        "thresholds": (0.90, 1.05, 1.20),
        "stake": 30,
        "prize_fund_factors": (1.0,),
        "forbidden_drawing_ids": frozenset(),
        "surface_builder": _surface_builder(),
    }
    arguments.update(overrides)
    return run_ev_backtest(session, **arguments)


def _manifest_payload(drawing_ids, holdout_size):
    return {
        "schema_version": 1,
        "code_version": "abc123",
        "last": len(drawing_ids),
        "holdout_size": holdout_size,
        "drawing_ids": drawing_ids,
        "input_data_hash": "input",
        "configuration_hash": "config",
        "protocol_hash": "protocol",
        "config": {},
    }


def test_backtest_types_are_immutable_and_deep_normalized(session):
    config = EVBacktestConfig(
        banks=[60],
        thresholds=[1.0],
        stake=30,
        prize_fund_factors=[0.7, 1.0],
    )

    assert config.banks == (60,)
    assert config.thresholds == (1.0,)
    with pytest.raises(FrozenInstanceError):
        config.stake = 40

    _add_drawing(session, 1)
    result = _run(session, banks=(60,), thresholds=(1.0,))
    assert isinstance(result.rows, tuple)
    assert isinstance(result.summaries, tuple)
    with pytest.raises(FrozenInstanceError):
        result.elapsed_seconds = 0.0


@pytest.mark.parametrize(
    ("drawing_ids", "holdout_size", "message"),
    [
        ([1, 2, 2], 1, "duplicate"),
        ([1, 2], 0, "positive"),
        ([1, 2], 3, "exceed"),
        ([1, 2], True, "integer"),
    ],
)
def test_frozen_holdout_loader_rejects_invalid_boundaries(
    tmp_path,
    drawing_ids,
    holdout_size,
    message,
):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(_manifest_payload(drawing_ids, holdout_size)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_frozen_holdout_ids(path)


def test_frozen_holdout_loader_returns_final_ordered_ids(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(_manifest_payload([7, 3, 9, 4], 2)),
        encoding="utf-8",
    )

    assert load_frozen_holdout_ids(path) == frozenset({9, 4})


def test_backtest_excludes_holdout_before_any_event_or_quote_query(session):
    for drawing_id in range(1, 5):
        _add_drawing(session, drawing_id)
    queries = []
    current_phase = {"value": "before_packages"}

    @event.listens_for(session.bind, "before_cursor_execute")
    def capture_event_queries(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ):
        del connection, cursor, context, executemany
        queries.append((current_phase["value"], statement, parameters))

    def progress(update):
        if update["phase"] == "packages_ready":
            assert update["package_hashes"]
            assert all(len(value) == 64 for value in update["package_hashes"])
        current_phase["value"] = update["phase"]

    result = _run(
        session,
        last=3,
        forbidden_drawing_ids=frozenset({4}),
        progress_callback=progress,
    )

    assert result.drawing_ids == (1, 2, 3)
    drawing_query_index = next(
        index
        for index, (_, statement, _) in enumerate(queries)
        if "from drawings" in statement.lower()
    )
    event_or_quote_query_indices = [
        index
        for index, (_, statement, _) in enumerate(queries)
        if _touches_event_or_quote(statement)
    ]
    assert event_or_quote_query_indices
    assert all(
        drawing_query_index < query_index
        for query_index in event_or_quote_query_indices
    )
    drawing_statement = queries[drawing_query_index][1].upper()
    assert "DRAWINGS.ID NOT IN" in drawing_statement
    assert set(_bound_integer_parameters(queries[drawing_query_index][2])) == {4}
    allowed_drawing_ids = {1, 2, 3}
    for phase, statement, parameters in queries:
        lowered = statement.lower()
        if not _touches_event_or_quote(statement):
            continue
        drawing_id = _bound_drawing_id_parameter(statement, parameters)
        assert drawing_id in allowed_drawing_ids
        assert drawing_id != 4
        if phase != "packages_ready":
            assert "events.result" not in lowered
    actual_queries = [
        (phase, statement)
        for phase, statement, _ in queries
        if "events.result" in statement.lower()
    ]
    assert actual_queries
    assert all(phase == "packages_ready" for phase, _ in actual_queries)


@pytest.mark.parametrize(
    "statement",
    (
        "SELECT events.event_order FROM events WHERE events.event_order = ?",
        "SELECT quotes.bk_win_1 FROM quotes WHERE quotes.event_order = ?",
    ),
)
def test_sql_scope_check_rejects_unscoped_event_and_quote_queries(statement):
    assert _touches_event_or_quote(statement)
    with pytest.raises(AssertionError, match="drawing_id"):
        _bound_drawing_id_parameter(statement, (1,))


def test_sql_scope_check_rejects_join_without_quote_drawing_relation():
    statement = (
        "SELECT events.event_order, quotes.bk_win_1 "
        "FROM events JOIN quotes "
        "ON quotes.event_order = events.event_order "
        "WHERE events.drawing_id = ?"
    )

    with pytest.raises(AssertionError, match="quotes.drawing_id"):
        _bound_drawing_id_parameter(statement, (1,))


def test_backtest_is_chronological_and_skips_invalid_inputs(session):
    _add_drawing(session, 1, number=1001)
    _add_drawing(session, 2, number=1002)
    _add_drawing(session, 3, number=1003, bk=(0.0, 0.0, 0.0))

    result = _run(session, last=2, banks=(60,), thresholds=(1.0,))

    assert result.drawing_ids == (1, 2)
    assert result.skipped_drawing_ids == (3,)
    assert [row.drawing_id for row in result.rows] == [1, 2]


def test_incomplete_actual_results_never_produce_rows(session):
    results = ["1"] * 15
    results[-1] = None
    _add_drawing(session, 1, results=tuple(results))

    result = _run(session, banks=(60,), thresholds=(1.0,))

    assert result.rows == ()
    assert result.processed_drawing_ids == ()
    assert result.skipped_drawing_ids == (1,)


def test_last_counts_latest_drawings_with_complete_actual_results(session):
    _add_drawing(session, 1, number=1001)
    _add_drawing(session, 2, number=1002)
    incomplete = ["1"] * 15
    incomplete[-1] = None
    _add_drawing(session, 3, number=1003, results=tuple(incomplete))

    result = _run(session, last=2, banks=(60,), thresholds=(1.0,))

    assert result.processed_drawing_ids == (1, 2)
    assert result.skipped_drawing_ids == (3,)


def test_inputs_and_package_hashes_are_complete_before_actual_result_load(
    monkeypatch,
    session,
):
    _add_drawing(session, 1)
    phases = []
    original_load = backtest_module._load_actual_result

    def load_result(*args, **kwargs):
        assert phases[-1]["phase"] == "packages_ready"
        assert all(len(value) == 64 for value in phases[-1]["package_hashes"])
        phases.append({"phase": "result_query"})
        return original_load(*args, **kwargs)

    monkeypatch.setattr(backtest_module, "_load_actual_result", load_result)
    _run(session, progress_callback=phases.append)

    assert [phase["phase"] for phase in phases].index("packages_ready") < [
        phase["phase"] for phase in phases
    ].index("result_query")


def test_one_component_build_and_one_ranking_per_factor_are_reused(
    monkeypatch,
    session,
):
    _add_drawing(session, 1)
    calls = []
    rank_calls = []

    def rank(surface):
        rank_calls.append(surface)
        return np.argsort(surface.gross_ev, kind="stable")[::-1]

    monkeypatch.setattr(backtest_module, "rank_coupon_indices", rank)
    result = _run(
        session,
        banks=(60, 90),
        thresholds=(0.9, 1.0),
        prize_fund_factors=(0.7, 1.0),
        surface_builder=_surface_builder(calls=calls),
    )

    assert calls == [1]
    assert len(rank_calls) == 2
    assert len(result.rows) == 8


def test_production_ranker_covers_complete_manageable_space_once_per_factor(
    monkeypatch,
):
    rank_calls = []
    materialize_calls = []

    def counted_production_rank(surface):
        rank_calls.append(surface.event_count)
        return production_rank_coupon_indices(surface)

    def counted_production_materialize(components, possible_winnings, jackpot):
        materialize_calls.append(possible_winnings)
        return production_materialize(components, possible_winnings, jackpot)

    monkeypatch.setattr(backtest_module, "rank_coupon_indices", counted_production_rank)
    monkeypatch.setattr(
        backtest_module,
        "materialize_ev_surface",
        counted_production_materialize,
    )
    components = EVComponents(
        possible_winnings_ev_per_ruble=np.linspace(0.001, 0.027, 3**3),
        jackpot_ev_per_ruble=np.zeros(3**3),
        event_count=3,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )
    ev_input = EVInput(
        drawing_id=1,
        drawing_number=1001,
        true_probabilities=((0.5, 0.3, 0.2),) * 3,
        crowd_probabilities=((0.4, 0.35, 0.25),) * 3,
        pool_sum=1_000_000.0,
        jackpot=0.0,
        possible_winnings=1_000_000.0,
        probability_sources=("totobrief_bk",) * 3,
        fetched_at="historical-db",
    )
    config = EVBacktestConfig(
        banks=(810,),
        thresholds=(0.0,),
        stake=30,
        prize_fund_factors=(0.7, 1.0),
    )

    pending = backtest_module._build_pending_packages(ev_input, components, config)

    assert materialize_calls == [700_000.0, 1_000_000.0]
    assert rank_calls == [3, 3]
    assert len(pending) == 2
    assert all(len(row.coupons) == 3**3 for row in pending)
    assert all(len(set(row.coupons)) == 3**3 for row in pending)


def test_threshold_selection_is_monotonic_and_respects_exact_bank_caps(session):
    _add_drawing(session, 1)
    result = _run(
        session,
        banks=(60, 90),
        thresholds=(0.90, 1.05, 1.20),
        surface_builder=_surface_builder((1.20, 1.10, 1.00, 0.95)),
    )

    for bank, cap in ((60, 2), (90, 3)):
        rows = [row for row in result.rows if row.bank == bank]
        assert [row.selected_coupons for row in rows] == [cap, 2, 1]
        assert all(row.cost <= bank for row in rows)
        assert all(row.unused_bank == bank - row.cost for row in rows)


def test_no_bet_rows_are_zero_cost_and_trigger_model_review(session):
    _add_drawing(session, 1)
    result = _run(
        session,
        banks=(60,),
        thresholds=(2.0,),
        surface_builder=_surface_builder((1.10,)),
    )

    row = result.rows[0]
    assert row.decision == "NO BET"
    assert row.selected_coupons == 0
    assert row.cost == 0
    assert row.unused_bank == 60
    assert row.package_expected_payout == 0.0
    assert row.package_modeled_roi is None
    assert row.best_hits is None
    assert not any(getattr(row, f"hit_{hits}") for hits in range(9, 16))
    assert result.summaries[0].skip_rate == 1.0
    assert result.summaries[0].model_review_required is True


@pytest.mark.parametrize(
    ("pool_sum", "decision", "supported"),
    [
        (3000.0, "PLAY", True),
        (2999.0, "NO BET", False),
    ],
)
def test_backtest_matches_live_self_dilution_boundary(
    session,
    pool_sum,
    decision,
    supported,
):
    _add_drawing(session, 1, pool_sum=pool_sum)

    result = _run(
        session,
        banks=(30,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,)),
    )

    row = result.rows[0]
    assert row.decision == decision
    assert row.model_supported is supported
    assert row.self_dilution_ratio == pytest.approx(30.0 / pool_sum)
    if supported:
        assert row.selected_coupons == 1
        assert row.cost == 30
    else:
        assert row.selected_coupons == 0
        assert row.cost == 0
        assert row.unused_bank == 30
        assert row.package_expected_payout == 0.0
        assert row.package_modeled_roi is None
        assert row.best_hits is None


def test_realized_best_hits_and_all_cumulative_indicators_are_recorded(session):
    _add_drawing(session, 1, results=("1",) * 15)
    result = _run(
        session,
        banks=(30,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,)),
    )

    row = result.rows[0]
    assert row.best_hits == 15
    assert all(getattr(row, f"hit_{hits}") for hits in range(9, 16))


def test_package_hashes_are_deterministic(session):
    _add_drawing(session, 1)

    first = _run(session, banks=(60,), thresholds=(1.0,))
    second = _run(session, banks=(60,), thresholds=(1.0,))

    assert [row.package_hash for row in first.rows] == [
        row.package_hash for row in second.rows
    ]


def test_checkpoint_contains_only_completed_drawings_and_resumes_exact_config(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    _add_drawing(session, 2)
    checkpoint = tmp_path / "ev.partial.csv"
    calls = []

    def interrupted_builder(ev_input, progress_callback=None):
        calls.append(ev_input.drawing_id)
        if ev_input.drawing_id == 1:
            raise KeyboardInterrupt("stop")
        return _surface_builder((1.10,))(ev_input, progress_callback)

    with pytest.raises(KeyboardInterrupt, match="stop"):
        _run(
            session,
            last=2,
            banks=(60,),
            thresholds=(1.0,),
            surface_builder=interrupted_builder,
            checkpoint_path=checkpoint,
        )

    with checkpoint.open(encoding="utf-8", newline="") as source:
        checkpoint_rows = list(csv.DictReader(source))
    completed_rows = [
        row for row in checkpoint_rows if row["record_type"] == "row"
    ]
    package_manifests = [
        row for row in checkpoint_rows if row["record_type"] == "package"
    ]
    assert {int(row["drawing_id"]) for row in completed_rows} == {2}
    assert package_manifests
    assert {
        row["package_hash"] for row in completed_rows
    } == {
        row["package_hash"] for row in package_manifests
    }

    resumed_calls = []
    result = _run(
        session,
        last=2,
        banks=(60,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,), calls=resumed_calls),
        checkpoint_path=checkpoint,
    )

    assert resumed_calls == [1]
    assert result.processed_drawing_ids == (1, 2)

    with pytest.raises(ValueError, match="configuration"):
        _run(
            session,
            last=2,
            banks=(90,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_same_config_resume_matches_uninterrupted_rows(session, tmp_path):
    _add_drawing(session, 1)
    _add_drawing(session, 2)
    uninterrupted = _run(
        session,
        last=2,
        banks=(60,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,)),
    )
    checkpoint = tmp_path / "resume.partial.csv"

    def interrupt_after_newest(ev_input, progress_callback=None):
        if ev_input.drawing_id == 1:
            raise KeyboardInterrupt("stop")
        return _surface_builder((1.10,))(ev_input, progress_callback)

    with pytest.raises(KeyboardInterrupt, match="stop"):
        _run(
            session,
            last=2,
            banks=(60,),
            thresholds=(1.0,),
            surface_builder=interrupt_after_newest,
            checkpoint_path=checkpoint,
        )
    resumed = _run(
        session,
        last=2,
        banks=(60,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,)),
        checkpoint_path=checkpoint,
    )

    assert resumed.rows == uninterrupted.rows
    assert resumed.processed_drawing_ids == uninterrupted.processed_drawing_ids


def test_checkpoint_skip_is_diagnostic_and_stale_skip_is_re_evaluated(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    incomplete = ["1"] * 15
    incomplete[-1] = None
    _add_drawing(session, 2, results=tuple(incomplete))
    checkpoint = tmp_path / "stale-skip.partial.csv"
    first = _run(
        session,
        last=1,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    assert first.processed_drawing_ids == (1,)
    assert first.skipped_drawing_ids == (2,)
    session.execute(
        update(Event)
        .where(Event.drawing_id == 2)
        .where(Event.event_order == 14)
        .values(result="1")
    )
    session.commit()

    resumed = _run(
        session,
        last=1,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )

    assert resumed.processed_drawing_ids == (2,)
    assert resumed.skipped_drawing_ids == ()


def test_checkpoint_rejects_duplicate_grid_combination(session, tmp_path):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "duplicate-grid.partial.csv"
    _run(
        session,
        banks=(60, 90),
        thresholds=(0.9, 1.05),
        checkpoint_path=checkpoint,
    )
    rows = _read_checkpoint(checkpoint)
    rows[1] = dict(rows[0])
    _write_checkpoint_rows(checkpoint, rows)

    with pytest.raises(ValueError, match="Cartesian grid"):
        _run(
            session,
            banks=(60, 90),
            thresholds=(0.9, 1.05),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_rejects_malformed_row_invariants(session, tmp_path):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "malformed.partial.csv"
    _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    rows = _read_checkpoint(checkpoint)
    rows[0]["cost"] = "1"
    _write_checkpoint_rows(checkpoint, rows)

    with pytest.raises(ValueError, match="cost"):
        _run(
            session,
            banks=(60,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_rejects_play_row_changed_to_empty_package_hash(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "empty-play-hash.partial.csv"
    _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    play_row = next(
        record
        for record in records
        if record["record_type"] == "row" and record["decision"] == "PLAY"
    )
    play_row["package_hash"] = backtest_module.EMPTY_PACKAGE_HASH
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="package"):
        _run(
            session,
            banks=(60,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_no_bet_references_only_empty_package_manifest(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "no-bet-package.partial.csv"
    result = _run(
        session,
        banks=(60,),
        thresholds=(2.0,),
        checkpoint_path=checkpoint,
    )

    records = _read_checkpoint(checkpoint)
    row = next(record for record in records if record["record_type"] == "row")
    manifests = [
        record for record in records if record["record_type"] == "package"
    ]

    assert row["decision"] == "NO BET"
    assert row["package_hash"] == backtest_module.EMPTY_PACKAGE_HASH
    assert len(manifests) == 1
    assert manifests[0]["package_hash"] == backtest_module.EMPTY_PACKAGE_HASH
    assert manifests[0]["coupon_payload"] == ""
    resumed = _run(
        session,
        banks=(60,),
        thresholds=(2.0,),
        checkpoint_path=checkpoint,
    )
    assert resumed.rows == result.rows


def test_checkpoint_rejects_coupon_payload_changed_without_hash_update(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "tampered-payload.partial.csv"
    _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    manifests = [
        record for record in records if record["record_type"] == "package"
    ]
    assert manifests
    payload = manifests[0]["coupon_payload"]
    replacement = "X" if payload[0] != "X" else "1"
    manifests[0]["coupon_payload"] = replacement + payload[1:]
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="package hash"):
        _run(
            session,
            banks=(60,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_rejects_equal_count_play_package_hash_swap(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    _add_drawing(session, 2)
    checkpoint = tmp_path / "swapped-package-hashes.partial.csv"

    def drawing_specific_surface(ev_input, progress_callback=None):
        del progress_callback
        values = (1.20, 0.80) if ev_input.drawing_id == 1 else (0.80, 1.20)
        return EVSurface(
            gross_ev=np.asarray(values, dtype=np.float64),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    _run(
        session,
        last=2,
        banks=(30,),
        thresholds=(1.0,),
        surface_builder=drawing_specific_surface,
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    play_rows = [
        record
        for record in records
        if record["record_type"] == "row" and record["decision"] == "PLAY"
    ]
    assert len(play_rows) == 2
    assert {row["selected_coupons"] for row in play_rows} == {"1"}
    first_hash = play_rows[0]["package_hash"]
    second_hash = play_rows[1]["package_hash"]
    assert first_hash != second_hash
    play_rows[0]["package_hash"] = second_hash
    play_rows[1]["package_hash"] = first_hash
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="context"):
        _run(
            session,
            last=2,
            banks=(30,),
            thresholds=(1.0,),
            surface_builder=drawing_specific_surface,
            checkpoint_path=checkpoint,
        )


@pytest.mark.parametrize(
    "tamper",
    ("duplicate", "missing", "extra", "unsorted"),
)
def test_checkpoint_rejects_noncanonical_or_mismatched_package_contexts(
    session,
    tmp_path,
    tamper,
):
    _add_drawing(session, 1)
    checkpoint = tmp_path / f"{tamper}-package-contexts.partial.csv"
    _run(
        session,
        banks=(30, 60),
        thresholds=(1.05,),
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    manifest = next(
        record for record in records if record["record_type"] == "package"
    )
    contexts = json.loads(manifest["row_contexts"])
    assert len(contexts) == 2
    if tamper == "duplicate":
        contexts.append(contexts[0])
    elif tamper == "missing":
        contexts.pop()
    elif tamper == "extra":
        contexts.append([999, 30, 1.05, 1.0])
        contexts.sort()
    else:
        contexts.reverse()
    manifest["row_contexts"] = json.dumps(contexts, separators=(",", ":"))
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="context"):
        _run(
            session,
            banks=(30, 60),
            thresholds=(1.05,),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_rejects_duplicate_package_manifest(session, tmp_path):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "duplicate-package.partial.csv"
    _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    manifest = next(
        record for record in records if record["record_type"] == "package"
    )
    records.append(dict(manifest))
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="duplicate"):
        _run(
            session,
            banks=(60,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_checkpoint_rejects_orphan_package_manifest(session, tmp_path):
    _add_drawing(session, 1)
    checkpoint = tmp_path / "orphan-package.partial.csv"
    _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        checkpoint_path=checkpoint,
    )
    records = _read_checkpoint(checkpoint)
    manifest = next(
        record for record in records if record["record_type"] == "package"
    )
    orphan = dict(manifest)
    orphan_coupons = ("2" * 15,)
    orphan["coupon_payload"] = ",".join(orphan_coupons)
    orphan["package_hash"] = backtest_module._package_hash(orphan_coupons)
    records.append(orphan)
    _write_checkpoint_rows(checkpoint, records)

    with pytest.raises(ValueError, match="orphan"):
        _run(
            session,
            banks=(60,),
            thresholds=(1.0,),
            checkpoint_path=checkpoint,
        )


def test_backtest_reports_are_deterministic_and_disclose_modeled_metrics(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    result = _run(
        session,
        banks=(60,),
        thresholds=(2.0,),
        surface_builder=_surface_builder((1.10,)),
    )

    first_paths = write_ev_backtest_reports(result, last=1, report_dir=tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first_paths)
    second_paths = write_ev_backtest_reports(result, last=1, report_dir=tmp_path)

    assert tuple(path.read_bytes() for path in second_paths) == first_bytes
    with first_paths[0].open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["package_expected_payout"] == "0.000000000000"
    assert rows[0]["package_modeled_roi"] == ""
    assert rows[0]["self_dilution_ratio"] == "0.000000000000"
    assert rows[0]["model_supported"] == "True"
    markdown = first_paths[1].read_text(encoding="utf-8")
    for expected in (
        "modeled payout uses expected crowd denominators",
        "not observed bookmaker payout",
        "modeled ROI is not observed ROI",
        "model_review_required=true",
        "NO BET",
        "self-dilution",
    ):
        assert expected in markdown


def test_final_and_checkpoint_paths_are_scoped_by_configuration_hash(
    session,
    tmp_path,
):
    _add_drawing(session, 1)
    first = _run(session, banks=(60,), thresholds=(1.0,))
    second = _run(session, banks=(90,), thresholds=(1.0,))
    third = _run(session, banks=(60,), thresholds=(1.05,))
    fourth = _run(
        session,
        banks=(60,),
        thresholds=(1.0,),
        forbidden_drawing_ids=frozenset({999}),
    )

    results = (first, second, third, fourth)
    report_paths = {
        ev_backtest_report_paths(result, 1, tmp_path)[0] for result in results
    }
    checkpoint_paths = {
        backtest_module.ev_backtest_checkpoint_path(
            result.configuration_hash,
            last=1,
            stake=30,
            report_dir=tmp_path,
        )
        for result in results
    }

    assert len(report_paths) == 4
    assert len(checkpoint_paths) == 4
    first_report = ev_backtest_report_paths(first, 1, tmp_path)[0]
    first_checkpoint = backtest_module.ev_backtest_checkpoint_path(
        first.configuration_hash,
        last=1,
        stake=30,
        report_dir=tmp_path,
    )
    assert first.configuration_hash in first_report.name
    assert first.configuration_hash in first_checkpoint.name


def test_backtest_cli_value_parsing_is_deterministic():
    assert _parse_csv_ints("4800, 6000,9600", "banks") == (4800, 6000, 9600)
    assert _parse_csv_floats("0.90,0.95,1.00,1.05", "thresholds") == (
        0.9,
        0.95,
        1.0,
        1.05,
    )
    with pytest.raises(ValueError, match="duplicate"):
        _parse_csv_ints("4800,4800", "banks")
    with pytest.raises(ValueError, match="empty"):
        _parse_csv_floats("0.9,,1.0", "thresholds")


def test_backtest_ev_help_requires_frozen_manifest():
    result = runner.invoke(app, ["backtest-ev", "--help"])

    assert result.exit_code == 0
    for option in (
        "--db",
        "--last",
        "--banks",
        "--thresholds",
        "--stake",
        "--frozen-manifest",
    ):
        assert option in result.output
    assert "required" in result.output.lower()


def _read_checkpoint(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _write_checkpoint_rows(path, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def _bound_integer_parameters(parameters):
    if isinstance(parameters, dict):
        values = parameters.values()
    elif isinstance(parameters, (list, tuple)):
        values = parameters
    else:
        values = (parameters,)
    return tuple(value for value in values if type(value) is int)


def _touches_event_or_quote(statement):
    return bool(_referenced_event_or_quote_tables(statement))


def _referenced_event_or_quote_tables(statement):
    return {
        match.group(1).lower()
        for match in re.finditer(
            r'\b(?:from|join)\s+(?:"?\w+"?\.)?"?(events|quotes)"?\b',
            statement,
            flags=re.IGNORECASE,
        )
    }


def _drawing_id_relation_tables(statement):
    if not re.search(
        r"\b(?:events\.drawing_id\s*=\s*quotes\.drawing_id|"
        r"quotes\.drawing_id\s*=\s*events\.drawing_id)\b",
        statement,
        flags=re.IGNORECASE,
    ):
        return set()
    return {"events", "quotes"}


def _bound_drawing_id_parameter(statement, parameters):
    matches = tuple(
        re.finditer(
            r"\b(events|quotes)\.drawing_id\s*=\s*\?",
            statement,
            flags=re.IGNORECASE,
        )
    )
    assert len(matches) == 1, (
        "Event/Quote SQL must have exactly one bound events.drawing_id or "
        "quotes.drawing_id predicate"
    )
    scoped_tables = {
        matches[0].group(1).lower(),
        *_drawing_id_relation_tables(statement),
    }
    missing_tables = (
        _referenced_event_or_quote_tables(statement) - scoped_tables
    )
    assert not missing_tables, (
        "Event/Quote SQL lacks required drawing-ID scope for "
        + ", ".join(
            f"{table}.drawing_id" for table in sorted(missing_tables)
        )
    )
    values = (
        tuple(parameters.values())
        if isinstance(parameters, dict)
        else tuple(parameters)
    )
    parameter_index = statement[: matches[0].end()].count("?") - 1
    assert 0 <= parameter_index < len(values)
    return values[parameter_index]
