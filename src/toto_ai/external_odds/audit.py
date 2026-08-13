from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

from toto_ai.external_odds.collection import (
    CONSENSUS_MINIMUM_BOOKMAKERS,
    EXTERNAL_CONSENSUS,
    TOTOBRIEF_BK_FALLBACK,
    ExternalCollectionSnapshot,
    ExternalEventDispositionRecord,
)
from toto_ai.external_odds.consensus import MAXIMUM_ODDS_AGE
from toto_ai.external_odds.storage import (
    count_complete_runs,
    load_latest_complete_collections,
)

GateDecision = Literal["PENDING", "GO", "STOP"]
CollectionScope = Literal[
    "ordinary_two_day",
    "expanded",
    "multi_day",
    "unknown",
]

COLLECTION_SCOPE_ORDER: tuple[CollectionScope, ...] = (
    "ordinary_two_day",
    "expanded",
    "multi_day",
    "unknown",
)

_CONSENSUS_FALLBACK_PATTERN = re.compile(
    r"^(?:fewer than [1-9][0-9]* eligible bookmakers|"
    r"external consensus unavailable)(?:: (?P<rejections>.+))?$"
)
_STALE_REASONS = frozenset({"stale prices"})
_SEMANTIC_REASONS = frozenset(
    {
        "duplicate bookmaker market",
        "not full-time three-way",
        "not regulation three-way",
    }
)
_INCOMPLETE_MARKET_REASONS = frozenset({"missing outcomes"})


@dataclass(frozen=True)
class CoverageDisposition:
    collection_id: str
    drawing_id: int
    drawing_number: int | None
    event_order: int
    sport: str
    league: str
    match_status: str
    match_orientation: str
    probability_source: str
    eligible_bookmaker_count: int
    fallback_reason: str
    provider_event_id: str | None
    provider_schedule_fetched_at: str | None
    provider_schedule_payload_hash: str | None
    market_fetched_at: tuple[str, ...]
    market_updated_at: tuple[str, ...]
    market_payload_hashes: tuple[str, ...]
    target_fetched_at: str
    collection_scope: CollectionScope
    target_fingerprint: str
    missing_start_horizon_days: int
    requested_schedule_dates: tuple[str, ...]
    successful_schedule_dates: tuple[str, ...]
    failed_schedule_dates: tuple[str, ...]
    failed_schedule_reasons: tuple[str, ...]
    target_starts_at: str | None
    provider_starts_at: str | None
    effective_starts_at: str | None
    effective_start_source: str
    eligibility_status: str
    eligibility_earliest_start: str | None
    eligibility_latest_start: str | None
    eligibility_span_days: int
    eligibility_missing_event_orders: tuple[int, ...]
    eligibility_totobrief_count: int
    eligibility_provider_count: int
    requests_made: int
    cache_hits: int
    daily_limit: int | None
    daily_remaining: int | None
    minute_remaining: int | None


@dataclass(frozen=True)
class CoverageMetrics:
    scope: str
    name: str
    target_count: int
    explicit_dispositions: int
    unique_match_count: int
    unique_match_rate: float
    missing_count: int
    missing_rate: float
    provider_missing_count: int
    partial_schedule_count: int
    ambiguous_count: int
    ambiguous_rate: float
    unknown_sport_count: int
    unknown_sport_rate: float
    consensus_1_count: int
    consensus_1_rate: float
    consensus_2_count: int
    consensus_2_rate: float
    consensus_3_count: int
    consensus_3_rate: float
    usable_consensus_count: int
    usable_consensus_rate: float
    stale_count: int
    semantic_count: int
    incomplete_market_count: int
    quota_count: int
    provider_error_count: int
    fallback_count: int


@dataclass(frozen=True)
class CoverageGate:
    decision: GateDecision
    reasons: tuple[str, ...]
    drawings: int
    events: int
    unique_match_rate: float
    consensus_rate: float
    ambiguous_matches: int
    explicit_dispositions: int
    operational_failures: int
    predicates: tuple[CoverageGatePredicate, ...]


@dataclass(frozen=True)
class CoverageGatePredicate:
    name: str
    operator: str
    threshold: int | float
    actual: int | float
    passed: bool


