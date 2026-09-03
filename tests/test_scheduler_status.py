import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from toto_ai.operations.scheduler_status import (
    scheduler_status,
    watch_scheduler_status,
)
from toto_ai.runner.scheduler import (
    SchedulerPlan,
    build_scheduler_plan,
    prepare_scheduler_artifacts,
)


def _plan(tmp_path: Path) -> SchedulerPlan:
    root = tmp_path.resolve()
    output = root / "evening"
    output.mkdir()
    ledger = root / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-09-02T00:00:00Z",
                "observations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    aliases = root / "aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    database = root / "toto.db"
    database.write_bytes(b"")
    return SchedulerPlan(
        drawing=4995,
        drawing_id=12092,
        ended_at=datetime(2026, 9, 3, 15, 55, tzinfo=timezone.utc),
        requested_bank=4980,
        output_dir=output,
        project_root=root,
        db=database,
        aliases=aliases,
        schedule_evidence_ledger=ledger,
    )


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_new_plan_uses_immutable_schedule_evidence_snapshot(tmp_path):
    root = tmp_path.resolve()
    output = root / "evening"
    ledger = root / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-09-02T00:00:00Z",
                "observations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    aliases = root / "aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    database = root / "toto.db"
    database.write_bytes(b"")

    source_plan = build_scheduler_plan(
        drawing=4995,
        drawing_id=12092,
        ended_at=datetime(2026, 9, 3, 15, 55, tzinfo=timezone.utc),
        bank=4980,
        output_dir=output,
        project_root=root,
        db=database,
        aliases=aliases,
        schedule_evidence_ledger=ledger,
    )
    plan = prepare_scheduler_artifacts(source_plan).plan

    assert plan.schedule_evidence_ledger != ledger.resolve()
    assert plan.schedule_evidence_ledger.parent.parent.name == "bindings"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-09-03T00:00:00Z",
                "observations": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = scheduler_status(
        plan,
        observed_at=datetime(2026, 9, 3, 13, 30, tzinfo=timezone.utc),
    )

    assert result["drawing_number"] == 4995
    assert result["mutated"] is False


def test_status_before_first_checkpoint_is_pending_and_read_only(tmp_path):
    plan = _plan(tmp_path)

    result = scheduler_status(
        plan,
        observed_at=datetime(2026, 9, 3, 13, 30, tzinfo=timezone.utc),
    )

    assert result["last_phase"] == "scheduled"
    assert result["primary_quality_v2"] == {"status": "pending", "reason": None}
    assert result["next_checkpoint"] == {
        "phase": "t_minus_120",
        "at_msk": "2026-09-03T16:55:00+03:00",
    }
    assert result["operator_result_ready"] is False
    assert result["terminal"] is False
    assert result["mutated"] is False


def test_status_reports_exact_failed_attempt(tmp_path):
    plan = _plan(tmp_path)
    status_path = plan.output_dir / "attempts" / "preflight-01" / "status.json"
    _write(
        status_path,
        {
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "run_id": "preflight-01-test",
            "state": "failed",
            "outcome": "error",
            "error": "source timeout",
            "completed_at": "2026-09-03T15:06:00Z",
        },
    )

    result = scheduler_status(
        plan,
        observed_at=datetime(2026, 9, 3, 15, 7, tzinfo=timezone.utc),
    )

    assert result["last_phase"] == "preflight"
    assert result["primary_quality_v2"]["status"] == "error"
    assert result["blocker"] == "source timeout"
    assert result["last_attempt"]["run_id"] == "preflight-01-test"


