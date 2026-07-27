from datetime import date, datetime, timedelta, timezone

import pytest

from toto_ai.external_odds.api_sports import (
    APISportsClient,
    APISportsJSONPayload,
    HistoricalCacheUnavailable,
    ProviderPlanUnavailable,
)
from toto_ai.external_odds.domain import QuotaState
from toto_ai.sports_stats.api_sports import APISportsFootballStatsProvider

UTC = timezone.utc


class Response:
    status_code = 200
    headers = {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "x-ratelimit-limit": "10",
        "x-ratelimit-remaining": "9",
    }

    def __init__(self, value):
        self.value = value

    def json(self):
        return self.value


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, headers, params, timeout):
        self.calls.append((url, headers, params, timeout))
        return Response(self.responses.pop(0))


class ExplodingSession:
    def get(self, *args, **kwargs):
        raise AssertionError("cache-only historical replay attempted network access")


class FakeClient:
    quota_state = QuotaState(100, 90, 10, 9)
    requests_made = 3
    cache_hits = 0

    def __init__(self, target, history, standings):
        self.target = target
        self.history = history
        self.standings = standings

    def fetch_football_fixture_payload(self, *args, **kwargs):
        return self.target

    def fetch_football_team_fixtures_payload(self, *args, **kwargs):
        return self.history

    def fetch_football_standings_payload(self, *args, **kwargs):
        return self.standings


def payload(endpoint, response):
    return APISportsJSONPayload(
        endpoint=endpoint,
        params=(("x", "1"),),
        payload={
            "errors": [],
            "results": len(response),
            "paging": {"current": 1, "total": 1},
            "response": response,
        },
        fetched_at=datetime(2026, 7, 20, tzinfo=UTC),
    )


def fixture_row(
    fixture_id,
    at,
    status="FT",
    home=10,
    away=20,
    goals=(2, 1),
):
    return {
        "fixture": {
            "id": fixture_id,
            "date": at,
            "status": {"short": status},
        },
        "league": {"id": 39, "season": 2026, "standings": True},
        "teams": {"home": {"id": home}, "away": {"id": away}},
        "goals": {"home": goals[0], "away": goals[1]},
    }


def test_adapter_rejects_cancelled_postponed_and_future_history():
    target = payload(
        "/fixtures",
        [fixture_row(99, "2026-07-30T18:00:00+00:00", status="NS")],
    )
    history = payload(
        "/fixtures",
        [
            fixture_row(1, "2026-07-20T18:00:00+00:00", status="FT"),
            fixture_row(2, "2026-07-21T18:00:00+00:00", status="PST"),
            fixture_row(3, "2026-07-22T18:00:00+00:00", status="CANC"),
            fixture_row(4, "2026-07-29T12:00:00+00:00", status="FT"),
            fixture_row(99, "2026-07-30T18:00:00+00:00", status="NS"),
        ],
    )
    standings = payload("/standings", [])
    provider = APISportsFootballStatsProvider(
        FakeClient(target, history, standings)
    )

    context = provider.fetch_target_fixture("99")
    fixtures = provider.fetch_completed_fixtures(
        "10",
        2026,
        cutoff=datetime(2026, 7, 29, 10, tzinfo=UTC),
        limit=10,
        target_fixture_id="99",
    )

    assert context.provider_fixture_id == "99"
    assert context.league_id == "39"
    assert context.season == 2026
    assert context.standings_supported is True
    assert tuple(item.provider_fixture_id for item in fixtures) == ("1",)


def test_adapter_ignores_history_rows_for_a_different_team():
    target = payload(
        "/fixtures",
        [fixture_row(99, "2026-07-30T18:00:00+00:00", status="NS")],
    )
    history = payload(
        "/fixtures",
        [
            fixture_row(
                1,
                "2026-07-20T18:00:00+00:00",
                home=30,
                away=40,
            )
        ],
    )
    history.payload["response"][0].pop("goals")
    provider = APISportsFootballStatsProvider(
        FakeClient(target, history, payload("/standings", []))
    )

    fixtures = provider.fetch_completed_fixtures(
        "10",
        2026,
        cutoff=datetime(2026, 7, 29, 10, tzinfo=UTC),
        limit=10,
        target_fixture_id="99",
    )

    assert fixtures == ()


def test_adapter_flattens_standing_groups_for_requested_season():
    target = payload("/fixtures", [])
    history = payload("/fixtures", [])
    standings = payload(
        "/standings",
        [
            {
                "league": {
                    "id": 39,
                    "season": 2026,
                    "standings": [
                        [
                            {
                                "rank": 1,
                                "team": {"id": 10},
                                "points": 6,
                                "all": {
                                    "played": 2,
                                    "win": 2,
                                    "draw": 0,
                                    "lose": 0,
                                    "goals": {"for": 4, "against": 1},
                                },
                            }
                        ]
                    ],
                }
            }
        ],
    )
    provider = APISportsFootballStatsProvider(
        FakeClient(target, history, standings)
    )

    rows = provider.fetch_standings("39", 2026)

    assert len(rows) == 1
    assert rows[0].team_id == "10"
    assert rows[0].rank == 1
    assert rows[0].points == 6


