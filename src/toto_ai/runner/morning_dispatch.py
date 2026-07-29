"""Dynamic, idempotent morning handoff to one exact evening scheduler."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import secrets
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from toto_ai.runner.scheduler import (
    SCHEDULER_LAUNCH_AGENT_FILENAME,
    SCHEDULER_PLAN_FILENAME,
    SCHEDULER_WRAPPER_FILENAME,
    SchedulerPlan,
    build_scheduler_plan,
    load_scheduler_plan,
    prepare_scheduler_artifacts,
    verify_scheduler_artifacts,
)
from toto_ai.runner.scheduler_state import scheduler_lock

_SHA256_LENGTH = 64
MORNING_DISPATCH_SCHEMA_VERSION = 1
_SCHEDULER_LABEL = re.compile(
    r"com\.totoai\.production-scheduler\.[0-9a-f]{16}\Z"
)


@dataclass(frozen=True)
class MorningPreparedDrawing:
    drawing_id: int
    drawing_number: int
    deadline: datetime
    drawing_fingerprint: str
    detail_sha256: str
    preparation_status: str
    mapped_count: int
    eligibility_status: str
    span_days: int | None

    def __post_init__(self) -> None:
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be a positive integer")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be a positive integer")
        object.__setattr__(self, "deadline", _utc(self.deadline, "deadline"))
        _sha256(self.drawing_fingerprint, "drawing_fingerprint")
        _sha256(self.detail_sha256, "detail_sha256")
        if not self.preparation_status:
            raise ValueError("preparation_status is required")
        if type(self.mapped_count) is not int or not 0 <= self.mapped_count <= 15:
            raise ValueError("mapped_count must be from 0 through 15")
        if not self.eligibility_status:
            raise ValueError("eligibility_status is required")
        if self.span_days is not None and (
            type(self.span_days) is not int or self.span_days <= 0
        ):
            raise ValueError("span_days must be a positive integer or null")

    def identity_payload(self) -> dict[str, object]:
        return {
            "drawing_id": self.drawing_id,
            "drawing_number": self.drawing_number,
            "deadline": _timestamp(self.deadline),
            "drawing_fingerprint": self.drawing_fingerprint,
            "detail_sha256": self.detail_sha256,
        }


@dataclass(frozen=True)
class MorningDispatchConfig:
    project_root: Path
    state_root: Path
    scheduler_root: Path
    env_file: Path
    bank: int
    stake: int = 30
    db: Path = Path("data/toto.db")
    aliases: Path = Path("data/external-odds/team-aliases.json")
    timing_overrides: Path | None = None
    reviewed_schedule_catalog: Path | None = None

    def __post_init__(self) -> None:
        root = Path(self.project_root).absolute()
        if not root.is_dir() or root.is_symlink():
            raise ValueError("project_root must be an existing regular directory")
        object.__setattr__(self, "project_root", root)
        for field in ("state_root", "scheduler_root", "env_file", "db", "aliases"):
            value = Path(getattr(self, field))
            if not value.is_absolute():
                value = root / value
            value = value.absolute()
            if not value.is_relative_to(root):
                raise ValueError(f"{field} must remain inside project_root")
            object.__setattr__(self, field, value)
        if self.timing_overrides is not None:
            value = Path(self.timing_overrides)
            if not value.is_absolute():
                value = root / value
            value = value.absolute()
            if not value.is_relative_to(root):
                raise ValueError("timing_overrides must remain inside project_root")
            object.__setattr__(self, "timing_overrides", value)
        if self.reviewed_schedule_catalog is not None:
            value = Path(self.reviewed_schedule_catalog)
            if not value.is_absolute():
                value = root / value
            value = value.absolute()
            if not value.is_relative_to(root):
                raise ValueError(
                    "reviewed_schedule_catalog must remain inside project_root"
                )
            object.__setattr__(self, "reviewed_schedule_catalog", value)
        if type(self.bank) is not int or self.bank <= 0:
            raise ValueError("bank must be a positive integer")
        if type(self.stake) is not int or self.stake <= 0:
            raise ValueError("stake must be a positive integer")
        if self.bank % self.stake:
            raise ValueError("bank must be exactly divisible by stake")


@dataclass(frozen=True)
class MorningDispatchResult:
    status: Literal["scheduled", "reused", "deferred"]
    reason: str
    record_path: Path
    plan_id: str | None
    plan_path: Path | None
    launch_agent_path: Path | None
    activation_status: Literal["not_requested", "generated", "activated"]


def dispatch_morning(
    config: MorningDispatchConfig,
    *,
    observed_at: datetime,
    prepare_current: Callable[[datetime], MorningPreparedDrawing],
    now: Callable[[], datetime],
    activate: Callable[[str, Path], object] | None = None,
    python_command: str | Path | None = None,
) -> MorningDispatchResult:
    """Resolve/prepare once and create at most one exact schema-v4 evening plan."""
    if not isinstance(config, MorningDispatchConfig):
        raise ValueError("config must be MorningDispatchConfig")
    observed = _utc(observed_at, "observed_at")
    config.state_root.mkdir(parents=True, exist_ok=True)
    if config.state_root.is_symlink():
        raise ValueError("state_root cannot be a symlink")
    with scheduler_lock(config.state_root / ".dispatch.lock"):
        evidence = prepare_current(observed)
        if not isinstance(evidence, MorningPreparedDrawing):
            raise ValueError("prepare_current returned invalid evidence")
        observed = _utc(now(), "post_preparation_observed_at")
        record_path = _record_path(config, evidence, observed)
        prior = _load_record(record_path)
        replace_prior = False
        if prior is not None:
            if prior.get("status") == "scheduled":
                return _reuse_prior(
                    config,
                    evidence=evidence,
                    record_path=record_path,
                    prior=prior,
                    activate=activate,
                    python_command=python_command,
                )
            if prior.get("status") != "deferred":
                raise ValueError("morning dispatch record status is invalid")
            if not _same_drawing_identity(prior, evidence):
                raise ValueError("morning dispatch identity conflict")
            replace_prior = True
        reason = _ineligibility_reason(evidence)
        if reason is not None:
            record = _record(
                evidence=evidence,
                observed_at=observed,
                status="deferred",
                reason=reason,
            )
            (
                _replace_record(record_path, record)
                if replace_prior
                else _write_record(record_path, record)
            )
            return MorningDispatchResult(
                "deferred",
                reason,
                record_path,
                None,
                None,
                None,
                "not_requested",
            )
        output_dir = config.scheduler_root / (
            f"evening-{evidence.drawing_number}-"
            f"{evidence.deadline.strftime('%Y%m%dT%H%M%SZ')}"
        )
        plan = build_scheduler_plan(
            drawing=evidence.drawing_number,
            drawing_id=evidence.drawing_id,
            ended_at=evidence.deadline,
            bank=config.bank,
            stake=config.stake,
            output_dir=output_dir,
            project_root=config.project_root,
            db=config.db,
            aliases=config.aliases,
            timing_overrides=config.timing_overrides,
            reviewed_schedule_catalog=config.reviewed_schedule_catalog,
            env_file=config.env_file,
        )
        if observed >= plan.preflight_at:
            reason = "late_dispatch"
            record = _record(
                evidence=evidence,
                observed_at=observed,
                status="deferred",
                reason=reason,
            )
            (
                _replace_record(record_path, record)
                if replace_prior
                else _write_record(record_path, record)
            )
            return MorningDispatchResult(
                "deferred",
                reason,
                record_path,
                None,
                None,
                None,
                "not_requested",
            )
        artifact_paths = (
            plan.output_dir / SCHEDULER_PLAN_FILENAME,
            plan.output_dir / SCHEDULER_WRAPPER_FILENAME,
            plan.output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME,
        )
        artifacts = (
            verify_scheduler_artifacts(
                plan,
                python_command=python_command,
            )
            if any(path.exists() for path in artifact_paths)
            else prepare_scheduler_artifacts(
                plan,
                python_command=python_command,
            )
        )
        activation_status: Literal["generated", "activated"] = "generated"
        record = _record(
            evidence=evidence,
            observed_at=observed,
            status="scheduled",
            reason="ready",
            plan=plan,
            activation_status=activation_status,
        )
        (
            _replace_record(record_path, record)
            if replace_prior
            else _write_record(record_path, record)
        )
        if activate is not None:
            activate(
                f"com.totoai.production-scheduler.{plan.plan_id}",
                artifacts.launch_agent_path,
            )
            activation_status = "activated"
            activated_record = dict(record)
            activated_record["activation_status"] = "activated"
            _replace_record(record_path, activated_record)
        return MorningDispatchResult(
            "scheduled",
            "ready",
            record_path,
            plan.plan_id,
            artifacts.plan_path,
            artifacts.launch_agent_path,
            activation_status,
        )


def activate_scheduler_launch_agent(
    label: str,
    candidate_path: Path,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> None:
    """Install/bootstrap only one verified project-generated scheduler plist."""
    if not _SCHEDULER_LABEL.fullmatch(label):
        raise ValueError("scheduler LaunchAgent label is invalid")
    candidate = Path(candidate_path).absolute()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("scheduler LaunchAgent candidate must be a regular file")
    try:
        payload = plistlib.loads(candidate.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise ValueError("scheduler LaunchAgent candidate is invalid") from error
    if not isinstance(payload, dict) or payload.get("Label") != label:
        raise ValueError("scheduler LaunchAgent candidate label mismatch")
    root = (
        Path.home() / "Library" / "LaunchAgents"
        if launch_agents_root is None
        else Path(launch_agents_root)
    ).absolute()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("LaunchAgents root cannot be a symlink")
    destination = root / f"{label}.plist"
    content = candidate.read_bytes()
    if destination.exists():
        if (
            destination.is_symlink()
            or not destination.is_file()
            or destination.read_bytes() != content
        ):
            raise ValueError("installed scheduler LaunchAgent conflicts")
    else:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    domain = f"gui/{os.getuid()}"
    completed = command_runner(
        ("launchctl", "bootstrap", domain, str(destination)),
        check=False,
        capture_output=True,
        text=True,
    )
    returncode = getattr(completed, "returncode", None)
    if returncode == 0:
        return
    inspected = command_runner(
        ("launchctl", "print", f"{domain}/{label}"),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(inspected, "returncode", None) != 0:
        detail = str(getattr(completed, "stderr", "")).strip()
        raise ValueError(
            "scheduler LaunchAgent bootstrap failed"
            + (f": {detail[-500:]}" if detail else "")
        )


def _reuse_prior(
    config: MorningDispatchConfig,
    *,
    evidence: MorningPreparedDrawing,
    record_path: Path,
    prior: Mapping[str, object],
    activate: Callable[[str, Path], object] | None,
    python_command: str | Path | None,
) -> MorningDispatchResult:
    identity = prior.get("identity")
    expected_identity = evidence.identity_payload()
    if not isinstance(identity, Mapping) or any(
        identity.get(field) != expected_identity[field]
        for field in (
            "drawing_id",
            "drawing_number",
            "deadline",
            "drawing_fingerprint",
        )
    ):
        raise ValueError("morning dispatch identity conflict")
    if prior.get("status") != "scheduled":
        reason = str(prior.get("reason", "deferred"))
        return MorningDispatchResult(
            "deferred",
            reason,
            record_path,
            None,
            None,
            None,
            "not_requested",
        )
    plan_path = Path(str(prior["plan_path"])).absolute()
    launch_agent_path = Path(str(prior["launch_agent_path"])).absolute()
    if (
        not plan_path.is_relative_to(config.project_root)
        or not launch_agent_path.is_relative_to(config.project_root)
    ):
        raise ValueError("morning dispatch artifact path escaped project_root")
    plan = load_scheduler_plan(plan_path)
    if (
        plan.plan_id != prior.get("plan_id")
        or plan.drawing != evidence.drawing_number
        or plan.drawing_id != evidence.drawing_id
        or plan.ended_at != evidence.deadline
        or launch_agent_path
        != plan.output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME
        or not launch_agent_path.is_file()
        or launch_agent_path.is_symlink()
    ):
        raise ValueError("morning dispatch persisted plan does not verify")
    artifacts = verify_scheduler_artifacts(
        plan,
        python_command=python_command,
    )
    if (
        artifacts.plan_path != plan_path
        or artifacts.launch_agent_path != launch_agent_path
    ):
        raise ValueError("morning dispatch persisted artifact paths conflict")
    activation_status = str(prior.get("activation_status", "generated"))
    if activation_status not in {"generated", "activated"}:
        raise ValueError("morning dispatch activation status is invalid")
    if activate is not None and activation_status != "activated":
        activate(
            f"com.totoai.production-scheduler.{plan.plan_id}",
            artifacts.launch_agent_path,
        )
        updated = dict(prior)
        updated["activation_status"] = "activated"
        _replace_record(record_path, updated)
        activation_status = "activated"
    return MorningDispatchResult(
        "reused",
        "ready",
        record_path,
        plan.plan_id,
        artifacts.plan_path,
        artifacts.launch_agent_path,
        activation_status,  # type: ignore[arg-type]
    )


def _same_drawing_identity(
    prior: Mapping[str, object],
    evidence: MorningPreparedDrawing,
) -> bool:
    identity = prior.get("identity")
    if not isinstance(identity, Mapping):
        return False
    expected = evidence.identity_payload()
    return all(
        identity.get(field) == expected[field]
        for field in ("drawing_id", "drawing_number", "deadline")
    )


def _ineligibility_reason(evidence: MorningPreparedDrawing) -> str | None:
    if evidence.preparation_status != "ready" or evidence.mapped_count != 15:
        return "preparation_not_ready"
    if evidence.span_days is not None and evidence.span_days > 5:
        return "drawing_span_exceeds_five_days"
    if evidence.eligibility_status != "playable":
        return "drawing_not_playable"
    if evidence.span_days is None or evidence.span_days > 2:
        return "drawing_not_playable"
    return None


def _record_path(
    config: MorningDispatchConfig,
    evidence: MorningPreparedDrawing,
    observed_at: datetime,
) -> Path:
    del observed_at
    deadline = evidence.deadline.strftime("%Y%m%dT%H%M%SZ")
    return config.state_root / f"drawing-{evidence.drawing_id}-{deadline}.json"


def _record(
    *,
    evidence: MorningPreparedDrawing,
    observed_at: datetime,
    status: str,
    reason: str,
    plan: SchedulerPlan | None = None,
    activation_status: str = "not_requested",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": MORNING_DISPATCH_SCHEMA_VERSION,
        "identity": evidence.identity_payload(),
        "observed_at": _timestamp(observed_at),
        "preparation": {
            "status": evidence.preparation_status,
            "mapped_count": evidence.mapped_count,
            "eligibility_status": evidence.eligibility_status,
            "span_days": evidence.span_days,
        },
        "status": status,
        "reason": reason,
        "plan_id": None,
        "plan_path": None,
        "launch_agent_path": None,
        "activation_status": activation_status,
    }
    if plan is not None:
        payload.update(
            {
                "plan_id": plan.plan_id,
                "plan_path": str(plan.output_dir / SCHEDULER_PLAN_FILENAME),
                "launch_agent_path": str(
                    plan.output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME
                ),
            }
        )
    payload["record_sha256"] = _record_sha256(payload)
    return payload


def _load_record(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("morning dispatch record must be a regular file")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("morning dispatch record could not be loaded") from error
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != MORNING_DISPATCH_SCHEMA_VERSION
        or payload.get("record_sha256") != _record_sha256(payload)
    ):
        raise ValueError("morning dispatch record integrity mismatch")
    return payload


def _write_record(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise ValueError("morning dispatch record already exists")
    _write_atomic(path, payload, replace=False)


def _replace_record(path: Path, payload: Mapping[str, object]) -> None:
    updated = dict(payload)
    updated["record_sha256"] = _record_sha256(updated)
    _write_atomic(path, updated, replace=True)


def _write_atomic(
    path: Path, payload: Mapping[str, object], *, replace: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _record_sha256(payload: Mapping[str, object]) -> str:
    unsigned = dict(payload)
    unsigned.pop("record_sha256", None)
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")
