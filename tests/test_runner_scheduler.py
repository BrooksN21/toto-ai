import copy
import hashlib
import json
import os
import plistlib
import subprocess
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import toto_ai.runner.scheduler as scheduler
from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from toto_ai.db.session import init_db
from toto_ai.external_odds.timing_overrides import (
    load_timing_override_catalog,
    timing_override_catalog_sha256,
)
from toto_ai.runner.scheduler import (
    PACKAGE_CSV_HEADER,
    RUNNER_MANIFEST_SCHEMA_VERSION,
    CommandSchedulerPhaseRunner,
    SchedulerError,
    SchedulerPhaseContext,
    SchedulerPhaseError,
    SchedulerPhaseResult,
    VirtualSchedulerClock,
    build_run_drawing_phase_command,
    build_scheduler_plan,
    execute_scheduler_plan,
    find_prior_bet_ready,
    parse_runner_manifest_phase_result,
    prepare_scheduler_artifacts,
)

UTC = timezone.utc
ENDED_AT = datetime(2030, 1, 2, 12, tzinfo=UTC)
FALLBACK_PACKAGE = (
    b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.05,0.05\n"
)
FINAL_PACKAGE = (
    b"rank,coupon,gross_ev,net_ev\n1,XXXXXXXXXXXXXXX,1.15,0.15\n"
)


def _plan(
    tmp_path: Path,
    *,
    timing_overrides: Path | None = None,
    minimum_gross_ev: float = 1.0,
):
    return build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=ENDED_AT,
        bank=4980,
        stake=30,
        minimum_gross_ev=minimum_gross_ev,
        output_dir=tmp_path / "scheduler",
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
        timing_overrides=timing_overrides,
    )


def _play(package: bytes, context: SchedulerPhaseContext):
    selected_count = len(package.decode("utf-8").splitlines()) - 1
    return SchedulerPhaseResult.play(
        package,
        effective_bank=4980,
        selected_count=selected_count,
        selected_cost=selected_count * 30,
        override_sha256=context.override_sha256,
        package_sha256=hashlib.sha256(package).hexdigest(),
    )


def _happy_runner(calls: list[SchedulerPhaseContext]):
    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        calls.append(context)
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preflight ok")
        return _play(
            FALLBACK_PACKAGE if context.phase == "fallback" else FINAL_PACKAGE,
            context,
        )

    return run


def _execute(plan, runner, *, run_id: str = "test-run", clock=None):
    clock = clock or VirtualSchedulerClock(plan.preflight_at)
    return execute_scheduler_plan(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=clock.sleep,
        run_id=run_id,
    )


def _status(result) -> dict[str, object]:
    return json.loads(result.status_path.read_text(encoding="utf-8"))


