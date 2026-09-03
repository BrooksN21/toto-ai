from __future__ import annotations

import pytest

from toto_ai.optimizer.uncertainty_package import (
    build_uncertainty_models,
    control_relative_exposure_constraints,
    flatten_probabilities,
    outcome_exposure,
    select_uncertainty_package,
)


def test_flatten_probabilities_moves_rows_toward_uniform() -> None:
    source = ((0.70, 0.20, 0.10), (0.20, 0.30, 0.50))

    flattened = flatten_probabilities(source, weight=0.15)

    assert flattened[0][0] < source[0][0]
    assert flattened[0][2] > source[0][2]
    assert flattened[1][2] < source[1][2]
    assert flattened[1][0] > source[1][0]
    assert all(sum(row) == pytest.approx(1.0) for row in flattened)


def test_uncertainty_models_are_named_and_deterministic() -> None:
    source = ((0.60, 0.25, 0.15),) * 3

    first = build_uncertainty_models(source, flatten_weights=(0.10, 0.20))
    second = build_uncertainty_models(source, flatten_weights=(0.10, 0.20))

    assert first == second
    assert tuple(first) == ("bk", "flatten_10", "flatten_20")
    assert first["bk"] == source
    assert first["flatten_20"][0] == pytest.approx(
        (0.5466666667, 0.2666666667, 0.1866666667)
    )


def test_direct_uncertainty_selector_uses_generated_candidate_universe() -> None:
    probabilities = ((0.75, 0.15, 0.10),) * 4
    anchors = ("1111", "XXXX")

    result = select_uncertainty_package(
        bk_probabilities=probabilities,
        anchor_coupons=anchors,
        category=14,
        max_coupons=6,
        flatten_weights=(0.20,),
        top_count=12,
        candidate_sample_count=100,
        mutation_limit=20,
        selection_sample_count=300,
        seed_material="direct-candidates",
    )

    assert len(result.selected_coupons) == 6
    assert len(set(result.selected_coupons)) == 6
    assert result.candidate_count > len(anchors)
    assert set(result.selected_coupons) - set(anchors)
    assert tuple(metric.model for metric in result.model_metrics) == (
        "bk",
        "flatten_20",
    )
    assert result.timed_out is False


def test_uncertainty_selector_rejects_invalid_flattening() -> None:
    with pytest.raises(ValueError, match="strictly between zero and one"):
        select_uncertainty_package(
            bk_probabilities=((0.5, 0.3, 0.2),),
            category=15,
            max_coupons=1,
            flatten_weights=(1.0,),
        )


def test_outcome_exposure_reports_counts_and_shares() -> None:
    exposure = outcome_exposure(("1X", "12", "2X", "11"))

    assert exposure[0] == {
        "event_order": 0,
        "counts": {"1": 3, "X": 0, "2": 1},
        "shares": {"1": 0.75, "X": 0.0, "2": 0.25},
    }
    assert exposure[1]["counts"] == {"1": 1, "X": 2, "2": 1}


def test_control_relative_constraints_bind_floor_and_maximum_to_control() -> None:
    constraints = control_relative_exposure_constraints(
        ((0.60, 0.25, 0.15),) * 2,
        control_coupons=("11", "12", "21", "22"),
        package_size=4,
        floor_scale=0.15,
        floor_exponent=1.0,
        near_fixed_share=0.95,
    )

    assert constraints.lower_bounds == ((0, 0, 0), (0, 0, 0))
    assert constraints.upper_bounds == ((2, 2, 2), (2, 2, 2))
