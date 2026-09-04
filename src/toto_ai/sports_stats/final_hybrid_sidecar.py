"""Fail-safe launcher for the final GOAL sports research comparison."""

from __future__ import annotations

import hashlib
import json
import math
import os
import plistlib
import re
import secrets
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
PARALLEL_SIDECAR_WRAPPER_FILENAME = "run-parallel-sidecar.sh"
PARALLEL_SIDECAR_LAUNCH_AGENT_FILENAME = "totoai-parallel-sidecar.plist"
_PARALLEL_SIDECAR_LABEL = re.compile(
    r"com\.totoai\.parallel-sidecar\.v1\.[0-9a-f]{16}\Z"
)
_MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class ParallelSidecarArtifacts:
    root: Path
    project_root: Path
    python_path: Path
    wrapper_path: Path
    launch_agent_path: Path
    launch_agent_label: str
    sports_artifact_path: Path
    authorization_path: Path | None
    scheduled_at: datetime
    reused: bool


@dataclass(frozen=True)
class ParallelSidecarRetryResult:
    status: str
    operator_result_sha256: str | None
    marker_path: Path | None


def prepare_parallel_sidecar_artifacts(
    *,
    scheduler_plan_path: str | Path,
    sports_artifact_path: str | Path,
    python_command: str | Path,
    parallel_authorization_path: str | Path | None = None,
) -> ParallelSidecarArtifacts:
    """Create one immutable, non-blocking T-30 sidecar for an exact plan."""

    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    sports_path = _regular_file(sports_artifact_path, "sports artifact")
    plan = load_scheduler_plan(plan_path)
    if not sports_path.is_relative_to(plan.project_root):
        raise ValueError("sports artifact must remain inside project_root")
    root = plan.output_dir / "parallel-challenger"
    discovered_authorization = root / PARALLEL_AUTHORIZATION_FILENAME
    if parallel_authorization_path is None:
        authorization_path = (
            _regular_file(
                discovered_authorization,
                "parallel release authorization",
            )
            if (
                discovered_authorization.exists()
                or discovered_authorization.is_symlink()
            )
            else None
        )
    else:
        authorization_path = _regular_file(
            parallel_authorization_path,
            "parallel release authorization",
        )
    if authorization_path is not None:
        _validate_parallel_authorization(plan, authorization_path)
    executable = _parallel_sidecar_python(
        project_root=plan.project_root,
        requested=python_command,
    )

    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("parallel sidecar root must be a regular directory")
    wrapper_path = root / PARALLEL_SIDECAR_WRAPPER_FILENAME
    launch_agent_path = root / PARALLEL_SIDECAR_LAUNCH_AGENT_FILENAME
    if wrapper_path.exists() != launch_agent_path.exists():
        raise ValueError("parallel sidecar artifact set is incomplete")
    reused = wrapper_path.exists()
    accepted_existing_wrappers: tuple[bytes, ...] = ()
    if reused:
        existing_executable, sports_path = _existing_parallel_wrapper_binding(
            wrapper_path=wrapper_path,
            plan=plan,
            plan_path=plan_path,
            root=root,
            authorization_path=authorization_path,
        )
        if existing_executable == executable:
            executable = existing_executable
        else:
            # A dispatcher launched outside the project virtualenv used to
            # freeze its system Python into this immutable wrapper.  The
            # existing bytes are accepted only after the complete plan/input
            # binding above has been validated, and only to migrate to the
            # canonical project virtualenv selected by
            # ``_parallel_sidecar_python``.
            accepted_existing_wrappers = (wrapper_path.read_bytes(),)
    label = f"com.totoai.parallel-sidecar.v1.{plan.plan_id}"
    if not _PARALLEL_SIDECAR_LABEL.fullmatch(label):
        raise ValueError("parallel sidecar label is invalid")
    scheduled_at = plan.operational_cutoff - timedelta(minutes=30)
    command = [
        str(executable),
        "-m",
        "toto_ai.cli",
        "run-final-goal-hybrid-sidecar",
        "--scheduler-plan",
        str(plan_path),
        "--sports-artifact",
        str(sports_path),
        "--output-root",
        str(root / "output"),
        "--wait-seconds",
        "900",
        "--minimum-runtime-seconds",
        "240",
    ]
    wrapper = (
        "#!/bin/zsh\n"
        "set -eu\n"
        f"cd {shlex.quote(str(plan.project_root))}\n"
        f"exec {shlex.join(command)}\n"
    ).encode()
    if authorization_path is not None:
        legacy_command = [
            *command,
            "--parallel-authorization",
            str(authorization_path),
        ]
        accepted_existing_wrappers = (
            *accepted_existing_wrappers,
            (
                "#!/bin/zsh\n"
                "set -eu\n"
                f"cd {shlex.quote(str(plan.project_root))}\n"
                f"exec {shlex.join(legacy_command)}\n"
            ).encode(),
        )
    local = scheduled_at.astimezone(_MOSCOW)
    plist = plistlib.dumps(
        {
            "Label": label,
            "ProcessType": "Background",
            "ProgramArguments": [str(wrapper_path)],
            "StandardErrorPath": str(root / "parallel-sidecar.stderr.log"),
            "StandardOutPath": str(root / "parallel-sidecar.stdout.log"),
            "StartCalendarInterval": {
                "Year": local.year,
                "Month": local.month,
                "Day": local.day,
                "Hour": local.hour,
                "Minute": local.minute,
            },
            "WorkingDirectory": str(plan.project_root),
        },
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )
    _write_expected(
        wrapper_path,
        wrapper,
        mode=0o700,
        accepted_existing=accepted_existing_wrappers,
    )
    _write_expected(launch_agent_path, plist, mode=0o600)
    return ParallelSidecarArtifacts(
        root=root,
        project_root=plan.project_root,
        python_path=executable,
        wrapper_path=wrapper_path,
        launch_agent_path=launch_agent_path,
        launch_agent_label=label,
        sports_artifact_path=sports_path,
        authorization_path=authorization_path,
        scheduled_at=scheduled_at,
        reused=reused,
    )


