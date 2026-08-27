from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from toto_ai.ev.drawing import resolve_open_drawing_from_api
from toto_ai.external_odds.api_sports import (
    APISportsDiagnostic,
    APISportsError,
    QuotaExhausted,
    SafetyStopReached,
    diagnostic_payload,
)
from toto_ai.external_odds.consensus import (
    MAXIMUM_ODDS_AGE,
    ConsensusResult,
    build_consensus,
)
from toto_ai.external_odds.domain import (
    ExternalOddsProvider,
    OutcomeTriplet,
    ProviderEvent,
    ProviderMarket,
    Sport,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.eligibility import (
    DrawingEligibility,
    EffectiveEventStart,
    classify_drawing_eligibility,
    target_fingerprint,
)
from toto_ai.external_odds.matching import MATCHER_VERSION, MatchDecision, match_event
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceIntegrityError,
    ScheduleEvidenceLedger,
    resolve_schedule_evidence,
)
from toto_ai.external_odds.schedule_sources import ReviewedCatalogScheduleSource
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import DrawingEventPinRecord

CONSENSUS_MINIMUM_BOOKMAKERS = 3
EXTERNAL_CONSENSUS = "external_consensus"
TOTOBRIEF_BK_FALLBACK = "totobrief_bk_fallback"
SAFETY_STOP_FALLBACK = "safety stop reached"
PIN_SCHEDULE_MAX_AGE = timedelta(hours=24)
PIN_START_TIME_TOLERANCE = timedelta(minutes=5)
_PIN_SOURCES_WITHOUT_LIVE_SCHEDULE = frozenset(
    {"totobrief-baseline", "reviewed-schedule", "schedule-evidence"}
)
_MOSCOW = ZoneInfo("Europe/Moscow")
_UNKNOWN_ELIGIBILITY = DrawingEligibility(
    status="unknown",
    earliest_start=None,
    latest_start=None,
    span_days=0,
    missing_event_orders=tuple(range(15)),
    totobrief_count=0,
    provider_count=0,
)


@dataclass(frozen=True)
class ExternalMarketProvenanceRecord:
    updated_at: str
    fetched_at: str
    payload_hash: str
    home_price: float | None
    draw_price: float | None
    away_price: float | None
    source_endpoint: str | None = None
    request_fingerprint: str | None = None


@dataclass(frozen=True)
class ExternalBookmakerQuoteRecord:
    bookmaker_id: str
    market_name: str
    updated_at: str
    fetched_at: str
    payload_hash: str
    home_price: float | None
    draw_price: float | None
    away_price: float | None
    eligible: int
    rejection_reason: str | None
    source_count: int
    source_provenance: tuple[ExternalMarketProvenanceRecord, ...]


@dataclass(frozen=True)
class ScheduleDateResult:
    sport: Sport
    requested_date: date
    events: tuple[ProviderEvent, ...]
    error: str | None
    provider_attempts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class PinnedRevalidationEvent:
    event_order: int
    status: str
    reason: str
    source_provider: str = "api-sports"
    revalidation_method: str = "api-sports-fixture-v1"
    evidence_id: str | None = None
    evidence_hash: str | None = None


@dataclass(frozen=True)
class PinnedRevalidationSummary:
    expected_count: int
    matched_count: int
    missing_event_orders: tuple[int, ...]
    provider_failure_event_orders: tuple[int, ...]
    stale_event_orders: tuple[int, ...]
    date_failure_event_orders: tuple[int, ...]
    identity_failure_event_orders: tuple[int, ...]
    start_time_failure_event_orders: tuple[int, ...]
    failed_schedule_dates: tuple[str, ...]
    oldest_schedule_fetched_at: str | None
    newest_schedule_fetched_at: str | None
    maximum_schedule_age_seconds: float | None
    schedule_fresh: bool
    provider_checks_passed: bool
    fixture_checks_passed: bool
    team_checks_passed: bool
    orientation_checks_passed: bool
    start_time_checks_passed: bool
    required_dates_complete: bool
    ready_for_play: bool
    events: tuple[PinnedRevalidationEvent, ...]


@dataclass(frozen=True)
class ExternalEventDispositionRecord:
    drawing_id: int
    event_order: int
    target_event_id: int
    sport: str
    championship: str
    starts_at: str
    home_team: str
    away_team: str
    home_team_en: str | None
    away_team_en: str | None
    match_status: str
    provider_event_id: str | None
    provider_event_fetched_at: str | None
    provider_event_payload_hash: str | None
    matcher_version: str
    match_candidate_ids: tuple[str, ...]
    match_reason: str
    probability_source: str
    probability_1: float
    probability_x: float
    probability_2: float
    eligible_bookmaker_count: int
    odds_age_hours: float | None
    fallback_reason: str | None
    payload_hash: str
    match_orientation: str = "none"
    bookmaker_quotes: tuple[ExternalBookmakerQuoteRecord, ...] = ()
    provider_starts_at: str | None = None
    effective_starts_at: str | None = None
    effective_start_source: str = "unresolved"
    provider_event_source_endpoint: str | None = None
    provider_event_request_fingerprint: str | None = None
    target_bk_probability_1: float | None = None
    target_bk_probability_x: float | None = None
    target_bk_probability_2: float | None = None


@dataclass(frozen=True)
class ExternalCollectionSnapshot:
    collection_id: str
    drawing_id: int
    drawing_number: int | None
    provider: str
    fetched_at: str
    target_fetched_at: str
    deadline: str
    event_count: int
    requests_made: int
    cache_hits: int
    daily_limit: int | None
    daily_remaining: int | None
    minute_remaining: int | None
    status: str
    events: tuple[ExternalEventDispositionRecord, ...]
    target_fingerprint: str = ""
    missing_start_horizon_days: int = 2
    requested_schedule_dates: tuple[ScheduleDateResult, ...] = ()
    successful_schedule_dates: tuple[ScheduleDateResult, ...] = ()
    failed_schedule_dates: tuple[ScheduleDateResult, ...] = ()
    eligibility: DrawingEligibility = _UNKNOWN_ELIGIBILITY
    pinned_revalidation: PinnedRevalidationSummary | None = None
    quota_limit: int | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    quota_last_cost: int | None = None


@dataclass(frozen=True)
class _MatchedTarget:
    decision: MatchDecision
    provider_event: ProviderEvent | None
    fallback_reason: str | None = None
    reviewed_start: datetime | None = None


@dataclass(frozen=True)
class _MarketFetchResult:
    markets: tuple[ProviderMarket, ...]
    fallback_reason: str | None


@dataclass(frozen=True)
class _ScheduleFetchResult:
    schedule_dates: tuple[ScheduleDateResult, ...]
    quota_exhausted: bool
    safety_stopped: bool


