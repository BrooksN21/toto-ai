"""Tracked T-45/T-30/T-20/T-16/T-10 production package scheduler.

The scheduler deliberately separates a process completing from an actionable
package becoming ``BET READY``. Package-producing work happens in immutable
phase scopes; the T-10 cutoff verifies the selected bytes and every pinned
scheduler input before an exclusive publication and marker write.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import plistlib
import re
import secrets
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from toto_ai.api.client import TotoBriefClient
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.drawing import resolve_open_drawing_from_api
from toto_ai.ev.models import EVConfig, validate_config_bank
from toto_ai.external_odds.matching import load_aliases
from toto_ai.external_odds.reviewed_schedule import (
    load_reviewed_schedule_catalog,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.timing_overrides import (
    load_timing_override_catalog,
    timing_override_catalog_sha256,
)
from toto_ai.operations.finished_draw import import_prebet_package_manifest
from toto_ai.package.audit import (
    PackageSafetyConfig,
    evaluate_package_safety,
)
from toto_ai.runner.final_input import (
    FinalInputSnapshot,
    capture_final_input,
    load_final_input,
)
from toto_ai.runner.scheduler_state import (
    load_state,
    recover_orphan,
    save_state,
    scheduler_lock,
    transition,
)

SCHEDULER_SCHEMA_VERSION = 5
LEGACY_SCHEDULER_SCHEMA_VERSION = 1
LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION = 2
LEGACY_ACTIONABLE_SCHEMA_VERSION = 3
STALE_T12_SCHEDULER_SCHEMA_VERSION = 4
RUNNER_MANIFEST_SCHEMA_VERSION = 5
SCHEDULER_PLAN_FILENAME = "scheduler-plan.json"
SCHEDULER_WRAPPER_FILENAME = "run-scheduler.sh"
SCHEDULER_LAUNCH_AGENT_FILENAME = "totoai-scheduler.plist"
MORNING_WRAPPER_FILENAME = "run-morning-preanalysis.sh"
MORNING_LAUNCH_AGENT_FILENAME = "totoai-morning-preanalysis.plist"
PACKAGE_CSV_HEADER = ("rank", "coupon", "gross_ev", "net_ev")
DEFAULT_MINIMUM_GROSS_EV = EVConfig(
    bank=30,
    mode="playable",
).min_gross_ev
DEFAULT_PACKAGE_SAFETY_CONFIG = PackageSafetyConfig()
PUBLICATION_LEAD_MINUTES = 10
SCHEDULER_TRIGGER_OFFSETS_MINUTES = (45, 30, 20, 16, 10)

SchedulerPhase = Literal["preflight", "fallback", "final", "freeze"]
PackagePhase = Literal["fallback", "final"]
SchedulerOutcome = Literal["bet-ready", "no-bet", "failed", "ignored"]
PhaseDecision = Literal["PLAY", "NO BET"]

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_COUPON_PATTERN = re.compile(r"[1X2]{15}\Z")
_MOSCOW = ZoneInfo("Europe/Moscow")
_TIMING_PAYLOAD_FIELDS = {
    "status",
    "reason",
    "target_fingerprint",
    "fingerprint_match",
    "span_days",
    "missing_event_orders",
    "totobrief_count",
    "provider_count",
    "operator_override_count",
    "earliest_start",
    "latest_start",
}
_PHASES: tuple[SchedulerPhase, ...] = (
    "preflight",
    "fallback",
    "final",
    "freeze",
)


class SchedulerError(RuntimeError):
    """Base error for controlled scheduler failures."""


class SchedulerPhaseError(SchedulerError):
    """A package phase failed without making a package actionable."""


class SchedulerPublicationDeadlineError(SchedulerPhaseError):
    """Publication crossed the hard T-10 boundary without integrity loss."""


class SchedulerTransientError(SchedulerPhaseError):
    """A typed retryable scheduler failure."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "transient",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class SchedulerPermanentError(SchedulerPhaseError):
    """A typed non-retryable scheduler failure."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "permanent",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class SchedulerIntegrityError(SchedulerPermanentError):
    """A typed integrity/identity failure that must terminate final."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "integrity",
        status_code: int | None = None,
    ) -> None:
        super().__init__(
            message,
            category=category,
            status_code=status_code,
        )


class _NonProductionArtifact(SchedulerError):
    """A valid non-production artifact stops without terminal markers."""


@dataclass(frozen=True)
class SchedulerPlan:
    """One exact drawing schedule anchored only to BaltBet ``ended_at``."""

    drawing: int
    ended_at: datetime
    requested_bank: int
    output_dir: Path
    project_root: Path
    drawing_id: int | None = None
    stake: int = 30
    minimum_gross_ev: float = DEFAULT_MINIMUM_GROSS_EV
    package_near_fixed_share: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.near_fixed_share
    )
    package_low_probability_threshold: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.low_probability_threshold
    )
    package_material_probability_threshold: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.material_probability_threshold
    )
    db: Path = Path("data/toto.db")
    aliases: Path = Path("data/external-odds/team-aliases.json")
    timing_overrides: Path | None = None
    reviewed_schedule_catalog: Path | None = None
    reviewed_catalog_sha256: str | None = None
    env_file: Path | None = None
    provider: str = "api-sports"
    quota_reserve: int = 10
    max_passes: int = 3
    max_expansion_passes: int = 3
    retry_delay_seconds: float = 65.0
    minimum_final_runtime_seconds: int = 180
    publication_reserve_seconds: int = 45
    max_final_attempts: int = 2
    transient_backoff_seconds: tuple[int, ...] = (2, 5, 10)
    actionable_safety_bound: bool = True
    source_schema_version: int = SCHEDULER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_positive_int("drawing", self.drawing)
        if not isinstance(self.actionable_safety_bound, bool):
            raise ValueError("actionable_safety_bound must be a bool")
        if self.drawing_id is not None:
            _require_positive_int("drawing_id", self.drawing_id)
        object.__setattr__(
            self,
            "ended_at",
            _require_utc_datetime("ended_at", self.ended_at),
        )
        validate_config_bank(self.requested_bank, self.stake)
        if not isinstance(self.minimum_gross_ev, (int, float)) or isinstance(
            self.minimum_gross_ev,
            bool,
        ):
            raise ValueError("minimum_gross_ev must be finite")
        try:
            minimum_gross_ev = float(self.minimum_gross_ev)
        except (OverflowError, TypeError, ValueError) as error:
            raise ValueError("minimum_gross_ev must be finite") from error
        if not math.isfinite(minimum_gross_ev):
            raise ValueError("minimum_gross_ev must be finite")
        object.__setattr__(
            self,
            "minimum_gross_ev",
            minimum_gross_ev,
        )
        safety_config = self.package_safety_config
        object.__setattr__(
            self, "package_near_fixed_share", safety_config.near_fixed_share
        )
        object.__setattr__(
            self,
            "package_low_probability_threshold",
            safety_config.low_probability_threshold,
        )
        object.__setattr__(
            self,
            "package_material_probability_threshold",
            safety_config.material_probability_threshold,
        )
        project_root = _validated_project_root(self.project_root)
        object.__setattr__(self, "project_root", project_root)
        object.__setattr__(
            self,
            "output_dir",
            _validated_project_path(
                project_root,
                self.output_dir,
                name="scheduler output_dir",
            ),
        )
        object.__setattr__(
            self,
            "db",
            _validated_project_path(
                project_root,
                self.db,
                name="scheduler database",
            ),
        )
        object.__setattr__(
            self,
            "aliases",
            _validated_project_path(
                project_root,
                self.aliases,
                name="scheduler aliases",
            ),
        )
        if self.timing_overrides is not None:
            object.__setattr__(
                self,
                "timing_overrides",
                _normalized_path(self.timing_overrides),
            )
        if self.reviewed_schedule_catalog is not None:
            object.__setattr__(
                self,
                "reviewed_schedule_catalog",
                _validated_project_path(
                    project_root,
                    self.reviewed_schedule_catalog,
                    name="reviewed schedule catalog",
                ),
            )
            catalog_path = self.reviewed_schedule_catalog
            if not catalog_path.is_file() or catalog_path.is_symlink():
                raise ValueError(
                    "reviewed schedule catalog must be a regular file"
                )
            observed_hash = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
            if (
                self.reviewed_catalog_sha256 is not None
                and self.reviewed_catalog_sha256 != observed_hash
            ):
                raise ValueError("reviewed schedule catalog content changed")
            object.__setattr__(
                self, "reviewed_catalog_sha256", observed_hash
            )
        elif self.reviewed_catalog_sha256 is not None:
            raise ValueError(
                "reviewed_catalog_sha256 requires reviewed schedule catalog"
            )
        if self.env_file is not None:
            object.__setattr__(
                self,
                "env_file",
                _normalized_path(self.env_file),
            )
        if self.provider != "api-sports":
            raise ValueError("provider must be api-sports")
        _require_non_negative_int("quota_reserve", self.quota_reserve)
        _require_positive_int("max_passes", self.max_passes)
        _require_positive_int(
            "max_expansion_passes", self.max_expansion_passes
        )
        if (
            not isinstance(self.retry_delay_seconds, (int, float))
            or isinstance(self.retry_delay_seconds, bool)
            or not 0 <= float(self.retry_delay_seconds) < float("inf")
        ):
            raise ValueError("retry_delay_seconds must be finite and non-negative")
        object.__setattr__(
            self,
            "retry_delay_seconds",
            float(self.retry_delay_seconds),
        )
        _require_positive_int(
            "minimum_final_runtime_seconds", self.minimum_final_runtime_seconds
        )
        _require_non_negative_int(
            "publication_reserve_seconds", self.publication_reserve_seconds
        )
        _require_positive_int("max_final_attempts", self.max_final_attempts)
        if self.source_schema_version not in {
            LEGACY_SCHEDULER_SCHEMA_VERSION,
            LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION,
            LEGACY_ACTIONABLE_SCHEMA_VERSION,
            SCHEDULER_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported scheduler source schema")
        if (
            not isinstance(self.transient_backoff_seconds, tuple)
            or not self.transient_backoff_seconds
            or any(
                type(value) is not int or value < 0
                for value in self.transient_backoff_seconds
            )
        ):
            raise ValueError("transient_backoff_seconds must be non-negative integers")

    @property
    def preflight_at(self) -> datetime:
        return self.ended_at - timedelta(minutes=45)

    @property
    def fallback_at(self) -> datetime:
        return self.ended_at - timedelta(minutes=30)

    @property
    def final_at(self) -> datetime:
        return self.ended_at - timedelta(minutes=20)

    @property
    def retry_at(self) -> datetime:
        return self.ended_at - timedelta(minutes=16)

    @property
    def publish_deadline(self) -> datetime:
        return self.ended_at - timedelta(minutes=PUBLICATION_LEAD_MINUTES)

    @property
    def actionable_publication_deadline(self) -> datetime:
        """Latest instant that still preserves the configured T-10 reserve."""
        return self.publish_deadline - timedelta(
            seconds=self.publication_reserve_seconds
        )

    @property
    def freeze_at(self) -> datetime:
        """Compatibility alias for the hard publication deadline."""
        return self.publish_deadline

    @property
    def deadlines(self) -> dict[str, datetime]:
        return {
            "ended_at": self.ended_at,
            "t_minus_45": self.preflight_at,
            "t_minus_30": self.fallback_at,
            "t_minus_20": self.final_at,
            "t_minus_16": self.retry_at,
            "t_minus_10": self.publish_deadline,
        }

    @property
    def package_safety_config(self) -> PackageSafetyConfig:
        return PackageSafetyConfig(
            near_fixed_share=self.package_near_fixed_share,
            low_probability_threshold=self.package_low_probability_threshold,
            material_probability_threshold=(
                self.package_material_probability_threshold
            ),
        )

    @property
    def plan_id(self) -> str:
        return hashlib.sha256(
            _canonical_json_bytes(self.semantic_payload())
        ).hexdigest()[:16]

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "target": {
                "drawing": self.drawing,
                "drawing_id": self.drawing_id,
                "ended_at": _timestamp(self.ended_at),
            },
            "config": {
                "requested_bank": self.requested_bank,
                "stake": self.stake,
                "minimum_gross_ev": self.minimum_gross_ev,
                "package_near_fixed_share": self.package_near_fixed_share,
                "package_low_probability_threshold": (
                    self.package_low_probability_threshold
                ),
                "package_material_probability_threshold": (
                    self.package_material_probability_threshold
                ),
                "provider": self.provider,
                "quota_reserve": self.quota_reserve,
                "max_passes": self.max_passes,
                "max_expansion_passes": self.max_expansion_passes,
                "retry_delay_seconds": self.retry_delay_seconds,
                "minimum_final_runtime_seconds": self.minimum_final_runtime_seconds,
                "publication_reserve_seconds": self.publication_reserve_seconds,
                "max_final_attempts": self.max_final_attempts,
                "transient_backoff_seconds": list(self.transient_backoff_seconds),
                "publication_lead_minutes": PUBLICATION_LEAD_MINUTES,
                "trigger_offsets_minutes": list(
                    SCHEDULER_TRIGGER_OFFSETS_MINUTES
                ),
            },
            "paths": {
                "project_root": str(self.project_root),
                "output_dir": str(self.output_dir),
                "db": str(self.db),
                "aliases": str(self.aliases),
                "timing_overrides": (
                    None
                    if self.timing_overrides is None
                    else str(self.timing_overrides)
                ),
                **(
                    {}
                    if self.reviewed_schedule_catalog is None
                    else {
                        "reviewed_schedule_catalog": str(
                            self.reviewed_schedule_catalog
                        ),
                        "reviewed_catalog_sha256": (
                            self.reviewed_catalog_sha256
                        ),
                    }
                ),
                **(
                    {}
                    if self.env_file is None
                    else {"env_file": str(self.env_file)}
                ),
            },
        }

    def to_payload(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["plan_id"] = self.plan_id
        payload["deadlines"] = {
            key: _timestamp(value) for key, value in self.deadlines.items()
        }
        return payload


@dataclass(frozen=True)
class SchedulerPhaseContext:
    """Immutable handoff to an injected preflight/package phase runner."""

    phase: Literal["preflight", "fallback", "final"]
    plan: SchedulerPlan
    run_id: str
    run_dir: Path
    work_dir: Path
    scheduled_at: datetime
    started_at: datetime
    override_sha256: str | None = None
    final_inputs_sha256: str | None = None
    atomic_final: bool = False


@dataclass(frozen=True)
class SchedulerPhaseResult:
    """Result returned by a phase runner before scheduler-owned publication."""

    status: Literal["complete", "failed", "ignored"] = "complete"
    decision: PhaseDecision | None = None
    reason: str = "phase completed"
    package_bytes: bytes | None = None
    package_path: Path | None = None
    package_sha256: str | None = None
    effective_bank: int | None = None
    selected_count: int | None = None
    selected_cost: int | None = None
    override_sha256: str | None = None
    final_inputs_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("complete", "failed", "ignored"):
            raise ValueError(
                "phase result status must be complete, failed, or ignored"
            )
        if self.decision not in (None, "PLAY", "NO BET"):
            raise ValueError("phase decision must be PLAY, NO BET, or absent")
        _require_text("reason", self.reason)
        if self.package_bytes is not None and not isinstance(
            self.package_bytes, bytes
        ):
            raise ValueError("package_bytes must be bytes")
        if self.package_path is not None:
            object.__setattr__(self, "package_path", Path(self.package_path))
        if self.package_bytes is not None and self.package_path is not None:
            raise ValueError("provide package_bytes or package_path, not both")
        if self.package_sha256 is not None:
            _require_sha256("package_sha256", self.package_sha256)
        if self.effective_bank is not None:
            _require_positive_int("effective_bank", self.effective_bank)
        if self.selected_count is not None:
            _require_positive_int("selected_count", self.selected_count)
        if self.selected_cost is not None:
            _require_positive_int("selected_cost", self.selected_cost)
        if self.override_sha256 is not None:
            _require_sha256("override_sha256", self.override_sha256)
        if self.final_inputs_sha256 is not None:
            _require_sha256(
                "final_inputs_sha256", self.final_inputs_sha256
            )

    @classmethod
    def completed(cls, reason: str = "phase completed") -> SchedulerPhaseResult:
        return cls(reason=reason)

    @classmethod
    def no_bet(cls, reason: str) -> SchedulerPhaseResult:
        return cls(decision="NO BET", reason=reason)

    @classmethod
    def play(
        cls,
        package: bytes | Path,
        *,
        reason: str = "PLAY package created",
        effective_bank: int,
        selected_count: int | None = None,
        selected_cost: int | None = None,
        override_sha256: str | None = None,
        final_inputs_sha256: str | None = None,
        package_sha256: str | None = None,
    ) -> SchedulerPhaseResult:
        return cls(
            decision="PLAY",
            reason=reason,
            package_bytes=package if isinstance(package, bytes) else None,
            package_path=package if isinstance(package, Path) else None,
            package_sha256=package_sha256,
            effective_bank=effective_bank,
            selected_count=selected_count,
            selected_cost=selected_cost,
            override_sha256=override_sha256,
            final_inputs_sha256=final_inputs_sha256,
        )

    @classmethod
    def failed(cls, reason: str) -> SchedulerPhaseResult:
        return cls(status="failed", reason=reason)

    @classmethod
    def ignored(cls, reason: str) -> SchedulerPhaseResult:
        return cls(status="ignored", reason=reason)


class SchedulerPhaseRunner(Protocol):
    def __call__(self, context: SchedulerPhaseContext) -> SchedulerPhaseResult: ...


@dataclass(frozen=True)
class PackageSnapshot:
    phase: PackagePhase
    path: Path
    sha256: str
    completed_at: datetime
    effective_bank: int
    selected_count: int
    selected_cost: int
    override_sha256: str | None
    final_inputs_sha256: str | None


@dataclass(frozen=True)
class SchedulerExecutionResult:
    outcome: SchedulerOutcome
    decision: Literal["PLAY", "NO BET", "FAILED", "IGNORED"]
    reason: str
    drawing: int
    run_id: str
    run_dir: Path
    status_path: Path
    marker_path: Path | None
    package_path: Path | None
    package_sha256: str | None
    requested_bank: int
    effective_bank: int | None


@dataclass(frozen=True)
class SchedulerArtifacts:
    plan_path: Path
    wrapper_path: Path
    launch_agent_path: Path


@dataclass(frozen=True)
class MorningPreanalysisArtifacts:
    wrapper_path: Path
    launch_agent_path: Path


def build_scheduler_plan(
    *,
    drawing: int,
    ended_at: datetime | str,
    bank: int,
    output_dir: str | Path,
    project_root: str | Path | None = None,
    drawing_id: int | None = None,
    stake: int = 30,
    minimum_gross_ev: float = DEFAULT_MINIMUM_GROSS_EV,
    package_near_fixed_share: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.near_fixed_share
    ),
    package_low_probability_threshold: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.low_probability_threshold
    ),
    package_material_probability_threshold: float = (
        DEFAULT_PACKAGE_SAFETY_CONFIG.material_probability_threshold
    ),
    db: str | Path = "data/toto.db",
    aliases: str | Path = "data/external-odds/team-aliases.json",
    timing_overrides: str | Path | None = None,
    reviewed_schedule_catalog: str | Path | None = None,
    reviewed_catalog_sha256: str | None = None,
    env_file: str | Path | None = None,
    provider: str = "api-sports",
    quota_reserve: int = 10,
    max_passes: int = 3,
    max_expansion_passes: int = 3,
    retry_delay_seconds: float = 65.0,
    minimum_final_runtime_seconds: int = 180,
    publication_reserve_seconds: int = 45,
    max_final_attempts: int = 2,
    transient_backoff_seconds: tuple[int, ...] = (2, 5, 10),
    _allow_missing_drawing_id: bool = False,
    _actionable_safety_bound: bool = True,
    source_schema_version: int = SCHEDULER_SCHEMA_VERSION,
) -> SchedulerPlan:
    """Build a strict plan; null or malformed ``ended_at`` fails immediately."""

    parsed_ended_at = _parse_utc_datetime("ended_at", ended_at)
    if drawing_id is None and not _allow_missing_drawing_id:
        raise ValueError("drawing_id is required for actionable scheduler plans")
    normalized_output = _normalized_path(output_dir)
    normalized_db = _normalized_path(db)
    normalized_aliases = _normalized_path(aliases)
    root = _normalized_path(
        Path(__file__).resolve().parents[3]
        if project_root is None
        else project_root
    )
    return SchedulerPlan(
        drawing=drawing,
        drawing_id=drawing_id,
        ended_at=parsed_ended_at,
        requested_bank=bank,
        stake=stake,
        minimum_gross_ev=minimum_gross_ev,
        package_near_fixed_share=package_near_fixed_share,
        package_low_probability_threshold=package_low_probability_threshold,
        package_material_probability_threshold=(
            package_material_probability_threshold
        ),
        output_dir=normalized_output,
        project_root=root,
        db=normalized_db,
        aliases=normalized_aliases,
        timing_overrides=(
            None if timing_overrides is None else Path(timing_overrides)
        ),
        reviewed_schedule_catalog=(
            None
            if reviewed_schedule_catalog is None
            else Path(reviewed_schedule_catalog)
        ),
        reviewed_catalog_sha256=reviewed_catalog_sha256,
        env_file=None if env_file is None else Path(env_file),
        provider=provider,
        quota_reserve=quota_reserve,
        max_passes=max_passes,
        max_expansion_passes=max_expansion_passes,
        retry_delay_seconds=retry_delay_seconds,
        minimum_final_runtime_seconds=minimum_final_runtime_seconds,
        publication_reserve_seconds=publication_reserve_seconds,
        max_final_attempts=max_final_attempts,
        transient_backoff_seconds=transient_backoff_seconds,
        actionable_safety_bound=_actionable_safety_bound,
        source_schema_version=source_schema_version,
    )


def scheduler_plan_json(plan: SchedulerPlan) -> str:
    _require_plan(plan)
    return _canonical_json_bytes(plan.to_payload()).decode("utf-8") + "\n"


def scheduler_launch_agent_label(plan: SchedulerPlan) -> str:
    """Return the only LaunchAgent label valid for this schema-v5 plan."""
    _require_plan(plan)
    if plan.source_schema_version != SCHEDULER_SCHEMA_VERSION:
        raise ValueError(
            "legacy scheduler plans cannot derive a production LaunchAgent label"
        )
    return (
        "com.totoai.production-scheduler."
        f"v{SCHEDULER_SCHEMA_VERSION}.{plan.plan_id}"
    )


