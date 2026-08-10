import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

import toto_ai.runner.reports as runner_reports
from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from toto_ai.ev.drawing import EVPackageRun, EVSensitivitySummary
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
from toto_ai.external_odds.timing_overrides import (
    TimingOverrideCatalog,
    TimingOverrideEvent,
    TimingOverrideRecord,
    classify_timing_snapshot,
    drawing_timing_snapshot_from_collection,
    overlay_timing_override,
    timing_override_catalog_sha256,
)
from toto_ai.runner import (
    DrawingRunnerConfig,
    DrawingRunnerResult,
    TimingOverrideAudit,
    pin_drawing,
)
from toto_ai.runner.reports import (
    DrawingRunPublication,
    RunnerReportLinks,
    drawing_run_candidate_paths,
    drawing_run_id,
    drawing_run_report_paths,
    publish_drawing_run_artifacts,
    write_drawing_run_reports,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 16, 15, tzinfo=UTC)
PREFLIGHT_AT = DEADLINE - timedelta(minutes=20)
FINAL_STARTED_AT = DEADLINE - timedelta(minutes=19)


def _target(
    *,
    drawing_id: int = 11953,
    drawing_number: int = 4945,
) -> TargetDrawing:
    events = tuple(
        TargetEvent(
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            event_id=20000 + order,
            event_order=order,
            sport="football",
            championship="Test Championship",
            starts_at=DEADLINE + timedelta(hours=order),
            deadline=DEADLINE,
            home_team=f"Home {order}",
            away_team=f"Away {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.2, 0.3, 0.5),
        )
        for order in range(15)
    )
    return TargetDrawing(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        deadline=DEADLINE,
        fetched_at=PREFLIGHT_AT,
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


def _collection(target: TargetDrawing) -> ProspectiveCollectionResult:
    pinned = pin_drawing(target)
    eligibility = _eligibility(target)
    events = tuple(
        ExternalEventDispositionRecord(
            drawing_id=target.drawing_id,
            event_order=event.event_order,
            target_event_id=event.event_id,
            sport=event.sport,
            championship=event.championship,
            starts_at=event.starts_at.isoformat(),
            home_team=event.home_team,
            away_team=event.away_team,
            home_team_en=None,
            away_team_en=None,
            match_status="missing",
            provider_event_id=None,
            provider_event_fetched_at=None,
            provider_event_payload_hash=None,
            matcher_version="v3",
            match_candidate_ids=(),
            match_reason="0 exact candidates",
            probability_source="totobrief_bk_fallback",
            probability_1=0.2,
            probability_x=0.3,
            probability_2=0.5,
            eligible_bookmaker_count=0,
            odds_age_hours=None,
            fallback_reason="0 exact candidates",
            payload_hash=f"event-{event.event_order}",
            effective_starts_at=event.starts_at.isoformat(),
            effective_start_source="totobrief",
        )
        for event in target.events
    )
    snapshot = ExternalCollectionSnapshot(
        collection_id="collection-final",
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider="api-sports",
        fetched_at=(FINAL_STARTED_AT + timedelta(seconds=1)).isoformat(),
        target_fetched_at=target.fetched_at.isoformat(),
        deadline=target.deadline.isoformat(),
        event_count=15,
        requests_made=4,
        cache_hits=11,
        daily_limit=100,
        daily_remaining=96,
        minute_remaining=6,
        status="complete",
        events=events,
        target_fingerprint=pinned.fingerprint,
        missing_start_horizon_days=2,
        eligibility=eligibility,
        pinned_revalidation=ready_pinned_revalidation(
            FINAL_STARTED_AT + timedelta(seconds=1)
        ),
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
        cache_dir=Path("cache/secret-free-run"),
        elapsed_seconds=1.0,
        stop_reason="no_retryable_fallbacks",
        expanded=False,
        final_horizon_days=2,
        total_requests=4,
        total_cache_hits=11,
        total_requested_schedule_dates=4,
        total_successful_schedule_dates=4,
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


def _audit(collection: ProspectiveCollectionResult) -> CoverageAudit:
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
        eligibility_counts={"playable": 1, "multi_day": 0, "unknown": 0},
        requested_schedule_date_count=4,
        successful_schedule_date_count=4,
        failed_schedule_date_count=0,
        failed_schedule_reason_counts={},
        fallback_reason_counts={"0 exact candidates": 15},
        fallback_median_per_drawing=15.0,
        fallback_p90_per_drawing=15.0,
        average_requests_per_drawing=4.0,
        maximum_requests_per_drawing=4,
        gate=CoverageGate(
            decision="PENDING",
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


def _runner_result(
    decision: str,
    coupon: str = "UNIQUE-COUPON",
    *,
    top_coupon: str | None = None,
    target: TargetDrawing | None = None,
    effective_budget: int | None = 90,
) -> DrawingRunnerResult:
    target = target or _target()
    pinned = pin_drawing(target)
    collection = _collection(target)
    mode = "research" if decision == "RESEARCH ONLY" else "playable"
    selected = (
        ()
        if decision == "NO BET"
        else (RankedCoupon(rank=1, coupon=coupon, gross_ev=1.1, net_ev=0.1),)
    )
    diagnostic_coupon = RankedCoupon(
        rank=1,
        coupon=top_coupon or coupon,
        gross_ev=1.1,
        net_ev=0.1,
    )
    cost = 30 if selected else 0
    timing = PlayTimingEligibility(
        status="playable",
        reason="all event starts fit within two Moscow dates",
        target_fingerprint=pinned.fingerprint,
        fingerprint_match=True,
    )
    ev_run = EVPackageRun(
        config=EVConfig(
            bank=4980,
            stake=30,
            mode=mode,
            effective_budget=effective_budget,
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
            fetched_at=(FINAL_STARTED_AT + timedelta(seconds=4)).isoformat(),
        ),
        surface=EVSurface(
            gross_ev=np.array([1.1]),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        ),
        package=EVPackage(
            decision=decision,
            coupons=selected,
            cost=cost,
            unused_bank=4980 - cost,
            expected_payout=33.0 if selected else 0.0,
            modeled_roi=0.1 if selected else None,
            derived_brief=("1",) * 15 if selected else (),
        ),
        top_coupons=(diagnostic_coupon,),
        sensitivity=(
            EVSensitivitySummary(
                prize_fund_factor=1.0,
                possible_winnings=10000.0,
                decision=decision,
                selected_count=len(selected),
                cost=cost,
                unused_bank=4980 - cost,
                expected_payout=33.0 if selected else 0.0,
                modeled_roi=0.1 if selected else None,
            ),
        ),
        possible_winnings_source="pool_sum proxy",
        jackpot_source="totobrief payload",
        self_dilution_ratio=cost / 10000.0,
        model_supported=True,
        model_warning=None,
        timing_eligibility=timing,
    )
    return DrawingRunnerResult(
        config=DrawingRunnerConfig(bank=4980, mode=mode),
        target=pinned,
        preflight_at=PREFLIGHT_AT,
        final_started_at=FINAL_STARTED_AT,
        final_fingerprint=pinned.fingerprint,
        collection_finished_at=FINAL_STARTED_AT + timedelta(seconds=1),
        timing_finished_at=FINAL_STARTED_AT + timedelta(seconds=2),
        audit_finished_at=FINAL_STARTED_AT + timedelta(seconds=3),
        ev_finished_at=FINAL_STARTED_AT + timedelta(seconds=5),
        finished_at=FINAL_STARTED_AT + timedelta(seconds=6),
        elapsed_seconds=6.0,
        decision=decision,
        terminal_reason="runner completed with a deterministic test result",
        collection=collection,
        timing_eligibility=timing,
        audit=_audit(collection),
        ev_run=ev_run,
    )


def _runner_result_with_override(decision: str) -> DrawingRunnerResult:
    result = _runner_result(decision, coupon="SELECTED-COUPON")
    assert result.collection is not None
    target = result.target.target
    record = TimingOverrideRecord(
        schema_version=1,
        override_id="drawing-4945-reviewed-timing-v1",
        drawing_id=target.drawing_id,
        drawing_number=None,
        target_fingerprint=result.target.fingerprint,
        reviewer="operator@example.test",
        reviewed_at=PREFLIGHT_AT,
        source_ref="offline-review:drawing-4945",
        events=tuple(
            TimingOverrideEvent(
                event_order=event.event_order,
                event_id=event.event_id,
                starts_at=event.starts_at,
            )
            for event in target.events
        ),
    )
    catalog = TimingOverrideCatalog(records=(record,))
    catalog_hash = timing_override_catalog_sha256(catalog)
    raw_snapshot = drawing_timing_snapshot_from_collection(
        result.collection.snapshot
    )
    overlay = overlay_timing_override(raw_snapshot, catalog)
    assert overlay.complete_overlay is True
    audit = TimingOverrideAudit(
        status="applied",
        preflight_catalog_sha256=catalog_hash,
        timing_catalog_sha256=catalog_hash,
        package_catalog_sha256=catalog_hash,
        override_id=record.override_id,
        reviewer=record.reviewer,
        reviewed_at=record.reviewed_at,
        source_ref=record.source_ref,
        overlay_complete=True,
        applied_events=(),
        preserved_event_orders=tuple(range(15)),
        diagnostics=tuple(
            f"{item.code}: {item.message}" for item in overlay.diagnostics
        ),
        overlay_summary=classify_timing_snapshot(overlay.snapshot),
    )
    return replace(
        result,
        raw_timing_eligibility=result.timing_eligibility,
        timing_override=audit,
    )


def _terminal_result(*, final_target: TargetDrawing | None) -> DrawingRunnerResult:
    target = _target()
    pinned = pin_drawing(target)
    final = None if final_target is None else pin_drawing(final_target)
    final_started_at = None if final is None else FINAL_STARTED_AT
    return DrawingRunnerResult(
        config=DrawingRunnerConfig(bank=4980),
        target=pinned,
        preflight_at=PREFLIGHT_AT,
        final_started_at=final_started_at,
        collection_finished_at=None,
        timing_finished_at=None,
        audit_finished_at=None,
        ev_finished_at=None,
        finished_at=final_started_at or PREFLIGHT_AT,
        elapsed_seconds=0.0,
        decision="NO BET",
        terminal_reason=(
            "safety cutoff reached before final resolve"
            if final is None
            else "final target does not match preflight"
        ),
        collection=None,
        timing_eligibility=PlayTimingEligibility.not_checked(),
        audit=None,
        ev_run=None,
        final_fingerprint=None if final is None else final.fingerprint,
    )


def test_not_checked_timing_does_not_claim_partial_4964_timing_details() -> None:
    """An early 12/15 NO BET must remain a canonical not-checked payload."""

    result = _runner_result("NO BET")
    assert result.collection is not None
    partial = DrawingEligibility(
        status="unknown",
        earliest_start=DEADLINE,
        latest_start=DEADLINE + timedelta(hours=5, minutes=45),
        span_days=1,
        missing_event_orders=(5, 8, 10),
        totobrief_count=0,
        provider_count=12,
    )
    collection = replace(
        result.collection,
        snapshot=replace(result.collection.snapshot, eligibility=partial),
        eligibility=partial,
    )
    not_checked = PlayTimingEligibility.not_checked()
    result = replace(
        result,
        collection=collection,
        timing_eligibility=not_checked,
        raw_timing_eligibility=not_checked,
        timing_override=None,
        terminal_reason=(
            "pinned revalidation is not ready: matched=12/15; "
            "provider_failures=(5, 8, 10)"
        ),
    )

    payload = runner_reports._eligibility_payload(result)

    for timing in (payload, payload["raw"], payload["effective"]):
        assert timing["status"] == "not_checked"
        assert timing["span_days"] is None
        assert timing["missing_event_orders"] == []
        assert timing["totobrief_count"] is None
        assert timing["provider_count"] is None
        assert timing["operator_override_count"] in (None, 0)
        assert timing["earliest_start"] is None
        assert timing["latest_start"] is None


def test_publication_skips_ev_child_for_computed_no_bet_and_hides_top_coupon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        _write_stub_external_reports,
    )
    result = _runner_result("NO BET", top_coupon="DIAGNOSTIC-COUPON-MUST-NOT-LEAK")

    publication = publish_drawing_run_artifacts(
        result,
        report_dir=tmp_path,
        protected_paths=(),
        protected_roots=(),
        now=lambda: DEADLINE - timedelta(minutes=6),
    )

    assert isinstance(publication, DrawingRunPublication)
    assert publication.result.decision == "NO BET"
    assert publication.ev == ()
    assert publication.external
    assert publication.runner
    for path in publication.paths:
        assert "DIAGNOSTIC-COUPON-MUST-NOT-LEAK" not in path.read_text(
            encoding="utf-8"
        )
    payload = json.loads(publication.runner[0].read_text(encoding="utf-8"))
    assert payload["report_links"]["ev"] == []


def test_publication_sanitizes_injected_play_before_any_actionable_writer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        _write_stub_external_reports,
    )
    result = _runner_result("PLAY", coupon="ACTIONABLE-COUPON-MUST-NOT-LEAK")
    publication = publish_drawing_run_artifacts(
        result,
        report_dir=tmp_path,
        protected_paths=(),
        protected_roots=(),
        now=lambda: DEADLINE - timedelta(minutes=6),
    )

    assert publication.result.decision == "NO BET"
    assert publication.result.ev_run is not None
    assert publication.result.ev_run.package.decision == "NO BET"
    assert publication.result.ev_run.package.paper_coupons
    assert "release gate is closed" in publication.result.terminal_reason
    assert publication.ev == ()
    payload = json.loads(publication.runner[0].read_text(encoding="utf-8"))
    assert payload["ev"]["package"]["coupons"] == []
    assert payload["ev"]["package"]["artifact_class"] == "TRAINING/PAPER"
    assert not tuple(tmp_path.glob("ev_package_*"))


def test_publication_rolls_back_installed_children_on_runner_base_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _runner_result("PLAY")
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        _write_stub_external_reports,
    )

    def interrupt_runner(*_args, **_kwargs):
        raise KeyboardInterrupt("post-install interruption")

    monkeypatch.setattr(
        runner_reports,
        "write_drawing_run_reports",
        interrupt_runner,
    )

    with pytest.raises(KeyboardInterrupt, match="post-install interruption"):
        publish_drawing_run_artifacts(
            result,
            report_dir=tmp_path,
            protected_paths=(),
            protected_roots=(),
            now=lambda: DEADLINE - timedelta(minutes=6),
        )

    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == ()


