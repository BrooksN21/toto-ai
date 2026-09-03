"""Research-only direct package generation under bounded BK uncertainty.

Unlike the legacy BK/sports recombination, this module creates a fresh coupon
universe from the bookmaker matrix and deterministic probability-flattening
scenarios.  It has no scheduler, release, operator, or wagering integration.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Mapping, Sequence

from toto_ai.ev.package_quality import continuous_exposure_lower_bounds
from toto_ai.optimizer.coupon_candidates import generate_candidate_coupons
from toto_ai.optimizer.coupon_probabilities import ProbabilityMatrix
from toto_ai.optimizer.robust_package import (
    ExposureConstraints,
    RobustPackageResult,
    select_robust_package,
)

DEFAULT_FLATTEN_WEIGHTS = (0.10, 0.20)


def outcome_exposure(coupons: Sequence[str]) -> tuple[dict[str, object], ...]:
    """Return deterministic per-event 1/X/2 counts and shares."""

    if not coupons:
        return ()
    event_count = len(coupons[0])
    if any(
        len(coupon) != event_count or set(coupon) - set("1X2")
        for coupon in coupons
    ):
        raise ValueError("coupons must contain equal-length 1/X/2 rows")
    total = len(coupons)
    rows = []
    for event_order in range(event_count):
        counts = {outcome: 0 for outcome in "1X2"}
        for coupon in coupons:
            counts[coupon[event_order]] += 1
        rows.append(
            {
                "event_order": event_order,
                "counts": counts,
                "shares": {
                    outcome: counts[outcome] / total for outcome in "1X2"
                },
            }
        )
    return tuple(rows)


def flatten_probabilities(
    probabilities: Sequence[Sequence[float]],
    *,
    weight: float,
) -> ProbabilityMatrix:
    """Move every 1/X/2 row toward uniform without changing its ordering."""

    if not math.isfinite(weight) or not 0.0 < weight < 1.0:
        raise ValueError("flatten weight must be strictly between zero and one")
    source = _normalize_probability_matrix(probabilities)
    uniform = 1.0 / 3.0
    return tuple(
        tuple((1.0 - weight) * value + weight * uniform for value in row)
        for row in source
    )


def build_uncertainty_models(
    bk_probabilities: Sequence[Sequence[float]],
    *,
    flatten_weights: Sequence[float] = DEFAULT_FLATTEN_WEIGHTS,
) -> Mapping[str, ProbabilityMatrix]:
    """Return the immutable BK control plus predeclared uncertainty scenarios."""

    baseline = _normalize_probability_matrix(bk_probabilities)
    if not flatten_weights:
        raise ValueError("at least one flatten weight is required")
    models: dict[str, ProbabilityMatrix] = {"bk": baseline}
    seen_weights: set[float] = set()
    for raw_weight in flatten_weights:
        weight = float(raw_weight)
        if weight in seen_weights:
            raise ValueError("flatten weights must be unique")
        seen_weights.add(weight)
        name = f"flatten_{round(weight * 100):02d}"
        if name in models:
            raise ValueError("flatten weights must have distinct percentage names")
        models[name] = flatten_probabilities(baseline, weight=weight)
    return models


def select_uncertainty_package(
    *,
    bk_probabilities: Sequence[Sequence[float]],
    category: int,
    max_coupons: int,
    anchor_coupons: Sequence[str] = (),
    flatten_weights: Sequence[float] = DEFAULT_FLATTEN_WEIGHTS,
    top_count: int = 2_000,
    candidate_sample_count: int = 4_000,
    mutation_limit: int = 2_000,
    selection_sample_count: int = 10_000,
    seed_material: str = "uncertainty-package-v1",
    exposure_constraints: ExposureConstraints | None = None,
    fallback_coupons: Sequence[str] = (),
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> RobustPackageResult:
    """Generate a direct candidate universe and select a maximin package.

    ``anchor_coupons`` may preserve a production control inside the candidate
    universe, but selection is not limited to those coupons.  Every uncertainty
    model contributes independently generated top, sampled and mutated rows.
    """

    if type(max_coupons) is not int or max_coupons <= 0:
        raise ValueError("max_coupons must be a positive int")
    if type(top_count) is not int or top_count < max_coupons:
        raise ValueError("top_count must be at least max_coupons")
    if type(candidate_sample_count) is not int or candidate_sample_count <= 0:
        raise ValueError("candidate_sample_count must be a positive int")
    if type(mutation_limit) is not int or mutation_limit < 0:
        raise ValueError("mutation_limit must be a non-negative int")
    if type(selection_sample_count) is not int or selection_sample_count <= 0:
        raise ValueError("selection_sample_count must be a positive int")
    if not isinstance(seed_material, str) or not seed_material:
        raise ValueError("seed_material must be a non-empty string")

    models = build_uncertainty_models(
        bk_probabilities,
        flatten_weights=flatten_weights,
    )
    candidates = list(dict.fromkeys(anchor_coupons))
    for model_name, probabilities in models.items():
        candidates.extend(
            generate_candidate_coupons(
                probabilities,
                max_coupons=max_coupons,
                top_count=top_count,
                sample_count=candidate_sample_count,
                mutation_limit=mutation_limit,
                seed=_seed(seed_material, model_name),
            )
        )
    unique_candidates = tuple(dict.fromkeys(candidates))
    return select_robust_package(
        candidates=unique_candidates,
        probability_models=models,
        category=category,
        max_coupons=max_coupons,
        sample_count=selection_sample_count,
        seed_material=f"{seed_material}-selector",
        exposure_constraints=exposure_constraints,
        fallback_coupons=fallback_coupons,
        deadline=deadline,
        time_func=time_func,
    )


def control_relative_exposure_constraints(
    probabilities: Sequence[Sequence[float]],
    *,
    control_coupons: Sequence[str],
    package_size: int,
    floor_scale: float,
    floor_exponent: float,
    near_fixed_share: float,
) -> ExposureConstraints:
    """Build quality-v2 floors and a hard cap no looser than the control."""

    rows = _normalize_probability_matrix(probabilities)
    control = tuple(control_coupons)
    if len(control) != package_size:
        raise ValueError("control_coupons must fill the package")
    exposure = outcome_exposure(control)
    if len(exposure) != len(rows):
        raise ValueError("control_coupons and probabilities must have equal events")
    lower = tuple(
        continuous_exposure_lower_bounds(
            row,
            package_size=package_size,
            scale=floor_scale,
            exponent=floor_exponent,
        )
        for row in rows
    )
    control_maximum = max(
        int(count)
        for event in exposure
        for count in event["counts"].values()  # type: ignore[union-attr]
    )
    hard_maximum = math.ceil(near_fixed_share * package_size) - 1
    maximum = min(control_maximum, hard_maximum)
    upper = tuple((maximum, maximum, maximum) for _ in rows)
    constraints = ExposureConstraints(lower_bounds=lower, upper_bounds=upper)
    for event, counts in enumerate(exposure):
        for outcome_index, outcome in enumerate("1X2"):
            count = int(counts["counts"][outcome])  # type: ignore[index]
            if not lower[event][outcome_index] <= count <= maximum:
                raise ValueError("control package violates derived exposure bounds")
    return constraints


def _normalize_probability_matrix(
    probabilities: Sequence[Sequence[float]],
) -> ProbabilityMatrix:
    rows = []
    for raw_row in probabilities:
        if len(raw_row) != 3:
            raise ValueError("each probability row must contain three outcomes")
        values = tuple(float(value) for value in raw_row)
        total = math.fsum(values)
        if (
            not math.isfinite(total)
            or total <= 0.0
            or any(not math.isfinite(value) or value <= 0.0 for value in values)
        ):
            raise ValueError("probabilities must be finite and positive")
        rows.append(tuple(value / total for value in values))
    if not rows:
        raise ValueError("probability matrix must contain at least one event")
    return tuple(rows)


def _seed(seed_material: str, model_name: str) -> int:
    digest = hashlib.sha256(f"{seed_material}:{model_name}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
