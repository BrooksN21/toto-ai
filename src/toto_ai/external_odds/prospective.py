from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from toto_ai.external_odds.collection import (
    SAFETY_STOP_FALLBACK,
    ExternalCollectionSnapshot,
    build_external_collection,
    resolve_open_target,
)
from toto_ai.external_odds.domain import ExternalOddsProvider, TargetDrawing
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.storage import save_collection
from toto_ai.external_odds.team_registry import DrawingEventPinRecord

ProspectivePhase = Literal["base", "expansion"]
ProspectiveStopReason = Literal[
    "no_retryable_fallbacks",
    "max_passes",
    "max_expansion_passes",
    "safety_stop",
]
ProviderFactory = Callable[[Path], ExternalOddsProvider]
_BASE_HORIZON_DAYS = 2
_MAX_HORIZON_DAYS = 5
_RETRYABLE_EXACT_REASONS = frozenset(
    (
        "partial schedule",
        "quota reserve reached",
    )
)
_RETRYABLE_REASON_PREFIXES = (
    "provider schedule failure:",
    "provider odds failure:",
)


@dataclass(frozen=True)
class ProspectiveCollectionPass:
    snapshot: ExternalCollectionSnapshot
    elapsed_seconds: float
    phase: ProspectivePhase
    phase_pass_number: int
    horizon_days: int


@dataclass(frozen=True)
class ProspectiveCollectionResult:
    snapshot: ExternalCollectionSnapshot
    passes: tuple[ProspectiveCollectionPass, ...]
    base_passes: tuple[ProspectiveCollectionPass, ...]
    expansion_passes: tuple[ProspectiveCollectionPass, ...]
    cache_dir: Path
    elapsed_seconds: float
    stop_reason: ProspectiveStopReason
    expanded: bool
    final_horizon_days: int
    total_requests: int
    total_cache_hits: int
    total_requested_schedule_dates: int
    total_successful_schedule_dates: int
    total_failed_schedule_dates: int
    eligibility: DrawingEligibility

    @property
    def base_pass_count(self) -> int:
        return len(self.base_passes)

    @property
    def expansion_pass_count(self) -> int:
        return len(self.expansion_passes)


def fresh_cache_session_dir(
    cache_root: Path,
    target: TargetDrawing,
    started_at: datetime,
) -> Path:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    drawing_label = target.drawing_number or target.drawing_id
    timestamp = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return Path(cache_root) / "runs" / f"{drawing_label}-{timestamp}-{uuid4().hex}"


def is_retryable_snapshot(snapshot: ExternalCollectionSnapshot) -> bool:
    return bool(snapshot.failed_schedule_dates) or any(
        _is_retryable_reason(event.fallback_reason) for event in snapshot.events
    )


