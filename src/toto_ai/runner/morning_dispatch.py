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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from toto_ai.runner.scheduler import (
    SCHEDULER_LAUNCH_AGENT_FILENAME,
    SCHEDULER_PLAN_FILENAME,
    SCHEDULER_SCHEMA_VERSION,
    SCHEDULER_WRAPPER_FILENAME,
    SchedulerPlan,
    build_scheduler_plan,
    load_scheduler_plan,
    prepare_scheduler_artifacts,
    scheduler_launch_agent_label,
    verify_scheduler_artifacts,
)
from toto_ai.runner.scheduler_state import scheduler_lock

_SHA256_LENGTH = 64
_MOSCOW = ZoneInfo("Europe/Moscow")
_ZERO_POOL_NOT_READY = "totobrief_pool_not_ready"
MORNING_DISPATCH_SCHEMA_VERSION = 1
PREFLIGHT_ESCALATION_SCHEMA_VERSION = 1
PREFLIGHT_RETRY_RUNNER_VERSION = 2
_SCHEDULER_LABEL = re.compile(
    rf"com\.totoai\.production-scheduler\.v{SCHEDULER_SCHEMA_VERSION}\."
    r"[0-9a-f]{16}\Z"
)


class MorningIdentityDriftError(ValueError):
    """The retried drawing no longer matches its persisted exact identity."""


