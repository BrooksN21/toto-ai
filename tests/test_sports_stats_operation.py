from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.external_odds.api_sports import (
    APISportsClient,
    APISportsJSONPayload,
)
from toto_ai.external_odds.domain import QuotaState, TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.operation import collect_and_store_sports_stats

UTC = timezone.utc
AS_OF = datetime(2026, 7, 29, 9, tzinfo=UTC)
DEADLINE = datetime(2026, 7, 29, 12, tzinfo=UTC)
TARGET_START = datetime(2026, 7, 29, 13, tzinfo=UTC)


class ExplodingTotoBriefClient:
    def drawing_info(self, drawing_id):
        raise AssertionError(f"historical mode made a network call for {drawing_id}")


class StaticTotoBriefClient:
    def drawing_info(self, drawing_id):
        assert drawing_id == 99
        return raw_payload()


class Response:
    status_code = 200
    headers = {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "99",
        "x-ratelimit-limit": "100",
        "x-ratelimit-remaining": "99",
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
        raise AssertionError("historical sports-stat replay attempted network access")


class FrozenAPISportsClient:
    quota_state = QuotaState(100, 90, 10, 9)
    requests_made = 0
    cache_hits = 45

    def __init__(self):
        self.calls = []

    def fetch_football_fixture_payload(
        self,
        fixture_id,
        *,
        as_of,
        cache_only,
    ):
        assert cache_only is True
        assert as_of == AS_OF
        self.calls.append(("fixture", fixture_id))
        order = int(fixture_id) - 1000
        return api_payload(
            "/fixtures",
            [
                {
                    "fixture": {
                        "id": int(fixture_id),
                        "date": (
                            TARGET_START + timedelta(minutes=order)
                        ).isoformat(),
                        "status": {"short": "NS"},
                    },
                    "league": {
                        "id": 39,
                        "season": 2026,
                        "standings": True,
                    },
                    "teams": {
                        "home": {"id": 2000 + order * 2},
                        "away": {"id": 2001 + order * 2},
                    },
                    "goals": {"home": None, "away": None},
                }
            ],
        )

    def fetch_football_team_fixtures_payload(
        self,
        team_id,
        season,
        *,
        limit,
        as_of,
        cache_only,
        historical_from,
        historical_to,
    ):
        assert cache_only is True
        assert as_of == AS_OF
        assert season == 2026
        assert limit == 10
        assert historical_from is not None
        assert historical_to is not None
        self.calls.append(("history", team_id))
        return api_payload(
            "/fixtures",
            [
                {
                    "fixture": {
                        "id": 50000 + int(team_id),
                        "date": (AS_OF - timedelta(days=4)).isoformat(),
                        "status": {"short": "FT"},
                    },
                    "league": {"id": 39, "season": 2026},
                    "teams": {
                        "home": {"id": int(team_id)},
                        "away": {"id": 90000 + int(team_id)},
                    },
                    "goals": {"home": 2, "away": 1},
                }
            ],
        )

    def fetch_football_standings_payload(
        self,
        league_id,
        season,
        *,
        as_of,
        cache_only,
    ):
        assert cache_only is True
        assert as_of == AS_OF
        self.calls.append(("standings", league_id))
        return api_payload(
            "/standings",
            [
                {
                    "league": {
                        "id": int(league_id),
                        "season": season,
                        "standings": [
                            [
                                {
                                    "rank": index + 1,
                                    "team": {"id": team_id},
                                    "points": 3,
                                    "all": {
                                        "played": 1,
                                        "win": 1,
                                        "draw": 0,
                                        "lose": 0,
                                        "goals": {"for": 2, "against": 1},
                                    },
                                }
                                for index, team_id in enumerate(range(2000, 2030))
                            ]
                        ],
                    }
                }
            ],
        )


def api_payload(endpoint, response):
    return APISportsJSONPayload(
        endpoint=endpoint,
        params=(("frozen", "1"),),
        payload={
            "errors": [],
            "results": len(response),
            "paging": {"current": 1, "total": 1},
            "response": response,
        },
        fetched_at=AS_OF - timedelta(minutes=5),
    )


def wire_payload(response):
    return {
        "errors": [],
        "results": len(response),
        "timestamp": int(AS_OF.timestamp()),
        "paging": {"current": 1, "total": 1},
        "response": response,
    }


def target_fixture_row(order):
    return {
        "fixture": {
            "id": 1000 + order,
            "date": (TARGET_START + timedelta(minutes=order)).isoformat(),
            "status": {"short": "NS"},
        },
        "league": {
            "id": 39,
            "season": 2026,
            "standings": True,
        },
        "teams": {
            "home": {"id": 2000 + order * 2},
            "away": {"id": 2001 + order * 2},
        },
        "goals": {"home": None, "away": None},
    }


def history_fixture_row(team_id, *, home):
    opponent_id = 90000 + team_id
    return {
        "fixture": {
            "id": 50000 + team_id,
            "date": (AS_OF - timedelta(days=4)).isoformat(),
            "status": {"short": "FT"},
        },
        "league": {"id": 39, "season": 2026},
        "teams": {
            "home": {"id": team_id if home else opponent_id},
            "away": {"id": opponent_id if home else team_id},
        },
        "goals": {"home": 2, "away": 1},
    }


def standings_response():
    return [
        {
            "league": {
                "id": 39,
                "season": 2026,
                "standings": [
                    [
                        {
                            "rank": index + 1,
                            "team": {"id": team_id},
                            "points": 3,
                            "all": {
                                "played": 1,
                                "win": 1,
                                "draw": 0,
                                "lose": 0,
                                "goals": {"for": 2, "against": 1},
                            },
                        }
                        for index, team_id in enumerate(range(2000, 2030))
                    ]
                ],
            }
        }
    ]


def prospective_responses():
    responses = []
    for order in range(15):
        responses.append(wire_payload([target_fixture_row(order)]))
        home_team_id = 2000 + order * 2
        away_team_id = home_team_id + 1
        responses.append(
            wire_payload([history_fixture_row(home_team_id, home=True)])
        )
        responses.append(
            wire_payload([history_fixture_row(away_team_id, home=False)])
        )
        if order == 0:
            responses.append(wire_payload(standings_response()))
    return responses


def target_and_pins():
    events = tuple(
        TargetEvent(
            drawing_id=99,
            drawing_number=5002,
            event_id=5000 + order,
            event_order=order,
            sport="football",
            championship="Test",
            starts_at=TARGET_START + timedelta(minutes=order),
            deadline=DEADLINE,
            home_team=f"Home {order}",
            away_team=f"Away {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.4, 0.3, 0.3),
        )
        for order in range(15)
    )
    target = TargetDrawing(
        drawing_id=99,
        drawing_number=5002,
        deadline=DEADLINE,
        fetched_at=AS_OF - timedelta(minutes=10),
        events=events,
    )
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    pins = tuple(
        DrawingEventPinRecord(
            id=order + 1,
            drawing_id=99,
            drawing_fingerprint=fingerprint,
            target_event_id=str(5000 + order),
            event_order=order,
            provider="api-sports",
            canonical_home_team_id=3000 + order * 2,
            canonical_away_team_id=3001 + order * 2,
            provider_home_team_id=str(2000 + order * 2),
            provider_away_team_id=str(2001 + order * 2),
            provider_fixture_id=str(1000 + order),
            starts_at=(TARGET_START + timedelta(minutes=order)).isoformat(),
            collection_id=None,
            provenance={},
            pin_hash="c" * 64,
            status="valid",
            created_at=(AS_OF - timedelta(hours=1)).isoformat(),
            invalidated_at=None,
            invalidation_reason=None,
        )
        for order in range(15)
    )
    return target, pins


def raw_payload():
    return {
        "data": {
            "id": 99,
            "number": 5002,
            "ended_at": DEADLINE.isoformat(),
            "events": [
                {
                    "id": 5000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "quotes": {
                        "pool_win_1": 34,
                        "pool_draw": 33,
                        "pool_win_2": 33,
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }


def call_historical(monkeypatch, tmp_path, *, raw_fetched_at):
    target, pins = target_and_pins()
    raw_dir = tmp_path / "raw"
    write_drawing_detail_cache(
        raw_payload(),
        drawing_id=99,
        cache_dir=raw_dir,
        fetched_at=raw_fetched_at,
        source="frozen-test",
        allowed_root=tmp_path,
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.resolve_drawing_reference",
        lambda *args, **kwargs: SimpleNamespace(drawing_id=99, number=5002),
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.parse_target_drawing",
        lambda payload, fetched_at: target,
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.load_ready_drawing_pins",
        lambda *args, **kwargs: pins,
    )
    provider = FrozenAPISportsClient()
    result = collect_and_store_sports_stats(
        db=str(tmp_path / "toto.db"),
        open_drawing=False,
        drawing_id=None,
        drawing_number=5002,
        history_size=10,
        report_dir=str(tmp_path / "reports"),
        cache_root=str(tmp_path / "api-cache"),
        raw_cache_dir=str(raw_dir),
        env_file=str(tmp_path / ".env"),
        historical_as_of=AS_OF,
        now=AS_OF + timedelta(hours=1),
        totobrief_client=ExplodingTotoBriefClient(),
        provider_client=provider,
    )
    return result, provider


def test_historical_collection_is_frozen_cache_only_and_report_deterministic(
    monkeypatch,
    tmp_path,
):
    (first, first_paths), first_provider = call_historical(
        monkeypatch,
        tmp_path,
        raw_fetched_at=AS_OF - timedelta(minutes=10),
    )
    first_bytes = tuple(path.read_bytes() for path in first_paths)
    (second, second_paths), second_provider = call_historical(
        monkeypatch,
        tmp_path,
        raw_fetched_at=AS_OF - timedelta(minutes=10),
    )

    assert first == second
    assert first.run_id == second.run_id
    assert tuple(path.read_bytes() for path in second_paths) == first_bytes
    assert first_provider.requests_made == 0
    assert second_provider.requests_made == 0
    assert first_provider.calls
    assert second_provider.calls


def test_prospective_cache_replays_historically_without_network(
    monkeypatch,
    tmp_path,
):
    target, pins = target_and_pins()
    raw_dir = tmp_path / "raw"
    api_cache = tmp_path / "api-cache"
    report_dir = tmp_path / "reports"
    write_drawing_detail_cache(
        raw_payload(),
        drawing_id=99,
        cache_dir=raw_dir,
        fetched_at=AS_OF - timedelta(minutes=1),
        source="frozen-test",
        allowed_root=tmp_path,
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.resolve_drawing_reference",
        lambda *args, **kwargs: SimpleNamespace(drawing_id=99, number=5002),
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.parse_target_drawing",
        lambda payload, fetched_at: target,
    )
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.load_ready_drawing_pins",
        lambda *args, **kwargs: pins,
    )
    warming_session = Session(prospective_responses())
    prospective, prospective_paths = collect_and_store_sports_stats(
        db=str(tmp_path / "toto.db"),
        open_drawing=False,
        drawing_id=None,
        drawing_number=5002,
        history_size=10,
        report_dir=str(report_dir),
        cache_root=str(api_cache),
        raw_cache_dir=str(raw_dir),
        env_file=str(tmp_path / ".env"),
        historical_as_of=None,
        now=AS_OF,
        totobrief_client=StaticTotoBriefClient(),
        provider_client=APISportsClient(
            "secret-key",
            session=warming_session,
            cache_dir=api_cache,
        ),
    )
    prospective_bytes = tuple(path.read_bytes() for path in prospective_paths)

    def replay():
        client = APISportsClient(
            "secret-key",
            session=ExplodingSession(),
            cache_dir=api_cache,
        )
        result = collect_and_store_sports_stats(
            db=str(tmp_path / "toto.db"),
            open_drawing=False,
            drawing_id=None,
            drawing_number=5002,
            history_size=10,
            report_dir=str(report_dir),
            cache_root=str(api_cache),
            raw_cache_dir=str(raw_dir),
            env_file=str(tmp_path / ".env"),
            historical_as_of=AS_OF,
            now=AS_OF + timedelta(hours=1),
            totobrief_client=ExplodingTotoBriefClient(),
            provider_client=client,
        )
        return result, client

    (first, first_paths), first_client = replay()
    first_bytes = tuple(path.read_bytes() for path in first_paths)
    (second, second_paths), second_client = replay()

    assert len(warming_session.calls) == 46
    assert prospective.events == first.events == second.events
    assert first_bytes == prospective_bytes
    assert tuple(path.read_bytes() for path in second_paths) == first_bytes
    assert first_client.requests_made == second_client.requests_made == 0
    assert first_client.cache_hits == second_client.cache_hits == 46


def test_historical_collection_rejects_detail_captured_after_as_of(
    monkeypatch,
    tmp_path,
):
    with pytest.raises(ValueError, match="captured after as-of"):
        call_historical(
            monkeypatch,
            tmp_path,
            raw_fetched_at=AS_OF + timedelta(minutes=1),
        )


def test_historical_collection_rejects_missing_raw_detail_before_provider_access(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "toto_ai.sports_stats.operation.resolve_drawing_reference",
        lambda *args, **kwargs: SimpleNamespace(drawing_id=99, number=5002),
    )
    provider = FrozenAPISportsClient()

    with pytest.raises(ValueError, match="drawing detail cache is missing"):
        collect_and_store_sports_stats(
            db=str(tmp_path / "toto.db"),
            open_drawing=False,
            drawing_id=99,
            drawing_number=None,
            history_size=10,
            report_dir=str(tmp_path / "reports"),
            cache_root=str(tmp_path / "api-cache"),
            raw_cache_dir=str(tmp_path / "raw"),
            env_file=str(tmp_path / ".env"),
            historical_as_of=AS_OF,
            now=AS_OF + timedelta(hours=1),
            totobrief_client=ExplodingTotoBriefClient(),
            provider_client=provider,
        )

    assert provider.calls == []
