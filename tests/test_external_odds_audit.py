from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base
from toto_ai.external_odds.audit import audit_external_coverage
from toto_ai.external_odds.collection import (
    ExternalBookmakerQuoteRecord,
    ExternalCollectionSnapshot,
    ExternalEventDispositionRecord,
    ExternalMarketProvenanceRecord,
    ScheduleDateResult,
)
from toto_ai.external_odds.eligibility import (
    EffectiveEventStart,
    classify_drawing_eligibility,
)
from toto_ai.external_odds.storage import (
    load_current_drawing_eligibility,
    save_collection,
)


def aware_now() -> datetime:
    return datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def audit_from_counts(
    *,
    drawings: int,
    events: int,
    unique_matches: int,
    usable_consensus: int,
    consumed_ambiguous: int,
    explicit_dispositions: int,
    operational_failures: int,
):
    return audit_external_coverage(
        _snapshot_session_factory(
            _collections_from_counts(
                drawings=drawings,
                events=events,
                unique_matches=unique_matches,
                usable_consensus=usable_consensus,
                consumed_ambiguous=consumed_ambiguous,
                explicit_dispositions=explicit_dispositions,
                operational_failures=operational_failures,
            )
        ),
        last=drawings,
        minimum_bookmakers=3,
    )


def test_gate_requires_all_registered_thresholds():
    audit = audit_from_counts(
        drawings=30,
        events=450,
        unique_matches=360,
        usable_consensus=315,
        consumed_ambiguous=0,
        explicit_dispositions=450,
        operational_failures=0,
    )

    assert audit.gate.decision == "GO"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"unique_matches": 359}, "unique match rate below 80%"),
        ({"usable_consensus": 314}, "consensus coverage below 70%"),
        ({"consumed_ambiguous": 1}, "ambiguous match consumed"),
        ({"explicit_dispositions": 449}, "silent event loss"),
    ],
)
def test_gate_fails_closed(change, reason):
    values = {
        "drawings": 30,
        "events": 450,
        "unique_matches": 360,
        "usable_consensus": 315,
        "consumed_ambiguous": 0,
        "explicit_dispositions": 450,
        "operational_failures": 0,
    }
    values.update(change)

    audit = audit_from_counts(**values)

    assert audit.gate.decision == "STOP"
    assert reason in audit.gate.reasons


def test_gate_is_pending_before_prospective_sample_floor():
    audit = audit_from_counts(
        drawings=29,
        events=435,
        unique_matches=435,
        usable_consensus=435,
        consumed_ambiguous=0,
        explicit_dispositions=435,
        operational_failures=0,
    )

    assert audit.gate.decision == "PENDING"
    assert "fewer than 30 drawings" in audit.gate.reasons
    assert "fewer than 450 events" in audit.gate.reasons


def test_gate_does_not_add_unregistered_provider_failure_predicate():
    audit = audit_from_counts(
        drawings=30,
        events=450,
        unique_matches=360,
        usable_consensus=315,
        consumed_ambiguous=0,
        explicit_dispositions=450,
        operational_failures=1,
    )

    assert audit.gate.decision == "GO"
    assert "operational failures present" not in audit.gate.reasons
    assert audit.gate.operational_failures == 1


