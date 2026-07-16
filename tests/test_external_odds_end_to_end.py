from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

import toto_ai.cli as cli_module
import toto_ai.ev.drawing as drawing_module
import toto_ai.external_odds.collection as collection_module
from toto_ai.cli import app
from toto_ai.db.models import Base
from toto_ai.ev.drawing import build_open_ev_package, ev_input_from_payload
from toto_ai.ev.models import EVComponents, EVConfig, EVSurface
from toto_ai.external_odds.api_sports import APISportsClient, APISportsError
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.collection import collect_open_external_odds
from toto_ai.external_odds.domain import ProviderEvent, ProviderMarket, QuotaState
from toto_ai.external_odds.prospective import collect_fresh_open_external_odds
from toto_ai.external_odds.reports import write_external_coverage_reports
from toto_ai.external_odds.storage import load_latest_complete_collections

FETCHED_AT = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
SECRET = "task7-secret-api-key"


@dataclass(frozen=True)
class TimingAcceptanceScenario:
    name: str
    drawing_id: int
    expected_status: str
    expected_span_days: int
    expected_horizon_days: int
    expected_expanded: bool
    missing_target_order: int | None = None
    provider_day_offset: int | None = None
    failed_schedule_date: date | None = None
    max_passes: int = 1


TIMING_ACCEPTANCE_SCENARIOS = (
    TimingAcceptanceScenario("ordinary", 9101, "playable", 2, 2, False),
    TimingAcceptanceScenario(
        "day_five",
        9102,
        "multi_day",
        5,
        5,
        True,
        missing_target_order=14,
        provider_day_offset=4,
    ),
    TimingAcceptanceScenario(
        "partial_date",
        9103,
        "unknown",
        1,
        2,
        False,
        missing_target_order=14,
        failed_schedule_date=date(2026, 7, 15),
    ),
    TimingAcceptanceScenario("multi_day", 9104, "multi_day", 3, 2, False),
    TimingAcceptanceScenario(
        "unresolved",
        9105,
        "unknown",
        1,
        5,
        True,
        missing_target_order=14,
    ),
)


