"""Paired prospective quality-v2 control versus quality-v3 research evaluation.

This module is deliberately core-only.  It accepts an already validated frozen
prefinal/final input identity, generates both packages with one capacity and
deterministic seed root, and later settles the pair without publishing coupon
strings or selecting an operator winner.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from toto_ai.ev.models import EVConfig, PackageDiversityMetrics
from toto_ai.ev.package_quality import (
    QUALITY_RELEASE_PROTOCOL_VERSION,
    PackageSelectionProvenance,
    package_quality_metrics,
    selection_context_sha256,
)
from toto_ai.operations.finished_draw import (
    EVENT_COUNT,
    VOID_RESULT,
    _compute_settlement,
)
from toto_ai.optimizer.robust_package import (
    RobustModelMetrics,
    RobustPackageResult,
    select_robust_package,
)
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyInput,
    StrategyResult,
    run_ev_crowd_current,
)
from toto_ai.optimizer.uncertainty_package import (
    DEFAULT_FLATTEN_WEIGHTS,
    build_uncertainty_models,
    control_relative_exposure_constraints,
    outcome_exposure,
    select_uncertainty_package,
)

QUALITY_V2 = "quality-v2"
QUALITY_V3 = "quality-v3"
QUALITY_V2_ROLE = "OPERATOR_CONTROL"
QUALITY_V3_ROLE = "RESEARCH_CHALLENGER_ONLY"
QUALITY_V3_VERSION = "quality-v3-bounded-uncertainty-v1"
PAIR_PROTOCOL_VERSION = "quality-v2-vs-v3-prospective-v1"
OUTCOMES = ("1", "X", "2")
_HEX = frozenset("0123456789abcdef")
_RESOLVED_STATUSES = frozenset({"resolved"})
_TERMINAL_VOID_STATUSES = frozenset({"void", "cancelled", "canceled"})
_POSTPONED_STATUSES = frozenset({"postponed", "postpone", "pst"})


class PairedQualityIntegrityError(ValueError):
    """Raised when a paired prospective identity or budget does not agree."""


class IncompletePairedResultsError(PairedQualityIntegrityError):
    """Raised when settlement is attempted with at least one pending event."""


@dataclass(frozen=True)
class QualityV3Config:
    """Hash-bound research-challenger policy."""

    category: int = 13
    flatten_weights: tuple[float, ...] = DEFAULT_FLATTEN_WEIGHTS
    top_count: int = 2_000
    candidate_sample_count: int = 4_000
    mutation_limit: int = 2_000
    scenario_sample_count: int = 10_000

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "flatten_weights",
            tuple(float(value) for value in self.flatten_weights),
        )
        if self.category != 13:
            raise ValueError("quality-v3 prospective category must be 13")
        if not self.flatten_weights or any(
            not math.isfinite(value) or not 0.0 < value < 1.0
            for value in self.flatten_weights
        ):
            raise ValueError("quality-v3 flatten weights must be finite in (0, 1)")
        if len(set(self.flatten_weights)) != len(self.flatten_weights):
            raise ValueError("quality-v3 flatten weights must be unique")
        if type(self.top_count) is not int or self.top_count <= 0:
            raise ValueError("quality-v3 top_count must be a positive int")
        if (
            type(self.candidate_sample_count) is not int
            or self.candidate_sample_count <= 0
        ):
            raise ValueError(
                "quality-v3 candidate_sample_count must be a positive int"
            )
        if type(self.mutation_limit) is not int or self.mutation_limit < 0:
            raise ValueError("quality-v3 mutation_limit must be a non-negative int")
        if (
            type(self.scenario_sample_count) is not int
            or self.scenario_sample_count <= 0
        ):
            raise ValueError(
                "quality-v3 scenario_sample_count must be a positive int"
            )

    def payload(self, *, coupon_capacity: int) -> dict[str, object]:
        return {
            "schema_version": 1,
            "strategy_version": QUALITY_V3_VERSION,
            "category": self.category,
            "coupon_capacity": coupon_capacity,
            "flatten_weights": list(self.flatten_weights),
            "top_count": self.top_count,
            "candidate_sample_count": self.candidate_sample_count,
            "mutation_limit": self.mutation_limit,
            "scenario_sample_count": self.scenario_sample_count,
            "candidate_source": "direct_top_sampled_mutated_per_model",
            "selector": "optimizer.robust_package.select_robust_package",
            "seed_protocol": PAIR_PROTOCOL_VERSION,
        }

    def config_sha256(self, *, coupon_capacity: int) -> str:
        return _sha256_json(self.payload(coupon_capacity=coupon_capacity))


@dataclass(frozen=True)
class ImmutableQualityInputIdentity:
    input_kind: Literal["prefinal", "final"]
    input_sha256: str
    frozen_input_sha256: str
    drawing_id: int
    drawing_number: int
    plan_id: str

    def __post_init__(self) -> None:
        if self.input_kind not in {"prefinal", "final"}:
            raise ValueError("input_kind must be prefinal or final")
        _validate_sha256(self.input_sha256, "input_sha256")
        _validate_sha256(self.frozen_input_sha256, "frozen_input_sha256")
        if type(self.drawing_id) is not int or self.drawing_id <= 0:
            raise ValueError("drawing_id must be a positive int")
        if type(self.drawing_number) is not int or self.drawing_number <= 0:
            raise ValueError("drawing_number must be a positive int")
        if not isinstance(self.plan_id, str) or not self.plan_id:
            raise ValueError("plan_id must be a non-empty string")


@dataclass(frozen=True)
class PairedStrategyIdentity:
    strategy_id: str
    strategy_version: str
    role: str
    config_sha256: str

    def __post_init__(self) -> None:
        if not self.strategy_id or not self.strategy_version or not self.role:
            raise ValueError("strategy identity fields must be non-empty")
        _validate_sha256(self.config_sha256, "strategy config_sha256")


@dataclass(frozen=True)
class EventExposureMetrics:
    event_order: int
    counts: tuple[int, int, int]
    shares: tuple[float, float, float]
    maximum_share: float


@dataclass(frozen=True)
class ConcentrationMetrics:
    fixed_event_count: int
    maximum_outcome_share: float
    mean_event_maximum_share: float


@dataclass(frozen=True)
class RobustScenarioMetrics:
    category: int
    sample_count_per_model: int
    worst_sampled_category_coverage: float
    mean_sampled_category_coverage: float
    models: tuple[RobustModelMetrics, ...]


@dataclass(frozen=True)
class ModeledPackageMetrics:
    probability_at_least_9: float
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float
    probability_method: str
    monte_carlo_seed: int
    monte_carlo_samples: int
    exposures: tuple[EventExposureMetrics, ...]
    concentration: ConcentrationMetrics
    diversity: PackageDiversityMetrics
    robust_scenarios: RobustScenarioMetrics


@dataclass(frozen=True)
class StrategyPackageEvaluation:
    identity: PairedStrategyIdentity
    input_sha256: str
    frozen_input_sha256: str
    requested_bank: int
    effective_budget: int
    stake: int
    coupon_capacity: int
    coupon_count: int
    cost: int
    unused_effective_budget: int
    package_sha256: str
    metrics: ModeledPackageMetrics
    coupons: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        _validate_sha256(self.input_sha256, "strategy input_sha256")
        _validate_sha256(self.frozen_input_sha256, "strategy frozen_input_sha256")
        _validate_sha256(self.package_sha256, "strategy package_sha256")
        object.__setattr__(self, "coupons", tuple(self.coupons))
        if self.coupon_count != len(self.coupons) or self.coupon_count <= 0:
            raise PairedQualityIntegrityError("strategy coupon count is invalid")
        if len(set(self.coupons)) != self.coupon_count or any(
            len(coupon) != EVENT_COUNT or set(coupon) - set(OUTCOMES)
            for coupon in self.coupons
        ):
            raise PairedQualityIntegrityError("strategy coupon package is invalid")
        if self.package_sha256 != _package_sha256(self.coupons):
            raise PairedQualityIntegrityError("strategy package hash mismatch")
        if self.requested_bank <= 0 or self.effective_budget <= 0 or self.stake <= 0:
            raise PairedQualityIntegrityError("strategy budget must be positive")
        if self.effective_budget > self.requested_bank:
            raise PairedQualityIntegrityError("effective budget exceeds bank")
        if self.coupon_capacity != self.effective_budget // self.stake:
            raise PairedQualityIntegrityError("strategy coupon capacity mismatch")
        if self.coupon_count > self.coupon_capacity:
            raise PairedQualityIntegrityError("strategy exceeds coupon capacity")
        if self.cost != self.coupon_count * self.stake:
            raise PairedQualityIntegrityError("strategy cost mismatch")
        if self.unused_effective_budget != self.effective_budget - self.cost:
            raise PairedQualityIntegrityError("strategy unused budget mismatch")

    def public_summary(self) -> dict[str, Any]:
        """Return a coupon-free prospective record."""
        payload = asdict(self)
        payload.pop("coupons")
        return payload


@dataclass(frozen=True)
class PairedQualityEvaluation:
    protocol_version: str
    input_identity: ImmutableQualityInputIdentity
    deterministic_seed_sha256: str
    control: StrategyPackageEvaluation
    challenger: StrategyPackageEvaluation
    operator_strategy_id: str = QUALITY_V2
    automatic_operator_switching: bool = False
    profitability_claimed: bool = False

    def __post_init__(self) -> None:
        if self.protocol_version != PAIR_PROTOCOL_VERSION:
            raise PairedQualityIntegrityError("paired protocol version mismatch")
        _validate_sha256(self.deterministic_seed_sha256, "deterministic seed")
        expected = {
            QUALITY_V2: (QUALITY_RELEASE_PROTOCOL_VERSION, QUALITY_V2_ROLE),
            QUALITY_V3: (QUALITY_V3_VERSION, QUALITY_V3_ROLE),
        }
        for package in (self.control, self.challenger):
            identity = package.identity
            if identity.strategy_id not in expected or (
                identity.strategy_version,
                identity.role,
            ) != expected[identity.strategy_id]:
                raise PairedQualityIntegrityError("strategy identity mismatch")
            if (
                package.input_sha256 != self.input_identity.input_sha256
                or package.frozen_input_sha256
                != self.input_identity.frozen_input_sha256
            ):
                raise PairedQualityIntegrityError("strategy input identity mismatch")
        if self.control.identity.strategy_id != QUALITY_V2:
            raise PairedQualityIntegrityError("quality-v2 must remain the control")
        if self.challenger.identity.strategy_id != QUALITY_V3:
            raise PairedQualityIntegrityError("quality-v3 must remain the challenger")
        budget_fields = (
            "requested_bank",
            "effective_budget",
            "stake",
            "coupon_capacity",
        )
        if any(
            getattr(self.control, name) != getattr(self.challenger, name)
            for name in budget_fields
        ):
            raise PairedQualityIntegrityError("paired strategy budget mismatch")
        if (
            self.operator_strategy_id != QUALITY_V2
            or self.automatic_operator_switching
            or self.profitability_claimed
        ):
            raise PairedQualityIntegrityError("unsafe paired decision policy")

    def public_summary(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "input_identity": asdict(self.input_identity),
            "deterministic_seed_sha256": self.deterministic_seed_sha256,
            "control": self.control.public_summary(),
            "challenger": self.challenger.public_summary(),
            "operator_strategy_id": self.operator_strategy_id,
            "automatic_operator_switching": False,
            "profitability_claimed": False,
        }


@dataclass(frozen=True)
class PairedResultEvent:
    event_order: int
    result: str | None
    result_status: str | None
    score: str | None = None

    def __post_init__(self) -> None:
        if type(self.event_order) is not int or not 0 <= self.event_order < EVENT_COUNT:
            raise ValueError("result event_order must be in 0..14")


@dataclass(frozen=True)
class PairedSettledResults:
    drawing_id: int
    drawing_number: int
    input_sha256: str
    events: tuple[PairedResultEvent, ...]

    def __post_init__(self) -> None:
        _validate_sha256(self.input_sha256, "result input_sha256")
        object.__setattr__(self, "events", tuple(self.events))
        if [event.event_order for event in self.events] != list(range(EVENT_COUNT)):
            raise ValueError("results must contain exactly event orders 0 through 14")


@dataclass(frozen=True)
class EventMissAttribution:
    event_order: int
    result_status: Literal["resolved", "void"]
    actual_outcome: str | None
    excluded_from_hit_denominator: bool
    actual_exposure_count: int | None
    actual_exposure_share: float | None
    actual_outcome_covered: bool | None
    best_coupon_miss_count: int
    any_best_coupon_missed: bool
    all_best_coupons_missed: bool
    concentration_gap: float | None


@dataclass(frozen=True)
class StrategySettlementMetrics:
    strategy: PairedStrategyIdentity
    package_sha256: str
    result_sha256: str
    coupon_count: int
    cost: int
    hit_denominator: int
    void_event_orders: tuple[int, ...]
    best_hits: int
    best_resolved_hits: int
    hit_13_count: int
    hit_14_count: int
    hit_15_count: int
    hit_at_least_13_count: int
    hit_at_least_14_count: int
    event_miss_attribution: tuple[EventMissAttribution, ...]


@dataclass(frozen=True)
class PairedQualitySettlement:
    protocol_version: str
    input_identity: ImmutableQualityInputIdentity
    result_sha256: str
    control: StrategySettlementMetrics
    challenger: StrategySettlementMetrics
    challenger_minus_control_best_hits: int
    challenger_minus_control_hit_13: int
    challenger_minus_control_hit_14: int
    challenger_minus_control_hit_15: int
    operator_strategy_id: str = QUALITY_V2
    automatic_operator_switching: bool = False
    profitability_evaluated: bool = False

    def __post_init__(self) -> None:
        if self.operator_strategy_id != QUALITY_V2:
            raise PairedQualityIntegrityError(
                "quality-v2 must remain the settlement operator strategy"
            )
        if self.automatic_operator_switching:
            raise PairedQualityIntegrityError(
                "automatic operator switching must remain disabled"
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the complete settlement without any coupon strings."""
        return asdict(self)


