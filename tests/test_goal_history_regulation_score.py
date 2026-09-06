from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from toto_ai.sports_stats.features import build_team_window
from toto_ai.sports_stats.goal_probe_research import _load_history_snapshot

AS_OF = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
CASES = json.loads(
    (
        Path(__file__).parent / "fixtures/goal_regulation_score_captured_contracts.json"
    ).read_text()
)["cases"]


def load(tmp_path, rows, team_id=None):
    team_id = team_id or rows[0]["homeTeamId"]
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "goal-api-v1",
                "http_status": 200,
                "endpoint": f"/teams/{team_id}/results",
                "params": {"limit": 10},
                "fetched_at": (AS_OF - timedelta(minutes=1)).isoformat(),
                "payload": {"success": True, "teamId": team_id, "data": rows},
            }
        )
    )
    before = path.read_bytes()
    result = _load_history_snapshot(
        root=tmp_path,
        probe_root=tmp_path,
        source_row={
            "snapshot_path": str(path),
            "history_count": len(rows),
            "venue_count": len(rows),
        },
        team_id=team_id,
        target_fixture_id="target",
        target_starts_at=AS_OF + timedelta(hours=2),
        as_of=AS_OF,
        deadline=AS_OF + timedelta(hours=3),
    )
    assert path.read_bytes() == before
    return result


def row(status="AFTER_PEN"):
    return {
        "id": "history",
        "matchStatus": status,
        "kickoffUtc": (AS_OF - timedelta(days=1)).isoformat(),
        "homeTeamId": "home",
        "awayTeamId": "away",
        "homeTeamScore": "5",
        "awayTeamScore": "3",
        "homeTeamFtScore": "1",
        "awayTeamFtScore": "1",
    }


@pytest.mark.parametrize("case", CASES)
def test_exact_captured_regulation_contract(tmp_path, case):
    raw = case["row"]
    result = load(tmp_path, [raw], case["team_id"])
    (fixture,) = result.fixtures
    expected = int(raw["homeTeamFtScore"]), int(raw["awayTeamFtScore"])
    assert (fixture.home_goals, fixture.away_goals) == expected
    window = build_team_window(
        team_id=raw["homeTeamId"],
        fixtures=result.fixtures,
        requested_count=10,
        target_starts_at=AS_OF + timedelta(hours=2),
        target_fixture_id="target",
        as_of=AS_OF,
    )
    assert (window.goals_for, window.goals_against) == expected
    assert window.draws == int(expected[0] == expected[1])
    assert window.wins == int(expected[0] > expected[1])


@pytest.mark.parametrize("status", ["AFTER_ET", "AFTER_PEN"])
@pytest.mark.parametrize(
    "value", [None, "", True, False, -1, "-1", 1.5, "1.5", "1-1", [], {"score": 1}]
)
@pytest.mark.parametrize("field", ["homeTeamFtScore", "awayTeamFtScore"])
def test_invalid_regulation_never_uses_aggregate(tmp_path, status, value, field):
    raw = row(status)
    raw[field] = value
    result = load(tmp_path, [raw])
    assert result.fixtures == ()
    reason = "regulation_score_missing" if value is None else "invalid_regulation_score"
    assert result.diagnostics.excluded_counts == {reason: 1}


@pytest.mark.parametrize("status", ["AFTER_ET", "AFTER_PEN"])
def test_missing_regulation_key_skips(tmp_path, status):
    raw = row(status)
    del raw["homeTeamFtScore"]
    result = load(tmp_path, [raw])
    assert not result.fixtures
    assert result.diagnostics.excluded_counts == {"regulation_score_missing": 1}


@pytest.mark.parametrize("value", [0, "0", 2, "2"])
def test_numeric_strings_accepted_aggregate_ignored(tmp_path, value):
    raw = row()
    raw.update(homeTeamFtScore=value, homeTeamScore=None, awayTeamScore=True)
    result = load(tmp_path, [raw])
    assert result.fixtures[0].home_goals == int(value)
    assert result.fixtures[0].away_goals == 1


def test_finished_valid_scores_preserved(tmp_path):
    result = load(tmp_path, [row("FINISHED")])
    assert (result.fixtures[0].home_goals, result.fixtures[0].away_goals) == (5, 3)


def test_finished_invalid_score_still_skips(tmp_path):
    raw = row("FINISHED")
    raw["homeTeamScore"] = True
    result = load(tmp_path, [raw])
    assert not result.fixtures
    assert result.diagnostics.excluded_counts == {"invalid_terminal_row": 1}


def test_duplicate_regulation_conflict_fails_closed(tmp_path):
    first = row()
    second = deepcopy(first)
    second["homeTeamFtScore"] = "2"
    with pytest.raises(ValueError, match="duplicate fixture ids"):
        load(tmp_path, [first, second])


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"id": "target"}, "target_fixture"),
        ({"kickoffUtc": AS_OF.isoformat()}, "at_or_after_as_of"),
        ({"homeTeamId": "other", "awayTeamId": "another"}, "unrelated_team"),
        ({"matchStatus": "LIVE"}, "non_terminal_status"),
    ],
)
def test_existing_chronology_team_status_filters(tmp_path, change, reason):
    raw = row()
    raw.update(change)
    result = load(tmp_path, [raw], "home")
    assert not result.fixtures
    assert result.diagnostics.excluded_counts == {reason: 1}
