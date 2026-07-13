from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.optimizer.brief import (
    EventBriefAnalysis,
    analyze_event,
    build_baseline_brief,
)
from toto_ai.optimizer.brief_backtest import best_coupon_hits, build_result_string
from toto_ai.optimizer.coupon_candidates import (
    generate_candidate_coupons,
    sample_scenarios,
)
from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    normalize_probability_matrix,
    top_probability_coupons,
)
from toto_ai.optimizer.cover import category_max_errors
from toto_ai.optimizer.direct_package import (
    estimate_package_coverage,
    select_weighted_package,
)


@dataclass(frozen=True)
class StrategyConfig:
    bank: int = 5000
    stake: int = 30
    category: int = 13
    seed: int = 42
    top_count: int = 1000
    candidate_samples: int = 3000
    mutation_limit: int = 1000
    optimization_samples: int = 2000
    validation_samples: int = 5000
    timeout_per_drawing: float | None = 30.0

    @property
    def max_coupons(self) -> int:
        return self.bank // self.stake


@dataclass(frozen=True)
class StrategyPackage:
    strategy: str
    coupons: list[str]
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    timed_out: bool


@dataclass(frozen=True)
class StrategyBacktestRow:
    drawing_id: int
    drawing_number: int | None
    segment: str
    strategy: str
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    package_hash: str


@dataclass(frozen=True)
class StrategyBacktestResult:
    rows: list[StrategyBacktestRow]
    summary: dict[str, object]
    config: StrategyConfig


def build_packages_for_probabilities(
    probabilities: ProbabilityMatrix,
    analyses: list[EventBriefAnalysis],
    drawing_id: int,
    config: StrategyConfig,
    baseline_builder: Callable[..., dict[str, Any]] = build_baseline_brief,
) -> list[StrategyPackage]:
    _validate_strategy_config(config)
    _validate_analyses_probabilities(analyses, probabilities)
    max_coupons = config.max_coupons

    validation_seed = config.seed ^ drawing_id ^ 0x5A5A
    validation_scenarios = sample_scenarios(
        probabilities,
        count=config.validation_samples,
        seed=validation_seed,
    )

    baseline_started = time.perf_counter()
    baseline_result = baseline_builder(
        analyses,
        category=config.category,
        bank=config.bank,
        stake=config.stake,
        timeout_per_drawing=config.timeout_per_drawing,
    )
    baseline_coupons = list(baseline_result["selected_coupons"])
    if len(baseline_coupons) > max_coupons:
        raise ValueError("Baseline package exceeds the configured budget.")
    baseline_package = StrategyPackage(
        strategy="baseline_brief",
        coupons=baseline_coupons,
        estimated_coverage=estimate_package_coverage(
            baseline_coupons,
            validation_scenarios,
            config.category,
        ),
        candidate_count=int(
            baseline_result.get("candidate_count", len(baseline_coupons))
        ),
        runtime_seconds=time.perf_counter() - baseline_started,
        timed_out=bool(baseline_result.get("timed_out", False)),
    )

    top_started = time.perf_counter()
    top_coupons = top_probability_coupons(probabilities, limit=max_coupons)
    top_package = StrategyPackage(
        strategy="top_probability",
        coupons=top_coupons,
        estimated_coverage=estimate_package_coverage(
            top_coupons,
            validation_scenarios,
            config.category,
        ),
        candidate_count=len(top_coupons),
        runtime_seconds=time.perf_counter() - top_started,
        timed_out=False,
    )

    weighted_started = time.perf_counter()
    candidate_seed = config.seed ^ drawing_id ^ 0xC3C3
    candidates = generate_candidate_coupons(
        probabilities,
        max_coupons=max_coupons,
        top_count=config.top_count,
        sample_count=config.candidate_samples,
        mutation_limit=config.mutation_limit,
        seed=candidate_seed,
    )
    optimization_seed = config.seed ^ drawing_id ^ 0xA5A5
    optimization_scenarios = sample_scenarios(
        probabilities,
        count=config.optimization_samples,
        seed=optimization_seed,
    )
    deadline = (
        None
        if config.timeout_per_drawing is None
        else weighted_started + config.timeout_per_drawing
    )
    weighted_result = select_weighted_package(
        candidates=candidates,
        scenarios=optimization_scenarios,
        probabilities=probabilities,
        category=config.category,
        max_coupons=max_coupons,
        deadline=deadline,
    )
    weighted_package = StrategyPackage(
        strategy="weighted_coverage",
        coupons=weighted_result.selected_coupons,
        estimated_coverage=estimate_package_coverage(
            weighted_result.selected_coupons,
            validation_scenarios,
            config.category,
        ),
        candidate_count=len(candidates),
        runtime_seconds=time.perf_counter() - weighted_started,
        timed_out=weighted_result.timed_out,
    )

    return [baseline_package, top_package, weighted_package]


