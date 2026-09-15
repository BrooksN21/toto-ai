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
from functools import wraps
from pathlib import Path
from types import MappingProxyType
from typing import Any

from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    exact_category_probabilities,
    package_quality_metrics,
    selection_probability_input_sha256,
)
from toto_ai.ev.runtime import RuntimeBudget, checkpoint, phase, runtime_scope
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.optimizer.coupon_probabilities import best_coupon_by_p13
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
    control_relative_exposure_constraints,
    outcome_exposure,
    select_uncertainty_package,
)
from toto_ai.package.audit import evaluate_package_safety
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import load_scheduler_plan
from toto_ai.sports_stats.parallel_g1 import (
    ParallelG1Config,
    family_refinement_coupons,
    run_parallel_g1,
)
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


def _runtime_comparison(function):
    @wraps(function)
    def run(**kwargs):
        output = Path(kwargs["output_dir"]).absolute()
        if output.is_symlink():
            raise ValueError("output directory must be a regular directory")
        output.mkdir(parents=True, exist_ok=True)

        def progress(payload):
            payload = {
                **payload,
                "observed_at": _timestamp(datetime.now(timezone.utc)),
                "operator_compatible": False,
                "automatic_wagering": False,
            }
            _write_replace(output / "runtime-progress.json", _pretty(payload))
            with (output / "runtime-progress.jsonl").open("ab") as stream:
                stream.write(_canonical(payload) + b"\n")
            print(json.dumps(payload, sort_keys=True), flush=True)

        budget = RuntimeBudget(deadline=kwargs.get("deadline"), progress=progress)
        with runtime_scope(budget):
            budget.check("started", force=True)
            try:
                result = function(**kwargs)
                budget.check("completed", force=True)
                return result
            except Exception as exc:
                _write_replace(
                    output / "runtime-failure.json",
                    _pretty(
                        {
                            "phase": budget.phase,
                            "reason": str(exc),
                            "error_type": type(exc).__name__,
                            "operator_compatible": False,
                            "automatic_wagering": False,
                            "completed_research_retained": True,
                        }
                    ),
                )
                raise

    return run


