"""Artifact-bound historical replay of quality-v2 versus quality-v3.

The replay keeps the historical quality-v2 package byte-for-byte as the
control and gives quality-v3 the same coupon count.  It is research-only and
cannot create or mutate scheduler/operator artifacts.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from toto_ai.db.models import Drawing, DrawingResultSnapshot, Event
from toto_ai.db.session import get_session_factory, open_readonly_db
from toto_ai.ev.drawing import effective_selection_budget
from toto_ai.ev.package_quality import (
    exact_category_probabilities,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.operations.finished_draw import VOID_RESULT, _compute_settlement
from toto_ai.optimizer.prospective_quality import QualityV3Config
from toto_ai.optimizer.strategy_execution import frozen_input_from_snapshot
from toto_ai.optimizer.uncertainty_package import (
    build_uncertainty_models,
    outcome_exposure,
    select_uncertainty_package,
)
from toto_ai.package.audit import canonical_probability_input_sha256, parse_package
from toto_ai.runner.final_input import FinalInputSnapshot

STATUS = "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE"
ARTIFACT_CLASS = "QUALITY_V2_VS_V3_ARTIFACT_REPLAY"


@dataclass(frozen=True)
class _HistoricalReplayPlan:
    plan_id: str
    drawing: int
    drawing_id: int
    ended_at: datetime
    operational_cutoff: datetime
    requested_bank: int
    stake: int


def execute_quality_replay(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    baseline_package_path: str | Path,
    db_path: str | Path,
    output_dir: str | Path,
    quality_v3_config: QualityV3Config | None = None,
) -> tuple[dict[str, Any], Path]:
    """Replay one immutable historical control and an equal-cost challenger."""

    plan_path = _regular_file(scheduler_plan_path, "scheduler plan")
    input_path = _regular_file(final_input_path, "final input")
    package_path = _regular_file(baseline_package_path, "baseline package")
    plan, snapshot = _load_historical_artifacts(plan_path, input_path)
    frozen = frozen_input_from_snapshot(snapshot, plan)
    baseline = parse_package(package_path)
    runtime_budget = effective_selection_budget(
        requested_bank=plan.requested_bank,
        pool_sum=frozen.pool_sum,
        stake=plan.stake,
    )
    if len(baseline) * plan.stake > runtime_budget:
        raise ValueError("historical baseline package exceeds its effective budget")

    config = QualityV3Config() if quality_v3_config is None else quality_v3_config
    if config.top_count < len(baseline):
        config = replace(config, top_count=len(baseline))
    models = build_uncertainty_models(
        frozen.bk_probability_matrix,
        flatten_weights=config.flatten_weights,
    )
    challenger = select_uncertainty_package(
        bk_probabilities=frozen.bk_probability_matrix,
        anchor_coupons=baseline,
        category=config.category,
        max_coupons=len(baseline),
        flatten_weights=config.flatten_weights,
        top_count=config.top_count,
        candidate_sample_count=config.candidate_sample_count,
        mutation_limit=config.mutation_limit,
        selection_sample_count=config.scenario_sample_count,
        seed_material=f"quality-replay-{snapshot.snapshot_sha256}",
    )
    if challenger.timed_out:
        raise ValueError("quality-v3 replay timed out")
    quality_v3 = tuple(challenger.selected_coupons)
    if len(quality_v3) != len(baseline):
        raise ValueError("quality-v3 replay must have the control coupon count")

    actual = _load_actual_result(db_path, drawing_number=frozen.drawing_number)
    report = compare_quality_packages(
        drawing_id=frozen.drawing_id,
        drawing_number=frozen.drawing_number,
        plan_id=plan.plan_id,
        final_input_sha256=snapshot.snapshot_sha256,
        probability_input_sha256=snapshot.probability_input_sha256,
        bank=plan.requested_bank,
        effective_budget=runtime_budget,
        stake=plan.stake,
        baseline=baseline,
        quality_v3=quality_v3,
        models=models,
        actual=actual,
        quality_v3_config=config,
    )
    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("output directory must be a regular directory")
    report_path = output / "quality-v2-v3-replay.json"
    _write_replace(report_path, _pretty(report))
    _write_rows(output / "quality-v2-v3-replay.csv", report)
    _write_markdown(output / "quality-v2-v3-replay.md", report)
    _write_research_package(
        output / "quality-v3-research-coupons.txt",
        stake=plan.stake,
        coupons=quality_v3,
    )
    return report, report_path


def compare_quality_packages(
    *,
    drawing_id: int,
    drawing_number: int,
    plan_id: str,
    final_input_sha256: str,
    probability_input_sha256: str,
    bank: int,
    effective_budget: int,
    stake: int,
    baseline: Sequence[str],
    quality_v3: Sequence[str],
    models: Mapping[str, Sequence[Sequence[float]]],
    actual: str | None,
    quality_v3_config: QualityV3Config,
) -> dict[str, Any]:
    """Build a fair equal-cost comparison from two already generated packages."""

    control = tuple(baseline)
    challenger = tuple(quality_v3)
    if not control or len(control) != len(challenger):
        raise ValueError("quality replay requires non-empty equal-size packages")
    all_coupons = (*control, *challenger)
    if any(
        len(coupon) != 15 or set(coupon) - set("1X2")
        for coupon in all_coupons
    ):
        raise ValueError("quality replay coupons must be 15-character 1/X/2 rows")
    if len(set(control)) != len(control) or len(set(challenger)) != len(challenger):
        raise ValueError("quality replay packages must not contain duplicates")
    if len(control) * stake > effective_budget:
        raise ValueError("quality replay package exceeds effective budget")
    if not models or tuple(models)[0] != "bk":
        raise ValueError("quality replay requires BK as the first model")
    if actual is not None and (
        len(actual) != 15 or set(actual) - (set("1X2") | {VOID_RESULT})
    ):
        raise ValueError("actual result must be a terminal 15-outcome row")

    strategies = {
        "quality-v2": _package_payload(control, models, stake, actual),
        "quality-v3": _package_payload(challenger, models, stake, actual),
    }
    settlement = None
    if actual is not None:
        q2 = strategies["quality-v2"]["settlement"]
        q3 = strategies["quality-v3"]["settlement"]
        settlement = {
            "actual": actual,
            "quality_v3_minus_quality_v2_best_hits": q3["best_hits"] - q2["best_hits"],
            "quality_v3_minus_quality_v2_hit13": q3["hit13"] - q2["hit13"],
            "quality_v3_minus_quality_v2_hit14": q3["hit14"] - q2["hit14"],
            "quality_v3_minus_quality_v2_hit15": q3["hit15"] - q2["hit15"],
        }
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "plan_id": plan_id,
        "final_input_sha256": final_input_sha256,
        "probability_input_sha256": probability_input_sha256,
        "bank": bank,
        "effective_budget": effective_budget,
        "stake": stake,
        "equal_coupon_count": len(control),
        "equal_cost": len(control) * stake,
        "quality_v3_config": quality_v3_config.payload(coupon_capacity=len(control)),
        "strategies": strategies,
        "settled": actual is not None,
        "settlement_comparison": settlement,
        "automatic_wagering": False,
        "operator_compatible": False,
        "scheduler_state_mutated": False,
        "profitability_proven": False,
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    return report


def _package_payload(
    coupons: tuple[str, ...],
    models: Mapping[str, Sequence[Sequence[float]]],
    stake: int,
    actual: str | None,
) -> dict[str, Any]:
    metrics = []
    for name, probabilities in models.items():
        p13, p14, p15 = exact_category_probabilities(coupons, probabilities)
        metrics.append({"model": name, "p13": p13, "p14": p14, "p15": p15})
    settlement = None
    if actual is not None:
        raw = _compute_settlement(
            actual=actual,
            coupons=coupons,
            stake=stake,
            payments=None,
        )
        settlement = {
            "best_hits": raw["best_hits"],
            "hit13": raw["hit_distribution"][13],
            "hit14": raw["hit_distribution"][14],
            "hit15": raw["hit_distribution"][15],
            "fixed_miss_events": raw["fixed_miss_events"],
            "zero_exposure_miss_events": raw["zero_exposure_miss_events"],
        }
    return {
        "package_sha256": _package_sha256(coupons),
        "coupon_count": len(coupons),
        "cost": len(coupons) * stake,
        "maximum_outcome_share": _maximum_outcome_share(coupons),
        "models": metrics,
        "settlement": settlement,
    }


def _load_actual_result(db_path: str | Path, *, drawing_number: int) -> str | None:
    engine = open_readonly_db(db_path)
    factory = get_session_factory(engine)
    try:
        with factory() as session:
            snapshot = session.scalar(
                select(DrawingResultSnapshot)
                .where(
                    DrawingResultSnapshot.drawing_number == drawing_number,
                    DrawingResultSnapshot.complete.is_(True),
                )
                .order_by(DrawingResultSnapshot.id.desc())
                .limit(1)
            )
            if snapshot is not None:
                return snapshot.actual
            drawing = session.scalar(
                select(Drawing)
                .where(Drawing.number == drawing_number)
                .order_by(Drawing.id.desc())
                .limit(1)
            )
            if drawing is None:
                return None
            events = tuple(
                session.scalars(
                    select(Event)
                    .where(Event.drawing_id == drawing.id)
                    .order_by(Event.event_order)
                ).all()
            )
            if len(events) != 15:
                return None
            normalized = tuple(_terminal_event_result(event) for event in events)
            if any(value is None for value in normalized):
                return None
            return "".join(value for value in normalized if value is not None)
    finally:
        engine.dispose()


def _terminal_event_result(event: Event) -> str | None:
    result = (event.result or "").strip().upper()
    status = (event.result_status or "").strip().lower()
    if result in set("1X2"):
        return result
    if result in {"*", "VOID"} or status in {
        "void",
        "cancelled",
        "canceled",
        "postponed",
        "postpone",
        "pst",
    }:
        return VOID_RESULT
    return None


def _load_historical_artifacts(
    plan_path: Path,
    input_path: Path,
) -> tuple[_HistoricalReplayPlan, FinalInputSnapshot]:
    """Load frozen history without revalidating today's mutable evidence ledger."""

    plan_document = _json_object(plan_path, "scheduler plan")
    required_plan_keys = {
        "schema_version",
        "plan_id",
        "target",
        "config",
        "paths",
        "deadlines",
    }
    if set(plan_document) != required_plan_keys:
        raise ValueError("historical scheduler plan keys are invalid")
    semantic = {
        key: plan_document[key]
        for key in ("schema_version", "target", "config", "paths")
    }
    expected_plan_id = hashlib.sha256(_canonical(semantic)).hexdigest()[:16]
    if plan_document["plan_id"] != expected_plan_id:
        raise ValueError("historical scheduler plan_id mismatch")
    target = plan_document["target"]
    config = plan_document["config"]
    if not isinstance(target, Mapping) or not isinstance(config, Mapping):
        raise ValueError("historical scheduler target/config are invalid")
    plan = _HistoricalReplayPlan(
        plan_id=expected_plan_id,
        drawing=_positive_int(target.get("drawing"), "drawing"),
        drawing_id=_positive_int(target.get("drawing_id"), "drawing_id"),
        ended_at=_datetime(target.get("ended_at"), "ended_at"),
        operational_cutoff=_datetime(
            target.get("operational_cutoff", target.get("ended_at")),
            "operational_cutoff",
        ),
        requested_bank=_positive_int(config.get("requested_bank"), "requested_bank"),
        stake=_positive_int(config.get("stake"), "stake"),
    )

    document = _json_object(input_path, "final input")
    declared_snapshot = document.get("snapshot_sha256")
    unsigned = dict(document)
    unsigned.pop("snapshot_sha256", None)
    if (
        not isinstance(declared_snapshot, str)
        or hashlib.sha256(_canonical(unsigned)).hexdigest() != declared_snapshot
    ):
        raise ValueError("historical final input snapshot hash mismatch")
    if document.get("plan_id") != plan.plan_id:
        raise ValueError("historical final input plan identity mismatch")
    captured_at = _datetime(document.get("captured_at"), "captured_at")
    deadline = _datetime(document.get("deadline"), "deadline")
    payload = document.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("historical final input payload is invalid")
    parsed = parse_target_drawing(payload, captured_at)
    if (
        parsed.drawing_id != plan.drawing_id
        or parsed.drawing_number != plan.drawing
        or parsed.deadline not in {plan.ended_at, plan.operational_cutoff}
        or deadline != plan.ended_at
        or captured_at > plan.ended_at
    ):
        raise ValueError("historical final input target identity mismatch")
    detail_hash = hashlib.sha256(_canonical(dict(payload))).hexdigest()
    probability_hash = canonical_probability_input_sha256(
        tuple(event.bk_probabilities for event in parsed.events)
    )
    fingerprint = target_fingerprint(
        drawing_id=parsed.drawing_id,
        drawing_number=parsed.drawing_number,
        deadline=deadline,
        events=parsed.events,
    )
    if (
        document.get("detail_payload_sha256") != detail_hash
        or document.get("probability_input_sha256") != probability_hash
        or document.get("target_fingerprint") != fingerprint
    ):
        raise ValueError("historical final input content binding mismatch")
    snapshot = FinalInputSnapshot(
        schema_version=_positive_int(document.get("schema_version"), "schema_version"),
        plan_id=plan.plan_id,
        attempt_id=str(document.get("attempt_id") or ""),
        drawing_id=plan.drawing_id,
        drawing_number=plan.drawing,
        deadline=deadline,
        captured_at=captured_at,
        target_fingerprint=fingerprint,
        detail_payload_sha256=detail_hash,
        probability_input_sha256=probability_hash,
        timing_override_sha256=document.get("timing_override_sha256"),
        payload=payload,
        snapshot_sha256=declared_snapshot,
        path=input_path,
    )
    return plan, snapshot


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} could not be loaded") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _maximum_outcome_share(coupons: Sequence[str]) -> float:
    return max(
        float(share)
        for event in outcome_exposure(coupons)
        for share in event["shares"].values()
    )


