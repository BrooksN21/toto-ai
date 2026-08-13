from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, literal_column, select

from toto_ai.db.models import (
    ExternalBookmakerQuote,
    ExternalCollectionRun,
    ExternalEventDisposition,
)
from toto_ai.external_odds.collection import (
    ExternalBookmakerQuoteRecord,
    ExternalCollectionSnapshot,
    ExternalEventDispositionRecord,
    ExternalMarketProvenanceRecord,
    PinnedRevalidationEvent,
    PinnedRevalidationSummary,
    ScheduleDateResult,
)
from toto_ai.external_odds.eligibility import (
    DrawingEligibility,
    EffectiveEventStart,
    classify_drawing_eligibility,
)


def save_collection(
    session_factory: Any,
    collection: ExternalCollectionSnapshot,
) -> None:
    canonical = _canonical_snapshot(collection)
    _validate_complete_collection(canonical)
    _validate_collection_provenance(canonical)
    expected = asdict(canonical)
    with session_factory.begin() as session:
        existing = session.get(ExternalCollectionRun, canonical.collection_id)
        if existing is not None:
            stored = _load_collection_by_id(session, canonical.collection_id)
            if _canonical_collection(stored) != expected:
                raise ValueError("conflicting collection content")
            return

        session.add(_collection_run_row(canonical))
        for event in canonical.events:
            session.add(_event_disposition_row(canonical.collection_id, event))
            for quote in _canonical_quotes(event.bookmaker_quotes):
                session.add(
                    _bookmaker_quote_row(
                        canonical.collection_id,
                        event.event_order,
                        quote,
                    )
                )


def load_latest_complete_collections(
    session_factory: Any,
    *,
    last: int,
    provider: str | None = None,
) -> tuple[ExternalCollectionSnapshot, ...]:
    if not isinstance(last, int) or isinstance(last, bool) or last <= 0:
        raise ValueError("last must be a positive integer")
    loaded: list[ExternalCollectionSnapshot] = []
    with session_factory() as session:
        query = select(ExternalCollectionRun).where(
            ExternalCollectionRun.status == "complete"
        )
        if provider is not None:
            if not isinstance(provider, str) or not provider.strip():
                raise ValueError("provider must be non-empty or None")
            query = query.where(ExternalCollectionRun.provider == provider)
        runs = session.scalars(
            query
            .order_by(
                ExternalCollectionRun.fetched_at.desc(),
                literal_column("rowid").desc(),
                ExternalCollectionRun.collection_id.desc(),
            )
        ).all()
        for run in runs:
            collection = _load_collection_by_id(session, run.collection_id)
            if collection.event_count == 15 and len(collection.events) == 15:
                loaded.append(collection)
            if len(loaded) == last:
                break
    return tuple(loaded)


def load_current_drawing_eligibility(
    session_factory: Any,
    drawing_id: int,
    target_fingerprint: str,
) -> DrawingEligibility | None:
    if (
        not isinstance(drawing_id, int)
        or isinstance(drawing_id, bool)
        or drawing_id <= 0
    ):
        raise ValueError("drawing_id must be a positive integer")
    if not isinstance(target_fingerprint, str) or not target_fingerprint:
        raise ValueError("target_fingerprint must be a non-empty string")

    with session_factory() as session:
        runs = session.scalars(
            select(ExternalCollectionRun)
            .where(
                ExternalCollectionRun.drawing_id == drawing_id,
                ExternalCollectionRun.target_fingerprint == target_fingerprint,
                ExternalCollectionRun.status == "complete",
                ExternalCollectionRun.event_count == 15,
            )
            .order_by(
                ExternalCollectionRun.fetched_at.desc(),
                literal_column("rowid").desc(),
                ExternalCollectionRun.collection_id.desc(),
            )
        ).all()
        for run in runs:
            collection = _load_collection_by_id(session, run.collection_id)
            if len(collection.events) == 15:
                return collection.eligibility
    return None