def _infer_scheduler_project_root(
    *,
    output_dir: Path,
    db: Path,
    aliases: Path,
) -> Path:
    """Infer the root only for legacy schema-v1 plans.

    Version 1 stored absolute operational paths but omitted the root itself.
    Their common ancestor is the narrowest compatible migration boundary.
    """

    try:
        common = Path(
            os.path.commonpath((str(output_dir), str(db), str(aliases)))
        )
    except ValueError as error:
        raise ValueError(
            "legacy scheduler plan project_root cannot be inferred"
        ) from error
    root = _normalized_path(common)
    if root == Path(root.anchor):
        raise ValueError(
            "legacy scheduler plan project_root inference is too broad"
        )
    return root


def _legacy_scheduler_plan_id(payload: Mapping[str, Any]) -> str:
    semantic = {
        "schema_version": payload["schema_version"],
        "target": payload["target"],
        "config": payload["config"],
        "paths": payload["paths"],
    }
    return hashlib.sha256(_canonical_json_bytes(semantic)).hexdigest()[:16]


def load_scheduler_plan(path: str | Path) -> SchedulerPlan:
    plan_path = _normalized_path(path)
    try:
        payload = _load_strict_json(plan_path, name="scheduler plan")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"scheduler plan could not be loaded: {error}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("scheduler plan must be a JSON object")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "plan_id",
            "target",
            "config",
            "paths",
            "deadlines",
        },
        "scheduler plan",
    )
    schema_version = payload["schema_version"]
    if schema_version == STALE_T12_SCHEDULER_SCHEMA_VERSION:
        raise ValueError(
            "stale scheduler schema v4 uses T-12 trigger semantics; "
            "regenerate schema v5"
        )
    if type(schema_version) is not int or schema_version not in {
        LEGACY_SCHEDULER_SCHEMA_VERSION,
        LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION,
        LEGACY_ACTIONABLE_SCHEMA_VERSION,
        SCHEDULER_SCHEMA_VERSION,
    }:
        raise ValueError(
            "scheduler plan schema_version must be "
            f"{LEGACY_SCHEDULER_SCHEMA_VERSION}, "
            f"{LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION}, or "
            f"{LEGACY_ACTIONABLE_SCHEMA_VERSION}, or "
            f"{SCHEDULER_SCHEMA_VERSION}"
        )
    target = _exact_mapping(
        payload["target"],
        {"drawing", "drawing_id", "ended_at"},
        "target",
    )
    base_config_keys = {
        "requested_bank",
        "stake",
        "minimum_gross_ev",
        "provider",
        "quota_reserve",
        "max_passes",
        "max_expansion_passes",
        "retry_delay_seconds",
    }
    tick_config_keys = {
        "minimum_final_runtime_seconds",
        "publication_reserve_seconds",
        "max_final_attempts",
        "transient_backoff_seconds",
    }
    trigger_config_keys = {
        "publication_lead_minutes",
        "trigger_offsets_minutes",
    }
    raw_config = payload["config"]
    if not isinstance(raw_config, Mapping):
        raise ValueError("config must be a JSON object")
    present_tick_keys = tick_config_keys & set(raw_config)
    if present_tick_keys and present_tick_keys != tick_config_keys:
        raise ValueError("config scheduler tick fields must be complete")
    if present_tick_keys:
        base_config_keys |= tick_config_keys
    if schema_version == SCHEDULER_SCHEMA_VERSION:
        base_config_keys |= trigger_config_keys
    safety_config_keys = {
        "package_near_fixed_share",
        "package_low_probability_threshold",
        "package_material_probability_threshold",
    }
    present_safety_keys = safety_config_keys & set(raw_config)
    if present_safety_keys and present_safety_keys != safety_config_keys:
        raise ValueError("config package safety thresholds must be complete")
    config = _exact_mapping(
        raw_config,
        base_config_keys | present_safety_keys,
        "config",
    )
    if schema_version == SCHEDULER_SCHEMA_VERSION and (
        config["publication_lead_minutes"] != PUBLICATION_LEAD_MINUTES
        or config["trigger_offsets_minutes"]
        != list(SCHEDULER_TRIGGER_OFFSETS_MINUTES)
    ):
        raise ValueError(
            "scheduler trigger semantics do not match schema v5; "
            "regenerate schema v5"
        )
    raw_paths = payload["paths"]
    if not isinstance(raw_paths, Mapping):
        raise ValueError("paths must be a JSON object")
    path_keys = {"output_dir", "db", "aliases", "timing_overrides"}
    if "reviewed_schedule_catalog" in raw_paths:
        path_keys.update(
            ("reviewed_schedule_catalog", "reviewed_catalog_sha256")
        )
    if schema_version in {
        LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION,
        LEGACY_ACTIONABLE_SCHEMA_VERSION,
        SCHEDULER_SCHEMA_VERSION,
    }:
        path_keys.add("project_root")
    if "env_file" in raw_paths:
        path_keys.add("env_file")
    paths = _exact_mapping(raw_paths, path_keys, "paths")
    plan = build_scheduler_plan(
        drawing=target["drawing"],
        drawing_id=target["drawing_id"],
        ended_at=target["ended_at"],
        bank=config["requested_bank"],
        stake=config["stake"],
        minimum_gross_ev=config["minimum_gross_ev"],
        package_near_fixed_share=config.get(
            "package_near_fixed_share",
            DEFAULT_PACKAGE_SAFETY_CONFIG.near_fixed_share,
        ),
        package_low_probability_threshold=config.get(
            "package_low_probability_threshold",
            DEFAULT_PACKAGE_SAFETY_CONFIG.low_probability_threshold,
        ),
        package_material_probability_threshold=config.get(
            "package_material_probability_threshold",
            DEFAULT_PACKAGE_SAFETY_CONFIG.material_probability_threshold,
        ),
        output_dir=paths["output_dir"],
        project_root=(
            paths["project_root"]
            if schema_version
            in {
                LEGACY_SAFETY_UNBOUND_SCHEMA_VERSION,
                LEGACY_ACTIONABLE_SCHEMA_VERSION,
                SCHEDULER_SCHEMA_VERSION,
            }
            else _infer_scheduler_project_root(
                output_dir=_normalized_path(paths["output_dir"]),
                db=_normalized_path(paths["db"]),
                aliases=_normalized_path(paths["aliases"]),
            )
        ),
        db=paths["db"],
        aliases=paths["aliases"],
        timing_overrides=paths["timing_overrides"],
        reviewed_schedule_catalog=paths.get("reviewed_schedule_catalog"),
        reviewed_catalog_sha256=paths.get("reviewed_catalog_sha256"),
        env_file=paths.get("env_file"),
        provider=config["provider"],
        quota_reserve=config["quota_reserve"],
        max_passes=config["max_passes"],
        max_expansion_passes=config["max_expansion_passes"],
        retry_delay_seconds=config["retry_delay_seconds"],
        minimum_final_runtime_seconds=config.get(
            "minimum_final_runtime_seconds", 180
        ),
        publication_reserve_seconds=config.get(
            "publication_reserve_seconds", 45
        ),
        max_final_attempts=config.get("max_final_attempts", 2),
        transient_backoff_seconds=tuple(
            config.get("transient_backoff_seconds", (2, 5, 10))
        ),
        _allow_missing_drawing_id=(
            schema_version != SCHEDULER_SCHEMA_VERSION
        ),
        _actionable_safety_bound=(
            schema_version == SCHEDULER_SCHEMA_VERSION
            and present_safety_keys == safety_config_keys
        ),
        source_schema_version=schema_version,
    )
    expected_plan_id = (
        plan.plan_id
        if schema_version == SCHEDULER_SCHEMA_VERSION
        else _legacy_scheduler_plan_id(payload)
    )
    if payload["plan_id"] != expected_plan_id:
        raise ValueError("scheduler plan_id does not match plan content")
    expected_deadlines = (
        {key: _timestamp(value) for key, value in plan.deadlines.items()}
        if schema_version == SCHEDULER_SCHEMA_VERSION
        else payload["deadlines"]
    )
    if payload["deadlines"] != expected_deadlines:
        raise ValueError("scheduler deadlines are not exact ended_at offsets")
    expected_plan_path = plan.output_dir / SCHEDULER_PLAN_FILENAME
    _require_contained_path(
        plan.output_dir,
        plan_path,
        name="scheduler plan path",
    )
    if plan_path != expected_plan_path:
        raise ValueError(
            "scheduler plan path must be the generated plan inside output_dir"
        )
    _require_regular_file(plan_path, name="scheduler plan", reject_symlink=True)
    return plan


def prepare_scheduler_artifacts(
    plan: SchedulerPlan,
    *,
    python_command: str | Path | None = None,
) -> SchedulerArtifacts:
    """Generate a tracked plan, generic wrapper, and LaunchAgent candidate.

    Nothing is installed.  Every artifact is generated below the explicit
    ``plan.output_dir`` and creation fails rather than overwriting an existing
    artifact.
    """

    _require_plan(plan)
    python_executable = _validated_python_executable(
        sys.executable if python_command is None else python_command
    )
    output_dir = plan.output_dir
    if plan.env_file is not None:
        _require_secure_env_file(plan.env_file)
    _ensure_output_directory(output_dir, output_dir)
    _reject_unsafe_output_descendants(output_dir)
    logs_dir = output_dir / "logs"
    _ensure_output_directory(output_dir, logs_dir)
    plan_path = output_dir / SCHEDULER_PLAN_FILENAME
    wrapper_path = output_dir / SCHEDULER_WRAPPER_FILENAME
    launch_agent_path = output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME
    _reject_stale_t12_scheduler_artifact(plan_path)
    created: list[Path] = []
    try:
        _write_exclusive_atomic(
            output_dir,
            plan_path,
            scheduler_plan_json(plan).encode("utf-8"),
        )
        created.append(plan_path)
        wrapper = _render_scheduler_wrapper(
            plan_path=plan_path,
            project_root=plan.project_root,
            python_executable=python_executable,
            env_file=plan.env_file,
        )
        _write_exclusive_atomic(
            output_dir,
            wrapper_path,
            wrapper.encode("utf-8"),
            mode=0o755,
        )
        created.append(wrapper_path)
        launch_agent = _render_launch_agent(
            plan,
            wrapper_path=wrapper_path,
            logs_dir=logs_dir,
        )
        _write_exclusive_atomic(output_dir, launch_agent_path, launch_agent)
        created.append(launch_agent_path)
    except BaseException:
        for path in reversed(created):
            _unlink_output_path(output_dir, path)
        raise
    return SchedulerArtifacts(
        plan_path=plan_path,
        wrapper_path=wrapper_path,
        launch_agent_path=launch_agent_path,
    )


def verify_scheduler_artifacts(
    plan: SchedulerPlan,
    *,
    python_command: str | Path | None = None,
) -> SchedulerArtifacts:
    """Verify and reuse an exact previously generated scheduler artifact set."""

    _require_plan(plan)
    python_executable = _validated_python_executable(
        sys.executable if python_command is None else python_command
    )
    if plan.env_file is not None:
        _require_secure_env_file(plan.env_file)
    output_dir = plan.output_dir
    _require_output_directory(output_dir, output_dir)
    _reject_unsafe_output_descendants(output_dir)
    logs_dir = output_dir / "logs"
    _require_output_directory(output_dir, logs_dir)
    artifacts = SchedulerArtifacts(
        plan_path=output_dir / SCHEDULER_PLAN_FILENAME,
        wrapper_path=output_dir / SCHEDULER_WRAPPER_FILENAME,
        launch_agent_path=output_dir / SCHEDULER_LAUNCH_AGENT_FILENAME,
    )
    _reject_stale_t12_scheduler_artifact(artifacts.plan_path)
    expected = {
        artifacts.plan_path: scheduler_plan_json(plan).encode("utf-8"),
        artifacts.wrapper_path: _render_scheduler_wrapper(
            plan_path=artifacts.plan_path,
            project_root=plan.project_root,
            python_executable=python_executable,
            env_file=plan.env_file,
        ).encode("utf-8"),
        artifacts.launch_agent_path: _render_launch_agent(
            plan,
            wrapper_path=artifacts.wrapper_path,
            logs_dir=logs_dir,
        ),
    }
    for path, content in expected.items():
        try:
            observed = _read_regular_file(
                path,
                name=f"scheduler artifact {path.name}",
                reject_symlink=True,
            )
        except (OSError, SchedulerError) as error:
            raise SchedulerIntegrityError(
                "existing scheduler artifact set is incomplete or unsafe",
                category="scheduler_artifact_integrity",
            ) from error
        if observed != content:
            raise SchedulerIntegrityError(
                f"existing scheduler artifact {path.name} conflicts",
                category="scheduler_artifact_integrity",
            )
    return artifacts


def prepare_morning_preanalysis_artifacts(
    *,
    times: Sequence[str],
    retry_count: int,
    retry_delay_seconds: float,
    output_dir: str | Path,
    env_file: str | Path,
    project_root: str | Path,
    bank: int,
    stake: int = 30,
    activate_evening: bool = False,
    reviewed_schedule_catalog: str | Path | None = None,
    python_command: str | Path | None = None,
) -> MorningPreanalysisArtifacts:
    """Generate, but never install, a non-betting morning launchd candidate."""
    validate_config_bank(bank, stake)
    _require_non_negative_int("retry_count", retry_count)
    if (
        not isinstance(retry_delay_seconds, (int, float))
        or isinstance(retry_delay_seconds, bool)
        or not math.isfinite(float(retry_delay_seconds))
        or float(retry_delay_seconds) < 0
    ):
        raise ValueError("retry_delay_seconds must be finite and non-negative")
    parsed_times = tuple(dict.fromkeys(_parse_morning_time(value) for value in times))
    if not parsed_times:
        raise ValueError("at least one morning time is required")
    root = _normalized_path(project_root)
    _require_directory_no_symlink(root, name="project root")
    rehearsal_root = root / "reports" / "rehearsal"
    destination = _normalized_path(output_dir)
    _require_contained_path(
        root,
        destination,
        name="morning preanalysis output",
    )
    _require_contained_path(
        rehearsal_root,
        destination,
        name="morning preanalysis output",
    )
    environment_path = _normalized_path(env_file)
    _require_secure_env_file(environment_path)
    python_executable = _validated_python_executable(
        sys.executable if python_command is None else python_command
    )

    _ensure_output_directory(destination, destination)
    _reject_unsafe_output_descendants(destination)
    logs_dir = destination / "logs"
    _ensure_output_directory(destination, logs_dir)
    wrapper_path = destination / MORNING_WRAPPER_FILENAME
    launch_agent_path = destination / MORNING_LAUNCH_AGENT_FILENAME
    created: list[Path] = []
    try:
        wrapper = _render_morning_preanalysis_wrapper(
            retry_count=retry_count,
            retry_delay_seconds=float(retry_delay_seconds),
            env_file=environment_path,
            project_root=root,
            bank=bank,
            stake=stake,
            activate_evening=activate_evening,
            reviewed_schedule_catalog=(
                None
                if reviewed_schedule_catalog is None
                else _normalized_path(reviewed_schedule_catalog)
            ),
            python_executable=python_executable,
        )
        _write_exclusive_atomic(
            destination,
            wrapper_path,
            wrapper.encode("utf-8"),
            mode=0o755,
        )
        created.append(wrapper_path)
        launch_agent = _render_morning_launch_agent(
            times=parsed_times,
            wrapper_path=wrapper_path,
            logs_dir=logs_dir,
            project_root=root,
        )
        _write_exclusive_atomic(destination, launch_agent_path, launch_agent)
        created.append(launch_agent_path)
    except BaseException:
        for path in reversed(created):
            _unlink_output_path(destination, path)
        raise
    return MorningPreanalysisArtifacts(wrapper_path, launch_agent_path)


def execute_scheduler_plan(
    plan: SchedulerPlan,
    *,
    phase_runner: SchedulerPhaseRunner,
    now: Callable[[], datetime],
    sleep: Callable[[float], object],
    run_id: str | None = None,
    honor_prior_bet_ready: bool = True,
) -> SchedulerExecutionResult:
    """Execute one plan with injected time and phase dependencies."""

    _require_plan(plan)
    if not isinstance(honor_prior_bet_ready, bool):
        raise ValueError("honor_prior_bet_ready must be a boolean")
    _ensure_output_directory(plan.output_dir, plan.output_dir)
    _reject_unsafe_output_descendants(plan.output_dir)
    prior_marker = _find_existing_bet_ready_marker(plan)
    if prior_marker is not None:
        raise SchedulerError(
            "BET READY was already published for this drawing; "
            f"refusing a duplicate scheduler execution ({prior_marker})"
        )

    initial_now = _read_now(now)
    resolved_run_id = run_id or _new_run_id(initial_now)
    _require_run_id(resolved_run_id)
    drawing_root = plan.output_dir / "runs" / str(plan.drawing)
    _ensure_output_directory(plan.output_dir, drawing_root)
    run_dir = drawing_root / resolved_run_id
    try:
        _create_output_directory_exclusive(plan.output_dir, run_dir)
    except FileExistsError as error:
        raise SchedulerError(
            f"scheduler run scope already exists: {run_dir}"
        ) from error
    status_path = run_dir / "status.json"
    phase_state = _initial_phase_state(plan)
    status = _base_status(plan, resolved_run_id, run_dir, phase_state)
    _write_exclusive_atomic(
        plan.output_dir,
        status_path,
        _canonical_json_bytes(status) + b"\n",
    )

    snapshots: dict[PackagePhase, PackageSnapshot] = {}
    phase_errors: list[str] = []
    phase_absences: list[str] = []
    final_inputs_sha256: str | None = None
    final_override_sha256: str | None = None

    try:
        if _read_now(now) > plan.freeze_at:
            phase_absences.append("execution began after T-10; no work recalculated")
        else:
            _wait_until(plan.preflight_at, now=now, sleep=sleep)
            preflight_started = _read_now(now)
            _phase_started(
                phase_state,
                "preflight",
                scheduled_at=plan.preflight_at,
                started_at=preflight_started,
            )
            _write_status_atomic(plan.output_dir, status_path, status)
            _validate_preflight_inputs(plan)
            preflight_context = _phase_context(
                plan,
                resolved_run_id,
                run_dir,
                phase="preflight",
                scheduled_at=plan.preflight_at,
                started_at=preflight_started,
            )
            preflight_result = _call_phase_runner(phase_runner, preflight_context)
            if preflight_result.status != "complete":
                raise SchedulerPhaseError(preflight_result.reason)
            preflight_finished = _read_now(now)
            _phase_finished(
                phase_state,
                "preflight",
                finished_at=preflight_finished,
                status="complete",
                reason=preflight_result.reason,
            )
            _write_status_atomic(plan.output_dir, status_path, status)

            if _read_now(now) < plan.freeze_at:
                snapshot = _execute_package_phase(
                    plan,
                    run_id=resolved_run_id,
                    run_dir=run_dir,
                    phase="fallback",
                    scheduled_at=plan.fallback_at,
                    phase_runner=phase_runner,
                    now=now,
                    sleep=sleep,
                    phase_state=phase_state,
                    status_path=status_path,
                    status=status,
                )
                if snapshot is not None:
                    snapshots["fallback"] = snapshot
                else:
                    reason = phase_state["fallback"].get("reason")
                    if reason:
                        message = f"fallback: {reason}"
                        phase_absences.append(
                            f"diagnostic {message}; fallback is never actionable"
                        )

            if _read_now(now) < plan.freeze_at:
                try:
                    # Pin scheduler inputs during the atomic-final phase, never
                    # during T-45/T-30 warmup or refresh. This intentionally
                    # permits a structurally valid operator catalog update
                    # during the review window.
                    _wait_until(plan.final_at, now=now, sleep=sleep)
                    final_override_sha256 = _current_override_sha256(plan)
                    final_inputs_sha256 = _final_inputs_sha256(
                        plan,
                        final_override_sha256,
                    )
                    snapshot = _execute_package_phase(
                        plan,
                        run_id=resolved_run_id,
                        run_dir=run_dir,
                        phase="final",
                        scheduled_at=plan.final_at,
                        phase_runner=phase_runner,
                        now=now,
                        sleep=sleep,
                        phase_state=phase_state,
                        status_path=status_path,
                        status=status,
                        override_sha256=final_override_sha256,
                        final_inputs_sha256=final_inputs_sha256,
                    )
                    if snapshot is not None:
                        snapshots["final"] = snapshot
                    else:
                        reason = phase_state["final"].get("reason")
                        if reason:
                            phase_absences.append(f"final: {reason}")
                except _NonProductionArtifact:
                    raise
                except Exception as error:
                    message = _safe_error(error)
                    phase_errors.append(f"final: {message}")
                    _ensure_phase_failure(
                        phase_state,
                        "final",
                        scheduled_at=plan.final_at,
                        observed_at=_read_now(now),
                        reason=message,
                    )
                    _write_status_atomic(plan.output_dir, status_path, status)

        _wait_until(plan.freeze_at, now=now, sleep=sleep)
        freeze_started = _read_now(now)
        _phase_started(
            phase_state,
            "freeze",
            scheduled_at=plan.freeze_at,
            started_at=freeze_started,
        )
        _write_status_atomic(plan.output_dir, status_path, status)
        terminal = _freeze_and_publish(
            plan,
            run_id=resolved_run_id,
            run_dir=run_dir,
            snapshots=snapshots,
            phase_errors=phase_errors,
            phase_absences=phase_absences,
            final_inputs_sha256=final_inputs_sha256,
            final_override_sha256=final_override_sha256,
            now=now,
        )
        freeze_finished = _read_now(now)
        _phase_finished(
            phase_state,
            "freeze",
            finished_at=freeze_finished,
            status="complete",
            reason=terminal["reason"],
        )
        return _finalize_status(
            plan,
            run_id=resolved_run_id,
            run_dir=run_dir,
            status_path=status_path,
            status=status,
            terminal=terminal,
            final_inputs_sha256=final_inputs_sha256,
            final_override_sha256=final_override_sha256,
            completed_at=freeze_finished,
            now=now,
        )
    except _NonProductionArtifact as error:
        observed_at = _read_now(now)
        terminal = {
            "outcome": "ignored",
            "decision": "IGNORED",
            "reason": str(error),
            "package_path": None,
            "package_sha256": None,
            "effective_bank": None,
            "selected_count": None,
            "selected_cost": None,
            "selected_snapshot": None,
            "published_at": None,
        }
        return _finalize_status(
            plan,
            run_id=resolved_run_id,
            run_dir=run_dir,
            status_path=status_path,
            status=status,
            terminal=terminal,
            final_inputs_sha256=final_inputs_sha256,
            final_override_sha256=final_override_sha256,
            completed_at=observed_at,
            now=now,
        )
    except Exception as error:
        observed_at = _read_now(now)
        message = _safe_error(error)
        active_phase = _active_phase(phase_state)
        if active_phase is not None:
            _phase_finished(
                phase_state,
                active_phase,
                finished_at=observed_at,
                status="failed",
                reason=message,
            )
        terminal = {
            "outcome": "failed",
            "decision": "FAILED",
            "reason": message,
            "package_path": None,
            "package_sha256": None,
            "effective_bank": None,
            "selected_count": None,
            "selected_cost": None,
            "selected_snapshot": None,
            "published_at": None,
        }
        return _finalize_status(
            plan,
            run_id=resolved_run_id,
            run_dir=run_dir,
            status_path=status_path,
            status=status,
            terminal=terminal,
            final_inputs_sha256=final_inputs_sha256,
            final_override_sha256=final_override_sha256,
            completed_at=observed_at,
            now=now,
        )


