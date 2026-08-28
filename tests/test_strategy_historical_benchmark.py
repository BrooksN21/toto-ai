import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from toto_ai.collector.lifecycle import RawArchive
from toto_ai.db.models import (
    Drawing,
    DrawingRawSnapshot,
    DrawingResultSnapshot,
    Event,
    Quote,
)
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.models import EVConfig
from toto_ai.optimizer.strategy_comparison import (
    StrategyComparisonBundle,
    StrategyResult,
)
from toto_ai.optimizer.strategy_historical_benchmark import (
    StrictHistoricalCase,
    benchmark_strict_historical_cases,
    frozen_input_from_raw_payload,
    historical_ev_config,
    load_strict_historical_cases,
    package_overlap,
    paired_bootstrap_interval,
    score_coupon_package,
    write_strict_historical_benchmark_reports,
)


def test_paired_bootstrap_interval_is_deterministic_and_small_sample_guarded():
    first = paired_bootstrap_interval(
        (1, -1, 2, 0),
        drawing_count=4,
        seed=123,
        replicates=1_000,
    )
    second = paired_bootstrap_interval(
        (1, -1, 2, 0),
        drawing_count=4,
        seed=123,
        replicates=1_000,
    )

    assert first == second
    assert first["mean_difference"] == 0.5
    assert first["interpretation_allowed"] is False
    with pytest.raises(ValueError, match="drawing count mismatch"):
        paired_bootstrap_interval((1, 2), drawing_count=3)


def test_strict_loader_uses_latest_predeadline_raw_not_mutable_db_quotes(tmp_path):
    db_path, factory = _database(tmp_path)
    deadline = "2030-01-01T00:00:00+00:00"
    actual = "1X2" * 5
    with factory.begin() as session:
        _add_complete_drawing(
            session,
            drawing_id=1,
            number=100,
            deadline=deadline,
            actual=actual,
            db_bk=(1.0, 1.0, 98.0),
        )
        older = _add_raw_snapshot(
            session,
            db_path=db_path,
            drawing_id=1,
            number=100,
            deadline=deadline,
            captured_at="2029-12-31T23:40:00+00:00",
            bk=(50.0, 30.0, 20.0),
            pool=(45.0, 35.0, 20.0),
        )
        selected = _add_raw_snapshot(
            session,
            db_path=db_path,
            drawing_id=1,
            number=100,
            deadline=deadline,
            captured_at="2029-12-31T23:50:00+00:00",
            bk=(70.0, 20.0, 10.0),
            pool=(60.0, 25.0, 15.0),
        )
        _add_raw_snapshot(
            session,
            db_path=db_path,
            drawing_id=1,
            number=100,
            deadline=deadline,
            captured_at="2030-01-01T00:01:00+00:00",
            bk=(10.0, 20.0, 70.0),
            pool=(15.0, 25.0, 60.0),
        )
        _add_result_snapshot(
            session,
            drawing_id=1,
            number=100,
            deadline=deadline,
            actual=actual,
            raw_snapshot_sha256=selected.snapshot_sha256,
        )

    with factory() as session:
        cases = load_strict_historical_cases(
            session,
            db_path=db_path,
            last=1,
            bank=4980,
            stake=30,
        )

    assert len(cases) == 1
    case = cases[0]
    assert case.raw_snapshot_sha256 == selected.snapshot_sha256
    assert case.raw_snapshot_sha256 != older.snapshot_sha256
    assert case.frozen_input.source_captured_at == "2029-12-31T23:50:00.000000Z"
    assert case.frozen_input.as_of == "2029-12-31T23:50:00.000000Z"
    assert case.frozen_input.bk_probability_matrix[0] == (0.7, 0.2, 0.1)
    assert case.frozen_input.crowd_probability_matrix[0] == pytest.approx(
        (0.6, 0.25, 0.15),
        abs=2e-5,
    )
    assert case.actual == actual
    assert case.staleness_seconds == 600.0


