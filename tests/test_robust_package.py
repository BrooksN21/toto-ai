from __future__ import annotations

import pytest

from toto_ai.optimizer.robust_package import (
    ExposureConstraints,
    select_robust_package,
)


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


def test_selector_enforces_exposure_bounds_during_construction() -> None:
    result = select_robust_package(
        candidates=["11", "12", "21", "22"],
        probability_models={
            "a": ((0.90, 0.05, 0.05),) * 2,
            "b": ((0.80, 0.10, 0.10),) * 2,
        },
        category=15,
        max_coupons=2,
        sample_count=200,
        exposure_constraints=ExposureConstraints(
            lower_bounds=((1, 0, 1), (1, 0, 1)),
            upper_bounds=((1, 2, 1), (1, 2, 1)),
        ),
        fallback_coupons=("11", "22"),
    )

    assert len(result.selected_coupons) == 2
    assert {coupon[0] for coupon in result.selected_coupons} == {"1", "2"}
    assert {coupon[1] for coupon in result.selected_coupons} == {"1", "2"}


def test_selector_rejects_fallback_that_violates_exposure_bounds() -> None:
    with pytest.raises(ValueError, match="fallback_coupons do not satisfy"):
        select_robust_package(
            candidates=["11", "12", "21", "22"],
            probability_models={
                "a": ((0.90, 0.05, 0.05),) * 2,
                "b": ((0.80, 0.10, 0.10),) * 2,
            },
            category=15,
            max_coupons=2,
            sample_count=200,
            exposure_constraints=ExposureConstraints(
                lower_bounds=((1, 0, 1), (1, 0, 1)),
                upper_bounds=((1, 2, 1), (1, 2, 1)),
            ),
            fallback_coupons=("11", "12"),
        )


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


def test_exposure_dead_end_reports_real_fallback_without_changing_coupons():
    # 11 is the greedy first choice, but its required complement22 is absent.
    # A complete feasible package12+21 DOES exist: the universe is not infeasible.
    result = select_robust_package(
        candidates=("11", "12", "21"),
        probability_models={"a": ((0.9, 0.05, 0.05),) * 2, "b": ((0.8, 0.1, 0.1),) * 2},
        category=15,
        max_coupons=2,
        sample_count=200,
        seed_material="trace-dead-end",
        exposure_constraints=ExposureConstraints(
            lower_bounds=((1, 0, 1),) * 2, upper_bounds=((1, 0, 1),) * 2
        ),
        fallback_coupons=("12", "21"),
    )
    assert result.selected_coupons == ("12", "21")
    assert not result.timed_out
    trace = result.selection_trace
    assert trace.path == "EXPOSURE_FALLBACK"
    assert trace.fallback_reason == "GREEDY_EXPOSURE_DEAD_END"
    assert trace.greedy_selected_count == 1
    assert trace.selection_iteration == 2
    assert trace.unselected_candidate_count == 2
    assert {
        (v.event_1based, v.outcome, v.kind, v.observed, v.limit)
        for v in trace.violated_constraints
    } == {(1, "2", "LOWER_NOT_MET", 0, 1), (2, "2", "LOWER_NOT_MET", 0, 1)}
    assert result.sampled_metrics_scope == "OPTIMIZER_SELECTION_SAMPLE_NOT_CALIBRATED"


def test_same_as_fallback_is_not_itself_a_fallback_trace():
    result = select_robust_package(
        candidates=("1",),
        probability_models={"a": ((0.6, 0.2, 0.2),), "b": ((0.5, 0.3, 0.2),)},
        category=15,
        max_coupons=1,
        sample_count=20,
        fallback_coupons=("1",),
    )
    assert result.selected_coupons == ("1",)
    assert result.selection_trace.path == "GREEDY_SELECTED"
    assert result.selection_trace.fallback_reason is None


def test_timeout_is_not_constraint_fallback():
    result = select_robust_package(
        candidates=("1",),
        probability_models={"a": ((0.6, 0.2, 0.2),), "b": ((0.5, 0.3, 0.2),)},
        category=15,
        max_coupons=1,
        sample_count=20,
        fallback_coupons=("1",),
        deadline=1.0,
        time_func=lambda: 2.0,
    )
    assert result.selection_trace.path == "TIMEOUT_BEFORE_SELECTION"
    assert result.selection_trace.fallback_reason is None