def build_external_collection(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    aliases: dict[str, str],
    missing_start_horizon_days: int = 2,
    *,
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None = None,
    reviewed_schedule_catalog: str | None = None,
    schedule_evidence_ledger: ScheduleEvidenceLedger | None = None,
    stop_at: datetime | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ExternalCollectionSnapshot:
    _validate_missing_start_horizon_days(missing_start_horizon_days)
    _validate_safety_boundary(stop_at, now)
    _bind_provider_safety_boundary(provider, stop_at=stop_at, now=now)
    request_counter = _RequestCounter(provider, stop_at=stop_at, now=now)
    provider_name = provider.provider_name
    matcher_version = (
        "the-odds-api-v1"
        if provider_name == "the-odds-api"
        else MATCHER_VERSION
    )
    observed_at = now()
    schedule_fetch = _fetch_schedules(
        target,
        request_counter,
        missing_start_horizon_days,
        prepared_pins=prepared_pins,
    )
    schedule_results = schedule_fetch.schedule_dates
    decisions = _match_targets(
        target,
        schedule_results,
        aliases,
        prepared_pins=prepared_pins,
        observed_at=observed_at,
        reviewed_schedule_catalog=reviewed_schedule_catalog,
        schedule_evidence_ledger=schedule_evidence_ledger,
        matcher_version=matcher_version,
    )
    pinned_revalidation = (
        _pinned_revalidation_summary(
            target,
            schedule_results,
            decisions,
            prepared_pins,
            observed_at=observed_at,
        )
        if prepared_pins is not None
        else None
    )

    market_cache: dict[tuple[Sport, str], tuple[ProviderMarket, ...]] = {}
    quota_stopped = schedule_fetch.quota_exhausted
    safety_stopped = schedule_fetch.safety_stopped
    market_results: dict[int, _MarketFetchResult] = {}
    prepared_by_order = (
        {}
        if prepared_pins is None
        else {pin.event_order: pin for pin in prepared_pins}
    )
    for event in target.events:
        matched_target = decisions[event.event_order]
        decision = matched_target.decision
        prepared_pin = prepared_by_order.get(event.event_order)
        if prepared_pin is not None and prepared_pin.schedule_only:
            market_results[event.event_order] = _MarketFetchResult(
                markets=(),
                fallback_reason=(
                    "reviewed schedule-only identity; TotoBrief BK fallback"
                ),
            )
            continue
        if safety_stopped or request_counter.safety_stop_reached():
            safety_stopped = True
            market_results[event.event_order] = _MarketFetchResult(
                markets=(),
                fallback_reason=SAFETY_STOP_FALLBACK,
            )
            continue
        if decision.status != "matched" or decision.provider_event_id is None:
            market_results[event.event_order] = _MarketFetchResult(
                markets=(),
                fallback_reason=matched_target.fallback_reason or decision.reason,
            )
            continue
        if quota_stopped:
            market_results[event.event_order] = _MarketFetchResult(
                markets=(),
                fallback_reason="quota reserve reached",
            )
            continue

        market_key = (event.sport, decision.provider_event_id)
        if market_key in market_cache:
            markets = market_cache[market_key]
        else:
            try:
                markets = request_counter.fetch_event_markets(
                    event.sport,
                    decision.provider_event_id,
                )
            except SafetyStopReached:
                safety_stopped = True
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason=SAFETY_STOP_FALLBACK,
                )
                continue
            except QuotaExhausted as error:
                quota_stopped = True
                reason = "quota reserve reached"
                if error.diagnostic is not None:
                    reason = f"{reason}: {error}"
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason=reason,
                )
                continue
            except APISportsError as error:
                reason = f"provider odds failure: {error}"
                if error.diagnostic is not None:
                    reason = f"{reason}: {error.diagnostic.summary()}"
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason=reason,
                )
                continue
            except Exception as error:
                reason = f"provider odds failure: {error.__class__.__name__}"
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason=reason,
                )
                continue
            market_cache[market_key] = markets
        market_results[event.event_order] = _MarketFetchResult(
            markets=markets,
            fallback_reason=None,
        )

    observed_at = _external_observed_at(target, decisions, market_results)
    rows: list[ExternalEventDispositionRecord] = []
    for event in target.events:
        matched_target = decisions[event.event_order]
        decision = matched_target.decision
        provider_event = matched_target.provider_event
        market_result = market_results[event.event_order]
        if market_result.fallback_reason is not None:
            rows.append(
                _fallback_disposition(
                    event,
                    decision,
                    provider_event,
                    market_result.fallback_reason,
                    reviewed_start=matched_target.reviewed_start,
                )
            )
            continue
        consensus = build_consensus(
            event,
            market_result.markets,
            observed_at,
            minimum_bookmakers=CONSENSUS_MINIMUM_BOOKMAKERS,
            maximum_age=MAXIMUM_ODDS_AGE,
        )
        rows.append(
            _consensus_disposition(
                event,
                decision,
                provider_event,
                consensus,
                observed_at,
                reviewed_start=matched_target.reviewed_start,
            )
        )

    ordered_rows = tuple(sorted(rows, key=lambda row: row.event_order))
    status = "complete" if len(ordered_rows) == 15 else "partial"
    quota = provider.quota_state
    credit_state = getattr(provider, "credit_state", None)
    quota_limit = (
        getattr(credit_state, "limit", None)
        if provider_name == "the-odds-api"
        else None
    )
    quota_remaining = (
        getattr(credit_state, "remaining", None)
        if provider_name == "the-odds-api"
        else None
    )
    quota_used = (
        getattr(credit_state, "used", None)
        if provider_name == "the-odds-api"
        else None
    )
    quota_last_cost = (
        getattr(credit_state, "last_cost", None)
        if provider_name == "the-odds-api"
        else None
    )
    target_identity = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    eligibility = classify_drawing_eligibility(
        tuple(
            _effective_event_start(
                event,
                decisions[event.event_order].provider_event,
                reviewed_start=decisions[event.event_order].reviewed_start,
            )
            for event in target.events
        )
    )
    successful_schedule_dates = tuple(
        result for result in schedule_results if result.error is None
    )
    failed_schedule_dates = tuple(
        result for result in schedule_results if result.error is not None
    )
    body = _collection_identity_payload(
        target=target,
        provider=provider_name,
        observed_at=observed_at,
        events=ordered_rows,
        requests_made=request_counter.requests_made,
        cache_hits=request_counter.cache_hits,
        daily_limit=quota.daily_limit,
        daily_remaining=quota.daily_remaining,
        minute_remaining=quota.minute_remaining,
        quota_limit=quota_limit,
        quota_remaining=quota_remaining,
        quota_used=quota_used,
        quota_last_cost=quota_last_cost,
        target_fingerprint_value=target_identity,
        missing_start_horizon_days=missing_start_horizon_days,
        requested_schedule_dates=schedule_results,
        successful_schedule_dates=successful_schedule_dates,
        failed_schedule_dates=failed_schedule_dates,
        eligibility=eligibility,
        pinned_revalidation=pinned_revalidation,
    )
    collection_id = _hash_payload(body)
    return ExternalCollectionSnapshot(
        collection_id=collection_id,
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider=provider_name,
        fetched_at=_iso_datetime(observed_at),
        target_fetched_at=_iso_datetime(target.fetched_at),
        deadline=_iso_datetime(target.deadline),
        event_count=len(ordered_rows),
        requests_made=request_counter.requests_made,
        cache_hits=request_counter.cache_hits,
        daily_limit=quota.daily_limit,
        daily_remaining=quota.daily_remaining,
        minute_remaining=quota.minute_remaining,
        status=status,
        events=ordered_rows,
        target_fingerprint=target_identity,
        missing_start_horizon_days=missing_start_horizon_days,
        requested_schedule_dates=schedule_results,
        successful_schedule_dates=successful_schedule_dates,
        failed_schedule_dates=failed_schedule_dates,
        eligibility=eligibility,
        pinned_revalidation=pinned_revalidation,
        quota_limit=quota_limit,
        quota_remaining=quota_remaining,
        quota_used=quota_used,
        quota_last_cost=quota_last_cost,
    )