def test_strict_loader_prediction_hash_ignores_raw_result_fields(tmp_path):
    deadline = "2030-01-01T00:00:00+00:00"
    payload = _raw_payload(
        drawing_id=1,
        number=100,
        deadline=deadline,
        bk=(50.0, 30.0, 20.0),
        pool=(45.0, 35.0, 20.0),
        embedded_result="2",
    )
    changed = deepcopy(payload)
    for event in changed["data"]["events"]:
        event["result"] = "1"
        event["score"] = "99:0"

    first = frozen_input_from_raw_payload(
        payload,
        captured_at="2029-12-31T23:50:00+00:00",
        bank=4980,
        stake=30,
    )
    second = frozen_input_from_raw_payload(
        changed,
        captured_at="2029-12-31T23:50:00+00:00",
        bank=4980,
        stake=30,
    )

    assert first.input_sha256 == second.input_sha256


def test_package_score_counts_void_as_correct_and_reports_actual_exposure():
    score = score_coupon_package(
        strategy_id="TEST",
        coupons=("1" * 15, "2" * 15),
        actual="1" * 14 + "*",
    )

    assert score.best_hits == 15
    assert score.average_hits == 8.0
    assert score.median_hits == 8.0
    assert score.hit_distribution == ((1, 1), (15, 1))
    assert score.category_counts == (
        (10, 0),
        (11, 0),
        (12, 0),
        (13, 0),
        (14, 0),
        (15, 1),
    )
    assert score.actual_outcome_exposure[:14] == (0.5,) * 14
    assert score.actual_outcome_exposure[14] == 1.0
    assert score.zero_exposure_event_orders == ()


def test_package_overlap_uses_unique_coupon_sets():
    overlap = package_overlap(("111", "222"), ("222", "XXX"))

    assert overlap.intersection_count == 1
    assert overlap.union_count == 3
    assert overlap.jaccard == 1 / 3


def test_historical_ev_config_preserves_objective_but_uses_requested_budget():
    production = EVConfig(
        bank=4_980,
        stake=30,
        mode="playable",
        effective_budget=4_980,
        package_safety_enabled=True,
        package_quality_candidate_count=777,
        package_probability_samples=999,
        package_provenance_required=True,
    )

    research = historical_ev_config(production, bank=9_960, stake=30)

    assert research.bank == 9_960
    assert research.stake == 30
    assert research.effective_budget == 9_960
    assert research.mode == "research"
    assert research.package_provenance_required is False
    assert research.package_safety_enabled is True
    assert research.package_quality_candidate_count == 777
    assert research.package_probability_samples == 999


