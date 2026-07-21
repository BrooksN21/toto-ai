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
from toto_ai.external_odds.timing_overrides import (
    TimingOverrideCatalog,
    TimingOverrideRecord,
    TimingSnapshotSummary,
    classify_timing_snapshot,
    drawing_timing_snapshot_from_collection,
    overlay_timing_override,
)

_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
RunnerDecision = Literal["PLAY", "NO BET", "RESEARCH ONLY"]
TimingOverrideStatus = Literal[
    "applied",
    "not_applied",
    "invalid_catalog",
    "catalog_changed",
    "hash_unverified",
]


@dataclass(frozen=True)
class AppliedTimingOverrideEvent:
    event_order: int
    event_id: int
    starts_at: datetime
    source_ref: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_order, int)
            or isinstance(self.event_order, bool)
            or self.event_order not in range(15)
        ):
            raise ValueError("event_order must be in range 0 through 14")
        _require_positive_int("event_id", self.event_id)
        _require_utc_datetime("starts_at", self.starts_at)
        _require_text("source_ref", self.source_ref)


@dataclass(frozen=True)
class TimingOverrideAudit:
    status: TimingOverrideStatus
    preflight_catalog_sha256: str | None
    timing_catalog_sha256: str | None
    package_catalog_sha256: str | None
    override_id: str | None
    reviewer: str | None
    reviewed_at: datetime | None
    source_ref: str | None
    overlay_complete: bool
    applied_events: tuple[AppliedTimingOverrideEvent, ...]
    preserved_event_orders: tuple[int, ...]
    diagnostics: tuple[str, ...]
    overlay_summary: TimingSnapshotSummary | None

    def __post_init__(self) -> None:
        if self.status not in (
            "applied",
            "not_applied",
            "invalid_catalog",
            "catalog_changed",
            "hash_unverified",
        ):
            raise ValueError("invalid timing override audit status")
        for name, value in (
            ("preflight_catalog_sha256", self.preflight_catalog_sha256),
            ("timing_catalog_sha256", self.timing_catalog_sha256),
            ("package_catalog_sha256", self.package_catalog_sha256),
        ):
            if value is not None and (
                not isinstance(value, str)
                or _FINGERPRINT_PATTERN.fullmatch(value) is None
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        provenance = (
            self.override_id,
            self.reviewer,
            self.reviewed_at,
            self.source_ref,
        )
        if any(value is not None for value in provenance) and not all(
            value is not None for value in provenance
        ):
            raise ValueError("override provenance must be complete when present")
        if self.override_id is not None:
            _require_text("override_id", self.override_id)
            _require_text("reviewer", self.reviewer)
            _require_utc_datetime("reviewed_at", self.reviewed_at)
            _require_text("source_ref", self.source_ref)
        if not isinstance(self.overlay_complete, bool):
            raise ValueError("overlay_complete must be a boolean")
        if not isinstance(self.applied_events, tuple) or any(
            not isinstance(event, AppliedTimingOverrideEvent)
            for event in self.applied_events
        ):
            raise ValueError(
                "applied_events must contain AppliedTimingOverrideEvent records"
            )
        applied_orders = tuple(event.event_order for event in self.applied_events)
        if applied_orders != tuple(sorted(set(applied_orders))):
            raise ValueError("applied override event orders must be ordered and unique")
        _require_event_orders("preserved_event_orders", self.preserved_event_orders)
        if set(applied_orders) & set(self.preserved_event_orders):
            raise ValueError("applied and preserved event orders must be disjoint")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.diagnostics
        ):
            raise ValueError("diagnostics must contain non-empty strings")
        if self.overlay_summary is not None and not isinstance(
            self.overlay_summary,
            TimingSnapshotSummary,
        ):
            raise ValueError("overlay_summary must be a TimingSnapshotSummary")
        validated_record = (
            None
            if self.overlay_summary is None
            else self.overlay_summary.validated_override_record
        )
        if validated_record is not None:
            if not isinstance(validated_record, TimingOverrideRecord):
                raise ValueError("overlay summary validated record is invalid")
            if (
                self.override_id != validated_record.override_id
                or self.reviewer != validated_record.reviewer
                or self.reviewed_at != validated_record.reviewed_at
                or self.source_ref != validated_record.source_ref
            ):
                raise ValueError(
                    "override audit provenance must match the validated record"
                )
            record_events = {
                event.event_order: event for event in validated_record.events
            }
            for event in self.applied_events:
                record_event = record_events[event.event_order]
                expected_source = record_event.source_ref or validated_record.source_ref
                if (
                    event.event_id != record_event.event_id
                    or event.starts_at != record_event.starts_at
                    or event.source_ref != expected_source
                ):
                    raise ValueError(
                        "applied override event must match the validated record"
                    )
        if self.status == "applied":
            if (
                self.preflight_catalog_sha256 is None
                or self.timing_catalog_sha256 != self.preflight_catalog_sha256
                or not self.overlay_complete
                or self.override_id is None
                or self.overlay_summary is None
                or validated_record is None
            ):
                raise ValueError("applied timing override audit is incomplete")
            if self.overlay_summary.status == "unknown":
                raise ValueError("applied override cannot retain unknown timing")
            if set(applied_orders) | set(self.preserved_event_orders) != set(
                range(15)
            ):
                raise ValueError(
                    "applied override must account for all event orders"
                )
        if self.package_catalog_sha256 is not None and (
            self.package_catalog_sha256 != self.preflight_catalog_sha256
            or self.status != "applied"
        ):
            raise ValueError("package catalog hash requires an applied exact catalog")
        if self.status == "invalid_catalog" and (
            self.preflight_catalog_sha256 is not None
            or self.timing_catalog_sha256 is not None
        ):
            raise ValueError("invalid catalog cannot have validated catalog hashes")


