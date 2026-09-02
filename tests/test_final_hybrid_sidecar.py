from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shlex
import sys
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


def test_prepare_parallel_sidecar_artifacts_is_idempotent_and_t30_bound(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    output = tmp_path / "evening"
    output.mkdir()
    plan = SimpleNamespace(
        project_root=tmp_path,
        output_dir=output,
        plan_id="a" * 16,
        operational_cutoff=datetime(2026, 9, 2, 14, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)

    first = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        python_command=sys.executable,
    )
    second = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        python_command=sys.executable,
    )

    assert first.wrapper_path == second.wrapper_path
    assert first.launch_agent_path == second.launch_agent_path
    assert first.reused is False
    assert second.reused is True
    assert first.scheduled_at == datetime(2026, 9, 2, 13, 30, tzinfo=UTC)
    wrapper = first.wrapper_path.read_text(encoding="utf-8")
    assert "run-final-goal-hybrid-sidecar" in wrapper
    assert str(plan_path) in wrapper
    assert str(sports_path) in wrapper
    plist = plistlib.loads(first.launch_agent_path.read_bytes())
    assert plist["Label"] == "com.totoai.parallel-sidecar.v1." + "a" * 16
    assert plist["StartCalendarInterval"] == {
        "Year": 2026,
        "Month": 9,
        "Day": 2,
        "Hour": 16,
        "Minute": 30,
    }


def test_prepare_parallel_sidecar_migrates_authorization_bound_wrapper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    output = tmp_path / "evening"
    output.mkdir()
    plan = SimpleNamespace(
        project_root=tmp_path,
        output_dir=output,
        plan_id="c" * 16,
        operational_cutoff=datetime(2026, 9, 2, 14, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    first = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        python_command=sys.executable,
    )
    canonical = first.wrapper_path.read_bytes()
    authorization = first.root / final_hybrid_sidecar.PARALLEL_AUTHORIZATION_FILENAME
    authorization.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        final_hybrid_sidecar,
        "_validate_parallel_authorization",
        lambda *_args, **_kwargs: {},
    )
    legacy = (
        canonical.decode("utf-8").rstrip("\n")
        + " --parallel-authorization "
        + shlex.quote(str(authorization))
        + "\n"
    ).encode()
    first.wrapper_path.write_bytes(legacy)

    migrated = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        python_command=sys.executable,
    )

    assert migrated.authorization_path == authorization
    assert migrated.wrapper_path.read_bytes() == canonical
    assert b"--parallel-authorization" not in migrated.wrapper_path.read_bytes()