def select_eligible_strategy_drawings(
    session: Session,
    last: int,
    community: str = "baltbet-main",
) -> list[Drawing]:
    drawings, _ = _scan_eligible_strategy_drawings(session, last, community)
    return drawings


def split_development_holdout(
    drawings: list[Drawing],
    holdout_size: int,
) -> dict[int, str]:
    if holdout_size < 0 or holdout_size > len(drawings):
        raise ValueError("holdout_size must be between zero and drawing count.")
    ordered = sorted(
        drawings,
        key=lambda drawing: (
            drawing.number if drawing.number is not None else drawing.id,
            drawing.id,
        ),
    )
    development_count = len(ordered) - holdout_size
    return {
        drawing.id: (
            "development" if index < development_count else "holdout"
        )
        for index, drawing in enumerate(ordered)
    }


def run_strategy_backtest(
    session: Session,
    last: int,
    holdout_size: int,
    config: StrategyConfig,
    community: str = "baltbet-main",
    progress_callback=None,
    package_builder=build_packages_for_probabilities,
) -> StrategyBacktestResult:
    if last <= 0:
        raise ValueError("last must be positive.")
    _validate_strategy_config(config)

    started_at = time.perf_counter()
    drawings, eligibility_skipped = _scan_eligible_strategy_drawings(
        session,
        last,
        community,
    )
    segments = split_development_holdout(drawings, holdout_size)
    rows = []
    generation_skipped = 0
    timed_out_drawings = 0
    holdout_timed_out = False

    for index, drawing in enumerate(drawings, start=1):
        events, quotes = _load_strategy_events_and_quotes(session, drawing.id)
        analyses = [
            analyze_event(event, quotes[event.event_order])
            for event in events
            if event.event_order is not None
        ]
        probabilities = normalize_probability_matrix(
            [analysis.bk for analysis in analyses]
        )

        try:
            packages = package_builder(
                probabilities=probabilities,
                analyses=analyses,
                drawing_id=drawing.id,
                config=config,
            )
        except ValueError:
            generation_skipped += 1
            _emit_strategy_progress(
                progress_callback,
                drawing,
                index,
                len(drawings),
                len(drawings),
                eligibility_skipped + generation_skipped,
                started_at,
            )
            continue

        if len(packages) != 3 or {package.strategy for package in packages} != {
            "baseline_brief",
            "top_probability",
            "weighted_coverage",
        }:
            generation_skipped += 1
            _emit_strategy_progress(
                progress_callback,
                drawing,
                index,
                len(drawings),
                len(drawings),
                eligibility_skipped + generation_skipped,
                started_at,
            )
            continue
        if any(package.timed_out for package in packages):
            generation_skipped += 1
            timed_out_drawings += 1
            holdout_timed_out = holdout_timed_out or segments[drawing.id] == "holdout"
            _emit_strategy_progress(
                progress_callback,
                drawing,
                index,
                len(drawings),
                len(drawings),
                eligibility_skipped + generation_skipped,
                started_at,
            )
            continue

        result_string = build_result_string(events)
        for package in packages:
            best_hits = best_coupon_hits(package.coupons, result_string)
            rows.append(
                StrategyBacktestRow(
                    drawing_id=drawing.id,
                    drawing_number=drawing.number,
                    segment=segments[drawing.id],
                    strategy=package.strategy,
                    best_hits=best_hits,
                    hit_13=best_hits >= 13,
                    hit_14=best_hits >= 14,
                    hit_15=best_hits == 15,
                    package_size=len(package.coupons),
                    package_cost=len(package.coupons) * config.stake,
                    estimated_coverage=package.estimated_coverage,
                    candidate_count=package.candidate_count,
                    runtime_seconds=package.runtime_seconds,
                    package_hash=hashlib.sha256(
                        ",".join(package.coupons).encode("utf-8")
                    ).hexdigest(),
                )
            )

        _emit_strategy_progress(
            progress_callback,
            drawing,
            index,
            len(drawings),
            len(drawings),
            eligibility_skipped + generation_skipped,
            started_at,
        )

    evaluated_ids = {row.drawing_id for row in rows}
    summary: dict[str, object] = {
        "requested_drawings": last,
        "eligible_drawings": len(drawings),
        "evaluated_drawings": len(evaluated_ids),
        "skipped_drawings": eligibility_skipped + generation_skipped,
        "timed_out_drawings": timed_out_drawings,
        "development_drawings": len(
            {row.drawing_id for row in rows if row.segment == "development"}
        ),
        "holdout_drawings": len(
            {row.drawing_id for row in rows if row.segment == "holdout"}
        ),
        "operationally_inconclusive": holdout_timed_out,
        "execution_time_seconds": round(time.perf_counter() - started_at, 4),
    }
    return StrategyBacktestResult(rows=rows, summary=summary, config=config)


