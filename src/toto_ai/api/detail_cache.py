from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.api.safe_paths import (
    fsync_directory,
    prepare_contained_parent,
    resolve_contained_path,
)

DETAIL_CACHE_METADATA_SCHEMA = 1
DEFAULT_DETAIL_CACHE_MAX_AGE_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class DrawingDetailCacheRecord:
    drawing_id: int
    payload: dict[str, Any]
    path: Path
    fetched_at: datetime
    age_seconds: float
    payload_sha256: str
    source: str
    metadata_source: str


def drawing_detail_cache_path(
    drawing_id: int,
    cache_dir: str | Path = "data/raw",
    *,
    allowed_root: str | Path = ".",
) -> Path:
    _require_positive_int("drawing_id", drawing_id)
    return resolve_contained_path(
        Path(cache_dir) / f"drawing_{drawing_id}.json",
        allowed_root=allowed_root,
    )


def write_drawing_detail_cache(
    payload: dict[str, Any],
    *,
    drawing_id: int,
    cache_dir: str | Path = "data/raw",
    fetched_at: datetime | None = None,
    source: str = "totobrief-network",
    allowed_root: str | Path = ".",
) -> DrawingDetailCacheRecord:
    fetched = _require_aware_datetime(fetched_at or datetime.now(timezone.utc))
    validated = validate_drawing_detail_payload(payload, expected_drawing_id=drawing_id)
    path = prepare_contained_parent(
        drawing_detail_cache_path(
            drawing_id,
            cache_dir,
            allowed_root=allowed_root,
        ),
        allowed_root=allowed_root,
    )
    payload_bytes = _canonical_pretty_json(validated)
    payload_hash = hashlib.sha256(_canonical_json(validated)).hexdigest()
    metadata = {
        "schema_version": DETAIL_CACHE_METADATA_SCHEMA,
        "drawing_id": drawing_id,
        "fetched_at": fetched.isoformat(),
        "payload_sha256": payload_hash,
        "source": _require_nonempty("source", source),
    }
    metadata_path = prepare_contained_parent(
        _metadata_path(path),
        allowed_root=allowed_root,
    )
    _publish_cache_pair(
        path,
        payload_bytes,
        metadata_path,
        _canonical_pretty_json(metadata),
    )
    return DrawingDetailCacheRecord(
        drawing_id=drawing_id,
        payload=validated,
        path=path,
        fetched_at=fetched,
        age_seconds=0.0,
        payload_sha256=payload_hash,
        source=source,
        metadata_source="sidecar",
    )


def load_drawing_detail_cache(
    drawing_id: int,
    *,
    cache_dir: str | Path = "data/raw",
    max_age_seconds: float | None = DEFAULT_DETAIL_CACHE_MAX_AGE_SECONDS,
    now: datetime | None = None,
    allowed_root: str | Path = ".",
) -> DrawingDetailCacheRecord:
    current = _require_aware_datetime(now or datetime.now(timezone.utc))
    if max_age_seconds is not None and (
        not math.isfinite(max_age_seconds) or max_age_seconds < 0
    ):
        raise ValueError("max_age_seconds must be finite and non-negative")
    path = drawing_detail_cache_path(
        drawing_id,
        cache_dir,
        allowed_root=allowed_root,
    )
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"drawing detail cache is missing: {path}") from None
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"drawing detail cache is malformed: {path}") from error
    payload = validate_drawing_detail_payload(
        raw_payload,
        expected_drawing_id=drawing_id,
    )
    payload_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()

    metadata_path = resolve_contained_path(
        _metadata_path(path),
        allowed_root=allowed_root,
    )
    if not metadata_path.is_file():
        raise ValueError("drawing detail cache metadata sidecar is missing")
    fetched_at, source = _load_metadata(
        metadata_path,
        drawing_id=drawing_id,
        payload_sha256=payload_hash,
    )

    age_seconds = (current - fetched_at).total_seconds()
    if age_seconds < -300:
        raise ValueError("drawing detail cache timestamp is in the future")
    age_seconds = max(0.0, age_seconds)
    if max_age_seconds is not None and age_seconds > max_age_seconds:
        raise ValueError(
            f"drawing detail cache is stale: age={age_seconds:.1f}s, "
            f"limit={max_age_seconds:.1f}s"
        )
    return DrawingDetailCacheRecord(
        drawing_id=drawing_id,
        payload=payload,
        path=path,
        fetched_at=fetched_at,
        age_seconds=age_seconds,
        payload_sha256=payload_hash,
        source=source,
        metadata_source="sidecar",
    )


