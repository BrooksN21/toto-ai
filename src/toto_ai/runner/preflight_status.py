"""Read-only concise status for the exact open-drawing preflight."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from toto_ai.analytics.api_inspector import resolve_drawing_reference
from toto_ai.db.models import (
    DrawingEventPin,
    DrawingPinSet,
    DrawingPinSetItem,
)
from toto_ai.db.session import get_session_factory, open_readonly_db
from toto_ai.runner.morning_dispatch import load_morning_dispatch_record
from toto_ai.runner.operational_selection import load_verified_operational_cutoffs
from toto_ai.runner.preflight_retry_scheduler import (
    prepare_preflight_retry_artifacts,
    verify_preflight_retry_launch_agent,
)
from toto_ai.runner.scheduler import (
    MORNING_WRAPPER_FILENAME,
    SchedulerError,
    experimental_manual_release_status,
    load_scheduler_plan,
)
from toto_ai.runner.scheduler_state import PHASES, load_state

MOSCOW = ZoneInfo("Europe/Moscow")


def build_preflight_status(
    *,
    db: str | Path,
    community: str,
    state_root: str | Path,
    scheduler_root: str | Path,
    now: datetime,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Return status using only read-only DB and local generated artifacts."""
    observed_at = _utc(now)
    database = Path(db).absolute()
    state = Path(state_root).absolute()
    scheduler = Path(scheduler_root).absolute()
    root = Path(project_root).absolute() if project_root is not None else state.parent
    engine = open_readonly_db(database)
    try:
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            reference = resolve_drawing_reference(
                session,
                open=True,
                community=community,
                now=observed_at,
                operational_cutoffs=load_verified_operational_cutoffs(
                    state,
                    project_root=root,
                ),
            )
        deadline = _parse_timestamp(reference.ended_at)
        record, record_path = _latest_record(
            state,
            drawing_id=reference.drawing_id,
            drawing_number=reference.number,
            deadline=deadline,
        )
        identity = record.get("identity") if record is not None else None
        fingerprint = (
            str(identity.get("drawing_fingerprint"))
            if isinstance(identity, dict)
            else None
        )
        preparation = (
            record.get("preparation") if record is not None else None
        )
        if not isinstance(preparation, dict):
            preparation = {}
        unresolved = preparation.get("unresolved", ())
        if not isinstance(unresolved, list):
            unresolved = []
        pin_count = _pin_count(
            session_factory,
            drawing_id=reference.drawing_id,
            fingerprint=fingerprint,
        )
        attention_path, retry_plan_path = _preflight_paths(
            state,
            drawing_id=reference.drawing_id,
            deadline=deadline,
            fingerprint=fingerprint,
        )
        activation = (
            str(record.get("activation_status", "not_requested"))
            if record is not None
            else "not_requested"
        )
        morning_state = _morning_activation_state(scheduler)
        release_gate = _release_gate_status(record)
        retry_scheduler = None
        if retry_plan_path.is_file():
            artifacts = prepare_preflight_retry_artifacts(
                retry_plan_path, write=False
            )
            terminal_retry = (
                preparation.get("status") == "ready"
                and int(preparation.get("mapped_count", 0)) == 15
                and not unresolved
            ) or observed_at >= deadline - timedelta(minutes=60)
            retry_scheduler = verify_preflight_retry_launch_agent(
                artifacts,
                now=observed_at,
                terminal=terminal_retry,
            )
        return {
            "drawing_id": reference.drawing_id,
            "drawing_number": reference.number,
            "deadline_utc": _timestamp(deadline),
            "deadline_msk": deadline.astimezone(MOSCOW).isoformat(),
            "drawing_fingerprint": fingerprint,
            "preparation_status": str(
                preparation.get("status", "not_run")
            ),
            "mapped_count": int(preparation.get("mapped_count", 0)),
            "pin_count": pin_count,
            "unresolved_count": len(unresolved),
            "unresolved_event_orders": [
                int(item["event_order"])
                for item in unresolved
                if isinstance(item, dict) and "event_order" in item
            ],
            "record_path": None if record_path is None else str(record_path),
            "attention_path": (
                str(attention_path) if attention_path.is_file() else None
            ),
            "retry_plan_path": (
                str(retry_plan_path) if retry_plan_path.is_file() else None
            ),
            "retry_scheduler": retry_scheduler,
            "morning_activation_state": morning_state,
            "evening_activation_state": activation,
            "evening_launch_agent_label": (
                None
                if record is None
                else record.get("launch_agent_label")
            ),
            "package_generation_state": (
                "enabled" if activation == "activated" else "disabled"
            ),
            "release_gate": release_gate,
            "evening_scheduler": _evening_scheduler_status(
                record,
                now=observed_at,
            ),
        }
    finally:
        engine.dispose()