def collect_open_external_odds(
    totobrief_client: Any,
    provider: ExternalOddsProvider,
    session_factory: Any,
    aliases: dict[str, str],
    fetched_at: datetime,
) -> ExternalCollectionSnapshot:
    target = resolve_open_target(totobrief_client, fetched_at)
    return collect_target_external_odds(
        target,
        provider,
        session_factory,
        aliases,
    )


def resolve_open_target(
    totobrief_client: Any,
    fetched_at: datetime,
) -> TargetDrawing:
    reference = resolve_open_drawing_from_api(totobrief_client)
    payload = totobrief_client.drawing_info(reference.drawing_id)
    target = parse_target_drawing(payload, fetched_at=fetched_at)
    if target.drawing_id != reference.drawing_id:
        raise ValueError("drawing-info id does not match resolved drawing")
    return target


def collect_target_external_odds(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    session_factory: Any,
    aliases: dict[str, str],
) -> ExternalCollectionSnapshot:
    result = build_external_collection(target, provider, aliases)
    if len(result.events) != 15:
        raise ValueError("external collection must contain exactly 15 dispositions")
    from toto_ai.external_odds.storage import save_collection

    save_collection(session_factory, result)
    return result


class _RequestCounter:
    def __init__(
        self,
        provider: ExternalOddsProvider,
        *,
        stop_at: datetime | None,
        now: Callable[[], datetime],
    ) -> None:
        self.provider = provider
        self.requests_made = 0
        self.cache_hits = 0
        self._stop_at = stop_at
        self._now = now

    def safety_stop_reached(self) -> bool:
        if self._stop_at is None:
            return False
        current = self._now()
        _require_utc_datetime("now", current)
        return current >= self._stop_at

    def _raise_if_safety_stopped(self) -> None:
        if self.safety_stop_reached():
            raise SafetyStopReached("external collection safety stop reached")

    def fetch_schedule(
        self,
        sport: Sport,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        self._raise_if_safety_stopped()
        before_requests = _provider_counter(self.provider, "requests_made")
        before_cache_hits = _provider_counter(self.provider, "cache_hits")
        try:
            result = self.provider.fetch_schedule(sport, dates)
        except Exception:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=max(1, len(dates)),
            )
            self._raise_if_safety_stopped()
            raise
        else:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=max(1, len(dates)),
            )
            self._raise_if_safety_stopped()
            return result

    def fetch_event_markets(
        self,
        sport: Sport,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        self._raise_if_safety_stopped()
        before_requests = _provider_counter(self.provider, "requests_made")
        before_cache_hits = _provider_counter(self.provider, "cache_hits")
        try:
            result = self.provider.fetch_event_markets(sport, provider_event_id)
        except Exception:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=1,
            )
            self._raise_if_safety_stopped()
            raise
        else:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=1,
            )
            self._raise_if_safety_stopped()
            return result

    def _sync_provider_counts(
        self,
        *,
        before_requests: int | None,
        before_cache_hits: int | None,
        fallback_requests: int,
    ) -> None:
        after_requests = _provider_counter(self.provider, "requests_made")
        if before_requests is not None and after_requests is not None:
            self.requests_made += max(0, after_requests - before_requests)
        else:
            self.requests_made += fallback_requests

        after_cache_hits = _provider_counter(self.provider, "cache_hits")
        if before_cache_hits is not None and after_cache_hits is not None:
            self.cache_hits += max(0, after_cache_hits - before_cache_hits)


def _provider_counter(provider: ExternalOddsProvider, name: str) -> int | None:
    value = getattr(provider, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _provider_diagnostic_count(provider: ExternalOddsProvider) -> int:
    diagnostics = getattr(provider, "request_diagnostics", ())
    if not isinstance(diagnostics, tuple):
        return 0
    return len(diagnostics)


def _provider_attempt_payloads(
    provider: ExternalOddsProvider,
    *,
    offset: int = 0,
    error: BaseException | None = None,
) -> tuple[dict[str, object], ...]:
    diagnostics = getattr(provider, "request_diagnostics", ())
    payloads: list[dict[str, object]] = []
    if isinstance(diagnostics, tuple):
        payloads.extend(
            item.payload()
            for item in diagnostics[offset:]
            if isinstance(item, APISportsDiagnostic)
        )
    error_payload = None if error is None else diagnostic_payload(error)
    if error_payload is not None and error_payload not in payloads:
        payloads.append(error_payload)
    return tuple(payloads)


def _fetch_schedules(
    target: TargetDrawing,
    request_counter: _RequestCounter,
    missing_start_horizon_days: int,
    *,
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None = None,
) -> _ScheduleFetchResult:
    required_dates: dict[Sport, set[date]] = defaultdict(set)
    if prepared_pins is not None:
        if len(prepared_pins) != 15:
            raise ValueError("prepared pins must contain exactly 15 events")
        for event, pin in zip(target.events, prepared_pins, strict=True):
            if pin.effective_source_provider in _PIN_SOURCES_WITHOUT_LIVE_SCHEDULE:
                continue
            starts_at = _event_datetime(pin.starts_at)
            if starts_at is None:
                raise ValueError("prepared pin must contain starts_at")
            required_dates[event.sport].add(starts_at.date())
    else:
        for event in target.events:
            if event.sport in {"football", "hockey"}:
                if event.starts_at is not None:
                    required_dates[event.sport].add(
                        event.starts_at.astimezone(timezone.utc).date()
                    )
                else:
                    required_dates[event.sport].update(
                        _missing_start_request_dates(
                            target.deadline,
                            missing_start_horizon_days,
                        )
                    )

    requested = tuple(
        (sport, requested_date)
        for sport in sorted(required_dates)
        for requested_date in sorted(required_dates[sport])
    )
    results: list[ScheduleDateResult] = []
    quota_stopped = False
    safety_stopped = False
    for sport, requested_date in requested:
        if safety_stopped or request_counter.safety_stop_reached():
            safety_stopped = True
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error=SAFETY_STOP_FALLBACK,
                )
            )
            continue
        if quota_stopped:
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error="quota reserve reached",
                )
            )
            continue
        diagnostic_offset = _provider_diagnostic_count(request_counter.provider)
        try:
            events = request_counter.fetch_schedule(sport, (requested_date,))
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=events,
                    error=None,
                    provider_attempts=_provider_attempt_payloads(
                        request_counter.provider,
                        offset=diagnostic_offset,
                    ),
                )
            )
        except SafetyStopReached as error:
            safety_stopped = True
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error=SAFETY_STOP_FALLBACK,
                    provider_attempts=_provider_attempt_payloads(
                        request_counter.provider,
                        offset=diagnostic_offset,
                        error=error,
                    ),
                )
            )
        except QuotaExhausted as error:
            quota_stopped = True
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error="quota reserve reached",
                    provider_attempts=_provider_attempt_payloads(
                        request_counter.provider,
                        offset=diagnostic_offset,
                        error=error,
                    ),
                )
            )
        except Exception as error:
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error="provider schedule failure",
                    provider_attempts=_provider_attempt_payloads(
                        request_counter.provider,
                        offset=diagnostic_offset,
                        error=error,
                    ),
                )
            )
    return _ScheduleFetchResult(
        schedule_dates=tuple(results),
        quota_exhausted=quota_stopped,
        safety_stopped=safety_stopped,
    )