ControlGenerator = Callable[..., StrategyResult]
ChallengerGenerator = Callable[..., RobustPackageResult]
RobustEvaluator = Callable[..., RobustPackageResult]


def evaluate_paired_quality(
    *,
    frozen_input: FrozenStrategyInput,
    input_kind: Literal["prefinal", "final"],
    input_sha256: str,
    plan_id: str,
    quality_v2_config: EVConfig,
    quality_v2_provenance: PackageSelectionProvenance | None = None,
    quality_v3_config: QualityV3Config | None = None,
    control_generator: ControlGenerator = run_ev_crowd_current,
    challenger_generator: ChallengerGenerator = select_uncertainty_package,
    robust_evaluator: RobustEvaluator = select_robust_package,
) -> PairedQualityEvaluation:
    """Generate and evaluate the control/challenger pair from one frozen input."""

    if not isinstance(frozen_input, FrozenStrategyInput):
        raise TypeError("frozen_input must be a FrozenStrategyInput")
    resolved_v3_config = (
        QualityV3Config() if quality_v3_config is None else quality_v3_config
    )
    if not isinstance(resolved_v3_config, QualityV3Config):
        raise TypeError("quality_v3_config must be a QualityV3Config")
    _validate_sha256(input_sha256, "input_sha256")
    if (
        quality_v2_config.bank != frozen_input.bank
        or quality_v2_config.stake != frozen_input.stake
    ):
        raise PairedQualityIntegrityError("quality-v2 input budget mismatch")
    effective_budget = quality_v2_config.selection_budget
    coupon_capacity = quality_v2_config.max_coupons
    if effective_budget <= 0 or coupon_capacity <= 0:
        raise PairedQualityIntegrityError("paired effective budget must be positive")
    if resolved_v3_config.top_count < coupon_capacity:
        raise PairedQualityIntegrityError(
            "quality-v3 top_count is below the shared coupon capacity"
        )

    input_identity = ImmutableQualityInputIdentity(
        input_kind=input_kind,
        input_sha256=input_sha256,
        frozen_input_sha256=frozen_input.input_sha256,
        drawing_id=frozen_input.drawing_id,
        drawing_number=frozen_input.drawing_number,
        plan_id=plan_id,
    )
    control_config_sha256 = selection_context_sha256(quality_v2_config)
    challenger_config_sha256 = resolved_v3_config.config_sha256(
        coupon_capacity=coupon_capacity
    )
    seed_sha256 = _sha256_json(
        {
            "protocol_version": PAIR_PROTOCOL_VERSION,
            "input_identity": asdict(input_identity),
            "quality_v2_config_sha256": control_config_sha256,
            "quality_v3_config_sha256": challenger_config_sha256,
            "requested_bank": frozen_input.bank,
            "effective_budget": effective_budget,
            "stake": frozen_input.stake,
            "coupon_capacity": coupon_capacity,
        }
    )

    control_result = control_generator(
        frozen_input,
        config=quality_v2_config,
        category=13,
        provenance=quality_v2_provenance,
    )
    _validate_control_result(
        control_result,
        frozen_input=frozen_input,
        config=quality_v2_config,
        effective_budget=effective_budget,
    )
    if control_result.timed_out:
        raise PairedQualityIntegrityError("quality-v2 generation timed out")

    challenger_seed = f"{seed_sha256}:quality-v3"
    exposure_constraints = control_relative_exposure_constraints(
        frozen_input.bk_probability_matrix,
        control_coupons=control_result.coupons,
        package_size=coupon_capacity,
        floor_scale=quality_v2_config.package_exposure_floor_scale,
        floor_exponent=quality_v2_config.package_exposure_floor_exponent,
        near_fixed_share=quality_v2_config.package_near_fixed_share,
    )
    challenger_result = challenger_generator(
        bk_probabilities=frozen_input.bk_probability_matrix,
        anchor_coupons=control_result.coupons,
        category=resolved_v3_config.category,
        max_coupons=coupon_capacity,
        flatten_weights=resolved_v3_config.flatten_weights,
        top_count=resolved_v3_config.top_count,
        candidate_sample_count=resolved_v3_config.candidate_sample_count,
        mutation_limit=resolved_v3_config.mutation_limit,
        selection_sample_count=resolved_v3_config.scenario_sample_count,
        seed_material=challenger_seed,
        exposure_constraints=exposure_constraints,
        fallback_coupons=control_result.coupons,
    )
    uncertainty_models = build_uncertainty_models(
        frozen_input.bk_probability_matrix,
        flatten_weights=resolved_v3_config.flatten_weights,
    )
    _validate_robust_result(
        challenger_result,
        expected_coupons=challenger_result.selected_coupons,
        coupon_capacity=coupon_capacity,
        expected_models=tuple(uncertainty_models),
        category=resolved_v3_config.category,
        sample_count=resolved_v3_config.scenario_sample_count,
        label="quality-v3",
    )
    control_robust = robust_evaluator(
        candidates=control_result.coupons,
        probability_models=uncertainty_models,
        category=resolved_v3_config.category,
        max_coupons=len(control_result.coupons),
        sample_count=resolved_v3_config.scenario_sample_count,
        seed_material=f"{challenger_seed}-selector",
    )
    if control_robust.timed_out:
        raise PairedQualityIntegrityError("quality-v2 robust evaluation timed out")
    _validate_robust_result(
        control_robust,
        expected_coupons=control_result.coupons,
        coupon_capacity=coupon_capacity,
        expected_models=tuple(uncertainty_models),
        category=resolved_v3_config.category,
        sample_count=resolved_v3_config.scenario_sample_count,
        label="quality-v2 robust evaluation",
    )

    common = {
        "input_sha256": input_sha256,
        "frozen_input_sha256": frozen_input.input_sha256,
        "requested_bank": frozen_input.bank,
        "effective_budget": effective_budget,
        "stake": frozen_input.stake,
        "coupon_capacity": coupon_capacity,
    }
    metric_seed = f"{seed_sha256}:paired-model-evaluation"
    control = _package_evaluation(
        identity=PairedStrategyIdentity(
            strategy_id=QUALITY_V2,
            strategy_version=QUALITY_RELEASE_PROTOCOL_VERSION,
            role=QUALITY_V2_ROLE,
            config_sha256=control_config_sha256,
        ),
        coupons=control_result.coupons,
        robust_result=control_robust,
        probabilities=frozen_input.bk_probability_matrix,
        metric_seed=metric_seed,
        monte_carlo_samples=quality_v2_config.package_probability_samples,
        close_distance=quality_v2_config.package_diversity_close_distance,
        **common,
    )
    challenger = _package_evaluation(
        identity=PairedStrategyIdentity(
            strategy_id=QUALITY_V3,
            strategy_version=QUALITY_V3_VERSION,
            role=QUALITY_V3_ROLE,
            config_sha256=challenger_config_sha256,
        ),
        coupons=challenger_result.selected_coupons,
        robust_result=challenger_result,
        probabilities=frozen_input.bk_probability_matrix,
        metric_seed=metric_seed,
        monte_carlo_samples=quality_v2_config.package_probability_samples,
        close_distance=quality_v2_config.package_diversity_close_distance,
        **common,
    )
    return PairedQualityEvaluation(
        protocol_version=PAIR_PROTOCOL_VERSION,
        input_identity=input_identity,
        deterministic_seed_sha256=seed_sha256,
        control=control,
        challenger=challenger,
    )