def validate_drawing_detail_payload(
    payload: Any,
    *,
    expected_drawing_id: int,
) -> dict[str, Any]:
    _require_positive_int("expected_drawing_id", expected_drawing_id)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ValueError("drawing detail payload must contain an object data field")
    data = payload["data"]
    drawing_id = data.get("id")
    if type(drawing_id) is not int or drawing_id != expected_drawing_id:
        raise ValueError(
            "drawing detail payload id does not match the requested drawing"
        )
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise ValueError("drawing detail payload must contain exactly 15 events")
    seen_orders: set[int] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("drawing detail payload event must be an object")
        _require_positive_int("drawing detail event id", event.get("id"))
        order = event.get("order")
        if type(order) is not int or order not in range(15):
            raise ValueError("drawing detail event order must be in range 0 through 14")
        if order in seen_orders:
            raise ValueError("drawing detail payload contains duplicate event orders")
        seen_orders.add(order)
        quotes = event.get("quotes")
        _validate_quotes(quotes, event_order=order)
    if seen_orders != set(range(15)):
        raise ValueError("drawing detail event orders must be exactly 0 through 14")
    return payload


def _load_metadata(
    path: Path,
    *,
    drawing_id: int,
    payload_sha256: str,
) -> tuple[datetime, str]:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"drawing detail cache metadata is malformed: {path}"
        ) from error
    if not isinstance(metadata, dict):
        raise ValueError("drawing detail cache metadata must be an object")
    if metadata.get("schema_version") != DETAIL_CACHE_METADATA_SCHEMA:
        raise ValueError("unsupported drawing detail cache metadata schema")
    if metadata.get("drawing_id") != drawing_id:
        raise ValueError("drawing detail cache metadata drawing id mismatch")
    if metadata.get("payload_sha256") != payload_sha256:
        raise ValueError("drawing detail cache metadata payload hash mismatch")
    fetched_raw = metadata.get("fetched_at")
    if not isinstance(fetched_raw, str):
        raise ValueError("drawing detail cache metadata fetched_at is invalid")
    try:
        fetched = datetime.fromisoformat(fetched_raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "drawing detail cache metadata fetched_at is invalid"
        ) from error
    return _require_aware_datetime(fetched), _require_nonempty(
        "source", metadata.get("source")
    )


def _metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.meta.json")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_pretty_json(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_temporary(path: Path, content: bytes) -> Path:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _publish_cache_pair(
    payload_path: Path,
    payload_content: bytes,
    metadata_path: Path,
    metadata_content: bytes,
) -> None:
    payload_temporary = _write_temporary(payload_path, payload_content)
    metadata_temporary = _write_temporary(metadata_path, metadata_content)
    try:
        # Metadata is the commit marker. A crash after the payload replacement
        # leaves an old/missing sidecar whose hash fails closed; only replacing
        # the fsynced sidecar publishes the new pair operationally.
        os.replace(payload_temporary, payload_path)
        fsync_directory(payload_path.parent)
        os.replace(metadata_temporary, metadata_path)
        fsync_directory(metadata_path.parent)
    finally:
        payload_temporary.unlink(missing_ok=True)
        metadata_temporary.unlink(missing_ok=True)


def _validate_quotes(value: Any, *, event_order: int) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"drawing detail event {event_order} quotes must be an object")
    for prefix in ("pool", "bk"):
        numbers = []
        for suffix in ("win_1", "draw", "win_2"):
            key = f"{prefix}_{suffix}"
            raw = value.get(key)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(
                    f"drawing detail event {event_order} quote {key} "
                    "must be finite and non-negative"
                )
            number = float(raw)
            if not math.isfinite(number) or number < 0:
                raise ValueError(
                    f"drawing detail event {event_order} quote {key} "
                    "must be finite and non-negative"
                )
            numbers.append(number)
        if sum(numbers) <= 0:
            raise ValueError(
                f"drawing detail event {event_order} {prefix} quotes must have "
                "a positive total"
            )


def _require_positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cache timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_nonempty(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()