def activate_parallel_sidecar_launch_agent(
    artifacts: ParallelSidecarArtifacts,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> None:
    """Install one verified sidecar without touching the primary scheduler."""

    if not isinstance(artifacts, ParallelSidecarArtifacts):
        raise ValueError("parallel sidecar artifacts are invalid")
    if not _PARALLEL_SIDECAR_LABEL.fullmatch(artifacts.launch_agent_label):
        raise ValueError("parallel sidecar label is invalid")
    candidate = _regular_file(
        artifacts.launch_agent_path,
        "parallel sidecar LaunchAgent",
    )
    try:
        payload = plistlib.loads(candidate.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise ValueError("parallel sidecar LaunchAgent is invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("Label") != artifacts.launch_agent_label
        or payload.get("ProgramArguments") != [str(artifacts.wrapper_path)]
    ):
        raise ValueError("parallel sidecar LaunchAgent binding mismatch")
    _regular_file(artifacts.wrapper_path, "parallel sidecar wrapper")
    smoke = command_runner(
        (
            str(artifacts.python_path),
            "-c",
            "import toto_ai; import toto_ai.cli",
        ),
        cwd=str(artifacts.project_root),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(smoke, "returncode", None) != 0:
        detail = str(getattr(smoke, "stderr", "")).strip()
        raise ValueError(
            "parallel sidecar Python import smoke failed"
            + (f": {detail[-500:]}" if detail else "")
        )
    root = (
        Path.home() / "Library" / "LaunchAgents"
        if launch_agents_root is None
        else Path(launch_agents_root)
    ).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("LaunchAgents root cannot be a symlink")
    destination = root / f"{artifacts.launch_agent_label}.plist"
    _write_expected(destination, candidate.read_bytes(), mode=0o600)
    domain = f"gui/{os.getuid()}"
    completed = command_runner(
        ("launchctl", "bootstrap", domain, str(destination)),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(completed, "returncode", None) == 0:
        return
    inspected = command_runner(
        (
            "launchctl",
            "print",
            f"{domain}/{artifacts.launch_agent_label}",
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(inspected, "returncode", None) != 0:
        detail = str(getattr(completed, "stderr", "")).strip()
        raise ValueError(
            "parallel sidecar LaunchAgent bootstrap failed"
            + (f": {detail[-500:]}" if detail else "")
        )


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
    root = Path(output_root).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("output root must be a regular directory")
    authorization_path = (
        None
        if parallel_authorization_path is None
        else _regular_file(
            parallel_authorization_path,
            "parallel release authorization",
        )
    )
    if authorization_path is None:
        candidate = root.parent / PARALLEL_AUTHORIZATION_FILENAME
        if candidate.is_file() and not candidate.is_symlink():
            authorization_path = candidate
    if authorization_path is not None:
        _validate_parallel_authorization(plan, authorization_path)
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
                        plan=plan,
                        plan_path=plan_path,
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
                    plan=plan,
                    plan_path=plan_path,
                    status="SKIPPED_OPERATOR_NO_BET",
                    started_at=started_at,
                    observed_at=observed_at,
                    reason=str(operator.get("reason") or "operator returned NO BET"),
                )
        if observed_at >= stop_waiting:
            return _terminal(
                status_path,
                plan=plan,
                plan_path=plan_path,
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


def retry_parallel_sidecar_after_operator_publication(
    *,
    plan: Any,
    scheduler_plan_path: str | Path,
    observed_at: datetime,
    process_launcher: Callable[..., object] = subprocess.Popen,
) -> ParallelSidecarRetryResult:
    """Start one detached retry for one exact newly-ready operator record."""

    observed = _utc(observed_at)
    if observed >= _utc(plan.publish_deadline):
        return ParallelSidecarRetryResult(
            status="SKIPPED_POST_CUTOFF",
            operator_result_sha256=None,
            marker_path=None,
        )

    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    output_dir = Path(plan.output_dir).absolute()
    if plan_path != output_dir / "scheduler-plan.json":
        return _retry_identity_mismatch()
    plan_sha256 = _sha256(plan_path)
    sidecar_root = output_dir / "parallel-challenger"
    status_path = sidecar_root / "output" / "sidecar-status.json"
    wrapper_path = sidecar_root / PARALLEL_SIDECAR_WRAPPER_FILENAME
    operator_path = output_dir / "operator-result.json"

    try:
        sidecar = _load_retry_sidecar_status(status_path)
        operator = _load_retry_operator_result(operator_path)
    except (OSError, TypeError, ValueError):
        return _retry_identity_mismatch()
    expected_identity = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
    }
    if (
        any(sidecar.get(key) != value for key, value in expected_identity.items())
        or sidecar.get("scheduler_plan_sha256") != plan_sha256
        or any(operator.get(key) != value for key, value in expected_identity.items())
        or operator.get("decision") != "PLAY"
        or operator.get("actionable") is not True
        or operator.get("automatic_wagering") is not False
        or _parse_retry_timestamp(operator.get("expires_at"))
        != _utc(plan.publish_deadline)
    ):
        return _retry_identity_mismatch()

    try:
        wrapper = _regular_file(wrapper_path, "parallel sidecar wrapper")
    except ValueError:
        return _retry_identity_mismatch()
    operator_sha256 = str(operator["record_sha256"])
    marker_path = sidecar_root / "parallel-sidecar-retry.json"
    marker = {
        "schema_version": 1,
        "status": "STARTED",
        **expected_identity,
        "scheduler_plan_sha256": plan_sha256,
        "sidecar_status_sha256": sidecar["record_sha256"],
        "operator_result_sha256": operator_sha256,
        "requested_at": _timestamp(observed),
        "automatic_wagering": False,
    }
    marker["record_sha256"] = hashlib.sha256(_canonical(marker)).hexdigest()
    marker_bytes = _canonical(marker) + b"\n"
    try:
        _write_exclusive_retry_marker(marker_path, marker_bytes)
    except FileExistsError:
        try:
            existing = _load_retry_marker(marker_path)
        except (OSError, TypeError, ValueError):
            return _retry_identity_mismatch()
        if (
            any(existing.get(key) != value for key, value in expected_identity.items())
            or existing.get("scheduler_plan_sha256") != plan_sha256
            or existing.get("sidecar_status_sha256") != sidecar["record_sha256"]
            or existing.get("operator_result_sha256") != operator_sha256
        ):
            return _retry_identity_mismatch()
        return ParallelSidecarRetryResult(
            status="ALREADY_STARTED",
            operator_result_sha256=operator_sha256,
            marker_path=marker_path,
        )

    process_launcher(
        [str(wrapper)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return ParallelSidecarRetryResult(
        status="STARTED",
        operator_result_sha256=operator_sha256,
        marker_path=marker_path,
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
    ranking = _selected_coupon_ranking(
        report=report,
        selected_id=selected_id,
        coupons=coupons,
    )

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
        "coupon_order_semantics": "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK",
        "highest_p13_single_coupon": ranking,
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


def _selected_coupon_ranking(
    *,
    report: Mapping[str, Any],
    selected_id: str,
    coupons: tuple[str, ...],
) -> Mapping[str, Any]:
    rankings = report.get("highest_p13_single_coupons")
    if not isinstance(rankings, Mapping):
        raise ValueError("parallel comparison has no coupon probability ranking")
    ranking = rankings.get(selected_id)
    if not isinstance(ranking, Mapping):
        raise ValueError("selected parallel package has no coupon probability ranking")
    position = ranking.get("package_position")
    coupon = ranking.get("coupon")
    if (
        type(position) is not int
        or not 1 <= position <= len(coupons)
        or not isinstance(coupon, str)
        or coupons[position - 1] != coupon
        or ranking.get("criterion") != "maximum_probability_at_least_13"
        or ranking.get("package_order_semantics")
        != "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK"
    ):
        raise ValueError("selected coupon probability ranking is not package-bound")
    for key in (
        "probability_at_least_13",
        "probability_at_least_14",
        "probability_at_least_15",
    ):
        value = ranking.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError("selected coupon probability ranking is invalid")
    reference_model = ranking.get("reference_model")
    if not isinstance(reference_model, str) or not reference_model:
        raise ValueError("selected coupon probability model is invalid")
    return dict(ranking)


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
    plan: Any,
    plan_path: Path,
    status: str,
    started_at: datetime,
    observed_at: datetime,
    reason: str,
) -> FinalHybridSidecarResult:
    payload = {
        "schema_version": 2,
        "status": status,
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "scheduler_plan_sha256": _sha256(plan_path),
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


def _retry_identity_mismatch() -> ParallelSidecarRetryResult:
    return ParallelSidecarRetryResult(
        status="IDENTITY_MISMATCH",
        operator_result_sha256=None,
        marker_path=None,
    )


def _load_retry_sidecar_status(path: Path) -> Mapping[str, Any]:
    payload = _load_hashed_retry_record(path, "parallel sidecar status")
    if (
        payload.get("schema_version") != 2
        or payload.get("status") != "SKIPPED_OPERATOR_NOT_READY"
        or payload.get("automatic_wagering") is not False
        or not isinstance(payload.get("reason"), str)
        or not payload["reason"].strip()
        or not isinstance(payload.get("scheduler_plan_sha256"), str)
        or len(payload["scheduler_plan_sha256"]) != 64
    ):
        raise ValueError("parallel sidecar status is not retryable")
    started_at = _parse_retry_timestamp(payload.get("started_at"))
    sidecar_observed_at = _parse_retry_timestamp(payload.get("observed_at"))
    if sidecar_observed_at < started_at:
        raise ValueError("parallel sidecar status timing is invalid")
    return payload


def _load_retry_operator_result(path: Path) -> Mapping[str, Any]:
    payload = _load_hashed_retry_record(path, "operator result")
    if payload.get("schema_version") != 3:
        raise ValueError("operator result schema is invalid")
    return payload


def _load_retry_marker(path: Path) -> Mapping[str, Any]:
    payload = _load_hashed_retry_record(path, "parallel sidecar retry marker")
    if (
        payload.get("schema_version") != 1
        or payload.get("status") != "STARTED"
        or payload.get("automatic_wagering") is not False
    ):
        raise ValueError("parallel sidecar retry marker is invalid")
    _parse_retry_timestamp(payload.get("requested_at"))
    return payload


def _load_hashed_retry_record(path: Path, name: str) -> Mapping[str, Any]:
    regular = _regular_file(path, name)
    try:
        payload = json.loads(regular.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is invalid") from error
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be an object")
    unsigned = dict(payload)
    declared = unsigned.pop("record_sha256", None)
    if declared != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError(f"{name} hash mismatch")
    return payload


def _parse_retry_timestamp(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            _text(value, "retry timestamp").replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError("retry timestamp is invalid") from error
    return _utc(parsed)


def _write_exclusive_retry_marker(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("parallel sidecar retry marker path is invalid")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


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


def _parallel_sidecar_python(
    *,
    project_root: Path,
    requested: str | Path,
) -> Path:
    """Bind scheduled project work to its virtualenv when one is available."""

    project_python = project_root / ".venv" / "bin" / "python"
    executable = (
        project_python.absolute()
        if project_python.exists() or project_python.is_symlink()
        else Path(requested).absolute()
    )
    try:
        executable_target = executable.resolve(strict=True)
    except OSError as error:
        raise ValueError("python command must resolve to an existing file") from error
    if not executable_target.is_file():
        raise ValueError("python command must resolve to a regular file")
    return executable


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


def _existing_parallel_wrapper_binding(
    *,
    wrapper_path: Path,
    plan: object,
    plan_path: Path,
    root: Path,
    authorization_path: Path | None,
) -> tuple[Path, Path]:
    """Validate and reuse the immutable input already bound to one plan."""

    wrapper = _regular_file(wrapper_path, "parallel sidecar wrapper")
    try:
        lines = wrapper.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("parallel sidecar wrapper is invalid") from error
    if (
        len(lines) != 4
        or lines[:2] != ["#!/bin/zsh", "set -eu"]
        or shlex.split(lines[2]) != ["cd", str(plan.project_root)]
        or not lines[3].startswith("exec ")
    ):
        raise ValueError("parallel sidecar wrapper binding mismatch")
    try:
        command = shlex.split(lines[3][len("exec ") :])
    except ValueError as error:
        raise ValueError("parallel sidecar wrapper command is invalid") from error
    if len(command) not in {14, 16} or command[1:4] != [
        "-m",
        "toto_ai.cli",
        "run-final-goal-hybrid-sidecar",
    ]:
        raise ValueError("parallel sidecar wrapper command mismatch")
    option_tokens = command[4:]
    if len(option_tokens) % 2:
        raise ValueError("parallel sidecar wrapper options are invalid")
    options: dict[str, str] = {}
    for name, value in zip(option_tokens[::2], option_tokens[1::2], strict=True):
        if name in options:
            raise ValueError("parallel sidecar wrapper option is duplicated")
        options[name] = value
    required = {
        "--scheduler-plan",
        "--sports-artifact",
        "--output-root",
        "--wait-seconds",
        "--minimum-runtime-seconds",
    }
    allowed = required | {"--parallel-authorization"}
    if set(options) - allowed or not required.issubset(options):
        raise ValueError("parallel sidecar wrapper options mismatch")
    if (
        Path(options["--scheduler-plan"]).absolute() != plan_path
        or Path(options["--output-root"]).absolute() != root / "output"
        or options["--wait-seconds"] != "900"
        or options["--minimum-runtime-seconds"] != "240"
    ):
        raise ValueError("parallel sidecar wrapper plan binding mismatch")
    bound_authorization = options.get("--parallel-authorization")
    if bound_authorization is not None and (
        authorization_path is None
        or Path(bound_authorization).absolute() != authorization_path
    ):
        raise ValueError("parallel sidecar wrapper authorization mismatch")
    executable = Path(command[0]).absolute()
    try:
        executable_target = executable.resolve(strict=True)
    except OSError as error:
        raise ValueError("parallel sidecar wrapper Python is missing") from error
    if not executable_target.is_file():
        raise ValueError("parallel sidecar wrapper Python is invalid")
    sports_path = _regular_file(
        options["--sports-artifact"],
        "parallel sidecar sports artifact",
    )
    if not sports_path.is_relative_to(plan.project_root):
        raise ValueError("parallel sidecar sports artifact binding mismatch")
    return executable, sports_path


def _write_expected(
    path: Path,
    content: bytes,
    *,
    mode: int,
    accepted_existing: tuple[bytes, ...] = (),
) -> None:
    """Create an immutable generated file or verify its exact existing bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("sidecar artifact path cannot traverse a symlink")
    if path.exists():
        if not path.is_file():
            raise ValueError("parallel sidecar artifact conflicts with expected bytes")
        existing = path.read_bytes()
        if existing in accepted_existing:
            _write_replace(path, content)
        elif existing != content:
            raise ValueError("parallel sidecar artifact conflicts with expected bytes")
        path.chmod(mode)
        return
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)
