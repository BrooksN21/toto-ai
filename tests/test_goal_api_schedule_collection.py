from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.goal_api import (
    GoalAPIClient,
    GoalAPIConfig,
    GoalAPIScheduleEvent,
)
from toto_ai.external_odds.schedule_source_collector import (
    _match_goal_api_candidates,
    collect_schedule_source_candidates,
)
from toto_ai.external_odds.thesportsdb import TheSportsDBConfig

UTC = timezone.utc
SECRET = "goal-collection-secret"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _queue(tmp_path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-25T17:00:00Z",
        "identity": {
            "drawing_id": 12068,
            "drawing_number": 4987,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-26T18:45:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12068,
                "drawing_number": 4987,
                "target_fingerprint": "a" * 64,
                "event_order": 0,
                "target_event_id": 190001,
                "home_team": "Викинг",
                "away_team": "Динамо Загреб",
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        ],
    }
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params)})
        requested_date = url.rsplit("/", 1)[-1]
        data = []
        if requested_date == "2026-08-26":
            data = [
                {
                    "id": 7001,
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
            ]
        return FakeResponse(
            {
                "success": True,
                "data": data,
                "pagination": {"hasMore": False},
            },
            headers={
                "X-RateLimit-Limit": "1000",
                "X-RateLimit-Remaining": "990",
            },
        )


def test_goal_api_adds_independent_non_promoting_candidate(tmp_path: Path) -> None:
    session = FakeSession()
    client = GoalAPIClient(
        SECRET,
        session=session,
        snapshot_dir=tmp_path / "out" / "goal-api-v1",
        now=lambda: datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(tmp_path),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
        goal_api_client=client,
        thesportsdb_config=TheSportsDBConfig(api_key=None),
        team_aliases={
            "Викинг": "Viking",
            "Динамо Загреб": "Dinamo Zagreb",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "goal-api-v1"
    )
    assert record["status"] == "independent_candidate"
    assert record["home_name"] == "Viking"
    assert record["away_name"] == "Dinamo Zagreb"
    assert record["starts_at"] == "2026-08-26T19:00:00Z"
    assert record["ledger_eligible"] is False
    assert record["missing_requirements"] == ["official_source", "review"]
    assert result.provider_statuses["goal-api-v1"]["candidate_count"] == 1
    assert result.provider_statuses["goal-api-v1"]["ledger_mutated"] is False
    assert len(session.calls) == 6


def test_goal_api_can_be_disabled_without_affecting_other_sources(
    tmp_path: Path,
) -> None:
    result = collect_schedule_source_candidates(
        _queue(tmp_path),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
        goal_api_config=GoalAPIConfig(api_key=None),
        thesportsdb_config=TheSportsDBConfig(api_key=None),
    )

    assert result.provider_statuses["goal-api-v1"]["status"] == (
        "disabled_missing_key"
    )
    assert all(
        item.get("source_provider") != "goal-api-v1" for item in result.records
    )


def test_match_before_drawing_deadline_on_same_moscow_day_is_eligible(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    payload = json.loads(queue.read_text(encoding="utf-8"))
    payload["identity"]["deadline"] = "2026-08-26T20:00:00Z"
    payload.pop("queue_sha256")
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    queue.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    client = GoalAPIClient(
        SECRET,
        session=FakeSession(),
        snapshot_dir=tmp_path / "out" / "goal-api-v1",
        now=lambda: datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
        goal_api_client=client,
        thesportsdb_config=TheSportsDBConfig(api_key=None),
        team_aliases={
            "Викинг": "Viking",
            "Динамо Загреб": "Dinamo Zagreb",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "goal-api-v1"
    )
    assert record["status"] == "independent_candidate"
    assert record["status_eligible"] is True
    assert "starts_before_drawing_deadline" not in record["missing_requirements"]
    assert result.provider_statuses["goal-api-v1"]["matched_count"] == 1
    assert result.provider_statuses["goal-api-v1"]["timing_conflict_count"] == 0


def test_goal_candidate_fallback_handles_unseen_cross_script_name_variants() -> None:
    event = GoalAPIScheduleEvent(
        provider_event_id="7002",
        competition="League Cup",
        home_team="Bradford City",
        away_team="Burnley",
        starts_at=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        status="scheduled",
        eligible=True,
        captured_at=datetime(2026, 8, 25, 17, 0, tzinfo=UTC),
        payload_hash="c" * 64,
        source_endpoint="/fixtures/date/2026-08-26",
        request_fingerprint="d" * 64,
    )
    row = {
        "drawing_id": 12068,
        "drawing_number": 4987,
        "target_event_id": 190003,
        "event_order": 2,
        "home_team": "Брэдфорд",
        "away_team": "Бернли",
    }

    selected, orientation, candidate_ids, status = _match_goal_api_candidates(
        row,
        (event,),
        aliases={},
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
    )

    assert selected == event
    assert orientation == "same"
    assert candidate_ids == ("7002",)
    assert status.startswith("fuzzy_candidate_margin_")
