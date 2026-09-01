import hashlib
import json
from datetime import datetime, timezone

from toto_ai.external_odds.schedule_source_collector import (
    collect_schedule_source_candidates,
)


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _queue(tmp_path):
    payload = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-14T08:00:00Z",
        "identity": {
            "drawing_id": 12033,
            "drawing_number": 4975,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-14T14:00:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12033,
                "drawing_number": 4975,
                "target_fingerprint": "a" * 64,
                "event_order": 8,
                "target_event_id": 179606,
                "home_team": "Анси",
                "away_team": "Родез",
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        ],
    }
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def test_collector_saves_raw_snapshot_and_independent_candidate(tmp_path):
    queue = _queue(tmp_path)

    def fetch(url):
        assert "sofascore.com/api/v1/search/all" in url
        return {
            "results": [
                {
                    "type": "event",
                    "entity": {
                        "id": 16386243,
                        "name": "Annecy FC - Rodez AF",
                        "slug": "annecy-fc-rodez-af",
                        "customId": "ANcsUrJb",
                        "startTimestamp": 1786733100,
                        "status": {"type": "notstarted"},
                        "homeTeam": {
                            "name": "Annecy FC",
                            "fieldTranslations": {
                                "nameTranslation": {"ru": "Анси"}
                            },
                        },
                        "awayTeam": {
                            "name": "Rodez AF",
                            "fieldTranslations": {
                                "nameTranslation": {"ru": "Родез Авейрон"}
                            },
                        },
                        "tournament": {"name": "Ligue 2"},
                    },
                }
            ]
        }

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=fetch,
        captured_at=datetime(2026, 8, 14, 9, tzinfo=timezone.utc),
    )

    assert result.candidate_count == 1
    assert result.unresolved_count == 0
    record = result.records[0]
    assert record["status"] == "independent_candidate"
    assert record["event_order"] == 8
    assert record["starts_at"] == "2026-08-14T18:45:00Z"
    assert record["source_role"] == "independent"
    assert record["identity_binding"] == "exact_same_target_event_v1"
    assert record["canonical_home_name"] == "Анси"
    assert record["canonical_away_name"] == "Родез"
    assert record["ledger_eligible"] is False
    assert record["missing_requirements"] == ["official_source", "review"]
    snapshot = tmp_path / "out" / record["snapshot_path"]
    assert snapshot.is_file()
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == record[
        "snapshot_sha256"
    ]
    report = json.loads(result.report_path.read_text())
    assert report["queue_sha256"] == json.loads(queue.read_text())["queue_sha256"]


def test_collector_rejects_queue_hash_drift(tmp_path):
    queue = _queue(tmp_path)
    payload = json.loads(queue.read_text())
    payload["records"][0]["home_team"] = "Changed"
    queue.write_text(json.dumps(payload))

    try:
        collect_schedule_source_candidates(
            queue,
            output_dir=tmp_path / "out",
            fetch_json=lambda _url: {},
        )
    except ValueError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("queue drift must fail")
