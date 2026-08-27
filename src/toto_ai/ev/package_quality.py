"""Deterministic package-quality metrics and selector provenance primitives."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

from toto_ai.ev.models import (
    EVConfig,
    PackageCategoryProbabilityMetrics,
    PackageDiversityMetrics,
    SafetyAwareSelectionDiagnostics,
)
from toto_ai.ev.ternary import OUTCOMES
from toto_ai.external_odds.schedule_evidence import load_schedule_evidence_ledger
from toto_ai.package.audit import canonical_probability_input_sha256

_HEX_DIGITS = frozenset("0123456789abcdef")
OPTIMIZATION_MC_STREAM = "quality-v2-optimization"
EVALUATION_MC_STREAM = "quality-v2-evaluation"
QUALITY_RELEASE_PROTOCOL_VERSION = "quality-v2-paper-only-v1"
SUPPORTED_SCHEDULER_SCHEMA_VERSION = 8
QUALITY_OBJECTIVE_ORDER = (
    "probability_at_least_13",
    "probability_at_least_14",
    "probability_at_least_15",
    "independent_probability_at_least_9",
    "diversity",
    "robust_ev",
)
SELECTION_CONTEXT_SCHEMA_VERSION = 1


def quality_v2_config_payload(config: EVConfig) -> dict[str, object]:
    """Canonical complete selector policy bound into plans and diagnostics."""
    return {
        "exposure_floor_scale": config.package_exposure_floor_scale,
        "exposure_floor_exponent": config.package_exposure_floor_exponent,
        "concentration_headroom_share": (config.package_concentration_headroom_share),
        "repair_iterations": config.package_quality_repair_iterations,
        "candidate_count": config.package_quality_candidate_count,
        "optimization_samples": config.package_optimization_probability_samples,
        "evaluation_samples": config.package_probability_samples,
        "optimization_stream": OPTIMIZATION_MC_STREAM,
        "evaluation_stream": EVALUATION_MC_STREAM,
        "objective_order": list(QUALITY_OBJECTIVE_ORDER),
        "objective_tolerances": [
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_category_probability_tolerance,
            config.package_diversity_tolerance,
            config.package_robust_ev_tolerance,
        ],
        "diversity_close_distance": config.package_diversity_close_distance,
        "diversity_score_definition": ("mean_hamming/event_count-close_pair_share"),
        "release_protocol_version": QUALITY_RELEASE_PROTOCOL_VERSION,
        "rng": "numpy.random.Generator(PCG64)",
        "numpy_version": np.__version__,
        "exposure_boundary_policy": "ieee754_floor_without_epsilon",
    }


def quality_v2_config_sha256(config: EVConfig) -> str:
    return hashlib.sha256(
        json.dumps(
            quality_v2_config_payload(config),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def bound_selection_context(config: EVConfig) -> dict[str, object]:
    """Return every runtime policy input that can affect package selection.

    Requested and effective capacity are both explicit.  A scheduler plan's
    effective capacity is an authorization cap; the immutable drawing input
    may reduce the runtime capacity, but can never increase it.  The nested
    quality-v2 payload binds the complete algorithm policy separately from the
    surrounding EV and safety gates.
    """
    if not isinstance(config, EVConfig):
        raise TypeError("selection context config must be an EVConfig")
    return {
        "schema_version": SELECTION_CONTEXT_SCHEMA_VERSION,
        "mode": config.mode,
        "bank": config.bank,
        "stake": config.stake,
        "coupon_capacity": config.bank // config.stake,
        "effective_budget": config.selection_budget,
        "effective_coupon_capacity": config.max_coupons,
        "minimum_gross_ev": config.min_gross_ev,
        "near_fixed_share_limit": config.package_near_fixed_share,
        "low_probability_threshold": config.package_low_probability_threshold,
        "material_probability_threshold": (
            config.package_material_probability_threshold
        ),
        "package_safety_enabled": config.package_safety_enabled,
        "provenance_required": config.package_provenance_required,
        "quality_v2": quality_v2_config_payload(config),
    }


def selection_context_sha256(context: EVConfig | dict[str, object]) -> str:
    """Hash one canonical selection context without accepting partial data."""
    payload = (
        bound_selection_context(context)
        if isinstance(context, EVConfig)
        else context
    )
    if not isinstance(payload, dict):
        raise TypeError("selection context must be an EVConfig or dict")
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class PackageSelectionProvenance:
    """Hashes binding one selector run to its exact immutable inputs."""

    probability_snapshot_sha256: str
    probability_input_sha256: str
    schedule_evidence_ledger_sha256: str
    schedule_evidence_semantic_hash: str
    probability_snapshot_path: str | None = None
    schedule_evidence_ledger_path: str | None = None
    scheduler_plan_path: str | None = None
    scheduler_plan_sha256: str | None = None
    selection_context: dict[str, object] | None = None
    selection_context_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "probability_snapshot_sha256",
            "probability_input_sha256",
            "schedule_evidence_ledger_sha256",
            "schedule_evidence_semantic_hash",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or set(value) - _HEX_DIGITS
            ):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        if self.scheduler_plan_sha256 is not None and (
            len(self.scheduler_plan_sha256) != 64
            or set(self.scheduler_plan_sha256) - _HEX_DIGITS
        ):
            raise ValueError("scheduler_plan_sha256 must be a lowercase digest")
        if self.selection_context is not None:
            try:
                canonical = json.loads(
                    json.dumps(
                        self.selection_context,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                )
            except (TypeError, ValueError) as error:
                raise ValueError("selection_context must be canonical JSON") from error
            if not isinstance(canonical, dict):
                raise ValueError("selection_context must be a JSON object")
            object.__setattr__(self, "selection_context", canonical)
        if self.selection_context_sha256 is not None and (
            len(self.selection_context_sha256) != 64
            or set(self.selection_context_sha256) - _HEX_DIGITS
        ):
            raise ValueError("selection_context_sha256 must be a lowercase digest")

    @classmethod
    def from_artifacts(
        cls,
        *,
        probability_snapshot_path: str | Path,
        probability_input_sha256: str,
        schedule_evidence_ledger_path: str | Path,
        scheduler_plan_path: str | Path,
        selection_config: EVConfig,
    ) -> PackageSelectionProvenance:
        """Bind provenance to validated bytes from three local artifacts."""
        snapshot_path = Path(probability_snapshot_path).absolute()
        ledger_path = Path(schedule_evidence_ledger_path).absolute()
        plan_path = Path(scheduler_plan_path).absolute()
        for label, path in (
            ("probability snapshot", snapshot_path),
            ("schedule evidence ledger", ledger_path),
            ("scheduler plan", plan_path),
        ):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"{label} must be a regular non-symlink file")
        snapshot_bytes = snapshot_path.read_bytes()
        snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
        try:
            snapshot_document = json.loads(snapshot_bytes)
        except (TypeError, ValueError):
            snapshot_document = None
        if (
            isinstance(snapshot_document, dict)
            and "snapshot_sha256" in snapshot_document
        ):
            declared = snapshot_document.pop("snapshot_sha256")
            canonical = json.dumps(
                snapshot_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
            if (
                not isinstance(declared, str)
                or hashlib.sha256(canonical).hexdigest() != declared
            ):
                raise ValueError("probability snapshot declared hash mismatch")
            snapshot_hash = declared
        ledger = load_schedule_evidence_ledger(ledger_path)
        context = bound_selection_context(selection_config)
        return cls(
            probability_snapshot_sha256=snapshot_hash,
            probability_input_sha256=probability_input_sha256,
            schedule_evidence_ledger_sha256=hashlib.sha256(
                ledger_path.read_bytes()
            ).hexdigest(),
            schedule_evidence_semantic_hash=ledger.semantic_hash,
            probability_snapshot_path=str(snapshot_path),
            schedule_evidence_ledger_path=str(ledger_path),
            scheduler_plan_path=str(plan_path),
            scheduler_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            selection_context=context,
            selection_context_sha256=selection_context_sha256(context),
        )

    @property
    def seed_material_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "probability_snapshot_sha256": self.probability_snapshot_sha256,
                    "probability_input_sha256": self.probability_input_sha256,
                    "schedule_evidence_ledger_sha256": (
                        self.schedule_evidence_ledger_sha256
                    ),
                    "schedule_evidence_semantic_hash": (
                        self.schedule_evidence_semantic_hash
                    ),
                    "scheduler_plan_sha256": self.scheduler_plan_sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def validate_selection_provenance(
    provenance: PackageSelectionProvenance | None,
    probabilities: Sequence[Sequence[float]],
    *,
    config: EVConfig,
    required: bool,
) -> tuple[bool, tuple[str, ...], str, str]:
    """Return completeness, fail-closed reasons, probability hash, and seed hash."""
    probability_hash = selection_probability_input_sha256(probabilities)
    if provenance is None:
        reason = ("selection_provenance_missing",) if required else ()
        seed_hash = hashlib.sha256(probability_hash.encode("ascii")).hexdigest()
        return False, reason, probability_hash, seed_hash
    if provenance.probability_input_sha256 != probability_hash:
        return (
            False,
            ("probability_input_sha256_mismatch",),
            probability_hash,
            provenance.seed_material_sha256,
        )
    expected_context = bound_selection_context(config)
    artifact_reasons = _artifact_provenance_reasons(
        provenance,
        expected_context=expected_context,
    )
    if required and artifact_reasons:
        return (
            False,
            artifact_reasons,
            probability_hash,
            provenance.seed_material_sha256,
        )
    return not artifact_reasons, (), probability_hash, provenance.seed_material_sha256


def _artifact_provenance_reasons(
    provenance: PackageSelectionProvenance,
    *,
    expected_context: dict[str, object],
) -> tuple[str, ...]:
    """Validate referenced local artifacts, never merely digest syntax."""
    reasons: list[str] = []
    if provenance.selection_context is None:
        reasons.append("selection_context_missing")
    if provenance.selection_context_sha256 is None:
        reasons.append("selection_context_sha256_missing")
    elif provenance.selection_context is not None and (
        selection_context_sha256(provenance.selection_context)
        != provenance.selection_context_sha256
    ):
        reasons.append("selection_context_sha256_mismatch")
    if provenance.selection_context != expected_context:
        reasons.append("selection_context_mismatch")
    snapshot = _bound_regular_file(
        provenance.probability_snapshot_path,
        provenance.probability_snapshot_sha256,
        "probability_snapshot",
        reasons,
    )
    if snapshot is not None:
        try:
            snapshot_document = json.loads(snapshot.read_bytes())
        except (OSError, TypeError, ValueError):
            reasons.append("probability_snapshot_invalid")
        else:
            declared_probability_hash = snapshot_document.get(
                "probability_input_sha256"
            )
            if declared_probability_hash is None:
                declared_probability_hash = snapshot_document.get(
                    "true_probability_input_sha256"
                )
            if declared_probability_hash is None:
                declared_probability_hash = _snapshot_probability_hash(
                    snapshot_document
                )
            if declared_probability_hash != provenance.probability_input_sha256:
                reasons.append("probability_snapshot_input_hash_mismatch")
    ledger = _bound_regular_file(
        provenance.schedule_evidence_ledger_path,
        provenance.schedule_evidence_ledger_sha256,
        "schedule_evidence_ledger",
        reasons,
    )
    if ledger is not None:
        try:
            semantic_hash = load_schedule_evidence_ledger(ledger).semantic_hash
        except (OSError, TypeError, ValueError):
            reasons.append("schedule_evidence_ledger_invalid")
        else:
            if semantic_hash != provenance.schedule_evidence_semantic_hash:
                reasons.append("schedule_evidence_semantic_hash_mismatch")
    if provenance.scheduler_plan_path is None:
        reasons.append("scheduler_plan_artifact_missing")
    elif provenance.scheduler_plan_sha256 is None:
        reasons.append("scheduler_plan_sha256_missing")
    else:
        plan = _bound_regular_file(
            provenance.scheduler_plan_path,
            provenance.scheduler_plan_sha256,
            "scheduler_plan",
            reasons,
        )
        if plan is not None:
            _validate_scheduler_plan_artifact(
                plan,
                reasons,
                expected_context=expected_context,
            )
    return tuple(dict.fromkeys(reasons))


def _validate_scheduler_plan_artifact(
    path: Path,
    reasons: list[str],
    *,
    expected_context: dict[str, object],
) -> None:
    """Require a canonical scheduler-plan shape, not merely arbitrary bytes."""
    try:
        document = json.loads(path.read_bytes())
    except (OSError, TypeError, ValueError):
        reasons.append("scheduler_plan_invalid")
        return
    if not isinstance(document, dict):
        reasons.append("scheduler_plan_invalid")
        return
    semantic = {
        key: value
        for key, value in document.items()
        if key not in {"plan_id", "deadlines"}
    }
    expected_plan_id = hashlib.sha256(
        json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    config = document.get("config")
    quality = config.get("quality_v2") if isinstance(config, dict) else None
    if (
        document.get("schema_version") != SUPPORTED_SCHEDULER_SCHEMA_VERSION
        or not isinstance(document.get("target"), dict)
        or not isinstance(document.get("paths"), dict)
        or not isinstance(document.get("deadlines"), dict)
        or document.get("plan_id") != expected_plan_id
        or not isinstance(quality, dict)
        or quality.get("release_protocol_version")
        != QUALITY_RELEASE_PROTOCOL_VERSION
    ):
        reasons.append("scheduler_plan_invalid")
        return
    plan_context = config.get("selection_context")
    if not isinstance(plan_context, dict) or not _selection_context_authorizes(
        plan_context,
        expected_context,
    ):
        reasons.append("scheduler_plan_selection_context_mismatch")
    try:
        plan_context_sha256 = (
            selection_context_sha256(plan_context)
            if isinstance(plan_context, dict)
            else None
        )
    except (TypeError, ValueError):
        plan_context_sha256 = None
    if config.get("selection_context_sha256") != plan_context_sha256:
        reasons.append("scheduler_plan_selection_context_sha256_mismatch")


def _selection_context_authorizes(
    plan_context: dict[str, object],
    runtime_context: dict[str, object],
) -> bool:
    """Return whether one plan context authorizes the exact runtime context."""
    capacity_fields = {"effective_budget", "effective_coupon_capacity"}
    if set(plan_context) != set(runtime_context):
        return False
    if any(
        plan_context[field] != runtime_context[field]
        for field in plan_context.keys() - capacity_fields
    ):
        return False

    bank = runtime_context.get("bank")
    stake = runtime_context.get("stake")
    coupon_capacity = runtime_context.get("coupon_capacity")
    plan_budget = plan_context.get("effective_budget")
    runtime_budget = runtime_context.get("effective_budget")
    plan_capacity = plan_context.get("effective_coupon_capacity")
    runtime_capacity = runtime_context.get("effective_coupon_capacity")
    integer_values = (
        bank,
        stake,
        coupon_capacity,
        plan_budget,
        runtime_budget,
        plan_capacity,
        runtime_capacity,
    )
    if any(type(value) is not int for value in integer_values):
        return False
    assert isinstance(bank, int)
    assert isinstance(stake, int)
    assert isinstance(coupon_capacity, int)
    assert isinstance(plan_budget, int)
    assert isinstance(runtime_budget, int)
    assert isinstance(plan_capacity, int)
    assert isinstance(runtime_capacity, int)
    return (
        bank > 0
        and stake > 0
        and bank % stake == 0
        and coupon_capacity == bank // stake
        and 0 <= runtime_budget <= plan_budget <= bank
        and plan_budget % stake == 0
        and runtime_budget % stake == 0
        and plan_capacity == plan_budget // stake
        and runtime_capacity == runtime_budget // stake
    )


def _snapshot_probability_hash(document: object) -> str | None:
    """Extract canonical BK probabilities from a frozen drawing JSON artifact."""
    if not isinstance(document, dict):
        return None
    payload = document.get("payload", document)
    data = payload.get("data") if isinstance(payload, dict) else None
    events = data.get("events") if isinstance(data, dict) else None
    if not isinstance(events, list):
        return None
    try:
        ordered = sorted(events, key=lambda event: int(event["order"]))
        rows = []
        for event in ordered:
            quotes = event["quotes"]
            raw = (
                float(quotes["bk_win_1"]),
                float(quotes["bk_draw"]),
                float(quotes["bk_win_2"]),
            )
            total = math.fsum(raw)
            rows.append(tuple(value / total for value in raw))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return selection_probability_input_sha256(rows)


def _bound_regular_file(
    path_text: str | None,
    expected_sha256: str,
    label: str,
    reasons: list[str],
) -> Path | None:
    if path_text is None:
        reasons.append(f"{label}_artifact_missing")
        return None
    path = Path(path_text)
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("not a regular non-symlink file")
        content = path.read_bytes()
    except OSError:
        reasons.append(f"{label}_artifact_unreadable")
        return None
    content_hash = hashlib.sha256(content).hexdigest()
    if content_hash != expected_sha256:
        declared_snapshot_hash = None
        if label == "probability_snapshot":
            try:
                document = json.loads(content)
                declared_snapshot_hash = document.pop("snapshot_sha256")
                canonical = json.dumps(
                    document,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            except (AttributeError, KeyError, TypeError, ValueError):
                declared_snapshot_hash = None
            else:
                if hashlib.sha256(canonical).hexdigest() != declared_snapshot_hash:
                    declared_snapshot_hash = None
        if declared_snapshot_hash != expected_sha256:
            reasons.append(f"{label}_sha256_mismatch")
    return path


def selection_probability_input_sha256(
    probabilities: Sequence[Sequence[float]],
) -> str:
    """Canonical probability hash, including reduced-event unit-test surfaces."""
    rows = _validated_probability_rows(probabilities)
    if len(rows) == 15:
        return canonical_probability_input_sha256(rows)
    return hashlib.sha256(
        json.dumps(
            [list(row) for row in rows],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def continuous_exposure_lower_bounds(
    probabilities: Sequence[float],
    *,
    package_size: int,
    scale: float,
    exponent: float,
) -> tuple[int, int, int]:
    """Map one event's probabilities to monotone, sum-feasible integer floors.

    The continuous target is ``K * scale * p**exponent`` and the enforced floor
    is its mathematical floor. Requiring ``scale <= 1`` and ``exponent >= 1``
    guarantees that the three floors sum to at most ``K`` for a normalized row.
    """
    if type(package_size) is not int or package_size <= 0:
        raise ValueError("package_size must be a positive int")
    if not 0.0 < scale <= 1.0 or exponent < 1.0:
        raise ValueError(
            "exposure floor must be sum-feasible: scale in (0, 1], exponent >= 1"
        )
    values = tuple(float(value) for value in probabilities)
    if len(values) != 3:
        raise ValueError("probabilities must contain exactly three outcomes")
    if not all(math.isfinite(value) and value >= 0.0 for value in values):
        raise ValueError("probabilities must be finite and non-negative")
    if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("probabilities must sum to one")
    floors = tuple(
        int(math.floor(package_size * scale * value**exponent)) for value in values
    )
    if sum(floors) > package_size:  # Defensive guard around future formula edits.
        raise ValueError("continuous exposure floors are not sum-feasible")
    return floors  # type: ignore[return-value]


def continuous_exposure_targets(
    probabilities: Sequence[float],
    *,
    package_size: int,
    scale: float,
    exponent: float,
) -> tuple[float, float, float]:
    _ = continuous_exposure_lower_bounds(
        probabilities,
        package_size=package_size,
        scale=scale,
        exponent=exponent,
    )
    return tuple(
        package_size * scale * float(value) ** exponent for value in probabilities
    )  # type: ignore[return-value]


def package_diversity_metrics(
    coupons: Sequence[str],
    *,
    close_distance: int = 2,
) -> PackageDiversityMetrics:
    canonical = tuple(coupons)
    if type(close_distance) is not int or close_distance < 0:
        raise ValueError("close_distance must be a non-negative int")
    if canonical:
        event_count = len(canonical[0])
        if event_count <= 0 or any(
            len(coupon) != event_count or set(coupon) - set(OUTCOMES)
            for coupon in canonical
        ):
            raise ValueError("coupons must use one consistent non-empty 1/X/2 shape")
    else:
        event_count = 0
    distances = [
        sum(left != right for left, right in zip(first, second, strict=True))
        for index, first in enumerate(canonical)
        for second in canonical[index + 1 :]
    ]
    distribution = tuple(sorted(Counter(distances).items()))
    pair_count = len(distances)
    close_pairs = sum(
        value for distance, value in distribution if distance <= close_distance
    )
    if distances:
        ordered = sorted(distances)
        middle = pair_count // 2
        median = (
            float(ordered[middle])
            if pair_count % 2
            else (ordered[middle - 1] + ordered[middle]) / 2.0
        )
        mean_distance = sum(distances) / pair_count
        minimum = min(distances)
        maximum = max(distances)
    else:
        median = mean_distance = 0.0
        minimum = maximum = 0
    if canonical:
        kernel_scale = max(1.0, event_count / 3.0)
        similarity_sum = float(len(canonical))
        similarity_sum += 2.0 * sum(
            math.exp(-distance / kernel_scale) for distance in distances
        )
        effective_count = len(canonical) ** 2 / similarity_sum
    else:
        effective_count = 0.0
    return PackageDiversityMetrics(
        pairwise_distance_distribution=distribution,
        minimum_pairwise_hamming=minimum,
        median_pairwise_hamming=median,
        mean_pairwise_hamming=mean_distance,
        maximum_pairwise_hamming=maximum,
        close_pair_count=close_pairs,
        close_pair_share=close_pairs / pair_count if pair_count else 0.0,
        effective_pattern_count=effective_count,
    )


def package_quality_metrics(
    coupons: Sequence[str],
    probabilities: Sequence[Sequence[float]],
    *,
    seed_material: str,
    monte_carlo_samples: int = 8_192,
    close_distance: int = 2,
    monte_carlo_stream: str = EVALUATION_MC_STREAM,
) -> PackageCategoryProbabilityMetrics | _CombinedPackageQualityMetrics:
    """Compute deterministic diversity plus P(9+/13+/14+/15).

    P(13+), P(14+), and P(15) are exact weighted unions of Hamming balls of
    radius 2, 1, and 0. P(9+) uses deterministic Monte Carlo; its seed is a
    SHA-256 derivation of the frozen provenance seed material.
    """
    canonical = tuple(coupons)
    rows = _validated_probability_rows(probabilities)
    if len(rows) != 15:
        raise ValueError("package category probabilities require exactly 15 events")
    if type(monte_carlo_samples) is not int or monte_carlo_samples <= 0:
        raise ValueError("monte_carlo_samples must be a positive int")
    diversity = package_diversity_metrics(
        canonical,
        close_distance=close_distance,
    )
    if any(len(coupon) != 15 for coupon in canonical):
        raise ValueError("category-probability coupons must contain 15 outcomes")
    probability_13, probability_14, probability_15 = exact_category_probabilities(
        canonical,
        rows,
    )
    samples, seed = deterministic_outcome_samples(
        rows,
        seed_material=seed_material,
        sample_count=monte_carlo_samples,
        stream=monte_carlo_stream,
    )
    probability_9 = _monte_carlo_probability_at_least_9(
        canonical,
        samples,
    )
    return _CombinedPackageQualityMetrics(
        **asdict(diversity),
        probability_at_least_9=probability_9,
        probability_at_least_13=probability_13,
        probability_at_least_14=probability_14,
        probability_at_least_15=probability_15,
        probability_9_method="deterministic_monte_carlo",
        probability_13_15_method="exact_hamming_union",
        monte_carlo_seed=seed,
        monte_carlo_stream=monte_carlo_stream,
        monte_carlo_samples=monte_carlo_samples,
        monte_carlo_worst_case_95_error=1.96 * math.sqrt(0.25 / monte_carlo_samples),
    )


@dataclass(frozen=True)
class _CombinedPackageQualityMetrics(
    PackageDiversityMetrics,
    PackageCategoryProbabilityMetrics,
):
    pass


def exact_category_probabilities(
    coupons: Sequence[str],
    probabilities: Sequence[Sequence[float]],
) -> tuple[float, float, float]:
    rows = _validated_probability_rows(probabilities)
    if len(rows) != 15:
        raise ValueError("exact category probabilities require exactly 15 events")
    balls = (set[tuple[int, ...]](), set[tuple[int, ...]](), set[tuple[int, ...]]())
    for coupon in coupons:
        digits = _coupon_digits(coupon)
        for state, distance in _states_within_two(digits):
            balls[0].add(state)
            if distance <= 1:
                balls[1].add(state)
            if distance == 0:
                balls[2].add(state)
    cache: dict[tuple[int, ...], float] = {}

    def probability(state: tuple[int, ...]) -> float:
        if state not in cache:
            cache[state] = math.prod(
                rows[event][outcome] for event, outcome in enumerate(state)
            )
        return cache[state]

    return tuple(math.fsum(probability(state) for state in states) for states in balls)  # type: ignore[return-value]


class ExactCategoryCoverage:
    """Incremental exact weighted unions for 13+, 14+, and 15 hits."""

    def __init__(
        self,
        coupons: Sequence[str],
        probabilities: Sequence[Sequence[float]],
    ) -> None:
        self._probabilities = _validated_probability_rows(probabilities)
        if len(self._probabilities) != 15:
            raise ValueError("exact category coverage requires exactly 15 events")
        self._counts = [dict[tuple[int, ...], int]() for _ in range(3)]
        self._masses = [0.0, 0.0, 0.0]
        self._state_probability_cache: dict[tuple[int, ...], float] = {}
        self._ball_cache: dict[str, tuple[frozenset[tuple[int, ...]], ...]] = {}
        for coupon in coupons:
            self._add(coupon)

    @property
    def probabilities(self) -> tuple[float, float, float]:
        return tuple(self._masses)  # type: ignore[return-value]

    def probabilities_after_swap(
        self,
        outgoing: str,
        incoming: str,
    ) -> tuple[float, float, float]:
        result = []
        outgoing_balls = self._balls(outgoing)
        incoming_balls = self._balls(incoming)
        for radius in range(3):
            outgoing_only = outgoing_balls[radius] - incoming_balls[radius]
            incoming_only = incoming_balls[radius] - outgoing_balls[radius]
            removed = math.fsum(
                self._state_probability(state)
                for state in outgoing_only
                if self._counts[radius].get(state) == 1
            )
            added = math.fsum(
                self._state_probability(state)
                for state in incoming_only
                if self._counts[radius].get(state, 0) == 0
            )
            result.append(self._masses[radius] - removed + added)
        return tuple(result)  # type: ignore[return-value]

    def probabilities_after_removal(
        self,
        outgoing: str,
    ) -> tuple[float, float, float]:
        result = []
        for radius, states in enumerate(self._balls(outgoing)):
            removed = math.fsum(
                self._state_probability(state)
                for state in states
                if self._counts[radius].get(state) == 1
            )
            result.append(self._masses[radius] - removed)
        return tuple(result)  # type: ignore[return-value]

    def apply_swap(self, outgoing: str, incoming: str) -> None:
        self._remove(outgoing)
        self._add(incoming)

    def _balls(self, coupon: str) -> tuple[frozenset[tuple[int, ...]], ...]:
        cached = self._ball_cache.get(coupon)
        if cached is not None:
            return cached
        by_radius = [
            set[tuple[int, ...]](),
            set[tuple[int, ...]](),
            set[tuple[int, ...]](),
        ]
        for state, distance in _states_within_two(_coupon_digits(coupon)):
            by_radius[0].add(state)
            if distance <= 1:
                by_radius[1].add(state)
            if distance == 0:
                by_radius[2].add(state)
        result = tuple(frozenset(states) for states in by_radius)
        self._ball_cache[coupon] = result
        return result

    def _state_probability(self, state: tuple[int, ...]) -> float:
        cached = self._state_probability_cache.get(state)
        if cached is None:
            cached = math.prod(
                self._probabilities[event][outcome]
                for event, outcome in enumerate(state)
            )
            self._state_probability_cache[state] = cached
        return cached

    def _add(self, coupon: str) -> None:
        for radius, states in enumerate(self._balls(coupon)):
            counts = self._counts[radius]
            for state in states:
                count = counts.get(state, 0)
                if count == 0:
                    self._masses[radius] += self._state_probability(state)
                counts[state] = count + 1

    def _remove(self, coupon: str) -> None:
        for radius, states in enumerate(self._balls(coupon)):
            counts = self._counts[radius]
            for state in states:
                count = counts[state]
                if count == 1:
                    self._masses[radius] -= self._state_probability(state)
                    del counts[state]
                else:
                    counts[state] = count - 1


def deterministic_outcome_samples(
    probabilities: Sequence[Sequence[float]],
    *,
    seed_material: str,
    sample_count: int,
    stream: str,
) -> tuple[np.ndarray, int]:
    """Draw an immutable, domain-separated modeled-outcome sample stream."""
    rows = _validated_probability_rows(probabilities)
    if type(sample_count) is not int or sample_count <= 0:
        raise ValueError("sample_count must be a positive int")
    if stream not in {OPTIMIZATION_MC_STREAM, EVALUATION_MC_STREAM}:
        raise ValueError("unknown Monte Carlo stream")
    seed = deterministic_outcome_seed(seed_material=seed_material, stream=stream)
    rng = np.random.default_rng(seed)
    random_values = rng.random((sample_count, len(rows)))
    samples = np.empty((sample_count, len(rows)), dtype=np.int8)
    for event, row in enumerate(rows):
        samples[:, event] = (random_values[:, event] >= row[0]).astype(np.int8)
        samples[:, event] += (random_values[:, event] >= row[0] + row[1]).astype(
            np.int8
        )
    return samples, seed


def deterministic_outcome_seed(*, seed_material: str, stream: str) -> int:
    """Derive one domain-separated NumPy seed without consuming a stream."""
    if stream not in {OPTIMIZATION_MC_STREAM, EVALUATION_MC_STREAM}:
        raise ValueError("unknown Monte Carlo stream")
    return int.from_bytes(
        hashlib.sha256(
            json.dumps(
                {"seed_material": seed_material, "stream": stream},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).digest()[:8],
        "big",
        signed=False,
    )


def diagnostics_with_hash(
    diagnostics: SafetyAwareSelectionDiagnostics,
) -> SafetyAwareSelectionDiagnostics:
    payload = asdict(replace(diagnostics, diagnostics_sha256=""))
    digest = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return replace(diagnostics, diagnostics_sha256=digest)


def diagnostics_payload_sha256(payload: dict[str, object]) -> str:
    unsigned = dict(payload)
    unsigned["diagnostics_sha256"] = ""
    return hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _validated_probability_rows(
    probabilities: Sequence[Sequence[float]],
) -> tuple[tuple[float, float, float], ...]:
    rows = []
    for row in probabilities:
        values = tuple(float(value) for value in row)
        if len(values) != 3:
            raise ValueError("probability rows must contain exactly three values")
        if not all(math.isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("probabilities must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("probability rows must sum to one")
        rows.append(values)
    return tuple(rows)


def _coupon_digits(coupon: str) -> tuple[int, ...]:
    try:
        return tuple(OUTCOMES.index(outcome) for outcome in coupon)
    except ValueError as error:
        raise ValueError("coupon outcomes must be 1, X, or 2") from error


def _states_within_two(
    digits: tuple[int, ...],
):
    yield digits, 0
    for event in range(len(digits)):
        for outcome in range(3):
            if outcome != digits[event]:
                state = list(digits)
                state[event] = outcome
                yield tuple(state), 1
    for first, second in itertools.combinations(range(len(digits)), 2):
        for first_outcome in range(3):
            if first_outcome == digits[first]:
                continue
            for second_outcome in range(3):
                if second_outcome == digits[second]:
                    continue
                state = list(digits)
                state[first] = first_outcome
                state[second] = second_outcome
                yield tuple(state), 2


def _monte_carlo_probability_at_least_9(
    coupons: tuple[str, ...],
    samples: np.ndarray,
) -> float:
    if not coupons:
        return 0.0
    minimum_distance = np.full(samples.shape[0], 16, dtype=np.int8)
    for coupon in coupons:
        digits = np.fromiter(_coupon_digits(coupon), dtype=np.int8, count=15)
        distance = np.count_nonzero(samples != digits, axis=1)
        minimum_distance = np.minimum(minimum_distance, distance)
    return float(np.mean(minimum_distance <= 6))