@_runtime_comparison
def execute_final_hybrid_comparison(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    sports_artifact_path: str | Path,
    output_dir: str | Path,
    deadline: float | None = None,
    g1_config: ParallelG1Config | None = None,
    expected_primary_coupons: tuple[str, ...] | None = None,
    primary_package_sha256: str | None = None,
    primary_control_record: Mapping[str, Any] | None = None,
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
    phase("control_ev")
    baseline = (
        run_ev_crowd_current(frozen, config=config, provenance=baseline_provenance)
        if primary_control_record is None
        else _reuse_verified_control(
            plan=plan,
            snapshot=snapshot,
            frozen=frozen,
            config=config,
            provenance=baseline_provenance,
            operator=primary_control_record,
            expected_coupons=expected_primary_coupons,
            upload_sha256=primary_package_sha256,
        )
    )

    # Persist the primary control and calculated ranking before any side work.
    # These research files do not replace the scheduler-owned operator record.
    if (
        expected_primary_coupons is not None
        and baseline.coupons != expected_primary_coupons
    ):
        raise ValueError("recomputed primary control differs from operator package")
    baseline_package = output / "baseline-final-research-coupons.txt"
    _write_replace(
        baseline_package,
        _research_package_bytes("FINAL_BK_CONTROL", plan.stake, baseline.coupons),
    )
    primary_ranking = _best_single_coupon_payload(
        baseline.coupons,
        frozen.bk_probability_matrix,
        reference_model="bk",
    )
    primary_ranking_document = {
        "schema_version": 1,
        "artifact_class": "PRIMARY_CONTROL_RANKING_ANALYSIS_ONLY",
        "plan_id": plan.plan_id,
        "plan_file_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "final_input_snapshot_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "package_sha256": _package_sha256(baseline.coupons),
        "operator_package_sha256": primary_package_sha256,
        "operator_control_verified": expected_primary_coupons is not None,
        "highest_p13_single_coupon": primary_ranking,
        "automatic_wagering": False,
        "operator_compatible": False,
    }
    primary_ranking_document["record_sha256"] = hashlib.sha256(
        _canonical(primary_ranking_document),
    ).hexdigest()
    _write_replace(
        output / "primary-bk-ranking.json", _pretty(primary_ranking_document)
    )

    phase("sports_preparation")
    sports_probabilities = _rebase_sports_probabilities(frozen, sports.events)
    checkpoint("sports_rebased")
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
    phase("sports_ev")
    sports_result = (
        baseline
        if sports.sports_coverage_count == 0
        else run_ev_crowd_current(
            sports_frozen,
            config=config,
            provenance=sports_provenance,
        )
    )
    _write_replace(
        output / "sports-final-research-coupons.txt",
        _research_package_bytes(
            "FINAL_GOAL_SPORTS_SHADOW", plan.stake, sports_result.coupons
        ),
    )
    phase("quality_v3")
    quality_v3_config = QualityV3Config()
    uncertainty_models = build_uncertainty_models(
        frozen.bk_probability_matrix,
        flatten_weights=quality_v3_config.flatten_weights,
    )
    exposure_constraints = control_relative_exposure_constraints(
        frozen.bk_probability_matrix,
        control_coupons=baseline.coupons,
        package_size=runtime_budget // plan.stake,
        floor_scale=config.package_exposure_floor_scale,
        floor_exponent=config.package_exposure_floor_exponent,
        near_fixed_share=config.package_near_fixed_share,
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
        exposure_constraints=exposure_constraints,
        fallback_coupons=baseline.coupons,
        deadline=deadline,
    )
    _write_replace(
        output / "quality-v3-final-research-coupons.txt",
        _research_package_bytes(
            "QUALITY_V3_BOUNDED_UNCERTAINTY_CHALLENGER",
            plan.stake,
            quality_v3.selected_coupons,
        ),
    )
    phase("robust")
    candidate_union = tuple(
        dict.fromkeys(
            (
                *baseline.coupons,
                *sports_result.coupons,
                *quality_v3.selected_coupons,
            )
        )
    )
    combined_models = MappingProxyType(
        {
            "bk": frozen.bk_probability_matrix,
            "sports": sports_probabilities,
            **{
                name: probabilities
                for name, probabilities in uncertainty_models.items()
                if name != "bk"
            },
        }
    )
    robust = select_robust_package(
        candidates=candidate_union,
        probability_models=combined_models,
        category=13,
        max_coupons=runtime_budget // plan.stake,
        sample_count=config.package_probability_samples,
        seed_material=(
            f"final-hybrid-robust-{snapshot.snapshot_sha256}-{probability_hash}"
        ),
        exposure_constraints=exposure_constraints,
        fallback_coupons=baseline.coupons,
        deadline=deadline,
    )
    _write_replace(
        output / "robust-final-research-coupons.txt",
        _research_package_bytes(
            "FINAL_PARALLEL_MODEL_MAXIMIN_RECOMBINATION",
            plan.stake,
            robust.selected_coupons,
        ),
    )
    phase("g1")
    checkpoint(
        "g1_admission",
        initial=len(robust.selected_coupons),
        universe=len(candidate_union),
        models=len(combined_models),
    )
    try:
        g1_research = (
            {
                "status": "DISABLED",
                "operator_compatible": False,
                "automatic_wagering": False,
                "research_only": True,
            }
            if g1_config is None
            else run_parallel_g1(
                initial_coupons=robust.selected_coupons,
                control_coupons=baseline.coupons,
                candidate_coupons=candidate_union,
                probability_models=combined_models,
                exposure_constraints=exposure_constraints,
                input_sha256=snapshot.snapshot_sha256,
                plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                bank=plan.requested_bank,
                effective_budget=runtime_budget,
                stake=plan.stake,
                safety_config=config.package_safety_config,
                deadline=deadline,
                config=g1_config,
            )
        )
    except Exception as exc:
        # Even unexpected adapter failures cannot replace any existing candidate.
        g1_research = {
            "status": "FALLBACK",
            "reason": type(exc).__name__,
            "selected_coupons": list(robust.selected_coupons),
            "research_only": True,
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
        }
    robust_coupons = robust.selected_coupons
    refinement_lineage = {
        "policy_version": "robust-family-g1-v1",
        "strategy_family": "robust",
        "variant": "g1-exact-maximin-refinement-v2",
        "applied": False,
        "parent_package_sha256": _package_sha256(robust_coupons),
        "authorization_route": "EXPLICIT_OPT_IN_EXISTING_ROBUST_FAMILY",
    }
    if isinstance(g1_config, ParallelG1Config) and g1_config.family_refinement:
        refined = family_refinement_coupons(
            g1_research,
            initial_coupons=robust.selected_coupons,
            candidate_coupons=candidate_union,
            models=combined_models,
            bounds=exposure_constraints,
            input_sha256=snapshot.snapshot_sha256,
            bank=plan.requested_bank,
            effective_budget=runtime_budget,
            stake=plan.stake,
            plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        )
        if refined is not None:
            robust_coupons = refined
            refinement_lineage["applied"] = True
    phase("cross_evaluation")
    baseline_quality_bk = package_quality_metrics(
        baseline.coupons,
        frozen.bk_probability_matrix,
        seed_material=f"final-hybrid-bk-{snapshot.snapshot_sha256}",
        monte_carlo_samples=config.package_probability_samples,
    )
    checkpoint("baseline_sports_quality")
    baseline_quality_sports = package_quality_metrics(
        baseline.coupons,
        sports_probabilities,
        seed_material=f"final-hybrid-bk-sports-{probability_hash}",
        monte_carlo_samples=config.package_probability_samples,
    )
    checkpoint("sports_bk_quality")
    sports_quality_bk = package_quality_metrics(
        sports_result.coupons,
        frozen.bk_probability_matrix,
        seed_material=f"final-hybrid-sports-bk-{snapshot.snapshot_sha256}",
        monte_carlo_samples=config.package_probability_samples,
    )
    checkpoint("sports_quality")
    sports_quality_sports = package_quality_metrics(
        sports_result.coupons,
        sports_probabilities,
        seed_material=f"final-hybrid-sports-{probability_hash}",
        monte_carlo_samples=config.package_probability_samples,
    )
    phase("selector_verification")
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
            coupons=robust_coupons,
            models=combined_models,
            probabilities=frozen.bk_probability_matrix,
            safety_config=config.package_safety_config,
            stake=plan.stake,
            timed_out=robust.timed_out,
        ),
    )
    experimental_selection = select_parallel_candidate(candidates)
    if refinement_lineage["applied"] and "robust" in experimental_selection.rejections:
        # The parent caller remains authoritative even after worker verification.
        robust_coupons = robust.selected_coupons
        candidates = (
            *candidates[:-1],
            _parallel_candidate(
                strategy_id="robust",
                coupons=robust_coupons,
                models=combined_models,
                probabilities=frozen.bk_probability_matrix,
                safety_config=config.package_safety_config,
                stake=plan.stake,
                timed_out=robust.timed_out,
            ),
        )
        experimental_selection = select_parallel_candidate(candidates)
        refinement_lineage["applied"] = False
        refinement_lineage["fallback_reason"] = "CALLER_SELECTOR_REJECTED_REFINEMENT"
    refinement_lineage["selected_package_sha256"] = _package_sha256(robust_coupons)
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
        "g1_research_refinement": g1_research,
        "o1_family_readiness": {
            "status": "UNAVAILABLE",
            "reason": "NO_INDEPENDENTLY_REVIEWED_EVENT_LOCAL_INPUT_ADAPTER",
            "assessment_executed": False,
            "role": "DESCRIPTIVE_EVIDENCE_ONLY_NOT_A_PROBABILITY_MODEL",
            "changes_probabilities": False,
            "strict_eligibility_reassessed": False,
            "gates_opened": [],
            "activation_allowed": False,
        },
        "baseline": _result_payload(baseline, baseline_quality_bk),
        "control_execution": {
            "mode": "RECOMPUTED"
            if primary_control_record is None
            else "VERIFIED_PRIMARY_REUSE",
            "operator_record_sha256": None
            if primary_control_record is None
            else primary_control_record.get("record_sha256"),
            "archive_manifest_sha256": None
            if primary_control_record is None
            else primary_control_record.get("archive_manifest_sha256"),
            "input_and_config_revalidated": True,
        },
        "sports": _result_payload(sports_result, sports_quality_sports),
        "robust": {
            "refinement_lineage": refinement_lineage,
            "sampled_metrics_scope": "PRE_G1_PARENT_PACKAGE",
            "coupon_count": len(robust_coupons),
            "cost": len(robust_coupons) * plan.stake,
            "unused_bank": runtime_budget - len(robust_coupons) * plan.stake,
            "candidate_count": robust.candidate_count,
            "category": robust.category,
            "sample_count_per_model": robust.sample_count_per_model,
            "worst_sampled_category_coverage": (robust.worst_sampled_category_coverage),
            "mean_sampled_category_coverage": (robust.mean_sampled_category_coverage),
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
        "coupon_order_semantics": "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK",
        "highest_p13_single_coupons": {
            "quality-v2": primary_ranking,
            "sports-shadow": _best_single_coupon_payload(
                sports_result.coupons,
                sports_probabilities,
                reference_model="sports",
            ),
            "quality-v3": _best_single_coupon_payload(
                quality_v3.selected_coupons,
                frozen.bk_probability_matrix,
                reference_model="bk",
            ),
            "robust": _best_single_coupon_payload(
                robust_coupons,
                frozen.bk_probability_matrix,
                reference_model="bk",
            ),
        },
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
                set(robust_coupons) & set(baseline.coupons)
            ),
            "robust_sports_overlap_count": len(
                set(robust_coupons) & set(sports_result.coupons)
            ),
        },
        "automatic_wagering": False,
        "operator_compatible": False,
        "scheduler_state_mutated": False,
        "profitability_proven": False,
    }
    phase("research_persistence")
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
            robust_coupons,
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