def _package_sha256(coupons: Sequence[str]) -> str:
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def _regular_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).absolute()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _write_rows(path: Path, report: Mapping[str, Any]) -> None:
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
                "hit13",
                "hit14",
                "hit15",
            ),
        )
        writer.writeheader()
        for strategy, payload in report["strategies"].items():
            settlement = payload["settlement"] or {}
            for metric in payload["models"]:
                writer.writerow(
                    {
                        "drawing_number": report["drawing_number"],
                        "strategy": strategy,
                        "model": metric["model"],
                        "p13": metric["p13"],
                        "p14": metric["p14"],
                        "p15": metric["p15"],
                        "best_hits": settlement.get("best_hits"),
                        "hit13": settlement.get("hit13"),
                        "hit14": settlement.get("hit14"),
                        "hit15": settlement.get("hit15"),
                    }
                )


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        f"# Quality-v2 vs quality-v3 replay: {report['drawing_number']}",
        "",
        f"- Status: `{report['status']}`",
        f"- Equal coupons: {report['equal_coupon_count']}",
        f"- Equal cost: {report['equal_cost']}",
        f"- Settled: {report['settled']}",
        "",
        "| Strategy | BK P13 | BK P14 | BK P15 | Best hits |",
        "|---|---:|---:|---:|---:|",
    ]
    for strategy, payload in report["strategies"].items():
        bk = next(row for row in payload["models"] if row["model"] == "bk")
        settlement = payload["settlement"] or {}
        cells = (
            strategy,
            f"{bk['p13']:.8f}",
            f"{bk['p14']:.8f}",
            f"{bk['p15']:.8f}",
            settlement.get("best_hits", ""),
        )
        lines.append("| " + " | ".join(str(value) for value in cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_research_package(path: Path, *, stake: int, coupons: Sequence[str]) -> None:
    rows = [f"# {STATUS}", f"# stake={stake}", "# operator_compatible=false"]
    rows.extend(f"{stake};" + ";".join(coupon) for coupon in coupons)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_replace(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
