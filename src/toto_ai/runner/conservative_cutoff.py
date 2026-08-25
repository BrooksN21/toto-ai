"""Hash-bound conservative scheduler cutoff evidence.

TotoBrief ``ended_at`` remains drawing identity metadata.  This module derives
an operational upper bound from independently collected fixture kickoffs.  The
bound can only move a scheduler earlier; it can never extend TotoBrief time.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CUTOFF_EVIDENCE_SCHEMA_VERSION = 1
_CANDIDATE_REPORT_SCHEMA_VERSION = 2
_QUALIFYING_STATUSES = frozenset({"independent_candidate", "timing_conflict"})
_DEFAULT_PROVIDERS = frozenset({"goal-api-v1"})


@dataclass(frozen=True)
class ConservativeCutoffEvidence:
    drawing_id: int
    drawing_number: int
    source_ended_at: datetime
    earliest_kickoff: datetime
    operational_cutoff: datetime
    source_report_path: Path
    source_report_sha256: str
    source_report_semantic_hash: str
    provider_names: tuple[str, ...]
    event_orders: tuple[int, ...]
    status: str
    record_sha256: str


def derive_conservative_cutoff(
    source_report_path: str | Path,
    *,
    source_ended_at: datetime | str,
    expected_drawing_id: int,
    expected_drawing_number: int,
    allowed_providers: Sequence[str] = tuple(_DEFAULT_PROVIDERS),
) -> ConservativeCutoffEvidence:
    """Derive a non-extending cutoff from one immutable candidate report."""

    report_path = Path(source_report_path).resolve(strict=True)
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError("cutoff source report must be a regular non-symlink file")
    report_bytes = report_path.read_bytes()
    report = _load_mapping(report_bytes, "cutoff source report")
    _validate_candidate_report_hash(report)
    if report.get("schema_version") != _CANDIDATE_REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported cutoff source report schema")
    if report.get("drawing_id") != expected_drawing_id:
        raise ValueError("cutoff source report drawing ID mismatch")
    if report.get("drawing_number") != expected_drawing_number:
        raise ValueError("cutoff source report drawing number mismatch")

    ended_at = _parse_utc(source_ended_at, "source_ended_at")
    providers = frozenset(
        _required_text(value, "allowed provider") for value in allowed_providers
    )
    if not providers:
        raise ValueError("at least one cutoff provider is required")
    records = report.get("records")
    if not isinstance(records, list):
        raise ValueError("cutoff source report records must be a list")

    qualified: list[tuple[datetime, int, str]] = []
    seen: set[tuple[str, int]] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("cutoff source record must be an object")
        provider = raw.get("source_provider")
        if provider not in providers or raw.get("status") not in _QUALIFYING_STATUSES:
            continue
        if (
            raw.get("source_role") != "independent"
            or raw.get("ledger_eligible") is not False
        ):
            raise ValueError("cutoff source record violates candidate-only boundary")
        if (
            raw.get("drawing_id") != expected_drawing_id
            or raw.get("drawing_number") != expected_drawing_number
        ):
            raise ValueError("cutoff source record drawing identity mismatch")
        order = raw.get("event_order")
        if type(order) is not int or not 0 <= order < 15:
            raise ValueError("cutoff source event_order must be from 0 through 14")
        starts_at = _parse_utc(raw.get("starts_at"), "starts_at")
        identity = (str(provider), order)
        if identity in seen:
            raise ValueError("duplicate cutoff source event record")
        seen.add(identity)
        qualified.append((starts_at, order, str(provider)))
    if not qualified:
        raise ValueError("cutoff source report has no qualifying kickoff evidence")

    earliest = min(item[0] for item in qualified)
    cutoff = min(ended_at, earliest)
    tied = tuple(sorted(item for item in qualified if item[0] == earliest))
    semantic_hash = str(report["report_sha256"])
    payload = _evidence_payload(
        drawing_id=expected_drawing_id,
        drawing_number=expected_drawing_number,
        source_ended_at=ended_at,
        earliest_kickoff=earliest,
        operational_cutoff=cutoff,
        source_report_path=report_path,
        source_report_sha256=hashlib.sha256(report_bytes).hexdigest(),
        source_report_semantic_hash=semantic_hash,
        provider_names=tuple(sorted({item[2] for item in tied})),
        event_orders=tuple(sorted(item[1] for item in tied)),
        status="tightened" if cutoff < ended_at else "unchanged",
    )
    return _evidence_from_payload(payload | {"record_sha256": _sha256_payload(payload)})


def write_conservative_cutoff_evidence(
    evidence: ConservativeCutoffEvidence,
    path: str | Path,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and (output.is_symlink() or not output.is_file()):
        raise ValueError("cutoff evidence output must be a regular file")
    if output.is_file():
        prior = _evidence_from_payload(
            _load_mapping(output.read_bytes(), "existing cutoff evidence")
        )
        if (
            prior.drawing_id != evidence.drawing_id
            or prior.drawing_number != evidence.drawing_number
            or prior.source_ended_at != evidence.source_ended_at
        ):
            raise ValueError("existing cutoff evidence drawing identity conflicts")
        if evidence.operational_cutoff > prior.operational_cutoff:
            raise ValueError("persisted operational cutoff cannot be relaxed")
    data = _serialized_evidence(evidence)
    temporary = output.with_name(
        f".{output.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output.resolve(strict=True)


def load_conservative_cutoff_evidence(
    path: str | Path,
    *,
    project_root: str | Path,
    expected_drawing_id: int,
    expected_drawing_number: int,
    expected_source_ended_at: datetime,
) -> ConservativeCutoffEvidence:
    root = Path(project_root).resolve(strict=True)
    evidence_path = Path(path).resolve(strict=True)
    if not evidence_path.is_relative_to(root):
        raise ValueError("cutoff evidence must remain inside project root")
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise ValueError("cutoff evidence must be a regular non-symlink file")
    payload = _load_mapping(evidence_path.read_bytes(), "cutoff evidence")
    evidence = _evidence_from_payload(payload)
    if evidence.drawing_id != expected_drawing_id:
        raise ValueError("cutoff evidence drawing ID mismatch")
    if evidence.drawing_number != expected_drawing_number:
        raise ValueError("cutoff evidence drawing number mismatch")
    expected_ended_at = _parse_utc(expected_source_ended_at, "expected_source_ended_at")
    if evidence.source_ended_at != expected_ended_at:
        raise ValueError("cutoff evidence source ended_at mismatch")
    if evidence.operational_cutoff > expected_ended_at:
        raise ValueError("operational cutoff cannot extend TotoBrief ended_at")
    source_path = evidence.source_report_path.resolve(strict=True)
    if not source_path.is_relative_to(root):
        raise ValueError("cutoff source report must remain inside project root")
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("cutoff source report must be a regular non-symlink file")
    source_bytes = source_path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != evidence.source_report_sha256:
        raise ValueError("cutoff source report content hash mismatch")
    report = _load_mapping(source_bytes, "cutoff source report")
    _validate_candidate_report_hash(report)
    if report["report_sha256"] != evidence.source_report_semantic_hash:
        raise ValueError("cutoff source report semantic hash mismatch")
    return evidence


def conservative_cutoff_evidence_sha256(evidence: ConservativeCutoffEvidence) -> str:
    return hashlib.sha256(_serialized_evidence(evidence)).hexdigest()


def _serialized_evidence(evidence: ConservativeCutoffEvidence) -> bytes:
    payload = _evidence_payload(
        drawing_id=evidence.drawing_id,
        drawing_number=evidence.drawing_number,
        source_ended_at=evidence.source_ended_at,
        earliest_kickoff=evidence.earliest_kickoff,
        operational_cutoff=evidence.operational_cutoff,
        source_report_path=evidence.source_report_path,
        source_report_sha256=evidence.source_report_sha256,
        source_report_semantic_hash=evidence.source_report_semantic_hash,
        provider_names=evidence.provider_names,
        event_orders=evidence.event_orders,
        status=evidence.status,
    )
    payload["record_sha256"] = evidence.record_sha256
    return (
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        + b"\n"
    )


def _evidence_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": CUTOFF_EVIDENCE_SCHEMA_VERSION,
        "drawing_id": values["drawing_id"],
        "drawing_number": values["drawing_number"],
        "source_ended_at": _timestamp(values["source_ended_at"]),
        "earliest_kickoff": _timestamp(values["earliest_kickoff"]),
        "operational_cutoff": _timestamp(values["operational_cutoff"]),
        "source_report_path": str(values["source_report_path"]),
        "source_report_sha256": values["source_report_sha256"],
        "source_report_semantic_hash": values["source_report_semantic_hash"],
        "provider_names": list(values["provider_names"]),
        "event_orders": list(values["event_orders"]),
        "status": values["status"],
    }


def _evidence_from_payload(payload: Mapping[str, Any]) -> ConservativeCutoffEvidence:
    expected = {
        "schema_version",
        "drawing_id",
        "drawing_number",
        "source_ended_at",
        "earliest_kickoff",
        "operational_cutoff",
        "source_report_path",
        "source_report_sha256",
        "source_report_semantic_hash",
        "provider_names",
        "event_orders",
        "status",
        "record_sha256",
    }
    if set(payload) != expected:
        raise ValueError("cutoff evidence fields are invalid")
    if payload["schema_version"] != CUTOFF_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported cutoff evidence schema")
    unsigned = dict(payload)
    record_hash = unsigned.pop("record_sha256")
    _require_sha256(record_hash, "record_sha256")
    if _sha256_payload(unsigned) != record_hash:
        raise ValueError("cutoff evidence record hash mismatch")
    drawing_id = payload["drawing_id"]
    drawing_number = payload["drawing_number"]
    if type(drawing_id) is not int or drawing_id <= 0:
        raise ValueError("cutoff evidence drawing_id must be positive")
    if type(drawing_number) is not int or drawing_number <= 0:
        raise ValueError("cutoff evidence drawing_number must be positive")
    providers = payload["provider_names"]
    orders = payload["event_orders"]
    if not isinstance(providers, list) or not providers:
        raise ValueError("cutoff evidence provider_names must be non-empty")
    if not isinstance(orders, list) or not orders:
        raise ValueError("cutoff evidence event_orders must be non-empty")
    parsed_orders = tuple(orders)
    if any(type(value) is not int or not 0 <= value < 15 for value in parsed_orders):
        raise ValueError("cutoff evidence event_orders are invalid")
    source_ended_at = _parse_utc(payload["source_ended_at"], "source_ended_at")
    earliest = _parse_utc(payload["earliest_kickoff"], "earliest_kickoff")
    cutoff = _parse_utc(payload["operational_cutoff"], "operational_cutoff")
    if cutoff != min(source_ended_at, earliest):
        raise ValueError("cutoff evidence does not use conservative minimum")
    status = payload["status"]
    if status != ("tightened" if cutoff < source_ended_at else "unchanged"):
        raise ValueError("cutoff evidence status is inconsistent")
    source_path = Path(
        _required_text(payload["source_report_path"], "source_report_path")
    )
    _require_sha256(payload["source_report_sha256"], "source_report_sha256")
    _require_sha256(
        payload["source_report_semantic_hash"], "source_report_semantic_hash"
    )
    return ConservativeCutoffEvidence(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        source_ended_at=source_ended_at,
        earliest_kickoff=earliest,
        operational_cutoff=cutoff,
        source_report_path=source_path,
        source_report_sha256=str(payload["source_report_sha256"]),
        source_report_semantic_hash=str(payload["source_report_semantic_hash"]),
        provider_names=tuple(
            _required_text(value, "provider_name") for value in providers
        ),
        event_orders=parsed_orders,
        status=str(status),
        record_sha256=str(record_hash),
    )


def _validate_candidate_report_hash(report: Mapping[str, Any]) -> None:
    semantic_hash = report.get("report_sha256")
    _require_sha256(semantic_hash, "source report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256")
    if _sha256_payload(unsigned) != semantic_hash:
        raise ValueError("cutoff source report semantic hash mismatch")


def _load_mapping(raw: bytes, name: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    return payload


def _parse_utc(value: datetime | str | object, name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{name} must be an ISO timestamp") from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _parse_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _sha256_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a SHA-256 hex digest") from error


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()
