from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base, ExternalCollectionRun, ExternalEventDisposition
from toto_ai.external_odds.api_sports import APISportsError, QuotaExhausted
from toto_ai.external_odds.collection import (
    build_external_collection,
    collect_open_external_odds,
    collect_target_external_odds,
    resolve_open_target,
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


class ReversedFirstProvider(MixedProvider):
    def fetch_schedule(self, sport, dates):
        events = super().fetch_schedule(sport, dates)
        return tuple(
            replace(
                event,
                home_team=event.away_team,
                away_team=event.home_team,
            )
            if event.provider_event_id == "football-0"
            else event
            for event in events
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
                away_price=8.0,
            )
            for index in range(3)
        )


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


def test_reversed_match_swaps_consensus_but_preserves_raw_provider_prices():
    result = build_external_collection(
        target_drawing(),
        ReversedFirstProvider(),
        aliases={},
    )

    event = result.events[0]
    assert event.match_status == "matched"
    assert event.match_orientation == "reversed"
    assert event.match_reason == "unique exact reversed match; outcomes swapped"
    assert (event.probability_1, event.probability_x, event.probability_2) == (
        pytest.approx(1 / 7),
        pytest.approx(2 / 7),
        pytest.approx(4 / 7),
    )
    assert all(quote.home_price == 2.0 for quote in event.bookmaker_quotes)
    assert all(quote.away_price == 8.0 for quote in event.bookmaker_quotes)


