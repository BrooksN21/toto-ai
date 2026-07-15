from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base, ExternalCollectionRun, ExternalEventDisposition
from toto_ai.external_odds.api_sports import APISportsError, QuotaExhausted
from toto_ai.external_odds.collection import (
    build_external_collection,
    collect_open_external_odds,
)
from toto_ai.external_odds.domain import (
    ProviderEvent,
    ProviderMarket,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)


def aware_now() -> datetime:
    return datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def target_drawing() -> TargetDrawing:
    now = aware_now()
    sports = ("football", "hockey", "unknown") + ("football",) * 12
    events = tuple(
        TargetEvent(
            drawing_id=9000,
            drawing_number=5000,
            event_id=10_000 + order,
            event_order=order,
            sport=sports[order],
            championship="League" if sports[order] != "unknown" else "Unknown",
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
        fetched_at=now,
        events=events,
    )


def multi_date_target_drawing() -> TargetDrawing:
    original = target_drawing()
    events = tuple(
        TargetEvent(
            drawing_id=event.drawing_id,
            drawing_number=event.drawing_number,
            event_id=event.event_id,
            event_order=event.event_order,
            sport=event.sport,
            championship=event.championship,
            starts_at=(
                event.starts_at + timedelta(days=1)
                if event.event_order == 14
                else event.starts_at
            ),
            deadline=event.deadline,
            home_team=event.home_team,
            away_team=event.away_team,
            home_team_en=event.home_team_en,
            away_team_en=event.away_team_en,
            bk_probabilities=event.bk_probabilities,
        )
        for event in original.events
    )
    return TargetDrawing(
        drawing_id=original.drawing_id,
        drawing_number=original.drawing_number,
        deadline=original.deadline,
        fetched_at=original.fetched_at,
        events=events,
    )


def drawing_info_payload(drawing_id: int) -> dict[str, object]:
    events = []
    for event in target_drawing().events:
        events.append(
            {
                "id": event.event_id,
                "order": event.event_order,
                "name": f"{event.home_team} - {event.away_team}",
                "championship": event.championship,
                "sport": event.sport if event.sport != "unknown" else None,
                "start_at": event.starts_at.isoformat(),
                "quotes": {
                    "bk_win_1": 0.5,
                    "bk_draw": 0.25,
                    "bk_win_2": 0.25,
                },
            }
        )
    return {
        "data": {
            "id": drawing_id,
            "number": 5000,
            "ended_at": target_drawing().deadline.isoformat(),
            "events": events,
        }
    }


class MixedProvider:
    provider_name = "api-sports"

    def __init__(self, target: TargetDrawing | None = None) -> None:
        self.target = target or target_drawing()
        self.schedule_calls = []
        self.market_calls = []
        self.requests_made = 0
        self._quota_state = QuotaState(100, 77, 10, 7)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def fetch_schedule(self, sport, dates):
        self.requests_made += max(1, len(dates))
        self.schedule_calls.append((sport, dates))
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"{sport}-{order}",
                sport=sport,
                league="League",
                starts_at=event.starts_at,
                home_team=event.home_team,
                away_team=event.away_team,
                fetched_at=aware_now(),
                payload_hash=f"schedule-{sport}-{order}",
            )
            for order, event in enumerate(self.target.events)
            if event.sport == sport
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        self.market_calls.append((sport, provider_event_id))
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name=(
                    "Match Winner"
                    if sport == "football"
                    else "Match Winner - Regulation Time"
                ),
                updated_at=aware_now() - timedelta(hours=1),
                fetched_at=aware_now(),
                payload_hash=f"market-{provider_event_id}-{index}",
                home_price=2.0,
                draw_price=4.0,
                away_price=4.0,
            )
            for index in range(3)
        )


class FailingProvider(MixedProvider):
    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        raise APISportsError("sanitized failure")


class QuotaProvider(MixedProvider):
    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        raise QuotaExhausted("quota reserve reached")


class ScheduleQuotaProvider(MixedProvider):
    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        self.schedule_calls.append((sport, dates))
        raise QuotaExhausted("quota reserve reached")


