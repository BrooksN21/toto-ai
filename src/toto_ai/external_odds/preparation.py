from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from math import isclose, isfinite
from pathlib import Path
from typing import Any

from toto_ai.db.models import Drawing
from toto_ai.external_odds.api_sports import _parse_schedule_payload
from toto_ai.external_odds.domain import (
    TOTO_BRIEF_OUTCOME_ORDER,
    ProviderEvent,
    TargetDrawing,
)
from toto_ai.external_odds.eligibility import (
    DrawingEligibility,
    EffectiveEventStart,
    classify_drawing_eligibility,
    target_fingerprint,
)
from toto_ai.external_odds.matching import normalize_team_name
from toto_ai.external_odds.reviewed_schedule import (
    ReviewedScheduleCatalog,
    ReviewedScheduleEvidence,
    load_reviewed_schedule_catalog,
    select_reviewed_evidence,
)
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceIntegrityError,
    ScheduleEvidenceLedger,
    ScheduleObservation,
    drawing_schedule_dates,
    load_bound_schedule_evidence_ledger,
    resolve_schedule_evidence,
)
from toto_ai.external_odds.team_registry import (
    DrawingEventPinRecord,
    enqueue_review,
    load_ready_drawing_pins,
    load_ready_pin_set,
    publish_canonical_pin_set,
    publish_drawing_preparation,
    refresh_ready_drawing_preparation_evidence,
    upsert_team_entity,
)
from toto_ai.external_odds.team_resolution import (
    RESOLVER_VERSION,
    CandidateResolution,
    ResolutionContext,
    derive_resolution_context,
    resolve_event_candidate,
)


@dataclass(frozen=True)
class PreparationEventResult:
    event_order: int
    target_event_id: int
    status: str
    provider_fixture_id: str | None
    reason: str
    confidence: float
    margin: float
    candidate_evidence: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class DrawingPreparationResult:
    drawing_id: int
    drawing_number: int | None
    drawing_fingerprint: str
    provider: str
    status: str
    mapped_count: int
    unresolved_event_orders: tuple[int, ...]
    eligibility: DrawingEligibility
    events: tuple[PreparationEventResult, ...]
    pins: tuple[DrawingEventPinRecord, ...]
    schedule_diagnostics: tuple[dict[str, str | None], ...] = ()

    @property
    def baseline_only_event_orders(self) -> tuple[int, ...]:
        return tuple(
            item.event_order
            for item in self.events
            if item.status == "baseline_only"
        )

    @property
    def external_coverage_count(self) -> int:
        return 15 - len(self.baseline_only_event_orders)


@dataclass(frozen=True)
class PreparationScheduleResult:
    candidates: tuple[ProviderEvent, ...]
    diagnostics: tuple[dict[str, str | None], ...]


@dataclass(frozen=True)
class _ResolutionPreview:
    provider_candidates: tuple[ProviderEvent, ...]
    resolutions: tuple[CandidateResolution, ...]
    candidate_by_id: Mapping[str, ProviderEvent]
    resolved_starts: Mapping[int, datetime]
    eligibility: DrawingEligibility


def fetch_preparation_schedule(
    target: TargetDrawing,
    provider_client: Any,
    *,
    session_factory: Any,
    provider: str = "api-sports",
    event_contexts: Mapping[int, ResolutionContext] | None = None,
    missing_start_horizon_days: int = 5,
) -> PreparationScheduleResult:
    """Fetch dates until strict non-publishing resolution is ready or exhausted."""
    if not 1 <= missing_start_horizon_days <= 5:
        raise ValueError("missing_start_horizon_days must be from 1 through 5")
    drawing_dates = drawing_schedule_dates(
        target,
        maximum_span_days=missing_start_horizon_days,
    )
    required: dict[str, set[date]] = {}
    for event in target.events:
        if event.sport not in {"football", "hockey"}:
            continue
        dates = required.setdefault(event.sport, set())
        # Fetch every UTC date in the drawing's bounded span.  Sparse known
        # starts must not create blind intermediate dates, and one missing
        # start expands the complete horizon rather than a per-event guess.
        dates.update(drawing_dates)

    events_by_identity: dict[tuple[str, str], ProviderEvent] = {}
    diagnostics: list[dict[str, str | None]] = []
    failed_before_readiness = False
    ready = False
    for sport in sorted(required):
        for requested_date in sorted(required[sport]):
            try:
                events = provider_client.fetch_schedule(sport, (requested_date,))
            except Exception as error:  # provider errors are isolated per date
                diagnostics.append(
                    {
                        "sport": sport,
                        "date": requested_date.isoformat(),
                        "status": "failed",
                        "reason": str(error) or type(error).__name__,
                    }
                )
                failed_before_readiness = True
                continue
            diagnostics.append(
                {
                    "sport": sport,
                    "date": requested_date.isoformat(),
                    "status": "success",
                    "reason": None,
                }
            )
            for event in events:
                events_by_identity[(event.provider, event.provider_event_id)] = event
            preview = _resolve_preparation_candidates(
                target,
                tuple(events_by_identity.values()),
                session_factory=session_factory,
                provider=provider,
                event_contexts=event_contexts,
            )
            ready = (
                not failed_before_readiness
                and all(
                    resolution.status == "matched" for resolution in preview.resolutions
                )
                and preview.eligibility.status == "playable"
            )
            if ready:
                break
        if ready:
            break
    return PreparationScheduleResult(
        candidates=tuple(events_by_identity.values()),
        diagnostics=tuple(diagnostics),
    )


