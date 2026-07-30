"""Passive, bounded nightly reconciliation orchestration.

This module deliberately owns no package generation, scheduler activation,
upload, or betting behavior.  It wraps the proven finished-drawing
reconciliation engine with an exact captured selection, a pre-mutation SQLite
backup, non-overlap locking, bounded execution, and auditable run artifacts.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import plistlib
import secrets
import shlex
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select

from toto_ai.analytics.data_health import audit_data_health
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db, open_readonly_db
from toto_ai.operations.reconciliation import (
    ReconciliationConfig,
    ReconciliationItem,
    reconcile_finished_drawings,
)

NIGHTLY_SCHEMA_VERSION = 1
DEFAULT_HOUR = 3
DEFAULT_MINUTE = 20
DEFAULT_RECENT_FINISHED = 30
DEFAULT_MAX_NETWORK_ATTEMPTS = 8
DEFAULT_TIMEOUT_SECONDS = 240.0
DEFAULT_BACKUP_RETENTION = 7
NIGHTLY_LABEL = "com.totoai.nightly-reconciliation.v1"
NIGHTLY_WRAPPER_FILENAME = "run-nightly-reconciliation.sh"
NIGHTLY_PLIST_FILENAME = "totoai-nightly-reconciliation.plist"
_PROCESS_HELD_LOCKS: set[Path] = set()


class OperationLockBusy(RuntimeError):
    """Raised when another compatible operation owns the global lock."""


@dataclass(frozen=True)
class NightlyReconciliationConfig:
    project_root: Path
    db_path: Path
    state_root: Path
    raw_archive_root: Path
    backup_root: Path
    recent_finished: int = DEFAULT_RECENT_FINISHED
    max_network_attempts: int = DEFAULT_MAX_NETWORK_ATTEMPTS
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    backup_retention: int = DEFAULT_BACKUP_RETENTION
    lock_wait_seconds: float = 0.0
    stale_lock_seconds: float = 2 * 60 * 60

    def __post_init__(self) -> None:
        root = Path(self.project_root).resolve()
        if not root.is_dir() or root.is_symlink():
            raise ValueError("project_root must be an existing regular directory")
        object.__setattr__(self, "project_root", root)
        for name in ("db_path", "state_root", "raw_archive_root", "backup_root"):
            value = Path(getattr(self, name))
            if not value.is_absolute():
                value = root / value
            value = value.resolve()
            if not value.is_relative_to(root):
                raise ValueError(f"{name} must remain inside project_root")
            object.__setattr__(self, name, value)
        if not self.db_path.is_file() or self.db_path.is_symlink():
            raise ValueError("db_path must be an existing regular SQLite file")
        for name in (
            "recent_finished",
            "max_network_attempts",
            "backup_retention",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("timeout_seconds", "lock_wait_seconds", "stale_lock_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @property
    def lock_path(self) -> Path:
        return self.project_root / "data" / "operations" / "global-maintenance.lock"


@dataclass(frozen=True)
class NightlyArtifacts:
    wrapper_path: Path
    launch_agent_path: Path
    schedule_hour: int
    schedule_minute: int
    installed: bool = False


@dataclass(frozen=True)
class LockLease:
    path: Path
    stale_recovered: bool


@dataclass(frozen=True)
class NightlyRunResult:
    schema_version: int
    run_id: str
    classification: Literal["SUCCESS", "PARTIAL", "DEFERRED", "FAILED"]
    reason: str
    started_at: str
    finished_at: str
    captured_drawing_numbers: tuple[int, ...]
    network_attempts: int
    complete: int
    source_incomplete: int
    transient_errors: int
    timed_out: bool
    stale_lock_recovered: bool
    backup_path: Path | None
    backup_manifest_path: Path | None
    run_dir: Path
    report_path: Path
    state_path: Path
    log_path: Path
    data_health_before: dict[str, object] | None
    data_health_after: dict[str, object] | None
    quick_check: str | None
    foreign_key_violations: int | None
    items: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for key in (
            "backup_path",
            "backup_manifest_path",
            "run_dir",
            "report_path",
            "state_path",
            "log_path",
        ):
            value = payload[key]
            payload[key] = None if value is None else str(value)
        return payload


class _CountingClient:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.calls = 0

    def drawing_info(self, drawing_id: int) -> Any:
        self.calls += 1
        return self.client.drawing_info(drawing_id)


def generate_nightly_reconciliation_artifacts(
    *,
    project_root: str | Path,
    output_dir: str | Path,
    db_path: str | Path = "data/toto.db",
    python_executable: str | Path | None = None,
    hour: int = DEFAULT_HOUR,
    minute: int = DEFAULT_MINUTE,
    recent_finished: int = DEFAULT_RECENT_FINISHED,
    max_network_attempts: int = DEFAULT_MAX_NETWORK_ATTEMPTS,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    backup_retention: int = DEFAULT_BACKUP_RETENTION,
) -> NightlyArtifacts:
    """Generate wrapper/plist artifacts inside the project; never install them."""
    _validate_schedule(hour, minute)
    root = Path(project_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("project_root must be an existing regular directory")
    destination = _contained(root, output_dir, "output_dir")
    reports_root = root / "reports"
    if not destination.is_relative_to(reports_root):
        raise ValueError("output_dir must remain inside project_root/reports")
    database = _contained(root, db_path, "db_path")
    if not database.is_file() or database.is_symlink():
        raise ValueError("db_path must be an existing regular file")
    executable = Path(
        python_executable or root / ".venv" / "bin" / "python"
    ).absolute()
    try:
        resolved_executable = executable.resolve(strict=True)
    except OSError as error:
        raise ValueError("python_executable does not exist") from error
    if (
        not resolved_executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise ValueError("python_executable must be an executable regular file")
    if (
        not executable.is_relative_to(root / ".venv" / "bin")
        or executable.name not in {"python", "python3"}
    ):
        raise ValueError("python_executable must remain inside project_root")
    for name, value in (
        ("recent_finished", recent_finished),
        ("max_network_attempts", max_network_attempts),
        ("backup_retention", backup_retention),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be positive")

    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError("output_dir cannot be a symlink")
    logs = destination / "logs"
    logs.mkdir(exist_ok=True)
    wrapper_path = destination / NIGHTLY_WRAPPER_FILENAME
    plist_path = destination / NIGHTLY_PLIST_FILENAME
    command = (
        str(executable),
        "-m",
        "toto_ai.cli",
        "nightly-reconciliation-run",
        "--db",
        str(database),
        "--project-root",
        str(root),
        "--last-finished",
        str(recent_finished),
        "--max-network-attempts",
        str(max_network_attempts),
        "--timeout-seconds",
        str(float(timeout_seconds)),
        "--backup-retention",
        str(backup_retention),
        "--state-root",
        str(root / "data" / "nightly-reconciliation"),
        "--raw-archive-root",
        str(root / "data" / "raw" / "archive"),
        "--backup-root",
        str(root / "data" / "backups"),
        "--request-state-file",
        str(root / "data" / "totobrief-cache" / "request-state.json"),
        "--no-force",
    )
    wrapper = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd {shlex.quote(str(root))}\n"
        f"exec {' '.join(shlex.quote(value) for value in command)}\n"
    )
    _write_exclusive(wrapper_path, wrapper.encode("utf-8"), mode=0o755)
    plist = {
        "Label": NIGHTLY_LABEL,
        "ProgramArguments": [str(wrapper_path)],
        "WorkingDirectory": str(root),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "stdout.log"),
        "StandardErrorPath": str(logs / "stderr.log"),
    }
    try:
        _write_exclusive(
            plist_path,
            plistlib.dumps(plist, sort_keys=True),
            mode=0o600,
        )
    except BaseException:
        wrapper_path.unlink(missing_ok=True)
        raise
    return NightlyArtifacts(
        wrapper_path=wrapper_path,
        launch_agent_path=plist_path,
        schedule_hour=hour,
        schedule_minute=minute,
    )


@contextmanager
def global_operation_lock(
    config: NightlyReconciliationConfig,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[LockLease]:
    """Acquire a non-overlapping maintenance lock with stale metadata recovery."""
    path = config.lock_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("operation lock path cannot traverse symlinks")
    resolved = path.resolve()
    if resolved in _PROCESS_HELD_LOCKS:
        raise OperationLockBusy("operation lock is already held")
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    started_wait = monotonic()
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError as error:
                if monotonic() - started_wait >= config.lock_wait_seconds:
                    raise OperationLockBusy("operation lock is busy") from error
                sleep(min(0.1, config.lock_wait_seconds))
        _PROCESS_HELD_LOCKS.add(resolved)
        observed = _aware(now())
        previous = _read_lock_metadata(descriptor)
        stale = _metadata_is_stale(
            previous,
            observed_at=observed,
            stale_seconds=config.stale_lock_seconds,
        )
        _write_lock_metadata(
            descriptor,
            {
                "schema_version": 1,
                "status": "running",
                "pid": os.getpid(),
                "started_at": observed.isoformat(),
                "stale_recovered": stale,
            },
        )
        try:
            yield LockLease(path=path, stale_recovered=stale)
        finally:
            _write_lock_metadata(
                descriptor,
                {
                    "schema_version": 1,
                    "status": "released",
                    "pid": os.getpid(),
                    "released_at": _aware(now()).isoformat(),
                },
            )
    finally:
        if acquired:
            _PROCESS_HELD_LOCKS.discard(resolved)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def run_nightly_reconciliation(
    config: NightlyReconciliationConfig,
    *,
    client: Any,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    before_apply: Callable[[], None] | None = None,
    force_for_test: bool = False,
) -> NightlyRunResult:
    """Run one bounded passive reconciliation cycle."""
    started = _aware(now())
    run_id = _run_id(started)
    run_dir = config.state_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    report_path = run_dir / "report.json"
    state_path = run_dir / "state.json"
    log_path = run_dir / "events.jsonl"
    start_tick = monotonic()
    lease: LockLease | None = None
    try:
        with global_operation_lock(
            config,
            now=now,
            monotonic=monotonic,
            sleep=sleep,
        ) as lease:
            _append_log(log_path, "lock_acquired", stale=lease.stale_recovered)
            scope_numbers = _recent_finished_numbers(
                config.db_path,
                limit=config.recent_finished,
            )
            selection = _eligible_numbers(
                config,
                scope_numbers=scope_numbers,
                force=force_for_test,
                now=now,
            )
            captured = selection[: config.max_network_attempts]
            if not captured:
                return _finish(
                    config,
                    run_id=run_id,
                    classification="DEFERRED",
                    reason="no_eligible_drawings",
                    started=started,
                    now=now,
                    run_dir=run_dir,
                    report_path=report_path,
                    state_path=state_path,
                    log_path=log_path,
                    captured=(),
                    network_attempts=0,
                    stale_lock_recovered=lease.stale_recovered,
                )
            if before_apply is not None:
                before_apply()
            confirmed = _eligible_numbers(
                config,
                scope_numbers=scope_numbers,
                force=force_for_test,
                now=now,
            )
            if confirmed != selection:
                return _finish(
                    config,
                    run_id=run_id,
                    classification="FAILED",
                    reason="captured_selection_drift",
                    started=started,
                    now=now,
                    run_dir=run_dir,
                    report_path=report_path,
                    state_path=state_path,
                    log_path=log_path,
                    captured=captured,
                    network_attempts=0,
                    stale_lock_recovered=lease.stale_recovered,
                )

            drawing_ids = _drawing_ids(config.db_path, captured)
            health_before = _health_summary(config.db_path, drawing_ids)
            backup_path, backup_manifest_path = _create_online_backup(
                config,
                observed_at=_aware(now()),
            )
            _cleanup_backups(config)
            counting_client = _CountingClient(client)
            items: list[dict[str, object]] = []
            timed_out = False

            for index, number in enumerate(captured):
                if monotonic() - start_tick >= config.timeout_seconds:
                    timed_out = True
                    for deferred in captured[index:]:
                        items.append(
                            {
                                "drawing_number": deferred,
                                "status": "timeout_deferred",
                                "reason": "run_timeout_before_network_attempt",
                            }
                        )
                    break
                try:
                    report = reconcile_finished_drawings(
                        get_session_factory(init_db(config.db_path)),
                        counting_client,
                        archive_root=config.raw_archive_root,
                        state_path=config.state_root / "finished-state.json",
                        config=ReconciliationConfig(
                            max_attempts=1,
                            initial_backoff_seconds=0,
                            max_backoff_seconds=0,
                            backoff_multiplier=1,
                            rate_limit_seconds=0,
                            batch_size=1,
                            dry_run=False,
                        ),
                        drawing_numbers=(number,),
                        force=force_for_test,
                        now=now,
                        sleep=sleep,
                    )
                except Exception as error:  # one drawing cannot corrupt the run
                    items.append(
                        {
                            "drawing_number": number,
                            "status": "failed",
                            "reason": _safe_error(error),
                        }
                    )
                    continue
                applied = [
                    item
                    for item in report.items
                    if item.status
                    not in {"cooldown", "quarantined", "deferred_batch"}
                ]
                if len(applied) != 1 or applied[0].drawing_number != number:
                    items.append(
                        {
                            "drawing_number": number,
                            "status": "failed",
                            "reason": "captured_selection_changed_during_apply",
                        }
                    )
                    continue
                items.append(_item_dict(applied[0]))
                if monotonic() - start_tick >= config.timeout_seconds:
                    timed_out = index + 1 < len(captured)
                    if timed_out:
                        for deferred in captured[index + 1 :]:
                            items.append(
                                {
                                    "drawing_number": deferred,
                                    "status": "timeout_deferred",
                                    "reason": "run_timeout_after_network_attempt",
                                }
                            )
                    break

            quick_check, foreign_keys = _integrity(config.db_path)
            if quick_check != "ok" or foreign_keys:
                classification = "FAILED"
                reason = "post_apply_integrity_failure"
            else:
                statuses = {str(item.get("status")) for item in items}
                if statuses == {"repaired"} and not timed_out:
                    classification = "SUCCESS"
                    reason = "all_captured_drawings_complete"
                elif "failed" in statuses and statuses <= {"failed"}:
                    classification = "FAILED"
                    reason = "all_captured_drawings_failed"
                else:
                    classification = "PARTIAL"
                    reason = (
                        "bounded_timeout"
                        if timed_out
                        else "source_incomplete_or_transient"
                    )
            health_after = _health_summary(config.db_path, drawing_ids)
            return _finish(
                config,
                run_id=run_id,
                classification=classification,
                reason=reason,
                started=started,
                now=now,
                run_dir=run_dir,
                report_path=report_path,
                state_path=state_path,
                log_path=log_path,
                captured=captured,
                network_attempts=counting_client.calls,
                stale_lock_recovered=lease.stale_recovered,
                backup_path=backup_path,
                backup_manifest_path=backup_manifest_path,
                items=tuple(items),
                timed_out=timed_out,
                data_health_before=health_before,
                data_health_after=health_after,
                quick_check=quick_check,
                foreign_key_violations=len(foreign_keys),
            )
    except OperationLockBusy:
        return _finish(
            config,
            run_id=run_id,
            classification="DEFERRED",
            reason="operation_lock_busy",
            started=started,
            now=now,
            run_dir=run_dir,
            report_path=report_path,
            state_path=state_path,
            log_path=log_path,
            captured=(),
            network_attempts=0,
            stale_lock_recovered=False,
        )
    except Exception as error:
        _append_log(log_path, "run_failed", reason=_safe_error(error))
        return _finish(
            config,
            run_id=run_id,
            classification="FAILED",
            reason=_safe_error(error),
            started=started,
            now=now,
            run_dir=run_dir,
            report_path=report_path,
            state_path=state_path,
            log_path=log_path,
            captured=(),
            network_attempts=0,
            stale_lock_recovered=(
                False if lease is None else lease.stale_recovered
            ),
        )


def _finish(
    config: NightlyReconciliationConfig,
    *,
    run_id: str,
    classification: Literal["SUCCESS", "PARTIAL", "DEFERRED", "FAILED"],
    reason: str,
    started: datetime,
    now: Callable[[], datetime],
    run_dir: Path,
    report_path: Path,
    state_path: Path,
    log_path: Path,
    captured: tuple[int, ...],
    network_attempts: int,
    stale_lock_recovered: bool,
    backup_path: Path | None = None,
    backup_manifest_path: Path | None = None,
    items: tuple[dict[str, object], ...] = (),
    timed_out: bool = False,
    data_health_before: dict[str, object] | None = None,
    data_health_after: dict[str, object] | None = None,
    quick_check: str | None = None,
    foreign_key_violations: int | None = None,
) -> NightlyRunResult:
    result = NightlyRunResult(
        schema_version=NIGHTLY_SCHEMA_VERSION,
        run_id=run_id,
        classification=classification,
        reason=reason,
        started_at=started.isoformat(),
        finished_at=_aware(now()).isoformat(),
        captured_drawing_numbers=captured,
        network_attempts=network_attempts,
        complete=sum(item.get("status") == "repaired" for item in items),
        source_incomplete=sum(
            item.get("status") in {"source_incomplete", "quarantined"}
            for item in items
        ),
        transient_errors=sum(
            item.get("status") in {"transient_error", "failed"} for item in items
        ),
        timed_out=timed_out,
        stale_lock_recovered=stale_lock_recovered,
        backup_path=backup_path,
        backup_manifest_path=backup_manifest_path,
        run_dir=run_dir,
        report_path=report_path,
        state_path=state_path,
        log_path=log_path,
        data_health_before=data_health_before,
        data_health_after=data_health_after,
        quick_check=quick_check,
        foreign_key_violations=foreign_key_violations,
        items=items,
    )
    payload = result.to_dict()
    _atomic_json(report_path, payload)
    _atomic_json(
        state_path,
        {
            "schema_version": NIGHTLY_SCHEMA_VERSION,
            "run_id": run_id,
            "classification": classification,
            "reason": reason,
            "finished_at": result.finished_at,
            "report_sha256": _sha256(report_path),
        },
    )
    _append_log(log_path, "run_finished", classification=classification, reason=reason)
    latest = config.state_root / "latest.json"
    _atomic_json(
        latest,
        {
            "schema_version": NIGHTLY_SCHEMA_VERSION,
            "run_id": run_id,
            "classification": classification,
            "report_path": str(report_path),
            "state_path": str(state_path),
            "finished_at": result.finished_at,
        },
    )
    return result


def _recent_finished_numbers(db_path: Path, *, limit: int) -> tuple[int, ...]:
    engine = open_readonly_db(db_path)
    try:
        factory = get_session_factory(engine)
        with factory() as session:
            rows = session.scalars(
                select(Drawing)
                .where(
                    Drawing.name == "baltbet-main",
                    Drawing.status == "finished",
                    Drawing.number.is_not(None),
                )
                .order_by(Drawing.number.desc(), Drawing.id.desc())
                .limit(limit)
            ).all()
        return tuple(
            drawing.number
            for drawing in reversed(rows)
            if drawing.number is not None
        )
    finally:
        engine.dispose()


def _eligible_numbers(
    config: NightlyReconciliationConfig,
    *,
    scope_numbers: tuple[int, ...],
    force: bool,
    now: Callable[[], datetime],
) -> tuple[int, ...]:
    if not scope_numbers:
        return ()
    engine = open_readonly_db(config.db_path)
    try:
        report = reconcile_finished_drawings(
            get_session_factory(engine),
            client=_NoNetworkClient(),
            archive_root=config.raw_archive_root,
            state_path=config.state_root / "finished-state.json",
            config=ReconciliationConfig(
                max_attempts=1,
                batch_size=config.max_network_attempts,
                dry_run=True,
            ),
            drawing_numbers=scope_numbers,
            force=force,
            now=now,
        )
    finally:
        engine.dispose()
    return tuple(
        item.drawing_number
        for item in report.items
        if item.status in {"would_reconcile", "would_defer_batch"}
    )


class _NoNetworkClient:
    def drawing_info(self, drawing_id: int) -> Any:
        raise AssertionError(f"dry-run attempted network for drawing {drawing_id}")


def _drawing_ids(db_path: Path, numbers: tuple[int, ...]) -> tuple[int, ...]:
    engine = open_readonly_db(db_path)
    try:
        factory = get_session_factory(engine)
        with factory() as session:
            rows = session.scalars(
                select(Drawing).where(Drawing.number.in_(numbers))
            ).all()
        mapping = {row.number: row.id for row in rows}
    finally:
        engine.dispose()
    if set(mapping) != set(numbers):
        raise ValueError("captured drawing identity is missing or ambiguous")
    return tuple(mapping[number] for number in numbers)


def _health_summary(db_path: Path, drawing_ids: tuple[int, ...]) -> dict[str, object]:
    engine = open_readonly_db(db_path)
    try:
        factory = get_session_factory(engine)
        with factory() as session:
            report = audit_data_health(
                session,
                db_path=db_path,
                use_case="historical_inventory",
                strict=False,
                drawing_ids=drawing_ids,
            )
    finally:
        engine.dispose()
    return {
        "contract_version": report.contract_version,
        "total_drawings": report.summary.total_drawings,
        "healthy_drawings": report.summary.healthy_drawings,
        "unhealthy_drawings": report.summary.unhealthy_drawings,
        "reason_counts": report.summary.reason_counts,
    }


def _create_online_backup(
    config: NightlyReconciliationConfig,
    *,
    observed_at: datetime,
) -> tuple[Path, Path]:
    config.backup_root.mkdir(parents=True, exist_ok=True)
    if config.backup_root.is_symlink():
        raise ValueError("backup_root cannot be a symlink")
    stamp = observed_at.strftime("%Y%m%dT%H%M%S%fZ")
    backup = config.backup_root / f"toto-nightly-before-{stamp}.db"
    manifest = config.backup_root / f"toto-nightly-before-{stamp}.manifest.json"
    descriptor = os.open(
        backup,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    os.close(descriptor)
    source_uri = f"{config.db_path.resolve().as_uri()}?mode=ro"
    try:
        with sqlite3.connect(source_uri, uri=True) as source:
            with sqlite3.connect(backup) as destination:
                source.backup(destination)
        os.chmod(backup, 0o600)
        quick_check, foreign_keys = _integrity(backup)
        if quick_check != "ok" or foreign_keys:
            raise ValueError("online backup failed integrity validation")
        payload = {
            "schema_version": 1,
            "created_at": observed_at.isoformat(),
            "source_db": str(config.db_path),
            "backup_path": str(backup),
            "backup_sha256": _sha256(backup),
            "backup_size": backup.stat().st_size,
            "quick_check": quick_check,
            "foreign_key_violations": len(foreign_keys),
            "known_good": True,
        }
        _atomic_json(manifest, payload, mode=0o600)
    except BaseException:
        backup.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        raise
    return backup, manifest


def _cleanup_backups(config: NightlyReconciliationConfig) -> None:
    known_good: list[tuple[Path, Path]] = []
    for manifest in sorted(config.backup_root.glob("toto-nightly-*.manifest.json")):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            backup = Path(payload["backup_path"])
            if (
                payload.get("known_good") is True
                and backup.is_file()
                and not backup.is_symlink()
                and backup.parent.resolve() == config.backup_root
                and payload.get("backup_sha256") == _sha256(backup)
                and _integrity(backup) == ("ok", [])
            ):
                known_good.append((backup, manifest))
        except (OSError, TypeError, ValueError, json.JSONDecodeError, KeyError):
            continue
    excess = max(0, len(known_good) - config.backup_retention)
    for backup, manifest in known_good[:excess]:
        # Retention is at least one, so the newest known-good copy is never removed.
        backup.unlink()
        manifest.unlink()


def _integrity(path: Path) -> tuple[str, list[tuple[Any, ...]]]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    return ("" if quick is None else str(quick[0])), foreign_keys


def _item_dict(item: ReconciliationItem) -> dict[str, object]:
    return {
        "drawing_id": item.drawing_id,
        "drawing_number": item.drawing_number,
        "status": item.status,
        "attempts": item.attempts,
        "terminal_results": item.terminal_results,
        "reason": item.reason,
        "classification": item.classification,
        "retry_state": item.retry_state,
        "next_eligible_at": item.next_eligible_at,
        "last_error_code": item.last_error_code,
        "raw_snapshot_sha256": item.raw_snapshot_sha256,
    }


def _metadata_is_stale(
    payload: dict[str, object] | None,
    *,
    observed_at: datetime,
    stale_seconds: float,
) -> bool:
    if not payload or payload.get("status") != "running":
        return False
    try:
        started = datetime.fromisoformat(str(payload["started_at"]))
        pid = int(payload["pid"])
    except (KeyError, TypeError, ValueError):
        return True
    if started.tzinfo is None or started.utcoffset() is None:
        return True
    age = (observed_at - started.astimezone(timezone.utc)).total_seconds()
    return age >= stale_seconds or not _pid_exists(pid)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno == errno.EPERM
    return True


def _read_lock_metadata(descriptor: int) -> dict[str, object] | None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = os.read(descriptor, 65536)
    if not raw:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_lock_metadata(descriptor: int, payload: dict[str, object]) -> None:
    raw = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    os.write(descriptor, raw)
    os.fsync(descriptor)


def _append_log(path: Path, event: str, **payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"event": event, **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def _atomic_json(path: Path, payload: object, *, mode: int = 0o600) -> None:
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_exclusive(path: Path, payload: bytes, *, mode: int) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _validate_schedule(hour: int, minute: int) -> None:
    if type(hour) is not int or not 0 <= hour <= 23:
        raise ValueError("hour must be from 0 through 23")
    if type(minute) is not int or not 0 <= minute <= 59:
        raise ValueError("minute must be from 0 through 59")


def _contained(root: Path, value: str | Path, name: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{name} must remain inside project_root")
    return resolved


def _run_id(observed_at: datetime) -> str:
    return (
        observed_at.strftime("%Y%m%dT%H%M%S%fZ")
        + f"-{os.getpid()}-{secrets.token_hex(3)}"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("nightly timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_error(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    return f"{type(error).__name__}:{message[:240]}"