def test_publication_never_calls_ev_writer_for_injected_play(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _runner_result("PLAY")
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        _write_stub_external_reports,
    )
    monkeypatch.setattr(
        runner_reports,
        "write_ev_package_reports",
        lambda *_args, **_kwargs: pytest.fail("actionable EV writer must not run"),
    )

    publication = publish_drawing_run_artifacts(
        result,
        report_dir=tmp_path,
        protected_paths=(),
        protected_roots=(),
        now=lambda: DEADLINE - timedelta(minutes=6),
    )

    assert publication.result.decision == "NO BET"
    assert publication.ev == ()


def test_publication_rechecks_symlink_swap_before_replacing_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _runner_result("NO BET")
    report_dir = tmp_path / "reports"
    cache_root = tmp_path / "cache"
    report_dir.mkdir()
    cache_root.mkdir()
    sentinel = cache_root / "protected.txt"
    sentinel.write_bytes(b"protected-cache-input")
    candidates = drawing_run_candidate_paths(
        result.config,
        result.target,
        result.preflight_at,
        report_dir,
    )
    runner_reports.validate_output_paths(
        candidates,
        protected_paths=(),
        protected_roots=(cache_root,),
    )
    report_dir.rmdir()
    report_dir.symlink_to(cache_root, target_is_directory=True)
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        lambda *_args, **_kwargs: pytest.fail("writers must not start"),
    )

    with pytest.raises(ValueError, match="protected roots"):
        publish_drawing_run_artifacts(
            result,
            report_dir=report_dir,
            protected_paths=(),
            protected_roots=(cache_root,),
            now=lambda: DEADLINE - timedelta(minutes=6),
        )

    assert sentinel.read_bytes() == b"protected-cache-input"
    assert report_dir.is_symlink()


