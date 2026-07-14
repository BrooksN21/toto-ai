import csv
import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from sqlalchemy import create_engine, event
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
from toto_ai.ev.models import EVSurface
from toto_ai.ev.reports import write_ev_backtest_reports

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
):
    number = number if number is not None else 1000 + drawing_id
    results = results if results is not None else ("1",) * event_count
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status="finished",
            pool_sum=1_000_000.0,
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
    queried_ids = []

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
        if "events" in statement.lower() or "quotes" in statement.lower():
            queried_ids.extend(
                value for value in parameters if isinstance(value, int)
            )

    result = _run(
        session,
        last=3,
        forbidden_drawing_ids=frozenset({4}),
    )

    assert result.drawing_ids == (1, 2, 3)
    assert 4 not in queried_ids


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
        if ev_input.drawing_id == 2:
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
    assert {int(row["drawing_id"]) for row in checkpoint_rows} == {1}

    resumed_calls = []
    result = _run(
        session,
        last=2,
        banks=(60,),
        thresholds=(1.0,),
        surface_builder=_surface_builder((1.10,), calls=resumed_calls),
        checkpoint_path=checkpoint,
    )

    assert resumed_calls == [2]
    assert result.processed_drawing_ids == (1, 2)

    with pytest.raises(ValueError, match="configuration"):
        _run(
            session,
            last=2,
            banks=(90,),
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
    markdown = first_paths[1].read_text(encoding="utf-8")
    for expected in (
        "modeled payout uses expected crowd denominators",
        "not observed bookmaker payout",
        "modeled ROI is not observed ROI",
        "model_review_required=true",
        "NO BET",
    ):
        assert expected in markdown


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