def prepare_drawing(
    target: TargetDrawing,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    *,
    session_factory: Any,
    provider: str = "api-sports",
    event_contexts: Mapping[int, ResolutionContext] | None = None,
    schedule_diagnostics: tuple[dict[str, str | None], ...] = (),
    reviewed_schedule_catalog: str | Path | None = None,
    schedule_evidence_ledger: str | Path | None = None,
    expected_schedule_evidence_sha256: str | None = None,
    expected_schedule_evidence_semantic_hash: str | None = None,
    evaluated_at: datetime | None = None,
) -> DrawingPreparationResult:
    """Resolve strict external pins and explicit TotoBrief baseline-only rows."""
    persist_drawing_identity(session_factory, target)
    fingerprint = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )
    reference = evaluated_at or datetime.now(timezone.utc)
    evidence_ledger = (
        None
        if schedule_evidence_ledger is None
        else load_bound_schedule_evidence_ledger(
            Path(schedule_evidence_ledger),
            expected_content_sha256=expected_schedule_evidence_sha256,
            expected_semantic_hash=expected_schedule_evidence_semantic_hash,
        )
    )
    # This also invalidates any valid pins for an older fingerprint.
    try:
        if reviewed_schedule_catalog is None and schedule_evidence_ledger is None:
            existing = load_ready_drawing_pins(
                session_factory,
                drawing_id=target.drawing_id,
                drawing_fingerprint=fingerprint,
                provider=provider,
            )
        else:
            existing = load_ready_pin_set(
                session_factory,
                drawing_id=target.drawing_id,
                drawing_fingerprint=fingerprint,
            )
    except ValueError as error:
        if str(error) not in {
            "drawing pins are incomplete",
            "stale drawing pins: fingerprint changed",
            "ready drawing preparation is missing; run prepare-drawing",
            "drawing preparation is not ready; run prepare-drawing",
            "preparation_fail:not_ready_15_of_15",
            "ready drawing preparation has no complete pin set",
        }:
            raise
        existing = ()
    if existing:
        failed_orders = _failed_date_pin_orders(target, existing, schedule_diagnostics)
        if failed_orders:
            raise ValueError(
                "required preparation schedule UTC date failed for event orders "
                f"{failed_orders}; retry before using existing pins"
            )
        reviewed_catalog = None
        if reviewed_schedule_catalog is not None:
            reviewed_catalog = load_reviewed_schedule_catalog(
                Path(reviewed_schedule_catalog),
                evaluated_at=evaluated_at or datetime.now(timezone.utc),
                max_age=timedelta(hours=12),
            )
        _validate_existing_pins_against_candidates(
            target,
            existing,
            tuple(candidates),
            provider=provider,
            reviewed_catalog=reviewed_catalog,
            schedule_evidence_ledger=evidence_ledger,
        )
        schedule_evidence_upgrade_orders = _baseline_schedule_evidence_upgrade_orders(
            target,
            existing,
            evidence_ledger,
            evaluated_at=reference,
        )
        if not schedule_evidence_upgrade_orders:
            result = _result_from_existing(target, fingerprint, provider, existing)
            refresh_ready_drawing_preparation_evidence(
                session_factory,
                drawing_id=target.drawing_id,
                drawing_fingerprint=fingerprint,
                provider=provider,
                readiness_summary=_readiness_summary(result, target),
            )
            return result
    else:
        schedule_evidence_upgrade_orders = ()

    preview = _resolve_preparation_candidates(
        target,
        candidates,
        session_factory=session_factory,
        provider=provider,
        event_contexts=event_contexts,
    )
    resolutions = list(preview.resolutions)
    candidate_by_id = preview.candidate_by_id
    reviewed_catalog: ReviewedScheduleCatalog | None = None
    reviewed_by_order: dict[int, ReviewedScheduleEvidence] = {}
    evidence_by_order: dict[int, ScheduleObservation] = {}
    evidence_conflict_orders: list[int] = []
    reviewed_error: str | None = None
    if reviewed_schedule_catalog is not None:
        reference = evaluated_at or datetime.now(timezone.utc)
        try:
            reviewed_catalog = load_reviewed_schedule_catalog(
                Path(reviewed_schedule_catalog),
                evaluated_at=reference,
                max_age=timedelta(hours=12),
            )
            reviewed_by_order = _admit_reviewed_fallbacks(
                target,
                fingerprint=fingerprint,
                resolutions=tuple(resolutions),
                catalog=reviewed_catalog,
                schedule_diagnostics=schedule_diagnostics,
            )
        except (OSError, TypeError, ValueError) as error:
            reviewed_error = str(error) or type(error).__name__
            reviewed_by_order = {}

    if schedule_evidence_ledger is not None:
        assert evidence_ledger is not None
        for event, resolution in zip(target.events, resolutions, strict=True):
            if (
                resolution.status == "matched"
                and event.event_order not in schedule_evidence_upgrade_orders
            ):
                continue
            evidence_resolution = resolve_schedule_evidence(
                event,
                evidence_ledger,
                evaluated_at=reference,
            )
            if (
                evidence_resolution.state == "RESOLVED"
                and evidence_resolution.observation is not None
            ):
                evidence_by_order[event.event_order] = evidence_resolution.observation
            elif evidence_resolution.state == "CONFLICT":
                evidence_conflict_orders.append(event.event_order)
    if evidence_conflict_orders:
        raise ScheduleEvidenceIntegrityError(
            "conflicting authoritative schedule identity for event orders "
            f"{tuple(evidence_conflict_orders)}"
        )

    baseline_orders = tuple(
        event.event_order
        for event, resolution in zip(target.events, resolutions, strict=True)
        if resolution.status != "matched"
        and event.event_order not in reviewed_by_order
        and event.event_order not in evidence_by_order
    )
    baseline_probability_hash = (
        _baseline_probability_input_sha256(target)
        if baseline_orders
        and all(event.pool_probabilities is not None for event in target.events)
        else None
    )

    pin_specs: list[dict[str, Any]] = []
    canonical_pin_specs: list[dict[str, Any]] = []
    events: list[PreparationEventResult] = []
    for event, resolution in zip(target.events, resolutions, strict=True):
        fixture_id = resolution.provider_event_id
        reviewed_evidence = reviewed_by_order.get(event.event_order)
        reusable_evidence = evidence_by_order.get(event.event_order)
        if reusable_evidence is not None:
            evidence_orientation = "same"
            evidence_resolution = resolve_schedule_evidence(
                event,
                evidence_ledger,
                evaluated_at=reference,
            )
            if evidence_resolution.orientation == "reversed":
                evidence_orientation = "reversed"
            canonical_home_name = (
                reusable_evidence.home_entity
                if evidence_orientation == "same"
                else reusable_evidence.away_entity
            )
            canonical_away_name = (
                reusable_evidence.away_entity
                if evidence_orientation == "same"
                else reusable_evidence.home_entity
            )
            home_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=canonical_home_name,
                context=event.championship,
            ).id
            away_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=canonical_away_name,
                context=event.championship,
            ).id
            canonical_pin_specs.append(
                {
                    "target_event_id": str(event.event_id),
                    "event_order": event.event_order,
                    "source_provider": "schedule-evidence",
                    "source_fixture_id": None,
                    "reviewed_evidence_id": reusable_evidence.observation_id,
                    "canonical_home_team_id": home_team_id,
                    "canonical_away_team_id": away_team_id,
                    "source_home_team_id": None,
                    "source_away_team_id": None,
                    "starts_at": reusable_evidence.starts_at,
                    "schedule_only": True,
                    "provenance": {
                        "resolver": "schedule-evidence-v1",
                        "orientation": evidence_orientation,
                        "evidence_id": reusable_evidence.observation_id,
                        "evidence_hash": reusable_evidence.semantic_hash,
                        "ledger_hash": evidence_ledger.semantic_hash,
                        "reviewer": reusable_evidence.reviewer,
                        "reviewed_at": reusable_evidence.reviewed_at.isoformat(),
                        "claims": [
                            {
                                "source_name": claim.source_name,
                                "role": claim.role,
                                "source_url": claim.source_url,
                            }
                            for claim in reusable_evidence.claims
                        ],
                    },
                }
            )
            events.append(
                PreparationEventResult(
                    event_order=event.event_order,
                    target_event_id=event.event_id,
                    status="matched",
                    provider_fixture_id=None,
                    reason="exact reusable reviewed schedule evidence",
                    confidence=1.0,
                    margin=1.0,
                )
            )
            continue
        if reviewed_evidence is not None:
            home_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=event.home_team,
                context=event.championship,
            ).id
            away_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=event.away_team,
                context=event.championship,
            ).id
            canonical_pin_specs.append(
                {
                    "target_event_id": str(event.event_id),
                    "event_order": event.event_order,
                    "source_provider": "reviewed-schedule",
                    "source_fixture_id": None,
                    "reviewed_evidence_id": reviewed_evidence.evidence_id,
                    "canonical_home_team_id": home_team_id,
                    "canonical_away_team_id": away_team_id,
                    "source_home_team_id": None,
                    "source_away_team_id": None,
                    "starts_at": reviewed_evidence.starts_at,
                    "schedule_only": True,
                    "provenance": {
                        "evidence_id": reviewed_evidence.evidence_id,
                        "evidence_hash": reviewed_evidence.semantic_hash,
                        "catalog_hash": reviewed_catalog.semantic_hash,
                        "reviewer": reviewed_evidence.reviewer,
                        "reviewed_at": reviewed_evidence.reviewed_at.isoformat(),
                        "source_claims": [
                            {
                                "source_name": claim.source_name,
                                "role": claim.role,
                                "source_url": claim.source_url,
                                "snapshot_sha256": claim.snapshot_sha256,
                                "captured_at": claim.captured_at.isoformat(),
                            }
                            for claim in reviewed_evidence.claims
                        ],
                    },
                }
            )
            events.append(
                PreparationEventResult(
                    event_order=event.event_order,
                    target_event_id=event.event_id,
                    status="matched",
                    provider_fixture_id=None,
                    reason=(
                        "strict reviewed schedule evidence admitted after "
                        "API-Sports source absence"
                    ),
                    confidence=1.0,
                    margin=1.0,
                    candidate_evidence=(),
                )
            )
            continue
        if resolution.status != "matched" or fixture_id is None:
            enqueue_review(
                session_factory,
                drawing_id=target.drawing_id,
                drawing_fingerprint=fingerprint,
                target_event_id=event.event_id,
                event_order=event.event_order,
                provider=provider,
                sport=event.sport,
                target_home_team=event.home_team,
                target_away_team=event.away_team,
                context={
                    "championship": event.championship,
                    "starts_at": _iso(event.starts_at),
                    "deadline": target.deadline.isoformat(),
                },
                resolution_reason=(
                    f"{resolution.reason}; reviewed fallback: {reviewed_error}"
                    if reviewed_error is not None
                    and resolution.status == "source_missing_competition"
                    else resolution.reason
                ),
                candidate_evidence=[asdict(item) for item in resolution.candidates],
            )
            if baseline_probability_hash is None:
                events.append(
                    PreparationEventResult(
                        event_order=event.event_order,
                        target_event_id=event.event_id,
                        status=resolution.status,
                        provider_fixture_id=fixture_id,
                        reason=resolution.reason,
                        confidence=resolution.confidence,
                        margin=resolution.margin,
                        candidate_evidence=tuple(
                            asdict(item) for item in resolution.candidates
                        ),
                    )
                )
                continue
            home_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=event.home_team,
                context=event.championship,
            ).id
            away_team_id = upsert_team_entity(
                session_factory,
                sport=event.sport,
                canonical_name=event.away_team,
                context=event.championship,
            ).id
            canonical_pin_specs.append(
                {
                    "target_event_id": str(event.event_id),
                    "event_order": event.event_order,
                    "source_provider": "totobrief-baseline",
                    "source_fixture_id": None,
                    "reviewed_evidence_id": None,
                    "canonical_home_team_id": home_team_id,
                    "canonical_away_team_id": away_team_id,
                    "source_home_team_id": None,
                    "source_away_team_id": None,
                    "starts_at": event.starts_at,
                    "schedule_only": True,
                    "provenance": {
                        "reason_code": "baseline_only_external_unavailable",
                        "resolution_status": resolution.status,
                        "resolution_reason": resolution.reason,
                        "totobrief_event_order": event.event_order,
                        "totobrief_event_id": event.event_id,
                        "bk_probabilities": event.bk_probabilities,
                        "pool_probabilities": event.pool_probabilities,
                        "baseline_probability_input_sha256": baseline_probability_hash,
                    },
                }
            )
            events.append(
                PreparationEventResult(
                    event_order=event.event_order,
                    target_event_id=event.event_id,
                    status="baseline_only",
                    provider_fixture_id=None,
                    reason="baseline_only_external_unavailable",
                    confidence=0.0,
                    margin=0.0,
                    candidate_evidence=tuple(
                        asdict(item) for item in resolution.candidates
                    ),
                )
            )
            continue
        else:
            candidate = candidate_by_id[fixture_id]
            provider_home, provider_away = _target_oriented_candidate(
                candidate, resolution.orientation
            )
            home_team_id = resolution.canonical_home_team_id
            away_team_id = resolution.canonical_away_team_id
            if home_team_id is None:
                home_team_id = upsert_team_entity(
                    session_factory,
                    sport=event.sport,
                    canonical_name=provider_home[0],
                    country=candidate.country,
                    context=candidate.league,
                ).id
            if away_team_id is None:
                away_team_id = upsert_team_entity(
                    session_factory,
                    sport=event.sport,
                    canonical_name=provider_away[0],
                    country=candidate.country,
                    context=candidate.league,
                ).id
            pin_specs.append(
                {
                    "drawing_id": target.drawing_id,
                    "drawing_fingerprint": fingerprint,
                    "target_event_id": event.event_id,
                    "event_order": event.event_order,
                    "provider": provider,
                    "canonical_home_team_id": home_team_id,
                    "canonical_away_team_id": away_team_id,
                    "provider_home_team_id": provider_home[1],
                    "provider_away_team_id": provider_away[1],
                    "provider_fixture_id": fixture_id,
                    "starts_at": candidate.starts_at,
                    "provenance": {
                        "resolver": RESOLVER_VERSION,
                        "reason": resolution.reason,
                        "confidence": resolution.confidence,
                        "margin": resolution.margin,
                        "orientation": resolution.orientation,
                        "provider_home_team": candidate.home_team,
                        "provider_away_team": candidate.away_team,
                        "provider_payload_hash": candidate.payload_hash,
                        "provider_fetched_at": candidate.fetched_at.isoformat(),
                        "league": candidate.league,
                        "country": candidate.country,
                    },
                }
            )
            canonical_pin_specs.append(
                {
                    "target_event_id": str(event.event_id),
                    "event_order": event.event_order,
                    "source_provider": provider,
                    "source_fixture_id": fixture_id,
                    "reviewed_evidence_id": None,
                    "canonical_home_team_id": home_team_id,
                    "canonical_away_team_id": away_team_id,
                    "source_home_team_id": provider_home[1],
                    "source_away_team_id": provider_away[1],
                    "starts_at": candidate.starts_at,
                    "schedule_only": False,
                    "provenance": {
                        "resolver": RESOLVER_VERSION,
                        "reason": resolution.reason,
                        "confidence": resolution.confidence,
                        "margin": resolution.margin,
                        "orientation": resolution.orientation,
                        "provider_home_team": candidate.home_team,
                        "provider_away_team": candidate.away_team,
                        "provider_payload_hash": candidate.payload_hash,
                        "provider_fetched_at": candidate.fetched_at.isoformat(),
                        "league": candidate.league,
                        "country": candidate.country,
                    },
                }
            )
        events.append(
            PreparationEventResult(
                event_order=event.event_order,
                target_event_id=event.event_id,
                status=resolution.status,
                provider_fixture_id=fixture_id,
                reason=resolution.reason,
                confidence=resolution.confidence,
                margin=resolution.margin,
                candidate_evidence=tuple(
                    asdict(item) for item in resolution.candidates
                ),
            )
        )

    eligibility = (
        _eligibility_with_reviewed(
            target,
            preview,
            reviewed_by_order,
            evidence_by_order=evidence_by_order,
        )
        if reviewed_by_order or evidence_by_order
        else preview.eligibility
    )
    date_failure_orders = _failed_date_event_orders(
        target,
        schedule_diagnostics,
        resolutions=tuple(resolutions),
        candidate_by_id=candidate_by_id,
        reviewed_by_order=reviewed_by_order,
        evidence_by_order=evidence_by_order,
        baseline_only_orders=baseline_orders,
    )
    has_external_coverage = any(event.status == "matched" for event in events)
    unresolved = tuple(
        sorted(
            {
                event.event_order
                for event in events
                if event.status != "matched"
                and not (
                    event.status == "baseline_only" and has_external_coverage
                )
            }
            | set(date_failure_orders)
        )
    )
    status = (
        "ready"
        if len(canonical_pin_specs) == 15
        and has_external_coverage
        and not unresolved
        and eligibility.status != "multi_day"
        and not date_failure_orders
        else "unresolved"
    )
    draft = DrawingPreparationResult(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        drawing_fingerprint=fingerprint,
        provider=provider,
        status=status,
        mapped_count=15 if status == "ready" else 0,
        unresolved_event_orders=unresolved,
        eligibility=eligibility,
        events=tuple(events),
        pins=(),
        schedule_diagnostics=schedule_diagnostics,
    )
    if status == "ready" and (
        reviewed_by_order
        or evidence_by_order
        or any(item.status == "baseline_only" for item in events)
    ):
        if existing and schedule_evidence_upgrade_orders:
            canonical_pin_specs = list(
                _merge_monotonic_schedule_upgrade_specs(
                    existing,
                    tuple(canonical_pin_specs),
                    upgrade_orders=schedule_evidence_upgrade_orders,
                )
            )
        selected_reviewed_hashes = {
            str(item["provenance"][hash_field])
            for item in canonical_pin_specs
            for source_provider, hash_field in (
                ("reviewed-schedule", "catalog_hash"),
                ("schedule-evidence", "ledger_hash"),
            )
            if item["source_provider"] == source_provider
        }
        if len(selected_reviewed_hashes) > 1:
            raise ValueError(
                "selected reviewed pins require conflicting reviewed catalog hashes"
            )
        selected_reviewed_catalog_hash = next(
            iter(selected_reviewed_hashes), None
        )
        pins = publish_canonical_pin_set(
            session_factory,
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            drawing_fingerprint=fingerprint,
            provider=provider,
            eligibility_status=eligibility.status,
            readiness_summary=_readiness_summary(draft, target),
            pin_specs=tuple(canonical_pin_specs),
            reviewed_catalog_hash=selected_reviewed_catalog_hash,
            allow_baseline_schedule_enrichment=bool(
                schedule_evidence_upgrade_orders
            ),
        )
    else:
        pins = publish_drawing_preparation(
            session_factory,
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            drawing_fingerprint=fingerprint,
            provider=provider,
            status=status,
            unresolved_event_orders=unresolved,
            eligibility_status=eligibility.status,
            readiness_summary=_readiness_summary(draft, target),
            pin_specs=tuple(pin_specs) if status == "ready" else (),
        )
    return DrawingPreparationResult(
        **{
            **draft.__dict__,
            "pins": tuple(sorted(pins, key=lambda pin: pin.event_order)),
        }
    )


