from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import requests

from toto_ai.external_odds.domain import ProviderEvent, QuotaState, TargetEvent


@dataclass
class FakeResponse:
    payload: dict[str, object]
    headers: dict[str, str]
    status_code: int = 200

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    def __init__(
        self, responses: list[FakeResponse | Exception] | None = None
    ) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict[str, object]] = []

    def queue(self, response: FakeResponse | Exception) -> None:
        self._responses.append(response)

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "params": dict(params),
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("unexpected network call")
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )


def quota_headers(
    *,
    daily_limit: str = "100",
    daily_remaining: str = "99",
    minute_limit: str = "10",
    minute_remaining: str = "9",
) -> dict[str, str]:
    return {
        "x-ratelimit-requests-limit": daily_limit,
        "x-ratelimit-requests-remaining": daily_remaining,
        "x-ratelimit-limit": minute_limit,
        "x-ratelimit-remaining": minute_remaining,
    }


def football_schedule_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_481_600,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "fixture": {
                    "id": 42,
                    "date": "2026-07-14T18:00:00+00:00",
                },
                "league": {"name": "Premier League"},
                "teams": {
                    "home": {"name": "Home FC"},
                    "away": {"name": "Away FC"},
                },
            }
        ],
    }


def hockey_schedule_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_482_200,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "game": {
                    "id": 77,
                    "date": "2026-07-14T19:30:00+00:00",
                },
                "league": {"name": "KHL"},
                "teams": {
                    "home": {"name": "СКА"},
                    "away": {"name": "ЦСКА"},
                },
            }
        ],
    }


