from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from toto_ai.ev.drawing import EVPackageRun
from toto_ai.ev.models import (
    EVConfig,
    EVInput,
    EVPackage,
    EVSurface,
    PlayTimingEligibility,
    RankedCoupon,
)
from toto_ai.external_odds.audit import (
    CoverageAudit,
    CoverageGate,
    CoverageMetrics,
)
from toto_ai.external_odds.collection import (
    ExternalCollectionSnapshot,
    ExternalEventDispositionRecord,
)
from toto_ai.external_odds.domain import TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.prospective import (
    ProspectiveCollectionPass,
    ProspectiveCollectionResult,
)
from toto_ai.runner import (
    DrawingRunnerConfig,
    DrawingRunnerResult,
    RunnerTargetMismatch,
    pin_drawing,
    run_drawing,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 16, 15, tzinfo=UTC)
T_MINUS_21 = DEADLINE - timedelta(minutes=21)
T_MINUS_20 = DEADLINE - timedelta(minutes=20)
T_MINUS_19 = DEADLINE - timedelta(minutes=19)
T_MINUS_18 = DEADLINE - timedelta(minutes=18)
T_MINUS_5 = DEADLINE - timedelta(minutes=5)


class SequenceClock:
    def __init__(self, *values):
        if not values:
            raise ValueError("at least one clock value is required")
        self._values = values
        self._index = 0

    def __call__(self):
        index = min(self._index, len(self._values) - 1)
        self._index += 1
        return self._values[index]


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def _target(
    *,
    drawing_id: int = 11953,
    drawing_number: int = 4945,
    deadline: datetime = DEADLINE,
    fetched_at: datetime = T_MINUS_21,
    home_prefix: str = "Home",
) -> TargetDrawing:
    events = tuple(
        TargetEvent(
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            event_id=drawing_id * 100 + event_order,
            event_order=event_order,
            sport="football",
            championship="Test Championship",
            starts_at=deadline + timedelta(hours=event_order),
            deadline=deadline,
            home_team=f"{home_prefix} {event_order}",
            away_team=f"Away {event_order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.2, 0.3, 0.5),
        )
        for event_order in range(15)
    )
    return TargetDrawing(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        deadline=deadline,
        fetched_at=fetched_at,
        events=events,
    )


def _eligibility(target: TargetDrawing) -> DrawingEligibility:
    return DrawingEligibility(
        status="playable",
        earliest_start=target.events[0].starts_at,
        latest_start=target.events[-1].starts_at,
        span_days=2,
        missing_event_orders=(),
        totobrief_count=15,
        provider_count=0,
    )


def _event_dispositions(
    target: TargetDrawing,
) -> tuple[ExternalEventDispositionRecord, ...]:
    return tuple(
        ExternalEventDispositionRecord(
            drawing_id=target.drawing_id,
            event_order=event.event_order,
            target_event_id=event.event_id,
            sport=event.sport,
            championship=event.championship,
            starts_at=event.starts_at.isoformat(),
            home_team=event.home_team,
            away_team=event.away_team,
            home_team_en=event.home_team_en,
            away_team_en=event.away_team_en,
            match_status="missing",
            provider_event_id=None,
            provider_event_fetched_at=None,
            provider_event_payload_hash=None,
            matcher_version="v3",
            match_candidate_ids=(),
            match_reason="0 exact candidates",
            probability_source="totobrief_bk_fallback",
            probability_1=event.bk_probabilities[0],
            probability_x=event.bk_probabilities[1],
            probability_2=event.bk_probabilities[2],
            eligible_bookmaker_count=0,
            odds_age_hours=None,
            fallback_reason="0 exact candidates",
            payload_hash=f"event-{event.event_order}",
            effective_starts_at=event.starts_at.isoformat(),
            effective_start_source="totobrief",
        )
        for event in target.events
    )


