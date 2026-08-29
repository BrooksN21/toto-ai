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


def run_final_hybrid_sidecar(
    *,
    scheduler_plan_path: str | Path,
    sports_artifact_path: str | Path,
    output_root: str | Path,
    wait_seconds: int = 600,
    minimum_runtime_seconds: int = 240,
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
                )
            if operator.get("decision") == "NO BET":
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
    )
    operator_coupons = _parse_operator_package(operator_export, plan.stake)
    baseline_coupons = _parse_research_package(paths.baseline_package)
    if operator_coupons != baseline_coupons:
        raise ValueError("recomputed BK control differs from operator package")
    completed_at = datetime.now(timezone.utc)
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
        "baseline_matches_operator": True,
        "sports_coverage_count": report["sports_coverage_count"],
        "sports_fallback_count": report["sports_fallback_count"],
        "automatic_wagering": False,
        "sports_operator_compatible": False,
        "profitability_proven": False,
    }
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    _write_replace(output / "sidecar-result.json", _canonical(payload) + b"\n")
    _write_replace(status_path, _canonical(payload) + b"\n")
    return FinalHybridSidecarResult(
        status="READY_BEFORE_T10",
        result_path=status_path,
        output_dir=output,
        reason=None,
    )


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