class PrimaryControlInvalid(ValueError):
    """Optional sidecar work lost its still-current native primary authority."""


def _validate_current_primary_upload(*, plan, operator, upload_sha256, now=None):
    """Revalidate native authority and current bytes, never reseal changed data.

    ``upload_sha256`` is pinned at the original native export. Native validation
    includes expiry, release authority, run paths/status/marker, CSV and archive.
    Re-read after validation as well: its IO must not hide a concurrent swap.
    """
    from toto_ai.runner.scheduler import (
        SchedulerError,
        _validated_actionable_operator_upload,
    )

    clock = now or (lambda: datetime.now(timezone.utc))

    def check_current():
        if clock() >= plan.publish_deadline:
            raise ValueError("primary expired at T-10")
        current = json.loads(
            _regular_file(
                plan.output_dir / "operator-result.json", "primary operator"
            ).read_bytes()
        )
        if current != operator or operator.get("package_sha256") != upload_sha256:
            raise ValueError("primary record/export binding changed")
        upload = _regular_file(operator.get("coupon_path"), "primary upload")
        source = _regular_file(operator.get("source_package_path"), "primary source")
        if upload != source.parent / "baltbet-upload.txt":
            raise ValueError("primary upload is not canonical run path")
        data = upload.read_bytes()
        if hashlib.sha256(data).hexdigest() != upload_sha256:
            raise ValueError("current primary upload hash mismatch")
        return data

    try:
        original = check_current()
        validated = _validated_actionable_operator_upload(
            plan, observed_at=clock(), allow_at_deadline=False
        )
        if validated != original or check_current() != original:
            raise ValueError("current primary bytes changed during validation")
    except (OSError, SchedulerError, TypeError, ValueError) as exc:
        raise PrimaryControlInvalid(f"verified primary reuse invalid: {exc}") from exc