def test_audit_reports_every_disposition_and_fallback_reason():
    audit = audit_external_coverage(
        _snapshot_session_factory(
            (
                _collection(
                    1,
                    (
                        "unknown sport",
                        "0 exact candidates",
                        "provider schedule failure: unavailable",
                        "provider odds failure: unavailable",
                        "quota reserve reached",
                    ),
                ),
            )
        ),
        last=1,
        minimum_bookmakers=3,
    )

    assert audit.total.target_count == 15
    assert audit.total.explicit_dispositions == 15
    assert len(audit.dispositions) == 15
    assert audit.fallback_reason_counts["unknown sport"] == 1
    assert audit.fallback_reason_counts["0 exact candidates"] == 1
    assert audit.fallback_reason_counts["provider schedule failure"] == 1
    assert audit.fallback_reason_counts["provider odds failure"] == 1
    assert audit.fallback_reason_counts["quota reserve reached"] == 1


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("fewer than 3 eligible bookmakers: stale prices", (1, 0, 0, 0, 0)),
        ("fewer than 3 eligible bookmakers: missing outcomes", (0, 0, 1, 0, 0)),
        (
            "fewer than 3 eligible bookmakers: duplicate bookmaker market",
            (0, 1, 0, 0, 0),
        ),
        (
            "fewer than 3 eligible bookmakers: not full-time three-way",
            (0, 1, 0, 0, 0),
        ),
        (
            "fewer than 3 eligible bookmakers: not regulation three-way",
            (0, 1, 0, 0, 0),
        ),
        ("fewer than 3 eligible bookmakers", (0, 0, 0, 0, 0)),
        ("quota reserve reached", (0, 0, 0, 1, 0)),
        ("provider odds failure: unavailable", (0, 0, 0, 0, 1)),
        (
            "stale prices extended; missing outcomes backup; "
            "not full-time three-way extra; quota-like; provider-like",
            (0, 0, 0, 0, 0),
        ),
    ],
)
def test_fallback_classification_uses_exact_canonical_reasons(reason, expected):
    audit = audit_external_coverage(
        _snapshot_session_factory((_collection(1, (reason,)),)),
        last=1,
        minimum_bookmakers=3,
    )

    assert (
        audit.total.stale_count,
        audit.total.semantic_count,
        audit.total.incomplete_market_count,
        audit.total.quota_count,
        audit.total.provider_error_count,
    ) == expected


def test_fallback_reason_components_are_classified_once_per_event():
    audit = audit_external_coverage(
        _snapshot_session_factory(
            (
                _collection(
                    1,
                    (
                        "fewer than 3 eligible bookmakers: "
                        "duplicate bookmaker market, missing outcomes, "
                        "not full-time three-way, stale prices",
                    ),
                ),
            )
        ),
        last=1,
        minimum_bookmakers=3,
    )

    assert audit.total.stale_count == 1
    assert audit.total.semantic_count == 1
    assert audit.total.incomplete_market_count == 1


def test_bookmaker_threshold_counts_include_matched_minimum_fallbacks():
    audit = audit_external_coverage(
        _snapshot_session_factory(
            (
                _collection(
                    1,
                    ("fewer than 3 eligible bookmakers",),
                    fallback_bookmaker_counts=(2,),
                ),
            )
        ),
        last=1,
        minimum_bookmakers=3,
    )

    assert audit.total.consensus_1_count == 15
    assert audit.total.consensus_2_count == 15
    assert audit.total.consensus_3_count == 14
    assert audit.total.usable_consensus_count == 14


def test_audit_reads_latest_complete_collections_from_storage():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    save_collection(factory, _collection(1, ()))
    save_collection(factory, _collection(2, ("0 exact candidates",)))

    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)

    assert audit.drawings == 1
    assert audit.total.target_count == 15
    assert audit.total.missing_count == 1
    assert audit.dispositions[0].drawing_id == 1002


def test_collection_scopes_are_disjoint_fixed_and_have_isolated_rates():
    fallback_counts = (0, 3, 6, 9)
    scope_names = ("ordinary_two_day", "expanded", "multi_day", "unknown")
    collections = tuple(
        _modern_collection(
            _collection(index, ("0 exact candidates",) * fallback_count),
            scope=scope,
        )
        for index, (scope, fallback_count) in enumerate(
            zip(scope_names, fallback_counts, strict=True),
            start=1,
        )
    )

    audit = audit_external_coverage(
        _snapshot_session_factory(collections),
        last=4,
        minimum_bookmakers=3,
    )

    assert [metric.name for metric in audit.by_scope] == list(scope_names)
    assert [metric.target_count for metric in audit.by_scope] == [15, 15, 15, 15]
    assert [metric.usable_consensus_rate for metric in audit.by_scope] == [
        1.0,
        0.8,
        0.6,
        0.4,
    ]
    assert sum(metric.target_count for metric in audit.by_scope) == 60


