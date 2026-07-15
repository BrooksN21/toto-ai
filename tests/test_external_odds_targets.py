from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from toto_ai.external_odds.domain import ProviderEvent, ProviderMarket, TargetEvent
from toto_ai.external_odds.targets import classify_sport, parse_target_drawing


def payload():
    events = []
    for order in reversed(range(15)):
        events.append(
            {
                "id": 10_000 + order,
                "order": order,
                "name": (
                    "Бавария — ПСЖ"
                    if order == 0
                    else f"Команда {order} - Гости {order}"
                ),
                "name_en": "Bayern Munich — PSG" if order == 0 else None,
                "championship": "Бундеслига" if order == 0 else "КХЛ",
                "sport": "football" if order == 0 else None,
                "start_at": "2026-07-14T18:00:00Z",
                "quotes": {
                    "bk_win_1": 0.60,
                    "bk_draw": 0.18,
                    "bk_win_2": 0.22,
                },
            }
        )
    return {
        "data": {
            "id": 9000,
            "number": 5000,
            "ended_at": "2026-07-14T17:55:00Z",
            "events": events,
        }
    }


def test_fresh_payload_becomes_fifteen_ordered_targets():
    drawing = parse_target_drawing(payload(), fetched_at="2026-07-14T12:00:00Z")

    assert drawing.drawing_id == 9000
    assert drawing.drawing_number == 5000
    assert tuple(event.event_order for event in drawing.events) == tuple(range(15))
    assert drawing.events[0].starts_at.isoformat() == "2026-07-14T18:00:00+00:00"
    assert drawing.events[0].deadline.isoformat() == "2026-07-14T17:55:00+00:00"
    assert drawing.events[0].home_team == "Бавария"
    assert drawing.events[0].away_team == "ПСЖ"
    assert drawing.events[0].home_team_en == "Bayern Munich"
    assert drawing.events[0].away_team_en == "PSG"
    assert drawing.events[0].bk_probabilities == pytest.approx((0.60, 0.18, 0.22))
    assert drawing.events[1].sport == "hockey"


def test_unknown_sport_is_explicit_and_not_guessed():
    assert classify_sport("Неизвестный турнир", None) == "unknown"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["data"]["events"].pop(), "exactly 15"),
        (
            lambda data: data["data"]["events"].__setitem__(
                0, {**data["data"]["events"][0], "order": 0}
            ),
            "orders 0 through 14",
        ),
        (
            lambda data: data["data"]["events"][0].__setitem__(
                "start_at", "2026-07-14T18:00:00"
            ),
            "timezone-aware",
        ),
    ],
)
def test_payload_requires_exactly_fifteen_unique_orders_and_aware_times(
    mutate, message
):
    data = payload()
    mutate(data)

    with pytest.raises(ValueError, match=message):
        parse_target_drawing(data, fetched_at="2026-07-14T12:00:00Z")


def test_payload_rejects_unsplittable_primary_name_and_invalid_bk_probabilities():
    data = payload()
    data["data"]["events"][0]["name"] = "Бавария"
    with pytest.raises(ValueError, match="home and away"):
        parse_target_drawing(data, fetched_at="2026-07-14T12:00:00Z")

    data = payload()
    data["data"]["events"][0]["quotes"]["bk_win_1"] = 0
    with pytest.raises(ValueError, match="positive"):
        parse_target_drawing(data, fetched_at="2026-07-14T12:00:00Z")


def test_domain_records_reject_invalid_times_orders_probabilities_and_prices():
    aware = datetime(2026, 7, 14, tzinfo=timezone.utc)
    valid_event = {
        "drawing_id": 9000,
        "drawing_number": None,
        "event_id": 1,
        "event_order": 0,
        "sport": "football",
        "championship": "League",
        "starts_at": aware,
        "deadline": aware,
        "home_team": "Home",
        "away_team": "Away",
        "home_team_en": None,
        "away_team_en": None,
        "bk_probabilities": (0.5, 0.3, 0.2),
    }

    with pytest.raises(ValueError, match="event_order"):
        TargetEvent(**(valid_event | {"event_order": 15}))
    with pytest.raises(ValueError, match="timezone-aware"):
        TargetEvent(**(valid_event | {"starts_at": datetime(2026, 7, 14)}))
    with pytest.raises(ValueError, match="sum to one"):
        TargetEvent(**(valid_event | {"bk_probabilities": (0.5, 0.3, 0.3)}))

    with pytest.raises(ValueError, match="decimal"):
        ProviderMarket(
            provider="api-sports",
            provider_event_id="42",
            bookmaker_id="bookmaker",
            market_name="Match Winner",
            updated_at=aware,
            fetched_at=aware,
            payload_hash="abc",
            home_price=0,
            draw_price=3.0,
            away_price=4.0,
        )

    with pytest.raises(ValueError, match="provider_event_id"):
        ProviderEvent(
            provider="api-sports",
            provider_event_id="",
            sport="football",
            league="League",
            starts_at=aware,
            home_team="Home",
            away_team="Away",
            fetched_at=aware,
            payload_hash="abc",
        )


def test_domain_records_accept_zero_offset_utc_datetimes():
    class ZeroOffsetUTC(tzinfo):
        def utcoffset(self, dt):
            return timedelta(0)

        def dst(self, dt):
            return timedelta(0)

        def tzname(self, dt):
            return "UTC+00-custom"

    zero_offset_utc = ZeroOffsetUTC()
    aware = datetime(2026, 7, 14, tzinfo=zero_offset_utc)

    event = TargetEvent(
        drawing_id=9000,
        drawing_number=5000,
        event_id=1,
        event_order=0,
        sport="football",
        championship="League",
        starts_at=aware,
        deadline=aware,
        home_team="Home",
        away_team="Away",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.5, 0.3, 0.2),
    )

    market = ProviderMarket(
        provider="api-sports",
        provider_event_id="42",
        bookmaker_id="bookmaker",
        market_name="Match Winner",
        updated_at=aware,
        fetched_at=aware,
        payload_hash="hash",
        home_price=2.0,
        draw_price=3.0,
        away_price=4.0,
    )

    provider_event = ProviderEvent(
        provider="api-sports",
        provider_event_id="42",
        sport="football",
        league="League",
        starts_at=aware,
        home_team="Home",
        away_team="Away",
        fetched_at=aware,
        payload_hash="hash",
        markets=(market,),
    )

    assert event.starts_at.utcoffset() == timedelta(0)
    assert provider_event.starts_at.utcoffset() == timedelta(0)
