import math

import numpy as np
import pytest

from toto_ai.ev.reference import (
    brute_force_gross_ev,
    coupon_payout,
    crowd_qualifying_stake,
    joint_distribution,
)


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


@pytest.mark.parametrize(
    "row, message",
    [
        ((2.0, 0.0, 0.0), "sum to 1"),
        ((0.5, 0.5, 0.5), "sum to 1"),
        ((math.nan, 0.5, 0.5), "finite and non-negative"),
        ((-0.1, 0.6, 0.5), "finite and non-negative"),
        ((0.5, 0.5), "exactly three values"),
    ],
)
def test_joint_distribution_rejects_invalid_probability_rows(row, message):
    with pytest.raises(ValueError, match=message):
        joint_distribution((row,))


@pytest.mark.parametrize("delta", [-0.5e-12, 0.5e-12])
def test_joint_distribution_accepts_probability_sum_within_tolerance(delta):
    result = joint_distribution(((1.0 + delta, 0.0, 0.0),))
    assert np.isclose(result.sum(), 1.0 + delta)


@pytest.mark.parametrize("matrix_name", ["true", "crowd"])
def test_reference_rejects_invalid_probability_rows_in_either_input(matrix_name):
    matrices = {
        "true": ((2.0, 0.0, 0.0),),
        "crowd": ((2.0, 0.0, 0.0),),
    }
    kwargs = {
        "true_probabilities": matrices["true"],
        "crowd_probabilities": matrices["crowd"],
        "pool_sum": 100.0,
        "stake": 10,
        "category_funds_by_hits": {1: 10.0},
        "minimum_category": 1,
    }
    kwargs[f"{matrix_name}_probabilities"] = ((0.5, 0.25, 0.25),)
    with pytest.raises(ValueError, match="sum to 1"):
        brute_force_gross_ev(**kwargs)


def test_reference_rejects_category_above_event_count_before_enumeration():
    with pytest.raises(ValueError, match=r"^category 2 must be in 1\.\.1$"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0),),
            crowd_probabilities=((0.5, 0.25, 0.25),),
            pool_sum=100.0,
            stake=10,
            category_funds_by_hits={2: 10.0},
            minimum_category=1,
        )


def test_reference_rejects_category_below_minimum_with_exact_range_error():
    with pytest.raises(ValueError, match=r"^category 1 must be in 2\.\.2$"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            crowd_probabilities=((0.5, 0.25, 0.25), (0.5, 0.25, 0.25)),
            pool_sum=100.0,
            stake=10,
            category_funds_by_hits={1: 10.0},
            minimum_category=2,
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


@pytest.mark.parametrize("fund", [-1.0, math.nan, math.inf])
def test_coupon_payout_rejects_invalid_category_funds(fund):
    with pytest.raises(
        ValueError,
        match="category funds must be finite and non-negative",
    ):
        coupon_payout(
            coupon=(0,),
            actual=(0,),
            category_funds_by_hits={1: fund},
            qualifying_stake={1: 100.0},
            stake=10,
        )


@pytest.mark.parametrize("category", [0, 2, True])
def test_coupon_payout_rejects_categories_outside_hit_range(category):
    with pytest.raises(ValueError, match=r"^category .+ must be in 1\.\.1$"):
        coupon_payout(
            coupon=(0,),
            actual=(0,),
            category_funds_by_hits={category: 10.0},
            qualifying_stake={category: 100.0},
            stake=10,
        )


@pytest.mark.parametrize("stake", [0, -1, 1.5, True])
def test_coupon_payout_rejects_invalid_stake(stake):
    with pytest.raises(ValueError, match="stake must be a positive int"):
        coupon_payout(
            coupon=(0,),
            actual=(0,),
            category_funds_by_hits={1: 10.0},
            qualifying_stake={1: 100.0},
            stake=stake,
        )


@pytest.mark.parametrize("denominator", [0.0, -1.0, math.nan, math.inf])
def test_coupon_payout_rejects_invalid_qualifying_stakes(denominator):
    with pytest.raises(
        ValueError,
        match="qualifying stake must be finite and positive",
    ):
        coupon_payout(
            coupon=(0,),
            actual=(0,),
            category_funds_by_hits={1: 10.0},
            qualifying_stake={1: denominator},
            stake=10,
        )


def test_coupon_payout_requires_a_qualifying_stake_for_every_category():
    with pytest.raises(ValueError, match="qualifying stake missing for category 2"):
        coupon_payout(
            coupon=(0, 0),
            actual=(0, 0),
            category_funds_by_hits={1: 10.0, 2: 10.0},
            qualifying_stake={1: 100.0},
            stake=10,
        )


def test_public_helpers_reject_bool_where_int_is_required():
    with pytest.raises(ValueError, match="category must be a positive int"):
        crowd_qualifying_stake(
            crowd_joint=(1.0,),
            states=((0,),),
            actual=(0,),
            pool_sum=100.0,
            category=True,
        )

    with pytest.raises(ValueError, match="stake must be a positive int"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0),),
            crowd_probabilities=((1.0, 0.0, 0.0),),
            pool_sum=100.0,
            stake=True,
            category_funds_by_hits={1: 10.0},
            minimum_category=1,
        )

    with pytest.raises(ValueError, match="minimum_category must be a positive int"):
        brute_force_gross_ev(
            true_probabilities=((1.0, 0.0, 0.0),),
            crowd_probabilities=((1.0, 0.0, 0.0),),
            pool_sum=100.0,
            stake=10,
            category_funds_by_hits={1: 10.0},
            minimum_category=True,
        )
