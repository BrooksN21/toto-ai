from __future__ import annotations

import heapq
import math
import time
from collections.abc import Iterator
from dataclasses import dataclass

from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    coupon_log_probability,
)
from toto_ai.optimizer.cover import category_max_errors


@dataclass(frozen=True)
class DirectPackageResult:
    selected_coupons: list[str]
    covered_scenario_weight: int
    total_scenario_weight: int
    estimated_coverage: float
    timed_out: bool


def neighbors_within_distance(value: str, max_errors: int) -> Iterator[str]:
    if not isinstance(max_errors, int) or max_errors < 0:
        raise ValueError("max_errors must be non-negative.")

    chars = list(value)
    yield value

    def mutate(start: int, remaining: int) -> Iterator[str]:
        if remaining == 0:
            return
        for position in range(start, len(chars)):
            original = chars[position]
            for replacement in OUTCOMES:
                if replacement == original:
                    continue
                chars[position] = replacement
                yield "".join(chars)
                yield from mutate(position + 1, remaining - 1)
            chars[position] = original

    yield from mutate(0, max_errors)


def select_weighted_package(
    candidates: list[str],
    scenarios: dict[str, int],
    probabilities: ProbabilityMatrix,
    category: int,
    max_coupons: int,
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> DirectPackageResult:
    if max_coupons < 0:
        raise ValueError("max_coupons must be non-negative.")
    if any(len(coupon) != len(probabilities) for coupon in candidates):
        raise ValueError("Candidate and probability lengths must match.")
    if any(set(coupon) - set(OUTCOMES) for coupon in candidates):
        raise ValueError("Candidate outcomes must be 1, X, or 2.")
    if any(len(scenario) != len(probabilities) for scenario in scenarios):
        raise ValueError("Scenario and probability lengths must match.")
    if any(set(scenario) - set(OUTCOMES) for scenario in scenarios):
        raise ValueError("Scenario outcomes must be 1, X, or 2.")
    if any(weight <= 0 for weight in scenarios.values()):
        raise ValueError("Scenario weights must be positive.")

    unique_candidates = list(dict.fromkeys(candidates))
    scenario_items = sorted(scenarios.items())
    total_weight = sum(weight for _, weight in scenario_items)
    if not unique_candidates or not scenario_items or max_coupons == 0:
        return DirectPackageResult([], 0, total_weight, 0.0, False)

    max_errors = category_max_errors(category)
    candidate_index = {
        coupon: index for index, coupon in enumerate(unique_candidates)
    }
    candidate_to_scenarios = [set() for _ in unique_candidates]
    scenario_to_candidates = []

    for scenario_index, (scenario, _) in enumerate(scenario_items):
        if deadline is not None and time_func() >= deadline:
            return DirectPackageResult([], 0, total_weight, 0.0, True)
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
    scores = [
        sum(weights[scenario] for scenario in covered)
        for covered in candidate_to_scenarios
    ]
    log_probabilities = [
        coupon_log_probability(coupon, probabilities)
        for coupon in unique_candidates
    ]
    versions = [0] * len(unique_candidates)
    selected_indexes = set()
    selected_order = []
    covered_scenarios = set()
    heap = [
        (
            -scores[index],
            -log_probabilities[index],
            coupon,
            versions[index],
            index,
        )
        for index, coupon in enumerate(unique_candidates)
    ]
    heapq.heapify(heap)

    timed_out = False
    while heap and len(selected_indexes) < max_coupons:
        if deadline is not None and time_func() >= deadline:
            timed_out = True
            break
        negative_score, _, _, version, index = heapq.heappop(heap)
        if index in selected_indexes or version != versions[index]:
            continue
        if -negative_score <= 0:
            break

        selected_indexes.add(index)
        selected_order.append(index)
        newly_covered = candidate_to_scenarios[index] - covered_scenarios
        for scenario_index in newly_covered:
            covered_scenarios.add(scenario_index)
            weight = weights[scenario_index]
            for affected in scenario_to_candidates[scenario_index]:
                if affected in selected_indexes:
                    continue
                scores[affected] -= weight
                versions[affected] += 1
                heapq.heappush(
                    heap,
                    (
                        -scores[affected],
                        -log_probabilities[affected],
                        unique_candidates[affected],
                        versions[affected],
                        affected,
                    ),
                )

    if not timed_out and len(selected_indexes) < max_coupons:
        remaining = sorted(
            (
                index
                for index in range(len(unique_candidates))
                if index not in selected_indexes
            ),
            key=lambda index: (
                -log_probabilities[index],
                unique_candidates[index],
            ),
        )
        for index in remaining:
            if len(selected_indexes) == max_coupons:
                break
            if deadline is not None and time_func() >= deadline:
                timed_out = True
                break
            selected_indexes.add(index)
            selected_order.append(index)

    selected = [unique_candidates[index] for index in selected_order]
    covered_weight = sum(weights[index] for index in covered_scenarios)
    return DirectPackageResult(
        selected_coupons=selected,
        covered_scenario_weight=covered_weight,
        total_scenario_weight=total_weight,
        estimated_coverage=covered_weight / total_weight,
        timed_out=timed_out,
    )


def select_hybrid_package(
    candidates: list[str],
    scenarios: dict[str, int],
    probabilities: ProbabilityMatrix,
    category: int,
    max_coupons: int,
    top_coupons: list[str],
    core_fraction: float,
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> DirectPackageResult:
    if not 0.0 < core_fraction <= 1.0:
        raise ValueError("core_fraction must be in (0, 1].")
    if max_coupons < 0:
        raise ValueError("max_coupons must be non-negative.")
    if len(top_coupons) < max_coupons:
        raise ValueError("top_coupons must contain max_coupons coupons.")
    if any(len(coupon) != len(probabilities) for coupon in top_coupons):
        raise ValueError("Top coupon and probability lengths must match.")
    if any(set(coupon) - set(OUTCOMES) for coupon in top_coupons):
        raise ValueError("Top coupon outcomes must be 1, X, or 2.")

    core_size = math.ceil(max_coupons * core_fraction)
    core = list(top_coupons[:core_size])
    if len(set(core)) != len(core):
        raise ValueError("Hybrid core coupons must be unique.")

    core_set = set(core)
    max_errors = category_max_errors(category)
    uncovered = {}
    for scenario, weight in scenarios.items():
        if deadline is not None and time_func() >= deadline:
            total_weight = sum(scenarios.values())
            return DirectPackageResult(
                core,
                0,
                total_weight,
                0.0,
                True,
            )
        if not any(
            neighbor in core_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        ):
            uncovered[scenario] = weight

    fill = select_weighted_package(
        candidates=[coupon for coupon in candidates if coupon not in core_set],
        scenarios=uncovered,
        probabilities=probabilities,
        category=category,
        max_coupons=max_coupons - core_size,
        deadline=deadline,
        time_func=time_func,
    )
    selected = [*core, *fill.selected_coupons]
    timed_out = fill.timed_out
    if not timed_out and len(selected) < max_coupons:
        if deadline is not None and time_func() >= deadline:
            timed_out = True
        else:
            selected_set = set(selected)
            ranked_remaining = []
            for coupon in dict.fromkeys(candidates):
                if coupon in selected_set:
                    continue
                if deadline is not None and time_func() >= deadline:
                    timed_out = True
                    break
                ranked_remaining.append(
                    (-coupon_log_probability(coupon, probabilities), coupon)
                )
            if not timed_out:
                remaining = [coupon for _, coupon in sorted(ranked_remaining)]
                if deadline is not None and time_func() >= deadline:
                    timed_out = True
                else:
                    for coupon in remaining:
                        if len(selected) == max_coupons:
                            break
                        if deadline is not None and time_func() >= deadline:
                            timed_out = True
                            break
                        selected.append(coupon)
    total_weight = sum(scenarios.values())
    if timed_out:
        covered_weight = 0
    else:
        covered_weight = _covered_scenario_weight(selected, scenarios, category)
    return DirectPackageResult(
        selected_coupons=selected,
        covered_scenario_weight=covered_weight,
        total_scenario_weight=total_weight,
        estimated_coverage=(covered_weight / total_weight if total_weight else 0.0),
        timed_out=timed_out,
    )


def _covered_scenario_weight(
    coupons: list[str], scenarios: dict[str, int], category: int
) -> int:
    coupon_set = set(coupons)
    max_errors = category_max_errors(category)
    return sum(
        weight
        for scenario, weight in scenarios.items()
        if any(
            neighbor in coupon_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        )
    )


def estimate_package_coverage(
    coupons: list[str],
    scenarios: dict[str, int],
    category: int,
) -> float:
    lengths = {len(value) for value in [*coupons, *scenarios]}
    if len(lengths) > 1:
        raise ValueError("Coupon and scenario lengths must match.")
    if any(set(value) - set(OUTCOMES) for value in [*coupons, *scenarios]):
        raise ValueError("Coupon and scenario outcomes must be 1, X, or 2.")
    if any(weight <= 0 for weight in scenarios.values()):
        raise ValueError("Scenario weights must be positive.")

    coupon_set = set(coupons)
    max_errors = category_max_errors(category)
    total = sum(scenarios.values())
    if total == 0:
        return 0.0
    covered = sum(
        weight
        for scenario, weight in scenarios.items()
        if any(
            neighbor in coupon_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        )
    )
    return covered / total
