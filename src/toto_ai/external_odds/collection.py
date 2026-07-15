from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import InitVar, asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from toto_ai.ev.drawing import resolve_open_drawing_from_api
from toto_ai.external_odds.api_sports import APISportsError, QuotaExhausted
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
from toto_ai.external_odds.targets import parse_target_drawing

CONSENSUS_MINIMUM_BOOKMAKERS = 3
EXTERNAL_CONSENSUS = "external_consensus"
TOTOBRIEF_BK_FALLBACK = "totobrief_bk_fallback"
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
    provider_starts_at: InitVar[str | None] = None
    effective_starts_at: InitVar[str | None] = None
    effective_start_source: InitVar[str] = "unresolved"

    def __post_init__(
        self,
        provider_starts_at: str | None,
        effective_starts_at: str | None,
        effective_start_source: str,
    ) -> None:
        object.__setattr__(self, "provider_starts_at", provider_starts_at)
        object.__setattr__(self, "effective_starts_at", effective_starts_at)
        object.__setattr__(
            self,
            "effective_start_source",
            effective_start_source,
        )


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
    target_fingerprint: InitVar[str] = ""
    missing_start_horizon_days: InitVar[int] = 2
    requested_schedule_dates: InitVar[tuple[ScheduleDateResult, ...]] = ()
    successful_schedule_dates: InitVar[tuple[ScheduleDateResult, ...]] = ()
    failed_schedule_dates: InitVar[tuple[ScheduleDateResult, ...]] = ()
    eligibility: InitVar[DrawingEligibility] = _UNKNOWN_ELIGIBILITY

    def __post_init__(
        self,
        target_fingerprint: str,
        missing_start_horizon_days: int,
        requested_schedule_dates: tuple[ScheduleDateResult, ...],
        successful_schedule_dates: tuple[ScheduleDateResult, ...],
        failed_schedule_dates: tuple[ScheduleDateResult, ...],
        eligibility: DrawingEligibility,
    ) -> None:
        object.__setattr__(self, "target_fingerprint", target_fingerprint)
        object.__setattr__(
            self,
            "missing_start_horizon_days",
            missing_start_horizon_days,
        )
        object.__setattr__(
            self,
            "requested_schedule_dates",
            requested_schedule_dates,
        )
        object.__setattr__(
            self,
            "successful_schedule_dates",
            successful_schedule_dates,
        )
        object.__setattr__(
            self,
            "failed_schedule_dates",
            failed_schedule_dates,
        )
        object.__setattr__(self, "eligibility", eligibility)


@dataclass(frozen=True)
class _MatchedTarget:
    decision: MatchDecision
    provider_event: ProviderEvent | None


@dataclass(frozen=True)
class _MarketFetchResult:
    markets: tuple[ProviderMarket, ...]
    fallback_reason: str | None


