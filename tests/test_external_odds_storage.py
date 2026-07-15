from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    ExternalBookmakerQuote,
    ExternalCollectionRun,
    ExternalEventDisposition,
)
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import (
    ProviderEvent,
    ProviderMarket,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.storage import (
    load_latest_complete_collections,
    save_collection,
)


def aware_now() -> datetime:
    return datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def target_drawing(*, fetched_at: datetime | None = None) -> TargetDrawing:
    now = aware_now()
    events = tuple(
        TargetEvent(
            drawing_id=9000,
            drawing_number=5000,
            event_id=10_000 + order,
            event_order=order,
            sport="football",
            championship="League",
            starts_at=now + timedelta(hours=6, minutes=order),
            deadline=now + timedelta(hours=5, minutes=55),
            home_team=f"Home {order}",
            away_team=f"Away {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.5, 0.25, 0.25),
        )
        for order in range(15)
    )
    return TargetDrawing(
        drawing_id=9000,
        drawing_number=5000,
        deadline=now + timedelta(hours=5, minutes=55),
        fetched_at=fetched_at or now,
        events=events,
    )


class CompleteProvider:
    provider_name = "api-sports"

    def __init__(
        self,
        *,
        schedule_hash_suffix: str = "",
        market_hash_suffix: str = "",
    ) -> None:
        self.requests_made = 0
        self.cache_hits = 0
        self.schedule_hash_suffix = schedule_hash_suffix
        self.market_hash_suffix = market_hash_suffix
        self._quota_state = QuotaState(
            daily_limit=100,
            daily_remaining=88,
            minute_limit=10,
            minute_remaining=8,
        )

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        assert sport == "football"
        assert dates == (aware_now().date(),)
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"provider-{order}",
                sport="football",
                league="League",
                starts_at=aware_now() + timedelta(hours=6, minutes=order),
                home_team=f"Home {order}",
                away_team=f"Away {order}",
                fetched_at=aware_now(),
                payload_hash=f"schedule-hash-{order}{self.schedule_hash_suffix}",
            )
            for order in range(15)
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        order = int(provider_event_id.split("-")[-1])
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name="Match Winner",
                updated_at=aware_now() - timedelta(hours=index),
                fetched_at=aware_now(),
                payload_hash=(
                    f"market-hash-{order}-{index}{self.market_hash_suffix}"
                ),
                home_price=2.0 + index / 10.0,
                draw_price=4.0 + index / 10.0,
                away_price=4.5 + index / 10.0,
            )
            for index in range(1, 4)
        )


class ReversedProvider(CompleteProvider):
    def fetch_event_markets(self, sport, provider_event_id):
        return tuple(reversed(super().fetch_event_markets(sport, provider_event_id)))


class DuplicateMarketProvider(CompleteProvider):
    def fetch_event_markets(self, sport, provider_event_id):
        markets = super().fetch_event_markets(sport, provider_event_id)
        duplicate = replace(
            markets[0],
            payload_hash=f"{markets[0].payload_hash}-duplicate",
            home_price=markets[0].home_price + 0.5,
        )
        return (duplicate, *reversed(markets))


class ReversedDuplicateMarketProvider(DuplicateMarketProvider):
    def fetch_event_markets(self, sport, provider_event_id):
        return tuple(reversed(super().fetch_event_markets(sport, provider_event_id)))


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def test_collection_persists_exactly_fifteen_dispositions(session_factory):
    result = build_external_collection(target_drawing(), CompleteProvider(), aliases={})

    save_collection(session_factory, result)
    stored = load_latest_complete_collections(session_factory, last=1)

    assert len(stored) == 1
    assert stored[0].status == "complete"
    assert stored[0].event_count == 15
    assert stored[0].requests_made == 16
    assert stored[0].cache_hits == 0
    assert stored[0].target_fetched_at == aware_now().isoformat()
    assert stored[0].daily_limit == 100
    assert stored[0].daily_remaining == 88
    assert stored[0].minute_remaining == 8
    assert len(stored[0].events) == 15
    assert tuple(row.event_order for row in stored[0].events) == tuple(range(15))
    assert all(
        row.probability_source == "external_consensus" for row in stored[0].events
    )
    assert sum(len(row.bookmaker_quotes) for row in stored[0].events) == 45


def test_same_canonical_inputs_are_idempotent(session_factory):
    result = build_external_collection(target_drawing(), CompleteProvider(), aliases={})

    save_collection(session_factory, result)
    save_collection(session_factory, result)

    with session_factory() as session:
        run_count = session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        )
        assert run_count == 1
        assert session.scalar(select(func.count(ExternalEventDisposition.id))) == 15
        assert session.scalar(select(func.count(ExternalBookmakerQuote.id))) == 45


