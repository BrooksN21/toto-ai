from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

import toto_ai.sports_stats.history_backfill as history_backfill
from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import SportsEventFeatureSnapshot, SportsStatsRun
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.package.audit import canonical_probability_input_sha256
from toto_ai.sports_stats.history_backfill import backfill_sports_history_manifest

_AS_OF = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
_DEADLINE = datetime(2026, 9, 1, 15, 45, tzinfo=timezone.utc)
_BASE_URL = "https://api.goal-api.com/v1"
_MANIFEST_CLASS = "SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_MANIFEST"


@dataclass(frozen=True)
class _Fixture:
    root: Path
    database: Path
    manifest_path: Path
    manifest: dict[str, object]
    raw_sources: tuple[Path, ...]


def test_valid_4993_like_raw_history_import_is_atomic_and_audited(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "valid", covered_events=11)

    report, paths = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "SUCCESS"
    assert report["inserted_count"] == 1
    assert report["reused_count"] == 0
    assert report["rejected_count"] == 0
    result = report["snapshots"][0]
    assert result["status"] == "inserted"
    assert result["drawing_number"] == 4993
    assert result["complete_count"] == 11
    assert result["missing_count"] == 4
    assert result["available_source_count"] == 22
    assert result["unavailable_source_count"] == 8

    factory = get_session_factory(init_db(fixture.database))
    with factory() as session:
        runs = tuple(session.scalars(select(SportsStatsRun)))
        rows = tuple(
            session.scalars(
                select(SportsEventFeatureSnapshot).order_by(
                    SportsEventFeatureSnapshot.event_order
                )
            )
        )
    assert len(runs) == 1
    assert runs[0].provider == "goal-api-v1"
    assert len(rows) == 15
    assert [row.status for row in rows[:11]] == ["complete"] * 11
    assert [row.status for row in rows[11:]] == ["missing"] * 4

    assert json.loads(paths.json.read_text(encoding="utf-8")) == report
    with paths.csv.open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 1
    assert csv_rows[0]["status"] == "inserted"
    assert "OFFLINE RAW-CAPTURE BACKFILL" in paths.markdown.read_text(
        encoding="utf-8"
    )


def test_frozen_final_input_validate_only_does_not_create_database(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "validate", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    snapshot = manifest["snapshots"][0]
    detail_path = fixture.root / snapshot["target_detail"]["path"]
    payload = _read_json(detail_path)
    target = parse_target_drawing(payload, _AS_OF - timedelta(hours=2))
    final_input = {
        "schema_version": 1,
        "plan_id": "test-plan",
        "attempt_id": "test-final-input",
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "deadline": _iso(target.deadline),
        "captured_at": _iso(_AS_OF - timedelta(hours=2)),
        "target_fingerprint": snapshot["drawing_fingerprint"],
        "detail_payload_sha256": _sha256_json(payload),
        "probability_input_sha256": canonical_probability_input_sha256(
            tuple(event.bk_probabilities for event in target.events)
        ),
        "timing_override_sha256": None,
        "payload": payload,
    }
    final_input["snapshot_sha256"] = _sha256_json(final_input)
    final_path = fixture.root / "frozen" / "final-input.json"
    _seal_raw_capture(final_path, final_input)
    snapshot["target_detail"] = {
        "artifact_type": "frozen_final_input",
        "path": final_path.relative_to(fixture.root).as_posix(),
        "sha256": _file_sha256(final_path),
    }
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=None,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
        validate_only=True,
    )

    assert report["status"] == "SUCCESS"
    assert report["validation_only"] is True
    assert report["database_writes"] == 0
    assert report["validated_count"] == 1
    assert report["snapshots"][0]["status"] == "validated"
    assert not fixture.database.exists()