@dataclass(frozen=True)
class RunnerTimingResolution:
    raw: PlayTimingEligibility
    effective: PlayTimingEligibility
    override: TimingOverrideAudit | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.raw, PlayTimingEligibility):
            raise ValueError("raw must be a PlayTimingEligibility")
        if not isinstance(self.effective, PlayTimingEligibility):
            raise ValueError("effective must be a PlayTimingEligibility")
        if self.override is None:
            if self.raw != self.effective:
                raise ValueError("timing cannot change without override audit")
            return
        if not isinstance(self.override, TimingOverrideAudit):
            raise ValueError("override must be a TimingOverrideAudit")
        if self.override.status != "applied" and self.effective.status != "unknown":
            raise ValueError("an unusable override must leave effective timing unknown")
        if self.override.status == "applied":
            summary = self.override.overlay_summary
            if summary is None or self.effective.status != summary.status:
                raise ValueError(
                    "effective timing must match the validated overlay summary"
                )

    @classmethod
    def without_override(
        cls,
        eligibility: PlayTimingEligibility,
    ) -> "RunnerTimingResolution":
        return cls(raw=eligibility, effective=eligibility)


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
    final_fingerprint: str | None
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
    raw_timing_eligibility: PlayTimingEligibility | None = None
    timing_override: TimingOverrideAudit | None = None

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
        if self.raw_timing_eligibility is None:
            object.__setattr__(
                self,
                "raw_timing_eligibility",
                self.timing_eligibility,
            )
        if not isinstance(self.raw_timing_eligibility, PlayTimingEligibility):
            raise ValueError(
                "raw_timing_eligibility must be a PlayTimingEligibility"
            )
        if self.timing_override is not None and not isinstance(
            self.timing_override,
            TimingOverrideAudit,
        ):
            raise ValueError("timing_override must be a TimingOverrideAudit")
        if self.timing_override is None and (
            self.raw_timing_eligibility != self.timing_eligibility
        ):
            raise ValueError("raw and effective timing require override audit")
        if (
            self.timing_override is not None
            and self.timing_override.status != "applied"
            and self.timing_eligibility.status != "unknown"
        ):
            raise ValueError("unusable override must leave effective timing unknown")
        if self.timing_override is not None:
            validate_timing_resolution_for_runner(
                RunnerTimingResolution(
                    raw=self.raw_timing_eligibility,
                    effective=self.timing_eligibility,
                    override=self.timing_override,
                ),
                target=self.target,
                collection=self.collection,
                preflight_at=self.preflight_at,
                require_override=True,
            )
        if self.audit is not None and not isinstance(self.audit, CoverageAudit):
            raise ValueError("audit must be a CoverageAudit")
        if self.ev_run is not None and not isinstance(self.ev_run, EVPackageRun):
            raise ValueError("ev_run must be an EVPackageRun")
        if self.final_fingerprint is not None and (
            not isinstance(self.final_fingerprint, str)
            or not _FINGERPRINT_PATTERN.fullmatch(self.final_fingerprint)
        ):
            raise ValueError(
                "final_fingerprint must be a lowercase SHA-256 hex digest"
            )
        if self.final_fingerprint is not None and self.final_started_at is None:
            raise ValueError("final fingerprint requires final_started_at")
        if self.final_started_at is not None and self.final_fingerprint is None:
            raise ValueError("final resolve requires a fingerprint")

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

        subsequent_phase_exists = (
            self.timing_eligibility.status != "not_checked"
            or any(
                value is not None
                for value in (
                    self.collection_finished_at,
                    self.timing_finished_at,
                    self.audit_finished_at,
                    self.ev_finished_at,
                )
            )
        )
        publishable_ev_exists = (
            self.ev_run is not None
            or self.decision in ("PLAY", "RESEARCH ONLY")
        )
        if (
            subsequent_phase_exists or publishable_ev_exists
        ) and self.final_fingerprint != self.target.fingerprint:
            raise ValueError(
                "final fingerprint must match the pinned preflight fingerprint"
            )

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
        raw_timing_fingerprint = self.raw_timing_eligibility.target_fingerprint
        if (
            raw_timing_fingerprint is not None
            and raw_timing_fingerprint != self.target.fingerprint
        ):
            raise ValueError("raw timing target does not match runner target")

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
            if (
                self.timing_override is not None
                and self.ev_run.timing_eligibility != self.timing_eligibility
            ):
                raise ValueError("EV timing does not match runner effective timing")
            if self.timing_override is not None and (
                self.timing_override.status != "applied"
                or self.timing_override.package_catalog_sha256
                != self.timing_override.preflight_catalog_sha256
            ):
                raise ValueError(
                    "EV with timing override requires the preflight catalog hash"
                )

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
            if self.ev_run.timing_eligibility.status != "playable":
                raise ValueError("PLAY requires EV playable timing")
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