@dataclass(frozen=True)
class CoverageAudit:
    provider: str
    requested_last: int
    drawings: int
    minimum_bookmakers: int
    consensus_minimum_bookmakers: int
    consensus_maximum_age_hours: float
    collections: tuple[ExternalCollectionSnapshot, ...]
    dispositions: tuple[CoverageDisposition, ...]
    total: CoverageMetrics
    by_sport: tuple[CoverageMetrics, ...]
    by_league: tuple[CoverageMetrics, ...]
    by_drawing: tuple[CoverageMetrics, ...]
    by_scope: tuple[CoverageMetrics, ...]
    eligibility_counts: dict[str, int]
    requested_schedule_date_count: int
    successful_schedule_date_count: int
    failed_schedule_date_count: int
    failed_schedule_reason_counts: dict[str, int]
    fallback_reason_counts: dict[str, int]
    fallback_median_per_drawing: float
    fallback_p90_per_drawing: float
    average_requests_per_drawing: float
    maximum_requests_per_drawing: int
    gate: CoverageGate


def audit_external_coverage(
    session_factory: Any,
    *,
    last: int = 30,
    minimum_bookmakers: int = 3,
    provider: str | None = None,
) -> CoverageAudit:
    if not isinstance(last, int) or isinstance(last, bool) or last <= 0:
        raise ValueError("last must be a positive integer")
    if (
        not isinstance(minimum_bookmakers, int)
        or isinstance(minimum_bookmakers, bool)
        or minimum_bookmakers <= 0
    ):
        raise ValueError("minimum_bookmakers must be a positive integer")

    collections = _latest_complete_collections(
        session_factory,
        last,
        provider=provider,
    )
    dispositions = tuple(
        row
        for collection in collections
        for row in _dispositions_for_collection(collection)
    )
    provider = collections[0].provider if collections else provider or "none"
    total = _metrics("overall", "all", dispositions, minimum_bookmakers)
    by_sport = _grouped_metrics("sport", dispositions, minimum_bookmakers)
    by_league = _grouped_metrics("league", dispositions, minimum_bookmakers)
    by_drawing = _drawing_metrics(dispositions, minimum_bookmakers)
    by_scope = _scope_metrics(dispositions, minimum_bookmakers)
    eligibility_counts = Counter(
        collection.eligibility.status for collection in collections
    )
    failed_schedule_reason_counts = Counter(
        result.error
        for collection in collections
        for result in collection.failed_schedule_dates
        if result.error is not None
    )
    fallback_counts = _fallback_counts(dispositions)
    fallback_per_drawing = tuple(metric.fallback_count for metric in by_drawing)
    requests = tuple(collection.requests_made for collection in collections)
    gate = _coverage_gate(
        drawings=len(collections),
        total=total,
        minimum_bookmakers=minimum_bookmakers,
    )
    return CoverageAudit(
        provider=provider,
        requested_last=last,
        drawings=len(collections),
        minimum_bookmakers=minimum_bookmakers,
        consensus_minimum_bookmakers=CONSENSUS_MINIMUM_BOOKMAKERS,
        consensus_maximum_age_hours=(MAXIMUM_ODDS_AGE.total_seconds() / 3600.0),
        collections=collections,
        dispositions=dispositions,
        total=total,
        by_sport=by_sport,
        by_league=by_league,
        by_drawing=by_drawing,
        by_scope=by_scope,
        eligibility_counts={
            status: eligibility_counts[status]
            for status in ("playable", "multi_day", "unknown")
        },
        requested_schedule_date_count=sum(
            len(collection.requested_schedule_dates) for collection in collections
        ),
        successful_schedule_date_count=sum(
            len(collection.successful_schedule_dates) for collection in collections
        ),
        failed_schedule_date_count=sum(
            len(collection.failed_schedule_dates) for collection in collections
        ),
        failed_schedule_reason_counts=dict(
            sorted(failed_schedule_reason_counts.items())
        ),
        fallback_reason_counts=dict(sorted(fallback_counts.items())),
        fallback_median_per_drawing=(
            float(median(fallback_per_drawing)) if fallback_per_drawing else 0.0
        ),
        fallback_p90_per_drawing=_percentile(fallback_per_drawing, 0.90),
        average_requests_per_drawing=(
            sum(requests) / len(requests) if requests else 0.0
        ),
        maximum_requests_per_drawing=max(requests) if requests else 0,
        gate=gate,
    )