def test_prepare_parallel_sidecar_reuses_first_frozen_sports_input(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    first_sports = tmp_path / "sports-first.json"
    later_sports = tmp_path / "sports-later.json"
    plan_path.write_text("{}", encoding="utf-8")
    first_sports.write_text("{}", encoding="utf-8")
    later_sports.write_text('{"later":true}', encoding="utf-8")
    output = tmp_path / "evening"
    output.mkdir()
    plan = SimpleNamespace(
        project_root=tmp_path,
        output_dir=output,
        plan_id="d" * 16,
        operational_cutoff=datetime(2026, 9, 2, 14, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    first = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=first_sports,
        python_command=sys.executable,
    )

    reused = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=later_sports,
        python_command=sys.executable,
    )

    assert reused.reused is True
    assert reused.sports_artifact_path == first.sports_artifact_path
    assert str(later_sports) not in reused.wrapper_path.read_text(encoding="utf-8")


def test_activate_parallel_sidecar_installs_verified_plist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    output = tmp_path / "evening"
    output.mkdir()
    plan = SimpleNamespace(
        project_root=tmp_path,
        output_dir=output,
        plan_id="b" * 16,
        operational_cutoff=datetime(2026, 9, 2, 14, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    artifacts = final_hybrid_sidecar.prepare_parallel_sidecar_artifacts(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        python_command=sys.executable,
    )
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stderr="")

    launch_agents = tmp_path / "LaunchAgents"
    final_hybrid_sidecar.activate_parallel_sidecar_launch_agent(
        artifacts,
        launch_agents_root=launch_agents,
        command_runner=runner,
    )

    installed = launch_agents / f"{artifacts.launch_agent_label}.plist"
    assert installed.read_bytes() == artifacts.launch_agent_path.read_bytes()
    assert calls == [
        (
            "launchctl",
            "bootstrap",
            f"gui/{os.getuid()}",
            str(installed),
        )
    ]


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


def test_sports_identity_uses_operational_cutoff_fingerprint(monkeypatch) -> None:
    operational_cutoff = datetime(2026, 8, 29, 13, 30, tzinfo=UTC)
    captured_at = operational_cutoff - timedelta(minutes=30)
    frozen = FrozenStrategyInput(
        drawing_id=12077,
        drawing_number=4990,
        drawing_fingerprint="a" * 64,
        source_captured_at=captured_at.isoformat(),
        as_of=captured_at.isoformat(),
        ended_at="2026-08-29T16:30:00+00:00",
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
    targets = tuple(
        SimpleNamespace(event_order=order, event_id=100 + order)
        for order in range(15)
    )
    monkeypatch.setattr(
        final_hybrid_comparison,
        "parse_target_drawing",
        lambda *_args: SimpleNamespace(
            drawing_id=12077,
            drawing_number=4990,
            events=targets,
        ),
    )

    def fingerprint(**kwargs):
        assert kwargs["deadline"] == operational_cutoff
        return "b" * 64

    monkeypatch.setattr(
        final_hybrid_comparison,
        "target_fingerprint",
        fingerprint,
    )
    sports = SimpleNamespace(
        drawing_id=12077,
        drawing_number=4990,
        deadline=operational_cutoff,
        drawing_fingerprint="b" * 64,
        authoritative_target_fingerprint="b" * 64,
        as_of=captured_at,
        events=tuple(
            SimpleNamespace(
                event_order=order,
                event_id=100 + order,
                # The sports evidence is captured before the final scheduler
                # input, so its embedded BK row may legitimately be older.
                # The comparison rebases the sports residual onto final BK.
                bk_probabilities=(0.4, 0.35, 0.25),
            )
            for order in range(15)
        ),
    )

    final_hybrid_comparison._validate_sports_artifact_identity(
        plan=SimpleNamespace(operational_cutoff=operational_cutoff),
        snapshot=SimpleNamespace(payload={}, captured_at=captured_at),
        frozen=frozen,
        sports=sports,
    )


def test_sidecar_waits_for_final_after_pre_final_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    plan_path = tmp_path / "scheduler-plan.json"
    sports_path = tmp_path / "sports.json"
    plan_path.write_text("{}", encoding="utf-8")
    sports_path.write_text("{}", encoding="utf-8")
    observed = datetime(2026, 9, 1, 13, 30, tzinfo=UTC)
    scheduler_dir = tmp_path / "scheduler"
    scheduler_dir.mkdir()
    operator_path = scheduler_dir / "operator-result.json"
    operator_path.write_text(
        json.dumps(
            {
                "plan_id": "plan",
                "drawing": 4993,
                "drawing_id": 12086,
                "decision": "NO BET",
                "actionable": False,
                "operator_status": "LAST_KNOWN_GOOD_DEGRADED",
                "provenance": "PRE_FINAL_CHECKPOINT",
                "reason": "validated refresh package available before final refresh",
            }
        ),
        encoding="utf-8",
    )
    plan = SimpleNamespace(
        output_dir=scheduler_dir,
        publish_deadline=observed + timedelta(minutes=10),
        plan_id="plan",
        drawing=4993,
        drawing_id=12086,
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    executed = []

    def fake_execute(**kwargs):
        executed.append(kwargs["operator"])
        result_path = tmp_path / "sidecar" / "sidecar-status.json"
        result_path.write_text("{}", encoding="utf-8")
        return final_hybrid_sidecar.FinalHybridSidecarResult(
            status="READY_BEFORE_T10",
            result_path=result_path,
            output_dir=tmp_path / "sidecar",
            reason=None,
        )

    def publish_final(_seconds: float) -> None:
        operator_path.write_text(
            json.dumps(
                {
                    "plan_id": "plan",
                    "drawing": 4993,
                    "drawing_id": 12086,
                    "decision": "PLAY",
                    "actionable": True,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(final_hybrid_sidecar, "_execute", fake_execute)

    result = run_final_hybrid_sidecar(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_root=tmp_path / "sidecar",
        wait_seconds=60,
        minimum_runtime_seconds=240,
        now=lambda: observed,
        sleeper=publish_final,
    )

    assert result.status == "READY_BEFORE_T10"
    assert len(executed) == 1
    assert executed[0]["decision"] == "PLAY"


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


def test_authorized_sidecar_exports_selected_challenger_before_t10(
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
        requested_bank=60,
        stake=30,
    )
    monkeypatch.setattr(final_hybrid_sidecar, "load_scheduler_plan", lambda _: plan)
    baseline_coupon = "1" * 15
    challenger_coupon = "X" * 15
    challenger_hash = hashlib.sha256(challenger_coupon.encode()).hexdigest()

    def fake_export(_plan, *, destination, observed_at):
        path = Path(destination)
        path.write_text(
            "30;" + ";".join(baseline_coupon) + "\n",
            encoding="utf-8",
        )
        return path

    def fake_compare(**kwargs):
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True)
        report_path = output / "comparison.json"
        baseline = output / "baseline.txt"
        sports = output / "sports.txt"
        robust = output / "robust.txt"
        quality_v3 = output / "quality-v3.txt"
        uncertainty = output / "uncertainty.txt"
        snapshot = output / "probabilities.json"
        baseline.write_text(baseline_coupon + "\n", encoding="utf-8")
        sports.write_text("2" * 15 + "\n", encoding="utf-8")
        robust.write_text("12X" * 5 + "\n", encoding="utf-8")
        quality_v3.write_text(challenger_coupon + "\n", encoding="utf-8")
        uncertainty.write_text(challenger_coupon + "\n", encoding="utf-8")
        snapshot.write_text("{}", encoding="utf-8")
        report = {
            "sports_coverage_count": 10,
            "sports_fallback_count": 5,
            "coupon_order_semantics": (
                "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK"
            ),
            "highest_p13_single_coupons": {
                "quality-v3": {
                    "coupon": challenger_coupon,
                    "package_position": 1,
                    "criterion": "maximum_probability_at_least_13",
                    "reference_model": "bk",
                    "probability_at_least_13": 0.1,
                    "probability_at_least_14": 0.01,
                    "probability_at_least_15": 0.001,
                    "package_order_semantics": (
                        "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK"
                    ),
                }
            },
            "experimental_selection": {
                "policy_version": "parallel-challenger-nondegradation-v1",
                "selected_strategy_id": "quality-v3",
                "selected_package_sha256": challenger_hash,
                "promoted": True,
                "selection_reason": "eligible",
                "candidates": [
                    {
                        "strategy_id": "quality-v3",
                        "eligible": True,
                        "coupon_count": 1,
                        "cost": 30,
                    }
                ],
            },
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report, SimpleNamespace(
            report=report_path,
            baseline_package=baseline,
            sports_package=sports,
            robust_package=robust,
            quality_v3_package=quality_v3,
            uncertainty_package=uncertainty,
            sports_probability_snapshot=snapshot,
        )

    monkeypatch.setattr(final_hybrid_sidecar, "export_operator_package", fake_export)
    monkeypatch.setattr(
        final_hybrid_sidecar,
        "execute_final_hybrid_comparison",
        fake_compare,
    )
    final_hybrid_sidecar.authorize_parallel_manual_release(
        scheduler_plan_path=plan_path,
        output_root=tmp_path / "sidecar",
        acknowledged=True,
        now=observed,
    )

    result = run_final_hybrid_sidecar(
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_root=tmp_path / "sidecar" / "output",
        wait_seconds=0,
        minimum_runtime_seconds=240,
        now=lambda: observed,
        sleeper=lambda _: None,
    )

    assert result.status == "READY_PARALLEL_PLAY_BEFORE_T10"
    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    release = payload["parallel_release"]
    assert release["decision"] == "PLAY"
    assert release["actionable"] is True
    assert release["selected_strategy_id"] == "quality-v3"
    assert release["highest_p13_single_coupon"] == {
        "coupon": challenger_coupon,
        "package_position": 1,
        "criterion": "maximum_probability_at_least_13",
        "reference_model": "bk",
        "probability_at_least_13": 0.1,
        "probability_at_least_14": 0.01,
        "probability_at_least_15": 0.001,
        "package_order_semantics": "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK",
    }
    assert release["automatic_wagering"] is False
    package = Path(release["selected_package_path"])
    assert package.read_text(encoding="utf-8") == (
        "30;" + ";".join(challenger_coupon) + "\n"
    )


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
    robust_call = {}

    def fake_robust(**kwargs):
        robust_call.update(kwargs)
        return robust

    monkeypatch.setattr(
        final_hybrid_comparison,
        "select_robust_package",
        fake_robust,
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
    monkeypatch.setattr(
        final_hybrid_comparison,
        "evaluate_package_safety",
        lambda *_args, **_kwargs: SimpleNamespace(
            decision="PLAY",
            reason_codes=(),
        ),
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
    assert payload["quality_v3_research_package_sha256"]
    assert set(robust_call["probability_models"]) == {
        "bk",
        "sports",
        "flatten_10",
        "flatten_20",
    }
    assert set(uncertainty_coupons).issubset(set(robust_call["candidates"]))
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