def test_strict_benchmark_scores_actuals_and_reports_pairwise_overlap(tmp_path):
    frozen = frozen_input_from_raw_payload(
        _raw_payload(
            drawing_id=1,
            number=100,
            deadline="2030-01-01T00:00:00+00:00",
            bk=(50.0, 30.0, 20.0),
            pool=(45.0, 35.0, 20.0),
            embedded_result="",
        ),
        captured_at="2029-12-31T23:50:00+00:00",
        bank=120,
        stake=30,
    )
    historical_case = StrictHistoricalCase(
        frozen_input=frozen,
        actual="1" * 15,
        raw_snapshot_sha256="a" * 64,
        result_snapshot_sha256="b" * 64,
        staleness_seconds=600.0,
    )

    def comparison_runner(case_input, *, ev_config, provenance):
        assert case_input is frozen
        assert ev_config.bank == 120
        assert provenance is None
        return _comparison_bundle(case_input)

    benchmark = benchmark_strict_historical_cases(
        (historical_case,),
        ev_config=EVConfig(bank=120, stake=30, mode="research"),
        comparison_runner=comparison_runner,
    )

    assert benchmark.summary["drawings_evaluated"] == 1
    assert benchmark.summary["evidence_tier"] == (
        "STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE"
    )
    assert benchmark.summary["winner_status"] == "INCONCLUSIVE_SMALL_SAMPLE"
    assert len(benchmark.rows) == 5
    by_strategy = {row.strategy_id: row for row in benchmark.rows}
    assert by_strategy["EV_CROWD_CURRENT"].best_hits == 15
    assert by_strategy["BK_PROBABILITY_ONLY"].best_hits == 14
    assert by_strategy["EV_CROWD_CURRENT"].bk_top_coupon == "1" * 15
    assert by_strategy["EV_CROWD_CURRENT"].bk_top_hits == 15
    assert benchmark.summary["bk_top_control"]["average_hits"] == 15
    ev_delta = benchmark.summary["paired_best_hits_vs_bk_probability_only"][
        "EV_CROWD_CURRENT"
    ]
    assert ev_delta["mean_difference"] == 1
    assert ev_delta["ci_95_lower"] == 1
    assert ev_delta["ci_95_upper"] == 1
    assert ev_delta["interpretation_allowed"] is False
    assert by_strategy["EV_CROWD_CURRENT"].hit_15 is True
    assert by_strategy["BK_PROBABILITY_ONLY"].hit_15 is False
    assert by_strategy["TOTOBRIEF_STYLE_COVER_13"].zero_exposure_event_orders == ()
    assert len(benchmark.overlaps) == 10
    ev_bk = next(
        row
        for row in benchmark.overlaps
        if row.left_strategy_id == "EV_CROWD_CURRENT"
        and row.right_strategy_id == "BK_PROBABILITY_ONLY"
    )
    assert ev_bk.intersection_count == 1
    assert ev_bk.union_count == 3

    paths = write_strict_historical_benchmark_reports(benchmark, tmp_path)

    payload = json.loads(paths.json.read_text())
    manifest = json.loads(paths.manifest.read_text())
    assert payload["summary"]["drawings_evaluated"] == 1
    assert payload["actionable"] is False
    markdown = paths.markdown.read_text()
    assert "NOT RELEASE EVIDENCE" in markdown
    assert "Paired best-hits difference vs BK probability-only package" in markdown
    assert "Interpretation allowed" in markdown
    assert manifest["evidence_tier"] == (
        "STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE"
    )
    assert manifest["automatic_wagering"] is False
    assert paths.rows_csv.read_text().count("\n") == 6
    assert paths.overlaps_csv.read_text().count("\n") == 11


def test_historical_strategy_benchmark_cli_help():
    from typer.testing import CliRunner

    from toto_ai.cli import app

    result = CliRunner().invoke(app, ["historical-strategy-benchmark", "--help"])

    assert result.exit_code == 0
    assert "--scheduler-plan" in result.stdout
    assert "--last" in result.stdout
    assert "--bank" in result.stdout


def _database(tmp_path: Path):
    path = tmp_path / "data" / "toto.db"
    engine = init_db(path)
    return path, get_session_factory(engine)


def _add_complete_drawing(
    session: Session,
    *,
    drawing_id: int,
    number: int,
    deadline: str,
    actual: str,
    db_bk: tuple[float, float, float],
) -> None:
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status="finished",
            pool_sum=1_000_000.0,
            jackpot=2_000_000.0,
            ended_at=deadline,
        )
    )
    for order, result in enumerate(actual):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=order,
                name=f"Home {order} — Away {order}",
                championship="Test league",
                sport="football",
                result=result,
                result_status="void" if result == "*" else "resolved",
                score=None,
            )
        )
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=order,
                pool_win_1=40.0,
                pool_draw=30.0,
                pool_win_2=30.0,
                bk_win_1=db_bk[0],
                bk_draw=db_bk[1],
                bk_win_2=db_bk[2],
            )
        )


def _add_raw_snapshot(
    session: Session,
    *,
    db_path: Path,
    drawing_id: int,
    number: int,
    deadline: str,
    captured_at: str,
    bk: tuple[float, float, float],
    pool: tuple[float, float, float],
    embedded_result: str = "",
) -> DrawingRawSnapshot:
    payload = _raw_payload(
        drawing_id=drawing_id,
        number=number,
        deadline=deadline,
        bk=bk,
        pool=pool,
        embedded_result=embedded_result,
    )
    record = RawArchive(db_path.parent / "raw" / "archive").archive(
        payload,
        captured_at=datetime.fromisoformat(captured_at),
        source="test",
        lifecycle_status="active",
        source_endpoint=f"/drawing-info/{drawing_id}",
    )
    row = DrawingRawSnapshot(
        snapshot_sha256=record.snapshot_sha256,
        payload_sha256=record.payload_sha256,
        metadata_sha256=record.metadata_sha256,
        drawing_id=drawing_id,
        drawing_number=number,
        captured_at=record.captured_at,
        source=record.source,
        source_endpoint=record.source_endpoint,
        lifecycle_status=record.lifecycle_status,
        payload_path=str(record.payload_path),
        metadata_path=str(record.metadata_path),
        imported_at=record.captured_at,
        classification="source_incomplete",
    )
    session.add(row)
    return row


