from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from toto_ai.external_odds.consensus import assess_market
from toto_ai.external_odds.domain import TargetEvent


@dataclass
class FakeResponse:
    payload: object
    headers: dict[str, str]
    status_code: int = 200

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected network call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def quota_headers(*, remaining: int = 499, used: int = 1, last: int = 1):
    return {
        "x-requests-remaining": str(remaining),
        "x-requests-used": str(used),
        "x-requests-last": str(last),
    }


def sports_payload() -> list[dict[str, object]]:
    return [
        {
            "key": "soccer_epl",
            "group": "Soccer",
            "title": "EPL",
            "active": True,
            "has_outrights": False,
        },
        {
            "key": "icehockey_nhl",
            "group": "Ice Hockey",
            "title": "NHL",
            "active": True,
            "has_outrights": False,
        },
        {
            "key": "soccer_inactive",
            "group": "Soccer",
            "title": "Inactive",
            "active": False,
            "has_outrights": False,
        },
    ]


def event_payload(
    *,
    event_id: str = "event-1",
    sport_key: str = "soccer_epl",
    sport_title: str = "EPL",
    home: str = "Home FC",
    away: str = "Away FC",
) -> dict[str, object]:
    return {
        "id": event_id,
        "sport_key": sport_key,
        "sport_title": sport_title,
        "commence_time": "2026-08-13T18:00:00Z",
        "home_team": home,
        "away_team": away,
    }


def odds_payload(
    *,
    sport_key: str = "soccer_epl",
    sport_title: str = "EPL",
    outcomes: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    event = event_payload(sport_key=sport_key, sport_title=sport_title)
    event["bookmakers"] = [
        {
            "key": "onexbet",
            "title": "1xBet",
            "last_update": "2026-08-13T17:50:00Z",
            "markets": [
                {
                    "key": "h2h",
                    "last_update": "2026-08-13T17:50:00Z",
                    "outcomes": outcomes
                    or [
                        {"name": "Home FC", "price": 2.1},
                        {"name": "Draw", "price": 3.4},
                        {"name": "Away FC", "price": 3.6},
                    ],
                }
            ],
        },
        {
            "key": "pinnacle",
            "title": "Pinnacle",
            "last_update": "2026-08-13T17:49:00Z",
            "markets": [
                {
                    "key": "h2h",
                    "last_update": "2026-08-13T17:49:00Z",
                    "outcomes": [
                        {"name": "Home FC", "price": 2.2},
                        {"name": "Draw", "price": 3.3},
                        {"name": "Away FC", "price": 3.5},
                    ],
                }
            ],
        },
    ]
    return [event]


def target_event(sport: str = "football") -> TargetEvent:
    return TargetEvent(
        drawing_id=1,
        drawing_number=5000,
        event_id=11,
        event_order=0,
        sport=sport,  # type: ignore[arg-type]
        championship="EPL" if sport == "football" else "NHL",
        starts_at=datetime(2026, 8, 13, 18, 0, tzinfo=timezone.utc),
        deadline=datetime(2026, 8, 13, 17, 0, tzinfo=timezone.utc),
        home_team="Home FC",
        away_team="Away FC",
        home_team_en="Home FC",
        away_team_en="Away FC",
        bk_probabilities=(0.4, 0.3, 0.3),
    )


def test_client_requires_key_before_transport(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    session = FakeSession([])
    with pytest.raises(ValueError, match="THE_ODDS_API_KEY"):
        TheOddsAPIClient("", session=session, cache_dir=tmp_path)

    assert session.calls == []


def test_free_catalog_and_events_parse_provenance_without_serializing_key(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([event_payload()], quota_headers(last=0, used=0)),
        ]
    )
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        now=lambda: datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc),
    )

    events = client.fetch_schedule("football", (date(2026, 8, 13),))

    assert len(events) == 1
    assert events[0].provider == "the-odds-api"
    assert events[0].provider_event_id == "event-1"
    assert events[0].league == "EPL"
    assert events[0].source_endpoint == "/v4/sports/soccer_epl/events"
    assert events[0].request_fingerprint
    assert client.credit_state.last_cost == 0
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )
    assert "secret-key" not in serialized
    assert "secret-key" not in events[0].request_fingerprint
    assert tuple(item.cache_hit for item in client.request_evidence) == (False, False)
    assert tuple(item.credit_cost for item in client.request_evidence) == (0, 0)


def test_refresh_credit_state_is_free_and_reuses_validated_catalog(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    session = FakeSession(
        [
            FakeResponse(
                sports_payload(),
                quota_headers(remaining=50, used=450, last=0),
            ),
            FakeResponse(
                [event_payload()],
                quota_headers(remaining=50, used=450, last=0),
            ),
        ]
    )
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
    )

    state = client.refresh_credit_state()
    events = client.fetch_schedule("football", (date(2026, 8, 13),))

    assert state.remaining == 50
    assert state.used == 450
    assert state.last_cost == 0
    assert client.credits_spent == 0
    assert len(events) == 1
    assert len(session.calls) == 2
    assert session.calls[0]["url"].endswith("/v4/sports")
    assert session.calls[1]["url"].endswith("/v4/sports/soccer_epl/events")