def _collection(target: TargetDrawing) -> ProspectiveCollectionResult:
    pinned = pin_drawing(target)
    eligibility = _eligibility(target)
    snapshot = ExternalCollectionSnapshot(
        collection_id="collection-1",
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider="api-sports",
        fetched_at=T_MINUS_18.isoformat(),
        target_fetched_at=target.fetched_at.isoformat(),
        deadline=target.deadline.isoformat(),
        event_count=15,
        requests_made=1,
        cache_hits=0,
        daily_limit=100,
        daily_remaining=99,
        minute_remaining=9,
        status="complete",
        events=_event_dispositions(target),
        target_fingerprint=pinned.fingerprint,
        missing_start_horizon_days=2,
        eligibility=eligibility,
        pinned_revalidation=ready_pinned_revalidation(T_MINUS_18),
    )
    collection_pass = ProspectiveCollectionPass(
        snapshot=snapshot,
        elapsed_seconds=1.0,
        phase="base",
        phase_pass_number=1,
        horizon_days=2,
    )
    return ProspectiveCollectionResult(
        snapshot=snapshot,
        passes=(collection_pass,),
        base_passes=(collection_pass,),
        expansion_passes=(),
        cache_dir=Path("unused-test-cache"),
        elapsed_seconds=1.0,
        stop_reason="no_retryable_fallbacks",
        expanded=False,
        final_horizon_days=2,
        total_requests=1,
        total_cache_hits=0,
        total_requested_schedule_dates=0,
        total_successful_schedule_dates=0,
        total_failed_schedule_dates=0,
        eligibility=eligibility,
    )


def _metrics() -> CoverageMetrics:
    return CoverageMetrics(
        scope="overall",
        name="all",
        target_count=15,
        explicit_dispositions=15,
        unique_match_count=0,
        unique_match_rate=0.0,
        missing_count=15,
        missing_rate=1.0,
        provider_missing_count=15,
        partial_schedule_count=0,
        ambiguous_count=0,
        ambiguous_rate=0.0,
        unknown_sport_count=0,
        unknown_sport_rate=0.0,
        consensus_1_count=0,
        consensus_1_rate=0.0,
        consensus_2_count=0,
        consensus_2_rate=0.0,
        consensus_3_count=0,
        consensus_3_rate=0.0,
        usable_consensus_count=0,
        usable_consensus_rate=0.0,
        stale_count=0,
        semantic_count=0,
        incomplete_market_count=0,
        quota_count=0,
        provider_error_count=0,
        fallback_count=15,
    )


def _audit(
    collection: ProspectiveCollectionResult,
    *,
    decision: str = "PENDING",
) -> CoverageAudit:
    metrics = _metrics()
    return CoverageAudit(
        provider="api-sports",
        requested_last=30,
        drawings=1,
        minimum_bookmakers=3,
        consensus_minimum_bookmakers=3,
        consensus_maximum_age_hours=36.0,
        collections=(collection.snapshot,),
        dispositions=(),
        total=metrics,
        by_sport=(),
        by_league=(),
        by_drawing=(),
        by_scope=(),
        eligibility_counts={"playable": 1},
        requested_schedule_date_count=0,
        successful_schedule_date_count=0,
        failed_schedule_date_count=0,
        failed_schedule_reason_counts={},
        fallback_reason_counts={"0 exact candidates": 15},
        fallback_median_per_drawing=15.0,
        fallback_p90_per_drawing=15.0,
        average_requests_per_drawing=1.0,
        maximum_requests_per_drawing=1,
        gate=CoverageGate(
            decision=decision,
            reasons=("prospective sample floor not met",),
            drawings=1,
            events=15,
            unique_match_rate=0.0,
            consensus_rate=0.0,
            ambiguous_matches=0,
            explicit_dispositions=15,
            operational_failures=0,
            predicates=(),
        ),
    )


def _timing(
    target: TargetDrawing,
    status: str = "playable",
) -> PlayTimingEligibility:
    fingerprint = pin_drawing(target).fingerprint
    if status == "not_checked":
        return PlayTimingEligibility.not_checked()
    return PlayTimingEligibility(
        status=status,
        reason=f"timing status is {status}",
        target_fingerprint=fingerprint,
        fingerprint_match=status != "absent",
    )


def _ranked_coupon() -> RankedCoupon:
    return RankedCoupon(
        rank=1,
        coupon="1" * 15,
        gross_ev=1.1,
        net_ev=0.1,
    )


