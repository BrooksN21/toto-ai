import math

import pytest
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.ev.benchmark import benchmark_ev_engine


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
    assert len(result["surface_sha256"]) == 64


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
