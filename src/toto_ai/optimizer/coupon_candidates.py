from __future__ import annotations

from collections import Counter
from random import Random

from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    coupon_log_probability,
    top_probability_coupons,
)


def sample_scenarios(
    probabilities: ProbabilityMatrix,
    count: int,
    seed: int,
) -> dict[str, int]:
    if count <= 0:
        raise ValueError("count must be positive.")

    rng = Random(seed)
    scenarios = Counter()
    for _ in range(count):
        outcomes = []
        for row in probabilities:
            draw = rng.random()
            cumulative = 0.0
            for outcome, probability in zip(OUTCOMES, row, strict=True):
                cumulative += probability
                if draw <= cumulative:
                    outcomes.append(outcome)
                    break
            else:
                outcomes.append(OUTCOMES[-1])
        scenarios["".join(outcomes)] += 1

    return dict(sorted(scenarios.items()))


def generate_candidate_coupons(
    probabilities: ProbabilityMatrix,
    max_coupons: int,
    top_count: int = 1000,
    sample_count: int = 3000,
    mutation_limit: int = 1000,
    seed: int = 42,
) -> list[str]:
    if max_coupons <= 0:
        raise ValueError("max_coupons must be positive.")
    if top_count < max_coupons:
        raise ValueError("top_count must be at least max_coupons.")
    if mutation_limit < 0:
        raise ValueError("mutation_limit must be non-negative.")

    top = top_probability_coupons(probabilities, limit=top_count)
    sampled = sample_scenarios(probabilities, count=sample_count, seed=seed)
    sampled_order = sorted(
        sampled,
        key=lambda coupon: (
            -sampled[coupon],
            -coupon_log_probability(coupon, probabilities),
            coupon,
        ),
    )

    mutations = set()
    for coupon in top:
        for position, current in enumerate(coupon):
            for replacement in OUTCOMES:
                if replacement == current:
                    continue
                mutations.add(
                    coupon[:position] + replacement + coupon[position + 1 :]
                )
    mutation_order = sorted(
        mutations,
        key=lambda coupon: (
            -coupon_log_probability(coupon, probabilities),
            coupon,
        ),
    )[:mutation_limit]

    ordered = [*top, *sampled_order, *mutation_order]
    return list(dict.fromkeys(ordered))
