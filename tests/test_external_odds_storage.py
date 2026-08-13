from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    ExternalBookmakerQuote,
    ExternalCollectionRun,
    ExternalEventDisposition,
)
from toto_ai.db.session import init_db, open_readonly_db
from toto_ai.external_odds import storage
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import (
    ProviderEvent,
    ProviderMarket,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.storage import (
    _canonical_collection,
    load_latest_complete_collections,
    save_collection,
)

RUN_PROVENANCE_COLUMNS = {
    "target_fingerprint",
    "missing_start_horizon_days",
    "requested_schedule_dates",
    "successful_schedule_dates",
    "failed_schedule_dates",
    "eligibility_status",
    "eligibility_earliest_start",
    "eligibility_latest_start",
    "eligibility_span_days",
    "eligibility_missing_event_orders",
    "eligibility_totobrief_count",
    "eligibility_provider_count",
    "quota_limit",
    "quota_remaining",
    "quota_used",
    "quota_last_cost",
}
EVENT_TIMING_COLUMNS = {
    "provider_starts_at",
    "effective_starts_at",
    "effective_start_source",
    "provider_event_source_endpoint",
    "provider_event_request_fingerprint",
    "target_bk_probability_1",
    "target_bk_probability_x",
    "target_bk_probability_2",
}


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


class TheOddsProvider(CompleteProvider):
    provider_name = "the-odds-api"
    credit_state = type(
        "CreditState",
        (),
        {"limit": 500, "remaining": 487, "used": 13, "last_cost": 1},
    )()

    def fetch_schedule(self, sport, dates):
        return tuple(
            replace(
                event,
                source_endpoint="/v4/sports/soccer_test/events",
                request_fingerprint="schedule-request",
            )
            for event in super().fetch_schedule(sport, dates)
        )

    def fetch_event_markets(self, sport, provider_event_id):
        return tuple(
            replace(
                market,
                market_name="1X2",
                source_endpoint="/v4/sports/soccer_test/odds",
                request_fingerprint="odds-request",
            )
            for market in super().fetch_event_markets(sport, provider_event_id)
        )


class CachedCompleteProvider(CompleteProvider):
    def fetch_schedule(self, sport, dates):
        events = super().fetch_schedule(sport, dates)
        self.requests_made -= 1
        self.cache_hits += 1
        return events

    def fetch_event_markets(self, sport, provider_event_id):
        markets = super().fetch_event_markets(sport, provider_event_id)
        self.requests_made -= 1
        self.cache_hits += 1
        return markets


class ScheduleFailureProvider(CompleteProvider):
    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        raise RuntimeError("provider unavailable")

    def fetch_event_markets(self, sport, provider_event_id):
        raise AssertionError("markets must not be fetched after schedule failure")


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
    assert _canonical_collection(stored[0]) == _canonical_collection(result)
    assert stored[0].target_fingerprint == result.target_fingerprint
    assert stored[0].missing_start_horizon_days == 2
    assert stored[0].requested_schedule_dates[0].events == ()
    assert stored[0].eligibility == result.eligibility
    assert stored[0].events[0].provider_starts_at == (
        aware_now() + timedelta(hours=6)
    ).isoformat()
    assert stored[0].events[0].effective_starts_at == (
        aware_now() + timedelta(hours=6)
    ).isoformat()
    assert stored[0].events[0].effective_start_source == "totobrief"


def test_latest_complete_collections_can_be_filtered_by_provider(session_factory):
    api_sports = build_external_collection(
        target_drawing(), CompleteProvider(), aliases={}
    )
    the_odds_api = replace(
        api_sports,
        collection_id="the-odds-api-collection",
        provider="the-odds-api",
    )
    save_collection(session_factory, api_sports)
    save_collection(session_factory, the_odds_api)

    loaded = load_latest_complete_collections(
        session_factory,
        last=10,
        provider="the-odds-api",
    )

    assert len(loaded) == 1
    assert loaded[0].collection_id == "the-odds-api-collection"
    assert loaded[0].provider == "the-odds-api"


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


def test_failed_schedule_date_provenance_round_trips_canonically(session_factory):
    result = build_external_collection(
        target_drawing(),
        ScheduleFailureProvider(),
        aliases={},
    )

    save_collection(session_factory, result)
    stored = load_latest_complete_collections(session_factory, last=1)[0]

    assert _canonical_collection(stored) == _canonical_collection(result)
    assert stored.successful_schedule_dates == ()
    assert tuple(
        (item.sport, item.requested_date, item.error)
        for item in stored.failed_schedule_dates
    ) == (("football", aware_now().date(), "provider schedule failure"),)
    with session_factory() as session:
        failed_json = session.scalar(
            select(ExternalCollectionRun.failed_schedule_dates).where(
                ExternalCollectionRun.collection_id == result.collection_id
            )
        )
    assert json.loads(failed_json) == [
        {
            "error": "provider schedule failure",
            "requested_date": aware_now().date().isoformat(),
            "sport": "football",
        }
    ]


def test_new_provenance_participates_in_equality_asdict_and_canonicalization():
    collection = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
    )
    changed = replace(
        collection,
        target_fingerprint="different-target-fingerprint",
        events=(
            replace(
                collection.events[0],
                effective_start_source="provider",
            ),
            *collection.events[1:],
        ),
    )

    assert changed != collection
    assert asdict(changed) != asdict(collection)
    assert _canonical_collection(changed) != _canonical_collection(collection)


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
    assert _canonical_collection(stored[0]) == _canonical_collection(canonical)


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