@dataclass(frozen=True)
class MorningUnresolvedEvent:
    event_order: int
    target_event_id: int
    home_team: str
    away_team: str
    resolution_status: str
    reason: str
    candidate_evidence: tuple[Mapping[str, object], ...] = ()
    provider_diagnostics: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if type(self.event_order) is not int or not 0 <= self.event_order < 15:
            raise ValueError("event_order must be from 0 through 14")
        if type(self.target_event_id) is not int or self.target_event_id <= 0:
            raise ValueError("target_event_id must be a positive integer")
        for value, name in (
            (self.home_team, "home_team"),
            (self.away_team, "away_team"),
            (self.resolution_status, "resolution_status"),
            (self.reason, "reason"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")

    @property
    def required_evidence_type(self) -> str:
        if self.resolution_status in {
            "source_missing_competition",
            "timing_unknown",
        }:
            return "reviewed_schedule"
        return "reviewed_alias"

    def payload(self) -> dict[str, object]:
        return {
            "event_order": self.event_order,
            "target_event_id": self.target_event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "resolution_status": self.resolution_status,
            "reason": self.reason,
            "candidate_evidence": [dict(item) for item in self.candidate_evidence],
            "provider_diagnostics": [dict(item) for item in self.provider_diagnostics],
            "required_evidence_type": self.required_evidence_type,
        }


@dataclass(frozen=True)
class MorningExpectedIdentity:
    drawing_id: int
    drawing_number: int
    deadline: datetime
    drawing_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be a positive integer")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be a positive integer")
        object.__setattr__(self, "deadline", _utc(self.deadline, "deadline"))
        _sha256(self.drawing_fingerprint, "drawing_fingerprint")


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
    unresolved_events: tuple[MorningUnresolvedEvent, ...] = ()
    not_ready_reason: str | None = None
    external_coverage_count: int = 15
    baseline_only_event_orders: tuple[int, ...] = ()
    reviewed_catalog_hash: str | None = None
    operational_cutoff: datetime | None = None
    cutoff_evidence: Path | None = None
    cutoff_evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be a positive integer")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be a positive integer")
        object.__setattr__(self, "deadline", _utc(self.deadline, "deadline"))
        operational_cutoff = (
            self.deadline
            if self.operational_cutoff is None
            else _utc(self.operational_cutoff, "operational_cutoff")
        )
        if operational_cutoff > self.deadline:
            raise ValueError("operational_cutoff cannot extend deadline")
        object.__setattr__(self, "operational_cutoff", operational_cutoff)
        if self.cutoff_evidence is None:
            if operational_cutoff != self.deadline:
                raise ValueError(
                    "an earlier operational_cutoff requires cutoff evidence"
                )
            if self.cutoff_evidence_sha256 is not None:
                raise ValueError("cutoff_evidence_sha256 requires cutoff evidence")
        else:
            object.__setattr__(self, "cutoff_evidence", Path(self.cutoff_evidence))
            _sha256(self.cutoff_evidence_sha256, "cutoff_evidence_sha256")
        _sha256(self.drawing_fingerprint, "drawing_fingerprint")
        _sha256(self.detail_sha256, "detail_sha256")
        if self.reviewed_catalog_hash is not None:
            _sha256(self.reviewed_catalog_hash, "reviewed_catalog_hash")
        if not self.preparation_status:
            raise ValueError("preparation_status is required")
        if type(self.mapped_count) is not int or not 0 <= self.mapped_count <= 15:
            raise ValueError("mapped_count must be from 0 through 15")
        if not self.eligibility_status:
            raise ValueError("eligibility_status is required")
        if (
            type(self.external_coverage_count) is not int
            or not 0 <= self.external_coverage_count <= 15
        ):
            raise ValueError("external_coverage_count must be from 0 through 15")
        if (
            tuple(sorted(self.baseline_only_event_orders))
            != self.baseline_only_event_orders
            or len(set(self.baseline_only_event_orders))
            != len(self.baseline_only_event_orders)
            or any(order not in range(15) for order in self.baseline_only_event_orders)
            or self.external_coverage_count + len(self.baseline_only_event_orders) != 15
        ):
            raise ValueError("baseline-only coverage evidence is inconsistent")
        if self.span_days is not None and (
            type(self.span_days) is not int or self.span_days <= 0
        ):
            raise ValueError("span_days must be a positive integer or null")
        orders = tuple(item.event_order for item in self.unresolved_events)
        if len(set(orders)) != len(orders) or tuple(sorted(orders)) != orders:
            raise ValueError(
                "unresolved_events must have unique ascending event orders"
            )
        if self.preparation_status == "ready" and self.unresolved_events:
            if (
                any(
                    item.resolution_status != "timing_unknown"
                    for item in self.unresolved_events
                )
                or not set(orders).issubset(self.baseline_only_event_orders)
                or self.eligibility_status != "unknown"
            ):
                raise ValueError(
                    "ready preparation may contain only baseline timing_unknown events"
                )
        if self.not_ready_reason is not None:
            if self.not_ready_reason != _ZERO_POOL_NOT_READY:
                raise ValueError("not_ready_reason is unsupported")
            if (
                self.preparation_status != "not_ready"
                or self.mapped_count != 0
                or self.eligibility_status != "unknown"
                or self.span_days is not None
                or self.unresolved_events
            ):
                raise ValueError("zero-pool not-ready evidence is inconsistent")

    def identity_payload(self) -> dict[str, object]:
        return {
            "drawing_id": self.drawing_id,
            "drawing_number": self.drawing_number,
            "deadline": _timestamp(self.deadline),
            "operational_cutoff": _timestamp(self.operational_cutoff),
            "cutoff_evidence_sha256": self.cutoff_evidence_sha256,
            "drawing_fingerprint": self.drawing_fingerprint,
            "detail_sha256": self.detail_sha256,
            "reviewed_catalog_hash": self.reviewed_catalog_hash,
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
    maintenance_lock: Path = Path("data/operations/global-maintenance.lock")
    timing_overrides: Path | None = None
    reviewed_schedule_catalog: Path | None = None
    schedule_evidence_ledger: Path = Path("data/schedule-evidence/ledger.json")
    retry_offsets_minutes: tuple[int, ...] = (360, 240, 180, 120, 90)
    retry_hard_stop_minutes: int = 60

    def __post_init__(self) -> None:
        root = Path(self.project_root).absolute()
        if not root.is_dir() or root.is_symlink():
            raise ValueError("project_root must be an existing regular directory")
        object.__setattr__(self, "project_root", root)
        for field in (
            "state_root",
            "scheduler_root",
            "env_file",
            "db",
            "aliases",
            "maintenance_lock",
            "schedule_evidence_ledger",
        ):
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
        if (
            not self.retry_offsets_minutes
            or any(
                type(value) is not int or value <= self.retry_hard_stop_minutes
                for value in self.retry_offsets_minutes
            )
            or tuple(sorted(set(self.retry_offsets_minutes), reverse=True))
            != self.retry_offsets_minutes
        ):
            raise ValueError(
                "retry_offsets_minutes must be unique descending values "
                "before the hard stop"
            )
        if (
            type(self.retry_hard_stop_minutes) is not int
            or self.retry_hard_stop_minutes <= 0
        ):
            raise ValueError("retry_hard_stop_minutes must be positive")


@dataclass(frozen=True)
class MorningDispatchResult:
    status: Literal["scheduled", "reused", "prepared", "deferred"]
    reason: str
    record_path: Path
    plan_id: str | None
    plan_path: Path | None
    launch_agent_path: Path | None
    activation_status: Literal["not_requested", "generated", "activated"]
    attention_path: Path | None = None
    retry_plan_path: Path | None = None
    review_queue_path: Path | None = None
    launch_agent_label: str | None = None


def dispatch_morning(
    config: MorningDispatchConfig,
    *,
    observed_at: datetime,
    prepare_current: Callable[[datetime], MorningPreparedDrawing],
    now: Callable[[], datetime],
    activate: Callable[[str, Path], object] | None = None,
    python_command: str | Path | None = None,
    expected_identity: MorningExpectedIdentity | None = None,
) -> MorningDispatchResult:
    """Resolve/prepare once and create at most one exact schema-v5 evening plan."""
    if not isinstance(config, MorningDispatchConfig):
        raise ValueError("config must be MorningDispatchConfig")
    observed = _utc(observed_at, "observed_at")
    with scheduler_lock(config.maintenance_lock):
        evidence = prepare_current(observed)
        if not isinstance(evidence, MorningPreparedDrawing):
            raise ValueError("prepare_current returned invalid evidence")
        _validate_expected_identity(evidence, expected_identity)
        config.state_root.mkdir(parents=True, exist_ok=True)
        if config.state_root.is_symlink():
            raise ValueError("state_root cannot be a symlink")
        with scheduler_lock(config.state_root / ".dispatch.lock"):
            return _dispatch_morning_locked(
                config,
                observed=observed,
                evidence=evidence,
                now=now,
                activate=activate,
                python_command=python_command,
            )


def _dispatch_morning_locked(
    config: MorningDispatchConfig,
    *,
    observed: datetime,
    evidence: MorningPreparedDrawing,
    now: Callable[[], datetime],
    activate: Callable[[str, Path], object] | None,
    python_command: str | Path | None,
) -> MorningDispatchResult:
    observed = _utc(now(), "post_preparation_observed_at")
    escalation = _update_preflight_escalation(
        config,
        evidence=evidence,
        observed_at=observed,
        python_command=python_command,
    )
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
        if prior.get("status") not in {"prepared", "deferred"}:
            raise ValueError("morning dispatch record status is invalid")
        if not _same_drawing_identity(
            prior, evidence
        ) and not _allows_deferred_reviewed_hash_transition(prior, evidence):
            raise ValueError("morning dispatch identity conflict")
        replace_prior = True
    reason = _ineligibility_reason(evidence)
    if reason is not None:
        status: Literal["prepared", "deferred"] = (
            "prepared"
            if reason == "drawing_not_playable"
            and evidence.preparation_status == "ready"
            and evidence.mapped_count == 15
            else "deferred"
        )
        record = _record(
            evidence=evidence,
            observed_at=observed,
            status=status,
            reason=reason,
        )
        (
            _replace_record(record_path, record)
            if replace_prior
            else _write_record(record_path, record)
        )
        return MorningDispatchResult(
            status,
            reason,
            record_path,
            None,
            None,
            None,
            "not_requested",
            escalation.attention_path,
            escalation.retry_plan_path,
            escalation.review_queue_path,
        )
    output_dir = config.scheduler_root / (
        f"evening-{evidence.drawing_number}-"
        f"{evidence.deadline.strftime('%Y%m%dT%H%M%SZ')}"
    )
    plan = build_scheduler_plan(
        drawing=evidence.drawing_number,
        drawing_id=evidence.drawing_id,
        ended_at=evidence.deadline,
        operational_cutoff=evidence.operational_cutoff,
        cutoff_evidence=evidence.cutoff_evidence,
        cutoff_evidence_sha256=evidence.cutoff_evidence_sha256,
        bank=config.bank,
        stake=config.stake,
        output_dir=output_dir,
        project_root=config.project_root,
        db=config.db,
        aliases=config.aliases,
        timing_overrides=config.timing_overrides,
        reviewed_schedule_catalog=config.reviewed_schedule_catalog,
        reviewed_catalog_hash=evidence.reviewed_catalog_hash,
        schedule_evidence_ledger=config.schedule_evidence_ledger,
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
            escalation.attention_path,
            escalation.retry_plan_path,
            escalation.review_queue_path,
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
    launch_agent_label = scheduler_launch_agent_label(plan)
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
            launch_agent_label,
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
        launch_agent_label=launch_agent_label,
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
    plan = load_scheduler_plan(candidate.parent / SCHEDULER_PLAN_FILENAME)
    artifacts = verify_scheduler_artifacts(plan)
    expected_label = scheduler_launch_agent_label(plan)
    if candidate != artifacts.launch_agent_path:
        raise ValueError("scheduler LaunchAgent candidate path mismatch")
    if label != expected_label:
        raise ValueError("scheduler LaunchAgent label does not match plan identity")
    if not isinstance(payload, dict) or payload.get("Label") != expected_label:
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
            "operational_cutoff",
            "cutoff_evidence_sha256",
            "drawing_fingerprint",
            "reviewed_catalog_hash",
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
    if not plan_path.is_relative_to(
        config.project_root
    ) or not launch_agent_path.is_relative_to(config.project_root):
        raise ValueError("morning dispatch artifact path escaped project_root")
    plan = load_scheduler_plan(plan_path)
    if (
        plan.plan_id != prior.get("plan_id")
        or plan.drawing != evidence.drawing_number
        or plan.drawing_id != evidence.drawing_id
        or plan.ended_at != evidence.deadline
        or plan.operational_cutoff != evidence.operational_cutoff
        or plan.cutoff_evidence_sha256 != evidence.cutoff_evidence_sha256
        or launch_agent_path != plan.output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME
        or not launch_agent_path.is_file()
        or launch_agent_path.is_symlink()
    ):
        raise ValueError("morning dispatch persisted plan does not verify")
    launch_agent_label = scheduler_launch_agent_label(plan)
    persisted_label = prior.get("launch_agent_label")
    if persisted_label not in {None, launch_agent_label}:
        raise ValueError("morning dispatch LaunchAgent label conflicts")
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
    if persisted_label is None:
        updated = dict(prior)
        updated["launch_agent_label"] = launch_agent_label
        _replace_record(record_path, updated)
        prior = updated
    if activate is not None and activation_status != "activated":
        activate(
            launch_agent_label,
            artifacts.launch_agent_path,
        )
        updated = dict(prior)
        updated["launch_agent_label"] = launch_agent_label
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
        launch_agent_label=launch_agent_label,
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
        for field in (
            "drawing_id",
            "drawing_number",
            "deadline",
            "drawing_fingerprint",
            "reviewed_catalog_hash",
        )
    )


def _allows_deferred_reviewed_hash_transition(
    prior: Mapping[str, object],
    evidence: MorningPreparedDrawing,
) -> bool:
    """Allow only artifact-free null-to-validated reviewed hash enrichment."""
    if (
        prior.get("status") not in {"prepared", "deferred"}
        or prior.get("activation_status") != "not_requested"
        or evidence.reviewed_catalog_hash is None
    ):
        return False
    protected_artifact_fields = (
        "plan_id",
        "plan_path",
        "launch_agent_path",
        "launch_agent_label",
        "package_path",
        "package_sha256",
        "package_manifest_path",
        "archive_manifest_path",
        "bet_ready_path",
    )
    if any(prior.get(field) is not None for field in protected_artifact_fields):
        return False
    identity = prior.get("identity")
    if not isinstance(identity, Mapping):
        return False
    expected = evidence.identity_payload()
    if identity.get("reviewed_catalog_hash") is not None:
        return False
    return all(
        identity.get(field) == expected[field]
        for field in (
            "drawing_id",
            "drawing_number",
            "deadline",
            "drawing_fingerprint",
        )
    )


def _ineligibility_reason(evidence: MorningPreparedDrawing) -> str | None:
    if evidence.not_ready_reason is not None:
        return evidence.not_ready_reason
    if evidence.preparation_status != "ready" or evidence.mapped_count != 15:
        unresolved_count = (
            len(evidence.unresolved_events)
            if evidence.unresolved_events
            else 15 - evidence.mapped_count
        )
        return f"ACTION REQUIRED: unresolved {unresolved_count}/15"
    timing_unknown_count = sum(
        item.resolution_status == "timing_unknown"
        for item in evidence.unresolved_events
    )
    if timing_unknown_count:
        return f"ACTION REQUIRED: timing unknown {timing_unknown_count}/15"
    if evidence.span_days is not None and evidence.span_days > 5:
        return "drawing_span_exceeds_five_days"
    return _playability_reason(evidence)


def _playability_reason(evidence: MorningPreparedDrawing) -> str | None:
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
    return config.state_root / (
        f"drawing-{evidence.drawing_id}-{deadline}-"
        f"{evidence.drawing_fingerprint[:16]}.json"
    )


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
            "external_coverage_count": evidence.external_coverage_count,
            "baseline_only_event_orders": list(evidence.baseline_only_event_orders),
            "eligibility_status": evidence.eligibility_status,
            "span_days": evidence.span_days,
            "unresolved": [item.payload() for item in evidence.unresolved_events],
            "not_ready_reason": evidence.not_ready_reason,
        },
        "playability": {
            "status": evidence.eligibility_status,
            "span_days": evidence.span_days,
            "playable": (
                evidence.eligibility_status == "playable"
                and evidence.span_days is not None
                and evidence.span_days <= 2
            ),
            "reason": _playability_reason(evidence),
        },
        "status": status,
        "reason": reason,
        "plan_id": None,
        "plan_path": None,
        "launch_agent_path": None,
        "launch_agent_label": None,
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
                "launch_agent_label": scheduler_launch_agent_label(plan),
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


