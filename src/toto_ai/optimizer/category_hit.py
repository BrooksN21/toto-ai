"""Deterministic category-hit seed packages built only from BK probabilities."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache

import numpy as np

from toto_ai.ev.package_quality import continuous_exposure_lower_bounds
from toto_ai.optimizer.brief import EventBriefAnalysis, build_baseline_brief
from toto_ai.optimizer.cover import verify_cover_package

OUTCOMES = ("1", "X", "2")


@lru_cache(maxsize=32)
def cover_14_bk_fill_seed(
    probabilities: tuple[tuple[float, float, float], ...],
    bank: int,
    stake: int,
    exposure_floor_scale: float = 0.15,
    exposure_floor_exponent: float = 1.0,
    near_fixed_share: float = 0.95,
    concentration_headroom_share: float = 0.03,
) -> tuple[str, ...]:
    """Return an exact Cover-14 core with a safety-compatible BK fill."""
    if len(probabilities) != 15:
        raise ValueError("category-hit seed requires exactly 15 events")
    if type(bank) is not int or type(stake) is not int or bank <= 0 or stake <= 0:
        raise ValueError("bank and stake must be positive integers")
    if bank % stake:
        raise ValueError("bank must be divisible by stake")
    analyses = [
        _analysis(event_order, row)
        for event_order, row in enumerate(probabilities)
    ]
    cover = build_baseline_brief(
        analyses,
        category=14,
        bank=bank,
        stake=stake,
    )
    core = tuple(str(coupon) for coupon in cover["selected_coupons"])
    verification = verify_cover_package(
        brief=list(cover["brief"]),
        category=14,
        coupons=list(core),
    )
    if not verification["guarantee_pass"]:
        raise ValueError("category-hit seed lost its exact Cover-14 core")
    capacity = bank // stake
    lower_bounds = np.asarray(
        [
            continuous_exposure_lower_bounds(
                row,
                package_size=capacity,
                scale=exposure_floor_scale,
                exponent=exposure_floor_exponent,
            )
            for row in probabilities
        ],
        dtype=np.int32,
    )
    maximum_count = math.ceil(near_fixed_share * capacity) - 1
    headroom_count = math.ceil(concentration_headroom_share * capacity)
    soft_upper_bounds = np.maximum(
        lower_bounds,
        np.full((15, 3), maximum_count - headroom_count, dtype=np.int32),
    )
    filled = _fill_safely(
        core=core,
        probabilities=probabilities,
        capacity=capacity,
        lower_bounds=lower_bounds,
        upper_bounds=soft_upper_bounds,
    )
    if filled is None:
        raise ValueError(
            "category-hit seed could not satisfy production exposure bounds"
        )
    return filled


def _fill_safely(
    *,
    core: tuple[str, ...],
    probabilities: tuple[tuple[float, float, float], ...],
    capacity: int,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> tuple[str, ...] | None:
    selected = set(core)
    fill_count = capacity - len(core)
    if fill_count < 0:
        return None
    digit_by_outcome = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    core_digits = np.asarray(
        [[digit_by_outcome[outcome] for outcome in coupon] for coupon in core],
        dtype=np.int8,
    )
    counts = np.zeros((15, 3), dtype=np.int32)
    for event in range(15):
        counts[event] = np.bincount(core_digits[:, event], minlength=3)
    targets = np.zeros((15, 3), dtype=np.int32)
    for event, row in enumerate(probabilities):
        minimum = np.maximum(lower_bounds[event] - counts[event], 0)
        maximum = upper_bounds[event] - counts[event]
        allocated = _bounded_allocation(row, fill_count, minimum, maximum)
        if allocated is None:
            return None
        targets[event] = allocated
    seed_bytes = json.dumps(
        probabilities,
        separators=(",", ":"),
    ).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_bytes).digest()[:8], "big")
    for attempt in range(256):
        rng = np.random.default_rng(seed + attempt)
        columns = []
        for event in range(15):
            values = np.repeat(np.arange(3, dtype=np.int8), targets[event])
            rng.shuffle(values)
            columns.append(values)
        digits = np.column_stack(columns)
        fill = tuple(
            "".join(OUTCOMES[int(outcome)] for outcome in row)
            for row in digits
        )
        if len(set(fill)) == fill_count and not selected.intersection(fill):
            coupons = (*core, *fill)
            break
    else:
        return None
    final_counts = counts + targets
    if (
        len(coupons) != capacity
        or np.any(final_counts < lower_bounds)
        or np.any(final_counts > upper_bounds)
    ):
        return None
    return coupons


def _bounded_allocation(
    probabilities: tuple[float, float, float],
    total: int,
    minimum: np.ndarray,
    maximum: np.ndarray,
) -> np.ndarray | None:
    if int(minimum.sum()) > total or int(maximum.sum()) < total:
        return None
    raw = np.asarray(probabilities, dtype=np.float64) * total
    allocation = np.clip(np.floor(raw).astype(np.int32), minimum, maximum)
    while int(allocation.sum()) < total:
        candidates = np.flatnonzero(allocation < maximum)
        if not candidates.size:
            return None
        best = min(
            candidates,
            key=lambda index: (-(raw[index] - allocation[index]), int(index)),
        )
        allocation[int(best)] += 1
    while int(allocation.sum()) > total:
        candidates = np.flatnonzero(allocation > minimum)
        if not candidates.size:
            return None
        best = min(
            candidates,
            key=lambda index: (-(allocation[index] - raw[index]), int(index)),
        )
        allocation[int(best)] -= 1
    return allocation


def _analysis(
    event_order: int,
    row: tuple[float, float, float],
) -> EventBriefAnalysis:
    probabilities = tuple(float(value) for value in row)
    if (
        len(probabilities) != 3
        or any(not math.isfinite(value) or value <= 0 for value in probabilities)
        or not math.isclose(sum(probabilities), 1.0, rel_tol=1e-12, abs_tol=1e-12)
    ):
        raise ValueError("BK rows must contain three positive probabilities")
    bk = dict(zip(OUTCOMES, probabilities, strict=True))
    ordered = sorted(OUTCOMES, key=lambda outcome: (-bk[outcome], outcome))
    gap = bk[ordered[0]] - bk[ordered[1]]
    entropy = -sum(value * math.log(value) for value in probabilities)
    if entropy >= 1.07 or gap <= 0.05:
        base_pick = "1X2"
        reason = "highly balanced event"
    elif gap <= 0.18 or bk[ordered[0]] < 0.52:
        top_two = set(ordered[:2])
        base_pick = "".join(outcome for outcome in OUTCOMES if outcome in top_two)
        reason = "uncertain event"
    else:
        base_pick = ordered[0]
        reason = "clear bookmaker favorite"
    return EventBriefAnalysis(
        event_order=event_order,
        name=f"Event {event_order + 1}",
        pool=dict(bk),
        bk=bk,
        bias={outcome: 0.0 for outcome in OUTCOMES},
        entropy=entropy,
        bk_gap=gap,
        base_pick=base_pick,
        reason=reason,
    )
