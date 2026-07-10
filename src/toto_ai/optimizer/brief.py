from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.optimizer.cover import (
    greedy_cover,
    verify_cover_package,
    write_cover_package_csv,
)

OUTCOMES = ("1", "X", "2")
OUTCOME_FIELDS = {
    "1": ("pool_win_1", "bk_win_1"),
    "X": ("pool_draw", "bk_draw"),
    "2": ("pool_win_2", "bk_win_2"),
}


@dataclass(frozen=True)
class EventBriefAnalysis:
    event_order: int
    name: str
    pool: dict[str, float]
    bk: dict[str, float]
    bias: dict[str, float]
    entropy: float
    bk_gap: float
    base_pick: str
    reason: str


def build_brief_for_drawing(
    session: Session,
    drawing_id: int,
    category: int,
    bank: int,
    stake: int = 30,
    report_dir: str | Path = "reports",
) -> dict[str, Any]:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} was not found.")

    events, quotes = _load_events_and_quotes(session, drawing_id)
    analyses = [
        analyze_event(event, quotes[event.event_order])
        for event in events
        if event.event_order is not None and event.event_order in quotes
    ]
    if len(analyses) != 15:
        raise ValueError("Open drawing must have 15 events with pool and BK quotes.")

    result = build_baseline_brief(
        analyses,
        category=category,
        bank=bank,
        stake=stake,
    )
    brief_path, package_path = write_brief_reports(
        drawing_number=drawing.number or drawing.id,
        analyses=analyses,
        result=result,
        report_dir=report_dir,
    )
    return {
        **result,
        "drawing_id": drawing.id,
        "drawing_number": drawing.number,
        "matches": analyses,
        "brief_path": brief_path,
        "package_path": package_path,
    }


def analyze_event(event: Event, quote: Quote) -> EventBriefAnalysis:
    pool = _quote_probabilities(quote, "pool")
    bk = _quote_probabilities(quote, "bk")
    if pool is None or bk is None:
        raise ValueError("Event is missing pool or BK probabilities.")

    ordered_outcomes = sorted(OUTCOMES, key=lambda outcome: (-bk[outcome], outcome))
    top = ordered_outcomes[0]
    second = ordered_outcomes[1]
    gap = bk[top] - bk[second]
    entropy = _entropy(bk)

    if entropy >= 1.07 or gap <= 0.05:
        base_pick = "1X2"
        reason = "highly balanced event"
    elif gap <= 0.18 or bk[top] < 0.52:
        top_two = set(ordered_outcomes[:2])
        base_pick = "".join(outcome for outcome in OUTCOMES if outcome in top_two)
        reason = "uncertain event"
    else:
        base_pick = top
        reason = "clear bookmaker favorite"

    return EventBriefAnalysis(
        event_order=event.event_order or 0,
        name=event.name or "",
        pool=pool,
        bk=bk,
        bias={outcome: pool[outcome] - bk[outcome] for outcome in OUTCOMES},
        entropy=entropy,
        bk_gap=gap,
        base_pick=base_pick,
        reason=reason,
    )


def build_baseline_brief(
    analyses: list[EventBriefAnalysis],
    category: int,
    bank: int,
    stake: int = 30,
) -> dict[str, Any]:
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")

    max_coupons = bank // stake
    candidates = []
    for brief in _candidate_briefs(analyses):
        cover = greedy_cover(
            brief=brief,
            category=category,
            max_coupons=max_coupons,
        )
        cost = len(cover["selected_coupons"]) * stake
        if cost > bank:
            continue
        verification = verify_cover_package(
            brief=brief,
            category=category,
            coupons=cover["selected_coupons"],
        )
        candidate = {
            "brief": brief,
            "selected_coupons": cover["selected_coupons"],
            "full_brief_size": cover["full_variants_count"],
            "covered_variants_count": cover["covered_variants_count"],
            "coverage_rate": cover["coverage_rate"],
            "cost": cost,
            "brief_probability": brief_hit_probability(brief, analyses),
            "value_score": value_against_crowd(brief, analyses),
            "category_guarantee": "PASS"
            if verification["guarantee_pass"]
            else "FAIL",
        }
        candidates.append(candidate)

    if not candidates:
        raise ValueError("No affordable cover package could be generated.")
    return max(candidates, key=rank_candidate_key)


def brief_hit_probability(
    brief: list[str],
    analyses: list[EventBriefAnalysis],
) -> float:
    log_probability = 0.0
    for pick, analysis in zip(brief, analyses, strict=True):
        included_probability = sum(
            analysis.bk[outcome]
            for outcome in OUTCOMES
            if outcome in pick
        )
        if included_probability <= 0:
            return 0.0
        log_probability += math.log(included_probability)
    return math.exp(log_probability)