def collect_fresh_open_external_odds(
    *,
    totobrief_client: Any,
    provider_factory: ProviderFactory,
    session_factory: Any,
    aliases: dict[str, str],
    cache_root: Path,
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None = None,
    reviewed_schedule_catalog: str | None = None,
    target: TargetDrawing | None = None,
    stop_at: datetime | None = None,
    max_passes: int = 3,
    expand_missing_starts: bool = True,
    expansion_horizon_days: int = 5,
    max_expansion_passes: int = 3,
    retry_delay_seconds: float = 65.0,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> ProspectiveCollectionResult:
    _validate_options(
        max_passes=max_passes,
        expand_missing_starts=expand_missing_starts,
        expansion_horizon_days=expansion_horizon_days,
        max_expansion_passes=max_expansion_passes,
        retry_delay_seconds=retry_delay_seconds,
    )
    started = monotonic()
    started_at = now()
    resolved_target = (
        resolve_open_target(totobrief_client, fetched_at=started_at)
        if target is None
        else target
    )
    _validate_stop_at(stop_at)
    if stop_at is not None and started_at >= stop_at:
        raise ValueError("safety stop reached before first collection pass")
    cache_dir = fresh_cache_session_dir(cache_root, resolved_target, started_at)
    base_passes: list[ProspectiveCollectionPass] = []
    expansion_passes: list[ProspectiveCollectionPass] = []
    stop_reason: ProspectiveStopReason = "max_passes"

    for pass_index in range(max_passes):
        if _safety_stop_reached(stop_at, now):
            if not base_passes:
                raise ValueError("safety stop reached before first collection pass")
            stop_reason = "safety_stop"
            break
        item = _run_pass(
            resolved_target,
            cache_dir=cache_dir,
            provider_factory=provider_factory,
            session_factory=session_factory,
            aliases=aliases,
            prepared_pins=prepared_pins,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            phase="base",
            phase_pass_number=pass_index + 1,
            horizon_days=_BASE_HORIZON_DAYS,
            stop_at=stop_at,
            now=now,
            monotonic=monotonic,
        )
        base_passes.append(item)
        if _snapshot_reached_safety_stop(item.snapshot) or _safety_stop_reached(
            stop_at, now
        ):
            stop_reason = "safety_stop"
            break
        if not is_retryable_snapshot(item.snapshot):
            stop_reason = "no_retryable_fallbacks"
            break
        if pass_index + 1 < max_passes:
            if _sleep_until_retry_or_stop(
                stop_at,
                retry_delay_seconds=retry_delay_seconds,
                now=now,
                sleep=sleep,
            ):
                stop_reason = "safety_stop"
                break

    stable_base_snapshot = (
        base_passes[-1].snapshot
        if stop_reason == "no_retryable_fallbacks"
        else None
    )
    if (
        expand_missing_starts
        and stable_base_snapshot is not None
        and _is_expansion_eligible(resolved_target, stable_base_snapshot)
    ):
        stop_reason = "max_expansion_passes"
        for pass_index in range(max_expansion_passes):
            if _safety_stop_reached(stop_at, now):
                stop_reason = "safety_stop"
                break
            item = _run_pass(
                resolved_target,
                cache_dir=cache_dir,
                provider_factory=provider_factory,
                session_factory=session_factory,
                aliases=aliases,
                prepared_pins=prepared_pins,
                reviewed_schedule_catalog=reviewed_schedule_catalog,
                phase="expansion",
                phase_pass_number=pass_index + 1,
                horizon_days=expansion_horizon_days,
                stop_at=stop_at,
                now=now,
                monotonic=monotonic,
            )
            expansion_passes.append(item)
            if _snapshot_reached_safety_stop(
                item.snapshot
            ) or _safety_stop_reached(stop_at, now):
                stop_reason = "safety_stop"
                break
            if not is_retryable_snapshot(item.snapshot):
                stop_reason = "no_retryable_fallbacks"
                break
            if pass_index + 1 < max_expansion_passes:
                if _sleep_until_retry_or_stop(
                    stop_at,
                    retry_delay_seconds=retry_delay_seconds,
                    now=now,
                    sleep=sleep,
                ):
                    stop_reason = "safety_stop"
                    break

    passes = (*base_passes, *expansion_passes)
    final_snapshot = passes[-1].snapshot
    return ProspectiveCollectionResult(
        snapshot=final_snapshot,
        passes=passes,
        base_passes=tuple(base_passes),
        expansion_passes=tuple(expansion_passes),
        cache_dir=cache_dir,
        elapsed_seconds=monotonic() - started,
        stop_reason=stop_reason,
        expanded=bool(expansion_passes),
        final_horizon_days=(
            expansion_horizon_days if expansion_passes else _BASE_HORIZON_DAYS
        ),
        total_requests=sum(item.snapshot.requests_made for item in passes),
        total_cache_hits=sum(item.snapshot.cache_hits for item in passes),
        total_requested_schedule_dates=sum(
            len(item.snapshot.requested_schedule_dates) for item in passes
        ),
        total_successful_schedule_dates=sum(
            len(item.snapshot.successful_schedule_dates) for item in passes
        ),
        total_failed_schedule_dates=sum(
            len(item.snapshot.failed_schedule_dates) for item in passes
        ),
        eligibility=final_snapshot.eligibility,
    )


def _run_pass(
    target: TargetDrawing,
    *,
    cache_dir: Path,
    provider_factory: ProviderFactory,
    session_factory: Any,
    aliases: dict[str, str],
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None,
    reviewed_schedule_catalog: str | None,
    phase: ProspectivePhase,
    phase_pass_number: int,
    horizon_days: int,
    stop_at: datetime | None,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
) -> ProspectiveCollectionPass:
    pass_started = monotonic()
    arguments = {
        "missing_start_horizon_days": horizon_days,
        "stop_at": stop_at,
        "now": now,
    }
    if prepared_pins is not None:
        arguments["prepared_pins"] = prepared_pins
    if reviewed_schedule_catalog is not None:
        arguments["reviewed_schedule_catalog"] = reviewed_schedule_catalog
    snapshot = _collect_target_pass(
        target,
        provider_factory(cache_dir),
        session_factory,
        aliases,
        **arguments,
    )
    return ProspectiveCollectionPass(
        snapshot=snapshot,
        elapsed_seconds=monotonic() - pass_started,
        phase=phase,
        phase_pass_number=phase_pass_number,
        horizon_days=horizon_days,
    )


def _collect_target_pass(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    session_factory: Any,
    aliases: dict[str, str],
    *,
    missing_start_horizon_days: int,
    stop_at: datetime | None,
    now: Callable[[], datetime],
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None = None,
    reviewed_schedule_catalog: str | None = None,
) -> ExternalCollectionSnapshot:
    snapshot = build_external_collection(
        target,
        provider,
        aliases,
        missing_start_horizon_days=missing_start_horizon_days,
        prepared_pins=prepared_pins,
        reviewed_schedule_catalog=reviewed_schedule_catalog,
        stop_at=stop_at,
        now=now,
    )
    if len(snapshot.events) != 15:
        raise ValueError("external collection must contain exactly 15 dispositions")
    save_collection(session_factory, snapshot)
    return snapshot


def _is_expansion_eligible(
    target: TargetDrawing,
    snapshot: ExternalCollectionSnapshot,
) -> bool:
    target_events = {event.event_order: event for event in target.events}
    return any(
        target_events[event.event_order].starts_at is None
        and event.match_status == "missing"
        and event.match_candidate_ids == ()
        and event.fallback_reason == "0 exact candidates"
        for event in snapshot.events
    )


def _is_retryable_reason(reason: str | None) -> bool:
    if reason is None:
        return False
    return reason in _RETRYABLE_EXACT_REASONS or reason.startswith(
        _RETRYABLE_REASON_PREFIXES
    )


def _snapshot_reached_safety_stop(snapshot: ExternalCollectionSnapshot) -> bool:
    return any(
        event.fallback_reason == SAFETY_STOP_FALLBACK for event in snapshot.events
    )


def _safety_stop_reached(
    stop_at: datetime | None,
    now: Callable[[], datetime],
) -> bool:
    return stop_at is not None and now() >= stop_at


def _sleep_until_retry_or_stop(
    stop_at: datetime | None,
    *,
    retry_delay_seconds: float,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> bool:
    if stop_at is None:
        sleep(retry_delay_seconds)
        return False
    remaining = (stop_at - now()).total_seconds()
    if remaining <= 0:
        return True
    sleep(min(retry_delay_seconds, remaining))
    return now() >= stop_at


def _validate_stop_at(stop_at: datetime | None) -> None:
    if stop_at is None:
        return
    if (
        not isinstance(stop_at, datetime)
        or stop_at.tzinfo is None
        or stop_at.utcoffset() != timedelta(0)
    ):
        raise ValueError("stop_at must be timezone-aware UTC")


def _validate_options(
    *,
    max_passes: int,
    expand_missing_starts: bool,
    expansion_horizon_days: int,
    max_expansion_passes: int,
    retry_delay_seconds: float,
) -> None:
    if (
        not isinstance(max_passes, int)
        or isinstance(max_passes, bool)
        or max_passes <= 0
    ):
        raise ValueError("max_passes must be a positive integer")
    if not isinstance(expand_missing_starts, bool):
        raise ValueError("expand_missing_starts must be a boolean")
    if (
        not isinstance(expansion_horizon_days, int)
        or isinstance(expansion_horizon_days, bool)
        or not _BASE_HORIZON_DAYS < expansion_horizon_days <= _MAX_HORIZON_DAYS
    ):
        raise ValueError(
            "expansion_horizon_days must be an integer greater than 2 "
            "and at most 5"
        )
    if (
        not isinstance(max_expansion_passes, int)
        or isinstance(max_expansion_passes, bool)
        or max_expansion_passes <= 0
    ):
        raise ValueError("max_expansion_passes must be a positive integer")
    if (
        not isinstance(retry_delay_seconds, (int, float))
        or isinstance(retry_delay_seconds, bool)
        or not isfinite(float(retry_delay_seconds))
        or retry_delay_seconds < 0
    ):
        raise ValueError("retry_delay_seconds must be finite and non-negative")
