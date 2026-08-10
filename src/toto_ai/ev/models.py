"""Immutable domain models for the expected-value package engine."""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from toto_ai.package.audit import PackageSafetyConfig

ProbabilityMatrix = tuple[tuple[float, float, float], ...]
EVMode = Literal["research", "playable"]
PlayTimingStatus = Literal[
    "playable",
    "multi_day",
    "unknown",
    "absent",
    "not_checked",
]


def _immutable_array(value: np.ndarray) -> np.ndarray:
    array = np.array(value, copy=True, order="C")
    backing = array.tobytes(order="C")
    return np.frombuffer(backing, dtype=array.dtype, count=array.size).reshape(
        array.shape,
    )


def _immutable_probability_matrix(value: ProbabilityMatrix) -> ProbabilityMatrix:
    matrix = tuple(tuple(row) for row in value)
    for row in matrix:
        if len(row) != 3:
            raise ValueError("probability rows must contain exactly three values")
    return matrix


def validate_config_bank(bank: int, stake: int) -> int:
    """Validate a bank without importing the prize helpers."""
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive int")
    if type(bank) is not int or bank <= 0:
        raise ValueError("bank must be a positive int")
    if bank % stake:
        raise ValueError("bank must be divisible by stake")
    return bank // stake


@dataclass(frozen=True)
class EVConfig:
    bank: int
    stake: int = 30
    mode: EVMode = "research"
    min_gross_ev: float = 1.0
    prize_fund_factor: float = 1.0
    possible_winnings: float | None = None
    effective_budget: int | None = None
    package_safety_enabled: bool = False
    package_near_fixed_share: float = 0.95
    package_low_probability_threshold: float = 0.20
    package_material_probability_threshold: float = 0.20
    package_exposure_floor_scale: float = 0.15
    package_exposure_floor_exponent: float = 1.0
    package_concentration_headroom_share: float = 0.03
    package_diversity_close_distance: int = 2
    package_diversity_weight: float = 0.10
    package_quality_repair_iterations: int = 12
    package_quality_candidate_count: int = 512
    package_probability_samples: int = 8_192
    package_optimization_probability_samples: int = 2_048
    package_category_probability_tolerance: float = 1e-12
    package_diversity_tolerance: float = 1e-12
    package_robust_ev_tolerance: float = 1e-12
    package_provenance_required: bool = False

    def __post_init__(self) -> None:
        validate_config_bank(self.bank, self.stake)
        if not isinstance(self.package_safety_enabled, bool):
            raise ValueError("package_safety_enabled must be a bool")
        if not isinstance(self.package_provenance_required, bool):
            raise ValueError("package_provenance_required must be a bool")
        if not 0.0 < self.package_exposure_floor_scale <= 1.0:
            raise ValueError("package_exposure_floor_scale must be in (0, 1]")
        if self.package_exposure_floor_exponent < 1.0:
            raise ValueError("package_exposure_floor_exponent must be at least 1")
        if not 0.0 <= self.package_concentration_headroom_share < 1.0:
            raise ValueError("package_concentration_headroom_share must be in [0, 1)")
        if (
            type(self.package_diversity_close_distance) is not int
            or self.package_diversity_close_distance < 0
        ):
            raise ValueError(
                "package_diversity_close_distance must be a non-negative int"
            )
        if not 0.0 <= self.package_diversity_weight <= 1.0:
            raise ValueError("package_diversity_weight must be in [0, 1]")
        if (
            type(self.package_quality_repair_iterations) is not int
            or self.package_quality_repair_iterations < 0
        ):
            raise ValueError(
                "package_quality_repair_iterations must be a non-negative int"
            )
        if (
            type(self.package_quality_candidate_count) is not int
            or self.package_quality_candidate_count <= 0
        ):
            raise ValueError("package_quality_candidate_count must be a positive int")
        if (
            type(self.package_probability_samples) is not int
            or self.package_probability_samples <= 0
        ):
            raise ValueError("package_probability_samples must be a positive int")
        if (
            type(self.package_optimization_probability_samples) is not int
            or self.package_optimization_probability_samples <= 0
        ):
            raise ValueError(
                "package_optimization_probability_samples must be a positive int"
            )
        for name, value in (
            (
                "package_category_probability_tolerance",
                self.package_category_probability_tolerance,
            ),
            ("package_diversity_tolerance", self.package_diversity_tolerance),
            ("package_robust_ev_tolerance", self.package_robust_ev_tolerance),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        _ = self.package_safety_config
        if self.effective_budget is not None:
            if type(self.effective_budget) is not int or self.effective_budget < 0:
                raise ValueError("effective_budget must be a non-negative int")
            if self.effective_budget > self.bank:
                raise ValueError("effective_budget cannot exceed bank")
            if self.effective_budget % self.stake:
                raise ValueError("effective_budget must be divisible by stake")

    @property
    def requested_bank(self) -> int:
        return self.bank

    @property
    def selection_budget(self) -> int:
        return self.bank if self.effective_budget is None else self.effective_budget

    @property
    def max_coupons(self) -> int:
        return self.selection_budget // self.stake

    @property
    def package_safety_config(self) -> PackageSafetyConfig:
        return PackageSafetyConfig(
            near_fixed_share=self.package_near_fixed_share,
            low_probability_threshold=self.package_low_probability_threshold,
            material_probability_threshold=self.package_material_probability_threshold,
        )


@dataclass(frozen=True)
class PlayTimingEligibility:
    status: PlayTimingStatus
    reason: str
    target_fingerprint: str | None
    fingerprint_match: bool

    def __post_init__(self) -> None:
        if self.status not in {
            "playable",
            "multi_day",
            "unknown",
            "absent",
            "not_checked",
        }:
            raise ValueError("invalid play timing eligibility status")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("timing eligibility reason must be non-empty")
        if self.target_fingerprint is not None and (
            not isinstance(self.target_fingerprint, str)
            or not self.target_fingerprint.strip()
        ):
            raise ValueError("target_fingerprint must be non-empty when present")
        if not isinstance(self.fingerprint_match, bool):
            raise ValueError("fingerprint_match must be a bool")
        if self.status == "not_checked":
            if self.target_fingerprint is not None or self.fingerprint_match:
                raise ValueError("not_checked timing cannot have a target match")
        elif (
            self.status in {"playable", "multi_day", "unknown"}
            and self.target_fingerprint is None
        ):
            raise ValueError("stored timing must include a target fingerprint")
        if self.status == "absent" and self.fingerprint_match:
            raise ValueError("absent timing cannot be an exact fingerprint match")
        if self.status in {"playable", "multi_day", "unknown"} and not (
            self.fingerprint_match
        ):
            raise ValueError("stored timing must be an exact fingerprint match")

    @classmethod
    def not_checked(cls) -> "PlayTimingEligibility":
        return cls(
            status="not_checked",
            reason="timing eligibility was not checked",
            target_fingerprint=None,
            fingerprint_match=False,
        )


@dataclass(frozen=True)
class EVInput:
    drawing_id: int
    drawing_number: int | None
    true_probabilities: ProbabilityMatrix
    crowd_probabilities: ProbabilityMatrix
    pool_sum: float
    jackpot: float
    possible_winnings: float
    probability_sources: tuple[str, ...]
    fetched_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "true_probabilities",
            _immutable_probability_matrix(self.true_probabilities),
        )
        object.__setattr__(
            self,
            "crowd_probabilities",
            _immutable_probability_matrix(self.crowd_probabilities),
        )
        object.__setattr__(
            self,
            "probability_sources",
            tuple(self.probability_sources),
        )


