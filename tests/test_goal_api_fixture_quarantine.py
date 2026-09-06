"""Opt-in fixture quarantine; strict callers and real observations stay intact."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from tests.test_goal_api_provider import FakeResponse, FakeSession, _fixture, _now
from tests.test_goal_api_schedule_collection import _queue
from toto_ai.external_odds.goal_api import GoalAPIClient, GoalAPIError
from toto_ai.external_odds.schedule_source_collector import _collect_goal_api_candidates


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(requests.sessions.Session, "request", deny)


def client_for(tmp_path, rows, *, budget=120, dates=False, times=None):
    session = FakeSession(
        [
            FakeResponse(
                {
                    "success": True,
                    "data": page,
                    "pagination": {
                        "hasMore": not dates and i < len(rows) - 1,
                        "nextOffset": i + 1,
                    },
                }
            )
            for i, page in enumerate(rows)
        ]
    )
    ticks = iter(times) if times is not None else None
    return GoalAPIClient(
        "synthetic-key",
        session=session,
        snapshot_dir=tmp_path,
        request_budget=budget,
        now=(lambda: next(ticks)) if ticks is not None else _now,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("apiId", 999),
        ("homeTeamId", 999),
        ("awayTeamId", 999),
        ("leagueId", 99),
        ("kickoffUtc", "2026-08-26T20:00:00Z"),
        ("matchStatus", "FINISHED"),
        ("homeTeamScore", "1"),
        ("awayTeamHalftimeScore", "0"),
        ("homeTeamName", "Other team"),
        ("unknownField", {"changed": True}),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_quarantine_is_permanent_symmetric_and_retains_all_observations(
    tmp_path,
    field,
    value,
    reverse,
):
    first = _fixture()
    second = first | {field: value, "updatedAt": "later"}
    pair = [first, second][::-1] if reverse else [first, second]
    other = _fixture(event_id=7002) | {"homeTeamName": "Unrelated"}
    client = client_for(tmp_path / "q", [[pair[0]], [pair[1]], [first, other]])
    events = client.fetch_schedule_for_collection((date(2026, 8, 26),))
    assert [e.provider_event_id for e in events] == ["7002"]
    assert client.requests_made == 3 and client.schedule_pagination_complete
    (conflict,) = client.schedule_conflicts
    assert conflict.provider_event_id == "7001"
    assert (
        field in conflict.differing_fields
        and "updatedAt" not in conflict.differing_fields
    )
    assert len(conflict.observations) == 3
    assert all(e.snapshot_path.is_file() for e in conflict.evidence)
    assert len(conflict.public_summary()["observations"]) == 3
    strict = client_for(tmp_path / "strict", [[first], [second]])
    with pytest.raises(GoalAPIError, match="duplicate event identity conflicts"):
        strict.fetch_schedule((date(2026, 8, 26),))


def test_conflict_does_not_prevent_next_date_and_latest_capture_is_conservative(
    tmp_path,
):
    first = _fixture() | {"kickoffUtc": "2026-08-25T19:00:00Z"}
    conflict = first | {"homeTeamScore": "1"}
    other = _fixture(event_id=7002)
    client = client_for(tmp_path, [[first, conflict], [other]], dates=True)
    events = client.fetch_schedule_for_collection(
        (date(2026, 8, 25), date(2026, 8, 26))
    )
    assert [e.provider_event_id for e in events] == ["7002"]
    assert client.requests_made == 2
    late = datetime(2026, 8, 26, 19, tzinfo=timezone.utc)
    client = client_for(
        tmp_path / "late",
        [[other], [other | {"updatedAt": "x"}]],
        times=[late - timedelta(seconds=1), late],
    )
    (event,) = client.fetch_schedule_for_collection((date(2026, 8, 26),))
    assert not event.eligible and event.captured_at == late
    assert not client.schedule_conflicts


def test_budget_failure_never_claims_complete_or_returns_partial_candidates(tmp_path):
    first = _fixture()
    client = client_for(
        tmp_path, [[first, first | {"homeTeamScore": "1"}], []], budget=1
    )
    with pytest.raises(GoalAPIError, match="request budget exhausted"):
        client.fetch_schedule_for_collection((date(2026, 8, 26),))
    assert not client.schedule_pagination_complete
    assert len(client.schedule_conflicts) == 1
    assert client.requests_made == 1 and client.budget_exhausted


def test_collector_keeps_unrelated_target_but_blocks_any_conflicting_observation(
    tmp_path,
):
    class Session:
        def get(self, url, *, params, headers, timeout):
            rows = []
            if url.endswith("2026-08-26"):
                first = _fixture()
                changed = first | {"homeTeamName": "Changed", "homeTeamScore": "1"}
                other = _fixture(event_id=7002) | {
                    "homeTeamName": "Alpha",
                    "awayTeamName": "Beta",
                }
                replacement = _fixture(event_id=7003)
                rows = [first, changed, other, replacement]
            return FakeResponse(
                {"success": True, "data": rows, "pagination": {"hasMore": False}}
            )

    queue = json.loads(_queue(tmp_path).read_text())
    queue["records"].append(
        queue["records"][0]
        | {
            "event_order": 1,
            "target_event_id": 190002,
            "home_team": "Alpha",
            "away_team": "Beta",
        }
    )
    output = tmp_path / "out"
    client = GoalAPIClient(
        "synthetic-key",
        session=Session(),
        snapshot_dir=output / "goal-api-v1",
        now=_now,
    )
    records, status = _collect_goal_api_candidates(
        queue,
        output=output,
        observed=_now(),
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=timezone.utc),
        ledger=None,
        config=None,
        client=client,
        team_aliases={"Викинг": "Viking", "Динамо Загреб": "Dinamo Zagreb"},
    )
    assert records[0]["status"] == "conflict"
    assert records[0]["quarantined_fixture_ids"] == ["7001"]
    assert records[1]["status"] == "independent_candidate"
    assert records[1]["source_event_id"] == "7002"
    assert not any(r["ledger_eligible"] for r in records)
    assert status["status"] == "partial_conflicts"
    assert status["pagination_complete"] is True
    assert status["quarantined_fixture_count"] == 1
    assert status["candidate_count"] == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_halftime_missing_to_known_is_quarantined_not_filled(tmp_path, reverse):
    first = _fixture() | {"homeTeamHalftimeScore": None, "awayTeamHalftimeScore": None}
    second = first | {"homeTeamHalftimeScore": "1", "awayTeamHalftimeScore": "0"}
    rows = [first, second][::-1] if reverse else [first, second]
    client = client_for(tmp_path, [[rows[0]], [rows[1]]])
    assert client.fetch_schedule_for_collection((date(2026, 8, 26),)) == ()
    (conflict,) = client.schedule_conflicts
    assert conflict.differing_fields == (
        "awayTeamHalftimeScore",
        "homeTeamHalftimeScore",
    )


def test_collector_request_budget_failure_is_explicit_and_non_promoting(tmp_path):
    first = _fixture()
    output = tmp_path / "out"
    client = client_for(
        output / "goal-api-v1", [[first, first | {"homeTeamScore": "1"}], []], budget=1
    )
    queue = json.loads(_queue(tmp_path).read_text())
    records, status = _collect_goal_api_candidates(
        queue,
        output=output,
        observed=_now(),
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=timezone.utc),
        ledger=None,
        config=None,
        client=client,
        team_aliases=None,
    )
    assert records[0]["status"] == status["status"] == "source_failed"
    assert status["candidate_count"] == 0 and not status["pagination_complete"]
    assert status["budget_exhausted"]
    assert len(status["quarantined_fixtures"]) == 1


@pytest.mark.parametrize(
    "event_id", ["cmt63ihwdf62st107zcaaswfn", "cmt63ihwff62ut1075qx5dhf0"]
)
def test_exact_saved_halftime_conflict_witnesses(tmp_path, event_id):
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/goal_schedule_quarantine_conflicts.json"
        ).read_text()
    )
    rows = [r for r in fixture["observations"] if r["raw_event"]["id"] == event_id]
    assert len(rows) == 2
    for row in rows:
        digest = hashlib.sha256(
            json.dumps(
                row["raw_event"],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert digest == row["raw_event_sha256"]
    client = client_for(
        tmp_path,
        [[r["raw_event"]] for r in rows],
        times=[
            datetime.fromisoformat(r["fetched_at"].replace("Z", "+00:00")) for r in rows
        ],
    )
    assert client.fetch_schedule_for_collection((date(2026, 9, 5),)) == ()
    (conflict,) = client.schedule_conflicts
    assert conflict.provider_event_id == event_id
    assert conflict.differing_fields == (
        "awayTeamHalftimeScore",
        "homeTeamHalftimeScore",
    )
    assert all(not e.eligible for e in conflict.observations)
