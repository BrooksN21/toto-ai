import inspect

import pytest

from toto_ai.optimizer import strategy_backtest as strategy_module
from toto_ai.optimizer.brief import EventBriefAnalysis
from toto_ai.optimizer.coupon_probabilities import (
    normalize_probability_matrix,
    top_probability_coupons,
)
from toto_ai.optimizer.direct_package import DirectPackageResult
from toto_ai.optimizer.strategy_backtest import (
    StrategyConfig,
    build_packages_for_probabilities,
)


def test_strategy_package_builder_has_no_actual_result_input():
    assert "result" not in inspect.signature(
        build_packages_for_probabilities
    ).parameters


def test_strategy_packages_share_budget_and_top_coupons():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    config = StrategyConfig(
        bank=90,
        stake=30,
        category=13,
        seed=42,
        top_count=5,
        candidate_samples=20,
        mutation_limit=10,
        optimization_samples=30,
        validation_samples=40,
    )

    packages = build_packages_for_probabilities(
        probabilities=probabilities,
        analyses=[],
        drawing_id=7,
        config=config,
        baseline_builder=lambda *args, **kwargs: {
            "selected_coupons": ["1111"],
            "cost": 30,
        },
    )

    by_name = {package.strategy: package for package in packages}
    assert set(by_name) == {
        "baseline_brief",
        "top_probability",
        "weighted_coverage",
    }
    assert by_name["top_probability"].coupons == top_probability_coupons(
        probabilities, limit=3
    )
    assert all(len(package.coupons) <= 3 for package in packages)


def test_strategy_builder_uses_separate_seeds_and_shared_validation(monkeypatch):
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}])
    scenario_calls = []
    candidate_seeds = []
    validation_ids = []

    def fake_sample(probabilities, count, seed):
        scenarios = {"1": count}
        scenario_calls.append((count, seed, scenarios))
        return scenarios

    def fake_candidates(*args, **kwargs):
        candidate_seeds.append(kwargs["seed"])
        return ["1"]

    def fake_coverage(coupons, scenarios, category):
        validation_ids.append(id(scenarios))
        return 1.0

    monkeypatch.setattr(strategy_module, "sample_scenarios", fake_sample)
    monkeypatch.setattr(strategy_module, "generate_candidate_coupons", fake_candidates)
    monkeypatch.setattr(
        strategy_module,
        "select_weighted_package",
        lambda **kwargs: DirectPackageResult(["1"], 1, 1, 1.0, False),
    )
    monkeypatch.setattr(
        strategy_module,
        "estimate_package_coverage",
        fake_coverage,
    )

    config = StrategyConfig(
        bank=30,
        stake=30,
        top_count=1,
        candidate_samples=2,
        optimization_samples=3,
        validation_samples=4,
        seed=42,
    )
    build_packages_for_probabilities(
        probabilities,
        analyses=[],
        drawing_id=7,
        config=config,
        baseline_builder=lambda *args, **kwargs: {"selected_coupons": ["1"]},
    )

    assert [(count, seed) for count, seed, _ in scenario_calls] == [
        (4, 42 ^ 7 ^ 0x5A5A),
        (3, 42 ^ 7 ^ 0xA5A5),
    ]
    assert candidate_seeds == [42 ^ 7 ^ 0xC3C3]
    assert validation_ids == [id(scenario_calls[0][2])] * 3


def test_strategy_package_outputs_are_deterministic():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 3
    )
    config = StrategyConfig(
        bank=60,
        stake=30,
        top_count=3,
        candidate_samples=10,
        optimization_samples=10,
        validation_samples=10,
        timeout_per_drawing=None,
    )
    def baseline(*args, **kwargs):
        return {"selected_coupons": ["111"]}

    first = build_packages_for_probabilities(
        probabilities, [], 7, config, baseline_builder=baseline
    )
    second = build_packages_for_probabilities(
        probabilities, [], 7, config, baseline_builder=baseline
    )

    assert [
        (
            package.strategy,
            package.coupons,
            package.estimated_coverage,
            package.candidate_count,
            package.timed_out,
        )
        for package in first
    ] == [
        (
            package.strategy,
            package.coupons,
            package.estimated_coverage,
            package.candidate_count,
            package.timed_out,
        )
        for package in second
    ]


def test_strategy_builder_passes_timeout_and_propagates_baseline_timeout():
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}])
    received = {}

    def baseline_builder(*args, **kwargs):
        received.update(kwargs)
        return {"selected_coupons": ["1"], "timed_out": True}

    packages = build_packages_for_probabilities(
        probabilities,
        analyses=[],
        drawing_id=7,
        config=StrategyConfig(
            bank=30,
            stake=30,
            top_count=1,
            candidate_samples=2,
            optimization_samples=2,
            validation_samples=2,
            timeout_per_drawing=1.5,
        ),
        baseline_builder=baseline_builder,
    )

    assert received["timeout_per_drawing"] == 1.5
    assert packages[0].timed_out is True


def test_strategy_builder_rejects_analysis_probability_mismatch():
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}])
    analysis = EventBriefAnalysis(
        event_order=1,
        name="Match",
        pool={"1": 0.5, "X": 0.3, "2": 0.2},
        bk={"1": 0.5, "X": 0.3, "2": 0.2},
        bias={"1": 0.0, "X": 0.0, "2": 0.0},
        entropy=1.0,
        bk_gap=0.2,
        base_pick="1",
        reason="test",
    )

    with pytest.raises(ValueError, match="BK probabilities must match"):
        build_packages_for_probabilities(
            probabilities,
            analyses=[analysis],
            drawing_id=7,
            config=StrategyConfig(
                bank=30,
                stake=30,
                top_count=1,
                candidate_samples=2,
                optimization_samples=2,
                validation_samples=2,
            ),
            baseline_builder=lambda *args, **kwargs: {"selected_coupons": ["1"]},
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bank": 0}, "bank must be positive"),
        ({"stake": 0}, "stake must be positive"),
        ({"category": 12}, "Category must be one of"),
        ({"bank": 20, "stake": 30}, "at least one coupon"),
        ({"bank": 90, "stake": 30, "top_count": 2}, "top_count"),
        ({"candidate_samples": 0}, "candidate_samples must be positive"),
        ({"optimization_samples": 0}, "optimization_samples must be positive"),
        ({"validation_samples": 0}, "validation_samples must be positive"),
        ({"mutation_limit": -1}, "mutation_limit must be non-negative"),
        ({"timeout_per_drawing": 0}, "timeout_per_drawing must be positive"),
    ],
)
def test_strategy_config_validation(overrides, message):
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}])
    config = StrategyConfig(**overrides)

    with pytest.raises(ValueError, match=message):
        build_packages_for_probabilities(
            probabilities,
            analyses=[],
            drawing_id=7,
            config=config,
            baseline_builder=lambda *args, **kwargs: {"selected_coupons": []},
        )