def load_morning_dispatch_record(path: str | Path) -> dict[str, object] | None:
    """Load one integrity-checked morning dispatch record without mutating it."""
    return _load_record(Path(path))


def _write_record(path: Path, payload: Mapping[str, object]) -> None:
    if path.exists():
        raise ValueError("morning dispatch record already exists")
    _write_atomic(path, payload, replace=False)


def _replace_record(path: Path, payload: Mapping[str, object]) -> None:
    updated = dict(payload)
    updated["record_sha256"] = _record_sha256(updated)
    _write_atomic(path, updated, replace=True)


def _write_atomic(path: Path, payload: Mapping[str, object], *, replace: bool) -> None:
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


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("preflight timestamp is invalid") from error
    return _utc(parsed, "preflight timestamp")


@dataclass(frozen=True)
class _EscalationPaths:
    attention_path: Path | None
    retry_plan_path: Path | None
    review_queue_path: Path | None


def _validate_expected_identity(
    evidence: MorningPreparedDrawing,
    expected: MorningExpectedIdentity | None,
) -> None:
    if expected is None:
        return
    if evidence.drawing_id != expected.drawing_id:
        raise MorningIdentityDriftError("preflight drawing ID drift")
    if evidence.drawing_number != expected.drawing_number:
        raise MorningIdentityDriftError("preflight drawing number drift")
    if evidence.deadline != expected.deadline:
        raise MorningIdentityDriftError("preflight deadline drift")
    if evidence.drawing_fingerprint != expected.drawing_fingerprint:
        raise MorningIdentityDriftError("preflight fingerprint drift")