def _validate_complete_collection(collection: ExternalCollectionSnapshot) -> None:
    if collection.event_count != 15 or len(collection.events) != 15:
        raise ValueError("collection must contain exactly 15 events")
    if tuple(event.event_order for event in collection.events) != tuple(range(15)):
        raise ValueError("collection event orders must be 0 through 14")
    if collection.status != "complete":
        raise ValueError("only complete collections can be saved")


def _load_collection_by_id(
    session: Any,
    collection_id: str,
) -> ExternalCollectionSnapshot:
    run = session.get(ExternalCollectionRun, collection_id)
    if run is None:
        raise ValueError("collection does not exist")
    legacy = run.target_fingerprint is None
    events = tuple(
        _event_record_from_row(event, _quote_records_for_event(session, event))
        for event in session.scalars(
            select(ExternalEventDisposition)
            .where(ExternalEventDisposition.collection_id == collection_id)
            .order_by(ExternalEventDisposition.event_order)
        )
    )
    collection = ExternalCollectionSnapshot(
        collection_id=run.collection_id,
        drawing_id=run.drawing_id,
        drawing_number=run.drawing_number,
        provider=run.provider,
        fetched_at=run.fetched_at,
        target_fetched_at=run.target_fetched_at,
        deadline=run.deadline,
        event_count=run.event_count,
        requests_made=run.requests_made,
        cache_hits=run.cache_hits,
        daily_limit=run.daily_limit,
        daily_remaining=run.daily_remaining,
        minute_remaining=run.minute_remaining,
        status=run.status,
        events=events,
        target_fingerprint=run.target_fingerprint or "",
        missing_start_horizon_days=_horizon_from_row(run, legacy),
        requested_schedule_dates=_schedule_dates_from_json(
            run.requested_schedule_dates,
            "requested_schedule_dates",
            allow_missing=legacy,
        ),
        successful_schedule_dates=_schedule_dates_from_json(
            run.successful_schedule_dates,
            "successful_schedule_dates",
            allow_missing=legacy,
        ),
        failed_schedule_dates=_schedule_dates_from_json(
            run.failed_schedule_dates,
            "failed_schedule_dates",
            allow_missing=legacy,
        ),
        eligibility=_eligibility_from_row(run),
        pinned_revalidation=_pinned_revalidation_from_json(
            run.pinned_revalidation_summary
        ),
    )
    canonical = _canonical_snapshot(collection)
    if canonical.target_fingerprint:
        _validate_collection_provenance(canonical)
    return canonical


def _quote_records_for_event(
    session: Any,
    event: ExternalEventDisposition,
) -> tuple[ExternalBookmakerQuoteRecord, ...]:
    rows = session.scalars(
        select(ExternalBookmakerQuote)
        .where(
            ExternalBookmakerQuote.collection_id == event.collection_id,
            ExternalBookmakerQuote.event_order == event.event_order,
        )
        .order_by(
            ExternalBookmakerQuote.bookmaker_id,
            ExternalBookmakerQuote.market_name,
        )
    ).all()
    return _canonical_quotes(tuple(_quote_record_from_row(row) for row in rows))


