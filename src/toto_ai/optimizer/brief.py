from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.data_health import require_data_health
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


class CoverEngineCache:
    def __init__(self, cover_func=greedy_cover):
        self.cover_func = cover_func
        self._cache: dict[tuple[tuple[str, ...], int, int], dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

    def get(
        self,
        brief: list[str],
        category: int,
        max_coupons: int,
    ) -> dict[str, Any]:
        key = (tuple(brief), category, max_coupons)
        if key in self._cache:
            self.hits += 1
            return self._cache[key]

        self.misses += 1
        result = self.cover_func(
            brief=list(brief),
            category=category,
            max_coupons=max_coupons,
        )
        self._cache[key] = result
        return result


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

    require_data_health(
        session,
        use_case="prospective_generation",
        drawing_ids=(drawing_id,),
    )
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
    top_candidates: int = 20,
    max_candidate_briefs: int = 200,
    timeout_per_drawing: float | None = None,
    cover_cache: CoverEngineCache | None = None,
    progress_callback=None,
) -> dict[str, Any]:
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")
    if top_candidates <= 0:
        raise ValueError("top_candidates must be a positive integer.")
    if max_candidate_briefs <= 0:
        raise ValueError("max_candidate_briefs must be a positive integer.")

    started_at = time.perf_counter()
    max_coupons = bank // stake
    cache = cover_cache or CoverEngineCache()
    timing = {
        "candidate_generation_time": 0.0,
        "scoring_time": 0.0,
        "cover_time": 0.0,
    }

    generation_started_at = time.perf_counter()
    candidate_briefs = _candidate_briefs(
        analyses,
        max_candidate_briefs=max_candidate_briefs,
    )
    timing["candidate_generation_time"] = time.perf_counter() - generation_started_at

    scoring_started_at = time.perf_counter()
    cheap_candidates = [
        _cheap_candidate(
            brief,
            analyses=analyses,
            max_coupons=max_coupons,
            stake=stake,
        )
        for brief in candidate_briefs
    ]
    affordable_candidates = [
        candidate
        for candidate in cheap_candidates
        if candidate["estimated_cost"] <= bank
    ]
    ranked_candidates = sorted(
        affordable_candidates,
        key=_cheap_rank_candidate_key,
        reverse=True,
    )
    exact_variant_limit = _exact_variant_limit(max_coupons)
    exact_candidates = [
        candidate
        for candidate in ranked_candidates
        if candidate["full_brief_size"] <= exact_variant_limit
    ][:top_candidates]
    if not exact_candidates and ranked_candidates:
        exact_candidates = [
            min(ranked_candidates, key=lambda candidate: candidate["full_brief_size"])
        ]
    timing["scoring_time"] = time.perf_counter() - scoring_started_at

    candidates = []
    timed_out = False
    total_exact = len(exact_candidates)
    for index, candidate in enumerate(exact_candidates, start=1):
        if progress_callback is not None:
            progress_callback(
                {
                    "candidate_index": index,
                    "candidate_total": total_exact,
                    "elapsed_time": time.perf_counter() - started_at,
                    "best_score": candidates[-1]["brief_probability"]
                    if candidates
                    else candidate["brief_probability"],
                }
            )

        cover_started_at = time.perf_counter()
        cover = cache.get(
            brief=candidate["brief"],
            category=category,
            max_coupons=max_coupons,
        )
        timing["cover_time"] += time.perf_counter() - cover_started_at

        cost = len(cover["selected_coupons"]) * stake
        if cost > bank:
            continue
        verification = verify_cover_package(
            brief=candidate["brief"],
            category=category,
            coupons=cover["selected_coupons"],
        )
        exact_candidate = {
            **candidate,
            "selected_coupons": cover["selected_coupons"],
            "full_brief_size": cover["full_variants_count"],
            "covered_variants_count": cover["covered_variants_count"],
            "coverage_rate": cover["coverage_rate"],
            "cost": cost,
            "category_guarantee": "PASS"
            if verification["guarantee_pass"]
            else "FAIL",
        }
        candidates.append(exact_candidate)
        best = max(candidates, key=rank_candidate_key)

        if progress_callback is not None:
            progress_callback(
                {
                    "candidate_index": index,
                    "candidate_total": total_exact,
                    "elapsed_time": time.perf_counter() - started_at,
                    "best_score": best["brief_probability"],
                }
            )

        if _timed_out(started_at, timeout_per_drawing):
            timed_out = True
            break

    if not candidates:
        if not exact_candidates:
            raise ValueError("No affordable cover package could be generated.")
        fallback = exact_candidates[0]
        cover = cache.get(
            brief=fallback["brief"],
            category=category,
            max_coupons=max_coupons,
        )
        candidates.append(
            {
                **fallback,
                "selected_coupons": cover["selected_coupons"],
                "full_brief_size": cover["full_variants_count"],
                "covered_variants_count": cover["covered_variants_count"],
                "coverage_rate": cover["coverage_rate"],
                "cost": len(cover["selected_coupons"]) * stake,
                "category_guarantee": "UNKNOWN",
            }
        )
        timed_out = True

    result = max(candidates, key=rank_candidate_key)
    total_time = time.perf_counter() - started_at
    return {
        **result,
        "timed_out": timed_out,
        "candidate_generation_time": round(timing["candidate_generation_time"], 4),
        "scoring_time": round(timing["scoring_time"], 4),
        "cover_time": round(timing["cover_time"], 4),
        "total_time": round(total_time, 4),
        "candidate_count": len(candidate_briefs),
        "exact_candidate_count": len(candidates),
        "skipped_exact_candidate_count": len(ranked_candidates) - total_exact,
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
    }


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


