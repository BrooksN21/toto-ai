import math

import numpy as np
import pytest

from toto_ai.ev.reference import brute_force_gross_ev, joint_distribution


def test_joint_distribution_uses_lexicographic_base_three_order():
    matrix = ((0.5, 0.3, 0.2), (0.6, 0.25, 0.15))
    result = joint_distribution(matrix)
    assert np.allclose(result[:3], [0.30, 0.125, 0.075])
    assert np.isclose(result.sum(), 1.0)


def test_one_event_reference_ev_matches_direct_manual_sum():
    true = ((0.5, 0.3, 0.2),)
    crowd = ((0.4, 0.35, 0.25),)
    funds = {1: 90.0}
    result = brute_force_gross_ev(
        true_probabilities=true,
        crowd_probabilities=crowd,
        pool_sum=300.0,
        stake=30,
        category_funds_by_hits=funds,
        minimum_category=1,
    )
    assert np.allclose(result, [0.375, 0.2571428571428571, 0.24])


def test_cumulative_categories_add_for_higher_hit_coupon():
    true = ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    crowd = ((0.5, 0.25, 0.25), (0.5, 0.25, 0.25))
    result = brute_force_gross_ev(
        true_probabilities=true,
        crowd_probabilities=crowd,
        pool_sum=120.0,
        stake=30,
        category_funds_by_hits={1: 60.0, 2: 60.0},
        minimum_category=1,
    )
    assert np.isclose(result[0], 8 / 3)


@pytest.mark.parametrize("event_count", range(1, 5))
def test_reference_randomized_invariants(event_count):
    rng = np.random.default_rng(42 + event_count)
    true = tuple(tuple(rng.dirichlet([1.0, 1.0, 1.0])) for _ in range(event_count))
    crowd = tuple(tuple(rng.dirichlet([1.0, 1.0, 1.0])) for _ in range(event_count))
    result = brute_force_gross_ev(
        true_probabilities=true,
        crowd_probabilities=crowd,
        pool_sum=1_000.0,
        stake=30,
        category_funds_by_hits={1: 60.0},
        minimum_category=1,
    )
    assert np.isfinite(result).all()
    assert (result >= 0).all()
    assert np.isclose(joint_distribution(true).sum(), 1.0)
    assert np.isclose(joint_distribution(crowd).sum(), 1.0)


def test_reference_allows_zero_probabilities():
    result = brute_force_gross_ev(
        true_probabilities=((1.0, 0.0, 0.0),),
        crowd_probabilities=((0.5, 0.25, 0.25),),
        pool_sum=100.0,
        stake=10,
        category_funds_by_hits={1: 10.0},
        minimum_category=1,
    )
    assert np.isfinite(result).all()
    assert np.isclose(result[0], 0.2)
    assert np.allclose(result[1:], 0.0)


def test_reference_rejects_non_positive_category_denominator():
    with pytest.raises(ValueError, match="qualifying stake"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0),),
            crowd_probabilities=((1.0, 0.0, 0.0),),
            pool_sum=100.0,
            stake=10,
            category_funds_by_hits={2: 10.0},
            minimum_category=1,
        )


def test_reference_rejects_non_finite_category_denominator():
    with pytest.raises(ValueError, match="qualifying stake"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0),),
            crowd_probabilities=((1.0, 0.0, 0.0),),
            pool_sum=math.inf,
            stake=10,
            category_funds_by_hits={1: 10.0},
            minimum_category=1,
        )


def test_reference_rejects_more_than_eight_events():
    probabilities = ((1 / 3, 1 / 3, 1 / 3),) * 9
    with pytest.raises(ValueError, match="at most 8 events"):
        brute_force_gross_ev(
            true_probabilities=probabilities,
            crowd_probabilities=probabilities,
            pool_sum=100.0,
            stake=10,
            category_funds_by_hits={1: 10.0},
            minimum_category=1,
        )