@dataclass(frozen=True)
class EVComponents:
    possible_winnings_ev_per_ruble: np.ndarray
    jackpot_ev_per_ruble: np.ndarray
    event_count: int
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "possible_winnings_ev_per_ruble",
            _immutable_array(self.possible_winnings_ev_per_ruble),
        )
        object.__setattr__(
            self,
            "jackpot_ev_per_ruble",
            _immutable_array(self.jackpot_ev_per_ruble),
        )


@dataclass(frozen=True)
class EVSurface:
    gross_ev: np.ndarray
    event_count: int
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "gross_ev", _immutable_array(self.gross_ev))


@dataclass(frozen=True)
class RankedCoupon:
    rank: int
    coupon: str
    gross_ev: float
    net_ev: float


@dataclass(frozen=True)
class SafetySelectionExposure:
    event: int
    counts: tuple[int, int, int]
    maximum_outcome: str
    maximum_count: int
    maximum_share: float


@dataclass(frozen=True)
class SafetyMaterialRepair:
    event: int
    outcome: str
    probability: float
    before_count: int
    after_count: int


@dataclass(frozen=True)
class SafetySelectionReplacement:
    outgoing_rank: int
    outgoing_coupon: str
    outgoing_gross_ev: float
    incoming_rank: int
    incoming_coupon: str
    incoming_gross_ev: float
    gross_ev_delta: float


@dataclass(frozen=True)
class PackageDiversityMetrics:
    pairwise_distance_distribution: tuple[tuple[int, int], ...]
    minimum_pairwise_hamming: int
    median_pairwise_hamming: float
    mean_pairwise_hamming: float
    maximum_pairwise_hamming: int
    close_pair_count: int
    close_pair_share: float
    effective_pattern_count: float


@dataclass(frozen=True)
class PackageCategoryProbabilityMetrics:
    probability_at_least_9: float
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float
    probability_9_method: str
    probability_13_15_method: str
    monte_carlo_seed: int
    monte_carlo_stream: str
    monte_carlo_samples: int
    monte_carlo_worst_case_95_error: float


