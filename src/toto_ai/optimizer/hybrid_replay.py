"""Historical equal-input replay of quality-v2, Sports v2, v3 and robust.

This module is deliberately research-only.  It consumes immutable historical
artifacts, verifies that the quality-v2 generator reproduces the archived
control package, and never imports scheduler execution or operator release.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    bound_selection_context,
    exact_category_probabilities,
    selection_context_sha256,
    selection_probability_input_sha256,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.operations.finished_draw import _compute_settlement
from toto_ai.optimizer.hybrid_attribution import (
    build_hybrid_event_attribution,
    write_hybrid_event_attribution,
)
from toto_ai.optimizer.prospective_quality import QualityV3Config
from toto_ai.optimizer.quality_replay import (
    load_historical_actual_result,
    load_historical_replay_artifacts,
)
from toto_ai.optimizer.robust_package import select_robust_package
from toto_ai.optimizer.strategy_comparison import run_ev_crowd_current
from toto_ai.optimizer.strategy_execution import frozen_input_from_snapshot
from toto_ai.optimizer.uncertainty_package import (
    build_uncertainty_models,
    outcome_exposure,
    select_uncertainty_package,
)
from toto_ai.package.audit import parse_package
from toto_ai.sports_stats.probabilities import load_shadow_probability_artifact

STATUS = "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE"
ARTIFACT_CLASS = "HISTORICAL_QUALITY_SPORTS_V2_ROBUST_REPLAY"


def execute_historical_hybrid_replay(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    baseline_package_path: str | Path,
    sports_artifact_path: str | Path,
    db_path: str | Path,
    output_dir: str | Path,
) -> tuple[dict[str, Any], Path]:
    """Replay four strategies on one historical input and realized result."""

    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    final_path = _regular_file(final_input_path, "final input")
    baseline_path = _regular_file(baseline_package_path, "baseline package")
    sports_path = _regular_file(sports_artifact_path, "sports artifact")
    plan, snapshot = load_historical_replay_artifacts(
        scheduler_plan_path=plan_path,
        final_input_path=final_path,
    )
    frozen = frozen_input_from_snapshot(snapshot, plan)
    archived_baseline = parse_package(baseline_path)
    runtime_budget = effective_selection_budget(
        requested_bank=plan.requested_bank,
        pool_sum=frozen.pool_sum,
        stake=plan.stake,
    )
    coupon_capacity = runtime_budget // plan.stake
    if len(archived_baseline) != coupon_capacity:
        raise ValueError("archived quality-v2 package does not fill replay capacity")

    # Artifact completeness is not revalidated against today's mutable ledger.
    # The historical hash bindings still seed the unchanged quality-v2 selector.
    research_config = replace(
        plan.quality_v2_ev_config,
        effective_budget=runtime_budget,
        package_provenance_required=False,
    )
    plan_sha256 = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    baseline_provenance = _historical_provenance(
        plan=plan,
        config=research_config,
        probability_snapshot_sha256=snapshot.snapshot_sha256,
        probability_input_sha256=snapshot.probability_input_sha256,
        scheduler_plan_sha256=plan_sha256,
    )
    reproduced = run_ev_crowd_current(
        frozen,
        config=research_config,
        provenance=baseline_provenance,
    )
    if reproduced.coupons != archived_baseline:
        raise ValueError(
            "historical quality-v2 reproduction differs from archived control"
        )

    sports = load_shadow_probability_artifact(sports_path)
    _validate_sports_identity(plan, frozen, snapshot, sports)
    sports_probabilities = _rebase_sports_probabilities(
        frozen.bk_probability_matrix,
        sports.events,
    )
    sports_frozen = replace(
        frozen,
        events=tuple(
            replace(event, bk_probabilities=sports_probabilities[event.event_order])
            for event in frozen.events
        ),
    )
    sports_probability_hash = selection_probability_input_sha256(
        sports_probabilities
    )
    sports_snapshot_hash = _sha256_json(
        {
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "final_input_sha256": snapshot.snapshot_sha256,
            "sports_artifact_sha256": sports.artifact_sha256,
            "probability_input_sha256": sports_probability_hash,
            "probabilities": sports_probabilities,
        }
    )
    sports_provenance = _historical_provenance(
        plan=plan,
        config=research_config,
        probability_snapshot_sha256=sports_snapshot_hash,
        probability_input_sha256=sports_probability_hash,
        scheduler_plan_sha256=plan_sha256,
    )
    sports_v2 = (
        reproduced
        if sports.sports_coverage_count == 0
        else run_ev_crowd_current(
            sports_frozen,
            config=research_config,
            provenance=sports_provenance,
        )
    )
    if len(sports_v2.coupons) != coupon_capacity:
        raise ValueError("Sports v2 replay did not fill the equal coupon capacity")

    quality_v3_config = QualityV3Config()
    uncertainty_models = build_uncertainty_models(
        frozen.bk_probability_matrix,
        flatten_weights=quality_v3_config.flatten_weights,
    )
    quality_v3_result = select_uncertainty_package(
        bk_probabilities=frozen.bk_probability_matrix,
        anchor_coupons=archived_baseline,
        category=quality_v3_config.category,
        max_coupons=coupon_capacity,
        flatten_weights=quality_v3_config.flatten_weights,
        top_count=max(quality_v3_config.top_count, coupon_capacity),
        candidate_sample_count=quality_v3_config.candidate_sample_count,
        mutation_limit=quality_v3_config.mutation_limit,
        selection_sample_count=quality_v3_config.scenario_sample_count,
        seed_material=f"quality-v3-{snapshot.snapshot_sha256}",
    )
    if quality_v3_result.timed_out:
        raise ValueError("quality-v3 historical replay timed out")
    quality_v3 = tuple(quality_v3_result.selected_coupons)
    if len(quality_v3) != coupon_capacity:
        raise ValueError("quality-v3 replay did not fill the equal coupon capacity")

    models = {
        "bk": frozen.bk_probability_matrix,
        "sports_v2": sports_probabilities,
        **{
            name: probabilities
            for name, probabilities in uncertainty_models.items()
            if name != "bk"
        },
    }
    candidates = tuple(
        dict.fromkeys((*archived_baseline, *sports_v2.coupons, *quality_v3))
    )
    robust_result = select_robust_package(
        candidates=candidates,
        probability_models=models,
        category=13,
        max_coupons=coupon_capacity,
        sample_count=research_config.package_probability_samples,
        seed_material=(
            f"historical-hybrid-robust-{snapshot.snapshot_sha256}-"
            f"{sports_probability_hash}"
        ),
    )
    if robust_result.timed_out:
        raise ValueError("robust historical replay timed out")
    robust = tuple(robust_result.selected_coupons)
    if len(robust) != coupon_capacity:
        raise ValueError("robust replay did not fill the equal coupon capacity")

    actual = load_historical_actual_result(
        db_path,
        drawing_number=frozen.drawing_number,
    )
    if actual is None:
        raise ValueError("historical drawing has no terminal result")
    packages = {
        "quality-v2": archived_baseline,
        "sports-v2": sports_v2.coupons,
        "quality-v3": quality_v3,
        "robust": robust,
    }
    strategies = {
        name: _strategy_payload(coupons, models=models, actual=actual, stake=plan.stake)
        for name, coupons in packages.items()
    }
    input_hashes = {
        "final_input_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "sports_probability_input_sha256": sports_probability_hash,
        "sports_artifact_sha256": sports.artifact_sha256,
        "scheduler_plan_sha256": plan_sha256,
    }
    attribution = build_hybrid_event_attribution(
        drawing_id=frozen.drawing_id,
        drawing_number=frozen.drawing_number,
        plan_id=plan.plan_id,
        event_names=tuple(event.name for event in frozen.events),
        actual=actual,
        probability_models=models,
        packages=packages,
        sports_events=sports.events,
        source_hashes=input_hashes,
    )
    report: dict[str, Any] = {
        "schema_version": 2,
        "status": STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": frozen.drawing_id,
        "drawing_number": frozen.drawing_number,
        "plan_id": plan.plan_id,
        "bank": plan.requested_bank,
        "effective_budget": runtime_budget,
        "stake": plan.stake,
        "equal_coupon_count": coupon_capacity,
        "equal_cost": coupon_capacity * plan.stake,
        "actual": actual,
        "quality_v2_reproduced_exactly": True,
        "sports_coverage_count": sports.sports_coverage_count,
        "sports_fallback_count": sports.fallback_count,
        "strategies": strategies,
        "overlap": {
            left: {
                right: len(set(packages[left]) & set(packages[right]))
                for right in packages
                if right != left
            }
            for left in packages
        },
        "inputs": input_hashes,
        "event_attribution": {
            "artifact_class": attribution["artifact_class"],
            "report_sha256": attribution["report_sha256"],
            "summary": attribution["summary"],
        },
        "historical_provenance_policy": (
            "declared immutable hashes seed the unchanged selector; live ledger "
            "is not consulted and operator provenance remains disabled"
        ),
        "automatic_wagering": False,
        "operator_compatible": False,
        "scheduler_state_mutated": False,
        "profitability_proven": False,
    }
    report["report_sha256"] = _sha256_json(report)

    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("output directory must be a regular directory")
    report_path = output / "historical-hybrid-replay.json"
    _write_replace(report_path, _pretty(report))
    _write_csv(output / "historical-hybrid-replay.csv", report)
    _write_markdown(output / "historical-hybrid-replay.md", report)
    write_hybrid_event_attribution(attribution, output_dir=output)
    for name, coupons in packages.items():
        _write_research_package(
            output / f"{name}-research-coupons.txt",
            role=name,
            stake=plan.stake,
            coupons=coupons,
        )
    return report, report_path


def _historical_provenance(
    *,
    plan: Any,
    config: EVConfig,
    probability_snapshot_sha256: str,
    probability_input_sha256: str,
    scheduler_plan_sha256: str,
) -> PackageSelectionProvenance:
    context = bound_selection_context(config)
    return PackageSelectionProvenance(
        probability_snapshot_sha256=probability_snapshot_sha256,
        probability_input_sha256=probability_input_sha256,
        schedule_evidence_ledger_sha256=(
            plan.schedule_evidence_ledger_sha256
        ),
        schedule_evidence_semantic_hash=(
            plan.schedule_evidence_semantic_hash
        ),
        scheduler_plan_sha256=scheduler_plan_sha256,
        selection_context=context,
        selection_context_sha256=selection_context_sha256(context),
    )


def _validate_sports_identity(
    plan: Any,
    frozen: Any,
    snapshot: Any,
    sports: Any,
) -> None:
    parsed = parse_target_drawing(snapshot.payload, snapshot.captured_at)
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
        raise ValueError("Sports v2 artifact drawing identity mismatch")
    if sports.as_of > snapshot.captured_at:
        raise ValueError("Sports v2 artifact was captured after final input")
    if len(sports.events) != 15:
        raise ValueError("Sports v2 artifact must contain exactly 15 events")
    for target, frozen_event, sports_event in zip(
        parsed.events,
        frozen.events,
        sorted(sports.events, key=lambda event: event.event_order),
        strict=True,
    ):
        if (
            sports_event.event_order != target.event_order
            or str(sports_event.event_id) != str(target.event_id)
            or any(
                not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
                for left, right in zip(
                    sports_event.bk_probabilities,
                    frozen_event.bk_probabilities,
                    strict=True,
                )
            )
        ):
            raise ValueError("Sports v2 artifact event identity mismatch")


def _rebase_sports_probabilities(
    baseline: Sequence[Sequence[float]],
    sports_events: Sequence[Any],
) -> tuple[tuple[float, float, float], ...]:
    ordered = tuple(sorted(sports_events, key=lambda event: event.event_order))
    if tuple(event.event_order for event in ordered) != tuple(range(15)):
        raise ValueError("Sports v2 event order is invalid")
    rows = []
    for bk_row, event in zip(baseline, ordered, strict=True):
        weight = float(event.blend_weight)
        if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
            raise ValueError("Sports v2 blend weight is invalid")
        if event.fallback_reason is not None:
            weight = 0.0
        raw = tuple(
            (1.0 - weight) * bk + weight * sports
            for bk, sports in zip(
                bk_row,
                event.sports_probabilities,
                strict=True,
            )
        )
        total = math.fsum(raw)
        if not math.isfinite(total) or total <= 0.0:
            raise ValueError("Sports v2 probability row is invalid")
        rows.append(tuple(value / total for value in raw))
    return tuple(rows)


def _strategy_payload(
    coupons: Sequence[str],
    *,
    models: Mapping[str, Sequence[Sequence[float]]],
    actual: str,
    stake: int,
) -> dict[str, Any]:
    package = tuple(coupons)
    settlement = _compute_settlement(
        actual=actual,
        coupons=package,
        stake=stake,
        payments=None,
    )
    return {
        "package_sha256": hashlib.sha256(
            ",".join(package).encode("utf-8")
        ).hexdigest(),
        "coupon_count": len(package),
        "cost": len(package) * stake,
        "maximum_outcome_share": max(
            float(share)
            for event in outcome_exposure(package)
            for share in event["shares"].values()
        ),
        "models": [
            {
                "model": name,
                "p13": probabilities[0],
                "p14": probabilities[1],
                "p15": probabilities[2],
            }
            for name, rows in models.items()
            for probabilities in [exact_category_probabilities(package, rows)]
        ],
        "settlement": {
            "best_hits": settlement["best_hits"],
            "hit13": settlement["hit_distribution"][13],
            "hit14": settlement["hit_distribution"][14],
            "hit15": settlement["hit_distribution"][15],
            "average_hits": _average_hits(package, actual),
            "fixed_miss_events": settlement["fixed_miss_events"],
            "zero_exposure_miss_events": settlement[
                "zero_exposure_miss_events"
            ],
        },
    }


def _average_hits(coupons: Sequence[str], actual: str) -> float:
    return sum(
        sum(
            expected == observed
            for expected, observed in zip(coupon, actual, strict=True)
        )
        for coupon in coupons
    ) / len(coupons)


def _write_csv(path: Path, report: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "drawing_number",
                "strategy",
                "model",
                "p13",
                "p14",
                "p15",
                "best_hits",
                "average_hits",
                "hit13",
                "hit14",
                "hit15",
            ),
        )
        writer.writeheader()
        for name, strategy in report["strategies"].items():
            settlement = strategy["settlement"]
            for model in strategy["models"]:
                writer.writerow(
                    {
                        "drawing_number": report["drawing_number"],
                        "strategy": name,
                        **model,
                        "best_hits": settlement["best_hits"],
                        "average_hits": settlement["average_hits"],
                        "hit13": settlement["hit13"],
                        "hit14": settlement["hit14"],
                        "hit15": settlement["hit15"],
                    }
                )


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        f"# Historical hybrid replay: {report['drawing_number']}",
        "",
        f"- Status: `{report['status']}`",
        f"- Equal package: {report['equal_coupon_count']} coupons / "
        f"{report['equal_cost']} RUB",
        f"- Sports coverage: {report['sports_coverage_count']}/15",
        f"- Quality-v2 reproduced: {report['quality_v2_reproduced_exactly']}",
        "",
        "| Strategy | Best | Average | 13 | 14 | 15 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, strategy in report["strategies"].items():
        settled = strategy["settlement"]
        lines.append(
            f"| {name} | {settled['best_hits']} | "
            f"{settled['average_hits']:.3f} | {settled['hit13']} | "
            f"{settled['hit14']} | {settled['hit15']} |"
        )
    lines.extend(
        (
            "",
            "Research only. Not operator-compatible. No profitability claim.",
            "",
        )
    )
    _write_replace(path, "\n".join(lines).encode("utf-8"))


def _write_research_package(
    path: Path,
    *,
    role: str,
    stake: int,
    coupons: Sequence[str],
) -> None:
    content = "\n".join(
        (
            "RESEARCH ONLY / NOT ACTIVATED / DO NOT WAGER",
            "NOT A BALTBet UPLOAD FILE",
            f"role={role} stake={stake} coupons={len(coupons)}",
            "",
            *coupons,
            "",
        )
    ).encode("utf-8")
    _write_replace(path, content)


def _regular_file(value: str | Path, label: str) -> Path:
    path = Path(value).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    return path


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


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