def test_semantic_retry_reuses_one_parent_and_fifteen_children(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "retry", covered_events=11)
    output = fixture.root / "audit"

    first, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=output,
        project_root=fixture.root,
    )
    second, paths = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=output,
        project_root=fixture.root,
    )
    second_bytes = tuple(
        path.read_bytes() for path in (paths.json, paths.csv, paths.markdown)
    )
    third, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=output,
        project_root=fixture.root,
    )

    assert first["snapshots"][0]["status"] == "inserted"
    assert second["snapshots"][0]["status"] == "reused"
    assert third == second
    assert second_bytes == tuple(
        path.read_bytes() for path in (paths.json, paths.csv, paths.markdown)
    )
    assert first["snapshots"][0]["run_id"] == second["snapshots"][0]["run_id"]
    factory = get_session_factory(init_db(fixture.database))
    with factory() as session:
        assert len(tuple(session.scalars(select(SportsStatsRun)))) == 1
        assert (
            len(tuple(session.scalars(select(SportsEventFeatureSnapshot))))
            == 15
        )


def test_changed_raw_sporting_evidence_conflicts_and_keeps_original(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "conflict", covered_events=11)
    first, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit-first",
        project_root=fixture.root,
    )
    manifest = deepcopy(fixture.manifest)
    source = manifest["snapshots"][0]["events"][0]["sources"]["home"]
    raw_path = fixture.root / source["path"]
    raw = _read_json(raw_path)
    raw["payload"]["data"][0]["homeTeamScore"] = "3"
    raw["response_hash"] = _sha256_json(raw["payload"])
    _seal_raw_capture(raw_path, raw)
    source["sha256"] = _file_sha256(raw_path)
    _write_manifest(fixture.manifest_path, manifest)

    second, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit-second",
        project_root=fixture.root,
    )

    assert first["snapshots"][0]["status"] == "inserted"
    assert second["snapshots"][0]["status"] == "rejected"
    assert "identity already has different content" in second["snapshots"][0][
        "error"
    ]
    factory = get_session_factory(init_db(fixture.database))
    with factory() as session:
        assert len(tuple(session.scalars(select(SportsStatsRun)))) == 1
        assert (
            len(tuple(session.scalars(select(SportsEventFeatureSnapshot))))
            == 15
        )


def test_raw_capture_tamper_fails_closed_without_database_rows(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "tamper", covered_events=11)
    fixture.raw_sources[0].write_bytes(fixture.raw_sources[0].read_bytes() + b" ")

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "REJECTED"
    assert report["snapshots"][0]["status"] == "rejected"
    assert "SHA-256 mismatch" in report["snapshots"][0]["error"]
    assert not fixture.database.exists()