def test_existing_transport_uses_finished_status_and_never_serializes_key(tmp_path):
    response = {
        "errors": [],
        "results": 0,
        "timestamp": int(datetime(2026, 7, 20, tzinfo=UTC).timestamp()),
        "paging": {"current": 1, "total": 1},
        "response": [],
    }
    session = Session([response])
    client = APISportsClient("secret-key", session=session, cache_dir=tmp_path)

    result = client.fetch_football_team_fixtures_payload(
        "10",
        2026,
        limit=10,
    )

    assert result.endpoint == "/fixtures"
    assert session.calls[0][2] == {
        "last": 10,
        "season": 2026,
        "status": "FT-AET-PEN",
        "team": "10",
        "timezone": "UTC",
    }
    assert "secret-key" not in next(tmp_path.glob("*.json")).read_text()


def test_free_plan_denial_is_explicit_and_sanitized(tmp_path):
    response = {
        "errors": {"plan": "secret provider detail"},
        "results": 0,
        "paging": {"current": 1, "total": 1},
        "response": [],
    }
    client = APISportsClient(
        "secret-key",
        session=Session([response]),
        cache_dir=tmp_path,
    )

    try:
        client.fetch_football_team_fixtures_payload("10", 2026, limit=10)
    except ProviderPlanUnavailable as error:
        assert str(error) == "API-Sports plan does not provide the requested data"
        assert "secret" not in str(error)
    else:
        raise AssertionError("plan denial was not surfaced")


def test_historical_cache_replay_is_deterministic_and_never_uses_network(
    tmp_path,
):
    fetched_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    responses = []
    for rows in (
        [fixture_row(99, "2026-07-30T18:00:00+00:00", status="NS")],
        [fixture_row(1, "2026-07-19T18:00:00+00:00", status="FT")],
        [],
    ):
        responses.append(
            {
                "errors": [],
                "results": len(rows),
                "timestamp": int(fetched_at.timestamp()),
                "paging": {"current": 1, "total": 1},
                "response": rows,
            }
        )
    warming = APISportsClient(
        "secret-key",
        session=Session(responses),
        cache_dir=tmp_path,
    )
    warming.fetch_football_fixture_payload("99")
    prospective_history = warming.fetch_football_team_fixtures_payload(
        "10",
        2026,
        limit=10,
    )
    warming.fetch_football_standings_payload("39", 2026)

    replay = APISportsClient(
        "secret-key",
        session=ExplodingSession(),
        cache_dir=tmp_path,
    )
    as_of = fetched_at + timedelta(minutes=1)
    first = (
        replay.fetch_football_fixture_payload(
            "99",
            as_of=as_of,
            cache_only=True,
        ),
        replay.fetch_football_team_fixtures_payload(
            "10",
            2026,
            limit=10,
            historical_from=date(2025, 7, 20),
            historical_to=date(2026, 7, 20),
            as_of=as_of,
            cache_only=True,
        ),
        replay.fetch_football_standings_payload(
            "39",
            2026,
            as_of=as_of,
            cache_only=True,
        ),
    )
    second = (
        replay.fetch_football_fixture_payload(
            "99",
            as_of=as_of,
            cache_only=True,
        ),
        replay.fetch_football_team_fixtures_payload(
            "10",
            2026,
            limit=10,
            historical_from=date(2025, 7, 20),
            historical_to=date(2026, 7, 20),
            as_of=as_of,
            cache_only=True,
        ),
        replay.fetch_football_standings_payload(
            "39",
            2026,
            as_of=as_of,
            cache_only=True,
        ),
    )

    assert first == second
    assert first[1] == prospective_history
    assert first[1].params == (
        ("last", "10"),
        ("season", "2026"),
        ("status", "FT-AET-PEN"),
        ("team", "10"),
        ("timezone", "UTC"),
    )
    assert replay.requests_made == 0
    assert replay.cache_hits == 6


def test_historical_replay_rejects_compatible_cache_captured_after_as_of(
    tmp_path,
):
    fetched_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    response = {
        "errors": [],
        "results": 1,
        "timestamp": int(fetched_at.timestamp()),
        "paging": {"current": 1, "total": 1},
        "response": [
            fixture_row(1, "2026-07-19T18:00:00+00:00", status="FT")
        ],
    }
    warming = APISportsClient(
        "secret-key",
        session=Session([response]),
        cache_dir=tmp_path,
    )
    warming.fetch_football_team_fixtures_payload("10", 2026, limit=10)
    replay = APISportsClient(
        "secret-key",
        session=ExplodingSession(),
        cache_dir=tmp_path,
    )

    with pytest.raises(HistoricalCacheUnavailable):
        replay.fetch_football_team_fixtures_payload(
            "10",
            2026,
            limit=10,
            historical_from=date(2025, 7, 20),
            historical_to=date(2026, 7, 20),
            as_of=fetched_at - timedelta(microseconds=1),
            cache_only=True,
        )

    assert replay.requests_made == 0
    assert replay.cache_hits == 0