def deduplicate_briefs(briefs: list[list[str]]) -> list[list[str]]:
    deduped = []
    seen = set()
    for brief in briefs:
        key = tuple(brief)
        if key not in seen:
            seen.add(key)
            deduped.append(brief)
    return deduped


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


def _candidate_briefs(
    analyses: list[EventBriefAnalysis],
    max_candidate_briefs: int | None = None,
) -> list[list[str]]:
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
    for count in range(1, len(ranked_clear) + 1):
        brief = base.copy()
        for analysis in ranked_clear[:count]:
            brief[analysis.event_order] = _top_pick(analysis)
        candidates.append(brief)

    deduped = deduplicate_briefs(candidates)
    if max_candidate_briefs is None:
        return deduped
    return deduped[:max_candidate_briefs]


def _cheap_candidate(
    brief: list[str],
    analyses: list[EventBriefAnalysis],
    max_coupons: int,
    stake: int,
) -> dict[str, Any]:
    full_brief_size = _brief_variant_count(brief)
    estimated_package_size = min(full_brief_size, max_coupons)
    estimated_coverage = (
        estimated_package_size / full_brief_size
        if full_brief_size
        else 0.0
    )
    return {
        "brief": brief,
        "full_brief_size": full_brief_size,
        "covered_variants_count": 0,
        "coverage_rate": estimated_coverage,
        "cost": estimated_package_size * stake,
        "estimated_package_size": estimated_package_size,
        "estimated_cost": estimated_package_size * stake,
        "brief_probability": brief_hit_probability(brief, analyses),
        "value_score": value_against_crowd(brief, analyses),
    }


def _brief_variant_count(brief: list[str]) -> int:
    total = 1
    for pick in brief:
        total *= len(pick)
    return total


def _cheap_rank_candidate_key(
    candidate: dict[str, Any],
) -> tuple[float, float, float, int]:
    return (
        float(candidate["brief_probability"]) * float(candidate["coverage_rate"]),
        float(candidate["coverage_rate"]),
        float(candidate["value_score"]) * 0.01,
        -int(candidate["estimated_cost"]),
    )


def _exact_variant_limit(max_coupons: int) -> int:
    return max(1000, min(5000, max_coupons * 10))


def _timed_out(started_at: float, timeout_per_drawing: float | None) -> bool:
    if timeout_per_drawing is None:
        return False
    return time.perf_counter() - started_at >= timeout_per_drawing


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