def test_post_kickoff_capture_fails_closed_even_with_updated_hash(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "late", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    event = manifest["snapshots"][0]["events"][0]
    source = event["sources"]["home"]
    raw_path = fixture.root / source["path"]
    raw = _read_json(raw_path)
    raw["fetched_at"] = event["target_starts_at"]
    _seal_raw_capture(raw_path, raw)
    source["sha256"] = _file_sha256(raw_path)
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "REJECTED"
    assert "strictly before target kickoff" in report["snapshots"][0]["error"]
    assert not fixture.database.exists()


def test_explicit_missing_source_is_persisted_as_unavailable(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "missing", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    event = manifest["snapshots"][0]["events"][0]
    event["sources"]["away"] = {
        "status": "unavailable",
        "reason": "source_not_captured",
    }
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    result = report["snapshots"][0]
    assert result["status"] == "inserted"
    assert result["complete_count"] == 10
    assert result["partial_count"] == 1
    assert result["missing_count"] == 4
    assert result["available_source_count"] == 21
    assert result["unavailable_source_count"] == 9
    factory = get_session_factory(init_db(fixture.database))
    with factory() as session:
        row = session.scalar(
            select(SportsEventFeatureSnapshot).where(
                SportsEventFeatureSnapshot.event_order == 0
            )
        )
    assert row is not None
    assert row.status == "partial"
    assert json.loads(row.missing_reasons_json) == [
        "historical_asof_unavailable"
    ]


def test_derived_probability_artifact_is_rejected_as_history_source(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "derived", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    derived = fixture.root / "reports" / "sports-v2-probabilities.json"
    derived.parent.mkdir(parents=True)
    _write_json(
        derived,
        {
            "schema_version": 2,
            "model": "sports-v2",
            "probabilities": [0.4, 0.3, 0.3],
        },
    )
    source = manifest["snapshots"][0]["events"][0]["sources"]["home"]
    source.update(
        {
            "artifact_type": "derived_probability_artifact",
            "path": derived.relative_to(fixture.root).as_posix(),
            "sha256": _file_sha256(derived),
        }
    )
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "REJECTED"
    assert "raw GOAL team-results capture" in report["snapshots"][0]["error"]
    assert not fixture.database.exists()


def test_partial_multi_snapshot_manifest_keeps_valid_snapshot_atomic(tmp_path):
    fixture = _write_manifest_fixture(tmp_path / "partial", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    incomplete = deepcopy(manifest["snapshots"][0])
    incomplete["events"] = incomplete["events"][:-1]
    manifest["snapshots"].append(incomplete)
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "PARTIAL"
    assert [row["status"] for row in report["snapshots"]] == [
        "inserted",
        "rejected",
    ]
    assert "exactly 15 events" in report["snapshots"][1]["error"]
    factory = get_session_factory(init_db(fixture.database))
    with factory() as session:
        assert len(tuple(session.scalars(select(SportsStatsRun)))) == 1
        assert (
            len(tuple(session.scalars(select(SportsEventFeatureSnapshot))))
            == 15
        )


@pytest.mark.parametrize("database_state", ["absent", "legacy", "initialized"])
@pytest.mark.parametrize("damage", ["snapshot", "hash", "identity", "as_of"])
@pytest.mark.parametrize("validate_only", [False, True])
def test_rejected_input_preserves_database_bytes_and_absence(
    tmp_path, database_state, damage, validate_only
):
    """Early init_db must not create, migrate, or rewrite a rejected input's DB."""
    fixture = _write_manifest_fixture(tmp_path / "rejected", covered_events=1)
    _prepare_database(fixture.database, database_state)
    before = _database_file_bytes(fixture.database)
    manifest = deepcopy(fixture.manifest)
    snapshot = manifest["snapshots"][0]
    if damage == "snapshot":
        snapshot["events"] = snapshot["events"][:-1]
        expected_error = "exactly 15 events"
    elif damage == "hash":
        source = fixture.raw_sources[0]
        source.write_bytes(source.read_bytes() + b" ")
        expected_error = "SHA-256 mismatch"
    elif damage == "identity":
        snapshot["drawing_id"] += 1
        expected_error = "drawing"
    else:
        snapshot["as_of"] = _iso(_AS_OF - timedelta(hours=1))
        expected_error = "as_of"
    _write_manifest(fixture.manifest_path, manifest)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
        validate_only=validate_only,
    )

    assert report["status"] == "REJECTED"
    assert report["database_writes"] == 0
    assert expected_error in report["snapshots"][0]["error"]
    assert _database_file_bytes(fixture.database) == before


@pytest.mark.parametrize("database_state", ["absent", "legacy", "initialized"])
def test_invalid_manifest_hash_preserves_database_bytes(tmp_path, database_state):
    fixture = _write_manifest_fixture(tmp_path / "manifest-hash", covered_events=1)
    _prepare_database(fixture.database, database_state)
    before = _database_file_bytes(fixture.database)
    manifest = deepcopy(fixture.manifest)
    manifest["manifest_sha256"] = "0" * 64
    _write_json(fixture.manifest_path, manifest)

    with pytest.raises(ValueError, match="manifest semantic hash"):
        backfill_sports_history_manifest(
            manifest_path=fixture.manifest_path,
            db=fixture.database,
            output_dir=fixture.root / "audit",
            project_root=fixture.root,
        )

    assert _database_file_bytes(fixture.database) == before


@pytest.mark.parametrize("database_state", ["absent", "legacy", "initialized"])
def test_valid_validate_only_preserves_database_bytes(tmp_path, database_state):
    fixture = _write_manifest_fixture(tmp_path / "validate-bytes", covered_events=1)
    _prepare_database(fixture.database, database_state)
    before = _database_file_bytes(fixture.database)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
        validate_only=True,
    )

    assert report["status"] == "SUCCESS"
    assert report["validated_count"] == 1
    assert report["database_writes"] == 0
    assert _database_file_bytes(fixture.database) == before


@pytest.mark.parametrize("invalid_first", [False, True])
def test_all_snapshots_are_validated_before_database_initialization(
    tmp_path, monkeypatch, invalid_first
):
    """Keep PARTIAL imports, but never initialize DB ahead of later validation."""
    fixture = _write_manifest_fixture(tmp_path / "preflight", covered_events=1)
    manifest = deepcopy(fixture.manifest)
    invalid = deepcopy(manifest["snapshots"][0])
    invalid["events"] = invalid["events"][:-1]
    manifest["snapshots"].insert(0 if invalid_first else 1, invalid)
    _write_manifest(fixture.manifest_path, manifest)
    completed = []
    real_build = history_backfill._build_snapshot
    real_init = history_backfill.init_db

    def record_validation(**kwargs):
        try:
            return real_build(**kwargs)
        finally:
            completed.append(kwargs["value"])

    def initialize_after_validation(path):
        assert len(completed) == 2
        return real_init(path)

    monkeypatch.setattr(history_backfill, "_build_snapshot", record_validation)
    monkeypatch.setattr(history_backfill, "init_db", initialize_after_validation)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "PARTIAL"
    expected = ["rejected", "inserted"] if invalid_first else ["inserted", "rejected"]
    assert [row["status"] for row in report["snapshots"]] == expected
    with sqlite3.connect(f"{fixture.database.as_uri()}?mode=ro", uri=True) as db:
        assert db.execute("SELECT count(*) FROM sports_stats_runs").fetchone() == (1,)
        assert db.execute(
            "SELECT count(*) FROM sports_event_feature_snapshots"
        ).fetchone() == (15,)


@pytest.mark.parametrize("database_state", ["absent", "legacy", "initialized"])
def test_successful_write_still_initializes_or_migrates_database(
    tmp_path, database_state
):
    fixture = _write_manifest_fixture(tmp_path / "write-schema", covered_events=1)
    _prepare_database(fixture.database, database_state)

    report, _ = backfill_sports_history_manifest(
        manifest_path=fixture.manifest_path,
        db=fixture.database,
        output_dir=fixture.root / "audit",
        project_root=fixture.root,
    )

    assert report["status"] == "SUCCESS"
    assert report["inserted_count"] == 1
    assert report["database_writes"] == 1
    with sqlite3.connect(f"{fixture.database.as_uri()}?mode=ro", uri=True) as db:
        assert db.execute("SELECT count(*) FROM sports_stats_runs").fetchone() == (1,)
        assert db.execute(
            "SELECT count(*) FROM sports_event_feature_snapshots"
        ).fetchone() == (15,)
        assert "result_status" in {
            row[1] for row in db.execute("PRAGMA table_info(events)")
        }
        if database_state != "absent":
            assert db.execute("SELECT value FROM retained_evidence").fetchall() == [
                ("keep exact bytes",)
            ]


def _prepare_database(database: Path, state: str) -> None:
    if state == "absent":
        assert not database.exists()
        return
    database.parent.mkdir(parents=True, exist_ok=True)
    if state == "initialized":
        init_db(database).dispose()
    with sqlite3.connect(database) as connection:
        if state == "legacy":
            connection.execute("CREATE TABLE events (id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO events VALUES (123)")
        connection.execute("CREATE TABLE retained_evidence (value TEXT)")
        connection.execute("INSERT INTO retained_evidence VALUES ('keep exact bytes')")
        connection.execute("PRAGMA user_version = 7")


def _database_file_bytes(database: Path) -> dict[str, bytes | None]:
    return {
        suffix: path.read_bytes() if path.exists() else None
        for suffix in ("", "-wal", "-shm", "-journal")
        for path in (Path(str(database) + suffix),)
    }


def _write_manifest_fixture(root: Path, *, covered_events: int) -> _Fixture:
    root.mkdir(parents=True)
    raw_cache = root / "data" / "raw"
    events = []
    for order in range(15):
        events.append(
            {
                "id": 190_000 + order,
                "order": order,
                "name": f"Home {order + 1} — Away {order + 1}",
                "name_en": None,
                "championship": "Test football",
                "start_at": None,
                "quotes": {
                    "bk_win_1": 40,
                    "bk_draw": 30,
                    "bk_win_2": 30,
                    "pool_win_1": 38,
                    "pool_draw": 32,
                    "pool_win_2": 30,
                },
                "result": None,
                "score": None,
            }
        )
    detail_payload = {
        "version": "test",
        "data": {
            "id": 12086,
            "number": 4993,
            "name": "baltbet-main",
            "ended_at": _iso(_DEADLINE + timedelta(hours=3)),
            "status": "open",
            "pool_sum": 100_000,
            "jackpot": 0,
            "payments": [],
            "events": events,
        },
    }
    detail = write_drawing_detail_cache(
        detail_payload,
        drawing_id=12086,
        cache_dir=raw_cache,
        fetched_at=_AS_OF - timedelta(hours=2),
        source="test-frozen",
        allowed_root=root,
    )
    detail_meta = raw_cache / "drawing_12086.meta.json"
    target = parse_target_drawing(detail_payload, detail.fetched_at)
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )

    schedule_records = []
    manifest_events = []
    raw_sources = []
    capture_dir = root / "frozen" / "goal-api-v1" / "snapshots"
    capture_dir.mkdir(parents=True)
    for event in target.events:
        if event.event_order >= covered_events:
            schedule_records.append(
                {
                    "status": "not_found",
                    "event_order": event.event_order,
                    "target_event_id": event.event_id,
                    "target_home_team": event.home_team,
                    "target_away_team": event.away_team,
                    "orientation": None,
                    "source_provider": "goal-api-v1",
                    "source_event_id": None,
                    "source_home_team_id": None,
                    "source_away_team_id": None,
                    "starts_at": None,
                    "source_status": None,
                    "ledger_eligible": False,
                }
            )
            manifest_events.append(
                {
                    "event_order": event.event_order,
                    "target_event_id": str(event.event_id),
                    "home_team": event.home_team,
                    "away_team": event.away_team,
                    "sport": "football",
                    "target_starts_at": None,
                    "provider_fixture_id": None,
                    "provider_home_team_id": None,
                    "provider_away_team_id": None,
                    "sources": {
                        "home": {
                            "status": "unavailable",
                            "reason": "target_fixture_missing",
                        },
                        "away": {
                            "status": "unavailable",
                            "reason": "target_fixture_missing",
                        },
                    },
                }
            )
            continue

        target_start = datetime(
            2026,
            9,
            1,
            16,
            event.event_order,
            tzinfo=timezone.utc,
        )
        fixture_id = f"target-fixture-{event.event_order}"
        home_id = f"home-team-{event.event_order}"
        away_id = f"away-team-{event.event_order}"
        schedule_records.append(
            {
                "status": "independent_candidate",
                "event_order": event.event_order,
                "target_event_id": event.event_id,
                "target_home_team": event.home_team,
                "target_away_team": event.away_team,
                "orientation": "same",
                "source_provider": "goal-api-v1",
                "source_event_id": fixture_id,
                "source_home_team_id": home_id,
                "source_away_team_id": away_id,
                "starts_at": _iso(target_start),
                "source_status": "scheduled",
                "ledger_eligible": False,
            }
        )
        sources = {}
        for side, team_id in (("home", home_id), ("away", away_id)):
            source_path = capture_dir / f"event-{event.event_order:02d}-{side}.json"
            _write_raw_capture(
                source_path,
                team_id=team_id,
                event_order=event.event_order,
                side=side,
                fetched_at=_AS_OF - timedelta(minutes=30),
            )
            raw_sources.append(source_path)
            sources[side] = {
                "status": "available",
                "artifact_type": "raw_goal_team_results_response",
                "path": source_path.relative_to(root).as_posix(),
                "sha256": _file_sha256(source_path),
            }
        manifest_events.append(
            {
                "event_order": event.event_order,
                "target_event_id": str(event.event_id),
                "home_team": event.home_team,
                "away_team": event.away_team,
                "sport": "football",
                "target_starts_at": _iso(target_start),
                "provider_fixture_id": fixture_id,
                "provider_home_team_id": home_id,
                "provider_away_team_id": away_id,
                "sources": sources,
            }
        )

    schedule = {
        "schema_version": 2,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "drawing_id": 12086,
        "drawing_number": 4993,
        "captured_at": _iso(_AS_OF - timedelta(hours=1)),
        "ledger_mutated": False,
        "records": schedule_records,
    }
    _seal_schedule(schedule)
    schedule_path = root / "frozen" / "schedule-source-candidates.json"
    _write_json(schedule_path, schedule)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "artifact_class": _MANIFEST_CLASS,
        "snapshots": [
            {
                "drawing_id": 12086,
                "drawing_number": 4993,
                "drawing_fingerprint": fingerprint,
                "provider": "goal-api-v1",
                "requested_history_size": 10,
                "as_of": _iso(_AS_OF),
                "deadline": _iso(_DEADLINE),
                "target_detail": {
                    "path": detail.path.relative_to(root).as_posix(),
                    "sha256": _file_sha256(detail.path),
                    "metadata_path": detail_meta.relative_to(root).as_posix(),
                    "metadata_sha256": _file_sha256(detail_meta),
                },
                "schedule_binding": {
                    "path": schedule_path.relative_to(root).as_posix(),
                    "sha256": _file_sha256(schedule_path),
                },
                "events": manifest_events,
            }
        ],
    }
    manifest_path = root / "manifests" / "sports-history.json"
    _write_manifest(manifest_path, manifest)
    return _Fixture(
        root=root,
        database=root / "data" / "toto.db",
        manifest_path=manifest_path,
        manifest=manifest,
        raw_sources=tuple(raw_sources),
    )