def test_bulk_eu_h2h_preserves_one_xbet_pinnacle_and_quota(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([event_payload()], quota_headers(last=0, used=0)),
            FakeResponse(odds_payload(), quota_headers()),
        ]
    )
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        quota_reserve=50,
        now=lambda: datetime(2026, 8, 13, 17, 55, tzinfo=timezone.utc),
    )

    client.fetch_schedule("football", (date(2026, 8, 13),))
    markets = client.fetch_event_markets("football", "event-1")

    assert tuple(market.bookmaker_id for market in markets) == (
        "onexbet",
        "pinnacle",
    )
    assert all(market.market_name == "1X2" for market in markets)
    assert markets[0].home_price == pytest.approx(2.1)
    assert markets[0].draw_price == pytest.approx(3.4)
    assert markets[0].away_price == pytest.approx(3.6)
    assert client.credit_state.remaining == 499
    assert client.credit_state.used == 1
    assert client.credit_state.last_cost == 1
    assert client.credits_spent == 1
    paid_call = session.calls[-1]
    assert paid_call["url"].endswith("/v4/sports/soccer_epl/odds")
    assert paid_call["params"]["regions"] == "eu"
    assert paid_call["params"]["markets"] == "h2h"
    assert paid_call["params"]["oddsFormat"] == "decimal"
    assert client.request_evidence[-1].endpoint == "/v4/sports/soccer_epl/odds"
    assert client.request_evidence[-1].credit_cost == 1
    assert client.request_evidence[-1].cache_hit is False
    raw_paths = tuple((tmp_path / "raw").glob("*.json"))
    assert len(raw_paths) == 3
    assert all(
        "secret-key" not in path.read_text(encoding="utf-8")
        for path in raw_paths
    )


def test_free_cache_hit_is_visible_but_paid_odds_are_never_reused(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    now = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
    first_session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([event_payload()], quota_headers(last=0, used=0)),
            FakeResponse(odds_payload(), quota_headers()),
        ]
    )
    first = TheOddsAPIClient(
        "secret-key",
        session=first_session,
        cache_dir=tmp_path,
        now=lambda: now,
    )
    first.fetch_schedule("football", (date(2026, 8, 13),))
    first.fetch_event_markets("football", "event-1")

    second_session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=1)),
            FakeResponse(odds_payload(), quota_headers(remaining=498, used=2)),
        ]
    )
    second = TheOddsAPIClient(
        "secret-key",
        session=second_session,
        cache_dir=tmp_path,
        now=lambda: now + timedelta(minutes=5),
    )
    second.fetch_schedule("football", (date(2026, 8, 13),))
    second.fetch_event_markets("football", "event-1")

    assert second.cache_hits == 2
    assert tuple(item.cache_hit for item in second.request_evidence[:2]) == (
        True,
        True,
    )
    assert second.request_evidence[-1].cache_hit is False
    assert second.request_evidence[-1].endpoint.endswith("/odds")
    assert len(second_session.calls) == 2


def test_bulk_odds_are_reused_for_two_events_in_same_sport_key(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    second_event = event_payload(event_id="event-2", home="Second H", away="Second A")
    first_odds = odds_payload()[0]
    second_odds = event_payload(event_id="event-2", home="Second H", away="Second A")
    second_odds["bookmakers"] = [
        {
            "key": "onexbet",
            "title": "1xBet",
            "last_update": "2026-08-13T17:50:00Z",
            "markets": [
                {
                    "key": "h2h",
                    "last_update": "2026-08-13T17:50:00Z",
                    "outcomes": [
                        {"name": "Second H", "price": 2.0},
                        {"name": "Draw", "price": 3.5},
                        {"name": "Second A", "price": 3.7},
                    ],
                }
            ],
        }
    ]
    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse(
                [event_payload(), second_event],
                quota_headers(last=0, used=0),
            ),
            FakeResponse([first_odds, second_odds], quota_headers()),
        ]
    )
    client = TheOddsAPIClient("secret-key", session=session, cache_dir=tmp_path)

    client.fetch_schedule("football", (date(2026, 8, 13),))
    first = client.fetch_event_markets("football", "event-1")
    second = client.fetch_event_markets("football", "event-2")

    assert len(first) == 2
    assert len(second) == 1
    assert len(session.calls) == 3
    assert client.credits_spent == 1


def test_schedule_accumulates_events_across_requested_dates(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    first = event_payload(event_id="event-1")
    second = event_payload(event_id="event-2")
    second["commence_time"] = "2026-08-14T18:00:00Z"
    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([first], quota_headers(last=0, used=0)),
            FakeResponse([second], quota_headers(last=0, used=0)),
        ]
    )
    client = TheOddsAPIClient("secret-key", session=session, cache_dir=tmp_path)

    first_result = client.fetch_schedule("football", (date(2026, 8, 13),))
    second_result = client.fetch_schedule("football", (date(2026, 8, 14),))

    assert tuple(event.provider_event_id for event in first_result) == ("event-1",)
    assert tuple(event.provider_event_id for event in second_result) == ("event-2",)
    assert len(session.calls) == 3


