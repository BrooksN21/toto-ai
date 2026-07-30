"""Lifecycle-aware, RAW-first drawing-detail imports.

The filesystem archive is the commit prerequisite. Analytical SQLite rows may
be rebuilt from it, but an import is never allowed to invent missing source
fields or turn an implicit cancellation into a toto VOID.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.api.safe_paths import fsync_directory
from toto_ai.db.models import (
    Drawing,
    DrawingRawSnapshot,
    DrawingResultSnapshot,
    Event,
    Quote,
)

EVENT_ORDERS = frozenset(range(15))
DECIDED_RESULTS = frozenset(("1", "X", "2"))
VOID_RESULT = "*"
RAW_ARCHIVE_SCHEMA_VERSION = 1
RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 3


@dataclass(frozen=True)
class RawArchiveRecord:
    snapshot_sha256: str
    payload_sha256: str
    metadata_sha256: str
    drawing_id: int
    drawing_number: int | None
    captured_at: str
    source: str
    source_endpoint: str | None
    lifecycle_status: str
    payload_path: Path
    metadata_path: Path
    created: bool


@dataclass(frozen=True)
class FullDetailImportResult:
    drawing_id: int
    drawing_number: int | None
    raw_snapshot_sha256: str
    terminal_result_count: int
    events_created: int
    events_updated: int
    quotes_created: int
    quotes_updated: int
    logical_changes: int
    result_snapshot_created: bool
    classification: str
    dry_run: bool


class RawArchive:
    """Content-addressed append-only detail archive."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def archive(
        self,
        payload: Mapping[str, Any],
        *,
        captured_at: datetime,
        source: str,
        lifecycle_status: str,
        source_endpoint: str | None = None,
    ) -> RawArchiveRecord:
        validated = validate_full_detail_payload(payload)
        captured = _aware(captured_at).isoformat()
        source_value = _nonempty(source, "source")
        status = _nonempty(lifecycle_status, "lifecycle_status")
        payload_bytes = _canonical_bytes(validated)
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        data = validated["data"]
        metadata_core = {
            "schema_version": RAW_ARCHIVE_SCHEMA_VERSION,
            "drawing_id": data["id"],
            "drawing_number": data.get("number"),
            "captured_at": captured,
            "source": source_value,
            "source_endpoint": source_endpoint,
            "lifecycle_status": status,
            "payload_sha256": payload_hash,
        }
        metadata_hash = hashlib.sha256(_canonical_bytes(metadata_core)).hexdigest()
        snapshot_hash = hashlib.sha256(
            _canonical_bytes(
                {
                    "payload_sha256": payload_hash,
                    "metadata_sha256": metadata_hash,
                }
            )
        ).hexdigest()
        metadata = {
            **metadata_core,
            "metadata_sha256": metadata_hash,
            "snapshot_sha256": snapshot_hash,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        directory = self.root / f"drawing_{data['id']}"
        if directory.is_symlink():
            raise ValueError("RAW archive drawing directory cannot be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        try:
            directory.resolve().relative_to(self.root)
        except ValueError as error:
            raise ValueError("RAW archive drawing directory escapes root") from error
        payload_path = directory / f"{snapshot_hash}.json"
        metadata_path = directory / f"{snapshot_hash}.meta.json"
        created = not payload_path.exists() or not metadata_path.exists()
        if not payload_path.exists():
            _write_once(payload_path, payload_bytes)
        elif payload_path.read_bytes() != payload_bytes:
            raise ValueError("content-addressed RAW payload collision")
        if not metadata_path.exists():
            _write_once(metadata_path, _pretty_bytes(metadata))
        elif metadata_path.read_bytes() != _pretty_bytes(metadata):
            raise ValueError("content-addressed RAW metadata collision")
        fsync_directory(directory)
        record = RawArchiveRecord(
            snapshot_sha256=snapshot_hash,
            payload_sha256=payload_hash,
            metadata_sha256=metadata_hash,
            drawing_id=data["id"],
            drawing_number=data.get("number"),
            captured_at=captured,
            source=source_value,
            source_endpoint=source_endpoint,
            lifecycle_status=status,
            payload_path=payload_path,
            metadata_path=metadata_path,
            created=created,
        )
        self.verify(record)
        return record

    def load(self, record: RawArchiveRecord) -> dict[str, Any]:
        self.verify(record)
        try:
            payload = json.loads(record.payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("RAW archive payload is malformed") from error
        return validate_full_detail_payload(
            payload,
            expected_drawing_id=record.drawing_id,
        )

    def verify(self, record: RawArchiveRecord) -> None:
        for path in (record.payload_path, record.metadata_path):
            try:
                path.resolve().relative_to(self.root)
            except ValueError as error:
                raise ValueError("RAW archive path escapes its root") from error
            if not path.is_file() or path.is_symlink():
                raise ValueError("RAW archive file is missing")
        payload_bytes = record.payload_path.read_bytes()
        if hashlib.sha256(payload_bytes).hexdigest() != record.payload_sha256:
            raise ValueError("RAW archive payload hash mismatch")
        try:
            metadata = json.loads(record.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("RAW archive metadata is malformed") from error
        unsigned = {
            key: value
            for key, value in metadata.items()
            if key not in ("metadata_sha256", "snapshot_sha256")
        }
        if hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != (
            record.metadata_sha256
        ):
            raise ValueError("RAW archive metadata hash mismatch")
        if metadata.get("snapshot_sha256") != record.snapshot_sha256:
            raise ValueError("RAW archive snapshot hash mismatch")
        computed_snapshot = hashlib.sha256(
            _canonical_bytes(
                {
                    "payload_sha256": record.payload_sha256,
                    "metadata_sha256": record.metadata_sha256,
                }
            )
        ).hexdigest()
        if computed_snapshot != record.snapshot_sha256:
            raise ValueError("RAW archive snapshot hash mismatch")


def validate_full_detail_payload(
    payload: Any,
    *,
    expected_drawing_id: int | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ValueError("drawing detail payload must contain an object data field")
    data = payload["data"]
    drawing_id = data.get("id")
    if type(drawing_id) is not int or drawing_id <= 0:
        raise ValueError("drawing detail id must be a positive integer")
    if expected_drawing_id is not None and drawing_id != expected_drawing_id:
        raise ValueError("drawing detail id does not match requested drawing")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise ValueError("drawing detail payload must contain exactly 15 events")
    orders: set[int] = set()
    ids: set[int] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("drawing detail event must be an object")
        event_id = event.get("id")
        order = event.get("order")
        if type(event_id) is not int or event_id <= 0 or event_id in ids:
            raise ValueError("drawing detail event ids must be positive and unique")
        if type(order) is not int or order not in EVENT_ORDERS or order in orders:
            raise ValueError("drawing detail event orders must be exactly 0 through 14")
        ids.add(event_id)
        orders.add(order)
        quotes = event.get("quotes")
        if quotes is not None and not isinstance(quotes, dict):
            raise ValueError("drawing detail quotes must be an object or null")
    if orders != EVENT_ORDERS:
        raise ValueError("drawing detail event orders must be exactly 0 through 14")
    return dict(payload)


def import_archived_detail(
    session_factory: sessionmaker[Session],
    archive: RawArchiveRecord,
    *,
    dry_run: bool = False,
    before_commit: Callable[[Session], None] | None = None,
) -> FullDetailImportResult:
    repository = RawArchive(archive.payload_path.parent.parent)
    payload = repository.load(archive)
    return _import_detail_payload(
        session_factory,
        payload,
        archive=archive,
        dry_run=dry_run,
        before_commit=before_commit,
    )


def preview_detail_payload(
    session_factory: sessionmaker[Session],
    payload: Mapping[str, Any],
    *,
    archive_root: str | Path,
    captured_at: datetime,
    source: str,
    lifecycle_status: str,
    source_endpoint: str | None = None,
) -> FullDetailImportResult:
    """Calculate an import delta without writing SQLite or RAW evidence."""
    validated = validate_full_detail_payload(payload)
    captured = _aware(captured_at).isoformat()
    source_value = _nonempty(source, "source")
    status = _nonempty(lifecycle_status, "lifecycle_status")
    payload_hash = hashlib.sha256(_canonical_bytes(validated)).hexdigest()
    data = validated["data"]
    metadata_core = {
        "schema_version": RAW_ARCHIVE_SCHEMA_VERSION,
        "drawing_id": data["id"],
        "drawing_number": data.get("number"),
        "captured_at": captured,
        "source": source_value,
        "source_endpoint": source_endpoint,
        "lifecycle_status": status,
        "payload_sha256": payload_hash,
    }
    metadata_hash = hashlib.sha256(_canonical_bytes(metadata_core)).hexdigest()
    snapshot_hash = hashlib.sha256(
        _canonical_bytes(
            {
                "payload_sha256": payload_hash,
                "metadata_sha256": metadata_hash,
            }
        )
    ).hexdigest()
    root = Path(archive_root).resolve()
    directory = root / f"drawing_{data['id']}"
    archive = RawArchiveRecord(
        snapshot_sha256=snapshot_hash,
        payload_sha256=payload_hash,
        metadata_sha256=metadata_hash,
        drawing_id=data["id"],
        drawing_number=data.get("number"),
        captured_at=captured,
        source=source_value,
        source_endpoint=source_endpoint,
        lifecycle_status=status,
        payload_path=directory / f"{snapshot_hash}.json",
        metadata_path=directory / f"{snapshot_hash}.meta.json",
        created=False,
    )
    return _import_detail_payload(
        session_factory,
        validated,
        archive=archive,
        dry_run=True,
        before_commit=None,
    )


def _import_detail_payload(
    session_factory: sessionmaker[Session],
    payload: Mapping[str, Any],
    *,
    archive: RawArchiveRecord,
    dry_run: bool,
    before_commit: Callable[[Session], None] | None,
) -> FullDetailImportResult:
    data = payload["data"]
    events_created = events_updated = quotes_created = quotes_updated = 0
    changes = 0
    terminal_events: list[dict[str, Any]] = []

    session = session_factory()
    original_autoflush = session.autoflush
    if dry_run:
        session.autoflush = False
    transaction = session.begin()
    try:
        if dry_run:
            raw_snapshot_exists = (
                session.get(
                    DrawingRawSnapshot,
                    archive.snapshot_sha256,
                )
                is not None
            )
            changes += int(not raw_snapshot_exists)
        else:
            inserted = session.execute(
                sqlite_insert(DrawingRawSnapshot)
                .values(
                    snapshot_sha256=archive.snapshot_sha256,
                    payload_sha256=archive.payload_sha256,
                    metadata_sha256=archive.metadata_sha256,
                    drawing_id=archive.drawing_id,
                    drawing_number=archive.drawing_number,
                    captured_at=archive.captured_at,
                    source=archive.source,
                    source_endpoint=archive.source_endpoint,
                    lifecycle_status=archive.lifecycle_status,
                    payload_path=str(archive.payload_path),
                    metadata_path=str(archive.metadata_path),
                    imported_at=datetime.now(timezone.utc).isoformat(),
                    classification="pending",
                )
                .on_conflict_do_nothing()
            )
            changes += max(0, inserted.rowcount)
        drawing = session.get(Drawing, archive.drawing_id)
        if drawing is None:
            drawing = Drawing(id=archive.drawing_id)
            if not dry_run:
                session.add(drawing)
            changes += 1
        if (
            drawing.number is not None
            and data.get("number") is not None
            and drawing.number != data.get("number")
        ):
            raise ValueError("drawing number conflicts with stored identity")
        if (
            drawing.ended_at
            and data.get("ended_at")
            and _canonical_timestamp(drawing.ended_at)
            != _canonical_timestamp(data.get("ended_at"))
        ):
            raise ValueError("drawing ended_at conflicts with stored identity")
        for field in ("number", "name", "started_at", "ended_at"):
            changes += _merge_attr(drawing, field, data.get(field))
        for field in ("pool_sum", "jackpot"):
            value = _finite_or_none(data.get(field))
            if value is not None and (
                value > 0 or getattr(drawing, field, None) in (None, 0)
            ):
                changes += _merge_attr(drawing, field, value)
        changes += _merge_status(drawing, data.get("status"))

        for item in sorted(data["events"], key=lambda value: value["order"]):
            order = item["order"]
            event = session.scalar(
                select(Event).where(
                    Event.drawing_id == archive.drawing_id,
                    Event.event_order == order,
                )
            )
            if event is None:
                event = Event(drawing_id=archive.drawing_id, event_order=order)
                if not dry_run:
                    session.add(event)
                events_created += 1
            event_changes = 0
            for field in ("name", "championship", "sport"):
                event_changes += _merge_attr(
                    event,
                    field,
                    item.get(field),
                    nonblank=True,
                )
            normalized_result = _source_result(item)
            if normalized_result is not None:
                result, result_status, score, void_source = normalized_result
                if (
                    event.result in DECIDED_RESULTS | {VOID_RESULT}
                    and event.result != result
                ):
                    raise ValueError(
                        f"event {order} terminal result conflicts with stored data"
                    )
                event_changes += _merge_attr(event, "result", result)
                event_changes += _merge_attr(
                    event,
                    "result_status",
                    result_status,
                )
                event_changes += _merge_attr(
                    event,
                    "score",
                    score,
                    allow_blank=result == VOID_RESULT,
                )
                normalized_event = {
                    "order": order,
                    "event_id": item["id"],
                    "result": result,
                    "result_status": result_status,
                    "score": score,
                }
                if void_source is not None:
                    normalized_event["void_source"] = void_source
                terminal_events.append(normalized_event)
            if event_changes and events_created == 0:
                events_updated += 1
            elif event_changes and event.id is not None:
                events_updated += 1
            changes += event_changes

            quotes = item.get("quotes")
            if not isinstance(quotes, dict):
                continue
            quote = session.scalar(
                select(Quote).where(
                    Quote.drawing_id == archive.drawing_id,
                    Quote.event_order == order,
                )
            )
            if quote is None:
                quote = Quote(drawing_id=archive.drawing_id, event_order=order)
                if not dry_run:
                    session.add(quote)
                quotes_created += 1
            quote_changes = _merge_quotes(quote, quotes)
            if quote_changes and quote.id is not None:
                quotes_updated += 1
            changes += quote_changes

        complete = (
            data.get("status") == "finished"
            and len(terminal_events) == 15
            and {event["order"] for event in terminal_events} == EVENT_ORDERS
        )
        snapshot_created = False
        if complete:
            terminal_events.sort(key=lambda value: value["order"])
            if dry_run:
                snapshot_created = _would_insert_result_snapshot(
                    session,
                    payload=payload,
                    archive=archive,
                    events=terminal_events,
                )
            else:
                snapshot_created = _insert_result_snapshot(
                    session,
                    payload=payload,
                    archive=archive,
                    events=terminal_events,
                )
            changes += int(snapshot_created)
        if archive.source.startswith(("canonical", "cache:")) and changes:
            classification = "importer_loss_recoverable_local"
        else:
            classification = "source_complete" if complete else "source_incomplete"
        if not dry_run:
            raw_row = session.get(
                DrawingRawSnapshot,
                archive.snapshot_sha256,
            )
            if raw_row is not None:
                raw_row.classification = classification
        if before_commit is not None and not dry_run:
            before_commit(session)
        if dry_run:
            transaction.rollback()
        else:
            transaction.commit()
    except BaseException:
        transaction.rollback()
        raise
    finally:
        session.autoflush = original_autoflush
        session.close()
    return FullDetailImportResult(
        drawing_id=archive.drawing_id,
        drawing_number=archive.drawing_number,
        raw_snapshot_sha256=archive.snapshot_sha256,
        terminal_result_count=len(terminal_events),
        events_created=events_created,
        events_updated=events_updated,
        quotes_created=quotes_created,
        quotes_updated=quotes_updated,
        logical_changes=changes,
        result_snapshot_created=snapshot_created,
        classification=classification,
        dry_run=dry_run,
    )


def finished_drawing_is_current(session: Session, drawing_id: int) -> bool:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None or drawing.status != "finished":
        return False
    events = session.scalars(
        select(Event).where(Event.drawing_id == drawing_id).order_by(Event.event_order)
    ).all()
    if (
        len(events) != 15
        or {event.event_order for event in events} != EVENT_ORDERS
        or any(
            event.result not in DECIDED_RESULTS | {VOID_RESULT}
            or (
                event.result == VOID_RESULT
                and event.result_status not in {"void", "cancelled", "canceled"}
            )
            for event in events
        )
    ):
        return False
    snapshot = session.scalar(
        select(DrawingResultSnapshot)
        .where(
            DrawingResultSnapshot.drawing_id == drawing_id,
            DrawingResultSnapshot.complete.is_(True),
            DrawingResultSnapshot.event_count == 15,
            DrawingResultSnapshot.raw_snapshot_sha256.is_not(None),
        )
        .order_by(DrawingResultSnapshot.id.desc())
    )
    return snapshot is not None


def _insert_result_snapshot(
    session: Session,
    *,
    payload: Mapping[str, Any],
    archive: RawArchiveRecord,
    events: list[dict[str, Any]],
) -> bool:
    values = _result_snapshot_values(
        payload=payload,
        archive=archive,
        events=events,
    )
    inserted = session.execute(
        sqlite_insert(DrawingResultSnapshot).values(**values).on_conflict_do_nothing()
    )
    return inserted.rowcount == 1


def _would_insert_result_snapshot(
    session: Session,
    *,
    payload: Mapping[str, Any],
    archive: RawArchiveRecord,
    events: list[dict[str, Any]],
) -> bool:
    values = _result_snapshot_values(
        payload=payload,
        archive=archive,
        events=events,
    )
    return (
        session.scalar(
            select(DrawingResultSnapshot.id).where(
                DrawingResultSnapshot.snapshot_sha256 == values["snapshot_sha256"]
            )
        )
        is None
    )


def _result_snapshot_values(
    *,
    payload: Mapping[str, Any],
    archive: RawArchiveRecord,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    data = payload["data"]
    number = data.get("number")
    ended_at = _canonical_timestamp(data.get("ended_at"))
    payments = data.get("payments")
    pool_sum = _finite_or_none(data.get("pool_sum"))
    jackpot = _finite_or_none(data.get("jackpot"))
    content = {
        "drawing_id": archive.drawing_id,
        "drawing_number": number,
        "status": "finished",
        "events": events,
        "payments": payments,
        "pool_sum": pool_sum,
        "jackpot": jackpot,
        "ended_at": ended_at,
    }
    snapshot_hash = hashlib.sha256(_canonical_bytes(content)).hexdigest()
    result_hash = hashlib.sha256(_canonical_bytes(events)).hexdigest()
    return {
        "drawing_id": archive.drawing_id,
        "drawing_number": number,
        "hash_schema_version": RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
        "ended_at": ended_at,
        "retrieved_at": archive.captured_at,
        "source_endpoint": archive.source_endpoint or f"archive:{archive.source}",
        "payload_sha256": archive.payload_sha256,
        "raw_snapshot_sha256": archive.snapshot_sha256,
        "result_sha256": result_hash,
        "snapshot_sha256": snapshot_hash,
        "complete": True,
        "event_count": 15,
        "actual": "".join(event["result"] for event in events),
        "events_json": _canonical_text(events),
        "payments_json": (None if payments is None else _canonical_text(payments)),
        "pool_sum": pool_sum,
        "jackpot": jackpot,
        "payload_json": _canonical_text(payload),
    }


def _source_result(
    item: Mapping[str, Any],
) -> tuple[str, str, str, str | None] | None:
    result = item.get("result")
    status = item.get("result_status")
    score = item.get("score")
    if result in DECIDED_RESULTS:
        if not isinstance(score, str) or not score.strip():
            return None
        return result, "resolved", score.strip(), None
    if result == VOID_RESULT and status in {"void", "cancelled", "canceled"}:
        source = item.get("void_source")
        if _valid_http_url(source):
            return VOID_RESULT, "void", "", str(source).strip()
    return None


def _merge_quotes(quote: Quote, values: Mapping[str, Any]) -> int:
    changed = 0
    for prefix in ("pool", "bk", "pin", "norm"):
        fields = (f"{prefix}_win_1", f"{prefix}_draw", f"{prefix}_win_2")
        triple = tuple(_finite_or_none(values.get(field)) for field in fields)
        if not all(value is not None for value in triple):
            continue
        if sum(value for value in triple if value is not None) <= 0:
            continue
        for field, value in zip(fields, triple, strict=True):
            changed += _merge_attr(quote, field, value)
    return changed


def _merge_attr(
    target: Any,
    field: str,
    value: Any,
    *,
    nonblank: bool = False,
    allow_blank: bool = False,
) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        if not value.strip() and not allow_blank:
            return 0
        if nonblank:
            value = value.strip()
    if getattr(target, field, None) == value:
        return 0
    setattr(target, field, value)
    return 1


def _merge_status(drawing: Drawing, status: Any) -> int:
    if not isinstance(status, str) or not status.strip():
        return 0
    old = drawing.status
    ranks = {None: 0, "expected": 1, "active": 2, "finished": 3}
    if ranks.get(status, 0) < ranks.get(old, 0):
        return 0
    return _merge_attr(drawing, "status", status.strip())


def _write_once(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            if path.read_bytes() != content:
                raise ValueError("content-addressed RAW archive collision") from error
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical_bytes(value: Any) -> bytes:
    return _canonical_text(value).encode("utf-8")


def _canonical_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _finite_or_none(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        return None
    return float(value)


def _canonical_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("finished detail ended_at must be present")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("finished detail ended_at is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("finished detail ended_at must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _valid_http_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
    )