def test_multiday_timing_boundary_acceptance(monkeypatch, tmp_path):
    factory, db_path = sqlite_factory(tmp_path)
    payloads = {
        scenario.name: timing_acceptance_payload(scenario)
        for scenario in TIMING_ACCEPTANCE_SCENARIOS
    }
    results = {}

    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("acceptance must not use the network")
        ),
    )

    for scenario in TIMING_ACCEPTANCE_SCENARIOS:
        payload = payloads[scenario.name]
        first = run_timing_acceptance_scenario(
            monkeypatch,
            tmp_path,
            factory,
            scenario,
            payload,
        )
        repeated = run_timing_acceptance_scenario(
            monkeypatch,
            tmp_path,
            factory,
            scenario,
            payload,
        )
        results[scenario.name] = first

        assert repeated.snapshot == first.snapshot
        assert tuple(item.snapshot for item in repeated.passes) == tuple(
            item.snapshot for item in first.passes
        )
        assert first.final_horizon_days == scenario.expected_horizon_days
        assert first.expanded is scenario.expected_expanded
        assert first.snapshot.eligibility.status == scenario.expected_status
        assert first.snapshot.eligibility.span_days == scenario.expected_span_days
        for item in first.passes:
            assert len(item.snapshot.events) == 15
            assert tuple(row.event_order for row in item.snapshot.events) == tuple(
                range(15)
            )

    stored_by_id = {
        collection.collection_id: collection
        for collection in load_latest_complete_collections(factory, last=20)
    }
    assert len(stored_by_id) == 7
    for result in results.values():
        for item in result.passes:
            reloaded = stored_by_id[item.snapshot.collection_id]
            expected_reload = storage_projected_snapshot(item.snapshot)
            assert reloaded == expected_reload
            assert asdict(reloaded) == asdict(expected_reload)
            with pytest.raises(FrozenInstanceError):
                reloaded.events = ()
            with pytest.raises(FrozenInstanceError):
                reloaded.events[0].fallback_reason = "mutated"

    ordinary = results["ordinary"]
    assert ordinary.base_pass_count == 1
    assert ordinary.expansion_pass_count == 0
    assert ordinary.snapshot.eligibility.totobrief_count == 15
    assert ordinary.snapshot.eligibility.provider_count == 0

    day_five = results["day_five"]
    assert day_five.base_pass_count == 1
    assert day_five.expansion_pass_count == 1
    assert day_five.base_passes[0].snapshot.events[14].fallback_reason == (
        "0 exact candidates"
    )
    assert day_five.snapshot.events[14].match_status == "matched"
    assert day_five.snapshot.events[14].effective_start_source == "provider"
    assert day_five.snapshot.eligibility.provider_count == 1
    assert day_five.snapshot.eligibility.totobrief_count == 14
    assert day_five.snapshot.eligibility.missing_event_orders == ()
    assert any(
        item.requested_date == date(2026, 7, 18)
        for item in day_five.snapshot.successful_schedule_dates
    )

    partial = results["partial_date"].snapshot
    assert partial.eligibility.missing_event_orders == (14,)
    assert partial.events[14].fallback_reason == "partial schedule"
    assert partial.successful_schedule_dates
    failed_schedule_dates = [
        (item.requested_date, item.error)
        for item in partial.failed_schedule_dates
    ]
    assert failed_schedule_dates == [
        (date(2026, 7, 15), "provider schedule failure")
    ]
    successful_date_keys = {
        (item.sport, item.requested_date)
        for item in partial.successful_schedule_dates
    }
    failed_date_keys = {
        (item.sport, item.requested_date)
        for item in partial.failed_schedule_dates
    }
    assert successful_date_keys.isdisjoint(failed_date_keys)

    unresolved = results["unresolved"].snapshot
    assert unresolved.eligibility.missing_event_orders == (14,)
    assert unresolved.events[14].effective_start_source == "unresolved"
    assert unresolved.events[14].fallback_reason == "0 exact candidates"

    audit = audit_external_coverage(factory, last=5, minimum_bookmakers=3)
    assert audit.drawings == 5
    assert len(audit.dispositions) == 75
    assert audit.eligibility_counts == {
        "playable": 1,
        "multi_day": 2,
        "unknown": 2,
    }
    for drawing_id in (scenario.drawing_id for scenario in TIMING_ACCEPTANCE_SCENARIOS):
        rows = tuple(row for row in audit.dispositions if row.drawing_id == drawing_id)
        assert len(rows) == 15
        assert tuple(row.event_order for row in rows) == tuple(range(15))

    first_report_paths = write_external_coverage_reports(
        audit,
        report_dir=tmp_path / "timing-reports",
    )
    first_report_bytes = tuple(path.read_bytes() for path in first_report_paths)
    repeated_report_paths = write_external_coverage_reports(
        audit,
        report_dir=tmp_path / "timing-reports",
    )
    assert tuple(path.read_bytes() for path in repeated_report_paths) == (
        first_report_bytes
    )
    with first_report_paths[0].open(newline="") as source:
        timing_report_rows = [
            row
            for row in csv.DictReader(source)
            if row["row_type"] == "disposition"
        ]
    expected_scopes = {
        "ordinary": "ordinary_two_day",
        "day_five": "multi_day",
        "partial_date": "unknown",
        "multi_day": "multi_day",
        "unresolved": "unknown",
    }
    for scenario in TIMING_ACCEPTANCE_SCENARIOS:
        rows = [
            row
            for row in timing_report_rows
            if int(row["drawing_id"]) == scenario.drawing_id
        ]
        assert len(rows) == 15
        assert [int(row["event_order"]) for row in rows] == list(range(15))
        assert {row["collection_scope"] for row in rows} == {
            expected_scopes[scenario.name]
        }
        assert {row["eligibility_status"] for row in rows} == {
            scenario.expected_status
        }
        assert {row["eligibility_span_days"] for row in rows} == {
            str(scenario.expected_span_days)
        }
        assert {row["missing_start_horizon_days"] for row in rows} == {
            str(scenario.expected_horizon_days)
        }
        assert {row["target_fingerprint"] for row in rows} == {
            results[scenario.name].snapshot.target_fingerprint
        }
        expected_missing_orders = (
            [scenario.missing_target_order]
            if scenario.expected_status == "unknown"
            else []
        )
        assert {
            row["eligibility_missing_event_orders"] for row in rows
        } == {json.dumps(expected_missing_orders, separators=(",", ":"))}

    report_by_scenario = {
        scenario.name: [
            row
            for row in timing_report_rows
            if int(row["drawing_id"]) == scenario.drawing_id
        ]
        for scenario in TIMING_ACCEPTANCE_SCENARIOS
    }
    assert report_by_scenario["day_five"][14]["effective_start_source"] == (
        "provider"
    )
    assert report_by_scenario["partial_date"][14]["effective_start_source"] == (
        "unresolved"
    )
    assert report_by_scenario["unresolved"][14]["effective_start_source"] == (
        "unresolved"
    )
    assert json.loads(
        report_by_scenario["partial_date"][0]["failed_schedule_dates"]
    ) == ["football:2026-07-15"]
    assert json.loads(
        report_by_scenario["partial_date"][0]["failed_schedule_reasons"]
    ) == ["provider schedule failure"]
    assert "football:2026-07-18" in json.loads(
        report_by_scenario["day_five"][0]["successful_schedule_dates"]
    )
    timing_markdown = first_report_paths[1].read_text(encoding="utf-8")
    assert "- playable: 1" in timing_markdown
    assert "- multi_day: 2" in timing_markdown
    assert "- unknown: 2" in timing_markdown

    install_fast_acceptance_ev(monkeypatch)
    timing_resolver = cli_module._build_timing_eligibility_resolver(str(db_path))
    for scenario in TIMING_ACCEPTANCE_SCENARIOS:
        playable = build_timing_acceptance_ev(
            payloads[scenario.name],
            mode="playable",
            timing_resolver=timing_resolver,
        )
        research = build_timing_acceptance_ev(
            payloads[scenario.name],
            mode="research",
            timing_resolver=timing_resolver,
        )

        assert playable.timing_eligibility.status == scenario.expected_status
        assert playable.timing_eligibility.fingerprint_match is True
        assert playable.timing_eligibility.target_fingerprint == (
            results[scenario.name].snapshot.target_fingerprint
        )
        assert playable.ev_input.probability_sources == ("totobrief_bk",) * 15
        assert research.ev_input.probability_sources == ("totobrief_bk",) * 15
        assert research.package.decision == "RESEARCH ONLY"
        assert research.package.coupons
        if scenario.expected_status == "playable":
            assert playable.package.decision == "PLAY"
            assert playable.package.cost == 30
        else:
            assert_zero_cost_no_bet(playable)

    mismatched_payload = deepcopy(payloads["ordinary"])
    mismatched_payload["data"]["events"][0]["name"] = (
        "Fingerprint Changed - Away 14"
    )
    mismatched = build_timing_acceptance_ev(
        mismatched_payload,
        mode="playable",
        timing_resolver=timing_resolver,
    )
    absent = build_timing_acceptance_ev(
        payloads["ordinary"],
        mode="playable",
        timing_resolver=cli_module._build_timing_eligibility_resolver(
            str(tmp_path / "absent.sqlite")
        ),
    )
    assert mismatched.timing_eligibility.status == "absent"
    assert "no complete stored eligibility" in mismatched.timing_eligibility.reason
    assert absent.timing_eligibility.status == "absent"
    assert "missing or unreadable" in absent.timing_eligibility.reason
    assert_zero_cost_no_bet(mismatched)
    assert_zero_cost_no_bet(absent)

    exported_provenance = json.dumps(
        [
            asdict(item.snapshot)
            for result in results.values()
            for item in result.passes
        ],
        default=str,
        sort_keys=True,
    )
    collected_errors = json.dumps(
        [
            item.error
            for result in results.values()
            for item in result.snapshot.failed_schedule_dates
        ]
        + [
            mismatched.timing_eligibility.reason,
            absent.timing_eligibility.reason,
        ]
    )
    assert SECRET not in "\n".join(sqlite_text_values(db_path))
    assert SECRET not in exported_provenance
    assert SECRET not in collected_errors
    assert SECRET not in b"".join(first_report_bytes).decode("utf-8")