def settle_paired_quality(
    pair: PairedQualityEvaluation,
    results: PairedSettledResults,
) -> PairedQualitySettlement:
    """Settle an intact pair and return only coupon-free comparison metrics."""

    if not isinstance(pair, PairedQualityEvaluation):
        raise TypeError("pair must be a PairedQualityEvaluation")
    if not isinstance(results, PairedSettledResults):
        raise TypeError("results must be PairedSettledResults")
    if (
        results.drawing_id != pair.input_identity.drawing_id
        or results.drawing_number != pair.input_identity.drawing_number
        or results.input_sha256 != pair.input_identity.input_sha256
    ):
        raise PairedQualityIntegrityError("settled result input identity mismatch")
    normalized = tuple(_normalized_result(event) for event in results.events)
    pending = tuple(
        event.event_order
        for event, outcome in zip(results.events, normalized, strict=True)
        if outcome is None
    )
    if pending:
        raise IncompletePairedResultsError(
            "paired settlement requires complete terminal results; pending orders: "
            + ", ".join(str(order) for order in pending)
        )
    actual = "".join(outcome for outcome in normalized if outcome is not None)
    result_sha256 = _sha256_json(
        [
            {
                "event_order": event.event_order,
                "result": outcome,
                "result_status": (
                    "void" if outcome == VOID_RESULT else "resolved"
                ),
                "score": "" if outcome == VOID_RESULT else event.score,
            }
            for event, outcome in zip(results.events, normalized, strict=True)
        ]
    )
    control = _settle_strategy(pair.control, actual, result_sha256)
    challenger = _settle_strategy(pair.challenger, actual, result_sha256)
    return PairedQualitySettlement(
        protocol_version=PAIR_PROTOCOL_VERSION,
        input_identity=pair.input_identity,
        result_sha256=result_sha256,
        control=control,
        challenger=challenger,
        challenger_minus_control_best_hits=(
            challenger.best_hits - control.best_hits
        ),
        challenger_minus_control_hit_13=(
            challenger.hit_13_count - control.hit_13_count
        ),
        challenger_minus_control_hit_14=(
            challenger.hit_14_count - control.hit_14_count
        ),
        challenger_minus_control_hit_15=(
            challenger.hit_15_count - control.hit_15_count
        ),
    )