def _baseline_schedule_evidence_upgrade_orders(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    ledger: ScheduleEvidenceLedger | None,
    *,
    evaluated_at: datetime,
) -> tuple[int, ...]:
    """Identify strict reviewed evidence that can replace baseline-only pins."""
    if ledger is None:
        return ()
    upgrades: list[int] = []
    conflicts: list[int] = []
    for event, pin in zip(target.events, pins, strict=True):
        if pin.effective_source_provider != "totobrief-baseline":
            continue
        resolution = resolve_schedule_evidence(
            event,
            ledger,
            evaluated_at=evaluated_at,
        )
        if resolution.state == "RESOLVED":
            upgrades.append(event.event_order)
        elif resolution.state == "CONFLICT":
            conflicts.append(event.event_order)
    if conflicts:
        raise ScheduleEvidenceIntegrityError(
            "conflicting authoritative schedule identity for event orders "
            f"{tuple(conflicts)}"
        )
    return tuple(upgrades)


def _merge_monotonic_schedule_upgrade_specs(
    existing: tuple[DrawingEventPinRecord, ...],
    proposed: tuple[Mapping[str, Any], ...],
    *,
    upgrade_orders: tuple[int, ...],
) -> tuple[dict[str, Any], ...]:
    """Preserve immutable pins while enriching baseline-only schedule rows."""
    existing_by_order = {pin.event_order: pin for pin in existing}
    proposed_by_order = {
        int(spec["event_order"]): dict(spec) for spec in proposed
    }
    if (
        tuple(sorted(existing_by_order)) != tuple(range(15))
        or tuple(sorted(proposed_by_order)) != tuple(range(15))
        or not upgrade_orders
        or any(order not in existing_by_order for order in upgrade_orders)
    ):
        raise ValueError("invalid monotonic schedule upgrade inputs")

    upgrade_set = set(upgrade_orders)
    merged: list[dict[str, Any]] = []
    for order in range(15):
        old = existing_by_order[order]
        new = proposed_by_order[order]
        if str(new.get("target_event_id")) != old.target_event_id:
            raise ValueError("schedule upgrade target event identity changed")
        if order not in upgrade_set:
            merged.append(_canonical_spec_from_existing_pin(old))
            continue
        if (
            old.effective_source_provider != "totobrief-baseline"
            or new.get("source_provider")
            not in {"reviewed-schedule", "schedule-evidence"}
            or new.get("event_order") != old.event_order
            or new.get("schedule_only") is not True
        ):
            raise ValueError("schedule upgrade is not monotonic")
        old_start = old.starts_at
        new_start = new.get("starts_at")
        if old_start not in {None, "baseline-only"} and (
            _parse_datetime(old_start) != new_start
        ):
            raise ValueError("schedule upgrade conflicts with existing kickoff")
        new["target_event_id"] = old.target_event_id
        new["canonical_home_team_id"] = old.canonical_home_team_id
        new["canonical_away_team_id"] = old.canonical_away_team_id
        merged.append(new)
    return tuple(merged)


