from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from toto_ai.db.models import Drawing
from toto_ai.external_odds.api_sports import _parse_schedule_payload
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing
from toto_ai.external_odds.eligibility import (
    DrawingEligibility,
    EffectiveEventStart,
    classify_drawing_eligibility,
    target_fingerprint,
)
from toto_ai.external_odds.matching import normalize_team_name
from toto_ai.external_odds.team_registry import (
    DrawingEventPinRecord,
    enqueue_review,
    load_ready_drawing_pins,
    publish_drawing_preparation,
    upsert_team_entity,
)
from toto_ai.external_odds.team_resolution import (
    CandidateResolution,
    ResolutionContext,
    derive_resolution_context,
    resolve_event_candidate,
)

_MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class PreparationEventResult:
    event_order: int
    target_event_id: int
    status: str
    provider_fixture_id: str | None
    reason: str
    confidence: float
    margin: float


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
    required: dict[str, set[date]] = {}
    for event in target.events:
        if event.sport not in {"football", "hockey"}:
            continue
        dates = required.setdefault(event.sport, set())
        if event.starts_at is not None:
            dates.add(event.starts_at.astimezone(timezone.utc).date())
        else:
            dates.update(
                _missing_start_dates(
                    target.deadline, missing_start_horizon_days
                )
            )

    events_by_identity: dict[tuple[str, str], ProviderEvent] = {}
    diagnostics: list[dict[str, str | None]] = []
    failed_before_readiness = False
    ready = False
    for sport in sorted(required):
        for requested_date in sorted(required[sport]):
            try:
                events = provider_client.fetch_schedule(
                    sport, (requested_date,)
                )
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
                    resolution.status == "matched"
                    for resolution in preview.resolutions
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
) -> DrawingPreparationResult:
    """Resolve a drawing and atomically publish pins only when all 15 are ready."""
    persist_drawing_identity(session_factory, target)
    fingerprint = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )
    # This also invalidates any valid pins for an older fingerprint.
    try:
        existing = load_ready_drawing_pins(
            session_factory,
            drawing_id=target.drawing_id,
            drawing_fingerprint=fingerprint,
            provider=provider,
        )
    except ValueError as error:
        if str(error) not in {
            "drawing pins are incomplete",
            "stale drawing pins: fingerprint changed",
            "ready drawing preparation is missing; run prepare-drawing",
            "drawing preparation is not ready; run prepare-drawing",
            "preparation_fail:not_ready_15_of_15",
        }:
            raise
        existing = ()
    if existing:
        failed_orders = _failed_date_event_orders(target, schedule_diagnostics)
        if failed_orders:
            raise ValueError(
                "required preparation schedule date failed for event orders "
                f"{failed_orders}; retry before using existing pins"
            )
        _validate_existing_pins_against_candidates(
            target, existing, tuple(candidates), provider=provider
        )
        return _result_from_existing(target, fingerprint, provider, existing)

    preview = _resolve_preparation_candidates(
        target,
        candidates,
        session_factory=session_factory,
        provider=provider,
        event_contexts=event_contexts,
    )
    resolutions = list(preview.resolutions)
    candidate_by_id = preview.candidate_by_id

    pin_specs: list[dict[str, Any]] = []
    events: list[PreparationEventResult] = []
    for event, resolution in zip(target.events, resolutions, strict=True):
        fixture_id = resolution.provider_event_id
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
                resolution_reason=resolution.reason,
                candidate_evidence=[asdict(item) for item in resolution.candidates],
            )
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
                        "resolver": "systematic-team-v1",
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
            )
        )

    eligibility = preview.eligibility
    date_failure_orders = _failed_date_event_orders(
        target, schedule_diagnostics
    )
    unresolved = tuple(
        sorted(
            {
                event.event_order
                for event in events
                if event.status != "matched"
            }
            | set(date_failure_orders)
        )
    )
    status = (
        "ready"
        if len(pin_specs) == 15
        and not unresolved
        and eligibility.status == "playable"
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
        raise ValueError(
            "systematic preparation requires a visible drawing number"
        )
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
            raise ValueError(
                "stored drawing number does not match preparation target"
            )
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
        if resolution.status == "matched"
        and resolution.provider_event_id is not None
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
        resolved_sport = "hockey" if any(
            isinstance(item, dict) and "game" in item for item in payload["response"]
        ) else sport
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
            starts_at=event.starts_at
            or _parse_datetime(pins[event.event_order].starts_at),
            source="totobrief" if event.starts_at is not None else "provider",
        )
        for event in target.events
    )
    eligibility = classify_drawing_eligibility(starts)
    events = tuple(
        PreparationEventResult(
            event_order=event.event_order,
            target_event_id=event.event_id,
            status="matched",
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
        "ready" if eligibility.status == "playable" else "unresolved",
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
    payload = json.dumps(
        probabilities,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()




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
) -> None:
    candidates_by_id: dict[str, list[ProviderEvent]] = {}
    for candidate in candidates:
        if candidate.provider == provider:
            candidates_by_id.setdefault(candidate.provider_event_id, []).append(
                candidate
            )
    for event, pin in zip(target.events, pins, strict=True):
        matches = candidates_by_id.get(pin.provider_fixture_id, [])
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


def _missing_start_dates(
    deadline: datetime, horizon_days: int
) -> tuple[date, ...]:
    local_date = deadline.astimezone(_MOSCOW).date()
    local_start = datetime.combine(local_date, datetime.min.time(), tzinfo=_MOSCOW)
    local_end = local_start + timedelta(days=horizon_days)
    first = local_start.astimezone(timezone.utc).date()
    last = (local_end - timedelta(microseconds=1)).astimezone(timezone.utc).date()
    return tuple(
        first + timedelta(days=offset)
        for offset in range((last - first).days + 1)
    )


def _failed_date_event_orders(
    target: TargetDrawing,
    diagnostics: tuple[dict[str, str | None], ...],
) -> tuple[int, ...]:
    failed = {
        (item.get("sport"), item.get("date"))
        for item in diagnostics
        if item.get("status") == "failed"
    }
    if not failed:
        return ()
    orders = []
    for event in target.events:
        if event.starts_at is None:
            if any(sport == event.sport for sport, _ in failed):
                orders.append(event.event_order)
        elif (event.sport, event.starts_at.date().isoformat()) in failed:
            orders.append(event.event_order)
    return tuple(orders)


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