def _validate_control_result(
    result: StrategyResult,
    *,
    frozen_input: FrozenStrategyInput,
    config: EVConfig,
    effective_budget: int,
) -> None:
    expected_config_sha256 = _sha256_json(
        {"category": 13, "ev_config": asdict(config)}
    )
    if (
        not isinstance(result, StrategyResult)
        or result.strategy_id != "EV_CROWD_CURRENT"
        or result.strategy_version != "v1"
        or result.input_sha256 != frozen_input.input_sha256
        or result.config_sha256 != expected_config_sha256
    ):
        raise PairedQualityIntegrityError("quality-v2 strategy identity mismatch")
    if result.requested_bank != frozen_input.bank or result.stake != frozen_input.stake:
        raise PairedQualityIntegrityError("quality-v2 result budget mismatch")
    if not result.coupons or result.cost > effective_budget:
        raise PairedQualityIntegrityError("quality-v2 result exceeds effective budget")


def _validate_robust_result(
    result: RobustPackageResult,
    *,
    expected_coupons: Sequence[str],
    coupon_capacity: int,
    expected_models: tuple[str, ...],
    category: int,
    sample_count: int,
    label: str,
) -> None:
    if not isinstance(result, RobustPackageResult) or result.timed_out:
        raise PairedQualityIntegrityError(f"{label} was incomplete")
    selected = tuple(result.selected_coupons)
    expected = tuple(expected_coupons)
    if (
        not selected
        or len(selected) > coupon_capacity
        or len(set(selected)) != len(selected)
        or set(selected) != set(expected)
    ):
        raise PairedQualityIntegrityError(f"{label} coupon identity mismatch")
    if result.category != category or result.sample_count_per_model != sample_count:
        raise PairedQualityIntegrityError(f"{label} scenario config mismatch")
    if tuple(metric.model for metric in result.model_metrics) != expected_models:
        raise PairedQualityIntegrityError(f"{label} scenario model mismatch")
    if any(
        not 0.0 <= value <= 1.0
        for value in (
            result.worst_sampled_category_coverage,
            result.mean_sampled_category_coverage,
            *(metric.sampled_category_coverage for metric in result.model_metrics),
        )
    ):
        raise PairedQualityIntegrityError(f"{label} scenario metric is invalid")


