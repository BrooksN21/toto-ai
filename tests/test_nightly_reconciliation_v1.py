from __future__ import annotations

import hashlib
import json
import plistlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.db.models import Drawing, DrawingReconciliationState, Event, Quote
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.nightly_reconciliation import (
    NightlyReconciliationConfig,
    generate_nightly_reconciliation_artifacts,
    run_nightly_reconciliation,
)
from toto_ai.runner.morning_dispatch import MorningDispatchConfig

NOW = datetime(2026, 7, 30, 0, 20, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, payloads: dict[int, dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls: list[int] = []

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        self.calls.append(drawing_id)
        return self.payloads[drawing_id]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload(
    drawing_id: int,
    number: int,
    *,
    terminal_count: int,
) -> dict[str, object]:
    return {
        "data": {
            "id": drawing_id,
            "number": number,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-29T20:00:00Z",
            "events": [
                {
                    "id": drawing_id * 100 + order,
                    "order": order,
                    "name": f"Event {number}-{order}",
                    "championship": "League",
                    "sport": "football",
                    "result": (
                        ("1", "X", "2")[order % 3]
                        if order < terminal_count
                        else None
                    ),
                    "result_status": (
                        "resolved" if order < terminal_count else None
                    ),
                    "score": "1 : 0" if order < terminal_count else None,
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


def _database(
    tmp_path: Path,
    *,
    finished: tuple[tuple[int, int], ...] = (
        (11990, 4960),
        (11992, 4961),
    ),
    active: tuple[tuple[int, int], ...] = ((11994, 4962),),
) -> Path:
    db_path = tmp_path / "data" / "toto.db"
    factory = get_session_factory(init_db(db_path))
    with factory.begin() as session:
        for drawing_id, number in (*finished, *active):
            status = "finished" if (drawing_id, number) in finished else "active"
            session.add(
                Drawing(
                    id=drawing_id,
                    number=number,
                    name="baltbet-main",
                    status=status,
                    ended_at="2026-07-29T20:00:00Z",
                )
            )
            for order in range(15):
                session.add(
                    Event(
                        drawing_id=drawing_id,
                        event_order=order,
                        name=f"Event {number}-{order}",
                    )
                )
                session.add(
                    Quote(
                        drawing_id=drawing_id,
                        event_order=order,
                        pool_win_1=40,
                        pool_draw=30,
                        pool_win_2=30,
                        bk_win_1=40,
                        bk_draw=30,
                        bk_win_2=30,
                    )
                )
    return db_path


def _config(tmp_path: Path, db_path: Path, **overrides: object):
    values = {
        "project_root": tmp_path,
        "db_path": db_path,
        "state_root": tmp_path / "data" / "nightly-reconciliation",
        "raw_archive_root": tmp_path / "data" / "raw" / "archive",
        "backup_root": tmp_path / "data" / "backups",
        "recent_finished": 30,
        "max_network_attempts": 8,
        "timeout_seconds": 240.0,
        "backup_retention": 7,
        "lock_wait_seconds": 0.0,
        "stale_lock_seconds": 3600.0,
    }
    values.update(overrides)
    return NightlyReconciliationConfig(**values)


def test_artifacts_default_to_0320_and_are_passive_safe(tmp_path: Path) -> None:
    root = tmp_path
    (root / ".venv" / "bin").mkdir(parents=True)
    python = root / ".venv" / "bin" / "python"
    python.write_bytes(b"#!/bin/sh\n")
    python.chmod(0o755)
    db_path = _database(tmp_path)

    artifacts = generate_nightly_reconciliation_artifacts(
        project_root=root,
        output_dir=root / "reports" / "nightly-reconciliation",
        db_path=db_path,
        python_executable=python,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert plist["StartCalendarInterval"] == {"Hour": 3, "Minute": 20}
    assert plist["WorkingDirectory"] == str(root.resolve())
    assert plist["ProgramArguments"] == [str(artifacts.wrapper_path)]
    assert "nightly-reconciliation-run" in wrapper
    assert "--last-finished 30" in wrapper
    assert "--max-network-attempts 8" in wrapper
    assert "--no-force" in wrapper
    assert str(db_path.resolve()) in wrapper
    forbidden = (
        "run-drawing",
        "scheduler-execute",
        "package",
        "upload",
        "bet-ready",
        "archive-package",
    )
    assert not any(token in wrapper.lower() for token in forbidden)
    assert artifacts.installed is False


def test_artifact_schedule_is_configurable_and_generate_only(tmp_path: Path) -> None:
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    python = tmp_path / ".venv" / "bin" / "python"
    python.write_bytes(b"#!/bin/sh\n")
    python.chmod(0o755)
    db_path = _database(tmp_path)

    artifacts = generate_nightly_reconciliation_artifacts(
        project_root=tmp_path,
        output_dir=tmp_path / "reports" / "nightly-custom",
        db_path=db_path,
        python_executable=python,
        hour=4,
        minute=5,
    )

    plist = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert plist["StartCalendarInterval"] == {"Hour": 4, "Minute": 5}
    assert not (tmp_path / "Library" / "LaunchAgents").exists()


def test_cli_plan_generates_only_repo_report_artifacts(tmp_path: Path) -> None:
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    python = tmp_path / ".venv" / "bin" / "python"
    python.write_bytes(b"#!/bin/sh\n")
    python.chmod(0o755)
    db_path = _database(tmp_path)
    output = tmp_path / "reports" / "nightly-cli"

    result = CliRunner().invoke(
        app,
        [
            "nightly-reconciliation-plan",
            "--project-root",
            str(tmp_path),
            "--db",
            str(db_path),
            "--output-dir",
            str(output),
            "--python-executable",
            str(python),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Generated only; nothing was installed or launched." in result.output
    assert (output / "run-nightly-reconciliation.sh").is_file()
    assert (output / "totoai-nightly-reconciliation.plist").is_file()


def test_nightly_and_morning_use_same_global_maintenance_lock(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    env_file.chmod(0o600)
    aliases = tmp_path / "data" / "aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    morning = MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "data" / "morning",
        scheduler_root=tmp_path / "reports" / "scheduler",
        env_file=env_file,
        bank=4980,
        db=db_path,
        aliases=aliases,
    )
    nightly = _config(tmp_path, db_path)
    assert morning.maintenance_lock == nightly.lock_path


def test_complete_plus_source_incomplete_is_partial_then_second_run_noop(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=14),
        }
    )
    config = _config(tmp_path, db_path)

    first = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: NOW,
    )

    assert first.classification == "PARTIAL"
    assert first.captured_drawing_numbers == (4960, 4961)
    assert first.network_attempts == 2
    assert first.complete == 1
    assert first.source_incomplete == 1
    assert first.backup_path is not None
    assert first.backup_manifest_path is not None
    assert first.backup_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(first.backup_manifest_path.read_text())["quick_check"] == "ok"
    backup_count = len(tuple(config.backup_root.glob("*.db")))

    second = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: NOW + timedelta(minutes=1),
    )

    assert second.classification == "DEFERRED"
    assert second.reason == "no_eligible_drawings"
    assert second.network_attempts == 0
    assert second.backup_path is None
    assert len(tuple(config.backup_root.glob("*.db"))) == backup_count
    assert client.calls == [11990, 11992]


def test_scope_is_last_finished_not_last_incomplete(tmp_path: Path) -> None:
    finished = tuple((10_000 + number, number) for number in range(4900, 4940))
    db_path = _database(tmp_path, finished=finished, active=())
    client = FakeClient(
        {
            drawing_id: _payload(drawing_id, number, terminal_count=15)
            for drawing_id, number in finished
        }
    )
    config = _config(
        tmp_path,
        db_path,
        recent_finished=30,
        max_network_attempts=8,
    )

    result = run_nightly_reconciliation(config, client=client, now=lambda: NOW)

    assert result.captured_drawing_numbers == tuple(range(4910, 4918))
    assert client.calls == [10_000 + number for number in range(4910, 4918)]


def test_captured_selection_drift_aborts_before_backup_or_network(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=15),
        }
    )
    config = _config(tmp_path, db_path)

    def mutate_between_selection_and_apply() -> None:
        factory = get_session_factory(init_db(db_path))
        with factory.begin() as session:
            drawing = session.scalar(select(Drawing).where(Drawing.number == 4961))
            assert drawing is not None
            drawing.status = "active"

    result = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: NOW,
        before_apply=mutate_between_selection_and_apply,
    )

    assert result.classification == "FAILED"
    assert result.reason == "captured_selection_drift"
    assert result.network_attempts == 0
    assert result.backup_path is None


def test_cooldown_expiry_during_run_does_not_change_captured_selection(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    factory = get_session_factory(init_db(db_path))
    with factory.begin() as session:
        session.add(
            DrawingReconciliationState(
                drawing_id=11992,
                provider="totobrief",
                source="/drawing-info/11992",
                last_attempt_at=(NOW - timedelta(minutes=1)).isoformat(),
                attempt_count=1,
                last_source_fingerprint="source-incomplete",
                terminal_count=0,
                classification="source_incomplete",
                retry_state="cooldown",
                next_eligible_at=(NOW + timedelta(minutes=1)).isoformat(),
                last_error_code=None,
                unchanged_observation_count=1,
                transient_error_count=0,
                updated_at=(NOW - timedelta(minutes=1)).isoformat(),
            )
        )
    client = FakeClient(
        {11990: _payload(11990, 4960, terminal_count=15)}
    )
    config = _config(tmp_path, db_path)
    clock = {"now": NOW}

    def advance_past_cooldown() -> None:
        clock["now"] = NOW + timedelta(minutes=2)

    result = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: clock["now"],
        before_apply=advance_past_cooldown,
    )

    assert result.classification == "SUCCESS"
    assert result.reason == "all_captured_drawings_complete"
    assert result.captured_drawing_numbers == (4960,)
    assert result.network_attempts == 1
    assert client.calls == [11990]


def test_result_fingerprint_change_during_run_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=15),
        }
    )
    config = _config(tmp_path, db_path)

    def mutate_result_without_completing_drawing() -> None:
        factory = get_session_factory(init_db(db_path))
        with factory.begin() as session:
            event = session.scalar(
                select(Event).where(
                    Event.drawing_id == 11992,
                    Event.event_order == 0,
                )
            )
            assert event is not None
            event.result = "1"
            event.result_status = "resolved"
            event.score = "1 : 0"

    result = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: NOW,
        before_apply=mutate_result_without_completing_drawing,
    )

    assert result.classification == "FAILED"
    assert result.reason == "captured_selection_drift"
    assert result.network_attempts == 0
    assert result.backup_path is None


