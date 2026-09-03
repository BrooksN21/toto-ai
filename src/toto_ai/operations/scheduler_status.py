"""Read-only, plan-bound scheduler status used by local watchers."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from toto_ai.runner.scheduler import (
    SchedulerPlan,
    experimental_manual_release_status,
)

_MOSCOW = ZoneInfo("Europe/Moscow")
_STRATEGIES = ("quality-v2", "sports-shadow", "quality-v3", "robust")


def scheduler_status(
    plan: SchedulerPlan, *, observed_at: datetime | None = None
) -> dict[str, object]:
    """Return one canonical status without executing or mutating the scheduler."""

    observed_at = _aware_utc(observed_at)
    output = plan.output_dir.resolve()
    attempt = _latest_attempt(output, plan)
    operator = _bound_json(output / "operator-result.json", plan)
    sidecar = _bound_json(
        output / "parallel-challenger" / "output" / "sidecar-status.json",
        plan,
    )
    comparison = _comparison(sidecar, output, plan)
    models = _model_states(comparison)
    selected_strategy = _selected_strategy(sidecar, comparison)
    best_coupon = _highest_p13(sidecar, comparison, selected_strategy)
    next_name, next_at = _next_checkpoint(plan, observed_at)
    last_phase = _last_phase(plan, observed_at, attempt)
    primary = _primary_status(attempt, operator)
    terminal = _terminal_operator(operator)
    manual_wager_request = _manual_wager_request(plan, observed_at)
    blocker = _blocker(attempt, operator, sidecar, manual_wager_request)
    expires_at = plan.deadlines["t_minus_10"]
    return {
        "schema_version": 1,
        "observed_at_msk": observed_at.astimezone(_MOSCOW).isoformat(),
        "drawing_number": plan.drawing,
        "drawing_id": plan.drawing_id,
        "plan_id": plan.plan_id,
        "output_dir": str(output),
        "last_phase": last_phase,
        "last_attempt": _attempt_summary(attempt),
        "primary_quality_v2": primary,
        "challengers": models,
        "selected_strategy": selected_strategy,
        "highest_p13_single_coupon": best_coupon,
        "operator_result": _operator_summary(operator),
        "operator_result_ready": operator is not None,
        "manual_wager_request": manual_wager_request,
        "terminal": terminal,
        "blocker": blocker,
        "next_checkpoint": {
            "phase": next_name,
            "at_msk": None
            if next_at is None
            else next_at.astimezone(_MOSCOW).isoformat(),
        },
        "expires_at_msk": expires_at.astimezone(_MOSCOW).isoformat(),
        "automatic_wagering": False,
        "mutated": False,
    }


def watch_scheduler_status(
    plan: SchedulerPlan,
    *,
    latest_path: Path,
    history_path: Path,
    interval_seconds: float = 30.0,
    status_provider: Callable[[SchedulerPlan], dict[str, object]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
) -> dict[str, object]:
    """Persist only status changes until the plan reaches a terminal result."""

    if interval_seconds <= 0:
        raise ValueError("watch interval must be positive")
    latest_path = _watch_path(plan, latest_path, "latest status")
    history_path = _watch_path(plan, history_path, "status history")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    provider = status_provider or (lambda value: scheduler_status(value))
    previous: str | None = None
    last: dict[str, object] | None = None
    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        last = provider(plan)
        encoded = json.dumps(
            last, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        fingerprint = _status_fingerprint(last)
        _atomic_text(latest_path, encoded + "\n")
        if fingerprint != previous:
            with history_path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")
            print(encoded, flush=True)
            previous = fingerprint
        if bool(last.get("terminal")):
            return last
        if max_iterations is None or iteration < max_iterations:
            sleep(interval_seconds)
    if last is None:
        raise ValueError("watcher did not observe scheduler status")
    return last


def _latest_attempt(
    output: Path, plan: SchedulerPlan
) -> Mapping[str, object] | None:
    attempts = output / "attempts"
    if not attempts.is_dir():
        return None
    candidates: list[tuple[datetime, Mapping[str, object]]] = []
    for path in attempts.glob("*/status.json"):
        payload = _bound_json(path, plan)
        if payload is None:
            continue
        completed = _timestamp(payload.get("completed_at"))
        published = _timestamp(payload.get("published_at"))
        fallback = datetime.min.replace(tzinfo=timezone.utc)
        candidates.append((completed or published or fallback, payload))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _bound_json(
    path: Path, plan: SchedulerPlan
) -> Mapping[str, object] | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"status artifact is unreadable: {path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"status artifact must be an object: {path}")
    plan_id = payload.get("plan_id")
    drawing = payload.get("drawing", payload.get("drawing_number"))
    if plan_id is not None and plan_id != plan.plan_id:
        raise ValueError(f"status artifact plan mismatch: {path}")
    if drawing is not None and drawing != plan.drawing:
        raise ValueError(f"status artifact drawing mismatch: {path}")
    return payload


def _comparison(
    sidecar: Mapping[str, object] | None,
    output: Path,
    plan: SchedulerPlan,
) -> Mapping[str, object] | None:
    if sidecar is None:
        return None
    raw_path = sidecar.get("research_report")
    if not isinstance(raw_path, str):
        return None
    path = Path(raw_path).resolve()
    if output not in path.parents:
        raise ValueError("parallel comparison escapes scheduler output")
    return _bound_json(path, plan)


def _model_states(
    comparison: Mapping[str, object] | None,
) -> dict[str, object]:
    states: dict[str, object] = {
        name: {"status": "pending", "reasons": []} for name in _STRATEGIES
    }
    if comparison is None:
        return states
    selection = comparison.get("experimental_selection")
    if not isinstance(selection, Mapping):
        return states
    rejections = selection.get("rejections")
    rejection_map = rejections if isinstance(rejections, Mapping) else {}
    candidates = selection.get("candidates")
    if not isinstance(candidates, list):
        return states
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        strategy = candidate.get("strategy_id")
        if strategy not in states:
            continue
        reasons = rejection_map.get(strategy, [])
        if not isinstance(reasons, list):
            reasons = []
        states[str(strategy)] = {
            "status": "rejected" if reasons else "eligible",
            "reasons": [str(reason) for reason in reasons],
            "coupon_count": candidate.get("coupon_count"),
            "cost": candidate.get("cost"),
            "maximum_outcome_share": candidate.get("maximum_outcome_share"),
        }
    return states


def _selected_strategy(
    sidecar: Mapping[str, object] | None,
    comparison: Mapping[str, object] | None,
) -> str | None:
    if sidecar is not None:
        release = sidecar.get("parallel_release")
        if isinstance(release, Mapping) and isinstance(
            release.get("selected_strategy_id"), str
        ):
            return str(release["selected_strategy_id"])
    if comparison is not None:
        selection = comparison.get("experimental_selection")
        if isinstance(selection, Mapping) and isinstance(
            selection.get("selected_strategy_id"), str
        ):
            return str(selection["selected_strategy_id"])
    return None


def _highest_p13(
    sidecar: Mapping[str, object] | None,
    comparison: Mapping[str, object] | None,
    selected_strategy: str | None,
) -> Mapping[str, object] | None:
    if sidecar is not None:
        release = sidecar.get("parallel_release")
        if isinstance(release, Mapping):
            value = release.get("highest_p13_single_coupon")
            if isinstance(value, Mapping):
                return dict(value) | {"strategy_id": selected_strategy}
    if comparison is not None and selected_strategy is not None:
        values = comparison.get("highest_p13_single_coupons")
        if isinstance(values, Mapping):
            value = values.get(selected_strategy)
            if isinstance(value, Mapping):
                return dict(value) | {"strategy_id": selected_strategy}
    return None


def _primary_status(
    attempt: Mapping[str, object] | None,
    operator: Mapping[str, object] | None,
) -> dict[str, object]:
    if operator is not None:
        return {
            "status": operator.get("operator_status", operator.get("decision")),
            "reason": operator.get("reason"),
        }
    if attempt is not None:
        return {
            "status": attempt.get("outcome", attempt.get("state", "attempted")),
            "reason": attempt.get("reason", attempt.get("error")),
        }
    return {"status": "pending", "reason": None}


def _attempt_summary(
    attempt: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if attempt is None:
        return None
    return {
        key: attempt.get(key)
        for key in (
            "run_id",
            "state",
            "outcome",
            "decision",
            "reason",
            "error",
            "completed_at",
        )
    }


def _operator_summary(
    operator: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if operator is None:
        return None
    return {
        key: operator.get(key)
        for key in (
            "operator_status",
            "decision",
            "actionable",
            "reason",
            "coupon_path",
            "package_sha256",
            "selected_count",
            "selected_cost",
            "completed_at",
        )
    }


def _terminal_operator(operator: Mapping[str, object] | None) -> bool:
    if operator is None:
        return False
    status = operator.get("operator_status", operator.get("decision"))
    return status in {"PLAY", "NO_BET", "NO BET"}


def _blocker(
    attempt: Mapping[str, object] | None,
    operator: Mapping[str, object] | None,
    sidecar: Mapping[str, object] | None,
    manual_wager_request: Mapping[str, object],
) -> str | None:
    if operator is not None and operator.get("operator_status") == "NO_BET":
        return str(operator.get("reason") or "operator returned NO_BET")
    if attempt is not None and attempt.get("state") == "failed":
        return str(attempt.get("error") or attempt.get("reason") or "attempt failed")
    if sidecar is not None and str(sidecar.get("status", "")).endswith("FAILED_OPEN"):
        return str(sidecar.get("error") or sidecar.get("status"))
    if manual_wager_request.get("state") == "owner_response_required":
        return "manual_wager_intent_and_release_not_recorded"
    if manual_wager_request.get("state") == "release_window_expired":
        return "manual_wager_release_expired_without_authorization"
    return None


def _manual_wager_request(
    plan: SchedulerPlan,
    observed_at: datetime,
) -> dict[str, object]:
    """Return a deterministic plan-bound owner decision prompt and state."""

    release = experimental_manual_release_status(plan)
    expires_at_msk = plan.publish_deadline.astimezone(_MOSCOW).isoformat()
    authorized = release.get("state") == "experimental_manual_authorized"
    expired = observed_at >= plan.publish_deadline
    prompt = None
    if not authorized and not expired:
        prompt = (
            f"Планируется ли ручная ставка на тираж {plan.drawing}? "
            "Если да, подтвердите experimental manual release для "
            f"plan_id {plan.plan_id}, банк {plan.requested_bank} ₽, "
            f"ставка {plan.stake} ₽ до {expires_at_msk}. "
            "Автоматические ставки запрещены."
        )
    payload: dict[str, object] = {
        "state": (
            "experimental_manual_authorized"
            if authorized
            else "release_window_expired"
            if expired
            else "owner_response_required"
        ),
        "action_required": not authorized and not expired,
        "prompt": prompt,
        "drawing_number": plan.drawing,
        "drawing_id": plan.drawing_id,
        "plan_id": plan.plan_id,
        "requested_bank": plan.requested_bank,
        "stake": plan.stake,
        "expires_at_msk": expires_at_msk,
        "authorization_sha256": release.get("authorization_sha256"),
        "profitability_proven": False,
        "automatic_wagering": False,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["request_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def _last_phase(
    plan: SchedulerPlan,
    observed_at: datetime,
    attempt: Mapping[str, object] | None,
) -> str:
    if attempt is not None:
        run_id = attempt.get("run_id")
        if isinstance(run_id, str) and run_id:
            return run_id.split("-", 1)[0]
    due = [
        (when, name)
        for name, when in plan.deadlines.items()
        if when <= observed_at and name != "ended_at"
    ]
    return "scheduled" if not due else max(due)[1]


def _next_checkpoint(
    plan: SchedulerPlan, observed_at: datetime
) -> tuple[str | None, datetime | None]:
    upcoming = [
        (when, name)
        for name, when in plan.deadlines.items()
        if when > observed_at and name != "ended_at"
    ]
    if not upcoming:
        return None, None
    when, name = min(upcoming)
    return name, when


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _aware_utc(value: datetime | None) -> datetime:
    value = datetime.now(timezone.utc) if value is None else value
    if value.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _watch_path(plan: SchedulerPlan, path: Path, name: str) -> Path:
    output = plan.output_dir.resolve()
    path = Path(path).resolve()
    if path == output or output not in path.parents:
        raise ValueError(f"{name} must remain inside scheduler output")
    if path.is_symlink():
        raise ValueError(f"{name} must not be a symlink")
    return path


def _status_fingerprint(status: Mapping[str, object]) -> str:
    stable = dict(status)
    stable.pop("observed_at_msk", None)
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        raise ValueError(f"stale watcher temporary file exists: {temporary}")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