def _latest_complete_collections(
    session_factory: Any,
    last: int,
    *,
    provider: str | None = None,
) -> tuple[ExternalCollectionSnapshot, ...]:
    test_collections = getattr(session_factory, "_external_collections_for_test", None)
    if test_collections is not None:
        source = tuple(
            collection
            for collection in test_collections
            if provider is None or collection.provider == provider
        )
    else:
        source = load_latest_complete_collections(
            session_factory,
            last=max(last, count_complete_runs(session_factory)),
            provider=provider,
        )
    selected: list[ExternalCollectionSnapshot] = []
    seen_drawings: set[int] = set()
    for collection in source:
        if collection.status != "complete":
            continue
        if collection.drawing_id in seen_drawings:
            continue
        seen_drawings.add(collection.drawing_id)
        selected.append(collection)
        if len(selected) == last:
            break
    return tuple(selected)


def _dispositions_for_collection(
    collection: ExternalCollectionSnapshot,
) -> tuple[CoverageDisposition, ...]:
    collection_scope = _collection_scope(collection)
    requested_schedule_dates = _schedule_date_units(
        collection.requested_schedule_dates
    )
    successful_schedule_dates = _schedule_date_units(
        collection.successful_schedule_dates
    )
    failed_schedule_dates = _schedule_date_units(collection.failed_schedule_dates)
    failed_schedule_reasons = tuple(
        result.error
        for result in collection.failed_schedule_dates
        if result.error is not None
    )
    eligibility = collection.eligibility
    rows_by_order = {event.event_order: event for event in collection.events}
    rows = []
    for order in range(collection.event_count):
        event = rows_by_order.get(order)
        if event is None:
            rows.append(
                CoverageDisposition(
                    collection_id=collection.collection_id,
                    drawing_id=collection.drawing_id,
                    drawing_number=collection.drawing_number,
                    event_order=order,
                    sport="unknown",
                    league="unknown",
                    match_status="missing_disposition",
                    match_orientation="none",
                    probability_source="missing_disposition",
                    eligible_bookmaker_count=0,
                    fallback_reason="silent event loss",
                    provider_event_id=None,
                    provider_schedule_fetched_at=None,
                    provider_schedule_payload_hash=None,
                    market_fetched_at=(),
                    market_updated_at=(),
                    market_payload_hashes=(),
                    target_fetched_at=collection.target_fetched_at,
                    collection_scope=collection_scope,
                    target_fingerprint=collection.target_fingerprint,
                    missing_start_horizon_days=(
                        collection.missing_start_horizon_days
                    ),
                    requested_schedule_dates=requested_schedule_dates,
                    successful_schedule_dates=successful_schedule_dates,
                    failed_schedule_dates=failed_schedule_dates,
                    failed_schedule_reasons=failed_schedule_reasons,
                    target_starts_at=None,
                    provider_starts_at=None,
                    effective_starts_at=None,
                    effective_start_source="unresolved",
                    eligibility_status=eligibility.status,
                    eligibility_earliest_start=_optional_datetime_text(
                        eligibility.earliest_start
                    ),
                    eligibility_latest_start=_optional_datetime_text(
                        eligibility.latest_start
                    ),
                    eligibility_span_days=eligibility.span_days,
                    eligibility_missing_event_orders=(
                        eligibility.missing_event_orders
                    ),
                    eligibility_totobrief_count=eligibility.totobrief_count,
                    eligibility_provider_count=eligibility.provider_count,
                    requests_made=collection.requests_made,
                    cache_hits=collection.cache_hits,
                    daily_limit=collection.daily_limit,
                    daily_remaining=collection.daily_remaining,
                    minute_remaining=collection.minute_remaining,
                )
            )
            continue
        rows.append(
            _disposition_from_event(
                collection,
                event,
                collection_scope=collection_scope,
                requested_schedule_dates=requested_schedule_dates,
                successful_schedule_dates=successful_schedule_dates,
                failed_schedule_dates=failed_schedule_dates,
                failed_schedule_reasons=failed_schedule_reasons,
            )
        )
    return tuple(rows)


