from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import toto_ai.runner.training_package as training_package
from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.cli import app
from toto_ai.collector.lifecycle import RawArchive
from toto_ai.ev.models import RankedCoupon, SafetyAwareSelectionDiagnostics
from toto_ai.ev.package_quality import (
    bound_selection_context,
    quality_v2_config_payload,
    quality_v2_config_sha256,
    selection_context_sha256,
)
from toto_ai.runner.scheduler import (
    SchedulerError,
    build_scheduler_plan,
    prepare_scheduler_artifacts,
)
from toto_ai.runner.training_package import (
    _QualityV2TrainingOutput,
    ensure_scheduler_training_package,
    load_scheduler_training_package,
)

FETCHED_AT = datetime(2032, 4, 4, 6, 30, tzinfo=timezone.utc)
GENERATED_AT = datetime(2032, 4, 4, 7, 0, tzinfo=timezone.utc)
ENDED_AT = datetime(2032, 4, 5, 18, 0, tzinfo=timezone.utc)
COUPONS = (
    "1X21X21X21X21X2",
    "X21X21X21X21X21",
    "21X21X21X21X21X",
    "111XXX222111XXX",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "data": {
            "id": 12054,
            "number": 4982,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": ENDED_AT.isoformat().replace("+00:00", "Z"),
            "pool_sum": 12_000,
            "jackpot": 1_000_000,
            "payments": [],
            "events": [
                {
                    "id": 50_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "championship": "Test League",
                    "sport": "football",
                    "quotes": {
                        "pool_win_1": 50 + order,
                        "pool_draw": 30 + order,
                        "pool_win_2": 20 + order,
                        "bk_win_1": 45 + order,
                        "bk_draw": 30 + order,
                        "bk_win_2": 25 + order,
                    },
                }
                for order in range(15)
            ],
        },
    }