def test_open_collection_records_all_events_and_never_changes_ev_input(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    payload = drawing_info_payload()
    original_ev = ev_input_from_payload(
        payload,
        fetched_at=FETCHED_AT.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    provider = MixedCoverageProvider(consensus_events=9)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(payload),
        provider=provider,
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    after_ev = ev_input_from_payload(
        payload,
        fetched_at=FETCHED_AT.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )

    assert len(result.events) == 15
    assert tuple(event.event_order for event in result.events) == tuple(range(15))
    assert (
        sum(row.probability_source == "external_consensus" for row in result.events)
        == 9
    )
    assert (
        sum(row.probability_source == "totobrief_bk_fallback" for row in result.events)
        == 6
    )
    assert all(row.fallback_reason for row in result.events[9:])
    assert after_ev.true_probabilities == original_ev.true_probabilities
    assert after_ev.probability_sources == ("totobrief_bk",) * 15


def test_provider_failure_still_records_fifteen_explicit_fallbacks(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=ProviderFailureProvider(),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)

    assert len(result.events) == 15
    assert all(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    assert all(
        row.fallback_reason.startswith("provider schedule failure")
        for row in result.events
    )
    assert audit.total.explicit_dispositions == 15
    assert audit.total.provider_error_count == 15
    assert audit.gate.decision == "PENDING"


def test_quota_failure_after_five_events_still_records_fifteen(
    monkeypatch,
    tmp_path,
):
    factory, _ = sqlite_factory(tmp_path)
    provider = QuotaAfterProvider(after=5)
    install_open_drawing(monkeypatch)

    result = collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=provider,
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )

    assert len(result.events) == 15
    assert (
        sum(row.probability_source == "external_consensus" for row in result.events)
        == 5
    )
    assert all(
        row.fallback_reason == "quota reserve reached" for row in result.events[5:]
    )
    assert provider.market_calls == tuple(f"football-{order}" for order in range(6))


def test_interrupted_collection_publishes_no_complete_run(monkeypatch, tmp_path):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)

    with pytest.raises(KeyboardInterrupt, match="operator interrupted"):
        collect_open_external_odds(
            totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
            provider=InterruptingProvider(),
            session_factory=factory,
            aliases={},
            fetched_at=FETCHED_AT,
        )

    assert load_latest_complete_collections(factory, last=1) == ()


def test_report_integrity_includes_required_evidence(monkeypatch, tmp_path):
    factory, _ = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)
    collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=MixedCoverageProvider(consensus_events=9),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)
    loaded = load_latest_complete_collections(factory, last=1)[0]

    first_paths = write_external_coverage_reports(audit, report_dir=tmp_path)
    first_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in first_paths
    )
    second_paths = write_external_coverage_reports(audit, report_dir=tmp_path)
    second_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest() for path in second_paths
    )

    assert second_hashes == first_hashes
    assert loaded.daily_limit == 100
    assert loaded.daily_remaining == 78
    assert loaded.requests_made == 16
    assert loaded.cache_hits == 0
    assert loaded.target_fetched_at == FETCHED_AT.isoformat()
    assert loaded.target_fingerprint
    assert loaded.missing_start_horizon_days == 2
    assert [
        (item.sport, item.requested_date.isoformat(), item.error)
        for item in loaded.requested_schedule_dates
    ] == [("football", "2026-07-14", None)]
    assert loaded.successful_schedule_dates == loaded.requested_schedule_dates
    assert loaded.failed_schedule_dates == ()
    assert loaded.eligibility.status == "playable"
    assert loaded.eligibility.span_days == 1
    assert loaded.eligibility.missing_event_orders == ()
    assert loaded.eligibility.totobrief_count == 15
    assert loaded.eligibility.provider_count == 0
    assert all(
        event.provider_event_fetched_at == FETCHED_AT.isoformat()
        for event in loaded.events
    )
    assert all(
        quote.fetched_at == FETCHED_AT.isoformat()
        and quote.updated_at == (FETCHED_AT - timedelta(hours=1)).isoformat()
        for event in loaded.events[:9]
        for quote in event.bookmaker_quotes
    )
    with first_paths[0].open(newline="") as source:
        reader = csv.DictReader(source)
        report_rows = list(reader)
    assert {
        "provider_schedule_fetched_at",
        "provider_schedule_payload_hash",
        "market_fetched_at",
        "market_updated_at",
        "market_payload_hashes",
        "requests_made",
        "cache_hits",
        "target_fetched_at",
        "daily_limit",
        "daily_remaining",
        "minute_remaining",
        "consensus_minimum_bookmakers",
        "consensus_maximum_age_hours",
        "gate_decision",
        "gate_predicate",
        "gate_operator",
        "gate_threshold",
        "gate_actual",
        "gate_passed",
        "collection_scope",
        "target_fingerprint",
        "missing_start_horizon_days",
        "requested_schedule_dates",
        "successful_schedule_dates",
        "failed_schedule_dates",
        "failed_schedule_reasons",
        "target_starts_at",
        "provider_starts_at",
        "effective_starts_at",
        "effective_start_source",
        "eligibility_status",
        "eligibility_earliest_start",
        "eligibility_latest_start",
        "eligibility_span_days",
        "eligibility_missing_event_orders",
        "eligibility_totobrief_count",
        "eligibility_provider_count",
        "provider_missing_count",
        "partial_schedule_count",
    } <= set(reader.fieldnames or ())
    disposition_rows = [row for row in report_rows if row["row_type"] == "disposition"]
    gate_rows = [row for row in report_rows if row["row_type"] == "gate_predicate"]
    assert len(disposition_rows) == 15
    assert [int(row["event_order"]) for row in disposition_rows] == list(range(15))
    assert [row["probability_source"] for row in disposition_rows[:10]] == [
        *("external_consensus" for _ in range(9)),
        "totobrief_bk_fallback",
    ]
    assert disposition_rows[9]["fallback_reason"] == "fewer than 3 eligible bookmakers"
    first_disposition = disposition_rows[0]
    assert first_disposition["collection_scope"] == "ordinary_two_day"
    assert first_disposition["target_fingerprint"] == loaded.target_fingerprint
    assert first_disposition["missing_start_horizon_days"] == "2"
    assert json.loads(first_disposition["requested_schedule_dates"]) == [
        "football:2026-07-14"
    ]
    assert json.loads(first_disposition["successful_schedule_dates"]) == [
        "football:2026-07-14"
    ]
    assert json.loads(first_disposition["failed_schedule_dates"]) == []
    assert json.loads(first_disposition["failed_schedule_reasons"]) == []
    assert first_disposition["target_starts_at"] == event_start(0).isoformat()
    assert first_disposition["provider_starts_at"] == event_start(0).isoformat()
    assert first_disposition["effective_starts_at"] == event_start(0).isoformat()
    assert first_disposition["effective_start_source"] == "totobrief"
    assert first_disposition["eligibility_status"] == "playable"
    assert first_disposition["eligibility_span_days"] == "1"
    assert first_disposition["eligibility_missing_event_orders"] == "[]"
    assert first_disposition["eligibility_totobrief_count"] == "15"
    assert first_disposition["eligibility_provider_count"] == "0"
    assert first_disposition["provider_schedule_fetched_at"] == FETCHED_AT.isoformat()
    assert first_disposition["provider_schedule_payload_hash"] == "schedule-hash-0"
    assert (
        json.loads(first_disposition["market_fetched_at"])
        == [FETCHED_AT.isoformat()] * 3
    )
    assert (
        json.loads(first_disposition["market_updated_at"])
        == [(FETCHED_AT - timedelta(hours=1)).isoformat()] * 3
    )
    assert json.loads(first_disposition["market_payload_hashes"]) == [
        "market-hash-0-0",
        "market-hash-0-1",
        "market-hash-0-2",
    ]
    assert {
        (
            row["requests_made"],
            row["cache_hits"],
            row["target_fetched_at"],
            row["daily_limit"],
            row["daily_remaining"],
            row["minute_remaining"],
            row["consensus_minimum_bookmakers"],
            row["consensus_maximum_age_hours"],
            row["gate_decision"],
        )
        for row in disposition_rows
    } == {
        (
            "16",
            "0",
            FETCHED_AT.isoformat(),
            "100",
            "78",
            "8",
            "3",
            "36.000000",
            "PENDING",
        )
    }
    assert [
        (
            row["gate_predicate"],
            row["gate_operator"],
            row["gate_threshold"],
            row["gate_actual"],
            row["gate_passed"],
        )
        for row in gate_rows
    ] == [
        ("minimum_drawings", ">=", "30", "1", "false"),
        ("minimum_events", ">=", "450", "15", "false"),
        (
            "minimum_unique_match_rate",
            ">=",
            "0.800000000000",
            "1.000000000000",
            "true",
        ),
        (
            "minimum_usable_consensus_rate",
            ">=",
            "0.700000000000",
            "0.600000000000",
            "false",
        ),
        ("zero_ambiguous_matches", "==", "0", "0", "true"),
        ("complete_explicit_dispositions", "==", "15", "15", "true"),
    ]
    markdown = first_paths[1].read_text(encoding="utf-8")
    assert "- minimum bookmakers: 3" in markdown
    assert "- collection consensus minimum bookmakers: 3" in markdown
    assert "- collection consensus maximum odds age hours: 36.000000" in markdown
    assert "- gate sample floor: 30 drawings and 450 events" in markdown
    assert "- decision: PENDING" in markdown
    assert "- reasons: fewer than 30 drawings, fewer than 450 events" in markdown
    assert "## Collection Run Evidence" in markdown
    assert "## Schedule Date Evidence" in markdown
    assert "## Eligibility Counts" in markdown
    assert "## Diagnostic Scope Metrics" in markdown
    assert "| ordinary_two_day | 15 |" in markdown
    assert f"| 16 | 0 | {FETCHED_AT.isoformat()} | 100 | 78 | 8 |" in markdown
    assert "## Gate Predicate Outcomes" in markdown
    assert "| minimum_events | 15 | >= | 450 | false |" in markdown
    assert (
        "| minimum_usable_consensus_rate | 0.600000000000 | >= | "
        "0.700000000000 | false |"
    ) in markdown
    assert first_hashes == (
        "45359a3edb07741261cf3cfa5caa3e6f85628f99e76adb3e9998afa4400655b5",
        "796fb78654a5db4a6c0bb9d9f8979fcf37b34c1b1d2f229ee9e080692f6544bb",
    )


