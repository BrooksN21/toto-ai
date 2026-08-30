from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from toto_ai.ev.models import EVConfig
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
        uncertainty = output / "uncertainty.txt"
        report.write_text("{}", encoding="utf-8")
        baseline.write_text(
            "RESEARCH ONLY\n" + coupon + "\n",
            encoding="utf-8",
        )
        sports.write_text("RESEARCH ONLY\n" + "2" * 15 + "\n", encoding="utf-8")
        robust.write_text("RESEARCH ONLY\n" + "X" * 15 + "\n", encoding="utf-8")
        uncertainty.write_text(
            "RESEARCH ONLY\n" + "1X2" * 5 + "\n",
            encoding="utf-8",
        )
        snapshot.write_text("{}", encoding="utf-8")
        return (
            {"sports_coverage_count": 10, "sports_fallback_count": 5},
            SimpleNamespace(
                report=report,
                baseline_package=baseline,
                sports_package=sports,
                robust_package=robust,
                uncertainty_package=uncertainty,
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
    assert payload["uncertainty_research_package_sha256"]


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
        uncertainty = output / "uncertainty.txt"
        snapshot = output / "probabilities.json"
        for path in (report, baseline, sports, robust, uncertainty, snapshot):
            path.write_text("{}", encoding="utf-8")
        return (
            {"sports_coverage_count": 10, "sports_fallback_count": 5},
            SimpleNamespace(
                report=report,
                baseline_package=baseline,
                sports_package=sports,
                robust_package=robust,
                uncertainty_package=uncertainty,
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
    assert payload["uncertainty_research_package_sha256"]


def test_real_sidecar_output_marks_uncertainty_v1_as_research_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    scheduler_dir = tmp_path / "scheduler"
    final_input = scheduler_dir / "attempts" / "final-1" / "final-input.json"
    final_input.parent.mkdir(parents=True)
    final_input.write_text("{}", encoding="utf-8")
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    (scheduler_dir / "operator-result.json").write_text(
        json.dumps({"decision": "NO BET", "reason": "release gate closed"}),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        output_dir=scheduler_dir,
        publish_deadline=observed + timedelta(minutes=10),
        plan_id="plan",
        drawing=4991,
        drawing_id=12081,
        requested_bank=60,
        stake=30,
        quality_v2_ev_config=EVConfig(
            bank=60,
            stake=30,
            mode="playable",
            package_safety_enabled=True,
            package_probability_samples=16,
            package_optimization_probability_samples=16,
        ),
        schedule_evidence_ledger=tmp_path / "ledger.json",
    )
    frozen = FrozenStrategyInput(
        drawing_id=12081,
        drawing_number=4991,
        drawing_fingerprint="a" * 64,
        source_captured_at="2026-08-30T11:00:00Z",
        as_of="2026-08-30T11:00:00Z",
        ended_at="2026-08-30T13:00:00Z",
        bank=60,
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
    snapshot = SimpleNamespace(
        captured_at=observed - timedelta(hours=1),
        snapshot_sha256="b" * 64,
        probability_input_sha256="c" * 64,
    )
    sports = SimpleNamespace(
        drawing_id=frozen.drawing_id,
        drawing_number=frozen.drawing_number,
        drawing_fingerprint=frozen.drawing_fingerprint,
        authoritative_target_fingerprint=frozen.drawing_fingerprint,
        as_of=observed - timedelta(hours=1),
        events=tuple(
            SimpleNamespace(
                event_order=order,
                blend_weight=0.0,
                fallback_reason="BK fallback",
                sports_probabilities=(0.5, 0.3, 0.2),
            )
            for order in range(15)
        ),
        artifact_sha256="d" * 64,
        sports_coverage_count=0,
        fallback_count=15,
    )
    baseline_coupons = ("1" * 15, "X" * 15)
    sports_coupons = ("2" * 15, "1X" * 7 + "1")
    uncertainty_coupons = ("1X2" * 5, "2X1" * 5)

    def strategy(coupons):
        return SimpleNamespace(
            coupons=coupons,
            coupon_count=len(coupons),
            cost=len(coupons) * 30,
            unused_bank=60 - len(coupons) * 30,
            package_sha256=hashlib.sha256(",".join(coupons).encode()).hexdigest(),
            runtime_seconds=0.0,
            probability_at_least_13=0.1,
            probability_at_least_14=0.05,
            probability_at_least_15=0.01,
        )

    @dataclass(frozen=True)
    class Quality:
        probability_at_least_13: float = 0.1

    robust = SimpleNamespace(
        selected_coupons=baseline_coupons,
        candidate_count=4,
        category=13,
        sample_count_per_model=16,
        worst_sampled_category_coverage=0.1,
        mean_sampled_category_coverage=0.1,
        timed_out=False,
        model_metrics=(),
    )
    uncertainty = SimpleNamespace(
        selected_coupons=uncertainty_coupons,
        candidate_count=8,
        category=13,
        sample_count_per_model=16,
        worst_sampled_category_coverage=0.2,
        mean_sampled_category_coverage=0.2,
        timed_out=False,
        model_metrics=(),
    )
    strategy_results = iter((strategy(baseline_coupons), strategy(sports_coupons)))
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    monkeypatch.setattr(
        final_hybrid_sidecar,
        "_latest_final_input",
        lambda _: final_input,
    )
    monkeypatch.setattr(final_hybrid_comparison, "load_scheduler_plan", lambda _: plan)
    monkeypatch.setattr(
        final_hybrid_comparison,
        "load_final_input",
        lambda *_args, **_kwargs: snapshot,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "frozen_input_from_snapshot",
        lambda *_args: frozen,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "load_shadow_probability_artifact",
        lambda _: sports,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "effective_selection_budget",
        lambda **_kwargs: 60,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "PackageSelectionProvenance",
        SimpleNamespace(from_artifacts=lambda **_kwargs: object()),
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "run_ev_crowd_current",
        lambda *_args, **_kwargs: next(strategy_results),
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "select_robust_package",
        lambda **_kwargs: robust,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "select_uncertainty_package",
        lambda **_kwargs: uncertainty,
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "package_quality_metrics",
        lambda *_args, **_kwargs: Quality(),
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

    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    uncertainty_path = Path(payload["uncertainty_research_package"])
    content = uncertainty_path.read_text(encoding="utf-8")
    assert result.status == "READY_RESEARCH_ONLY_NO_BET"
    assert payload["automatic_wagering"] is False
    assert payload["operator_compatible"] is False
    assert hashlib.sha256(uncertainty_path.read_bytes()).hexdigest() == payload[
        "uncertainty_research_package_sha256"
    ]
    assert content.splitlines()[:4] == [
        "RESEARCH ONLY / NOT ACTIVATED / DO NOT WAGER",
        "NOT A BALTBet UPLOAD FILE",
        "role=DIRECT_BK_BOUNDED_UNCERTAINTY_CHALLENGER stake=30 coupons=2",
        "",
    ]
    assert content.splitlines()[4:] == list(uncertainty_coupons)