def test_schedule_request_count_reflects_each_required_sport_date():
    target = multi_date_target_drawing()
    provider = MixedProvider(target)

    result = build_external_collection(target, provider, aliases={})

    assert provider.schedule_calls == [
        ("football", (aware_now().date(),)),
        ("football", ((aware_now() + timedelta(days=1)).date(),)),
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

    expected_dates = (
        (target.deadline - timedelta(days=1)).date(),
        target.deadline.date(),
        (target.deadline + timedelta(days=1)).date(),
    )
    assert provider.schedule_calls == [
        *( ("football", (requested_date,)) for requested_date in expected_dates),
        *( ("hockey", (requested_date,)) for requested_date in expected_dates),
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


def test_schedule_collection_records_one_date_results_and_eligibility():
    result = build_external_collection(target_drawing(), MixedProvider(), aliases={})

    requested_dates = [
        (item.sport, item.requested_date.isoformat())
        for item in result.requested_schedule_dates
    ]
    assert requested_dates == [
        ("football", aware_now().date().isoformat()),
        ("hockey", aware_now().date().isoformat()),
    ]
    assert result.successful_schedule_dates == result.requested_schedule_dates
    assert result.failed_schedule_dates == ()
    assert result.target_fingerprint
    assert result.missing_start_horizon_days == 2
    assert result.eligibility.status == "playable"
    assert result.eligibility.totobrief_count == 15
    assert result.eligibility.provider_count == 0


def test_five_day_missing_start_horizon_requests_only_its_utc_coverage():
    class EmptyProvider:
        provider_name = "api-sports"
        quota_state = QuotaState(100, 90, 10, 9)

        def __init__(self):
            self.schedule_calls = []

        def fetch_schedule(self, sport, dates):
            self.schedule_calls.append((sport, dates))
            return ()

        def fetch_event_markets(self, sport, provider_event_id):
            raise AssertionError("markets must not be fetched without a match")

    original = target_drawing()
    deadline = datetime(2026, 7, 15, 21, 30, tzinfo=timezone.utc)
    target = replace(
        original,
        deadline=deadline,
        events=tuple(
            replace(event, starts_at=None, deadline=deadline)
            for event in original.events
        ),
    )
    provider = EmptyProvider()

    result = build_external_collection(
        target,
        provider,
        aliases={},
        missing_start_horizon_days=5,
    )

    expected_dates = tuple(
        (deadline + timedelta(days=offset)).date()
        for offset in range(6)
    )
    assert provider.schedule_calls == [
        *( ("football", (requested_date,)) for requested_date in expected_dates),
        *( ("hockey", (requested_date,)) for requested_date in expected_dates),
    ]
    requested_dates = [
        (item.sport, item.requested_date)
        for item in result.requested_schedule_dates
    ]
    assert requested_dates == [
        *( ("football", requested_date) for requested_date in expected_dates),
        *( ("hockey", requested_date) for requested_date in expected_dates),
    ]


def test_schedule_date_failure_preserves_other_dates_and_only_affects_its_target():
    class OneDateFailureProvider(MixedProvider):
        def fetch_schedule(self, sport, dates):
            requested_date = dates[0]
            self.requests_made += 1
            self.schedule_calls.append((sport, dates))
            if (
                sport == "football"
                and requested_date == (aware_now() + timedelta(days=1)).date()
            ):
                raise APISportsError("API key must not appear in collection provenance")
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
                if event.sport == sport and event.starts_at.date() == requested_date
            )

    target = multi_date_target_drawing()
    result = build_external_collection(
        target,
        OneDateFailureProvider(target),
        aliases={},
    )

    assert result.events[0].probability_source == "external_consensus"
    assert result.events[14].match_status == "provider_failure"
    assert result.events[14].fallback_reason == "provider schedule failure"
    failed_dates = [
        (item.sport, item.requested_date.isoformat(), item.error)
        for item in result.failed_schedule_dates
    ]
    assert failed_dates == [
        (
            "football",
            (aware_now() + timedelta(days=1)).date().isoformat(),
            "provider schedule failure",
        )
    ]


def test_schedule_quota_failure_marks_current_and_unattempted_dates_without_requests():
    original = target_drawing()
    target = replace(
        original,
        events=tuple(replace(event, starts_at=None) for event in original.events),
    )
    provider = ScheduleQuotaProvider()

    result = build_external_collection(target, provider, aliases={})

    assert provider.schedule_calls == [
        ("football", (aware_now().date() - timedelta(days=1),))
    ]
    assert len(result.requested_schedule_dates) == 6
    assert result.successful_schedule_dates == ()
    assert len(result.failed_schedule_dates) == 6
    assert {item.error for item in result.failed_schedule_dates} == {
        "quota reserve reached"
    }


def test_unmatched_missing_start_with_failed_schedule_uses_partial_schedule_fallback():
    original = target_drawing()
    target = replace(
        original,
        events=tuple(replace(event, starts_at=None) for event in original.events),
    )

    result = build_external_collection(target, FailingProvider(target), aliases={})

    assert result.events[0].match_status == "missing"
    assert result.events[0].fallback_reason == "partial schedule"
    assert result.eligibility.status == "unknown"


def test_provider_start_becomes_effective_without_overwriting_missing_target_start():
    original = target_drawing()
    target = replace(
        original,
        events=tuple(
            replace(event, starts_at=None) if event.event_order == 0 else event
            for event in original.events
        ),
    )

    result = build_external_collection(target, MixedProvider(original), aliases={})

    event = result.events[0]
    assert event.starts_at == ""
    assert event.provider_starts_at == original.events[0].starts_at.isoformat()
    assert event.effective_starts_at == original.events[0].starts_at.isoformat()
    assert event.effective_start_source == "provider"
    assert result.eligibility.totobrief_count == 14
    assert result.eligibility.provider_count == 1


def test_schedule_provenance_changes_collection_identity():
    class FailingSecondDateProvider(MixedProvider):
        def fetch_schedule(self, sport, dates):
            requested_date = dates[0]
            if requested_date == (aware_now() + timedelta(days=1)).date():
                self.schedule_calls.append((sport, dates))
                self.requests_made += 1
                raise APISportsError("not retained")
            return super().fetch_schedule(sport, dates)

    original = target_drawing()
    target = replace(
        original,
        events=tuple(replace(event, starts_at=None) for event in original.events),
    )
    all_successful = build_external_collection(
        target,
        MixedProvider(original),
        aliases={},
    )
    with_failed_date = build_external_collection(
        target,
        FailingSecondDateProvider(original),
        aliases={},
    )

    assert all_successful.collection_id != with_failed_date.collection_id


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


def test_resolve_open_target_fetches_one_pinned_drawing(monkeypatch):
    class FakeTotoBriefClient:
        def __init__(self) -> None:
            self.info_calls = []

        def drawing_info(self, drawing_id):
            self.info_calls.append(drawing_id)
            return drawing_info_payload(drawing_id)

    resolve_calls = []
    monkeypatch.setattr(
        "toto_ai.external_odds.collection.resolve_open_drawing_from_api",
        lambda client: (
            resolve_calls.append(client)
            or type("Reference", (), {"drawing_id": 9000, "number": 5000})()
        ),
    )
    client = FakeTotoBriefClient()

    target = resolve_open_target(client, fetched_at=aware_now())

    assert resolve_calls == [client]
    assert client.info_calls == [9000]
    assert target.drawing_id == 9000
    assert target.fetched_at == aware_now()


def test_resolve_open_target_rejects_drawing_info_id_mismatch(monkeypatch):
    class FakeTotoBriefClient:
        def drawing_info(self, drawing_id):
            return drawing_info_payload(drawing_id + 1)

    monkeypatch.setattr(
        "toto_ai.external_odds.collection.resolve_open_drawing_from_api",
        lambda _client: type(
            "Reference", (), {"drawing_id": 9000, "number": 5000}
        )(),
    )

    with pytest.raises(ValueError, match="drawing-info id does not match resolved"):
        resolve_open_target(FakeTotoBriefClient(), fetched_at=aware_now())


def test_collect_target_external_odds_saves_supplied_target_without_api_access():
    factory = session_factory()

    result = collect_target_external_odds(
        target_drawing(),
        MixedProvider(),
        factory,
        aliases={},
    )

    assert result.drawing_id == 9000
    with factory() as session:
        assert session.scalar(
            select(func.count(ExternalCollectionRun.collection_id))
        ) == 1
        assert session.scalar(select(func.count(ExternalEventDisposition.id))) == 15
