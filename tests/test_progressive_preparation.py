from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base, DrawingEventPin
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing, TargetEvent
from toto_ai.external_odds.preparation import (
    fetch_preparation_schedule,
    prepare_drawing,
)
from toto_ai.external_odds.team_registry import backfill_accepted_matches

DEADLINE = datetime(2026, 7, 22, 16, tzinfo=timezone.utc)
FETCHED_AT = DEADLINE - timedelta(hours=1)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target() -> TargetDrawing:
    events = tuple(
        TargetEvent(
            drawing_id=11970,
            drawing_number=4952,
            event_id=33000 + order,
            event_order=order,
            sport="football",
            championship="США. National League",
            starts_at=None,
            deadline=DEADLINE,
            home_team=f"Проверенная домашняя {order}",
            away_team=f"Проверенная гостевая {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.4, 0.3, 0.3),
        )
        for order in range(15)
    )
    return TargetDrawing(11970, 4952, DEADLINE, FETCHED_AT, events)


def _provider_event(order: int, starts_at: datetime) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=f"fixture-{order}",
        sport="football",
        league="National League",
        starts_at=starts_at,
        home_team=f"Reviewed Home {order}",
        away_team=f"Reviewed Away {order}",
        fetched_at=FETCHED_AT,
        payload_hash=f"schedule-hash-{order}",
        country="United States",
        provider_home_team_id=f"provider-home-{order}",
        provider_away_team_id=f"provider-away-{order}",
    )


def _seed_reviewed_provider_ids(session_factory) -> None:
    matches = []
    for order in range(15):
        matches.append(
            {
                "drawing_id": 11970,
                "target_event_id": 33000 + order,
                "provider_fixture_id": f"fixture-{order}",
                "sport": "football",
                "target_home": f"Проверенная домашняя {order}",
                "target_away": f"Проверенная гостевая {order}",
                "provider_home": f"Reviewed Home {order}",
                "provider_away": f"Reviewed Away {order}",
                "provider_home_team_id": f"provider-home-{order}",
                "provider_away_team_id": f"provider-away-{order}",
                "country": "USA",
                "league": "National League",
                "reason": "reviewed/provider-ID exact accepted fixture",
                "reviewed": True,
            }
        )
    assert backfill_accepted_matches(session_factory, matches) == 30


def _events_by_date() -> dict[date, tuple[ProviderEvent, ...]]:
    first_start = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    second_start = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    return {
        date(2026, 7, 21): (),
        date(2026, 7, 22): tuple(
            _provider_event(order, first_start) for order in range(8)
        ),
        date(2026, 7, 23): tuple(
            _provider_event(order, second_start) for order in range(8, 15)
        ),
    }


def test_4952_style_progressive_preparation_stops_after_ready_date(
    session_factory,
):
    target = _target()
    _seed_reviewed_provider_ids(session_factory)
    events_by_date = _events_by_date()

    class Provider:
        def __init__(self):
            self.requested_dates = []

        def fetch_schedule(self, sport, dates):
            assert sport == "football"
            requested_date = dates[0]
            self.requested_dates.append(requested_date)
            return events_by_date.get(requested_date, ())

    provider = Provider()
    schedule = fetch_preparation_schedule(
        target,
        provider,
        session_factory=session_factory,
        missing_start_horizon_days=5,
    )

    assert provider.requested_dates == [
        date(2026, 7, 21),
        date(2026, 7, 22),
        date(2026, 7, 23),
    ]
    assert len(schedule.candidates) == 15
    assert [item["date"] for item in schedule.diagnostics] == [
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
    ]
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0

    prepared = prepare_drawing(
        target,
        schedule.candidates,
        session_factory=session_factory,
        schedule_diagnostics=schedule.diagnostics,
    )

    assert prepared.status == "ready"
    assert prepared.mapped_count == 15
    assert prepared.eligibility.status == "playable"
    assert prepared.eligibility.span_days == 2
    assert len(prepared.pins) == 15


def test_progressive_preparation_scopes_later_failure_to_unresolved_event(
    session_factory,
):
    target = _target()
    _seed_reviewed_provider_ids(session_factory)
    events_by_date = _events_by_date()
    events_by_date[date(2026, 7, 23)] = events_by_date[
        date(2026, 7, 23)
    ][:-1]

    class Provider:
        def __init__(self):
            self.requested_dates = []

        def fetch_schedule(self, sport, dates):
            assert sport == "football"
            requested_date = dates[0]
            self.requested_dates.append(requested_date)
            if requested_date == date(2026, 7, 24):
                raise RuntimeError("required date unavailable")
            return events_by_date.get(requested_date, ())

    provider = Provider()
    schedule = fetch_preparation_schedule(
        target,
        provider,
        session_factory=session_factory,
        missing_start_horizon_days=5,
    )

    assert provider.requested_dates == [
        date(2026, 7, 21),
        date(2026, 7, 22),
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 25),
        date(2026, 7, 26),
    ]
    assert len(schedule.candidates) == 14
    assert schedule.diagnostics[3] == {
        "sport": "football",
        "date": "2026-07-24",
        "status": "failed",
        "reason": "required date unavailable",
    }

    prepared = prepare_drawing(
        target,
        schedule.candidates,
        session_factory=session_factory,
        schedule_diagnostics=schedule.diagnostics,
    )

    assert prepared.status == "unresolved"
    assert prepared.mapped_count == 0
    assert prepared.pins == ()
    assert prepared.unresolved_event_orders == (14,)
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0
