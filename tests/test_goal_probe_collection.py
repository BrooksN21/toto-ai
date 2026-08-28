from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.external_odds.goal_api import GoalAPIClient
from toto_ai.sports_stats import goal_probe_collection
from toto_ai.sports_stats.goal_probe_collection import (
    collect_goal_probe_input,
    ensure_goal_probe_input,
)
from toto_ai.sports_stats.goal_probe_research import load_goal_probe_shadow

UTC = timezone.utc


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append(url)
        if "/teams/" in url:
            team_id = url.split("/teams/", 1)[1].split("/", 1)[0]
            order = int(team_id.rsplit("-", 1)[1])
            side = "home" if "home" in team_id else "away"
            opponent = f"opponent-{order}-{side}"
            return FakeResponse(
                {
                    "success": True,
                    "teamId": team_id,
                    "data": [
                        {
                            "id": f"history-{team_id}",
                            "matchStatus": "FINISHED",
                            "kickoffUtc": "2026-08-20T16:00:00Z",
                            "homeTeamId": team_id if side == "home" else opponent,
                            "awayTeamId": opponent if side == "home" else team_id,
                            "homeTeamScore": "2",
                            "awayTeamScore": "1",
                        }
                    ],
                },
                headers={"X-RateLimit-Remaining": "900"},
            )
        requested_date = url.rsplit("/", 1)[-1]
        fixtures = []
        if requested_date == "2026-08-27":
            fixtures = [
                {
                    "id": f"fixture-{order}",
                    "homeTeamName": f"Home {order + 1}",
                    "awayTeamName": f"Away {order + 1}",
                    "homeTeamId": f"home-{order}",
                    "awayTeamId": f"away-{order}",
                    "kickoffUtc": f"2026-08-27T16:{order:02d}:00Z",
                    "leagueName": "Test League",
                    "matchStatus": "SCHEDULED",
                }
                for order in range(15)
            ]
        return FakeResponse(
            {
                "success": True,
                "data": fixtures,
                "pagination": {"hasMore": False},
            },
            headers={"X-RateLimit-Remaining": "950"},
        )