def _write_raw_capture(
    path: Path,
    *,
    team_id: str,
    event_order: int,
    side: str,
    fetched_at: datetime,
) -> None:
    endpoint = f"/teams/{team_id}/results"
    params = [["limit", "10"]]
    payload = {
        "success": True,
        "teamId": team_id,
        "data": [
            {
                "id": f"history-{event_order}-{side}",
                "matchStatus": "FINISHED",
                "kickoffUtc": _iso(_AS_OF - timedelta(days=event_order + 1)),
                "homeTeamId": team_id if side == "home" else f"opponent-{event_order}",
                "awayTeamId": f"opponent-{event_order}" if side == "home" else team_id,
                "homeTeamScore": "2" if side == "home" else "1",
                "awayTeamScore": "0",
            }
        ],
    }
    document = {
        "schema_version": 1,
        "provider": "goal-api-v1",
        "endpoint": endpoint,
        "params": params,
        "request_fingerprint": _sha256_json(
            {
                "provider": "goal-api-v1",
                "base_url": _BASE_URL,
                "endpoint": endpoint,
                "params": params,
            }
        ),
        "fetched_at": _iso(fetched_at),
        "response_hash": _sha256_json(payload),
        "payload": payload,
    }
    _seal_raw_capture(path, document)


def _seal_raw_capture(path: Path, document: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(document) + b"\n")


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    payload.pop("manifest_sha256", None)
    payload["manifest_sha256"] = _sha256_json(payload)
    _write_json(path, payload)


def _seal_schedule(payload: dict[str, object]) -> None:
    payload.pop("report_sha256", None)
    payload["report_sha256"] = _sha256_json(payload)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
