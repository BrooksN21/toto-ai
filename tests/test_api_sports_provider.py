from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import requests

from toto_ai.external_odds.domain import ProviderEvent, QuotaState


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


def test_quota_reserve_stops_before_request(fake_session, tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, QuotaExhausted

    client = APISportsClient(
        "secret-key", session=fake_session, cache_dir=tmp_path, quota_reserve=5
    )
    client.set_quota_for_test(QuotaState(100, 5, 10, 10))

    with pytest.raises(QuotaExhausted):
        client.fetch_event_markets("hockey", "42")

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


def test_final_provider_failure_is_sanitized_and_does_not_leak_key(tmp_path):
    from toto_ai.external_odds.api_sports import APISportsClient, APISportsError

    fake_session = FakeSession(
        [
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(),
                status_code=500,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(),
                status_code=500,
            ),
            FakeResponse(
                payload=football_schedule_payload(),
                headers=quota_headers(),
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