def _validate_strategy_config(config: StrategyConfig) -> None:
    if config.bank <= 0:
        raise ValueError("bank must be positive.")
    if config.stake <= 0:
        raise ValueError("stake must be positive.")
    category_max_errors(config.category)
    if config.max_coupons <= 0:
        raise ValueError("Budget must fund at least one coupon.")
    if config.top_count < config.max_coupons:
        raise ValueError("top_count must be at least the package coupon limit.")
    for field_name in (
        "candidate_samples",
        "optimization_samples",
        "validation_samples",
    ):
        if getattr(config, field_name) <= 0:
            raise ValueError(f"{field_name} must be positive.")
    if config.mutation_limit < 0:
        raise ValueError("mutation_limit must be non-negative.")
    if config.timeout_per_drawing is not None and (
        not math.isfinite(config.timeout_per_drawing)
        or config.timeout_per_drawing <= 0
    ):
        raise ValueError("timeout_per_drawing must be positive and finite.")


def _validate_analyses_probabilities(
    analyses: list[EventBriefAnalysis],
    probabilities: ProbabilityMatrix,
) -> None:
    if not analyses:
        return
    if len(analyses) != len(probabilities):
        raise ValueError("Analysis and probability matrix lengths must match.")
    for analysis, row in zip(analyses, probabilities, strict=True):
        if any(
            not math.isclose(
                analysis.bk[outcome],
                row[index],
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            for index, outcome in enumerate(OUTCOMES)
        ):
            raise ValueError("Analysis BK probabilities must match the matrix.")


def _scan_eligible_strategy_drawings(
    session: Session,
    last: int,
    community: str,
) -> tuple[list[Drawing], int]:
    if last <= 0:
        raise ValueError("last must be positive.")

    candidates = session.scalars(
        select(Drawing)
        .where(Drawing.name == community)
        .where(Drawing.status == "finished")
        .order_by(Drawing.number.desc(), Drawing.id.desc())
    ).all()
    selected = []
    skipped = 0
    for drawing in candidates:
        events, quotes = _load_strategy_events_and_quotes(session, drawing.id)
        event_orders = {
            event.event_order for event in events if event.event_order is not None
        }
        if (
            not _has_supported_results(events)
            or event_orders != set(range(15))
            or set(quotes) != event_orders
        ):
            skipped += 1
            continue
        try:
            analyses = [
                analyze_event(event, quotes[event.event_order])
                for event in events
                if event.event_order is not None
            ]
        except (KeyError, ValueError):
            skipped += 1
            continue
        if len(analyses) != 15:
            skipped += 1
            continue
        selected.append(drawing)
        if len(selected) == last:
            break

    selected.sort(
        key=lambda drawing: (
            drawing.number if drawing.number is not None else drawing.id,
            drawing.id,
        )
    )
    return selected, skipped


def _load_strategy_events_and_quotes(
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


def _has_supported_results(events: list[Event]) -> bool:
    return len(events) == 15 and all(
        normalize_result(event.result) is not None for event in events
    )


def _emit_strategy_progress(
    callback,
    drawing: Drawing,
    index: int,
    total: int,
    eligible: int,
    skipped: int,
    started_at: float,
) -> None:
    if callback is None:
        return
    elapsed = time.perf_counter() - started_at
    average = elapsed / index
    callback(
        {
            "drawing_number": drawing.number,
            "drawing_index": index,
            "drawing_total": total,
            "eligible": eligible,
            "skipped": skipped,
            "elapsed_time": elapsed,
            "eta_seconds": average * (total - index),
        }
    )