def _canonical_spec_from_existing_pin(
    pin: DrawingEventPinRecord,
) -> dict[str, Any]:
    return {
        "target_event_id": pin.target_event_id,
        "event_order": pin.event_order,
        "source_provider": pin.effective_source_provider,
        "source_fixture_id": pin.effective_source_fixture_id,
        "reviewed_evidence_id": pin.reviewed_evidence_id,
        "canonical_home_team_id": pin.canonical_home_team_id,
        "canonical_away_team_id": pin.canonical_away_team_id,
        "source_home_team_id": pin.provider_home_team_id,
        "source_away_team_id": pin.provider_away_team_id,
        "starts_at": pin.starts_at,
        "source_identity_hash": pin.source_identity_hash,
        "schedule_only": pin.schedule_only,
        "provenance": pin.provenance,
    }


def _admit_reviewed_fallbacks(
    target: TargetDrawing,
    *,
    fingerprint: str,
    resolutions: tuple[CandidateResolution, ...],
    catalog: ReviewedScheduleCatalog,
    schedule_diagnostics: tuple[dict[str, str | None], ...],
) -> dict[int, ReviewedScheduleEvidence]:
    if any(resolution.status in {"ambiguous", "missing"} for resolution in resolutions):
        raise ValueError(
            "reviewed fallback cannot mask ambiguous or unproven API absence"
        )
    admitted: dict[int, ReviewedScheduleEvidence] = {}
    for event, resolution in zip(target.events, resolutions, strict=True):
        if resolution.status != "source_missing_competition":
            continue
        if target.drawing_number is None:
            raise ValueError("reviewed fallback requires visible drawing number")
        evidence = select_reviewed_evidence(
            catalog,
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            target_fingerprint=fingerprint,
            event_order=event.event_order,
            target_event_id=event.event_id,
        )
        relevant_key = (
            evidence.sport,
            evidence.starts_at.astimezone(timezone.utc).date().isoformat(),
        )
        relevant_status = _schedule_diagnostic_statuses(schedule_diagnostics).get(
            relevant_key
        )
        if relevant_status != "success":
            raise ValueError(
                "reviewed fallback requires successful API-Sports fetch for "
                f"relevant UTC date {relevant_key[0]}:{relevant_key[1]}"
            )
        if evidence.sport != event.sport:
            raise ValueError("reviewed evidence sport does not match target")
        if (
            event.starts_at is not None
            and evidence.starts_at != event.starts_at.astimezone(timezone.utc)
        ):
            raise ValueError("reviewed evidence start date/time does not match target")
        if evidence.starts_at < target.deadline:
            raise ValueError("reviewed evidence starts before drawing deadline")
        expected_class = _target_gender_age_class(event)
        if evidence.gender_age_class != expected_class:
            raise ValueError("reviewed evidence gender/age class does not match target")
        admitted[event.event_order] = evidence
    return admitted


