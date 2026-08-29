from __future__ import annotations

import pytest

from toto_ai.optimizer.robust_package import select_robust_package


def test_maximin_selector_covers_opposing_models() -> None:
    result = select_robust_package(
        candidates=["11", "22", "XX"],
        probability_models={
            "home": ((0.90, 0.05, 0.05),) * 2,
            "away": ((0.05, 0.05, 0.90),) * 2,
        },
        category=15,
        max_coupons=2,
        sample_count=5_000,
        seed_material="opposing-models",
    )

    assert set(result.selected_coupons) == {"11", "22"}
    assert result.worst_sampled_category_coverage > 0.79
    assert result.mean_sampled_category_coverage > 0.80
    assert result.timed_out is False


def test_selector_is_deterministic_unique_and_does_not_mutate_inputs() -> None:
    candidates = ["11", "22", "XX", "11"]
    models = {
        "a": ((0.60, 0.25, 0.15),) * 2,
        "b": ((0.15, 0.25, 0.60),) * 2,
    }
    candidates_before = list(candidates)
    models_before = dict(models)
    kwargs = dict(
        candidates=candidates,
        probability_models=models,
        category=14,
        max_coupons=3,
        sample_count=500,
        seed_material="deterministic",
    )

    first = select_robust_package(**kwargs)
    second = select_robust_package(**kwargs)

    assert first == second
    assert len(first.selected_coupons) == len(set(first.selected_coupons)) == 3
    assert candidates == candidates_before
    assert models == models_before


def test_fifteen_event_result_reports_exact_metrics_for_every_model() -> None:
    result = select_robust_package(
        candidates=["1" * 15, "2" * 15],
        probability_models={
            "bk": ((0.60, 0.20, 0.20),) * 15,
            "sports": ((0.20, 0.20, 0.60),) * 15,
        },
        category=13,
        max_coupons=2,
        sample_count=200,
        seed_material="exact-metrics",
    )

    assert result.selected_coupons == ("1" * 15, "2" * 15)
    assert {metric.model for metric in result.model_metrics} == {"bk", "sports"}
    for metric in result.model_metrics:
        assert metric.exact_p13 is not None
        assert metric.exact_p14 is not None
        assert metric.exact_p15 is not None
        assert metric.exact_p13 >= metric.exact_p14 >= metric.exact_p15


def test_timeout_fails_closed_before_workload_construction() -> None:
    result = select_robust_package(
        candidates=["1"],
        probability_models={
            "a": ((0.60, 0.25, 0.15),),
            "b": ((0.15, 0.25, 0.60),),
        },
        category=15,
        max_coupons=1,
        sample_count=100,
        deadline=1.0,
        time_func=lambda: 2.0,
    )

    assert result.selected_coupons == ()
    assert result.timed_out is True


@pytest.mark.parametrize(
    ("models", "message"),
    [
        ({"one": ((0.5, 0.3, 0.2),)}, "at least two"),
        (
            {
                "one": ((0.5, 0.3, 0.2),),
                "two": ((0.5, 0.5),),
            },
            "three outcomes",
        ),
    ],
)
def test_invalid_probability_models_are_rejected(models, message) -> None:
    with pytest.raises(ValueError, match=message):
        select_robust_package(
            candidates=["1"],
            probability_models=models,
            category=15,
            max_coupons=1,
        )