def test_publication_treats_interrupt_after_transaction_commit_as_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _runner_result("NO BET")
    monkeypatch.setattr(
        runner_reports,
        "write_external_coverage_reports",
        _write_stub_external_reports,
    )
    real_exit = runner_reports.ArtifactPublicationTransaction.__exit__

    def interrupt_after_commit(self, *args):
        outcome = real_exit(self, *args)
        if self.committed:
            raise KeyboardInterrupt("interrupt after publication commit")
        return outcome

    monkeypatch.setattr(
        runner_reports.ArtifactPublicationTransaction,
        "__exit__",
        interrupt_after_commit,
    )

    publication = publish_drawing_run_artifacts(
        result,
        report_dir=tmp_path,
        protected_paths=(),
        protected_roots=(),
        now=lambda: DEADLINE - timedelta(minutes=6),
    )

    assert publication.result.decision == "NO BET"
    assert publication.paths
    assert all(path.exists() for path in publication.paths)


def _write_stub_external_reports(
    audit: CoverageAudit,
    report_dir: str | Path,
    *,
    input_paths=(),
) -> tuple[Path, Path]:
    del input_paths
    paths = runner_reports.external_coverage_report_paths(audit, report_dir)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("external audit\n", encoding="utf-8")
    return paths


def _interrupt_second_install(monkeypatch) -> None:
    real_replace = os.replace
    installs = 0

    def interrupt(source, destination):
        nonlocal installs
        source_path = Path(source)
        destination_path = Path(destination)
        is_install = (
            source_path.name.endswith(".tmp")
            and not source_path.name.endswith(".bak.tmp")
            and destination_path.suffix in {".json", ".md"}
        )
        if is_install:
            installs += 1
            if installs == 2:
                raise KeyboardInterrupt
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupt)