def _update_preflight_escalation(
    config: MorningDispatchConfig,
    *,
    evidence: MorningPreparedDrawing,
    observed_at: datetime,
    python_command: str | Path | None,
) -> _EscalationPaths:
    root = _preflight_root(config, evidence)
    attention_path = root / "attention.json"
    if (
        evidence.preparation_status == "ready"
        and evidence.mapped_count == 15
        and not evidence.unresolved_events
        and _playability_reason(evidence) is None
    ):
        if attention_path.is_file():
            prior = _load_json_mapping(attention_path)
            identity = prior.get("identity")
            if (
                isinstance(identity, Mapping)
                and identity.get("drawing_fingerprint") == evidence.drawing_fingerprint
            ):
                attention_path.unlink()
                (root / "ACTION_REQUIRED.md").unlink(missing_ok=True)
                resolved = {
                    "schema_version": PREFLIGHT_ESCALATION_SCHEMA_VERSION,
                    "status": "RESOLVED: READY 15/15",
                    "resolved_at": _timestamp(observed_at),
                    "identity": evidence.identity_payload(),
                }
                resolved["record_sha256"] = _record_sha256(resolved)
                _write_json_idempotent(root / "RESOLVED.json", resolved)
        return _EscalationPaths(None, None, None)
    bootstrap_not_ready = evidence.not_ready_reason == _ZERO_POOL_NOT_READY
    timing_unknown = bool(evidence.unresolved_events) and all(
        item.resolution_status == "timing_unknown"
        for item in evidence.unresolved_events
    )
    retry_can_activate_evening = bootstrap_not_ready or timing_unknown
    if not evidence.unresolved_events and not bootstrap_not_ready:
        return _EscalationPaths(None, None, None)

    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("preflight escalation root cannot be a symlink")
    prior = _load_json_mapping(attention_path) if attention_path.is_file() else None
    first_seen = (
        str(prior["first_seen"]) if prior is not None else _timestamp(observed_at)
    )
    prior_attempts = int(prior.get("attempts", 0)) if prior is not None else 0
    retry_plan_path = root / "retry-plan.json"
    if retry_plan_path.is_file():
        retry_plan = _load_json_mapping(retry_plan_path)
        identity = retry_plan.get("identity")
        if (
            not isinstance(identity, Mapping)
            or identity.get("drawing_id") != evidence.drawing_id
            or identity.get("drawing_number") != evidence.drawing_number
            or identity.get("drawing_fingerprint") != evidence.drawing_fingerprint
            or identity.get("deadline") != _timestamp(evidence.deadline)
            or retry_plan.get("passive") is not True
            or retry_plan.get("activate_evening") is not retry_can_activate_evening
        ):
            raise ValueError("existing passive retry plan identity conflicts")
        runner_upgrade_required = (
            retry_plan.get("runner_version") != PREFLIGHT_RETRY_RUNNER_VERSION
        )
        prior_cutoff = _parse_timestamp(
            str(identity.get("operational_cutoff", identity["deadline"]))
        )
        if evidence.operational_cutoff > prior_cutoff:
            raise ValueError("passive retry cutoff cannot be relaxed")
        if evidence.operational_cutoff < prior_cutoff or runner_upgrade_required:
            retry_plan = _retry_plan_payload(
                config,
                evidence=evidence,
                observed_at=observed_at,
                python_command=python_command,
            )
            _write_atomic(retry_plan_path, retry_plan, replace=True)
    else:
        retry_plan = _retry_plan_payload(
            config,
            evidence=evidence,
            observed_at=observed_at,
            python_command=python_command,
        )
        _write_json_idempotent(retry_plan_path, retry_plan)
    future_attempts = retry_plan["attempts"]
    next_retry = (
        next(
            (
                item["scheduled_at"]
                for item in future_attempts
                if isinstance(item, Mapping)
                and _parse_timestamp(str(item["scheduled_at"])) > observed_at
            ),
            None,
        )
        if isinstance(future_attempts, list)
        else None
    )
    unresolved_payload = [item.payload() for item in evidence.unresolved_events]
    attention_status = (
        _ZERO_POOL_NOT_READY
        if bootstrap_not_ready
        else (
            f"ACTION REQUIRED: timing unknown {len(evidence.unresolved_events)}/15"
            if timing_unknown
            else f"ACTION REQUIRED: unresolved {len(evidence.unresolved_events)}/15"
        )
    )
    attempt = {
        "schema_version": PREFLIGHT_ESCALATION_SCHEMA_VERSION,
        "status": attention_status,
        "identity": evidence.identity_payload(),
        "captured_at": _timestamp(observed_at),
        "unresolved": unresolved_payload,
        "next_retry": next_retry,
        "passive": True,
        "activate_evening": retry_can_activate_evening,
    }
    attempt["record_sha256"] = _record_sha256(attempt)
    attempt_id = hashlib.sha256(_canonical(attempt)).hexdigest()[:16]
    attempt_dir = root / "attempts"
    attempt_path = attempt_dir / (
        f"{observed_at.strftime('%Y%m%dT%H%M%S%fZ')}-{attempt_id}.json"
    )
    created = _write_json_idempotent(attempt_path, attempt)
    attempt_report = attempt_path.with_suffix(".md")
    _write_text_idempotent(
        attempt_report,
        _render_attempt_report(attempt),
    )
    attempts = prior_attempts + int(created)
    attention = {
        "schema_version": PREFLIGHT_ESCALATION_SCHEMA_VERSION,
        "status": attempt["status"],
        "identity": evidence.identity_payload(),
        "first_seen": first_seen,
        "last_seen": _timestamp(observed_at),
        "attempts": attempts,
        "next_retry": next_retry,
        "unresolved": unresolved_payload,
        "retry_plan_path": str(retry_plan_path),
        "passive": True,
        "activate_evening": retry_can_activate_evening,
    }
    attention["record_sha256"] = _record_sha256(attention)
    _write_atomic(attention_path, attention, replace=attention_path.exists())
    _refresh_generated_report(
        root / "ACTION_REQUIRED.md", _render_attention_report(attention)
    )
    _refresh_generated_notify_command(
        root / "notify.command",
        "/usr/bin/osascript -e "
        f'\'display notification "{attention_status}" '
        f'with title "TotoAI drawing {evidence.drawing_number}"\'\n',
        drawing_number=evidence.drawing_number,
    )
    missing_schedule_orders = tuple(
        item.event_order
        for item in evidence.unresolved_events
        if item.required_evidence_type == "reviewed_schedule"
    )
    queue_suffix = hashlib.sha256(_canonical(missing_schedule_orders)).hexdigest()[:12]
    review_queue_path = root / f"reviewed-schedule-queue-{queue_suffix}.json"
    if review_queue_path.is_file():
        queue = _load_json_mapping(review_queue_path)
        identity = queue.get("identity")
        if (
            not isinstance(identity, Mapping)
            or identity.get("drawing_fingerprint") != evidence.drawing_fingerprint
        ):
            raise ValueError("existing reviewed schedule queue identity conflicts")
    else:
        queue = _review_queue_payload(evidence, observed_at=observed_at)
        if queue["records"]:
            _write_json_idempotent(review_queue_path, queue)
        else:
            review_queue_path = None
    return _EscalationPaths(attention_path, retry_plan_path, review_queue_path)