def _target_gender_age_class(event: Any) -> str:
    text = " ".join(
        (
            event.championship,
            event.home_team,
            event.away_team,
            event.home_team_en or "",
            event.away_team_en or "",
        )
    ).casefold()
    if any(token in text for token in ("(ж)", "жен", "women", "female")):
        return "women-senior"
    if any(token in text for token in ("u19", "u-19", "u21", "u-21", "мол", "youth")):
        return "men-youth"
    return "men-senior"


def _eligibility_with_reviewed(
    target: TargetDrawing,
    preview: _ResolutionPreview,
    reviewed_by_order: Mapping[int, ReviewedScheduleEvidence],
    *,
    evidence_by_order: Mapping[int, ScheduleObservation] | None = None,
) -> DrawingEligibility:
    evidence_by_order = evidence_by_order or {}
    return classify_drawing_eligibility(
        tuple(
            EffectiveEventStart(
                event_order=event.event_order,
                starts_at=(
                    event.starts_at
                    if event.starts_at is not None
                    else (
                        reviewed_by_order[event.event_order].starts_at
                        if event.event_order in reviewed_by_order
                        else (
                            evidence_by_order[event.event_order].starts_at
                            if event.event_order in evidence_by_order
                            else preview.resolved_starts.get(event.event_order)
                        )
                    )
                ),
                source=(
                    "totobrief"
                    if event.starts_at is not None
                    else (
                        "provider"
                        if event.event_order in reviewed_by_order
                        or event.event_order in evidence_by_order
                        or preview.resolved_starts.get(event.event_order) is not None
                        else "unresolved"
                    )
                ),
            )
            for event in target.events
        )
    )