class LaterMarketObservationProvider(MixedProvider):
    def fetch_schedule(self, sport, dates):
        self.requests_made += max(1, len(dates))
        self.schedule_calls.append((sport, dates))
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"{sport}-{order}",
                sport=sport,
                league="League",
                starts_at=event.starts_at,
                home_team=event.home_team,
                away_team=event.away_team,
                fetched_at=aware_now() + timedelta(minutes=1),
                payload_hash=f"schedule-{sport}-{order}",
            )
            for order, event in enumerate(self.target.events)
            if event.sport == sport
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        self.market_calls.append((sport, provider_event_id))
        order = int(provider_event_id.rsplit("-", 1)[1])
        fetched_at = aware_now() + timedelta(minutes=2)
        if order == 0:
            updated_at = aware_now() + timedelta(minutes=1, seconds=30)
        elif order == 1:
            updated_at = fetched_at + timedelta(seconds=1)
        else:
            updated_at = fetched_at - timedelta(hours=36, seconds=1)
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name=(
                    "Match Winner"
                    if sport == "football"
                    else "Match Winner - Regulation Time"
                ),
                updated_at=updated_at,
                fetched_at=fetched_at,
                payload_hash=f"market-{provider_event_id}-{index}",
                home_price=2.0,
                draw_price=4.0,
                away_price=4.0,
            )
            for index in range(3)
        )