def test_secret_absent_from_sqlite_cache_cli_exceptions_and_reports(
    monkeypatch,
    tmp_path,
):
    factory, db_path = sqlite_factory(tmp_path)
    install_open_drawing(monkeypatch)
    audit_report_dir = tmp_path / "reports"
    collect_open_external_odds(
        totobrief_client=FakeTotoBriefClient(drawing_info_payload()),
        provider=MixedCoverageProvider(consensus_events=9),
        session_factory=factory,
        aliases={},
        fetched_at=FETCHED_AT,
    )
    report_paths = write_external_coverage_reports(
        audit_external_coverage(factory, last=1, minimum_bookmakers=3),
        report_dir=audit_report_dir,
    )

    cache_dir = tmp_path / "cache"
    cache_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    APISportsClient(SECRET, session=cache_session, cache_dir=cache_dir).fetch_schedule(
        "football",
        (date(2026, 7, 14),),
    )

    failing_session = FakeSession(
        [requests.ConnectionError(f"transport leaked {SECRET}")]
    )
    with pytest.raises(APISportsError) as excinfo:
        APISportsClient(
            SECRET,
            session=failing_session,
            cache_dir=tmp_path / "failing-cache",
            max_retries=0,
        ).fetch_schedule("football", (date(2026, 7, 14),))

    class ExplodingAPISportsClient:
        def __init__(self, *_args, **_kwargs):
            raise APISportsError(f"provider leaked {SECRET}")

    monkeypatch.setenv("API_SPORTS_KEY", SECRET)
    monkeypatch.setattr(cli_module, "APISportsClient", ExplodingAPISportsClient)
    monkeypatch.setattr(
        cli_module,
        "collect_fresh_open_external_odds",
        lambda **kwargs: kwargs["provider_factory"](tmp_path / "fresh-cache"),
    )
    cli_result = CliRunner().invoke(
        app,
        [
            "collect-external-odds",
            "--open",
            "--db",
            str(tmp_path / "cli.db"),
        ],
    )

    assert cache_session.calls[0]["headers"]["x-apisports-key"] == SECRET
    assert SECRET not in "\n".join(sqlite_text_values(db_path))
    assert SECRET not in "".join(
        path.read_text(encoding="utf-8") for path in cache_dir.iterdir()
    )
    transport_chain = recursive_exception_chain(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None
    assert len(transport_chain) == 1
    assert_secret_absent_from_exception_chain(excinfo.value)
    assert cli_result.exit_code != 0
    assert SECRET not in cli_result.output
    assert_secret_absent_from_exception_chain(cli_result.exception)
    assert "[redacted]" in cli_result.output
    assert SECRET not in "".join(
        path.read_text(encoding="utf-8") for path in report_paths
    )


def run_timing_acceptance_scenario(
    monkeypatch,
    tmp_path: Path,
    factory,
    scenario: TimingAcceptanceScenario,
    payload: dict[str, object],
):
    install_open_drawing(
        monkeypatch,
        drawing_id=scenario.drawing_id,
        drawing_number=scenario.drawing_id - 4000,
    )
    provider_starts = timing_acceptance_provider_starts(scenario, payload)
    provider_paths = []
    monotonic_values = iter(float(value) for value in range(20))

    def provider_factory(cache_dir: Path):
        pass_index = len(provider_paths)
        provider_paths.append(cache_dir)
        return TimingAcceptanceProvider(
            scenario=scenario,
            starts_by_order=provider_starts,
            observed_at=FETCHED_AT + timedelta(minutes=pass_index + 1),
        )

    def forbid_sleep(_seconds: float) -> None:
        raise AssertionError("acceptance must not sleep")

    result = collect_fresh_open_external_odds(
        totobrief_client=FakeTotoBriefClient(payload),
        provider_factory=provider_factory,
        session_factory=factory,
        aliases={},
        cache_root=tmp_path / "acceptance-cache",
        max_passes=scenario.max_passes,
        expansion_horizon_days=5,
        max_expansion_passes=1,
        retry_delay_seconds=0.0,
        now=lambda: FETCHED_AT,
        monotonic=lambda: next(monotonic_values),
        sleep=forbid_sleep,
    )

    assert provider_paths == [result.cache_dir] * len(result.passes)
    return result


def storage_projected_snapshot(snapshot):
    def projected_dates(values):
        return tuple(replace(item, events=()) for item in values)

    return replace(
        snapshot,
        requested_schedule_dates=projected_dates(snapshot.requested_schedule_dates),
        successful_schedule_dates=projected_dates(
            snapshot.successful_schedule_dates
        ),
        failed_schedule_dates=projected_dates(snapshot.failed_schedule_dates),
    )


def timing_acceptance_payload(
    scenario: TimingAcceptanceScenario,
) -> dict[str, object]:
    deadline = datetime(2026, 7, 14, 15, 0, tzinfo=timezone.utc)
    base_start = deadline + timedelta(hours=1)
    events = []
    for order in reversed(range(15)):
        if scenario.name == "ordinary":
            day_offset = order // 8
        elif scenario.name == "multi_day":
            day_offset = order // 5
        else:
            day_offset = 0
        starts_at = base_start + timedelta(days=day_offset, minutes=order)
        if order == scenario.missing_target_order:
            starts_at = None
        events.append(
            {
                "id": scenario.drawing_id * 100 + order,
                "order": order,
                "name": f"Home {order} - Away {order}",
                "name_en": f"Home {order} - Away {order}",
                "championship": f"League {order % 3}",
                "sport": "football",
                "start_at": None if starts_at is None else starts_at.isoformat(),
                "quotes": {
                    "bk_win_1": 45 + order,
                    "bk_draw": 30 + order,
                    "bk_win_2": 25 + order,
                    "pool_win_1": 48 + order,
                    "pool_draw": 32 + order,
                    "pool_win_2": 20 + order,
                },
            }
        )
    return {
        "data": {
            "id": scenario.drawing_id,
            "number": scenario.drawing_id - 4000,
            "ended_at": deadline.isoformat(),
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": events,
        }
    }


def timing_acceptance_provider_starts(
    scenario: TimingAcceptanceScenario,
    payload: dict[str, object],
) -> dict[int, datetime]:
    data = payload["data"]
    assert isinstance(data, dict)
    events = data["events"]
    assert isinstance(events, list)
    starts_by_order = {
        event["order"]: datetime.fromisoformat(event["start_at"])
        for event in events
        if event["start_at"] is not None
    }
    if scenario.provider_day_offset is not None:
        deadline = datetime.fromisoformat(data["ended_at"])
        starts_by_order[scenario.missing_target_order] = deadline + timedelta(
            days=scenario.provider_day_offset,
            hours=1,
            minutes=scenario.missing_target_order,
        )
    return starts_by_order


class TimingAcceptanceProvider:
    provider_name = "api-sports"

    def __init__(
        self,
        *,
        scenario: TimingAcceptanceScenario,
        starts_by_order: dict[int, datetime],
        observed_at: datetime,
    ) -> None:
        self.scenario = scenario
        self.starts_by_order = starts_by_order
        self.observed_at = observed_at
        self.requests_made = 0
        self.cache_hits = 0
        self._quota_state = QuotaState(100, 80, 10, 8)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(
        self,
        sport: str,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        assert sport == "football"
        assert len(dates) == 1
        requested_date = dates[0]
        if requested_date == self.scenario.failed_schedule_date:
            raise APISportsError(
                f"schedule unavailable; credential {SECRET}"
            )
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"event-{order}",
                sport="football",
                league=f"League {order % 3}",
                starts_at=starts_at,
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                fetched_at=self.observed_at,
                payload_hash=f"{self.scenario.name}-schedule-{order}",
            )
            for order, starts_at in sorted(self.starts_by_order.items())
            if starts_at.date() == requested_date
        )

    def fetch_event_markets(
        self,
        sport: str,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        self.requests_made += 1
        assert sport == "football"
        order = int(provider_event_id.removeprefix("event-"))
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=self.observed_at - timedelta(hours=1),
                fetched_at=self.observed_at,
                payload_hash=(
                    f"{self.scenario.name}-market-{order}-{index}"
                ),
                home_price=2.0 + index / 10,
                draw_price=3.8 + index / 10,
                away_price=4.2 + index / 10,
            )
            for index in range(3)
        )


