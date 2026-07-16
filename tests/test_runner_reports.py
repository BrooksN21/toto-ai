import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

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
from toto_ai.runner import DrawingRunnerConfig, DrawingRunnerResult, pin_drawing
from toto_ai.runner.reports import (
    RunnerReportLinks,
    drawing_run_id,
    drawing_run_report_paths,
    write_drawing_run_reports,
)

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 16, 15, tzinfo=UTC)
PREFLIGHT_AT = DEADLINE - timedelta(minutes=20)
FINAL_STARTED_AT = DEADLINE - timedelta(minutes=19)


def _target() -> TargetDrawing:
    events = tuple(
        TargetEvent(
            drawing_id=11953,
            drawing_number=4945,
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
        drawing_id=11953,
        drawing_number=4945,
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
) -> DrawingRunnerResult:
    target = _target()
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
        config=EVConfig(bank=4980, stake=30, mode=mode),
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


def test_manifest_and_markdown_contain_complete_operator_facts(tmp_path):
    result = _runner_result("PLAY", coupon="SELECTED-COUPON")
    links = RunnerReportLinks(
        external=(Path("reports/external.csv"), Path("reports/external.md")),
        ev=(Path("reports/ev.csv"), Path("reports/ev.md")),
    )

    json_path, markdown_path = write_drawing_run_reports(
        result,
        links=links,
        report_dir=tmp_path,
    )
    payload = json.loads(json_path.read_text())
    markdown = markdown_path.read_text()

    assert payload["schema_version"] == 1
    assert payload["run_id"] == drawing_run_id(result)
    assert payload["decision"] == "PLAY"
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
    assert payload["eligibility"]["span_days"] == 2
    assert payload["coverage"]["gate_decision"] == "PENDING"
    assert payload["ev"]["package"]["coupons"] == [
        {
            "coupon": "SELECTED-COUPON",
            "gross_ev": 1.1,
            "net_ev": 0.1,
            "rank": 1,
        }
    ]
    assert payload["report_links"] == {
        "ev": ["reports/ev.csv", "reports/ev.md"],
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
    assert "SELECTED-COUPON" in markdown
    assert "api-sports" in markdown
    assert "PENDING" in markdown


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