def test_non_overlap_and_stale_metadata_recovery(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    config = _config(tmp_path, db_path)
    config.state_root.mkdir(parents=True)
    config.lock_path.parent.mkdir(parents=True)
    config.lock_path.write_text(
        json.dumps(
            {
                "status": "running",
                "pid": 999_999_999,
                "started_at": (NOW - timedelta(hours=2)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=15),
        }
    )

    recovered = run_nightly_reconciliation(config, client=client, now=lambda: NOW)
    assert recovered.stale_lock_recovered is True

    from toto_ai.operations.nightly_reconciliation import global_operation_lock

    with global_operation_lock(config, now=lambda: NOW):
        blocked = run_nightly_reconciliation(config, client=client, now=lambda: NOW)
    assert blocked.classification == "DEFERRED"
    assert blocked.reason == "operation_lock_busy"
    assert blocked.network_attempts == 0
    assert blocked.backup_path is None


def test_backup_retention_keeps_at_least_one_known_good(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    config = _config(tmp_path, db_path, backup_retention=2)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=14),
            11992: _payload(11992, 4961, terminal_count=14),
        }
    )

    for day in range(4):
        run_nightly_reconciliation(
            config,
            client=client,
            now=lambda day=day: NOW + timedelta(days=day),
            force_for_test=True,
        )

    backups = sorted(config.backup_root.glob("*.db"))
    manifests = sorted(config.backup_root.glob("*.manifest.json"))
    assert len(backups) == 2
    assert len(manifests) == 2
    assert all(json.loads(path.read_text())["known_good"] for path in manifests)
    assert all(_sha256(path) for path in backups)