def _collection_run_row(
    collection: ExternalCollectionSnapshot,
) -> ExternalCollectionRun:
    eligibility = collection.eligibility
    return ExternalCollectionRun(
        collection_id=collection.collection_id,
        drawing_id=collection.drawing_id,
        drawing_number=collection.drawing_number,
        provider=collection.provider,
        fetched_at=collection.fetched_at,
        target_fetched_at=collection.target_fetched_at,
        deadline=collection.deadline,
        event_count=collection.event_count,
        requests_made=collection.requests_made,
        cache_hits=collection.cache_hits,
        daily_limit=collection.daily_limit,
        daily_remaining=collection.daily_remaining,
        minute_remaining=collection.minute_remaining,
        status=collection.status,
        target_fingerprint=collection.target_fingerprint,
        missing_start_horizon_days=collection.missing_start_horizon_days,
        requested_schedule_dates=_schedule_dates_json(
            collection.requested_schedule_dates
        ),
        successful_schedule_dates=_schedule_dates_json(
            collection.successful_schedule_dates
        ),
        failed_schedule_dates=_schedule_dates_json(
            collection.failed_schedule_dates
        ),
        eligibility_status=eligibility.status,
        eligibility_earliest_start=_optional_datetime_text(
            eligibility.earliest_start
        ),
        eligibility_latest_start=_optional_datetime_text(eligibility.latest_start),
        eligibility_span_days=eligibility.span_days,
        eligibility_missing_event_orders=json.dumps(
            eligibility.missing_event_orders,
            separators=(",", ":"),
        ),
        eligibility_totobrief_count=eligibility.totobrief_count,
        eligibility_provider_count=eligibility.provider_count,
        pinned_revalidation_summary=(
            None
            if collection.pinned_revalidation is None
            else json.dumps(
                asdict(collection.pinned_revalidation),
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
    )


def _event_disposition_row(
    collection_id: str,
    event: ExternalEventDispositionRecord,
) -> ExternalEventDisposition:
    return ExternalEventDisposition(
        collection_id=collection_id,
        drawing_id=event.drawing_id,
        event_order=event.event_order,
        target_event_id=event.target_event_id,
        sport=event.sport,
        championship=event.championship,
        starts_at=event.starts_at,
        home_team=event.home_team,
        away_team=event.away_team,
        home_team_en=event.home_team_en,
        away_team_en=event.away_team_en,
        match_status=event.match_status,
        match_orientation=event.match_orientation,
        provider_event_id=event.provider_event_id,
        provider_event_fetched_at=event.provider_event_fetched_at,
        provider_event_payload_hash=event.provider_event_payload_hash,
        matcher_version=event.matcher_version,
        match_candidate_ids=json.dumps(
            event.match_candidate_ids,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        match_reason=event.match_reason,
        probability_source=event.probability_source,
        probability_1=event.probability_1,
        probability_x=event.probability_x,
        probability_2=event.probability_2,
        eligible_bookmaker_count=event.eligible_bookmaker_count,
        odds_age_hours=event.odds_age_hours,
        fallback_reason=event.fallback_reason,
        payload_hash=event.payload_hash,
        provider_starts_at=event.provider_starts_at,
        effective_starts_at=event.effective_starts_at,
        effective_start_source=event.effective_start_source,
    )


def _bookmaker_quote_row(
    collection_id: str,
    event_order: int,
    quote: ExternalBookmakerQuoteRecord,
) -> ExternalBookmakerQuote:
    return ExternalBookmakerQuote(
        collection_id=collection_id,
        event_order=event_order,
        bookmaker_id=quote.bookmaker_id,
        market_name=quote.market_name,
        updated_at=quote.updated_at,
        fetched_at=quote.fetched_at,
        payload_hash=quote.payload_hash,
        home_price=quote.home_price,
        draw_price=quote.draw_price,
        away_price=quote.away_price,
        eligible=quote.eligible,
        rejection_reason=quote.rejection_reason,
        source_count=quote.source_count,
        source_provenance=json.dumps(
            tuple(asdict(source) for source in quote.source_provenance),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def _event_record_from_row(
    row: ExternalEventDisposition,
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
) -> ExternalEventDispositionRecord:
    return ExternalEventDispositionRecord(
        drawing_id=row.drawing_id,
        event_order=row.event_order,
        target_event_id=row.target_event_id,
        sport=row.sport,
        championship=row.championship,
        starts_at=row.starts_at,
        home_team=row.home_team,
        away_team=row.away_team,
        home_team_en=row.home_team_en,
        away_team_en=row.away_team_en,
        match_status=row.match_status,
        match_orientation=row.match_orientation,
        provider_event_id=row.provider_event_id,
        provider_event_fetched_at=row.provider_event_fetched_at,
        provider_event_payload_hash=row.provider_event_payload_hash,
        matcher_version=row.matcher_version,
        match_candidate_ids=tuple(json.loads(row.match_candidate_ids)),
        match_reason=row.match_reason,
        probability_source=row.probability_source,
        probability_1=row.probability_1,
        probability_x=row.probability_x,
        probability_2=row.probability_2,
        eligible_bookmaker_count=row.eligible_bookmaker_count,
        odds_age_hours=row.odds_age_hours,
        fallback_reason=row.fallback_reason,
        payload_hash=row.payload_hash,
        bookmaker_quotes=quotes,
        provider_starts_at=row.provider_starts_at,
        effective_starts_at=row.effective_starts_at,
        effective_start_source=row.effective_start_source or "unresolved",
    )


def _quote_record_from_row(row: ExternalBookmakerQuote) -> ExternalBookmakerQuoteRecord:
    return ExternalBookmakerQuoteRecord(
        bookmaker_id=row.bookmaker_id,
        market_name=row.market_name,
        updated_at=row.updated_at,
        fetched_at=row.fetched_at,
        payload_hash=row.payload_hash,
        home_price=row.home_price,
        draw_price=row.draw_price,
        away_price=row.away_price,
        eligible=row.eligible,
        rejection_reason=row.rejection_reason,
        source_count=row.source_count,
        source_provenance=tuple(
            ExternalMarketProvenanceRecord(**source)
            for source in json.loads(row.source_provenance)
        ),
    )


def _canonical_collection(collection: ExternalCollectionSnapshot) -> dict[str, object]:
    return asdict(_canonical_snapshot(collection))


def _canonical_snapshot(
    collection: ExternalCollectionSnapshot,
) -> ExternalCollectionSnapshot:
    requested = _canonical_schedule_dates(
        collection.requested_schedule_dates,
        "requested_schedule_dates",
    )
    successful = _canonical_schedule_dates(
        collection.successful_schedule_dates,
        "successful_schedule_dates",
    )
    failed = _canonical_schedule_dates(
        collection.failed_schedule_dates,
        "failed_schedule_dates",
    )
    if successful != tuple(item for item in requested if item.error is None):
        raise ValueError("successful schedule dates are inconsistent with requested")
    if failed != tuple(item for item in requested if item.error is not None):
        raise ValueError("failed schedule dates are inconsistent with requested")
    return replace(
        collection,
        requested_schedule_dates=requested,
        successful_schedule_dates=successful,
        failed_schedule_dates=failed,
        events=tuple(
            replace(
                event,
                bookmaker_quotes=_canonical_quotes(event.bookmaker_quotes),
            )
            for event in collection.events
        ),
    )


def _canonical_schedule_dates(
    values: tuple[ScheduleDateResult, ...],
    field_name: str,
) -> tuple[ScheduleDateResult, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    canonical: list[ScheduleDateResult] = []
    seen: set[tuple[str, date]] = set()
    for item in values:
        if not isinstance(item, ScheduleDateResult):
            raise ValueError(f"{field_name} must contain ScheduleDateResult records")
        if item.sport not in {"football", "hockey"}:
            raise ValueError(f"{field_name} contains an unsupported sport")
        if not isinstance(item.requested_date, date) or isinstance(
            item.requested_date, datetime
        ):
            raise ValueError(f"{field_name} contains an invalid requested date")
        if item.error is not None and (
            not isinstance(item.error, str) or not item.error
        ):
            raise ValueError(f"{field_name} contains an invalid error")
        key = (item.sport, item.requested_date)
        if key in seen:
            raise ValueError(f"{field_name} contains duplicate sport/date entries")
        seen.add(key)
        canonical.append(replace(item, events=()))
    return tuple(
        sorted(canonical, key=lambda item: (item.sport, item.requested_date))
    )


def _schedule_dates_json(values: tuple[ScheduleDateResult, ...]) -> str:
    payload = tuple(
        {
            "sport": item.sport,
            "requested_date": item.requested_date.isoformat(),
            "error": item.error,
        }
        for item in values
    )
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _schedule_dates_from_json(
    value: str | None,
    field_name: str,
    *,
    allow_missing: bool,
) -> tuple[ScheduleDateResult, ...]:
    if value is None:
        if allow_missing:
            return ()
        raise ValueError(f"invalid {field_name} JSON")
    try:
        payload = json.loads(value)
        if not isinstance(payload, list):
            raise ValueError("schedule payload must be a list")
        records = []
        for item in payload:
            if not isinstance(item, dict) or set(item) != {
                "sport",
                "requested_date",
                "error",
            }:
                raise ValueError("schedule entry has invalid fields")
            requested_date_text = item["requested_date"]
            if not isinstance(requested_date_text, str):
                raise ValueError("requested date must be text")
            requested_date = date.fromisoformat(requested_date_text)
            if requested_date.isoformat() != requested_date_text:
                raise ValueError("requested date must be canonical ISO format")
            records.append(
                ScheduleDateResult(
                    sport=item["sport"],
                    requested_date=requested_date,
                    events=(),
                    error=item["error"],
                )
            )
        return _canonical_schedule_dates(tuple(records), field_name)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {field_name} JSON") from error


def _eligibility_from_row(run: ExternalCollectionRun) -> DrawingEligibility:
    if run.target_fingerprint is None:
        return DrawingEligibility(
            status="unknown",
            earliest_start=None,
            latest_start=None,
            span_days=0,
            missing_event_orders=tuple(range(15)),
            totobrief_count=0,
            provider_count=0,
        )
    if run.eligibility_status is None:
        raise ValueError("eligibility_status must be present")
    return DrawingEligibility(
        status=run.eligibility_status,
        earliest_start=_datetime_from_text(
            run.eligibility_earliest_start,
            "eligibility_earliest_start",
        ),
        latest_start=_datetime_from_text(
            run.eligibility_latest_start,
            "eligibility_latest_start",
        ),
        span_days=_required_integer(
            run.eligibility_span_days,
            "eligibility_span_days",
        ),
        missing_event_orders=_integer_tuple_from_json(
            run.eligibility_missing_event_orders,
            "eligibility_missing_event_orders",
        ),
        totobrief_count=_required_integer(
            run.eligibility_totobrief_count,
            "eligibility_totobrief_count",
        ),
        provider_count=_required_integer(
            run.eligibility_provider_count,
            "eligibility_provider_count",
        ),
    )


def _integer_tuple_from_json(value: str | None, field_name: str) -> tuple[int, ...]:
    try:
        payload = json.loads(value) if value is not None else None
        if not isinstance(payload, list) or any(
            not isinstance(item, int) or isinstance(item, bool) for item in payload
        ):
            raise ValueError("integer tuple payload is invalid")
        return tuple(payload)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {field_name} JSON") from error


def _pinned_revalidation_from_json(
    value: str | None,
) -> PinnedRevalidationSummary | None:
    if value is None:
        return None
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("summary must be an object")
        event_payloads = payload.pop("events")
        if not isinstance(event_payloads, list):
            raise ValueError("events must be a list")
        events = tuple(
            PinnedRevalidationEvent(**item)
            for item in event_payloads
            if isinstance(item, dict)
        )
        if len(events) != len(event_payloads):
            raise ValueError("events must contain objects")
        tuple_fields = (
            "missing_event_orders",
            "provider_failure_event_orders",
            "stale_event_orders",
            "date_failure_event_orders",
            "identity_failure_event_orders",
            "start_time_failure_event_orders",
            "failed_schedule_dates",
        )
        for field in tuple_fields:
            items = payload[field]
            if not isinstance(items, list):
                raise ValueError(f"{field} must be a list")
            payload[field] = tuple(items)
        return PinnedRevalidationSummary(**payload, events=events)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid pinned_revalidation_summary JSON") from error


def _required_integer(value: int | None, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _horizon_from_row(run: ExternalCollectionRun, legacy: bool) -> int:
    if run.missing_start_horizon_days is None:
        if legacy:
            return 2
        raise ValueError("missing_start_horizon_days must be present")
    return run.missing_start_horizon_days


def _optional_datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _datetime_from_text(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be ISO datetime text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be ISO datetime text") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _validate_collection_provenance(
    collection: ExternalCollectionSnapshot,
) -> None:
    if (
        not isinstance(collection.missing_start_horizon_days, int)
        or isinstance(collection.missing_start_horizon_days, bool)
        or not 1 <= collection.missing_start_horizon_days <= 5
    ):
        raise ValueError("missing_start_horizon_days must be from 1 through 5")
    if not isinstance(collection.target_fingerprint, str):
        raise ValueError("target_fingerprint must be text")
    if not collection.target_fingerprint:
        if collection.eligibility.status != "unknown":
            raise ValueError("collection without target fingerprint must be unknown")
        return

    _validate_pinned_revalidation(collection)

    starts = []
    for event in collection.events:
        target_start = _event_datetime(event.starts_at, "starts_at")
        provider_start = _event_datetime(
            event.provider_starts_at,
            "provider_starts_at",
        )
        effective_start = _event_datetime(
            event.effective_starts_at,
            "effective_starts_at",
        )
        source = event.effective_start_source
        if source == "totobrief":
            if target_start is None or effective_start != target_start:
                raise ValueError("totobrief effective start is inconsistent")
        elif source == "provider":
            if (
                target_start is not None
                or provider_start is None
                or effective_start != provider_start
            ):
                raise ValueError("provider effective start is inconsistent")
        elif source == "unresolved":
            if target_start is not None or provider_start is not None:
                raise ValueError("unresolved effective start is inconsistent")
        starts.append(
            EffectiveEventStart(
                event_order=event.event_order,
                starts_at=effective_start,
                source=source,
            )
        )
    derived = classify_drawing_eligibility(tuple(starts))
    if derived != collection.eligibility:
        raise ValueError("eligibility does not match event timing")


def _validate_pinned_revalidation(
    collection: ExternalCollectionSnapshot,
) -> None:
    summary = collection.pinned_revalidation
    if summary is None:
        return
    if summary.expected_count != 15 or len(summary.events) != 15:
        raise ValueError("pinned revalidation must describe exactly 15 events")
    if tuple(item.event_order for item in summary.events) != tuple(range(15)):
        raise ValueError("pinned revalidation event orders must be 0 through 14")
    matched = tuple(
        item.event_order for item in summary.events if item.status == "matched"
    )
    if summary.matched_count != len(matched):
        raise ValueError("pinned revalidation matched count is inconsistent")
    if summary.ready_for_play != (
        summary.matched_count == 15
        and summary.schedule_fresh
        and summary.provider_checks_passed
        and summary.fixture_checks_passed
        and summary.team_checks_passed
        and summary.orientation_checks_passed
        and summary.start_time_checks_passed
        and summary.required_dates_complete
    ):
        raise ValueError("pinned revalidation ready status is inconsistent")


def _event_datetime(value: str | None, field_name: str) -> datetime | None:
    if value in {None, ""}:
        return None
    return _datetime_from_text(value, field_name)


def _canonical_quotes(
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
) -> tuple[ExternalBookmakerQuoteRecord, ...]:
    return tuple(
        sorted(
            quotes,
            key=lambda quote: (
                quote.bookmaker_id,
                quote.market_name,
                json.dumps(
                    asdict(quote),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )
    )


def count_complete_runs(session_factory: Any) -> int:
    with session_factory() as session:
        return (
            session.scalar(
                select(func.count(ExternalCollectionRun.collection_id)).where(
                    ExternalCollectionRun.status == "complete"
                )
            )
            or 0
        )