def _package_evaluation(
    *,
    identity: PairedStrategyIdentity,
    coupons: Sequence[str],
    robust_result: RobustPackageResult,
    probabilities: Sequence[Sequence[float]],
    metric_seed: str,
    monte_carlo_samples: int,
    close_distance: int,
    input_sha256: str,
    frozen_input_sha256: str,
    requested_bank: int,
    effective_budget: int,
    stake: int,
    coupon_capacity: int,
) -> StrategyPackageEvaluation:
    canonical = tuple(coupons)
    quality = package_quality_metrics(
        canonical,
        probabilities,
        seed_material=metric_seed,
        monte_carlo_samples=monte_carlo_samples,
        close_distance=close_distance,
    )
    exposure_rows = outcome_exposure(canonical)
    exposures = tuple(
        EventExposureMetrics(
            event_order=int(row["event_order"]),
            counts=tuple(int(row["counts"][outcome]) for outcome in OUTCOMES),
            shares=tuple(float(row["shares"][outcome]) for outcome in OUTCOMES),
            maximum_share=max(float(value) for value in row["shares"].values()),
        )
        for row in exposure_rows
    )
    maxima = tuple(row.maximum_share for row in exposures)
    concentration = ConcentrationMetrics(
        fixed_event_count=sum(value == 1.0 for value in maxima),
        maximum_outcome_share=max(maxima),
        mean_event_maximum_share=math.fsum(maxima) / len(maxima),
    )
    diversity = PackageDiversityMetrics(
        pairwise_distance_distribution=quality.pairwise_distance_distribution,
        minimum_pairwise_hamming=quality.minimum_pairwise_hamming,
        median_pairwise_hamming=quality.median_pairwise_hamming,
        mean_pairwise_hamming=quality.mean_pairwise_hamming,
        maximum_pairwise_hamming=quality.maximum_pairwise_hamming,
        close_pair_count=quality.close_pair_count,
        close_pair_share=quality.close_pair_share,
        effective_pattern_count=quality.effective_pattern_count,
    )
    modeled = ModeledPackageMetrics(
        probability_at_least_9=quality.probability_at_least_9,
        probability_at_least_13=quality.probability_at_least_13,
        probability_at_least_14=quality.probability_at_least_14,
        probability_at_least_15=quality.probability_at_least_15,
        probability_method=quality.probability_13_15_method,
        monte_carlo_seed=quality.monte_carlo_seed,
        monte_carlo_samples=quality.monte_carlo_samples,
        exposures=exposures,
        concentration=concentration,
        diversity=diversity,
        robust_scenarios=RobustScenarioMetrics(
            category=robust_result.category,
            sample_count_per_model=robust_result.sample_count_per_model,
            worst_sampled_category_coverage=(
                robust_result.worst_sampled_category_coverage
            ),
            mean_sampled_category_coverage=(
                robust_result.mean_sampled_category_coverage
            ),
            models=tuple(robust_result.model_metrics),
        ),
    )
    cost = len(canonical) * stake
    return StrategyPackageEvaluation(
        identity=identity,
        input_sha256=input_sha256,
        frozen_input_sha256=frozen_input_sha256,
        requested_bank=requested_bank,
        effective_budget=effective_budget,
        stake=stake,
        coupon_capacity=coupon_capacity,
        coupon_count=len(canonical),
        cost=cost,
        unused_effective_budget=effective_budget - cost,
        package_sha256=_package_sha256(canonical),
        metrics=modeled,
        coupons=canonical,
    )


