"""Exact expected value over the full ternary coupon space."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from toto_ai.ev.models import EVComponents, EVInput, EVSurface, ProbabilityMatrix
from toto_ai.ev.prize import category_funds

OUTCOMES = ("1", "X", "2")
MAX_EVENTS = 15
PROBABILITY_TOLERANCE = 1e-12

ProgressPayload = dict[str, str | int | float]
ProgressCallback = Callable[[ProgressPayload], None]


@dataclass
class _AccumulationResult:
    arrays: tuple[np.ndarray, ...]
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float
    direct_samples: tuple[np.ndarray, ...] | None


def coupon_from_index(index: int, event_count: int) -> str:
    """Return the C-order base-three coupon string for a flat index."""
    event_count = _validated_event_count(event_count)
    if type(index) is not int:
        raise ValueError("index must be an int")
    coupon_count = 3**event_count
    if index < 0 or index >= coupon_count:
        raise ValueError(f"index must be in 0..{coupon_count - 1}")

    digits = [OUTCOMES[0]] * event_count
    remainder = index
    for position in range(event_count - 1, -1, -1):
        remainder, digit = divmod(remainder, 3)
        digits[position] = OUTCOMES[digit]
    return "".join(digits)


def index_from_coupon(coupon: Sequence[str]) -> int:
    """Return the C-order flat index for a coupon in 1/X/2 outcome order."""
    values = tuple(coupon)
    if not values:
        raise ValueError("coupon must contain at least one outcome")
    if len(values) > MAX_EVENTS:
        raise ValueError(f"coupon must contain at most {MAX_EVENTS} outcomes")

    digit_by_outcome = {outcome: digit for digit, outcome in enumerate(OUTCOMES)}
    index = 0
    for outcome in values:
        if outcome not in digit_by_outcome:
            raise ValueError("coupon outcomes must be one of '1', 'X', or '2'")
        index = index * 3 + digit_by_outcome[outcome]
    return index


def hamming_ball_kernel(event_count: int, minimum_hits: int) -> np.ndarray:
    """Return the symmetric ternary Hamming-ball kernel in C order."""
    event_count = _validated_event_count(event_count)
    minimum_hits = _validated_minimum_category(minimum_hits, event_count)
    maximum_errors = event_count - minimum_hits

    weights = np.zeros(1, dtype=np.uint8)
    for _ in range(event_count):
        weights = np.concatenate((weights, weights + 1, weights + 1))
    return (weights <= maximum_errors).astype(np.float64)


def ternary_convolve(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
    event_count: int,
) -> np.ndarray:
    """Return cyclic convolution on ``(Z3)^event_count`` in C order."""
    event_count = _validated_event_count(event_count)
    shape = (3,) * event_count
    size = 3**event_count
    left_array = _validated_flat_array(left, "left", size)
    right_array = _validated_flat_array(right, "right", size)

    left_fft = np.fft.fftn(left_array.reshape(shape))
    right_fft = np.fft.fftn(right_array.reshape(shape))
    left_fft *= right_fft
    del right_fft
    result = np.fft.ifftn(left_fft).real.reshape(-1)
    result[np.abs(result) < 1e-15] = 0.0
    return result


def compute_ev_components(
    ev_input: EVInput,
    progress_callback: ProgressCallback | None = None,
) -> EVComponents:
    """Compute reusable official 9..15 regular-prize and jackpot unit EV."""
    components, _ = _compute_official_components(
        ev_input,
        progress_callback=progress_callback,
        direct_sample_indices=None,
    )
    return components


def materialize_ev_surface(
    components: EVComponents,
    possible_winnings: float,
    jackpot: float,
) -> EVSurface:
    """Scale reusable component arrays into one immutable EV surface."""
    gross_ev = (
        components.possible_winnings_ev_per_ruble * possible_winnings
        + components.jackpot_ev_per_ruble * jackpot
    )
    return EVSurface(
        gross_ev=gross_ev,
        event_count=components.event_count,
        probability_mass=components.probability_mass,
        crowd_mass=components.crowd_mass,
        minimum_denominator=components.minimum_denominator,
    )


def compute_ev_surface(
    true_probabilities: ProbabilityMatrix,
    crowd_probabilities: ProbabilityMatrix,
    pool_sum: float,
    category_funds_by_hits: Mapping[int, float],
    stake: int,
    minimum_category: int,
    progress_callback: ProgressCallback | None = None,
) -> EVSurface:
    """Compute an exact EV surface for an explicit arbitrary category mapping.

    ``stake`` is validated to match the payout API even though it cancels when
    payout is converted to a return multiple.
    """
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive int")

    true_matrix, crowd_matrix = _validated_matching_matrices(
        true_probabilities,
        crowd_probabilities,
    )
    event_count = len(true_matrix)
    funds = _validated_category_funds(
        category_funds_by_hits,
        minimum_category,
        event_count,
    )
    result = _accumulate_categories(
        true_matrix=true_matrix,
        crowd_matrix=crowd_matrix,
        pool_sum=pool_sum,
        coefficient_maps=(funds,),
        progress_callback=progress_callback,
        direct_sample_indices=None,
    )
    return EVSurface(
        gross_ev=result.arrays[0],
        event_count=event_count,
        probability_mass=result.probability_mass,
        crowd_mass=result.crowd_mass,
        minimum_denominator=result.minimum_denominator,
    )


def _compute_official_components(
    ev_input: EVInput,
    progress_callback: ProgressCallback | None,
    direct_sample_indices: np.ndarray | None,
) -> tuple[EVComponents, tuple[np.ndarray, np.ndarray] | None]:
    true_matrix, crowd_matrix = _validated_matching_matrices(
        ev_input.true_probabilities,
        ev_input.crowd_probabilities,
    )
    event_count = len(true_matrix)
    if event_count < 9:
        raise ValueError("official categories require 9..15 events")

    regular_coefficients = {
        category: coefficient
        for category, coefficient in category_funds(1.0, 0.0).items()
        if category <= event_count
    }
    jackpot_coefficients = {
        category: coefficient
        for category, coefficient in category_funds(0.0, 1.0).items()
        if category <= event_count
    }
    result = _accumulate_categories(
        true_matrix=true_matrix,
        crowd_matrix=crowd_matrix,
        pool_sum=ev_input.pool_sum,
        coefficient_maps=(regular_coefficients, jackpot_coefficients),
        progress_callback=progress_callback,
        direct_sample_indices=direct_sample_indices,
    )
    components = EVComponents(
        possible_winnings_ev_per_ruble=result.arrays[0],
        jackpot_ev_per_ruble=result.arrays[1],
        event_count=event_count,
        probability_mass=result.probability_mass,
        crowd_mass=result.crowd_mass,
        minimum_denominator=result.minimum_denominator,
    )
    if result.direct_samples is None:
        return components, None
    return components, (result.direct_samples[0], result.direct_samples[1])


def _accumulate_categories(
    true_matrix: ProbabilityMatrix,
    crowd_matrix: ProbabilityMatrix,
    pool_sum: float,
    coefficient_maps: tuple[dict[int, float], ...],
    progress_callback: ProgressCallback | None,
    direct_sample_indices: np.ndarray | None,
) -> _AccumulationResult:
    try:
        pool_sum = float(pool_sum)
    except (TypeError, ValueError) as error:
        raise ValueError("pool_sum must be finite and positive") from error
    if not math.isfinite(pool_sum) or pool_sum <= 0:
        raise ValueError("pool_sum must be finite and positive")

    event_count = len(true_matrix)
    probability = _joint_distribution(true_matrix)
    crowd = _joint_distribution(crowd_matrix)
    probability_mass = float(probability.sum(dtype=np.float64))
    crowd_mass = float(crowd.sum(dtype=np.float64))
    _require_unit_mass(probability_mass, "true probability")
    _require_unit_mass(crowd_mass, "crowd probability")

    categories = sorted(
        {category for mapping in coefficient_maps for category in mapping},
    )
    size = probability.size
    accumulators = tuple(np.zeros(size, dtype=np.float64) for _ in coefficient_maps)
    direct_accumulators = (
        tuple(
            np.zeros(len(direct_sample_indices), dtype=np.float64)
            for _ in coefficient_maps
        )
        if direct_sample_indices is not None
        else None
    )
    minimum_denominator = math.inf
    started_at = time.perf_counter()

    for category in categories:
        kernel = hamming_ball_kernel(event_count, category)
        crowd_tail = ternary_convolve(crowd, kernel, event_count)
        denominator = pool_sum * crowd_tail
        if not np.isfinite(denominator).all() or np.any(denominator <= 0):
            raise ValueError(
                f"category {category} denominator must be finite and positive",
            )
        minimum_denominator = min(
            minimum_denominator,
            float(denominator.min()),
        )
        weighted_probability = probability / denominator

        if direct_accumulators is not None and direct_sample_indices is not None:
            kernel_indices = np.flatnonzero(kernel)
            direct_units = _direct_hamming_sums(
                weighted_probability,
                kernel_indices,
                direct_sample_indices,
                event_count,
            )
            for accumulator, coefficients in zip(
                direct_accumulators,
                coefficient_maps,
                strict=True,
            ):
                accumulator += direct_units * coefficients.get(category, 0.0)
            del kernel_indices, direct_units

        contribution = ternary_convolve(weighted_probability, kernel, event_count)
        for accumulator, coefficients in zip(
            accumulators,
            coefficient_maps,
            strict=True,
        ):
            accumulator += contribution * coefficients.get(category, 0.0)

        del kernel, crowd_tail, denominator, weighted_probability, contribution
        if progress_callback is not None:
            progress_callback(
                {
                    "phase": "category",
                    "category": category,
                    "elapsed": time.perf_counter() - started_at,
                },
            )

    return _AccumulationResult(
        arrays=accumulators,
        probability_mass=probability_mass,
        crowd_mass=crowd_mass,
        minimum_denominator=minimum_denominator,
        direct_samples=direct_accumulators,
    )


def _direct_hamming_sums(
    weighted_probability: np.ndarray,
    kernel_indices: np.ndarray,
    coupon_indices: np.ndarray,
    event_count: int,
) -> np.ndarray:
    """Directly sum ``f(y) K(c-y)`` using explicit ternary subtraction."""
    values = np.zeros(len(coupon_indices), dtype=np.float64)
    for sample_position, coupon_index in enumerate(coupon_indices):
        offsets = kernel_indices.copy()
        actual_indices = np.zeros(len(kernel_indices), dtype=np.int64)
        coupon_remainder = int(coupon_index)
        place = 1
        for _ in range(event_count):
            offsets, offset_digit = np.divmod(offsets, 3)
            coupon_remainder, coupon_digit = divmod(coupon_remainder, 3)
            actual_indices += ((coupon_digit - offset_digit) % 3) * place
            place *= 3
        values[sample_position] = weighted_probability[actual_indices].sum(
            dtype=np.float64,
        )
    return values


def _joint_distribution(matrix: ProbabilityMatrix) -> np.ndarray:
    joint = np.ones(1, dtype=np.float64)
    for row in matrix:
        joint = np.kron(joint, np.asarray(row, dtype=np.float64))
    return joint


def _validated_matching_matrices(
    true_probabilities: ProbabilityMatrix,
    crowd_probabilities: ProbabilityMatrix,
) -> tuple[ProbabilityMatrix, ProbabilityMatrix]:
    true_matrix = _validated_matrix(true_probabilities, "true probabilities")
    crowd_matrix = _validated_matrix(crowd_probabilities, "crowd probabilities")
    if len(true_matrix) != len(crowd_matrix):
        raise ValueError("true and crowd probabilities must have the same event count")
    return true_matrix, crowd_matrix


def _validated_matrix(
    matrix: ProbabilityMatrix,
    name: str,
) -> ProbabilityMatrix:
    try:
        rows = tuple(tuple(row) for row in matrix)
    except TypeError as error:
        raise ValueError(f"{name} must be a probability matrix") from error
    event_count = len(rows)
    _validated_event_count(event_count)

    validated: list[tuple[float, float, float]] = []
    for row in rows:
        if len(row) != 3:
            raise ValueError(f"{name} rows must contain exactly three values")
        try:
            values = tuple(float(value) for value in row)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{name} probabilities must be finite and non-negative",
            ) from error
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError(f"{name} probabilities must be finite and non-negative")
        if not math.isclose(
            sum(values),
            1.0,
            rel_tol=PROBABILITY_TOLERANCE,
            abs_tol=PROBABILITY_TOLERANCE,
        ):
            raise ValueError(f"{name} rows must sum to 1 within 1e-12")
        validated.append(values)
    return tuple(validated)


def _validated_category_funds(
    category_funds_by_hits: Mapping[int, float],
    minimum_category: int,
    event_count: int,
) -> dict[int, float]:
    minimum_category = _validated_minimum_category(minimum_category, event_count)
    if not category_funds_by_hits:
        raise ValueError("category_funds_by_hits must not be empty")

    validated: dict[int, float] = {}
    for category, fund in category_funds_by_hits.items():
        if (
            type(category) is not int
            or category < minimum_category
            or category > event_count
        ):
            raise ValueError(
                f"category {category} must be in {minimum_category}..{event_count}",
            )
        try:
            value = float(fund)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "category funds must be finite and non-negative",
            ) from error
        if not math.isfinite(value) or value < 0:
            raise ValueError("category funds must be finite and non-negative")
        validated[category] = value
    return validated


def _validated_event_count(event_count: int) -> int:
    if type(event_count) is not int or event_count < 1 or event_count > MAX_EVENTS:
        raise ValueError(f"event_count must be in 1..{MAX_EVENTS}")
    return event_count


def _validated_minimum_category(minimum_category: int, event_count: int) -> int:
    if type(minimum_category) is not int or minimum_category <= 0:
        raise ValueError("minimum_category must be a positive int")
    if minimum_category > event_count:
        raise ValueError("minimum_category must not exceed event_count")
    return minimum_category


def _validated_flat_array(
    values: Sequence[float] | np.ndarray,
    name: str,
    size: int,
) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must contain finite numeric values") from error
    if array.size != size:
        raise ValueError(f"{name} must contain exactly {size} values")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite numeric values")
    return array.reshape(-1)


def _require_unit_mass(value: float, name: str) -> None:
    if not math.isfinite(value) or abs(value - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError(f"{name} mass must be one within 1e-12")
