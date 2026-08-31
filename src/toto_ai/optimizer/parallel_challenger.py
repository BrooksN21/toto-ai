"""Deterministic policy for an isolated experimental package challenger.

The selector does not generate packages, mutate scheduler state, authorize a
wager, or export coupons.  It consumes already verified metrics and chooses a
winner under the predeclared non-degradation gate used by the drawing-4993
parallel experiment.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

CONTROL_STRATEGY_ID = "quality-v2"
POLICY_VERSION = "parallel-challenger-nondegradation-v1"
_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class ExactCategoryMetrics:
    model: str
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model:
            raise ValueError("model must be a non-empty string")
        values = (
            self.probability_at_least_13,
            self.probability_at_least_14,
            self.probability_at_least_15,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            for value in values
        ):
            raise ValueError("category probabilities must be finite in [0, 1]")
        if not values[0] >= values[1] >= values[2]:
            raise ValueError("category probabilities must be nested")


@dataclass(frozen=True)
class ParallelCandidate:
    strategy_id: str
    package_sha256: str
    coupon_count: int
    cost: int
    maximum_outcome_share: float
    eligible: bool
    rejection_reasons: tuple[str, ...]
    models: tuple[ExactCategoryMetrics, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id:
            raise ValueError("strategy_id must be a non-empty string")
        if (
            not isinstance(self.package_sha256, str)
            or len(self.package_sha256) != 64
            or set(self.package_sha256) - _HEX
        ):
            raise ValueError("package_sha256 must be lowercase SHA-256")
        if type(self.coupon_count) is not int or self.coupon_count < 0:
            raise ValueError("coupon_count must be a non-negative int")
        if type(self.cost) is not int or self.cost < 0:
            raise ValueError("cost must be a non-negative int")
        if (
            isinstance(self.maximum_outcome_share, bool)
            or not isinstance(self.maximum_outcome_share, (int, float))
            or not math.isfinite(float(self.maximum_outcome_share))
            or not 0.0 <= float(self.maximum_outcome_share) <= 1.0
        ):
            raise ValueError("maximum_outcome_share must be finite in [0, 1]")
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be a bool")
        object.__setattr__(self, "rejection_reasons", tuple(self.rejection_reasons))
        object.__setattr__(self, "models", tuple(self.models))
        if not self.models:
            raise ValueError("candidate must contain model metrics")
        names = tuple(row.model for row in self.models)
        if len(set(names)) != len(names):
            raise ValueError("candidate model names must be unique")
        if self.eligible and self.rejection_reasons:
            raise ValueError("eligible candidate cannot have rejection reasons")
        if self.eligible and (self.coupon_count == 0 or self.cost == 0):
            raise ValueError("eligible candidate must contain paid coupons")
        if not self.eligible and not self.rejection_reasons:
            raise ValueError("ineligible candidate must have rejection reasons")

    def model(self, name: str) -> ExactCategoryMetrics:
        for row in self.models:
            if row.model == name:
                return row
        raise ValueError(f"candidate {self.strategy_id} has no {name} model")

    @property
    def worst_p13(self) -> float:
        return min(row.probability_at_least_13 for row in self.models)

    @property
    def mean_p13(self) -> float:
        return math.fsum(row.probability_at_least_13 for row in self.models) / len(
            self.models
        )

    @property
    def worst_p14(self) -> float:
        return min(row.probability_at_least_14 for row in self.models)

    @property
    def worst_p15(self) -> float:
        return min(row.probability_at_least_15 for row in self.models)

    def public_summary(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParallelSelection:
    policy_version: str
    selected_strategy_id: str
    selected_package_sha256: str
    promoted: bool
    selection_reason: str
    rejections: dict[str, tuple[str, ...]]
    candidates: tuple[ParallelCandidate, ...]

    def public_summary(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "selected_strategy_id": self.selected_strategy_id,
            "selected_package_sha256": self.selected_package_sha256,
            "promoted": self.promoted,
            "selection_reason": self.selection_reason,
            "rejections": self.rejections,
            "candidates": [candidate.public_summary() for candidate in self.candidates],
            "automatic_wagering": False,
            "profitability_proven": False,
        }


def select_parallel_candidate(
    candidates: tuple[ParallelCandidate, ...],
    *,
    numeric_tolerance: float = 1e-12,
) -> ParallelSelection:
    """Select an experimental winner without weakening the BK control."""

    candidates = tuple(candidates)
    if len(candidates) != len({candidate.strategy_id for candidate in candidates}):
        raise ValueError("parallel strategy IDs must be unique")
    controls = tuple(
        candidate
        for candidate in candidates
        if candidate.strategy_id == CONTROL_STRATEGY_ID
    )
    if len(controls) != 1 or not controls[0].eligible:
        raise ValueError("one eligible quality-v2 control is required")
    if (
        isinstance(numeric_tolerance, bool)
        or not isinstance(numeric_tolerance, (int, float))
        or not math.isfinite(float(numeric_tolerance))
        or float(numeric_tolerance) < 0.0
    ):
        raise ValueError("numeric_tolerance must be finite and non-negative")
    tolerance = float(numeric_tolerance)
    control = controls[0]
    model_names = tuple(row.model for row in control.models)
    if any(
        tuple(row.model for row in candidate.models) != model_names
        for candidate in candidates
    ):
        raise ValueError("parallel candidates must use identical model sets")
    control_bk = control.model("bk")
    rejections: dict[str, tuple[str, ...]] = {}
    promotable: list[ParallelCandidate] = []

    for candidate in candidates:
        if candidate is control:
            continue
        reasons = list(candidate.rejection_reasons)
        if candidate.eligible:
            candidate_bk = candidate.model("bk")
            if (
                candidate_bk.probability_at_least_13
                < control_bk.probability_at_least_13 - tolerance
            ):
                reasons.append("bk_p13_below_control")
            if (
                candidate_bk.probability_at_least_14
                < control_bk.probability_at_least_14 - tolerance
            ):
                reasons.append("bk_p14_below_control")
            if (
                candidate_bk.probability_at_least_15
                < control_bk.probability_at_least_15 - tolerance
            ):
                reasons.append("bk_p15_below_control")
            if (
                candidate.maximum_outcome_share
                > control.maximum_outcome_share + tolerance
            ):
                reasons.append("concentration_above_control")
            if candidate.worst_p13 <= control.worst_p13 + tolerance:
                reasons.append("worst_model_p13_not_improved")
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            rejections[candidate.strategy_id] = tuple(reasons)
        else:
            promotable.append(candidate)

    if not promotable:
        selected = control
        reason = "no_challenger_passed_nondegradation_gate"
    else:
        selected = sorted(
            promotable,
            key=lambda candidate: (
                -candidate.worst_p13,
                -candidate.mean_p13,
                -candidate.worst_p14,
                -candidate.worst_p15,
                candidate.package_sha256,
            ),
        )[0]
        reason = "eligible_challenger_dominates_control_gate"

    return ParallelSelection(
        policy_version=POLICY_VERSION,
        selected_strategy_id=selected.strategy_id,
        selected_package_sha256=selected.package_sha256,
        promoted=selected is not control,
        selection_reason=reason,
        rejections=rejections,
        candidates=candidates,
    )
