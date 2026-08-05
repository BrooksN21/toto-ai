import pytest

from toto_ai.optimizer.coupon_candidates import (
    generate_candidate_coupons,
    sample_scenarios,
)
from toto_ai.optimizer.coupon_probabilities import (
    normalize_probability_matrix,
    top_probability_coupons,
)


def test_sample_scenarios_is_deterministic_and_preserves_count():
    probabilities = normalize_probability_matrix(
        [{"1": 70, "X": 20, "2": 10}, {"1": 10, "X": 20, "2": 70}]
    )

    first = sample_scenarios(probabilities, count=100, seed=17)
    second = sample_scenarios(probabilities, count=100, seed=17)

    assert first == second
    assert sum(first.values()) == 100
    assert all(len(scenario) == 2 for scenario in first)


def test_sample_scenarios_rejects_non_positive_count():
    probabilities = normalize_probability_matrix([{"1": 70, "X": 20, "2": 10}])

    with pytest.raises(ValueError, match="count must be positive"):
        sample_scenarios(probabilities, count=0, seed=17)


def test_generate_candidates_contains_top_package_and_is_deterministic():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    expected_top = top_probability_coupons(probabilities, limit=3)

    first = generate_candidate_coupons(
        probabilities,
        max_coupons=3,
        top_count=5,
        sample_count=20,
        mutation_limit=8,
        seed=9,
    )
    second = generate_candidate_coupons(
        probabilities,
        max_coupons=3,
        top_count=5,
        sample_count=20,
        mutation_limit=8,
        seed=9,
    )

    assert first == second
    assert first[:3] == expected_top
    assert len(first) == len(set(first))
    assert "1111" in first


def test_generate_candidates_validates_limits():
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}])

    with pytest.raises(ValueError, match="max_coupons must be positive"):
        generate_candidate_coupons(probabilities, max_coupons=0)
    with pytest.raises(ValueError, match="top_count must be at least max_coupons"):
        generate_candidate_coupons(
            probabilities,
            max_coupons=2,
            top_count=1,
        )
    with pytest.raises(ValueError, match="mutation_limit must be non-negative"):
        generate_candidate_coupons(
            probabilities,
            max_coupons=1,
            mutation_limit=-1,
        )