def _plan(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    db = data / "toto.db"
    db.touch()
    aliases = data / "aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4982,
        drawing_id=12054,
        ended_at=ENDED_AT,
        bank=660,
        stake=30,
        output_dir=tmp_path / "reports" / "rehearsal" / "evening-4982",
        project_root=tmp_path,
        db=db,
        aliases=aliases,
    )
    prepare_scheduler_artifacts(plan)
    source_payload = _payload()
    archive = RawArchive(data / "raw" / "archive").archive(
        source_payload,
        captured_at=FETCHED_AT,
        source="test-morning",
        lifecycle_status="active",
        source_endpoint="/drawing-info/12054",
    )
    mutable_payload = _payload()
    mutable_payload["data"]["pool_sum"] = 99_000  # type: ignore[index]
    write_drawing_detail_cache(
        mutable_payload,
        drawing_id=12054,
        cache_dir=data / "raw",
        fetched_at=FETCHED_AT.replace(minute=45),
        source="later-mutable-current",
        allowed_root=tmp_path,
    )
    record_path = data / "scheduler" / "morning-dispatch" / "ready.json"
    record_path.parent.mkdir(parents=True)
    record: dict[str, object] = {
        "schema_version": 1,
        "observed_at": GENERATED_AT.isoformat().replace("+00:00", "Z"),
        "status": "scheduled",
        "plan_id": plan.plan_id,
        "plan_path": str(plan.output_dir / "scheduler-plan.json"),
        "identity": {
            "drawing_id": 12054,
            "drawing_number": 4982,
            "deadline": ENDED_AT.isoformat().replace("+00:00", "Z"),
            "detail_sha256": hashlib.sha256(_canonical(source_payload)).hexdigest(),
        },
    }
    record["record_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    record_path.write_bytes(_canonical(record) + b"\n")
    return plan, record_path, data / "raw", archive


def _fake_output(plan, snapshot) -> _QualityV2TrainingOutput:
    effective_budget = 120
    runtime_config = replace(
        plan.quality_v2_ev_config,
        effective_budget=effective_budget,
    )
    quality_hash = quality_v2_config_sha256(runtime_config)
    selection_hash = selection_context_sha256(runtime_config)
    safety_hash = "a" * 64
    selection = {
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
    safety = {
        "decision": "PLAY",
        "safety_sha256": safety_hash,
        "evaluated_coupons": list(COUPONS),
        "uploadable_coupons": list(COUPONS),
    }
    diagnostics = {
        "schema_version": 1,
        "mode": "TRAINING_PAPER",
        "actionable": False,
        "pipeline": "production_quality_v2_ev",
        "plan_id": plan.plan_id,
        "input_snapshot_sha256": snapshot.snapshot_sha256,
        "probability_input_sha256": snapshot.probability_input_sha256,
        "requested_bank": plan.requested_bank,
        "effective_budget": effective_budget,
        "stake": plan.stake,
        "selected_count": len(COUPONS),
        "selected_cost": len(COUPONS) * plan.stake,
        "quality_v2": quality_v2_config_payload(runtime_config),
        "quality_v2_config_sha256": quality_hash,
        "selection_context": bound_selection_context(runtime_config),
        "selection_context_sha256": selection_hash,
        "selection_diagnostics": selection,
        "package_safety": safety,
        "paper_coupons": [
            {"rank": rank, "coupon": coupon, "gross_ev": 1.2, "net_ev": 0.2}
            for rank, coupon in enumerate(COUPONS, start=1)
        ],
    }
    return _QualityV2TrainingOutput(
        coupons=COUPONS,
        selected_cost=len(COUPONS) * plan.stake,
        effective_budget=effective_budget,
        structural_status="STRUCTURAL_PASS",
        safety_sha256=safety_hash,
        quality_v2_config_sha256=quality_hash,
        selection_context_sha256=selection_hash,
        diagnostics=diagnostics,
    )


def _ensure(monkeypatch, plan, record_path, cache_dir):
    monkeypatch.setattr(training_package, "_run_quality_v2_pipeline", _fake_output)
    return ensure_scheduler_training_package(
        plan,
        morning_record_path=record_path,
        input_cache_dir=cache_dir,
        generated_at=GENERATED_AT,
    )


def test_training_package_is_quality_v2_plan_bound_non_actionable_and_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, record_path, cache_dir, archive = _plan(tmp_path)
    state_path = plan.output_dir / "scheduler-state.json"
    state_path.write_text('{"revision":0}\n', encoding="utf-8")
    state_before = state_path.read_bytes()

    first = _ensure(monkeypatch, plan, record_path, cache_dir)
    result_before = first.result_path.read_bytes()
    package_before = first.paper_path.read_bytes()
    second = ensure_scheduler_training_package(
        plan,
        morning_record_path=record_path,
        input_cache_dir=cache_dir,
        generated_at=GENERATED_AT.replace(hour=8),
    )

    assert second == first
    assert load_scheduler_training_package(plan) == first
    assert first.pipeline == "production_quality_v2_ev"
    assert first.structural_status == "STRUCTURAL_PASS"
    assert first.mode == "TRAINING_PAPER"
    assert first.actionable is False
    assert first.operator_export_allowed is False
    assert first.automatic_wagering is False
    assert first.plan_id == plan.plan_id
    assert first.drawing_id == 12054
    assert first.drawing == 4982
    assert first.requested_bank == 660
    assert first.effective_budget == 120
    assert first.selected_count == 4
    assert first.selected_cost == 120
    assert first.unused_requested_bank == 540
    assert "one_percent_pool_self_dilution_limit" in first.bank_usage_reason
    assert first.input_path.name == "final-input.json"
    assert first.source_archive_path == archive.payload_path
    assert first.source_archive_snapshot_sha256 == archive.snapshot_sha256
    assert first.source_archive_payload_sha256 == archive.payload_sha256
    assert first.diagnostics_path.name == "training-quality-v2.json"
    assert first.result_path.read_bytes() == result_before
    assert first.paper_path.read_bytes() == package_before
    assert state_path.read_bytes() == state_before
    assert not (plan.output_dir / "operator-result.json").exists()
    assert not tuple(plan.output_dir.rglob(".bet-ready"))
    assert not tuple(plan.output_dir.rglob(".no-bet"))


def test_quality_v2_training_uses_production_pipeline_and_runtime_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, record_path, cache_dir, _archive = _plan(tmp_path)
    input_resolution = training_package._ensure_training_input(
        plan,
        morning_record_path=record_path,
        input_cache_dir=cache_dir,
        generated_at=GENERATED_AT,
    )
    snapshot = input_resolution.snapshot
    runtime_config = replace(plan.quality_v2_ev_config, effective_budget=120)
    quality_hash = quality_v2_config_sha256(runtime_config)
    selection_hash = selection_context_sha256(runtime_config)
    diagnostics = SafetyAwareSelectionDiagnostics(
        required_coupon_count=4,
        eligible_candidate_count=100,
        candidate_universe_count=100,
        candidate_universe_exhaustive=False,
        concentration_maximum_count=3,
        pre_exposures=(),
        post_exposures=(),
        material_outcomes_repaired=(),
        replacements=(),
        gross_ev_delta=0.0,
        pre_package_sha256="1" * 64,
        post_package_sha256="2" * 64,
        constraint_feasible=True,
        infeasibility_reasons=(),
        probability_snapshot_sha256=snapshot.snapshot_sha256,
        probability_input_sha256=snapshot.probability_input_sha256,
        schedule_evidence_ledger_sha256=plan.schedule_evidence_ledger_sha256,
        schedule_evidence_semantic_hash=plan.schedule_evidence_semantic_hash,
        provenance_complete=True,
        quality_v2_config_sha256=quality_hash,
        selection_context_sha256=selection_hash,
        release_gate_decision="NO BET",
        real_money_actionable=False,
    )
    ranked = tuple(
        RankedCoupon(rank=index, coupon=coupon, gross_ev=1.2, net_ev=0.2)
        for index, coupon in enumerate(COUPONS, start=1)
    )

    class Safety:
        decision = "PLAY"
        evaluated_coupons = COUPONS
        uploadable_coupons = COUPONS
        safety_sha256 = "a" * 64

        def to_dict(self):
            return {
                "decision": self.decision,
                "evaluated_coupons": list(self.evaluated_coupons),
                "uploadable_coupons": list(self.uploadable_coupons),
                "safety_sha256": self.safety_sha256,
            }

    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            effective_budget=120,
            package_safety=Safety(),
            package=SimpleNamespace(
                decision="NO BET",
                decision_reason="quality_v2_real_money_release_gate_closed",
                structural_status="STRUCTURAL_PASS",
                artifact_class="TRAINING/PAPER",
                coupons=(),
                cost=0,
                paper_coupons=ranked,
                paper_cost=120,
                selection_diagnostics=diagnostics,
            ),
        )

    monkeypatch.setattr(training_package, "build_open_ev_package", build)
    output = training_package._run_quality_v2_pipeline(plan, snapshot)

    assert output.coupons == COUPONS
    assert captured["config"] == runtime_config
    assert captured["payload"] is snapshot.payload
    assert captured["selection_provenance"].selection_context == (
        bound_selection_context(runtime_config)
    )
    assert captured["client"].__class__.__name__ == "_ImmutableInputClient"


def test_resolve_morning_detail_hash_uses_verified_archive_snapshot(
    tmp_path: Path,
) -> None:
    plan, record_path, cache_dir, archive = _plan(tmp_path)
    record = json.loads(record_path.read_text())
    detail_sha256 = record["identity"]["detail_sha256"]

    resolved, payload = training_package._resolve_archived_morning_input(
        plan,
        raw_root=cache_dir,
        detail_sha256=detail_sha256,
        observed_at=GENERATED_AT,
    )

    assert resolved.payload_path == archive.payload_path
    assert resolved.metadata_path == archive.metadata_path
    assert resolved.snapshot_sha256 == archive.snapshot_sha256
    assert resolved.payload_sha256 == archive.payload_sha256
    assert payload == _payload()
    assert payload["data"]["pool_sum"] == 12_000  # type: ignore[index]
    assert json.loads((cache_dir / "drawing_12054.json").read_text())["data"][
        "pool_sum"
    ] == 99_000


def test_resolve_morning_detail_hash_mismatch_does_not_use_mutable_cache(
    tmp_path: Path,
) -> None:
    plan, _record_path, cache_dir, _archive = _plan(tmp_path)
    mutable_payload = json.loads((cache_dir / "drawing_12054.json").read_text())
    mutable_hash = hashlib.sha256(_canonical(mutable_payload)).hexdigest()

    with pytest.raises(ValueError, match="no verified immutable archive snapshot"):
        training_package._resolve_archived_morning_input(
            plan,
            raw_root=cache_dir,
            detail_sha256=mutable_hash,
            observed_at=GENERATED_AT,
        )


def test_training_archive_hash_mismatch_fails_closed_without_state_or_markers(
    tmp_path: Path,
) -> None:
    plan, record_path, cache_dir, _archive = _plan(tmp_path)
    state_path = plan.output_dir / "scheduler-state.json"
    state_path.write_text('{"revision":0}\n', encoding="utf-8")
    state_before = state_path.read_bytes()
    record = json.loads(record_path.read_text())
    record["identity"]["detail_sha256"] = "f" * 64
    record.pop("record_sha256")
    record["record_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    record_path.write_bytes(_canonical(record) + b"\n")

    with pytest.raises(ValueError, match="no verified immutable archive snapshot"):
        ensure_scheduler_training_package(
            plan,
            morning_record_path=record_path,
            input_cache_dir=cache_dir,
            generated_at=GENERATED_AT,
        )

    root = plan.output_dir / "training-package"
    assert state_path.read_bytes() == state_before
    assert not (root / "input" / "final-input.json").exists()
    assert not (root / "training-package-result.json").exists()
    assert not (plan.output_dir / "operator-result.json").exists()
    assert not tuple(plan.output_dir.rglob(".bet-ready"))
    assert not tuple(plan.output_dir.rglob(".no-bet"))


def test_existing_training_package_rechecks_morning_archive_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, record_path, cache_dir, _archive = _plan(tmp_path)
    _ensure(monkeypatch, plan, record_path, cache_dir)
    record = json.loads(record_path.read_text())
    record["identity"]["detail_sha256"] = "f" * 64
    record.pop("record_sha256")
    record["record_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
    record_path.write_bytes(_canonical(record) + b"\n")

    with pytest.raises(ValueError, match="no verified immutable archive snapshot"):
        ensure_scheduler_training_package(
            plan,
            morning_record_path=record_path,
            input_cache_dir=cache_dir,
            generated_at=GENERATED_AT,
        )


def test_training_package_rejects_symlinked_training_root(
    tmp_path: Path,
) -> None:
    plan, record_path, cache_dir, _archive = _plan(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (plan.output_dir / "training-package").symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises(SchedulerError, match="symlink"):
        ensure_scheduler_training_package(
            plan,
            morning_record_path=record_path,
            input_cache_dir=cache_dir,
            generated_at=GENERATED_AT,
        )

    assert not tuple(outside.iterdir())


def test_training_package_rejects_symlinked_checkpoint_ancestor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, record_path, cache_dir, _archive = _plan(tmp_path)
    root = plan.output_dir / "training-package"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "checkpoints").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(training_package, "_run_quality_v2_pipeline", _fake_output)

    with pytest.raises(SchedulerError, match="symlink"):
        ensure_scheduler_training_package(
            plan,
            morning_record_path=record_path,
            input_cache_dir=cache_dir,
            generated_at=GENERATED_AT,
        )

    assert not tuple(outside.iterdir())
    assert not (root / "training-package-result.json").exists()


def test_scheduler_training_package_cli_uses_bound_morning_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan, record_path, cache_dir, archive = _plan(tmp_path)
    monkeypatch.setattr(training_package, "_run_quality_v2_pipeline", _fake_output)

    result = CliRunner().invoke(
        app,
        [
            "scheduler-training-package",
            "--plan",
            str(plan.output_dir / "scheduler-plan.json"),
            "--morning-record",
            str(record_path),
            "--input-cache-dir",
            str(cache_dir),
            "--at",
            "2032-04-04T07:00:00Z",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["mode"] == "TRAINING_PAPER"
    assert payload["actionable"] is False
    assert payload["pipeline"] == "production_quality_v2_ev"
    assert payload["structural_status"] == "STRUCTURAL_PASS"
    assert payload["plan_id"] == plan.plan_id
    assert payload["drawing"] == 4982
    assert payload["requested_bank"] == 660
    assert payload["effective_budget"] == 120
    assert payload["selected_count"] == 4
    assert payload["selected_cost"] == 120
    assert payload["source_archive_path"] == str(archive.payload_path)
    assert payload["source_archive_snapshot_sha256"] == archive.snapshot_sha256
    assert Path(payload["result_path"]).is_file()
    assert Path(payload["input_path"]).is_file()
    assert Path(payload["paper_path"]).is_file()
    assert Path(payload["diagnostics_path"]).is_file()
    assert not (plan.output_dir / "scheduler-state.json").exists()
    assert not (plan.output_dir / "operator-result.json").exists()
