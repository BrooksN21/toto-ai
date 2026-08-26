"""Verified operational cutoffs used only to retire already closed drawings."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from toto_ai.runner.conservative_cutoff import (
    conservative_cutoff_evidence_sha256,
    load_conservative_cutoff_evidence,
)
from toto_ai.runner.morning_dispatch import load_morning_dispatch_record


def load_verified_operational_cutoffs(
    state_root: str | Path,
    *,
    project_root: str | Path,
) -> dict[int, datetime]:
    """Return only cutoffs whose record, evidence and source report all verify."""

    root = Path(project_root).resolve(strict=True)
    state = Path(state_root).resolve(strict=False)
    if not state.is_relative_to(root):
        raise ValueError("operational selection state must remain inside project root")
    if not state.exists():
        return {}
    if state.is_symlink() or not state.is_dir():
        raise ValueError("operational selection state must be a regular directory")

    cutoffs: dict[int, datetime] = {}
    for record_path in sorted(state.glob("drawing-*.json")):
        try:
            record = load_morning_dispatch_record(record_path)
            identity = None if record is None else record.get("identity")
            if not isinstance(identity, dict):
                continue
            drawing_id = identity.get("drawing_id")
            drawing_number = identity.get("drawing_number")
            fingerprint = identity.get("drawing_fingerprint")
            evidence_sha256 = identity.get("cutoff_evidence_sha256")
            deadline = _parse_utc(identity.get("deadline"))
            cutoff = _parse_utc(identity.get("operational_cutoff"))
            if (
                type(drawing_id) is not int
                or drawing_id <= 0
                or type(drawing_number) is not int
                or drawing_number <= 0
                or not isinstance(fingerprint, str)
                or len(fingerprint) < 16
                or not isinstance(evidence_sha256, str)
                or cutoff >= deadline
            ):
                continue
            evidence_path = (
                state
                / "preflight"
                / (
                    f"drawing-{drawing_id}-{deadline.strftime('%Y%m%dT%H%M%SZ')}-"
                    f"{fingerprint[:16]}"
                )
                / "source-collector"
                / "conservative-cutoff.json"
            )
            evidence = load_conservative_cutoff_evidence(
                evidence_path,
                project_root=root,
                expected_drawing_id=drawing_id,
                expected_drawing_number=drawing_number,
                expected_source_ended_at=deadline,
            )
            if (
                evidence.operational_cutoff != cutoff
                or conservative_cutoff_evidence_sha256(evidence) != evidence_sha256
            ):
                continue
        except (OSError, TypeError, ValueError):
            # Unverified local state must never retire a drawing early.
            continue
        prior = cutoffs.get(drawing_id)
        cutoffs[drawing_id] = cutoff if prior is None else min(prior, cutoff)
    return cutoffs


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("operational selection timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("operational selection timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)
