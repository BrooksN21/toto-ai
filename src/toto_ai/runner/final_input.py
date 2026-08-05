"""Immutable, exact TotoBrief input for one production final attempt."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from toto_ai.api.client import TotoBriefClient
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.package.audit import canonical_probability_input_sha256

if TYPE_CHECKING:
    from toto_ai.runner.scheduler import SchedulerPlan

FINAL_INPUT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FinalInputSnapshot:
    schema_version: int
    plan_id: str
    attempt_id: str
    drawing_id: int
    drawing_number: int
    deadline: datetime
    captured_at: datetime
    target_fingerprint: str
    detail_payload_sha256: str
    probability_input_sha256: str
    timing_override_sha256: str | None
    payload: Mapping[str, object]
    snapshot_sha256: str
    path: Path


def capture_final_input(
    *,
    client: TotoBriefClient,
    plan: SchedulerPlan,
    attempt_id: str,
    now: Callable[[], datetime] | None = None,
    destination: Path,
    timing_override_sha256: str | None,
) -> FinalInputSnapshot:
    """Fetch exact detail once, validate it, and exclusively persist it."""
    if plan.drawing_id is None:
        raise ValueError("atomic final requires an exact drawing_id")
    payload = client.drawing_info(plan.drawing_id)
    captured = _utc(
        datetime.now(timezone.utc) if now is None else now(),
        "captured_at",
    )
    if not isinstance(payload, Mapping):
        raise ValueError("final drawing detail must be a mapping")
    return persist_final_input(
        payload,
        plan=plan,
        attempt_id=attempt_id,
        captured_at=captured,
        destination=destination,
        timing_override_sha256=timing_override_sha256,
    )


def persist_final_input(
    payload: Mapping[str, object],
    *,
    plan: SchedulerPlan,
    attempt_id: str,
    captured_at: datetime,
    destination: Path,
    timing_override_sha256: str | None,
) -> FinalInputSnapshot:
    """Persist an already captured payload without any network access."""
    captured = _utc(captured_at, "captured_at")
    if captured > plan.ended_at:
        raise ValueError("final input was captured after drawing deadline")
    if not attempt_id or len(attempt_id) > 128:
        raise ValueError("attempt_id must be non-empty and bounded")
    target = parse_target_drawing(payload, captured)
    if (
        target.drawing_id != plan.drawing_id
        or target.drawing_number != plan.drawing
        or target.deadline != plan.ended_at
    ):
        raise ValueError("final input drawing identity does not match plan")
    payload_copy = json.loads(_canonical_bytes(payload))
    detail_hash = _sha256(_canonical_bytes(payload_copy))
    probability_hash = canonical_probability_input_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    fingerprint = target_fingerprint(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        deadline=target.deadline,
        events=target.events,
    )
    metadata = {
        "schema_version": FINAL_INPUT_SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "attempt_id": attempt_id,
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "deadline": _timestamp(target.deadline),
        "captured_at": _timestamp(captured),
        "target_fingerprint": fingerprint,
        "detail_payload_sha256": detail_hash,
        "probability_input_sha256": probability_hash,
        "timing_override_sha256": timing_override_sha256,
        "payload": payload_copy,
    }
    snapshot_hash = _sha256(_canonical_bytes(metadata))
    document = {**metadata, "snapshot_sha256": snapshot_hash}
    path = Path(destination).absolute()
    _write_exclusive(path, _canonical_bytes(document) + b"\n")
    return _snapshot(document, path)


def load_final_input(
    path: Path, *, expected_plan: SchedulerPlan
) -> FinalInputSnapshot:
    resolved = Path(path).absolute()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("final input must be a regular non-symlink file")
    try:
        document = json.loads(resolved.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("final input could not be loaded") from error
    if not isinstance(document, dict):
        raise ValueError("final input must be a JSON object")
    declared = document.get("snapshot_sha256")
    unsigned = dict(document)
    unsigned.pop("snapshot_sha256", None)
    if not isinstance(declared, str) or declared != _sha256(
        _canonical_bytes(unsigned)
    ):
        raise ValueError("final input snapshot hash mismatch")
    snapshot = _snapshot(document, resolved)
    if snapshot.plan_id != expected_plan.plan_id:
        raise ValueError("final input plan identity mismatch")
    target = parse_target_drawing(snapshot.payload, snapshot.captured_at)
    if (
        target.drawing_id != expected_plan.drawing_id
        or target.drawing_number != expected_plan.drawing
        or target.deadline != expected_plan.ended_at
        or target_fingerprint(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            deadline=target.deadline,
            events=target.events,
        )
        != snapshot.target_fingerprint
    ):
        raise ValueError("final input target identity mismatch")
    if snapshot.captured_at > expected_plan.ended_at:
        raise ValueError("final input was captured after drawing deadline")
    if (
        _sha256(_canonical_bytes(dict(snapshot.payload)))
        != snapshot.detail_payload_sha256
    ):
        raise ValueError("final input detail payload hash mismatch")
    probability_hash = canonical_probability_input_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    if probability_hash != snapshot.probability_input_sha256:
        raise ValueError("final input probability hash mismatch")
    return snapshot


def _snapshot(document: Mapping[str, Any], path: Path) -> FinalInputSnapshot:
    required = {
        "schema_version",
        "plan_id",
        "attempt_id",
        "drawing_id",
        "drawing_number",
        "deadline",
        "captured_at",
        "target_fingerprint",
        "detail_payload_sha256",
        "probability_input_sha256",
        "timing_override_sha256",
        "payload",
        "snapshot_sha256",
    }
    if set(document) != required:
        raise ValueError("final input fields are invalid")
    if document["schema_version"] != FINAL_INPUT_SCHEMA_VERSION:
        raise ValueError("unsupported final input schema")
    payload = document["payload"]
    if not isinstance(payload, Mapping):
        raise ValueError("final input payload must be a mapping")
    return FinalInputSnapshot(
        schema_version=FINAL_INPUT_SCHEMA_VERSION,
        plan_id=str(document["plan_id"]),
        attempt_id=str(document["attempt_id"]),
        drawing_id=int(document["drawing_id"]),
        drawing_number=int(document["drawing_number"]),
        deadline=_parse_timestamp(document["deadline"]),
        captured_at=_parse_timestamp(document["captured_at"]),
        target_fingerprint=str(document["target_fingerprint"]),
        detail_payload_sha256=str(document["detail_payload_sha256"]),
        probability_input_sha256=str(document["probability_input_sha256"]),
        timing_override_sha256=document["timing_override_sha256"],
        payload=MappingProxyType(dict(payload)),
        snapshot_sha256=str(document["snapshot_sha256"]),
        path=path,
    )


def _write_exclusive(path: Path, content: bytes) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or path.is_symlink():
        raise ValueError("final input path cannot traverse a symlink")
    temporary = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("final input timestamp must be a string")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")
    except ValueError as error:
        raise ValueError("final input timestamp is invalid") from error