def test_gate_keeps_existing_predicates_and_uses_all_selected_scopes():
    collections = tuple(
        _modern_collection(_collection(index, ()), scope=scope)
        for index, scope in enumerate(
            ("ordinary_two_day", "expanded", "multi_day", "unknown"),
            start=1,
        )
    )

    audit = audit_external_coverage(
        _snapshot_session_factory(collections),
        last=4,
        minimum_bookmakers=3,
    )

    assert audit.total.target_count == 60
    assert audit.gate.events == 60
    assert audit.gate.unique_match_rate == audit.total.unique_match_rate == 1.0
    assert audit.gate.consensus_rate == audit.total.usable_consensus_rate == 1.0
    assert [predicate.name for predicate in audit.gate.predicates] == [
        "minimum_drawings",
        "minimum_events",
        "minimum_unique_match_rate",
        "minimum_usable_consensus_rate",
        "zero_ambiguous_matches",
        "complete_explicit_dispositions",
    ]


def test_provider_missing_and_partial_schedule_events_are_counted_separately():
    collection = _modern_collection(
        _collection(1, ("0 exact candidates", "partial schedule")),
        scope="unknown",
    )

    audit = audit_external_coverage(
        _snapshot_session_factory((collection,)),
        last=1,
        minimum_bookmakers=3,
    )

    assert audit.total.missing_count == 2
    assert audit.total.provider_missing_count == 1
    assert audit.total.partial_schedule_count == 1


def test_failed_schedule_date_units_and_reasons_are_not_event_fallback_units():
    schedule_results = (
        ScheduleDateResult("football", date(2026, 7, 14), (), None),
        ScheduleDateResult(
            "football",
            date(2026, 7, 15),
            (),
            "provider schedule failure",
        ),
        ScheduleDateResult(
            "hockey",
            date(2026, 7, 14),
            (),
            "provider schedule failure",
        ),
        ScheduleDateResult(
            "hockey",
            date(2026, 7, 15),
            (),
            "quota reserve reached",
        ),
    )
    collection = _modern_collection(
        _collection(1, ("partial schedule",)),
        scope="unknown",
        schedule_results=schedule_results,
    )

    audit = audit_external_coverage(
        _snapshot_session_factory((collection,)),
        last=1,
        minimum_bookmakers=3,
    )

    assert audit.requested_schedule_date_count == 4
    assert audit.successful_schedule_date_count == 1
    assert audit.failed_schedule_date_count == 3
    assert audit.failed_schedule_reason_counts == {
        "provider schedule failure": 2,
        "quota reserve reached": 1,
    }
    assert audit.total.partial_schedule_count == 1
    assert audit.failed_schedule_date_count != audit.total.partial_schedule_count


def test_storage_backed_audit_exposes_collection_and_event_timing_provenance():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    schedule_results = (
        ScheduleDateResult("football", date(2026, 7, 14), (), None),
        ScheduleDateResult(
            "hockey",
            date(2026, 7, 15),
            (),
            "provider schedule failure",
        ),
    )
    collection = _modern_collection(
        _collection(1, ()),
        scope="ordinary_two_day",
        schedule_results=schedule_results,
        provider_orders=(0,),
    )
    save_collection(factory, collection)

    audit = audit_external_coverage(factory, last=1, minimum_bookmakers=3)
    row = audit.dispositions[0]

    assert row.collection_scope == "ordinary_two_day"
    assert row.target_fingerprint == "fingerprint-1"
    assert row.missing_start_horizon_days == 2
    assert row.requested_schedule_dates == (
        "football:2026-07-14",
        "hockey:2026-07-15",
    )
    assert row.successful_schedule_dates == ("football:2026-07-14",)
    assert row.failed_schedule_dates == ("hockey:2026-07-15",)
    assert row.failed_schedule_reasons == ("provider schedule failure",)
    assert row.target_starts_at == ""
    assert row.provider_starts_at == aware_now().isoformat()
    assert row.effective_starts_at == aware_now().isoformat()
    assert row.effective_start_source == "provider"
    assert row.eligibility_status == "playable"
    assert row.eligibility_span_days == 2
    assert row.eligibility_missing_event_orders == ()
    assert row.eligibility_totobrief_count == 14
    assert row.eligibility_provider_count == 1