def install_fast_acceptance_ev(monkeypatch) -> None:
    def fixed_components(_ev_input, progress_callback=None):
        if progress_callback is not None:
            progress_callback({"phase": "category", "category": 15})
        values = np.zeros(9, dtype=np.float64)
        return EVComponents(
            possible_winnings_ev_per_ruble=values,
            jackpot_ev_per_ruble=values,
            event_count=2,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    def fixed_surface(_components, _possible_winnings, _jackpot):
        return EVSurface(
            gross_ev=np.linspace(1.1, 1.3, num=9, dtype=np.float64),
            event_count=2,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    monkeypatch.setattr(drawing_module, "compute_ev_components", fixed_components)
    monkeypatch.setattr(drawing_module, "materialize_ev_surface", fixed_surface)
    monkeypatch.setattr(
        drawing_module,
        "_utc_now",
        lambda: FETCHED_AT.isoformat(),
    )


def build_timing_acceptance_ev(payload, *, mode, timing_resolver):
    data = payload["data"]
    return build_open_ev_package(
        client=FakeTotoBriefClient(payload),
        drawing_id=data["id"],
        config=EVConfig(bank=30, stake=30, mode=mode, min_gross_ev=1.0),
        timing_eligibility_resolver=timing_resolver,
    )


def assert_zero_cost_no_bet(run) -> None:
    assert run.package.decision == "NO BET"
    assert run.package.coupons == ()
    assert run.package.cost == 0
    assert run.package.unused_bank == run.config.bank
    assert run.package.expected_payout == 0.0
    assert run.package.modeled_roi is None
    assert all(value == "" for value in run.package.derived_brief)
    assert all(row.decision == "NO BET" for row in run.sensitivity)


def recursive_exception_chain(error: BaseException) -> tuple[BaseException, ...]:
    pending = [error]
    seen: set[int] = set()
    chain: list[BaseException] = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return tuple(chain)


def assert_secret_absent_from_exception_chain(error: BaseException) -> None:
    for reachable in recursive_exception_chain(error):
        assert SECRET not in str(reachable)
        assert SECRET not in repr(reachable)


def sqlite_factory(tmp_path: Path):
    db_path = tmp_path / "toto.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False), db_path


def install_open_drawing(
    monkeypatch,
    *,
    drawing_id: int = 9000,
    drawing_number: int = 5000,
) -> None:
    monkeypatch.setattr(
        collection_module,
        "resolve_open_drawing_from_api",
        lambda _client: type(
            "Reference",
            (),
            {"drawing_id": drawing_id, "number": drawing_number},
        )(),
    )


class FakeTotoBriefClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        assert drawing_id == self.payload["data"]["id"]
        return self.payload


class MixedCoverageProvider:
    provider_name = "api-sports"

    def __init__(self, *, consensus_events: int) -> None:
        self.consensus_events = consensus_events
        self.requests_made = 0
        self.market_calls: tuple[str, ...] = ()
        self._quota_state = QuotaState(100, 78, 10, 8)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(
        self, sport: str, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        assert sport == "football"
        assert dates == (date(2026, 7, 14),)
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"football-{order}",
                sport="football",
                league=f"League {order % 3}",
                starts_at=event_start(order),
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                fetched_at=FETCHED_AT,
                payload_hash=f"schedule-hash-{order}",
            )
            for order in range(15)
        )

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        self.requests_made += 1
        self.market_calls = (*self.market_calls, provider_event_id)
        order = int(provider_event_id.rsplit("-", 1)[1])
        bookmaker_count = 3 if order < self.consensus_events else 2
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=FETCHED_AT - timedelta(hours=1),
                fetched_at=FETCHED_AT,
                payload_hash=f"market-hash-{order}-{index}",
                home_price=2.0 + index / 10,
                draw_price=3.8 + index / 10,
                away_price=4.2 + index / 10,
            )
            for index in range(bookmaker_count)
        )


