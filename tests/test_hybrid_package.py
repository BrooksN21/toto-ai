from math import ceil

import pytest

from toto_ai.optimizer import direct_package as direct_package_module
from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix
from toto_ai.optimizer.direct_package import (
    select_hybrid_package,
    select_weighted_package,
)


def test_hybrid_uses_exact_top_prefix_and_ceiling_core_size():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    top = ["1111", "111X", "11X1", "1X11"]
    result = select_hybrid_package(
        candidates=[*top, "XXXX", "2222"],
        scenarios={"1111": 10, "XXXX": 9, "2222": 8},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=top,
        core_fraction=0.50,
    )

    assert ceil(4 * 0.50) == 2
    assert result.selected_coupons[:2] == top[:2]
    assert len(result.selected_coupons) == 4


def test_production_core_sizes_are_fixed():
    assert [ceil(166 * value) for value in (0.50, 0.75, 0.90)] == [83, 125, 150]


def test_hybrid_fill_ignores_scenarios_already_covered_by_core():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 2
    )
    result = select_hybrid_package(
        candidates=["11", "1X", "XX", "22"],
        scenarios={"11": 100, "XX": 9, "22": 8},
        probabilities=probabilities,
        category=15,
        max_coupons=2,
        top_coupons=["11", "1X"],
        core_fraction=0.50,
    )

    assert result.selected_coupons == ["11", "XX"]
    assert result.covered_scenario_weight == 109
    assert result.estimated_coverage == pytest.approx(109 / 117)


def test_hybrid_is_unique_deterministic_and_does_not_mutate_inputs():
    candidates = ["11", "1X", "X1", "XX", "22"]
    scenarios = {"11": 4, "XX": 3, "22": 2}
    original_candidates = list(candidates)
    original_scenarios = dict(scenarios)
    kwargs = dict(
        candidates=candidates,
        scenarios=scenarios,
        probabilities=normalize_probability_matrix(
            [{"1": 50, "X": 30, "2": 20}] * 2
        ),
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
    )

    first = select_hybrid_package(**kwargs)
    second = select_hybrid_package(**kwargs)

    assert first == second
    assert len(first.selected_coupons) == len(set(first.selected_coupons)) == 4
    assert candidates == original_candidates
    assert scenarios == original_scenarios


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1])
def test_hybrid_rejects_invalid_fraction(fraction):
    with pytest.raises(ValueError, match="core_fraction"):
        select_hybrid_package(
            candidates=["1"],
            scenarios={"1": 1},
            probabilities=normalize_probability_matrix([{"1": 1, "X": 1, "2": 1}]),
            category=15,
            max_coupons=1,
            top_coupons=["1"],
            core_fraction=fraction,
        )


def test_hybrid_probability_fallback_is_unique_when_core_covers_all_scenarios():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    result = select_hybrid_package(
        candidates=["11", "1X", "1X", "X1", "X1", "XX"],
        scenarios={"11": 10},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
    )

    assert result.selected_coupons == ["11", "1X", "X1", "XX"]
    assert len(result.selected_coupons) == len(set(result.selected_coupons)) == 4


def test_hybrid_timeout_after_core_coverage_retains_core_without_probability_fallback():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    timestamps = iter([0.0, 2.0])

    result = select_hybrid_package(
        candidates=["11", "1X", "X1", "XX"],
        scenarios={"11": 10},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
        deadline=1.0,
        time_func=lambda: next(timestamps),
    )

    assert result.selected_coupons == ["11", "1X"]
    assert result.covered_scenario_weight == 0
    assert result.timed_out is True
    assert len(result.selected_coupons) < 4


def test_hybrid_timeout_during_probability_fallback_ranking_returns_partial_package():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    timestamps = iter([0.0, 0.0, 0.0, 2.0])

    result = select_hybrid_package(
        candidates=["11", "1X", "X1", "XX"],
        scenarios={"11": 10},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
        deadline=1.0,
        time_func=lambda: next(timestamps),
    )

    assert result.selected_coupons == ["11", "1X"]
    assert result.timed_out is True
    assert len(result.selected_coupons) < 4


def test_hybrid_retains_only_the_core_on_timeout_before_fill():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )

    result = select_hybrid_package(
        candidates=["11", "1X", "X1", "XX"],
        scenarios={"11": 4, "XX": 3},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
        deadline=1.0,
        time_func=lambda: 2.0,
    )

    assert result.selected_coupons == ["11", "1X"]
    assert result.covered_scenario_weight == 0
    assert result.timed_out is True


def test_hybrid_timeout_skips_post_deadline_exact_coverage(monkeypatch):
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    monkeypatch.setattr(
        direct_package_module,
        "_covered_scenario_weight",
        lambda *args: pytest.fail(
            "timed-out selection must not run exact coverage"
        ),
    )

    result = select_hybrid_package(
        candidates=["11", "1X", "X1", "XX"],
        scenarios={"11": 4, "XX": 3},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
        deadline=1.0,
        time_func=lambda: 2.0,
    )

    assert result.selected_coupons == ["11", "1X"]
    assert result.covered_scenario_weight == 0
    assert result.timed_out is True


def test_existing_weighted_selector_output_is_unchanged():
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