def _preflight_root(
    config: MorningDispatchConfig, evidence: MorningPreparedDrawing
) -> Path:
    deadline = evidence.deadline.strftime("%Y%m%dT%H%M%SZ")
    return (
        config.state_root
        / "preflight"
        / (
            f"drawing-{evidence.drawing_id}-{deadline}-"
            f"{evidence.drawing_fingerprint[:16]}"
        )
    )


def _retry_plan_payload(
    config: MorningDispatchConfig,
    *,
    evidence: MorningPreparedDrawing,
    observed_at: datetime,
    python_command: str | Path | None,
) -> dict[str, object]:
    hard_stop = evidence.operational_cutoff - timedelta(
        minutes=config.retry_hard_stop_minutes
    )
    executable = str(python_command or "python")
    activate_evening = evidence.not_ready_reason == _ZERO_POOL_NOT_READY or (
        bool(evidence.unresolved_events)
        and all(
            item.resolution_status == "timing_unknown"
            for item in evidence.unresolved_events
        )
    )
    attempts = []
    scheduled_times = (
        _zero_pool_retry_times(observed_at, hard_stop)
        if activate_evening
        else tuple(
            evidence.operational_cutoff - timedelta(minutes=offset)
            for offset in config.retry_offsets_minutes
        )
    )
    for scheduled_at in scheduled_times:
        if scheduled_at <= observed_at or scheduled_at >= hard_stop:
            continue
        command = [
            executable,
            "-m",
            "toto_ai.cli",
            "morning-dispatch",
            "--bank",
            str(config.bank),
            "--stake",
            str(config.stake),
            "--env-file",
            str(config.env_file),
            "--project-root",
            str(config.project_root),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
            "--db",
            str(config.db),
            "--aliases",
            str(config.aliases),
            "--expected-drawing-id",
            str(evidence.drawing_id),
            "--expected-drawing-number",
            str(evidence.drawing_number),
            "--expected-fingerprint",
            evidence.drawing_fingerprint,
            "--expected-deadline",
            _timestamp(evidence.deadline),
        ]
        if config.reviewed_schedule_catalog is not None:
            command.extend(
                (
                    "--reviewed-schedule-catalog",
                    str(config.reviewed_schedule_catalog),
                )
            )
        command.extend(
            (
                "--schedule-evidence-ledger",
                str(config.schedule_evidence_ledger),
            )
        )
        if activate_evening:
            command.append("--activate")
        command.append("--preflight-retry-child")
        attempts.append(
            {
                "scheduled_at": _timestamp(scheduled_at),
                "command": command,
                "status": "planned",
            }
        )
    payload: dict[str, object] = {
        "schema_version": PREFLIGHT_ESCALATION_SCHEMA_VERSION,
        "runner_version": PREFLIGHT_RETRY_RUNNER_VERSION,
        "plan_type": "passive_preflight_retry",
        "identity": evidence.identity_payload(),
        "created_at": _timestamp(observed_at),
        "hard_stop": _timestamp(hard_stop),
        "passive": True,
        "activate_evening": activate_evening,
        "attempts": attempts,
    }
    payload["plan_sha256"] = _record_sha256(payload)
    return payload


