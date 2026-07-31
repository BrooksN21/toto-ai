"""Drawing-bound launchd scheduler for passive preflight retries only."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import secrets
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.runner.scheduler import (
    _render_secure_env_prelude,
    _require_secure_env_file,
)

_LABEL = re.compile(r"com\.totoai\.preflight-retry\.\d+\.[0-9a-f]{16}\Z")
_FORBIDDEN = ("--activate", "run-drawing", ".bet-ready")


@dataclass(frozen=True)
class PreflightRetryArtifacts:
    label: str
    plan_path: Path
    wrapper_path: Path
    candidate_path: Path


def prepare_preflight_retry_artifacts(
    plan_path: str | Path,
    *,
    write: bool = True,
) -> PreflightRetryArtifacts:
    """Idempotently generate a wrapper and plist from one persisted retry plan."""
    plan_path = Path(plan_path).resolve()
    plan = _load_plan(plan_path)
    identity = plan["identity"]
    label = (
        f"com.totoai.preflight-retry.{identity['drawing_id']}."
        f"{identity['drawing_fingerprint'][:16]}"
    )
    if not _LABEL.fullmatch(label):
        raise ValueError("invalid preflight retry LaunchAgent label")
    root = plan_path.parent / "launchd"
    wrapper = root / "run-preflight-retry"
    candidate = root / f"{label}.plist"
    command = tuple(str(value) for value in plan["attempts"][0]["command"])
    env_file = Path(_option_value(command, "--env-file")).resolve()
    project_root = Path(_option_value(command, "--project-root")).resolve()
    _require_secure_env_file(env_file)
    if not project_root.is_dir() or project_root.is_symlink():
        raise ValueError("preflight retry project root is invalid")
    wrapper_bytes = (
        "#!/bin/sh\nset -eu\numask 077\n"
        + _render_secure_env_prelude(
            env_file=env_file,
            python_executable=command[0],
        )
        + "cd "
        + _quote(str(project_root))
        + "\nexec "
        + _quote(command[0])
        + " -m toto_ai.cli preflight-retry-run --plan "
        + _quote(str(plan_path))
        + "\n"
    ).encode()
    _assert_passive(wrapper_bytes.decode())
    calendars = [
        _calendar(_parse(item["scheduled_at"]).astimezone())
        for item in plan["attempts"]
    ]
    calendars.append(_calendar(_parse(plan["hard_stop"]).astimezone()))
    payload = {
        "Label": label,
        "ProgramArguments": [str(wrapper)],
        "RunAtLoad": False,
        "StartCalendarInterval": calendars,
        "StandardOutPath": str(root / "stdout.log"),
        "StandardErrorPath": str(root / "stderr.log"),
    }
    plist_bytes = plistlib.dumps(payload, sort_keys=True)
    if write:
        root.mkdir(parents=True, exist_ok=True)
        _write_exact(wrapper, wrapper_bytes, 0o700)
        _write_exact(candidate, plist_bytes, 0o600)
    return PreflightRetryArtifacts(label, plan_path, wrapper, candidate)


def install_preflight_retry_launch_agent(
    artifacts: PreflightRetryArtifacts,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> dict[str, object]:
    """Explicitly install exact candidate bytes; repeated calls are harmless."""
    root = (launch_agents_root or Path.home() / "Library/LaunchAgents").resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{artifacts.label}.plist"
    candidate = artifacts.candidate_path.read_bytes()
    _write_exact(destination, candidate, 0o600)
    domain = f"gui/{os.getuid()}"
    probe = _launchctl(
        command_runner, "print", f"{domain}/{artifacts.label}"
    )
    if getattr(probe, "returncode", 1) != 0:
        result = _launchctl(
            command_runner, "bootstrap", domain, str(destination)
        )
        if getattr(result, "returncode", 1) != 0:
            cleanup_preflight_retry_launch_agent(
                artifacts,
                launch_agents_root=root,
                command_runner=command_runner,
            )
            raise ValueError("preflight retry LaunchAgent bootstrap failed")
    status = verify_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=command_runner
    )
    if not status["active"]:
        cleanup_preflight_retry_launch_agent(
            artifacts,
            launch_agents_root=root,
            command_runner=command_runner,
        )
        raise ValueError("preflight retry LaunchAgent did not verify active")
    return status


def cleanup_preflight_retry_launch_agent(
    artifacts: PreflightRetryArtifacts,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> None:
    """Unload and remove only this exact drawing/fingerprint LaunchAgent."""
    root = (launch_agents_root or Path.home() / "Library/LaunchAgents").resolve()
    destination = root / f"{artifacts.label}.plist"
    domain = f"gui/{os.getuid()}"
    probe = _launchctl(
        command_runner, "print", f"{domain}/{artifacts.label}"
    )
    if getattr(probe, "returncode", 1) == 0:
        result = _launchctl(
            command_runner, "bootout", f"{domain}/{artifacts.label}"
        )
        if getattr(result, "returncode", 1) != 0:
            raise ValueError("preflight retry LaunchAgent bootout failed")
        verify = _launchctl(
            command_runner, "print", f"{domain}/{artifacts.label}"
        )
        if getattr(verify, "returncode", 1) == 0:
            raise ValueError("preflight retry LaunchAgent remained loaded")
    if destination.is_symlink():
        raise ValueError("installed preflight retry plist is a symlink")
    destination.unlink(missing_ok=True)


def verify_preflight_retry_launch_agent(
    artifacts: PreflightRetryArtifacts,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
    now: datetime | None = None,
    terminal: bool = False,
) -> dict[str, object]:
    root = (launch_agents_root or Path.home() / "Library/LaunchAgents").resolve()
    installed = root / f"{artifacts.label}.plist"
    installed_verified = (
        artifacts.candidate_path.is_file()
        and installed.is_file()
        and not installed.is_symlink()
        and installed.read_bytes() == artifacts.candidate_path.read_bytes()
    )
    loaded_verified = False
    if installed_verified:
        probe = _launchctl(
            command_runner,
            "print",
            f"gui/{os.getuid()}/{artifacts.label}",
        )
        loaded_verified = getattr(probe, "returncode", 1) == 0
    active = installed_verified and loaded_verified and not terminal
    return {
        "label": artifacts.label,
        "installed_path": str(installed),
        "installed_verified": installed_verified,
        "loaded_verified": loaded_verified,
        "active": active,
        "next_run": (
            None
            if terminal
            else _next_run(
                _load_plan(artifacts.plan_path),
                now or datetime.now(timezone.utc),
            )
        ),
    }


def run_preflight_retry(
    plan_path: str | Path,
    *,
    now: datetime,
    command_runner: Callable[..., object] = subprocess.run,
    launch_agents_root: Path | None = None,
) -> int:
    """Execute the due identity-bound passive attempt and clean terminal jobs."""
    artifacts = prepare_preflight_retry_artifacts(plan_path, write=False)
    plan = _load_plan(artifacts.plan_path)
    observed = _utc(now)
    if observed >= _parse(plan["hard_stop"]):
        cleanup_preflight_retry_launch_agent(
            artifacts,
            launch_agents_root=launch_agents_root,
            command_runner=command_runner,
        )
        return 0
    state_path = artifacts.plan_path.parent / "retry-runtime.json"
    state = _load_runtime_state(state_path, plan["identity"])
    attempt = _due_attempt(plan, observed, state["executed"])
    if attempt is None:
        return 0
    command = tuple(str(value) for value in attempt["command"])
    _verify_command_identity(command, plan["identity"])
    result = command_runner(
        command, check=False, capture_output=True, text=True
    )
    code = int(getattr(result, "returncode", 1))
    scheduled_at = str(attempt["scheduled_at"])
    state["executed"][scheduled_at] = {
        "completed_at": _timestamp(observed),
        "returncode": code,
    }
    _write_runtime_state(state_path, state)
    payload = _result_payload(result)
    terminal = code in {0, 3} or (
        payload.get("status") == "deferred"
        and payload.get("reason")
        in {"drawing_not_playable", "drawing_span_exceeds_five_days", "late_dispatch"}
    )
    if terminal:
        cleanup_preflight_retry_launch_agent(
            artifacts,
            launch_agents_root=launch_agents_root,
            command_runner=command_runner,
        )
    return code


def _load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    expected_hash = plan.pop("plan_sha256", None)
    actual_hash = hashlib.sha256(_canonical(plan)).hexdigest()
    plan["plan_sha256"] = expected_hash
    identity = plan.get("identity")
    attempts = plan.get("attempts")
    if (
        plan.get("plan_type") != "passive_preflight_retry"
        or plan.get("passive") is not True
        or plan.get("activate_evening") is not False
        or not isinstance(identity, Mapping)
        or not isinstance(attempts, list)
        or not attempts
        or expected_hash != actual_hash
    ):
        raise ValueError("invalid passive preflight retry plan")
    for attempt in attempts:
        if not isinstance(attempt, Mapping):
            raise ValueError("invalid passive preflight retry attempt")
        _verify_command_identity(
            tuple(str(value) for value in attempt.get("command", ())),
            identity,
        )
        _parse(str(attempt.get("scheduled_at", "")))
    return plan


def _verify_command_identity(
    command: Sequence[str], identity: Mapping[str, object]
) -> None:
    _assert_passive(" ".join(command))
    required = {
        "--expected-drawing-id": str(identity.get("drawing_id")),
        "--expected-drawing-number": str(identity.get("drawing_number")),
        "--expected-fingerprint": str(identity.get("drawing_fingerprint")),
        "--expected-deadline": str(identity.get("deadline")),
    }
    for option, expected in required.items():
        if command.count(option) != 1:
            raise ValueError(f"retry command lacks exact {option}")
        index = command.index(option)
        if index + 1 >= len(command) or command[index + 1] != expected:
            raise ValueError(f"retry command {option} identity drift")


def _option_value(command: Sequence[str], option: str) -> str:
    if command.count(option) != 1:
        raise ValueError(f"retry command lacks exact {option}")
    index = command.index(option)
    if index + 1 >= len(command) or not command[index + 1]:
        raise ValueError(f"retry command {option} value is missing")
    return command[index + 1]


def _due_attempt(
    plan: Mapping[str, object],
    now: datetime,
    executed: Mapping[str, object],
) -> Mapping[str, object] | None:
    due = [
        item
        for item in plan["attempts"]
        if _parse(str(item["scheduled_at"])) <= now
        and str(item["scheduled_at"]) not in executed
    ]
    return max(due, key=lambda item: _parse(str(item["scheduled_at"]))) if due else None


def _next_run(plan: dict, now: datetime) -> str | None:
    observed = _utc(now)
    if observed >= _parse(plan["hard_stop"]):
        return None
    return next(
        (
            item["scheduled_at"]
            for item in plan["attempts"]
            if observed < _parse(item["scheduled_at"]) < _parse(plan["hard_stop"])
        ),
        None,
    )


def _load_runtime_state(
    path: Path, identity: Mapping[str, object]
) -> dict[str, object]:
    if not path.exists():
        return {"identity": dict(identity), "executed": {}}
    if path.is_symlink() or not path.is_file():
        raise ValueError("preflight retry runtime state is invalid")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("identity") != dict(identity)
        or not isinstance(payload.get("executed"), dict)
    ):
        raise ValueError("preflight retry runtime identity drift")
    return payload


def _write_runtime_state(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    temporary.write_bytes(_canonical(payload) + b"\n")
    os.replace(temporary, path)


def _result_payload(result: object) -> dict[str, object]:
    stdout = getattr(result, "stdout", "")
    if not isinstance(stdout, str):
        return {}
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _assert_passive(value: str) -> None:
    lowered = value.lower()
    if any(token in lowered for token in _FORBIDDEN) or re.search(
        r"(^|[\s_-])bet([\s_-]|$)", lowered
    ):
        raise ValueError("preflight retry command is not passive")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _parse(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid preflight retry timestamp") from error
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("preflight retry time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _calendar(value: datetime) -> dict[str, int]:
    return {
        "Month": value.month,
        "Day": value.day,
        "Hour": value.hour,
        "Minute": value.minute,
    }


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _write_exact(path: Path, content: bytes, mode: int) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError(f"conflicting preflight scheduler artifact: {path}")
        path.chmod(mode)
        return
    path.write_bytes(content)
    path.chmod(mode)


def _launchctl(
    runner: Callable[..., object], *arguments: str
) -> object:
    return runner(
        ("launchctl", *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
