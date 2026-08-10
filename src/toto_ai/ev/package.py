"""Deterministic dynamic-bank selection over a complete EV surface."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import numpy as np

from toto_ai.ev.models import (
    EVConfig,
    EVPackage,
    EVSurface,
    RankedCoupon,
    SafetyAwareSelectionDiagnostics,
    SafetyMaterialRepair,
    SafetySelectionExposure,
    SafetySelectionReplacement,
)
from toto_ai.ev.ternary import MAX_EVENTS, OUTCOMES, coupon_from_index

RANK_RTOL = 1e-12
RANK_ATOL = 1e-15
_TIE_SCAN_CHUNK_SIZE = 1 << 18
_ORDER_REVERSE_CHUNK_SIZE = 1 << 20
_SAFETY_PAIR_CHUNK_SIZE = 1 << 12
_SAFETY_INITIAL_CANDIDATES = 1 << 15
_SAFETY_CANDIDATES_PER_COUPON = 128
_SAFETY_CANDIDATE_EXPANSION = 4
_SAFETY_MAX_CANDIDATES = 1_000_000


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


def select_ev_package(
    surface: EVSurface,
    config: EVConfig,
    *,
    probabilities: Sequence[Sequence[float]] | None = None,
) -> EVPackage:
    """Select a deterministic research or playable package from all coupons."""
    package, _ = select_ev_package_with_top_coupons(
        surface,
        config,
        probabilities=probabilities,
        diagnostic_limit=0,
    )
    return package


def select_ev_package_with_top_coupons(
    surface: EVSurface,
    config: EVConfig,
    *,
    probabilities: Sequence[Sequence[float]] | None = None,
    diagnostic_limit: int = 20,
) -> tuple[EVPackage, tuple[RankedCoupon, ...]]:
    """Select a package and diagnostics from one complete deterministic order."""
    gross_ev, event_count = _validated_surface(surface)
    if not isinstance(config, EVConfig):
        raise ValueError("config must be an EVConfig")
    if type(diagnostic_limit) is not int or diagnostic_limit < 0:
        raise ValueError("diagnostic_limit must be a non-negative int")

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
        if config.package_safety_enabled and config.max_coupons:
            probability_rows = _validated_selection_probabilities(
                probabilities,
                event_count,
            )
            package = _select_safety_aware_package(
                gross_ev=gross_ev,
                event_count=event_count,
                order=order,
                eligible_positions=eligible_positions,
                config=config,
                probabilities=probability_rows,
            )
            diagnostic_positions = np.arange(
                min(diagnostic_limit, order.size),
                dtype=np.int64,
            )
            return package, _ranked_coupons(
                gross_ev,
                event_count,
                order,
                diagnostic_positions,
            )
        selected_positions = eligible_positions[: config.max_coupons]
        decision = "PLAY" if selected_positions.size else "NO BET"
    else:
        raise ValueError("mode must be 'research' or 'playable'")

    coupons = _ranked_coupons(
        gross_ev,
        event_count,
        order,
        selected_positions,
    )
    cost = len(coupons) * config.stake
    expected_payout = float(
        sum((coupon.gross_ev * config.stake for coupon in coupons), start=0.0),
    )

    package = EVPackage(
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
    diagnostic_positions = np.arange(
        min(diagnostic_limit, order.size),
        dtype=np.int64,
    )
    return package, _ranked_coupons(
        gross_ev,
        event_count,
        order,
        diagnostic_positions,
    )


def _select_safety_aware_package(
    *,
    gross_ev: np.ndarray,
    event_count: int,
    order: np.ndarray,
    eligible_positions: np.ndarray,
    config: EVConfig,
    probabilities: tuple[tuple[float, float, float], ...],
) -> EVPackage:
    required = config.max_coupons
    eligible_indices = order[eligible_positions]
    eligible_count = int(eligible_indices.size)
    baseline_count = min(required, eligible_count)
    baseline_indices = eligible_indices[:baseline_count]
    baseline_ranks = eligible_positions[:baseline_count] + 1
    baseline_digits = _coupon_digits(baseline_indices, event_count)
    baseline_counts = _selection_counts(baseline_digits, event_count)
    maximum_count = math.ceil(config.package_near_fixed_share * required) - 1
    lower_bounds = np.array(
        [
            [
                int(value >= config.package_material_probability_threshold)
                for value in row
            ]
            for row in probabilities
        ],
        dtype=np.int16,
    )
    upper_bounds = np.full((event_count, 3), maximum_count, dtype=np.int32)
    structural_reasons = _structural_infeasibility_reasons(
        required=required,
        eligible_count=eligible_count,
        maximum_count=maximum_count,
        lower_bounds=lower_bounds,
    )
    if structural_reasons:
        diagnostics = _selection_diagnostics(
            gross_ev=gross_ev,
            event_count=event_count,
            probabilities=probabilities,
            lower_bounds=lower_bounds,
            required=required,
            eligible_count=eligible_count,
            universe_count=eligible_count,
            universe_exhaustive=True,
            maximum_count=maximum_count,
            baseline_indices=baseline_indices,
            baseline_ranks=baseline_ranks,
            baseline_counts=baseline_counts,
            selected_indices=baseline_indices,
            selected_ranks=baseline_ranks,
            selected_counts=baseline_counts,
            feasible=False,
            reasons=structural_reasons,
        )
        return _infeasible_package(config, event_count, diagnostics)

    maximum_universe = min(eligible_count, _SAFETY_MAX_CANDIDATES)
    universe_count = min(
        maximum_universe,
        max(
            required,
            _SAFETY_INITIAL_CANDIDATES,
            required * _SAFETY_CANDIDATES_PER_COUPON,
        ),
    )
    selected_positions: np.ndarray | None = None
    selected_counts = baseline_counts
    while universe_count:
        universe_indices = eligible_indices[:universe_count]
        universe_ranks = eligible_positions[:universe_count] + 1
        universe_digits = _coupon_digits(universe_indices, event_count)
        repaired = _repair_selection(
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            required=required,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
        )
        selected_positions, selected_counts = repaired
        if _constraint_violation(selected_counts, lower_bounds, upper_bounds) == 0:
            break
        if universe_count == maximum_universe:
            selected_positions = None
            break
        universe_count = min(
            maximum_universe,
            universe_count * _SAFETY_CANDIDATE_EXPANSION,
        )

    universe_exhaustive = universe_count == eligible_count
    if selected_positions is None:
        reason = (
            "no_feasible_swap_sequence_in_eligible_universe"
            if universe_exhaustive
            else (
                "deterministic_candidate_universe_exhausted:"
                f"{universe_count}_of_{eligible_count}"
            )
        )
        diagnostics = _selection_diagnostics(
            gross_ev=gross_ev,
            event_count=event_count,
            probabilities=probabilities,
            lower_bounds=lower_bounds,
            required=required,
            eligible_count=eligible_count,
            universe_count=universe_count,
            universe_exhaustive=universe_exhaustive,
            maximum_count=maximum_count,
            baseline_indices=baseline_indices,
            baseline_ranks=baseline_ranks,
            baseline_counts=baseline_counts,
            selected_indices=baseline_indices,
            selected_ranks=baseline_ranks,
            selected_counts=baseline_counts,
            feasible=False,
            reasons=(reason,),
        )
        return _infeasible_package(config, event_count, diagnostics)

    universe_indices = eligible_indices[:universe_count]
    universe_ranks = eligible_positions[:universe_count] + 1
    selected_indices = universe_indices[selected_positions]
    selected_ranks = universe_ranks[selected_positions]
    selected_order = np.argsort(selected_ranks, kind="stable")
    selected_indices = selected_indices[selected_order]
    selected_ranks = selected_ranks[selected_order]
    selected_digits = _coupon_digits(selected_indices, event_count)
    selected_counts = _selection_counts(selected_digits, event_count)
    diagnostics = _selection_diagnostics(
        gross_ev=gross_ev,
        event_count=event_count,
        probabilities=probabilities,
        lower_bounds=lower_bounds,
        required=required,
        eligible_count=eligible_count,
        universe_count=universe_count,
        universe_exhaustive=universe_exhaustive,
        maximum_count=maximum_count,
        baseline_indices=baseline_indices,
        baseline_ranks=baseline_ranks,
        baseline_counts=baseline_counts,
        selected_indices=selected_indices,
        selected_ranks=selected_ranks,
        selected_counts=selected_counts,
        feasible=True,
        reasons=(),
    )
    coupons = tuple(
        RankedCoupon(
            rank=int(rank),
            coupon=coupon_from_index(int(index), event_count),
            gross_ev=float(gross_ev[index]),
            net_ev=float(gross_ev[index] - 1.0),
        )
        for rank, index in zip(selected_ranks, selected_indices, strict=True)
    )
    cost = len(coupons) * config.stake
    expected_payout = float(
        sum((coupon.gross_ev * config.stake for coupon in coupons), start=0.0),
    )
    return EVPackage(
        decision="PLAY",
        coupons=coupons,
        cost=cost,
        unused_bank=config.bank - cost,
        expected_payout=expected_payout,
        modeled_roi=expected_payout / cost - 1.0,
        derived_brief=derive_brief(
            tuple(coupon.coupon for coupon in coupons),
            event_count=event_count,
        ),
        selection_diagnostics=diagnostics,
    )


def _repair_selection(
    *,
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    required: int,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> tuple[np.ndarray | None, np.ndarray]:
    selected = np.zeros(universe_indices.size, dtype=bool)
    selected[:required] = True
    counts = _selection_counts(universe_digits[:required], lower_bounds.shape[0])
    maximum_iterations = required * lower_bounds.shape[0]
    for _ in range(maximum_iterations):
        violation = _constraint_violation(counts, lower_bounds, upper_bounds)
        if violation == 0:
            _improve_feasible_selection(
                gross_ev=gross_ev,
                universe_indices=universe_indices,
                universe_ranks=universe_ranks,
                universe_digits=universe_digits,
                selected=selected,
                counts=counts,
                lower_bounds=lower_bounds,
                upper_bounds=upper_bounds,
            )
            return np.flatnonzero(selected), counts
        pair = _best_repair_swap(
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            selected=selected,
            counts=counts,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            current_violation=violation,
        )
        if pair is None:
            return None, counts
        incoming_position, outgoing_position = pair
        _apply_swap(
            selected,
            counts,
            universe_digits,
            incoming_position,
            outgoing_position,
        )
    return None, counts


def _best_repair_swap(
    *,
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    selected: np.ndarray,
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    current_violation: int,
) -> tuple[int, int] | None:
    selected_positions = np.flatnonzero(selected)
    selected_digits = universe_digits[selected_positions]
    selected_ev = gross_ev[universe_indices[selected_positions]]
    selected_ranks = universe_ranks[selected_positions]
    delta_tables = _swap_delta_tables(counts, lower_bounds, upper_bounds)
    best_key: tuple[int, float, int, int] | None = None
    best_pair: tuple[int, int] | None = None
    for start in range(0, universe_indices.size, _SAFETY_PAIR_CHUNK_SIZE):
        stop = min(start + _SAFETY_PAIR_CHUNK_SIZE, universe_indices.size)
        incoming_positions = np.arange(start, stop, dtype=np.int64)
        unselected = ~selected[incoming_positions]
        if not bool(unselected.any()):
            continue
        incoming_positions = incoming_positions[unselected]
        incoming_digits = universe_digits[incoming_positions]
        deltas = _pair_deltas(delta_tables, incoming_digits, selected_digits)
        new_violations = current_violation + deltas
        minimum_violation = int(new_violations.min())
        if minimum_violation >= current_violation:
            continue
        incoming_rows, outgoing_columns = np.where(
            new_violations == minimum_violation
        )
        incoming = incoming_positions[incoming_rows]
        outgoing = selected_positions[outgoing_columns]
        losses = (
            selected_ev[outgoing_columns]
            - gross_ev[universe_indices[incoming]]
        )
        for offset in range(incoming.size):
            key = (
                minimum_violation,
                float(losses[offset]),
                int(universe_ranks[incoming[offset]]),
                int(selected_ranks[outgoing_columns[offset]]),
            )
            if best_key is None or key < best_key:
                best_key = key
                best_pair = (int(incoming[offset]), int(outgoing[offset]))
    return best_pair


def _improve_feasible_selection(
    *,
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    selected: np.ndarray,
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> None:
    while True:
        selected_positions = np.flatnonzero(selected)
        selected_digits = universe_digits[selected_positions]
        selected_ev = gross_ev[universe_indices[selected_positions]]
        selected_ranks = universe_ranks[selected_positions]
        worst_selected_rank = int(selected_ranks.max())
        delta_tables = _swap_delta_tables(counts, lower_bounds, upper_bounds)
        best_key: tuple[float, int, int] | None = None
        best_pair: tuple[int, int] | None = None
        for start in range(0, universe_indices.size, _SAFETY_PAIR_CHUNK_SIZE):
            stop = min(start + _SAFETY_PAIR_CHUNK_SIZE, universe_indices.size)
            incoming_positions = np.arange(start, stop, dtype=np.int64)
            eligible = (~selected[incoming_positions]) & (
                universe_ranks[incoming_positions] < worst_selected_rank
            )
            if not bool(eligible.any()):
                continue
            incoming_positions = incoming_positions[eligible]
            incoming_digits = universe_digits[incoming_positions]
            deltas = _pair_deltas(delta_tables, incoming_digits, selected_digits)
            incoming_rows, outgoing_columns = np.where(deltas == 0)
            if not incoming_rows.size:
                continue
            incoming = incoming_positions[incoming_rows]
            improves_rank = (
                universe_ranks[incoming]
                < selected_ranks[outgoing_columns]
            )
            incoming = incoming[improves_rank]
            outgoing_columns = outgoing_columns[improves_rank]
            if not incoming.size:
                continue
            gains = (
                gross_ev[universe_indices[incoming]]
                - selected_ev[outgoing_columns]
            )
            for offset in range(incoming.size):
                key = (
                    -float(gains[offset]),
                    int(universe_ranks[incoming[offset]]),
                    int(selected_ranks[outgoing_columns[offset]]),
                )
                if best_key is None or key < best_key:
                    best_key = key
                    best_pair = (
                        int(incoming[offset]),
                        int(selected_positions[outgoing_columns[offset]]),
                    )
        if best_pair is None:
            return
        _apply_swap(selected, counts, universe_digits, *best_pair)


def _swap_delta_tables(
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> np.ndarray:
    tables = np.zeros((counts.shape[0], 3, 3), dtype=np.int16)
    for event in range(counts.shape[0]):
        for incoming in range(3):
            for outgoing in range(3):
                if incoming == outgoing:
                    continue
                before = _cell_violation(
                    int(counts[event, outgoing]),
                    int(lower_bounds[event, outgoing]),
                    int(upper_bounds[event, outgoing]),
                ) + _cell_violation(
                    int(counts[event, incoming]),
                    int(lower_bounds[event, incoming]),
                    int(upper_bounds[event, incoming]),
                )
                after = _cell_violation(
                    int(counts[event, outgoing]) - 1,
                    int(lower_bounds[event, outgoing]),
                    int(upper_bounds[event, outgoing]),
                ) + _cell_violation(
                    int(counts[event, incoming]) + 1,
                    int(lower_bounds[event, incoming]),
                    int(upper_bounds[event, incoming]),
                )
                tables[event, incoming, outgoing] = after - before
    return tables


def _pair_deltas(
    delta_tables: np.ndarray,
    incoming_digits: np.ndarray,
    selected_digits: np.ndarray,
) -> np.ndarray:
    deltas = np.zeros(
        (incoming_digits.shape[0], selected_digits.shape[0]),
        dtype=np.int16,
    )
    for event in range(incoming_digits.shape[1]):
        deltas += delta_tables[
            event,
            incoming_digits[:, event, None],
            selected_digits[None, :, event],
        ]
    return deltas


def _apply_swap(
    selected: np.ndarray,
    counts: np.ndarray,
    universe_digits: np.ndarray,
    incoming_position: int,
    outgoing_position: int,
) -> None:
    outgoing_digits = universe_digits[outgoing_position]
    incoming_digits = universe_digits[incoming_position]
    for event, (outgoing, incoming) in enumerate(
        zip(outgoing_digits, incoming_digits, strict=True)
    ):
        counts[event, outgoing] -= 1
        counts[event, incoming] += 1
    selected[outgoing_position] = False
    selected[incoming_position] = True


def _structural_infeasibility_reasons(
    *,
    required: int,
    eligible_count: int,
    maximum_count: int,
    lower_bounds: np.ndarray,
) -> tuple[str, ...]:
    reasons = []
    if eligible_count < required:
        reasons.append(
            f"eligible_candidate_count_{eligible_count}_below_required_{required}"
        )
    for event in range(lower_bounds.shape[0]):
        if 3 * maximum_count < required:
            reasons.append(
                f"event_{event + 1}_concentration_capacity_below_package_size"
            )
        if int(lower_bounds[event].sum()) > required:
            reasons.append(
                f"event_{event + 1}_material_minimums_exceed_package_size"
            )
    return tuple(reasons)


def _constraint_violation(
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> int:
    below = np.maximum(lower_bounds - counts, 0)
    above = np.maximum(counts - upper_bounds, 0)
    return int(below.sum() + above.sum())


def _cell_violation(count: int, lower: int, upper: int) -> int:
    return max(lower - count, 0) + max(count - upper, 0)


def _coupon_digits(indices: np.ndarray, event_count: int) -> np.ndarray:
    values = np.asarray(indices, dtype=np.int64)
    digits = np.empty((values.size, event_count), dtype=np.int8)
    for event in range(event_count):
        divisor = 3 ** (event_count - event - 1)
        digits[:, event] = (values // divisor) % 3
    return digits


def _selection_counts(digits: np.ndarray, event_count: int) -> np.ndarray:
    counts = np.zeros((event_count, 3), dtype=np.int32)
    for event in range(event_count):
        counts[event] = np.bincount(digits[:, event], minlength=3)
    return counts


def _selection_diagnostics(
    *,
    gross_ev: np.ndarray,
    event_count: int,
    probabilities: tuple[tuple[float, float, float], ...],
    lower_bounds: np.ndarray,
    required: int,
    eligible_count: int,
    universe_count: int,
    universe_exhaustive: bool,
    maximum_count: int,
    baseline_indices: np.ndarray,
    baseline_ranks: np.ndarray,
    baseline_counts: np.ndarray,
    selected_indices: np.ndarray,
    selected_ranks: np.ndarray,
    selected_counts: np.ndarray,
    feasible: bool,
    reasons: tuple[str, ...],
) -> SafetyAwareSelectionDiagnostics:
    baseline_coupons = tuple(
        coupon_from_index(int(index), event_count) for index in baseline_indices
    )
    selected_pairs = sorted(
        zip(selected_ranks.tolist(), selected_indices.tolist(), strict=True)
    )
    selected_coupons = tuple(
        coupon_from_index(int(index), event_count) for _, index in selected_pairs
    )
    selected_index_set = {int(index) for index in selected_indices}
    baseline_index_set = {int(index) for index in baseline_indices}
    removed = [
        (int(rank), int(index))
        for rank, index in zip(baseline_ranks, baseline_indices, strict=True)
        if int(index) not in selected_index_set
    ]
    added = [
        (int(rank), int(index))
        for rank, index in selected_pairs
        if int(index) not in baseline_index_set
    ]
    replacements = tuple(
        SafetySelectionReplacement(
            outgoing_rank=outgoing_rank,
            outgoing_coupon=coupon_from_index(outgoing_index, event_count),
            outgoing_gross_ev=float(gross_ev[outgoing_index]),
            incoming_rank=incoming_rank,
            incoming_coupon=coupon_from_index(incoming_index, event_count),
            incoming_gross_ev=float(gross_ev[incoming_index]),
            gross_ev_delta=float(
                gross_ev[incoming_index] - gross_ev[outgoing_index]
            ),
        )
        for (outgoing_rank, outgoing_index), (incoming_rank, incoming_index) in zip(
            sorted(removed),
            sorted(added),
            strict=True,
        )
    )
    material_repairs = []
    for event, row in enumerate(probabilities):
        for outcome_index, probability in enumerate(row):
            before = int(baseline_counts[event, outcome_index])
            after = int(selected_counts[event, outcome_index])
            if lower_bounds[event, outcome_index] and before == 0 and after > 0:
                material_repairs.append(
                    SafetyMaterialRepair(
                        event=event + 1,
                        outcome=OUTCOMES[outcome_index],
                        probability=probability,
                        before_count=before,
                        after_count=after,
                    )
                )
    pre_sum = float(gross_ev[baseline_indices].sum(dtype=np.float64))
    post_sum = float(gross_ev[selected_indices].sum(dtype=np.float64))
    return SafetyAwareSelectionDiagnostics(
        required_coupon_count=required,
        eligible_candidate_count=eligible_count,
        candidate_universe_count=universe_count,
        candidate_universe_exhaustive=universe_exhaustive,
        concentration_maximum_count=maximum_count,
        pre_exposures=_exposure_diagnostics(baseline_counts),
        post_exposures=_exposure_diagnostics(selected_counts),
        material_outcomes_repaired=tuple(material_repairs),
        replacements=replacements,
        gross_ev_delta=post_sum - pre_sum,
        pre_package_sha256=_package_sha256(baseline_coupons),
        post_package_sha256=_package_sha256(selected_coupons),
        constraint_feasible=feasible,
        infeasibility_reasons=reasons,
    )


def _exposure_diagnostics(
    counts: np.ndarray,
) -> tuple[SafetySelectionExposure, ...]:
    total = int(counts[0].sum()) if counts.size else 0
    result = []
    for event, row in enumerate(counts):
        maximum_outcome_index = int(np.argmax(row))
        maximum = int(row[maximum_outcome_index])
        result.append(
            SafetySelectionExposure(
                event=event + 1,
                counts=tuple(int(value) for value in row),
                maximum_outcome=OUTCOMES[maximum_outcome_index],
                maximum_count=maximum,
                maximum_share=maximum / total if total else 0.0,
            )
        )
    return tuple(result)


def _package_sha256(coupons: Sequence[str]) -> str:
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def _infeasible_package(
    config: EVConfig,
    event_count: int,
    diagnostics: SafetyAwareSelectionDiagnostics,
) -> EVPackage:
    return EVPackage(
        decision="NO BET",
        coupons=(),
        cost=0,
        unused_bank=config.bank,
        expected_payout=0.0,
        modeled_roi=None,
        derived_brief=derive_brief((), event_count=event_count),
        decision_reason="safety_reselection_infeasible",
        selection_diagnostics=diagnostics,
    )


def _validated_selection_probabilities(
    probabilities: Sequence[Sequence[float]] | None,
    event_count: int,
) -> tuple[tuple[float, float, float], ...]:
    if probabilities is None or len(probabilities) != event_count:
        raise ValueError(
            "safety-aware selection requires one probability triplet per event"
        )
    rows = []
    for row in probabilities:
        if isinstance(row, (str, bytes)) or len(row) != 3:
            raise ValueError("safety-aware probability rows must contain 1/X/2")
        values = tuple(float(value) for value in row)
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            raise ValueError(
                "safety-aware probabilities must be finite and non-negative"
            )
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("safety-aware probability rows must sum to one")
        rows.append(values)
    return tuple(rows)


def _ranked_coupons(
    gross_ev: np.ndarray,
    event_count: int,
    order: np.ndarray,
    positions: np.ndarray,
) -> tuple[RankedCoupon, ...]:
    indices = order[positions]
    return tuple(
        RankedCoupon(
            rank=int(position) + 1,
            coupon=coupon_from_index(int(index), event_count),
            gross_ev=float(gross_ev[index]),
            net_ev=float(gross_ev[index] - 1.0),
        )
        for position, index in zip(positions, indices, strict=True)
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