def value_against_crowd(
    brief: list[str],
    analyses: list[EventBriefAnalysis],
) -> float:
    values = []
    for pick, analysis in zip(brief, analyses, strict=True):
        values.extend(
            analysis.bk[outcome] - analysis.pool[outcome]
            for outcome in OUTCOMES
            if outcome in pick
        )
    if not values:
        return 0.0
    return sum(values) / len(values)


def rank_candidate_key(candidate: dict[str, Any]) -> tuple[float, float, float, int]:
    return (
        float(candidate["brief_probability"]),
        float(candidate["coverage_rate"]),
        float(candidate["value_score"]) * 0.01,
        -int(candidate["cost"]),
    )


def write_brief_reports(
    drawing_number: int,
    analyses: list[EventBriefAnalysis],
    result: dict[str, Any],
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    brief_path = output_dir / f"brief_{drawing_number}.csv"
    package_path = output_dir / f"package_{drawing_number}.csv"

    with brief_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            [
                "event_order",
                "match",
                "pool_1",
                "pool_x",
                "pool_2",
                "bk_1",
                "bk_x",
                "bk_2",
                "selected_cover",
                "reason",
            ]
        )
        for analysis, pick in zip(analyses, result["brief"], strict=True):
            writer.writerow(
                [
                    analysis.event_order + 1,
                    analysis.name,
                    analysis.pool["1"],
                    analysis.pool["X"],
                    analysis.pool["2"],
                    analysis.bk["1"],
                    analysis.bk["X"],
                    analysis.bk["2"],
                    pick,
                    analysis.reason,
                ]
            )

    write_cover_package_csv(result["selected_coupons"], output_path=package_path)
    return brief_path, package_path


def _load_events_and_quotes(
    session: Session,
    drawing_id: int,
) -> tuple[list[Event], dict[int, Quote]]:
    events = list(
        session.scalars(
            select(Event)
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
    )
    quotes = {
        quote.event_order: quote
        for quote in session.scalars(
            select(Quote)
            .where(Quote.drawing_id == drawing_id)
            .order_by(Quote.event_order)
        ).all()
        if quote.event_order is not None
    }
    return events, quotes


def _candidate_briefs(analyses: list[EventBriefAnalysis]) -> list[list[str]]:
    candidates = []
    base = [analysis.base_pick for analysis in analyses]
    candidates.append(base)

    ranked_uncertain = sorted(
        analyses,
        key=lambda analysis: (-analysis.entropy, analysis.bk_gap, analysis.event_order),
    )
    for count in range(1, min(8, len(ranked_uncertain)) + 1):
        brief = base.copy()
        for analysis in ranked_uncertain[:count]:
            brief[analysis.event_order] = _widen_pick(brief[analysis.event_order])
        candidates.append(brief)

    ranked_clear = sorted(
        analyses,
        key=lambda analysis: (analysis.entropy, -analysis.bk_gap, analysis.event_order),
    )
    for count in range(1, min(5, len(ranked_clear)) + 1):
        brief = base.copy()
        for analysis in ranked_clear[:count]:
            brief[analysis.event_order] = _top_pick(analysis)
        candidates.append(brief)

    deduped = []
    seen = set()
    for brief in candidates:
        key = tuple(brief)
        if key not in seen:
            seen.add(key)
            deduped.append(brief)
    return deduped


def _top_pick(analysis: EventBriefAnalysis) -> str:
    return max(OUTCOMES, key=lambda outcome: analysis.bk[outcome])


def _widen_pick(pick: str) -> str:
    if len(pick) == 1:
        return pick
    if len(pick) == 2:
        return "1X2"
    return pick


def _quote_probabilities(quote: Quote, prefix: str) -> dict[str, float] | None:
    raw = {
        "1": getattr(quote, f"{prefix}_win_1"),
        "X": getattr(quote, f"{prefix}_draw"),
        "2": getattr(quote, f"{prefix}_win_2"),
    }
    if any(value is None or value <= 0 for value in raw.values()):
        return None
    probabilities = {
        outcome: _to_probability(value)
        for outcome, value in raw.items()
        if value is not None
    }
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {
        outcome: probability / total
        for outcome, probability in probabilities.items()
    }


def _to_probability(value: float) -> float:
    return value / 100 if value > 1 else value


def _entropy(probabilities: dict[str, float]) -> float:
    return -sum(
        probability * math.log(probability)
        for probability in probabilities.values()
        if probability > 0
    )