def _ev_run(
    target: TargetDrawing,
    *,
    mode: str = "playable",
    decision: str | None = None,
    decision_reason: str | None = None,
) -> EVPackageRun:
    resolved_decision = decision or (
        "RESEARCH ONLY" if mode == "research" else "PLAY"
    )
    selected = () if resolved_decision == "NO BET" else (_ranked_coupon(),)
    cost = 30 if selected else 0
    return EVPackageRun(
        config=EVConfig(
            bank=4980,
            stake=30,
            mode=mode,
            effective_budget=90,
        ),
        ev_input=EVInput(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            true_probabilities=((0.2, 0.3, 0.5),) * 15,
            crowd_probabilities=((0.3, 0.3, 0.4),) * 15,
            pool_sum=10000.0,
            jackpot=0.0,
            possible_winnings=10000.0,
            probability_sources=("totobrief_bk",) * 15,
            fetched_at=T_MINUS_18.isoformat(),
        ),
        surface=EVSurface(
            gross_ev=np.array([1.1]),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        ),
        package=EVPackage(
            decision=resolved_decision,
            coupons=selected,
            cost=cost,
            unused_bank=4980 - cost,
            expected_payout=33.0 if selected else 0.0,
            modeled_roi=0.1 if selected else None,
            derived_brief=("1",) * 15 if selected else (),
            decision_reason=decision_reason,
        ),
        top_coupons=(_ranked_coupon(),),
        sensitivity=(),
        possible_winnings_source="pool_sum proxy",
        jackpot_source="totobrief payload",
        self_dilution_ratio=cost / 10000.0,
        model_supported=True,
        model_warning=None,
        timing_eligibility=_timing(target),
    )


def _recording_resolver(calls, *targets):
    index = 0

    def resolve(resolved_at):
        nonlocal index
        phase = "preflight" if index == 0 else "final"
        calls.append(phase)
        target = targets[min(index, len(targets) - 1)]
        index += 1
        return target

    return resolve


def _recording_dependencies(calls, target, collection, audit, timing, ev_run):
    def collect(resolved_target, stop_at):
        calls.append("collect")
        assert resolved_target == target
        assert stop_at == T_MINUS_5
        return collection

    def resolve_timing(pinned):
        calls.append("timing")
        assert pinned == pin_drawing(target)
        return timing

    def audit_coverage():
        calls.append("audit")
        return audit

    def build_package(pinned):
        calls.append("ev")
        assert pinned == pin_drawing(target)
        return ev_run

    return collect, resolve_timing, audit_coverage, build_package


def _complete_result(
    *,
    decision: str = "PLAY",
    target: TargetDrawing | None = None,
    collection: ProspectiveCollectionResult | None = None,
    timing: PlayTimingEligibility | None = None,
    audit: CoverageAudit | None = None,
    ev_run: EVPackageRun | None = None,
) -> DrawingRunnerResult:
    resolved_target = target or _target(fetched_at=T_MINUS_19)
    resolved_collection = collection or _collection(resolved_target)
    resolved_timing = timing or _timing(resolved_target)
    resolved_audit = audit or _audit(resolved_collection)
    resolved_ev = ev_run
    if resolved_ev is None and decision != "NO BET":
        resolved_ev = _ev_run(
            resolved_target,
            mode="research" if decision == "RESEARCH ONLY" else "playable",
        )
    return DrawingRunnerResult(
        config=DrawingRunnerConfig(
            bank=4980,
            mode="research" if decision == "RESEARCH ONLY" else "playable",
        ),
        target=pin_drawing(resolved_target),
        preflight_at=T_MINUS_20,
        final_started_at=T_MINUS_19,
        final_fingerprint=pin_drawing(resolved_target).fingerprint,
        collection_finished_at=T_MINUS_18,
        timing_finished_at=T_MINUS_18 + timedelta(seconds=1),
        audit_finished_at=T_MINUS_18 + timedelta(seconds=2),
        ev_finished_at=(
            T_MINUS_18 + timedelta(seconds=3) if resolved_ev is not None else None
        ),
        finished_at=T_MINUS_18 + timedelta(seconds=4),
        elapsed_seconds=4.0,
        decision=decision,
        terminal_reason="test terminal reason",
        collection=resolved_collection,
        timing_eligibility=resolved_timing,
        audit=resolved_audit,
        ev_run=resolved_ev,
    )


