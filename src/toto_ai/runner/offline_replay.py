"""Strict, network-free inputs for deterministic drawing replays."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.external_odds.domain import ProviderEvent, QuotaState, TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.preparation import load_local_schedule
from toto_ai.external_odds.targets import parse_target_drawing

OFFLINE_REPLAY_CACHE_SCHEMA_VERSION = 1
_TARGET_FIELDS = {
    "schema_version",
    "cache_kind",
    "provider",
    "drawing_id",
    "drawing_number",
    "fetched_at",
    "payload_sha256",
    "payload",
}
_SCHEDULE_FIELDS = {
    "schema_version",
    "cache_kind",
    "provider",
    "drawing_id",
    "drawing_number",
    "deadline",
    "target_event_ids",
    "target_fingerprint",
    "fetched_at",
    "payload_sha256",
    "events",
}
_SCHEDULE_EVENT_FIELDS = {
    "id",
    "sport",
    "date",
    "league",
    "country",
    "home",
    "away",
    "home_id",
    "away_id",
    "payload_hash",
}


@dataclass(frozen=True)
class OfflineReplayInputs:
    target: TargetDrawing
    target_payload: dict[str, Any]
    schedule_events: tuple[ProviderEvent, ...]
    replay_as_of: datetime
    target_cache_path: Path
    target_cache_sha256: str
    target_payload_sha256: str
    schedule_cache_path: Path
    schedule_cache_sha256: str
    schedule_payload_sha256: str
    provider: str


@dataclass(frozen=True)
class OfflineReplayPaths:
    root: Path
    db: Path
    reports: Path
    provider_cache: Path


def resolve_offline_replay_paths(
    *,
    replay_root: str | Path,
    db: str | Path | None,
    report_dir: str | Path | None,
    cache_root: str | Path | None,
    project_root: str | Path,
) -> OfflineReplayPaths:
    """Resolve a replay-only output boundary without creating anything."""

    project = Path(project_root).resolve(strict=True)
    root = _isolated_path(replay_root, "replay root")
    forbidden = (
        project,
        project / "data",
        project / "reports",
        project / ".git",
    )
    if root == project:
        raise ValueError("replay root must not be the repository root")
    for live_root in forbidden[1:]:
        live = live_root.resolve(strict=False)
        if _contains(root, live) or _contains(live, root):
            raise ValueError(
                "replay root overlaps project production data, reports, cache, "
                "or marker state"
            )

    resolved_db = _replay_output_path(db, root / "replay.sqlite", root, "db")
    resolved_reports = _replay_output_path(
        report_dir, root / "reports", root, "report directory"
    )
    resolved_cache = _replay_output_path(
        cache_root, root / "provider-cache", root, "provider cache"
    )
    if any(
        _contains(left, right) or _contains(right, left)
        for left, right in (
            (resolved_db, resolved_reports),
            (resolved_db, resolved_cache),
        )
    ):
        raise ValueError("replay database must not overlap replay directories")
    if _contains(resolved_reports, resolved_cache) or _contains(
        resolved_cache, resolved_reports
    ):
        raise ValueError(
            "replay report and provider-cache directories must not overlap"
        )
    return OfflineReplayPaths(
        root=root,
        db=resolved_db,
        reports=resolved_reports,
        provider_cache=resolved_cache,
    )


class OfflineScheduleProvider:
    """In-memory provider implementing only cached schedule/market reads."""

    def __init__(self, events: tuple[ProviderEvent, ...], provider: str) -> None:
        self.provider_name = provider
        self._events = events
        self.requests_made = 0
        self.cache_hits = 0
        self.quota_state = QuotaState(0, 0, 0, 0)

    def fetch_schedule(self, sport: str, dates: tuple[object, ...]):
        self.requests_made += 1
        requested = set(dates)
        return tuple(
            event
            for event in self._events
            if event.sport == sport and event.starts_at.date() in requested
        )

    def fetch_event_markets(self, sport: str, provider_event_id: str):
        self.requests_made += 1
        for event in self._events:
            if event.sport == sport and event.provider_event_id == provider_event_id:
                return event.markets
        return ()


def load_offline_replay_inputs(
    *,
    drawing_id: int,
    target_cache: str | Path,
    schedule_cache: str | Path,
    replay_as_of: str,
    provider: str,
) -> OfflineReplayInputs:
    if (
        not isinstance(drawing_id, int)
        or isinstance(drawing_id, bool)
        or drawing_id <= 0
    ):
        raise ValueError("offline replay drawing_id must be a positive integer")
    if provider != "api-sports":
        raise ValueError("offline replay provider must be api-sports")
    observed_at = parse_replay_as_of(replay_as_of)
    target_path, target_bytes, target_envelope = _read_cache(
        target_cache, "target cache"
    )
    schedule_path, schedule_bytes, schedule_envelope = _read_cache(
        schedule_cache, "schedule cache"
    )
    _require_exact_fields(target_envelope, _TARGET_FIELDS, "target cache")
    _require_exact_fields(schedule_envelope, _SCHEDULE_FIELDS, "schedule cache")
    _require_cache_header(
        target_envelope,
        kind="totobrief-target",
        provider="totobrief",
        name="target cache",
    )
    _require_cache_header(
        schedule_envelope,
        kind="api-sports-schedule",
        provider=provider,
        name="schedule cache",
    )

    target_payload = target_envelope["payload"]
    if not isinstance(target_payload, dict):
        raise ValueError("target cache payload must be an object")
    target_payload_sha256 = _canonical_sha256(target_payload)
    _require_digest(
        target_envelope["payload_sha256"],
        target_payload_sha256,
        "target cache payload",
    )
    target = parse_target_drawing(
        target_payload,
        fetched_at=_strict_aware_datetime(
            target_envelope["fetched_at"], "target fetched_at"
        ),
    )
    if target.drawing_id != drawing_id:
        raise ValueError("target cache drawing id does not match --drawing-id")
    if (
        target_envelope["drawing_id"] != target.drawing_id
        or target_envelope["drawing_number"] != target.drawing_number
    ):
        raise ValueError("target cache envelope identity does not match payload")
    if observed_at < target.fetched_at:
        raise ValueError("replay-as-of predates the target cache observation")

    events_payload = schedule_envelope["events"]
    if not isinstance(events_payload, list) or not events_payload:
        raise ValueError("schedule cache events must be a non-empty list")
    for index, item in enumerate(events_payload):
        if not isinstance(item, dict):
            raise ValueError(f"schedule cache event {index} must be an object")
        unknown = set(item) - _SCHEDULE_EVENT_FIELDS
        required = {"id", "date", "league", "home", "away"}
        missing = required - set(item)
        if missing or unknown:
            raise ValueError(
                f"schedule cache event {index} schema mismatch: "
                f"missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
    schedule_payload_sha256 = _canonical_sha256(events_payload)
    _require_digest(
        schedule_envelope["payload_sha256"],
        schedule_payload_sha256,
        "schedule cache payload",
    )
    fingerprint = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )
    target_event_ids = [event.event_id for event in target.events]
    if (
        schedule_envelope["drawing_id"] != target.drawing_id
        or schedule_envelope["drawing_number"] != target.drawing_number
        or schedule_envelope["target_event_ids"] != target_event_ids
        or schedule_envelope["target_fingerprint"] != fingerprint
        or _strict_aware_datetime(schedule_envelope["deadline"], "schedule deadline")
        != target.deadline
    ):
        raise ValueError("schedule cache does not match exact target identity")
    schedule_events = load_local_schedule(schedule_path, provider=provider)
    identities = tuple(event.provider_event_id for event in schedule_events)
    if len(set(identities)) != len(identities):
        raise ValueError("schedule cache provider fixture IDs must be unique")
    if any(
        event.provider != provider
        or event.provider_home_team_id is None
        or event.provider_away_team_id is None
        for event in schedule_events
    ):
        raise ValueError("schedule cache provider/team identity is incomplete")

    return OfflineReplayInputs(
        target=target,
        target_payload=target_payload,
        schedule_events=schedule_events,
        replay_as_of=observed_at,
        target_cache_path=target_path,
        target_cache_sha256=hashlib.sha256(target_bytes).hexdigest(),
        target_payload_sha256=target_payload_sha256,
        schedule_cache_path=schedule_path,
        schedule_cache_sha256=hashlib.sha256(schedule_bytes).hexdigest(),
        schedule_payload_sha256=schedule_payload_sha256,
        provider=provider,
    )


def parse_replay_as_of(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("--replay-as-of must be a timezone-aware ISO8601 value")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "--replay-as-of must be a timezone-aware ISO8601 value"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--replay-as-of must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read_cache(
    path_value: str | Path, name: str
) -> tuple[Path, bytes, dict[str, Any]]:
    path = Path(path_value)
    if path.is_symlink():
        raise ValueError(f"{name} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError(f"{name} must be a regular file")
        content = resolved.read_bytes()
    except OSError as error:
        raise ValueError(f"{name} could not be read: {error}") from error
    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{name} must contain strict UTF-8 JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return resolved, content, payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _require_exact_fields(value: dict[str, Any], expected: set[str], name: str) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        raise ValueError(
            f"{name} schema mismatch: missing={missing}, unknown={unknown}"
        )


def _require_cache_header(
    value: dict[str, Any], *, kind: str, provider: str, name: str
) -> None:
    if value["schema_version"] != OFFLINE_REPLAY_CACHE_SCHEMA_VERSION:
        raise ValueError(f"{name} schema_version must be 1")
    if value["cache_kind"] != kind or value["provider"] != provider:
        raise ValueError(f"{name} kind/provider is invalid")


def _canonical_sha256(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _require_digest(value: object, actual: str, name: str) -> None:
    if not isinstance(value, str) or value != actual:
        raise ValueError(f"{name} SHA-256 mismatch")


def _strict_aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be timezone-aware ISO8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be timezone-aware ISO8601 text") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _replay_output_path(
    value: str | Path | None,
    default: Path,
    root: Path,
    name: str,
) -> Path:
    path = _isolated_path(default if value is None else value, name)
    if path == root or not _contains(path, root):
        raise ValueError(f"offline replay {name} must resolve under --replay-root")
    return path


def _isolated_path(value: str | Path, name: str) -> Path:
    path = Path(value)
    if not os.fspath(path).strip():
        raise ValueError(f"{name} must be a non-empty path")
    lexical = Path(os.path.abspath(os.fspath(path)))
    for candidate in (lexical, *lexical.parents):
        if candidate.is_symlink():
            raise ValueError(f"{name} must not traverse symlinks")
    resolved = lexical.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir() and name == "replay root":
        raise ValueError("replay root must be a directory")
    return resolved


def _contains(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
