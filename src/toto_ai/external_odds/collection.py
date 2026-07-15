from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

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
from toto_ai.external_odds.matching import MATCHER_VERSION, MatchDecision, match_event
from toto_ai.external_odds.targets import parse_target_drawing

CONSENSUS_MINIMUM_BOOKMAKERS = 3
EXTERNAL_CONSENSUS = "external_consensus"
TOTOBRIEF_BK_FALLBACK = "totobrief_bk_fallback"


@dataclass(frozen=True)
class ExternalBookmakerQuoteRecord:
    bookmaker_id: str
    market_name: str
    updated_at: str
    home_price: float | None
    draw_price: float | None
    away_price: float | None
    eligible: int
    rejection_reason: str | None


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
    matcher_version: str
    probability_source: str
    probability_1: float
    probability_x: float
    probability_2: float
    eligible_bookmaker_count: int
    odds_age_hours: float | None
    fallback_reason: str | None
    payload_hash: str
    bookmaker_quotes: tuple[ExternalBookmakerQuoteRecord, ...] = ()


@dataclass(frozen=True)
class ExternalCollectionSnapshot:
    collection_id: str
    drawing_id: int
    drawing_number: int | None
    provider: str
    fetched_at: str
    deadline: str
    event_count: int
    requests_made: int
    daily_limit: int | None
    daily_remaining: int | None
    minute_remaining: int | None
    status: str
    events: tuple[ExternalEventDispositionRecord, ...]


def build_external_collection(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    aliases: dict[str, str],
) -> ExternalCollectionSnapshot:
    request_counter = _RequestCounter(provider)
    provider_name = provider.provider_name
    schedules, schedule_failures = _fetch_schedules(target, provider, request_counter)
    decisions = _match_targets(target, schedules, schedule_failures, aliases)

    market_cache: dict[tuple[Sport, str], tuple[ProviderMarket, ...]] = {}
    quota_stopped = False
    rows: list[ExternalEventDispositionRecord] = []
    for event in target.events:
        decision = decisions[event.event_order]
        if decision.status != "matched" or decision.provider_event_id is None:
            rows.append(_fallback_disposition(event, decision, decision.reason))
            continue
        if quota_stopped:
            rows.append(_fallback_disposition(event, decision, "quota reserve reached"))
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
                rows.append(
                    _fallback_disposition(event, decision, "quota reserve reached")
                )
                continue
            except APISportsError as error:
                rows.append(
                    _fallback_disposition(
                        event,
                        decision,
                        f"provider odds failure: {error}",
                    )
                )
                continue
            except Exception as error:
                rows.append(
                    _fallback_disposition(
                        event,
                        decision,
                        f"provider odds failure: {error.__class__.__name__}",
                    )
                )
                continue
            market_cache[market_key] = markets

        consensus = build_consensus(
            event,
            markets,
            target.fetched_at,
            minimum_bookmakers=CONSENSUS_MINIMUM_BOOKMAKERS,
            maximum_age=MAXIMUM_ODDS_AGE,
        )
        rows.append(_consensus_disposition(event, decision, consensus))

    ordered_rows = tuple(sorted(rows, key=lambda row: row.event_order))
    status = "complete" if len(ordered_rows) == 15 else "partial"
    quota = provider.quota_state
    body = _collection_identity_payload(
        target=target,
        provider=provider_name,
        events=ordered_rows,
    )
    collection_id = _hash_payload(body)
    return ExternalCollectionSnapshot(
        collection_id=collection_id,
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        provider=provider_name,
        fetched_at=_iso_datetime(target.fetched_at),
        deadline=_iso_datetime(target.deadline),
        event_count=len(ordered_rows),
        requests_made=request_counter.requests_made,
        daily_limit=quota.daily_limit,
        daily_remaining=quota.daily_remaining,
        minute_remaining=quota.minute_remaining,
        status=status,
        events=ordered_rows,
    )


