from __future__ import annotations

import heapq
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

OUTCOMES = ("1", "X", "2")
OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}
ProbabilityMatrix = tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class CouponCategoryProbabilities:
    coupon: str
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float


@dataclass(frozen=True)
class BestCouponByP13(CouponCategoryProbabilities):
    package_position: int
    criterion: str = "maximum_probability_at_least_13"


def normalize_probability_matrix(
    rows: Sequence[Mapping[str, float]],
) -> ProbabilityMatrix:
    if not rows:
        raise ValueError("Probability matrix must contain at least one event.")

    normalized = []
    for row in rows:
        if any(outcome not in row for outcome in OUTCOMES):
            raise ValueError("Every event must contain outcomes 1, X, and 2.")
        values = tuple(float(row[outcome]) for outcome in OUTCOMES)
        total = sum(values)
        if not math.isfinite(total) or any(
            not math.isfinite(value) or value <= 0 for value in values
        ):
            raise ValueError(
                "Every event must contain finite positive probabilities."
            )
        normalized.append(tuple(value / total for value in values))

    return tuple(normalized)


def coupon_log_probability(
    coupon: str,
    probabilities: ProbabilityMatrix,
) -> float:
    if len(coupon) != len(probabilities):
        raise ValueError("Coupon and probability matrix lengths must match.")
    try:
        return sum(
            math.log(row[OUTCOME_INDEX[outcome]])
            for outcome, row in zip(coupon, probabilities, strict=True)
        )
    except KeyError as error:
        raise ValueError("Coupon outcomes must be 1, X, or 2.") from error


def coupon_category_probabilities(
    coupon: str,
    probabilities: ProbabilityMatrix,
) -> CouponCategoryProbabilities:
    """Return exact 13+/14+/15 probabilities for one 15-event coupon."""

    if len(probabilities) != 15 or len(coupon) != 15:
        raise ValueError("Coupon category probabilities require 15 events.")
    try:
        match_probabilities = tuple(
            row[OUTCOME_INDEX[outcome]]
            for outcome, row in zip(coupon, probabilities, strict=True)
        )
    except KeyError as error:
        raise ValueError("Coupon outcomes must be 1, X, or 2.") from error
    if any(
        not math.isfinite(probability) or not 0.0 <= probability <= 1.0
        for probability in match_probabilities
    ):
        raise ValueError("Coupon match probabilities must be finite in [0, 1].")

    distribution = [1.0] + [0.0] * 15
    for probability in match_probabilities:
        updated = [0.0] * 16
        for hits, mass in enumerate(distribution):
            updated[hits] += mass * (1.0 - probability)
            if hits < 15:
                updated[hits + 1] += mass * probability
        distribution = updated
    return CouponCategoryProbabilities(
        coupon=coupon,
        probability_at_least_13=math.fsum(distribution[13:]),
        probability_at_least_14=math.fsum(distribution[14:]),
        probability_at_least_15=distribution[15],
    )


def best_coupon_by_p13(
    coupons: Sequence[str],
    probabilities: ProbabilityMatrix,
) -> BestCouponByP13:
    """Rank package coupons explicitly; package order has no score semantics."""

    package = tuple(coupons)
    if not package:
        raise ValueError("Coupon package must not be empty.")
    if len(set(package)) != len(package):
        raise ValueError("Coupon package must contain unique coupons.")
    metrics = tuple(
        coupon_category_probabilities(coupon, probabilities) for coupon in package
    )
    selected = sorted(
        metrics,
        key=lambda row: (
            -row.probability_at_least_13,
            -row.probability_at_least_14,
            -row.probability_at_least_15,
            row.coupon,
        ),
    )[0]
    return BestCouponByP13(
        coupon=selected.coupon,
        probability_at_least_13=selected.probability_at_least_13,
        probability_at_least_14=selected.probability_at_least_14,
        probability_at_least_15=selected.probability_at_least_15,
        package_position=package.index(selected.coupon) + 1,
    )


def top_probability_coupons(
    probabilities: ProbabilityMatrix,
    limit: int,
) -> list[str]:
    if limit < 0:
        raise ValueError("limit must be non-negative.")
    if limit == 0:
        return []
    if not probabilities:
        raise ValueError("Probability matrix must contain at least one event.")

    ranked = tuple(
        tuple(
            sorted(
                zip(OUTCOMES, row, strict=True),
                key=lambda item: (-item[1], item[0]),
            )
        )
        for row in probabilities
    )

    def state_coupon(state: tuple[int, ...]) -> str:
        return "".join(
            ranked[position][rank][0] for position, rank in enumerate(state)
        )

    def state_log_probability(state: tuple[int, ...]) -> float:
        return sum(
            math.log(ranked[position][rank][1])
            for position, rank in enumerate(state)
        )

    start = (0,) * len(probabilities)
    start_coupon = state_coupon(start)
    heap = [(-state_log_probability(start), start_coupon, start)]
    seen = {start}
    coupons = []

    while heap and len(coupons) < limit:
        _, coupon, state = heapq.heappop(heap)
        coupons.append(coupon)

        for position, rank in enumerate(state):
            if rank + 1 == len(OUTCOMES):
                continue
            next_state = list(state)
            next_state[position] += 1
            next_state_tuple = tuple(next_state)
            if next_state_tuple in seen:
                continue
            seen.add(next_state_tuple)
            next_coupon = state_coupon(next_state_tuple)
            heapq.heappush(
                heap,
                (
                    -state_log_probability(next_state_tuple),
                    next_coupon,
                    next_state_tuple,
                ),
            )

    return coupons
