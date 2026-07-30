"""Bounded, resumable reconciliation for incomplete finished drawings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.collector.lifecycle import (
    RawArchive,
    finished_drawing_is_current,
    import_archived_detail,
    validate_full_detail_payload,
)
from toto_ai.db.models import Drawing


@dataclass(frozen=True)
class ReconciliationConfig:
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    rate_limit_seconds: float = 0.0
    batch_size: int | None = None
    dry_run: bool = False

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if self.batch_size is not None and (
            type(self.batch_size) is not int or self.batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer or None")
        for name in (
            "initial_backoff_seconds",
            "max_backoff_seconds",
            "backoff_multiplier",
            "rate_limit_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError(
                "max_backoff_seconds must be at least initial_backoff_seconds"
            )


@dataclass(frozen=True)
class ReconciliationTarget:
    drawing_id: int
    number: int
    ended_at: str


@dataclass(frozen=True)
class ReconciliationItem:
    drawing_id: int
    drawing_number: int
    status: Literal[
        "would_reconcile",
        "repaired",
        "source_incomplete",
        "exhausted",
    ]
    attempts: int
    terminal_results: int
    reason: str
    raw_snapshot_sha256: str | None


@dataclass(frozen=True)
class ReconciliationReport:
    selected: int
    processed: int
    repaired: int
    source_incomplete: int
    exhausted: int
    dry_run: bool
    items: tuple[ReconciliationItem, ...]


@dataclass(frozen=True)
class OfflineRepairItem:
    drawing_number: int
    drawing_id: int | None
    status: Literal[
        "would_repair",
        "would_no_change",
        "repaired",
        "no_change",
        "source_missing",
        "invalid",
    ]
    logical_changes: int
    classification: str
    reason: str


@dataclass(frozen=True)
class OfflineRepairReport:
    selected: int
    repaired: int
    source_missing: int
    invalid: int
    dry_run: bool
    items: tuple[OfflineRepairItem, ...]


def select_incomplete_finished_drawings(
    session_factory: sessionmaker[Session],
    *,
    from_drawing: int | None = None,
    to_drawing: int | None = None,
    last: int | None = None,
    batch_size: int | None = None,
) -> tuple[ReconciliationTarget, ...]:
    _validate_selectors(from_drawing, to_drawing, last)
    with session_factory() as session:
        drawings = session.scalars(
            select(Drawing)
            .where(
                Drawing.name == "baltbet-main",
                Drawing.status == "finished",
            )
            .order_by(Drawing.number, Drawing.id)
        ).all()
        selected = [
            drawing
            for drawing in drawings
            if drawing.number is not None
            and (from_drawing is None or drawing.number >= from_drawing)
            and (to_drawing is None or drawing.number <= to_drawing)
            and not finished_drawing_is_current(session, drawing.id)
        ]
    if last is not None:
        selected = selected[-last:]
    if batch_size is not None:
        selected = selected[:batch_size]
    return tuple(
        ReconciliationTarget(
            drawing_id=drawing.id,
            number=drawing.number,
            ended_at=drawing.ended_at or "",
        )
        for drawing in selected
    )


def reconcile_finished_drawings(
    session_factory: sessionmaker[Session],
    client: Any,
    *,
    archive_root: str | Path,
    state_path: str | Path,
    config: ReconciliationConfig | None = None,
    from_drawing: int | None = None,
    to_drawing: int | None = None,
    last: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
) -> ReconciliationReport:
    config = config or ReconciliationConfig()
    targets = select_incomplete_finished_drawings(
        session_factory,
        from_drawing=from_drawing,
        to_drawing=to_drawing,
        last=last,
        batch_size=config.batch_size,
    )
    if config.dry_run:
        items = tuple(
            ReconciliationItem(
                drawing_id=target.drawing_id,
                drawing_number=target.number,
                status="would_reconcile",
                attempts=0,
                terminal_results=0,
                reason="dry_run_no_network",
                raw_snapshot_sha256=None,
            )
            for target in targets
        )
        return ReconciliationReport(
            selected=len(targets),
            processed=0,
            repaired=0,
            source_incomplete=0,
            exhausted=0,
            dry_run=True,
            items=items,
        )

    state = _load_state(state_path)
    archive = RawArchive(archive_root)
    items: list[ReconciliationItem] = []
    for target_index, target in enumerate(targets):
        delay = float(config.initial_backoff_seconds)
        last_item: ReconciliationItem | None = None
        for attempt in range(1, config.max_attempts + 1):
            try:
                payload = client.drawing_info(target.drawing_id)
                validate_full_detail_payload(
                    payload,
                    expected_drawing_id=target.drawing_id,
                )
                data = payload["data"]
                if data.get("number") != target.number:
                    raise ValueError("drawing number mismatch")
                if data.get("status") != "finished":
                    raise ValueError("source drawing is not finished")
                record = archive.archive(
                    payload,
                    captured_at=_aware(now()),
                    source="totobrief-network",
                    source_endpoint=f"/drawing-info/{target.drawing_id}",
                    lifecycle_status="finished",
                )
                imported = import_archived_detail(session_factory, record)
            except (
                OSError,
                TimeoutError,
                ConnectionError,
                requests.RequestException,
                TotoBriefRequestError,
            ):
                last_item = ReconciliationItem(
                    drawing_id=target.drawing_id,
                    drawing_number=target.number,
                    status="exhausted",
                    attempts=attempt,
                    terminal_results=0,
                    reason="transport_error",
                    raw_snapshot_sha256=None,
                )
            except (KeyError, TypeError, ValueError) as error:
                last_item = ReconciliationItem(
                    drawing_id=target.drawing_id,
                    drawing_number=target.number,
                    status="exhausted",
                    attempts=attempt,
                    terminal_results=0,
                    reason=_safe_reason(error),
                    raw_snapshot_sha256=None,
                )
            else:
                if imported.terminal_result_count == 15:
                    last_item = ReconciliationItem(
                        drawing_id=target.drawing_id,
                        drawing_number=target.number,
                        status="repaired",
                        attempts=attempt,
                        terminal_results=15,
                        reason="terminal_15_of_15",
                        raw_snapshot_sha256=record.snapshot_sha256,
                    )
                else:
                    last_item = ReconciliationItem(
                        drawing_id=target.drawing_id,
                        drawing_number=target.number,
                        status="source_incomplete",
                        attempts=attempt,
                        terminal_results=imported.terminal_result_count,
                        reason="source_payload_incomplete",
                        raw_snapshot_sha256=record.snapshot_sha256,
                    )
            state["attempts"].append(
                {
                    **asdict(last_item),
                    "recorded_at": _aware(now()).isoformat(),
                }
            )
            state["updated_at"] = _aware(now()).isoformat()
            _write_state(state_path, state)
            if last_item.status == "repaired":
                break
            if attempt < config.max_attempts:
                sleep(delay)
                delay = min(
                    float(config.max_backoff_seconds),
                    delay * float(config.backoff_multiplier),
                )
        assert last_item is not None
        items.append(last_item)
        state["drawings"][str(target.drawing_id)] = asdict(last_item)
        state["updated_at"] = _aware(now()).isoformat()
        _write_state(state_path, state)
        if target_index + 1 < len(targets) and config.rate_limit_seconds:
            sleep(float(config.rate_limit_seconds))

    return ReconciliationReport(
        selected=len(targets),
        processed=len(items),
        repaired=sum(item.status == "repaired" for item in items),
        source_incomplete=sum(
            item.status == "source_incomplete" for item in items
        ),
        exhausted=sum(item.status == "exhausted" for item in items),
        dry_run=False,
        items=tuple(items),
    )


def repair_from_canonical_raw(
    session_factory: sessionmaker[Session],
    *,
    raw_cache_root: str | Path,
    archive_root: str | Path,
    drawing_numbers: tuple[int, ...],
    dry_run: bool = True,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> OfflineRepairReport:
    """Repair only fields proved present in validated local canonical RAW."""
    if not drawing_numbers or any(
        type(number) is not int or number < 1 for number in drawing_numbers
    ):
        raise ValueError("drawing_numbers must contain positive integers")
    items: list[OfflineRepairItem] = []
    archive = RawArchive(archive_root)
    for number in drawing_numbers:
        with session_factory() as session:
            matches = session.scalars(
                select(Drawing).where(Drawing.number == number)
            ).all()
        if len(matches) != 1:
            items.append(
                OfflineRepairItem(
                    drawing_number=number,
                    drawing_id=None,
                    status="invalid",
                    logical_changes=0,
                    classification="unknown_legacy",
                    reason="drawing_identity_missing_or_ambiguous",
                )
            )
            continue
        drawing = matches[0]
        try:
            cached = load_drawing_detail_cache(
                drawing.id,
                cache_dir=raw_cache_root,
                max_age_seconds=None,
                now=_aware(now()),
                allowed_root=Path(raw_cache_root).resolve().parent,
            )
        except (OSError, TypeError, ValueError):
            items.append(
                OfflineRepairItem(
                    drawing_number=number,
                    drawing_id=drawing.id,
                    status="source_missing",
                    logical_changes=0,
                    classification="no_local_evidence",
                    reason="canonical_raw_missing_or_invalid",
                )
            )
            continue
        try:
            record = archive.archive(
                cached.payload,
                captured_at=cached.fetched_at,
                source=f"canonical-cache:{cached.source}",
                source_endpoint=f"/drawing-info/{drawing.id}",
                lifecycle_status=str(
                    cached.payload["data"].get("status") or "unknown"
                ),
            )
            imported = import_archived_detail(
                session_factory,
                record,
                dry_run=dry_run,
            )
        except (OSError, TypeError, ValueError) as error:
            items.append(
                OfflineRepairItem(
                    drawing_number=number,
                    drawing_id=drawing.id,
                    status="invalid",
                    logical_changes=0,
                    classification="unknown_legacy",
                    reason=_safe_reason(error),
                )
            )
            continue
        items.append(
            OfflineRepairItem(
                drawing_number=number,
                drawing_id=drawing.id,
                status=(
                    "would_repair"
                    if dry_run and imported.logical_changes
                    else "would_no_change"
                    if dry_run
                    else "repaired"
                    if imported.logical_changes
                    else "no_change"
                ),
                logical_changes=imported.logical_changes,
                classification=imported.classification,
                reason=(
                    "validated_canonical_raw_dry_run"
                    if dry_run
                    else "validated_canonical_raw_applied"
                ),
            )
        )
    return OfflineRepairReport(
        selected=len(drawing_numbers),
        repaired=sum(item.status == "repaired" for item in items),
        source_missing=sum(
            item.status == "source_missing" for item in items
        ),
        invalid=sum(item.status == "invalid" for item in items),
        dry_run=dry_run,
        items=tuple(items),
    )


def _validate_selectors(
    from_drawing: int | None,
    to_drawing: int | None,
    last: int | None,
) -> None:
    for name, value in (
        ("from_drawing", from_drawing),
        ("to_drawing", to_drawing),
        ("last", last),
    ):
        if value is not None and (type(value) is not int or value < 1):
            raise ValueError(f"{name} must be a positive integer or None")
    if (
        from_drawing is not None
        and to_drawing is not None
        and from_drawing > to_drawing
    ):
        raise ValueError("from_drawing cannot exceed to_drawing")
    if last is not None and (
        from_drawing is not None or to_drawing is not None
    ):
        raise ValueError("last cannot be combined with a drawing range")


def _load_state(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {
            "schema_version": 1,
            "updated_at": None,
            "drawings": {},
            "attempts": [],
        }
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("reconciliation state is malformed") from error
    expected_hash = payload.pop("state_sha256", None)
    if expected_hash != _hash(payload):
        raise ValueError("reconciliation state hash mismatch")
    payload.setdefault("attempts", [])
    if (
        payload.get("schema_version") != 1
        or not isinstance(payload.get("drawings"), dict)
        or not isinstance(payload.get("attempts"), list)
    ):
        raise ValueError("reconciliation state is malformed")
    return payload


def _write_state(path: str | Path, state: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["state_sha256"] = _hash(state)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reconciliation timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _safe_reason(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    return message[:300]
