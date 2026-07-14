"""Deterministic correctness and resource benchmark for the exact EV engine."""

from __future__ import annotations

import hashlib
import math
import sys
import time
from typing import Any

import numpy as np

from toto_ai.ev.models import EVInput, ProbabilityMatrix
from toto_ai.ev.prize import normalize_triplet
from toto_ai.ev.reference import MAX_REFERENCE_EVENTS, brute_force_gross_ev
from toto_ai.ev.ternary import (
    MAX_EVENTS,
    _compute_official_components,
    compute_ev_surface,
    materialize_ev_surface,
)

BENCHMARK_POOL_SUM = 1_000_000.0
BENCHMARK_POSSIBLE_WINNINGS = 18_000.0
BENCHMARK_JACKPOT = 10_000.0
BENCHMARK_STAKE = 30
HASH_DECIMALS = 12


def benchmark_ev_engine(
    event_count: int = 15,
    sample_count: int = 20,
) -> dict[str, Any]:
    """Run deterministic exact-EV verification and return benchmark diagnostics."""
    if type(event_count) is not int or event_count < 1 or event_count > MAX_EVENTS:
        raise ValueError(f"event_count must be in 1..{MAX_EVENTS}")
    if type(sample_count) is not int or sample_count <= 0:
        raise ValueError("sample_count must be a positive int")
    coupon_count = 3**event_count
    if sample_count > coupon_count:
        raise ValueError("sample_count must not exceed coupon count")

    true_probabilities, crowd_probabilities = _benchmark_matrices(event_count)
    sample_indices = np.linspace(
        0,
        coupon_count - 1,
        num=sample_count,
        dtype=np.int64,
    )
    started_at = time.perf_counter()

    if event_count <= MAX_REFERENCE_EVENTS:
        minimum_category = max(1, event_count - 2)
        funds = {
            category: float(20 * 2 ** (event_count - category))
            for category in range(minimum_category, event_count + 1)
        }
        surface = compute_ev_surface(
            true_probabilities,
            crowd_probabilities,
            BENCHMARK_POOL_SUM,
            funds,
            BENCHMARK_STAKE,
            minimum_category,
        )
        reference = brute_force_gross_ev(
            true_probabilities,
            crowd_probabilities,
            BENCHMARK_POOL_SUM,
            BENCHMARK_STAKE,
            funds,
            minimum_category,
        )
        absolute_error = np.abs(surface.gross_ev - reference)
        maximum_error = float(absolute_error.max(initial=0.0))
        verified = np.allclose(
            surface.gross_ev,
            reference,
            rtol=1e-10,
            atol=1e-12,
        )
        verification_method = "full brute-force oracle"
        possible_winnings_hash = None
        jackpot_hash = None
    else:
        ev_input = EVInput(
            drawing_id=0,
            drawing_number=None,
            true_probabilities=true_probabilities,
            crowd_probabilities=crowd_probabilities,
            pool_sum=BENCHMARK_POOL_SUM,
            jackpot=BENCHMARK_JACKPOT,
            possible_winnings=BENCHMARK_POSSIBLE_WINNINGS,
            probability_sources=("deterministic-benchmark",) * event_count,
            fetched_at="deterministic-benchmark",
        )
        components, direct_components = _compute_official_components(
            ev_input,
            progress_callback=None,
            direct_sample_indices=sample_indices,
        )
        if direct_components is None:
            raise RuntimeError("direct sample verification was not produced")
        surface = materialize_ev_surface(
            components,
            BENCHMARK_POSSIBLE_WINNINGS,
            BENCHMARK_JACKPOT,
        )
        direct_values = (
            direct_components[0] * BENCHMARK_POSSIBLE_WINNINGS
            + direct_components[1] * BENCHMARK_JACKPOT
        )
        sampled_values = surface.gross_ev[sample_indices]
        maximum_error = float(
            np.abs(sampled_values - direct_values).max(initial=0.0),
        )
        verified = np.allclose(
            sampled_values,
            direct_values,
            rtol=1e-10,
            atol=1e-12,
        )
        verification_method = "fixed coupons by direct ternary sum"
        possible_winnings_hash = _deterministic_array_hash(
            components.possible_winnings_ev_per_ruble,
        )
        jackpot_hash = _deterministic_array_hash(
            components.jackpot_ev_per_ruble,
        )

    elapsed_seconds = time.perf_counter() - started_at
    masses_valid = (
        math.isclose(surface.probability_mass, 1.0, rel_tol=0.0, abs_tol=1e-12)
        and math.isclose(surface.crowd_mass, 1.0, rel_tol=0.0, abs_tol=1e-12)
    )
    denominator_valid = (
        math.isfinite(surface.minimum_denominator)
        and surface.minimum_denominator > 0
    )
    surface_hash = _deterministic_array_hash(surface.gross_ev)
    hashes_valid = len(surface_hash) == 64 and (
        event_count <= MAX_REFERENCE_EVENTS
        or (
            possible_winnings_hash is not None
            and len(possible_winnings_hash) == 64
            and jackpot_hash is not None
            and len(jackpot_hash) == 64
        )
    )
    verification = (
        "PASS"
        if verified and masses_valid and denominator_valid and hashes_valid
        else "FAIL"
    )

    return {
        "event_count": event_count,
        "coupon_count": coupon_count,
        "elapsed_seconds": elapsed_seconds,
        "peak_memory_bytes": _peak_resident_memory_bytes(),
        "probability_mass": surface.probability_mass,
        "crowd_mass": surface.crowd_mass,
        "minimum_denominator": surface.minimum_denominator,
        "maximum_sampled_absolute_error": maximum_error,
        "verification": verification,
        "verification_method": verification_method,
        "sample_indices": tuple(int(index) for index in sample_indices),
        "sample_values": tuple(
            float(value) for value in surface.gross_ev[sample_indices]
        ),
        "surface_sha256": surface_hash,
        "possible_winnings_sha256": possible_winnings_hash,
        "jackpot_sha256": jackpot_hash,
    }


def _benchmark_matrices(
    event_count: int,
) -> tuple[ProbabilityMatrix, ProbabilityMatrix]:
    true_rows = []
    crowd_rows = []
    for index in range(event_count):
        true_rows.append(
            normalize_triplet(
                (
                    0.50 + 0.01 * (index % 3),
                    0.30 + 0.01 * ((index + 1) % 3),
                    0.20 + 0.01 * ((index + 2) % 3),
                ),
            ),
        )
        crowd_rows.append(
            normalize_triplet(
                (
                    0.38 + 0.01 * ((index + 2) % 3),
                    0.34 + 0.01 * (index % 3),
                    0.28 + 0.01 * ((index + 1) % 3),
                ),
            ),
        )
    return tuple(true_rows), tuple(crowd_rows)


def _deterministic_array_hash(array: np.ndarray) -> str:
    normalized = np.round(np.asarray(array, dtype=np.float64), HASH_DECIMALS)
    little_endian = normalized.astype("<f8", copy=False)
    return hashlib.sha256(little_endian.tobytes(order="C")).hexdigest()


def _peak_resident_memory_bytes() -> int | None:
    try:
        import resource

        maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, ValueError):
        return None
    return maximum if sys.platform == "darwin" else maximum * 1024
