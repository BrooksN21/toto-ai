"""Final-input-bound BK versus sports-shadow package comparison.

The command implemented here is a research sidecar.  It consumes the exact
immutable scheduler input and the already frozen sports artifact, but never
mutates scheduler state or creates an operator-compatible sports package.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    exact_category_probabilities,
    package_quality_metrics,
    selection_probability_input_sha256,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.optimizer.parallel_challenger import (
    ExactCategoryMetrics,
    ParallelCandidate,
    select_parallel_candidate,
)
from toto_ai.optimizer.prospective_quality import QualityV3Config
from toto_ai.optimizer.robust_package import select_robust_package
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyInput,
    StrategyResult,
    run_ev_crowd_current,
)
from toto_ai.optimizer.strategy_execution import frozen_input_from_snapshot
from toto_ai.optimizer.uncertainty_package import (
    build_uncertainty_models,
    outcome_exposure,
    select_uncertainty_package,
)
from toto_ai.package.audit import evaluate_package_safety
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import load_scheduler_plan
from toto_ai.sports_stats.probabilities import load_shadow_probability_artifact

STATUS = "PAPER_ONLY_NOT_ACTIVATED"
ARTIFACT_CLASS = "FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON"


@dataclass(frozen=True)
class FinalHybridComparisonPaths:
    report: Path
    baseline_package: Path
    sports_package: Path
    robust_package: Path
    quality_v3_package: Path
    uncertainty_package: Path
    sports_probability_snapshot: Path


def execute_final_hybrid_comparison(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    sports_artifact_path: str | Path,
    output_dir: str | Path,
    deadline: float | None = None,
) -> tuple[dict[str, Any], FinalHybridComparisonPaths]:
    """Generate equal-config BK and sports packages from one final input."""

    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    input_path = _regular_file(final_input_path, "final input")
    sports_path = _regular_file(sports_artifact_path, "sports artifact")
    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("output directory must be a regular directory")

    plan = load_scheduler_plan(plan_path)
    snapshot = load_final_input(input_path, expected_plan=plan)
    frozen = frozen_input_from_snapshot(snapshot, plan)
    sports = load_shadow_probability_artifact(sports_path)
    _validate_sports_artifact_identity(
        plan=plan,
        snapshot=snapshot,
        frozen=frozen,
        sports=sports,
    )

    runtime_budget = effective_selection_budget(
        requested_bank=plan.requested_bank,
        pool_sum=frozen.pool_sum,
        stake=plan.stake,
    )
    config = replace(plan.quality_v2_ev_config, effective_budget=runtime_budget)
    baseline_provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=input_path,
        probability_input_sha256=snapshot.probability_input_sha256,
        schedule_evidence_ledger_path=plan.schedule_evidence_ledger,
        scheduler_plan_path=plan_path,
        selection_config=config,
    )
    baseline = run_ev_crowd_current(
        frozen,
        config=config,
        provenance=baseline_provenance,
    )

    sports_probabilities = _rebase_sports_probabilities(frozen, sports.events)
    sports_frozen = replace(
        frozen,
        events=tuple(
            replace(event, bk_probabilities=sports_probabilities[event.event_order])
            for event in frozen.events
        ),
    )
    sports_probability_snapshot = output / "sports-final-probability-snapshot.json"
    probability_hash = selection_probability_input_sha256(sports_probabilities)
    snapshot_document = {
        "schema_version": 1,
        "status": STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "plan_id": plan.plan_id,
        "drawing_id": frozen.drawing_id,
        "drawing_number": frozen.drawing_number,
        "as_of": _timestamp(snapshot.captured_at),
        "final_input_snapshot_sha256": snapshot.snapshot_sha256,
        "source_sports_artifact_sha256": sports.artifact_sha256,
        "probability_input_sha256": probability_hash,
        "probabilities": [list(row) for row in sports_probabilities],
        "automatic_wagering": False,
        "operator_compatible": False,
    }
    _write_replace(sports_probability_snapshot, _canonical(snapshot_document) + b"\n")
    sports_provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=sports_probability_snapshot,
        probability_input_sha256=probability_hash,
        schedule_evidence_ledger_path=plan.schedule_evidence_ledger,
        scheduler_plan_path=plan_path,
        selection_config=config,
    )
    sports_result = (
        baseline
        if sports.sports_coverage_count == 0
        else run_ev_crowd_current(
            sports_frozen,
            config=config,
            provenance=sports_provenance,
        )
    )
    quality_v3_config = QualityV3Config()
    uncertainty_models = build_uncertainty_models(
        frozen.bk_probability_matrix,
        flatten_weights=quality_v3_config.flatten_weights,
    )
    quality_v3 = select_uncertainty_package(
        bk_probabilities=frozen.bk_probability_matrix,
        anchor_coupons=baseline.coupons,
        category=quality_v3_config.category,
        max_coupons=runtime_budget // plan.stake,
        flatten_weights=quality_v3_config.flatten_weights,
        top_count=quality_v3_config.top_count,
        candidate_sample_count=quality_v3_config.candidate_sample_count,
        mutation_limit=quality_v3_config.mutation_limit,
        selection_sample_count=quality_v3_config.scenario_sample_count,
        seed_material=f"quality-v3-{snapshot.snapshot_sha256}",
        deadline=deadline,
    )
    candidate_union = tuple(
        dict.fromkeys(
            (
                *baseline.coupons,
                *sports_result.coupons,
                *quality_v3.selected_coupons,
            )
        )
    )
    combined_models = {
        "bk": frozen.bk_probability_matrix,
        "sports": sports_probabilities,
        **{
            name: probabilities
            for name, probabilities in uncertainty_models.items()
            if name != "bk"
        },
    }
    robust = select_robust_package(
        candidates=candidate_union,
        probability_models=combined_models,
        category=13,
        max_coupons=runtime_budget // plan.stake,
        sample_count=config.package_probability_samples,
        seed_material=(
            f"final-hybrid-robust-{snapshot.snapshot_sha256}-{probability_hash}"
        ),
        deadline=deadline,
    )
    baseline_quality_bk = package_quality_metrics(
        baseline.coupons,
        frozen.bk_probability_matrix,
        seed_material=f"final-hybrid-bk-{snapshot.snapshot_sha256}",
        monte_carlo_samples=config.package_probability_samples,
    )
    baseline_quality_sports = package_quality_metrics(
        baseline.coupons,
        sports_probabilities,
        seed_material=f"final-hybrid-bk-sports-{probability_hash}",
        monte_carlo_samples=config.package_probability_samples,
    )
    sports_quality_bk = package_quality_metrics(
        sports_result.coupons,
        frozen.bk_probability_matrix,
        seed_material=f"final-hybrid-sports-bk-{snapshot.snapshot_sha256}",
        monte_carlo_samples=config.package_probability_samples,
    )
    sports_quality_sports = package_quality_metrics(
        sports_result.coupons,
        sports_probabilities,
        seed_material=f"final-hybrid-sports-{probability_hash}",
        monte_carlo_samples=config.package_probability_samples,
    )
    candidates = (
        _parallel_candidate(
            strategy_id="quality-v2",
            coupons=baseline.coupons,
            models=combined_models,
            probabilities=frozen.bk_probability_matrix,
            safety_config=config.package_safety_config,
            stake=plan.stake,
        ),
        _parallel_candidate(
            strategy_id="sports-shadow",
            coupons=sports_result.coupons,
            models=combined_models,
            probabilities=frozen.bk_probability_matrix,
            safety_config=config.package_safety_config,
            stake=plan.stake,
        ),
        _parallel_candidate(
            strategy_id="quality-v3",
            coupons=quality_v3.selected_coupons,
            models=combined_models,
            probabilities=frozen.bk_probability_matrix,
            safety_config=config.package_safety_config,
            stake=plan.stake,
            timed_out=quality_v3.timed_out,
        ),
        _parallel_candidate(
            strategy_id="robust",
            coupons=robust.selected_coupons,
            models=combined_models,
            probabilities=frozen.bk_probability_matrix,
            safety_config=config.package_safety_config,
            stake=plan.stake,
            timed_out=robust.timed_out,
        ),
    )
    experimental_selection = select_parallel_candidate(candidates)
    overlap = len(set(baseline.coupons) & set(sports_result.coupons))
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": frozen.drawing_id,
        "drawing_number": frozen.drawing_number,
        "plan_id": plan.plan_id,
        "as_of": _timestamp(snapshot.captured_at),
        "bank": plan.requested_bank,
        "effective_budget": runtime_budget,
        "stake": plan.stake,
        "final_input_snapshot_sha256": snapshot.snapshot_sha256,
        "sports_artifact_sha256": sports.artifact_sha256,
        "sports_coverage_count": sports.sports_coverage_count,
        "sports_fallback_count": sports.fallback_count,
        "baseline": _result_payload(baseline, baseline_quality_bk),
        "sports": _result_payload(sports_result, sports_quality_sports),
        "robust": {
            "coupon_count": len(robust.selected_coupons),
            "cost": len(robust.selected_coupons) * plan.stake,
            "unused_bank": runtime_budget
            - len(robust.selected_coupons) * plan.stake,
            "candidate_count": robust.candidate_count,
            "category": robust.category,
            "sample_count_per_model": robust.sample_count_per_model,
            "worst_sampled_category_coverage": (
                robust.worst_sampled_category_coverage
            ),
            "mean_sampled_category_coverage": (
                robust.mean_sampled_category_coverage
            ),
            "timed_out": robust.timed_out,
            "models": [asdict(item) for item in robust.model_metrics],
        },
        "quality_v3": {
            "role": "DIRECT_BK_BOUNDED_UNCERTAINTY_CHALLENGER",
            "config": quality_v3_config.payload(
                coupon_capacity=runtime_budget // plan.stake
            ),
            "coupon_count": len(quality_v3.selected_coupons),
            "cost": len(quality_v3.selected_coupons) * plan.stake,
            "unused_bank": runtime_budget
            - len(quality_v3.selected_coupons) * plan.stake,
            "candidate_count": quality_v3.candidate_count,
            "candidate_source": "direct_top_sampled_mutated_per_model",
            "category": quality_v3.category,
            "flatten_weights": list(quality_v3_config.flatten_weights),
            "sample_count_per_model": quality_v3.sample_count_per_model,
            "worst_sampled_category_coverage": (
                quality_v3.worst_sampled_category_coverage
            ),
            "mean_sampled_category_coverage": (
                quality_v3.mean_sampled_category_coverage
            ),
            "timed_out": quality_v3.timed_out,
            "models": [asdict(item) for item in quality_v3.model_metrics],
            "baseline_models": _exact_model_metrics(
                baseline.coupons,
                uncertainty_models,
            ),
            "exposure": outcome_exposure(quality_v3.selected_coupons),
        },
        "uncertainty_v1": {
            "deprecated_alias_of": "quality_v3",
            "package_sha256": _package_sha256(quality_v3.selected_coupons),
        },
        "experimental_selection": experimental_selection.public_summary(),
        "cross_evaluation": {
            "baseline_under_sports": asdict(baseline_quality_sports),
            "sports_under_bk": asdict(sports_quality_bk),
        },
        "comparison": {
            "overlap_count": overlap,
            "overlap_share": overlap / len(baseline.coupons),
            "baseline_only_count": len(
                set(baseline.coupons) - set(sports_result.coupons)
            ),
            "sports_only_count": len(
                set(sports_result.coupons) - set(baseline.coupons)
            ),
            "robust_baseline_overlap_count": len(
                set(robust.selected_coupons) & set(baseline.coupons)
            ),
            "robust_sports_overlap_count": len(
                set(robust.selected_coupons) & set(sports_result.coupons)
            ),
        },
        "automatic_wagering": False,
        "operator_compatible": False,
        "scheduler_state_mutated": False,
        "profitability_proven": False,
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()

    baseline_package = output / "baseline-final-research-coupons.txt"
    sports_package = output / "sports-final-research-coupons.txt"
    robust_package = output / "robust-final-research-coupons.txt"
    quality_v3_package = output / "quality-v3-final-research-coupons.txt"
    uncertainty_package = output / "uncertainty-v1-final-research-coupons.txt"
    report_path = output / "comparison.json"
    _write_replace(
        baseline_package,
        _research_package_bytes("FINAL_BK_CONTROL", plan.stake, baseline.coupons),
    )
    _write_replace(
        sports_package,
        _research_package_bytes(
            "FINAL_GOAL_SPORTS_SHADOW", plan.stake, sports_result.coupons
        ),
    )
    _write_replace(
        robust_package,
        _research_package_bytes(
            "FINAL_PARALLEL_MODEL_MAXIMIN_RECOMBINATION",
            plan.stake,
            robust.selected_coupons,
        ),
    )
    _write_replace(
        quality_v3_package,
        _research_package_bytes(
            "QUALITY_V3_BOUNDED_UNCERTAINTY_CHALLENGER",
            plan.stake,
            quality_v3.selected_coupons,
        ),
    )
    _write_replace(
        uncertainty_package,
        _research_package_bytes(
            "DIRECT_BK_BOUNDED_UNCERTAINTY_CHALLENGER",
            plan.stake,
            quality_v3.selected_coupons,
        ),
    )
    _write_replace(report_path, _pretty(report))
    return report, FinalHybridComparisonPaths(
        report=report_path,
        baseline_package=baseline_package,
        sports_package=sports_package,
        robust_package=robust_package,
        quality_v3_package=quality_v3_package,
        uncertainty_package=uncertainty_package,
        sports_probability_snapshot=sports_probability_snapshot,
    )


def _exact_model_metrics(
    coupons: tuple[str, ...],
    models: Mapping[str, tuple[tuple[float, float, float], ...]],
) -> list[dict[str, float | str]]:
    rows = []
    for name, probabilities in models.items():
        p13, p14, p15 = exact_category_probabilities(coupons, probabilities)
        rows.append(
            {
                "model": name,
                "exact_p13": p13,
                "exact_p14": p14,
                "exact_p15": p15,
            }
        )
    return rows


def _validate_sports_artifact_identity(
    *,
    plan: Any,
    snapshot: Any,
    frozen: FrozenStrategyInput,
    sports: Any,
) -> None:
    """Bind sports evidence to the operational, not raw TotoBrief, cutoff."""

    payload = getattr(snapshot, "payload", None)
    if isinstance(payload, Mapping):
        parsed = parse_target_drawing(payload, snapshot.captured_at)
        operational_fingerprint = target_fingerprint(
            drawing_id=parsed.drawing_id,
            drawing_number=parsed.drawing_number,
            deadline=plan.operational_cutoff,
            events=parsed.events,
        )
        if (
            sports.drawing_id != frozen.drawing_id
            or sports.drawing_number != frozen.drawing_number
            or sports.deadline != plan.operational_cutoff
            or sports.drawing_fingerprint != operational_fingerprint
            or sports.authoritative_target_fingerprint != operational_fingerprint
        ):
            raise ValueError("sports artifact drawing identity mismatch")
        ordered = tuple(sorted(sports.events, key=lambda event: event.event_order))
        if len(ordered) != 15:
            raise ValueError("sports artifact must contain exactly 15 events")
        for target, _frozen_event, sports_event in zip(
            parsed.events,
            frozen.events,
            ordered,
            strict=True,
        ):
            if (
                sports_event.event_order != target.event_order
                or str(sports_event.event_id) != str(target.event_id)
            ):
                raise ValueError("sports artifact event identity mismatch")
    elif (
        sports.drawing_id != frozen.drawing_id
        or sports.drawing_number != frozen.drawing_number
        or sports.drawing_fingerprint != frozen.drawing_fingerprint
        or sports.authoritative_target_fingerprint != frozen.drawing_fingerprint
    ):
        raise ValueError("sports artifact drawing identity mismatch")
    if sports.as_of > snapshot.captured_at:
        raise ValueError("sports artifact was captured after final input")
    if len(sports.events) != 15:
        raise ValueError("sports artifact must contain exactly 15 events")


def _parallel_candidate(
    *,
    strategy_id: str,
    coupons: tuple[str, ...],
    models: Mapping[str, tuple[tuple[float, float, float], ...]],
    probabilities: tuple[tuple[float, float, float], ...],
    safety_config: Any,
    stake: int = 30,
    timed_out: bool = False,
) -> ParallelCandidate:
    reasons = []
    if timed_out:
        reasons.append("generation_timed_out")
    if not coupons:
        reasons.append("empty_package")
    else:
        safety = evaluate_package_safety(
            coupons,
            probabilities,
            config=safety_config,
        )
        if safety.decision != "PLAY":
            reasons.extend(
                f"package_safety:{code}" for code in safety.reason_codes
            )
    model_metrics = tuple(
        _exact_category_metrics(coupons, name=name, probabilities=rows)
        for name, rows in models.items()
    )
    return ParallelCandidate(
        strategy_id=strategy_id,
        package_sha256=_package_sha256(coupons),
        coupon_count=len(coupons),
        cost=len(coupons) * stake,
        maximum_outcome_share=_maximum_outcome_share(coupons),
        eligible=not reasons,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        models=model_metrics,
    )


def _exact_category_metrics(
    coupons: tuple[str, ...],
    *,
    name: str,
    probabilities: tuple[tuple[float, float, float], ...],
) -> ExactCategoryMetrics:
    if coupons:
        p13, p14, p15 = exact_category_probabilities(coupons, probabilities)
    else:
        p13 = p14 = p15 = 0.0
    return ExactCategoryMetrics(
        model=name,
        probability_at_least_13=p13,
        probability_at_least_14=p14,
        probability_at_least_15=p15,
    )


def _maximum_outcome_share(coupons: tuple[str, ...]) -> float:
    if not coupons:
        return 1.0
    return max(
        max(row["shares"].values())
        for row in outcome_exposure(coupons)
    )


def _package_sha256(coupons: tuple[str, ...]) -> str:
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def _rebase_sports_probabilities(
    frozen: FrozenStrategyInput,
    sports_events: Any,
) -> tuple[tuple[float, float, float], ...]:
    ordered = tuple(sorted(sports_events, key=lambda event: event.event_order))
    if tuple(event.event_order for event in ordered) != tuple(range(15)):
        raise ValueError("sports artifact event order is invalid")
    rows = []
    for baseline_event, sports_event in zip(frozen.events, ordered, strict=True):
        weight = float(sports_event.blend_weight)
        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
            raise ValueError("sports blend weight is invalid")
        if sports_event.fallback_reason is not None:
            weight = 0.0
        raw = tuple(
            (1.0 - weight) * bk + weight * sports
            for bk, sports in zip(
                baseline_event.bk_probabilities,
                sports_event.sports_probabilities,
                strict=True,
            )
        )
        total = math.fsum(raw)
        if not math.isfinite(total) or total <= 0.0:
            raise ValueError("sports probability row is invalid")
        rows.append(tuple(value / total for value in raw))
    return tuple(rows)


def _result_payload(result: StrategyResult, quality: Any) -> dict[str, Any]:
    return {
        "coupon_count": result.coupon_count,
        "cost": result.cost,
        "unused_bank": result.unused_bank,
        "package_sha256": result.package_sha256,
        "runtime_seconds": result.runtime_seconds,
        "p13": result.probability_at_least_13,
        "p14": result.probability_at_least_14,
        "p15": result.probability_at_least_15,
        "quality": asdict(quality),
    }


def _research_package_bytes(role: str, stake: int, coupons: tuple[str, ...]) -> bytes:
    lines = [
        "RESEARCH ONLY / NOT ACTIVATED / DO NOT WAGER",
        "NOT A BALTBet UPLOAD FILE",
        f"role={role} stake={stake} coupons={len(coupons)}",
        "",
        *coupons,
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _regular_file(value: str | Path, name: str) -> Path:
    path = Path(value).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be a regular non-symlink file")
    return path


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("output path cannot traverse a symlink")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