def _normalized_result(event: PairedResultEvent) -> str | None:
    status = "" if event.result_status is None else event.result_status.strip().lower()
    result = "" if event.result is None else event.result.strip().upper()
    score = "" if event.score is None else event.score.strip()
    if result in OUTCOMES:
        if not score or status not in _RESOLVED_STATUSES:
            raise PairedQualityIntegrityError(
                f"event {event.event_order} resolved result is inconsistent"
            )
        return result
    if result in {VOID_RESULT, "VOID"}:
        if score or status not in _TERMINAL_VOID_STATUSES | _POSTPONED_STATUSES:
            raise PairedQualityIntegrityError(
                f"event {event.event_order} VOID result is inconsistent"
            )
        return VOID_RESULT
    if result:
        raise PairedQualityIntegrityError(
            f"event {event.event_order} result is unsupported"
        )
    if score:
        raise PairedQualityIntegrityError(
            f"event {event.event_order} pending result cannot have a score"
        )
    if status in _TERMINAL_VOID_STATUSES:
        return VOID_RESULT
    return None


def _settle_strategy(
    package: StrategyPackageEvaluation,
    actual: str,
    result_sha256: str,
) -> StrategySettlementMetrics:
    settlement = _compute_settlement(
        actual=actual,
        coupons=package.coupons,
        stake=package.stake,
        payments=None,
    )
    best_coupons = tuple(
        package.coupons[rank - 1] for rank in settlement["best_coupon_ranks"]
    )
    rows = []
    for exposure, outcome in zip(package.metrics.exposures, actual, strict=True):
        if outcome == VOID_RESULT:
            rows.append(
                EventMissAttribution(
                    event_order=exposure.event_order,
                    result_status="void",
                    actual_outcome=None,
                    excluded_from_hit_denominator=True,
                    actual_exposure_count=None,
                    actual_exposure_share=None,
                    actual_outcome_covered=None,
                    best_coupon_miss_count=0,
                    any_best_coupon_missed=False,
                    all_best_coupons_missed=False,
                    concentration_gap=None,
                )
            )
            continue
        outcome_index = OUTCOMES.index(outcome)
        exposure_count = exposure.counts[outcome_index]
        exposure_share = exposure.shares[outcome_index]
        miss_count = sum(
            coupon[exposure.event_order] != outcome for coupon in best_coupons
        )
        rows.append(
            EventMissAttribution(
                event_order=exposure.event_order,
                result_status="resolved",
                actual_outcome=outcome,
                excluded_from_hit_denominator=False,
                actual_exposure_count=exposure_count,
                actual_exposure_share=exposure_share,
                actual_outcome_covered=exposure_count > 0,
                best_coupon_miss_count=miss_count,
                any_best_coupon_missed=miss_count > 0,
                all_best_coupons_missed=miss_count == len(best_coupons),
                concentration_gap=exposure.maximum_share - exposure_share,
            )
        )
    distribution: Mapping[int, int] = settlement["hit_distribution"]
    void_orders = tuple(settlement["void_event_orders"])
    return StrategySettlementMetrics(
        strategy=package.identity,
        package_sha256=package.package_sha256,
        result_sha256=result_sha256,
        coupon_count=package.coupon_count,
        cost=package.cost,
        hit_denominator=EVENT_COUNT - len(void_orders),
        void_event_orders=void_orders,
        best_hits=int(settlement["best_hits"]),
        best_resolved_hits=int(settlement["best_hits"]) - len(void_orders),
        hit_13_count=distribution[13],
        hit_14_count=distribution[14],
        hit_15_count=distribution[15],
        hit_at_least_13_count=sum(distribution[value] for value in range(13, 16)),
        hit_at_least_14_count=sum(distribution[value] for value in range(14, 16)),
        event_miss_attribution=tuple(rows),
    )


def _validate_sha256(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _package_sha256(coupons: Sequence[str]) -> str:
    return hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode("utf-8")
    ).hexdigest()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
