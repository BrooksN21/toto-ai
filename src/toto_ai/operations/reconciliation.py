"""Bounded, resumable reconciliation for incomplete finished drawings."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import requests
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.collector.lifecycle import (
    RawArchive,
    finished_drawing_is_current,
    import_archived_detail,
    preview_detail_payload,
    validate_full_detail_payload,
)
from toto_ai.db.models import Drawing, DrawingReconciliationState, Event


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
class ReconciliationRetryPolicy:
    """Persistent retry policy shared by manual, range, and nightly runs."""

    source_incomplete_base_seconds: float = 6 * 60 * 60
    source_incomplete_max_seconds: float = 7 * 24 * 60 * 60
    source_incomplete_multiplier: float = 2.0
    source_incomplete_quarantine_after: int = 5
    quarantine_seconds: float = 30 * 24 * 60 * 60
    transient_base_seconds: float = 5 * 60
    transient_max_seconds: float = 60 * 60
    transient_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if (
            type(self.source_incomplete_quarantine_after) is not int
            or self.source_incomplete_quarantine_after < 2
        ):
            raise ValueError(
                "source_incomplete_quarantine_after must be an integer >= 2"
            )
        for name in (
            "source_incomplete_base_seconds",
            "source_incomplete_max_seconds",
            "source_incomplete_multiplier",
            "quarantine_seconds",
            "transient_base_seconds",
            "transient_max_seconds",
            "transient_multiplier",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if self.source_incomplete_multiplier < 1:
            raise ValueError("source_incomplete_multiplier must be at least 1")
        if self.transient_multiplier < 1:
            raise ValueError("transient_multiplier must be at least 1")
        if self.source_incomplete_max_seconds < self.source_incomplete_base_seconds:
            raise ValueError("source_incomplete_max_seconds must be at least its base")
        if self.transient_max_seconds < self.transient_base_seconds:
            raise ValueError(
                "transient_max_seconds must be at least transient_base_seconds"
            )


@dataclass(frozen=True)
class ReconciliationTarget:
    drawing_id: int
    number: int
    ended_at: str
    terminal_count: int


@dataclass(frozen=True)
class ReconciliationItem:
    drawing_id: int
    drawing_number: int
    status: Literal[
        "would_reconcile",
        "would_skip_cooldown",
        "would_skip_quarantined",
        "would_defer_batch",
        "repaired",
        "source_incomplete",
        "transient_error",
        "cooldown",
        "quarantined",
        "deferred_batch",
    ]
    attempts: int
    terminal_results: int
    reason: str
    raw_snapshot_sha256: str | None
    classification: str | None = None
    retry_state: str | None = None
    next_eligible_at: str | None = None
    last_error_code: str | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    selected: int
    processed: int
    repaired: int
    source_incomplete: int
    exhausted: int
    transient_error: int
    skipped_cooldown: int
    quarantined: int
    dry_run: bool
    force: bool
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
        selected_ids = tuple(drawing.id for drawing in selected)
        terminal_counts = dict.fromkeys(selected_ids, 0)
        if selected_ids:
            for event in session.scalars(
                select(Event).where(Event.drawing_id.in_(selected_ids))
            ).all():
                if _event_is_terminal(event):
                    terminal_counts[event.drawing_id] += 1
    if last is not None:
        selected = selected[-last:]
    if batch_size is not None:
        selected = selected[:batch_size]
    return tuple(
        ReconciliationTarget(
            drawing_id=drawing.id,
            number=drawing.number,
            ended_at=drawing.ended_at or "",
            terminal_count=terminal_counts[drawing.id],
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
    retry_policy: ReconciliationRetryPolicy | None = None,
    from_drawing: int | None = None,
    to_drawing: int | None = None,
    last: int | None = None,
    force: bool = False,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
) -> ReconciliationReport:
    config = config or ReconciliationConfig()
    policy = retry_policy or ReconciliationRetryPolicy()
    if type(force) is not bool:
        raise ValueError("force must be a boolean")
    targets = select_incomplete_finished_drawings(
        session_factory,
        from_drawing=from_drawing,
        to_drawing=to_drawing,
        last=last,
        batch_size=None,
    )
    observed_at = _aware(now())
    persisted = _load_persisted_states(session_factory, targets)
    eligible_targets: list[ReconciliationTarget] = []
    items: list[ReconciliationItem] = []

    for target in targets:
        source = _source_for(target.drawing_id)
        row = persisted.get((target.drawing_id, "totobrief", source))
        blocked_status = _blocked_status(
            row,
            target=target,
            observed_at=observed_at,
            force=force,
        )
        if blocked_status is not None:
            items.append(
                _blocked_item(
                    target,
                    row,
                    status=(
                        f"would_skip_{blocked_status}"
                        if config.dry_run
                        else blocked_status
                    ),
                )
            )
            continue
        if config.batch_size is not None and len(eligible_targets) >= config.batch_size:
            items.append(
                _blocked_item(
                    target,
                    row,
                    status=(
                        "would_defer_batch" if config.dry_run else "deferred_batch"
                    ),
                    reason="batch_limit",
                )
            )
            continue
        eligible_targets.append(target)
        if config.dry_run:
            items.append(
                _blocked_item(
                    target,
                    row,
                    status="would_reconcile",
                    reason=(
                        "dry_run_force_no_network" if force else "dry_run_no_network"
                    ),
                )
            )

    if config.dry_run:
        return _report(
            selected=len(targets),
            processed=0,
            dry_run=True,
            force=force,
            items=items,
        )

    state = _load_state(state_path)
    archive = RawArchive(archive_root)
    processed_items: list[ReconciliationItem] = []
    for target_index, target in enumerate(eligible_targets):
        delay = float(config.initial_backoff_seconds)
        last_item: ReconciliationItem | None = None
        for attempt in range(1, config.max_attempts + 1):
            attempted_at = _aware(now())
            source = _source_for(target.drawing_id)
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
            ) as error:
                last_error_code = _transient_error_code(error)
                row = _record_transient_error(
                    session_factory,
                    target=target,
                    provider="totobrief",
                    source=source,
                    attempted_at=attempted_at,
                    error_code=last_error_code,
                    policy=policy,
                )
                last_item = _item_from_state(
                    target,
                    row,
                    status="transient_error",
                    reason=last_error_code,
                )
            except (KeyError, TypeError, ValueError) as error:
                last_error_code = "source_validation_error"
                row = _record_transient_error(
                    session_factory,
                    target=target,
                    provider="totobrief",
                    source=source,
                    attempted_at=attempted_at,
                    error_code=last_error_code,
                    policy=policy,
                )
                last_item = _item_from_state(
                    target,
                    row,
                    status="transient_error",
                    reason=f"{last_error_code}:{_safe_reason(error)}",
                )
            else:
                if imported.terminal_result_count == 15:
                    row = _record_complete(
                        session_factory,
                        target=target,
                        provider="totobrief",
                        source=source,
                        attempted_at=attempted_at,
                        source_fingerprint=record.payload_sha256,
                    )
                    last_item = _item_from_state(
                        target,
                        row,
                        status="repaired",
                        reason="terminal_15_of_15",
                        raw_snapshot_sha256=record.snapshot_sha256,
                    )
                else:
                    row = _record_source_incomplete(
                        session_factory,
                        target=target,
                        provider="totobrief",
                        source=source,
                        attempted_at=attempted_at,
                        source_fingerprint=record.payload_sha256,
                        terminal_count=imported.terminal_result_count,
                        policy=policy,
                    )
                    last_item = _item_from_state(
                        target,
                        row,
                        status=(
                            "quarantined"
                            if row.retry_state == "quarantined"
                            else "source_incomplete"
                        ),
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
            if last_item.status in {
                "repaired",
                "source_incomplete",
                "quarantined",
            }:
                break
            if attempt < config.max_attempts:
                sleep(delay)
                delay = min(
                    float(config.max_backoff_seconds),
                    delay * float(config.backoff_multiplier),
                )
        assert last_item is not None
        processed_items.append(last_item)
        state["drawings"][str(target.drawing_id)] = asdict(last_item)
        state["updated_at"] = _aware(now()).isoformat()
        _write_state(state_path, state)
        if target_index + 1 < len(eligible_targets) and config.rate_limit_seconds:
            sleep(float(config.rate_limit_seconds))

    items.extend(processed_items)
    items.sort(key=lambda item: (item.drawing_number, item.drawing_id))
    return _report(
        selected=len(targets),
        processed=len(processed_items),
        dry_run=False,
        force=force,
        items=items,
    )


def _load_persisted_states(
    session_factory: sessionmaker[Session],
    targets: tuple[ReconciliationTarget, ...],
) -> dict[tuple[int, str, str], DrawingReconciliationState]:
    if not targets:
        return {}
    drawing_ids = tuple(target.drawing_id for target in targets)
    with session_factory() as session:
        bind = session.get_bind()
        if not inspect(bind).has_table(DrawingReconciliationState.__tablename__):
            return {}
        rows = session.scalars(
            select(DrawingReconciliationState).where(
                DrawingReconciliationState.drawing_id.in_(drawing_ids)
            )
        ).all()
    return {(row.drawing_id, row.provider, row.source): row for row in rows}


def _blocked_status(
    row: DrawingReconciliationState | None,
    *,
    target: ReconciliationTarget,
    observed_at: datetime,
    force: bool,
) -> Literal["cooldown", "quarantined"] | None:
    if row is None or force or row.retry_state in {"eligible", "complete"}:
        return None
    if target.terminal_count > row.terminal_count:
        return None
    if row.retry_state not in {"cooldown", "quarantined"}:
        raise ValueError("reconciliation retry state is invalid")
    if row.next_eligible_at is None:
        raise ValueError("blocked reconciliation state lacks next_eligible_at")
    next_eligible_at = _parse_timestamp(
        row.next_eligible_at,
        field="reconciliation next_eligible_at",
    )
    if observed_at >= next_eligible_at:
        return None
    return row.retry_state  # type: ignore[return-value]


def _blocked_item(
    target: ReconciliationTarget,
    row: DrawingReconciliationState | None,
    *,
    status: str,
    reason: str | None = None,
) -> ReconciliationItem:
    retry_state = row.retry_state if row is not None else "eligible"
    return ReconciliationItem(
        drawing_id=target.drawing_id,
        drawing_number=target.number,
        status=status,  # type: ignore[arg-type]
        attempts=row.attempt_count if row is not None else 0,
        terminal_results=row.terminal_count if row is not None else 0,
        reason=reason or f"retry_state_{retry_state}",
        raw_snapshot_sha256=None,
        classification=row.classification if row is not None else None,
        retry_state=retry_state,
        next_eligible_at=(row.next_eligible_at if row is not None else None),
        last_error_code=row.last_error_code if row is not None else None,
    )


def _item_from_state(
    target: ReconciliationTarget,
    row: DrawingReconciliationState,
    *,
    status: str,
    reason: str,
    raw_snapshot_sha256: str | None = None,
) -> ReconciliationItem:
    return ReconciliationItem(
        drawing_id=target.drawing_id,
        drawing_number=target.number,
        status=status,  # type: ignore[arg-type]
        attempts=row.attempt_count,
        terminal_results=row.terminal_count,
        reason=reason,
        raw_snapshot_sha256=raw_snapshot_sha256,
        classification=row.classification,
        retry_state=row.retry_state,
        next_eligible_at=row.next_eligible_at,
        last_error_code=row.last_error_code,
    )


def _record_source_incomplete(
    session_factory: sessionmaker[Session],
    *,
    target: ReconciliationTarget,
    provider: str,
    source: str,
    attempted_at: datetime,
    source_fingerprint: str,
    terminal_count: int,
    policy: ReconciliationRetryPolicy,
) -> DrawingReconciliationState:
    with session_factory.begin() as session:
        row = _get_or_create_state(
            session,
            target=target,
            provider=provider,
            source=source,
            observed_at=attempted_at,
        )
        unchanged = (
            row.classification == "source_incomplete"
            and row.last_source_fingerprint == source_fingerprint
            and row.terminal_count == terminal_count
        )
        unchanged_count = row.unchanged_observation_count + 1 if unchanged else 1
        quarantined = unchanged_count >= policy.source_incomplete_quarantine_after
        if quarantined:
            retry_state = "quarantined"
            next_eligible_at = attempted_at + timedelta(
                seconds=float(policy.quarantine_seconds)
            )
        else:
            retry_state = "cooldown"
            cooldown = min(
                float(policy.source_incomplete_max_seconds),
                float(policy.source_incomplete_base_seconds)
                * (float(policy.source_incomplete_multiplier) ** (unchanged_count - 1)),
            )
            next_eligible_at = attempted_at + timedelta(seconds=cooldown)
        row.last_attempt_at = attempted_at.isoformat()
        row.attempt_count += 1
        row.last_source_fingerprint = source_fingerprint
        row.terminal_count = terminal_count
        row.classification = "source_incomplete"
        row.retry_state = retry_state
        row.next_eligible_at = next_eligible_at.isoformat()
        row.last_error_code = None
        row.unchanged_observation_count = unchanged_count
        row.transient_error_count = 0
        row.updated_at = attempted_at.isoformat()
        session.flush()
        session.refresh(row)
        return row


def _record_complete(
    session_factory: sessionmaker[Session],
    *,
    target: ReconciliationTarget,
    provider: str,
    source: str,
    attempted_at: datetime,
    source_fingerprint: str,
) -> DrawingReconciliationState:
    with session_factory.begin() as session:
        row = _get_or_create_state(
            session,
            target=target,
            provider=provider,
            source=source,
            observed_at=attempted_at,
        )
        row.last_attempt_at = attempted_at.isoformat()
        row.attempt_count += 1
        row.last_source_fingerprint = source_fingerprint
        row.terminal_count = 15
        row.classification = "complete"
        row.retry_state = "complete"
        row.next_eligible_at = None
        row.last_error_code = None
        row.unchanged_observation_count = 0
        row.transient_error_count = 0
        row.updated_at = attempted_at.isoformat()
        session.flush()
        session.refresh(row)
        return row


def _record_transient_error(
    session_factory: sessionmaker[Session],
    *,
    target: ReconciliationTarget,
    provider: str,
    source: str,
    attempted_at: datetime,
    error_code: str,
    policy: ReconciliationRetryPolicy,
) -> DrawingReconciliationState:
    with session_factory.begin() as session:
        row = _get_or_create_state(
            session,
            target=target,
            provider=provider,
            source=source,
            observed_at=attempted_at,
        )
        error_count = (
            row.transient_error_count + 1
            if row.classification == "transient_error"
            else 1
        )
        cooldown = min(
            float(policy.transient_max_seconds),
            float(policy.transient_base_seconds)
            * (float(policy.transient_multiplier) ** (error_count - 1)),
        )
        row.last_attempt_at = attempted_at.isoformat()
        row.attempt_count += 1
        row.classification = "transient_error"
        row.retry_state = "cooldown"
        row.next_eligible_at = (attempted_at + timedelta(seconds=cooldown)).isoformat()
        row.last_error_code = error_code
        row.unchanged_observation_count = 0
        row.transient_error_count = error_count
        row.updated_at = attempted_at.isoformat()
        session.flush()
        session.refresh(row)
        return row


def _get_or_create_state(
    session: Session,
    *,
    target: ReconciliationTarget,
    provider: str,
    source: str,
    observed_at: datetime,
) -> DrawingReconciliationState:
    row = session.scalar(
        select(DrawingReconciliationState).where(
            DrawingReconciliationState.drawing_id == target.drawing_id,
            DrawingReconciliationState.provider == provider,
            DrawingReconciliationState.source == source,
        )
    )
    if row is not None:
        return row
    row = DrawingReconciliationState(
        drawing_id=target.drawing_id,
        provider=provider,
        source=source,
        last_attempt_at=None,
        attempt_count=0,
        last_source_fingerprint=None,
        terminal_count=0,
        classification="transient_error",
        retry_state="eligible",
        next_eligible_at=None,
        last_error_code=None,
        unchanged_observation_count=0,
        transient_error_count=0,
        updated_at=observed_at.isoformat(),
    )
    session.add(row)
    session.flush()
    return row


def _report(
    *,
    selected: int,
    processed: int,
    dry_run: bool,
    force: bool,
    items: list[ReconciliationItem],
) -> ReconciliationReport:
    frozen = tuple(items)
    transient = sum(item.status == "transient_error" for item in frozen)
    return ReconciliationReport(
        selected=selected,
        processed=processed,
        repaired=sum(item.status == "repaired" for item in frozen),
        source_incomplete=sum(item.status == "source_incomplete" for item in frozen),
        exhausted=transient,
        transient_error=transient,
        skipped_cooldown=sum(
            item.status in {"cooldown", "would_skip_cooldown"} for item in frozen
        ),
        quarantined=sum(
            item.status in {"quarantined", "would_skip_quarantined"} for item in frozen
        ),
        dry_run=dry_run,
        force=force,
        items=frozen,
    )


def _source_for(drawing_id: int) -> str:
    return f"/drawing-info/{drawing_id}"


def _event_is_terminal(event: Event) -> bool:
    if event.result in {"1", "X", "2"}:
        return True
    return event.result == "*" and event.result_status in {
        "void",
        "cancelled",
        "canceled",
    }


def _transient_error_code(error: BaseException) -> str:
    if isinstance(error, TotoBriefRequestError):
        if error.status_code == 429:
            return "http_429"
        if error.status_code is not None and 500 <= error.status_code <= 599:
            return f"http_{error.status_code}"
        if error.status_code is not None:
            return f"http_{error.status_code}"
        return "transport_error"
    if isinstance(error, OSError) and not isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
            requests.RequestException,
        ),
    ):
        return "local_io_error"
    return "transport_error"


def _parse_timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} is invalid") from error
    return _aware(parsed)


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
            if dry_run:
                imported = preview_detail_payload(
                    session_factory,
                    cached.payload,
                    archive_root=archive_root,
                    captured_at=cached.fetched_at,
                    source=f"canonical-cache:{cached.source}",
                    source_endpoint=f"/drawing-info/{drawing.id}",
                    lifecycle_status=str(
                        cached.payload["data"].get("status") or "unknown"
                    ),
                )
            else:
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
                    dry_run=False,
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
        source_missing=sum(item.status == "source_missing" for item in items),
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
    if last is not None and (from_drawing is not None or to_drawing is not None):
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
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
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