def test_legacy_collection_is_always_in_unknown_scope():
    audit = audit_external_coverage(
        _snapshot_session_factory((_collection(1, ()),)),
        last=1,
        minimum_bookmakers=3,
    )

    assert [metric.target_count for metric in audit.by_scope] == [0, 0, 0, 15]
    assert {row.collection_scope for row in audit.dispositions} == {"unknown"}
    assert {row.eligibility_status for row in audit.dispositions} == {"unknown"}


def test_same_timestamp_append_order_wins_exact_lookup_and_audit_dedup(
    tmp_path,
):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'audit.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    older = _modern_collection(_collection(1, ()), scope="ordinary_two_day")
    same_base = replace(
        _modern_collection(_collection(2, ()), scope="ordinary_two_day"),
        collection_id="same-timestamp-base",
    )
    newer = _modern_collection(_collection(3, ()), scope="ordinary_two_day")
    same_later = replace(
        _modern_collection(_collection(2, ()), scope="unknown"),
        collection_id="same-timestamp-later",
    )
    for collection in (same_base, newer, older, same_later):
        save_collection(factory, collection)

    assert load_current_drawing_eligibility(
        factory,
        same_later.drawing_id,
        same_later.target_fingerprint,
    ) == same_later.eligibility
    audit = audit_external_coverage(factory, last=3, minimum_bookmakers=3)
    assert tuple(item.collection_id for item in audit.collections) == (
        newer.collection_id,
        same_later.collection_id,
        older.collection_id,
    )
    assert same_base.collection_id not in {
        item.collection_id for item in audit.collections
    }
    engine.dispose()


def _snapshot_session_factory(collections):
    class SnapshotFactory:
        _external_collections_for_test = tuple(collections)

    return SnapshotFactory()


def _collections_from_counts(
    *,
    drawings: int,
    events: int,
    unique_matches: int,
    usable_consensus: int,
    consumed_ambiguous: int,
    explicit_dispositions: int,
    operational_failures: int,
):
    if events > drawings * 15:
        raise ValueError("events cannot exceed drawings * 15 in test fixture")
    rows = []
    for index in range(events):
        if index >= explicit_dispositions:
            rows.append("silent")
        elif index < usable_consensus:
            rows.append("consensus")
        elif index < unique_matches:
            rows.append("matched_fallback")
        elif index < unique_matches + consumed_ambiguous:
            rows.append("ambiguous")
        elif index < unique_matches + consumed_ambiguous + operational_failures:
            rows.append("provider_failure")
        else:
            rows.append("missing")
    rows.extend(["absent"] * (drawings * 15 - len(rows)))
    return tuple(
        _collection(
            drawing_index + 1,
            (),
            event_kinds=tuple(rows[drawing_index * 15 : (drawing_index + 1) * 15]),
        )
        for drawing_index in range(drawings)
    )