def _disposition_from_event(
    collection: ExternalCollectionSnapshot,
    event: ExternalEventDispositionRecord,
    *,
    collection_scope: CollectionScope,
    requested_schedule_dates: tuple[str, ...],
    successful_schedule_dates: tuple[str, ...],
    failed_schedule_dates: tuple[str, ...],
    failed_schedule_reasons: tuple[str, ...],
) -> CoverageDisposition:
    reason = _normalized_reason(event.fallback_reason)
    if event.probability_source == TOTOBRIEF_BK_FALLBACK and not reason:
        reason = "silent event loss"
    quotes = tuple(
        sorted(
            event.bookmaker_quotes,
            key=lambda quote: (
                quote.bookmaker_id,
                quote.market_name,
                quote.updated_at,
                quote.fetched_at,
                quote.payload_hash,
            ),
        )
    )
    eligibility = collection.eligibility
    return CoverageDisposition(
        collection_id=collection.collection_id,
        drawing_id=collection.drawing_id,
        drawing_number=collection.drawing_number,
        event_order=event.event_order,
        sport=event.sport,
        league=event.championship,
        match_status=event.match_status,
        match_orientation=event.match_orientation,
        probability_source=event.probability_source,
        eligible_bookmaker_count=event.eligible_bookmaker_count,
        fallback_reason=reason,
        provider_event_id=event.provider_event_id,
        provider_schedule_fetched_at=event.provider_event_fetched_at,
        provider_schedule_payload_hash=event.provider_event_payload_hash,
        market_fetched_at=tuple(quote.fetched_at for quote in quotes),
        market_updated_at=tuple(quote.updated_at for quote in quotes),
        market_payload_hashes=tuple(quote.payload_hash for quote in quotes),
        target_fetched_at=collection.target_fetched_at,
        collection_scope=collection_scope,
        target_fingerprint=collection.target_fingerprint,
        missing_start_horizon_days=collection.missing_start_horizon_days,
        requested_schedule_dates=requested_schedule_dates,
        successful_schedule_dates=successful_schedule_dates,
        failed_schedule_dates=failed_schedule_dates,
        failed_schedule_reasons=failed_schedule_reasons,
        target_starts_at=event.starts_at,
        provider_starts_at=event.provider_starts_at,
        effective_starts_at=event.effective_starts_at,
        effective_start_source=event.effective_start_source,
        eligibility_status=eligibility.status,
        eligibility_earliest_start=_optional_datetime_text(
            eligibility.earliest_start
        ),
        eligibility_latest_start=_optional_datetime_text(eligibility.latest_start),
        eligibility_span_days=eligibility.span_days,
        eligibility_missing_event_orders=eligibility.missing_event_orders,
        eligibility_totobrief_count=eligibility.totobrief_count,
        eligibility_provider_count=eligibility.provider_count,
        requests_made=collection.requests_made,
        cache_hits=collection.cache_hits,
        daily_limit=collection.daily_limit,
        daily_remaining=collection.daily_remaining,
        minute_remaining=collection.minute_remaining,
    )