def _latest_record(
    state_root: Path,
    *,
    drawing_id: int,
    drawing_number: int | None,
    deadline: datetime,
) -> tuple[dict[str, object] | None, Path | None]:
    prefix = f"drawing-{drawing_id}-{deadline.strftime('%Y%m%dT%H%M%SZ')}"
    candidates: list[tuple[str, Path, dict[str, object]]] = []
    if state_root.is_dir() and not state_root.is_symlink():
        for path in state_root.glob(f"{prefix}*.json"):
            record = load_morning_dispatch_record(path)
            if record is None:
                continue
            identity = record.get("identity")
            if (
                not isinstance(identity, dict)
                or identity.get("drawing_id") != drawing_id
                or identity.get("drawing_number") != drawing_number
                or identity.get("deadline") != _timestamp(deadline)
            ):
                continue
            candidates.append((str(record.get("observed_at", "")), path, record))
    if not candidates:
        return None, None
    _, path, record = max(candidates, key=lambda item: (item[0], str(item[1])))
    return record, path


def _pin_count(
    session_factory: Any,
    *,
    drawing_id: int,
    fingerprint: str | None,
) -> int:
    if fingerprint is None:
        return 0
    with session_factory() as session:
        legacy = int(
            session.scalar(
                select(func.count())
                .select_from(DrawingEventPin)
                .where(
                    DrawingEventPin.drawing_id == drawing_id,
                    DrawingEventPin.drawing_fingerprint == fingerprint,
                    DrawingEventPin.status == "valid",
                )
            )
            or 0
        )
        pin_set_id = session.scalar(
            select(DrawingPinSet.pin_set_id).where(
                DrawingPinSet.drawing_id == drawing_id,
                DrawingPinSet.drawing_fingerprint == fingerprint,
                DrawingPinSet.status == "ready",
            )
        )
        canonical = (
            0
            if pin_set_id is None
            else int(
                session.scalar(
                    select(func.count())
                    .select_from(DrawingPinSetItem)
                    .where(DrawingPinSetItem.pin_set_id == pin_set_id)
                )
                or 0
            )
        )
    return max(legacy, canonical)


def _preflight_paths(
    state_root: Path,
    *,
    drawing_id: int,
    deadline: datetime,
    fingerprint: str | None,
) -> tuple[Path, Path]:
    if fingerprint is None:
        root = state_root / "preflight" / "not-prepared"
    else:
        root = state_root / "preflight" / (
            f"drawing-{drawing_id}-{deadline.strftime('%Y%m%dT%H%M%SZ')}-"
            f"{fingerprint[:16]}"
        )
    return root / "attention.json", root / "retry-plan.json"


def _morning_activation_state(scheduler_root: Path) -> str:
    wrapper = scheduler_root / "morning-dispatcher" / MORNING_WRAPPER_FILENAME
    if not wrapper.is_file() or wrapper.is_symlink():
        return "not_generated"
    content = wrapper.read_text(encoding="utf-8")
    return "activation_enabled_candidate" if "--activate" in content else "passive"


def _release_gate_status(record: dict[str, object] | None) -> dict[str, object]:
    if record is None or record.get("activation_status") != "activated":
        return {
            "state": "scheduler_not_activated",
            "profitability_proven": False,
            "automatic_wagering": False,
        }
    plan_value = record.get("plan_path")
    if not isinstance(plan_value, str) or not plan_value.strip():
        return {
            "state": "scheduler_plan_missing",
            "profitability_proven": False,
            "automatic_wagering": False,
        }
    try:
        plan = load_scheduler_plan(plan_value)
        return dict(experimental_manual_release_status(plan))
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        return {
            "state": "release_authorization_invalid",
            "reason": str(error),
            "profitability_proven": False,
            "automatic_wagering": False,
        }