def _reuse_verified_control(
    *,
    plan,
    snapshot,
    frozen,
    config,
    provenance,
    operator,
    expected_coupons,
    upload_sha256,
):
    """Reuse only a native-validated, same-plan final primary, not a loose TXT.

    The sidecar first performs the existing full actionable operator export
    (including authority/DB archive validation). This pure reader rechecks its
    record, current file identity, archive, source bytes, final input and exact
    probability/config provenance. It grants no release authority of its own.
    """
    import time

    from toto_ai.ev.package_quality import validate_selection_provenance
    from toto_ai.optimizer.strategy_comparison import _strategy_result
    from toto_ai.runner.scheduler import (
        _operator_result_sha256,
        _validate_experimental_manual_release,
        _validate_package_csv,
    )

    started = time.perf_counter()
    _validate_current_primary_upload(
        plan=plan, operator=operator, upload_sha256=upload_sha256
    )
    current = json.loads(
        _regular_file(
            plan.output_dir / "operator-result.json", "primary operator"
        ).read_bytes()
    )
    if (
        current != operator
        or operator.get("record_sha256") != _operator_result_sha256(operator)
        or operator.get("plan_id") != plan.plan_id
        or operator.get("drawing") != frozen.drawing_number
        or operator.get("drawing_id") != frozen.drawing_id
        or operator.get("decision") != "PLAY"
        or operator.get("operator_status") != "FINAL_FRESH"
        or operator.get("provenance") != "FINAL_FRESH"
        or operator.get("actionable") is not True
        or operator.get("automatic_wagering") is not False
        or operator.get("requested_bank") != config.bank
        or operator.get("stake") != config.stake
        or operator.get("effective_bank") != config.selection_budget
        or not expected_coupons
        or operator.get("package_sha256") != upload_sha256
    ):
        raise ValueError("verified primary reuse operator binding mismatch")
    if operator.get("release_mode") == "EXPERIMENTAL_MANUAL":
        auth = _validate_experimental_manual_release(plan)
        if auth["record_sha256"] != operator.get("release_authorization_sha256"):
            raise ValueError("verified primary reuse authorization mismatch")
    elif operator.get("release_mode") != "STANDARD":
        raise ValueError("verified primary reuse release mode mismatch")
    valid, reasons, _, _ = validate_selection_provenance(
        provenance, frozen.bk_probability_matrix, config=config, required=True
    )
    if not valid:
        raise ValueError(f"verified primary reuse provenance mismatch: {reasons}")
    run = snapshot.path.parent
    if (
        run != plan.output_dir / "attempts" / snapshot.attempt_id
        or operator.get("run_id") != snapshot.attempt_id
        or operator.get("source_package_path") != str(run / "package.csv")
        or operator.get("archive_manifest_path") != str(run / "package-archive.json")
    ):
        raise ValueError("verified primary reuse run path mismatch")
    source = _regular_file(run / "package.csv", "primary source").read_bytes()
    source_hash = hashlib.sha256(source).hexdigest()
    if source_hash != operator.get("source_package_sha256"):
        raise ValueError("verified primary reuse source hash mismatch")
    archive = json.loads(
        _regular_file(run / "package-archive.json", "primary archive").read_bytes()
    )
    unsigned = dict(archive)
    digest = unsigned.pop("archive_manifest_sha256", None)
    if (
        digest != operator.get("archive_manifest_sha256")
        or digest != hashlib.sha256(_canonical(unsigned)).hexdigest()
        or archive.get("final_input_sha256") != snapshot.snapshot_sha256
        or archive.get("probability_input_sha256") != snapshot.probability_input_sha256
        or archive.get("source_bytes_sha256") != source_hash
        or archive.get("source_path") != str(run / "package.csv")
        or archive.get("drawing_id") != frozen.drawing_id
        or archive.get("drawing_number") != frozen.drawing_number
        or archive.get("stake") != frozen.stake
        or archive.get("cost") != config.selection_budget
        or archive.get("coupon_count") != config.max_coupons
        or archive.get("provenance") != "pre_bet_runner"
    ):
        raise ValueError("verified primary reuse final/archive binding mismatch")
    validated = _validate_package_csv(
        source,
        stake=frozen.stake,
        minimum_gross_ev=config.min_gross_ev,
        expected_count=config.max_coupons,
        expected_cost=config.selection_budget,
    )
    if validated.coupons != expected_coupons or _package_sha256(
        validated.coupons
    ) != archive.get("canonical_package_sha256"):
        raise ValueError("verified primary reuse coupon binding mismatch")
    checkpoint(
        "verified_primary_reuse", coupons=len(validated.coupons), ev_calls_avoided=1
    )
    result = _strategy_result(
        strategy_id="EV_CROWD_CURRENT",
        source_engine="verified_scheduler_primary",
        category=13,
        frozen=frozen,
        coupons=validated.coupons,
        config={"category": 13, "ev_config": asdict(config)},
        runtime_seconds=time.perf_counter() - started,
    )
    return replace(result, runtime_seconds=time.perf_counter() - started)


def _exact_model_metrics(
    coupons: tuple[str, ...],
    models: Mapping[str, tuple[tuple[float, float, float], ...]],
) -> list[dict[str, float | str]]:
    rows = []
    for name, probabilities in models.items():
        checkpoint("exact_model_metrics", model=name, coupons=len(coupons))
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
            if sports_event.event_order != target.event_order or str(
                sports_event.event_id
            ) != str(target.event_id):
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
            reasons.extend(f"package_safety:{code}" for code in safety.reason_codes)
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
    return max(max(row["shares"].values()) for row in outcome_exposure(coupons))


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


def _best_single_coupon_payload(
    coupons: tuple[str, ...],
    probabilities: tuple[tuple[float, float, float], ...],
    *,
    reference_model: str,
) -> dict[str, Any]:
    result = best_coupon_by_p13(coupons, probabilities)
    return {
        **asdict(result),
        "reference_model": reference_model,
        "package_order_semantics": "PACKAGE_SELECTION_ORDER_NOT_PROBABILITY_RANK",
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