class PartialFakeSession(FakeSession):
    missing_orders = frozenset({3, 7, 8, 11, 14})

    def get(self, url, *, params, headers, timeout):
        response = super().get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if "/fixtures/date/" in url and isinstance(response.payload, dict):
            values = response.payload.get("data")
            if isinstance(values, list):
                response.payload["data"] = [
                    row
                    for row in values
                    if int(str(row["id"]).rsplit("-", 1)[1])
                    not in self.missing_orders
                ]
        return response


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_inputs(root: Path) -> Path:
    deadline = "2026-08-27T19:00:00Z"
    events = []
    records = []
    for order in range(15):
        event_id = 200000 + order
        events.append(
            {
                "id": event_id,
                "order": order,
                "name": f"Home {order + 1} — Away {order + 1}",
                "championship": "Test football",
                "start_at": None,
                "quotes": {
                    "bk_win_1": 40,
                    "bk_draw": 30,
                    "bk_win_2": 30,
                    "pool_win_1": 40,
                    "pool_draw": 30,
                    "pool_win_2": 30,
                },
                "result": None,
                "score": None,
            }
        )
        records.append(
            {
                "status": "awaiting_review",
                "drawing_id": 12071,
                "drawing_number": 4988,
                "target_fingerprint": "a" * 64,
                "event_order": order,
                "target_event_id": event_id,
                "home_team": f"Home {order + 1}",
                "away_team": f"Away {order + 1}",
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        )
    write_drawing_detail_cache(
        {
            "version": "test",
            "data": {
                "id": 12071,
                "number": 4988,
                "name": "baltbet-main",
                "ended_at": deadline,
                "status": "open",
                "pool_sum": 1000,
                "jackpot": 0,
                "payments": [],
                "events": events,
            },
        },
        drawing_id=12071,
        cache_dir=root / "data" / "raw",
        fetched_at=datetime(2026, 8, 27, 7, 30, tzinfo=UTC),
        source="test",
        allowed_root=root,
    )
    queue = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-27T07:30:00Z",
        "identity": {
            "drawing_id": 12071,
            "drawing_number": 4988,
            "drawing_fingerprint": "a" * 64,
            "deadline": deadline,
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": records,
    }
    queue["queue_sha256"] = hashlib.sha256(_canonical(queue)).hexdigest()
    queue_path = root / "queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    return queue_path


def test_collect_goal_probe_builds_adapter_compatible_15_event_input(
    tmp_path: Path,
) -> None:
    queue = _write_inputs(tmp_path)
    session = FakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    client = GoalAPIClient(
        "test-secret",
        session=session,
        snapshot_dir=(
            tmp_path / "reports" / "goal-full-probe" / "schedule" / "goal-api-v1"
        ),
        request_budget=120,
        now=lambda: observed,
    )

    result = collect_goal_probe_input(
        drawing_id=12071,
        queue_path=queue,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_dir=tmp_path / "reports" / "goal-full-probe",
        client=client,
        project_root=tmp_path,
        captured_at=observed,
    )

    assert result.event_count == 15
    assert result.history_source_count == 30
    assert result.sports_eligible_count == 15
    assert result.request_count == 36
    coverage = json.loads(result.coverage_summary_path.read_text(encoding="utf-8"))
    assert len(coverage["events"]) == 15
    assert all(len(row["sources"]) == 2 for row in coverage["events"])
    frozen = "\n".join(
        path.read_text(encoding="utf-8")
        for path in result.coverage_summary_path.parent.glob("*.json")
    )
    assert "test-secret" not in frozen

    bundle = load_goal_probe_shadow(
        drawing_id=12071,
        as_of=result.captured_at,
        raw_cache_dir=tmp_path / "data" / "raw",
        coverage_summary_path=result.coverage_summary_path,
        project_root=tmp_path,
    )

    assert bundle.shadow.sports_coverage_count == 15
    assert bundle.shadow.fallback_count == 0


def test_collect_goal_probe_keeps_15_events_with_explicit_bk_fallback(
    tmp_path: Path,
) -> None:
    queue = _write_inputs(tmp_path)
    session = PartialFakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    client = GoalAPIClient(
        "test-secret",
        session=session,
        snapshot_dir=(
            tmp_path / "reports" / "goal-partial-probe" / "schedule" / "goal-api-v1"
        ),
        request_budget=120,
        now=lambda: observed,
    )

    result = collect_goal_probe_input(
        drawing_id=12071,
        queue_path=queue,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_dir=tmp_path / "reports" / "goal-partial-probe",
        client=client,
        project_root=tmp_path,
        captured_at=observed,
    )

    assert result.event_count == 15
    assert result.sports_eligible_count == 10
    assert result.history_source_count == 20
    coverage = json.loads(result.coverage_summary_path.read_text(encoding="utf-8"))
    assert len(coverage["events"]) == 15
    fallback = [row for row in coverage["events"] if not row["sports_eligible"]]
    assert [row["event_order"] for row in fallback] == [3, 7, 8, 11, 14]
    assert all(row["fallback_reason"] == "target_fixture_missing" for row in fallback)
    assert all(row["sources"] == [] for row in fallback)

    bundle = load_goal_probe_shadow(
        drawing_id=12071,
        as_of=result.captured_at,
        raw_cache_dir=tmp_path / "data" / "raw",
        coverage_summary_path=result.coverage_summary_path,
        project_root=tmp_path,
    )

    assert bundle.shadow.sports_coverage_count == 10
    assert bundle.shadow.fallback_count == 5
    assert [
        row.event_order
        for row in bundle.shadow.events
        if row.probability_source == "totobrief_bk_fallback"
    ] == [3, 7, 8, 11, 14]


def test_ensure_goal_probe_generates_full_queue_and_reuses_current_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)
    session = FakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    real_client = GoalAPIClient

    def client_factory(api_key, *, snapshot_dir, request_budget):
        return real_client(
            api_key,
            session=session,
            snapshot_dir=snapshot_dir,
            request_budget=request_budget,
            now=lambda: observed,
        )

    monkeypatch.setattr(goal_probe_collection, "GoalAPIClient", client_factory)
    output = tmp_path / "reports" / "sports-analytics" / "4988" / "goal-auto"
    first = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )
    calls_after_first = len(session.calls)
    second = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )

    assert first.reused is False
    assert second.reused is True
    assert calls_after_first == 36
    assert len(session.calls) == calls_after_first
    marker = json.loads((output / "current.json").read_text(encoding="utf-8"))
    assert marker["package_influence"] == "NONE"
    assert marker["automatic_wagering"] is False
    queue_paths = tuple((output / "captures").glob("*/goal-shadow-queue.json"))
    assert len(queue_paths) == 1
    queue = json.loads(queue_paths[0].read_text(encoding="utf-8"))
    assert len(queue["records"]) == 15
    assert "test-secret" not in (output / "current.json").read_text(
        encoding="utf-8"
    )


def test_ensure_goal_probe_reuses_partial_marker_with_bk_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)
    session = PartialFakeSession()
    observed = datetime(2026, 8, 27, 8, 0, tzinfo=UTC)
    real_client = GoalAPIClient

    def client_factory(api_key, *, snapshot_dir, request_budget):
        return real_client(
            api_key,
            session=session,
            snapshot_dir=snapshot_dir,
            request_budget=request_budget,
            now=lambda: observed,
        )

    monkeypatch.setattr(goal_probe_collection, "GoalAPIClient", client_factory)
    output = tmp_path / "reports" / "sports-analytics" / "4988" / "goal-auto"
    first = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )
    calls_after_first = len(session.calls)
    second = ensure_goal_probe_input(
        drawing_id=12071,
        raw_cache_dir=tmp_path / "data" / "raw",
        output_root=output,
        api_key="test-secret",
        project_root=tmp_path,
        captured_at=observed,
    )

    assert first.sports_eligible_count == 10
    assert first.history_source_count == 20
    assert second.reused is True
    assert second.sports_eligible_count == 10
    assert second.history_source_count == 20
    assert len(session.calls) == calls_after_first