def persist_drawing_identity(
    session_factory: Any,
    target: TargetDrawing,
    *,
    require_visible_number: bool = False,
) -> None:
    """Persist or verify the authoritative target identity used for preparation."""

    if not isinstance(target, TargetDrawing):
        raise ValueError("target must be a TargetDrawing")
    if require_visible_number and target.drawing_number is None:
        raise ValueError("systematic preparation requires a visible drawing number")
    ended_at = target.deadline.astimezone(timezone.utc).isoformat()
    with session_factory.begin() as session:
        drawing = session.get(Drawing, target.drawing_id)
        if drawing is None:
            session.add(
                Drawing(
                    id=target.drawing_id,
                    number=target.drawing_number,
                    ended_at=ended_at,
                )
            )
            return
        if (
            drawing.number is not None
            and target.drawing_number is not None
            and drawing.number != target.drawing_number
        ):
            raise ValueError("stored drawing number does not match preparation target")
        if drawing.number is None:
            drawing.number = target.drawing_number
        if drawing.ended_at is not None:
            if _parse_datetime(drawing.ended_at) != target.deadline:
                raise ValueError(
                    "stored drawing ended_at does not match preparation target"
                )
        else:
            drawing.ended_at = ended_at


def _resolve_preparation_candidates(
    target: TargetDrawing,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    *,
    session_factory: Any,
    provider: str,
    event_contexts: Mapping[int, ResolutionContext] | None,
) -> _ResolutionPreview:
    provider_candidates = tuple(
        candidate for candidate in candidates if candidate.provider == provider
    )
    resolutions: list[CandidateResolution] = []
    for event in target.events:
        context = (
            event_contexts.get(event.event_order)
            if event_contexts is not None
            else None
        ) or derive_resolution_context(event, provider=provider)
        resolutions.append(
            resolve_event_candidate(
                event,
                provider_candidates,
                session_factory=session_factory,
                context=context,
            )
        )

    matched_fixture_ids = [
        resolution.provider_event_id
        for resolution in resolutions
        if resolution.status == "matched"
    ]
    duplicated = {
        fixture_id
        for fixture_id in matched_fixture_ids
        if matched_fixture_ids.count(fixture_id) > 1
    }
    if duplicated:
        resolutions = [
            (
                CandidateResolution(
                    status="ambiguous",
                    provider_event_id=None,
                    orientation=None,
                    confidence=resolution.confidence,
                    margin=resolution.margin,
                    reason="provider fixture is not unique across drawing events",
                    candidates=resolution.candidates,
                )
                if resolution.provider_event_id in duplicated
                else resolution
            )
            for resolution in resolutions
        ]

    candidate_by_id = {
        candidate.provider_event_id: candidate for candidate in provider_candidates
    }
    resolved_starts = {
        event.event_order: candidate_by_id[resolution.provider_event_id].starts_at
        for event, resolution in zip(target.events, resolutions, strict=True)
        if resolution.status == "matched" and resolution.provider_event_id is not None
    }
    starts = tuple(
        EffectiveEventStart(
            event_order=event.event_order,
            starts_at=(
                event.starts_at
                if event.starts_at is not None
                else resolved_starts.get(event.event_order)
            ),
            source=(
                "totobrief"
                if event.starts_at is not None
                else (
                    "provider"
                    if resolved_starts.get(event.event_order) is not None
                    else "unresolved"
                )
            ),
        )
        for event in target.events
    )
    return _ResolutionPreview(
        provider_candidates=provider_candidates,
        resolutions=tuple(resolutions),
        candidate_by_id=candidate_by_id,
        resolved_starts=resolved_starts,
        eligibility=classify_drawing_eligibility(starts),
    )


