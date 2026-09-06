"""Offline regressions for semantic fixture identity vs capture provenance."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from tests.test_goal_api_provider import FakeResponse, FakeSession, _fixture, _now
from tests.test_goal_api_schedule_collection import _queue
from toto_ai.external_odds.goal_api import GoalAPIClient, GoalAPIError
from toto_ai.external_odds.schedule_source_collector import _collect_goal_api_candidates


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pagination regression attempted real network")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


def _client(tmp_path, rows, *, times=None, separate_dates=False):
    responses = [
        FakeResponse(
            {
                "success": True,
                "data": [row],
                "pagination": {
                    "hasMore": not separate_dates and index + 1 < len(rows),
                    "nextOffset": index + 1,
                },
            }
        )
        for index, row in enumerate(rows)
    ]
    session = FakeSession(responses)
    clock = iter(times) if times is not None else None
    client = GoalAPIClient(
        "synthetic-key",
        session=session,
        snapshot_dir=tmp_path,
        now=(lambda: next(clock)) if clock is not None else _now,
    )
    return client


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_frozen_duplicate_witness_is_accepted_and_raw_provenance_retained(
    tmp_path, reverse
):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/goal_pagination_duplicate.json").read_text()
    )
    rows = [row["raw_event"] for row in fixture["observations"]]
    assert [_hash(row) for row in rows] == [
        row["raw_event_sha256"] for row in fixture["observations"]
    ]
    assert {key for key in rows[0] if rows[0][key] != rows[1][key]} == {"updatedAt"}
    rows = rows[::-1] if reverse else rows
    client = _client(tmp_path, rows)

    events = client.fetch_schedule((date(2026, 9, 5),))

    assert len(events) == 1
    event = events[0]
    assert event.provider_event_id == fixture["fixture_id"]
    assert event.status == "finished" and event.eligible is False
    assert event.payload_hash in {_hash(row) for row in rows}
    snapshots = [
        json.loads(e.snapshot_path.read_text()) for e in client.request_evidence
    ]
    assert [s["payload"]["data"][0] for s in snapshots] == rows
    assert len(client.request_evidence) == 2
    assert event.request_fingerprint in {
        e.request_fingerprint for e in client.request_evidence
    }


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("metadata", [False, True])
def test_page_order_and_metadata_do_not_change_fixture_semantics(
    tmp_path, reverse, metadata
):
    first = _fixture()
    second = deepcopy(first)
    if metadata:
        first["updatedAt"] = "2026-08-25T16:00:00Z"
        second["updatedAt"] = "2026-08-25T16:30:00Z"
    rows = [first, second][:: -1 if reverse else 1]
    client = _client(tmp_path, rows)

    events = client.fetch_schedule((date(2026, 8, 26),))

    assert len(events) == 1
    assert events[0].provider_event_id == "7001"
    assert events[0].status == "not_started" and events[0].eligible
    assert events[0].starts_at == datetime(2026, 8, 26, 19, tzinfo=timezone.utc)
    assert events[0].payload_hash == max(_hash(row) for row in rows)
    assert len(client.request_evidence) == 2
    selected = next(
        e
        for e in client.request_evidence
        if e.request_fingerprint == events[0].request_fingerprint
    )
    raw = json.loads(selected.snapshot_path.read_text())["payload"]["data"][0]
    assert _hash(raw) == events[0].payload_hash


def test_cross_date_endpoint_and_capture_metadata_do_not_conflict(tmp_path):
    now = _now()
    client = _client(
        tmp_path,
        [_fixture(), _fixture()],
        separate_dates=True,
        times=[now, now + timedelta(minutes=1)],
    )

    events = client.fetch_schedule((date(2026, 8, 25), date(2026, 8, 26)))

    assert len(events) == 1
    assert events[0].captured_at == now + timedelta(minutes=1)
    assert events[0].source_endpoint.endswith("2026-08-26")
    assert len({e.endpoint for e in client.request_evidence}) == 2


@pytest.mark.parametrize("reverse", [False, True])
def test_latest_capture_cannot_keep_pre_kickoff_eligibility(tmp_path, reverse):
    kickoff = datetime(2026, 8, 26, 19, tzinfo=timezone.utc)
    times = [kickoff - timedelta(seconds=1), kickoff]
    client = _client(
        tmp_path,
        [_fixture(), _fixture()],
        times=times[::-1] if reverse else times,
    )

    (event,) = client.fetch_schedule((date(2026, 8, 26),))

    assert event.captured_at == kickoff
    assert event.status == "not_started"
    assert event.eligible is False


@pytest.mark.parametrize("status", ["UNRECOGNIZED_STATUS", "FINISHED"])
def test_metadata_dedup_does_not_promote_unknown_or_terminal_status(tmp_path, status):
    first = _fixture() | {"matchStatus": status, "updatedAt": "first"}
    second = first | {"updatedAt": "second"}
    (event,) = _client(tmp_path, [first, second]).fetch_schedule((date(2026, 8, 26),))
    assert event.status == (
        "unknown" if status == "UNRECOGNIZED_STATUS" else "finished"
    )
    assert event.eligible is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("homeTeamName", "Other home"),
        ("awayTeamName", "Other away"),
        ("homeTeamId", 999),
        ("awayTeamId", 999),
        ("apiId", 999),
        ("kickoffUtc", "2026-08-26T19:01:00Z"),
        ("leagueName", "Different league"),
        ("matchStatus", "UNKNOWN_CHANGED_STATUS"),
        ("homeTeamScore", "1"),
        ("awayTeamScore", "2"),
        ("unknownProviderField", {"changed": True}),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_real_or_unclassified_fixture_changes_still_fail_closed(
    tmp_path, key, value, reverse
):
    first = _fixture()
    second = first | {key: value, "updatedAt": "metadata-too"}
    client = _client(tmp_path, [first, second][:: -1 if reverse else 1])
    with pytest.raises(GoalAPIError, match="duplicate event identity conflicts"):
        client.fetch_schedule((date(2026, 8, 26),))
    assert len(client.request_evidence) == 2


@pytest.mark.parametrize(
    "statuses", [("UNRECOGNIZED_A", "UNRECOGNIZED_B"), ("NS", "NOT_STARTED")]
)
def test_distinct_raw_statuses_are_not_silently_merged(tmp_path, statuses):
    rows = [_fixture() | {"matchStatus": status} for status in statuses]
    with pytest.raises(GoalAPIError, match="duplicate event identity conflicts"):
        _client(tmp_path, rows).fetch_schedule((date(2026, 8, 26),))


def test_generic_collector_survives_metadata_duplicate_without_promoting(tmp_path):
    class ScheduleSession:
        def get(self, url, *, params, headers, timeout):
            target_date = url.endswith("2026-08-26")
            second = params["offset"] != "0"
            data = (
                [_fixture() | {"updatedAt": "second" if second else "first"}]
                if target_date
                else []
            )
            return FakeResponse(
                {
                    "success": True,
                    "data": data,
                    "pagination": {
                        "hasMore": target_date and not second,
                        "nextOffset": 1,
                    },
                }
            )

    output = tmp_path / "out"
    client = GoalAPIClient(
        "synthetic-key",
        session=ScheduleSession(),
        snapshot_dir=output / "goal-api-v1",
        now=_now,
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
        team_aliases={"Викинг": "Viking", "Динамо Загреб": "Dinamo Zagreb"},
    )

    assert status["candidate_count"] == 1
    assert status["status"] == "collected"
    assert records[0]["status"] == "independent_candidate"
    assert records[0]["ledger_eligible"] is False
    assert records[0]["missing_requirements"] == ["official_source", "review"]
