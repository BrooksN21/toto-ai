from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.cli import app
from toto_ai.db.models import (
    Drawing,
    DrawingReconciliationState,
    Event,
    Quote,
)
from toto_ai.db.session import get_session_factory, init_db, open_readonly_db

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_fingerprint(path: Path) -> dict[str, object]:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        schema = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        row_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
    return {
        "sha256": _sha256(path),
        "schema": schema,
        "row_counts": row_counts,
        "wal": _sidecar_fingerprint(Path(f"{path}-wal")),
        "shm": _sidecar_fingerprint(Path(f"{path}-shm")),
    }


def _sidecar_fingerprint(path: Path) -> tuple[bool, str | None]:
    return path.exists(), _sha256(path) if path.exists() else None


def _file_tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _seed_incomplete_drawing(
    db_path: Path,
    *,
    with_reconciliation_state: bool,
) -> None:
    engine = init_db(db_path)
    factory = get_session_factory(engine)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11955,
                number=4946,
                name="baltbet-main",
                status="finished",
                ended_at="2026-07-30T10:00:00Z",
            )
        )
        for order in range(15):
            session.add(
                Event(
                    drawing_id=11955,
                    event_order=order,
                    name=f"Event {order}",
                    result=("1", "X", "2")[order % 3] if order < 14 else None,
                    result_status="resolved" if order < 14 else None,
                    score="1 : 0" if order < 14 else None,
                )
            )
            session.add(
                Quote(
                    drawing_id=11955,
                    event_order=order,
                    pool_win_1=40,
                    pool_draw=30,
                    pool_win_2=30,
                    bk_win_1=40,
                    bk_draw=30,
                    bk_win_2=30,
                )
            )
        if with_reconciliation_state:
            session.add(
                DrawingReconciliationState(
                    drawing_id=11955,
                    provider="totobrief",
                    source="/drawing-info/11955",
                    last_attempt_at=NOW.isoformat(),
                    attempt_count=1,
                    last_source_fingerprint="a" * 64,
                    terminal_count=14,
                    classification="source_incomplete",
                    retry_state="cooldown",
                    next_eligible_at="2099-01-01T00:00:00+00:00",
                    last_error_code=None,
                    unchanged_observation_count=1,
                    transient_error_count=0,
                    updated_at=NOW.isoformat(),
                )
            )
    engine.dispose()
    if not with_reconciliation_state:
        with sqlite3.connect(db_path) as connection:
            connection.execute("DROP TABLE drawing_reconciliation_states")


def _run_reconcile_dry_run(tmp_path: Path, db_path: Path):
    return CliRunner().invoke(
        app,
        [
            "reconcile-finished",
            "--db",
            str(db_path),
            "--from-drawing",
            "4946",
            "--to-drawing",
            "4946",
            "--batch-size",
            "1",
            "--state-file",
            str(tmp_path / "state.json"),
            "--raw-archive-root",
            str(tmp_path / "archive"),
            "--dry-run",
        ],
    )


def _complete_payload() -> dict[str, object]:
    return {
        "data": {
            "id": 11955,
            "number": 4946,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-30T10:00:00Z",
            "events": [
                {
                    "id": 1195500 + order,
                    "order": order,
                    "name": f"Event {order}",
                    "championship": "League",
                    "sport": "football",
                    "result": ("1", "X", "2")[order % 3],
                    "result_status": "resolved",
                    "score": "1 : 0",
                    "quotes": {
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }


def test_reconcile_dry_run_is_physically_readonly_without_state_table(
    tmp_path,
):
    db_path = tmp_path / "missing-state.db"
    _seed_incomplete_drawing(
        db_path,
        with_reconciliation_state=False,
    )
    before = _database_fingerprint(db_path)
    files_before = _file_tree_fingerprint(tmp_path)

    result = _run_reconcile_dry_run(tmp_path, db_path)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["selected"] == 1
    assert payload["items"][0]["status"] == "would_reconcile"
    assert _database_fingerprint(db_path) == before
    assert _file_tree_fingerprint(tmp_path) == files_before
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "archive").exists()


def test_reconcile_dry_run_is_physically_readonly_with_state_table(tmp_path):
    db_path = tmp_path / "existing-state.db"
    _seed_incomplete_drawing(
        db_path,
        with_reconciliation_state=True,
    )
    before = _database_fingerprint(db_path)
    files_before = _file_tree_fingerprint(tmp_path)

    result = _run_reconcile_dry_run(tmp_path, db_path)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["selected"] == 1
    assert payload["items"][0]["status"] == "would_skip_cooldown"
    assert _database_fingerprint(db_path) == before
    assert _file_tree_fingerprint(tmp_path) == files_before
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "archive").exists()


def test_repair_canonical_raw_dry_run_is_physically_readonly(tmp_path):
    db_path = tmp_path / "repair.db"
    _seed_incomplete_drawing(
        db_path,
        with_reconciliation_state=False,
    )
    raw_root = tmp_path / "raw"
    payload = {
        "data": {
            "id": 11955,
            "number": 4946,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-30T10:00:00Z",
            "events": [
                {
                    "id": 1195500 + order,
                    "order": order,
                    "name": f"Restored Event {order}",
                    "championship": "League",
                    "sport": "football",
                    "result": (("1", "X", "2")[order % 3] if order < 14 else None),
                    "result_status": "resolved" if order < 14 else None,
                    "score": "1 : 0" if order < 14 else None,
                    "quotes": {
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }
    write_drawing_detail_cache(
        payload,
        drawing_id=11955,
        cache_dir=raw_root,
        fetched_at=datetime.now(timezone.utc),
        source="finished-result",
        allowed_root=tmp_path,
    )
    before = _database_fingerprint(db_path)
    files_before = _file_tree_fingerprint(tmp_path)
    archive_root = tmp_path / "archive"

    result = CliRunner().invoke(
        app,
        [
            "repair-canonical-raw",
            "--db",
            str(db_path),
            "--raw-cache-root",
            str(raw_root),
            "--raw-archive-root",
            str(archive_root),
            "--drawing-number",
            "4946",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["items"][0]["status"] == "would_repair"
    assert _database_fingerprint(db_path) == before
    assert _file_tree_fingerprint(tmp_path) == files_before
    assert not archive_root.exists()
    readonly_engine = open_readonly_db(db_path)
    factory = get_session_factory(readonly_engine)
    with factory() as session:
        assert (
            session.scalar(
                select(Event).where(
                    Event.drawing_id == 11955,
                    Event.event_order == 0,
                )
            ).name
            == "Event 0"
        )
    readonly_engine.dispose()


def test_reconcile_apply_sets_up_missing_schema_before_first_mutation(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "apply.db"
    _seed_incomplete_drawing(
        db_path,
        with_reconciliation_state=False,
    )

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 11955
            return _complete_payload()

    monkeypatch.setattr("toto_ai.cli.TotoBriefClient", Client)
    result = CliRunner().invoke(
        app,
        [
            "reconcile-finished",
            "--db",
            str(db_path),
            "--from-drawing",
            "4946",
            "--to-drawing",
            "4946",
            "--batch-size",
            "1",
            "--max-attempts",
            "1",
            "--rate-limit-seconds",
            "0",
            "--state-file",
            str(tmp_path / "state.json"),
            "--raw-archive-root",
            str(tmp_path / "archive"),
            "--apply",
        ],
    )

    assert result.exit_code == 0, result.output
    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM drawing_reconciliation_states"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM drawing_result_snapshots "
                "WHERE drawing_id = 11955 AND complete = 1"
            ).fetchone()[0]
            == 1
        )