def _write_catalog(path: Path, *, suffix: str) -> str:
    payload = {
        "overrides": [
            {
                "schema_version": 1,
                "override_id": f"reviewed-{suffix}",
                "drawing_id": 12001,
                "target_fingerprint": "a" * 64,
                "reviewer": f"reviewer-{suffix}",
                "reviewed_at": "2029-12-30T12:00:00+00:00",
                "source_ref": f"offline-review:{suffix}",
                "events": [
                    {
                        "event_order": 0,
                        "event_id": 70001,
                        "starts_at": "2030-01-02T12:30:00+00:00",
                    }
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    catalog = load_timing_override_catalog(path)
    return timing_override_catalog_sha256(catalog)


def _write_complete_catalog(path: Path) -> str:
    payload = {
        "overrides": [
            {
                "schema_version": 1,
                "override_id": "reviewed-complete",
                "drawing_id": 12001,
                "target_fingerprint": "a" * 64,
                "reviewer": "release-reviewer",
                "reviewed_at": "2030-01-02T11:30:00+00:00",
                "source_ref": "offline-review:complete",
                "events": [
                    {
                        "event_order": order,
                        "event_id": 70001 + order,
                        "starts_at": (
                            datetime(2030, 1, 2, 12, 30, tzinfo=UTC)
                            + timedelta(minutes=5 * order)
                        ).isoformat(),
                    }
                    for order in range(15)
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return timing_override_catalog_sha256(load_timing_override_catalog(path))


def _manifest_context(
    tmp_path: Path,
    *,
    phase: str = "final",
    timing_overrides: Path | None = None,
    override_sha256: str | None = None,
    minimum_gross_ev: float = 1.0,
) -> SchedulerPhaseContext:
    plan = _plan(
        tmp_path,
        timing_overrides=timing_overrides,
        minimum_gross_ev=minimum_gross_ev,
    )
    run_dir = plan.output_dir / "runs" / "5001" / "manifest-test"
    work_dir = run_dir / "work" / phase
    work_dir.mkdir(parents=True)
    scheduled_at = plan.final_at if phase == "final" else plan.fallback_at
    return SchedulerPhaseContext(
        phase=phase,  # type: ignore[arg-type]
        plan=plan,
        run_id="manifest-test",
        run_dir=run_dir,
        work_dir=work_dir,
        scheduled_at=scheduled_at,
        started_at=scheduled_at,
        override_sha256=override_sha256,
    )


def _valid_runner_manifest(
    context: SchedulerPhaseContext,
) -> dict[str, object]:
    fingerprint = "a" * 64
    coupons = [
        {
            "rank": 1,
            "coupon": "111111111111111",
            "gross_ev": 1.2,
            "net_ev": 0.2,
        },
        {
            "rank": 2,
            "coupon": "XXXXXXXXXXXXXXX",
            "gross_ev": 1.1,
            "net_ev": 0.1,
        },
    ]
    selected_count = len(coupons)
    selected_cost = selected_count * context.plan.stake
    expected_payout = sum(
        float(row["gross_ev"]) * context.plan.stake for row in coupons
    )
    return {
        "schema_version": RUNNER_MANIFEST_SCHEMA_VERSION,
        "run_id": "local-runner-fixture",
        "command_status": "success",
        "decision": "PLAY",
        "terminal_reason": "local fixture PLAY",
        "target": {
            "drawing_id": context.plan.drawing_id,
            "drawing_number": context.plan.drawing,
            "deadline": context.plan.ended_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "preflight_fingerprint": fingerprint,
            "final_fingerprint": fingerprint,
        },
        "config": {
            "bank": context.plan.requested_bank,
            "stake": context.plan.stake,
            "mode": "playable",
            "final_lead_minutes": 30 if context.phase == "fallback" else 15,
            "safety_stop_minutes": 10,
            "provider": context.plan.provider,
        },
        "timeline": {
            "preflight_at": "2030-01-02T11:15:00Z",
            "final_started_at": "2030-01-02T11:45:00Z",
            "collection_finished_at": "2030-01-02T11:46:00Z",
            "timing_finished_at": "2030-01-02T11:47:00Z",
            "audit_finished_at": "2030-01-02T11:48:00Z",
            "ev_finished_at": "2030-01-02T11:49:00Z",
            "finished_at": "2030-01-02T11:49:00Z",
            "elapsed_seconds": 1.0,
        },
        "collection": {
            "final_collection_id": "c" * 64,
            "collection_ids": ["c" * 64],
            "pass_count": 1,
            "base_pass_count": 1,
            "expansion_pass_count": 0,
            "expanded": False,
            "final_horizon_days": 2,
            "stop_reason": "no_retryable_fallbacks",
            "total_requests": 5,
            "total_cache_hits": 0,
            "requested_schedule_date_count": 2,
            "successful_schedule_date_count": 2,
            "failed_schedule_date_count": 0,
            "elapsed_seconds": 1.0,
            "pinned_revalidation": asdict(
                ready_pinned_revalidation(context.started_at)
            ),
        },
        "eligibility": {
            "status": "playable",
            "reason": "all starts are playable",
            "target_fingerprint": fingerprint,
            "fingerprint_match": True,
            "span_days": 1,
            "missing_event_orders": [],
            "totobrief_count": 15,
            "provider_count": 0,
            "operator_override_count": 0,
            "earliest_start": "2030-01-02T12:30:00Z",
            "latest_start": "2030-01-02T14:30:00Z",
            "effective": {
                "status": "playable",
                "reason": "all starts are playable",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "raw": {
                "status": "playable",
                "reason": "all starts are playable",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "override": None,
        },
        "coverage": {
            "gate_decision": "PENDING",
            "gate_reasons": ["prospective sample is incomplete"],
            "drawings": 1,
            "events": 15,
            "unique_match_rate": 0.8,
            "consensus_rate": 0.7,
            "ambiguous_matches": 0,
            "explicit_dispositions": 15,
            "operational_failures": 0,
        },
        "ev": {
            "computed": True,
            "requested_bank": context.plan.requested_bank,
            "effective_budget": selected_cost,
            "selected_cost": selected_cost,
            "unused_requested_bank": (
                context.plan.requested_bank - selected_cost
            ),
            "input_fetched_at": "2030-01-02T11:45:00Z",
            "minimum_gross_ev": context.plan.minimum_gross_ev,
            "prize_fund_factor": 1.0,
            "possible_winnings_source": "pool_sum proxy",
            "jackpot_source": "totobrief payload",
            "self_dilution_ratio": 0.001,
            "model_supported": True,
            "model_warning": None,
            "package": {
                "decision": "PLAY",
                "decision_reason": None,
                "coupons": coupons,
                "selected_count": selected_count,
                "cost": selected_cost,
                "unused_bank": context.plan.requested_bank - selected_cost,
                "expected_payout": expected_payout,
                "modeled_roi": expected_payout / selected_cost - 1.0,
                "derived_brief": ["1X"] * 15,
            },
            "sensitivity": [],
        },
        "report_links": {"external": [], "ev": []},
        "replay": None,
        "warnings": [],
    }


def _write_runner_manifest(
    context: SchedulerPhaseContext,
    payload: dict[str, object],
    *,
    raw: str | None = None,
) -> Path:
    report_dir = context.work_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "drawing_run_fixture.json"
    path.write_text(
        json.dumps(payload) if raw is None else raw,
        encoding="utf-8",
    )
    return path


def test_happy_final_package_is_the_only_bet_ready_publication(tmp_path: Path):
    plan = _plan(tmp_path)
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls))

    assert result.outcome == "bet-ready"
    assert result.decision == "PLAY"
    assert result.package_path == result.run_dir / "package.csv"
    assert result.package_path.read_bytes() == FINAL_PACKAGE
    assert result.package_sha256 == hashlib.sha256(FINAL_PACKAGE).hexdigest()
    assert result.marker_path.name == ".bet-ready"
    assert result.marker_path.is_file()
    assert not (result.run_dir / ".success").exists()
    assert not (result.run_dir / ".no-bet").exists()
    assert not (result.run_dir / ".failed").exists()

    status = _status(result)
    assert status["drawing"] == 5001
    assert status["run_id"] == "test-run"
    assert status["decision"] == "PLAY"
    assert status["requested_bank"] == 4980
    assert status["effective_bank"] == 4980
    assert status["package_path"] == str(result.package_path)
    assert status["package_sha256"] == result.package_sha256
    assert status["selected_snapshot"] == "final"
    assert status["published_at"] == "2030-01-02T11:50:00Z"
    assert tuple(context.phase for context in calls) == (
        "preflight",
        "fallback",
        "final",
    )


def test_final_exception_never_promotes_diagnostic_fallback(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        raise RuntimeError("final computation failed")

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert result.package_path is None
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / ".bet-ready").exists()
    status = _status(result)
    assert status["selected_snapshot"] is None
    assert status["phase_timestamps"]["final"]["status"] == "failed"
    assert "final computation failed" in status["phase_timestamps"]["final"][
        "reason"
    ]


def test_explicit_final_no_bet_never_promotes_diagnostic_fallback(
    tmp_path: Path,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        return SchedulerPhaseResult.no_bet("authoritative final NO BET")

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert not (result.run_dir / ".bet-ready").exists()
    assert (result.run_dir / "snapshots" / "fallback" / "package.csv").is_file()
    assert "audit only" in result.reason


def test_both_safe_packages_absent_is_completed_no_bet(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        return SchedulerPhaseResult.no_bet(f"{context.phase} safely declined")

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / "package.csv").exists()
    assert _status(result)["package_sha256"] is None


def test_unhandled_preflight_exception_is_failed_not_complete(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(_context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        raise RuntimeError("configuration exploded")

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert result.decision == "FAILED"
    assert result.marker_path.name == ".failed"
    assert result.marker_path.is_file()
    assert "configuration exploded" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_final_completion_after_t_minus_10_is_never_bet_ready(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = VirtualSchedulerClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        clock.sleep(5 * 60 + 1)
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "no-bet"
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "snapshots" / "final").exists()
    assert _status(result)["phase_timestamps"]["final"]["status"] == "late"
    assert (result.run_dir / "snapshots" / "fallback" / "package.csv").is_file()


def test_snapshot_package_tampering_fails_closed(tmp_path: Path):
    plan = _plan(tmp_path)
    captured: dict[str, Path] = {}

    class TamperingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at and "run_dir" in captured:
                package = (
                    captured["run_dir"]
                    / "snapshots"
                    / "final"
                    / "package.csv"
                )
                if package.exists():
                    package.write_bytes(b"tampered\n")

    clock = TamperingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        captured["run_dir"] = context.run_dir
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "failed"
    assert "package path or SHA-256 changed" in result.reason
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / ".bet-ready").exists()


def test_override_is_forwarded_and_final_hash_is_pinned_at_t_minus_15(
    tmp_path: Path,
):
    catalog_path = tmp_path / "timing-overrides.json"
    old_hash = _write_catalog(catalog_path, suffix="old")
    plan = _plan(tmp_path, timing_overrides=catalog_path)
    observed: list[SchedulerPhaseContext] = []

    class UpdatingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.final_at:
                _write_catalog(catalog_path, suffix="final")

    clock = UpdatingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        observed.append(context)
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        return _play(
            FALLBACK_PACKAGE if context.phase == "fallback" else FINAL_PACKAGE,
            context,
        )

    result = _execute(plan, run, clock=clock)
    final_hash = timing_override_catalog_sha256(
        load_timing_override_catalog(catalog_path)
    )

    assert result.outcome == "bet-ready"
    assert old_hash != final_hash
    assert observed[0].override_sha256 is None
    assert observed[1].override_sha256 == old_hash
    assert observed[2].override_sha256 == final_hash
    assert observed[2].final_inputs_sha256 is not None
    status = _status(result)
    assert status["final_override_sha256"] == final_hash
    assert status["final_inputs_sha256"] == observed[2].final_inputs_sha256

    command = build_run_drawing_phase_command(observed[2])
    override_index = command.index("--timing-overrides")
    assert command[override_index + 1] == str(catalog_path.absolute())
    assert "5001" not in command


def test_override_change_after_final_pin_fails_closed(tmp_path: Path):
    catalog_path = tmp_path / "timing-overrides.json"
    _write_catalog(catalog_path, suffix="initial")
    plan = _plan(tmp_path, timing_overrides=catalog_path)

    class TamperingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at:
                _write_catalog(catalog_path, suffix="tampered")

    clock = TamperingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "failed"
    assert "timing override semantic hash changed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_final_input_hash_is_recomputed_at_freeze_and_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    original = scheduler._final_inputs_sha256
    calls: list[str | None] = []

    def tracked(current_plan, override_sha256):
        calls.append(override_sha256)
        return original(current_plan, override_sha256)

    monkeypatch.setattr(scheduler, "_final_inputs_sha256", tracked)

    result = _execute(plan, _happy_runner([]))

    assert result.outcome == "bet-ready"
    assert len(calls) >= 3


def test_packages_are_run_scoped_and_existing_scope_is_never_overwritten(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    first = _execute(plan, _happy_runner([]), run_id="run-one")
    assert first.package_path.read_bytes() == FINAL_PACKAGE
    assert first.package_path == (
        plan.output_dir / "runs" / "5001" / "run-one" / "package.csv"
    )

    second_clock = VirtualSchedulerClock(plan.preflight_at)
    with pytest.raises(SchedulerError, match="already published"):
        execute_scheduler_plan(
            plan,
            phase_runner=_happy_runner([]),
            now=second_clock.now,
            sleep=second_clock.sleep,
            run_id="run-two",
            honor_prior_bet_ready=False,
        )
    assert not (first.run_dir.parent / "run-two").exists()
    assert first.package_path.read_bytes() == FINAL_PACKAGE

    collision_plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=ENDED_AT,
        bank=4980,
        output_dir=tmp_path / "collision-scheduler",
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
    )
    existing_scope = collision_plan.output_dir / "runs" / "5001" / "run-one"
    existing_scope.mkdir(parents=True)
    sentinel = existing_scope / "sentinel"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    collision_clock = VirtualSchedulerClock(collision_plan.preflight_at)
    with pytest.raises(SchedulerError, match="already exists"):
        execute_scheduler_plan(
            collision_plan,
            phase_runner=_happy_runner([]),
            now=collision_clock.now,
            sleep=collision_clock.sleep,
            run_id="run-one",
        )
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"


def test_old_success_no_bet_and_failed_markers_do_not_suppress_retry(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    drawing_root = plan.output_dir / "runs" / "5001"
    for marker in (".success", ".no-bet", ".failed"):
        legacy = drawing_root / marker.removeprefix(".")
        legacy.mkdir(parents=True)
        (legacy / marker).write_text("old\n", encoding="utf-8")
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls), run_id="retry")

    assert result.outcome == "bet-ready"
    assert len(calls) == 3
    assert find_prior_bet_ready(plan).run_id == "retry"


def test_existing_bet_ready_fails_duplicate_without_new_run_or_marker(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    first = _execute(plan, _happy_runner([]), run_id="published")
    existing_runs = tuple((first.run_dir.parent).iterdir())
    calls: list[SchedulerPhaseContext] = []
    clock = VirtualSchedulerClock(plan.preflight_at)

    with pytest.raises(SchedulerError, match="already published"):
        execute_scheduler_plan(
            plan,
            phase_runner=_happy_runner(calls),
            now=clock.now,
            sleep=clock.sleep,
            run_id="duplicate",
        )

    assert calls == []
    assert tuple((first.run_dir.parent).iterdir()) == existing_runs
    assert not (first.run_dir.parent / "duplicate").exists()
    assert first.marker_path.is_file()


@pytest.mark.parametrize(
    "ended_at",
    [None, "not-a-date", "2030-01-02T12:00:00", "2030-01-02T15:00:00+03:00"],
)
def test_null_or_invalid_ended_at_fails_before_scheduling(
    tmp_path: Path, ended_at: object
):
    with pytest.raises(ValueError, match="ended_at"):
        build_scheduler_plan(
            drawing=5001,
            ended_at=ended_at,  # type: ignore[arg-type]
            bank=4980,
            output_dir=tmp_path / "scheduler",
        )
    assert not (tmp_path / "scheduler").exists()


@pytest.mark.parametrize("minimum_gross_ev", [float("nan"), float("inf")])
def test_scheduler_plan_rejects_non_finite_minimum_gross_ev(
    tmp_path: Path,
    minimum_gross_ev: float,
):
    with pytest.raises(ValueError, match="minimum_gross_ev must be finite"):
        _plan(tmp_path, minimum_gross_ev=minimum_gross_ev)

    assert not (tmp_path / "scheduler").exists()


def test_exact_offsets_and_phase_start_times_are_ended_at_anchored(tmp_path: Path):
    plan = _plan(tmp_path)
    assert plan.preflight_at == ENDED_AT - timedelta(minutes=45)
    assert plan.fallback_at == ENDED_AT - timedelta(minutes=30)
    assert plan.final_at == ENDED_AT - timedelta(minutes=15)
    assert plan.freeze_at == ENDED_AT - timedelta(minutes=10)
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls))

    assert [context.started_at for context in calls] == [
        plan.preflight_at,
        plan.fallback_at,
        plan.final_at,
    ]
    phases = _status(result)["phase_timestamps"]
    assert phases["freeze"]["started_at"] == "2030-01-02T11:50:00Z"
    assert _status(result)["deadlines"] == {
        "ended_at": "2030-01-02T12:00:00Z",
        "t_minus_10": "2030-01-02T11:50:00Z",
        "t_minus_15": "2030-01-02T11:45:00Z",
        "t_minus_30": "2030-01-02T11:30:00Z",
        "t_minus_45": "2030-01-02T11:15:00Z",
    }


def test_generated_artifacts_are_credential_free_generic_and_exclusive(
    tmp_path: Path,
):
    plan = build_scheduler_plan(
        drawing=5003,
        drawing_id=12003,
        ended_at=ENDED_AT,
        bank=5010,
        output_dir=tmp_path / "generated",
    )

    artifacts = prepare_scheduler_artifacts(plan)
    plan_text = artifacts.plan_path.read_text(encoding="utf-8")
    wrapper_text = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist_text = artifacts.launch_agent_path.read_text(encoding="utf-8")
    combined = plan_text + wrapper_text + plist_text

    assert "API_SPORTS_KEY" not in combined
    assert "api-sports-test-secret" not in combined
    assert "4947" not in combined
    assert "4950" not in combined
    assert "--drawing" not in wrapper_text
    assert "scheduler-execute" in wrapper_text
    assert json.loads(plan_text)["config"]["minimum_gross_ev"] == 1.0
    assert os.stat(artifacts.wrapper_path).st_mode & 0o111
    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    assert launch_agent["Label"].startswith("com.totoai.production-scheduler.")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        prepare_scheduler_artifacts(plan)


def test_generated_artifacts_quote_paths_without_shell_injection(
    tmp_path: Path,
):
    plan = build_scheduler_plan(
        drawing=5004,
        drawing_id=12004,
        ended_at=ENDED_AT,
        bank=4980,
        output_dir=tmp_path / "generated safe;$(touch escaped)",
    )

    artifacts = prepare_scheduler_artifacts(plan)

    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    subprocess.run(
        [str(artifacts.wrapper_path), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not (tmp_path / "injected").exists()
    assert not (tmp_path / "escaped").exists()


def test_generated_artifacts_reject_shell_script_executable(tmp_path: Path):
    executable = tmp_path / "python-probe"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    plan = _plan(tmp_path)

    with pytest.raises(ValueError, match="current interpreter"):
        prepare_scheduler_artifacts(plan, python_command=executable)

    assert not plan.output_dir.exists()


@pytest.mark.parametrize(
    "python_command",
    ["python", "python; touch unsafe", "", "relative/path"],
)
def test_generated_artifacts_reject_unsafe_python_command(
    tmp_path: Path,
    python_command: str,
):
    plan = _plan(tmp_path)

    with pytest.raises(ValueError, match="python executable"):
        prepare_scheduler_artifacts(plan, python_command=python_command)

    assert not plan.output_dir.exists()


def test_phase_command_rejects_shell_command_instead_of_executable(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)

    with pytest.raises(ValueError, match="absolute path"):
        build_run_drawing_phase_command(
            context,
            python_executable="python -c 'raise SystemExit()'",
        )


def test_command_phase_preflight_validates_data_before_subprocess(tmp_path: Path):
    plan = _plan(tmp_path)
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="preflight",
        run_dir=tmp_path / "run",
        work_dir=tmp_path / "run" / "work" / "preflight",
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"}
    )

    with pytest.raises(SchedulerPhaseError, match="database"):
        runner(context)


def test_command_phase_preflight_runs_mandatory_prepare_drawing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    init_db(plan.db).dispose()
    plan.aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="preflight-ready",
        run_dir=plan.output_dir / "run",
        work_dir=plan.output_dir / "run" / "work" / "preflight",
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    calls = []

    def completed(command, **kwargs):
        calls.append((tuple(command), kwargs["env"]))
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"ready"}', stderr=""
        )

    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    runner = CommandSchedulerPhaseRunner(
        environment={
            "API_SPORTS_KEY": "not-persisted",
            "TOTO_LEGACY_NAME_MATCHING": "1",
        },
        target_validator=lambda _plan, _started_at: None,
    )

    result = runner(context)

    assert result.status == "complete"
    assert calls[0][0][3] == "prepare-drawing"
    assert "--open" in calls[0][0]
    assert "TOTO_LEGACY_NAME_MATCHING" not in calls[0][1]


def test_production_manifest_parser_accepts_strict_schema_v4_play(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "PLAY"
    assert result.effective_bank == 60
    assert result.selected_count == 2
    assert result.selected_cost == 60
    assert result.package_bytes is not None
    assert result.package_bytes.splitlines()[0] == ",".join(
        PACKAGE_CSV_HEADER
    ).encode()


def test_production_manifest_parser_ignores_offline_replay_as_non_production(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["replay"] = {
        "mode": "offline-replay",
        "actionable": False,
    }
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.status == "ignored"
    assert result.decision is None
    assert result.reason == "non-production offline replay manifest ignored"


def test_full_scheduler_ignores_replay_manifest_without_any_marker(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("diagnostic fallback")
        payload = _valid_runner_manifest(context)
        payload["replay"] = {
            "mode": "offline-replay",
            "actionable": False,
        }
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="ignored-offline-replay")

    assert result.outcome == "ignored"
    assert result.decision == "IGNORED"
    assert result.marker_path is None
    assert result.reason == "non-production offline replay manifest ignored"
    assert not any(
        path.name in {".bet-ready", ".no-bet", ".failed", ".ignored"}
        for path in result.run_dir.rglob("*")
    )
    status = _status(result)
    assert status["state"] == "ignored"
    assert status["outcome"] == "ignored"
    assert status["decision"] == "IGNORED"


def test_full_scheduler_invalid_live_manifest_retains_failed_marker(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("diagnostic fallback")
        payload = _valid_runner_manifest(context)
        del payload["timeline"]
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="invalid-live-manifest")

    assert result.outcome == "failed"
    assert result.decision == "FAILED"
    assert result.marker_path == result.run_dir / ".failed"
    assert result.marker_path.is_file()


def test_scheduler_manifest_pin_revalidation_failure_publishes_no_bet_marker(
    tmp_path: Path,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("fallback cannot authorize play")
        payload = _valid_runner_manifest(context)
        collection = payload["collection"]
        assert isinstance(collection, dict)
        summary = collection["pinned_revalidation"]
        assert isinstance(summary, dict)
        summary["matched_count"] = 14
        summary["provider_failure_event_orders"] = [14]
        summary["stale_event_orders"] = [14]
        summary["schedule_fresh"] = False
        summary["provider_checks_passed"] = False
        summary["fixture_checks_passed"] = False
        summary["team_checks_passed"] = False
        summary["orientation_checks_passed"] = False
        summary["start_time_checks_passed"] = False
        summary["ready_for_play"] = False
        events = list(summary["events"])
        summary["events"] = events
        event = events[14]
        assert isinstance(event, dict)
        event["status"] = "provider_failure"
        event["reason"] = "pinned fixture revalidation schedule is stale"
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="stale-pin-manifest")

    assert result.outcome == "no-bet"
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / ".bet-ready").exists()


def test_scheduler_plan_threshold_is_forwarded_and_enforced(tmp_path: Path):
    context = _manifest_context(tmp_path, minimum_gross_ev=1.1)
    command = build_run_drawing_phase_command(context)
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    result = parse_runner_manifest_phase_result(context, manifest)

    assert command[command.index("--min-gross-ev") + 1] == "1.1000000000000001"
    assert result.decision == "PLAY"


def test_production_manifest_parser_accepts_explicit_schema_v4_no_bet(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["decision"] = "NO BET"
    payload["terminal_reason"] = "authoritative threshold NO BET"
    ev = payload["ev"]
    assert isinstance(ev, dict)
    ev.update(
        {
            "computed": False,
            "effective_budget": None,
            "selected_cost": None,
            "unused_requested_bank": None,
            "input_fetched_at": None,
            "minimum_gross_ev": None,
            "prize_fund_factor": None,
            "possible_winnings_source": None,
            "jackpot_source": None,
            "self_dilution_ratio": None,
            "model_supported": None,
        }
    )
    package = ev["package"]
    assert isinstance(package, dict)
    package.update(
        {
            "decision": "NO BET",
            "decision_reason": "threshold not met",
            "coupons": [],
            "selected_count": None,
            "cost": None,
            "unused_bank": None,
            "expected_payout": None,
            "modeled_roi": None,
            "derived_brief": [],
        }
    )
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.package_bytes is None


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("schema", "schema_version"),
        ("command", "command_status"),
        ("nested-no-bet", "both be PLAY"),
        ("bad-coupon", "15 characters"),
        ("count", "count"),
        ("cost", "inconsistent"),
        ("missing-effective", "missing fields"),
        ("timing", "status is inconsistent"),
        ("ev-not-computed", "computed EV"),
        ("requested-bank", "requested_bank"),
        ("effective-bank", "divisible"),
        ("stake", "config"),
        ("missing-timeline", "missing fields"),
    ],
)
def test_production_manifest_parser_rejects_review_malformed_cases(
    tmp_path: Path,
    case: str,
    expected: str,
):
    context = _manifest_context(tmp_path)
    payload = copy.deepcopy(_valid_runner_manifest(context))
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    coupons = package["coupons"]
    assert isinstance(coupons, list)
    if case == "schema":
        payload["schema_version"] = 999
    elif case == "command":
        payload["command_status"] = "failed"
    elif case == "nested-no-bet":
        package["decision"] = "NO BET"
    elif case == "bad-coupon":
        coupon = coupons[0]
        assert isinstance(coupon, dict)
        coupon["coupon"] = "BAD"
    elif case == "count":
        package["selected_count"] = 3
    elif case == "cost":
        package["cost"] = 30
    elif case == "missing-effective":
        del ev["effective_budget"]
    elif case == "timing":
        eligibility = payload["eligibility"]
        assert isinstance(eligibility, dict)
        effective = eligibility["effective"]
        assert isinstance(effective, dict)
        effective["status"] = "unknown"
    elif case == "ev-not-computed":
        ev["computed"] = False
    elif case == "requested-bank":
        ev["requested_bank"] = 5000
    elif case == "effective-bank":
        ev["effective_budget"] = 31
    elif case == "stake":
        config = payload["config"]
        assert isinstance(config, dict)
        config["stake"] = 10
    elif case == "missing-timeline":
        del payload["timeline"]
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match=expected):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_cannot_lower_plan_threshold_to_publish_half_ev_coupon(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    ev["minimum_gross_ev"] = 0.0
    package = ev["package"]
    assert isinstance(package, dict)
    coupons = package["coupons"]
    assert isinstance(coupons, list)
    first = coupons[0]
    assert isinstance(first, dict)
    first["gross_ev"] = 0.5
    first["net_ev"] = -0.5
    expected_payout = sum(float(row["gross_ev"]) * 30 for row in coupons)
    package["expected_payout"] = expected_payout
    package["modeled_roi"] = expected_payout / 60 - 1.0
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="does not match scheduler plan"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_playable_timing_cannot_hide_missing_events(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["missing_event_orders"] = [14]
        timing["totobrief_count"] = 14
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="status is inconsistent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_timing_source_counts_must_total_known_events(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["provider_count"] = 1
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="source counts"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_playable_timing_rejects_multi_day_span(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["span_days"] = 3
        timing["earliest_start"] = "2030-01-02T00:00:00Z"
        timing["latest_start"] = "2030-01-04T00:00:00Z"
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="status is inconsistent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_forged_override_without_configured_catalog(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    eligibility["override"] = {
        "status": "not_applied",
        "preflight_catalog_sha256": None,
        "timing_catalog_sha256": None,
        "package_catalog_sha256": None,
        "override_id": None,
        "reviewer": None,
        "reviewed_at": None,
        "source_ref": None,
        "overlay_complete": False,
        "applied_events": [],
        "preserved_event_orders": [],
        "diagnostics": ["forged audit"],
    }
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="must be absent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_non_string_decision_reason(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    package["decision_reason"] = 7
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="decision_reason"):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize("location", ["manifest", "target", "coupon"])
def test_manifest_rejects_unknown_schema_v4_fields(
    tmp_path: Path,
    location: str,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    if location == "manifest":
        payload["unauthorized"] = True
    elif location == "target":
        target = payload["target"]
        assert isinstance(target, dict)
        target["unauthorized"] = True
    else:
        ev = payload["ev"]
        assert isinstance(ev, dict)
        package = ev["package"]
        assert isinstance(package, dict)
        coupons = package["coupons"]
        assert isinstance(coupons, list)
        coupon = coupons[0]
        assert isinstance(coupon, dict)
        coupon["unauthorized"] = True
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="unknown fields"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_boolean_integer_field(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    package["selected_count"] = True
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="must be an integer"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_accepts_complete_pinned_override_for_incomplete_raw_timing(
    tmp_path: Path,
):
    catalog_path = tmp_path / "timing-overrides.json"
    catalog_hash = _write_complete_catalog(catalog_path)
    context = _manifest_context(
        tmp_path,
        timing_overrides=catalog_path,
        override_sha256=catalog_hash,
    )
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    raw = eligibility["raw"]
    effective = eligibility["effective"]
    assert isinstance(raw, dict)
    assert isinstance(effective, dict)
    raw.update(
        {
            "status": "unknown",
            "reason": "two starts unresolved",
            "missing_event_orders": [13, 14],
            "totobrief_count": 13,
        }
    )
    effective.update(
        {
            "reason": "complete reviewed timing overlay",
            "totobrief_count": 13,
            "operator_override_count": 2,
        }
    )
    for field in scheduler._TIMING_PAYLOAD_FIELDS:
        eligibility[field] = effective[field]
    eligibility["override"] = {
        "status": "applied",
        "preflight_catalog_sha256": catalog_hash,
        "timing_catalog_sha256": catalog_hash,
        "package_catalog_sha256": catalog_hash,
        "override_id": "reviewed-complete",
        "reviewer": "release-reviewer",
        "reviewed_at": "2030-01-02T11:30:00+00:00",
        "source_ref": "offline-review:complete",
        "overlay_complete": True,
        "applied_events": [
            {
                "event_order": order,
                "event_id": 70001 + order,
                "starts_at": (
                    datetime(2030, 1, 2, 12, 30, tzinfo=UTC)
                    + timedelta(minutes=5 * order)
                ).isoformat(),
                "source_ref": "offline-review:complete",
            }
            for order in (13, 14)
        ],
        "preserved_event_orders": list(range(13)),
        "diagnostics": [],
    }
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "PLAY"
    assert result.override_sha256 == catalog_hash


@pytest.mark.parametrize("non_finite", ["NaN", "Infinity", "-Infinity"])
def test_production_manifest_parser_rejects_non_finite_json_metrics(
    tmp_path: Path,
    non_finite: str,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    raw = json.dumps(payload).replace('"gross_ev": 1.2', f'"gross_ev": {non_finite}')
    manifest = _write_runner_manifest(context, payload, raw=raw)

    with pytest.raises(SchedulerPhaseError, match="non-finite"):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize(
    "package",
    [
        b"rank,coupon,gross_ev,net_ev\n",
        b"rank,coupon,gross_ev,net_ev\n1,BAD,1.1,0.1\n",
        (
            b"rank,coupon,gross_ev,net_ev\n"
            b"1,111111111111111,nan,0.1\n"
        ),
        (
            b"rank,coupon,gross_ev,net_ev\n"
            b"1,111111111111111,inf,0.1\n"
        ),
        b"coupon,rank,gross_ev,net_ev\n111111111111111,1,1.1,0.1\n",
        b'"rank",coupon,gross_ev,net_ev\n1,111111111111111,1.1,0.1\n',
        (
            b"rank,coupon,gross_ev,net_ev\n"
            b"1,111111111111111,1.1,0.1\n"
            b"2,111111111111111,1.05,0.05\n"
        ),
    ],
)
def test_capture_path_rejects_malformed_or_empty_package_csv(
    tmp_path: Path,
    package: bytes,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return SchedulerPhaseResult.play(
            package,
            effective_bank=4980,
            override_sha256=context.override_sha256,
            package_sha256=hashlib.sha256(package).hexdigest(),
        )

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "package.csv").exists()


@pytest.mark.parametrize(
    ("selected_count", "selected_cost"),
    [(2, 30), (1, 60)],
)
def test_capture_path_rejects_count_or_cost_mismatch(
    tmp_path: Path,
    selected_count: int,
    selected_cost: int,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return SchedulerPhaseResult.play(
            FINAL_PACKAGE,
            effective_bank=4980,
            selected_count=selected_count,
            selected_cost=selected_cost,
            override_sha256=context.override_sha256,
        )

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert "package CSV" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_symlinked_runs_directory_is_rejected_without_escape(tmp_path: Path):
    plan = _plan(tmp_path)
    plan.output_dir.mkdir(parents=True)
    escaped = tmp_path / "escaped-runs"
    escaped.mkdir()
    (plan.output_dir / "runs").symlink_to(escaped, target_is_directory=True)

    with pytest.raises(SchedulerError, match="symlink"):
        _execute(plan, _happy_runner([]))

    assert tuple(escaped.iterdir()) == ()


def test_symlinked_source_package_is_rejected_without_escape(tmp_path: Path):
    plan = _plan(tmp_path)
    external_package = tmp_path / "external-package.csv"
    external_package.write_bytes(FINAL_PACKAGE)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        source = context.work_dir / "source-package.csv"
        source.symlink_to(external_package)
        return SchedulerPhaseResult.play(
            source,
            effective_bank=4980,
            selected_count=1,
            selected_cost=30,
            override_sha256=context.override_sha256,
        )

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert not (result.run_dir / ".bet-ready").exists()
    assert external_package.read_bytes() == FINAL_PACKAGE


def test_symlinked_status_escape_is_rejected_without_external_write(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    external_status = tmp_path / "external-status.json"
    external_status.write_text("unchanged\n", encoding="utf-8")

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            status = context.run_dir / "status.json"
            status.unlink()
            status.symlink_to(external_status)
            return SchedulerPhaseResult.completed()
        return _play(FINAL_PACKAGE, context)

    with pytest.raises(SchedulerError, match="symlink"):
        _execute(plan, run)

    assert external_status.read_text(encoding="utf-8") == "unchanged\n"
    assert not any(plan.output_dir.rglob(".bet-ready"))


def test_symlinked_snapshot_package_cannot_create_bet_ready(tmp_path: Path):
    plan = _plan(tmp_path)
    external_package = tmp_path / "external-snapshot.csv"
    external_package.write_bytes(FINAL_PACKAGE)
    captured: dict[str, Path] = {}

    class SymlinkingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at and "run_dir" in captured:
                package = (
                    captured["run_dir"]
                    / "snapshots"
                    / "final"
                    / "package.csv"
                )
                package.unlink()
                package.symlink_to(external_package)

    clock = SymlinkingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        captured["run_dir"] = context.run_dir
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "failed"
    assert not (result.run_dir / ".bet-ready").exists()
    assert external_package.read_bytes() == FINAL_PACKAGE


def test_runner_manifest_symlink_is_rejected(tmp_path: Path):
    context = _manifest_context(tmp_path)
    outside = tmp_path / "outside-manifest.json"
    outside.write_text(
        json.dumps(_valid_runner_manifest(context)),
        encoding="utf-8",
    )
    report_dir = context.work_dir / "reports"
    report_dir.mkdir()
    manifest = report_dir / "drawing_run_fixture.json"
    manifest.symlink_to(outside)

    with pytest.raises(SchedulerPhaseError, match="symlink|escapes"):
        parse_runner_manifest_phase_result(context, manifest)
