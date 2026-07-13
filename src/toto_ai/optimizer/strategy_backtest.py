from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from toto_ai.optimizer.brief import EventBriefAnalysis, build_baseline_brief
from toto_ai.optimizer.coupon_candidates import (
    generate_candidate_coupons,
    sample_scenarios,
)
from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
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
