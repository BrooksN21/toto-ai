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
from toto_ai.ev.package_quality import (
    OPTIMIZATION_MC_STREAM,
    ExactCategoryCoverage,
    PackageSelectionProvenance,
    continuous_exposure_lower_bounds,
    continuous_exposure_targets,
    deterministic_outcome_samples,
    deterministic_outcome_seed,
    diagnostics_with_hash,
    package_diversity_metrics,
    package_quality_metrics,
    quality_v2_config_sha256,
    selection_context_sha256,
    validate_selection_provenance,
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
    provenance: PackageSelectionProvenance | None = None,
) -> EVPackage:
    """Select a deterministic research or playable package from all coupons."""
    package, _ = select_ev_package_with_top_coupons(
        surface,
        config,
        probabilities=probabilities,
        provenance=provenance,
        diagnostic_limit=0,
    )
    return package


def select_ev_package_with_top_coupons(
    surface: EVSurface,
    config: EVConfig,
    *,
    probabilities: Sequence[Sequence[float]] | None = None,
    provenance: PackageSelectionProvenance | None = None,
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
                provenance=provenance,
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
    provenance: PackageSelectionProvenance | None,
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
            continuous_exposure_lower_bounds(
                row,
                package_size=required,
                scale=config.package_exposure_floor_scale,
                exponent=config.package_exposure_floor_exponent,
            )
            for row in probabilities
        ],
        dtype=np.int16,
    )
    continuous_targets = tuple(
        continuous_exposure_targets(
            row,
            package_size=required,
            scale=config.package_exposure_floor_scale,
            exponent=config.package_exposure_floor_exponent,
        )
        for row in probabilities
    )
    upper_bounds = np.full((event_count, 3), maximum_count, dtype=np.int32)
    headroom_count = math.ceil(config.package_concentration_headroom_share * required)
    soft_maximum_count = max(0, maximum_count - headroom_count)
    soft_upper_bounds = np.maximum(
        lower_bounds,
        np.full((event_count, 3), soft_maximum_count, dtype=np.int32),
    )
    (
        provenance_complete,
        provenance_reasons,
        probability_input_sha256,
        seed_material_sha256,
    ) = validate_selection_provenance(
        provenance,
        probabilities,
        config=config,
        required=config.package_provenance_required,
    )
    structural_reasons = (
        _structural_infeasibility_reasons(
            required=required,
            eligible_count=eligible_count,
            maximum_count=maximum_count,
            lower_bounds=lower_bounds,
        )
        + provenance_reasons
    )
    if structural_reasons:
        diagnostics = _selection_diagnostics(
            gross_ev=gross_ev,
            event_count=event_count,
            probabilities=probabilities,
            lower_bounds=lower_bounds,
            continuous_targets=continuous_targets,
            soft_upper_bounds=soft_upper_bounds,
            config=config,
            provenance=provenance,
            provenance_complete=provenance_complete,
            probability_input_sha256=probability_input_sha256,
            seed_material_sha256=seed_material_sha256,
            required=required,
            eligible_count=eligible_count,
            universe_count=eligible_count,
            universe_exhaustive=True,
            maximum_count=maximum_count,
            soft_maximum_count=soft_maximum_count,
            headroom_count=headroom_count,
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
    quality_repair_count = 0
    pre_quality_objective = None
    post_quality_objective = None
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
            soft_upper_bounds=soft_upper_bounds,
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
            continuous_targets=continuous_targets,
            soft_upper_bounds=soft_upper_bounds,
            config=config,
            provenance=provenance,
            provenance_complete=provenance_complete,
            probability_input_sha256=probability_input_sha256,
            seed_material_sha256=seed_material_sha256,
            required=required,
            eligible_count=eligible_count,
            universe_count=universe_count,
            universe_exhaustive=universe_exhaustive,
            maximum_count=maximum_count,
            soft_maximum_count=soft_maximum_count,
            headroom_count=headroom_count,
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
    universe_digits = _coupon_digits(universe_indices, event_count)
    (
        selected_positions,
        selected_counts,
        quality_repair_count,
        pre_quality_objective,
        post_quality_objective,
    ) = _improve_quality_selection(
        gross_ev=gross_ev,
        universe_indices=universe_indices,
        universe_ranks=universe_ranks,
        universe_digits=universe_digits,
        selected_positions=selected_positions,
        selected_counts=selected_counts,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        soft_upper_bounds=soft_upper_bounds,
        probabilities=probabilities,
        config=config,
        seed_material_sha256=seed_material_sha256,
    )
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
        continuous_targets=continuous_targets,
        soft_upper_bounds=soft_upper_bounds,
        config=config,
        provenance=provenance,
        provenance_complete=provenance_complete,
        probability_input_sha256=probability_input_sha256,
        seed_material_sha256=seed_material_sha256,
        required=required,
        eligible_count=eligible_count,
        universe_count=universe_count,
        universe_exhaustive=universe_exhaustive,
        maximum_count=maximum_count,
        soft_maximum_count=soft_maximum_count,
        headroom_count=headroom_count,
        baseline_indices=baseline_indices,
        baseline_ranks=baseline_ranks,
        baseline_counts=baseline_counts,
        selected_indices=selected_indices,
        selected_ranks=selected_ranks,
        selected_counts=selected_counts,
        feasible=True,
        reasons=(),
        quality_repair_count=quality_repair_count,
        pre_quality_objective=pre_quality_objective,
        post_quality_objective=post_quality_objective,
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
        decision="NO BET",
        coupons=(),
        cost=0,
        unused_bank=config.bank,
        expected_payout=0.0,
        modeled_roi=None,
        derived_brief=(),
        decision_reason="quality_v2_real_money_release_gate_closed",
        structural_status="STRUCTURAL_PASS",
        artifact_class="TRAINING/PAPER",
        paper_coupons=coupons,
        paper_cost=cost,
        paper_expected_payout=expected_payout,
        paper_modeled_roi=expected_payout / cost - 1.0,
        paper_derived_brief=derive_brief(
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
    soft_upper_bounds: np.ndarray,
) -> tuple[np.ndarray | None, np.ndarray]:
    selected = np.zeros(universe_indices.size, dtype=bool)
    selected[:required] = True
    counts = _selection_counts(universe_digits[:required], lower_bounds.shape[0])
    coupon_exposures = _coupon_exposures(universe_digits)
    maximum_iterations = required * lower_bounds.shape[0]
    for _ in range(maximum_iterations):
        violation = _constraint_violation(counts, lower_bounds, upper_bounds)
        headroom_violation = _upper_violation(counts, soft_upper_bounds)
        if violation == 0 and headroom_violation == 0:
            _improve_feasible_selection(
                gross_ev=gross_ev,
                universe_indices=universe_indices,
                universe_ranks=universe_ranks,
                universe_digits=universe_digits,
                selected=selected,
                counts=counts,
                lower_bounds=lower_bounds,
                upper_bounds=upper_bounds,
                soft_upper_bounds=soft_upper_bounds,
            )
            return np.flatnonzero(selected), counts
        pair = _best_repair_swap(
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            coupon_exposures=coupon_exposures,
            selected=selected,
            counts=counts,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            soft_upper_bounds=soft_upper_bounds,
            current_violation=violation,
            current_headroom_violation=headroom_violation,
        )
        if pair is None:
            if violation:
                return None, counts
            _improve_feasible_selection(
                gross_ev=gross_ev,
                universe_indices=universe_indices,
                universe_ranks=universe_ranks,
                universe_digits=universe_digits,
                selected=selected,
                counts=counts,
                lower_bounds=lower_bounds,
                upper_bounds=upper_bounds,
                soft_upper_bounds=soft_upper_bounds,
            )
            return np.flatnonzero(selected), counts
        incoming_position, outgoing_position = pair
        _apply_swap(
            selected,
            counts,
            universe_digits,
            incoming_position,
            outgoing_position,
        )
    if _constraint_violation(counts, lower_bounds, upper_bounds) == 0:
        return np.flatnonzero(selected), counts
    return None, counts


def _improve_quality_selection(
    *,
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    selected_positions: np.ndarray,
    selected_counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    soft_upper_bounds: np.ndarray,
    probabilities: tuple[tuple[float, float, float], ...],
    config: EVConfig,
    seed_material_sha256: str,
) -> tuple[
    np.ndarray,
    np.ndarray,
    int,
    tuple[float, ...] | None,
    tuple[float, ...] | None,
]:
    """Improve category/diversity quality lexicographically after safety.

    Safety and soft headroom are lexicographically fixed first. The quality
    The deterministic order is exact union P(13+), exact union P(14+), exact
    union P(15), independently sampled P(9+), Hamming diversity, then robust
    log-EV. The category probabilities are nested, never added or weighted.
    """
    if config.package_quality_repair_iterations == 0 or selected_positions.size < 2:
        return selected_positions, selected_counts, 0, None, None
    selected = np.zeros(universe_indices.size, dtype=bool)
    selected[selected_positions] = True
    counts = selected_counts.copy()
    probability_array = np.asarray(probabilities, dtype=np.float64)
    joint_probabilities = np.ones(universe_indices.size, dtype=np.float64)
    for event in range(universe_digits.shape[1]):
        joint_probabilities *= probability_array[
            event,
            universe_digits[:, event],
        ]
    exact_coverage = None
    modeled_samples = None
    if universe_digits.shape[1] == MAX_EVENTS:
        exact_coverage = ExactCategoryCoverage(
            tuple(
                coupon_from_index(int(universe_indices[position]), MAX_EVENTS)
                for position in selected_positions
            ),
            probabilities,
        )
        modeled_samples, _ = deterministic_outcome_samples(
            probabilities,
            seed_material=seed_material_sha256,
            sample_count=config.package_optimization_probability_samples,
            stream=OPTIMIZATION_MC_STREAM,
        )
    repairs = 0
    initial_quality: tuple[float, ...] | None = None
    final_quality: tuple[float, ...] | None = None
    tolerances = _quality_objective_tolerances(config)
    for _ in range(config.package_quality_repair_iterations):
        selected_positions = np.flatnonzero(selected)
        selected_digits = universe_digits[selected_positions]
        pairwise = np.count_nonzero(
            selected_digits[:, None, :] != selected_digits[None, :, :],
            axis=2,
        )
        upper_triangle = np.triu_indices(selected_positions.size, k=1)
        pair_distances = pairwise[upper_triangle]
        pair_count = pair_distances.size
        close_count = int(
            np.count_nonzero(pair_distances <= config.package_diversity_close_distance)
        )
        distance_sum = int(pair_distances.sum())
        close_contribution = np.count_nonzero(
            (pairwise <= config.package_diversity_close_distance) & (pairwise > 0),
            axis=1,
        )
        outgoing_order = np.lexsort(
            (
                universe_ranks[selected_positions],
                -close_contribution,
            )
        )[: min(8, selected_positions.size)]
        unselected_positions = np.flatnonzero(~selected)
        candidate_positions = _quality_candidate_positions(
            unselected_positions,
            config.package_quality_candidate_count,
        )
        if not candidate_positions.size:
            break
        current_soft_violation = _upper_violation(counts, soft_upper_bounds)
        current_p15 = float(joint_probabilities[selected_positions].sum())
        current_diversity = _diversity_objective(
            distance_sum,
            close_count,
            pair_count,
            universe_digits.shape[1],
        )
        selected_sample_distances = None
        current_probabilities = None
        if exact_coverage is not None and modeled_samples is not None:
            selected_sample_distances = np.count_nonzero(
                selected_digits[:, None, :] != modeled_samples[None, :, :],
                axis=2,
            )
            current_p9 = float(np.mean(selected_sample_distances.min(axis=0) <= 6))
            current_p13, current_p14, current_exact_p15 = exact_coverage.probabilities
            current_probabilities = (
                current_p13,
                current_p14,
                current_exact_p15,
                current_p9,
            )
        else:
            current_probabilities = (
                current_p15,
                current_p15,
                current_p15,
                0.0,
            )
        current_robust = float(
            np.log1p(gross_ev[universe_indices[selected_positions]]).sum(
                dtype=np.float64
            )
        )
        current_quality = _quality_objective_with_robust(
            current_probabilities,
            current_diversity,
            current_robust,
        )
        if initial_quality is None:
            initial_quality = current_quality
        final_quality = current_quality
        incoming_digits = universe_digits[candidate_positions]
        incoming_sample_distances = (
            None
            if modeled_samples is None
            else np.count_nonzero(
                incoming_digits[:, None, :] != modeled_samples[None, :, :],
                axis=2,
            )
        )
        best_key: tuple[int, int] | None = None
        best_pair: tuple[int, int] | None = None
        best_quality: tuple[float, ...] | None = None
        for outgoing_column in outgoing_order:
            outgoing_position = int(selected_positions[outgoing_column])
            retained = np.delete(selected_digits, outgoing_column, axis=0)
            retained_sample_minimum = (
                None
                if selected_sample_distances is None
                else np.delete(
                    selected_sample_distances,
                    outgoing_column,
                    axis=0,
                ).min(axis=0)
            )
            outgoing_coupon = (
                None
                if exact_coverage is None
                else coupon_from_index(
                    int(universe_indices[outgoing_position]),
                    MAX_EVENTS,
                )
            )
            incoming_distances = np.count_nonzero(
                incoming_digits[:, None, :] != retained[None, :, :],
                axis=2,
            )
            for row, incoming_position in enumerate(candidate_positions):
                candidate_counts = counts.copy()
                _apply_count_swap(
                    candidate_counts,
                    universe_digits[outgoing_position],
                    universe_digits[incoming_position],
                )
                if _constraint_violation(
                    candidate_counts,
                    lower_bounds,
                    upper_bounds,
                ):
                    continue
                candidate_soft = _upper_violation(
                    candidate_counts,
                    soft_upper_bounds,
                )
                if candidate_soft > current_soft_violation:
                    continue
                outgoing_close = int(
                    np.count_nonzero(
                        pairwise[outgoing_column]
                        <= config.package_diversity_close_distance
                    )
                    - 1
                )
                incoming_close = int(
                    np.count_nonzero(
                        incoming_distances[row]
                        <= config.package_diversity_close_distance
                    )
                )
                candidate_close = close_count - outgoing_close + incoming_close
                candidate_distance_sum = (
                    distance_sum
                    - int(pairwise[outgoing_column].sum())
                    + int(incoming_distances[row].sum())
                )
                candidate_diversity = _diversity_objective(
                    candidate_distance_sum,
                    candidate_close,
                    pair_count,
                    universe_digits.shape[1],
                )
                candidate_p15 = (
                    current_p15
                    - float(joint_probabilities[outgoing_position])
                    + float(joint_probabilities[incoming_position])
                )
                if (
                    exact_coverage is not None
                    and retained_sample_minimum is not None
                    and incoming_sample_distances is not None
                    and current_probabilities is not None
                    and outgoing_coupon is not None
                ):
                    candidate_p9 = float(
                        np.mean(
                            np.minimum(
                                retained_sample_minimum,
                                incoming_sample_distances[row],
                            )
                            <= 6
                        )
                    )
                    incoming_coupon = coupon_from_index(
                        int(universe_indices[incoming_position]),
                        MAX_EVENTS,
                    )
                    candidate_p13, candidate_p14, candidate_exact_p15 = (
                        exact_coverage.probabilities_after_swap(
                            outgoing_coupon,
                            incoming_coupon,
                        )
                    )
                    candidate_probabilities = (
                        candidate_p13,
                        candidate_p14,
                        candidate_exact_p15,
                        candidate_p9,
                    )
                else:
                    candidate_probabilities = (
                        candidate_p15,
                        candidate_p15,
                        candidate_p15,
                        0.0,
                    )
                robust_delta = math.log1p(
                    float(gross_ev[universe_indices[incoming_position]])
                ) - math.log1p(float(gross_ev[universe_indices[outgoing_position]]))
                candidate_quality = _quality_objective_with_robust(
                    candidate_probabilities,
                    candidate_diversity,
                    current_robust + robust_delta,
                )
                if (
                    _compare_quality_objectives(
                        candidate_quality,
                        current_quality,
                        tolerances,
                    )
                    <= 0
                ):
                    continue
                key = (
                    int(universe_ranks[incoming_position]),
                    int(universe_ranks[outgoing_position]),
                )
                if (
                    best_quality is None
                    or _compare_quality_objectives(
                        candidate_quality,
                        best_quality,
                        tolerances,
                    )
                    > 0
                    or (
                        _compare_quality_objectives(
                            candidate_quality,
                            best_quality,
                            tolerances,
                        )
                        == 0
                        and (best_key is None or key < best_key)
                    )
                ):
                    best_key = key
                    best_pair = (int(incoming_position), outgoing_position)
                    best_quality = candidate_quality
        if best_pair is None:
            break
        incoming_position, outgoing_position = best_pair
        if exact_coverage is not None:
            exact_coverage.apply_swap(
                coupon_from_index(int(universe_indices[outgoing_position]), MAX_EVENTS),
                coupon_from_index(int(universe_indices[incoming_position]), MAX_EVENTS),
            )
        _apply_swap(
            selected,
            counts,
            universe_digits,
            incoming_position,
            outgoing_position,
        )
        repairs += 1
        final_quality = best_quality
    return (
        np.flatnonzero(selected),
        counts,
        repairs,
        initial_quality,
        final_quality,
    )


def _quality_candidate_positions(
    positions: np.ndarray,
    limit: int,
) -> np.ndarray:
    if positions.size <= limit:
        return positions
    top_count = max(1, limit // 2)
    top = positions[:top_count]
    spread = positions[
        np.linspace(
            top_count,
            positions.size - 1,
            num=limit - top_count,
            dtype=np.int64,
        )
    ]
    return np.unique(np.concatenate((top, spread)))


def _diversity_objective(
    distance_sum: int,
    close_count: int,
    pair_count: int,
    event_count: int,
) -> float:
    if not pair_count:
        return 0.0
    return distance_sum / (pair_count * event_count) - close_count / pair_count


def _quality_objective(
    probabilities: tuple[float, float, float, float],
    diversity_score: float,
) -> tuple[float, ...]:
    """Return P13/P14/P15/P9/diversity/robust in comparison order."""
    robust_ev_score = 0.0
    if len(probabilities) != 4:
        raise ValueError("quality objective requires P13/P14/P15/P9")
    return (
        float(probabilities[0]),
        float(probabilities[1]),
        float(probabilities[2]),
        float(probabilities[3]),
        float(diversity_score),
        robust_ev_score,
    )


def _quality_objective_with_robust(
    probabilities: tuple[float, float, float, float],
    diversity_score: float,
    robust_ev_score: float,
) -> tuple[float, ...]:
    return (*_quality_objective(probabilities, diversity_score)[:-1], robust_ev_score)


def _quality_objective_tolerances(config: EVConfig) -> tuple[float, ...]:
    return (
        config.package_category_probability_tolerance,
        config.package_category_probability_tolerance,
        config.package_category_probability_tolerance,
        config.package_category_probability_tolerance,
        config.package_diversity_tolerance,
        config.package_robust_ev_tolerance,
    )


def _compare_quality_objectives(
    left: tuple[float, ...],
    right: tuple[float, ...],
    tolerances: tuple[float, ...],
) -> int:
    """Compare deterministic lexicographic objectives with per-tier deadbands."""
    if not (len(left) == len(right) == len(tolerances)):
        raise ValueError("objective values and tolerances must have equal lengths")
    for candidate, baseline, tolerance in zip(left, right, tolerances, strict=True):
        delta = candidate - baseline
        if delta > tolerance:
            return 1
        if delta < -tolerance:
            return -1
    return 0


def _apply_count_swap(
    counts: np.ndarray,
    outgoing_digits: np.ndarray,
    incoming_digits: np.ndarray,
) -> None:
    for event, (outgoing, incoming) in enumerate(
        zip(outgoing_digits, incoming_digits, strict=True)
    ):
        counts[event, outgoing] -= 1
        counts[event, incoming] += 1


def _best_repair_swap(
    *,
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    coupon_exposures: np.ndarray,
    selected: np.ndarray,
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
    soft_upper_bounds: np.ndarray,
    current_violation: int,
    current_headroom_violation: int,
) -> tuple[int, int] | None:
    selected_positions = np.flatnonzero(selected)
    selected_digits = universe_digits[selected_positions]
    selected_ev = gross_ev[universe_indices[selected_positions]]
    selected_ranks = universe_ranks[selected_positions]
    delta_tables = _swap_delta_tables(counts, lower_bounds, upper_bounds)
    soft_delta_tables = _swap_delta_tables(
        counts,
        np.zeros_like(lower_bounds),
        soft_upper_bounds,
    )
    unselected_positions = np.flatnonzero(~selected)
    hard_deficits = (counts < lower_bounds).reshape(-1)
    hard_excesses = (counts > upper_bounds).reshape(-1)
    soft_excesses = (counts > soft_upper_bounds).reshape(-1)
    incoming_hard_benefit = (
        np.any(coupon_exposures[unselected_positions][:, hard_deficits], axis=1)
        if bool(hard_deficits.any())
        else np.zeros(unselected_positions.size, dtype=bool)
    )
    outgoing_hard_benefit = (
        np.any(coupon_exposures[selected_positions][:, hard_excesses], axis=1)
        if bool(hard_excesses.any())
        else np.zeros(selected_positions.size, dtype=bool)
    )

    # Every strict hard-violation improvement must either add to a deficit or
    # remove from an excess. Evaluate that exact union without duplicate pairs.
    if current_violation:
        hard_groups = []
        beneficial_outgoing = np.flatnonzero(outgoing_hard_benefit)
        if beneficial_outgoing.size:
            hard_groups.append((unselected_positions, beneficial_outgoing))
        remaining_outgoing = np.flatnonzero(~outgoing_hard_benefit)
        beneficial_incoming = unselected_positions[incoming_hard_benefit]
        if beneficial_incoming.size and remaining_outgoing.size:
            hard_groups.append((beneficial_incoming, remaining_outgoing))
        best = _best_swap_from_groups(
            groups=hard_groups,
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            selected_positions=selected_positions,
            selected_digits=selected_digits,
            selected_ev=selected_ev,
            selected_ranks=selected_ranks,
            delta_tables=delta_tables,
            soft_delta_tables=soft_delta_tables,
            current_violation=current_violation,
            current_headroom_violation=current_headroom_violation,
            require_hard_improvement=True,
        )
        if best is not None:
            return best

    # With hard violation fixed (or with no direct hard improvement), a strict
    # soft improvement must remove an outcome currently above the soft bound.
    outgoing_soft_benefit = (
        np.any(coupon_exposures[selected_positions][:, soft_excesses], axis=1)
        if bool(soft_excesses.any())
        else np.zeros(selected_positions.size, dtype=bool)
    )
    beneficial_soft_outgoing = np.flatnonzero(outgoing_soft_benefit)
    if not beneficial_soft_outgoing.size:
        return None
    return _best_swap_from_groups(
        groups=[(unselected_positions, beneficial_soft_outgoing)],
        gross_ev=gross_ev,
        universe_indices=universe_indices,
        universe_ranks=universe_ranks,
        universe_digits=universe_digits,
        selected_positions=selected_positions,
        selected_digits=selected_digits,
        selected_ev=selected_ev,
        selected_ranks=selected_ranks,
        delta_tables=delta_tables,
        soft_delta_tables=soft_delta_tables,
        current_violation=current_violation,
        current_headroom_violation=current_headroom_violation,
        require_hard_improvement=False,
    )


def _best_swap_from_groups(
    *,
    groups: Sequence[tuple[np.ndarray, np.ndarray]],
    gross_ev: np.ndarray,
    universe_indices: np.ndarray,
    universe_ranks: np.ndarray,
    universe_digits: np.ndarray,
    selected_positions: np.ndarray,
    selected_digits: np.ndarray,
    selected_ev: np.ndarray,
    selected_ranks: np.ndarray,
    delta_tables: np.ndarray,
    soft_delta_tables: np.ndarray,
    current_violation: int,
    current_headroom_violation: int,
    require_hard_improvement: bool,
) -> tuple[int, int] | None:
    best_key: tuple[int, int, float, int, int] | None = None
    best_pair: tuple[int, int] | None = None
    for incoming_group, outgoing_columns in groups:
        if not incoming_group.size or not outgoing_columns.size:
            continue
        group_selected_digits = selected_digits[outgoing_columns]
        group_selected_ev = selected_ev[outgoing_columns]
        group_selected_ranks = selected_ranks[outgoing_columns]
        for start in range(0, incoming_group.size, _SAFETY_PAIR_CHUNK_SIZE):
            incoming_positions = incoming_group[start : start + _SAFETY_PAIR_CHUNK_SIZE]
            incoming_digits = universe_digits[incoming_positions]
            hard = current_violation + _pair_deltas(
                delta_tables,
                incoming_digits,
                group_selected_digits,
            )
            soft = current_headroom_violation + _pair_deltas(
                soft_delta_tables,
                incoming_digits,
                group_selected_digits,
            )
            valid = (
                hard < current_violation
                if require_hard_improvement
                else ((hard == current_violation) & (soft < current_headroom_violation))
            )
            local = _lexicographic_best_swap(
                valid=valid,
                hard=hard,
                soft=soft,
                incoming_positions=incoming_positions,
                outgoing_columns=outgoing_columns,
                incoming_ev=gross_ev[universe_indices[incoming_positions]],
                outgoing_ev=group_selected_ev,
                incoming_ranks=universe_ranks[incoming_positions],
                outgoing_ranks=group_selected_ranks,
            )
            if local is None:
                continue
            key, incoming_position, group_outgoing_column = local
            if best_key is None or key < best_key:
                best_key = key
                best_pair = (
                    incoming_position,
                    int(selected_positions[outgoing_columns[group_outgoing_column]]),
                )
    return best_pair


def _lexicographic_best_swap(
    *,
    valid: np.ndarray,
    hard: np.ndarray,
    soft: np.ndarray,
    incoming_positions: np.ndarray,
    outgoing_columns: np.ndarray,
    incoming_ev: np.ndarray,
    outgoing_ev: np.ndarray,
    incoming_ranks: np.ndarray,
    outgoing_ranks: np.ndarray,
) -> tuple[tuple[int, int, float, int, int], int, int] | None:
    """Find the exact lexicographic matrix minimum without Python pair loops."""
    if not bool(valid.any()):
        return None
    minimum_hard = int(hard[valid].min())
    candidates = valid & (hard == minimum_hard)
    minimum_soft = int(soft[candidates].min())
    candidates &= soft == minimum_soft
    losses = outgoing_ev[None, :] - incoming_ev[:, None]
    minimum_loss = float(losses[candidates].min())
    candidates &= losses == minimum_loss
    candidate_rows = np.flatnonzero(np.any(candidates, axis=1))
    minimum_incoming_rank = int(incoming_ranks[candidate_rows].min())
    incoming_row = int(
        candidate_rows[
            np.flatnonzero(incoming_ranks[candidate_rows] == minimum_incoming_rank)[0]
        ]
    )
    candidate_columns = np.flatnonzero(candidates[incoming_row])
    minimum_outgoing_rank = int(outgoing_ranks[candidate_columns].min())
    outgoing_column = int(
        candidate_columns[
            np.flatnonzero(outgoing_ranks[candidate_columns] == minimum_outgoing_rank)[
                0
            ]
        ]
    )
    key = (
        minimum_hard,
        minimum_soft,
        minimum_loss,
        minimum_incoming_rank,
        minimum_outgoing_rank,
    )
    return key, int(incoming_positions[incoming_row]), outgoing_column


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
    soft_upper_bounds: np.ndarray,
) -> None:
    while True:
        selected_positions = np.flatnonzero(selected)
        selected_digits = universe_digits[selected_positions]
        selected_ev = gross_ev[universe_indices[selected_positions]]
        selected_ranks = universe_ranks[selected_positions]
        worst_selected_rank = int(selected_ranks.max())
        delta_tables = _swap_delta_tables(counts, lower_bounds, upper_bounds)
        soft_delta_tables = _swap_delta_tables(
            counts,
            np.zeros_like(lower_bounds),
            soft_upper_bounds,
        )
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
            soft_deltas = _pair_deltas(
                soft_delta_tables,
                incoming_digits,
                selected_digits,
            )
            valid = (deltas == 0) & (soft_deltas <= 0)
            valid &= universe_ranks[incoming_positions, None] < selected_ranks[None, :]
            if not bool(valid.any()):
                continue
            gains = (
                gross_ev[universe_indices[incoming_positions], None]
                - selected_ev[None, :]
            )
            maximum_gain = float(gains[valid].max())
            candidates = valid & (gains == maximum_gain)
            candidate_rows = np.flatnonzero(np.any(candidates, axis=1))
            minimum_incoming_rank = int(
                universe_ranks[incoming_positions[candidate_rows]].min()
            )
            incoming_row = int(
                candidate_rows[
                    np.flatnonzero(
                        universe_ranks[incoming_positions[candidate_rows]]
                        == minimum_incoming_rank
                    )[0]
                ]
            )
            candidate_columns = np.flatnonzero(candidates[incoming_row])
            minimum_outgoing_rank = int(selected_ranks[candidate_columns].min())
            outgoing_column = int(
                candidate_columns[
                    np.flatnonzero(
                        selected_ranks[candidate_columns] == minimum_outgoing_rank
                    )[0]
                ]
            )
            key = (
                -maximum_gain,
                minimum_incoming_rank,
                minimum_outgoing_rank,
            )
            if best_key is None or key < best_key:
                best_key = key
                best_pair = (
                    int(incoming_positions[incoming_row]),
                    int(selected_positions[outgoing_column]),
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
            reasons.append(f"event_{event + 1}_material_minimums_exceed_package_size")
    return tuple(reasons)


def _constraint_violation(
    counts: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> int:
    below = np.maximum(lower_bounds - counts, 0)
    above = np.maximum(counts - upper_bounds, 0)
    return int(below.sum() + above.sum())


def _upper_violation(counts: np.ndarray, upper_bounds: np.ndarray) -> int:
    return int(np.maximum(counts - upper_bounds, 0).sum())


def _cell_violation(count: int, lower: int, upper: int) -> int:
    return max(lower - count, 0) + max(count - upper, 0)


def _coupon_digits(indices: np.ndarray, event_count: int) -> np.ndarray:
    values = np.asarray(indices, dtype=np.int64)
    digits = np.empty((values.size, event_count), dtype=np.int8)
    for event in range(event_count):
        divisor = 3 ** (event_count - event - 1)
        digits[:, event] = (values // divisor) % 3
    return digits


def _coupon_exposures(digits: np.ndarray) -> np.ndarray:
    """Precompute flattened one-hot outcome exposure for every coupon."""
    return np.eye(3, dtype=bool)[digits].reshape(digits.shape[0], -1)


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
    continuous_targets: tuple[tuple[float, float, float], ...],
    soft_upper_bounds: np.ndarray,
    config: EVConfig,
    provenance: PackageSelectionProvenance | None,
    provenance_complete: bool,
    probability_input_sha256: str,
    seed_material_sha256: str,
    required: int,
    eligible_count: int,
    universe_count: int,
    universe_exhaustive: bool,
    maximum_count: int,
    soft_maximum_count: int,
    headroom_count: int,
    baseline_indices: np.ndarray,
    baseline_ranks: np.ndarray,
    baseline_counts: np.ndarray,
    selected_indices: np.ndarray,
    selected_ranks: np.ndarray,
    selected_counts: np.ndarray,
    feasible: bool,
    reasons: tuple[str, ...],
    quality_repair_count: int = 0,
    pre_quality_objective: tuple[float, ...] | None = None,
    post_quality_objective: tuple[float, ...] | None = None,
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
            gross_ev_delta=float(gross_ev[incoming_index] - gross_ev[outgoing_index]),
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
            if before < lower_bounds[event, outcome_index] <= after or (
                before == 0 and after > 0 and probability > 0.0
            ):
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
    pre_diversity = package_diversity_metrics(
        baseline_coupons,
        close_distance=config.package_diversity_close_distance,
    )
    post_diversity = package_diversity_metrics(
        selected_coupons,
        close_distance=config.package_diversity_close_distance,
    )
    pre_category = None
    post_category = None
    if event_count == MAX_EVENTS:
        pre_category = package_quality_metrics(
            baseline_coupons,
            probabilities,
            seed_material=seed_material_sha256,
            monte_carlo_samples=config.package_probability_samples,
            close_distance=config.package_diversity_close_distance,
        )
        post_category = package_quality_metrics(
            selected_coupons,
            probabilities,
            seed_material=seed_material_sha256,
            monte_carlo_samples=config.package_probability_samples,
            close_distance=config.package_diversity_close_distance,
        )
    headroom_violations = tuple(
        f"event_{event + 1}_{OUTCOMES[outcome]}_exceeds_soft_maximum_by_{excess}"
        for event in range(event_count)
        for outcome in range(3)
        if (
            excess := int(
                max(
                    selected_counts[event, outcome] - soft_upper_bounds[event, outcome],
                    0,
                )
            )
        )
    )
    pre_robust = float(np.log1p(gross_ev[baseline_indices]).sum(dtype=np.float64))
    post_robust = float(np.log1p(gross_ev[selected_indices]).sum(dtype=np.float64))
    diagnostics = SafetyAwareSelectionDiagnostics(
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
        exposure_floor_scale=config.package_exposure_floor_scale,
        exposure_floor_exponent=config.package_exposure_floor_exponent,
        exposure_lower_bounds=tuple(
            tuple(int(value) for value in row) for row in lower_bounds
        ),
        exposure_continuous_targets=continuous_targets,
        concentration_headroom_count=headroom_count,
        concentration_soft_maximum_count=soft_maximum_count,
        headroom_violation_count=_upper_violation(
            selected_counts,
            soft_upper_bounds,
        ),
        headroom_violations=headroom_violations,
        pre_diversity=pre_diversity,
        post_diversity=post_diversity,
        pre_category_probabilities=pre_category,
        post_category_probabilities=post_category,
        robust_ev_score_delta=post_robust - pre_robust,
        quality_repair_count=quality_repair_count,
        pre_lexicographic_objective=pre_quality_objective,
        post_lexicographic_objective=post_quality_objective,
        objective_tolerances=(
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_diversity_tolerance,
            config.package_robust_ev_tolerance,
        ),
        probability_snapshot_sha256=(
            None if provenance is None else provenance.probability_snapshot_sha256
        ),
        probability_input_sha256=probability_input_sha256,
        schedule_evidence_ledger_sha256=(
            None if provenance is None else provenance.schedule_evidence_ledger_sha256
        ),
        schedule_evidence_semantic_hash=(
            None if provenance is None else provenance.schedule_evidence_semantic_hash
        ),
        provenance_complete=provenance_complete,
        monte_carlo_seed_material_sha256=seed_material_sha256,
        optimization_monte_carlo_seed=deterministic_outcome_seed(
            seed_material=seed_material_sha256,
            stream=OPTIMIZATION_MC_STREAM,
        ),
        evaluation_monte_carlo_seed=(
            None if post_category is None else post_category.monte_carlo_seed
        ),
        optimization_monte_carlo_samples=(
            config.package_optimization_probability_samples
        ),
        evaluation_monte_carlo_samples=config.package_probability_samples,
        quality_v2_config_sha256=quality_v2_config_sha256(config),
        selection_context_sha256=selection_context_sha256(config),
    )
    return diagnostics_with_hash(diagnostics)


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
        structural_status="STRUCTURAL_FAIL",
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
