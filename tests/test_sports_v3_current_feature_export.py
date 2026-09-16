"""Current-drawing row export remains a sealed, unreviewed research artifact."""

import hashlib
import json

from toto_ai.research.sports_v3_current_feature_export import seal_current_rows
from toto_ai.research.sports_v3_retrospective_fit import _validate_row
from toto_ai.research.sports_v3_retrospective_predict import (
    REVIEWED,
    _roster,
    derive_reviewed,
)
from toto_ai.sports_stats.v3_probability import FEATURE_NAMES

CAPTURED = "2026-09-16T10:00:00Z"
HISTORY_FETCHED = "2026-09-15T10:00:00Z"
DRAWING_ID = 5008
DRAWING_NUMBER = 5008
MISSING_ORDERS = {3, 9, 13}


def _write_json(root, relative, document):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target_event(order):
    return {
        "id": 10_000 + order,
        "order": order,
        "championship": "Synthetic League",
        "sport": "football",
        "name": f"Home {order} — Away {order}",
        "start_at": "2026-09-17T12:00:00Z",
        "quotes": {
            "bk_win_1": 0.5,
            "bk_draw": 0.25,
            "bk_win_2": 0.25,
            "pool_win_1": 0,
            "pool_draw": 0,
            "pool_win_2": 0,
        },
    }


def _history(order):
    matches = []
    for side, team in (("home", f"home-{order}"), ("away", f"away-{order}")):
        for number in range(3):
            opponent = f"{side}-opponent-{order}-{number}"
            matches.append(
                {
                    "id": f"history-{side}-{order}-{number}",
                    "matchStatus": "FINISHED",
                    "kickoffUtc": f"2026-09-{10 + number:02}T10:00:00Z",
                    "homeTeamId": team if side == "home" else opponent,
                    "awayTeamId": opponent if side == "home" else team,
                    "homeTeamScore": number + 1,
                    "awayTeamScore": number,
                }
            )
    return {"fetched_at": HISTORY_FETCHED, "payload": {"data": matches}}


def _synthetic_sources(tmp_path):
    events = []
    for order in range(15):
        fixture = None
        if order not in MISSING_ORDERS:
            target_path = f"fixtures/target-{order}.json"
            target_hash = _write_json(
                tmp_path,
                target_path,
                {
                    "provider_fixture_id": f"fixture-{order}",
                    "provider_home_team_id": f"home-{order}",
                    "provider_away_team_id": f"away-{order}",
                    "payload": {"kickoffUtc": "2026-09-17T12:00:00Z"},
                },
            )
            history_path = f"history/history-{order}.json"
            history_hash = _write_json(tmp_path, history_path, _history(order))
            fixture = {"path": target_path, "file_sha256": target_hash}
            ledgers = [
                {"history_path": history_path, "history_sha256": history_hash}
            ]
        else:
            ledgers = []
        events.append(
            {
                "event_order": order,
                "target_fixture": fixture,
                "history_admission_ledger": ledgers,
            }
        )

    source_path = "source-evidence.json"
    _write_json(
        tmp_path,
        source_path,
        {
            "drawing_id": DRAWING_ID,
            "drawing_number": DRAWING_NUMBER,
            "events": events,
        },
    )
    final_path = "final-input.json"
    _write_json(
        tmp_path,
        final_path,
        {
            "captured_at": CAPTURED,
            "probability_input_sha256": "a" * 64,
            "payload": {
                "data": {
                    "id": DRAWING_ID,
                    "number": DRAWING_NUMBER,
                    "name": "Synthetic Toto",
                    "ended_at": "2026-09-18T12:00:00Z",
                    "events": [_target_event(order) for order in range(15)],
                }
            },
        },
    )
    return source_path, final_path


def test_current_export_is_complete_roster_and_unreviewed_original_rows(tmp_path):
    source_path, final_path = _synthetic_sources(tmp_path)
    exported = seal_current_rows(
        root=tmp_path,
        source_evidence_path=source_path,
        final_input_path=final_path,
    )
    rows, roster = exported["original_rows"], exported["roster"]

    assert len(rows) == 12
    assert len(roster) == 15
    assert [slot["event_order"] for slot in roster] == list(range(15))
    assert [
        slot["event_order"] for slot in roster if slot["feature_sha256"] is None
    ] == sorted(MISSING_ORDERS)
    assert all(
        roster[order]["status"] == "BK_FALLBACK_NO_PROVIDER_FIXTURE"
        for order in MISSING_ORDERS
    )
    assert all(row["identity_status"] == "UNKNOWN" for row in rows)
    assert all(set(row["features"]) == set(FEATURE_NAMES) for row in rows)
    assert all(row["decision_cutoff"] < row["kickoff"] for row in rows)

    expected_final_hash = hashlib.sha256(
        (tmp_path / final_path).read_bytes()
    ).hexdigest()
    expected_evidence_hash = hashlib.sha256(
        (tmp_path / source_path).read_bytes()
    ).hexdigest()
    expected_probability_input_hash = "a" * 64
    assert exported["input_hashes"] == {
        "source_evidence_sha256": expected_evidence_hash,
        "final_input_file_sha256": expected_final_hash,
        "probability_input_sha256": expected_probability_input_hash,
    }
    assert all(slot["bk_input_file_sha256"] == expected_final_hash for slot in roster)
    assert all(
        slot["bk_input_sha256"] == expected_probability_input_hash for slot in roster
    )

    slots_by_order = {slot["event_order"]: slot for slot in roster}
    rows_by_order = {row["event_order"]: row for row in rows}
    assert set(rows_by_order).isdisjoint(MISSING_ORDERS)
    assert {
        order: slot["feature_sha256"]
        for order, slot in slots_by_order.items()
        if order not in MISSING_ORDERS
    } == {order: row["sha256"] for order, row in rows_by_order.items()}
    assert len(_roster(roster)) == 15
    for row in rows:
        _validate_row(row, {row["sha256"]})

    decisions = [
        {
            "decision": "ACCEPT",
            "row_id": slots_by_order[row["event_order"]]["row_id"],
            "event_order": row["event_order"],
            "original_row_sha256": row["sha256"],
            "raw_identity": {
                "fixture_id": row["event_id"],
                "kickoff_utc": row["kickoff"],
            },
            "allowed_identity_status_update": {"from": "UNKNOWN", "to": REVIEWED},
        }
        for row in rows
    ]
    reviewed = derive_reviewed(rows, decisions, roster)
    assert {row["event_order"] for row in reviewed} == set(rows_by_order)
    assert all(row["identity_status"] == REVIEWED for row in reviewed)
