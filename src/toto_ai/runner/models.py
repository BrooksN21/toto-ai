"""Immutable runner configuration, target, and terminal result records."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Literal

from toto_ai.ev.drawing import EVPackageRun
from toto_ai.ev.models import (
    EVConfig,
    EVMode,
    PlayTimingEligibility,
    validate_config_bank,
)
from toto_ai.external_odds.audit import CoverageAudit
from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.prospective import ProspectiveCollectionResult

_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")
RunnerDecision = Literal["PLAY", "NO BET", "RESEARCH ONLY"]


@dataclass(frozen=True)
class DrawingRunnerConfig:
    bank: int
    stake: int = 30
    mode: EVMode = "playable"
    final_lead_minutes: int = 20
    safety_stop_minutes: int = 5

    def __post_init__(self) -> None:
        validate_config_bank(self.bank, self.stake)
        if self.mode not in ("research", "playable"):
            raise ValueError("mode must be research or playable")
        _require_positive_int("final_lead_minutes", self.final_lead_minutes)
        _require_positive_int("safety_stop_minutes", self.safety_stop_minutes)
        if self.final_lead_minutes <= self.safety_stop_minutes:
            raise ValueError("final lead must be greater than safety stop")

    @property
    def ev_config(self) -> EVConfig:
        return EVConfig(bank=self.bank, stake=self.stake, mode=self.mode)


@dataclass(frozen=True)
class PinnedDrawing:
    target: TargetDrawing
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, TargetDrawing):
            raise ValueError("target must be a TargetDrawing")
        if not isinstance(self.fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(
            self.fingerprint
        ):
            raise ValueError("fingerprint must be a lowercase SHA-256 hex digest")
        expected_fingerprint = target_fingerprint(
            self.target.drawing_id,
            self.target.drawing_number,
            self.target.deadline,
            self.target.events,
        )
        if self.fingerprint != expected_fingerprint:
            raise ValueError("fingerprint does not match target")


@dataclass(frozen=True)
class DrawingRunnerResult:
    config: DrawingRunnerConfig
    target: PinnedDrawing
    preflight_at: datetime
    final_started_at: datetime | None
    collection_finished_at: datetime | None
    timing_finished_at: datetime | None
    audit_finished_at: datetime | None
    ev_finished_at: datetime | None
    finished_at: datetime
    elapsed_seconds: float
    decision: RunnerDecision
    terminal_reason: str
    collection: ProspectiveCollectionResult | None
    timing_eligibility: PlayTimingEligibility
    audit: CoverageAudit | None
    ev_run: EVPackageRun | None

    def __post_init__(self) -> None:
        if not isinstance(self.config, DrawingRunnerConfig):
            raise ValueError("config must be a DrawingRunnerConfig")
        if not isinstance(self.target, PinnedDrawing):
            raise ValueError("target must be a PinnedDrawing")
        if self.decision not in ("PLAY", "NO BET", "RESEARCH ONLY"):
            raise ValueError("invalid runner decision")
        if (
            not isinstance(self.terminal_reason, str)
            or not self.terminal_reason.strip()
        ):
            raise ValueError("terminal_reason must be non-empty")
        if (
            not isinstance(self.elapsed_seconds, (int, float))
            or isinstance(self.elapsed_seconds, bool)
            or not isfinite(float(self.elapsed_seconds))
            or self.elapsed_seconds < 0
        ):
            raise ValueError("elapsed_seconds must be finite and non-negative")
        if self.collection is not None and not isinstance(
            self.collection, ProspectiveCollectionResult
        ):
            raise ValueError("collection must be a ProspectiveCollectionResult")
        if not isinstance(self.timing_eligibility, PlayTimingEligibility):
            raise ValueError("timing_eligibility must be a PlayTimingEligibility")
        if self.audit is not None and not isinstance(self.audit, CoverageAudit):
            raise ValueError("audit must be a CoverageAudit")
        if self.ev_run is not None and not isinstance(self.ev_run, EVPackageRun):
            raise ValueError("ev_run must be an EVPackageRun")

        timestamps = (
            ("preflight_at", self.preflight_at),
            ("final_started_at", self.final_started_at),
            ("collection_finished_at", self.collection_finished_at),
            ("timing_finished_at", self.timing_finished_at),
            ("audit_finished_at", self.audit_finished_at),
            ("ev_finished_at", self.ev_finished_at),
            ("finished_at", self.finished_at),
        )
        present_timestamps = []
        for name, value in timestamps:
            if value is not None:
                _require_utc_datetime(name, value)
                present_timestamps.append(value)
        if any(
            later < earlier
            for earlier, later in zip(
                present_timestamps,
                present_timestamps[1:],
                strict=False,
            )
        ):
            raise ValueError("runner phase timestamps must be chronological")
        phase_timestamps = tuple(value for _, value in timestamps[1:-1])
        missing_phase_seen = False
        for value in phase_timestamps:
            if value is None:
                missing_phase_seen = True
            elif missing_phase_seen:
                raise ValueError("runner phase timestamps must be contiguous")

        if (self.collection is None) != (self.collection_finished_at is None):
            raise ValueError("collection and collection_finished_at must agree")
        if self.audit is None and self.audit_finished_at is not None:
            raise ValueError("audit_finished_at requires an audit")
        if self.audit is not None and self.audit_finished_at is None:
            raise ValueError("audit requires audit_finished_at")
        if self.ev_run is not None and self.ev_finished_at is None:
            raise ValueError("ev_run requires ev_finished_at")

        self._validate_target_identities()
        self._validate_terminal_decision()

    def _validate_target_identities(self) -> None:
        target = self.target.target
        if self.collection is not None:
            snapshot = self.collection.snapshot
            try:
                collection_deadline = _parse_utc_datetime(snapshot.deadline)
            except (TypeError, ValueError) as error:
                raise ValueError("collection target deadline is invalid") from error
            if (
                snapshot.drawing_id != target.drawing_id
                or snapshot.drawing_number != target.drawing_number
                or collection_deadline != target.deadline
                or snapshot.target_fingerprint != self.target.fingerprint
            ):
                raise ValueError("collection target does not match runner target")

        timing_fingerprint = self.timing_eligibility.target_fingerprint
        if (
            timing_fingerprint is not None
            and timing_fingerprint != self.target.fingerprint
        ):
            raise ValueError("timing target does not match runner target")

        if self.ev_run is not None:
            ev_input = self.ev_run.ev_input
            ev_timing_fingerprint = (
                self.ev_run.timing_eligibility.target_fingerprint
            )
            if (
                ev_input.drawing_id != target.drawing_id
                or ev_input.drawing_number != target.drawing_number
                or ev_timing_fingerprint != self.target.fingerprint
            ):
                raise ValueError("EV target does not match runner target")
            if (
                self.ev_run.config.bank != self.config.bank
                or self.ev_run.config.stake != self.config.stake
                or self.ev_run.config.mode != self.config.mode
            ):
                raise ValueError("EV config does not match runner config")

    def _validate_terminal_decision(self) -> None:
        package = None if self.ev_run is None else self.ev_run.package
        if self.decision == "PLAY":
            if self.timing_eligibility.status != "playable":
                raise ValueError("PLAY requires playable timing")
            if (
                self.config.mode != "playable"
                or package is None
                or package.decision != "PLAY"
            ):
                raise ValueError("PLAY requires an EV PLAY package")
            return
        if self.decision == "RESEARCH ONLY":
            if (
                self.config.mode != "research"
                or package is None
                or package.decision != "RESEARCH ONLY"
            ):
                raise ValueError(
                    "RESEARCH ONLY requires an EV research package"
                )
            return
        if package is not None and (
            package.decision != "NO BET"
            or package.cost != 0
            or bool(package.coupons)
        ):
            raise ValueError("NO BET cannot retain an actionable EV package")


def pin_drawing(target: TargetDrawing) -> PinnedDrawing:
    if not isinstance(target, TargetDrawing):
        raise ValueError("target must be a TargetDrawing")
    return PinnedDrawing(
        target=target,
        fingerprint=target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
    )


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_utc_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _parse_utc_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    _require_utc_datetime("timestamp", parsed)
    return parsed
