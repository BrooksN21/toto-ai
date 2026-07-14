"""Deterministic dynamic-bank selection over a complete EV surface."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from toto_ai.ev.models import EVConfig, EVPackage, EVSurface, RankedCoupon
from toto_ai.ev.ternary import MAX_EVENTS, OUTCOMES, coupon_from_index

RANK_RTOL = 1e-12
RANK_ATOL = 1e-15
_TIE_SCAN_CHUNK_SIZE = 1 << 18
_ORDER_REVERSE_CHUNK_SIZE = 1 << 20


def rank_coupon_indices(surface: EVSurface) -> np.ndarray:
    """Return all coupon indices in complete deterministic EV order.

    The full index order is required. Additional working arrays stay bounded:
    ascending indices are reversed in chunks, then a streaming adjacent-value
    scan sends only actual tolerance-tie candidate blocks for in-place sorting.
    """
    gross_ev, event_count = _validated_surface(surface)
    order = np.argsort(gross_ev, kind="quicksort")
    _reverse_in_place(order)
    _reorder_tolerance_ties(order, gross_ev)

    return order


def _reverse_in_place(order: np.ndarray) -> None:
    left = 0
    right = order.size
    while right - left > 1:
        count = min(_ORDER_REVERSE_CHUNK_SIZE, (right - left) // 2)
        right_start = right - count
        left_values = order[left : left + count].copy()
        order[left : left + count] = order[right_start:right][::-1]
        order[right_start:right] = left_values[::-1]
        left += count
        right = right_start


def _reorder_tolerance_ties(order: np.ndarray, gross_ev: np.ndarray) -> None:
    if order.size < 2:
        return

    open_block_start: int | None = None
    edge_start = 0
    edge_count = order.size - 1
    while edge_start < edge_count:
        edge_stop = min(edge_start + _TIE_SCAN_CHUNK_SIZE, edge_count)
        ordered_values = gross_ev[order[edge_start : edge_stop + 1]]
        close_edges = _adjacent_values_close(ordered_values)
        changes = np.flatnonzero(close_edges[1:] != close_edges[:-1]) + 1

        segment_start = 0
        for segment_stop in changes:
            open_block_start = _consume_tie_edge_segment(
                order,
                gross_ev,
                edge_start,
                segment_start,
                close_edges,
                open_block_start,
            )
            segment_start = int(segment_stop)
        open_block_start = _consume_tie_edge_segment(
            order,
            gross_ev,
            edge_start,
            segment_start,
            close_edges,
            open_block_start,
        )
        edge_start = edge_stop

    if open_block_start is not None:
        _process_tie_candidate_block(
            order,
            gross_ev,
            open_block_start,
            order.size,
        )


def _consume_tie_edge_segment(
    order: np.ndarray,
    gross_ev: np.ndarray,
    edge_start: int,
    segment_start: int,
    close_edges: np.ndarray,
    open_block_start: int | None,
) -> int | None:
    global_edge_start = edge_start + segment_start
    if bool(close_edges[segment_start]):
        return global_edge_start if open_block_start is None else open_block_start
    if open_block_start is not None:
        _process_tie_candidate_block(
            order,
            gross_ev,
            open_block_start,
            global_edge_start + 1,
        )
    return None


def _adjacent_values_close(ordered_values: np.ndarray) -> np.ndarray:
    return _values_close_to_bases(ordered_values[1:], ordered_values[:-1])


def _values_close_to_bases(values: np.ndarray, bases: np.ndarray) -> np.ndarray:
    if np.issubdtype(values.dtype, np.integer):
        differences = bases - values
        return differences.astype(np.longdouble) <= (
            np.longdouble(RANK_ATOL)
            + np.longdouble(RANK_RTOL) * bases.astype(np.longdouble)
        )
    return np.isclose(values, bases, rtol=RANK_RTOL, atol=RANK_ATOL)


def _process_tie_candidate_block(
    order: np.ndarray,
    gross_ev: np.ndarray,
    block_start: int,
    block_stop: int,
) -> None:
    run_start = block_start
    while run_start < block_stop:
        run_stop = _find_run_first_stop(order, gross_ev, run_start, block_stop)
        if run_stop - run_start > 1:
            order[run_start:run_stop].sort(kind="quicksort")
        run_start = run_stop


def _find_run_first_stop(
    order: np.ndarray,
    gross_ev: np.ndarray,
    run_start: int,
    block_stop: int,
) -> int:
    base_ev = gross_ev[order[run_start]]
    position = run_start + 1
    while position < block_stop:
        chunk_stop = min(position + _TIE_SCAN_CHUNK_SIZE, block_stop)
        values = gross_ev[order[position:chunk_stop]]
        close = _values_close_to_base(values, base_ev)
        if not bool(close.all()):
            return position + int(np.argmax(~close))
        position = chunk_stop
    return block_stop


def _values_close_to_base(values: np.ndarray, base: float) -> np.ndarray:
    if np.issubdtype(values.dtype, np.integer):
        differences = base - values
        tolerance = np.longdouble(RANK_ATOL) + np.longdouble(RANK_RTOL) * np.longdouble(
            base,
        )
        return differences.astype(np.longdouble) <= tolerance
    return np.isclose(values, base, rtol=RANK_RTOL, atol=RANK_ATOL)


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
