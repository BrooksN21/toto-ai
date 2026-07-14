import itertools
import math

import numpy as np
import pytest
from typer.testing import CliRunner

import toto_ai.ev.benchmark as benchmark_module
from toto_ai.cli import app
from toto_ai.ev.benchmark import benchmark_ev_engine
from toto_ai.ev.prize import category_funds
from toto_ai.ev.reference import brute_force_gross_ev, joint_distribution
from toto_ai.ev.ternary import (
    _poisson_binomial_tails_for_indices,
    compute_ev_surface,
)


def test_small_benchmark_verifies_complete_surface_against_oracle():
    result = benchmark_ev_engine(event_count=4, sample_count=7)

    assert result["event_count"] == 4
    assert result["coupon_count"] == 3**4
    assert result["verification"] == "PASS"
    assert result["verification_method"] == "full brute-force oracle"
    assert result["maximum_sampled_absolute_error"] <= 1e-12
    assert result["minimum_denominator"] > 0
    assert math.isclose(result["probability_mass"], 1.0, abs_tol=1e-12)
    assert math.isclose(result["crowd_mass"], 1.0, abs_tol=1e-12)
    assert result["elapsed_seconds"] >= 0
    assert result["peak_memory_bytes"] is None or result["peak_memory_bytes"] > 0


def test_official_category_coefficients_match_literal_expectations():
    assert category_funds(possible_winnings=18.0, jackpot=10.0) == {
        9: 8.0,
        10: 4.0,
        11: 2.0,
        12: 1.0,
        13: 1.0,
        14: 2.0,
        15: 10.0,
    }


def test_scalar_crowd_tail_preserves_tiny_positive_probability():
    row = (0.999998, 0.000001, 0.000001)

    tail = benchmark_module._scalar_poisson_binomial_tail(
        (row,) * 5,
        actual_index=3**5 - 1,
        minimum_hits=5,
    )

    assert tail > 0.0
    assert tail == pytest.approx(1e-30, rel=1e-12, abs=0.0)


def test_independent_direct_coupon_components_match_small_oracle():
    true = (
        (0.5, 0.3, 0.2),
        (0.45, 0.35, 0.2),
        (0.4, 0.25, 0.35),
        (0.6, 0.25, 0.15),
    )
    crowd = (
        (0.4, 0.35, 0.25),
        (0.3, 0.45, 0.25),
        (0.5, 0.2, 0.3),
        (0.35, 0.4, 0.25),
    )
    regular_coefficients = {2: 0.5, 3: 0.25, 4: 0.125}
    jackpot_coefficients = {3: 0.1, 4: 0.9}
    sample_indices = np.array([0, 17, 40, 80], dtype=np.int64)

    regular, jackpot = benchmark_module._independent_direct_coupon_components(
        true,
        crowd,
        pool_sum=1_000.0,
        coupon_indices=sample_indices,
        regular_coefficients=regular_coefficients,
        jackpot_coefficients=jackpot_coefficients,
        chunk_size=11,
    )

    expected_regular = brute_force_gross_ev(
        true,
        crowd,
        1_000.0,
        30,
        regular_coefficients,
        2,
    )
    expected_jackpot = brute_force_gross_ev(
        true,
        crowd,
        1_000.0,
        30,
        jackpot_coefficients,
        3,
    )
    np.testing.assert_allclose(
        regular,
        expected_regular[sample_indices],
        rtol=1e-12,
        atol=1e-15,
    )
    np.testing.assert_allclose(
        jackpot,
        expected_jackpot[sample_indices],
        rtol=1e-12,
        atol=1e-15,
    )


def test_non_unit_tolerance_rows_agree_across_evaluators():
    true = (
        (0.5000000000001, 0.3000000000001, 0.2),
        (0.4500000000001, 0.3500000000001, 0.2),
        (0.4000000000001, 0.2500000000001, 0.35),
    )
    crowd = (
        (0.4000000000001, 0.3500000000001, 0.25),
        (0.3000000000001, 0.4500000000001, 0.25),
        (0.5000000000001, 0.2000000000001, 0.3),
    )
    funds = {2: 0.5, 3: 0.25}
    coupon_indices = np.array([0, 7, 17, 26], dtype=np.int64)

    surface = compute_ev_surface(true, crowd, 1_000.0, funds, 30, 2)
    reference = brute_force_gross_ev(true, crowd, 1_000.0, 30, funds, 2)
    direct_regular, direct_jackpot = (
        benchmark_module._independent_direct_coupon_components(
            true,
            crowd,
            pool_sum=1_000.0,
            coupon_indices=coupon_indices,
            regular_coefficients=funds,
            jackpot_coefficients={},
            chunk_size=11,
        )
    )
    scalar_tail = benchmark_module._scalar_poisson_binomial_tail(
        crowd,
        actual_index=17,
        minimum_hits=2,
    )
    production_tail = _poisson_binomial_tails_for_indices(
        crowd,
        minimum_hits=2,
        actual_indices=np.array([17], dtype=np.int64),
    )[0]
    actual = (1, 2, 2)
    reference_tail = sum(
        probability
        for probability, ticket in zip(
            joint_distribution(crowd),
            itertools.product(range(3), repeat=len(crowd)),
            strict=True,
        )
        if sum(left == right for left, right in zip(ticket, actual, strict=True)) >= 2
    )

    np.testing.assert_allclose(surface.gross_ev, reference, rtol=1e-13, atol=1e-15)
    np.testing.assert_allclose(
        direct_regular + direct_jackpot,
        reference[coupon_indices],
        rtol=1e-14,
        atol=1e-15,
    )
    assert scalar_tail == pytest.approx(reference_tail, rel=1e-14, abs=0.0)
    assert production_tail == pytest.approx(reference_tail, rel=1e-14, abs=0.0)


def test_fingerprint_shape_is_not_a_pass_predicate(monkeypatch):
    monkeypatch.setattr(
        benchmark_module,
        "_deterministic_array_hash",
        lambda _array: "diagnostic-fingerprint",
    )

    result = benchmark_ev_engine(event_count=2, sample_count=3)

    assert result["verification"] == "PASS"
    assert result["surface_sha256"] == "diagnostic-fingerprint"


def test_benchmark_diagnostics_are_deterministic_except_resources():
    first = benchmark_ev_engine(event_count=2, sample_count=3)
    second = benchmark_ev_engine(event_count=2, sample_count=3)

    for key in (
        "sample_indices",
        "sample_values",
        "surface_sha256",
        "verification",
        "verification_method",
    ):
        assert first[key] == second[key]


@pytest.mark.parametrize(
    ("event_count", "sample_count", "message"),
    [
        (0, 1, "event_count must be in 1..15"),
        (16, 1, "event_count must be in 1..15"),
        (True, 1, "event_count must be in 1..15"),
        (2, 0, "sample_count must be a positive int"),
        (2, True, "sample_count must be a positive int"),
        (1, 4, "sample_count must not exceed coupon count"),
    ],
)
def test_benchmark_validates_dimensions(event_count, sample_count, message):
    with pytest.raises(ValueError, match=message):
        benchmark_ev_engine(event_count=event_count, sample_count=sample_count)


def test_benchmark_ev_cli_prints_required_diagnostics():
    result = CliRunner().invoke(
        app,
        ["benchmark-ev", "--events", "2", "--samples", "3"],
    )

    assert result.exit_code == 0
    assert "Exact EV Engine Benchmark" in result.stdout
    assert "coupon count" in result.stdout
    assert "minimum denominator" in result.stdout
    assert "maximum sampled absolute error" in result.stdout
    assert "PASS" in result.stdout