@dataclass(frozen=True)
class SafetyAwareSelectionDiagnostics:
    required_coupon_count: int
    eligible_candidate_count: int
    candidate_universe_count: int
    candidate_universe_exhaustive: bool
    concentration_maximum_count: int
    pre_exposures: tuple[SafetySelectionExposure, ...]
    post_exposures: tuple[SafetySelectionExposure, ...]
    material_outcomes_repaired: tuple[SafetyMaterialRepair, ...]
    replacements: tuple[SafetySelectionReplacement, ...]
    gross_ev_delta: float
    pre_package_sha256: str
    post_package_sha256: str
    constraint_feasible: bool
    infeasibility_reasons: tuple[str, ...]
    exposure_floor_scale: float = 0.0
    exposure_floor_exponent: float = 1.0
    exposure_lower_bounds: tuple[tuple[int, int, int], ...] = ()
    exposure_continuous_targets: tuple[tuple[float, float, float], ...] = ()
    concentration_headroom_count: int = 0
    concentration_soft_maximum_count: int = 0
    headroom_violation_count: int = 0
    headroom_violations: tuple[str, ...] = ()
    pre_diversity: PackageDiversityMetrics | None = None
    post_diversity: PackageDiversityMetrics | None = None
    pre_category_probabilities: PackageCategoryProbabilityMetrics | None = None
    post_category_probabilities: PackageCategoryProbabilityMetrics | None = None
    robust_ev_score_delta: float = 0.0
    quality_repair_count: int = 0
    quality_objective_definition: str = (
        "lexicographic(P13+, P14+, P15, independent-MC P9+, diversity, "
        "robust log-EV); nested category probabilities are not added"
    )
    objective_order: tuple[str, ...] = (
        "probability_at_least_13",
        "probability_at_least_14",
        "probability_at_least_15",
        "independent_probability_at_least_9",
        "diversity",
        "robust_ev",
    )
    objective_tolerances: tuple[float, ...] = (
        1e-12,
        1e-12,
        1e-12,
        1e-12,
        1e-12,
        1e-12,
    )
    pre_lexicographic_objective: tuple[float, ...] | None = None
    post_lexicographic_objective: tuple[float, ...] | None = None
    probability_snapshot_sha256: str | None = None
    probability_input_sha256: str | None = None
    schedule_evidence_ledger_sha256: str | None = None
    schedule_evidence_semantic_hash: str | None = None
    provenance_complete: bool = False
    monte_carlo_seed_material_sha256: str | None = None
    optimization_monte_carlo_seed: int | None = None
    evaluation_monte_carlo_seed: int | None = None
    optimization_monte_carlo_samples: int = 0
    evaluation_monte_carlo_samples: int = 0
    optimization_monte_carlo_stream: str = "quality-v2-optimization"
    evaluation_monte_carlo_stream: str = "quality-v2-evaluation"
    numpy_version: str = np.__version__
    quality_v2_config_sha256: str | None = None
    selection_context_sha256: str | None = None
    release_protocol_version: str = "quality-v2-paper-only-v1"
    release_evidence_id: str | None = None
    release_evidence_sha256: str | None = None
    release_gate_decision: str = "NO BET"
    release_gate_reason: str = (
        "prospective holdout thresholds have not been predeclared and met"
    )
    real_money_actionable: bool = False
    diagnostics_sha256: str = ""


@dataclass(frozen=True)
class EVPackage:
    decision: Literal["PLAY", "NO BET", "RESEARCH ONLY"]
    coupons: tuple[RankedCoupon, ...]
    cost: int
    unused_bank: int
    expected_payout: float
    modeled_roi: float | None
    derived_brief: tuple[str, ...]
    decision_reason: str | None = None
    selection_diagnostics: SafetyAwareSelectionDiagnostics | None = None
    structural_status: Literal[
        "STRUCTURAL_PASS", "STRUCTURAL_FAIL", "NOT_EVALUATED"
    ] = "NOT_EVALUATED"
    artifact_class: Literal["TRAINING/PAPER", "NONE"] = "NONE"
    paper_coupons: tuple[RankedCoupon, ...] = ()
    paper_cost: int = 0
    paper_expected_payout: float = 0.0
    paper_modeled_roi: float | None = None
    paper_derived_brief: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "coupons", tuple(self.coupons))
        object.__setattr__(self, "derived_brief", tuple(self.derived_brief))
        object.__setattr__(self, "paper_coupons", tuple(self.paper_coupons))
        object.__setattr__(self, "paper_derived_brief", tuple(self.paper_derived_brief))
        if self.decision_reason is not None and (
            not isinstance(self.decision_reason, str)
            or not self.decision_reason.strip()
        ):
            raise ValueError("decision_reason must be non-empty when present")
        if self.structural_status == "STRUCTURAL_PASS":
            if self.decision != "NO BET" or self.artifact_class != "TRAINING/PAPER":
                raise ValueError(
                    "STRUCTURAL_PASS is paper-only and requires top-level NO BET"
                )
            if self.coupons or self.cost or self.expected_payout:
                raise ValueError("paper coupons cannot appear in actionable fields")
        if self.artifact_class == "TRAINING/PAPER" and (
            not self.paper_coupons or self.paper_cost <= 0
        ):
            raise ValueError("paper artifact requires coupons and positive paper cost")