def test_request_and_cache_provenance_are_part_of_collection_identity(
    session_factory,
):
    fetched = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
    )
    cached = build_external_collection(
        target_drawing(),
        CachedCompleteProvider(),
        aliases={},
    )

    assert fetched.requests_made == 16
    assert fetched.cache_hits == 0
    assert cached.requests_made == 0
    assert cached.cache_hits == 16
    assert fetched.collection_id != cached.collection_id

    save_collection(session_factory, fetched)
    save_collection(session_factory, cached)

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
    assert event.match_orientation == "same"
    assert event.provider_event_fetched_at == aware_now().isoformat()
    assert event.provider_event_payload_hash == "schedule-hash-0"
    assert quote.fetched_at == aware_now().isoformat()
    assert quote.payload_hash == "market-hash-0-1"
    assert event.provider_starts_at == (aware_now() + timedelta(hours=6)).isoformat()
    assert event.effective_starts_at == (aware_now() + timedelta(hours=6)).isoformat()
    assert event.effective_start_source == "totobrief"
    assert _canonical_collection(stored) == _canonical_collection(baseline)


def test_the_odds_api_quota_endpoint_and_bk_provenance_round_trip(
    session_factory,
):
    result = build_external_collection(
        target_drawing(),
        TheOddsProvider(),
        aliases={},
    )

    save_collection(session_factory, result)
    stored = load_latest_complete_collections(
        session_factory,
        last=1,
        provider="the-odds-api",
    )[0]

    assert (
        stored.quota_limit,
        stored.quota_remaining,
        stored.quota_used,
        stored.quota_last_cost,
    ) == (500, 487, 13, 1)
    event = stored.events[0]
    assert event.provider_event_source_endpoint.endswith("/events")
    assert event.provider_event_request_fingerprint == "schedule-request"
    assert (
        event.target_bk_probability_1,
        event.target_bk_probability_x,
        event.target_bk_probability_2,
    ) == pytest.approx((0.5, 0.25, 0.25))
    source = event.bookmaker_quotes[0].source_provenance[0]
    assert source.source_endpoint.endswith("/odds")
    assert source.request_fingerprint == "odds-request"
    assert _canonical_collection(stored) == _canonical_collection(result)


def test_schedule_metadata_changes_identity_and_is_append_only(session_factory):
    ordinary = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
        missing_start_horizon_days=2,
    )
    expanded = build_external_collection(
        target_drawing(),
        CompleteProvider(),
        aliases={},
        missing_start_horizon_days=5,
    )

    assert ordinary.collection_id != expanded.collection_id

    save_collection(session_factory, ordinary)
    save_collection(session_factory, expanded)
    save_collection(session_factory, expanded)

    with session_factory() as session:
        assert session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        ) == 2


def test_current_eligibility_lookup_requires_exact_target_fingerprint(
    session_factory,
):
    collection = build_external_collection(
        target_drawing(), CompleteProvider(), aliases={}
    )
    save_collection(session_factory, collection)

    assert storage.load_current_drawing_eligibility(
        session_factory,
        collection.drawing_id,
        collection.target_fingerprint,
    ) == collection.eligibility
    assert (
        storage.load_current_drawing_eligibility(
            session_factory,
            collection.drawing_id,
            "0" * 64,
        )
        is None
    )
    with session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE external_collection_runs SET target_fingerprint = NULL "
                "WHERE collection_id = :collection_id"
            ),
            {"collection_id": collection.collection_id},
        )
    assert (
        storage.load_current_drawing_eligibility(
            session_factory,
            collection.drawing_id,
            collection.target_fingerprint,
        )
        is None
    )
    assert load_latest_complete_collections(session_factory, last=1)[0].eligibility == (
        DrawingEligibility(
            status="unknown",
            earliest_start=None,
            latest_start=None,
            span_days=0,
            missing_event_orders=tuple(range(15)),
            totobrief_count=0,
            provider_count=0,
        )
    )
    assert (
        storage.load_current_drawing_eligibility(
            session_factory,
            collection.drawing_id + 1,
            collection.target_fingerprint,
        )
        is None
    )