def _raw_payload(
    *,
    drawing_id: int,
    number: int,
    deadline: str,
    bk: tuple[float, float, float],
    pool: tuple[float, float, float],
    embedded_result: str,
) -> dict[str, object]:
    return {
        "version": "1.0",
        "data": {
            "id": drawing_id,
            "number": number,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": deadline,
            "pool_sum": 1_000_000,
            "jackpot": 2_000_000,
            "events": [
                {
                    "id": drawing_id * 100 + order,
                    "order": order,
                    "name": f"Home {order} — Away {order}",
                    "championship": "Test league",
                    "start_at": None,
                    "result": embedded_result,
                    "score": "1:0" if embedded_result else "",
                    "quotes": {
                        "bk_win_1": bk[0],
                        "bk_draw": bk[1],
                        "bk_win_2": bk[2],
                        "pool_win_1": pool[0],
                        "pool_draw": pool[1],
                        "pool_win_2": pool[2],
                    },
                }
                for order in range(15)
            ],
        },
    }


def _add_result_snapshot(
    session: Session,
    *,
    drawing_id: int,
    number: int,
    deadline: str,
    actual: str,
    raw_snapshot_sha256: str,
) -> None:
    session.add(
        DrawingResultSnapshot(
            drawing_id=drawing_id,
            drawing_number=number,
            hash_schema_version=3,
            ended_at=deadline,
            retrieved_at="2030-01-02T00:00:00+00:00",
            source_endpoint=f"/drawing-info/{drawing_id}",
            payload_sha256=f"result-payload-{drawing_id}",
            raw_snapshot_sha256=raw_snapshot_sha256,
            result_sha256=f"result-{drawing_id}",
            snapshot_sha256=f"result-snapshot-{drawing_id}",
            complete=True,
            event_count=15,
            actual=actual,
            events_json="[]",
            payload_json="{}",
        )
    )


def _comparison_bundle(frozen):
    shared = "1" * 15
    ev = _strategy_result(
        frozen,
        "EV_CROWD_CURRENT",
        (shared, "X" + "1" * 14),
    )
    bk = _strategy_result(
        frozen,
        "BK_PROBABILITY_ONLY",
        ("X" + "1" * 14, "2" + "1" * 14),
    )
    cover_13 = _strategy_result(
        frozen,
        "TOTOBRIEF_STYLE_COVER_13",
        (shared,),
    )
    cover_14 = _strategy_result(
        frozen,
        "TOTOBRIEF_STYLE_COVER_14",
        ("X" * 15,),
        category=14,
    )
    cover_14_bk_fill = _strategy_result(
        frozen,
        "COVER_14_BK_FILL",
        ("2" * 15,),
        category=14,
    )
    return StrategyComparisonBundle(
        frozen_input=frozen,
        results=(ev, bk, cover_13, cover_14, cover_14_bk_fill),
    )


def _strategy_result(frozen, strategy_id, coupons, *, category=13):
    import hashlib

    package_sha256 = hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode()
    ).hexdigest()
    return StrategyResult(
        strategy_id=strategy_id,
        strategy_version="v1",
        source_engine="test",
        category=category,
        input_sha256=frozen.input_sha256,
        config_sha256="c" * 64,
        package_sha256=package_sha256,
        requested_bank=frozen.bank,
        stake=frozen.stake,
        coupons=tuple(coupons),
        cost=len(coupons) * frozen.stake,
        unused_bank=frozen.bank - len(coupons) * frozen.stake,
        probability_at_least_13=0.1,
        probability_at_least_14=0.05,
        probability_at_least_15=0.01,
        runtime_seconds=0.01,
        timed_out=False,
    )
