"""Restart-safe plan-scoped state and lock for scheduler ticks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_SCHEMA_VERSION = 1
PHASES = ("warmup", "refresh", "final", "publish")


def initial_state(plan_id: str, now: datetime) -> dict[str, Any]:
    timestamp = _timestamp(now)
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "plan_id": plan_id,
        "revision": 0,
        "updated_at": timestamp,
        "phases": {
            "warmup": {"status": "pending", "attempts": []},
            "refresh": {"status": "pending", "attempts": []},
            "final": {"status": "pending", "attempts": []},
            "publish": {"status": "pending", "attempts": []},
        },
        "terminal": None,
        "transitions": [],
        "previous_state_sha256": None,
    }
    state["state_sha256"] = state_sha256(state)
    return state


def state_sha256(state: Mapping[str, Any]) -> str:
    unsigned = json.loads(json.dumps(state))
    unsigned.pop("state_sha256", None)
    for record in unsigned.get("transitions", []):
        record.pop("current_state_sha256", None)
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def load_state(path: Path, *, plan_id: str, now: datetime) -> dict[str, Any]:
    if not path.exists():
        return initial_state(plan_id, now)
    if path.is_symlink() or not path.is_file():
        raise ValueError("scheduler state must be a regular non-symlink file")
    try:
        state = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("scheduler state could not be loaded") from error
    if not isinstance(state, dict) or state.get("plan_id") != plan_id:
        raise ValueError("scheduler state plan identity mismatch")
    if state.get("state_sha256") != state_sha256(state):
        raise ValueError("scheduler state hash mismatch")
    if set(state.get("phases", {})) != set(PHASES):
        raise ValueError("scheduler state phase set is invalid")
    return state


def transition(
    state: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    observed_at: datetime,
    attempt_id: str | None = None,
    reason: str | None = None,
    terminal: str | None = None,
) -> dict[str, Any]:
    if phase not in PHASES:
        raise ValueError("unknown scheduler phase")
    previous_hash = state_sha256(state)
    updated = json.loads(json.dumps(state))
    updated["revision"] = int(updated["revision"]) + 1
    updated["updated_at"] = _timestamp(observed_at)
    updated["previous_state_sha256"] = previous_hash
    updated["phases"][phase]["status"] = status
    if attempt_id is not None:
        attempts = updated["phases"][phase]["attempts"]
        if attempt_id not in attempts:
            attempts.append(attempt_id)
    record = {
        "phase": phase,
        "status": status,
        "observed_at": _timestamp(observed_at),
        "attempt_id": attempt_id,
        "reason": reason,
        "previous_state_sha256": previous_hash,
    }
    updated["transitions"].append(record)
    if terminal is not None:
        updated["terminal"] = terminal
    updated["state_sha256"] = state_sha256(updated)
    record["current_state_sha256"] = updated["state_sha256"]
    return updated


def recover_orphan(state: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    updated = dict(state)
    for phase in PHASES:
        if updated["phases"][phase]["status"] == "running":
            attempts = updated["phases"][phase]["attempts"]
            updated = transition(
                updated,
                phase=phase,
                status="retryable_failed",
                observed_at=now,
                attempt_id=attempts[-1] if attempts else None,
                reason="orphaned_running_attempt",
            )
    return updated


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    if state.get("state_sha256") != state_sha256(state):
        raise ValueError("refusing to persist inconsistent scheduler state")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("scheduler state path cannot traverse symlinks")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(state) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def scheduler_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("scheduler lock path cannot traverse symlinks")
    descriptor = os.open(
        path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduler state timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