def test_normal_playable_run_orders_every_phase():
    target = _target()
    pinned = pin_drawing(target)
    collection = _collection(target)
    timing = _timing(target)
    audit = _audit(collection)
    ev_run = _ev_run(target)
    calls = []
    updates = []
    sleeps = []
    dependencies = _recording_dependencies(
        calls, target, collection, audit, timing, ev_run
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=SequenceClock(T_MINUS_21, T_MINUS_20, T_MINUS_19, T_MINUS_18),
        monotonic=SequenceClock(10.0, 14.0),
        sleep=sleeps.append,
        progress_callback=updates.append,
    )

    assert result.decision == "PLAY"
    assert result.target == pinned
    assert result.final_fingerprint == pinned.fingerprint
    assert result.collection == collection
    assert result.audit == audit
    assert result.ev_run == ev_run
    assert result.ev_run.effective_budget == 90
    assert result.ev_run.selected_cost == 30
    assert result.ev_run.unused_requested_bank == 4950
    assert result.elapsed_seconds == 4.0
    assert calls == ["preflight", "final", "collect", "timing", "audit", "ev"]
    assert sleeps == []
    assert [update["phase"] for update in updates] == [
        "preflight",
        "final",
        "collect",
        "timing",
        "audit",
        "ev",
        "complete",
    ]


def test_preflight_check_failure_stops_before_wait_and_provider_access():
    pinned = pin_drawing(_target())
    calls: list[str] = []

    def preflight_check(target, preflight_at):
        calls.append("preflight-check")
        assert target == pinned
        assert preflight_at == T_MINUS_21
        raise OSError("report directory is not writable")

    with pytest.raises(OSError, match="not writable"):
        run_drawing(
            config=DrawingRunnerConfig(bank=4980),
            resolve_target=_recording_resolver(calls, pinned),
            collect_target=lambda *_args: pytest.fail(
                "collection must not start"
            ),
            resolve_timing=lambda *_args: pytest.fail("timing must not start"),
            audit_coverage=lambda: pytest.fail("audit must not start"),
            build_package=lambda *_args: pytest.fail("EV must not start"),
            now=SequenceClock(T_MINUS_21),
            monotonic=SequenceClock(10.0),
            sleep=lambda _seconds: pytest.fail("wait must not start"),
            preflight_check=preflight_check,
        )

    assert calls == ["preflight", "preflight-check"]


def test_launch_before_final_window_waits_with_injected_sleep():
    target = _target()
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    sleeps = []
    updates = []
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        _ev_run(target),
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=SequenceClock(T_MINUS_21, T_MINUS_21, T_MINUS_20, T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=sleeps.append,
        progress_callback=updates.append,
    )

    assert result.decision == "PLAY"
    assert sleeps == [30.0]
    assert [update["phase"] for update in updates] == [
        "preflight",
        "waiting",
        "final",
        "collect",
        "timing",
        "audit",
        "ev",
        "complete",
    ]


def test_immediate_final_window_launch_does_not_sleep():
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    sleeps = []
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        _ev_run(target),
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 1.5),
        sleep=sleeps.append,
    )

    assert result.decision == "PLAY"
    assert sleeps == []


def test_already_closed_launch_stops_after_preflight():
    target = _target(fetched_at=T_MINUS_5)
    calls = []
    updates = []

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pin_drawing(target)),
        collect_target=lambda *_args: pytest.fail("provider must not run"),
        resolve_timing=lambda _target: pytest.fail("timing must not run"),
        audit_coverage=lambda: pytest.fail("audit must not run"),
        build_package=lambda _drawing_id: pytest.fail("EV must not run"),
        now=SequenceClock(T_MINUS_5),
        monotonic=SequenceClock(1.0, 1.25),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=updates.append,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "safety cutoff reached before final resolve"
    assert result.final_started_at is None
    assert result.final_fingerprint is None
    assert calls == ["preflight"]
    assert [update["phase"] for update in updates] == ["preflight", "complete"]


def _changed_pinned_target(kind: str):
    if kind == "id":
        return pin_drawing(_target(drawing_id=11954, fetched_at=T_MINUS_19))
    if kind == "number":
        return pin_drawing(_target(drawing_number=4946, fetched_at=T_MINUS_19))
    if kind == "deadline":
        return pin_drawing(
            _target(deadline=DEADLINE + timedelta(hours=1), fetched_at=T_MINUS_19)
        )
    if kind == "fingerprint":
        return pin_drawing(_target(home_prefix="Changed", fetched_at=T_MINUS_19))
    raise AssertionError(f"unexpected target change kind: {kind}")


