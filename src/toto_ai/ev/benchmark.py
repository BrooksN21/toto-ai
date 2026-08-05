"""Deterministic correctness and resource benchmark for the exact EV engine."""

from __future__ import annotations

import hashlib
import math
import sys
import time
from collections.abc import Mapping, Sequence
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
DIRECT_VERIFICATION_CHUNK_SIZE = 1 << 15
OFFICIAL_REGULAR_COEFFICIENTS = {
    9: 8 / 18,
    10: 4 / 18,
    11: 2 / 18,
    12: 1 / 18,
    13: 1 / 18,
    14: 1 / 18,
    15: 1 / 18,
}
OFFICIAL_JACKPOT_COEFFICIENTS = {
    9: 0.0,
    10: 0.0,
    11: 0.0,
    12: 0.0,
    13: 0.0,
    14: 0.1,
    15: 0.9,
}


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
        maximum_tail_error = 0.0
        crowd_tails_verified = True
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
        components, production_tail_samples = _compute_official_components(
            ev_input,
            progress_callback=None,
            crowd_sample_indices=sample_indices,
        )
        if production_tail_samples is None:
            raise RuntimeError("crowd-tail sample verification was not produced")
        surface = materialize_ev_surface(
            components,
            BENCHMARK_POSSIBLE_WINNINGS,
            BENCHMARK_JACKPOT,
        )
        regular_coefficients = {
            category: coefficient
            for category, coefficient in OFFICIAL_REGULAR_COEFFICIENTS.items()
            if category <= event_count
        }
        jackpot_coefficients = {
            category: coefficient
            for category, coefficient in OFFICIAL_JACKPOT_COEFFICIENTS.items()
            if category <= event_count
        }
        direct_components = _independent_direct_coupon_components(
            true_probabilities,
            crowd_probabilities,
            pool_sum=BENCHMARK_POOL_SUM,
            coupon_indices=sample_indices,
            regular_coefficients=regular_coefficients,
            jackpot_coefficients=jackpot_coefficients,
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
        tail_errors = []
        crowd_tails_verified = True
        for category in regular_coefficients:
            expected_tails = np.array(
                [
                    _scalar_poisson_binomial_tail(
                        crowd_probabilities,
                        int(actual_index),
                        category,
                    )
                    for actual_index in sample_indices
                ],
                dtype=np.float64,
            )
            actual_tails = production_tail_samples[category]
            tail_errors.append(
                float(np.abs(actual_tails - expected_tails).max(initial=0.0)),
            )
            crowd_tails_verified = crowd_tails_verified and np.allclose(
                actual_tails,
                expected_tails,
                rtol=1e-12,
                atol=0.0,
            )
        maximum_tail_error = max(tail_errors, default=0.0)
        verification_method = (
            "independent scalar crowd tails and direct all-state coupon sums"
        )
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
    verification = (
        "PASS"
        if verified and crowd_tails_verified and masses_valid and denominator_valid
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
        "maximum_sampled_crowd_tail_absolute_error": maximum_tail_error,
        "crowd_tail_samples_verified": bool(crowd_tails_verified),
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


def _scalar_poisson_binomial_tail(
    crowd_probabilities: ProbabilityMatrix,
    actual_index: int,
    minimum_hits: int,
) -> float:
    """Independently compute one crowd tail with scalar Python arithmetic."""
    event_count = len(crowd_probabilities)
    if actual_index < 0 or actual_index >= 3**event_count:
        raise ValueError("actual_index is outside the ternary state space")
    if minimum_hits < 1 or minimum_hits > event_count:
        raise ValueError("minimum_hits is outside the event count")

    actual = [0] * event_count
    remainder = actual_index
    for position in range(event_count - 1, -1, -1):
        remainder, actual[position] = divmod(remainder, 3)

    probabilities = [1.0] + [0.0] * event_count
    for processed_events, (row, outcome) in enumerate(
        zip(crowd_probabilities, actual, strict=True),
    ):
        match_probability = float(row[outcome])
        nonmatch_probability = (
            math.fsum(float(value) for value in row) - match_probability
        )
        next_probabilities = [0.0] * (event_count + 1)
        for hit_count in range(processed_events + 1):
            probability = probabilities[hit_count]
            next_probabilities[hit_count] += probability * nonmatch_probability
            next_probabilities[hit_count + 1] += probability * match_probability
        probabilities = next_probabilities
    return math.fsum(probabilities[minimum_hits:])


def _independent_direct_coupon_components(
    true_probabilities: ProbabilityMatrix,
    crowd_probabilities: ProbabilityMatrix,
    pool_sum: float,
    coupon_indices: Sequence[int] | np.ndarray,
    regular_coefficients: Mapping[int, float],
    jackpot_coefficients: Mapping[int, float],
    chunk_size: int = DIRECT_VERIFICATION_CHUNK_SIZE,
) -> tuple[np.ndarray, np.ndarray]:
    """Directly sum sampled coupon EVs over every actual-result state."""
    event_count = len(true_probabilities)
    if len(crowd_probabilities) != event_count:
        raise ValueError("benchmark matrices must have matching event counts")
    if not math.isfinite(pool_sum) or pool_sum <= 0:
        raise ValueError("pool_sum must be finite and positive")
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive int")

    indices = np.asarray(coupon_indices)
    if indices.ndim != 1 or indices.dtype.kind not in "iu":
        raise ValueError("coupon_indices must be a one-dimensional integer array")
    indices = indices.astype(np.int64, copy=False)
    state_count = 3**event_count
    if np.any(indices < 0) or np.any(indices >= state_count):
        raise ValueError("coupon_indices are outside the ternary state space")

    categories = sorted(set(regular_coefficients) | set(jackpot_coefficients))
    if any(category < 1 or category > event_count for category in categories):
        raise ValueError("coefficient category is outside the event count")
    coupon_digits = _decode_state_indices(indices, event_count)
    regular_components = np.zeros(len(indices), dtype=np.float64)
    jackpot_components = np.zeros(len(indices), dtype=np.float64)

    for start in range(0, state_count, chunk_size):
        stop = min(start + chunk_size, state_count)
        actual_indices = np.arange(start, stop, dtype=np.int64)
        actual_digits = _decode_state_indices(actual_indices, event_count)

        true_probability = np.ones(stop - start, dtype=np.float64)
        match_distribution = np.zeros(
            (stop - start, event_count + 1),
            dtype=np.float64,
        )
        match_distribution[:, 0] = 1.0
        for event_index, (true_row, crowd_row) in enumerate(
            zip(true_probabilities, crowd_probabilities, strict=True),
        ):
            outcomes = actual_digits[:, event_index]
            true_probability *= np.asarray(true_row, dtype=np.float64)[outcomes]
            crowd_values = np.asarray(crowd_row, dtype=np.float64)
            match_probability = crowd_values[outcomes]
            nonmatch_probability = (
                crowd_values.sum(dtype=np.float64) - match_probability
            )
            for hit_count in range(event_index + 1, 0, -1):
                match_distribution[:, hit_count] = (
                    match_distribution[:, hit_count]
                    * nonmatch_probability
                    + match_distribution[:, hit_count - 1] * match_probability
                )
            match_distribution[:, 0] *= nonmatch_probability

        crowd_tails = {
            category: match_distribution[:, category:].sum(
                axis=1,
                dtype=np.float64,
            )
            for category in categories
        }
        if any(
            not np.isfinite(tail).all() or np.any(tail <= 0.0)
            for tail in crowd_tails.values()
        ):
            raise ValueError("independent crowd tails must be finite and positive")

        hits = np.equal(
            actual_digits[:, np.newaxis, :],
            coupon_digits[np.newaxis, :, :],
        ).sum(axis=2)
        regular_return = np.zeros(hits.shape, dtype=np.float64)
        jackpot_return = np.zeros(hits.shape, dtype=np.float64)
        for category in categories:
            inverse_denominator = 1.0 / (pool_sum * crowd_tails[category])
            qualifies = hits >= category
            regular_return += (
                qualifies
                * inverse_denominator[:, np.newaxis]
                * regular_coefficients.get(category, 0.0)
            )
            jackpot_return += (
                qualifies
                * inverse_denominator[:, np.newaxis]
                * jackpot_coefficients.get(category, 0.0)
            )

        regular_components += np.sum(
            true_probability[:, np.newaxis] * regular_return,
            axis=0,
            dtype=np.float64,
        )
        jackpot_components += np.sum(
            true_probability[:, np.newaxis] * jackpot_return,
            axis=0,
            dtype=np.float64,
        )

    return regular_components, jackpot_components


def _decode_state_indices(indices: np.ndarray, event_count: int) -> np.ndarray:
    digits = np.empty((len(indices), event_count), dtype=np.uint8)
    remainders = indices.copy()
    for position in range(event_count - 1, -1, -1):
        remainders, digits[:, position] = np.divmod(remainders, 3)
    return digits


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
