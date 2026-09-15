"""Inactive numeric candidate entry; production does NOT import this module.

Native rank, seed-cover, exposure repair and quality optimization are reused.
Only their orchestration is local; no operational gate is disabled or mocked.
Outputs remain NOT_NATIVE_EQUIVALENT until a separate parity receipt proves
the relevant frozen configuration. This module never emits operator artifacts.
"""

import math
from dataclasses import dataclass

import numpy as np

from toto_ai.ev import package as native
from toto_ai.ev.models import EVConfig, EVSurface
from toto_ai.ev.package_quality import continuous_exposure_lower_bounds
from toto_ai.ev.runtime import checkpoint
from toto_ai.ev.ternary import MAX_EVENTS, coupon_from_index, index_from_coupon
from toto_ai.optimizer.category_hit import cover_14_bk_fill_seed
from toto_ai.research.raw_package_replay import ResearchInput, _sha


@dataclass(frozen=True)
class ResearchGenerationContext:
    input: ResearchInput
    seed_material: str
    operator_compatible: bool = False

    def __post_init__(self):
        if (
            not isinstance(self.input, ResearchInput)
            or self.operator_compatible is not False
        ):
            raise ValueError("verified research input required")
        _sha(self.seed_material)
        if self.input.config.selection_budget != self.input.frozen.bank:
            raise ValueError("research budget binding mismatch")


@dataclass(frozen=True)
class NumericCandidate:
    coupons: tuple[str, ...]
    reason: str | None
    universe_count: int
    operator_compatible: bool = False
    automatic_wagering: bool = False
    equivalence_status: str = "NOT_NATIVE_EQUIVALENT"


def generate_candidate(surface: EVSurface, context: ResearchGenerationContext):
    if surface.event_count != len(context.input.frozen.events):
        raise ValueError("surface event count mismatch")
    return select_numeric_candidate(
        surface,
        config=context.input.config,
        probabilities=context.input.frozen.bk_probability_matrix,
        seed_material=context.seed_material,
    )


def select_numeric_candidate(surface, *, config, probabilities, seed_material):
    """Same numeric steps as native _select_safety_aware_package; no authority."""
    if (
        not isinstance(config, EVConfig)
        or config.mode != "playable"
        or not config.package_safety_enabled
    ):
        raise ValueError("explicit safety-aware numeric configuration required")
    _sha(seed_material)
    gross_ev, event_count = native._validated_surface(surface)
    probabilities = native._validated_selection_probabilities(
        probabilities, event_count
    )
    required = config.max_coupons
    if not required:
        raise ValueError("positive coupon capacity required")
    order = native.rank_coupon_indices(surface)
    eligible_positions = np.flatnonzero(
        gross_ev[order] >= native._validated_minimum_ev(config.min_gross_ev)
    )
    eligible_indices = order[eligible_positions]
    # Preserve the native pre-seed eligible_count, including its expansion cap.
    eligible_count = int(eligible_indices.size)
    if event_count == MAX_EVENTS:
        seed = cover_14_bk_fill_seed(
            probabilities,
            config.selection_budget,
            config.stake,
            config.package_exposure_floor_scale,
            config.package_exposure_floor_exponent,
            config.package_near_fixed_share,
            config.package_concentration_headroom_share,
        )
        eligible_indices, _ = native._eligible_hybrid_candidate_indices(
            eligible_indices=eligible_indices,
            seed_indices=np.asarray(
                [index_from_coupon(c) for c in seed], dtype=np.int64
            ),
        )
        eligible_positions = np.arange(eligible_indices.size, dtype=np.int64)
    maximum_count = math.ceil(config.package_near_fixed_share * required) - 1
    lower = np.array(
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
    upper = np.full((event_count, 3), maximum_count, dtype=np.int32)
    headroom = math.ceil(config.package_concentration_headroom_share * required)
    soft_upper = np.maximum(
        lower,
        np.full((event_count, 3), max(0, maximum_count - headroom), dtype=np.int32),
    )
    reasons = native._structural_infeasibility_reasons(
        required=required,
        eligible_count=eligible_count,
        maximum_count=maximum_count,
        lower_bounds=lower,
    )
    if reasons:
        return NumericCandidate((), ";".join(reasons), 0)
    maximum_universe = min(eligible_count, native._SAFETY_MAX_CANDIDATES)
    size = min(
        maximum_universe,
        max(
            required,
            native._SAFETY_INITIAL_CANDIDATES,
            required * native._SAFETY_CANDIDATES_PER_COUPON,
        ),
    )
    positions = None
    while size:
        checkpoint("research_native_safety_repair", candidates=size)
        indices = eligible_indices[:size]
        ranks = eligible_positions[:size] + 1
        digits = native._coupon_digits(indices, event_count)
        positions, counts = native._repair_selection(
            gross_ev=gross_ev,
            universe_indices=indices,
            universe_ranks=ranks,
            universe_digits=digits,
            required=required,
            lower_bounds=lower,
            upper_bounds=upper,
            soft_upper_bounds=soft_upper,
        )
        if native._constraint_violation(counts, lower, upper) == 0:
            break
        if size == maximum_universe:
            positions = None
            break
        size = min(maximum_universe, size * native._SAFETY_CANDIDATE_EXPANSION)
    if positions is None:
        return NumericCandidate(
            (), "native_candidate_universe_no_feasible_repair", size
        )
    indices = eligible_indices[:size]
    ranks = eligible_positions[:size] + 1
    digits = native._coupon_digits(indices, event_count)
    positions, _, _, _, _ = native._improve_quality_selection(
        gross_ev=gross_ev,
        universe_indices=indices,
        universe_ranks=ranks,
        universe_digits=digits,
        selected_positions=positions,
        selected_counts=counts,
        lower_bounds=lower,
        upper_bounds=upper,
        soft_upper_bounds=soft_upper,
        probabilities=probabilities,
        config=config,
        seed_material_sha256=seed_material,
    )
    chosen = indices[positions][np.argsort(ranks[positions], kind="stable")]
    return NumericCandidate(
        tuple(coupon_from_index(int(i), event_count) for i in chosen), None, size
    )