def validate_timing_resolution_for_runner(
    resolution: RunnerTimingResolution,
    *,
    target: PinnedDrawing,
    collection: ProspectiveCollectionResult | None,
    preflight_at: datetime,
    require_override: bool,
) -> None:
    """Validate exact override evidence before it can influence runner timing."""

    if not isinstance(resolution, RunnerTimingResolution):
        raise ValueError("resolution must be a RunnerTimingResolution")
    if not isinstance(target, PinnedDrawing):
        raise ValueError("target must be a PinnedDrawing")
    _require_utc_datetime("preflight_at", preflight_at)
    if not isinstance(require_override, bool):
        raise ValueError("require_override must be a boolean")

    audit = resolution.override
    if audit is None:
        if require_override:
            raise ValueError(
                "an explicitly supplied timing catalog requires override audit"
            )
        return
    if audit.status != "applied":
        return
    if collection is None:
        raise ValueError("applied timing override requires a collection snapshot")
    if not isinstance(collection, ProspectiveCollectionResult):
        raise ValueError("collection must be a ProspectiveCollectionResult")

    raw_snapshot = drawing_timing_snapshot_from_collection(collection.snapshot)
    pinned_target = target.target
    if (
        raw_snapshot.drawing_id != pinned_target.drawing_id
        or raw_snapshot.drawing_number != pinned_target.drawing_number
        or raw_snapshot.target_fingerprint != target.fingerprint
        or raw_snapshot.ended_at != pinned_target.deadline
        or raw_snapshot.pinned_at != pinned_target.fetched_at
    ):
        raise ValueError(
            "timing override collection does not match the pinned drawing"
        )

    raw_summary = classify_timing_snapshot(raw_snapshot)
    if (
        resolution.raw.status != raw_summary.status
        or resolution.raw.target_fingerprint != target.fingerprint
        or not resolution.raw.fingerprint_match
    ):
        raise ValueError(
            "timing override raw eligibility does not match immutable collection"
        )

    overlay_summary = audit.overlay_summary
    if overlay_summary is None:
        raise ValueError("applied timing override requires an overlay summary")
    record = overlay_summary.validated_override_record
    if record is None:
        raise ValueError("applied timing override requires an exact validated record")
    if record.reviewed_at > preflight_at:
        raise ValueError("timing override was reviewed after runner preflight")
    if record.target_fingerprint != target.fingerprint:
        raise ValueError("timing override fingerprint does not match pinned drawing")
    if record.drawing_id is not None:
        identity_matches = record.drawing_id == pinned_target.drawing_id
    else:
        identity_matches = record.drawing_number == pinned_target.drawing_number
    if not identity_matches:
        raise ValueError("timing override identity does not match pinned drawing")

    target_event_ids = tuple(event.event_id for event in pinned_target.events)
    record_event_ids = tuple(event.event_id for event in record.events)
    if record_event_ids != target_event_ids:
        raise ValueError("timing override events do not match pinned drawing events")

    expected_overlay = overlay_timing_override(
        raw_snapshot,
        TimingOverrideCatalog(records=(record,)),
    )
    if not expected_overlay.complete_overlay:
        raise ValueError("timing override record cannot produce a complete overlay")
    expected_summary = classify_timing_snapshot(expected_overlay.snapshot)
    if overlay_summary != expected_summary:
        raise ValueError("timing override summary does not match exact overlay")
    if audit.preserved_event_orders != expected_overlay.preserved_event_orders:
        raise ValueError("timing override did not preserve the exact known starts")
    expected_record_events = {
        event.event_order: event for event in record.events
    }
    expected_applied_events = tuple(
        (
            order,
            expected_record_events[order].event_id,
            expected_record_events[order].starts_at,
            expected_record_events[order].source_ref or record.source_ref,
        )
        for order in expected_overlay.applied_event_orders
    )
    observed_applied_events = tuple(
        (event.event_order, event.event_id, event.starts_at, event.source_ref)
        for event in audit.applied_events
    )
    if observed_applied_events != expected_applied_events:
        raise ValueError("timing override applied events do not match exact overlay")
    if (
        resolution.effective.status != expected_summary.status
        or resolution.effective.target_fingerprint != target.fingerprint
        or not resolution.effective.fingerprint_match
    ):
        raise ValueError("effective timing does not match exact validated overlay")


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty canonical text")


def _require_event_orders(name: str, value: object) -> None:
    if (
        not isinstance(value, tuple)
        or any(
            not isinstance(order, int)
            or isinstance(order, bool)
            or order not in range(15)
            for order in value
        )
        or value != tuple(sorted(set(value)))
    ):
        raise ValueError(f"{name} must be an ordered tuple of unique event orders")


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