def test_quote_order_is_canonical_for_identity_comparison_and_storage(
    session_factory,
):
    canonical = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
    )
    provider_reversed = build_external_collection(
        target_drawing(),
        ReversedProvider(),
        aliases={},
    )

    assert provider_reversed == canonical
    manually_reversed = replace(
        canonical,
        events=(
            replace(
                canonical.events[0],
                bookmaker_quotes=tuple(
                    reversed(canonical.events[0].bookmaker_quotes)
                ),
            ),
            *canonical.events[1:],
        ),
    )
    save_collection(session_factory, canonical)
    save_collection(session_factory, manually_reversed)

    stored = load_latest_complete_collections(session_factory, last=1)
    assert stored == (canonical,)


def test_fetched_at_is_part_of_collection_identity(session_factory):
    first = build_external_collection(
        target_drawing(fetched_at=aware_now()),
        CompleteProvider(),
        aliases={},
    )
    second = build_external_collection(
        target_drawing(fetched_at=aware_now() + timedelta(seconds=1)),
        CompleteProvider(),
        aliases={},
    )

    save_collection(session_factory, first)
    save_collection(session_factory, second)

    assert first.collection_id != second.collection_id
    with session_factory() as session:
        run_count = session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        )
        assert run_count == 2


def test_provider_provenance_round_trips_and_binds_collection_identity(
    session_factory,
):
    baseline = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
    )
    changed_event = build_external_collection(
        target_drawing(),
        CompleteProvider(schedule_hash_suffix="-changed"),
        aliases={},
    )
    changed_market = build_external_collection(
        target_drawing(),
        CompleteProvider(market_hash_suffix="-changed"),
        aliases={},
    )

    assert len(
        {
            baseline.collection_id,
            changed_event.collection_id,
            changed_market.collection_id,
        }
    ) == 3

    save_collection(session_factory, baseline)
    stored = load_latest_complete_collections(session_factory, last=1)[0]
    event = stored.events[0]
    quote = event.bookmaker_quotes[0]
    assert event.match_candidate_ids == ("provider-0",)
    assert event.match_reason == "unique exact match"
    assert event.provider_event_fetched_at == aware_now().isoformat()
    assert event.provider_event_payload_hash == "schedule-hash-0"
    assert quote.fetched_at == aware_now().isoformat()
    assert quote.payload_hash == "market-hash-0-1"
    assert stored == baseline


def test_duplicate_bookmaker_market_is_coalesced_with_aggregate_provenance(
    session_factory,
):
    result = build_external_collection(
        target_drawing(),
        DuplicateMarketProvider(),
        aliases={},
    )
    reordered = build_external_collection(
        target_drawing(),
        ReversedDuplicateMarketProvider(),
        aliases={},
    )

    assert reordered == result
    event = result.events[0]
    assert event.probability_source == "totobrief_bk_fallback"
    assert event.eligible_bookmaker_count == 2
    assert "duplicate bookmaker market" in event.fallback_reason
    assert len(event.bookmaker_quotes) == 3
    duplicate = event.bookmaker_quotes[0]
    assert duplicate.bookmaker_id == "book-1"
    assert duplicate.market_name == "Match Winner"
    assert duplicate.eligible == 0
    assert duplicate.rejection_reason == "duplicate bookmaker market"
    assert duplicate.source_count == 2
    assert tuple(
        source.payload_hash for source in duplicate.source_provenance
    ) == ("market-hash-0-1", "market-hash-0-1-duplicate")
    assert all(
        source.fetched_at == aware_now().isoformat()
        for source in duplicate.source_provenance
    )
    assert len(duplicate.payload_hash) == 64

    save_collection(session_factory, result)
    stored = load_latest_complete_collections(session_factory, last=1)
    assert stored == (result,)
    with session_factory() as session:
        assert session.scalar(select(func.count(ExternalEventDisposition.id))) == 15
        assert session.scalar(select(func.count(ExternalBookmakerQuote.id))) == 45


def test_conflicting_existing_collection_id_is_rejected(session_factory):
    result = build_external_collection(target_drawing(), CompleteProvider(), aliases={})
    save_collection(session_factory, result)

    tampered = result.__class__(
        **{
            **result.__dict__,
            "events": (
                result.events[0].__class__(
                    **{
                        **result.events[0].__dict__,
                        "probability_1": result.events[0].probability_1 + 0.01,
                    }
                ),
                *result.events[1:],
            ),
        }
    )

    with pytest.raises(ValueError, match="conflicting collection content"):
        save_collection(session_factory, tampered)


def test_save_collection_rolls_back_partial_failure(session_factory, monkeypatch):
    result = build_external_collection(target_drawing(), CompleteProvider(), aliases={})

    def fail_on_quote(*args, **kwargs):
        raise RuntimeError("injected quote failure")

    monkeypatch.setattr(
        "toto_ai.external_odds.storage._bookmaker_quote_row",
        fail_on_quote,
    )

    with pytest.raises(RuntimeError, match="injected quote failure"):
        save_collection(session_factory, result)

    with session_factory() as session:
        run_count = session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        )
        assert run_count == 0
        assert session.scalar(select(func.count(ExternalEventDisposition.id))) == 0
        assert session.scalar(select(func.count(ExternalBookmakerQuote.id))) == 0