def _evening_scheduler_status(
    record: dict[str, object] | None,
    *,
    now: datetime,
) -> dict[str, object]:
    """Return a hash-verified, read-only phase snapshot for one evening plan."""

    observed_at = _utc(now)
    if record is None or record.get("activation_status") != "activated":
        return {
            "state": "not_activated",
            "next_checkpoint": None,
        }
    plan_value = record.get("plan_path")
    if not isinstance(plan_value, str) or not plan_value.strip():
        return {
            "state": "invalid",
            "reason": "scheduler plan is missing",
            "next_checkpoint": None,
        }
    try:
        plan = load_scheduler_plan(plan_value)
        state_path = plan.output_dir / "scheduler-state.json"
        state = load_state(
            state_path,
            plan_id=plan.plan_id,
            now=observed_at,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        return {
            "state": "invalid",
            "reason": str(error),
            "next_checkpoint": None,
        }

    transitions = state.get("transitions", [])
    latest_by_phase: dict[str, dict[str, object]] = {}
    if isinstance(transitions, list):
        for item in transitions:
            if isinstance(item, dict) and item.get("phase") in PHASES:
                latest_by_phase[str(item["phase"])] = item
    phases: dict[str, dict[str, object]] = {}
    state_phases = state["phases"]
    for phase in PHASES:
        phase_state = state_phases[phase]
        latest = latest_by_phase.get(phase)
        attempts = phase_state.get("attempts", [])
        phases[phase] = {
            "status": phase_state.get("status"),
            "attempt_count": len(attempts) if isinstance(attempts, list) else 0,
            "latest_observed_at": (
                None if latest is None else latest.get("observed_at")
            ),
            "latest_reason": None if latest is None else latest.get("reason"),
        }

    checkpoints = (
        ("tls_preflight", "tls_preflight", plan.tls_preflight_at),
        ("api_preflight", "api_preflight", plan.api_preflight_at),
        (
            "freshness_preflight",
            "freshness_preflight",
            plan.freshness_preflight_at,
        ),
        ("warmup", "warmup", plan.preflight_at),
        ("refresh", "refresh", plan.fallback_at),
        ("final", "final", plan.final_at),
        ("final_retry", "final", plan.retry_at),
        ("publish", "publish", plan.publish_deadline),
    )
    next_checkpoint = None
    for checkpoint, _state_phase, scheduled_at in checkpoints:
        if scheduled_at > observed_at:
            next_checkpoint = {
                "phase": checkpoint,
                "at_utc": _timestamp(scheduled_at),
                "at_msk": scheduled_at.astimezone(MOSCOW).isoformat(),
            }
            break

    overdue: list[dict[str, object]] = []
    for checkpoint, state_phase, scheduled_at in checkpoints:
        if scheduled_at > observed_at:
            continue
        if phases[state_phase]["status"] in {"pending", "retryable_failed"}:
            overdue.append(
                {
                    "phase": checkpoint,
                    "at_utc": _timestamp(scheduled_at),
                }
            )

    terminal = state.get("terminal")
    if terminal is not None:
        status = "terminal"
        next_checkpoint = None
    elif overdue:
        status = "attention_required"
    elif int(state.get("revision", 0)) > 0:
        status = "running_schedule"
    else:
        status = "waiting"
    last_transition = transitions[-1] if transitions else None
    return {
        "state": status,
        "plan_id": plan.plan_id,
        "state_path": str(state_path),
        "state_revision": int(state.get("revision", 0)),
        "updated_at": state.get("updated_at"),
        "terminal": terminal,
        "phases": phases,
        "last_transition": last_transition,
        "next_checkpoint": next_checkpoint,
        "overdue_checkpoints": overdue,
    }


def _parse_timestamp(value: str | None) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("open drawing deadline is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("open drawing deadline is invalid") from error
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("status time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")