def _collection(
    drawing_index: int,
    fallback_reasons: tuple[str, ...],
    *,
    event_kinds: tuple[str, ...] | None = None,
    fallback_bookmaker_counts: tuple[int, ...] | None = None,
) -> ExternalCollectionSnapshot:
    if fallback_bookmaker_counts is not None and len(fallback_bookmaker_counts) != len(
        fallback_reasons
    ):
        raise ValueError("fallback bookmaker counts must align with fallback reasons")
    now = aware_now() + timedelta(minutes=drawing_index)
    kinds = event_kinds or (
        *("fallback" for _ in fallback_reasons),
        *("consensus" for _ in range(15 - len(fallback_reasons))),
    )
    events = []
    for order, kind in enumerate(kinds):
        if kind == "absent":
            continue
        if kind == "fallback":
            reason = fallback_reasons[order]
            status = _status_for_reason(reason)
            base_kind = {
                "ambiguous": "ambiguous",
                "missing": "missing",
                "provider_failure": "provider_failure",
                "unknown_sport": "missing",
            }.get(status, "matched_fallback")
            event = _event(drawing_index, order, kind=base_kind)
            event = replace(
                event,
                match_status=status,
                fallback_reason=reason,
                probability_source="totobrief_bk_fallback",
                eligible_bookmaker_count=(
                    fallback_bookmaker_counts[order]
                    if fallback_bookmaker_counts is not None
                    else 0
                ),
                bookmaker_quotes=(),
            )
        else:
            event = _event(drawing_index, order, kind=kind)
        events.append(event)
    return ExternalCollectionSnapshot(
        collection_id=f"collection-{drawing_index}",
        drawing_id=1000 + drawing_index,
        drawing_number=5000 + drawing_index,
        provider="api-sports",
        fetched_at=now.isoformat(),
        target_fetched_at=(now - timedelta(minutes=1)).isoformat(),
        deadline=(now + timedelta(hours=6)).isoformat(),
        event_count=15,
        requests_made=16,
        cache_hits=0,
        daily_limit=100,
        daily_remaining=100 - drawing_index,
        minute_remaining=9,
        status="complete",
        events=tuple(events),
    )


def _modern_collection(
    collection: ExternalCollectionSnapshot,
    *,
    scope: str,
    schedule_results: tuple[ScheduleDateResult, ...] | None = None,
    provider_orders: tuple[int, ...] = (),
) -> ExternalCollectionSnapshot:
    if scope not in {"ordinary_two_day", "expanded", "multi_day", "unknown"}:
        raise ValueError("unsupported test collection scope")
    events = []
    for event in collection.events:
        target_start = aware_now() + timedelta(hours=event.event_order)
        if scope == "multi_day":
            target_start = aware_now() + timedelta(
                days=event.event_order // 5,
                hours=event.event_order % 5,
            )
        if event.event_order in provider_orders:
            events.append(
                replace(
                    event,
                    starts_at="",
                    provider_starts_at=target_start.isoformat(),
                    effective_starts_at=target_start.isoformat(),
                    effective_start_source="provider",
                )
            )
        elif scope == "unknown" and event.event_order == 14:
            events.append(
                replace(
                    event,
                    starts_at="",
                    provider_starts_at=None,
                    effective_starts_at=None,
                    effective_start_source="unresolved",
                )
            )
        else:
            events.append(
                replace(
                    event,
                    starts_at=target_start.isoformat(),
                    provider_starts_at=None,
                    effective_starts_at=target_start.isoformat(),
                    effective_start_source="totobrief",
                )
            )
    results = schedule_results or (
        ScheduleDateResult("football", date(2026, 7, 14), (), None),
    )
    eligibility = classify_drawing_eligibility(
        tuple(
            EffectiveEventStart(
                event.event_order,
                (
                    datetime.fromisoformat(event.effective_starts_at)
                    if event.effective_starts_at is not None
                    else None
                ),
                event.effective_start_source,
            )
            for event in events
        )
    )
    return replace(
        collection,
        events=tuple(events),
        target_fingerprint=f"fingerprint-{collection.drawing_id - 1000}",
        missing_start_horizon_days=5 if scope != "ordinary_two_day" else 2,
        requested_schedule_dates=results,
        successful_schedule_dates=tuple(item for item in results if item.error is None),
        failed_schedule_dates=tuple(item for item in results if item.error is not None),
        eligibility=eligibility,
    )