class ProviderFailureProvider(MixedCoverageProvider):
    def __init__(self) -> None:
        super().__init__(consensus_events=0)

    def fetch_schedule(
        self, sport: str, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self.requests_made += 1
        raise APISportsError("sanitized provider unavailable")


class QuotaAfterProvider(MixedCoverageProvider):
    def __init__(self, *, after: int) -> None:
        super().__init__(consensus_events=15)
        self.after = after

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        if len(self.market_calls) >= self.after:
            self.market_calls = (*self.market_calls, provider_event_id)
            self.requests_made += 1
            self._quota_state = QuotaState(100, 10, 10, 0)
            from toto_ai.external_odds.api_sports import QuotaExhausted

            raise QuotaExhausted("quota reserve reached")
        return super().fetch_event_markets(sport, provider_event_id)


class InterruptingProvider(MixedCoverageProvider):
    def __init__(self) -> None:
        super().__init__(consensus_events=15)

    def fetch_event_markets(
        self, sport: str, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        raise KeyboardInterrupt("operator interrupted")


def drawing_info_payload() -> dict[str, object]:
    return {
        "data": {
            "id": 9000,
            "number": 5000,
            "ended_at": (FETCHED_AT + timedelta(hours=5)).isoformat(),
            "pool_sum": 2_000_000.0,
            "jackpot": 250_000.0,
            "events": [
                {
                    "id": 10_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "name_en": f"Home {order} - Away {order}",
                    "championship": f"League {order % 3}",
                    "sport": "football",
                    "start_at": event_start(order).isoformat(),
                    "quotes": {
                        "bk_win_1": 45 + order,
                        "bk_draw": 30 + order,
                        "bk_win_2": 25 + order,
                        "pool_win_1": 48 + order,
                        "pool_draw": 32 + order,
                        "pool_win_2": 20 + order,
                    },
                }
                for order in reversed(range(15))
            ],
        }
    }


def event_start(order: int) -> datetime:
    return FETCHED_AT + timedelta(hours=6, minutes=order)


def sqlite_text_values(db_path: Path) -> list[str]:
    values: list[str] = []
    with sqlite3.connect(db_path) as connection:
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table_name in table_names:
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table_name})")
                if "CHAR" in row[2].upper() or "TEXT" in row[2].upper()
            ]
            if not columns:
                continue
            escaped_columns = ", ".join(f'"{column}"' for column in columns)
            for row in connection.execute(
                f'SELECT {escaped_columns} FROM "{table_name}"'
            ):
                values.extend(str(value) for value in row if value is not None)
    return values


@dataclass
class FakeResponse:
    payload: dict[str, object]
    headers: dict[str, str]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def quota_headers() -> dict[str, str]:
    return {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "x-ratelimit-limit": "10",
        "x-ratelimit-remaining": "9",
    }


def football_schedule_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_481_600,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "fixture": {
                    "id": 42,
                    "date": "2026-07-14T18:00:00+00:00",
                },
                "league": {"name": "Premier League"},
                "teams": {
                    "home": {"name": "Home FC"},
                    "away": {"name": "Away FC"},
                },
            }
        ],
    }