def execute_scheduler_tick(
    plan: SchedulerPlan,
    *,
    phase_runner: SchedulerPhaseRunner,
    now: Callable[[], datetime],
    sleep: Callable[[float], object],
) -> SchedulerExecutionResult | None:
    """Run at most one due scheduler phase and return immediately.

    State is plan-scoped and hash verified.  Warmup and refresh failures are
    recorded but deliberately never become terminal dependencies of final.
    """
    _require_plan(plan)
    _ensure_output_directory(plan.output_dir, plan.output_dir)
    _reject_unsafe_output_descendants(plan.output_dir)
    state_path = plan.output_dir / "scheduler-state.json"
    lock_path = plan.output_dir / ".scheduler.lock"
    with scheduler_lock(lock_path):
        observed = _read_now(now)
        state = recover_orphan(
            load_state(state_path, plan_id=plan.plan_id, now=observed), observed
        )
        save_state(state_path, state)
        prior = find_prior_bet_ready(plan)
        if prior is not None:
            return prior
        recovered = _recover_atomic_publication(
            plan,
            state=state,
            state_path=state_path,
            observed_at=observed,
            now=now,
        )
        if recovered is not None:
            return recovered
        if state["terminal"] is not None:
            return None
        if observed >= plan.publish_deadline:
            return _finalize_tick_no_bet(
                plan, state=state, state_path=state_path, observed_at=observed,
                reason="T-10 publication deadline was missed",
            )

        phase: str | None = None
        runner_phase: Literal["preflight", "final"] | None = None
        scheduled_at: datetime | None = None
        if (
            observed >= plan.retry_at
            and state["phases"]["final"]["status"]
            in {"pending", "retryable_failed"}
        ):
            phase, runner_phase, scheduled_at = "final", "final", plan.retry_at
        elif (
            observed >= plan.final_at
            and state["phases"]["final"]["status"] == "pending"
        ):
            phase, runner_phase, scheduled_at = "final", "final", plan.final_at
        elif (
            observed >= plan.fallback_at
            and state["phases"]["refresh"]["status"] == "pending"
        ):
            phase, runner_phase, scheduled_at = "refresh", "preflight", plan.fallback_at
        elif (
            observed >= plan.preflight_at
            and state["phases"]["warmup"]["status"] == "pending"
        ):
            phase, runner_phase, scheduled_at = "warmup", "preflight", plan.preflight_at
        if phase is None or runner_phase is None or scheduled_at is None:
            return None

        attempts = state["phases"][phase]["attempts"]
        if phase == "final":
            if len(attempts) >= plan.max_final_attempts:
                return _finalize_tick_no_bet(
                    plan, state=state, state_path=state_path, observed_at=observed,
                    reason="final attempt limit exhausted",
                )
            remaining = (
                plan.actionable_publication_deadline - observed
            ).total_seconds()
            if remaining < plan.minimum_final_runtime_seconds:
                return _finalize_tick_no_bet(
                    plan, state=state, state_path=state_path, observed_at=observed,
                    reason=(
                        "insufficient final runtime budget before the "
                        "actionable cutoff"
                    ),
                )

        attempt_id = f"{phase}-{len(attempts) + 1:02d}-{_new_run_id(observed)}"
        run_dir = plan.output_dir / "attempts" / attempt_id
        _create_output_directory_exclusive(plan.output_dir, run_dir)
        state = transition(
            state, phase=phase, status="running", observed_at=observed,
            attempt_id=attempt_id,
        )
        save_state(state_path, state)
        context = SchedulerPhaseContext(
            phase=runner_phase,
            plan=plan,
            run_id=attempt_id,
            run_dir=run_dir,
            work_dir=run_dir / runner_phase,
            scheduled_at=scheduled_at,
            started_at=observed,
            override_sha256=(
                _current_override_sha256(plan) if phase == "final" else None
            ),
            # Atomic final input does not exist until the phase runner captures
            # it.  The parser returns the canonical binding after validating
            # the immutable snapshot and package-safety probabilities.
            final_inputs_sha256=None,
            atomic_final=phase == "final",
        )
        try:
            retry_delays = (
                plan.transient_backoff_seconds if phase == "final" else ()
            )
            for retry_index in range(len(retry_delays) + 1):
                try:
                    result = _call_phase_runner(phase_runner, context)
                    break
                except Exception as phase_error:
                    if (
                        _permanent_tick_error(phase_error)
                        or retry_index >= len(retry_delays)
                    ):
                        raise
                    delay = retry_delays[retry_index]
                    remaining = (
                        plan.actionable_publication_deadline - _read_now(now)
                    ).total_seconds()
                    if (
                        delay + plan.minimum_final_runtime_seconds
                        > remaining
                    ):
                        raise
                    sleep(delay)
            completed = _read_now(now)
            if result.status != "complete":
                raise SchedulerPhaseError(result.reason)
            if (
                phase == "final"
                and completed > plan.actionable_publication_deadline
            ):
                return _finalize_tick_no_bet(
                    plan,
                    state=state,
                    state_path=state_path,
                    observed_at=completed,
                    reason=(
                        "final work completed inside the publication reserve "
                        "before T-10"
                    ),
                )
            if phase != "final":
                state = transition(
                    state, phase=phase, status="complete",
                    observed_at=completed, attempt_id=attempt_id,
                    reason=result.reason,
                )
                save_state(state_path, state)
                return None
            if result.decision == "NO BET":
                return _finalize_tick_no_bet(
                    plan, state=state, state_path=state_path,
                    observed_at=completed, reason=result.reason,
                )
            if result.decision != "PLAY":
                raise SchedulerIntegrityError(
                    "final phase must return PLAY or NO BET",
                    category="phase_contract",
                )
            try:
                snapshot = _capture_snapshot(
                    plan, context=context, result=result, completed_at=completed
                )
            except SchedulerIntegrityError:
                raise
            except (
                OSError,
                SchedulerError,
                TypeError,
                ValueError,
            ) as error:
                raise SchedulerIntegrityError(
                    f"final package snapshot rejected: {_safe_error(error)}",
                    category="package_integrity",
                ) from error
            phase_state = _initial_phase_state(plan)
            status = _base_status(plan, attempt_id, run_dir, phase_state)
            status_path = run_dir / "status.json"
            _write_exclusive_atomic(
                plan.output_dir, status_path,
                _canonical_json_bytes(status) + b"\n",
            )
            terminal = _freeze_and_publish(
                plan, run_id=attempt_id, run_dir=run_dir,
                snapshots={"final": snapshot}, phase_errors=[],
                phase_absences=[],
                final_inputs_sha256=snapshot.final_inputs_sha256,
                final_override_sha256=context.override_sha256,
                now=now,
            )
            completed = _read_now(now)
            finalized = _finalize_status(
                plan, run_id=attempt_id, run_dir=run_dir,
                status_path=status_path, status=status, terminal=terminal,
                final_inputs_sha256=snapshot.final_inputs_sha256,
                final_override_sha256=context.override_sha256,
                completed_at=completed, now=now,
            )
            state = _transition_after_tick_publication(
                state,
                result=finalized,
                intended_outcome=terminal["outcome"],
                observed_at=completed,
                attempt_id=attempt_id,
            )
            save_state(state_path, state)
            return finalized
        except Exception as error:
            completed = _read_now(now)
            permanent = _permanent_tick_error(error)
            status = "integrity_failed" if permanent and phase == "final" else (
                "permanent_failed" if permanent else "retryable_failed"
            )
            state = transition(
                state, phase=phase, status=status, observed_at=completed,
                attempt_id=attempt_id, reason=_safe_error(error),
                terminal="failed" if permanent and phase == "final" else None,
            )
            save_state(state_path, state)
            if permanent and phase == "final":
                raise
            return None


def _permanent_tick_error(error: Exception) -> bool:
    """Classify failures by type/status only; error text is never semantic."""

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, SchedulerPermanentError):
            return True
        if isinstance(current, SchedulerTransientError):
            return False
        if isinstance(current, TotoBriefRequestError):
            status = current.status_code
            if status is None:
                return False
            return (
                400 <= status < 500
                and status not in {408, 409, 425, 429}
            )
        if isinstance(
            current,
            (
                TimeoutError,
                subprocess.TimeoutExpired,
                ConnectionError,
            ),
        ):
            return False
        current = current.__cause__ or current.__context__
    # Unknown failures remain retryable and are bounded by max_final_attempts.
    return False


def _remove_actionable_publication_artifacts(
    plan: SchedulerPlan,
    run_dir: Path,
) -> None:
    """Remove package bytes that no longer have a timely actionable marker."""
    _unlink_output_path(
        plan.output_dir,
        run_dir / "package.csv",
        missing_ok=True,
    )
    _unlink_output_path(
        plan.output_dir,
        run_dir / "package-archive.json",
        missing_ok=True,
    )


def _recover_atomic_publication(
    plan: SchedulerPlan,
    *,
    state: Mapping[str, Any],
    state_path: Path,
    observed_at: datetime,
    now: Callable[[], datetime],
) -> SchedulerExecutionResult | None:
    attempts_root = plan.output_dir / "attempts"
    if not attempts_root.is_dir():
        return None
    candidates = tuple(
        sorted(
            path.parent
            for path in attempts_root.glob("*/package-archive.json")
            if path.is_file() and not path.is_symlink()
        )
    )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise SchedulerError("multiple recoverable atomic publications exist")
    run_dir = candidates[0]
    attempt_id = run_dir.name
    manifest_path = run_dir / "package-archive.json"
    package_path = run_dir / "package.csv"
    final_input_path = run_dir / "final-input.json"
    final_input = load_final_input(final_input_path, expected_plan=plan)
    if final_input.attempt_id != attempt_id:
        raise SchedulerError(
            "recoverable archive final-input attempt mismatch"
        )
    current_override_sha256 = _current_override_sha256(plan)
    if final_input.timing_override_sha256 != current_override_sha256:
        raise SchedulerIntegrityError(
            "recoverable archive timing override changed after atomic-final "
            "capture",
            category="timing_override_integrity",
        )
    final_inputs_sha256 = _final_inputs_sha256(
        plan,
        final_input.timing_override_sha256,
        final_input,
    )
    payload = _load_strict_json(manifest_path, name="package archive")
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version") != 2
        or payload.get("final_input_sha256") != final_input.snapshot_sha256
        or payload.get("probability_input_sha256")
        != final_input.probability_input_sha256
    ):
        raise SchedulerError("recoverable archive final-input provenance mismatch")
    if observed_at > plan.publish_deadline:
        _remove_actionable_publication_artifacts(plan, run_dir)
        return _finalize_tick_no_bet(
            plan,
            state=state,
            state_path=state_path,
            observed_at=observed_at,
            reason=(
                "archive recovered after the T-10 publication deadline; "
                "publication suppressed"
            ),
        )
    archive_engine = init_db(plan.db)
    try:
        archived = import_prebet_package_manifest(
            get_session_factory(archive_engine), manifest_path, package_path
        )
    finally:
        archive_engine.dispose()
    if archived.final_input_sha256 != final_input.snapshot_sha256:
        raise SchedulerError("recoverable durable archive did not verify")
    status_path = run_dir / "status.json"
    if status_path.is_file():
        status = _load_strict_json(status_path, name="scheduler status")
        if not isinstance(status, dict):
            raise SchedulerError("recoverable scheduler status is invalid")
    else:
        phase_state = _initial_phase_state(plan)
        status = _base_status(plan, attempt_id, run_dir, phase_state)
        _write_exclusive_atomic(
            plan.output_dir,
            status_path,
            _canonical_json_bytes(status) + b"\n",
        )
    terminal = {
        "outcome": "bet-ready",
        "decision": "PLAY",
        "reason": "verified archive recovered no later than T-10",
        "package_path": package_path,
        "package_sha256": archived.source_bytes_sha256,
        "effective_bank": plan.requested_bank,
        "selected_count": archived.coupon_count,
        "selected_cost": archived.cost,
        "selected_snapshot": "final",
        "published_at": observed_at,
    }
    finalized = _finalize_status(
        plan,
        run_id=attempt_id,
        run_dir=run_dir,
        status_path=status_path,
        status=status,
        terminal=terminal,
        final_inputs_sha256=final_inputs_sha256,
        final_override_sha256=final_input.timing_override_sha256,
        completed_at=observed_at,
        now=now,
    )
    updated = _transition_after_tick_publication(
        state,
        result=finalized,
        intended_outcome=terminal["outcome"],
        observed_at=observed_at,
        attempt_id=attempt_id,
    )
    save_state(state_path, updated)
    return finalized


def _transition_after_tick_publication(
    state: Mapping[str, Any],
    *,
    result: SchedulerExecutionResult,
    intended_outcome: str,
    observed_at: datetime,
    attempt_id: str,
) -> dict[str, Any]:
    """Persist terminal success only after its marker exists and verifies."""

    if result.outcome == "bet-ready":
        updated = transition(
            state,
            phase="final",
            status="complete",
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
        )
        return transition(
            updated,
            phase="publish",
            status="complete",
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
            terminal="bet_ready",
        )
    if result.outcome == "no-bet":
        updated = transition(
            state,
            phase="final",
            status="no_bet",
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
        )
        return transition(
            updated,
            phase="publish",
            status="no_bet",
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
            terminal="no_bet",
        )
    if result.outcome == "failed":
        final_status = (
            "complete" if intended_outcome == "bet-ready" else "no_bet"
        )
        updated = transition(
            state,
            phase="final",
            status=final_status,
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
        )
        return transition(
            updated,
            phase="publish",
            status="permanent_failed",
            observed_at=observed_at,
            attempt_id=attempt_id,
            reason=result.reason,
            terminal="failed",
        )
    raise SchedulerIntegrityError(
        "atomic publication returned an unsupported outcome",
        category="phase_contract",
    )


def _finalize_tick_no_bet(
    plan: SchedulerPlan,
    *,
    state: Mapping[str, Any],
    state_path: Path,
    observed_at: datetime,
    reason: str,
) -> SchedulerExecutionResult:
    run_id = f"no-bet-{_new_run_id(observed_at)}"
    run_dir = plan.output_dir / "runs" / str(plan.drawing) / run_id
    _create_output_directory_exclusive(plan.output_dir, run_dir)
    phase_state = _initial_phase_state(plan)
    status = _base_status(plan, run_id, run_dir, phase_state)
    status_path = run_dir / "status.json"
    _write_exclusive_atomic(
        plan.output_dir, status_path, _canonical_json_bytes(status) + b"\n"
    )
    terminal = _no_package_terminal([], [reason])
    updated = transition(
        state, phase="final", status="no_bet", observed_at=observed_at,
        reason=reason,
    )
    updated = transition(
        updated, phase="publish", status="no_bet", observed_at=observed_at,
        reason=reason, terminal="no_bet",
    )
    save_state(state_path, updated)
    return _finalize_status(
        plan, run_id=run_id, run_dir=run_dir, status_path=status_path,
        status=status, terminal=terminal, final_inputs_sha256=None,
        final_override_sha256=None, completed_at=observed_at,
        now=lambda: observed_at,
    )


def find_prior_bet_ready(plan: SchedulerPlan) -> SchedulerExecutionResult | None:
    """Return only a cryptographically valid prior ``.bet-ready`` run.

    Legacy ``.success`` files and run-scoped ``.no-bet``/``.failed`` markers
    are intentionally ignored.
    """

    _require_plan(plan)
    if not _path_exists(plan.output_dir):
        return None
    _reject_unsafe_output_descendants(plan.output_dir)
    roots = tuple(
        root
        for root in (
            plan.output_dir / "runs" / str(plan.drawing),
            plan.output_dir / "attempts",
        )
        if _path_exists(root)
    )
    run_dirs: list[Path] = []
    for root in roots:
        _require_output_directory(plan.output_dir, root)
        run_dirs.extend(path for path in root.iterdir() if path.is_dir())
    for run_dir in sorted(run_dirs, reverse=True):
        marker_path = run_dir / ".bet-ready"
        if not run_dir.is_dir() or not _path_exists(marker_path):
            continue
        status_path = run_dir / "status.json"
        try:
            _require_regular_file(
                marker_path,
                name="prior BET READY marker",
                reject_symlink=True,
            )
            payload = _load_strict_json(status_path, name="prior status")
            if not isinstance(payload, Mapping):
                continue
            if (
                payload.get("schema_version") != SCHEDULER_SCHEMA_VERSION
                or payload.get("plan_id") != plan.plan_id
                or payload.get("outcome") != "bet-ready"
                or payload.get("decision") != "PLAY"
            ):
                continue
            package_path = Path(str(payload["package_path"]))
            expected_path = run_dir / "package.csv"
            if _normalized_path(package_path) != _normalized_path(expected_path):
                continue
            package_sha256 = str(payload["package_sha256"])
            _require_sha256("package_sha256", package_sha256)
            selected_count = payload.get("selected_count")
            selected_cost = payload.get("selected_cost")
            if (
                type(selected_count) is not int
                or selected_count <= 0
                or type(selected_cost) is not int
                or selected_cost <= 0
                or not _valid_package_hash(
                    plan,
                    expected_path,
                    package_sha256,
                    expected_count=selected_count,
                    expected_cost=selected_cost,
                )
            ):
                continue
            published_at = _parse_utc_datetime(
                "published_at", payload.get("published_at")
            )
            if published_at > plan.freeze_at:
                continue
            return _execution_result_from_status(payload, run_dir, status_path)
        except (KeyError, OSError, SchedulerError, TypeError, ValueError):
            continue
    return None


def build_run_drawing_phase_command(
    context: SchedulerPhaseContext,
    *,
    python_executable: str | Path = sys.executable,
) -> tuple[str, ...]:
    """Build the credential-free command for a fallback or final snapshot."""

    if context.phase not in ("fallback", "final"):
        raise ValueError("run-drawing command is only valid for package phases")
    validated_executable = _validated_python_executable(python_executable)
    plan = context.plan
    atomic_final = context.phase == "final" and context.atomic_final
    lead_minutes = 30 if context.phase == "fallback" else (20 if atomic_final else 15)
    report_dir = context.work_dir / "reports"
    cache_root = context.work_dir / "cache"
    command = [
        validated_executable,
        "-m",
        "toto_ai.cli",
        "run-drawing",
        "--open",
        "--bank",
        str(plan.requested_bank),
        "--stake",
        str(plan.stake),
        "--mode",
        "playable",
        "--min-gross-ev",
        format(plan.minimum_gross_ev, ".17g"),
        "--package-near-fixed-share",
        format(plan.package_near_fixed_share, ".17g"),
        "--package-low-probability-threshold",
        format(plan.package_low_probability_threshold, ".17g"),
        "--package-material-probability-threshold",
        format(plan.package_material_probability_threshold, ".17g"),
        "--final-lead-minutes",
        str(lead_minutes),
        "--safety-stop-minutes",
        str(12 if atomic_final else 10),
        "--db",
        str(plan.db),
        "--report-dir",
        str(report_dir),
        "--provider",
        plan.provider,
        "--aliases",
        str(plan.aliases),
        "--quota-reserve",
        str(plan.quota_reserve),
        "--max-passes",
        str(plan.max_passes),
        "--max-expansion-passes",
        str(plan.max_expansion_passes),
        "--retry-delay-seconds",
        str(plan.retry_delay_seconds),
        "--cache-root",
        str(cache_root),
    ]
    if plan.timing_overrides is not None:
        command.extend(("--timing-overrides", str(plan.timing_overrides)))
    if plan.reviewed_schedule_catalog is not None:
        command.extend(
            (
                "--reviewed-schedule-catalog",
                str(plan.reviewed_schedule_catalog),
            )
        )
    return tuple(command)


def build_prepare_drawing_command(
    plan: SchedulerPlan,
    _work_dir: Path,
    *,
    python_executable: str | Path = sys.executable,
) -> tuple[str, ...]:
    """Build the mandatory systematic-resolution scheduler preflight."""
    command = [
        _validated_python_executable(python_executable),
        "-m",
        "toto_ai.cli",
        "prepare-drawing",
        "--open",
        "--db",
        str(plan.db),
        "--aliases",
        str(plan.aliases),
        "--provider",
        plan.provider,
        "--raw-cache-dir",
        str(plan.project_root / "data" / "raw"),
        "--cache-root",
        str(plan.project_root / "data" / "external-cache" / "api-sports"),
        "--quota-reserve",
        str(plan.quota_reserve),
        "--expansion-horizon-days",
        "5",
    ]
    if plan.reviewed_schedule_catalog is not None:
        command.extend(
            (
                "--reviewed-schedule-catalog",
                str(plan.reviewed_schedule_catalog),
            )
        )
    return tuple(command)


