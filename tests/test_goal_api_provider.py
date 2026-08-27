from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from toto_ai.external_odds.goal_api import (
    DEFAULT_BASE_URL,
    GOAL_API_KEY_ENV,
    USER_AGENT,
    GoalAPIClient,
    GoalAPIConfig,
    GoalAPIDisabledError,
    load_goal_api_config,
    load_goal_api_key,
)

UTC = timezone.utc
SECRET = "goal-test-secret"


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected GOAL API request")
        return self.responses.pop(0)


def _fixture(*, event_id: int = 7001) -> dict[str, object]:
    return {
        "id": event_id,
        "apiId": 9001,
        "homeTeamName": "Viking",
        "awayTeamName": "Dinamo Zagreb",
        "homeTeamId": 101,
        "awayTeamId": 102,
        "kickoffUtc": "2026-08-26T19:00:00Z",
        "leagueName": "UEFA Champions League Qualification",
        "leagueId": 11,
        "matchStatus": "Not Started",
    }


def _now() -> datetime:
    return datetime(2026, 8, 25, 17, 0, tzinfo=UTC)


def test_config_requires_explicit_key_and_rejects_non_official_host() -> None:
    missing = load_goal_api_config({})
    configured = load_goal_api_config({GOAL_API_KEY_ENV: SECRET})

    assert missing.enabled is False
    assert configured.enabled is True
    assert configured.api_key == SECRET
    assert SECRET not in repr(configured)
    with pytest.raises(ValueError, match="official HTTPS"):
        GoalAPIConfig(api_key=SECRET, base_url="https://example.com/v1")


def test_missing_key_fails_before_transport(tmp_path: Path) -> None:
    session = FakeSession([])

    with pytest.raises(GoalAPIDisabledError, match=GOAL_API_KEY_ENV):
        GoalAPIClient("", session=session, snapshot_dir=tmp_path)

    assert session.calls == []


def test_key_loader_reads_only_secure_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(GOAL_API_KEY_ENV, raising=False)
    path = tmp_path / ".env"
    path.write_text(f"GOAL_API_KEY={SECRET}\n", encoding="utf-8")
    path.chmod(0o600)

    assert load_goal_api_key(path) == SECRET

    path.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        load_goal_api_key(path)


def test_fetch_schedule_paginates_and_freezes_secret_safe_evidence(
    tmp_path: Path,
) -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "success": True,
                    "data": [_fixture()],
                    "pagination": {"hasMore": True, "nextOffset": 1},
                },
                headers={
                    "X-RateLimit-Limit": "1000",
                    "X-RateLimit-Remaining": "999",
                    "X-RateLimit-Reset": "123456",
                },
            ),
            FakeResponse(
                {
                    "success": True,
                    "data": [],
                    "pagination": {"hasMore": False},
                },
                headers={
                    "X-RateLimit-Limit": "1000",
                    "X-RateLimit-Remaining": "998",
                    "X-RateLimit-Reset": "123456",
                },
            ),
        ]
    )
    client = GoalAPIClient(
        SECRET,
        session=session,
        snapshot_dir=tmp_path,
        now=_now,
    )

    events = client.fetch_schedule((date(2026, 8, 26),))

    assert len(events) == 1
    event = events[0]
    assert event.provider_event_id == "7001"
    assert event.home_team == "Viking"
    assert event.away_team == "Dinamo Zagreb"
    assert event.starts_at == datetime(2026, 8, 26, 19, 0, tzinfo=UTC)
    assert event.status == "not_started"
    assert event.eligible is True
    assert event.provider_home_team_id == "101"
    assert event.provider_away_team_id == "102"
    assert client.requests_made == 2
    assert client.quota_state.daily_remaining == 998
    assert session.calls[0]["url"] == (
        f"{DEFAULT_BASE_URL}/fixtures/date/2026-08-26"
    )
    assert session.calls[0]["headers"]["User-Agent"] == USER_AGENT
    assert session.calls[0]["headers"]["Authorization"] == f"Bearer {SECRET}"
    artifacts = "\n".join(
        path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.json")
    )
    assert SECRET not in artifacts
    for evidence in client.request_evidence:
        document = json.loads(evidence.snapshot_path.read_text(encoding="utf-8"))
        assert "Authorization" not in json.dumps(document)


def test_fetch_team_results_binds_identity_and_freezes_secret_safe_payload(
    tmp_path: Path,
) -> None:
    payload = {
        "success": True,
        "teamId": "team-101",
        "data": [
            {
                "id": "history-1",
                "matchStatus": "FINISHED",
                "kickoffUtc": "2026-08-20T18:00:00Z",
                "homeTeamId": "team-101",
                "awayTeamId": "team-202",
                "homeTeamScore": "2",
                "awayTeamScore": "1",
            }
        ],
    }
    session = FakeSession(
        [
            FakeResponse(
                payload,
                headers={"X-RateLimit-Remaining": "997"},
            )
        ]
    )
    client = GoalAPIClient(
        SECRET,
        session=session,
        snapshot_dir=tmp_path,
        now=_now,
    )

    result = client.fetch_team_results("team-101")

    assert result.team_id == "team-101"
    assert result.payload == payload
    assert result.http_status == 200
    assert result.quota_daily_remaining == 997
    assert session.calls[0]["url"] == f"{DEFAULT_BASE_URL}/teams/team-101/results"
    assert session.calls[0]["params"] == {"limit": "10"}
    frozen = result.evidence.snapshot_path.read_text(encoding="utf-8")
    assert SECRET not in frozen
    assert json.loads(frozen)["payload"] == payload


def test_fetch_team_results_rejects_unsafe_identity_before_transport(
    tmp_path: Path,
) -> None:
    session = FakeSession([])
    client = GoalAPIClient(
        SECRET,
        session=session,
        snapshot_dir=tmp_path,
        now=_now,
    )

    with pytest.raises(ValueError, match="unsupported characters"):
        client.fetch_team_results("../secret")

    assert session.calls == []


def test_finished_fixture_is_retained_but_not_eligible(tmp_path: Path) -> None:
    fixture = _fixture()
    fixture["matchStatus"] = "Finished"
    session = FakeSession(
        [
            FakeResponse(
                {
                    "success": True,
                    "data": [fixture],
                    "pagination": {"hasMore": False},
                }
            )
        ]
    )
    client = GoalAPIClient(
        SECRET,
        session=session,
        snapshot_dir=tmp_path,
        now=_now,
    )

    event = client.fetch_schedule((date(2026, 8, 26),))[0]

    assert event.status == "finished"
    assert event.eligible is False