def odds_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_481_900,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "fixture": {
                    "id": 42,
                    "date": "2026-07-14T18:00:00+00:00",
                },
                "league": {"name": "Premier League"},
                "teams": {
                    "home": {"name": "Home FC"},
                    "away": {"name": "Away FC"},
                },
                "bookmakers": [
                    {
                        "id": 6,
                        "update": "2026-07-14T10:00:00+00:00",
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.30"},
                                    {"value": "Away", "odd": "3.80"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def official_football_odds_payload() -> dict[str, object]:
    payload = odds_payload()
    item = dict(payload["response"][0])
    item["update"] = "2026-07-14T10:30:00+00:00"
    item.pop("teams")
    bookmakers = []
    for bookmaker in item["bookmakers"]:
        clone = dict(bookmaker)
        clone.pop("update", None)
        bookmakers.append(clone)
    item["bookmakers"] = bookmakers
    official = {**payload, "response": [item]}
    official.pop("timestamp")
    return official


def hockey_odds_payload() -> dict[str, object]:
    return {
        "errors": [],
        "results": 1,
        "timestamp": 1_784_482_500,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "game": {
                    "id": 77,
                    "date": "2026-07-14T19:30:00+00:00",
                },
                "league": {"name": "KHL"},
                "teams": {
                    "home": {"name": "СКА"},
                    "away": {"name": "ЦСКА"},
                },
                "bookmakers": [
                    {
                        "id": "12",
                        "update": "2026-07-14T11:00:00+00:00",
                        "bets": [
                            {
                                "name": "Home/Draw/Away",
                                "values": [
                                    {"value": "Home", "odd": "1.90"},
                                    {"value": "Draw", "odd": "4.20"},
                                    {"value": "Away", "odd": "3.10"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def official_hockey_odds_payload() -> dict[str, object]:
    payload = hockey_odds_payload()
    item = dict(payload["response"][0])
    item["update"] = "2026-07-14T11:30:00+00:00"
    bookmakers = []
    for bookmaker in item["bookmakers"]:
        clone = dict(bookmaker)
        clone.pop("update", None)
        bookmakers.append(clone)
    item["bookmakers"] = bookmakers
    return {**payload, "response": [item]}


def read_cache_text(cache_dir: Path) -> str:
    return "".join(path.read_text() for path in sorted(cache_dir.iterdir()))


def test_client_requires_key_before_network_call(fake_session, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    with pytest.raises(ValueError, match="API_SPORTS_KEY"):
        APISportsClient(api_key="", session=fake_session, cache_dir=tmp_path)

    assert fake_session.calls == []


def test_schedule_response_is_cached_and_key_is_never_serialized(
    fake_session, tmp_path
):
    from toto_ai.external_odds.api_sports import APISportsClient

    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    first = client.fetch_schedule("football", (date(2026, 7, 14),))
    second = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert first == second
    assert len(fake_session.calls) == 1
    assert first[0].provider_event_id == "42"
    assert first[0].starts_at == datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc)
    assert first[0].league == "Premier League"
    assert first[0].home_team == "Home FC"
    assert first[0].away_team == "Away FC"
    assert "secret-key" not in read_cache_text(tmp_path)


def test_schedule_cache_is_shared_across_fresh_market_sessions(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    shared_schedule = tmp_path / "shared-schedule"
    first_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    first = APISportsClient(
        "secret-key",
        session=first_session,
        cache_dir=tmp_path / "market-one",
        schedule_cache_dir=shared_schedule,
        now=lambda: datetime(2026, 7, 19, 17, 25, tzinfo=timezone.utc),
    )
    second_session = FakeSession()
    second = APISportsClient(
        "secret-key",
        session=second_session,
        cache_dir=tmp_path / "market-two",
        schedule_cache_dir=shared_schedule,
        now=lambda: datetime(2026, 7, 19, 17, 30, tzinfo=timezone.utc),
    )

    first_result = first.fetch_schedule("football", (date(2026, 7, 14),))
    second_result = second.fetch_schedule("football", (date(2026, 7, 14),))

    assert first_result == second_result
    assert len(first_session.calls) == 1
    assert second_session.calls == []
    assert second.cache_hits == 1
    assert tuple(shared_schedule.glob("*.json"))
    assert not tuple((tmp_path / "market-one").glob("*.json"))


def test_shared_schedule_cache_never_reuses_market_odds(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    shared_schedule = tmp_path / "shared-schedule"
    first_session = FakeSession(
        [FakeResponse(payload=odds_payload(), headers=quota_headers())]
    )
    second_session = FakeSession(
        [FakeResponse(payload=odds_payload(), headers=quota_headers())]
    )
    first = APISportsClient(
        "secret-key",
        session=first_session,
        cache_dir=tmp_path / "market-one",
        schedule_cache_dir=shared_schedule,
    )
    second = APISportsClient(
        "secret-key",
        session=second_session,
        cache_dir=tmp_path / "market-two",
        schedule_cache_dir=shared_schedule,
    )

    first.fetch_event_markets("football", "42")
    second.fetch_event_markets("football", "42")

    assert len(first_session.calls) == 1
    assert len(second_session.calls) == 1
    assert not shared_schedule.exists()


def test_stale_shared_schedule_cache_is_refetched(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    shared_schedule = tmp_path / "shared-schedule"
    first_payload = football_schedule_payload()
    refreshed_payload = football_schedule_payload()
    refreshed_at = datetime(2026, 7, 19, 19, 30, tzinfo=timezone.utc)
    refreshed_payload["timestamp"] = int(refreshed_at.timestamp())
    first = APISportsClient(
        "secret-key",
        session=FakeSession(
            [FakeResponse(payload=first_payload, headers=quota_headers())]
        ),
        cache_dir=tmp_path / "market-one",
        schedule_cache_dir=shared_schedule,
        now=lambda: datetime(2026, 7, 19, 17, 25, tzinfo=timezone.utc),
    )
    second_session = FakeSession(
        [FakeResponse(payload=refreshed_payload, headers=quota_headers())]
    )
    second = APISportsClient(
        "secret-key",
        session=second_session,
        cache_dir=tmp_path / "market-two",
        schedule_cache_dir=shared_schedule,
        schedule_cache_max_age_seconds=3600,
        now=lambda: refreshed_at,
    )

    first.fetch_schedule("football", (date(2026, 7, 14),))
    second.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(second_session.calls) == 1
    assert second.cache_hits == 0


def test_official_schedule_without_timestamp_uses_cached_observation_time(
    monkeypatch, tmp_path
):
    from toto_ai.external_odds.api_sports import APISportsClient

    observed_at = datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "toto_ai.external_odds.api_sports._utc_now", lambda: observed_at
    )
    payload = football_schedule_payload()
    payload.pop("timestamp")
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    first = client.fetch_schedule("football", (date(2026, 7, 14),))
    second = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert first == second
    assert first[0].fetched_at == observed_at
    assert len(fake_session.calls) == 1
    cache = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert cache["fetched_at"] == "2026-07-15T12:30:00+00:00"


def test_quota_reserve_stops_before_request(fake_session, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, QuotaExhausted

    client = APISportsClient(
        "secret-key", session=fake_session, cache_dir=tmp_path, quota_reserve=5
    )
    client.set_quota_for_test(QuotaState(100, 5, 10, 10))

    with pytest.raises(QuotaExhausted):
        client.fetch_event_markets("hockey", "42")

    assert fake_session.calls == []


def test_daily_reserve_does_not_consume_minute_remaining_budget(
    fake_session, tmp_path
):
    from toto_ai.external_odds.api_sports import APISportsClient

    client = APISportsClient(
        "secret-key", session=fake_session, cache_dir=tmp_path, quota_reserve=10
    )
    client.set_quota_for_test(QuotaState(100, 99, 10, 9))

    events = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(events) == 1
    assert len(fake_session.calls) == 1


def test_zero_minute_remaining_stops_before_request(fake_session, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, QuotaExhausted

    client = APISportsClient(
        "secret-key", session=fake_session, cache_dir=tmp_path, quota_reserve=0
    )
    client.set_quota_for_test(QuotaState(100, 99, 10, 0))

    with pytest.raises(QuotaExhausted):
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert fake_session.calls == []


def test_hockey_schedule_uses_game_shape(fake_session, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=hockey_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    events = client.fetch_schedule("hockey", (date(2026, 7, 14),))

    assert events == (
        ProviderEvent(
            provider="api-sports",
            provider_event_id="77",
            sport="hockey",
            league="KHL",
            starts_at=datetime(2026, 7, 14, 19, 30, tzinfo=timezone.utc),
            home_team="СКА",
            away_team="ЦСКА",
            fetched_at=datetime.fromtimestamp(1_784_482_200, tz=timezone.utc),
            payload_hash=hashlib.sha256(
                json.dumps(
                    hockey_schedule_payload()["response"][0],
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        ),
    )


def test_hockey_schedule_uses_hockey_games_endpoint(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=hockey_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    client.fetch_schedule("hockey", (date(2026, 7, 14),))

    assert fake_session.calls[0]["url"] == "https://v1.hockey.api-sports.io/games"
    assert fake_session.calls[0]["params"] == {"date": "2026-07-14"}


def test_hockey_schedule_rejects_football_fixture_shape(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    fake_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="game"):
        client.fetch_schedule("hockey", (date(2026, 7, 14),))


def test_event_markets_preserve_bookmaker_market_and_prices(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=odds_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("football", "42")

    assert len(markets) == 1
    assert markets[0].bookmaker_id == "6"
    assert markets[0].market_name == "Match Winner"
    assert markets[0].updated_at == datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
    assert markets[0].home_price == pytest.approx(2.10)
    assert markets[0].draw_price == pytest.approx(3.30)
    assert markets[0].away_price == pytest.approx(3.80)


def test_unrelated_markets_do_not_abort_eligible_three_way_market(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient
    from toto_ai.external_odds.consensus import build_consensus

    payload = odds_payload()
    payload["timestamp"] = int(
        datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc).timestamp()
    )
    payload["response"][0]["bookmakers"][0]["bets"].extend(
        [
            {
                "name": "Goals Over/Under",
                "values": [
                    {"value": "Over 2.5", "odd": "1.90"},
                    {"value": "Under 2.5", "odd": "1.90"},
                ],
            },
            {
                "name": "Double Chance",
                "values": [
                    {"value": "Home/Draw", "odd": "1.30"},
                    {"value": "Home/Away", "odd": "1.35"},
                    {"value": "Draw/Away", "odd": "1.40"},
                ],
            },
            {
                "name": "Moneyline",
                "values": [
                    {"value": "Home", "odd": "1.70"},
                    {"value": "Away", "odd": "2.10"},
                ],
            },
        ]
    )
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("football", "42")
    consensus = build_consensus(
        TargetEvent(
            drawing_id=1,
            drawing_number=None,
            event_id=1,
            event_order=0,
            sport="football",
            championship="Premier League",
            starts_at=datetime(2026, 7, 14, 18, 0, tzinfo=timezone.utc),
            deadline=datetime(2026, 7, 14, 17, 0, tzinfo=timezone.utc),
            home_team="Home FC",
            away_team="Away FC",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.4, 0.3, 0.3),
        ),
        markets,
        fetched_at=datetime.fromtimestamp(payload["timestamp"], tz=timezone.utc),
        minimum_bookmakers=1,
    )

    assert tuple(market.market_name for market in markets) == (
        "Match Winner",
        "Goals Over/Under",
        "Double Chance",
        "Moneyline",
    )
    assert consensus.eligible_bookmaker_count == 1
    assert consensus.probabilities is not None
    assert tuple(assessment.eligible for assessment in consensus.assessments) == (
        True,
        False,
        False,
        False,
    )
    assert tuple(
        assessment.rejection_reason for assessment in consensus.assessments[1:]
    ) == ("not full-time three-way",) * 3


def test_official_football_odds_item_update_is_default_for_bookmakers(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [
            FakeResponse(
                payload=official_football_odds_payload(),
                headers=quota_headers(),
            )
        ]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("football", "42")

    assert len(markets) == 1
    assert markets[0].updated_at == datetime(
        2026, 7, 14, 10, 30, tzinfo=timezone.utc
    )


def test_official_odds_accept_numeric_labels_in_non_three_way_market(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    payload = official_football_odds_payload()
    payload["response"][0]["bookmakers"][0]["bets"].append(
        {
            "id": 40,
            "name": "Home Team Exact Goals Number",
            "values": [
                {"value": 0, "odd": "4.60"},
                {"value": 1, "odd": "3.10"},
            ],
        }
    )
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("football", "42")

    assert tuple(market.market_name for market in markets) == (
        "Match Winner",
        "Home Team Exact Goals Number",
    )
    assert markets[1].home_price is None
    assert markets[1].draw_price is None
    assert markets[1].away_price is None


def test_valid_bookmaker_update_overrides_item_update_when_present(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    payload = official_football_odds_payload()
    payload["response"][0]["bookmakers"][0]["update"] = "2026-07-14T10:45:00+00:00"
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("football", "42")

    assert markets[0].updated_at == datetime(
        2026, 7, 14, 10, 45, tzinfo=timezone.utc
    )


def test_hockey_event_markets_use_game_query_and_parse_game_shape(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=hockey_odds_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("hockey", "77")

    assert fake_session.calls[0]["url"] == "https://v1.hockey.api-sports.io/odds"
    assert fake_session.calls[0]["params"] == {"game": "77", "page": 1}
    assert len(markets) == 1
    assert markets[0].provider_event_id == "77"
    assert markets[0].bookmaker_id == "12"
    assert markets[0].market_name == "Home/Draw/Away"
    assert markets[0].home_price == pytest.approx(1.90)
    assert markets[0].draw_price == pytest.approx(4.20)
    assert markets[0].away_price == pytest.approx(3.10)


def test_official_hockey_odds_item_update_is_default_for_bookmakers(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=official_hockey_odds_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    markets = client.fetch_event_markets("hockey", "77")

    assert len(markets) == 1
    assert markets[0].updated_at == datetime(
        2026, 7, 14, 11, 30, tzinfo=timezone.utc
    )


def test_duplicate_market_outcome_label_fails_closed(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    payload = odds_payload()
    payload["response"][0]["bookmakers"][0]["bets"][0]["values"] = [
        {"value": "Home", "odd": "2.10"},
        {"value": "Home", "odd": "2.20"},
        {"value": "Draw", "odd": "3.30"},
        {"value": "Away", "odd": "3.80"},
    ]
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="duplicate outcome"):
        client.fetch_event_markets("football", "42")


def test_unknown_extra_market_outcome_label_fails_closed(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    payload = odds_payload()
    payload["response"][0]["bookmakers"][0]["bets"][0]["values"] = [
        {"value": "Home", "odd": "2.10"},
        {"value": "Draw", "odd": "3.30"},
        {"value": "Away", "odd": "3.80"},
        {"value": "No Goal", "odd": "11.0"},
    ]
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="unknown outcome"):
        client.fetch_event_markets("football", "42")


def test_missing_market_outcome_label_fails_closed(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    payload = odds_payload()
    payload["response"][0]["bookmakers"][0]["bets"][0]["values"] = [
        {"value": "Home", "odd": "2.10"},
        {"value": "Away", "odd": "3.80"},
    ]
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="missing outcome Draw"):
        client.fetch_event_markets("football", "42")


def test_transient_connection_errors_retry_with_bounded_delays(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "toto_ai.external_odds.api_sports.time.sleep", sleep_calls.append
    )
    fake_session = FakeSession(
        [
            requests.ConnectionError("network down"),
            requests.ConnectionError("network still down"),
            FakeResponse(payload=football_schedule_payload(), headers=quota_headers()),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        max_retries=2,
    )

    events = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(events) == 1
    assert len(fake_session.calls) == 3
    assert sleep_calls == [0.05, 0.1]


def test_safety_stop_prevents_transport_retry(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    stop_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    current = [stop_at.replace(minute=59, hour=11)]
    sleep_calls: list[float] = []

    class AdvancingSession(FakeSession):
        def get(self, *args, **kwargs):
            try:
                return super().get(*args, **kwargs)
            finally:
                current[0] = stop_at

    session = AdvancingSession([requests.ConnectionError("network down")])
    monkeypatch.setattr(
        "toto_ai.external_odds.api_sports.time.sleep", sleep_calls.append
    )
    client = APISportsClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        max_retries=2,
        stop_at=stop_at,
        now=lambda: current[0],
    )

    with pytest.raises(APISportsError, match="safety stop"):
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(session.calls) == 1
    assert sleep_calls == []


def test_request_timeout_is_clamped_to_remaining_safety_window(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    stop_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    current = stop_at.replace(second=55, minute=59, hour=11)
    session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        timeout=30.0,
        stop_at=stop_at,
        now=lambda: current,
    )

    client.fetch_schedule("football", (date(2026, 7, 14),))

    assert session.calls[0]["timeout"] == pytest.approx(5.0)


def test_429_updates_quota_state_before_retry(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    retry_quota = QuotaState(100, 7, 10, 8)
    success_quota = QuotaState(100, 6, 10, 9)
    fake_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(daily_remaining="7", minute_remaining="8"),
                status_code=429,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(daily_remaining="6", minute_remaining="9"),
            ),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        quota_reserve=0,
        max_retries=1,
    )
    quota_at_retry: list[QuotaState] = []
    monkeypatch.setattr(
        client,
        "_sleep_before_retry",
        lambda attempt: quota_at_retry.append(client.quota_state),
    )

    client.fetch_schedule("football", (date(2026, 7, 14),))

    assert quota_at_retry == [retry_quota]
    assert client.quota_state == success_quota


def test_429_exhausted_quota_stops_before_retry(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, QuotaExhausted

    fake_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(daily_remaining="7", minute_remaining="0"),
                status_code=429,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(daily_remaining="6", minute_remaining="9"),
            ),
        ]
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "toto_ai.external_odds.api_sports.time.sleep", sleep_calls.append
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        quota_reserve=0,
        max_retries=1,
    )

    with pytest.raises(QuotaExhausted):
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert client.quota_state == QuotaState(100, 7, 10, 0)
    assert len(fake_session.calls) == 1
    assert sleep_calls == []


def test_final_provider_failure_is_sanitized_and_does_not_leak_key(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    retry_headers = quota_headers(minute_limit="100", minute_remaining="99")
    fake_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=retry_headers,
                status_code=500,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=retry_headers,
                status_code=500,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=retry_headers,
                status_code=500,
            ),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        max_retries=2,
    )

    with pytest.raises(APISportsError, match="API-Sports request failed") as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert "secret-key" not in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


def test_non_retry_http_failure_is_sanitized_and_not_cached(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    fake_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(),
                status_code=401,
            )
        ]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="status 401") as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert client.quota_state == QuotaState(100, 99, 10, 9)
    assert "secret-key" not in str(excinfo.value)
    assert "v3.football.api-sports.io" not in str(excinfo.value)
    assert "2026-07-14" not in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


def test_semantic_error_exposes_only_normalized_secret_safe_diagnostic(tmp_path):
    from toto_ai.external_odds.api_sports import (
        APISportsClient,
        ProviderPlanUnavailable,
    )

    api_key = "semantic-secret-key"
    payload = {
        **football_schedule_payload(),
        "errors": {
            "plan": {"api_key": api_key, "raw": football_schedule_payload()},
            "Requests Limit": f"token={api_key}",
            api_key: "mirrored credential",
        },
    }
    headers = {
        "X-RateLimit-Requests-Limit": "100",
        "X-RateLimit-Requests-Remaining": "17",
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "4",
        "X-RateLimit-Requests-Reset": "3600",
        "X-RateLimit-Reset": "42",
        "Authorization": f"Bearer {api_key}",
    }
    session = FakeSession([FakeResponse(payload=payload, headers=headers)])
    client = APISportsClient(api_key, session=session, cache_dir=tmp_path)

    with pytest.raises(ProviderPlanUnavailable) as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert str(excinfo.value) == (
        "API-Sports plan does not provide the requested data"
    )
    diagnostic = excinfo.value.diagnostic_payload()
    assert diagnostic == {
        "category": "semantic_error",
        "endpoint": "/fixtures",
        "attempt": 1,
        "http_status": 200,
        "provider_errors": [
            {"code": "plan", "message": "provider error"},
            {"code": "requests_limit", "message": "token=[REDACTED]"},
            {"code": "redacted", "message": "mirrored credential"},
        ],
        "quota_daily_limit": 100,
        "quota_daily_remaining": 17,
        "quota_minute_limit": 10,
        "quota_minute_remaining": 4,
        "quota_daily_reset": 3600,
        "quota_minute_reset": 42,
    }
    serialized = json.dumps(diagnostic, sort_keys=True)
    assert api_key not in str(excinfo.value)
    assert api_key not in serialized
    assert "Authorization" not in serialized
    assert "headers" not in serialized
    assert "raw" not in serialized
    assert "response" not in serialized
    assert client.request_diagnostics == (excinfo.value.diagnostic,)
    assert list(tmp_path.iterdir()) == []


def test_diagnostic_serialization_rejects_arbitrary_identity_and_metadata():
    from toto_ai.external_odds.api_sports import (
        APISportsDiagnostic,
        APISportsProviderError,
    )

    diagnostic = APISportsDiagnostic(
        category="raw response payload",
        endpoint="/odds?api_key=diagnostic-secret-key",
        attempt=0,
        http_status=999,
        provider_errors=(
            APISportsProviderError(
                code="invalid code with spaces",
                message="Authorization: Bearer diagnostic-secret-key",
            ),
        ),
        quota_daily_limit=-1,
    )

    payload = diagnostic.payload()
    assert payload["category"] == "semantic_error"
    assert payload["endpoint"] == "/odds"
    assert payload["attempt"] == 1
    assert payload["http_status"] is None
    assert payload["provider_errors"] == [
        {
            "code": "invalid_code_with_spaces",
            "message": "Authorization=[REDACTED]",
        }
    ]
    assert payload["quota_daily_limit"] is None
    serialized = json.dumps(payload, sort_keys=True)
    assert "diagnostic-secret-key" not in serialized
    assert "api_key" not in serialized
    assert "raw response payload" not in serialized


def test_http_error_diagnostic_keeps_status_quota_and_redacts_provider_message(
    tmp_path,
):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    api_key = "http-secret-key"
    payload = {
        **football_schedule_payload(),
        "errors": {"auth": f"Authorization: Bearer {api_key}"},
    }
    session = FakeSession(
        [
            FakeResponse(
                payload=payload,
                headers=quota_headers(daily_remaining="3", minute_remaining="2"),
                status_code=403,
            )
        ]
    )
    client = APISportsClient(api_key, session=session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="status 403") as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert str(excinfo.value) == "API-Sports request failed with status 403"
    diagnostic = excinfo.value.diagnostic_payload()
    assert diagnostic is not None
    assert diagnostic["category"] == "http_failure"
    assert diagnostic["http_status"] == 403
    assert diagnostic["quota_daily_limit"] == 100
    assert diagnostic["quota_daily_remaining"] == 3
    assert diagnostic["quota_minute_limit"] == 10
    assert diagnostic["quota_minute_remaining"] == 2
    assert diagnostic["provider_errors"] == [
        {"code": "auth", "message": "Authorization=[REDACTED]"}
    ]
    assert api_key not in str(excinfo.value)
    assert api_key not in json.dumps(diagnostic, sort_keys=True)
    assert list(tmp_path.iterdir()) == []


def test_retry_diagnostics_capture_each_http_attempt_without_raw_metadata(
    monkeypatch,
    tmp_path,
):
    from toto_ai.external_odds.api_sports import APISportsClient

    first_headers = quota_headers(daily_remaining="7", minute_remaining="8") | {
        "x-ratelimit-requests-reset": "120",
        "x-ratelimit-reset": "8",
    }
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    **football_schedule_payload(),
                    "errors": {"rate limit": "retry later"},
                },
                headers=first_headers,
                status_code=429,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(daily_remaining="6", minute_remaining="9"),
            ),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        quota_reserve=0,
        max_retries=1,
    )
    monkeypatch.setattr(client, "_sleep_before_retry", lambda attempt: None)

    client.fetch_schedule("football", (date(2026, 7, 14),))

    attempts = tuple(item.payload() for item in client.request_diagnostics)
    assert tuple(item["category"] for item in attempts) == (
        "http_retry",
        "success",
    )
    assert tuple(item["attempt"] for item in attempts) == (1, 2)
    assert tuple(item["http_status"] for item in attempts) == (429, 200)
    assert attempts[0]["provider_errors"] == [
        {"code": "rate_limit", "message": "retry later"}
    ]
    assert attempts[0]["quota_daily_reset"] == 120
    assert attempts[0]["quota_minute_reset"] == 8
    assert attempts[1]["quota_daily_remaining"] == 6
    assert "headers" not in json.dumps(attempts, sort_keys=True)
    assert "payload" not in json.dumps(attempts, sort_keys=True)


@pytest.mark.parametrize(
    "corrupt_cache",
    [
        '{"api_key":"secret-key"',
        json.dumps(
            {
                "quota": {"daily_limit": 100},
                "payload": football_schedule_payload(),
            }
        ),
    ],
)
def test_corrupt_cache_fails_closed_without_refetch(corrupt_cache, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    fake_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)
    client.fetch_schedule("football", (date(2026, 7, 14),))
    cache_path = next(tmp_path.glob("*.json"))
    cache_path.write_text(corrupt_cache)

    with pytest.raises(APISportsError, match="cache") as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(fake_session.calls) == 1
    assert "secret-key" not in str(excinfo.value)
    assert str(cache_path) not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_cache_write_uses_same_directory_atomic_replace(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    original_replace = Path.replace
    replacements: list[tuple[Path, Path]] = []

    def observe_replace(source: Path, target: Path) -> Path:
        target = Path(target)
        assert source.parent == target.parent == tmp_path
        assert source.name.startswith(f".{target.name}.")
        assert source.name.endswith(".tmp")
        assert not target.exists()
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", observe_replace)
    fake_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    client.fetch_schedule("football", (date(2026, 7, 14),))

    assert len(replacements) == 1
    assert sorted(path.suffix for path in tmp_path.iterdir()) == [".json"]


def test_cache_write_failure_is_sanitized_and_removes_temporary_file(
    monkeypatch, tmp_path
):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    def fail_replace(source: Path, target: Path) -> Path:
        raise OSError("secret-key raw cache path")

    monkeypatch.setattr(Path, "replace", fail_replace)
    fake_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="cache write") as excinfo:
        client.fetch_schedule("football", (date(2026, 7, 14),))

    assert "secret-key" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {**football_schedule_payload(), "errors": {"token": "bad"}},
            "provider errors",
        ),
        (
            {**football_schedule_payload(), "paging": {"current": 0, "total": 1}},
            "paging",
        ),
        ({**football_schedule_payload(), "timestamp": "later"}, "timestamp"),
        ({**football_schedule_payload(), "timestamp": float("inf")}, "timestamp"),
        (
            {
                **odds_payload(),
                "response": [
                    {
                        **odds_payload()["response"][0],
                        "bookmakers": [
                            {
                                "id": 6,
                                "update": "2026-07-14T10:00:00+00:00",
                                "bets": [
                                    {
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "bad"},
                                            {"value": "Draw", "odd": "3.30"},
                                            {"value": "Away", "odd": "3.80"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "price",
        ),
        (
            {
                **odds_payload(),
                "response": [
                    {
                        **odds_payload()["response"][0],
                        "bookmakers": [
                            {
                                "id": 6,
                                "update": "2026-07-14T10:00:00+00:00",
                                "bets": [
                                    {
                                        "name": "Match Winner",
                                        "values": [
                                            {"value": "Home", "odd": "0"},
                                            {"value": "Draw", "odd": "3.30"},
                                            {"value": "Away", "odd": "3.80"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "price",
        ),
        (
            {
                **football_schedule_payload(),
                "response": [
                    {
                        **football_schedule_payload()["response"][0],
                        "fixture": {
                            "id": "",
                            "date": "2026-07-14T18:00:00+00:00",
                        },
                    }
                ],
            },
            "fixture id",
        ),
    ],
)
def test_invalid_provider_shapes_raise_sanitized_errors(payload, message, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match=message):
        if "bookmakers" in json.dumps(payload):
            client.fetch_event_markets("football", "42")
        else:
            client.fetch_schedule("football", (date(2026, 7, 14),))


def test_quota_from_headers_parses_optional_integers():
    from toto_ai.external_odds.api_sports import quota_from_headers

    quota = quota_from_headers(
        {
            "x-ratelimit-requests-limit": "100",
            "x-ratelimit-requests-remaining": "88",
            "x-ratelimit-limit": "",
            "x-ratelimit-remaining": "5",
        }
    )

    assert quota == QuotaState(100, 88, None, 5)


def test_schedule_fetch_uses_unpaged_provider_contract(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    fake_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    events = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert tuple(event.provider_event_id for event in events) == ("42",)
    assert fake_session.calls[0]["params"] == {"date": "2026-07-14"}


def test_schedule_fetch_rejects_unexpected_multiple_pages(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    payload = {
        **football_schedule_payload(),
        "paging": {"current": 1, "total": 2},
    }
    fake_session = FakeSession([FakeResponse(payload=payload, headers=quota_headers())])
    client = APISportsClient("secret-key", session=fake_session, cache_dir=tmp_path)

    with pytest.raises(APISportsError, match="paging"):
        client.fetch_schedule("football", (date(2026, 7, 14),))


def test_odds_fetch_consumes_all_pages_deterministically(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    first = {**odds_payload(), "paging": {"current": 1, "total": 2}}
    second_bookmaker = {
        **odds_payload()["response"][0]["bookmakers"][0],
        "id": 7,
    }
    second = {
        **odds_payload(),
        "paging": {"current": 2, "total": 2},
        "response": [
            {
                **odds_payload()["response"][0],
                "bookmakers": [second_bookmaker],
            }
        ],
    }
    fake_session = FakeSession(
        [
            FakeResponse(payload=first, headers=quota_headers()),
            FakeResponse(payload=second, headers=quota_headers(daily_remaining="98")),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        quota_reserve=0,
    )

    markets = client.fetch_event_markets("football", "42")

    assert tuple(market.bookmaker_id for market in markets) == ("6", "7")
    assert [call["params"] for call in fake_session.calls] == [
        {"fixture": "42", "page": 1},
        {"fixture": "42", "page": 2},
    ]


def test_safety_stop_prevents_later_schedule_date_request(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    stop_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    current = [stop_at.replace(minute=59, hour=11)]

    class AdvancingSession(FakeSession):
        def get(self, *args, **kwargs):
            response = super().get(*args, **kwargs)
            current[0] = stop_at
            return response

    session = AdvancingSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        stop_at=stop_at,
        now=lambda: current[0],
    )

    with pytest.raises(APISportsError, match="safety stop"):
        client.fetch_schedule(
            "football",
            (date(2026, 7, 14), date(2026, 7, 15)),
        )

    assert len(session.calls) == 1


def test_safety_stop_prevents_later_odds_page_request(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    stop_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
    current = [stop_at.replace(minute=59, hour=11)]
    first = {**odds_payload(), "paging": {"current": 1, "total": 2}}

    class AdvancingSession(FakeSession):
        def get(self, *args, **kwargs):
            response = super().get(*args, **kwargs)
            current[0] = stop_at
            return response

    session = AdvancingSession(
        [FakeResponse(payload=first, headers=quota_headers())]
    )
    client = APISportsClient(
        "secret-key",
        session=session,
        cache_dir=tmp_path,
        quota_reserve=0,
        stop_at=stop_at,
        now=lambda: current[0],
    )

    with pytest.raises(APISportsError, match="safety stop"):
        client.fetch_event_markets("football", "42")

    assert [call["params"] for call in session.calls] == [
        {"fixture": "42", "page": 1}
    ]


@pytest.mark.parametrize(
    "pages",
    [
        ({"current": 2, "total": 2},),
        ({"current": 1, "total": 2}, {"current": 1, "total": 2}),
        ({"current": 1, "total": 2}, {"current": 2, "total": 3}),
    ],
)
def test_inconsistent_or_invalid_pagination_fails_closed(pages, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    responses = [
        FakeResponse(
            payload={**odds_payload(), "paging": paging},
            headers=quota_headers(daily_remaining=str(99 - index)),
        )
        for index, paging in enumerate(pages)
    ]
    fake_session = FakeSession(responses)
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        quota_reserve=0,
    )

    with pytest.raises(APISportsError, match="paging"):
        client.fetch_event_markets("football", "42")


def test_cache_hits_and_retries_are_accounted_separately(monkeypatch, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    monkeypatch.setattr("toto_ai.external_odds.api_sports.time.sleep", lambda _: None)
    fake_session = FakeSession(
        [
            requests.ConnectionError("network down"),
            FakeResponse(payload=football_schedule_payload(), headers=quota_headers()),
        ]
    )
    client = APISportsClient(
        "secret-key",
        session=fake_session,
        cache_dir=tmp_path,
        max_retries=1,
    )

    first = client.fetch_schedule("football", (date(2026, 7, 14),))
    second = client.fetch_schedule("football", (date(2026, 7, 14),))

    assert first == second
    assert client.requests_made == 2
    assert client.cache_hits == 1
    assert client.logical_fetches == 2


def test_cached_quota_does_not_block_fresh_request_in_new_client(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient

    first_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(minute_remaining="0"),
            )
        ]
    )
    APISportsClient(
        "secret-key",
        session=first_session,
        cache_dir=tmp_path,
        quota_reserve=0,
    ).fetch_schedule("football", (date(2026, 7, 14),))

    second_session = FakeSession(
        [FakeResponse(payload=football_schedule_payload(), headers=quota_headers())]
    )
    client = APISportsClient(
        "secret-key",
        session=second_session,
        cache_dir=tmp_path,
        quota_reserve=0,
    )

    client.fetch_schedule(
        "football",
        (date(2026, 7, 14), date(2026, 7, 15)),
    )

    assert client.cache_hits == 1
    assert client.requests_made == 1
    assert client.quota_state == QuotaState(100, 99, 10, 9)
