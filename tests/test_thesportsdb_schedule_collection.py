from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.schedule_source_collector import (
    collect_schedule_source_candidates,
)
from toto_ai.external_odds.thesportsdb import (
    TheSportsDBClient,
    TheSportsDBConfig,
)

UTC = timezone.utc
SECRET = "collection-secret"


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
        "created_at": "2026-08-24T15:00:00Z",
        "identity": {
            "drawing_id": 12062,
            "drawing_number": 4985,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-24T16:00:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12062,
                "drawing_number": 4985,
                "target_fingerprint": "a" * 64,
                "event_order": 8,
                "target_event_id": 180008,
                "home_team": "Росарио Сентраль",
                "away_team": "Тальерес",
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

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def get(self, url, *, params, timeout):
        self.calls.append(url)
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


def _fixture() -> dict[str, object]:
    return json.loads(
        Path("tests/fixtures/thesportsdb_v1_events.json").read_text(encoding="utf-8")
    )


def test_collection_uses_existing_alias_orientation_matcher_without_promotion(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    session = FakeSession([FakeResponse(_fixture()), FakeResponse(_fixture())])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases={
            "Росарио Сентраль": "Rosario Central",
            "Тальерес": "Talleres de Córdoba",
        },
    )

    records = [
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    ]
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "1001"
    assert record["orientation"] == "reversed"
    assert record["source_status"] == "not_started"
    assert record["status_eligible"] is True
    assert record["ledger_eligible"] is False
    assert record["missing_requirements"] == ["official_source", "review"]
    assert result.candidate_count == 1
    assert result.unresolved_count == 0
    assert result.provider_statuses["thesportsdb-v1"]["status"] == "collected"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert report["ledger_mutated"] is False
    assert report["providers"]["thesportsdb-v1"]["candidate_count"] == 1
    assert SECRET not in result.report_path.read_text(encoding="utf-8")
    assert not tuple(tmp_path.rglob("ledger.json"))
    assert len(session.calls) == 2


def test_collection_queries_reverse_orientation_when_forward_search_is_empty(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    session = FakeSession(
        [
            FakeResponse({"event": []}),
            FakeResponse(_fixture()),
        ]
    )
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases={
            "Росарио Сентраль": "Rosario Central",
            "Тальерес": "Talleres de Córdoba",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "1001"
    assert record["orientation"] == "reversed"
    assert record["ledger_eligible"] is False
    assert result.provider_statuses["thesportsdb-v1"]["ledger_mutated"] is False
    assert len(session.calls) == 2


def test_collection_can_explicitly_disable_thesportsdb(tmp_path: Path) -> None:
    result = collect_schedule_source_candidates(
        _queue(tmp_path),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_config=TheSportsDBConfig(api_key=None),
    )

    status = result.provider_statuses["thesportsdb-v1"]
    assert status == {
        "status": "disabled_missing_key",
        "config_key": "THESPORTSDB_API_KEY",
        "candidate_count": 0,
        "ledger_mutated": False,
    }
    assert result.candidate_count == 0
    assert result.unresolved_count == 1
    assert all(
        item.get("source_provider") != "thesportsdb-v1" for item in result.records
    )
