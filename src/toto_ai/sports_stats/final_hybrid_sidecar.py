"""Fail-safe launcher for the final GOAL sports research comparison."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from toto_ai.optimizer.parallel_challenger import POLICY_VERSION
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import export_operator_package, load_scheduler_plan
from toto_ai.sports_stats.final_hybrid_comparison import (
    execute_final_hybrid_comparison,
)


@dataclass(frozen=True)
class FinalHybridSidecarResult:
    status: str
    result_path: Path
    output_dir: Path | None
    reason: str | None


PARALLEL_AUTHORIZATION_FILENAME = "parallel-release-authorization.json"


def authorize_parallel_manual_release(
    *,
    scheduler_plan_path: str | Path,
    output_root: str | Path,
    acknowledged: bool,
    now: datetime | None = None,
) -> Path:
    """Authorize the exact plan-bound selector, never automatic wagering."""

    if acknowledged is not True:
        raise ValueError("explicit parallel experimental-risk acknowledgement required")
    plan = load_scheduler_plan(_regular_file(scheduler_plan_path, "scheduler plan"))
    observed_at = _utc(datetime.now(timezone.utc) if now is None else now)
    if observed_at >= plan.publish_deadline:
        raise ValueError("parallel release cannot be authorized at or after T-10")
    root = Path(output_root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("output root must be a regular directory")
    path = root / PARALLEL_AUTHORIZATION_FILENAME
    if path.exists():
        _validate_parallel_authorization(plan, path)
        return path
    payload = {
        "schema_version": 1,
        "authorization_mode": "EXPERIMENTAL_PARALLEL_MANUAL",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "requested_bank": plan.requested_bank,
        "stake": plan.stake,
        "expires_at": _timestamp(plan.publish_deadline),
        "selection_policy_version": POLICY_VERSION,
        "candidate_strategies": [
            "quality-v2",
            "sports-shadow",
            "quality-v3",
            "robust",
        ],
        "risk_acknowledged": True,
        "profitability_proven": False,
        "automatic_wagering": False,
        "authorized_at": _timestamp(observed_at),
    }
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(path, _canonical(payload) + b"\n")
    _validate_parallel_authorization(plan, path)
    return path


def run_final_hybrid_sidecar(
    *,
    scheduler_plan_path: str | Path,
    sports_artifact_path: str | Path,
    output_root: str | Path,
    wait_seconds: int = 600,
    minimum_runtime_seconds: int = 240,
    parallel_authorization_path: str | Path | None = None,
    poll_seconds: float = 5.0,
    now: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> FinalHybridSidecarResult:
    """Wait for scheduler PLAY, then compute the isolated research pair."""

    if wait_seconds < 0 or minimum_runtime_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("sidecar timing values are invalid")
    clock = now or (lambda: datetime.now(timezone.utc))
    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    sports_path = _regular_file(sports_artifact_path, "sports artifact")
    plan = load_scheduler_plan(plan_path)
    authorization_path = (
        None
        if parallel_authorization_path is None
        else _regular_file(
            parallel_authorization_path,
            "parallel release authorization",
        )
    )
    if authorization_path is not None:
        _validate_parallel_authorization(plan, authorization_path)
    root = Path(output_root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("output root must be a regular directory")
    status_path = root / "sidecar-status.json"
    started_at = _utc(clock())
    latest_start = plan.publish_deadline - timedelta(
        seconds=minimum_runtime_seconds
    )
    stop_waiting = min(started_at + timedelta(seconds=wait_seconds), latest_start)

    while True:
        observed_at = _utc(clock())
        operator_path = plan.output_dir / "operator-result.json"
        operator = _load_operator_result(operator_path)
        if operator is not None:
            if (
                operator.get("plan_id") == plan.plan_id
                and operator.get("drawing") == plan.drawing
                and operator.get("drawing_id") == plan.drawing_id
                and operator.get("decision") == "PLAY"
                and operator.get("actionable") is True
            ):
                if observed_at >= latest_start:
                    return _terminal(
                        status_path,
                        status="SKIPPED_INSUFFICIENT_RUNTIME",
                        started_at=started_at,
                        observed_at=observed_at,
                        reason="operator package arrived after sidecar safe start",
                    )
                return _execute(
                    plan=plan,
                    plan_path=plan_path,
                    sports_path=sports_path,
                    output_root=root,
                    operator=operator,
                    status_path=status_path,
                    started_at=started_at,
                    observed_at=observed_at,
                    parallel_authorization_path=authorization_path,
                    clock=clock,
                )
            if _is_pre_final_checkpoint(operator):
                # Warmup/refresh deliberately publish a non-actionable LKG
                # record before atomic final starts.  It is not a terminal
                # operator decision, so the sidecar must keep polling for the
                # final PLAY/NO BET publication instead of racing the main
                # scheduler and exiting early.
                pass
            elif operator.get("decision") == "NO BET":
                if observed_at < latest_start:
                    final_input = _latest_final_input(plan)
                    if final_input is not None:
                        return _execute_no_bet_research(
                            plan=plan,
                            plan_path=plan_path,
                            sports_path=sports_path,
                            output_root=root,
                            final_input=final_input,
                            status_path=status_path,
                            started_at=started_at,
                            observed_at=observed_at,
                            operator_reason=str(
                                operator.get("reason") or "operator returned NO BET"
                            ),
                        )
                return _terminal(
                    status_path,
                    status="SKIPPED_OPERATOR_NO_BET",
                    started_at=started_at,
                    observed_at=observed_at,
                    reason=str(operator.get("reason") or "operator returned NO BET"),
                )
        if observed_at >= stop_waiting:
            return _terminal(
                status_path,
                status="SKIPPED_OPERATOR_NOT_READY",
                started_at=started_at,
                observed_at=observed_at,
                reason="operator PLAY was not ready before sidecar safe start",
            )
        sleeper(
            min(
                poll_seconds,
                max(0.1, (stop_waiting - observed_at).total_seconds()),
            )
        )


def _is_pre_final_checkpoint(operator: Mapping[str, Any]) -> bool:
    return (
        operator.get("decision") == "NO BET"
        and operator.get("actionable") is False
        and operator.get("operator_status") == "LAST_KNOWN_GOOD_DEGRADED"
        and operator.get("provenance") == "PRE_FINAL_CHECKPOINT"
    )


def _execute(
    *,
    plan: Any,
    plan_path: Path,
    sports_path: Path,
    output_root: Path,
    operator: Mapping[str, Any],
    status_path: Path,
    started_at: datetime,
    observed_at: datetime,
    parallel_authorization_path: Path | None,
    clock: Callable[[], datetime],
) -> FinalHybridSidecarResult:
    run_id = _text(operator.get("run_id"), "operator run_id")
    source_path = _regular_file(
        _text(operator.get("source_package_path"), "operator source package"),
        "operator source package",
    )
    final_input = _regular_file(source_path.parent / "final-input.json", "final input")
    output = output_root / f"run-{run_id}"
    output.mkdir(parents=True, exist_ok=True)
    operator_export = output / "operator-bk-package.txt"
    if operator_export.exists():
        raise ValueError("sidecar operator export already exists")
    export_operator_package(
        plan,
        destination=operator_export,
        observed_at=observed_at,
    )
    report, paths = execute_final_hybrid_comparison(
        final_input_path=final_input,
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_dir=output / "research-comparison",
        deadline=_comparison_deadline(plan.publish_deadline, observed_at),
    )
    operator_coupons = _parse_operator_package(operator_export, plan.stake)
    baseline_coupons = _parse_research_package(paths.baseline_package)
    quality_v3_package = getattr(
        paths,
        "quality_v3_package",
        paths.uncertainty_package,
    )
    if operator_coupons != baseline_coupons:
        raise ValueError("recomputed BK control differs from operator package")
    completed_at = _utc(clock())
    parallel_release = None
    if parallel_authorization_path is not None:
        parallel_release = _publish_parallel_selection(
            plan=plan,
            report=report,
            paths=paths,
            operator_export=operator_export,
            output=output,
            authorization_path=parallel_authorization_path,
            observed_at=completed_at,
        )
    payload = {
        "schema_version": 1,
        "status": "READY_BEFORE_T10",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": run_id,
        "started_at": _timestamp(started_at),
        "operator_observed_at": _timestamp(observed_at),
        "completed_at": _timestamp(completed_at),
        "expires_at": _timestamp(plan.publish_deadline),
        "operator_package": str(operator_export),
        "operator_package_sha256": _sha256(operator_export),
        "research_report": str(paths.report),
        "research_report_sha256": _sha256(paths.report),
        "sports_research_package": str(paths.sports_package),
        "sports_research_package_sha256": _sha256(paths.sports_package),
        "robust_research_package": str(paths.robust_package),
        "robust_research_package_sha256": _sha256(paths.robust_package),
        "quality_v3_research_package": str(quality_v3_package),
        "quality_v3_research_package_sha256": _sha256(quality_v3_package),
        "uncertainty_research_package": str(paths.uncertainty_package),
        "uncertainty_research_package_sha256": _sha256(
            paths.uncertainty_package
        ),
        "baseline_matches_operator": True,
        "sports_coverage_count": report["sports_coverage_count"],
        "sports_fallback_count": report["sports_fallback_count"],
        "automatic_wagering": False,
        "sports_operator_compatible": False,
        "profitability_proven": False,
        "parallel_release": parallel_release,
    }
    result_status = (
        "READY_PARALLEL_PLAY_BEFORE_T10"
        if parallel_release is not None
        else "READY_BEFORE_T10"
    )
    payload["status"] = result_status
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(output / "sidecar-result.json", _canonical(payload) + b"\n")
    _write_replace(status_path, _canonical(payload) + b"\n")
    return FinalHybridSidecarResult(
        status=result_status,
        result_path=status_path,
        output_dir=output,
        reason=None,
    )


def _execute_no_bet_research(
    *,
    plan: Any,
    plan_path: Path,
    sports_path: Path,
    output_root: Path,
    final_input: Path,
    status_path: Path,
    started_at: datetime,
    observed_at: datetime,
    operator_reason: str,
) -> FinalHybridSidecarResult:
    run_id = final_input.parent.name
    output = output_root / f"run-{run_id}"
    output.mkdir(parents=True, exist_ok=True)
    report, paths = execute_final_hybrid_comparison(
        final_input_path=final_input,
        scheduler_plan_path=plan_path,
        sports_artifact_path=sports_path,
        output_dir=output / "research-comparison",
        deadline=_comparison_deadline(plan.publish_deadline, observed_at),
    )
    completed_at = datetime.now(timezone.utc)
    quality_v3_package = getattr(
        paths,
        "quality_v3_package",
        paths.uncertainty_package,
    )
    payload = {
        "schema_version": 1,
        "status": "READY_RESEARCH_ONLY_NO_BET",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": run_id,
        "started_at": _timestamp(started_at),
        "operator_observed_at": _timestamp(observed_at),
        "completed_at": _timestamp(completed_at),
        "operator_reason": operator_reason,
        "final_input": str(final_input),
        "final_input_sha256": _sha256(final_input),
        "research_report": str(paths.report),
        "research_report_sha256": _sha256(paths.report),
        "baseline_research_package": str(paths.baseline_package),
        "baseline_research_package_sha256": _sha256(paths.baseline_package),
        "sports_research_package": str(paths.sports_package),
        "sports_research_package_sha256": _sha256(paths.sports_package),
        "robust_research_package": str(paths.robust_package),
        "robust_research_package_sha256": _sha256(paths.robust_package),
        "quality_v3_research_package": str(quality_v3_package),
        "quality_v3_research_package_sha256": _sha256(quality_v3_package),
        "uncertainty_research_package": str(paths.uncertainty_package),
        "uncertainty_research_package_sha256": _sha256(
            paths.uncertainty_package
        ),
        "sports_coverage_count": report["sports_coverage_count"],
        "sports_fallback_count": report["sports_fallback_count"],
        "automatic_wagering": False,
        "operator_compatible": False,
        "profitability_proven": False,
    }
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(output / "sidecar-result.json", _canonical(payload) + b"\n")
    _write_replace(status_path, _canonical(payload) + b"\n")
    return FinalHybridSidecarResult(
        status="READY_RESEARCH_ONLY_NO_BET",
        result_path=status_path,
        output_dir=output,
        reason=operator_reason,
    )


def _publish_parallel_selection(
    *,
    plan: Any,
    report: Mapping[str, Any],
    paths: Any,
    operator_export: Path,
    output: Path,
    authorization_path: Path,
    observed_at: datetime,
) -> dict[str, Any]:
    authorization = _validate_parallel_authorization(plan, authorization_path)
    completed_at = _utc(observed_at)
    if completed_at >= plan.publish_deadline:
        raise ValueError("parallel selection completed at or after T-10")
    selection = report.get("experimental_selection")
    if not isinstance(selection, Mapping):
        raise ValueError("parallel comparison has no selection record")
    if selection.get("policy_version") != POLICY_VERSION:
        raise ValueError("parallel selection policy mismatch")
    selected_id = _text(
        selection.get("selected_strategy_id"),
        "selected parallel strategy",
    )
    selected_hash = _text(
        selection.get("selected_package_sha256"),
        "selected parallel package hash",
    )
    candidates = selection.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("parallel selection candidates are invalid")
    selected_candidate = next(
        (
            row
            for row in candidates
            if isinstance(row, Mapping) and row.get("strategy_id") == selected_id
        ),
        None,
    )
    if selected_candidate is None or selected_candidate.get("eligible") is not True:
        raise ValueError("selected parallel candidate is not eligible")
    package_paths = {
        "quality-v2": operator_export,
        "sports-shadow": paths.sports_package,
        "quality-v3": getattr(
            paths,
            "quality_v3_package",
            paths.uncertainty_package,
        ),
        "robust": paths.robust_package,
    }
    if selected_id not in package_paths:
        raise ValueError("selected parallel strategy is unsupported")
    if selected_id == "quality-v2":
        coupons = _parse_operator_package(package_paths[selected_id], plan.stake)
    else:
        coupons = _parse_research_package(package_paths[selected_id])
    canonical_hash = hashlib.sha256(
        ",".join(coupons).encode("utf-8")
    ).hexdigest()
    expected_count = selected_candidate.get("coupon_count")
    expected_cost = selected_candidate.get("cost")
    if (
        canonical_hash != selected_hash
        or len(coupons) != expected_count
        or len(coupons) * plan.stake != expected_cost
        or len(coupons) * plan.stake > plan.requested_bank
    ):
        raise ValueError("selected parallel package binding mismatch")

    package_path = output / "selected-parallel-operator-package.txt"
    _write_replace(package_path, _operator_package_bytes(plan.stake, coupons))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "READY_PARALLEL_PLAY_BEFORE_T10",
        "decision": "PLAY",
        "actionable": True,
        "authorization_mode": "EXPERIMENTAL_PARALLEL_MANUAL",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "selected_strategy_id": selected_id,
        "selected_package_sha256": selected_hash,
        "selected_coupon_count": len(coupons),
        "selected_cost": len(coupons) * plan.stake,
        "selected_package_path": str(package_path),
        "selected_package_file_sha256": _sha256(package_path),
        "selection_policy_version": POLICY_VERSION,
        "selection_reason": selection.get("selection_reason"),
        "selection_promoted": selection.get("promoted"),
        "authorization_path": str(authorization_path),
        "authorization_sha256": authorization["record_sha256"],
        "published_at": _timestamp(completed_at),
        "expires_at": _timestamp(plan.publish_deadline),
        "risk_acknowledged": True,
        "profitability_proven": False,
        "automatic_wagering": False,
    }
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(
        output / "parallel-operator-result.json",
        _canonical(payload) + b"\n",
    )
    return payload


def _validate_parallel_authorization(
    plan: Any,
    path: Path,
) -> Mapping[str, Any]:
    regular = _regular_file(path, "parallel release authorization")
    try:
        payload = json.loads(regular.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("parallel release authorization is invalid") from error
    if not isinstance(payload, Mapping):
        raise ValueError("parallel release authorization must be an object")
    expected = {
        "schema_version": 1,
        "authorization_mode": "EXPERIMENTAL_PARALLEL_MANUAL",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "requested_bank": plan.requested_bank,
        "stake": plan.stake,
        "expires_at": _timestamp(plan.publish_deadline),
        "selection_policy_version": POLICY_VERSION,
        "candidate_strategies": [
            "quality-v2",
            "sports-shadow",
            "quality-v3",
            "robust",
        ],
        "risk_acknowledged": True,
        "profitability_proven": False,
        "automatic_wagering": False,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("parallel release authorization does not match plan")
    unsigned = dict(payload)
    declared = unsigned.pop("record_sha256", None)
    if declared != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError("parallel release authorization hash mismatch")
    authorized_at = _utc(
        datetime.fromisoformat(
            _text(payload.get("authorized_at"), "parallel authorized_at").replace(
                "Z",
                "+00:00",
            )
        )
    )
    if authorized_at >= plan.publish_deadline:
        raise ValueError("parallel release authorization is not pre-T-10")
    return payload


def _operator_package_bytes(stake: int, coupons: tuple[str, ...]) -> bytes:
    return (
        "\n".join(f"{stake};" + ";".join(coupon) for coupon in coupons) + "\n"
    ).encode("utf-8")


def _latest_final_input(plan: Any) -> Path | None:
    candidates = []
    attempts = plan.output_dir / "attempts"
    if not attempts.is_dir() or attempts.is_symlink():
        return None
    for path in attempts.glob("final-*/final-input.json"):
        try:
            regular = _regular_file(path, "final input")
            snapshot = load_final_input(regular, expected_plan=plan)
        except (OSError, TypeError, ValueError):
            continue
        candidates.append((snapshot.captured_at, regular))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], str(item[1])))
    return candidates[-1][1]


def _comparison_deadline(
    publish_deadline: datetime,
    observed_at: datetime,
) -> float:
    remaining = max(
        0.0,
        (_utc(publish_deadline) - _utc(observed_at)).total_seconds() - 5.0,
    )
    return time.perf_counter() + remaining


def _terminal(
    path: Path,
    *,
    status: str,
    started_at: datetime,
    observed_at: datetime,
    reason: str,
) -> FinalHybridSidecarResult:
    payload = {
        "schema_version": 1,
        "status": status,
        "started_at": _timestamp(started_at),
        "observed_at": _timestamp(observed_at),
        "reason": reason,
        "automatic_wagering": False,
    }
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(path, _canonical(payload) + b"\n")
    return FinalHybridSidecarResult(
        status=status,
        result_path=path,
        output_dir=None,
        reason=reason,
    )


def _load_operator_result(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    regular = _regular_file(path, "operator result")
    try:
        value = json.loads(regular.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("operator result is invalid") from error
    if not isinstance(value, Mapping):
        raise ValueError("operator result must be an object")
    return value


def _parse_operator_package(path: Path, stake: int) -> tuple[str, ...]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        values = [value.strip() for value in raw.split(";")]
        if len(values) != 16 or int(values[0]) != stake:
            raise ValueError("operator package row is invalid")
        coupon = "".join(values[1:])
        if len(coupon) != 15 or set(coupon) - set("1X2"):
            raise ValueError("operator coupon is invalid")
        rows.append(coupon)
    if not rows or len(set(rows)) != len(rows):
        raise ValueError("operator package coupons are invalid")
    return tuple(rows)


def _parse_research_package(path: Path) -> tuple[str, ...]:
    rows = tuple(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if len(line) == 15 and not (set(line) - set("1X2"))
    )
    if not rows or len(set(rows)) != len(rows):
        raise ValueError("research package coupons are invalid")
    return rows


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} is invalid")
    return value


def _regular_file(value: str | Path, name: str) -> Path:
    path = Path(value).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be a regular non-symlink file")
    return path


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _write_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("sidecar output path cannot traverse a symlink")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
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
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