def load_local_schedule(
    path: str | Path,
    *,
    provider: str = "api-sports",
    sport: str = "football",
) -> tuple[ProviderEvent, ...]:
    """Load a self-contained normalized schedule fixture/cache without network."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("schedule cache must be a JSON object")
    envelope_fetched_at = payload.get("fetched_at")
    if "payload" in payload and isinstance(payload["payload"], dict):
        payload = payload["payload"]
    fetched_at = _parse_datetime(
        envelope_fetched_at or payload.get("fetched_at") or payload.get("timestamp")
    )
    if isinstance(payload.get("response"), list):
        resolved_sport = (
            "hockey"
            if any(
                isinstance(item, dict) and "game" in item
                for item in payload["response"]
            )
            else sport
        )
        return _parse_schedule_payload(  # type: ignore[arg-type]
            resolved_sport, payload, fetched_at=fetched_at
        )
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("normalized schedule cache must contain events")
    events = []
    for item in raw_events:
        if not isinstance(item, dict):
            raise ValueError("schedule event must be an object")
        event_id = str(item["id"])
        events.append(
            ProviderEvent(
                provider=provider,
                provider_event_id=event_id,
                sport=str(item.get("sport", "football")),  # type: ignore[arg-type]
                league=str(item["league"]),
                starts_at=_parse_datetime(item["date"]),
                home_team=str(item["home"]),
                away_team=str(item["away"]),
                fetched_at=fetched_at,
                payload_hash=str(item.get("payload_hash", f"cache-{event_id}")),
                country=(None if item.get("country") is None else str(item["country"])),
                provider_home_team_id=(
                    str(item["home_id"])
                    if item.get("home_id") is not None
                    else _name_team_id(item["home"])
                ),
                provider_away_team_id=(
                    str(item["away_id"])
                    if item.get("away_id") is not None
                    else _name_team_id(item["away"])
                ),
            )
        )
    return tuple(events)


def _result_from_existing(
    target: TargetDrawing,
    fingerprint: str,
    provider: str,
    pins: tuple[DrawingEventPinRecord, ...],
) -> DrawingPreparationResult:
    starts = tuple(
        EffectiveEventStart(
            event_order=event.event_order,
            starts_at=(
                event.starts_at
                or (
                    None
                    if pins[event.event_order].starts_at is None
                    else _parse_datetime(pins[event.event_order].starts_at)
                )
            ),
            source=(
                "totobrief"
                if event.starts_at is not None
                else (
                    "unresolved"
                    if pins[event.event_order].starts_at is None
                    else "provider"
                )
            ),
        )
        for event in target.events
    )
    eligibility = classify_drawing_eligibility(starts)
    events = tuple(
        PreparationEventResult(
            event_order=event.event_order,
            target_event_id=event.event_id,
            status=(
                "baseline_only"
                if pins[event.event_order].effective_source_provider
                == "totobrief-baseline"
                else "matched"
            ),
            provider_fixture_id=pins[event.event_order].provider_fixture_id,
            reason="existing exact drawing pin",
            confidence=1.0,
            margin=1.0,
        )
        for event in target.events
    )
    return DrawingPreparationResult(
        target.drawing_id,
        target.drawing_number,
        fingerprint,
        provider,
        "ready" if eligibility.status != "multi_day" else "unresolved",
        15,
        (),
        eligibility,
        events,
        pins,
    )


def _readiness_summary(
    result: DrawingPreparationResult,
    target: TargetDrawing,
) -> str:
    probability_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    market_probability_hash = (
        _baseline_probability_input_sha256(target)
        if all(event.pool_probabilities is not None for event in target.events)
        else None
    )
    evidence_entry = {
        "version": 1,
        "target_fetched_at": target.fetched_at.isoformat(),
        "probability_input_sha256": probability_hash,
        "market_probability_input_sha256": market_probability_hash,
        "probability_outcome_order": list(TOTO_BRIEF_OUTCOME_ORDER),
    }
    return json.dumps(
        {
            "status": result.status,
            "mapped_count": result.mapped_count,
            "unresolved_event_orders": result.unresolved_event_orders,
            "eligibility": asdict(result.eligibility),
            "events": [asdict(event) for event in result.events],
            "schedule_diagnostics": result.schedule_diagnostics,
            "target_fetched_at": target.fetched_at.isoformat(),
            "probability_input_sha256": probability_hash,
            "market_probability_input_sha256": market_probability_hash,
            "probability_outcome_order": list(TOTO_BRIEF_OUTCOME_ORDER),
            "market_evidence_version": 1,
            "market_evidence_history": [evidence_entry],
            "baseline_probability_input_sha256": (
                market_probability_hash
                if result.baseline_only_event_orders
                else None
            ),
            "external_coverage_count": result.external_coverage_count,
            "baseline_only_event_orders": result.baseline_only_event_orders,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def preparation_probability_sha256(
    probabilities: tuple[tuple[float, float, float], ...],
) -> str:
    if len(probabilities) != 15:
        raise ValueError("preparation probabilities require exactly 15 rows")
    for row in probabilities:
        if len(row) != 3:
            raise ValueError(
                "preparation probabilities require exactly three values per row"
            )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
            for value in row
        ):
            raise ValueError("preparation probabilities require finite positive values")
        if not isclose(sum(row), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("preparation probabilities must sum to one")
    payload = json.dumps(
        probabilities,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _baseline_probability_input_sha256(target: TargetDrawing) -> str:
    rows = []
    for event in target.events:
        if event.pool_probabilities is None:
            raise ValueError(
                "baseline probabilities require complete TotoBrief pool rows"
            )
        rows.append(
            {
                "event_order": event.event_order,
                "event_id": event.event_id,
                "bk": event.bk_probabilities,
                "pool": event.pool_probabilities,
            }
        )
    # Reuse the strict finite/positive/normalized validator for both matrices.
    preparation_probability_sha256(tuple(item["bk"] for item in rows))
    preparation_probability_sha256(tuple(item["pool"] for item in rows))
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def refresh_ready_preparation_for_target(
    target: TargetDrawing,
    *,
    session_factory: Any,
    provider: str,
) -> None:
    """Bind immutable pins to the latest complete TotoBrief market snapshot."""
    market_probability_hash = _baseline_probability_input_sha256(target)
    probability_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    refresh_ready_drawing_preparation_evidence(
        session_factory,
        drawing_id=target.drawing_id,
        drawing_fingerprint=target_fingerprint(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            deadline=target.deadline,
            events=target.events,
        ),
        provider=provider,
        readiness_summary=json.dumps(
            {
                "status": "ready",
                "mapped_count": 15,
                "unresolved_event_orders": [],
                "target_fetched_at": target.fetched_at.isoformat(),
                "probability_input_sha256": probability_hash,
                "market_probability_input_sha256": market_probability_hash,
                "baseline_probability_input_sha256": market_probability_hash,
                "probability_outcome_order": list(TOTO_BRIEF_OUTCOME_ORDER),
                "market_evidence_version": 1,
                "market_evidence_history": [
                    {
                        "version": 1,
                        "target_fetched_at": target.fetched_at.isoformat(),
                        "probability_input_sha256": probability_hash,
                        "market_probability_input_sha256": market_probability_hash,
                        "probability_outcome_order": list(
                            TOTO_BRIEF_OUTCOME_ORDER
                        ),
                    }
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _target_oriented_candidate(
    candidate: ProviderEvent, orientation: str | None
) -> tuple[tuple[str, str], tuple[str, str]]:
    home = (
        candidate.home_team,
        candidate.provider_home_team_id or _name_team_id(candidate.home_team),
    )
    away = (
        candidate.away_team,
        candidate.provider_away_team_id or _name_team_id(candidate.away_team),
    )
    return (home, away) if orientation == "same" else (away, home)


def _validate_existing_pins_against_candidates(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    candidates: tuple[ProviderEvent, ...],
    *,
    provider: str,
    reviewed_catalog: ReviewedScheduleCatalog | None = None,
    schedule_evidence_ledger: ScheduleEvidenceLedger | None = None,
) -> None:
    candidates_by_id: dict[str, list[ProviderEvent]] = {}
    for candidate in candidates:
        if candidate.provider == provider:
            candidates_by_id.setdefault(candidate.provider_event_id, []).append(
                candidate
            )
    for event, pin in zip(target.events, pins, strict=True):
        if pin.effective_source_provider == "totobrief-baseline":
            if (
                pin.target_event_id != str(event.event_id)
                or pin.event_order != event.event_order
                or pin.provenance.get("reason_code")
                != "baseline_only_external_unavailable"
            ):
                raise ValueError("ready TotoBrief baseline pin conflicts with target")
            continue
        if pin.effective_source_provider == "schedule-evidence":
            if schedule_evidence_ledger is None or pin.reviewed_evidence_id is None:
                raise ValueError(
                    "ready schedule-evidence pin cannot be revalidated without ledger"
                )
            resolution = resolve_schedule_evidence(
                event,
                schedule_evidence_ledger,
                evaluated_at=datetime.now(timezone.utc),
            )
            evidence = resolution.observation
            if (
                resolution.state != "RESOLVED"
                or evidence is None
                or evidence.observation_id != pin.reviewed_evidence_id
                or _parse_datetime(pin.starts_at) != evidence.starts_at
                or resolution.orientation
                != pin.provenance.get("orientation", "same")
                or pin.provenance.get("evidence_hash") != evidence.semantic_hash
                or pin.provenance.get("ledger_hash")
                != schedule_evidence_ledger.semantic_hash
            ):
                raise ScheduleEvidenceIntegrityError(
                    "ready schedule-evidence pin conflicts with ledger"
                )
            continue
        if pin.effective_source_provider == "reviewed-schedule":
            if reviewed_catalog is None or pin.reviewed_evidence_id is None:
                raise ValueError(
                    "ready reviewed pin cannot be revalidated without catalog"
                )
            if target.drawing_number is None:
                raise ValueError("reviewed pin requires visible drawing number")
            evidence = select_reviewed_evidence(
                reviewed_catalog,
                drawing_id=target.drawing_id,
                drawing_number=target.drawing_number,
                target_fingerprint=pin.drawing_fingerprint,
                event_order=event.event_order,
                target_event_id=event.event_id,
            )
            if (
                evidence.evidence_id != pin.reviewed_evidence_id
                or _parse_datetime(pin.starts_at) != evidence.starts_at
                or pin.provenance.get("evidence_hash") != evidence.semantic_hash
                or pin.provenance.get("catalog_hash") != reviewed_catalog.semantic_hash
            ):
                raise ValueError("ready reviewed pin conflicts with catalog")
            continue
        if pin.effective_source_provider != provider:
            raise ValueError("ready drawing pin has unknown source provider")
        matches = candidates_by_id.get(pin.effective_source_fixture_id, [])
        if len(matches) != 1:
            raise ValueError(
                "ready drawing preparation cannot be revalidated; "
                "refresh schedule and rerun prepare-drawing"
            )
        candidate = matches[0]
        orientation = pin.provenance.get("orientation", "same")
        if orientation not in {"same", "reversed"}:
            raise ValueError("ready drawing preparation has invalid orientation")
        provider_home, provider_away = _target_oriented_candidate(
            candidate, str(orientation)
        )
        if (
            provider_home[1] != pin.provider_home_team_id
            or provider_away[1] != pin.provider_away_team_id
            or _parse_datetime(pin.starts_at) != candidate.starts_at
            or event.event_order != pin.event_order
        ):
            raise ValueError(
                "ready drawing preparation conflicts with changed provider data; "
                "invalidate or create a new drawing version"
            )


def _name_team_id(value: object) -> str:
    return f"name:{normalize_team_name(str(value))}"


def _failed_date_event_orders(
    target: TargetDrawing,
    diagnostics: tuple[dict[str, str | None], ...],
    *,
    resolutions: tuple[CandidateResolution, ...] = (),
    candidate_by_id: Mapping[str, ProviderEvent] | None = None,
    reviewed_by_order: Mapping[int, ReviewedScheduleEvidence] | None = None,
    evidence_by_order: Mapping[int, ScheduleObservation] | None = None,
    baseline_only_orders: tuple[int, ...] = (),
) -> tuple[int, ...]:
    statuses = _schedule_diagnostic_statuses(diagnostics)
    failed = {key for key, status in statuses.items() if status == "failed"}
    if not failed:
        return ()
    resolution_by_order = {
        event.event_order: resolution
        for event, resolution in zip(target.events, resolutions, strict=True)
    }
    candidate_by_id = candidate_by_id or {}
    reviewed_by_order = reviewed_by_order or {}
    evidence_by_order = evidence_by_order or {}
    orders = []
    for event in target.events:
        if event.event_order in baseline_only_orders:
            continue
        effective_start = event.starts_at
        reviewed = reviewed_by_order.get(event.event_order)
        reusable = evidence_by_order.get(event.event_order)
        if effective_start is None and reviewed is not None:
            effective_start = reviewed.starts_at
        if effective_start is None and reusable is not None:
            effective_start = reusable.starts_at
        if effective_start is None:
            resolution = resolution_by_order.get(event.event_order)
            candidate = (
                None
                if resolution is None or resolution.provider_event_id is None
                else candidate_by_id.get(resolution.provider_event_id)
            )
            if candidate is not None:
                effective_start = candidate.starts_at
        if effective_start is None:
            if any(sport == event.sport for sport, _ in failed):
                orders.append(event.event_order)
        elif event.event_order in evidence_by_order:
            # The relevant UTC date is backed by independent reviewed evidence;
            # an API provider plan gap cannot erase that source observation.
            continue
        elif (
            event.sport,
            effective_start.astimezone(timezone.utc).date().isoformat(),
        ) in failed:
            orders.append(event.event_order)
    return tuple(orders)


def _failed_date_pin_orders(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    diagnostics: tuple[dict[str, str | None], ...],
) -> tuple[int, ...]:
    failed = {
        key
        for key, status in _schedule_diagnostic_statuses(diagnostics).items()
        if status == "failed"
    }
    if not failed:
        return ()
    return tuple(
        event.event_order
        for event, pin in zip(target.events, pins, strict=True)
        if pin.effective_source_provider
        not in {"totobrief-baseline", "schedule-evidence"}
        and (
            event.sport,
            _parse_datetime(pin.starts_at).date().isoformat(),
        )
        in failed
    )


def _schedule_diagnostic_statuses(
    diagnostics: tuple[dict[str, str | None], ...],
) -> dict[tuple[str, str], str]:
    """Return the final per-UTC-date fetch status.

    API-Sports schedule requests explicitly use ``timezone=UTC`` semantics,
    so local-calendar rollover must not change the relevant provider date.
    Later diagnostics for the same key supersede an earlier retry result.
    """
    statuses: dict[tuple[str, str], str] = {}
    for item in diagnostics:
        sport = item.get("sport")
        requested_date = item.get("date")
        status = item.get("status")
        if not sport or not requested_date or status not in {"success", "failed"}:
            continue
        try:
            canonical_date = date.fromisoformat(requested_date).isoformat()
        except ValueError:
            continue
        statuses[(sport, canonical_date)] = status
    return statuses


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("schedule datetime must be timezone-aware ISO text")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("schedule datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
