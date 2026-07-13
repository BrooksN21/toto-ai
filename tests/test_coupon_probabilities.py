import math
from itertools import product

import pytest

from toto_ai.optimizer.coupon_probabilities import (
    coupon_log_probability,
    normalize_probability_matrix,
    top_probability_coupons,
)


def test_normalize_probability_matrix_uses_fixed_outcome_order():
    matrix = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}, {"1": 2, "X": 3, "2": 5}]
    )

    assert matrix == ((0.5, 0.3, 0.2), (0.2, 0.3, 0.5))
    assert coupon_log_probability("12", matrix) == pytest.approx(
        math.log(0.5) + math.log(0.5)
    )


def test_normalize_probability_matrix_rejects_missing_or_non_positive_rows():
    with pytest.raises(ValueError, match="positive probabilities"):
        normalize_probability_matrix([{"1": 0, "X": 0, "2": 0}])
    with pytest.raises(ValueError, match="outcomes 1, X, and 2"):
        normalize_probability_matrix([{"1": 50, "X": 50}])


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_normalize_probability_matrix_rejects_non_finite_values(invalid):
    with pytest.raises(ValueError, match="finite positive probabilities"):
        normalize_probability_matrix([{"1": invalid, "X": 30, "2": 20}])


def test_top_probability_coupons_returns_exact_probability_order():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}, {"1": 50, "X": 20, "2": 30}]
    )

    assert top_probability_coupons(probabilities, limit=4) == [
        "11",
        "12",
        "X1",
        "1X",
    ]


def test_top_probability_coupons_is_deterministic_on_ties():
    probabilities = normalize_probability_matrix(
        [{"1": 1, "X": 1, "2": 1}, {"1": 1, "X": 1, "2": 1}]
    )

    assert top_probability_coupons(probabilities, limit=4) == [
        "11",
        "12",
        "1X",
        "21",
    ]


@pytest.mark.parametrize("limit", [1, 4, 9, 20])
def test_top_probability_coupons_matches_exhaustive_order(limit):
    probabilities = normalize_probability_matrix(
        [{"1": 5, "X": 3, "2": 2}, {"1": 2, "X": 4, "2": 4}]
    )
    exhaustive = sorted(
        ("".join(outcomes) for outcomes in product("1X2", repeat=2)),
        key=lambda coupon: (
            -coupon_log_probability(coupon, probabilities),
            coupon,
        ),
    )

    assert top_probability_coupons(probabilities, limit=limit) == exhaustive[:limit]