class CacheHitProvider(MixedProvider):
    def __init__(self) -> None:
        super().__init__()
        self.cache_hits = 0
        self.logical_fetches = 0

    def fetch_schedule(self, sport, dates):
        self.logical_fetches += 1
        self.cache_hits += 1
        self.schedule_calls.append((sport, dates))
        return tuple(
            ProviderEvent(
                provider=self.provider_name,
                provider_event_id=f"{sport}-{order}",
                sport=sport,
                league="League",
                starts_at=event.starts_at,
                home_team=event.home_team,
                away_team=event.away_team,
                fetched_at=aware_now(),
                payload_hash=f"schedule-{sport}-{order}",
            )
            for order, event in enumerate(self.target.events)
            if event.sport == sport
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.logical_fetches += 1
        self.cache_hits += 1
        self.market_calls.append((sport, provider_event_id))
        return tuple(
            ProviderMarket(
                provider=self.provider_name,
                provider_event_id=provider_event_id,
                bookmaker_id=f"book-{index}",
                market_name=(
                    "Match Winner"
                    if sport == "football"
                    else "Match Winner - Regulation Time"
                ),
                updated_at=aware_now() - timedelta(hours=1),
                fetched_at=aware_now(),
                payload_hash=f"market-{provider_event_id}-{index}",
                home_price=2.0,
                draw_price=4.0,
                away_price=4.0,
            )
            for index in range(3)
        )


def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_build_fetches_schedules_before_unique_odds_and_records_every_event():
    provider = MixedProvider()

    result = build_external_collection(target_drawing(), provider, aliases={})

    assert len(result.events) == 15
    assert tuple(row.event_order for row in result.events) == tuple(range(15))
    assert provider.schedule_calls == [
        ("football", (aware_now().date(),)),
        ("hockey", (aware_now().date(),)),
    ]
    assert provider.market_calls == [
        ("football", "football-0"),
        ("hockey", "hockey-1"),
        *(
            ("football", f"football-{order}")
            for order in range(3, 15)
        ),
    ]
    assert result.events[0].probability_source == "external_consensus"
    assert result.events[1].probability_source == "external_consensus"
    assert result.events[2].match_status == "unknown_sport"
    assert result.events[2].probability_source == "totobrief_bk_fallback"
    assert result.events[2].fallback_reason == "unknown sport"
    assert result.daily_limit == 100
    assert result.daily_remaining == 77
    assert result.minute_remaining == 7


def test_schedule_request_count_reflects_each_required_sport_date():
    target = multi_date_target_drawing()
    provider = MixedProvider(target)

    result = build_external_collection(target, provider, aliases={})

    assert provider.schedule_calls == [
        ("football", (aware_now().date(), (aware_now() + timedelta(days=1)).date())),
        ("hockey", (aware_now().date(),)),
    ]
    assert result.requests_made == 17


def test_missing_target_start_fetches_bounded_dates_from_drawing_deadline():
    class EmptyProvider:
        provider_name = "api-sports"

        def __init__(self):
            self.schedule_calls = []
            self.requests_made = 0
            self.cache_hits = 0
            self.quota_state = QuotaState(100, 90, 10, 9)

        def fetch_schedule(self, sport, dates):
            self.schedule_calls.append((sport, dates))
            self.requests_made += len(dates)
            return ()

        def fetch_event_markets(self, sport, provider_event_id):
            raise AssertionError("markets must not be fetched without a match")

    original = target_drawing()
    events = tuple(
        TargetEvent(
            **{
                **event.__dict__,
                "starts_at": None,
            }
        )
        for event in original.events
    )
    target = TargetDrawing(
        drawing_id=original.drawing_id,
        drawing_number=original.drawing_number,
        deadline=original.deadline,
        fetched_at=original.fetched_at,
        events=events,
    )
    provider = EmptyProvider()

    result = build_external_collection(target, provider, aliases={})

    expected_dates = tuple(
        (target.deadline + timedelta(days=offset)).date() for offset in range(2)
    )
    assert provider.schedule_calls == [
        ("football", expected_dates),
        ("hockey", expected_dates),
    ]
    assert all(event.starts_at == "" for event in result.events)
    assert all(event.match_status != "matched" for event in result.events)


def test_collection_observation_clock_allows_markets_fetched_after_target_snapshot():
    target = target_drawing()
    provider = LaterMarketObservationProvider(target)

    result = build_external_collection(target, provider, aliases={})

    assert result.fetched_at == (aware_now() + timedelta(minutes=2)).isoformat()
    assert result.target_fetched_at == aware_now().isoformat()
    assert result.events[0].probability_source == "external_consensus"
    assert result.events[1].probability_source == "totobrief_bk_fallback"
    assert "future update timestamp" in result.events[1].fallback_reason
    assert result.events[3].probability_source == "totobrief_bk_fallback"
    assert "stale prices" in result.events[3].fallback_reason


def test_collection_uses_actual_provider_network_delta_not_logical_cache_calls():
    provider = CacheHitProvider()

    result = build_external_collection(target_drawing(), provider, aliases={})

    assert provider.logical_fetches == 16
    assert result.requests_made == 0
    assert result.cache_hits == 16


def test_provider_failure_falls_back_for_every_remaining_event():
    result = build_external_collection(target_drawing(), FailingProvider(), aliases={})

    assert len(result.events) == 15
    assert all(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    assert all(row.fallback_reason for row in result.events)
    assert {row.match_status for row in result.events} == {
        "provider_failure",
        "unknown_sport",
    }


def test_quota_failure_records_explicit_fallback_without_silent_loss():
    result = build_external_collection(target_drawing(), QuotaProvider(), aliases={})

    assert len(result.events) == 15
    assert all(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    assert any("quota" in row.fallback_reason for row in result.events)
    assert sum(row.match_status == "matched" for row in result.events) == 14


def test_schedule_quota_failure_stops_provider_calls_for_remaining_sports():
    provider = ScheduleQuotaProvider()

    result = build_external_collection(target_drawing(), provider, aliases={})

    assert provider.schedule_calls == [("football", (aware_now().date(),))]
    assert len(result.events) == 15
    assert all(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    assert all(row.fallback_reason for row in result.events)


def test_collect_open_external_odds_fetches_resolved_drawing_and_saves(monkeypatch):
    class FakeTotoBriefClient:
        def __init__(self) -> None:
            self.info_calls = []

        def drawing_info(self, drawing_id):
            self.info_calls.append(drawing_id)
            return drawing_info_payload(drawing_id)

    client = FakeTotoBriefClient()
    provider = MixedProvider()
    factory = session_factory()

    monkeypatch.setattr(
        "toto_ai.external_odds.collection.resolve_open_drawing_from_api",
        lambda totobrief_client: type(
            "Reference",
            (),
            {"drawing_id": 9000, "number": 5000},
        )(),
    )

    result = collect_open_external_odds(
        client,
        provider,
        factory,
        aliases={},
        fetched_at=aware_now(),
    )

    assert client.info_calls == [9000]
    assert len(result.events) == 15
    with factory() as session:
        run_count = session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        )
        assert run_count == 1
        assert session.scalar(select(func.count(ExternalEventDisposition.id))) == 15