def _event(
    drawing_index: int,
    event_order: int,
    *,
    kind: str,
) -> ExternalEventDispositionRecord:
    matched = kind in {"consensus", "matched_fallback"}
    ambiguous = kind == "ambiguous"
    provider_failure = kind == "provider_failure"
    source = "external_consensus" if kind == "consensus" else "totobrief_bk_fallback"
    fallback_reason = None
    if source != "external_consensus":
        fallback_reason = {
            "matched_fallback": "minimum bookmakers unavailable",
            "ambiguous": "2 exact candidates",
            "provider_failure": "provider schedule failure: unavailable",
            "missing": "0 exact candidates",
            "silent": None,
        }.get(kind, "minimum bookmakers unavailable")
    match_status = "matched"
    if ambiguous:
        match_status = "ambiguous"
    elif provider_failure:
        match_status = "provider_failure"
    elif kind == "missing":
        match_status = "missing"
    return ExternalEventDispositionRecord(
        drawing_id=1000 + drawing_index,
        event_order=event_order,
        target_event_id=10_000 + event_order,
        sport="football" if event_order % 5 else "hockey",
        championship=f"League {event_order % 3}",
        starts_at=(aware_now() + timedelta(hours=event_order)).isoformat(),
        home_team=f"Home {event_order}",
        away_team=f"Away {event_order}",
        home_team_en=None,
        away_team_en=None,
        match_status=match_status,
        provider_event_id=(
            f"provider-{drawing_index}-{event_order}" if matched else None
        ),
        provider_event_fetched_at=aware_now().isoformat() if matched else None,
        provider_event_payload_hash="schedule-hash" if matched else None,
        matcher_version="api-sports-v1",
        match_candidate_ids=(
            ("a", "b") if ambiguous else (f"provider-{event_order}",) if matched else ()
        ),
        match_reason="unique exact match" if matched else fallback_reason or "",
        probability_source=source,
        probability_1=0.5,
        probability_x=0.25,
        probability_2=0.25,
        eligible_bookmaker_count=3 if source == "external_consensus" else 0,
        odds_age_hours=1.0 if source == "external_consensus" else None,
        fallback_reason=fallback_reason,
        payload_hash=f"event-hash-{drawing_index}-{event_order}",
        bookmaker_quotes=_quotes(event_order) if source == "external_consensus" else (),
    )


def _status_for_reason(reason: str) -> str:
    if reason == "unknown sport":
        return "unknown_sport"
    if reason == "partial schedule":
        return "missing"
    if reason.endswith("exact candidates"):
        return "missing" if reason.startswith("0 ") else "ambiguous"
    if "provider" in reason:
        return "provider_failure"
    return "matched"


def _quotes(event_order: int) -> tuple[ExternalBookmakerQuoteRecord, ...]:
    return tuple(
        ExternalBookmakerQuoteRecord(
            bookmaker_id=f"book-{index}",
            market_name="Match Winner",
            updated_at=aware_now().isoformat(),
            fetched_at=aware_now().isoformat(),
            payload_hash=f"quote-hash-{event_order}-{index}",
            home_price=2.0,
            draw_price=4.0,
            away_price=4.0,
            eligible=1,
            rejection_reason=None,
            source_count=1,
            source_provenance=(
                ExternalMarketProvenanceRecord(
                    updated_at=aware_now().isoformat(),
                    fetched_at=aware_now().isoformat(),
                    payload_hash=f"quote-hash-{event_order}-{index}",
                    home_price=2.0,
                    draw_price=4.0,
                    away_price=4.0,
                ),
            ),
        )
        for index in range(3)
    )