def test_save_rejects_event_timing_inconsistent_with_eligibility(session_factory):
    collection = build_external_collection(
        target_drawing(), CompleteProvider(), aliases={}
    )
    inconsistent = replace(
        collection,
        eligibility=DrawingEligibility(
            status="unknown",
            earliest_start=None,
            latest_start=None,
            span_days=0,
            missing_event_orders=tuple(range(15)),
            totobrief_count=0,
            provider_count=0,
        ),
    )

    with pytest.raises(ValueError, match="eligibility.*event timing"):
        save_collection(session_factory, inconsistent)


def test_load_rejects_malformed_schedule_json_and_inconsistent_eligibility(
    session_factory,
):
    collection = build_external_collection(
        target_drawing(), CompleteProvider(), aliases={}
    )
    save_collection(session_factory, collection)
    with session_factory.begin() as session:
        original_json = session.scalar(
            select(ExternalCollectionRun.requested_schedule_dates).where(
                ExternalCollectionRun.collection_id == collection.collection_id
            )
        )
        session.execute(
            text(
                "UPDATE external_collection_runs "
                "SET requested_schedule_dates = '{' "
                "WHERE collection_id = :collection_id"
            ),
            {"collection_id": collection.collection_id},
        )

    with pytest.raises(ValueError, match="requested_schedule_dates JSON"):
        load_latest_complete_collections(session_factory, last=1)

    with session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE external_collection_runs "
                "SET requested_schedule_dates = :requested_schedule_dates, "
                "eligibility_status = 'unknown' "
                "WHERE collection_id = :collection_id"
            ),
            {
                "collection_id": collection.collection_id,
                "requested_schedule_dates": original_json,
            },
        )

    with pytest.raises(ValueError, match="status is inconsistent"):
        load_latest_complete_collections(session_factory, last=1)


def test_init_db_adds_and_backfills_legacy_external_provenance(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE external_collection_runs ("
            "collection_id VARCHAR PRIMARY KEY)"
        )
        connection.execute(
            "INSERT INTO external_collection_runs (collection_id) VALUES ('legacy')"
        )
        connection.execute(
            "CREATE TABLE external_event_dispositions ("
            "id INTEGER PRIMARY KEY, match_status VARCHAR NOT NULL)"
        )
        connection.execute(
            "INSERT INTO external_event_dispositions (id, match_status) "
            "VALUES (1, 'matched'), (2, 'missing')"
        )

    engine = init_db(db_path)

    event_columns = {
        column["name"]
        for column in inspect(engine).get_columns("external_event_dispositions")
    }
    run_columns = {
        column["name"]
        for column in inspect(engine).get_columns("external_collection_runs")
    }
    with engine.connect() as connection:
        event_rows = connection.execute(
            text(
                "SELECT id, match_orientation, provider_starts_at, "
                "effective_starts_at, effective_start_source "
                "FROM external_event_dispositions ORDER BY id"
            )
        ).all()
        run_row = connection.execute(
            text(
                "SELECT target_fingerprint, missing_start_horizon_days, "
                "eligibility_status, eligibility_earliest_start, "
                "eligibility_latest_start, eligibility_span_days, "
                "eligibility_missing_event_orders, eligibility_totobrief_count, "
                "eligibility_provider_count FROM external_collection_runs"
            )
        ).one()
    engine.dispose()

    assert RUN_PROVENANCE_COLUMNS <= run_columns
    assert EVENT_TIMING_COLUMNS | {"match_orientation"} <= event_columns
    assert event_rows == [
        (1, "same", None, None, "unresolved"),
        (2, "none", None, None, "unresolved"),
    ]
    assert run_row == (
        None,
        None,
        "unknown",
        None,
        None,
        0,
        "[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14]",
        0,
        0,
    )


def test_open_readonly_db_never_migrates_legacy_tables(tmp_path):
    db_path = tmp_path / "readonly-legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE external_collection_runs ("
            "collection_id VARCHAR PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE external_event_dispositions ("
            "id INTEGER PRIMARY KEY, match_status VARCHAR NOT NULL)"
        )

    engine = open_readonly_db(db_path)
    run_columns = {
        column["name"]
        for column in inspect(engine).get_columns("external_collection_runs")
    }
    event_columns = {
        column["name"]
        for column in inspect(engine).get_columns("external_event_dispositions")
    }
    engine.dispose()

    assert RUN_PROVENANCE_COLUMNS.isdisjoint(run_columns)
    assert EVENT_TIMING_COLUMNS.isdisjoint(event_columns)


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
    assert _canonical_collection(stored[0]) == _canonical_collection(result)
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
