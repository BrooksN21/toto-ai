from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

from sqlalchemy import func, select

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
)


def save_collection(
    session_factory: Any,
    collection: ExternalCollectionSnapshot,
) -> None:
    _validate_complete_collection(collection)
    expected = _canonical_collection(collection)
    with session_factory.begin() as session:
        existing = session.get(ExternalCollectionRun, collection.collection_id)
        if existing is not None:
            stored = _load_collection_by_id(session, collection.collection_id)
            if _canonical_collection(stored) != expected:
                raise ValueError("conflicting collection content")
            return

        session.add(_collection_run_row(collection))
        for event in collection.events:
            session.add(_event_disposition_row(collection.collection_id, event))
            for quote in _canonical_quotes(event.bookmaker_quotes):
                session.add(
                    _bookmaker_quote_row(
                        collection.collection_id,
                        event.event_order,
                        quote,
                    )
                )


def load_latest_complete_collections(
    session_factory: Any,
    *,
    last: int,
) -> tuple[ExternalCollectionSnapshot, ...]:
    if not isinstance(last, int) or isinstance(last, bool) or last <= 0:
        raise ValueError("last must be a positive integer")
    loaded: list[ExternalCollectionSnapshot] = []
    with session_factory() as session:
        runs = session.scalars(
            select(ExternalCollectionRun)
            .where(ExternalCollectionRun.status == "complete")
            .order_by(
                ExternalCollectionRun.fetched_at.desc(),
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
    events = tuple(
        _event_record_from_row(event, _quote_records_for_event(session, event))
        for event in session.scalars(
            select(ExternalEventDisposition)
            .where(ExternalEventDisposition.collection_id == collection_id)
            .order_by(ExternalEventDisposition.event_order)
        )
    )
    return ExternalCollectionSnapshot(
        collection_id=run.collection_id,
        drawing_id=run.drawing_id,
        drawing_number=run.drawing_number,
        provider=run.provider,
        fetched_at=run.fetched_at,
        deadline=run.deadline,
        event_count=run.event_count,
        requests_made=run.requests_made,
        daily_limit=run.daily_limit,
        daily_remaining=run.daily_remaining,
        minute_remaining=run.minute_remaining,
        status=run.status,
        events=events,
    )


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
    return ExternalCollectionRun(
        collection_id=collection.collection_id,
        drawing_id=collection.drawing_id,
        drawing_number=collection.drawing_number,
        provider=collection.provider,
        fetched_at=collection.fetched_at,
        deadline=collection.deadline,
        event_count=collection.event_count,
        requests_made=collection.requests_made,
        daily_limit=collection.daily_limit,
        daily_remaining=collection.daily_remaining,
        minute_remaining=collection.minute_remaining,
        status=collection.status,
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
    normalized = replace(
        collection,
        events=tuple(
            replace(
                event,
                bookmaker_quotes=_canonical_quotes(event.bookmaker_quotes),
            )
            for event in collection.events
        ),
    )
    return asdict(normalized)


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