def test_hockey_two_way_h2h_is_not_regulation_three_way(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import TheOddsAPIClient

    hockey_event = event_payload(
        sport_key="icehockey_nhl", sport_title="NHL"
    )
    two_way = odds_payload(
        sport_key="icehockey_nhl",
        sport_title="NHL",
        outcomes=[
            {"name": "Home FC", "price": 1.8},
            {"name": "Away FC", "price": 2.1},
        ],
    )
    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([hockey_event], quota_headers(last=0, used=0)),
            FakeResponse(two_way, quota_headers()),
        ]
    )
    fetched_at = datetime(2026, 8, 13, 17, 55, tzinfo=timezone.utc)
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        now=lambda: fetched_at,
    )

    client.fetch_schedule("hockey", (date(2026, 8, 13),))
    market = client.fetch_event_markets("hockey", "event-1")[0]
    assessment = assess_market(target_event("hockey"), market, fetched_at)

    assert market.market_name == "H2H Including Overtime"
    assert market.draw_price is None
    assert assessment.eligible is False
    assert assessment.rejection_reason == "not regulation three-way"


def test_quota_reserve_stops_before_optional_paid_call(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import (
        TheOddsAPIClient,
        TheOddsAPIQuotaExhausted,
    )

    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(remaining=50, last=0)),
            FakeResponse([event_payload()], quota_headers(remaining=50, last=0)),
        ]
    )
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        quota_reserve=50,
    )

    client.fetch_schedule("football", (date(2026, 8, 13),))
    with pytest.raises(TheOddsAPIQuotaExhausted, match="quota reserve"):
        client.fetch_event_markets("football", "event-1")

    assert len(session.calls) == 2


def test_paid_call_primes_quota_when_only_cached_free_discovery_exists(
    tmp_path: Path,
) -> None:
    from toto_ai.external_odds.the_odds_api import (
        TheOddsAPIClient,
        TheOddsAPIQuotaExhausted,
    )

    initial = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(remaining=50, last=0)),
            FakeResponse([event_payload()], quota_headers(remaining=50, last=0)),
        ]
    )
    first = TheOddsAPIClient(
        "secret-key",
        session=initial,
        cache_dir=tmp_path,
        quota_reserve=50,
        now=lambda: datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc),
    )
    first.fetch_schedule("football", (date(2026, 8, 13),))

    fresh_quota = FakeSession(
        [FakeResponse(sports_payload(), quota_headers(remaining=50, last=0))]
    )
    second = TheOddsAPIClient(
        "secret-key",
        session=fresh_quota,
        cache_dir=tmp_path,
        quota_reserve=50,
        now=lambda: datetime(2026, 8, 13, 16, 5, tzinfo=timezone.utc),
    )
    second.fetch_schedule("football", (date(2026, 8, 13),))

    with pytest.raises(TheOddsAPIQuotaExhausted):
        second.fetch_event_markets("football", "event-1")

    assert len(fresh_quota.calls) == 1


def test_transport_error_is_sanitized_and_never_contains_key(tmp_path: Path) -> None:
    from toto_ai.external_odds.the_odds_api import (
        TheOddsAPIClient,
        TheOddsAPIError,
    )

    session = FakeSession([requests.ConnectionError("secret-key leaked")])
    client = TheOddsAPIClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        max_retries=0,
    )

    with pytest.raises(TheOddsAPIError) as caught:
        client.fetch_schedule("football", (date(2026, 8, 13),))

    assert "secret-key" not in str(caught.value)


@pytest.mark.parametrize(
    "outcomes, message",
    [
        (
            [
                {"name": "Home FC", "price": 2.0},
                {"name": "Home FC", "price": 2.1},
                {"name": "Draw", "price": 3.0},
                {"name": "Away FC", "price": 4.0},
            ],
            "duplicate outcome",
        ),
        (
            [
                {"name": "Home FC", "price": 2.0},
                {"name": "Draw", "price": 3.0},
                {"name": "Away FC", "price": 4.0},
                {"name": "Other", "price": 99.0},
            ],
            "unknown outcome",
        ),
    ],
)
def test_malformed_h2h_outcomes_fail_closed(
    tmp_path: Path,
    outcomes: list[dict[str, object]],
    message: str,
) -> None:
    from toto_ai.external_odds.the_odds_api import (
        TheOddsAPIClient,
        TheOddsAPIError,
    )

    session = FakeSession(
        [
            FakeResponse(sports_payload(), quota_headers(last=0, used=0)),
            FakeResponse([event_payload()], quota_headers(last=0, used=0)),
            FakeResponse(odds_payload(outcomes=outcomes), quota_headers()),
        ]
    )
    client = TheOddsAPIClient("secret-key", session=session, cache_dir=tmp_path)

    client.fetch_schedule("football", (date(2026, 8, 13),))
    with pytest.raises(TheOddsAPIError, match=message):
        client.fetch_event_markets("football", "event-1")
