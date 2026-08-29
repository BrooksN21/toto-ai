"""Research-only maximin package selection across probability models.

The selector is deliberately provider-neutral.  It receives a finite coupon
universe and two or more pre-deadline probability matrices, then greedily
maximizes the worst sampled category coverage across those models.  It has no
operator, scheduler, release, or wagering integration.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.optimizer.coupon_candidates import sample_scenarios
from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    coupon_log_probability,
)
from toto_ai.optimizer.cover import category_max_errors
from toto_ai.optimizer.direct_package import neighbors_within_distance


@dataclass(frozen=True)
class RobustModelMetrics:
    model: str
    sampled_category_coverage: float
    exact_p13: float | None
    exact_p14: float | None
    exact_p15: float | None


@dataclass(frozen=True)
class RobustPackageResult:
    selected_coupons: tuple[str, ...]
    model_metrics: tuple[RobustModelMetrics, ...]
    worst_sampled_category_coverage: float
    mean_sampled_category_coverage: float
    candidate_count: int
    sample_count_per_model: int
    category: int
    timed_out: bool


@dataclass
class _ModelWorkload:
    name: str
    probabilities: ProbabilityMatrix
    weights: list[int]
    candidate_to_scenarios: list[set[int]]
    scenario_to_candidates: list[list[int]]
    marginal_scores: list[int]
    total_weight: int
    covered_scenarios: set[int]
    covered_weight: int = 0


def select_robust_package(
    *,
    candidates: Sequence[str],
    probability_models: Mapping[str, Sequence[Sequence[float]]],
    category: int,
    max_coupons: int,
    sample_count: int = 10_000,
    seed_material: str = "robust-package-v1",
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> RobustPackageResult:
    """Select a deterministic finite-universe maximin research package.

    The primary greedy objective is the minimum projected sampled category
    coverage across all supplied models.  Mean coverage and worst/mean coupon
    log probability are deterministic tie-breakers.  Exact 13+/14+/15 model
    probabilities are reported for 15-event packages after selection.
    """

    if type(max_coupons) is not int or max_coupons < 0:
        raise ValueError("max_coupons must be a non-negative int")
    if type(sample_count) is not int or sample_count <= 0:
        raise ValueError("sample_count must be a positive int")
    if not isinstance(seed_material, str) or not seed_material:
        raise ValueError("seed_material must be a non-empty string")
    max_errors = category_max_errors(category)
    models = _normalize_models(probability_models)
    event_count = len(models[0][1])
    unique_candidates = tuple(dict.fromkeys(candidates))
    _validate_candidates(unique_candidates, event_count)
    if not unique_candidates or max_coupons == 0:
        return _empty_result(
            models=models,
            candidate_count=len(unique_candidates),
            sample_count=sample_count,
            category=category,
        )

    candidate_index = {
        coupon: index for index, coupon in enumerate(unique_candidates)
    }
    workloads: list[_ModelWorkload] = []
    for model_name, probabilities in models:
        if _expired(deadline, time_func):
            return _empty_result(
                models=models,
                candidate_count=len(unique_candidates),
                sample_count=sample_count,
                category=category,
                timed_out=True,
            )
        scenarios = sample_scenarios(
            probabilities,
            count=sample_count,
            seed=_model_seed(seed_material, model_name),
        )
        workload = _build_workload(
            model_name=model_name,
            probabilities=probabilities,
            candidates=unique_candidates,
            candidate_index=candidate_index,
            scenarios=scenarios,
            max_errors=max_errors,
            deadline=deadline,
            time_func=time_func,
        )
        if workload is None:
            return _empty_result(
                models=models,
                candidate_count=len(unique_candidates),
                sample_count=sample_count,
                category=category,
                timed_out=True,
            )
        workloads.append(workload)

    log_probabilities = tuple(
        tuple(
            coupon_log_probability(coupon, probabilities)
            for coupon in unique_candidates
        )
        for _, probabilities in models
    )
    selected_indexes: set[int] = set()
    selected_order: list[int] = []
    limit = min(max_coupons, len(unique_candidates))
    timed_out = False
    while len(selected_order) < limit:
        if _expired(deadline, time_func):
            timed_out = True
            break
        remaining = (
            index
            for index in range(len(unique_candidates))
            if index not in selected_indexes
        )
        best_index: int | None = None
        best_key: tuple[float, float, float, float] | None = None
        for index in remaining:
            projected = tuple(
                (workload.covered_weight + workload.marginal_scores[index])
                / workload.total_weight
                for workload in workloads
            )
            coupon_logs = tuple(row[index] for row in log_probabilities)
            key = (
                min(projected),
                math.fsum(projected) / len(projected),
                min(coupon_logs),
                math.fsum(coupon_logs) / len(coupon_logs),
            )
            if (
                best_key is None
                or key > best_key
                or (
                    key == best_key
                    and unique_candidates[index] < unique_candidates[best_index]  # type: ignore[index]
                )
            ):
                best_index = index
                best_key = key
        if best_index is None:
            break
        selected_indexes.add(best_index)
        selected_order.append(best_index)
        for workload in workloads:
            _apply_candidate(workload, best_index, selected_indexes)

    selected = tuple(unique_candidates[index] for index in selected_order)
    metrics = _model_metrics(selected, workloads, event_count)
    sampled = tuple(item.sampled_category_coverage for item in metrics)
    return RobustPackageResult(
        selected_coupons=selected,
        model_metrics=metrics,
        worst_sampled_category_coverage=min(sampled),
        mean_sampled_category_coverage=math.fsum(sampled) / len(sampled),
        candidate_count=len(unique_candidates),
        sample_count_per_model=sample_count,
        category=category,
        timed_out=timed_out,
    )


def _normalize_models(
    probability_models: Mapping[str, Sequence[Sequence[float]]],
) -> tuple[tuple[str, ProbabilityMatrix], ...]:
    if not isinstance(probability_models, Mapping) or len(probability_models) < 2:
        raise ValueError("at least two probability models are required")
    normalized = []
    event_count: int | None = None
    for name in sorted(probability_models):
        if not isinstance(name, str) or not name:
            raise ValueError("probability model names must be non-empty strings")
        rows = []
        for raw_row in probability_models[name]:
            if len(raw_row) != 3:
                raise ValueError("each probability row must contain three outcomes")
            values = tuple(float(value) for value in raw_row)
            total = math.fsum(values)
            if (
                not math.isfinite(total)
                or total <= 0.0
                or any(not math.isfinite(value) or value <= 0.0 for value in values)
            ):
                raise ValueError("probabilities must be finite and positive")
            rows.append(tuple(value / total for value in values))
        if not rows:
            raise ValueError("probability models must contain at least one event")
        if event_count is None:
            event_count = len(rows)
        elif len(rows) != event_count:
            raise ValueError("all probability models must have the same event count")
        normalized.append((name, tuple(rows)))
    return tuple(normalized)


def _validate_candidates(candidates: Sequence[str], event_count: int) -> None:
    if any(len(coupon) != event_count for coupon in candidates):
        raise ValueError("candidate and probability lengths must match")
    if any(set(coupon) - set(OUTCOMES) for coupon in candidates):
        raise ValueError("candidate outcomes must be 1, X, or 2")


def _build_workload(
    *,
    model_name: str,
    probabilities: ProbabilityMatrix,
    candidates: tuple[str, ...],
    candidate_index: Mapping[str, int],
    scenarios: Mapping[str, int],
    max_errors: int,
    deadline: float | None,
    time_func,
) -> _ModelWorkload | None:
    scenario_items = tuple(sorted(scenarios.items()))
    candidate_to_scenarios = [set() for _ in candidates]
    scenario_to_candidates: list[list[int]] = []
    for scenario_index, (scenario, _) in enumerate(scenario_items):
        if _expired(deadline, time_func):
            return None
        matches = sorted(
            {
                candidate_index[neighbor]
                for neighbor in neighbors_within_distance(scenario, max_errors)
                if neighbor in candidate_index
            }
        )
        scenario_to_candidates.append(matches)
        for index in matches:
            candidate_to_scenarios[index].add(scenario_index)
    weights = [weight for _, weight in scenario_items]
    return _ModelWorkload(
        name=model_name,
        probabilities=probabilities,
        weights=weights,
        candidate_to_scenarios=candidate_to_scenarios,
        scenario_to_candidates=scenario_to_candidates,
        marginal_scores=[
            sum(weights[scenario] for scenario in covered)
            for covered in candidate_to_scenarios
        ],
        total_weight=sum(weights),
        covered_scenarios=set(),
    )


def _apply_candidate(
    workload: _ModelWorkload,
    selected_index: int,
    selected_indexes: set[int],
) -> None:
    newly_covered = (
        workload.candidate_to_scenarios[selected_index]
        - workload.covered_scenarios
    )
    for scenario_index in newly_covered:
        workload.covered_scenarios.add(scenario_index)
        weight = workload.weights[scenario_index]
        workload.covered_weight += weight
        for affected in workload.scenario_to_candidates[scenario_index]:
            if affected not in selected_indexes:
                workload.marginal_scores[affected] -= weight


def _model_metrics(
    coupons: tuple[str, ...],
    workloads: Sequence[_ModelWorkload],
    event_count: int,
) -> tuple[RobustModelMetrics, ...]:
    result = []
    for workload in workloads:
        exact = (
            exact_category_probabilities(coupons, workload.probabilities)
            if event_count == 15 and coupons
            else (None, None, None)
        )
        result.append(
            RobustModelMetrics(
                model=workload.name,
                sampled_category_coverage=(
                    workload.covered_weight / workload.total_weight
                ),
                exact_p13=exact[0],
                exact_p14=exact[1],
                exact_p15=exact[2],
            )
        )
    return tuple(result)


def _empty_result(
    *,
    models: Sequence[tuple[str, ProbabilityMatrix]],
    candidate_count: int,
    sample_count: int,
    category: int,
    timed_out: bool = False,
) -> RobustPackageResult:
    metrics = tuple(
        RobustModelMetrics(name, 0.0, None, None, None) for name, _ in models
    )
    return RobustPackageResult(
        selected_coupons=(),
        model_metrics=metrics,
        worst_sampled_category_coverage=0.0,
        mean_sampled_category_coverage=0.0,
        candidate_count=candidate_count,
        sample_count_per_model=sample_count,
        category=category,
        timed_out=timed_out,
    )


def _model_seed(seed_material: str, model_name: str) -> int:
    digest = hashlib.sha256(f"{seed_material}\0{model_name}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _expired(deadline: float | None, time_func) -> bool:
    return deadline is not None and time_func() >= deadline