def test_run_id_is_canonical_and_paths_are_deterministic(tmp_path):
    result = _runner_result("PLAY")
    identity = {
        "config": {
            "bank": 4980,
            "final_lead_minutes": 20,
            "mode": "playable",
            "provider": "api-sports",
            "safety_stop_minutes": 5,
            "stake": 30,
        },
        "preflight_at": PREFLIGHT_AT.isoformat(),
        "target": {
            "deadline": DEADLINE.isoformat(),
            "drawing_id": 11953,
            "drawing_number": 4945,
            "fingerprint": result.target.fingerprint,
        },
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    expected_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    assert drawing_run_id(result) == expected_id
    assert drawing_run_report_paths(result, tmp_path) == (
        tmp_path / f"drawing_run_4945_20260716T150000Z_{expected_id}.json",
        tmp_path / f"drawing_run_4945_20260716T150000Z_{expected_id}.md",
    )
    assert drawing_run_report_paths(result, tmp_path) == drawing_run_report_paths(
        result, tmp_path
    )


def test_distinct_invocation_inputs_have_distinct_run_ids():
    result = _runner_result("PLAY")
    earlier_preflight = replace(
        result,
        preflight_at=result.preflight_at - timedelta(seconds=1),
    )
    different_config = replace(
        result,
        config=replace(result.config, final_lead_minutes=25),
    )

    assert drawing_run_id(result) != drawing_run_id(earlier_preflight)
    assert drawing_run_id(result) != drawing_run_id(different_config)


def test_json_is_canonical_and_repeated_report_bytes_are_identical(tmp_path):
    result = _runner_result("PLAY")
    first_paths = write_drawing_run_reports(result, report_dir=tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first_paths)
    second_paths = write_drawing_run_reports(result, report_dir=tmp_path)

    assert second_paths == first_paths
    assert tuple(path.read_bytes() for path in second_paths) == first_bytes
    json_text = first_paths[0].read_text()
    assert json_text == json.dumps(
        json.loads(json_text),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_model_and_direct_writer_suppress_manually_injected_play(tmp_path):
    result = _runner_result("PLAY", coupon="INJECTED-WAGER-COUPON")

    assert result.decision == "NO BET"
    assert result.ev_run is not None
    assert result.ev_run.package.decision == "NO BET"
    assert result.ev_run.package.coupons == ()
    assert result.ev_run.package.paper_coupons[0].coupon == "INJECTED-WAGER-COUPON"

    json_path, markdown_path = write_drawing_run_reports(
        result,
        report_dir=tmp_path,
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["decision"] == "NO BET"
    assert payload["ev"]["package"]["coupons"] == []
    assert payload["ev"]["package"]["artifact_class"] == "TRAINING/PAPER"
    assert "INJECTED-WAGER-COUPON" not in markdown_path.read_text(encoding="utf-8")


def test_manifest_and_markdown_contain_complete_operator_facts(tmp_path):
    result = _runner_result("PLAY", coupon="SELECTED-COUPON")
    links = RunnerReportLinks(
        external=(Path("reports/external.csv"), Path("reports/external.md")),
    )

    json_path, markdown_path = write_drawing_run_reports(
        result,
        links=links,
        report_dir=tmp_path,
    )
    payload = json.loads(json_path.read_text())
    markdown = markdown_path.read_text()

    assert payload["schema_version"] == 4
    assert payload["run_id"] == drawing_run_id(result)
    assert payload["decision"] == "NO BET"
    assert payload["command_status"] == "success"
    assert payload["config"]["provider"] == "api-sports"
    assert payload["target"] == {
        "deadline": DEADLINE.isoformat(),
        "drawing_id": 11953,
        "drawing_number": 4945,
        "final_fingerprint": result.target.fingerprint,
        "preflight_fingerprint": result.target.fingerprint,
    }
    assert payload["collection"]["collection_ids"] == ["collection-final"]
    assert payload["collection"]["pass_count"] == 1
    assert payload["collection"]["total_requests"] == 4
    assert payload["eligibility"]["status"] == "playable"
    assert payload["eligibility"]["raw"] == payload["eligibility"]["effective"]
    assert payload["eligibility"]["raw"]["span_days"] == 2
    assert payload["eligibility"]["raw"]["operator_override_count"] == 0
    assert payload["eligibility"]["override"] is None
    assert payload["coverage"]["gate_decision"] == "PENDING"
    assert payload["ev"]["requested_bank"] == 4980
    assert payload["ev"]["effective_budget"] == 90
    assert payload["ev"]["selected_cost"] == 0
    assert payload["ev"]["unused_requested_bank"] == 4980
    assert payload["ev"]["package"]["coupons"] == []
    assert payload["ev"]["package"]["paper_coupons"] == [
        {
            "coupon": "SELECTED-COUPON",
            "gross_ev": 1.1,
            "net_ev": 0.1,
            "rank": 1,
        }
    ]
    assert payload["report_links"] == {
        "ev": [],
        "external": ["reports/external.csv", "reports/external.md"],
    }
    for heading in (
        "# Drawing Run 4945",
        "## Decision",
        "## Target",
        "## Configuration",
        "## Timeline",
        "## Collection",
        "## Timing Eligibility",
        "## Coverage Audit",
        "## EV Package",
        "## Associated Reports",
    ):
        assert heading in markdown
    assert "SELECTED-COUPON" not in markdown
    assert "api-sports" in markdown
    assert "PENDING" in markdown
    assert "schema version: 4" in markdown
    assert "no timing override catalog supplied" in markdown


def test_schema_v4_has_stable_timing_and_budget_shapes_with_or_without_override(
    tmp_path,
):
    non_override_json, _ = write_drawing_run_reports(
        _runner_result("PLAY", coupon="SELECTED-COUPON"),
        report_dir=tmp_path / "non-override",
    )
    computed_json, _ = write_drawing_run_reports(
        _runner_result_with_override("PLAY"),
        report_dir=tmp_path / "computed",
    )
    suppressed_result = replace(
        _runner_result_with_override("PLAY"),
        decision="NO BET",
        terminal_reason="timing override package was suppressed for test",
        ev_finished_at=None,
        finished_at=FINAL_STARTED_AT + timedelta(seconds=3),
        ev_run=None,
    )
    suppressed_json, _ = write_drawing_run_reports(
        suppressed_result,
        report_dir=tmp_path / "suppressed",
    )

    non_override = json.loads(non_override_json.read_text())
    computed = json.loads(computed_json.read_text())
    suppressed = json.loads(suppressed_json.read_text())

    assert non_override["schema_version"] == 4
    assert non_override["eligibility"]["raw"] == (
        non_override["eligibility"]["effective"]
    )
    assert non_override["eligibility"]["override"] is None
    assert non_override["ev"]["requested_bank"] == 4980
    assert non_override["ev"]["effective_budget"] == 90
    assert non_override["ev"]["selected_cost"] == 0
    assert non_override["ev"]["unused_requested_bank"] == 4980
    assert non_override["ev"]["package"]["paper_selected_count"] == 1
    assert computed["schema_version"] == 4
    assert computed["ev"]["computed"] is True
    assert computed["ev"]["input_fetched_at"] == (
        FINAL_STARTED_AT + timedelta(seconds=4)
    ).isoformat()
    assert computed["eligibility"]["raw"] == computed["eligibility"]["effective"]
    assert computed["eligibility"]["override"]["status"] == "applied"
    assert computed["eligibility"]["override"]["override_id"] == (
        "drawing-4945-reviewed-timing-v1"
    )
    assert computed["ev"]["requested_bank"] == 4980
    assert computed["ev"]["effective_budget"] == 90
    assert computed["ev"]["selected_cost"] == 0
    assert computed["ev"]["unused_requested_bank"] == 4980
    assert computed["ev"]["package"]["decision"] == "NO BET"
    assert computed["ev"]["package"]["coupons"] == []
    assert computed["ev"]["package"]["paper_selected_count"] == 1
    assert computed["ev"]["package"]["paper_cost"] == 30

    assert suppressed["schema_version"] == 4
    assert suppressed["eligibility"]["raw"] == suppressed["eligibility"]["effective"]
    assert suppressed["eligibility"]["override"]["status"] == "applied"
    assert suppressed["ev"] == {
        "computed": False,
        "input_fetched_at": None,
        "minimum_gross_ev": None,
        "prize_fund_factor": None,
        "possible_winnings_source": None,
        "jackpot_source": None,
        "self_dilution_ratio": None,
        "model_supported": None,
        "model_warning": None,
        "package_safety": None,
        "selection_diagnostics": None,
        "requested_bank": 4980,
        "effective_budget": None,
        "selected_cost": None,
        "unused_requested_bank": None,
        "package": {
            "decision": "NO BET",
            "decision_reason": "timing override package was suppressed for test",
            "coupons": [],
            "selected_count": None,
            "cost": None,
            "unused_bank": None,
            "expected_payout": None,
            "modeled_roi": None,
            "derived_brief": [],
            "structural_status": "NOT_EVALUATED",
            "artifact_class": "NONE",
            "paper_coupons": [],
            "paper_selected_count": 0,
            "paper_cost": 0,
            "paper_expected_payout": 0.0,
            "paper_modeled_roi": None,
            "paper_derived_brief": [],
        },
        "sensitivity": [],
    }


def test_schema_v4_computed_no_bet_preserves_known_budget_and_reason(tmp_path):
    result = _runner_result("NO BET")

    json_path, _ = write_drawing_run_reports(result, report_dir=tmp_path)
    ev = json.loads(json_path.read_text())["ev"]

    assert ev["computed"] is True
    assert ev["requested_bank"] == 4980
    assert ev["effective_budget"] == 90
    assert ev["selected_cost"] == 0
    assert ev["unused_requested_bank"] == 4980
    assert ev["package"]["decision"] == "NO BET"
    assert ev["package"]["decision_reason"] == result.terminal_reason
    assert ev["package"]["selected_count"] == 0
    assert ev["package"]["cost"] == 0


def test_schema_v4_non_override_not_computed_uses_explicit_null_provenance(
    tmp_path,
):
    result = _terminal_result(final_target=None)

    json_path, markdown_path = write_drawing_run_reports(
        result,
        report_dir=tmp_path,
    )
    payload = json.loads(json_path.read_text())
    ev = payload["ev"]
    markdown = markdown_path.read_text()

    assert payload["schema_version"] == 4
    assert payload["eligibility"]["raw"] == payload["eligibility"]["effective"]
    assert payload["eligibility"]["override"] is None
    assert ev["computed"] is False
    assert ev["requested_bank"] == 4980
    assert ev["effective_budget"] is None
    assert ev["selected_cost"] is None
    assert ev["unused_requested_bank"] is None
    assert ev["package"]["decision"] == "NO BET"
    assert ev["package"]["decision_reason"] == result.terminal_reason
    assert ev["package"]["selected_count"] is None
    assert ev["package"]["cost"] is None
    assert ev["package"]["unused_bank"] is None
    assert f"decision reason: {result.terminal_reason}" in markdown
    assert "effective cap: n/a" in markdown
    assert "selected cost: n/a" in markdown
    assert "unused requested bank: n/a" in markdown


def test_schema_v4_preserves_drawing_4950_exact_effective_cap_810(tmp_path):
    result = _runner_result(
        "PLAY",
        coupon="DRAWING-4950-SELECTED",
        target=_target(drawing_id=11964, drawing_number=4950),
        effective_budget=810,
    )

    json_path, _ = write_drawing_run_reports(result, report_dir=tmp_path)
    payload = json.loads(json_path.read_text())

    assert payload["schema_version"] == 4
    assert payload["target"]["drawing_number"] == 4950
    assert payload["ev"]["requested_bank"] == 4980
    assert payload["ev"]["effective_budget"] == 810
    assert payload["ev"]["selected_cost"] == 0
    assert payload["ev"]["unused_requested_bank"] == 4980
    assert payload["ev"]["package"]["selected_count"] == 0
    assert payload["ev"]["package"]["paper_selected_count"] == 1


@pytest.mark.parametrize("effective_budget", [None, 0])
def test_schema_v4_sanitizes_play_without_positive_explicit_effective_budget(
    tmp_path,
    effective_budget,
):
    result = _runner_result("PLAY", effective_budget=effective_budget)

    json_path, _ = write_drawing_run_reports(result, report_dir=tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["decision"] == "NO BET"
    assert payload["ev"]["package"]["coupons"] == []
    assert payload["ev"]["package"]["paper_selected_count"] == 1


def test_schema_v4_rejects_selected_cost_count_mismatch(tmp_path):
    result = _runner_result("RESEARCH ONLY")
    assert result.ev_run is not None
    bad_package = replace(
        result.ev_run.package,
        cost=60,
        unused_bank=4920,
    )
    bad_result = replace(
        result,
        ev_run=replace(result.ev_run, package=bad_package),
    )

    with pytest.raises(ValueError, match="selected coupon count"):
        write_drawing_run_reports(bad_result, report_dir=tmp_path)


def test_mismatch_report_serializes_observed_final_fingerprint(tmp_path):
    changed_target = replace(
        _target(),
        events=tuple(
            replace(event, home_team=f"Changed {event.event_order}")
            for event in _target().events
        ),
    )
    result = _terminal_result(final_target=changed_target)

    json_path, markdown_path = write_drawing_run_reports(
        result,
        report_dir=tmp_path,
    )
    payload = json.loads(json_path.read_text())

    assert result.final_fingerprint != result.target.fingerprint
    assert payload["target"]["final_fingerprint"] == result.final_fingerprint
    assert result.final_fingerprint in markdown_path.read_text()


def test_early_cutoff_report_serializes_null_final_fingerprint(tmp_path):
    result = _terminal_result(final_target=None)

    json_path, markdown_path = write_drawing_run_reports(
        result,
        report_dir=tmp_path,
    )
    json_text = json_path.read_text()

    assert json.loads(json_text)["target"]["final_fingerprint"] is None
    assert '"final_fingerprint":null' in json_text
    assert "- final fingerprint: null" in markdown_path.read_text()


@pytest.mark.parametrize("decision", ["PLAY", "RESEARCH ONLY"])
def test_actionable_reports_serialize_only_selected_package_coupons(
    decision,
    tmp_path,
):
    result = _runner_result(
        decision,
        coupon="SELECTED-COUPON",
        top_coupon="DIAGNOSTIC-COUPON",
    )

    paths = write_drawing_run_reports(result, report_dir=tmp_path)
    combined = "".join(path.read_text() for path in paths)

    assert "SELECTED-COUPON" in combined
    assert "DIAGNOSTIC-COUPON" not in combined


def test_no_bet_report_never_contains_discarded_coupon(tmp_path):
    result = _runner_result("NO BET")
    json_path, markdown_path = write_drawing_run_reports(result, report_dir=tmp_path)
    combined = json_path.read_text() + markdown_path.read_text()
    assert "UNIQUE-COUPON" not in combined
    assert '"decision":"NO BET"' in json_path.read_text()
    assert json.loads(json_path.read_text())["ev"]["package"]["coupons"] == []


def test_secret_environment_and_internal_diagnostics_are_not_serialized(
    monkeypatch,
    tmp_path,
):
    secret = "API-SPORTS-SECRET-123"
    monkeypatch.setenv("API_SPORTS_KEY", secret)
    result = _runner_result(
        "PLAY",
        coupon="SELECTED-COUPON",
        top_coupon=secret,
    )

    paths = write_drawing_run_reports(result, report_dir=tmp_path)

    assert secret not in b"".join(path.read_bytes() for path in paths).decode()


@pytest.mark.parametrize("output_index", [0, 1])
def test_report_output_cannot_collide_with_an_input_path(tmp_path, output_index):
    result = _runner_result("PLAY")
    output_paths = drawing_run_report_paths(result, tmp_path)

    with pytest.raises(ValueError, match="runner report and input paths"):
        write_drawing_run_reports(
            result,
            report_dir=tmp_path,
            input_paths=(output_paths[output_index],),
        )

    assert not any(path.exists() for path in output_paths)


def test_report_output_rejects_lexical_input_alias_before_writes(tmp_path):
    result = _runner_result("PLAY")
    output_paths = drawing_run_report_paths(result, tmp_path)
    lexical_alias = tmp_path / "not-created" / ".." / output_paths[0].name

    with pytest.raises(ValueError, match="runner report and input paths"):
        write_drawing_run_reports(
            result,
            report_dir=tmp_path,
            input_paths=(lexical_alias,),
        )

    assert not any(path.exists() for path in output_paths)
    assert not (tmp_path / "not-created").exists()


def test_report_output_rejects_symlink_input_alias_before_writes(tmp_path):
    result = _runner_result("PLAY")
    real_dir = tmp_path / "real"
    alias_dir = tmp_path / "alias"
    real_dir.mkdir()
    alias_dir.symlink_to(real_dir, target_is_directory=True)
    output_paths = drawing_run_report_paths(result, alias_dir)
    real_input = real_dir / output_paths[0].name

    with pytest.raises(ValueError, match="runner report and input paths"):
        write_drawing_run_reports(
            result,
            report_dir=alias_dir,
            input_paths=(real_input,),
        )

    assert not any(path.exists() for path in output_paths)
    assert tuple(real_dir.iterdir()) == ()


def test_runner_report_pair_is_restored_on_interruption(monkeypatch, tmp_path):
    original = write_drawing_run_reports(
        _runner_result("PLAY", coupon="ORIGINAL-COUPON"), report_dir=tmp_path
    )
    original_bytes = tuple(path.read_bytes() for path in original)
    _interrupt_second_install(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        write_drawing_run_reports(
            _runner_result("PLAY", coupon="CHANGED-COUPON"), report_dir=tmp_path
        )
    assert tuple(path.read_bytes() for path in original) == original_bytes
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_new_runner_report_pair_is_removed_on_interruption(monkeypatch, tmp_path):
    result = _runner_result("PLAY")
    expected_paths = drawing_run_report_paths(result, tmp_path)
    _interrupt_second_install(monkeypatch)

    with pytest.raises(KeyboardInterrupt):
        write_drawing_run_reports(result, report_dir=tmp_path)

    assert not any(path.exists() for path in expected_paths)
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_runner_report_pair_survives_temp_write_interruption(monkeypatch, tmp_path):
    original = write_drawing_run_reports(
        _runner_result("PLAY", coupon="ORIGINAL-COUPON"), report_dir=tmp_path
    )
    original_bytes = tuple(path.read_bytes() for path in original)
    real_write = runner_reports._write_exclusive
    interrupted = False

    def interrupt(path, content):
        nonlocal interrupted
        if not interrupted and path.name.endswith(".tmp"):
            interrupted = True
            with path.open("xb") as output:
                output.write(content[:1])
            raise KeyboardInterrupt
        return real_write(path, content)

    monkeypatch.setattr(runner_reports, "_write_exclusive", interrupt)

    with pytest.raises(KeyboardInterrupt):
        write_drawing_run_reports(
            _runner_result("PLAY", coupon="CHANGED-COUPON"),
            report_dir=tmp_path,
        )

    assert tuple(path.read_bytes() for path in original) == original_bytes
    assert not tuple(tmp_path.glob(".*.tmp"))


def test_runner_report_pair_survives_partial_backup_interruption(
    monkeypatch,
    tmp_path,
):
    original = write_drawing_run_reports(
        _runner_result("PLAY", coupon="ORIGINAL-COUPON"), report_dir=tmp_path
    )
    original_bytes = tuple(path.read_bytes() for path in original)
    real_copy = runner_reports._copy_exclusive
    interrupted = False

    def interrupt(source, destination):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            with source.open("rb") as input_file, destination.open("xb") as output:
                output.write(input_file.read(1))
            raise KeyboardInterrupt
        return real_copy(source, destination)

    monkeypatch.setattr(runner_reports, "_copy_exclusive", interrupt)

    with pytest.raises(KeyboardInterrupt):
        write_drawing_run_reports(
            _runner_result("PLAY", coupon="CHANGED-COUPON"),
            report_dir=tmp_path,
        )

    assert tuple(path.read_bytes() for path in original) == original_bytes
    assert not tuple(tmp_path.glob(".*.tmp"))
