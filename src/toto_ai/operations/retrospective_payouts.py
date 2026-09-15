"""Research payout estimates; actual receipts remain separate authoritative data."""

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal


def cumulative_payout_comparison(
    hit_distribution: Mapping[int, int],
    coefficients: Mapping[int, str],
    *,
    stake: int,
    actual_return: str | None = None,
) -> dict[str, str | None]:
    """Hold displayed coefficients fixed; never round intermediate products.

    A receipt does not replace the estimate: both are retained to expose missing
    provider precision, rounding differences, or a different actual wager.
    """
    if set(coefficients) != set(range(9, 16)):
        raise ValueError("complete category coefficients 9..15 are required")
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive integer")
    if any(
        type(hits) is not int
        or not 0 <= hits <= 15
        or type(count) is not int
        or count < 0
        for hits, count in hit_distribution.items()
    ):
        raise ValueError("invalid exact hit histogram")
    values = {category: Decimal(value) for category, value in coefficients.items()}
    if any(not value.is_finite() or value < 0 for value in values.values()):
        raise ValueError("coefficients must be finite and nonnegative")
    cost = Decimal(stake * sum(hit_distribution.values()))
    if cost == 0:
        raise ValueError("empty package has no ROI")
    cent = Decimal("0.01")
    raw = Decimal(0)
    prematurely_rounded = Decimal(0)
    for hits, count in hit_distribution.items():
        unit = stake * sum(
            (value for category, value in values.items() if category <= hits),
            Decimal(0),
        )
        raw += unit * count
        prematurely_rounded += unit.quantize(cent, rounding=ROUND_HALF_UP) * count
    estimated = raw.quantize(cent, rounding=ROUND_HALF_UP)
    actual = None if actual_return is None else Decimal(actual_return)
    if actual is not None and (not actual.is_finite() or actual < 0):
        raise ValueError("actual receipt return must be finite and nonnegative")
    return {
        "cost_rub": str(cost),
        "unrounded_estimated_return_rub": str(raw),
        "estimated_return_rub": str(estimated),
        "estimated_net_rub": str(estimated - cost),
        "estimated_roi_percent": str((estimated / cost - 1) * 100),
        "per_coupon_rounding_scenario_rub": str(prematurely_rounded),
        "actual_return_rub": None if actual is None else str(actual),
        "actual_net_rub": None if actual is None else str(actual - cost),
        "actual_roi_percent": (
            None if actual is None else str((actual / cost - 1) * 100)
        ),
    }