def _zero_pool_retry_times(
    observed_at: datetime,
    hard_stop: datetime,
) -> tuple[datetime, ...]:
    observed = _utc(observed_at, "observed_at")
    stop = _utc(hard_stop, "hard_stop")
    local_observed = observed.astimezone(_MOSCOW)
    rounded = local_observed.replace(second=0, microsecond=0)
    if rounded < local_observed:
        rounded += timedelta(minutes=1)
    candidates = [rounded + timedelta(minutes=delay) for delay in (10, 30, 60, 180)]
    next_day = local_observed.date() + timedelta(days=1)
    candidates.extend(
        datetime(
            next_day.year,
            next_day.month,
            next_day.day,
            hour,
            minute,
            tzinfo=_MOSCOW,
        )
        for hour, minute in ((8, 0), (10, 30), (12, 0))
    )
    stop_local = stop.astimezone(_MOSCOW)
    hourly_retry = datetime(
        stop_local.year,
        stop_local.month,
        stop_local.day,
        13,
        0,
        tzinfo=_MOSCOW,
    )
    while hourly_retry.astimezone(timezone.utc) < stop:
        candidates.append(hourly_retry)
        hourly_retry += timedelta(hours=1)
    return tuple(
        sorted(
            {
                value.astimezone(timezone.utc)
                for value in candidates
                if value.date() in {local_observed.date(), next_day}
                and observed < value.astimezone(timezone.utc) < stop
            }
        )
    )