def _match_targets(
    target: TargetDrawing,
    schedule_results: tuple[ScheduleDateResult, ...],
    aliases: dict[str, str],
    *,
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None = None,
    observed_at: datetime | None = None,
    reviewed_schedule_catalog: str | None = None,
    schedule_evidence_ledger: ScheduleEvidenceLedger | None = None,
    matcher_version: str = MATCHER_VERSION,
) -> dict[int, _MatchedTarget]:
    if prepared_pins is not None:
        if observed_at is None:
            raise ValueError("pin revalidation observation time is required")
        return _match_targets_from_pins(
            target,
            schedule_results,
            prepared_pins,
            observed_at=observed_at,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            schedule_evidence_ledger=schedule_evidence_ledger,
        )
    schedules = _successful_schedule_events(schedule_results)
    failures = {
        (result.sport, result.requested_date): result.error
        for result in schedule_results
        if result.error is not None
    }
    failures_by_sport = {
        sport
        for sport, _ in failures
    }
    decisions: dict[int, _MatchedTarget] = {}
    for event in target.events:
        if event.sport not in {"football", "hockey"}:
            decision = match_event(
                event,
                (),
                aliases,
                matcher_version=matcher_version,
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        if (
            event.starts_at is not None
            and (event.sport, event.starts_at.astimezone(timezone.utc).date())
            in failures
        ):
            decisions[event.event_order] = _MatchedTarget(
                decision=MatchDecision(
                    status="provider_failure",
                    provider_event_id=None,
                    matcher_version=MATCHER_VERSION,
                    candidate_ids=(),
                    reason=failures[
                        (event.sport, event.starts_at.astimezone(timezone.utc).date())
                    ],
                ),
                provider_event=None,
            )
            continue
        decision = match_event(
            event,
            schedules.get(event.sport, ()),
            aliases,
            matcher_version=matcher_version,
        )
        fallback_reason = None
        if (
            event.starts_at is None
            and decision.status == "missing"
            and event.sport in failures_by_sport
        ):
            # Keep the precise matcher rejection in match_reason. The later
            # transport failure remains the fallback classification only.
            fallback_reason = "partial schedule"
        provider_event = _matched_provider_event(
            decision,
            schedules.get(event.sport, ()),
        )
        decisions[event.event_order] = _MatchedTarget(
            decision, provider_event, fallback_reason
        )
    return decisions


def _match_targets_from_pins(
    target: TargetDrawing,
    schedule_results: tuple[ScheduleDateResult, ...],
    pins: tuple[DrawingEventPinRecord, ...],
    *,
    observed_at: datetime,
    reviewed_schedule_catalog: str | None = None,
    schedule_evidence_ledger: ScheduleEvidenceLedger | None = None,
) -> dict[int, _MatchedTarget]:
    fingerprint = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )
    if len(pins) != 15 or tuple(pin.event_order for pin in pins) != tuple(range(15)):
        raise ValueError("prepared pins must contain event orders 0 through 14")
    schedules = _successful_schedule_events(schedule_results)
    failures = {
        (result.sport, result.requested_date): result.error
        for result in schedule_results
        if result.error is not None
    }
    decisions: dict[int, _MatchedTarget] = {}
    reviewed_results = _reviewed_pin_revalidation(
        target,
        pins,
        observed_at=observed_at,
        reviewed_schedule_catalog=reviewed_schedule_catalog,
    )
    evidence_results = _schedule_evidence_pin_revalidation(
        target,
        pins,
        observed_at=observed_at,
        schedule_evidence_ledger=schedule_evidence_ledger,
    )
    for event, pin in zip(target.events, pins, strict=True):
        if (
            pin.drawing_id != target.drawing_id
            or pin.drawing_fingerprint != fingerprint
            or pin.target_event_id != str(event.event_id)
            or pin.status != "valid"
        ):
            raise ValueError(
                "prepared pin does not match exact drawing fingerprint/event"
            )
        if pin.effective_source_provider == "totobrief-baseline":
            if (
                pin.provenance.get("reason_code")
                != "baseline_only_external_unavailable"
            ):
                raise ValueError("TotoBrief baseline source semantics changed")
            decision = MatchDecision(
                status="matched",
                provider_event_id=None,
                matcher_version="totobrief-baseline-v1",
                candidate_ids=(),
                reason="baseline_only_external_unavailable",
                orientation="same",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        pinned_start = _event_datetime(pin.starts_at)
        if pinned_start is None:
            raise ValueError("prepared pin must contain starts_at")
        if pin.effective_source_provider in {"reviewed-schedule", "schedule-evidence"}:
            if pin.effective_source_provider == "schedule-evidence":
                resolution = evidence_results.get(event.event_order)
                evidence = None if resolution is None else resolution.observation
                matched = bool(
                    resolution is not None
                    and resolution.state == "RESOLVED"
                    and evidence is not None
                    and evidence.observation_id == pin.reviewed_evidence_id
                    and evidence.starts_at == pinned_start
                    and evidence.semantic_hash
                    == pin.provenance.get("evidence_hash")
                    and resolution.orientation
                    == pin.provenance.get("orientation", "same")
                )
                if not matched:
                    raise ScheduleEvidenceIntegrityError(
                        "prepared schedule-evidence pin conflicts with the "
                        "bound ledger"
                    )
                decision = MatchDecision(
                    status="matched",
                    provider_event_id=None,
                    matcher_version="schedule-evidence-v1",
                    candidate_ids=(),
                    reason=(
                        "exact reusable schedule evidence revalidated; "
                        f"evidence={evidence.observation_id}"
                    ),
                    orientation=resolution.orientation or "same",
                )
                decisions[event.event_order] = _MatchedTarget(
                    decision,
                    None,
                    reviewed_start=pinned_start,
                )
                continue
            reviewed = reviewed_results.get(event.event_order)
            if reviewed is None or not reviewed.matched:
                decision = MatchDecision(
                    status="provider_failure",
                    provider_event_id=None,
                    matcher_version="reviewed-schedule-v1",
                    candidate_ids=(),
                    reason=(
                        "reviewed schedule revalidation failed: "
                        + (
                            "catalog unavailable"
                            if reviewed is None
                            else str(reviewed.reason)
                        )
                    ),
                )
                decisions[event.event_order] = _MatchedTarget(decision, None)
                continue
            decision = MatchDecision(
                status="matched",
                provider_event_id=None,
                matcher_version="reviewed-schedule-v1",
                candidate_ids=(),
                reason=(
                    "exact reviewed schedule evidence revalidated; "
                    f"evidence={reviewed.evidence_id}"
                ),
                orientation="same",
            )
            decisions[event.event_order] = _MatchedTarget(
                decision,
                None,
                reviewed_start=pinned_start,
            )
            continue
        failure = failures.get((event.sport, pinned_start.date()))
        if failure is not None:
            decision = MatchDecision(
                status="provider_failure",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason=f"pinned fixture revalidation unavailable: {failure}",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        candidates = tuple(
            candidate
            for candidate in schedules.get(event.sport, ())
            if candidate.provider_event_id == pin.provider_fixture_id
        )
        if len(candidates) > 1:
            raise ValueError("pinned provider fixture is not unique in schedule")
        if not candidates:
            decision = MatchDecision(
                status="missing",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason=(
                    "pinned provider fixture absent from recent schedule; "
                    "rerun prepare-drawing"
                ),
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        provider_event = candidates[0]
        if provider_event.provider != pin.provider:
            decision = MatchDecision(
                status="missing",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason="pinned fixture provider identity changed",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        orientation = str(pin.provenance.get("orientation", "same"))
        if orientation not in {"same", "reversed"}:
            decision = MatchDecision(
                status="missing",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason="prepared pin orientation is invalid",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        if not _pin_team_ids_match(provider_event, pin):
            decision = MatchDecision(
                status="missing",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason="pinned provider team IDs changed",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        if abs(provider_event.starts_at - pinned_start) > PIN_START_TIME_TOLERANCE:
            decision = MatchDecision(
                status="missing",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason="pinned provider fixture start changed; rerun prepare-drawing",
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        if (
            provider_event.fetched_at > observed_at + timedelta(minutes=5)
            or observed_at - provider_event.fetched_at > PIN_SCHEDULE_MAX_AGE
        ):
            decision = MatchDecision(
                status="provider_failure",
                provider_event_id=None,
                matcher_version="systematic-team-pin-v1",
                candidate_ids=(pin.provider_fixture_id,),
                reason=(
                    "pinned fixture revalidation schedule is stale; "
                    "refresh schedule cache"
                ),
            )
            decisions[event.event_order] = _MatchedTarget(decision, None)
            continue
        decision = MatchDecision(
            status="matched",
            provider_event_id=pin.provider_fixture_id,
            matcher_version="systematic-team-pin-v1",
            candidate_ids=(pin.provider_fixture_id,),
            reason="exact valid drawing pin; name rematching bypassed",
            orientation=orientation,  # type: ignore[arg-type]
        )
        decisions[event.event_order] = _MatchedTarget(decision, provider_event)
    return decisions


def _schedule_evidence_pin_revalidation(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    *,
    observed_at: datetime,
    schedule_evidence_ledger: ScheduleEvidenceLedger | None,
) -> dict[int, Any]:
    evidence_pins = tuple(
        pin for pin in pins if pin.effective_source_provider == "schedule-evidence"
    )
    if not evidence_pins:
        return {}
    if schedule_evidence_ledger is None:
        raise ScheduleEvidenceIntegrityError(
            "schedule-evidence pins require the bound ledger"
        )
    if any(
        not isinstance(pin.provenance, dict)
        or pin.provenance.get("ledger_hash")
        != schedule_evidence_ledger.semantic_hash
        for pin in evidence_pins
    ):
        raise ScheduleEvidenceIntegrityError(
            "prepared schedule-evidence pin ledger hash conflicts with the "
            "bound ledger"
        )
    return {
        event.event_order: resolve_schedule_evidence(
            event,
            schedule_evidence_ledger,
            evaluated_at=observed_at,
        )
        for event, pin in zip(target.events, pins, strict=True)
        if pin.effective_source_provider == "schedule-evidence"
    }


def _reviewed_pin_revalidation(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    *,
    observed_at: datetime,
    reviewed_schedule_catalog: str | None,
) -> dict[int, Any]:
    reviewed = tuple(
        pin
        for pin in pins
        if pin.effective_source_provider == "reviewed-schedule"
    )
    if not reviewed:
        return {}
    if reviewed_schedule_catalog is None:
        return {}
    hashes = {
        pin.provenance.get("catalog_hash")
        for pin in reviewed
        if isinstance(pin.provenance, dict)
    }
    if len(hashes) != 1 or not isinstance(next(iter(hashes)), str):
        return {}
    expected_hash = next(iter(hashes))
    source = ReviewedCatalogScheduleSource(
        Path(reviewed_schedule_catalog),
        expected_catalog_hash=expected_hash,
    )
    return {
        item.event_order: item
        for item in source.revalidate_pins(
            reviewed,
            target=target,
            evaluated_at=observed_at,
        )
    }


def _pin_team_ids_match(
    candidate: ProviderEvent, pin: DrawingEventPinRecord
) -> bool:
    if (
        candidate.provider_home_team_id is None
        or candidate.provider_away_team_id is None
    ):
        return False
    orientation = pin.provenance.get("orientation", "same")
    expected = (
        (pin.provider_home_team_id, pin.provider_away_team_id)
        if orientation == "same"
        else (pin.provider_away_team_id, pin.provider_home_team_id)
    )
    return (
        candidate.provider_home_team_id,
        candidate.provider_away_team_id,
    ) == expected


def pinned_revalidation_is_ready(snapshot: ExternalCollectionSnapshot) -> bool:
    summary = snapshot.pinned_revalidation
    return bool(
        summary is not None
        and summary.expected_count == 15
        and summary.matched_count == 15
        and summary.ready_for_play
    )


def _pinned_revalidation_summary(
    target: TargetDrawing,
    schedule_results: tuple[ScheduleDateResult, ...],
    decisions: dict[int, _MatchedTarget],
    pins: tuple[DrawingEventPinRecord, ...],
    *,
    observed_at: datetime,
) -> PinnedRevalidationSummary:
    results = tuple(
        PinnedRevalidationEvent(
            event_order=event.event_order,
            status=decisions[event.event_order].decision.status,
            reason=decisions[event.event_order].decision.reason,
            source_provider=pins[event.event_order].effective_source_provider,
            revalidation_method=(
                "totobrief-baseline-v1"
                if pins[event.event_order].effective_source_provider
                == "totobrief-baseline"
                else "schedule-evidence-v1"
                if pins[event.event_order].effective_source_provider
                == "schedule-evidence"
                else (
                    "reviewed-catalog-v1"
                    if pins[event.event_order].effective_source_provider
                    == "reviewed-schedule"
                    else "api-sports-fixture-v1"
                )
            ),
            evidence_id=pins[event.event_order].reviewed_evidence_id,
            evidence_hash=(
                pins[event.event_order].provenance.get("evidence_hash")
                if pins[event.event_order].effective_source_provider
                in {"reviewed-schedule", "schedule-evidence"}
                else (
                    pins[event.event_order].provenance.get(
                        "baseline_probability_input_sha256"
                    )
                    if pins[event.event_order].effective_source_provider
                    == "totobrief-baseline"
                    else pins[event.event_order].provenance.get(
                    "provider_payload_hash"
                    )
                )
            ),
        )
        for event in target.events
    )
    matched = tuple(item.event_order for item in results if item.status == "matched")
    missing = tuple(item.event_order for item in results if item.status == "missing")
    provider_failures = tuple(
        item.event_order for item in results if item.status == "provider_failure"
    )
    stale = _orders_with_reason(results, "schedule is stale")
    date_failures = _orders_with_reason(results, "revalidation unavailable")
    provider_failures_by_identity = _orders_with_reason(
        results, "provider identity changed"
    )
    fixture_failures = _orders_with_reason(
        results, "fixture absent from recent schedule"
    )
    team_failures = _orders_with_reason(results, "team IDs changed")
    orientation_failures = _orders_with_reason(results, "orientation is invalid")
    start_failures = _orders_with_reason(results, "fixture start changed")
    identity_failures = tuple(
        sorted(
            set(provider_failures_by_identity)
            | set(fixture_failures)
            | set(team_failures)
            | set(orientation_failures)
        )
    )
    failed_dates = tuple(
        f"{item.sport}:{item.requested_date.isoformat()}:{item.error}"
        for item in schedule_results
        if item.error is not None
    )
    live_schedule_pins = tuple(
        pin
        for pin in pins
        if pin.effective_source_provider not in _PIN_SOURCES_WITHOUT_LIVE_SCHEDULE
    )
    pin_ids = {
        pin.provider_fixture_id
        for pin in live_schedule_pins
        if pin.provider_fixture_id is not None
    }
    fetched_at = tuple(
        event.fetched_at
        for result in schedule_results
        if result.error is None
        for event in result.events
        if event.provider_event_id in pin_ids
    )
    oldest = min(fetched_at) if fetched_at else None
    newest = max(fetched_at) if fetched_at else None
    maximum_age = (
        None
        if oldest is None
        else max(0.0, (observed_at - oldest).total_seconds())
    )
    matched_count = len(matched)
    required_dates_complete = not failed_dates
    live_schedule_count = len(live_schedule_pins)
    schedule_fresh = (
        matched_count == 15
        and not stale
        and (oldest is not None or live_schedule_count == 0)
    )
    provider_checks_passed = matched_count == 15 and not provider_failures_by_identity
    fixture_checks_passed = matched_count == 15 and not fixture_failures
    team_checks_passed = matched_count == 15 and not team_failures
    orientation_checks_passed = matched_count == 15 and not orientation_failures
    start_time_checks_passed = matched_count == 15 and not start_failures
    ready = all(
        (
            matched_count == 15,
            required_dates_complete,
            schedule_fresh,
            provider_checks_passed,
            fixture_checks_passed,
            team_checks_passed,
            orientation_checks_passed,
            start_time_checks_passed,
        )
    )
    return PinnedRevalidationSummary(
        expected_count=15,
        matched_count=matched_count,
        missing_event_orders=missing,
        provider_failure_event_orders=provider_failures,
        stale_event_orders=stale,
        date_failure_event_orders=date_failures,
        identity_failure_event_orders=identity_failures,
        start_time_failure_event_orders=start_failures,
        failed_schedule_dates=failed_dates,
        oldest_schedule_fetched_at=(None if oldest is None else _iso_datetime(oldest)),
        newest_schedule_fetched_at=(None if newest is None else _iso_datetime(newest)),
        maximum_schedule_age_seconds=maximum_age,
        schedule_fresh=schedule_fresh,
        provider_checks_passed=provider_checks_passed,
        fixture_checks_passed=fixture_checks_passed,
        team_checks_passed=team_checks_passed,
        orientation_checks_passed=orientation_checks_passed,
        start_time_checks_passed=start_time_checks_passed,
        required_dates_complete=required_dates_complete,
        ready_for_play=ready,
        events=results,
    )


def _orders_with_reason(
    events: tuple[PinnedRevalidationEvent, ...], fragment: str
) -> tuple[int, ...]:
    return tuple(item.event_order for item in events if fragment in item.reason)


def _event_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("prepared pin datetime is invalid") from error
    else:
        raise ValueError("prepared pin datetime is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("prepared pin datetime must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _successful_schedule_events(
    schedule_results: tuple[ScheduleDateResult, ...],
) -> dict[Sport, tuple[ProviderEvent, ...]]:
    events_by_sport: dict[Sport, dict[str, ProviderEvent]] = defaultdict(dict)
    for result in schedule_results:
        if result.error is not None:
            continue
        for event in result.events:
            events_by_sport[result.sport].setdefault(event.provider_event_id, event)
    return {
        sport: tuple(
            events_by_sport[sport][event_id]
            for event_id in sorted(events_by_sport[sport])
        )
        for sport in events_by_sport
    }


def _matched_provider_event(
    decision: MatchDecision,
    candidates: tuple[ProviderEvent, ...],
) -> ProviderEvent | None:
    if decision.status != "matched" or decision.provider_event_id is None:
        return None
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.provider_event_id == decision.provider_event_id
    )
    if len(matches) != 1:
        raise ValueError("matched provider event id must resolve uniquely")
    return matches[0]


def _fallback_disposition(
    event: TargetEvent,
    decision: MatchDecision,
    provider_event: ProviderEvent | None,
    reason: str,
    *,
    reviewed_start: datetime | None = None,
) -> ExternalEventDispositionRecord:
    payload = _event_payload(
        event=event,
        decision=decision,
        provider_event=provider_event,
        probability_source=TOTOBRIEF_BK_FALLBACK,
        probabilities=event.bk_probabilities,
        eligible_bookmaker_count=0,
        odds_age_hours=None,
        fallback_reason=reason,
        quotes=(),
        reviewed_start=reviewed_start,
    )
    return _event_record(
        event=event,
        decision=decision,
        provider_event=provider_event,
        probability_source=TOTOBRIEF_BK_FALLBACK,
        probabilities=event.bk_probabilities,
        eligible_bookmaker_count=0,
        odds_age_hours=None,
        fallback_reason=reason,
        payload_hash=_hash_payload(payload),
        quotes=(),
        reviewed_start=reviewed_start,
    )


def _consensus_disposition(
    event: TargetEvent,
    decision: MatchDecision,
    provider_event: ProviderEvent | None,
    consensus: ConsensusResult,
    observed_at: datetime,
    *,
    reviewed_start: datetime | None = None,
) -> ExternalEventDispositionRecord:
    quotes = _assessment_quotes(consensus)
    if consensus.probabilities is None:
        probability_source = TOTOBRIEF_BK_FALLBACK
        probabilities = event.bk_probabilities
        fallback_reason = _consensus_fallback_reason(consensus)
    else:
        probability_source = EXTERNAL_CONSENSUS
        probabilities = _target_oriented_probabilities(
            consensus.probabilities,
            decision,
        )
        fallback_reason = None
    odds_age_hours = _odds_age_hours(consensus, observed_at)
    payload = _event_payload(
        event=event,
        decision=decision,
        provider_event=provider_event,
        probability_source=probability_source,
        probabilities=probabilities,
        eligible_bookmaker_count=consensus.eligible_bookmaker_count,
        odds_age_hours=odds_age_hours,
        fallback_reason=fallback_reason,
        quotes=quotes,
        reviewed_start=reviewed_start,
    )
    return _event_record(
        event=event,
        decision=decision,
        provider_event=provider_event,
        probability_source=probability_source,
        probabilities=probabilities,
        eligible_bookmaker_count=consensus.eligible_bookmaker_count,
        odds_age_hours=odds_age_hours,
        fallback_reason=fallback_reason,
        payload_hash=_hash_payload(payload),
        quotes=quotes,
        reviewed_start=reviewed_start,
    )


def _event_record(
    *,
    event: TargetEvent,
    decision: MatchDecision,
    provider_event: ProviderEvent | None,
    probability_source: str,
    probabilities: OutcomeTriplet,
    eligible_bookmaker_count: int,
    odds_age_hours: float | None,
    fallback_reason: str | None,
    payload_hash: str,
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
    reviewed_start: datetime | None = None,
) -> ExternalEventDispositionRecord:
    effective_start = _effective_event_start(
        event,
        provider_event,
        reviewed_start=reviewed_start,
    )
    return ExternalEventDispositionRecord(
        drawing_id=event.drawing_id,
        event_order=event.event_order,
        target_event_id=event.event_id,
        sport=event.sport,
        championship=event.championship,
        starts_at=_optional_iso_datetime(event.starts_at),
        home_team=event.home_team,
        away_team=event.away_team,
        home_team_en=event.home_team_en,
        away_team_en=event.away_team_en,
        match_status=decision.status,
        provider_event_id=decision.provider_event_id,
        provider_event_fetched_at=(
            _iso_datetime(provider_event.fetched_at)
            if provider_event is not None
            else None
        ),
        provider_event_payload_hash=(
            provider_event.payload_hash if provider_event is not None else None
        ),
        provider_event_source_endpoint=(
            provider_event.source_endpoint if provider_event is not None else None
        ),
        provider_event_request_fingerprint=(
            provider_event.request_fingerprint if provider_event is not None else None
        ),
        matcher_version=decision.matcher_version,
        match_candidate_ids=decision.candidate_ids,
        match_reason=decision.reason,
        probability_source=probability_source,
        probability_1=probabilities[0],
        probability_x=probabilities[1],
        probability_2=probabilities[2],
        eligible_bookmaker_count=eligible_bookmaker_count,
        odds_age_hours=odds_age_hours,
        fallback_reason=fallback_reason,
        payload_hash=payload_hash,
        match_orientation=decision.orientation or "none",
        bookmaker_quotes=quotes,
        provider_starts_at=(
            _iso_datetime(provider_event.starts_at)
            if provider_event is not None
            else (
                _iso_datetime(reviewed_start)
                if reviewed_start is not None
                else None
            )
        ),
        effective_starts_at=(
            _iso_datetime(effective_start.starts_at)
            if effective_start.starts_at is not None
            else None
        ),
        effective_start_source=effective_start.source,
        target_bk_probability_1=(
            event.bk_probabilities[0]
            if decision.matcher_version == "the-odds-api-v1"
            else None
        ),
        target_bk_probability_x=(
            event.bk_probabilities[1]
            if decision.matcher_version == "the-odds-api-v1"
            else None
        ),
        target_bk_probability_2=(
            event.bk_probabilities[2]
            if decision.matcher_version == "the-odds-api-v1"
            else None
        ),
    )


def _consensus_fallback_reason(consensus: ConsensusResult) -> str:
    reasons = sorted(
        {
            assessment.rejection_reason
            for assessment in consensus.assessments
            if assessment.rejection_reason is not None
        }
    )
    base = consensus.fallback_reason or "external consensus unavailable"
    if not reasons:
        return base
    return f"{base}: {', '.join(reasons)}"


def _target_oriented_probabilities(
    probabilities: OutcomeTriplet,
    decision: MatchDecision,
) -> OutcomeTriplet:
    if decision.orientation == "reversed":
        return probabilities[2], probabilities[1], probabilities[0]
    return probabilities


def _odds_age_hours(
    consensus: ConsensusResult,
    observed_at: datetime,
) -> float | None:
    assessed = tuple(assessment.market for assessment in consensus.assessments)
    if not assessed:
        return None
    oldest = max(observed_at - market.updated_at for market in assessed)
    return oldest.total_seconds() / 3600.0


def _event_payload(
    *,
    event: TargetEvent,
    decision: MatchDecision,
    provider_event: ProviderEvent | None,
    probability_source: str,
    probabilities: OutcomeTriplet,
    eligible_bookmaker_count: int,
    odds_age_hours: float | None,
    fallback_reason: str | None,
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
    reviewed_start: datetime | None = None,
) -> dict[str, object]:
    effective_start = _effective_event_start(
        event,
        provider_event,
        reviewed_start=reviewed_start,
    )
    return {
        "target": _target_event_payload(event),
        "match": {
            "status": decision.status,
            "provider_event_id": decision.provider_event_id,
            "matcher_version": decision.matcher_version,
            "candidate_ids": decision.candidate_ids,
            "reason": decision.reason,
            "orientation": decision.orientation,
        },
        "provider_event": (
            {
                "fetched_at": _iso_datetime(provider_event.fetched_at),
                "payload_hash": provider_event.payload_hash,
                "starts_at": _iso_datetime(provider_event.starts_at),
                **(
                    {
                        "source_endpoint": provider_event.source_endpoint,
                        "request_fingerprint": provider_event.request_fingerprint,
                    }
                    if provider_event.source_endpoint is not None
                    or provider_event.request_fingerprint is not None
                    else {}
                ),
            }
            if provider_event is not None
            else None
        ),
        "probability_source": probability_source,
        "probabilities": probabilities,
        "eligible_bookmaker_count": eligible_bookmaker_count,
        "odds_age_hours": odds_age_hours,
        "fallback_reason": fallback_reason,
        "quotes": tuple(_quote_identity_payload(quote) for quote in quotes),
        "effective_start": {
            "starts_at": (
                _iso_datetime(effective_start.starts_at)
                if effective_start.starts_at is not None
                else None
            ),
            "source": effective_start.source,
        },
    }


def _collection_identity_payload(
    *,
    target: TargetDrawing,
    provider: str,
    observed_at: datetime,
    events: tuple[ExternalEventDispositionRecord, ...],
    requests_made: int,
    cache_hits: int,
    daily_limit: int | None,
    daily_remaining: int | None,
    minute_remaining: int | None,
    quota_limit: int | None,
    quota_remaining: int | None,
    quota_used: int | None,
    quota_last_cost: int | None,
    target_fingerprint_value: str,
    missing_start_horizon_days: int,
    requested_schedule_dates: tuple[ScheduleDateResult, ...],
    successful_schedule_dates: tuple[ScheduleDateResult, ...],
    failed_schedule_dates: tuple[ScheduleDateResult, ...],
    eligibility: DrawingEligibility,
    pinned_revalidation: PinnedRevalidationSummary | None,
) -> dict[str, object]:
    return {
        "drawing": {
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "deadline": _iso_datetime(target.deadline),
            "target_fetched_at": _iso_datetime(target.fetched_at),
            "external_observed_at": _iso_datetime(observed_at),
        },
        "provider": provider,
        "operational_provenance": {
            "requests_made": requests_made,
            "cache_hits": cache_hits,
            "daily_limit": daily_limit,
            "daily_remaining": daily_remaining,
            "minute_remaining": minute_remaining,
        }
        | (
            {
                "quota_limit": quota_limit,
                "quota_remaining": quota_remaining,
                "quota_used": quota_used,
                "quota_last_cost": quota_last_cost,
            }
            if provider == "the-odds-api"
            else {}
        ),
        "target_fingerprint": target_fingerprint_value,
        "missing_start_horizon_days": missing_start_horizon_days,
        "schedule_dates": {
            "requested": _schedule_date_payload(requested_schedule_dates),
            "successful": _schedule_date_payload(successful_schedule_dates),
            "failed": _schedule_date_payload(failed_schedule_dates),
        },
        "eligibility": {
            "status": eligibility.status,
            "earliest_start": _optional_datetime_or_none(eligibility.earliest_start),
            "latest_start": _optional_datetime_or_none(eligibility.latest_start),
            "span_days": eligibility.span_days,
            "missing_event_orders": eligibility.missing_event_orders,
            "totobrief_count": eligibility.totobrief_count,
            "provider_count": eligibility.provider_count,
        },
        "pinned_revalidation": (
            None if pinned_revalidation is None else asdict(pinned_revalidation)
        ),
        "target_payload": tuple(
            _target_event_payload(event) for event in target.events
        ),
        "events": tuple(
            {
                key: value
                for key, value in event.__dict__.items()
                if key != "bookmaker_quotes"
                and not (
                    key
                    in {
                        "provider_event_source_endpoint",
                        "provider_event_request_fingerprint",
                        "target_bk_probability_1",
                        "target_bk_probability_x",
                        "target_bk_probability_2",
                    }
                    and value is None
                )
            }
            | {
                "bookmaker_quotes": tuple(
                    _quote_identity_payload(quote)
                    for quote in _canonical_quotes(event.bookmaker_quotes)
                )
            }
            for event in events
        ),
        "consensus": {
            "minimum_bookmakers": CONSENSUS_MINIMUM_BOOKMAKERS,
            "maximum_odds_age_seconds": int(MAXIMUM_ODDS_AGE.total_seconds()),
        },
    }


def _schedule_date_payload(
    schedule_dates: tuple[ScheduleDateResult, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        (
            {
                "sport": result.sport,
                "requested_date": result.requested_date.isoformat(),
                "error": result.error,
            }
            | (
                {"provider_attempts": result.provider_attempts}
                if result.provider_attempts
                else {}
            )
        )
        for result in sorted(
            schedule_dates,
            key=lambda result: (result.sport, result.requested_date),
        )
    )


def _target_event_payload(event: TargetEvent) -> dict[str, object]:
    return {
        "drawing_id": event.drawing_id,
        "drawing_number": event.drawing_number,
        "event_id": event.event_id,
        "event_order": event.event_order,
        "sport": event.sport,
        "championship": event.championship,
        "starts_at": _optional_iso_datetime(event.starts_at),
        "deadline": _iso_datetime(event.deadline),
        "home_team": event.home_team,
        "away_team": event.away_team,
        "home_team_en": event.home_team_en,
        "away_team_en": event.away_team_en,
        "bk_probabilities": event.bk_probabilities,
    }


def _hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _assessment_quotes(
    consensus: ConsensusResult,
) -> tuple[ExternalBookmakerQuoteRecord, ...]:
    grouped = defaultdict(list)
    for assessment in consensus.assessments:
        grouped[
            (assessment.market.bookmaker_id, assessment.market.market_name)
        ].append(assessment)

    quotes = []
    for assessments in grouped.values():
        provenance = _canonical_market_provenance(
            tuple(_market_provenance(item.market) for item in assessments)
        )
        if len(assessments) == 1:
            assessment = assessments[0]
            market = assessment.market
            quotes.append(
                ExternalBookmakerQuoteRecord(
                    bookmaker_id=market.bookmaker_id,
                    market_name=market.market_name,
                    updated_at=_iso_datetime(market.updated_at),
                    fetched_at=_iso_datetime(market.fetched_at),
                    payload_hash=market.payload_hash,
                    home_price=market.home_price,
                    draw_price=market.draw_price,
                    away_price=market.away_price,
                    eligible=1 if assessment.eligible else 0,
                    rejection_reason=assessment.rejection_reason,
                    source_count=1,
                    source_provenance=provenance,
                )
            )
            continue

        quotes.append(
            ExternalBookmakerQuoteRecord(
                bookmaker_id=assessments[0].market.bookmaker_id,
                market_name=assessments[0].market.market_name,
                updated_at=max(source.updated_at for source in provenance),
                fetched_at=max(source.fetched_at for source in provenance),
                payload_hash=_hash_payload(
                    {
                        "duplicate_market_provenance": tuple(
                            _market_provenance_identity_payload(source)
                            for source in provenance
                        )
                    }
                ),
                home_price=None,
                draw_price=None,
                away_price=None,
                eligible=0,
                rejection_reason="duplicate bookmaker market",
                source_count=len(provenance),
                source_provenance=provenance,
            )
        )
    return _canonical_quotes(tuple(quotes))


def _market_provenance(market: ProviderMarket) -> ExternalMarketProvenanceRecord:
    return ExternalMarketProvenanceRecord(
        updated_at=_iso_datetime(market.updated_at),
        fetched_at=_iso_datetime(market.fetched_at),
        payload_hash=market.payload_hash,
        home_price=market.home_price,
        draw_price=market.draw_price,
        away_price=market.away_price,
        source_endpoint=market.source_endpoint,
        request_fingerprint=market.request_fingerprint,
    )


def _market_provenance_identity_payload(
    source: ExternalMarketProvenanceRecord,
) -> dict[str, object]:
    payload = asdict(source)
    return {
        key: value
        for key, value in payload.items()
        if key not in {"source_endpoint", "request_fingerprint"} or value is not None
    }


def _quote_identity_payload(
    quote: ExternalBookmakerQuoteRecord,
) -> dict[str, object]:
    payload = {
        key: value
        for key, value in asdict(quote).items()
        if key != "source_provenance"
    }
    payload["source_provenance"] = tuple(
        _market_provenance_identity_payload(source)
        for source in quote.source_provenance
    )
    return payload


def _canonical_market_provenance(
    provenance: tuple[ExternalMarketProvenanceRecord, ...],
) -> tuple[ExternalMarketProvenanceRecord, ...]:
    return tuple(
        sorted(
            provenance,
            key=lambda source: json.dumps(
                asdict(source),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    )


def _canonical_quotes(
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
) -> tuple[ExternalBookmakerQuoteRecord, ...]:
    return tuple(sorted(quotes, key=_quote_sort_key))


def _quote_sort_key(quote: ExternalBookmakerQuoteRecord) -> tuple[str, str, str]:
    return (
        quote.bookmaker_id,
        quote.market_name,
        json.dumps(
            asdict(quote),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _optional_iso_datetime(value: datetime | None) -> str:
    return "" if value is None else _iso_datetime(value)


def _optional_datetime_or_none(value: datetime | None) -> str | None:
    return None if value is None else _iso_datetime(value)


def _validate_safety_boundary(
    stop_at: datetime | None,
    now: Callable[[], datetime],
) -> None:
    if not callable(now):
        raise ValueError("now must be callable")
    if stop_at is not None:
        _require_utc_datetime("stop_at", stop_at)


def _bind_provider_safety_boundary(
    provider: ExternalOddsProvider,
    *,
    stop_at: datetime | None,
    now: Callable[[], datetime],
) -> None:
    bind = getattr(provider, "bind_safety_boundary", None)
    if bind is not None:
        if not callable(bind):
            raise ValueError("provider safety boundary binder must be callable")
        bind(stop_at=stop_at, now=now)


def _require_utc_datetime(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _validate_missing_start_horizon_days(value: int) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= 5
    ):
        raise ValueError(
            "missing_start_horizon_days must be an integer from 1 through 5"
        )


def _missing_start_request_dates(
    deadline: datetime,
    missing_start_horizon_days: int,
) -> tuple[date, ...]:
    local_deadline_date = deadline.astimezone(_MOSCOW).date()
    local_horizon_start = datetime.combine(
        local_deadline_date,
        datetime.min.time(),
        tzinfo=_MOSCOW,
    )
    local_horizon_end = local_horizon_start + timedelta(
        days=missing_start_horizon_days
    )
    first_utc_date = local_horizon_start.astimezone(timezone.utc).date()
    last_utc_date = (
        local_horizon_end - timedelta(microseconds=1)
    ).astimezone(timezone.utc).date()
    return tuple(
        first_utc_date + timedelta(days=offset)
        for offset in range((last_utc_date - first_utc_date).days + 1)
    )


def _effective_event_start(
    event: TargetEvent,
    provider_event: ProviderEvent | None,
    *,
    reviewed_start: datetime | None = None,
) -> EffectiveEventStart:
    if event.starts_at is not None:
        return EffectiveEventStart(
            event_order=event.event_order,
            starts_at=event.starts_at,
            source="totobrief",
        )
    if provider_event is not None:
        return EffectiveEventStart(
            event_order=event.event_order,
            starts_at=provider_event.starts_at,
            source="provider",
        )
    if reviewed_start is not None:
        return EffectiveEventStart(
            event_order=event.event_order,
            starts_at=reviewed_start,
            source="provider",
        )
    return EffectiveEventStart(
        event_order=event.event_order,
        starts_at=None,
        source="unresolved",
    )


def _external_observed_at(
    target: TargetDrawing,
    decisions: dict[int, _MatchedTarget],
    market_results: dict[int, _MarketFetchResult],
) -> datetime:
    observed = target.fetched_at
    for matched in decisions.values():
        if (
            matched.provider_event is not None
            and matched.provider_event.fetched_at > observed
        ):
            observed = matched.provider_event.fetched_at
    for result in market_results.values():
        for market in result.markets:
            if market.fetched_at > observed:
                observed = market.fetched_at
    return observed