@pytest.mark.parametrize("kind", ["id", "number", "deadline", "fingerprint"])
def test_target_change_fails_closed_before_provider_access(kind):
    preflight = pin_drawing(_target())
    changed_final = _changed_pinned_target(kind)
    calls = []
    updates = []

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, preflight, changed_final),
        collect_target=lambda *_args: pytest.fail("provider must not run"),
        resolve_timing=lambda _target: pytest.fail("timing must not run"),
        audit_coverage=lambda: pytest.fail("audit must not run"),
        build_package=lambda _drawing_id: pytest.fail("EV must not run"),
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 1.25),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=updates.append,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "final target does not match preflight"
    assert result.target == preflight
    assert result.final_fingerprint == changed_final.fingerprint
    assert calls == ["preflight", "final"]
    assert [update["phase"] for update in updates] == [
        "preflight",
        "final",
        "complete",
    ]


@pytest.mark.parametrize("status", ["unknown", "multi_day", "absent", "not_checked"])
def test_non_playable_timing_runs_audit_but_skips_ev(status):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    updates = []

    def collect(resolved_target, stop_at):
        calls.append("collect")
        assert resolved_target == target
        assert stop_at == T_MINUS_5
        return collection

    def resolve_timing(_target):
        calls.append("timing")
        return _timing(target, status)

    def audit_coverage():
        calls.append("audit")
        return _audit(collection)

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=collect,
        resolve_timing=resolve_timing,
        audit_coverage=audit_coverage,
        build_package=lambda _drawing_id: pytest.fail("EV must not run"),
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=updates.append,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == f"timing eligibility is not playable: {status}"
    assert result.ev_run is None
    assert calls == ["preflight", "final", "collect", "timing", "audit"]
    assert [update["phase"] for update in updates] == [
        "preflight",
        "final",
        "collect",
        "timing",
        "audit",
        "complete",
    ]


def test_research_mode_retains_research_only_package_despite_timing_warning():
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    ev_run = _ev_run(target, mode="research")
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target, "unknown"),
        ev_run,
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980, mode="research"),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
    )

    assert result.decision == "RESEARCH ONLY"
    assert result.ev_run == ev_run
    assert result.timing_eligibility.status == "unknown"


@pytest.mark.parametrize("coverage_decision", ["GO", "PENDING", "STOP"])
def test_coverage_is_diagnostic_and_does_not_change_ev_input_or_decision(
    coverage_decision,
):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    built_for = []

    def build_package(pinned):
        calls.append("ev")
        built_for.append(pinned)
        return _ev_run(target)

    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection, decision=coverage_decision),
        _timing(target),
        _ev_run(target),
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=build_package,
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
    )

    assert result.audit.gate.decision == coverage_decision
    assert result.decision == "PLAY"
    assert built_for == [pinned]


@pytest.mark.parametrize(
    ("cutoff_phase", "expected_calls", "expected_progress"),
    [
        (
            "collection",
            ["preflight", "final"],
            ["preflight", "final", "complete"],
        ),
        (
            "audit",
            ["preflight", "final", "collect", "timing"],
            ["preflight", "final", "collect", "timing", "complete"],
        ),
        (
            "ev",
            ["preflight", "final", "collect", "timing", "audit"],
            ["preflight", "final", "collect", "timing", "audit", "complete"],
        ),
    ],
)
def test_safety_cutoff_is_rechecked_before_bound_phases(
    cutoff_phase, expected_calls, expected_progress
):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    clock = MutableClock(T_MINUS_19)
    calls = []
    updates = []

    def resolve(resolved_at):
        phase = "preflight" if not calls else "final"
        calls.append(phase)
        if phase == "final" and cutoff_phase == "collection":
            clock.value = T_MINUS_5
        return pinned

    def collect(_target, _stop_at):
        calls.append("collect")
        return collection

    def resolve_timing(_target):
        calls.append("timing")
        if cutoff_phase == "audit":
            clock.value = T_MINUS_5
        return _timing(target)

    def audit_coverage():
        calls.append("audit")
        if cutoff_phase == "ev":
            clock.value = T_MINUS_5
        return _audit(collection)

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=resolve,
        collect_target=collect,
        resolve_timing=resolve_timing,
        audit_coverage=audit_coverage,
        build_package=lambda _drawing_id: pytest.fail("EV must not run"),
        now=clock,
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=updates.append,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == f"safety cutoff reached before {cutoff_phase}"
    assert calls == expected_calls
    assert [update["phase"] for update in updates] == expected_progress


