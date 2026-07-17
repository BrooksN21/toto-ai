"""Provider-neutral safe drawing runner orchestration."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from math import isfinite

from toto_ai.ev.drawing import EVPackageRun
from toto_ai.ev.models import PlayTimingEligibility
from toto_ai.external_odds.audit import CoverageAudit
from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.prospective import ProspectiveCollectionResult
from toto_ai.runner.models import (
    DrawingRunnerConfig,
    DrawingRunnerResult,
    PinnedDrawing,
)
from toto_ai.runner.timing import (
    RunnerSchedule,
    build_runner_schedule,
    runner_window,
    wait_for_final_window,
)

ProgressCallback = Callable[[dict[str, object]], object]
TargetResolver = Callable[[datetime], PinnedDrawing]
TargetCollector = Callable[
    [TargetDrawing, datetime], ProspectiveCollectionResult
]
TimingResolver = Callable[[PinnedDrawing], PlayTimingEligibility]
CoverageAuditor = Callable[[], CoverageAudit]
PackageBuilder = Callable[[PinnedDrawing], EVPackageRun]
PreflightCheck = Callable[[PinnedDrawing, datetime], object]


class RunnerTargetMismatch(RuntimeError):
    """Expected fail-closed mutation between collection and the EV payload."""


def run_drawing(
    *,
    config: DrawingRunnerConfig,
    resolve_target: TargetResolver,
    collect_target: TargetCollector,
    resolve_timing: TimingResolver,
    audit_coverage: CoverageAuditor,
    build_package: PackageBuilder,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
    sleep: Callable[[float], object],
    progress_callback: ProgressCallback | None = None,
    preflight_check: PreflightCheck | None = None,
) -> DrawingRunnerResult:
    """Run one preflight-to-EV state machine with injected dependencies."""
    if not isinstance(config, DrawingRunnerConfig):
        raise ValueError("config must be a DrawingRunnerConfig")
    started_monotonic = _read_monotonic(monotonic)
    preflight_at = _read_now(now)
    _notify(progress_callback, "preflight")
    preflight = resolve_target(preflight_at)
    _require_pinned_target("preflight", preflight)
    schedule = build_runner_schedule(preflight.target.deadline, config)
    if preflight_check is not None:
        if not callable(preflight_check):
            raise ValueError("preflight_check must be callable")
        preflight_check(preflight, preflight_at)

    window = wait_for_final_window(
        schedule,
        now=now,
        sleep=sleep,
        progress_callback=progress_callback,
    )
    if window == "closed":
        finished_at = _read_now(now)
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=None,
            final_fingerprint=None,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before final resolve",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )

    final_started_at = _read_now(now)
    if _is_closed(schedule, final_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=None,
            final_fingerprint=None,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=final_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before final resolve",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )

    _notify(progress_callback, "final")
    final_started_at = _read_now(now)
    if _is_closed(schedule, final_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=None,
            final_fingerprint=None,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=final_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before final resolve",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )
    final = resolve_target(final_started_at)
    _require_pinned_target("final", final)
    if not _same_target(preflight, final):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=_read_now(now),
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="final target does not match preflight",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )

    collection_started_at = _read_now(now)
    if _is_closed(schedule, collection_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=collection_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before collection",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )

    _notify(progress_callback, "collect")
    collection_started_at = _read_now(now)
    if _is_closed(schedule, collection_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=collection_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before collection",
            collection=None,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )
    collection = collect_target(final.target, schedule.safety_stops_at)
    if not isinstance(collection, ProspectiveCollectionResult):
        raise ValueError("collect_target must return ProspectiveCollectionResult")
    collection_finished_at = _read_now(now)
    if _is_closed(schedule, collection_finished_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=collection_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before timing",
            collection=collection,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )

    _notify(progress_callback, "timing")
    timing_started_at = _read_now(now)
    if _is_closed(schedule, timing_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=timing_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before timing",
            collection=collection,
            timing_eligibility=PlayTimingEligibility.not_checked(),
            audit=None,
            progress_callback=progress_callback,
        )
    timing_eligibility = resolve_timing(final)
    if not isinstance(timing_eligibility, PlayTimingEligibility):
        raise ValueError("resolve_timing must return PlayTimingEligibility")
    timing_finished_at = _read_now(now)
    if _is_closed(schedule, timing_finished_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=timing_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before audit",
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=None,
            progress_callback=progress_callback,
        )

    _notify(progress_callback, "audit")
    audit_started_at = _read_now(now)
    if _is_closed(schedule, audit_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=audit_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before audit",
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=None,
            progress_callback=progress_callback,
        )
    audit = audit_coverage()
    if not isinstance(audit, CoverageAudit):
        raise ValueError("audit_coverage must return CoverageAudit")
    audit_finished_at = _read_now(now)
    if _is_closed(schedule, audit_finished_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=audit_finished_at,
            ev_finished_at=None,
            finished_at=audit_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before ev",
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=audit,
            progress_callback=progress_callback,
        )

    if config.mode == "playable" and timing_eligibility.status != "playable":
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=audit_finished_at,
            ev_finished_at=None,
            finished_at=audit_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason=(
                "timing eligibility is not playable: "
                f"{timing_eligibility.status}"
            ),
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=audit,
            progress_callback=progress_callback,
        )

    _notify(progress_callback, "ev")
    ev_started_at = _read_now(now)
    if _is_closed(schedule, ev_started_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=audit_finished_at,
            ev_finished_at=None,
            finished_at=ev_started_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached before ev",
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=audit,
            progress_callback=progress_callback,
        )
    try:
        ev_run = build_package(final)
    except RunnerTargetMismatch as error:
        mismatch_finished_at = _read_now(now)
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=audit_finished_at,
            ev_finished_at=None,
            finished_at=mismatch_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason=str(error),
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=audit,
            progress_callback=progress_callback,
        )
    if not isinstance(ev_run, EVPackageRun):
        raise ValueError("build_package must return EVPackageRun")
    ev_finished_at = _read_now(now)
    if _is_closed(schedule, ev_finished_at):
        return _no_bet_result(
            config=config,
            target=preflight,
            preflight_at=preflight_at,
            final_started_at=final_started_at,
            final_fingerprint=final.fingerprint,
            collection_finished_at=collection_finished_at,
            timing_finished_at=timing_finished_at,
            audit_finished_at=audit_finished_at,
            ev_finished_at=ev_finished_at,
            finished_at=ev_finished_at,
            started_monotonic=started_monotonic,
            monotonic=monotonic,
            terminal_reason="safety cutoff reached after EV",
            collection=collection,
            timing_eligibility=timing_eligibility,
            audit=audit,
            progress_callback=progress_callback,
        )

    decision = ev_run.package.decision
    terminal_reason = {
        "PLAY": "EV package selected playable coupons",
        "NO BET": "EV package returned NO BET",
        "RESEARCH ONLY": "research package completed",
    }.get(decision)
    if terminal_reason is None:
        raise ValueError("EV package returned an invalid decision")
    elapsed_seconds = _elapsed_seconds(started_monotonic, monotonic)
    result = DrawingRunnerResult(
        config=config,
        target=preflight,
        preflight_at=preflight_at,
        final_started_at=final_started_at,
        final_fingerprint=final.fingerprint,
        collection_finished_at=collection_finished_at,
        timing_finished_at=timing_finished_at,
        audit_finished_at=audit_finished_at,
        ev_finished_at=ev_finished_at,
        finished_at=ev_finished_at,
        elapsed_seconds=elapsed_seconds,
        decision=decision,
        terminal_reason=terminal_reason,
        collection=collection,
        timing_eligibility=timing_eligibility,
        audit=audit,
        ev_run=ev_run,
    )
    _notify(progress_callback, "complete", decision=decision)
    completed_at = _read_now(now)
    if _is_closed(schedule, completed_at):
        return replace(
            result,
            finished_at=completed_at,
            elapsed_seconds=_elapsed_seconds(started_monotonic, monotonic),
            decision="NO BET",
            terminal_reason="safety cutoff reached after complete",
            ev_run=None,
        )
    return result


def _same_target(left: PinnedDrawing, right: PinnedDrawing) -> bool:
    return (
        left.target.drawing_id == right.target.drawing_id
        and left.target.drawing_number == right.target.drawing_number
        and left.target.deadline == right.target.deadline
        and left.fingerprint == right.fingerprint
    )


def _no_bet_result(
    *,
    config: DrawingRunnerConfig,
    target: PinnedDrawing,
    preflight_at: datetime,
    final_started_at: datetime | None,
    final_fingerprint: str | None,
    collection_finished_at: datetime | None,
    timing_finished_at: datetime | None,
    audit_finished_at: datetime | None,
    ev_finished_at: datetime | None,
    finished_at: datetime,
    started_monotonic: float,
    monotonic: Callable[[], float],
    terminal_reason: str,
    collection: ProspectiveCollectionResult | None,
    timing_eligibility: PlayTimingEligibility,
    audit: CoverageAudit | None,
    progress_callback: ProgressCallback | None,
) -> DrawingRunnerResult:
    elapsed_seconds = _elapsed_seconds(started_monotonic, monotonic)
    result = DrawingRunnerResult(
        config=config,
        target=target,
        preflight_at=preflight_at,
        final_started_at=final_started_at,
        final_fingerprint=final_fingerprint,
        collection_finished_at=collection_finished_at,
        timing_finished_at=timing_finished_at,
        audit_finished_at=audit_finished_at,
        ev_finished_at=ev_finished_at,
        finished_at=finished_at,
        elapsed_seconds=elapsed_seconds,
        decision="NO BET",
        terminal_reason=terminal_reason,
        collection=collection,
        timing_eligibility=timing_eligibility,
        audit=audit,
        ev_run=None,
    )
    _notify(progress_callback, "complete", decision="NO BET")
    return result


def _require_pinned_target(name: str, value: object) -> None:
    if not isinstance(value, PinnedDrawing):
        raise ValueError(f"{name} resolver must return PinnedDrawing")


def _read_now(now: Callable[[], datetime]) -> datetime:
    value = now()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("now must return timezone-aware UTC datetimes")
    if value.utcoffset() != timedelta(0):
        raise ValueError("now must return timezone-aware UTC datetimes")
    return value


def _read_monotonic(monotonic: Callable[[], float]) -> float:
    value = monotonic()
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
    ):
        raise ValueError("monotonic must return a finite number")
    return float(value)


def _elapsed_seconds(
    started_monotonic: float,
    monotonic: Callable[[], float],
) -> float:
    elapsed = _read_monotonic(monotonic) - started_monotonic
    if elapsed < 0:
        raise ValueError("monotonic clock must not move backwards")
    return elapsed


def _is_closed(schedule: RunnerSchedule, current_time: datetime) -> bool:
    return runner_window(schedule, current_time) == "closed"


def _notify(
    callback: ProgressCallback | None,
    phase: str,
    **values: object,
) -> None:
    if callback is not None:
        callback({"phase": phase, **values})