def build_external_collection(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    aliases: dict[str, str],
    missing_start_horizon_days: int = 2,
) -> ExternalCollectionSnapshot:
    _validate_missing_start_horizon_days(missing_start_horizon_days)
    request_counter = _RequestCounter(provider)
    provider_name = provider.provider_name
    schedule_results = _fetch_schedules(
        target,
        request_counter,
        missing_start_horizon_days,
    )
    decisions = _match_targets(target, schedule_results, aliases)

    market_cache: dict[tuple[Sport, str], tuple[ProviderMarket, ...]] = {}
    quota_stopped = False
    market_results: dict[int, _MarketFetchResult] = {}
    for event in target.events:
        matched_target = decisions[event.event_order]
        decision = matched_target.decision
        if decision.status != "matched" or decision.provider_event_id is None:
            market_results[event.event_order] = _MarketFetchResult(
                markets=(),
                fallback_reason=decision.reason,
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
            except QuotaExhausted:
                quota_stopped = True
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason="quota reserve reached",
                )
                continue
            except APISportsError as error:
                market_results[event.event_order] = _MarketFetchResult(
                    markets=(),
                    fallback_reason=f"provider odds failure: {error}",
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
            )
        )

    ordered_rows = tuple(sorted(rows, key=lambda row: row.event_order))
    status = "complete" if len(ordered_rows) == 15 else "partial"
    quota = provider.quota_state
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
        target_fingerprint_value=target_identity,
        missing_start_horizon_days=missing_start_horizon_days,
        requested_schedule_dates=schedule_results,
        successful_schedule_dates=successful_schedule_dates,
        failed_schedule_dates=failed_schedule_dates,
        eligibility=eligibility,
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
    def __init__(self, provider: ExternalOddsProvider) -> None:
        self.provider = provider
        self.requests_made = 0
        self.cache_hits = 0

    def fetch_schedule(
        self,
        sport: Sport,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        before_requests = _provider_counter(self.provider, "requests_made")
        before_cache_hits = _provider_counter(self.provider, "cache_hits")
        try:
            return self.provider.fetch_schedule(sport, dates)
        finally:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=max(1, len(dates)),
            )

    def fetch_event_markets(
        self,
        sport: Sport,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        before_requests = _provider_counter(self.provider, "requests_made")
        before_cache_hits = _provider_counter(self.provider, "cache_hits")
        try:
            return self.provider.fetch_event_markets(sport, provider_event_id)
        finally:
            self._sync_provider_counts(
                before_requests=before_requests,
                before_cache_hits=before_cache_hits,
                fallback_requests=1,
            )

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


def _fetch_schedules(
    target: TargetDrawing,
    request_counter: _RequestCounter,
    missing_start_horizon_days: int,
) -> tuple[ScheduleDateResult, ...]:
    required_dates: dict[Sport, set[date]] = defaultdict(set)
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
    for sport, requested_date in requested:
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
        try:
            events = request_counter.fetch_schedule(sport, (requested_date,))
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=events,
                    error=None,
                )
            )
        except QuotaExhausted:
            quota_stopped = True
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error="quota reserve reached",
                )
            )
        except Exception:
            results.append(
                ScheduleDateResult(
                    sport=sport,
                    requested_date=requested_date,
                    events=(),
                    error="provider schedule failure",
                )
            )
    return tuple(results)


def _match_targets(
    target: TargetDrawing,
    schedule_results: tuple[ScheduleDateResult, ...],
    aliases: dict[str, str],
) -> dict[int, _MatchedTarget]:
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
            decision = match_event(event, (), aliases)
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
        )
        if (
            event.starts_at is None
            and decision.status == "missing"
            and event.sport in failures_by_sport
        ):
            decision = MatchDecision(
                status=decision.status,
                provider_event_id=decision.provider_event_id,
                matcher_version=decision.matcher_version,
                candidate_ids=decision.candidate_ids,
                reason="partial schedule",
                orientation=decision.orientation,
            )
        provider_event = _matched_provider_event(
            decision,
            schedules.get(event.sport, ()),
        )
        decisions[event.event_order] = _MatchedTarget(decision, provider_event)
    return decisions


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
    )


def _consensus_disposition(
    event: TargetEvent,
    decision: MatchDecision,
    provider_event: ProviderEvent | None,
    consensus: ConsensusResult,
    observed_at: datetime,
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
) -> ExternalEventDispositionRecord:
    effective_start = _effective_event_start(event, provider_event)
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
            else None
        ),
        effective_starts_at=(
            _iso_datetime(effective_start.starts_at)
            if effective_start.starts_at is not None
            else None
        ),
        effective_start_source=effective_start.source,
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
) -> dict[str, object]:
    effective_start = _effective_event_start(event, provider_event)
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
            }
            if provider_event is not None
            else None
        ),
        "probability_source": probability_source,
        "probabilities": probabilities,
        "eligible_bookmaker_count": eligible_bookmaker_count,
        "odds_age_hours": odds_age_hours,
        "fallback_reason": fallback_reason,
        "quotes": tuple(asdict(quote) for quote in quotes),
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
    target_fingerprint_value: str,
    missing_start_horizon_days: int,
    requested_schedule_dates: tuple[ScheduleDateResult, ...],
    successful_schedule_dates: tuple[ScheduleDateResult, ...],
    failed_schedule_dates: tuple[ScheduleDateResult, ...],
    eligibility: DrawingEligibility,
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
        "target_payload": tuple(
            _target_event_payload(event) for event in target.events
        ),
        "events": tuple(
            {
                key: value
                for key, value in event.__dict__.items()
                if key != "bookmaker_quotes"
            }
            | {
                "bookmaker_quotes": tuple(
                    asdict(quote)
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
) -> tuple[dict[str, str | None], ...]:
    return tuple(
        {
            "sport": result.sport,
            "requested_date": result.requested_date.isoformat(),
            "error": result.error,
        }
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
                            asdict(source) for source in provenance
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
    )


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
