"""Deterministic dynamic-bank selection over a complete EV surface."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from toto_ai.ev.models import EVConfig, EVPackage, EVSurface, RankedCoupon
from toto_ai.ev.ternary import MAX_EVENTS, OUTCOMES, coupon_from_index

RANK_RTOL = 1e-12
RANK_ATOL = 1e-15


def rank_coupon_indices(surface: EVSurface) -> np.ndarray:
    """Return all coupon indices in complete deterministic EV order."""
    gross_ev, event_count = _validated_surface(surface)
    indices = np.arange(gross_ev.size, dtype=np.int64)
    order = np.lexsort((indices, -gross_ev))
    ordered_ev = gross_ev[order]

    if order.size > 1:
        # Candidate blocks conservatively contain every tolerance-tie run.
        adjacent_gap = ordered_ev[:-1] - ordered_ev[1:]
        adjacent_tolerance = RANK_ATOL + RANK_RTOL * ordered_ev[:-1]
        close_boundaries = adjacent_gap <= 2.0 * adjacent_tolerance
        block_starts = np.flatnonzero(
            np.concatenate((np.array([True]), ~close_boundaries)),
        )
        block_stops = np.concatenate((block_starts[1:], np.array([order.size])))

        for block_start, block_stop in zip(block_starts, block_stops, strict=True):
            position = int(block_start)
            stop = int(block_stop)
            while position < stop:
                base_ev = ordered_ev[position]
                close = np.isclose(
                    ordered_ev[position:stop],
                    base_ev,
                    rtol=RANK_RTOL,
                    atol=RANK_ATOL,
                )
                if bool(close.all()):
                    run_stop = stop
                else:
                    run_stop = position + int(np.argmax(~close))

                tie_indices = order[position:run_stop]
                if tie_indices.size > 1 and bool(
                    np.any(tie_indices[1:] < tie_indices[:-1]),
                ):
                    tie_indices.sort()
                position = run_stop

    return order


def select_ev_package(surface: EVSurface, config: EVConfig) -> EVPackage:
    """Select a deterministic research or playable package from all coupons."""
    gross_ev, event_count = _validated_surface(surface)
    if not isinstance(config, EVConfig):
        raise ValueError("config must be an EVConfig")

    order = rank_coupon_indices(surface)
    if config.mode == "research":
        selected_positions = np.arange(
            min(config.max_coupons, order.size),
            dtype=np.int64,
        )
        decision = "RESEARCH ONLY"
    elif config.mode == "playable":
        minimum_ev = _validated_minimum_ev(config.min_gross_ev)
        eligible_positions = np.flatnonzero(gross_ev[order] >= minimum_ev)
        selected_positions = eligible_positions[: config.max_coupons]
        decision = "PLAY" if selected_positions.size else "NO BET"
    else:
        raise ValueError("mode must be 'research' or 'playable'")

    selected_indices = order[selected_positions]
    coupons = tuple(
        RankedCoupon(
            rank=int(position) + 1,
            coupon=coupon_from_index(int(index), event_count),
            gross_ev=float(gross_ev[index]),
            net_ev=float(gross_ev[index] - 1.0),
        )
        for position, index in zip(selected_positions, selected_indices, strict=True)
    )
    cost = len(coupons) * config.stake
    expected_payout = float(
        sum((coupon.gross_ev * config.stake for coupon in coupons), start=0.0),
    )

    return EVPackage(
        decision=decision,
        coupons=coupons,
        cost=cost,
        unused_bank=config.bank - cost,
        expected_payout=expected_payout,
        modeled_roi=expected_payout / cost - 1.0 if cost else None,
        derived_brief=derive_brief(
            tuple(coupon.coupon for coupon in coupons),
            event_count=event_count,
        ),
    )


def derive_brief(coupons: Sequence[str], event_count: int) -> tuple[str, ...]:
    """Union coupon outcomes per event in fixed ``1``, ``X``, ``2`` order."""
    event_count = _validated_event_count(event_count)
    selected = tuple(coupons)
    outcomes_by_event = [set[str]() for _ in range(event_count)]

    for coupon in selected:
        if not isinstance(coupon, str) or len(coupon) != event_count:
            raise ValueError("coupon length must match event_count")
        for position, outcome in enumerate(coupon):
            if outcome not in OUTCOMES:
                raise ValueError("coupon outcomes must be one of '1', 'X', or '2'")
            outcomes_by_event[position].add(outcome)

    return tuple(
        "".join(outcome for outcome in OUTCOMES if outcome in selected_outcomes)
        for selected_outcomes in outcomes_by_event
    )


def _validated_surface(surface: EVSurface) -> tuple[np.ndarray, int]:
    if not isinstance(surface, EVSurface):
        raise ValueError("surface must be an EVSurface")
    event_count = _validated_event_count(surface.event_count)
    gross_ev = surface.gross_ev
    if gross_ev.ndim != 1:
        raise ValueError("gross_ev must be one-dimensional")
    if gross_ev.size != 3**event_count:
        raise ValueError("gross_ev length must equal 3**event_count")
    if not (
        np.issubdtype(gross_ev.dtype, np.floating)
        or np.issubdtype(gross_ev.dtype, np.integer)
    ):
        raise ValueError("gross_ev must be finite and non-negative")
    if not np.isfinite(gross_ev).all() or np.any(gross_ev < 0.0):
        raise ValueError("gross_ev must be finite and non-negative")
    return gross_ev, event_count


def _validated_event_count(event_count: int) -> int:
    if type(event_count) is not int or not 1 <= event_count <= MAX_EVENTS:
        raise ValueError(f"event_count must be in 1..{MAX_EVENTS}")
    return event_count


def _validated_minimum_ev(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("min_gross_ev must be finite")
    try:
        minimum_ev = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("min_gross_ev must be finite") from error
    if not math.isfinite(minimum_ev):
        raise ValueError("min_gross_ev must be finite")
    return minimum_ev
