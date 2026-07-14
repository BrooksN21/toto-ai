"""Prize-fund allocation and crowd-probability math."""

import math

from toto_ai.ev.models import ProbabilityMatrix, validate_config_bank

CROWD_JOINT_MODEL = "independent_event_marginals"


def _require_non_negative_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def validate_bank(bank: int, stake: int) -> int:
    """Return the number of coupons available for a valid bank."""
    return validate_config_bank(bank, stake)


def category_funds(possible_winnings: float, jackpot: float) -> dict[int, float]:
    """Return the official cumulative prize allocation by hit category."""
    _require_non_negative_finite("possible_winnings", possible_winnings)
    _require_non_negative_finite("jackpot", jackpot)
    return {
        9: possible_winnings * 8 / 18,
        10: possible_winnings * 4 / 18,
        11: possible_winnings * 2 / 18,
        12: possible_winnings / 18,
        13: possible_winnings / 18,
        14: possible_winnings / 18 + jackpot / 10,
        15: possible_winnings / 18 + jackpot * 9 / 10,
    }


def normalize_triplet(values: tuple[float, float, float]) -> tuple[float, float, float]:
    """Normalize a non-negative finite probability triplet."""
    if len(values) != 3:
        raise ValueError("probability triplet must contain exactly three values")
    for value in values:
        _require_non_negative_finite("probability", value)
    total = sum(values)
    if total == 0:
        raise ValueError("probability triplet total must be positive")
    return tuple(value / total for value in values)


def smooth_crowd_matrix(
    matrix: ProbabilityMatrix,
    pool_sum: float,
    stake: int,
) -> ProbabilityMatrix:
    """Apply Jeffreys smoothing to normalized crowd marginal rows.

    The returned rows are event marginals. Later joint coupon probabilities are
    modeled as the product of one marginal from each event, as named by
    ``CROWD_JOINT_MODEL``; this function does not infer event correlations.
    """
    _require_non_negative_finite("pool_sum", pool_sum)
    if stake <= 0:
        raise ValueError("stake must be positive")
    observations = pool_sum / stake
    denominator = observations + 1.5
    return tuple(
        tuple(
            (observations * value + 0.5) / denominator
            for value in normalize_triplet(row)
        )
        for row in matrix
    )