def test_timeout_stops_before_next_network_attempt(tmp_path: Path) -> None:
    db_path = _database(tmp_path)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=15),
        }
    )
    ticks = iter((0.0, 0.0, 0.0, 2.0, 2.0, 2.0))
    config = _config(tmp_path, db_path, timeout_seconds=1.0)

    result = run_nightly_reconciliation(
        config,
        client=client,
        now=lambda: NOW,
        monotonic=lambda: next(ticks),
    )

    assert result.classification == "PARTIAL"
    assert result.timed_out is True
    assert result.network_attempts == 1
    assert client.calls == [11990]


def test_backup_is_valid_online_copy_and_main_db_remains_usable(
    tmp_path: Path,
) -> None:
    db_path = _database(tmp_path)
    client = FakeClient(
        {
            11990: _payload(11990, 4960, terminal_count=15),
            11992: _payload(11992, 4961, terminal_count=15),
        }
    )
    result = run_nightly_reconciliation(
        _config(tmp_path, db_path),
        client=client,
        now=lambda: NOW,
    )
    assert result.backup_path is not None
    with sqlite3.connect(result.backup_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_config_rejects_db_outside_project_and_invalid_limits(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.db"
    outside.write_bytes(b"")
    with pytest.raises(ValueError, match="db_path"):
        _config(tmp_path, outside)
    db_path = _database(tmp_path)
    with pytest.raises(ValueError, match="max_network_attempts"):
        _config(tmp_path, db_path, max_network_attempts=0)
    with pytest.raises(ValueError, match="backup_retention"):
        _config(tmp_path, db_path, backup_retention=0)