@pytest.mark.parametrize(
    ("cutoff_phase", "terminal_phase", "expected_calls"),
    [
        ("final", "final resolve", ["preflight"]),
        ("collect", "collection", ["preflight", "final"]),
        ("timing", "timing", ["preflight", "final", "collect"]),
        ("audit", "audit", ["preflight", "final", "collect", "timing"]),
        ("ev", "ev", ["preflight", "final", "collect", "timing", "audit"]),
    ],
)
def test_progress_callback_cutoff_skips_the_notified_bound_phase(
    cutoff_phase, terminal_phase, expected_calls
):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    clock = MutableClock(T_MINUS_19)
    calls = []
    updates = []

    def progress_callback(update):
        updates.append(update)
        if update["phase"] == cutoff_phase:
            clock.value = T_MINUS_5

    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        _ev_run(target),
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=clock,
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=progress_callback,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == f"safety cutoff reached before {terminal_phase}"
    assert calls == expected_calls
    assert [update["phase"] for update in updates] == [
        *expected_calls,
        cutoff_phase,
        "complete",
    ]


@pytest.mark.parametrize("mode", ["playable", "research"])
def test_package_completing_at_cutoff_is_discarded_in_every_mode(mode):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    clock = MutableClock(T_MINUS_19)
    calls = []
    ev_run = _ev_run(target, mode=mode)
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        ev_run,
    )

    def build_package(expected):
        calls.append("ev")
        assert expected == pinned
        clock.value = T_MINUS_5
        return ev_run

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980, mode=mode),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=build_package,
        now=clock,
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "safety cutoff reached after EV"
    assert result.ev_run is None
    assert result.ev_finished_at == T_MINUS_5
    assert calls == ["preflight", "final", "collect", "timing", "audit", "ev"]


@pytest.mark.parametrize("mode", ["playable", "research"])
def test_complete_callback_reaching_cutoff_suppresses_actionable_result(mode):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    clock = MutableClock(T_MINUS_19)
    calls = []
    updates = []
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        _ev_run(target, mode=mode),
    )

    def progress_callback(update):
        updates.append(update)
        if update["phase"] == "complete":
            clock.value = T_MINUS_5

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980, mode=mode),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=clock,
        monotonic=SequenceClock(1.0, 2.0, 3.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
        progress_callback=progress_callback,
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "safety cutoff reached after complete"
    assert result.ev_run is None
    assert result.ev_finished_at == T_MINUS_19
    assert result.finished_at == T_MINUS_5
    assert [update["phase"] for update in updates].count("complete") == 1


def test_second_fetch_target_mismatch_is_coupon_free_no_bet():
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        _ev_run(target),
    )

    def build_package(expected_target):
        calls.append("ev")
        assert expected_target == pinned
        raise RunnerTargetMismatch("fresh EV target does not match pinned target")

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=build_package,
        now=MutableClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == "fresh EV target does not match pinned target"
    assert result.ev_run is None
    assert result.ev_finished_at is None
    assert calls == ["preflight", "final", "collect", "timing", "audit", "ev"]


def test_success_validation_failure_does_not_emit_complete_progress():
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    updates = []
    bad_ev_run = replace(
        _ev_run(target),
        ev_input=replace(_ev_run(target).ev_input, drawing_id=99999),
    )
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        bad_ev_run,
    )

    with pytest.raises(ValueError, match="EV target"):
        run_drawing(
            config=DrawingRunnerConfig(bank=4980),
            resolve_target=_recording_resolver(calls, pinned, pinned),
            collect_target=dependencies[0],
            resolve_timing=dependencies[1],
            audit_coverage=dependencies[2],
            build_package=dependencies[3],
            now=SequenceClock(T_MINUS_19),
            monotonic=SequenceClock(1.0, 2.0),
            sleep=lambda _seconds: pytest.fail("sleep must not run"),
            progress_callback=updates.append,
        )

    assert [update["phase"] for update in updates] == [
        "preflight",
        "final",
        "collect",
        "timing",
        "audit",
        "ev",
    ]