def _review_queue_payload(
    evidence: MorningPreparedDrawing,
    *,
    observed_at: datetime,
) -> dict[str, object]:
    records = []
    for item in evidence.unresolved_events:
        if item.required_evidence_type != "reviewed_schedule":
            continue
        template = {
            "evidence_id": None,
            "drawing_id": evidence.drawing_id,
            "drawing_number": evidence.drawing_number,
            "target_fingerprint": evidence.drawing_fingerprint,
            "event_order": item.event_order,
            "target_event_id": item.target_event_id,
            "reviewer": None,
            "reviewed_at": None,
            "claims": [
                {
                    "role": "official",
                    "source_url": None,
                    "snapshot_path": None,
                    "snapshot_sha256": None,
                    "captured_at": None,
                    "home_name": item.home_team,
                    "away_name": item.away_team,
                    "starts_at": None,
                    "status": "scheduled",
                },
                {
                    "role": "independent",
                    "source_url": None,
                    "snapshot_path": None,
                    "snapshot_sha256": None,
                    "captured_at": None,
                    "home_name": item.home_team,
                    "away_name": item.away_team,
                    "starts_at": None,
                    "status": "scheduled",
                },
            ],
        }
        records.append(
            {
                "status": "awaiting_review",
                "drawing_id": evidence.drawing_id,
                "drawing_number": evidence.drawing_number,
                "target_fingerprint": evidence.drawing_fingerprint,
                "event_order": item.event_order,
                "target_event_id": item.target_event_id,
                "home_team": item.home_team,
                "away_team": item.away_team,
                "source_fixture_id": None,
                "requirements": {
                    "minimum_https_sources": 2,
                    "required_roles": ["official", "independent"],
                    "exact_team_and_start_agreement": True,
                    "snapshot_sha256_required": True,
                    "freshness_required": True,
                    "reviewer_required": True,
                    "fake_api_fixture_ids_forbidden": True,
                },
                "template": template,
            }
        )
    payload: dict[str, object] = {
        "schema_version": PREFLIGHT_ESCALATION_SCHEMA_VERSION,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": _timestamp(observed_at),
        "identity": evidence.identity_payload(),
        "records": records,
    }
    payload["queue_sha256"] = _record_sha256(payload)
    return payload


