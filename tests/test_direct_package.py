import pytest

from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix
from toto_ai.optimizer.direct_package import (
    estimate_package_coverage,
    neighbors_within_distance,
    select_weighted_package,
)


def test_neighbors_within_distance_has_expected_radius_sizes():
    assert len(set(neighbors_within_distance("111", 0))) == 1
    assert len(set(neighbors_within_distance("111", 1))) == 7
    assert len(set(neighbors_within_distance("111", 2))) == 19

    with pytest.raises(ValueError, match="max_errors must be non-negative"):
        list(neighbors_within_distance("111", -1))


def test_weighted_package_selects_largest_new_mass_then_probability():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 3
    )
    scenarios = {"111": 40, "XXX": 35, "222": 25}

    result = select_weighted_package(
        candidates=["XXX", "111", "222"],
        scenarios=scenarios,
        probabilities=probabilities,
        category=15,
        max_coupons=2,
    )

    assert result.selected_coupons == ["111", "XXX"]
    assert result.covered_scenario_weight == 75
    assert result.estimated_coverage == 0.75


def test_weighted_package_respects_coupon_limit_and_validation_is_exact():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 3
    )
    result = select_weighted_package(
        candidates=["111", "XXX", "222"],
        scenarios={"111": 1, "XXX": 1, "222": 1},
        probabilities=probabilities,
        category=15,
        max_coupons=1,
    )

    assert len(result.selected_coupons) == 1
    assert estimate_package_coverage(
        result.selected_coupons,
        {"111": 2, "XXX": 1},
        category=15,
    ) == 2 / 3


def test_weighted_package_uses_probability_then_lexical_tie_breaks():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    result = select_weighted_package(
        candidates=["X1", "1X", "22"],
        scenarios={"X1": 1, "1X": 1, "22": 1},
        probabilities=probabilities,
        category=15,
        max_coupons=1,
    )

    assert result.selected_coupons == ["1X"]


def test_weighted_package_recalculates_overlapping_marginal_scores():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )

    result = select_weighted_package(
        candidates=["22", "11", "XX"],
        scenarios={"11": 5, "12": 4, "22": 3, "XX": 4},
        probabilities=probabilities,
        category=14,
        max_coupons=2,
    )

    assert result.selected_coupons == ["11", "XX"]
    assert result.covered_scenario_weight == 13


def test_weighted_package_retains_partial_result_on_timeout():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    timestamps = iter([0.0, 0.0, 0.0, 0.0, 0.0, 2.0])

    result = select_weighted_package(
        candidates=["22", "11", "XX"],
        scenarios={"11": 5, "12": 4, "22": 3, "XX": 4},
        probabilities=probabilities,
        category=14,
        max_coupons=3,
        deadline=1.0,
        time_func=lambda: next(timestamps),
    )

    assert result.selected_coupons == ["11"]
    assert result.covered_scenario_weight == 9
    assert result.timed_out is True


def test_weighted_package_validates_inputs():
    probabilities = normalize_probability_matrix([{"1": 50, "X": 30, "2": 20}])

    with pytest.raises(ValueError, match="max_coupons must be non-negative"):
        select_weighted_package([], {}, probabilities, category=13, max_coupons=-1)
    with pytest.raises(ValueError, match="lengths must match"):
        select_weighted_package(["11"], {}, probabilities, category=13, max_coupons=1)
    with pytest.raises(ValueError, match="weights must be positive"):
        select_weighted_package(["1"], {"1": 0}, probabilities, 13, 1)
    with pytest.raises(ValueError, match="Candidate outcomes"):
        select_weighted_package(["A"], {"1": 1}, probabilities, 13, 1)
    with pytest.raises(ValueError, match="Scenario and probability lengths"):
        select_weighted_package(["1"], {"11": 1}, probabilities, 13, 1)
    with pytest.raises(ValueError, match="Scenario outcomes"):
        select_weighted_package(["1"], {"A": 1}, probabilities, 13, 1)