def test_status_reports_all_models_selection_and_computed_best_coupon(tmp_path):
    plan = _plan(tmp_path)
    run = plan.output_dir / "parallel-challenger" / "output" / "run-final"
    comparison_path = run / "research-comparison" / "comparison.json"
    _write(
        comparison_path,
        {
            "plan_id": plan.plan_id,
            "drawing_number": plan.drawing,
            "experimental_selection": {
                "candidates": [
                    {
                        "strategy_id": "quality-v2",
                        "coupon_count": 166,
                        "cost": 4980,
                        "maximum_outcome_share": 0.75,
                    },
                    {
                        "strategy_id": "sports-shadow",
                        "coupon_count": 166,
                        "cost": 4980,
                        "maximum_outcome_share": 0.74,
                    },
                    {
                        "strategy_id": "quality-v3",
                        "coupon_count": 166,
                        "cost": 4980,
                        "maximum_outcome_share": 0.88,
                    },
                    {
                        "strategy_id": "robust",
                        "coupon_count": 166,
                        "cost": 4980,
                        "maximum_outcome_share": 0.89,
                    },
                ],
                "rejections": {
                    "quality-v3": ["concentration_above_control"],
                    "robust": ["concentration_above_control"],
                },
                "selected_strategy_id": "sports-shadow",
            },
            "highest_p13_single_coupons": {
                "sports-shadow": {
                    "coupon": "1" * 15,
                    "criterion": "maximum_probability_at_least_13",
                    "package_position": 12,
                    "probability_at_least_13": 0.0003,
                    "reference_model": "sports",
                }
            },
        },
    )
    _write(
        plan.output_dir
        / "parallel-challenger"
        / "output"
        / "sidecar-status.json",
        {
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "status": "READY_PARALLEL_PLAY_BEFORE_T10",
            "research_report": str(comparison_path),
            "parallel_release": {
                "selected_strategy_id": "sports-shadow",
                "highest_p13_single_coupon": {
                    "coupon": "1" * 15,
                    "criterion": "maximum_probability_at_least_13",
                    "package_position": 12,
                    "probability_at_least_13": 0.0003,
                    "reference_model": "sports",
                },
            },
        },
    )
    _write(
        plan.output_dir / "operator-result.json",
        {
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "operator_status": "PLAY",
            "decision": "PLAY",
            "actionable": True,
            "reason": "ready",
            "coupon_path": str(plan.output_dir / "operator-package.txt"),
            "package_sha256": "a" * 64,
            "selected_count": 166,
            "selected_cost": 4980,
            "completed_at": "2026-09-03T15:30:00Z",
        },
    )

    result = scheduler_status(
        plan,
        observed_at=datetime(2026, 9, 3, 15, 31, tzinfo=timezone.utc),
    )

    assert result["selected_strategy"] == "sports-shadow"
    assert result["challengers"]["quality-v3"] == {
        "status": "rejected",
        "reasons": ["concentration_above_control"],
        "coupon_count": 166,
        "cost": 4980,
        "maximum_outcome_share": 0.88,
    }
    assert result["challengers"]["sports-shadow"]["status"] == "eligible"
    assert result["highest_p13_single_coupon"] == {
        "coupon": "1" * 15,
        "criterion": "maximum_probability_at_least_13",
        "package_position": 12,
        "probability_at_least_13": 0.0003,
        "reference_model": "sports",
        "strategy_id": "sports-shadow",
    }
    assert result["operator_result_ready"] is True
    assert result["terminal"] is True


def test_status_rejects_cross_plan_artifact(tmp_path):
    plan = _plan(tmp_path)
    _write(
        plan.output_dir / "operator-result.json",
        {"plan_id": "wrong", "drawing": plan.drawing},
    )

    with pytest.raises(ValueError, match="plan mismatch"):
        scheduler_status(plan)


def test_watcher_writes_latest_and_only_state_changes(tmp_path):
    plan = _plan(tmp_path)
    statuses = iter(
        (
            {"observed_at_msk": "one", "terminal": False, "state": "pending"},
            {"observed_at_msk": "two", "terminal": False, "state": "pending"},
            {"observed_at_msk": "three", "terminal": True, "state": "PLAY"},
        )
    )
    sleeps: list[float] = []
    latest = plan.output_dir / "watcher" / "latest.json"
    history = plan.output_dir / "watcher" / "history.jsonl"

    result = watch_scheduler_status(
        plan,
        latest_path=latest,
        history_path=history,
        interval_seconds=5,
        status_provider=lambda _: next(statuses),
        sleep=sleeps.append,
    )

    assert result["state"] == "PLAY"
    assert json.loads(latest.read_text())["observed_at_msk"] == "three"
    rows = [json.loads(row) for row in history.read_text().splitlines()]
    assert [row["state"] for row in rows] == ["pending", "PLAY"]
    assert sleeps == [5, 5]


def test_watcher_rejects_output_outside_plan(tmp_path):
    plan = _plan(tmp_path)

    with pytest.raises(ValueError, match="inside scheduler output"):
        watch_scheduler_status(
            plan,
            latest_path=tmp_path / "outside.json",
            history_path=plan.output_dir / "history.jsonl",
            max_iterations=1,
        )