def test_fail_closed_validation_failure_does_not_emit_complete_progress():
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    mismatched_collection = replace(
        collection,
        snapshot=replace(collection.snapshot, drawing_number=9999),
    )
    clock = MutableClock(T_MINUS_19)
    calls = []
    updates = []

    def collect(_target, _stop_at):
        calls.append("collect")
        clock.value = T_MINUS_5
        return mismatched_collection

    with pytest.raises(ValueError, match="collection target"):
        run_drawing(
            config=DrawingRunnerConfig(bank=4980),
            resolve_target=_recording_resolver(calls, pinned, pinned),
            collect_target=collect,
            resolve_timing=lambda _target: pytest.fail("timing must not run"),
            audit_coverage=lambda: pytest.fail("audit must not run"),
            build_package=lambda _drawing_id: pytest.fail("EV must not run"),
            now=clock,
            monotonic=SequenceClock(1.0, 2.0),
            sleep=lambda _seconds: pytest.fail("sleep must not run"),
            progress_callback=updates.append,
        )

    assert calls == ["preflight", "final", "collect"]
    assert [update["phase"] for update in updates] == [
        "preflight",
        "final",
        "collect",
    ]


@pytest.mark.parametrize(
    ("decision_reason", "expected_reason"),
    [
        (None, "EV package returned NO BET"),
        ("timing:multi_day", "timing:multi_day"),
        (
            "self_dilution:package_cost_exceeds_1_percent_pool",
            "self_dilution:package_cost_exceeds_1_percent_pool",
        ),
    ],
)
def test_ev_no_bet_retains_zero_cost_run_and_actual_gate_reason(
    decision_reason,
    expected_reason,
):
    target = _target(fetched_at=T_MINUS_19)
    pinned = pin_drawing(target)
    collection = _collection(target)
    calls = []
    ev_run = _ev_run(
        target,
        decision="NO BET",
        decision_reason=decision_reason,
    )
    dependencies = _recording_dependencies(
        calls,
        target,
        collection,
        _audit(collection),
        _timing(target),
        ev_run,
    )

    result = run_drawing(
        config=DrawingRunnerConfig(bank=4980),
        resolve_target=_recording_resolver(calls, pinned, pinned),
        collect_target=dependencies[0],
        resolve_timing=dependencies[1],
        audit_coverage=dependencies[2],
        build_package=dependencies[3],
        now=SequenceClock(T_MINUS_19),
        monotonic=SequenceClock(1.0, 2.0),
        sleep=lambda _seconds: pytest.fail("sleep must not run"),
    )

    assert result.decision == "NO BET"
    assert result.terminal_reason == expected_reason
    assert result.ev_run == ev_run
    assert result.ev_run.package.cost == 0
    assert result.ev_run.package.coupons == ()
    assert result.ev_run.top_coupons


def test_result_rejects_play_without_a_play_package():
    target = _target(fetched_at=T_MINUS_19)
    with pytest.raises(ValueError, match="PLAY requires"):
        _complete_result(
            decision="PLAY",
            target=target,
            ev_run=_ev_run(target, decision="NO BET"),
        )


def test_result_rejects_play_without_exact_playable_timing():
    target = _target(fetched_at=T_MINUS_19)

    with pytest.raises(ValueError, match="PLAY requires playable timing"):
        _complete_result(
            decision="PLAY",
            target=target,
            timing=_timing(target, "unknown"),
        )


def test_result_rejects_play_when_ev_run_timing_is_not_playable():
    target = _target(fetched_at=T_MINUS_19)
    ev_run = replace(
        _ev_run(target),
        timing_eligibility=_timing(target, "unknown"),
    )

    with pytest.raises(ValueError, match="EV playable timing"):
        _complete_result(decision="PLAY", target=target, ev_run=ev_run)


def test_result_rejects_research_only_without_a_research_package():
    target = _target(fetched_at=T_MINUS_19)
    with pytest.raises(ValueError, match="RESEARCH ONLY requires"):
        _complete_result(
            decision="RESEARCH ONLY",
            target=target,
            ev_run=_ev_run(target, mode="research", decision="NO BET"),
        )