def _metrics(
    scope: str,
    name: str,
    rows: tuple[CoverageDisposition, ...],
    minimum_bookmakers: int,
) -> CoverageMetrics:
    target_count = len(rows)
    unique_matches = sum(
        row.match_status == "matched" and row.provider_event_id is not None
        for row in rows
    )
    explicit = sum(_is_explicit_disposition(row) for row in rows)
    missing = sum(row.match_status == "missing" for row in rows)
    ambiguous = sum(row.match_status == "ambiguous" for row in rows)
    unknown_sport = sum(row.match_status == "unknown_sport" for row in rows)
    consensus_1 = _bookmaker_coverage_count(rows, 1)
    consensus_2 = _bookmaker_coverage_count(rows, 2)
    consensus_3 = _bookmaker_coverage_count(rows, 3)
    usable_consensus = _usable_consensus_count(rows, minimum_bookmakers)
    reasons = tuple(row.fallback_reason for row in rows if row.fallback_reason)
    return CoverageMetrics(
        scope=scope,
        name=name,
        target_count=target_count,
        explicit_dispositions=explicit,
        unique_match_count=unique_matches,
        unique_match_rate=_rate(unique_matches, target_count),
        missing_count=missing,
        missing_rate=_rate(missing, target_count),
        provider_missing_count=sum(
            row.match_status == "missing"
            and row.fallback_reason == "0 exact candidates"
            for row in rows
        ),
        partial_schedule_count=sum(
            row.match_status == "missing"
            and row.fallback_reason == "partial schedule"
            for row in rows
        ),
        ambiguous_count=ambiguous,
        ambiguous_rate=_rate(ambiguous, target_count),
        unknown_sport_count=unknown_sport,
        unknown_sport_rate=_rate(unknown_sport, target_count),
        consensus_1_count=consensus_1,
        consensus_1_rate=_rate(consensus_1, target_count),
        consensus_2_count=consensus_2,
        consensus_2_rate=_rate(consensus_2, target_count),
        consensus_3_count=consensus_3,
        consensus_3_rate=_rate(consensus_3, target_count),
        usable_consensus_count=usable_consensus,
        usable_consensus_rate=_rate(usable_consensus, target_count),
        stale_count=sum(_is_stale(reason) for reason in reasons),
        semantic_count=sum(_is_semantic(reason) for reason in reasons),
        incomplete_market_count=sum(
            _is_incomplete_market(reason) for reason in reasons
        ),
        quota_count=sum(reason == "quota reserve reached" for reason in reasons),
        provider_error_count=sum(
            reason in {"provider schedule failure", "provider odds failure"}
            for reason in reasons
        ),
        fallback_count=sum(
            row.probability_source == TOTOBRIEF_BK_FALLBACK
            or row.probability_source == "missing_disposition"
            for row in rows
        ),
    )


def _grouped_metrics(
    scope: str,
    rows: tuple[CoverageDisposition, ...],
    minimum_bookmakers: int,
) -> tuple[CoverageMetrics, ...]:
    grouped: dict[str, list[CoverageDisposition]] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, scope)].append(row)
    return tuple(
        _metrics(scope, name, tuple(grouped[name]), minimum_bookmakers)
        for name in sorted(grouped)
    )


def _drawing_metrics(
    rows: tuple[CoverageDisposition, ...],
    minimum_bookmakers: int,
) -> tuple[CoverageMetrics, ...]:
    grouped: dict[tuple[int, int | None], list[CoverageDisposition]] = defaultdict(list)
    for row in rows:
        grouped[(row.drawing_id, row.drawing_number)].append(row)
    metrics = []
    for drawing_id, drawing_number in sorted(grouped):
        name = str(drawing_number or drawing_id)
        metrics.append(
            _metrics(
                "drawing",
                name,
                tuple(grouped[(drawing_id, drawing_number)]),
                minimum_bookmakers,
            )
        )
    return tuple(metrics)


def _scope_metrics(
    rows: tuple[CoverageDisposition, ...],
    minimum_bookmakers: int,
) -> tuple[CoverageMetrics, ...]:
    grouped: dict[CollectionScope, list[CoverageDisposition]] = defaultdict(list)
    for row in rows:
        grouped[row.collection_scope].append(row)
    return tuple(
        _metrics(
            "collection_scope",
            scope,
            tuple(grouped[scope]),
            minimum_bookmakers,
        )
        for scope in COLLECTION_SCOPE_ORDER
    )


def _collection_scope(collection: ExternalCollectionSnapshot) -> CollectionScope:
    if collection.eligibility.status == "multi_day":
        return "multi_day"
    if collection.eligibility.status == "unknown":
        return "unknown"
    if collection.missing_start_horizon_days > 2:
        return "expanded"
    return "ordinary_two_day"