def collect_open_external_odds(
    totobrief_client: Any,
    provider: ExternalOddsProvider,
    session_factory: Any,
    aliases: dict[str, str],
    fetched_at: datetime,
) -> ExternalCollectionSnapshot:
    reference = resolve_open_drawing_from_api(totobrief_client)
    payload = totobrief_client.drawing_info(reference.drawing_id)
    target = parse_target_drawing(payload, fetched_at=fetched_at)
    if target.drawing_id != reference.drawing_id:
        raise ValueError("drawing-info id does not match resolved drawing")
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

    def fetch_schedule(
        self,
        sport: Sport,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        before = _provider_requests_made(self.provider)
        expected_requests = max(1, len(dates))
        self.requests_made += expected_requests
        result = self.provider.fetch_schedule(sport, dates)
        self._sync_provider_count(before, expected_requests)
        return result

    def fetch_event_markets(
        self,
        sport: Sport,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        before = _provider_requests_made(self.provider)
        self.requests_made += 1
        result = self.provider.fetch_event_markets(sport, provider_event_id)
        self._sync_provider_count(before, 1)
        return result

    def _sync_provider_count(self, before: int | None, expected_requests: int) -> None:
        after = _provider_requests_made(self.provider)
        if before is not None and after is not None and after > before:
            self.requests_made += max(0, after - before - expected_requests)


def _provider_requests_made(provider: ExternalOddsProvider) -> int | None:
    value = getattr(provider, "requests_made", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _fetch_schedules(
    target: TargetDrawing,
    provider: ExternalOddsProvider,
    request_counter: _RequestCounter,
) -> tuple[dict[Sport, tuple[ProviderEvent, ...]], dict[Sport, str]]:
    required_dates: dict[Sport, set[date]] = defaultdict(set)
    for event in target.events:
        if event.sport in {"football", "hockey"}:
            required_dates[event.sport].add(event.starts_at.date())

    schedules: dict[Sport, tuple[ProviderEvent, ...]] = {}
    failures: dict[Sport, str] = {}
    sports = tuple(sorted(required_dates))
    for index, sport in enumerate(sports):
        dates = tuple(sorted(required_dates[sport]))
        try:
            schedules[sport] = request_counter.fetch_schedule(sport, dates)
        except QuotaExhausted:
            for remaining_sport in sports[index:]:
                failures[remaining_sport] = "quota reserve reached"
            break
        except APISportsError as error:
            failures[sport] = f"provider schedule failure: {error}"
        except Exception as error:
            failures[sport] = (
                f"provider schedule failure: {error.__class__.__name__}"
            )
    return schedules, failures


def _match_targets(
    target: TargetDrawing,
    schedules: dict[Sport, tuple[ProviderEvent, ...]],
    schedule_failures: dict[Sport, str],
    aliases: dict[str, str],
) -> dict[int, MatchDecision]:
    decisions: dict[int, MatchDecision] = {}
    for event in target.events:
        if event.sport in schedule_failures:
            decisions[event.event_order] = MatchDecision(
                status="provider_failure",
                provider_event_id=None,
                matcher_version=MATCHER_VERSION,
                candidate_ids=(),
                reason=schedule_failures[event.sport],
            )
            continue
        decisions[event.event_order] = match_event(
            event,
            schedules.get(event.sport, ()),
            aliases,
        )
    return decisions


def _fallback_disposition(
    event: TargetEvent,
    decision: MatchDecision,
    reason: str,
) -> ExternalEventDispositionRecord:
    payload = _event_payload(
        event=event,
        decision=decision,
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
    consensus: ConsensusResult,
) -> ExternalEventDispositionRecord:
    quotes = tuple(
        ExternalBookmakerQuoteRecord(
            bookmaker_id=assessment.market.bookmaker_id,
            market_name=assessment.market.market_name,
            updated_at=_iso_datetime(assessment.market.updated_at),
            home_price=assessment.market.home_price,
            draw_price=assessment.market.draw_price,
            away_price=assessment.market.away_price,
            eligible=1 if assessment.eligible else 0,
            rejection_reason=assessment.rejection_reason,
        )
        for assessment in consensus.assessments
    )
    if consensus.probabilities is None:
        probability_source = TOTOBRIEF_BK_FALLBACK
        probabilities = event.bk_probabilities
        fallback_reason = _consensus_fallback_reason(consensus)
    else:
        probability_source = EXTERNAL_CONSENSUS
        probabilities = consensus.probabilities
        fallback_reason = None
    odds_age_hours = _odds_age_hours(event, consensus)
    payload = _event_payload(
        event=event,
        decision=decision,
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
    probability_source: str,
    probabilities: OutcomeTriplet,
    eligible_bookmaker_count: int,
    odds_age_hours: float | None,
    fallback_reason: str | None,
    payload_hash: str,
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
) -> ExternalEventDispositionRecord:
    return ExternalEventDispositionRecord(
        drawing_id=event.drawing_id,
        event_order=event.event_order,
        target_event_id=event.event_id,
        sport=event.sport,
        championship=event.championship,
        starts_at=_iso_datetime(event.starts_at),
        home_team=event.home_team,
        away_team=event.away_team,
        home_team_en=event.home_team_en,
        away_team_en=event.away_team_en,
        match_status=decision.status,
        provider_event_id=decision.provider_event_id,
        matcher_version=decision.matcher_version,
        probability_source=probability_source,
        probability_1=probabilities[0],
        probability_x=probabilities[1],
        probability_2=probabilities[2],
        eligible_bookmaker_count=eligible_bookmaker_count,
        odds_age_hours=odds_age_hours,
        fallback_reason=fallback_reason,
        payload_hash=payload_hash,
        bookmaker_quotes=quotes,
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


def _odds_age_hours(
    event: TargetEvent,
    consensus: ConsensusResult,
) -> float | None:
    assessed = tuple(assessment.market for assessment in consensus.assessments)
    if not assessed:
        return None
    oldest = max(market.fetched_at - market.updated_at for market in assessed)
    return oldest.total_seconds() / 3600.0


def _event_payload(
    *,
    event: TargetEvent,
    decision: MatchDecision,
    probability_source: str,
    probabilities: OutcomeTriplet,
    eligible_bookmaker_count: int,
    odds_age_hours: float | None,
    fallback_reason: str | None,
    quotes: tuple[ExternalBookmakerQuoteRecord, ...],
) -> dict[str, object]:
    return {
        "target": _target_event_payload(event),
        "match": {
            "status": decision.status,
            "provider_event_id": decision.provider_event_id,
            "matcher_version": decision.matcher_version,
            "candidate_ids": decision.candidate_ids,
            "reason": decision.reason,
        },
        "probability_source": probability_source,
        "probabilities": probabilities,
        "eligible_bookmaker_count": eligible_bookmaker_count,
        "odds_age_hours": odds_age_hours,
        "fallback_reason": fallback_reason,
        "quotes": tuple(quote.__dict__ for quote in quotes),
    }


def _collection_identity_payload(
    *,
    target: TargetDrawing,
    provider: str,
    events: tuple[ExternalEventDispositionRecord, ...],
) -> dict[str, object]:
    return {
        "drawing": {
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "deadline": _iso_datetime(target.deadline),
            "fetched_at": _iso_datetime(target.fetched_at),
        },
        "provider": provider,
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
                    quote.__dict__ for quote in event.bookmaker_quotes
                )
            }
            for event in events
        ),
        "consensus": {
            "minimum_bookmakers": CONSENSUS_MINIMUM_BOOKMAKERS,
            "maximum_odds_age_seconds": int(MAXIMUM_ODDS_AGE.total_seconds()),
        },
    }


def _target_event_payload(event: TargetEvent) -> dict[str, object]:
    return {
        "drawing_id": event.drawing_id,
        "drawing_number": event.drawing_number,
        "event_id": event.event_id,
        "event_order": event.event_order,
        "sport": event.sport,
        "championship": event.championship,
        "starts_at": _iso_datetime(event.starts_at),
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


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
