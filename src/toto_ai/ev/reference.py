"""Independent brute-force expected-value calculations for small spaces."""

import itertools
import math
from collections.abc import Mapping, Sequence

import numpy as np

from toto_ai.ev.models import ProbabilityMatrix

MAX_REFERENCE_EVENTS = 8
PROBABILITY_SUM_RTOL = 1e-12
PROBABILITY_SUM_ATOL = 1e-12


def _validated_matrix(
    matrix: ProbabilityMatrix,
    name: str,
) -> tuple[tuple[float, float, float], ...]:
    rows = tuple(tuple(row) for row in matrix)
    event_count = len(rows)
    if event_count == 0:
        raise ValueError(f"{name} must contain at least one event")
    if event_count > MAX_REFERENCE_EVENTS:
        raise ValueError(
            f"reference oracle supports at most {MAX_REFERENCE_EVENTS} events",
        )

    validated: list[tuple[float, float, float]] = []
    for row in rows:
        if len(row) != 3:
            raise ValueError(f"{name} rows must contain exactly three values")
        values = tuple(float(value) for value in row)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError(f"{name} probabilities must be finite and non-negative")
        if not math.isclose(
            sum(values),
            1.0,
            rel_tol=PROBABILITY_SUM_RTOL,
            abs_tol=PROBABILITY_SUM_ATOL,
        ):
            raise ValueError(
                f"{name} rows must sum to 1 within rtol={PROBABILITY_SUM_RTOL} "
                f"and atol={PROBABILITY_SUM_ATOL}",
            )
        validated.append(values)
    return tuple(validated)


def _states(event_count: int) -> tuple[tuple[int, ...], ...]:
    return tuple(itertools.product(range(3), repeat=event_count))


def joint_distribution(matrix: ProbabilityMatrix) -> np.ndarray:
    """Return the independent joint distribution in deterministic C order."""
    validated = _validated_matrix(matrix, "probability matrix")
    states = _states(len(validated))
    return np.array(
        [
            math.prod(
                row[outcome]
                for row, outcome in zip(validated, state, strict=True)
            )
            for state in states
        ],
        dtype=np.float64,
    )


def coupon_hits(coupon: Sequence[int], actual: Sequence[int]) -> int:
    """Count matching event positions between a coupon and an actual result."""
    if len(coupon) != len(actual):
        raise ValueError("coupon and actual must have the same event count")
    return sum(left == right for left, right in zip(coupon, actual, strict=True))


def crowd_qualifying_stake(
    crowd_joint: Sequence[float],
    states: Sequence[Sequence[int]],
    actual: Sequence[int],
    pool_sum: float,
    category: int,
) -> float:
    """Return modeled crowd stake whose coupons qualify for a category."""
    if type(category) is not int or category <= 0:
        raise ValueError("category must be a positive int")
    qualifying_probability = sum(
        probability
        for probability, ticket in zip(crowd_joint, states, strict=True)
        if coupon_hits(ticket, actual) >= category
    )
    qualifying_stake = float(pool_sum) * float(qualifying_probability)
    if not math.isfinite(qualifying_stake) or qualifying_stake <= 0:
        raise ValueError("qualifying stake must be finite and positive")
    return qualifying_stake


def coupon_payout(
    coupon: Sequence[int],
    actual: Sequence[int],
    category_funds_by_hits: Mapping[int, float],
    qualifying_stake: Mapping[int, float],
    stake: int,
) -> float:
    """Return a coupon's payout for one actual result."""
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive int")
    event_count = len(actual)
    funds = _validated_category_funds(
        category_funds_by_hits,
        minimum_category=1,
        event_count=event_count,
    )
    validated_stakes: dict[int, float] = {}
    for category in funds:
        if category not in qualifying_stake:
            raise ValueError(f"qualifying stake missing for category {category}")
        validated_stakes[category] = _positive_denominator(qualifying_stake[category])
    hits = coupon_hits(coupon, actual)
    return sum(
        funds[category] * stake / validated_stakes[category]
        for category in funds
        if category <= hits
    )


def _positive_denominator(value: float) -> float:
    denominator = float(value)
    if not math.isfinite(denominator) or denominator <= 0:
        raise ValueError("qualifying stake must be finite and positive")
    return denominator


def _validated_category_funds(
    category_funds_by_hits: Mapping[int, float],
    minimum_category: int,
    event_count: int,
) -> dict[int, float]:
    if type(minimum_category) is not int or minimum_category <= 0:
        raise ValueError("minimum_category must be a positive int")
    if minimum_category > event_count:
        raise ValueError("minimum_category must not exceed event_count")
    if not category_funds_by_hits:
        raise ValueError("category_funds_by_hits must not be empty")

    validated: dict[int, float] = {}
    for category, fund in category_funds_by_hits.items():
        if (
            type(category) is not int
            or category < minimum_category
            or category > event_count
        ):
            raise ValueError(
                f"category {category} must be in {minimum_category}..{event_count}",
            )
        value = float(fund)
        if not math.isfinite(value) or value < 0:
            raise ValueError("category funds must be finite and non-negative")
        validated[category] = value
    return validated


def brute_force_gross_ev(
    true_probabilities: ProbabilityMatrix,
    crowd_probabilities: ProbabilityMatrix,
    pool_sum: float,
    stake: int,
    category_funds_by_hits: Mapping[int, float],
    minimum_category: int,
) -> np.ndarray:
    """Exhaustively calculate modeled gross EV for every coupon state."""
    true_matrix = _validated_matrix(true_probabilities, "true probabilities")
    crowd_matrix = _validated_matrix(crowd_probabilities, "crowd probabilities")
    if len(true_matrix) != len(crowd_matrix):
        raise ValueError("true and crowd probabilities must have the same event count")
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive int")
    funds = _validated_category_funds(
        category_funds_by_hits,
        minimum_category,
        event_count=len(true_matrix),
    )

    states = _states(len(true_matrix))
    true_joint = joint_distribution(true_matrix)
    crowd_joint = joint_distribution(crowd_matrix)
    gross_ev = np.zeros(len(states), dtype=np.float64)

    for actual_index, actual in enumerate(states):
        actual_probability = true_joint[actual_index]
        qualifying_stake = {
            category: crowd_qualifying_stake(
                crowd_joint,
                states,
                actual,
                pool_sum,
                category,
            )
            for category in funds
        }
        for coupon_index, coupon in enumerate(states):
            hits = coupon_hits(coupon, actual)
            payout = sum(
                funds[category] * stake / qualifying_stake[category]
                for category in funds
                if category <= hits
            )
            gross_ev[coupon_index] += actual_probability * payout / stake
    return gross_ev