def _schedule_date_units(values: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(
        f"{value.sport}:{value.requested_date.isoformat()}" for value in values
    )


def _optional_datetime_text(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _coverage_gate(
    *,
    drawings: int,
    total: CoverageMetrics,
    minimum_bookmakers: int,
) -> CoverageGate:
    predicates = (
        CoverageGatePredicate(
            name="minimum_drawings",
            operator=">=",
            threshold=30,
            actual=drawings,
            passed=drawings >= 30,
        ),
        CoverageGatePredicate(
            name="minimum_events",
            operator=">=",
            threshold=450,
            actual=total.target_count,
            passed=total.target_count >= 450,
        ),
        CoverageGatePredicate(
            name="minimum_unique_match_rate",
            operator=">=",
            threshold=0.80,
            actual=total.unique_match_rate,
            passed=total.unique_match_rate >= 0.80,
        ),
        CoverageGatePredicate(
            name="minimum_usable_consensus_rate",
            operator=">=",
            threshold=0.70,
            actual=total.usable_consensus_rate,
            passed=total.usable_consensus_rate >= 0.70,
        ),
        CoverageGatePredicate(
            name="zero_ambiguous_matches",
            operator="==",
            threshold=0,
            actual=total.ambiguous_count,
            passed=total.ambiguous_count == 0,
        ),
        CoverageGatePredicate(
            name="complete_explicit_dispositions",
            operator="==",
            threshold=total.target_count,
            actual=total.explicit_dispositions,
            passed=total.explicit_dispositions == total.target_count,
        ),
    )
    reasons: list[str] = []
    if not predicates[0].passed:
        reasons.append("fewer than 30 drawings")
    if not predicates[1].passed:
        reasons.append("fewer than 450 events")
    pending = bool(reasons)
    if not pending:
        if not predicates[2].passed:
            reasons.append("unique match rate below 80%")
        if not predicates[3].passed:
            reasons.append("consensus coverage below 70%")
        if not predicates[4].passed:
            reasons.append("ambiguous match consumed")
        if not predicates[5].passed:
            reasons.append("silent event loss")
    return CoverageGate(
        decision="PENDING" if pending else "STOP" if reasons else "GO",
        reasons=tuple(reasons),
        drawings=drawings,
        events=total.target_count,
        unique_match_rate=total.unique_match_rate,
        consensus_rate=total.usable_consensus_rate,
        ambiguous_matches=total.ambiguous_count,
        explicit_dispositions=total.explicit_dispositions,
        operational_failures=total.provider_error_count,
        predicates=predicates,
    )


def _fallback_counts(rows: tuple[CoverageDisposition, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        if row.fallback_reason:
            counts[row.fallback_reason] += 1
    return counts


def _is_explicit_disposition(row: CoverageDisposition) -> bool:
    if row.fallback_reason == "silent event loss":
        return False
    return row.probability_source == EXTERNAL_CONSENSUS or (
        row.probability_source == TOTOBRIEF_BK_FALLBACK and bool(row.fallback_reason)
    )


def _bookmaker_coverage_count(
    rows: tuple[CoverageDisposition, ...],
    minimum: int,
) -> int:
    return sum(
        row.match_status == "matched" and row.eligible_bookmaker_count >= minimum
        for row in rows
    )


def _usable_consensus_count(
    rows: tuple[CoverageDisposition, ...],
    minimum: int,
) -> int:
    return sum(
        row.probability_source == EXTERNAL_CONSENSUS
        and row.eligible_bookmaker_count >= minimum
        for row in rows
    )


def _normalized_reason(reason: str | None) -> str:
    if not reason:
        return ""
    value = reason.strip()
    for prefix in (
        "provider schedule failure",
        "provider odds failure",
    ):
        if value.startswith(prefix):
            return prefix
    return value


def _is_stale(reason: str) -> bool:
    return bool(_reason_components(reason) & _STALE_REASONS)


def _is_semantic(reason: str) -> bool:
    return bool(_reason_components(reason) & _SEMANTIC_REASONS)


def _is_incomplete_market(reason: str) -> bool:
    return bool(_reason_components(reason) & _INCOMPLETE_MARKET_REASONS)


def _reason_components(reason: str) -> frozenset[str]:
    match = _CONSENSUS_FALLBACK_PATTERN.fullmatch(reason)
    if match is None or match.group("rejections") is None:
        return frozenset({reason})
    return frozenset(match.group("rejections").split(", "))


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _percentile(values: tuple[int, ...], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int((len(ordered) - 1) * percentile)
    return float(ordered[index])
