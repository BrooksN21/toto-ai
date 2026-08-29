from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
)
from toto_ai.sports_stats import final_hybrid_comparison, final_hybrid_sidecar
from toto_ai.sports_stats.final_hybrid_sidecar import run_final_hybrid_sidecar

UTC = timezone.utc


def test_rebase_uses_final_bk_and_event_local_fallback() -> None:
    frozen = FrozenStrategyInput(
        drawing_id=1,
        drawing_number=2,
        drawing_fingerprint="a" * 64,
        source_captured_at="2026-08-28T10:00:00Z",
        as_of="2026-08-28T10:00:00Z",
        ended_at="2026-08-28T18:00:00Z",
        bank=4980,
        stake=30,
        pool_sum=1.0,
        jackpot=0.0,
        possible_winnings=1.0,
        events=tuple(
            FrozenStrategyEvent(
                event_order=order,
                name=f"Event {order + 1}",
                bk_probabilities=(0.5, 0.3, 0.2),
                crowd_probabilities=(0.4, 0.3, 0.3),
            )
            for order in range(15)
        ),
    )
    sports = tuple(
        SimpleNamespace(
            event_order=order,
            blend_weight=0.5,
            fallback_reason="missing" if order == 1 else None,
            sports_probabilities=(0.2, 0.3, 0.5),
        )
        for order in range(15)
    )

    rows = final_hybrid_comparison._rebase_sports_probabilities(frozen, sports)

    assert rows[0] == (0.35, 0.3, 0.35)
    assert rows[1] == (0.5, 0.3, 0.2)


def test_sidecar_skips_when_operator_is_not_ready_before_safe_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    observed = datetime(2026, 8, 28, 14, 46, tzinfo=UTC)
    plan = SimpleNamespace(
        output_dir=tmp_path / "scheduler",
        publish_deadline=observed + timedelta(seconds=200),
        plan_id="plan",
        drawing=4989,
        drawing_id=12074,
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)

    result = run_final_hybrid_sidecar(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_root=tmp_path / "sidecar",
        wait_seconds=0,
        minimum_runtime_seconds=240,
        now=lambda: observed,
        sleeper=lambda _: None,
    )

    assert result.status == "SKIPPED_OPERATOR_NOT_READY"
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert payload["automatic_wagering"] is False


def test_sidecar_binds_recomputed_baseline_to_operator_package(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    observed = datetime(2026, 8, 28, 14, 40, tzinfo=UTC)
    scheduler = tmp_path / "scheduler"
    run_dir = scheduler / "attempts" / "run-1"
    run_dir.mkdir(parents=True)
    source = run_dir / "package.csv"
    source.write_text("source", encoding="utf-8")
    (run_dir / "final-input.json").write_text("{}", encoding="utf-8")
    operator = {
        "plan_id": "plan",
        "drawing": 4989,
        "drawing_id": 12074,
        "decision": "PLAY",
        "actionable": True,
        "run_id": "run-1",
        "source_package_path": str(source),
    }
    (scheduler / "operator-result.json").write_text(
        json.dumps(operator),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        output_dir=scheduler,
        publish_deadline=observed + timedelta(minutes=10),
        plan_id="plan",
        drawing=4989,
        drawing_id=12074,
        stake=30,
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)

    coupon = "1" * 15

    def fake_export(_plan, *, destination, observed_at):
        path = Path(destination)
        path.write_text("30; " + "; ".join(coupon) + "\n", encoding="utf-8")
        return path

    def fake_compare(**kwargs):
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        report = output / "comparison.json"
        baseline = output / "baseline.txt"
        sports = output / "sports.txt"
        snapshot = output / "probabilities.json"
        robust = output / "robust.txt"
        report.write_text("{}", encoding="utf-8")
        baseline.write_text(
            "RESEARCH ONLY\n" + coupon + "\n",
            encoding="utf-8",
        )
        sports.write_text("RESEARCH ONLY\n" + "2" * 15 + "\n", encoding="utf-8")
        robust.write_text("RESEARCH ONLY\n" + "X" * 15 + "\n", encoding="utf-8")
        snapshot.write_text("{}", encoding="utf-8")
        return (
            {"sports_coverage_count": 10, "sports_fallback_count": 5},
            SimpleNamespace(
                report=report,
                baseline_package=baseline,
                sports_package=sports,
                robust_package=robust,
                sports_probability_snapshot=snapshot,
            ),
        )

    monkeypatch.setattr(final_hybrid_sidecar, "export_operator_package", fake_export)
    monkeypatch.setattr(
        final_hybrid_sidecar,
        "execute_final_hybrid_comparison",
        fake_compare,
    )

    result = run_final_hybrid_sidecar(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_root=tmp_path / "sidecar",
        wait_seconds=0,
        minimum_runtime_seconds=240,
        now=lambda: observed,
        sleeper=lambda _: None,
    )

    assert result.status == "READY_BEFORE_T10"
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert payload["baseline_matches_operator"] is True
    assert payload["sports_operator_compatible"] is False


def test_sidecar_builds_research_comparison_from_final_input_after_no_bet(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    final_input = tmp_path / "scheduler" / "attempts" / "final-1" / "final-input.json"
    final_input.parent.mkdir(parents=True)
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    final_input.write_text("{}", encoding="utf-8")
    observed = datetime(2026, 8, 28, 14, 40, tzinfo=UTC)
    scheduler_dir = tmp_path / "scheduler"
    (scheduler_dir / "operator-result.json").write_text(
        json.dumps({"decision": "NO BET", "reason": "release gate closed"}),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        output_dir=scheduler_dir,
        publish_deadline=observed + timedelta(minutes=10),
        plan_id="plan",
        drawing=4989,
        drawing_id=12074,
        stake=30,
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    monkeypatch.setattr(
        final_hybrid_sidecar,
        "_latest_final_input",
        lambda _: final_input,
    )

    def fake_compare(**kwargs):
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        report = output / "comparison.json"
        baseline = output / "baseline.txt"
        sports = output / "sports.txt"
        robust = output / "robust.txt"
        snapshot = output / "probabilities.json"
        for path in (report, baseline, sports, robust, snapshot):
            path.write_text("{}", encoding="utf-8")
        return (
            {"sports_coverage_count": 10, "sports_fallback_count": 5},
            SimpleNamespace(
                report=report,
                baseline_package=baseline,
                sports_package=sports,
                robust_package=robust,
                sports_probability_snapshot=snapshot,
            ),
        )

    monkeypatch.setattr(
        final_hybrid_sidecar,
        "execute_final_hybrid_comparison",
        fake_compare,
    )

    result = run_final_hybrid_sidecar(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_root=tmp_path / "sidecar",
        wait_seconds=0,
        minimum_runtime_seconds=240,
        now=lambda: observed,
        sleeper=lambda _: None,
    )

    assert result.status == "READY_RESEARCH_ONLY_NO_BET"
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    assert payload["operator_compatible"] is False
    assert payload["automatic_wagering"] is False
    assert payload["operator_reason"] == "release gate closed"