def _render_attempt_report(payload: Mapping[str, object]) -> str:
    return _render_attention_report(payload)


def _render_attention_report(payload: Mapping[str, object]) -> str:
    lines = [
        f"# {payload['status']}",
        "",
        f"- First seen: {payload.get('first_seen', payload.get('captured_at'))}",
        f"- Last seen: {payload.get('last_seen', payload.get('captured_at'))}",
        f"- Next retry: {payload.get('next_retry') or 'none before hard stop'}",
        "- Evening activation: "
        + (
            "enabled only after a retry becomes fully playable"
            if payload.get("activate_evening") is True
            else "disabled"
        ),
        "",
        "## Unresolved events",
        "",
    ]
    for item in payload.get("unresolved", []):
        if not isinstance(item, Mapping):
            continue
        lines.extend(
            (
                f"### #{int(item['event_order']) + 1}: "
                f"{item['home_team']} — {item['away_team']}",
                "",
                f"- Status: `{item['resolution_status']}`",
                f"- Reason: {item['reason']}",
                f"- Required evidence: `{item['required_evidence_type']}`",
                "",
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _load_json_mapping(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("preflight artifact must be an object")
    return payload


def _write_json_idempotent(path: Path, payload: Mapping[str, object]) -> bool:
    expected = _canonical(payload) + b"\n"
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"existing preflight artifact conflicts: {path}")
        return False
    _write_atomic(path, payload, replace=False)
    return True


def _write_text_idempotent(path: Path, content: str) -> None:
    expected = content.encode("utf-8")
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"existing preflight text artifact conflicts: {path}")
        return
    _write_bytes(path, expected, replace=False)


def _refresh_generated_report(path: Path, content: str) -> None:
    expected = content.encode("utf-8")
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"existing preflight text artifact conflicts: {path}")
        existing = path.read_bytes()
        if existing == expected:
            return
        if not (
            existing.startswith(b"# ACTION REQUIRED: unresolved ")
            or existing.startswith(b"# ACTION REQUIRED: timing unknown ")
            or existing.startswith(b"# totobrief_pool_not_ready\n")
        ):
            raise ValueError(f"existing preflight text artifact conflicts: {path}")
    _write_bytes(path, expected, replace=path.exists())


def _refresh_generated_notify_command(
    path: Path,
    content: str,
    *,
    drawing_number: int,
) -> None:
    expected = content.encode("utf-8")
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"existing preflight text artifact conflicts: {path}")
        existing = path.read_bytes()
        if existing == expected:
            return
        prefix = b"/usr/bin/osascript -e 'display notification \""
        suffix = f'" with title "TotoAI drawing {drawing_number}"\'\n'.encode()
        if not existing.startswith(prefix) or not existing.endswith(suffix):
            raise ValueError(f"existing preflight text artifact conflicts: {path}")
    _write_bytes(path, expected, replace=path.exists())


def _write_bytes(path: Path, content: bytes, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