@pytest.mark.parametrize(("cost", "selected"), [(30, False), (0, True)])
def test_result_rejects_actionable_ev_package_on_no_bet(cost, selected):
    target = _target(fetched_at=T_MINUS_19)
    ev_run = _ev_run(target, decision="NO BET")
    bad_package = replace(
        ev_run.package,
        cost=cost,
        coupons=(_ranked_coupon(),) if selected else (),
    )

    with pytest.raises(ValueError, match="NO BET"):
        _complete_result(
            decision="NO BET",
            target=target,
            ev_run=replace(ev_run, package=bad_package),
        )


def test_result_allows_zero_cost_no_bet_with_diagnostic_top_coupons():
    target = _target(fetched_at=T_MINUS_19)
    ev_run = _ev_run(target, decision="NO BET")

    result = _complete_result(
        decision="NO BET",
        target=target,
        ev_run=ev_run,
    )

    assert result.ev_run == ev_run
    assert result.ev_run.top_coupons


def test_result_rejects_collection_from_a_different_target():
    target = _target(fetched_at=T_MINUS_19)
    collection = _collection(target)
    mismatched = replace(
        collection,
        snapshot=replace(collection.snapshot, drawing_number=9999),
    )

    with pytest.raises(ValueError, match="collection target"):
        _complete_result(target=target, collection=mismatched)


def test_result_rejects_timing_fingerprint_from_a_different_target():
    target = _target(fetched_at=T_MINUS_19)
    other = _target(home_prefix="Other", fetched_at=T_MINUS_19)

    with pytest.raises(ValueError, match="timing target"):
        _complete_result(target=target, timing=_timing(other))


def test_result_rejects_ev_input_from_a_different_target():
    target = _target(fetched_at=T_MINUS_19)
    ev_run = _ev_run(target)
    mismatched_input = replace(ev_run.ev_input, drawing_id=99999)

    with pytest.raises(ValueError, match="EV target"):
        _complete_result(
            target=target,
            ev_run=replace(ev_run, ev_input=mismatched_input),
        )


def test_result_rejects_naive_phase_timestamp():
    result = _complete_result()

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replace(result, collection_finished_at=T_MINUS_18.replace(tzinfo=None))


def test_result_rejects_final_fingerprint_without_final_start():
    result = _complete_result()

    with pytest.raises(ValueError, match="final fingerprint requires final_started_at"):
        replace(result, final_started_at=None)


def test_result_rejects_completed_final_without_fingerprint():
    result = _complete_result()

    with pytest.raises(ValueError, match="final resolve requires a fingerprint"):
        replace(result, final_fingerprint=None)


def test_result_rejects_mismatched_final_fingerprint_after_collection():
    result = _complete_result()
    changed_final = pin_drawing(_target(home_prefix="Changed"))

    with pytest.raises(ValueError, match="final fingerprint must match"):
        replace(result, final_fingerprint=changed_final.fingerprint)


def test_result_rejects_mismatched_final_fingerprint_with_checked_timing():
    target = _target()
    preflight = pin_drawing(target)
    changed_final = pin_drawing(_target(home_prefix="Changed"))

    with pytest.raises(ValueError, match="final fingerprint must match"):
        DrawingRunnerResult(
            config=DrawingRunnerConfig(bank=4980),
            target=preflight,
            preflight_at=T_MINUS_20,
            final_started_at=T_MINUS_19,
            final_fingerprint=changed_final.fingerprint,
            collection_finished_at=None,
            timing_finished_at=None,
            audit_finished_at=None,
            ev_finished_at=None,
            finished_at=T_MINUS_19,
            elapsed_seconds=1.0,
            decision="NO BET",
            terminal_reason="test terminal reason",
            collection=None,
            timing_eligibility=_timing(target),
            audit=None,
            ev_run=None,
        )


def test_result_rejects_non_chronological_phase_timestamps():
    result = _complete_result()

    with pytest.raises(ValueError, match="chronological"):
        replace(result, final_started_at=result.preflight_at - timedelta(seconds=1))


def test_result_rejects_missing_earlier_phase_timestamp():
    result = _complete_result()

    with pytest.raises(ValueError, match="phase timestamps"):
        replace(result, collection_finished_at=None)