class CommandSchedulerPhaseRunner:
    """Production adapter around the existing safe ``run-drawing`` command."""

    def __init__(
        self,
        *,
        python_executable: str | Path = sys.executable,
        environment: Mapping[str, str] | None = None,
        target_validator: Callable[[SchedulerPlan, datetime], object]
        | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.python_executable = _validated_python_executable(python_executable)
        self.environment = dict(os.environ if environment is None else environment)
        self.environment.pop("TOTO_LEGACY_NAME_MATCHING", None)
        self.target_validator = target_validator or _validate_live_scheduler_target
        self.now = now or (lambda: datetime.now(timezone.utc))

    def __call__(self, context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            self._preflight(context.plan, context.work_dir)
            self.target_validator(context.plan, _read_now(self.now))
            return SchedulerPhaseResult.completed(
                "target, data access, configuration, and override catalog validated"
            )

        context.work_dir.mkdir(parents=True, exist_ok=True)
        atomic_input = None
        if context.phase == "final" and context.atomic_final:
            final_input_path = context.run_dir / "final-input.json"
            try:
                atomic_input = (
                    load_final_input(final_input_path, expected_plan=context.plan)
                    if final_input_path.exists()
                    else capture_final_input(
                        client=TotoBriefClient(),
                        plan=context.plan,
                        attempt_id=context.run_id,
                        now=self.now,
                        destination=final_input_path,
                        timing_override_sha256=context.override_sha256,
                    )
                )
            except TotoBriefRequestError:
                raise
            except (OSError, TypeError, ValueError) as error:
                raise SchedulerIntegrityError(
                    f"final input validation failed: {_safe_error(error)}",
                    category="final_input_integrity",
                ) from error
            if atomic_input.attempt_id != context.run_id:
                raise SchedulerIntegrityError(
                    "persisted final input attempt identity mismatch",
                    category="final_input_identity",
                )
        command = build_run_drawing_phase_command(
            context,
            python_executable=self.python_executable,
        )
        command_environment = dict(self.environment)
        if atomic_input is not None:
            command_environment["TOTO_FINAL_INPUT"] = str(atomic_input.path)
            command_environment["TOTO_SCHEDULER_PLAN"] = str(
                context.plan.output_dir / SCHEDULER_PLAN_FILENAME
            )
        subprocess_started_at = _read_now(self.now)
        timeout_seconds = (
            context.plan.actionable_publication_deadline
            - subprocess_started_at
        ).total_seconds()
        if timeout_seconds <= 0:
            raise SchedulerTransientError(
                "run-drawing cannot preserve the publication reserve before T-10",
                category="run_drawing_timeout",
            )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=command_environment,
                cwd=context.plan.project_root,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise SchedulerTransientError(
                "run-drawing timed out before the T-10 cutoff",
                category="run_drawing_timeout",
            ) from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            secret = self.environment.get("API_SPORTS_KEY", "")
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
            detail = detail[-1000:]
            suffix = f": {detail}" if detail else ""
            raise SchedulerTransientError(
                f"run-drawing exited with code {completed.returncode}{suffix}",
                category="run_drawing_process",
            )
        try:
            _reject_unsafe_output_descendants(context.plan.output_dir)
            report_dir = context.work_dir / "reports"
            _require_output_directory(context.plan.output_dir, report_dir)
            manifests = tuple(
                sorted(
                    path
                    for path in report_dir.iterdir()
                    if path.name.startswith("drawing_run_")
                    and path.name.endswith(".json")
                )
            )
            if len(manifests) != 1:
                raise SchedulerIntegrityError(
                    "run-drawing must publish exactly one runner JSON manifest",
                    category="runner_manifest_integrity",
                )
            return parse_runner_manifest_phase_result(context, manifests[0])
        except SchedulerIntegrityError:
            raise
        except (OSError, SchedulerError, TypeError, ValueError) as error:
            raise SchedulerIntegrityError(
                f"runner artifact validation failed: {_safe_error(error)}",
                category="runner_manifest_integrity",
            ) from error

    def _preflight(self, plan: SchedulerPlan, work_dir: Path) -> None:
        if not _is_regular_file(plan.db, reject_symlink=True) or not os.access(
            plan.db, os.R_OK | os.W_OK
        ):
            raise SchedulerPhaseError("database must be a readable, writable file")
        if not _is_regular_file(
            plan.aliases, reject_symlink=True
        ) or not os.access(plan.aliases, os.R_OK):
            raise SchedulerPhaseError("aliases must be a readable file")
        load_aliases(plan.aliases)
        if not self.environment.get("API_SPORTS_KEY", "").strip():
            raise SchedulerPhaseError("API_SPORTS_KEY is required")
        _ensure_output_directory(plan.output_dir, work_dir)
        probe = work_dir / ".preflight-write-probe"
        _write_exclusive_atomic(plan.output_dir, probe, b"ok\n")
        _unlink_output_path(plan.output_dir, probe)
        command = build_prepare_drawing_command(
            plan, work_dir, python_executable=self.python_executable
        )
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=self.environment,
                cwd=plan.project_root,
                timeout=300,
            )
        except subprocess.TimeoutExpired as error:
            raise SchedulerTransientError(
                "prepare-drawing preflight timed out",
                category="preflight_timeout",
            ) from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            secret = self.environment.get("API_SPORTS_KEY", "")
            if secret:
                detail = detail.replace(secret, "[REDACTED]")
            suffix = f": {detail[-1000:]}" if detail else ""
            raise SchedulerTransientError(
                "prepare-drawing did not produce a ready 15/15 preparation"
                f"{suffix}",
                category="preparation_unavailable",
            )


class SimulatedSchedulerPhaseRunner:
    """Deterministic, network-free phase runner for CLI acceptance and drills."""

    def __call__(self, context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("simulated preflight passed")
        minimum_gross_ev = context.plan.minimum_gross_ev
        fallback_gross_ev = max(1.10, minimum_gross_ev)
        final_gross_ev = max(1.12, minimum_gross_ev)
        second_final_gross_ev = max(1.05, minimum_gross_ev)
        coupons = (
            (
                (
                    1,
                    "111111111111111",
                    fallback_gross_ev,
                    fallback_gross_ev - 1.0,
                ),
            )
            if context.phase == "fallback"
            else (
                (
                    1,
                    "111111111111111",
                    final_gross_ev,
                    final_gross_ev - 1.0,
                ),
                (
                    2,
                    "XXXXXXXXXXXXXXX",
                    second_final_gross_ev,
                    second_final_gross_ev - 1.0,
                ),
            )
        )
        package = _render_package_csv(coupons)
        return SchedulerPhaseResult.play(
            package,
            reason=f"simulated {context.phase} PLAY package",
            effective_bank=context.plan.requested_bank,
            selected_count=len(coupons),
            selected_cost=len(coupons) * context.plan.stake,
            override_sha256=context.override_sha256,
            package_sha256=_sha256_bytes(package),
        )


class VirtualSchedulerClock:
    """Simple deterministic clock used by explicit simulated CLI execution."""

    def __init__(self, initial: datetime) -> None:
        self.current = _require_utc_datetime("initial", initial)

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("sleep seconds must be non-negative")
        self.current += timedelta(seconds=float(seconds))


def _execute_package_phase(
    plan: SchedulerPlan,
    *,
    run_id: str,
    run_dir: Path,
    phase: PackagePhase,
    scheduled_at: datetime,
    phase_runner: SchedulerPhaseRunner,
    now: Callable[[], datetime],
    sleep: Callable[[float], object],
    phase_state: dict[str, dict[str, Any]],
    status_path: Path,
    status: dict[str, Any],
    override_sha256: str | None = None,
    final_inputs_sha256: str | None = None,
) -> PackageSnapshot | None:
    _wait_until(scheduled_at, now=now, sleep=sleep)
    started_at = _read_now(now)
    _phase_started(
        phase_state,
        phase,
        scheduled_at=scheduled_at,
        started_at=started_at,
    )
    _write_status_atomic(plan.output_dir, status_path, status)
    _validate_status_file(plan, status_path, status)
    phase_override_sha256 = (
        _current_override_sha256(plan)
        if override_sha256 is None
        else override_sha256
    )
    context = _phase_context(
        plan,
        run_id,
        run_dir,
        phase=phase,
        scheduled_at=scheduled_at,
        started_at=started_at,
        override_sha256=phase_override_sha256,
        final_inputs_sha256=final_inputs_sha256,
    )
    try:
        result = _call_phase_runner(phase_runner, context)
        completed_at = _read_now(now)
        if result.status == "ignored":
            _phase_finished(
                phase_state,
                phase,
                finished_at=completed_at,
                status="ignored",
                reason=result.reason,
            )
            _write_status_atomic(plan.output_dir, status_path, status)
            raise _NonProductionArtifact(result.reason)
        if result.status == "failed":
            raise SchedulerPhaseError(result.reason)
        if result.decision == "NO BET":
            if any(
                value is not None
                for value in (
                    result.package_bytes,
                    result.package_path,
                    result.package_sha256,
                    result.effective_bank,
                    result.selected_count,
                    result.selected_cost,
                )
            ):
                raise SchedulerPhaseError("NO BET phase cannot return a package")
            _phase_finished(
                phase_state,
                phase,
                finished_at=completed_at,
                status="complete",
                reason=result.reason,
            )
            _write_status_atomic(plan.output_dir, status_path, status)
            return None
        if result.decision != "PLAY":
            raise SchedulerPhaseError("package phase must return PLAY or NO BET")
        if completed_at > plan.freeze_at:
            _phase_finished(
                phase_state,
                phase,
                finished_at=completed_at,
                status="late",
                reason="package completed after T-10 and was not captured",
            )
            _write_status_atomic(plan.output_dir, status_path, status)
            return None
        snapshot = _capture_snapshot(
            plan,
            context=context,
            result=result,
            completed_at=completed_at,
        )
        _phase_finished(
            phase_state,
            phase,
            finished_at=completed_at,
            status="complete",
            reason=result.reason,
        )
        phase_state[phase]["snapshot_path"] = str(snapshot.path)
        phase_state[phase]["snapshot_sha256"] = snapshot.sha256
        _write_status_atomic(plan.output_dir, status_path, status)
        return snapshot
    except _NonProductionArtifact:
        raise
    except Exception as error:
        completed_at = _read_now(now)
        _phase_finished(
            phase_state,
            phase,
            finished_at=completed_at,
            status="failed",
            reason=_safe_error(error),
        )
        _write_status_atomic(plan.output_dir, status_path, status)
        if phase == "final":
            raise
        return None


def _capture_snapshot(
    plan: SchedulerPlan,
    *,
    context: SchedulerPhaseContext,
    result: SchedulerPhaseResult,
    completed_at: datetime,
) -> PackageSnapshot:
    if result.package_bytes is not None:
        package_bytes = result.package_bytes
    elif result.package_path is not None:
        try:
            _require_contained_path(
                context.work_dir,
                result.package_path,
                name="source package",
            )
            package_bytes = _read_regular_file(
                result.package_path,
                name="source package",
                reject_symlink=True,
            )
        except OSError as error:
            raise SchedulerPhaseError(f"package could not be read: {error}") from error
    else:
        raise SchedulerPhaseError("PLAY phase did not return a package")
    package = _validate_package_csv(
        package_bytes,
        stake=plan.stake,
        minimum_gross_ev=plan.minimum_gross_ev,
        expected_count=result.selected_count,
        expected_cost=result.selected_cost,
    )
    observed_sha256 = _sha256_bytes(package_bytes)
    if (
        result.package_sha256 is not None
        and result.package_sha256 != observed_sha256
    ):
        raise SchedulerPhaseError("phase package SHA-256 did not verify")
    if result.effective_bank is None:
        raise SchedulerPhaseError("PLAY phase must report effective_bank")
    validate_config_bank(result.effective_bank, plan.stake)
    if result.effective_bank > plan.requested_bank:
        raise SchedulerPhaseError("effective bank exceeds requested maximum")
    if package.cost > result.effective_bank:
        raise SchedulerPhaseError("package cost exceeds effective bank")
    if result.override_sha256 != context.override_sha256:
        raise SchedulerPhaseError("phase timing override hash did not verify")
    final_inputs_sha256 = context.final_inputs_sha256
    if context.atomic_final:
        final_input = load_final_input(
            context.run_dir / "final-input.json",
            expected_plan=plan,
        )
        final_inputs_sha256 = _final_inputs_sha256(
            plan,
            context.override_sha256,
            final_input,
        )
        if (
            result.final_inputs_sha256 is not None
            and result.final_inputs_sha256 != final_inputs_sha256
        ):
            raise SchedulerPhaseError(
                "phase final-input binding did not verify"
            )
    elif result.final_inputs_sha256 is not None:
        raise SchedulerPhaseError(
            "non-atomic phase cannot return a final-input binding"
        )

    snapshot_dir = context.run_dir / "snapshots" / context.phase
    _create_output_directory_exclusive(plan.output_dir, snapshot_dir)
    package_path = snapshot_dir / "package.csv"
    _write_exclusive_atomic(plan.output_dir, package_path, package_bytes)
    if not _valid_package_hash(
        plan,
        package_path,
        observed_sha256,
        expected_count=package.count,
        expected_cost=package.cost,
    ):
        raise SchedulerPhaseError("captured package SHA-256 did not verify")
    snapshot = PackageSnapshot(
        phase=context.phase,
        path=package_path,
        sha256=observed_sha256,
        completed_at=completed_at,
        effective_bank=result.effective_bank,
        selected_count=package.count,
        selected_cost=package.cost,
        override_sha256=context.override_sha256,
        final_inputs_sha256=final_inputs_sha256,
    )
    manifest = {
        "phase": snapshot.phase,
        "completed_at": _timestamp(snapshot.completed_at),
        "package_path": str(snapshot.path),
        "package_sha256": snapshot.sha256,
        "requested_bank": plan.requested_bank,
        "effective_bank": snapshot.effective_bank,
        "selected_count": snapshot.selected_count,
        "selected_cost": snapshot.selected_cost,
        "override_sha256": snapshot.override_sha256,
        "final_inputs_sha256": snapshot.final_inputs_sha256,
    }
    _write_exclusive_atomic(
        plan.output_dir,
        snapshot_dir / "manifest.json",
        _canonical_json_bytes(manifest) + b"\n",
    )
    return snapshot


def _freeze_and_publish(
    plan: SchedulerPlan,
    *,
    run_id: str,
    run_dir: Path,
    snapshots: Mapping[PackagePhase, PackageSnapshot],
    phase_errors: list[str],
    phase_absences: list[str],
    final_inputs_sha256: str | None,
    final_override_sha256: str | None,
    now: Callable[[], datetime],
) -> dict[str, Any]:
    publication_deadline = plan.freeze_at
    observed_at = _read_now(now)
    if plan.drawing_id is None:
        phase_errors.append(
            "freeze: internal drawing_id is required for package archival"
        )
        return _no_package_terminal(phase_errors, phase_absences)
    if not plan.actionable_safety_bound:
        phase_errors.append(
            "freeze: legacy scheduler plan lacks trusted package safety binding"
        )
        return _no_package_terminal(phase_errors, phase_absences)
    if observed_at > publication_deadline:
        phase_absences.append("T-10 publication deadline was missed")
        return _no_package_terminal(phase_errors, phase_absences)

    try:
        _reject_unsafe_output_descendants(plan.output_dir)
        current_override_sha256 = _current_override_sha256(plan)
        final_input_path = run_dir / "final-input.json"
        final_input = (
            load_final_input(final_input_path, expected_plan=plan)
            if final_input_path.exists()
            else None
        )
        current_final_inputs_sha256 = (
            _final_inputs_sha256(
                plan,
                current_override_sha256,
                final_input,
            )
            if final_input is not None
            else _final_inputs_sha256(plan, current_override_sha256)
        )
    except Exception as error:
        phase_errors.append(f"freeze override validation: {_safe_error(error)}")
        return _no_package_terminal(phase_errors, phase_absences)

    fallback_snapshot = snapshots.get("fallback")
    if fallback_snapshot is not None:
        phase_absences.append(
            "fallback PLAY snapshot retained for audit only; "
            "fresh final PLAY is mandatory"
        )

    snapshot = snapshots.get("final")
    if snapshot is None:
        return _no_package_terminal(phase_errors, phase_absences)

    error = _snapshot_validation_error(
        plan,
        snapshot,
        current_override_sha256=current_override_sha256,
        pinned_final_inputs_sha256=final_inputs_sha256,
        current_final_inputs_sha256=current_final_inputs_sha256,
        final_override_sha256=final_override_sha256,
    )
    if error is not None:
        phase_errors.append(f"final: {error}")
        return _no_package_terminal(phase_errors, phase_absences)

    package_path = run_dir / "package.csv"
    archive_manifest_path = run_dir / "package-archive.json"
    try:
        package_bytes = _read_regular_file(
            snapshot.path,
            name="final snapshot package",
            reject_symlink=True,
        )
        validated_package = _validate_package_csv(
            package_bytes,
            stake=plan.stake,
            minimum_gross_ev=plan.minimum_gross_ev,
            expected_count=snapshot.selected_count,
            expected_cost=snapshot.selected_cost,
        )
        if _sha256_bytes(package_bytes) != snapshot.sha256:
            raise SchedulerPhaseError("source package changed during publication")
        _write_exclusive_atomic(plan.output_dir, package_path, package_bytes)
        if not _valid_package_hash(
            plan,
            package_path,
            snapshot.sha256,
            expected_count=snapshot.selected_count,
            expected_cost=snapshot.selected_cost,
        ):
            raise SchedulerPhaseError("published package SHA-256 did not verify")

        publication_override_sha256 = _current_override_sha256(plan)
        publication_final_inputs_sha256 = (
            _final_inputs_sha256(
                plan,
                publication_override_sha256,
                final_input,
            )
            if final_input is not None
            else _final_inputs_sha256(plan, publication_override_sha256)
        )
        if publication_override_sha256 != snapshot.override_sha256:
            raise SchedulerPhaseError(
                "timing override hash changed during T-10 publication"
            )
        if publication_final_inputs_sha256 != snapshot.final_inputs_sha256:
            raise SchedulerPhaseError(
                "final input hash changed during T-10 publication"
            )
        published_at = _read_now(now)
        if published_at > publication_deadline:
            raise SchedulerPublicationDeadlineError(
                "package publication completed after T-10"
            )
        canonical_package_sha256 = hashlib.sha256(
            ",".join(validated_package.coupons).encode("utf-8")
        ).hexdigest()
        archive_payload = {
            "schema_version": 2 if final_input is not None else 1,
            "provenance": "pre_bet_runner",
            "drawing_id": plan.drawing_id,
            "drawing_number": plan.drawing,
            "ended_at": _timestamp(plan.ended_at),
            "archived_at": _timestamp(published_at),
            "stake": plan.stake,
            "coupon_count": validated_package.count,
            "cost": validated_package.cost,
            "source_path": str(package_path),
            "source_bytes_sha256": snapshot.sha256,
            "canonical_package_sha256": canonical_package_sha256,
        }
        if final_input is not None:
            archive_payload.update(
                {
                    "final_input_sha256": final_input.snapshot_sha256,
                    "probability_input_sha256": (
                        final_input.probability_input_sha256
                    ),
                    "final_input_captured_at": _timestamp(
                        final_input.captured_at
                    ),
                }
            )
        archive_payload["archive_manifest_sha256"] = _sha256_bytes(
            _canonical_json_bytes(archive_payload)
        )
        _write_exclusive_atomic(
            plan.output_dir,
            archive_manifest_path,
            _canonical_json_bytes(archive_payload) + b"\n",
        )
        if _read_now(now) > publication_deadline:
            raise SchedulerPublicationDeadlineError(
                "archive manifest completed after T-10"
            )
        archive_engine = init_db(plan.db)
        try:
            archived = import_prebet_package_manifest(
                get_session_factory(archive_engine),
                archive_manifest_path,
                package_path,
            )
            archive_completed_at = _read_now(now)
        finally:
            archive_engine.dispose()
        if archive_completed_at > publication_deadline:
            raise SchedulerPublicationDeadlineError(
                "durable archive completed after T-10"
            )
        if (
            archived.drawing_id != plan.drawing_id
            or archived.drawing_number != plan.drawing
            or archived.stake != plan.stake
            or archived.package_sha256 != canonical_package_sha256
            or archived.source_bytes_sha256 != snapshot.sha256
            or archived.provenance != "pre_bet_runner"
            or archived.archive_manifest_sha256
            != archive_payload["archive_manifest_sha256"]
            or (
                final_input is not None
                and (
                    archived.final_input_sha256
                    != final_input.snapshot_sha256
                    or archived.probability_input_sha256
                    != final_input.probability_input_sha256
                    or archived.final_input_captured_at
                    != _timestamp(final_input.captured_at)
                )
            )
        ):
            raise SchedulerPhaseError(
                "durable pre-bet package archive did not verify"
            )
        return {
            "outcome": "bet-ready",
            "decision": "PLAY",
            "reason": "final package verified and published no later than T-10",
            "package_path": package_path,
            "package_sha256": snapshot.sha256,
            "effective_bank": snapshot.effective_bank,
            "selected_count": snapshot.selected_count,
            "selected_cost": snapshot.selected_cost,
            "selected_snapshot": "final",
            "published_at": published_at,
        }
    except SchedulerPublicationDeadlineError as error:
        _remove_actionable_publication_artifacts(plan, run_dir)
        phase_absences.append(f"final: {_safe_error(error)}")
        return _no_package_terminal(phase_errors, phase_absences)
    except Exception as error:
        _remove_actionable_publication_artifacts(plan, run_dir)
        phase_errors.append(f"final: {_safe_error(error)}")
        return _no_package_terminal(phase_errors, phase_absences)


def _snapshot_validation_error(
    plan: SchedulerPlan,
    snapshot: PackageSnapshot,
    *,
    current_override_sha256: str | None,
    pinned_final_inputs_sha256: str | None,
    current_final_inputs_sha256: str,
    final_override_sha256: str | None,
) -> str | None:
    if snapshot.completed_at > plan.actionable_publication_deadline:
        return "package calculation completed inside the publication reserve"
    if not _valid_package_hash(
        plan,
        snapshot.path,
        snapshot.sha256,
        expected_count=snapshot.selected_count,
        expected_cost=snapshot.selected_cost,
    ):
        return "package path or SHA-256 changed"
    if snapshot.override_sha256 != current_override_sha256:
        return "timing override semantic hash changed before freeze"
    if (
        snapshot.phase != "final"
        or snapshot.final_inputs_sha256 is None
        or snapshot.final_inputs_sha256 != pinned_final_inputs_sha256
        or snapshot.final_inputs_sha256 != current_final_inputs_sha256
        or snapshot.override_sha256 != final_override_sha256
    ):
        return "final inputs do not match the atomic-final pin"
    return None


def _no_package_terminal(
    phase_errors: Sequence[str], phase_absences: Sequence[str]
) -> dict[str, Any]:
    if phase_errors:
        outcome: SchedulerOutcome = "failed"
        decision: Literal["NO BET", "FAILED"] = "FAILED"
        reason = "fail closed: " + "; ".join((*phase_errors, *phase_absences))
    else:
        outcome = "no-bet"
        decision = "NO BET"
        reason = (
            "no valid authoritative final PLAY package at T-10"
            + (": " + "; ".join(phase_absences) if phase_absences else "")
        )
    return {
        "outcome": outcome,
        "decision": decision,
        "reason": reason,
        "package_path": None,
        "package_sha256": None,
        "effective_bank": None,
        "selected_count": None,
        "selected_cost": None,
        "selected_snapshot": None,
        "published_at": None,
    }


def _finalize_status(
    plan: SchedulerPlan,
    *,
    run_id: str,
    run_dir: Path,
    status_path: Path,
    status: dict[str, Any],
    terminal: Mapping[str, Any],
    final_inputs_sha256: str | None,
    final_override_sha256: str | None,
    completed_at: datetime,
    now: Callable[[], datetime],
) -> SchedulerExecutionResult:
    publication_deadline = plan.freeze_at
    if terminal["outcome"] == "bet-ready":
        _validate_terminal_package(plan, run_dir, terminal)
    status.update(
        {
            "state": (
                "ignored" if terminal["outcome"] == "ignored" else "complete"
            ),
            "outcome": terminal["outcome"],
            "decision": terminal["decision"],
            "reason": terminal["reason"],
            "package_path": (
                None
                if terminal["package_path"] is None
                else str(terminal["package_path"])
            ),
            "package_sha256": terminal["package_sha256"],
            "requested_bank": plan.requested_bank,
            "effective_bank": terminal["effective_bank"],
            "selected_count": terminal["selected_count"],
            "selected_cost": terminal["selected_cost"],
            "selected_snapshot": terminal["selected_snapshot"],
            "published_at": (
                None
                if terminal["published_at"] is None
                else _timestamp(terminal["published_at"])
            ),
            "completed_at": _timestamp(completed_at),
            "final_inputs_sha256": final_inputs_sha256,
            "final_override_sha256": final_override_sha256,
        }
    )
    _write_status_atomic(plan.output_dir, status_path, status)
    _validate_status_file(plan, status_path, status)
    if terminal["outcome"] == "ignored":
        return _execution_result_from_status(status, run_dir, status_path)
    marker_path = run_dir / f".{terminal['outcome']}"
    marker_payload = {
        "drawing": plan.drawing,
        "run_id": run_id,
        "outcome": terminal["outcome"],
        "decision": terminal["decision"],
        "status_path": str(status_path),
        "package_path": status["package_path"],
        "package_sha256": status["package_sha256"],
        "completed_at": status["completed_at"],
    }
    try:
        if terminal["outcome"] == "bet-ready":
            _validate_terminal_package(plan, run_dir, terminal)
            _validate_status_file(plan, status_path, status)
            if _read_now(now) > publication_deadline:
                raise SchedulerPublicationDeadlineError(
                    "bet-ready marker deadline crossed after durable archive"
                )
        _write_exclusive_atomic(
            plan.output_dir,
            marker_path,
            _canonical_json_bytes(marker_payload) + b"\n",
        )
        if terminal["outcome"] == "bet-ready":
            try:
                if _read_now(now) > publication_deadline:
                    raise SchedulerPublicationDeadlineError(
                        "bet-ready marker completed after T-10"
                    )
                _validate_terminal_package(plan, run_dir, terminal)
                _validate_status_file(plan, status_path, status)
            except Exception:
                _unlink_output_path(
                    plan.output_dir,
                    marker_path,
                    missing_ok=True,
                )
                raise
    except Exception as error:
        if terminal["outcome"] != "failed":
            deadline_missed = isinstance(
                error,
                SchedulerPublicationDeadlineError,
            )
            failure_outcome = "no-bet" if deadline_missed else "failed"
            failure_decision = "NO BET" if deadline_missed else "FAILED"
            failure_reason = (
                f"terminal marker publication missed T-10: {_safe_error(error)}"
                if deadline_missed
                else f"terminal marker publication failed: {_safe_error(error)}"
            )
            status.update(
                {
                    "outcome": failure_outcome,
                    "decision": failure_decision,
                    "reason": failure_reason,
                    "package_path": None,
                    "package_sha256": None,
                    "effective_bank": None,
                    "selected_count": None,
                    "selected_cost": None,
                    "selected_snapshot": None,
                    "published_at": None,
                }
            )
            _remove_actionable_publication_artifacts(plan, run_dir)
            _write_status_atomic(plan.output_dir, status_path, status)
            marker_path = run_dir / f".{failure_outcome}"
            _write_exclusive_atomic(
                plan.output_dir,
                marker_path,
                _canonical_json_bytes(
                    {
                        **marker_payload,
                        "outcome": failure_outcome,
                        "decision": failure_decision,
                        "package_path": None,
                        "package_sha256": None,
                    }
                )
                + b"\n",
            )
        else:
            raise
    return _execution_result_from_status(status, run_dir, status_path)


def _parse_runner_manifest_phase_result_strict(
    context: SchedulerPhaseContext, manifest_path: Path
) -> SchedulerPhaseResult:
    """Parse one production runner manifest into a fail-closed phase result."""

    if context.phase not in ("fallback", "final"):
        raise SchedulerPhaseError(
            "runner manifests are valid only for package phases"
        )
    normalized_manifest = _normalized_path(manifest_path)
    try:
        _require_contained_path(
            context.work_dir,
            normalized_manifest,
            name="runner manifest",
        )
        payload = _load_strict_json(
            normalized_manifest,
            name="runner manifest",
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise SchedulerPhaseError(
            f"runner manifest could not be read: {error}"
        ) from error
    if not isinstance(payload, Mapping):
        raise SchedulerPhaseError("runner manifest must be a JSON object")
    _require_exact_phase_fields(
        payload,
        {
            "schema_version",
            "run_id",
            "command_status",
            "decision",
            "terminal_reason",
            "target",
            "config",
            "timeline",
            "collection",
            "eligibility",
            "coverage",
            "ev",
            "report_links",
            "replay",
            "final_input",
            "warnings",
        },
        "runner manifest",
    )
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != RUNNER_MANIFEST_SCHEMA_VERSION
    ):
        raise SchedulerPhaseError(
            "runner manifest schema_version must be "
            f"{RUNNER_MANIFEST_SCHEMA_VERSION}"
        )
    if payload["command_status"] != "success":
        raise SchedulerPhaseError("runner command_status must be success")
    _strict_text("runner run_id", payload["run_id"])
    if payload["replay"] is not None:
        return SchedulerPhaseResult.ignored(
            "non-production offline replay manifest ignored"
        )
    _validate_runner_manifest_diagnostics(payload)
    final_input_snapshot = None
    if context.atomic_final:
        final_input = _exact_phase_mapping(
            payload["final_input"],
            {
                "path",
                "captured_at",
                "snapshot_sha256",
                "detail_payload_sha256",
                "probability_input_sha256",
                "attempt_id",
            },
            "runner final input",
        )
        final_input_path = Path(
            _strict_text("runner final input path", final_input["path"])
        )
        _require_contained_path(
            context.run_dir, final_input_path, name="runner final input"
        )
        final_input_snapshot = load_final_input(
            final_input_path, expected_plan=context.plan
        )
        if (
            final_input_snapshot.attempt_id != context.run_id
            or final_input_snapshot.snapshot_sha256
            != _strict_sha256(
                "runner final input snapshot_sha256",
                final_input["snapshot_sha256"],
            )
            or final_input_snapshot.detail_payload_sha256
            != _strict_sha256(
                "runner final input detail_payload_sha256",
                final_input["detail_payload_sha256"],
            )
            or final_input_snapshot.probability_input_sha256
            != _strict_sha256(
                "runner final input probability_input_sha256",
                final_input["probability_input_sha256"],
            )
        ):
            raise SchedulerPhaseError("runner final input provenance mismatch")

    target = _exact_phase_mapping(
        payload["target"],
        {
            "drawing_id",
            "drawing_number",
            "deadline",
            "preflight_fingerprint",
            "final_fingerprint",
        },
        "runner target",
    )
    config = _exact_phase_mapping(
        payload["config"],
        {
            "bank",
            "stake",
            "mode",
            "final_lead_minutes",
            "safety_stop_minutes",
            "provider",
        },
        "runner config",
    )
    eligibility = _exact_phase_mapping(
        payload["eligibility"],
        {
            "status",
            "reason",
            "target_fingerprint",
            "fingerprint_match",
            "span_days",
            "missing_event_orders",
            "totobrief_count",
            "provider_count",
            "operator_override_count",
            "earliest_start",
            "latest_start",
            "raw",
            "effective",
            "override",
        },
        "runner eligibility",
    )
    effective_eligibility = _exact_phase_mapping(
        eligibility["effective"],
        _TIMING_PAYLOAD_FIELDS,
        "runner effective eligibility",
    )
    raw_eligibility = _exact_phase_mapping(
        eligibility["raw"],
        _TIMING_PAYLOAD_FIELDS,
        "runner raw eligibility",
    )
    top_eligibility = _validate_timing_payload(
        eligibility,
        name="runner eligibility",
    )
    validated_raw_eligibility = _validate_timing_payload(
        raw_eligibility,
        name="runner raw eligibility",
    )
    validated_effective_eligibility = _validate_timing_payload(
        effective_eligibility,
        name="runner effective eligibility",
    )
    validated_override = _validate_override_payload(eligibility["override"])
    ev = _exact_phase_mapping(
        payload["ev"],
        {
            "computed",
            "requested_bank",
            "effective_budget",
            "selected_cost",
            "unused_requested_bank",
            "input_fetched_at",
            "minimum_gross_ev",
            "prize_fund_factor",
            "possible_winnings_source",
            "jackpot_source",
            "self_dilution_ratio",
            "model_supported",
            "model_warning",
            "package_safety",
            "package",
            "sensitivity",
        },
        "runner EV payload",
    )
    package = _exact_phase_mapping(
        ev["package"],
        {
            "decision",
            "decision_reason",
            "coupons",
            "selected_count",
            "cost",
            "unused_bank",
            "expected_payout",
            "modeled_roi",
            "derived_brief",
        },
        "runner EV package",
    )
    package_safety = ev["package_safety"]
    recomputed_safety = None
    if package_safety is not None:
        safety = _exact_phase_mapping(
            package_safety,
            {
                "decision",
                "reason_codes",
                "reasons",
                "config",
                "evaluated_coupons",
                "package_sha256",
                "probability_input_sha256",
                "probabilities",
                "uploadable_coupons",
                "safety_sha256",
            },
            "runner package safety",
        )
        safety_config_payload = _exact_phase_mapping(
            safety["config"],
            {
                "near_fixed_share",
                "low_probability_threshold",
                "material_probability_threshold",
            },
            "runner package safety config",
        )
        try:
            manifest_safety_config = PackageSafetyConfig(**safety_config_payload)
        except (TypeError, ValueError) as error:
            raise SchedulerPhaseError(
                f"runner package safety config is invalid: {error}"
            ) from error
        approved_safety_config = context.plan.package_safety_config
        if manifest_safety_config != approved_safety_config:
            raise SchedulerPhaseError(
                "runner package safety config does not match scheduler plan"
            )
        _strict_sha256("package safety package_sha256", safety["package_sha256"])
        _strict_sha256(
            "package safety probability_input_sha256",
            safety["probability_input_sha256"],
        )
        _strict_sha256("package safety safety_sha256", safety["safety_sha256"])
        try:
            recomputed_safety = evaluate_package_safety(
                safety["evaluated_coupons"],
                safety["probabilities"],
                config=approved_safety_config,
            )
        except (TypeError, ValueError) as error:
            raise SchedulerPhaseError(
                f"runner package safety evidence is invalid: {error}"
            ) from error
        if json.loads(json.dumps(recomputed_safety.to_dict())) != package_safety:
            raise SchedulerPhaseError(
                "runner package safety evidence does not match canonical "
                "recomputation"
            )
        if (
            final_input_snapshot is not None
            and safety["probability_input_sha256"]
            != final_input_snapshot.probability_input_sha256
        ):
            raise SchedulerPhaseError(
                "package safety probabilities do not match final input"
            )
    plan = context.plan
    manifest_drawing_id = _strict_int("runner drawing_id", target["drawing_id"])
    manifest_drawing_number = _strict_int(
        "runner drawing_number", target["drawing_number"]
    )
    if manifest_drawing_id <= 0 or manifest_drawing_number <= 0:
        raise SchedulerPhaseError("runner target IDs must be positive")
    if (
        manifest_drawing_number != plan.drawing
        or (
            plan.drawing_id is not None
            and manifest_drawing_id != plan.drawing_id
        )
        or _parse_utc_datetime("runner deadline", target["deadline"])
        != plan.ended_at
    ):
        raise SchedulerPhaseError(
            "runner manifest target does not match scheduler plan"
        )
    preflight_fingerprint = _strict_sha256(
        "runner preflight_fingerprint",
        target["preflight_fingerprint"],
    )
    final_fingerprint = target["final_fingerprint"]
    if final_fingerprint is not None:
        final_fingerprint = _strict_sha256(
            "runner final_fingerprint",
            final_fingerprint,
        )
    if (
        _strict_int("runner bank", config["bank"]) != plan.requested_bank
        or _strict_int("runner stake", config["stake"]) != plan.stake
        or config["mode"] != "playable"
        or config["provider"] != plan.provider
        or _strict_int(
            "runner final_lead_minutes", config["final_lead_minutes"]
        )
        != (
            30
            if context.phase == "fallback"
            else (20 if context.atomic_final else 15)
        )
        or _strict_int(
            "runner safety_stop_minutes", config["safety_stop_minutes"]
        )
        != (12 if context.atomic_final else 10)
    ):
        raise SchedulerPhaseError(
            "runner manifest config does not match scheduler plan"
        )
    decision = payload["decision"]
    if type(decision) is not str or decision not in ("PLAY", "NO BET"):
        raise SchedulerPhaseError("runner decision must be PLAY or NO BET")
    reason = _strict_text("runner terminal_reason", payload["terminal_reason"])
    _validate_timing_relationships(
        context,
        target=target,
        eligibility=eligibility,
        raw=validated_raw_eligibility,
        effective=validated_effective_eligibility,
        override=validated_override,
        require_playable=decision == "PLAY",
    )
    if decision == "NO BET":
        _validate_no_bet_manifest(plan, ev, package)
        return SchedulerPhaseResult.no_bet(reason)
    if not _manifest_pinned_revalidation_ready(payload["collection"]):
        return SchedulerPhaseResult.no_bet(
            "pinned revalidation is not fresh matched 15/15"
        )
    if decision != "PLAY" or package["decision"] != "PLAY":
        raise SchedulerPhaseError(
            "runner manifest top-level and package decisions must both be PLAY"
        )
    if package_safety is None or safety["decision"] != "PLAY":
        raise SchedulerPhaseError("PLAY runner manifest lacks a passing safety gate")
    if safety["reason_codes"] or safety["reasons"]:
        raise SchedulerPhaseError("PLAY runner manifest retains safety reasons")
    if ev["computed"] is not True:
        raise SchedulerPhaseError("PLAY runner manifest must have computed EV")
    if (
        top_eligibility.status != "playable"
        or validated_effective_eligibility.status != "playable"
        or not top_eligibility.fingerprint_match
        or not validated_effective_eligibility.fingerprint_match
    ):
        raise SchedulerPhaseError(
            "PLAY runner manifest effective timing must be playable"
        )
    if ev["model_supported"] is not True:
        raise SchedulerPhaseError("PLAY runner manifest model must be supported")

    if final_fingerprint is None:
        raise SchedulerPhaseError("PLAY runner final fingerprint is absent")
    if preflight_fingerprint != final_fingerprint:
        raise SchedulerPhaseError("runner target fingerprint changed")
    if (
        validated_effective_eligibility.target_fingerprint
        != final_fingerprint
    ):
        raise SchedulerPhaseError(
            "effective timing fingerprint does not match final target"
        )

    requested_bank = _strict_int("EV requested_bank", ev["requested_bank"])
    effective_bank = _strict_int("EV effective_budget", ev["effective_budget"])
    selected_cost = _strict_int("EV selected_cost", ev["selected_cost"])
    unused_requested_bank = _strict_int(
        "EV unused_requested_bank", ev["unused_requested_bank"]
    )
    if requested_bank != plan.requested_bank:
        raise SchedulerPhaseError("EV requested_bank does not match scheduler plan")
    validate_config_bank(effective_bank, plan.stake)
    if effective_bank > requested_bank:
        raise SchedulerPhaseError("EV effective_budget exceeds requested bank")

    selected_count = _strict_int(
        "package selected_count", package["selected_count"]
    )
    package_cost = _strict_int("package cost", package["cost"])
    unused_bank = _strict_non_negative_int(
        "package unused_bank", package["unused_bank"]
    )
    if selected_count <= 0:
        raise SchedulerPhaseError("PLAY package selected_count must be positive")
    expected_cost = selected_count * plan.stake
    if (
        package_cost != expected_cost
        or selected_cost != expected_cost
        or package_cost > effective_bank
        or unused_bank != requested_bank - package_cost
        or unused_requested_bank != requested_bank - package_cost
    ):
        raise SchedulerPhaseError(
            "runner package bank, stake, count, and cost fields are inconsistent"
        )

    minimum_gross_ev = _finite_metric(
        "EV minimum_gross_ev", ev["minimum_gross_ev"]
    )
    prize_fund_factor = _finite_metric(
        "EV prize_fund_factor", ev["prize_fund_factor"]
    )
    self_dilution_ratio = _finite_metric(
        "EV self_dilution_ratio", ev["self_dilution_ratio"]
    )
    expected_payout = _finite_metric(
        "package expected_payout", package["expected_payout"]
    )
    modeled_roi = _finite_metric("package modeled_roi", package["modeled_roi"])
    if (
        prize_fund_factor < 0
        or self_dilution_ratio < 0
        or expected_payout < 0
    ):
        raise SchedulerPhaseError("runner EV metrics must be non-negative")
    if minimum_gross_ev != plan.minimum_gross_ev:
        raise SchedulerPhaseError(
            "EV minimum_gross_ev does not match scheduler plan"
        )
    if self_dilution_ratio > 0.01:
        raise SchedulerPhaseError("PLAY self-dilution ratio is unsupported")
    if ev["model_warning"] is not None:
        raise SchedulerPhaseError("PLAY runner manifest must not retain model warning")
    if not math.isclose(
        modeled_roi,
        expected_payout / package_cost - 1.0,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise SchedulerPhaseError("package modeled_roi is inconsistent with cost")
    _parse_utc_datetime("EV input_fetched_at", ev["input_fetched_at"])
    _strict_text("EV possible_winnings_source", ev["possible_winnings_source"])
    _strict_text("EV jackpot_source", ev["jackpot_source"])
    decision_reason = package["decision_reason"]
    if decision_reason is not None:
        _strict_text("package decision_reason", decision_reason)

    coupons = package["coupons"]
    if not isinstance(coupons, list) or not coupons:
        raise SchedulerPhaseError("PLAY runner manifest has no selected coupons")
    rows: list[tuple[int, str, float, float]] = []
    for item in coupons:
        row = _exact_phase_mapping(
            item,
            {"rank", "coupon", "gross_ev", "net_ev"},
            "runner coupon row",
        )
        rank = _strict_int("coupon rank", row["rank"])
        coupon = _strict_text("coupon", row["coupon"])
        gross_ev = _finite_metric("coupon gross_ev", row["gross_ev"])
        net_ev = _finite_metric("coupon net_ev", row["net_ev"])
        if not math.isclose(
            net_ev,
            gross_ev - 1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise SchedulerPhaseError("coupon gross_ev and net_ev are inconsistent")
        if gross_ev < minimum_gross_ev:
            raise SchedulerPhaseError("PLAY coupon is below minimum_gross_ev")
        rows.append((rank, coupon, gross_ev, net_ev))
    if len(rows) != selected_count:
        raise SchedulerPhaseError("runner coupon row count is inconsistent")
    computed_expected_payout = sum(
        gross_ev * plan.stake for _, _, gross_ev, _ in rows
    )
    if not math.isclose(
        expected_payout,
        computed_expected_payout,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise SchedulerPhaseError(
            "package expected_payout is inconsistent with coupon metrics"
        )
    package_bytes = _render_package_csv(rows)
    validated_package = _validate_package_csv(
        package_bytes,
        stake=plan.stake,
        minimum_gross_ev=plan.minimum_gross_ev,
        expected_count=selected_count,
        expected_cost=selected_cost,
    )
    if recomputed_safety is None:
        raise SchedulerPhaseError("PLAY runner manifest lacks recomputed safety")
    if recomputed_safety.uploadable_coupons != validated_package.coupons:
        raise SchedulerPhaseError(
            "PLAY runner package differs from safety-approved coupons"
        )
    _validate_derived_brief(package["derived_brief"], validated_package.coupons)
    _validate_sensitivity_rows(
        ev["sensitivity"],
        stake=plan.stake,
        requested_bank=requested_bank,
        effective_bank=effective_bank,
    )

    observed_override = (
        None
        if validated_override is None
        else validated_override.package_catalog_sha256
    )
    return SchedulerPhaseResult.play(
        package_bytes,
        reason=reason,
        effective_bank=effective_bank,
        selected_count=selected_count,
        selected_cost=selected_cost,
        override_sha256=observed_override,
        final_inputs_sha256=(
            None
            if final_input_snapshot is None
            else _final_inputs_sha256(
                context.plan,
                observed_override,
                final_input_snapshot,
            )
        ),
        package_sha256=_sha256_bytes(package_bytes),
    )


def parse_runner_manifest_phase_result(
    context: SchedulerPhaseContext, manifest_path: Path
) -> SchedulerPhaseResult:
    """Public fail-closed production manifest parser."""

    try:
        return _parse_runner_manifest_phase_result_strict(context, manifest_path)
    except SchedulerIntegrityError:
        raise
    except (
        OSError,
        OverflowError,
        SchedulerError,
        TypeError,
        ValueError,
    ) as error:
        raise SchedulerIntegrityError(
            f"runner manifest validation failed: {_safe_error(error)}",
            category="runner_manifest_integrity",
        ) from error


def _phase_result_from_runner_manifest(
    context: SchedulerPhaseContext, manifest_path: Path
) -> SchedulerPhaseResult:
    """Backward-compatible private alias for the strict production parser."""

    return parse_runner_manifest_phase_result(context, manifest_path)


@dataclass(frozen=True)
class _ValidatedPackageCSV:
    count: int
    cost: int
    coupons: tuple[str, ...]


@dataclass(frozen=True)
class _ValidatedTimingPayload:
    payload: Mapping[str, Any]
    status: str
    target_fingerprint: str | None
    fingerprint_match: bool
    span_days: int | None
    missing_event_orders: tuple[int, ...]
    totobrief_count: int | None
    provider_count: int | None
    operator_override_count: int | None
    earliest_start: datetime | None
    latest_start: datetime | None
    details_available: bool

    @property
    def known_count(self) -> int | None:
        if not self.details_available:
            return None
        return 15 - len(self.missing_event_orders)


@dataclass(frozen=True)
class _ValidatedOverrideEvent:
    event_order: int
    event_id: int
    starts_at: datetime
    source_ref: str


@dataclass(frozen=True)
class _ValidatedOverrideAudit:
    status: str
    preflight_catalog_sha256: str | None
    timing_catalog_sha256: str | None
    package_catalog_sha256: str | None
    override_id: str | None
    reviewer: str | None
    reviewed_at: datetime | None
    source_ref: str | None
    overlay_complete: bool
    applied_events: tuple[_ValidatedOverrideEvent, ...]
    preserved_event_orders: tuple[int, ...]


def _validate_runner_manifest_diagnostics(payload: Mapping[str, Any]) -> None:
    timeline = _exact_phase_mapping(
        payload["timeline"],
        {
            "preflight_at",
            "final_started_at",
            "collection_finished_at",
            "timing_finished_at",
            "audit_finished_at",
            "ev_finished_at",
            "finished_at",
            "elapsed_seconds",
        },
        "runner timeline",
    )
    _parse_utc_datetime("timeline preflight_at", timeline["preflight_at"])
    _parse_utc_datetime("timeline finished_at", timeline["finished_at"])
    for field in (
        "final_started_at",
        "collection_finished_at",
        "timing_finished_at",
        "audit_finished_at",
        "ev_finished_at",
    ):
        value = timeline[field]
        if value is not None:
            _parse_utc_datetime(f"timeline {field}", value)
    if _finite_metric("timeline elapsed_seconds", timeline["elapsed_seconds"]) < 0:
        raise SchedulerPhaseError("timeline elapsed_seconds must be non-negative")

    collection = payload["collection"]
    if collection is not None:
        collection_payload = _exact_phase_mapping(
            collection,
            {
                "final_collection_id",
                "collection_ids",
                "pass_count",
                "base_pass_count",
                "expansion_pass_count",
                "expanded",
                "final_horizon_days",
                "stop_reason",
                "total_requests",
                "total_cache_hits",
                "requested_schedule_date_count",
                "successful_schedule_date_count",
                "failed_schedule_date_count",
                "elapsed_seconds",
                "pinned_revalidation",
            },
            "runner collection",
        )
        _strict_text(
            "collection final_collection_id",
            collection_payload["final_collection_id"],
        )
        collection_ids = collection_payload["collection_ids"]
        if not isinstance(collection_ids, list) or not collection_ids:
            raise SchedulerPhaseError("collection_ids must be a non-empty list")
        for collection_id in collection_ids:
            _strict_text("collection_id", collection_id)
        pass_count = _strict_non_negative_int(
            "collection pass_count", collection_payload["pass_count"]
        )
        base_count = _strict_non_negative_int(
            "collection base_pass_count",
            collection_payload["base_pass_count"],
        )
        expansion_count = _strict_non_negative_int(
            "collection expansion_pass_count",
            collection_payload["expansion_pass_count"],
        )
        if pass_count != len(collection_ids) or pass_count != (
            base_count + expansion_count
        ):
            raise SchedulerPhaseError("collection pass counts are inconsistent")
        if type(collection_payload["expanded"]) is not bool:
            raise SchedulerPhaseError("collection expanded must be boolean")
        for field in (
            "final_horizon_days",
            "total_requests",
            "total_cache_hits",
            "requested_schedule_date_count",
            "successful_schedule_date_count",
            "failed_schedule_date_count",
        ):
            _strict_non_negative_int(
                f"collection {field}", collection_payload[field]
            )
        _strict_text("collection stop_reason", collection_payload["stop_reason"])
        if (
            _finite_metric(
                "collection elapsed_seconds",
                collection_payload["elapsed_seconds"],
            )
            < 0
        ):
            raise SchedulerPhaseError(
                "collection elapsed_seconds must be non-negative"
            )
        _validate_pinned_revalidation_payload(
            collection_payload["pinned_revalidation"]
        )

    coverage = payload["coverage"]
    if coverage is not None:
        coverage_payload = _exact_phase_mapping(
            coverage,
            {
                "gate_decision",
                "gate_reasons",
                "drawings",
                "events",
                "unique_match_rate",
                "consensus_rate",
                "ambiguous_matches",
                "explicit_dispositions",
                "operational_failures",
            },
            "runner coverage",
        )
        if coverage_payload["gate_decision"] not in ("GO", "PENDING", "STOP"):
            raise SchedulerPhaseError("coverage gate_decision is invalid")
        reasons = coverage_payload["gate_reasons"]
        if not isinstance(reasons, list):
            raise SchedulerPhaseError("coverage gate_reasons must be a list")
        for reason in reasons:
            _strict_text("coverage gate reason", reason)
        for field in (
            "drawings",
            "events",
            "ambiguous_matches",
            "explicit_dispositions",
            "operational_failures",
        ):
            _strict_non_negative_int(f"coverage {field}", coverage_payload[field])
        for field in ("unique_match_rate", "consensus_rate"):
            rate = _finite_metric(f"coverage {field}", coverage_payload[field])
            if not 0 <= rate <= 1:
                raise SchedulerPhaseError(f"coverage {field} must be in [0, 1]")

    links = _exact_phase_mapping(
        payload["report_links"],
        {"external", "ev"},
        "runner report_links",
    )
    for field in ("external", "ev"):
        values = links[field]
        if not isinstance(values, list):
            raise SchedulerPhaseError(f"report_links {field} must be a list")
        for value in values:
            _strict_text(f"report_links {field} path", value)
    warnings = payload["warnings"]
    if not isinstance(warnings, list):
        raise SchedulerPhaseError("runner warnings must be a list")
    for warning in warnings:
        _strict_text("runner warning", warning)


def _manifest_pinned_revalidation_ready(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    return _validate_pinned_revalidation_payload(
        value.get("pinned_revalidation")
    )


def _validate_pinned_revalidation_payload(value: object) -> bool:
    if value is None:
        return False
    summary = _exact_phase_mapping(
        value,
        {
            "expected_count",
            "matched_count",
            "missing_event_orders",
            "provider_failure_event_orders",
            "stale_event_orders",
            "date_failure_event_orders",
            "identity_failure_event_orders",
            "start_time_failure_event_orders",
            "failed_schedule_dates",
            "oldest_schedule_fetched_at",
            "newest_schedule_fetched_at",
            "maximum_schedule_age_seconds",
            "schedule_fresh",
            "provider_checks_passed",
            "fixture_checks_passed",
            "team_checks_passed",
            "orientation_checks_passed",
            "start_time_checks_passed",
            "required_dates_complete",
            "ready_for_play",
            "events",
        },
        "pinned revalidation",
    )
    expected = _strict_non_negative_int(
        "pinned revalidation expected_count", summary["expected_count"]
    )
    matched = _strict_non_negative_int(
        "pinned revalidation matched_count", summary["matched_count"]
    )
    if expected != 15 or matched > expected:
        raise SchedulerPhaseError(
            "pinned revalidation counts must describe exactly 15 events"
        )
    order_fields = (
        "missing_event_orders",
        "provider_failure_event_orders",
        "stale_event_orders",
        "date_failure_event_orders",
        "identity_failure_event_orders",
        "start_time_failure_event_orders",
    )
    orders: dict[str, tuple[int, ...]] = {}
    for field in order_fields:
        raw = summary[field]
        if not isinstance(raw, list) or any(
            type(order) is not int or not 0 <= order < 15 for order in raw
        ):
            raise SchedulerPhaseError(
                f"pinned revalidation {field} must contain event orders"
            )
        if raw != sorted(set(raw)):
            raise SchedulerPhaseError(
                f"pinned revalidation {field} must be ordered and unique"
            )
        orders[field] = tuple(raw)
    failed_dates = summary["failed_schedule_dates"]
    if not isinstance(failed_dates, list):
        raise SchedulerPhaseError(
            "pinned revalidation failed_schedule_dates must be a list"
        )
    for item in failed_dates:
        _strict_text("pinned revalidation failed schedule date", item)
    events = summary["events"]
    if not isinstance(events, list) or len(events) != 15:
        raise SchedulerPhaseError(
            "pinned revalidation events must contain exactly 15 rows"
        )
    matched_orders = []
    for expected_order, item in enumerate(events):
        row = _exact_phase_mapping(
            item,
            {
                "event_order",
                "status",
                "reason",
                "source_provider",
                "revalidation_method",
                "evidence_id",
                "evidence_hash",
            },
            "pinned revalidation event",
        )
        if _strict_int("pinned event_order", row["event_order"]) != expected_order:
            raise SchedulerPhaseError(
                "pinned revalidation event orders must be 0 through 14"
            )
        if row["status"] not in {"matched", "missing", "provider_failure"}:
            raise SchedulerPhaseError("pinned revalidation event status is invalid")
        _strict_text("pinned revalidation event reason", row["reason"])
        source_provider = _strict_text(
            "pinned revalidation source_provider", row["source_provider"]
        )
        method = _strict_text(
            "pinned revalidation method", row["revalidation_method"]
        )
        if source_provider == "reviewed-schedule":
            if (
                method != "reviewed-catalog-v1"
                or not isinstance(row["evidence_id"], str)
                or not isinstance(row["evidence_hash"], str)
            ):
                raise SchedulerPhaseError(
                    "reviewed pin revalidation provenance is incomplete"
                )
        elif source_provider == "api-sports":
            if method != "api-sports-fixture-v1":
                raise SchedulerPhaseError(
                    "API-Sports pin revalidation method is invalid"
                )
        else:
            raise SchedulerPhaseError(
                "pinned revalidation source provider is unknown"
            )
        if row["status"] == "matched":
            matched_orders.append(expected_order)
    if matched != len(matched_orders):
        raise SchedulerPhaseError(
            "pinned revalidation matched count is inconsistent"
        )
    boolean_fields = (
        "schedule_fresh",
        "provider_checks_passed",
        "fixture_checks_passed",
        "team_checks_passed",
        "orientation_checks_passed",
        "start_time_checks_passed",
        "required_dates_complete",
        "ready_for_play",
    )
    for field in boolean_fields:
        if type(summary[field]) is not bool:
            raise SchedulerPhaseError(f"pinned revalidation {field} must be boolean")
    for field in ("oldest_schedule_fetched_at", "newest_schedule_fetched_at"):
        if summary[field] is not None:
            _parse_utc_datetime(f"pinned revalidation {field}", summary[field])
    maximum_age = summary["maximum_schedule_age_seconds"]
    if maximum_age is not None and _finite_metric(
        "pinned revalidation maximum_schedule_age_seconds", maximum_age
    ) < 0:
        raise SchedulerPhaseError(
            "pinned revalidation maximum schedule age must be non-negative"
        )
    ready = bool(summary["ready_for_play"])
    derived_ready = (
        matched == 15
        and not any(orders.values())
        and not failed_dates
        and all(bool(summary[field]) for field in boolean_fields[:-1])
    )
    if ready != derived_ready:
        raise SchedulerPhaseError(
            "pinned revalidation ready status is inconsistent"
        )
    return ready


def _validate_timing_payload(
    value: Mapping[str, Any], *, name: str
) -> _ValidatedTimingPayload:
    status = value["status"]
    if type(status) is not str or status not in {
        "playable",
        "multi_day",
        "unknown",
        "absent",
        "not_checked",
    }:
        raise SchedulerPhaseError(f"{name} status is invalid")
    _strict_text(f"{name} reason", value["reason"])
    fingerprint = value["target_fingerprint"]
    if fingerprint is not None:
        fingerprint = _strict_sha256(f"{name} target_fingerprint", fingerprint)
    fingerprint_match = value["fingerprint_match"]
    if type(fingerprint_match) is not bool:
        raise SchedulerPhaseError(f"{name} fingerprint_match must be boolean")
    if fingerprint_match and fingerprint is None:
        raise SchedulerPhaseError(
            f"{name} cannot match an absent target fingerprint"
        )

    missing_orders_value = value["missing_event_orders"]
    if not isinstance(missing_orders_value, list):
        raise SchedulerPhaseError(f"{name} missing_event_orders must be a list")
    if any(
        type(order) is not int or not 0 <= order < 15
        for order in missing_orders_value
    ):
        raise SchedulerPhaseError(f"{name} contains invalid missing event orders")
    if missing_orders_value != sorted(set(missing_orders_value)):
        raise SchedulerPhaseError(
            f"{name} missing event orders must be ordered and unique"
        )
    missing_orders = tuple(missing_orders_value)

    counts: list[int | None] = []
    for field in (
        "totobrief_count",
        "provider_count",
        "operator_override_count",
    ):
        count = value[field]
        if count is not None:
            count = _strict_non_negative_int(f"{name} {field}", count)
            if count > 15:
                raise SchedulerPhaseError(f"{name} {field} cannot exceed 15")
        counts.append(count)
    totobrief_count, provider_count, operator_override_count = counts

    span_value = value["span_days"]
    span_days = (
        None
        if span_value is None
        else _strict_non_negative_int(f"{name} span_days", span_value)
    )
    earliest_value = value["earliest_start"]
    latest_value = value["latest_start"]
    earliest_start = (
        None
        if earliest_value is None
        else _parse_utc_datetime(f"{name} earliest_start", earliest_value)
    )
    latest_start = (
        None
        if latest_value is None
        else _parse_utc_datetime(f"{name} latest_start", latest_value)
    )

    details_available = all(count is not None for count in counts)
    if not details_available:
        if not (
            totobrief_count is None
            and provider_count is None
            and operator_override_count in (None, 0)
        ):
            raise SchedulerPhaseError(f"{name} timing counts are incomplete")
        if (
            span_days is not None
            or missing_orders
            or earliest_start is not None
            or latest_start is not None
        ):
            raise SchedulerPhaseError(
                f"{name} unavailable timing details are inconsistent"
            )
        if status not in {"unknown", "absent", "not_checked"}:
            raise SchedulerPhaseError(
                f"{name} status requires complete timing details"
            )
    else:
        assert totobrief_count is not None
        assert provider_count is not None
        assert operator_override_count is not None
        if span_days is None:
            raise SchedulerPhaseError(f"{name} span_days must be present")
        known_count = 15 - len(missing_orders)
        if (
            totobrief_count + provider_count + operator_override_count
            != known_count
        ):
            raise SchedulerPhaseError(
                f"{name} source counts and missing event orders are inconsistent"
            )
        if known_count == 0:
            if earliest_start is not None or latest_start is not None or span_days != 0:
                raise SchedulerPhaseError(
                    f"{name} empty timing bounds are inconsistent"
                )
        else:
            if earliest_start is None or latest_start is None:
                raise SchedulerPhaseError(
                    f"{name} known starts require both timing bounds"
                )
            if earliest_start > latest_start:
                raise SchedulerPhaseError(
                    f"{name} earliest_start is after latest_start"
                )
            expected_span = (
                latest_start.astimezone(_MOSCOW).date()
                - earliest_start.astimezone(_MOSCOW).date()
            ).days + 1
            if span_days != expected_span:
                raise SchedulerPhaseError(
                    f"{name} span_days is inconsistent with timing bounds"
                )
        expected_status = (
            "multi_day"
            if span_days > 2
            else "unknown"
            if missing_orders
            else "playable"
        )
        if status != expected_status:
            raise SchedulerPhaseError(
                f"{name} status is inconsistent with timing completeness"
            )
        if status == "playable" and not fingerprint_match:
            raise SchedulerPhaseError(
                f"{name} playable status requires an exact fingerprint match"
            )

    return _ValidatedTimingPayload(
        payload=value,
        status=status,
        target_fingerprint=fingerprint,
        fingerprint_match=fingerprint_match,
        span_days=span_days,
        missing_event_orders=missing_orders,
        totobrief_count=totobrief_count,
        provider_count=provider_count,
        operator_override_count=operator_override_count,
        earliest_start=earliest_start,
        latest_start=latest_start,
        details_available=details_available,
    )


def _validate_override_payload(value: object) -> _ValidatedOverrideAudit | None:
    if value is None:
        return None
    override = _exact_phase_mapping(
        value,
        {
            "status",
            "preflight_catalog_sha256",
            "timing_catalog_sha256",
            "package_catalog_sha256",
            "override_id",
            "reviewer",
            "reviewed_at",
            "source_ref",
            "overlay_complete",
            "applied_events",
            "preserved_event_orders",
            "diagnostics",
        },
        "runner timing override",
    )
    status = override["status"]
    if type(status) is not str or status not in {
        "applied",
        "not_applied",
        "invalid_catalog",
        "catalog_changed",
        "hash_unverified",
    }:
        raise SchedulerPhaseError("timing override status is invalid")

    hashes: list[str | None] = []
    for field in (
        "preflight_catalog_sha256",
        "timing_catalog_sha256",
        "package_catalog_sha256",
    ):
        digest = override[field]
        if digest is not None:
            digest = _strict_sha256(f"timing override {field}", digest)
        hashes.append(digest)
    preflight_hash, timing_hash, package_hash = hashes

    override_id = override["override_id"]
    reviewer = override["reviewer"]
    reviewed_at_value = override["reviewed_at"]
    source_ref = override["source_ref"]
    provenance = (override_id, reviewer, reviewed_at_value, source_ref)
    if any(item is not None for item in provenance) and not all(
        item is not None for item in provenance
    ):
        raise SchedulerPhaseError("timing override provenance must be complete")
    reviewed_at: datetime | None = None
    if override_id is not None:
        override_id = _strict_text("timing override override_id", override_id)
        reviewer = _strict_text("timing override reviewer", reviewer)
        reviewed_at = _parse_utc_datetime(
            "timing override reviewed_at", reviewed_at_value
        )
        source_ref = _strict_text("timing override source_ref", source_ref)

    overlay_complete = override["overlay_complete"]
    if type(overlay_complete) is not bool:
        raise SchedulerPhaseError("timing override overlay_complete must be boolean")
    events_value = override["applied_events"]
    if not isinstance(events_value, list):
        raise SchedulerPhaseError("timing override applied_events must be a list")
    events: list[_ValidatedOverrideEvent] = []
    for event in events_value:
        event_payload = _exact_phase_mapping(
            event,
            {"event_order", "event_id", "starts_at", "source_ref"},
            "timing override event",
        )
        order = _strict_non_negative_int(
            "timing override event_order", event_payload["event_order"]
        )
        if order >= 15:
            raise SchedulerPhaseError("timing override event_order is invalid")
        event_id = _strict_int(
            "timing override event_id", event_payload["event_id"]
        )
        if event_id <= 0:
            raise SchedulerPhaseError("timing override event_id must be positive")
        events.append(
            _ValidatedOverrideEvent(
                event_order=order,
                event_id=event_id,
                starts_at=_parse_utc_datetime(
                    "timing override starts_at", event_payload["starts_at"]
                ),
                source_ref=_strict_text(
                    "timing override source_ref", event_payload["source_ref"]
                ),
            )
        )
    event_orders = tuple(event.event_order for event in events)
    if event_orders != tuple(sorted(set(event_orders))):
        raise SchedulerPhaseError(
            "timing override applied event orders must be ordered and unique"
        )
    event_ids = tuple(event.event_id for event in events)
    if len(set(event_ids)) != len(event_ids):
        raise SchedulerPhaseError("timing override event IDs must be unique")

    preserved_value = override["preserved_event_orders"]
    if not isinstance(preserved_value, list) or any(
        type(order) is not int or not 0 <= order < 15
        for order in preserved_value
    ):
        raise SchedulerPhaseError(
            "timing override preserved_event_orders is invalid"
        )
    if preserved_value != sorted(set(preserved_value)):
        raise SchedulerPhaseError(
            "timing override preserved event orders must be ordered and unique"
        )
    preserved = tuple(preserved_value)
    if set(event_orders) & set(preserved):
        raise SchedulerPhaseError(
            "timing override applied and preserved event orders overlap"
        )

    diagnostics = override["diagnostics"]
    if not isinstance(diagnostics, list):
        raise SchedulerPhaseError("timing override diagnostics must be a list")
    for diagnostic in diagnostics:
        _strict_text("timing override diagnostic", diagnostic)

    if status == "applied" and (
        not overlay_complete
        or override_id is None
        or set(event_orders) | set(preserved) != set(range(15))
        or preflight_hash is None
        or timing_hash is None
    ):
        raise SchedulerPhaseError("applied timing override audit is incomplete")
    if package_hash is not None and status != "applied":
        raise SchedulerPhaseError(
            "timing override package hash requires applied status"
        )

    return _ValidatedOverrideAudit(
        status=status,
        preflight_catalog_sha256=preflight_hash,
        timing_catalog_sha256=timing_hash,
        package_catalog_sha256=package_hash,
        override_id=override_id,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        source_ref=source_ref,
        overlay_complete=overlay_complete,
        applied_events=tuple(events),
        preserved_event_orders=preserved,
    )


def _validate_timing_relationships(
    context: SchedulerPhaseContext,
    *,
    target: Mapping[str, Any],
    eligibility: Mapping[str, Any],
    raw: _ValidatedTimingPayload,
    effective: _ValidatedTimingPayload,
    override: _ValidatedOverrideAudit | None,
    require_playable: bool,
) -> None:
    for field in _TIMING_PAYLOAD_FIELDS:
        if eligibility[field] != effective.payload[field]:
            raise SchedulerPhaseError(
                "runner top-level eligibility must exactly match effective timing"
            )
    if raw.details_available and raw.operator_override_count != 0:
        raise SchedulerPhaseError(
            "raw timing cannot contain operator override starts"
        )
    if require_playable and (
        effective.status != "playable"
        or not effective.details_available
        or effective.known_count != 15
        or effective.missing_event_orders
        or effective.span_days not in (1, 2)
    ):
        raise SchedulerPhaseError(
            "PLAY runner manifest effective timing must be complete and playable"
        )

    plan = context.plan
    if plan.timing_overrides is None:
        if override is not None:
            raise SchedulerPhaseError(
                "timing override audit must be absent without a configured catalog"
            )
        if context.override_sha256 is not None:
            raise SchedulerPhaseError(
                "phase override hash is invalid without a configured catalog"
            )
        if raw.payload != effective.payload:
            raise SchedulerPhaseError(
                "effective timing cannot change without a configured override"
            )
        if effective.operator_override_count not in (None, 0):
            raise SchedulerPhaseError(
                "effective timing claims an unconfigured override transformation"
            )
        return

    if override is None:
        if raw.payload != effective.payload:
            raise SchedulerPhaseError(
                "effective timing changed without an override audit"
            )
        if require_playable:
            raise SchedulerPhaseError(
                "configured timing override must have a complete applied audit"
            )
        return
    if override.status != "applied":
        if effective.status != "unknown" or effective.details_available:
            raise SchedulerPhaseError(
                "unusable timing override must leave effective timing unknown"
            )
        if require_playable:
            raise SchedulerPhaseError("PLAY timing override must be applied")
        return

    _validate_applied_override(
        context,
        target=target,
        raw=raw,
        effective=effective,
        override=override,
        require_package_hash=require_playable,
    )


def _validate_applied_override(
    context: SchedulerPhaseContext,
    *,
    target: Mapping[str, Any],
    raw: _ValidatedTimingPayload,
    effective: _ValidatedTimingPayload,
    override: _ValidatedOverrideAudit,
    require_package_hash: bool,
) -> None:
    plan = context.plan
    pinned_hash = context.override_sha256
    if pinned_hash is None:
        raise SchedulerPhaseError("configured timing override hash was not pinned")
    _strict_sha256("phase timing override hash", pinned_hash)
    if (
        override.preflight_catalog_sha256 != pinned_hash
        or override.timing_catalog_sha256 != pinned_hash
        or (
            require_package_hash
            and override.package_catalog_sha256 != pinned_hash
        )
        or (
            override.package_catalog_sha256 is not None
            and override.package_catalog_sha256 != pinned_hash
        )
    ):
        raise SchedulerPhaseError(
            "runner timing override hashes do not match the phase pin"
        )
    assert plan.timing_overrides is not None
    catalog = load_timing_override_catalog(plan.timing_overrides)
    if timing_override_catalog_sha256(catalog) != pinned_hash:
        raise SchedulerPhaseError(
            "timing override semantic hash changed during manifest validation"
        )
    records = tuple(
        record
        for record in catalog.records
        if record.override_id == override.override_id
    )
    if len(records) != 1 or not records[0].is_complete:
        raise SchedulerPhaseError(
            "applied timing override must match one complete catalog record"
        )
    record = records[0]
    drawing_id = _strict_int("runner drawing_id", target["drawing_id"])
    drawing_number = _strict_int(
        "runner drawing_number", target["drawing_number"]
    )
    final_fingerprint = target["final_fingerprint"]
    if (
        record.target_fingerprint != final_fingerprint
        or (
            record.drawing_id is not None
            and record.drawing_id != drawing_id
        )
        or (
            record.drawing_number is not None
            and record.drawing_number != drawing_number
        )
        or record.reviewer != override.reviewer
        or record.reviewed_at != override.reviewed_at
        or record.source_ref != override.source_ref
    ):
        raise SchedulerPhaseError(
            "timing override audit provenance does not match the catalog"
        )
    if (
        record.reviewed_at < plan.ended_at - timedelta(days=7)
        or record.reviewed_at > context.started_at
    ):
        raise SchedulerPhaseError("timing override review time is inadmissible")

    record_events = {event.event_order: event for event in record.events}
    latest_start = plan.ended_at + timedelta(days=5)
    for record_event in record.events:
        if not plan.ended_at <= record_event.starts_at <= latest_start:
            raise SchedulerPhaseError(
                "timing override event start is outside the legal horizon"
            )
    for event in override.applied_events:
        record_event = record_events[event.event_order]
        expected_source = record_event.source_ref or record.source_ref
        if (
            event.event_id != record_event.event_id
            or event.starts_at != record_event.starts_at
            or event.source_ref != expected_source
        ):
            raise SchedulerPhaseError(
                "applied timing override event provenance does not match catalog"
            )

    if not raw.details_available or not effective.details_available:
        raise SchedulerPhaseError(
            "applied timing override requires complete raw and effective counts"
        )
    applied_orders = tuple(
        event.event_order for event in override.applied_events
    )
    expected_preserved = tuple(
        order for order in range(15) if order not in raw.missing_event_orders
    )
    if (
        applied_orders != raw.missing_event_orders
        or override.preserved_event_orders != expected_preserved
    ):
        raise SchedulerPhaseError(
            "timing override applied/preserved orders contradict raw timing"
        )
    if effective.status == "playable" and raw.status != "playable" and (
        raw.status != "unknown" or not raw.missing_event_orders
    ):
        raise SchedulerPhaseError(
            "a playable overlay can only repair incomplete raw timing"
        )
    if (
        raw.target_fingerprint != effective.target_fingerprint
        or not raw.fingerprint_match
        or not effective.fingerprint_match
        or raw.totobrief_count != effective.totobrief_count
        or raw.provider_count != effective.provider_count
        or effective.operator_override_count != len(applied_orders)
        or effective.missing_event_orders
    ):
        raise SchedulerPhaseError(
            "effective timing counts or fingerprint contradict the override overlay"
        )

    known_bounds = [
        value
        for value in (raw.earliest_start, raw.latest_start)
        if value is not None
    ]
    known_bounds.extend(event.starts_at for event in override.applied_events)
    if (
        not known_bounds
        or effective.earliest_start != min(known_bounds)
        or effective.latest_start != max(known_bounds)
    ):
        raise SchedulerPhaseError(
            "effective timing bounds contradict the applied override"
        )


def _validate_package_csv(
    content: bytes,
    *,
    stake: int,
    minimum_gross_ev: float,
    expected_count: int | None = None,
    expected_cost: int | None = None,
) -> _ValidatedPackageCSV:
    """Validate the complete operator CSV contract without coercive parsing."""

    if not isinstance(content, bytes) or not content:
        raise SchedulerPhaseError("PLAY package CSV must be non-empty bytes")
    expected_header = ",".join(PACKAGE_CSV_HEADER).encode("ascii") + b"\n"
    if not content.startswith(expected_header):
        raise SchedulerPhaseError(
            f"package CSV header must be exactly {','.join(PACKAGE_CSV_HEADER)}"
        )
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SchedulerPhaseError("package CSV must be valid UTF-8") from error
    if "\x00" in text:
        raise SchedulerPhaseError("package CSV must not contain NUL bytes")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        raise SchedulerPhaseError(f"package CSV is malformed: {error}") from error
    if not rows or tuple(rows[0]) != PACKAGE_CSV_HEADER:
        raise SchedulerPhaseError(
            f"package CSV header must be exactly {','.join(PACKAGE_CSV_HEADER)}"
        )
    data_rows = rows[1:]
    if not data_rows:
        raise SchedulerPhaseError("PLAY package CSV must contain at least one coupon")

    coupons: list[str] = []
    ranks: list[int] = []
    for row_number, row in enumerate(data_rows, start=2):
        if len(row) != len(PACKAGE_CSV_HEADER):
            raise SchedulerPhaseError(
                f"package CSV row {row_number} must contain exactly four fields"
            )
        rank_text, coupon, gross_ev_text, net_ev_text = row
        if any(value != value.strip() for value in row):
            raise SchedulerPhaseError(
                f"package CSV row {row_number} contains surrounding whitespace"
            )
        try:
            rank = int(rank_text)
        except ValueError as error:
            raise SchedulerPhaseError(
                f"package CSV row {row_number} rank is invalid"
            ) from error
        if rank <= 0 or str(rank) != rank_text:
            raise SchedulerPhaseError(
                f"package CSV row {row_number} rank must be canonical and positive"
            )
        if _COUPON_PATTERN.fullmatch(coupon) is None:
            raise SchedulerPhaseError(
                f"package CSV row {row_number} coupon must contain "
                "exactly 15 characters from 1/X/2"
            )
        try:
            gross_ev = float(gross_ev_text)
            net_ev = float(net_ev_text)
        except ValueError as error:
            raise SchedulerPhaseError(
                f"package CSV row {row_number} EV metric is invalid"
            ) from error
        if not math.isfinite(gross_ev) or not math.isfinite(net_ev):
            raise SchedulerPhaseError(
                f"package CSV row {row_number} EV metrics must be finite"
            )
        if gross_ev < 0 or not math.isclose(
            net_ev,
            gross_ev - 1.0,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise SchedulerPhaseError(
                f"package CSV row {row_number} EV metrics are inconsistent"
            )
        if gross_ev < minimum_gross_ev:
            raise SchedulerPhaseError(
                f"package CSV row {row_number} is below plan minimum_gross_ev"
            )
        ranks.append(rank)
        coupons.append(coupon)

    if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
        raise SchedulerPhaseError(
            "package CSV ranks must be unique and strictly increasing"
        )
    if len(set(coupons)) != len(coupons):
        raise SchedulerPhaseError("package CSV coupons must be unique")
    count = len(coupons)
    cost = count * stake
    if expected_count is not None and expected_count != count:
        raise SchedulerPhaseError("package CSV row count does not match selected_count")
    if expected_cost is not None and expected_cost != cost:
        raise SchedulerPhaseError("package CSV cost does not equal count times stake")
    return _ValidatedPackageCSV(count=count, cost=cost, coupons=tuple(coupons))


def _validate_no_bet_manifest(
    plan: SchedulerPlan,
    ev: Mapping[str, Any],
    package: Mapping[str, Any],
) -> None:
    if package["decision"] != "NO BET":
        raise SchedulerPhaseError(
            "NO BET runner manifest must have nested package decision NO BET"
        )
    if (
        _strict_int("NO BET requested_bank", ev["requested_bank"])
        != plan.requested_bank
    ):
        raise SchedulerPhaseError("NO BET requested_bank is inconsistent")
    _strict_text("NO BET decision_reason", package["decision_reason"])
    if not isinstance(package["coupons"], list) or package["coupons"]:
        raise SchedulerPhaseError("NO BET runner manifest is not coupon-free")
    if not isinstance(package["derived_brief"], list) or package["derived_brief"]:
        raise SchedulerPhaseError("NO BET runner manifest is not zero-cost")
    computed = ev["computed"]
    if type(computed) is not bool:
        raise SchedulerPhaseError("NO BET computed flag must be boolean")
    if not isinstance(ev["sensitivity"], list):
        raise SchedulerPhaseError("EV sensitivity must be a list")
    if computed is False:
        if any(
            value is not None
            for value in (
                ev["effective_budget"],
                ev["selected_cost"],
                ev["unused_requested_bank"],
                ev["input_fetched_at"],
                ev["minimum_gross_ev"],
                ev["prize_fund_factor"],
                ev["possible_winnings_source"],
                ev["jackpot_source"],
                ev["self_dilution_ratio"],
                ev["model_supported"],
                ev["model_warning"],
                package["selected_count"],
                package["cost"],
                package["unused_bank"],
                package["expected_payout"],
                package["modeled_roi"],
            )
        ):
            raise SchedulerPhaseError(
                "uncomputed NO BET manifest must use unavailable package metrics"
            )
        if ev["sensitivity"] != []:
            raise SchedulerPhaseError(
                "uncomputed NO BET manifest must not contain sensitivity rows"
            )
        return
    effective = _strict_non_negative_int(
        "NO BET effective_budget", ev["effective_budget"]
    )
    if effective > plan.requested_bank or effective % plan.stake:
        raise SchedulerPhaseError("NO BET effective_budget is inconsistent")
    selected_cost = _strict_non_negative_int(
        "NO BET selected_cost", ev["selected_cost"]
    )
    unused_requested = _strict_non_negative_int(
        "NO BET unused_requested_bank", ev["unused_requested_bank"]
    )
    selected_count = _strict_non_negative_int(
        "NO BET package selected_count", package["selected_count"]
    )
    package_cost = _strict_non_negative_int(
        "NO BET package cost", package["cost"]
    )
    unused_bank = _strict_non_negative_int(
        "NO BET package unused_bank", package["unused_bank"]
    )
    expected_payout = _finite_metric(
        "NO BET package expected_payout", package["expected_payout"]
    )
    if (
        selected_cost != 0
        or unused_requested != plan.requested_bank
        or selected_count != 0
        or package_cost != 0
        or unused_bank != plan.requested_bank
        or expected_payout != 0.0
        or package["modeled_roi"] is not None
    ):
        raise SchedulerPhaseError("computed NO BET manifest must be zero-cost")
    _parse_utc_datetime("NO BET input_fetched_at", ev["input_fetched_at"])
    minimum_gross_ev = _finite_metric(
        "NO BET minimum_gross_ev", ev["minimum_gross_ev"]
    )
    if minimum_gross_ev != plan.minimum_gross_ev:
        raise SchedulerPhaseError(
            "NO BET minimum_gross_ev does not match scheduler plan"
        )
    prize_fund_factor = _finite_metric(
        "NO BET prize_fund_factor", ev["prize_fund_factor"]
    )
    if prize_fund_factor < 0:
        raise SchedulerPhaseError("NO BET prize_fund_factor must be non-negative")
    _strict_text(
        "NO BET possible_winnings_source", ev["possible_winnings_source"]
    )
    _strict_text("NO BET jackpot_source", ev["jackpot_source"])
    if _finite_metric(
        "NO BET self_dilution_ratio", ev["self_dilution_ratio"]
    ) < 0:
        raise SchedulerPhaseError(
            "NO BET self_dilution_ratio must be non-negative"
        )
    if type(ev["model_supported"]) is not bool:
        raise SchedulerPhaseError("NO BET model_supported must be boolean")
    if ev["model_warning"] is not None:
        _strict_text("NO BET model_warning", ev["model_warning"])
    _validate_sensitivity_rows(
        ev["sensitivity"],
        stake=plan.stake,
        requested_bank=plan.requested_bank,
        effective_bank=effective,
    )


def _validate_derived_brief(value: object, coupons: Sequence[str]) -> None:
    if not isinstance(value, list) or len(value) != 15:
        raise SchedulerPhaseError("package derived_brief must contain 15 positions")
    expected = [
        "".join(
            outcome
            for outcome in ("1", "X", "2")
            if any(coupon[index] == outcome for coupon in coupons)
        )
        for index in range(15)
    ]
    if value != expected:
        raise SchedulerPhaseError("package derived_brief is inconsistent with coupons")


def _validate_sensitivity_rows(
    value: object,
    *,
    stake: int,
    requested_bank: int,
    effective_bank: int,
) -> None:
    if not isinstance(value, list):
        raise SchedulerPhaseError("EV sensitivity must be a list")
    for item in value:
        row = _exact_phase_mapping(
            item,
            {
                "prize_fund_factor",
                "possible_winnings",
                "decision",
                "selected_count",
                "cost",
                "unused_bank",
                "expected_payout",
                "modeled_roi",
            },
            "EV sensitivity row",
        )
        _finite_metric("sensitivity prize_fund_factor", row["prize_fund_factor"])
        _finite_metric("sensitivity possible_winnings", row["possible_winnings"])
        count = _strict_non_negative_int(
            "sensitivity selected_count", row["selected_count"]
        )
        cost = _strict_non_negative_int("sensitivity cost", row["cost"])
        unused = _strict_non_negative_int(
            "sensitivity unused_bank", row["unused_bank"]
        )
        _finite_metric("sensitivity expected_payout", row["expected_payout"])
        if row["modeled_roi"] is not None:
            _finite_metric("sensitivity modeled_roi", row["modeled_roi"])
        if row["decision"] not in ("PLAY", "NO BET", "RESEARCH ONLY"):
            raise SchedulerPhaseError("sensitivity decision is invalid")
        if (
            cost != count * stake
            or cost > effective_bank
            or cost + unused != requested_bank
        ):
            raise SchedulerPhaseError(
                "sensitivity bank, stake, count, and cost are inconsistent"
            )


def _render_package_csv(rows: Sequence[tuple[int, str, float, float]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(PACKAGE_CSV_HEADER)
    for rank, coupon, gross_ev, net_ev in rows:
        writer.writerow(
            (rank, coupon, format(gross_ev, ".17g"), format(net_ev, ".17g"))
        )
    return output.getvalue().encode("utf-8")


def _render_scheduler_wrapper(
    *,
    plan_path: Path,
    project_root: Path,
    python_executable: str,
    env_file: Path | None,
) -> str:
    executable_arg = shlex.quote(python_executable)
    plan_arg = shlex.quote(str(plan_path))
    return (
        "#!/bin/sh\nset -eu\numask 077\n"
        + (
            ""
            if env_file is None
            else _render_secure_env_prelude(
                env_file=env_file,
                python_executable=python_executable,
            )
        )
        + f"cd {shlex.quote(str(project_root))}\n"
        + f"exec {executable_arg} -m toto_ai.cli scheduler-execute "
        f"--plan {plan_arg} \"$@\"\n"
    )


def _render_launch_agent(
    plan: SchedulerPlan,
    *,
    wrapper_path: Path,
    logs_dir: Path,
) -> bytes:
    local_starts = (
        plan.preflight_at,
        plan.fallback_at,
        plan.final_at,
        plan.retry_at,
        plan.publish_deadline,
    )
    payload = {
        "Label": scheduler_launch_agent_label(plan),
        "ProgramArguments": [str(wrapper_path)],
        "WorkingDirectory": str(plan.project_root),
        "RunAtLoad": False,
        "StartCalendarInterval": [
            {
                "Year": local_start.astimezone(_MOSCOW).year,
                "Month": local_start.astimezone(_MOSCOW).month,
                "Day": local_start.astimezone(_MOSCOW).day,
                "Hour": local_start.astimezone(_MOSCOW).hour,
                "Minute": local_start.astimezone(_MOSCOW).minute,
            }
            for local_start in local_starts
        ],
        "StandardOutPath": str(logs_dir / "scheduler.stdout.log"),
        "StandardErrorPath": str(logs_dir / "scheduler.stderr.log"),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _reject_stale_t12_scheduler_artifact(plan_path: Path) -> None:
    """Reject a persisted schema-v4/T-12 plan before reuse or overwrite."""

    if not _path_exists(plan_path):
        return
    try:
        _require_regular_file(
            plan_path,
            name="scheduler plan",
            reject_symlink=True,
        )
        payload = _load_strict_json(plan_path, name="scheduler plan")
    except (OSError, SchedulerError, UnicodeDecodeError, ValueError):
        return
    if (
        isinstance(payload, Mapping)
        and payload.get("schema_version") == STALE_T12_SCHEDULER_SCHEMA_VERSION
    ):
        raise SchedulerIntegrityError(
            "stale scheduler schema v4 uses T-12 trigger semantics; "
            "regenerate schema v5",
            category="stale_scheduler_schema",
        )


def _render_morning_preanalysis_wrapper(
    *,
    retry_count: int,
    retry_delay_seconds: float,
    env_file: Path,
    project_root: Path,
    bank: int,
    stake: int,
    activate_evening: bool,
    reviewed_schedule_catalog: Path | None,
    python_executable: str,
) -> str:
    executable = shlex.quote(python_executable)
    command_values = [
        python_executable,
        "-m",
        "toto_ai.cli",
        "morning-dispatch",
        "--bank",
        str(bank),
        "--stake",
        str(stake),
        "--env-file",
        str(env_file),
        "--project-root",
        str(project_root),
        "--state-root",
        str(project_root / "data" / "scheduler" / "morning-dispatch"),
        "--scheduler-root",
        str(project_root / "reports" / "rehearsal"),
        "--db",
        str(project_root / "data" / "toto.db"),
        "--aliases",
        str(project_root / "data" / "external-odds" / "team-aliases.json"),
        "--raw-cache-dir",
        str(project_root / "data" / "raw"),
        "--totobrief-rate-state",
        str(
            project_root
            / "data"
            / "totobrief-cache"
            / "request-state.json"
        ),
        "--cache-root",
        str(project_root / "data" / "external-cache" / "api-sports"),
    ]
    if activate_evening:
        command_values.append("--activate")
    if reviewed_schedule_catalog is not None:
        _require_contained_path(
            project_root,
            reviewed_schedule_catalog,
            name="reviewed schedule catalog",
        )
        command_values.extend(
            (
                "--reviewed-schedule-catalog",
                str(reviewed_schedule_catalog),
            )
        )
    command = " ".join(
        shlex.quote(value)
        for value in command_values
    )
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        "umask 077\n"
        + _render_secure_env_prelude(
            env_file=env_file,
            python_executable=python_executable,
        )
        + f"cd {shlex.quote(str(project_root))}\n"
        + "attempt=0\n"
        + "while :; do\n"
        + f"  if {command}; then\n"
        + "    exit 0\n"
        + "  else\n"
        + "    status=$?\n"
        + "  fi\n"
        + f"  if [ \"$attempt\" -ge {retry_count} ]; then\n"
        + "    exit \"$status\"\n"
        + "  fi\n"
        + "  attempt=$((attempt + 1))\n"
        + f"  {executable} -c 'import time; time.sleep({retry_delay_seconds!r})'\n"
        + "done\n"
    )


def _render_morning_launch_agent(
    *,
    times: Sequence[tuple[int, int]],
    wrapper_path: Path,
    logs_dir: Path,
    project_root: Path,
) -> bytes:
    payload = {
        "Label": "com.totoai.morning-dispatcher.v1",
        "ProgramArguments": [str(wrapper_path)],
        "WorkingDirectory": str(project_root),
        "RunAtLoad": False,
        "StartCalendarInterval": [
            {"Hour": hour, "Minute": minute} for hour, minute in times
        ],
        "StandardOutPath": str(logs_dir / "morning.stdout.log"),
        "StandardErrorPath": str(logs_dir / "morning.stderr.log"),
    }
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)


def _render_secure_env_prelude(
    *,
    env_file: Path,
    python_executable: str,
) -> str:
    environment_arg = shlex.quote(str(env_file))
    executable_arg = shlex.quote(python_executable)
    return (
        f"ENV_FILE={environment_arg}\n"
        f"{executable_arg} - \"$ENV_FILE\" <<'PY'\n"
        "import os\n"
        "import stat\n"
        "import sys\n"
        "path = sys.argv[1]\n"
        "try:\n"
        "    metadata = os.lstat(path)\n"
        "except OSError:\n"
        "    raise SystemExit('scheduler env file is missing or inaccessible')\n"
        "if stat.S_ISLNK(metadata.st_mode):\n"
        "    raise SystemExit('scheduler env file must not be a symlink')\n"
        "if not stat.S_ISREG(metadata.st_mode):\n"
        "    raise SystemExit('scheduler env file must be a regular file')\n"
        "if metadata.st_uid != os.getuid():\n"
        "    raise SystemExit('scheduler env file must be owned by current user')\n"
        "if stat.S_IMODE(metadata.st_mode) & ~0o600:\n"
        "    raise SystemExit('scheduler env file mode must be no broader than 0600')\n"
        "PY\n"
        ". \"$ENV_FILE\"\n"
        "if [ -z \"${API_SPORTS_KEY:-}\" ]; then\n"
        "  echo 'API_SPORTS_KEY is required in scheduler env file' >&2\n"
        "  exit 78\n"
        "fi\n"
        "export API_SPORTS_KEY\n"
    )


def _validate_preflight_inputs(plan: SchedulerPlan) -> None:
    # Strict parsing is intentional, but this T-45 validation does not retain a
    # semantic hash. A valid operator edit before atomic-final capture is
    # therefore allowed.
    if plan.timing_overrides is not None:
        _require_regular_file(
            plan.timing_overrides,
            name="timing override catalog",
            reject_symlink=True,
        )
        load_timing_override_catalog(plan.timing_overrides)
    if plan.reviewed_schedule_catalog is not None:
        _require_regular_file(
            plan.reviewed_schedule_catalog,
            name="reviewed schedule catalog",
            reject_symlink=True,
        )
        load_reviewed_schedule_catalog(
            plan.reviewed_schedule_catalog,
            evaluated_at=datetime.now(timezone.utc),
            max_age=timedelta(hours=12),
        )


def _validate_live_scheduler_target(
    plan: SchedulerPlan, observed_at: datetime
) -> None:
    """Validate the exact open target during the production T-45 preflight."""

    client = TotoBriefClient()
    reference = resolve_open_drawing_from_api(client, now=observed_at)
    target = parse_target_drawing(
        client.drawing_info(reference.drawing_id),
        fetched_at=observed_at,
    )
    if (
        reference.number != plan.drawing
        or target.drawing_number != plan.drawing
        or target.deadline != plan.ended_at
        or (
            plan.drawing_id is not None
            and (
                reference.drawing_id != plan.drawing_id
                or target.drawing_id != plan.drawing_id
            )
        )
    ):
        raise SchedulerIntegrityError(
            "live open drawing does not match the scheduler target",
            category="target_identity",
        )


def _current_override_sha256(plan: SchedulerPlan) -> str | None:
    if plan.timing_overrides is None:
        return None
    _require_regular_file(
        plan.timing_overrides,
        name="timing override catalog",
        reject_symlink=True,
    )
    catalog = load_timing_override_catalog(plan.timing_overrides)
    return timing_override_catalog_sha256(catalog)


def _final_inputs_sha256(
    plan: SchedulerPlan,
    override_sha256: str | None,
    final_input: FinalInputSnapshot | None = None,
) -> str:
    payload = {
        "plan": plan.semantic_payload(),
        "plan_id": plan.plan_id,
        "target_deadline": _timestamp(plan.ended_at),
        "requested_bank": plan.requested_bank,
        "stake": plan.stake,
        "timing_override_sha256": override_sha256,
        "final_input": (
            None
            if final_input is None
            else {
                "attempt_id": final_input.attempt_id,
                "captured_at": _timestamp(final_input.captured_at),
                "snapshot_sha256": final_input.snapshot_sha256,
                "detail_payload_sha256": final_input.detail_payload_sha256,
                "probability_input_sha256": (
                    final_input.probability_input_sha256
                ),
            }
        ),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _initial_phase_state(plan: SchedulerPlan) -> dict[str, dict[str, Any]]:
    scheduled = {
        "preflight": plan.preflight_at,
        "fallback": plan.fallback_at,
        "final": plan.final_at,
        "freeze": plan.freeze_at,
    }
    return {
        phase: {
            "scheduled_at": _timestamp(scheduled[phase]),
            "started_at": None,
            "finished_at": None,
            "status": "pending",
            "reason": None,
        }
        for phase in _PHASES
    }


def _base_status(
    plan: SchedulerPlan,
    run_id: str,
    run_dir: Path,
    phase_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": "running",
        "outcome": None,
        "decision": None,
        "reason": "scheduler execution in progress",
        "package_path": None,
        "package_sha256": None,
        "requested_bank": plan.requested_bank,
        "effective_bank": None,
        "selected_count": None,
        "selected_cost": None,
        "selected_snapshot": None,
        "published_at": None,
        "completed_at": None,
        "final_inputs_sha256": None,
        "final_override_sha256": None,
        "deadlines": {
            key: _timestamp(value) for key, value in plan.deadlines.items()
        },
        "phase_timestamps": phase_state,
    }


def _phase_context(
    plan: SchedulerPlan,
    run_id: str,
    run_dir: Path,
    *,
    phase: Literal["preflight", "fallback", "final"],
    scheduled_at: datetime,
    started_at: datetime,
    override_sha256: str | None = None,
    final_inputs_sha256: str | None = None,
) -> SchedulerPhaseContext:
    work_dir = run_dir / "work" / phase
    _ensure_output_directory(plan.output_dir, work_dir)
    return SchedulerPhaseContext(
        phase=phase,
        plan=plan,
        run_id=run_id,
        run_dir=run_dir,
        work_dir=work_dir,
        scheduled_at=scheduled_at,
        started_at=started_at,
        override_sha256=override_sha256,
        final_inputs_sha256=final_inputs_sha256,
    )


def _call_phase_runner(
    phase_runner: SchedulerPhaseRunner, context: SchedulerPhaseContext
) -> SchedulerPhaseResult:
    result = phase_runner(context)
    if not isinstance(result, SchedulerPhaseResult):
        raise SchedulerIntegrityError(
            "phase runner must return SchedulerPhaseResult",
            category="phase_contract",
        )
    return result


def _phase_started(
    phase_state: dict[str, dict[str, Any]],
    phase: SchedulerPhase,
    *,
    scheduled_at: datetime,
    started_at: datetime,
) -> None:
    row = phase_state[phase]
    row.update(
        {
            "scheduled_at": _timestamp(scheduled_at),
            "started_at": _timestamp(started_at),
            "finished_at": None,
            "status": "running",
            "reason": None,
        }
    )


def _phase_finished(
    phase_state: dict[str, dict[str, Any]],
    phase: SchedulerPhase,
    *,
    finished_at: datetime,
    status: str,
    reason: str,
) -> None:
    row = phase_state[phase]
    if row["started_at"] is None:
        row["started_at"] = _timestamp(finished_at)
    row.update(
        {
            "finished_at": _timestamp(finished_at),
            "status": status,
            "reason": reason,
        }
    )


def _ensure_phase_failure(
    phase_state: dict[str, dict[str, Any]],
    phase: SchedulerPhase,
    *,
    scheduled_at: datetime,
    observed_at: datetime,
    reason: str,
) -> None:
    if phase_state[phase]["started_at"] is None:
        _phase_started(
            phase_state,
            phase,
            scheduled_at=scheduled_at,
            started_at=observed_at,
        )
    _phase_finished(
        phase_state,
        phase,
        finished_at=observed_at,
        status="failed",
        reason=reason,
    )


def _active_phase(
    phase_state: Mapping[str, Mapping[str, Any]],
) -> SchedulerPhase | None:
    for phase in _PHASES:
        if phase_state[phase]["status"] == "running":
            return phase
    return None


def _wait_until(
    target: datetime,
    *,
    now: Callable[[], datetime],
    sleep: Callable[[float], object],
) -> None:
    while True:
        current = _read_now(now)
        remaining = (target - current).total_seconds()
        if remaining <= 0:
            return
        sleep(remaining)
        advanced = _read_now(now)
        if advanced <= current:
            raise SchedulerError("scheduler sleeper did not advance the UTC clock")


def _write_status_atomic(
    output_root: Path,
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    target = _require_contained_path(output_root, path, name="status path")
    _ensure_output_directory(output_root, target.parent)
    _require_regular_file(target, name="status file", reject_symlink=True)
    temp_path = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = _open_exclusive_regular(temp_path, mode=0o644)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            output.write(_canonical_json_bytes(payload) + b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, target)
        _require_regular_file(target, name="status file", reject_symlink=True)
        _fsync_directory(target.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        _unlink_output_path(output_root, temp_path, missing_ok=True)


def _write_exclusive_atomic(
    output_root: Path,
    path: Path,
    content: bytes,
    mode: int = 0o644,
) -> None:
    if not isinstance(content, bytes):
        raise TypeError("artifact content must be bytes")
    target = _require_contained_path(output_root, path, name="artifact path")
    _ensure_output_directory(output_root, target.parent)
    if _path_exists(target):
        raise FileExistsError(f"refusing to overwrite existing artifact: {target}")
    temp_path = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = _open_exclusive_regular(temp_path, mode=mode)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = None
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temp_path, target, follow_symlinks=False)
        except FileExistsError as error:
            raise FileExistsError(
                f"refusing to overwrite existing artifact: {target}"
            ) from error
        _require_regular_file(target, name="published artifact", reject_symlink=True)
        _fsync_directory(target.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        _unlink_output_path(output_root, temp_path, missing_ok=True)


def _open_exclusive_regular(path: Path, *, mode: int) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise SchedulerError(f"artifact temporary path is not regular: {path}")
        os.fchmod(descriptor, mode)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _execution_result_from_status(
    status: Mapping[str, Any], run_dir: Path, status_path: Path
) -> SchedulerExecutionResult:
    outcome = status["outcome"]
    decision = status["decision"]
    if outcome not in ("bet-ready", "no-bet", "failed", "ignored"):
        raise ValueError("terminal scheduler status has invalid outcome")
    if decision not in ("PLAY", "NO BET", "FAILED", "IGNORED"):
        raise ValueError("terminal scheduler status has invalid decision")
    package_value = status.get("package_path")
    package_path = None if package_value is None else Path(str(package_value))
    marker_path = None if outcome == "ignored" else run_dir / f".{outcome}"
    return SchedulerExecutionResult(
        outcome=outcome,
        decision=decision,
        reason=str(status["reason"]),
        drawing=int(status["drawing"]),
        run_id=str(status["run_id"]),
        run_dir=run_dir,
        status_path=status_path,
        marker_path=marker_path,
        package_path=package_path,
        package_sha256=status.get("package_sha256"),
        requested_bank=int(status["requested_bank"]),
        effective_bank=status.get("effective_bank"),
    )


def _valid_package_hash(
    plan: SchedulerPlan,
    path: Path,
    expected_sha256: str,
    *,
    expected_count: int,
    expected_cost: int,
) -> bool:
    try:
        _require_sha256("package_sha256", expected_sha256)
        _require_contained_path(plan.output_dir, path, name="package path")
        content = _read_regular_file(
            path,
            name="package file",
            reject_symlink=True,
        )
        _validate_package_csv(
            content,
            stake=plan.stake,
            minimum_gross_ev=plan.minimum_gross_ev,
            expected_count=expected_count,
            expected_cost=expected_cost,
        )
        return _sha256_bytes(content) == expected_sha256
    except (OSError, SchedulerError, TypeError, ValueError):
        return False


def _validate_terminal_package(
    plan: SchedulerPlan,
    run_dir: Path,
    terminal: Mapping[str, Any],
) -> None:
    package_path = terminal.get("package_path")
    package_sha256 = terminal.get("package_sha256")
    effective_bank = terminal.get("effective_bank")
    selected_count = terminal.get("selected_count")
    selected_cost = terminal.get("selected_cost")
    if not isinstance(package_path, Path) or package_path != run_dir / "package.csv":
        raise SchedulerPhaseError("terminal package path is not run-scoped")
    _require_sha256("terminal package_sha256", package_sha256)
    _require_positive_int("terminal effective_bank", effective_bank)
    _require_positive_int("terminal selected_count", selected_count)
    _require_positive_int("terminal selected_cost", selected_cost)
    assert isinstance(effective_bank, int)
    assert isinstance(selected_count, int)
    assert isinstance(selected_cost, int)
    if (
        effective_bank > plan.requested_bank
        or selected_cost != selected_count * plan.stake
        or selected_cost > effective_bank
        or terminal.get("selected_snapshot") != "final"
    ):
        raise SchedulerPhaseError("terminal package metadata is inconsistent")
    if not _valid_package_hash(
        plan,
        package_path,
        package_sha256,
        expected_count=selected_count,
        expected_cost=selected_cost,
    ):
        raise SchedulerPhaseError("terminal package failed final validation")


def _validate_status_file(
    plan: SchedulerPlan,
    status_path: Path,
    status: Mapping[str, Any],
) -> None:
    _require_contained_path(plan.output_dir, status_path, name="status path")
    observed = _read_regular_file(
        status_path,
        name="status file",
        reject_symlink=True,
    )
    expected = _canonical_json_bytes(status) + b"\n"
    if observed != expected:
        raise SchedulerError("scheduler status changed during publication")


def _load_strict_json(path: Path, *, name: str) -> object:
    content = _read_regular_file(path, name=name, reject_symlink=True)
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise

    def reject_constant(value: str) -> object:
        raise ValueError(f"{name} contains non-finite JSON number {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{name} contains duplicate field {key!r}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} is not valid JSON: {error}") from error
    _require_finite_json_numbers(payload, name=name)
    return payload


def _read_regular_file(
    path: Path,
    *,
    name: str,
    reject_symlink: bool,
) -> bytes:
    normalized = _normalized_path(path)
    _require_regular_file(
        normalized,
        name=name,
        reject_symlink=reject_symlink,
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SchedulerError(f"{name} must be a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise SchedulerError(f"{name} changed while it was read")
    finally:
        os.close(descriptor)
    current = os.lstat(normalized)
    if (
        not stat.S_ISREG(current.st_mode)
        or current.st_dev != after.st_dev
        or current.st_ino != after.st_ino
    ):
        raise SchedulerError(f"{name} changed while it was read")
    return b"".join(chunks)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _new_run_id(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(4)


def _require_run_id(value: object) -> None:
    if not isinstance(value, str) or _RUN_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("run_id must be a safe 1-128 character identifier")


def _read_now(now: Callable[[], datetime]) -> datetime:
    return _require_utc_datetime("scheduler clock", now())


def _parse_utc_datetime(name: str, value: object) -> datetime:
    if isinstance(value, datetime):
        return _require_utc_datetime(name, value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO timezone-aware UTC datetime")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"{name} must be an ISO timezone-aware UTC datetime"
        ) from error
    return _require_utc_datetime(name, parsed)


def _require_utc_datetime(name: str, value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _require_utc_datetime("timestamp", value).isoformat().replace(
        "+00:00", "Z"
    )


def _normalized_path(value: object) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("scheduler paths must be strings or path-like values")
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValueError("scheduler paths must be non-empty")
    return Path(os.path.abspath(os.path.expanduser(raw)))


def _validated_project_root(value: object) -> Path:
    root = _normalized_path(value)
    if root == Path(root.anchor):
        raise ValueError("scheduler project_root must not be filesystem root")
    try:
        resolved = root.resolve(strict=True)
    except OSError as error:
        raise ValueError(
            "scheduler project_root must be an existing directory"
        ) from error
    if root != resolved:
        raise ValueError("scheduler project_root must not contain symlinks")
    if not resolved.is_dir():
        raise ValueError("scheduler project_root must be an existing directory")
    return resolved


def _validated_project_path(
    project_root: Path,
    value: object,
    *,
    name: str,
) -> Path:
    path = _normalized_path(value)
    try:
        resolved = path.resolve(strict=False)
    except OSError as error:
        raise ValueError(f"{name} could not be resolved safely") from error
    if path != resolved:
        raise ValueError(f"{name} must not contain symlinks")
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"{name} must be contained within project_root") from error
    return resolved


def _require_contained_path(
    root: Path,
    path: Path,
    *,
    name: str,
) -> Path:
    normalized_root = _normalized_path(root)
    normalized_path = _normalized_path(path)
    try:
        relative = normalized_path.relative_to(normalized_root)
    except ValueError as error:
        raise SchedulerError(
            f"{name} must remain inside output root {normalized_root}"
        ) from error
    if ".." in relative.parts:
        raise SchedulerError(f"{name} contains an unsafe parent traversal")
    _reject_existing_symlink_components(normalized_root, normalized_path, name=name)
    if _path_exists(normalized_root):
        resolved_root = normalized_root.resolve(strict=True)
        resolved_path = normalized_path.resolve(strict=False)
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError as error:
            raise SchedulerError(
                f"resolved {name} escapes output root {normalized_root}"
            ) from error
    return normalized_path


def _reject_existing_symlink_components(
    root: Path,
    path: Path,
    *,
    name: str,
) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise SchedulerError(f"{name} is outside its declared root") from error
    candidates = [root]
    for index in range(1, len(relative.parts) + 1):
        candidates.append(root / Path(*relative.parts[:index]))
    for current in candidates:
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise SchedulerError(f"{name} contains symlink component: {current}")


def _path_exists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _is_regular_file(path: Path, *, reject_symlink: bool) -> bool:
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if reject_symlink and stat.S_ISLNK(metadata.st_mode):
        return False
    return stat.S_ISREG(metadata.st_mode)


def _require_regular_file(
    path: Path,
    *,
    name: str,
    reject_symlink: bool,
) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise SchedulerError(f"{name} must be an existing regular file") from error
    if reject_symlink and stat.S_ISLNK(metadata.st_mode):
        raise SchedulerError(f"{name} must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise SchedulerError(f"{name} must be a regular file")


def _require_secure_env_file(path: Path) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise SchedulerError(
            "scheduler env file must be an existing regular file"
        ) from error
    if stat.S_ISLNK(metadata.st_mode):
        raise SchedulerError("scheduler env file must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise SchedulerError("scheduler env file must be a regular file")
    if metadata.st_uid != os.getuid():
        raise SchedulerError("scheduler env file must be owned by current user")
    if stat.S_IMODE(metadata.st_mode) & ~0o600:
        raise SchedulerError(
            "scheduler env file mode must be no broader than 0600"
        )


def _parse_morning_time(value: object) -> tuple[int, int]:
    if not isinstance(value, str) or re.fullmatch(r"\d{2}:\d{2}", value) is None:
        raise ValueError("morning time must use HH:MM")
    hour, minute = (int(part) for part in value.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("morning time must use a valid 24-hour HH:MM value")
    return hour, minute


def _ensure_output_directory(output_root: Path, directory: Path) -> None:
    root = _normalized_path(output_root)
    target = _normalized_path(directory)
    if target != root:
        _require_contained_path(root, target, name="output directory")
    if not _path_exists(root):
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            pass
    _require_directory_no_symlink(root, name="output root")
    if target == root:
        return
    relative = target.relative_to(root)
    current = root
    for part in relative.parts:
        current /= part
        if _path_exists(current):
            _require_directory_no_symlink(current, name="output descendant")
            continue
        try:
            current.mkdir()
        except FileExistsError:
            pass
        _require_directory_no_symlink(current, name="output descendant")
    _require_contained_path(root, target, name="output directory")


def _create_output_directory_exclusive(
    output_root: Path,
    directory: Path,
) -> None:
    target = _require_contained_path(
        output_root,
        directory,
        name="exclusive output directory",
    )
    _ensure_output_directory(output_root, target.parent)
    try:
        target.mkdir()
    except FileExistsError:
        raise
    _require_directory_no_symlink(target, name="exclusive output directory")


def _require_output_directory(output_root: Path, directory: Path) -> None:
    target = _require_contained_path(
        output_root,
        directory,
        name="output directory",
    )
    _require_directory_no_symlink(target, name="output directory")


def _require_directory_no_symlink(path: Path, *, name: str) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise SchedulerError(f"{name} must be an existing directory") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise SchedulerError(f"{name} must not be a symlink: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise SchedulerError(f"{name} must be a directory: {path}")


def _reject_unsafe_output_descendants(output_root: Path) -> None:
    root = _normalized_path(output_root)
    _require_directory_no_symlink(root, name="output root")
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            entries = tuple(os.scandir(current))
        except OSError as error:
            raise SchedulerError(
                f"output directory could not be inspected: {current}"
            ) from error
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            entry_path = Path(entry.path)
            if stat.S_ISLNK(metadata.st_mode):
                raise SchedulerError(
                    f"output root contains symlink descendant: {entry_path}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(entry_path)
            elif not stat.S_ISREG(metadata.st_mode):
                raise SchedulerError(
                    f"output root contains non-regular descendant: {entry_path}"
                )


def _unlink_output_path(
    output_root: Path,
    path: Path,
    *,
    missing_ok: bool = False,
) -> None:
    target = _require_contained_path(output_root, path, name="cleanup path")
    try:
        metadata = os.lstat(target)
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        raise SchedulerError(f"refusing to unlink output directory: {target}")
    target.unlink()


def _validated_python_executable(value: str | Path) -> str:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("python executable must be one absolute path")
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValueError("python executable must be one absolute path")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise ValueError("python executable path contains control characters")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("python executable must be an absolute path")
    absolute = Path(os.path.abspath(path))
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as error:
        raise ValueError("python executable does not exist") from error
    if not _is_regular_file(resolved, reject_symlink=True):
        raise ValueError("python executable must resolve to a regular file")
    if not os.access(absolute, os.X_OK):
        raise ValueError("python executable must be executable")

    current = Path(os.path.abspath(sys.executable))
    try:
        current_resolved = current.resolve(strict=True)
    except OSError as error:  # pragma: no cover - a broken running interpreter
        raise ValueError("current Python executable could not be validated") from error
    if not _is_regular_file(current_resolved, reject_symlink=True) or not os.access(
        current,
        os.X_OK,
    ):
        raise ValueError("current Python executable could not be validated")
    if absolute == current and resolved == current_resolved:
        return str(current)

    project_interpreter = (
        Path(__file__).resolve().parents[3] / ".venv" / "bin" / "python"
    )
    try:
        project_resolved = project_interpreter.resolve(strict=True)
    except OSError:
        project_resolved = None
    if (
        project_resolved is not None
        and project_resolved == current_resolved
        and absolute in {project_interpreter, project_resolved}
        and resolved == project_resolved
        and os.access(project_interpreter, os.X_OK)
    ):
        return str(project_resolved)

    raise ValueError(
        "python executable must be the current interpreter or the exact "
        "project .venv interpreter"
    )


def _find_existing_bet_ready_marker(plan: SchedulerPlan) -> Path | None:
    drawing_root = plan.output_dir / "runs" / str(plan.drawing)
    if not _path_exists(drawing_root):
        return None
    _require_output_directory(plan.output_dir, drawing_root)
    for entry in sorted(drawing_root.iterdir(), reverse=True):
        _require_contained_path(plan.output_dir, entry, name="prior run path")
        if not entry.is_dir():
            continue
        marker = entry / ".bet-ready"
        if not _path_exists(marker):
            continue
        _require_regular_file(
            marker,
            name="prior BET READY marker",
            reject_symlink=True,
        )
        return marker
    return None


def _require_exact_phase_fields(
    value: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    observed = set(value)
    missing = sorted(expected - observed)
    unknown = sorted(observed - expected)
    if missing or unknown:
        details = []
        if missing:
            details.append(f"missing fields {missing}")
        if unknown:
            details.append(f"unknown fields {unknown}")
        raise SchedulerPhaseError(f"{name} has {' and '.join(details)}")


def _exact_phase_mapping(
    value: object,
    expected: set[str],
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchedulerPhaseError(f"{name} must be an object")
    _require_exact_phase_fields(value, expected, name)
    return value


def _strict_int(name: str, value: object) -> int:
    if type(value) is not int:
        raise SchedulerPhaseError(f"{name} must be an integer")
    return value


def _strict_non_negative_int(name: str, value: object) -> int:
    result = _strict_int(name, value)
    if result < 0:
        raise SchedulerPhaseError(f"{name} must be non-negative")
    return result


def _strict_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SchedulerPhaseError(f"{name} must be non-empty canonical text")
    return value


def _strict_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise SchedulerPhaseError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _finite_metric(name: str, value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchedulerPhaseError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise SchedulerPhaseError(f"{name} must be a finite number")
    return result


def _require_finite_json_numbers(value: object, *, name: str) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, Mapping):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError(f"{name} contains a non-finite numeric value")


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _require_plan(plan: object) -> None:
    if not isinstance(plan, SchedulerPlan):
        raise ValueError("plan must be a SchedulerPlan")


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_non_negative_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], name: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} fields must be exactly {sorted(expected)}")


def _exact_mapping(
    value: object, expected: set[str], name: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    _require_exact_keys(value, expected, name)
    return value


def _safe_error(error: BaseException) -> str:
    message = str(error).strip()
    return message or type(error).__name__
