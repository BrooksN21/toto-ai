"""Plan-bound execution of the production quality-v2 pipeline for training."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.collector.lifecycle import RawArchive, RawArchiveRecord
from toto_ai.ev.drawing import build_open_ev_package, effective_selection_budget
from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    bound_selection_context,
    quality_v2_config_payload,
    quality_v2_config_sha256,
    selection_context_sha256,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.optimizer.category_hit import (
    CategoryHitSeedInfeasibleError,
    cover_14_bk_fill_seed,
)
from toto_ai.runner.final_input import (
    FinalInputSnapshot,
    load_final_input,
    persist_final_input,
)
from toto_ai.runner.morning_dispatch import load_morning_dispatch_record
from toto_ai.runner.scheduler import (
    SCHEDULER_PLAN_FILENAME,
    SchedulerPlan,
    _ensure_output_directory,
    _read_regular_file,
    _require_contained_path,
    _require_output_directory,
    _unlink_output_path,
    _write_exclusive_atomic,
    load_scheduler_plan,
    render_paper_package,
    validate_paper_package,
)
from toto_ai.runner.scheduler_state import scheduler_lock

TRAINING_PACKAGE_SCHEMA_VERSION = 2
TRAINING_DIAGNOSTICS_SCHEMA_VERSION = 1
TRAINING_PACKAGE_ROOT = "training-package"
TRAINING_PACKAGE_RESULT_FILENAME = "training-package-result.json"
TRAINING_INPUT_FILENAME = "final-input.json"
TRAINING_PAPER_FILENAME = "training-paper-package.txt"
TRAINING_DIAGNOSTICS_FILENAME = "training-quality-v2.json"
TRAINING_MODE = "TRAINING_PAPER"
TRAINING_PIPELINE = "production_quality_v2_ev"
_SHA256_LENGTH = 64


class TrainingPackageDeferred(ValueError):
    """The current immutable input is too early for a valid training package."""


@dataclass(frozen=True)
class SchedulerTrainingPackageResult:
    result_path: Path
    input_path: Path
    paper_path: Path
    diagnostics_path: Path
    plan_id: str
    drawing: int
    drawing_id: int
    deadline: datetime
    generated_at: datetime
    input_captured_at: datetime
    mode: str
    actionable: bool
    operator_export_allowed: bool
    automatic_wagering: bool
    pipeline: str
    structural_status: str
    requested_bank: int
    effective_budget: int
    stake: int
    selected_count: int
    selected_cost: int
    unused_requested_bank: int
    bank_usage_reason: str
    source_archive_path: Path
    source_archive_snapshot_sha256: str
    source_archive_payload_sha256: str
    input_snapshot_sha256: str
    probability_input_sha256: str
    package_sha256: str
    diagnostics_sha256: str
    safety_sha256: str
    quality_v2_config_sha256: str
    selection_context_sha256: str
    result_sha256: str


@dataclass(frozen=True)
class _QualityV2TrainingOutput:
    coupons: tuple[str, ...]
    selected_cost: int
    effective_budget: int
    structural_status: str
    safety_sha256: str
    quality_v2_config_sha256: str
    selection_context_sha256: str
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class _TrainingInputResolution:
    snapshot: FinalInputSnapshot
    archive: RawArchiveRecord


class _ImmutableInputClient:
    def drawing_info(self, _drawing_id: int) -> Mapping[str, object]:
        raise AssertionError("training quality-v2 execution must not use the network")


def ensure_scheduler_training_package(
    plan: SchedulerPlan,
    *,
    morning_record_path: str | Path,
    input_cache_dir: str | Path,
    generated_at: datetime,
) -> SchedulerTrainingPackageResult:
    """Create or reuse one immutable, non-actionable quality-v2 package."""

    verified_plan = _verified_persisted_plan(plan)
    generated = _utc(generated_at, "generated_at")
    if generated >= verified_plan.ended_at:
        raise ValueError("training package must be generated before drawing deadline")
    root = verified_plan.output_dir / TRAINING_PACKAGE_ROOT
    _ensure_output_directory(verified_plan.output_dir, root)
    lock_path = root / ".training-package.lock"
    with scheduler_lock(lock_path):
        _require_output_directory(verified_plan.output_dir, root)
        result_path = root / TRAINING_PACKAGE_RESULT_FILENAME
        input_resolution = _ensure_training_input(
            verified_plan,
            morning_record_path=morning_record_path,
            input_cache_dir=input_cache_dir,
            generated_at=generated,
        )
        if result_path.exists():
            existing = load_scheduler_training_package(verified_plan)
            if (
                existing.source_archive_snapshot_sha256
                != input_resolution.archive.snapshot_sha256
                or existing.source_archive_payload_sha256
                != input_resolution.archive.payload_sha256
                or existing.input_snapshot_sha256
                != input_resolution.snapshot.snapshot_sha256
            ):
                raise ValueError(
                    "existing training package source archive binding mismatch"
                )
            return existing

        snapshot = input_resolution.snapshot
        output = _run_quality_v2_pipeline(verified_plan, snapshot)
        selected_count = len(output.coupons)
        selected_cost = output.selected_cost
        if selected_count <= 0 or selected_cost != selected_count * verified_plan.stake:
            raise ValueError("quality-v2 training package cost is inconsistent")
        if not selected_cost <= output.effective_budget <= verified_plan.requested_bank:
            raise ValueError("quality-v2 training package exceeds its bound budget")

        paper_bytes = render_paper_package(
            output.coupons,
            stake=verified_plan.stake,
        )
        validate_paper_package(
            paper_bytes,
            stake=verified_plan.stake,
            expected_coupons=output.coupons,
            expected_count=selected_count,
            expected_cost=selected_cost,
        )
        diagnostics_bytes = _canonical(output.diagnostics) + b"\n"
        package_sha256 = _sha256(paper_bytes)
        diagnostics_sha256 = _sha256(diagnostics_bytes)
        checkpoint_id = f"{snapshot.snapshot_sha256[:12]}-{package_sha256[:12]}"
        checkpoint = root / "checkpoints" / checkpoint_id
        paper_path = checkpoint / TRAINING_PAPER_FILENAME
        diagnostics_path = checkpoint / TRAINING_DIAGNOSTICS_FILENAME
        bank_usage_reason = _bank_usage_reason(
            requested_bank=verified_plan.requested_bank,
            effective_budget=output.effective_budget,
            selected_cost=selected_cost,
        )
        payload: dict[str, object] = {
            "schema_version": TRAINING_PACKAGE_SCHEMA_VERSION,
            "status": "ready",
            "mode": TRAINING_MODE,
            "actionable": False,
            "operator_export_allowed": False,
            "automatic_wagering": False,
            "decision": "TRAINING ONLY / DO NOT WAGER",
            "pipeline": TRAINING_PIPELINE,
            "pipeline_contract": (
                "build_open_ev_package+quality_v2_objectives+"
                "safety_reselection+evaluate_package_safety"
            ),
            "structural_status": output.structural_status,
            "plan_id": verified_plan.plan_id,
            "drawing": verified_plan.drawing,
            "drawing_id": _drawing_id(verified_plan),
            "deadline": _timestamp(verified_plan.ended_at),
            "generated_at": _timestamp(generated),
            "input_captured_at": _timestamp(snapshot.captured_at),
            "requested_bank": verified_plan.requested_bank,
            "effective_budget": output.effective_budget,
            "stake": verified_plan.stake,
            "selected_count": selected_count,
            "selected_cost": selected_cost,
            "unused_requested_bank": verified_plan.requested_bank - selected_cost,
            "bank_usage_reason": bank_usage_reason,
            "source_archive_path": str(input_resolution.archive.payload_path),
            "source_archive_snapshot_sha256": (
                input_resolution.archive.snapshot_sha256
            ),
            "source_archive_payload_sha256": (
                input_resolution.archive.payload_sha256
            ),
            "input_snapshot_sha256": snapshot.snapshot_sha256,
            "probability_input_sha256": snapshot.probability_input_sha256,
            "quality_v2_config_sha256": output.quality_v2_config_sha256,
            "selection_context_sha256": output.selection_context_sha256,
            "safety_sha256": output.safety_sha256,
            "package_sha256": package_sha256,
            "diagnostics_sha256": diagnostics_sha256,
            "checkpoint_id": checkpoint_id,
            "input_path": str(snapshot.path),
            "paper_path": str(paper_path),
            "diagnostics_path": str(diagnostics_path),
        }
        payload["result_sha256"] = _result_sha256(payload)

        created: list[Path] = []
        try:
            _write_exclusive_atomic(
                verified_plan.output_dir,
                paper_path,
                paper_bytes,
                mode=0o600,
            )
            created.append(paper_path)
            _write_exclusive_atomic(
                verified_plan.output_dir,
                diagnostics_path,
                diagnostics_bytes,
                mode=0o600,
            )
            created.append(diagnostics_path)
            _write_exclusive_atomic(
                verified_plan.output_dir,
                result_path,
                _canonical(payload) + b"\n",
                mode=0o600,
            )
            created.append(result_path)
        except BaseException:
            for path in reversed(created):
                _unlink_output_path(verified_plan.output_dir, path, missing_ok=True)
            _remove_empty_checkpoint(checkpoint, root=root)
            raise
        return load_scheduler_training_package(verified_plan)


def load_scheduler_training_package(
    plan: SchedulerPlan,
) -> SchedulerTrainingPackageResult:
    """Load and fully validate one scheduler-owned training artifact."""

    verified_plan = _verified_persisted_plan(plan)
    root = verified_plan.output_dir / TRAINING_PACKAGE_ROOT
    _require_output_directory(verified_plan.output_dir, root)
    result_path = root / TRAINING_PACKAGE_RESULT_FILENAME
    payload = _load_json_file(result_path, "training package result")
    if payload.get("schema_version") != TRAINING_PACKAGE_SCHEMA_VERSION:
        raise ValueError("training package schema is unsupported")
    if payload.get("result_sha256") != _result_sha256(payload):
        raise ValueError("training package result integrity mismatch")
    expected_scalars = {
        "status": "ready",
        "mode": TRAINING_MODE,
        "actionable": False,
        "operator_export_allowed": False,
        "automatic_wagering": False,
        "decision": "TRAINING ONLY / DO NOT WAGER",
        "pipeline": TRAINING_PIPELINE,
        "structural_status": "STRUCTURAL_PASS",
        "plan_id": verified_plan.plan_id,
        "drawing": verified_plan.drawing,
        "drawing_id": _drawing_id(verified_plan),
        "deadline": _timestamp(verified_plan.ended_at),
        "requested_bank": verified_plan.requested_bank,
        "stake": verified_plan.stake,
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ValueError(f"training package {field} mismatch")
    generated_at = _parse_timestamp(payload.get("generated_at"), "generated_at")
    input_captured_at = _parse_timestamp(
        payload.get("input_captured_at"),
        "input_captured_at",
    )
    if generated_at >= verified_plan.ended_at:
        raise ValueError("training package was generated after drawing deadline")
    if input_captured_at > generated_at:
        raise ValueError("training package input was captured after generation")

    selected_count = _positive_int(payload.get("selected_count"), "selected_count")
    selected_cost = _positive_int(payload.get("selected_cost"), "selected_cost")
    effective_budget = _positive_int(
        payload.get("effective_budget"),
        "effective_budget",
    )
    unused_requested_bank = _non_negative_int(
        payload.get("unused_requested_bank"),
        "unused_requested_bank",
    )
    if selected_cost != selected_count * verified_plan.stake:
        raise ValueError("training package cost mismatch")
    if not selected_cost <= effective_budget <= verified_plan.requested_bank:
        raise ValueError("training package budget mismatch")
    if unused_requested_bank != verified_plan.requested_bank - selected_cost:
        raise ValueError("training package unused bank mismatch")
    expected_bank_reason = _bank_usage_reason(
        requested_bank=verified_plan.requested_bank,
        effective_budget=effective_budget,
        selected_cost=selected_cost,
    )
    if payload.get("bank_usage_reason") != expected_bank_reason:
        raise ValueError("training package bank usage reason mismatch")

    checkpoint_id = _text(payload.get("checkpoint_id"), "checkpoint_id")
    checkpoint = root / "checkpoints" / checkpoint_id
    source_archive_path = _require_contained_path(
        verified_plan.project_root,
        Path(_text(payload.get("source_archive_path"), "source_archive_path")),
        name="training source archive path",
    )
    archive_record = _load_verified_archive_record(
        verified_plan,
        source_archive_path,
    )
    source_archive_snapshot_sha256 = _sha256_field(
        payload.get("source_archive_snapshot_sha256"),
        "source_archive_snapshot_sha256",
    )
    source_archive_payload_sha256 = _sha256_field(
        payload.get("source_archive_payload_sha256"),
        "source_archive_payload_sha256",
    )
    if (
        archive_record.snapshot_sha256 != source_archive_snapshot_sha256
        or archive_record.payload_sha256 != source_archive_payload_sha256
    ):
        raise ValueError("training package source archive binding mismatch")
    input_path = _bound_path(
        payload.get("input_path"),
        expected=root / "input" / TRAINING_INPUT_FILENAME,
        root=root,
        name="input_path",
    )
    paper_path = _bound_path(
        payload.get("paper_path"),
        expected=checkpoint / TRAINING_PAPER_FILENAME,
        root=root,
        name="paper_path",
    )
    diagnostics_path = _bound_path(
        payload.get("diagnostics_path"),
        expected=checkpoint / TRAINING_DIAGNOSTICS_FILENAME,
        root=root,
        name="diagnostics_path",
    )
    snapshot = load_final_input(input_path, expected_plan=verified_plan)
    if snapshot.captured_at != input_captured_at:
        raise ValueError("training package input captured_at mismatch")
    input_snapshot_sha256 = _sha256_field(
        payload.get("input_snapshot_sha256"),
        "input_snapshot_sha256",
    )
    probability_input_sha256 = _sha256_field(
        payload.get("probability_input_sha256"),
        "probability_input_sha256",
    )
    if (
        snapshot.snapshot_sha256 != input_snapshot_sha256
        or snapshot.probability_input_sha256 != probability_input_sha256
    ):
        raise ValueError("training package input binding mismatch")
    archived_payload = RawArchive(source_archive_path.parent.parent).load(
        archive_record
    )
    if _canonical(archived_payload) != _canonical(dict(snapshot.payload)):
        raise ValueError("training package input differs from its source archive")

    paper_bytes = _read_regular_file(
        paper_path,
        name="training paper package",
        reject_symlink=True,
    )
    diagnostics_bytes = _read_regular_file(
        diagnostics_path,
        name="training quality-v2 diagnostics",
        reject_symlink=True,
    )
    package_sha256 = _sha256_field(payload.get("package_sha256"), "package_sha256")
    diagnostics_sha256 = _sha256_field(
        payload.get("diagnostics_sha256"),
        "diagnostics_sha256",
    )
    if _sha256(paper_bytes) != package_sha256:
        raise ValueError("training paper package integrity mismatch")
    if _sha256(diagnostics_bytes) != diagnostics_sha256:
        raise ValueError("training quality-v2 diagnostics integrity mismatch")
    coupons = _paper_coupons(paper_bytes)
    validate_paper_package(
        paper_bytes,
        stake=verified_plan.stake,
        expected_coupons=coupons,
        expected_count=selected_count,
        expected_cost=selected_cost,
    )

    diagnostics = _decode_json(diagnostics_bytes, "training quality-v2 diagnostics")
    runtime_config = replace(
        verified_plan.quality_v2_ev_config,
        effective_budget=effective_budget,
    )
    expected_quality_hash = quality_v2_config_sha256(runtime_config)
    expected_selection_hash = selection_context_sha256(runtime_config)
    quality_hash = _sha256_field(
        payload.get("quality_v2_config_sha256"),
        "quality_v2_config_sha256",
    )
    selection_hash = _sha256_field(
        payload.get("selection_context_sha256"),
        "selection_context_sha256",
    )
    safety_sha256 = _sha256_field(payload.get("safety_sha256"), "safety_sha256")
    if (
        quality_hash != expected_quality_hash
        or selection_hash != expected_selection_hash
    ):
        raise ValueError("training package quality-v2 configuration mismatch")
    _validate_diagnostics(
        diagnostics,
        plan=verified_plan,
        snapshot=snapshot,
        coupons=coupons,
        selected_cost=selected_cost,
        effective_budget=effective_budget,
        safety_sha256=safety_sha256,
        quality_hash=quality_hash,
        selection_hash=selection_hash,
    )
    return SchedulerTrainingPackageResult(
        result_path=result_path,
        input_path=input_path,
        paper_path=paper_path,
        diagnostics_path=diagnostics_path,
        plan_id=verified_plan.plan_id,
        drawing=verified_plan.drawing,
        drawing_id=_drawing_id(verified_plan),
        deadline=verified_plan.ended_at,
        generated_at=generated_at,
        input_captured_at=input_captured_at,
        mode=TRAINING_MODE,
        actionable=False,
        operator_export_allowed=False,
        automatic_wagering=False,
        pipeline=TRAINING_PIPELINE,
        structural_status="STRUCTURAL_PASS",
        requested_bank=verified_plan.requested_bank,
        effective_budget=effective_budget,
        stake=verified_plan.stake,
        selected_count=selected_count,
        selected_cost=selected_cost,
        unused_requested_bank=unused_requested_bank,
        bank_usage_reason=expected_bank_reason,
        source_archive_path=source_archive_path,
        source_archive_snapshot_sha256=source_archive_snapshot_sha256,
        source_archive_payload_sha256=source_archive_payload_sha256,
        input_snapshot_sha256=input_snapshot_sha256,
        probability_input_sha256=probability_input_sha256,
        package_sha256=package_sha256,
        diagnostics_sha256=diagnostics_sha256,
        safety_sha256=safety_sha256,
        quality_v2_config_sha256=quality_hash,
        selection_context_sha256=selection_hash,
        result_sha256=_sha256_field(payload.get("result_sha256"), "result_sha256"),
    )


def _ensure_training_input(
    plan: SchedulerPlan,
    *,
    morning_record_path: str | Path,
    input_cache_dir: str | Path,
    generated_at: datetime,
) -> _TrainingInputResolution:
    root = plan.output_dir / TRAINING_PACKAGE_ROOT
    input_path = root / "input" / TRAINING_INPUT_FILENAME
    _require_contained_path(plan.output_dir, input_path, name="training input path")

    record_path = _require_contained_path(
        plan.project_root,
        _project_path(plan, morning_record_path),
        name="morning dispatch record",
    )
    record = load_morning_dispatch_record(record_path)
    if record is None:
        raise ValueError("morning dispatch record is missing")
    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("morning dispatch record identity is missing")
    expected_record_fields = {
        "status": "scheduled",
        "plan_id": plan.plan_id,
        "plan_path": str(plan.output_dir / SCHEDULER_PLAN_FILENAME),
    }
    for field, expected in expected_record_fields.items():
        if record.get(field) != expected:
            raise ValueError(f"morning dispatch record {field} mismatch")
    expected_identity = {
        "drawing_id": _drawing_id(plan),
        "drawing_number": plan.drawing,
        "deadline": _timestamp(plan.ended_at),
    }
    for field, expected in expected_identity.items():
        if identity.get(field) != expected:
            raise ValueError(f"morning dispatch record {field} mismatch")
    detail_sha256 = _sha256_field(identity.get("detail_sha256"), "detail_sha256")
    observed_at = _parse_timestamp(record.get("observed_at"), "observed_at")
    if observed_at > generated_at or observed_at >= plan.ended_at:
        raise ValueError("morning dispatch record timestamp is invalid for training")

    raw_root = _require_contained_path(
        plan.project_root,
        _project_path(plan, input_cache_dir),
        name="training raw archive root",
    )
    archive, archived_payload = _resolve_archived_morning_input(
        plan,
        raw_root=raw_root,
        detail_sha256=detail_sha256,
        observed_at=observed_at,
    )
    archive_captured_at = _parse_timestamp(archive.captured_at, "archive captured_at")
    expected_attempt_id = f"morning-training-{archive.snapshot_sha256}"
    if input_path.exists():
        snapshot = load_final_input(input_path, expected_plan=plan)
        if (
            snapshot.attempt_id != expected_attempt_id
            or _canonical(dict(snapshot.payload)) != _canonical(archived_payload)
        ):
            raise ValueError("existing training input source archive binding mismatch")
        return _TrainingInputResolution(snapshot=snapshot, archive=archive)

    _ensure_output_directory(plan.output_dir, input_path.parent)
    persist_final_input(
        archived_payload,
        plan=plan,
        attempt_id=expected_attempt_id,
        captured_at=archive_captured_at,
        destination=input_path,
        timing_override_sha256=None,
    )
    _require_contained_path(plan.output_dir, input_path, name="training input path")
    snapshot = load_final_input(input_path, expected_plan=plan)
    return _TrainingInputResolution(snapshot=snapshot, archive=archive)


def _resolve_archived_morning_input(
    plan: SchedulerPlan,
    *,
    raw_root: Path,
    detail_sha256: str,
    observed_at: datetime,
) -> tuple[RawArchiveRecord, dict[str, Any]]:
    """Resolve the morning payload only from a verified immutable archive.

    ``detail_sha256`` is the canonical payload hash recorded by morning
    dispatch.  The mutable ``drawing_<id>.json`` operational cache is
    intentionally not consulted here: an absent or non-matching archive is a
    hard failure for the scheduler-owned training package.
    """
    archive_root = _require_contained_path(
        plan.project_root,
        raw_root / "archive",
        name="training immutable archive root",
    )
    drawing_dir = _require_contained_path(
        archive_root,
        archive_root / f"drawing_{_drawing_id(plan)}",
        name="training drawing archive",
    )
    if not drawing_dir.is_dir() or drawing_dir.is_symlink():
        raise ValueError("training drawing archive must be a non-symlink directory")
    matches: list[tuple[datetime, RawArchiveRecord, dict[str, Any]]] = []
    metadata_paths = sorted(drawing_dir.glob("*.meta.json"))
    if not metadata_paths:
        raise ValueError("training drawing archive contains no snapshots")
    for metadata_path in metadata_paths:
        record = _load_verified_archive_record(
            plan,
            metadata_path.with_name(
                metadata_path.name.removesuffix(".meta.json") + ".json"
            ),
            expected_archive_root=archive_root,
        )
        captured_at = _parse_timestamp(record.captured_at, "archive captured_at")
        if captured_at > observed_at or captured_at >= plan.ended_at:
            continue
        payload = RawArchive(archive_root).load(record)
        if _sha256(_canonical(payload)) == detail_sha256:
            matches.append((captured_at, record, payload))
    if not matches:
        raise ValueError(
            "no verified immutable archive snapshot matches the morning detail hash"
        )
    latest_captured_at = max(item[0] for item in matches)
    latest = [item for item in matches if item[0] == latest_captured_at]
    if len(latest) != 1:
        raise ValueError("morning detail hash resolves to ambiguous archive snapshots")
    _, record, payload = latest[0]
    return record, payload


def _run_quality_v2_pipeline(
    plan: SchedulerPlan,
    snapshot: FinalInputSnapshot,
) -> _QualityV2TrainingOutput:
    data = snapshot.payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("training input payload data is missing")
    pool_sum = data.get("pool_sum")
    runtime_budget = effective_selection_budget(
        requested_bank=plan.requested_bank,
        pool_sum=pool_sum,  # type: ignore[arg-type]
        stake=plan.stake,
    )
    if runtime_budget < plan.stake:
        raise ValueError("training input effective budget is below one coupon")
    runtime_config: EVConfig = replace(
        plan.quality_v2_ev_config,
        effective_budget=runtime_budget,
    )
    target = parse_target_drawing(snapshot.payload, snapshot.captured_at)
    try:
        cover_14_bk_fill_seed(
            tuple(event.bk_probabilities for event in target.events),
            runtime_budget,
            plan.stake,
            runtime_config.package_exposure_floor_scale,
            runtime_config.package_exposure_floor_exponent,
            runtime_config.package_near_fixed_share,
            runtime_config.package_concentration_headroom_share,
        )
    except CategoryHitSeedInfeasibleError as error:
        if runtime_budget >= plan.requested_bank:
            raise
        capacity = runtime_budget // plan.stake
        raise TrainingPackageDeferred(
            "current pool supports only "
            f"{runtime_budget} RUB / {capacity} coupons; the quality-v2 "
            "training package is deferred until a later pool snapshot"
        ) from error
    plan_path = plan.output_dir / SCHEDULER_PLAN_FILENAME
    provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=snapshot.path,
        probability_input_sha256=snapshot.probability_input_sha256,
        schedule_evidence_ledger_path=plan.schedule_evidence_ledger,
        scheduler_plan_path=plan_path,
        selection_config=runtime_config,
    )
    ev_run = build_open_ev_package(
        client=_ImmutableInputClient(),  # type: ignore[arg-type]
        drawing_id=_drawing_id(plan),
        config=runtime_config,
        payload=snapshot.payload,
        fetched_at=snapshot.captured_at,
        selection_provenance=provenance,
    )
    package = ev_run.package
    diagnostics = package.selection_diagnostics
    safety = ev_run.package_safety
    if (
        package.decision != "NO BET"
        or package.decision_reason != "quality_v2_real_money_release_gate_closed"
        or package.structural_status != "STRUCTURAL_PASS"
        or package.artifact_class != "TRAINING/PAPER"
        or package.coupons
        or package.cost != 0
        or not package.paper_coupons
        or diagnostics is None
        or not diagnostics.constraint_feasible
        or not diagnostics.provenance_complete
        or diagnostics.release_gate_decision != "NO BET"
        or diagnostics.real_money_actionable
        or safety is None
        or safety.decision != "PLAY"
    ):
        raise ValueError("production quality-v2 training pipeline did not pass")
    coupons = tuple(coupon.coupon for coupon in package.paper_coupons)
    if safety.evaluated_coupons != coupons or safety.uploadable_coupons != coupons:
        raise ValueError("quality-v2 safety evidence differs from selected coupons")
    selected_cost = package.paper_cost
    if selected_cost != len(coupons) * plan.stake:
        raise ValueError("quality-v2 paper cost is inconsistent")
    quality_hash = quality_v2_config_sha256(runtime_config)
    runtime_selection_hash = selection_context_sha256(runtime_config)
    if (
        diagnostics.quality_v2_config_sha256 != quality_hash
        or diagnostics.selection_context_sha256 != runtime_selection_hash
        or diagnostics.probability_snapshot_sha256 != snapshot.snapshot_sha256
        or diagnostics.probability_input_sha256 != snapshot.probability_input_sha256
        or diagnostics.schedule_evidence_ledger_sha256
        != plan.schedule_evidence_ledger_sha256
        or diagnostics.schedule_evidence_semantic_hash
        != plan.schedule_evidence_semantic_hash
    ):
        raise ValueError("quality-v2 diagnostics lost immutable provenance")
    diagnostics_payload: dict[str, object] = {
        "schema_version": TRAINING_DIAGNOSTICS_SCHEMA_VERSION,
        "mode": TRAINING_MODE,
        "actionable": False,
        "pipeline": TRAINING_PIPELINE,
        "plan_id": plan.plan_id,
        "input_snapshot_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "requested_bank": plan.requested_bank,
        "effective_budget": ev_run.effective_budget,
        "stake": plan.stake,
        "selected_count": len(coupons),
        "selected_cost": selected_cost,
        "quality_v2": quality_v2_config_payload(runtime_config),
        "quality_v2_config_sha256": quality_hash,
        "selection_context": bound_selection_context(runtime_config),
        "selection_context_sha256": runtime_selection_hash,
        "selection_diagnostics": asdict(diagnostics),
        "package_safety": safety.to_dict(),
        "paper_coupons": [
            {
                "rank": coupon.rank,
                "coupon": coupon.coupon,
                "gross_ev": coupon.gross_ev,
                "net_ev": coupon.net_ev,
            }
            for coupon in package.paper_coupons
        ],
    }
    return _QualityV2TrainingOutput(
        coupons=coupons,
        selected_cost=selected_cost,
        effective_budget=ev_run.effective_budget,
        structural_status=package.structural_status,
        safety_sha256=safety.safety_sha256,
        quality_v2_config_sha256=quality_hash,
        selection_context_sha256=runtime_selection_hash,
        diagnostics=diagnostics_payload,
    )


def _validate_diagnostics(
    diagnostics: Mapping[str, object],
    *,
    plan: SchedulerPlan,
    snapshot: FinalInputSnapshot,
    coupons: tuple[str, ...],
    selected_cost: int,
    effective_budget: int,
    safety_sha256: str,
    quality_hash: str,
    selection_hash: str,
) -> None:
    expected = {
        "schema_version": TRAINING_DIAGNOSTICS_SCHEMA_VERSION,
        "mode": TRAINING_MODE,
        "actionable": False,
        "pipeline": TRAINING_PIPELINE,
        "plan_id": plan.plan_id,
        "input_snapshot_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "requested_bank": plan.requested_bank,
        "effective_budget": effective_budget,
        "stake": plan.stake,
        "selected_count": len(coupons),
        "selected_cost": selected_cost,
        "quality_v2_config_sha256": quality_hash,
        "selection_context_sha256": selection_hash,
    }
    for field, value in expected.items():
        if diagnostics.get(field) != value:
            raise ValueError(f"training diagnostics {field} mismatch")
    runtime_config = replace(
        plan.quality_v2_ev_config,
        effective_budget=effective_budget,
    )
    if diagnostics.get("quality_v2") != quality_v2_config_payload(runtime_config):
        raise ValueError("training diagnostics quality-v2 policy mismatch")
    if diagnostics.get("selection_context") != bound_selection_context(runtime_config):
        raise ValueError("training diagnostics selection context mismatch")
    selection = diagnostics.get("selection_diagnostics")
    if not isinstance(selection, Mapping):
        raise ValueError("training selection diagnostics are missing")
    required_selection = {
        "constraint_feasible": True,
        "provenance_complete": True,
        "probability_snapshot_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "schedule_evidence_ledger_sha256": plan.schedule_evidence_ledger_sha256,
        "schedule_evidence_semantic_hash": plan.schedule_evidence_semantic_hash,
        "quality_v2_config_sha256": quality_hash,
        "selection_context_sha256": selection_hash,
        "release_gate_decision": "NO BET",
        "real_money_actionable": False,
    }
    for field, value in required_selection.items():
        if selection.get(field) != value:
            raise ValueError(f"training selection diagnostics {field} mismatch")
    safety = diagnostics.get("package_safety")
    if not isinstance(safety, Mapping):
        raise ValueError("training package safety evidence is missing")
    if (
        safety.get("decision") != "PLAY"
        or safety.get("safety_sha256") != safety_sha256
        or safety.get("evaluated_coupons") != list(coupons)
        or safety.get("uploadable_coupons") != list(coupons)
    ):
        raise ValueError("training package safety evidence mismatch")
    paper_rows = diagnostics.get("paper_coupons")
    if (
        not isinstance(paper_rows, list)
        or [row.get("coupon") for row in paper_rows if isinstance(row, Mapping)]
        != list(coupons)
    ):
        raise ValueError("training diagnostics coupons mismatch")


def _load_verified_archive_record(
    plan: SchedulerPlan,
    payload_path: Path,
    *,
    expected_archive_root: Path | None = None,
) -> RawArchiveRecord:
    payload = _require_contained_path(
        plan.project_root,
        payload_path,
        name="training archive payload",
    )
    archive_root = _require_contained_path(
        plan.project_root,
        payload.parent.parent,
        name="training immutable archive root",
    )
    if expected_archive_root is not None and archive_root != expected_archive_root:
        raise ValueError("training archive payload is outside the configured archive")
    expected_drawing_dir = archive_root / f"drawing_{_drawing_id(plan)}"
    if payload.parent != expected_drawing_dir:
        raise ValueError("training archive payload drawing directory mismatch")
    metadata_path = payload.with_name(f"{payload.stem}.meta.json")
    metadata = _load_json_file(metadata_path, "training archive metadata")
    if metadata.get("schema_version") != 1:
        raise ValueError("training archive metadata schema is unsupported")
    snapshot_sha256 = _sha256_field(
        metadata.get("snapshot_sha256"),
        "source archive snapshot_sha256",
    )
    if payload.name != f"{snapshot_sha256}.json":
        raise ValueError("training archive payload filename mismatch")
    drawing_id = _positive_int(metadata.get("drawing_id"), "archive drawing_id")
    drawing_number = _positive_int(
        metadata.get("drawing_number"),
        "archive drawing_number",
    )
    if drawing_id != _drawing_id(plan) or drawing_number != plan.drawing:
        raise ValueError("training archive drawing identity mismatch")
    source_endpoint = metadata.get("source_endpoint")
    if source_endpoint is not None and not isinstance(source_endpoint, str):
        raise ValueError("training archive source_endpoint is invalid")
    record = RawArchiveRecord(
        snapshot_sha256=snapshot_sha256,
        payload_sha256=_sha256_field(
            metadata.get("payload_sha256"),
            "source archive payload_sha256",
        ),
        metadata_sha256=_sha256_field(
            metadata.get("metadata_sha256"),
            "source archive metadata_sha256",
        ),
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        captured_at=_text(metadata.get("captured_at"), "archive captured_at"),
        source=_text(metadata.get("source"), "archive source"),
        source_endpoint=source_endpoint,
        lifecycle_status=_text(
            metadata.get("lifecycle_status"),
            "archive lifecycle_status",
        ),
        payload_path=payload,
        metadata_path=metadata_path,
        created=False,
    )
    RawArchive(archive_root).verify(record)
    return record


def _verified_persisted_plan(plan: SchedulerPlan) -> SchedulerPlan:
    if not isinstance(plan, SchedulerPlan):
        raise ValueError("plan must be a SchedulerPlan")
    persisted = load_scheduler_plan(plan.output_dir / SCHEDULER_PLAN_FILENAME)
    if persisted != plan:
        raise ValueError("training package plan differs from persisted scheduler plan")
    return persisted


def _project_path(plan: SchedulerPlan, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else plan.project_root / path


def _drawing_id(plan: SchedulerPlan) -> int:
    if plan.drawing_id is None:
        raise ValueError("training package requires scheduler drawing_id")
    return plan.drawing_id


def _load_json_file(path: Path, name: str) -> dict[str, object]:
    content = _read_regular_file(path, name=name, reject_symlink=True)
    return _decode_json(content, name)


def _decode_json(content: bytes, name: str) -> dict[str, object]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    return payload


def _bound_path(
    value: object,
    *,
    expected: Path,
    root: Path,
    name: str,
) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"training package {name} is invalid")
    path = _require_contained_path(root, Path(value), name=f"training {name}")
    if path != expected.absolute():
        raise ValueError(f"training package {name} escaped its checkpoint")
    return path


def _paper_coupons(content: bytes) -> tuple[str, ...]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("training paper package is not UTF-8") from error
    coupons: list[str] = []
    for line in lines:
        parts = line.split("; ")
        if len(parts) != 16:
            raise ValueError("training paper package row is malformed")
        coupons.append("".join(parts[1:]))
    return tuple(coupons)


def _bank_usage_reason(
    *,
    requested_bank: int,
    effective_budget: int,
    selected_cost: int,
) -> str:
    if selected_cost == requested_bank:
        return "configured_bank_cap_fully_used"
    if effective_budget < requested_bank and selected_cost == effective_budget:
        return (
            "selected_cost_below_configured_bank_cap_because_the_production_"
            "one_percent_pool_self_dilution_limit_reduced_the_effective_budget"
        )
    if selected_cost < effective_budget:
        return (
            "selected_cost_below_effective_budget_because_the_production_"
            "minimum_gross_ev_and_quality_constraints_selected_fewer_coupons"
        )
    return "effective_optimization_budget_is_below_the_configured_bank_cap"


def _remove_empty_checkpoint(path: Path, *, root: Path) -> None:
    current = path
    while current != root and current.is_relative_to(root):
        try:
            _require_output_directory(root, current)
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _result_sha256(payload: Mapping[str, object]) -> str:
    unsigned = dict(payload)
    unsigned.pop("result_sha256", None)
    return _sha256(_canonical(unsigned))


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_field(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"training package {name} must be a lowercase SHA-256")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"training package {name} must be positive")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"training package {name} must be non-negative")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"training package {name} is required")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"training package {name} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"training package {name} is invalid") from error
    return _utc(parsed, name)
