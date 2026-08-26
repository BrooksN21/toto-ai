import copy
import hashlib
import json
import os
import plistlib
import subprocess
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

import toto_ai.runner.scheduler as scheduler
from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from tests.test_package_audit import DRAWING_4952_PROBABILITIES
from toto_ai.db.models import ArchivedPackage, Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.package_quality import (
    EVALUATION_MC_STREAM,
    OPTIMIZATION_MC_STREAM,
    bound_selection_context,
    deterministic_outcome_seed,
    diagnostics_payload_sha256,
    quality_v2_config_payload,
    quality_v2_config_sha256,
    selection_context_sha256,
)
from toto_ai.external_odds.timing_overrides import (
    load_timing_override_catalog,
    timing_override_catalog_sha256,
)
from toto_ai.package.audit import PackageSafetyConfig, evaluate_package_safety
from toto_ai.runner.scheduler import (
    RUNNER_MANIFEST_SCHEMA_VERSION,
    CommandSchedulerPhaseRunner,
    SchedulerError,
    SchedulerIntegrityError,
    SchedulerPhaseContext,
    SchedulerPhaseError,
    SchedulerPhaseResult,
    SchedulerTransientError,
    VirtualSchedulerClock,
    authorize_experimental_manual_release,
    build_prepare_drawing_command,
    build_run_drawing_phase_command,
    build_scheduler_plan,
    clone_scheduler_plan_for_recovery,
    execute_scheduler_plan,
    execute_scheduler_preflight_only,
    execute_scheduler_tick,
    find_prior_bet_ready,
    parse_runner_manifest_phase_result,
    prepare_scheduler_artifacts,
)

UTC = timezone.utc
ENDED_AT = datetime(2030, 1, 2, 12, tzinfo=UTC)
FALLBACK_PACKAGE = b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.05,0.05\n"
FINAL_PACKAGE = b"rank,coupon,gross_ev,net_ev\n1,XXXXXXXXXXXXXXX,1.15,0.15\n"


def _plan(
    tmp_path: Path,
    *,
    timing_overrides: Path | None = None,
    minimum_gross_ev: float = 1.0,
    package_near_fixed_share: float = 0.95,
    package_low_probability_threshold: float = 0.20,
    package_material_probability_threshold: float = 0.20,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    return build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=ENDED_AT,
        bank=4980,
        stake=30,
        minimum_gross_ev=minimum_gross_ev,
        package_near_fixed_share=package_near_fixed_share,
        package_low_probability_threshold=package_low_probability_threshold,
        package_material_probability_threshold=(package_material_probability_threshold),
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
        timing_overrides=timing_overrides,
    )


def test_recovery_plan_clone_preserves_every_semantic_input_except_output_dir(
    tmp_path: Path,
) -> None:
    source = replace(
        _plan(tmp_path),
        reviewed_catalog_hash="c" * 64,
    )

    recovered = clone_scheduler_plan_for_recovery(
        source,
        output_dir=tmp_path / "scheduler-recovery",
    )

    assert recovered.output_dir == (tmp_path / "scheduler-recovery").resolve()
    for field in fields(source):
        if field.name != "output_dir":
            assert getattr(recovered, field.name) == getattr(source, field.name)

    context = SchedulerPhaseContext(
        phase="final",
        plan=recovered,
        run_id="recovery-regression",
        run_dir=tmp_path / "recovery-run",
        work_dir=tmp_path / "recovery-work",
        scheduled_at=recovered.final_at,
        started_at=recovered.final_at,
        atomic_final=True,
        scheduler_phase="final",
    )
    command = build_run_drawing_phase_command(context)
    option = command.index("--expected-reviewed-catalog-hash")
    assert command[option + 1] == "c" * 64


def _atomic_final_payload(plan):
    return {
        "data": {
            "id": plan.drawing_id,
            "number": plan.drawing,
            "status": "active",
            "ended_at": plan.ended_at.isoformat(),
            "events": [
                {
                    "id": 39000 + order,
                    "order": order,
                    "name": f"Home {order} — Away {order}",
                    "championship": "Fixture League",
                    "quotes": {
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }


def test_preflight_only_runs_production_preflight_without_package(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    observed = plan.tls_preflight_at - timedelta(hours=1)
    contexts: list[SchedulerPhaseContext] = []

    def phase_runner(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        contexts.append(context)
        return SchedulerPhaseResult.completed("real preflight passed")

    result = execute_scheduler_preflight_only(
        plan,
        phase_runner=phase_runner,
        now=lambda: observed,
    )

    assert result["status"] == "PASS"
    assert result["package_generation"] is False
    assert result["training"] is False
    assert len(contexts) == 1
    assert contexts[0].phase == "preflight"
    assert contexts[0].scheduler_phase == "tls_preflight"
    persisted = json.loads(Path(str(result["result_path"])).read_text())
    assert persisted == result


def test_preflight_only_rejects_accidental_package_output(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    observed = plan.tls_preflight_at - timedelta(hours=1)

    result = execute_scheduler_preflight_only(
        plan,
        phase_runner=lambda _context: SchedulerPhaseResult(
            reason="unexpected package",
            package_bytes=FALLBACK_PACKAGE,
        ),
        now=lambda: observed,
    )

    assert result["status"] == "FAIL"
    assert "forbidden package output" in str(result["reason"])
    assert result["package_generation"] is False


def test_preflight_only_refuses_to_overlap_first_scheduler_checkpoint(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)

    with pytest.raises(SchedulerPhaseError, match="before the first"):
        execute_scheduler_preflight_only(
            plan,
            phase_runner=lambda _context: SchedulerPhaseResult.completed("unused"),
            now=lambda: plan.tls_preflight_at,
        )


def test_live_target_validation_keeps_cutoff_selected_plan_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    preceding_deadline = plan.ended_at - timedelta(hours=1)

    class Client:
        def drawings(self, name, page):
            assert (name, page) == ("baltbet-main", 1)
            return {
                "data": [
                    {
                        "id": 12000,
                        "number": 5000,
                        "status": "expected",
                        "ended_at": preceding_deadline.isoformat(),
                    },
                    {
                        "id": plan.drawing_id,
                        "number": plan.drawing,
                        "status": "expected",
                        "ended_at": plan.ended_at.isoformat(),
                    },
                ]
            }

        def drawing_info(self, drawing_id):
            assert drawing_id == plan.drawing_id
            return _atomic_final_payload(plan)

    frozen = []
    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(
        scheduler,
        "_freeze_authoritative_drawing",
        lambda target_plan, fingerprint: frozen.append(
            (target_plan.plan_id, fingerprint)
        ),
    )

    scheduler._validate_live_scheduler_target(
        plan,
        preceding_deadline + timedelta(minutes=1),
    )

    assert len(frozen) == 1
    assert frozen[0][0] == plan.plan_id


def test_live_target_validation_rejects_plan_target_missing_from_page(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)

    class Client:
        def drawings(self, name, page):
            assert (name, page) == ("baltbet-main", 1)
            return {
                "data": [
                    {
                        "id": 12000,
                        "number": 5000,
                        "status": "expected",
                        "ended_at": (plan.ended_at - timedelta(hours=1)).isoformat(),
                    }
                ]
            }

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)

    with pytest.raises(SchedulerIntegrityError, match="not uniquely present"):
        scheduler._validate_live_scheduler_target(
            plan,
            plan.tls_preflight_at,
        )


def _play(package: bytes, context: SchedulerPhaseContext):
    selected_count = len(package.decode("utf-8").splitlines()) - 1
    return SchedulerPhaseResult.play(
        package,
        effective_bank=4980,
        selected_count=selected_count,
        selected_cost=selected_count * 30,
        override_sha256=context.override_sha256,
        package_sha256=hashlib.sha256(package).hexdigest(),
    )


def _happy_runner(calls: list[SchedulerPhaseContext]):
    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        calls.append(context)
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preflight ok")
        return _play(
            FALLBACK_PACKAGE if context.phase == "fallback" else FINAL_PACKAGE,
            context,
        )

    return run


def _execute(plan, runner, *, run_id: str = "test-run", clock=None):
    if plan.drawing_id is not None:
        engine = init_db(plan.db)
        with get_session_factory(engine).begin() as session:
            if session.get(Drawing, plan.drawing_id) is None:
                session.add(
                    Drawing(
                        id=plan.drawing_id,
                        number=plan.drawing,
                        name="scheduler-test",
                        status="active",
                        ended_at=plan.ended_at.isoformat(),
                    )
                )
        engine.dispose()
    clock = clock or VirtualSchedulerClock(plan.preflight_at)
    return execute_scheduler_plan(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=clock.sleep,
        run_id=run_id,
    )


def _status(result) -> dict[str, object]:
    return json.loads(result.status_path.read_text(encoding="utf-8"))


def _write_catalog(path: Path, *, suffix: str) -> str:
    payload = {
        "overrides": [
            {
                "schema_version": 1,
                "override_id": f"reviewed-{suffix}",
                "drawing_id": 12001,
                "target_fingerprint": "a" * 64,
                "reviewer": f"reviewer-{suffix}",
                "reviewed_at": "2029-12-30T12:00:00+00:00",
                "source_ref": f"offline-review:{suffix}",
                "events": [
                    {
                        "event_order": 0,
                        "event_id": 70001,
                        "starts_at": "2030-01-02T12:30:00+00:00",
                    }
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    catalog = load_timing_override_catalog(path)
    return timing_override_catalog_sha256(catalog)


def _write_complete_catalog(path: Path) -> str:
    payload = {
        "overrides": [
            {
                "schema_version": 1,
                "override_id": "reviewed-complete",
                "drawing_id": 12001,
                "target_fingerprint": "a" * 64,
                "reviewer": "release-reviewer",
                "reviewed_at": "2030-01-02T11:30:00+00:00",
                "source_ref": "offline-review:complete",
                "events": [
                    {
                        "event_order": order,
                        "event_id": 70001 + order,
                        "starts_at": (
                            datetime(2030, 1, 2, 12, 30, tzinfo=UTC)
                            + timedelta(minutes=5 * order)
                        ).isoformat(),
                    }
                    for order in range(15)
                ],
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return timing_override_catalog_sha256(load_timing_override_catalog(path))


def _manifest_context(
    tmp_path: Path,
    *,
    phase: str = "final",
    timing_overrides: Path | None = None,
    override_sha256: str | None = None,
    minimum_gross_ev: float = 1.0,
    package_material_probability_threshold: float = 0.20,
) -> SchedulerPhaseContext:
    plan = _plan(
        tmp_path,
        timing_overrides=timing_overrides,
        minimum_gross_ev=minimum_gross_ev,
        package_material_probability_threshold=(package_material_probability_threshold),
    )
    run_dir = plan.output_dir / "runs" / "5001" / "manifest-test"
    work_dir = run_dir / "work" / phase
    work_dir.mkdir(parents=True)
    scheduled_at = plan.final_at if phase == "final" else plan.fallback_at
    return SchedulerPhaseContext(
        phase=phase,  # type: ignore[arg-type]
        plan=plan,
        run_id="manifest-test",
        run_dir=run_dir,
        work_dir=work_dir,
        scheduled_at=scheduled_at,
        started_at=scheduled_at,
        override_sha256=override_sha256,
    )


def _valid_runner_manifest(
    context: SchedulerPhaseContext,
) -> dict[str, object]:
    fingerprint = "a" * 64
    coupons = [
        {
            "rank": 1,
            "coupon": "111111111111111",
            "gross_ev": 1.2,
            "net_ev": 0.2,
        },
        {
            "rank": 2,
            "coupon": "XXXXXXXXXXXXXXX",
            "gross_ev": 1.1,
            "net_ev": 0.1,
        },
    ]
    selected_count = len(coupons)
    selected_cost = selected_count * context.plan.stake
    expected_payout = sum(
        float(row["gross_ev"]) * context.plan.stake for row in coupons
    )
    safety = evaluate_package_safety(
        tuple(str(row["coupon"]) for row in coupons),
        ((0.45, 0.45, 0.10),) * 15,
        config=context.plan.package_safety_config,
    ).to_dict()
    selection_diagnostics = {
        "post_package_sha256": hashlib.sha256(
            ",".join(str(row["coupon"]) for row in coupons).encode("utf-8")
        ).hexdigest(),
        "probability_snapshot_sha256": "1" * 64,
        "probability_input_sha256": safety["probability_input_sha256"],
        "schedule_evidence_ledger_sha256": (
            context.plan.schedule_evidence_ledger_sha256
        ),
        "schedule_evidence_semantic_hash": (
            context.plan.schedule_evidence_semantic_hash
        ),
        "provenance_complete": True,
        "monte_carlo_seed_material_sha256": "4" * 64,
        "optimization_monte_carlo_seed": deterministic_outcome_seed(
            seed_material="4" * 64,
            stream=OPTIMIZATION_MC_STREAM,
        ),
        "evaluation_monte_carlo_seed": deterministic_outcome_seed(
            seed_material="4" * 64,
            stream=EVALUATION_MC_STREAM,
        ),
        "optimization_monte_carlo_samples": (
            context.plan.package_optimization_probability_samples
        ),
        "evaluation_monte_carlo_samples": context.plan.package_probability_samples,
        "optimization_monte_carlo_stream": OPTIMIZATION_MC_STREAM,
        "evaluation_monte_carlo_stream": EVALUATION_MC_STREAM,
        "numpy_version": quality_v2_config_payload(context.plan.quality_v2_ev_config)[
            "numpy_version"
        ],
        "quality_v2_config_sha256": quality_v2_config_sha256(
            context.plan.quality_v2_ev_config
        ),
        "selection_context_sha256": selection_context_sha256(
            context.plan.quality_v2_ev_config
        ),
        "release_protocol_version": "quality-v2-paper-only-v1",
        "release_evidence_id": None,
        "release_evidence_sha256": None,
        "release_gate_decision": "NO BET",
        "release_gate_reason": "trusted prospective evidence registry absent",
        "real_money_actionable": False,
        "diagnostics_sha256": "",
    }
    selection_diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(
        selection_diagnostics
    )
    return {
        "schema_version": RUNNER_MANIFEST_SCHEMA_VERSION,
        "run_id": "local-runner-fixture",
        "command_status": "success",
        "decision": "NO BET",
        "terminal_reason": "quality-v2 paper-only release gate",
        "target": {
            "drawing_id": context.plan.drawing_id,
            "drawing_number": context.plan.drawing,
            "deadline": context.plan.ended_at.isoformat().replace("+00:00", "Z"),
            "preflight_fingerprint": fingerprint,
            "final_fingerprint": fingerprint,
        },
        "config": {
            "bank": context.plan.requested_bank,
            "stake": context.plan.stake,
            "mode": "playable",
            "final_lead_minutes": scheduler._runner_final_lead_minutes(context),
            "safety_stop_minutes": scheduler._runner_safety_stop_minutes(context),
            "provider": context.plan.provider,
            "quality_v2": quality_v2_config_payload(context.plan.quality_v2_ev_config),
            "selection_context": bound_selection_context(
                context.plan.quality_v2_ev_config
            ),
            "selection_context_sha256": selection_context_sha256(
                context.plan.quality_v2_ev_config
            ),
        },
        "timeline": {
            "preflight_at": "2030-01-02T11:15:00Z",
            "final_started_at": "2030-01-02T11:45:00Z",
            "collection_finished_at": "2030-01-02T11:46:00Z",
            "timing_finished_at": "2030-01-02T11:47:00Z",
            "audit_finished_at": "2030-01-02T11:48:00Z",
            "ev_finished_at": "2030-01-02T11:49:00Z",
            "finished_at": "2030-01-02T11:49:00Z",
            "elapsed_seconds": 1.0,
        },
        "collection": {
            "final_collection_id": "c" * 64,
            "collection_ids": ["c" * 64],
            "pass_count": 1,
            "base_pass_count": 1,
            "expansion_pass_count": 0,
            "expanded": False,
            "final_horizon_days": 2,
            "stop_reason": "no_retryable_fallbacks",
            "total_requests": 5,
            "total_cache_hits": 0,
            "requested_schedule_date_count": 2,
            "successful_schedule_date_count": 2,
            "failed_schedule_date_count": 0,
            "elapsed_seconds": 1.0,
            "pinned_revalidation": asdict(
                ready_pinned_revalidation(context.started_at)
            ),
        },
        "eligibility": {
            "status": "playable",
            "reason": "all starts are playable",
            "target_fingerprint": fingerprint,
            "fingerprint_match": True,
            "span_days": 1,
            "missing_event_orders": [],
            "totobrief_count": 15,
            "provider_count": 0,
            "operator_override_count": 0,
            "earliest_start": "2030-01-02T12:30:00Z",
            "latest_start": "2030-01-02T14:30:00Z",
            "effective": {
                "status": "playable",
                "reason": "all starts are playable",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "raw": {
                "status": "playable",
                "reason": "all starts are playable",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "override": None,
        },
        "coverage": {
            "gate_decision": "PENDING",
            "gate_reasons": ["prospective sample is incomplete"],
            "drawings": 1,
            "events": 15,
            "unique_match_rate": 0.8,
            "consensus_rate": 0.7,
            "ambiguous_matches": 0,
            "explicit_dispositions": 15,
            "operational_failures": 0,
        },
        "ev": {
            "computed": True,
            "requested_bank": context.plan.requested_bank,
            "effective_budget": selected_cost,
            "selected_cost": 0,
            "unused_requested_bank": context.plan.requested_bank,
            "input_fetched_at": "2030-01-02T11:45:00Z",
            "minimum_gross_ev": context.plan.minimum_gross_ev,
            "prize_fund_factor": 1.0,
            "possible_winnings_source": "pool_sum proxy",
            "jackpot_source": "totobrief payload",
            "self_dilution_ratio": 0.001,
            "model_supported": True,
            "model_warning": None,
            "package_safety": safety,
            "selection_diagnostics": selection_diagnostics,
            "package": {
                "decision": "NO BET",
                "decision_reason": "quality_v2_real_money_release_gate_closed",
                "coupons": [],
                "selected_count": 0,
                "cost": 0,
                "unused_bank": context.plan.requested_bank,
                "expected_payout": 0.0,
                "modeled_roi": None,
                "derived_brief": [],
                "structural_status": "STRUCTURAL_PASS",
                "artifact_class": "TRAINING/PAPER",
                "paper_coupons": coupons,
                "paper_selected_count": selected_count,
                "paper_cost": selected_cost,
                "paper_expected_payout": expected_payout,
                "paper_modeled_roi": expected_payout / selected_cost - 1.0,
                "paper_derived_brief": ["1X"] * 15,
            },
            "sensitivity": [],
        },
        "report_links": {"external": [], "ev": []},
        "replay": None,
        "final_input": {
            "path": "final-input.json",
            "captured_at": "2030-01-02T11:40:00Z",
            "snapshot_sha256": "1" * 64,
            "detail_payload_sha256": "2" * 64,
            "probability_input_sha256": "3" * 64,
            "attempt_id": "test",
        },
        "warnings": [],
    }


def _write_runner_manifest(
    context: SchedulerPhaseContext,
    payload: dict[str, object],
    *,
    raw: str | None = None,
) -> Path:
    report_dir = context.work_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "drawing_run_fixture.json"
    path.write_text(
        json.dumps(payload) if raw is None else raw,
        encoding="utf-8",
    )
    return path


def _unsafe_4952_no_bet_manifest(
    context: SchedulerPhaseContext,
) -> dict[str, object]:
    payload = _valid_runner_manifest(context)
    coupons = tuple(
        (Path(__file__).parent / "fixtures" / "drawing_4952_coupons.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    safety = evaluate_package_safety(
        coupons,
        DRAWING_4952_PROBABILITIES,
        config=PackageSafetyConfig(),
    )
    assert safety.decision == "NO BET"
    payload["decision"] = "NO BET"
    payload["terminal_reason"] = "package safety rejected archived 4952 package"
    ev = payload["ev"]
    ev["package_safety"] = safety.to_dict()
    ev["selection_diagnostics"] = None
    ev["selected_cost"] = 0
    ev["unused_requested_bank"] = context.plan.requested_bank
    package = ev["package"]
    package.update(
        {
            "decision": "NO BET",
            "decision_reason": "package_safety:extreme_concentration",
            "coupons": [],
            "selected_count": 0,
            "cost": 0,
            "unused_bank": context.plan.requested_bank,
            "expected_payout": 0.0,
            "modeled_roi": None,
            "derived_brief": [],
            "structural_status": "STRUCTURAL_FAIL",
            "artifact_class": "NONE",
            "paper_coupons": [],
            "paper_selected_count": 0,
            "paper_cost": 0,
            "paper_expected_payout": 0.0,
            "paper_modeled_roi": None,
            "paper_derived_brief": [],
        }
    )
    return payload


def _passing_safety_no_bet_manifest(
    context: SchedulerPhaseContext,
    *,
    terminal_reason: str,
) -> dict[str, object]:
    payload = _valid_runner_manifest(context)
    payload["decision"] = "NO BET"
    payload["terminal_reason"] = terminal_reason
    ev = payload["ev"]
    ev["selection_diagnostics"] = None
    ev["selected_cost"] = 0
    ev["unused_requested_bank"] = context.plan.requested_bank
    package = ev["package"]
    package.update(
        {
            "decision": "NO BET",
            "decision_reason": terminal_reason,
            "coupons": [],
            "selected_count": 0,
            "cost": 0,
            "unused_bank": context.plan.requested_bank,
            "expected_payout": 0.0,
            "modeled_roi": None,
            "derived_brief": [],
            "structural_status": "NOT_EVALUATED",
            "artifact_class": "NONE",
            "paper_coupons": [],
            "paper_selected_count": 0,
            "paper_cost": 0,
            "paper_expected_payout": 0.0,
            "paper_modeled_roi": None,
            "paper_derived_brief": [],
        }
    )
    return payload


def test_structurally_playable_phase_is_forced_to_paper_only_no_bet(tmp_path: Path):
    plan = _plan(tmp_path)
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls))

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert result.package_sha256 is None
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / "package-archive.json").exists()
    assert not (result.run_dir / ".success").exists()
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / ".failed").exists()

    status = _status(result)
    assert status["drawing"] == 5001
    assert status["run_id"] == "test-run"
    assert status["decision"] == "NO BET"
    assert status["requested_bank"] == 4980
    assert status["effective_bank"] is None
    assert status["package_path"] is None
    assert status["package_sha256"] is None
    assert status["selected_snapshot"] is None
    assert status["published_at"] is None
    assert tuple(context.phase for context in calls) == (
        "preflight",
        "fallback",
        "final",
    )
    paper = scheduler.load_paper_package(plan)
    assert paper.decision == "NO BET"
    assert paper.actionable is False
    assert paper.count == 0
    assert paper.cost == 0
    assert paper.source_package_path is None
    assert paper.paper_path is None
    post_draw = json.loads(
        (plan.output_dir / "post-draw" / f"post-draw-{plan.drawing_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert post_draw["package_binding"]["kind"] == "package_free_no_bet"


def test_loaded_evening_scheduler_installs_bound_post_draw_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _plan(tmp_path)
    installed: list[tuple[Path, Path]] = []

    monkeypatch.setattr(scheduler, "_scheduler_launch_agent_is_loaded", lambda _p: True)

    def install(plan_path, plist_path):
        installed.append((Path(plan_path), Path(plist_path)))
        return {
            "label": f"com.toto-ai.post-draw-{plan.drawing_id}",
            "installed_path": str(tmp_path / "installed.plist"),
            "installed_verified": True,
            "loaded_verified": True,
            "active": True,
        }

    monkeypatch.setattr(
        "toto_ai.operations.finished_draw.install_post_draw_launch_agent",
        install,
    )

    result = _execute(plan, _happy_runner([]), run_id="post-draw-activation")

    assert result.outcome == "no-bet"
    assert len(installed) == 1
    post_draw = json.loads(installed[0][0].read_text(encoding="utf-8"))
    assert post_draw["automation_installation"] is True
    activation = json.loads(
        (plan.output_dir / "post-draw" / "activation-status.json").read_text(
            encoding="utf-8"
        )
    )
    assert activation["active"] is True
    assert activation["automatic_wagering"] is False


def test_final_exception_never_promotes_diagnostic_fallback(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        raise RuntimeError("final computation failed")

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert result.package_path is None
    assert not (result.run_dir / "package.csv").exists()
    assert result.marker_path.name == ".failed"
    assert result.marker_path.is_file()
    paper = scheduler.load_paper_package(plan)
    assert paper.decision == "NO BET"
    assert paper.actionable is False
    assert paper.count == 0
    assert paper.cost == 0
    assert paper.source_package_path is None
    assert paper.paper_path is None


def test_post_draw_generation_error_never_changes_primary_terminal_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _plan(tmp_path)

    def fail_post_draw_generation(**_kwargs):
        raise RuntimeError("post-draw database unavailable")

    monkeypatch.setattr(
        "toto_ai.operations.finished_draw.prepare_post_draw_scheduler_artifacts",
        fail_post_draw_generation,
    )

    result = _execute(plan, _happy_runner([]), run_id="advisory-failure")

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / ".failed").exists()
    status = _status(result)
    assert status["outcome"] == "no-bet"
    assert status["decision"] == "NO BET"
    paper = scheduler.load_paper_package(plan)
    assert paper.decision == "NO BET"
    assert paper.count == 0
    assert paper.cost == 0
    generation_error = json.loads(
        (plan.output_dir / "post-draw" / "generation-error.json").read_text(
            encoding="utf-8"
        )
    )
    assert generation_error["drawing"] == plan.drawing
    assert generation_error["drawing_id"] == plan.drawing_id
    assert generation_error["automatic_wagering"] is False
    assert "post-draw database unavailable" in generation_error["error"]


def test_archive_failure_is_terminal_failed_without_bet_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _plan(tmp_path)
    monkeypatch.setattr(
        scheduler,
        "import_prebet_package_manifest",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("archive database unavailable")
        ),
    )

    result = _execute(plan, _happy_runner([]), run_id="archive-failed")

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert result.marker_path.name == ".no-bet"
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / "package-archive.json").exists()


def test_deadline_crossed_during_durable_archive_is_zero_cost_no_bet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _plan(tmp_path)
    clock = VirtualSchedulerClock(plan.preflight_at)
    original_import = scheduler.import_prebet_package_manifest

    def import_then_cross_deadline(*args, **kwargs):
        archived = original_import(*args, **kwargs)
        clock.sleep(1)
        return archived

    monkeypatch.setattr(
        scheduler,
        "import_prebet_package_manifest",
        import_then_cross_deadline,
    )

    result = _execute(
        plan,
        _happy_runner([]),
        run_id="archive-crossed-deadline",
        clock=clock,
    )

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()
    assert result.marker_path == result.run_dir / ".no-bet"
    assert result.marker_path.is_file()
    assert result.package_path is None
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / "package-archive.json").exists()
    engine = init_db(plan.db)
    with get_session_factory(engine)() as session:
        archived = session.scalar(select(ArchivedPackage))
        assert archived is None
    engine.dispose()


def test_bet_ready_marker_crossing_hard_t10_becomes_zero_cost_no_bet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _plan(tmp_path)
    clock = VirtualSchedulerClock(plan.preflight_at)
    original_validate = scheduler._validate_status_file
    advanced = False

    def validate_then_cross_deadline(*args, **kwargs):
        nonlocal advanced
        original_validate(*args, **kwargs)
        status = args[2]
        if not advanced and status.get("outcome") == "bet-ready":
            advanced = True
            clock.sleep(1)

    monkeypatch.setattr(
        scheduler,
        "_validate_status_file",
        validate_then_cross_deadline,
    )

    result = _execute(
        plan,
        _happy_runner([]),
        run_id="marker-crossed-deadline",
        clock=clock,
    )

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()
    assert result.marker_path == result.run_dir / ".no-bet"
    assert result.marker_path.is_file()
    assert result.package_path is None
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / "package-archive.json").exists()
    engine = init_db(plan.db)
    with get_session_factory(engine)() as session:
        assert session.scalar(select(ArchivedPackage)) is None
    engine.dispose()


def test_legacy_plan_without_internal_drawing_id_cannot_publish(
    tmp_path: Path,
):
    plan = replace(
        _plan(tmp_path),
        drawing_id=None,
        actionable_safety_bound=False,
    )

    result = _execute(plan, _happy_runner([]), run_id="legacy-no-internal-id")

    assert result.outcome == "failed"
    assert result.decision == "FAILED"
    assert result.package_path is None
    assert not (result.run_dir / ".bet-ready").exists()
    status = _status(result)
    assert status["selected_snapshot"] is None
    assert status["phase_timestamps"]["final"]["status"] == "complete"
    assert "internal drawing_id" in status["reason"]


def test_explicit_final_no_bet_never_promotes_diagnostic_fallback(
    tmp_path: Path,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        return SchedulerPhaseResult.no_bet("authoritative final NO BET")

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "snapshots" / "fallback").exists()
    assert "real-money release gate closed" in result.reason


def test_both_safe_packages_absent_is_completed_no_bet(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        return SchedulerPhaseResult.no_bet(f"{context.phase} safely declined")

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / "package.csv").exists()
    assert _status(result)["package_sha256"] is None


def test_unhandled_preflight_exception_is_failed_not_complete(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(_context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        raise RuntimeError("configuration exploded")

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert result.decision == "FAILED"
    assert result.marker_path.name == ".failed"
    assert result.marker_path.is_file()
    assert "configuration exploded" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_final_completion_after_t_minus_10_is_never_bet_ready(tmp_path: Path):
    plan = _plan(tmp_path)
    clock = VirtualSchedulerClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return _play(FALLBACK_PACKAGE, context)
        clock.sleep(10 * 60 + 1)
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "no-bet"
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "snapshots" / "final").exists()
    assert _status(result)["phase_timestamps"]["final"]["status"] == "complete"
    assert not (result.run_dir / "snapshots" / "fallback").exists()


def test_snapshot_package_tampering_fails_closed(tmp_path: Path):
    plan = _plan(tmp_path)
    captured: dict[str, Path] = {}

    class TamperingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at and "run_dir" in captured:
                package = captured["run_dir"] / "snapshots" / "final" / "package.csv"
                if package.exists():
                    package.write_bytes(b"tampered\n")

    clock = TamperingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        captured["run_dir"] = context.run_dir
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "no-bet"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / "package.csv").exists()
    assert not (result.run_dir / ".bet-ready").exists()


def test_override_is_forwarded_and_final_hash_is_pinned_at_t_minus_15(
    tmp_path: Path,
):
    catalog_path = tmp_path / "timing-overrides.json"
    old_hash = _write_catalog(catalog_path, suffix="old")
    plan = _plan(tmp_path, timing_overrides=catalog_path)
    observed: list[SchedulerPhaseContext] = []

    class UpdatingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.final_at:
                _write_catalog(catalog_path, suffix="final")

    clock = UpdatingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        observed.append(context)
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        return _play(
            FALLBACK_PACKAGE if context.phase == "fallback" else FINAL_PACKAGE,
            context,
        )

    result = _execute(plan, run, clock=clock)
    final_hash = timing_override_catalog_sha256(
        load_timing_override_catalog(catalog_path)
    )

    assert result.outcome == "no-bet"
    assert old_hash != final_hash
    assert observed[0].override_sha256 is None
    assert observed[1].override_sha256 == old_hash
    assert observed[2].override_sha256 == final_hash
    assert observed[2].final_inputs_sha256 is not None
    status = _status(result)
    assert status["final_override_sha256"] == final_hash
    assert status["final_inputs_sha256"] == observed[2].final_inputs_sha256

    command = build_run_drawing_phase_command(observed[2])
    override_index = command.index("--timing-overrides")
    assert command[override_index + 1] == str(catalog_path.absolute())
    assert "5001" not in command


def test_override_change_after_final_pin_fails_closed(tmp_path: Path):
    catalog_path = tmp_path / "timing-overrides.json"
    _write_catalog(catalog_path, suffix="initial")
    plan = _plan(tmp_path, timing_overrides=catalog_path)

    class TamperingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at:
                _write_catalog(catalog_path, suffix="tampered")

    clock = TamperingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "no-bet"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_final_input_hash_is_recomputed_at_freeze_and_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    original = scheduler._final_inputs_sha256
    calls: list[str | None] = []

    def tracked(current_plan, override_sha256):
        calls.append(override_sha256)
        return original(current_plan, override_sha256)

    monkeypatch.setattr(scheduler, "_final_inputs_sha256", tracked)

    result = _execute(plan, _happy_runner([]))

    assert result.outcome == "no-bet"
    assert len(calls) >= 1


def test_packages_are_run_scoped_and_existing_scope_is_never_overwritten(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    first = _execute(plan, _happy_runner([]), run_id="run-one")
    assert first.outcome == "no-bet"
    assert first.package_path is None

    second_clock = VirtualSchedulerClock(plan.preflight_at)
    second = execute_scheduler_plan(
        plan,
        phase_runner=_happy_runner([]),
        now=second_clock.now,
        sleep=second_clock.sleep,
        run_id="run-two",
        honor_prior_bet_ready=False,
    )
    assert second.outcome == "no-bet"
    assert second.run_dir != first.run_dir

    collision_plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=ENDED_AT,
        bank=4980,
        output_dir=tmp_path / "collision-scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
    )
    existing_scope = collision_plan.output_dir / "runs" / "5001" / "run-one"
    existing_scope.mkdir(parents=True)
    sentinel = existing_scope / "sentinel"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    collision_clock = VirtualSchedulerClock(collision_plan.preflight_at)
    with pytest.raises(SchedulerError, match="already exists"):
        execute_scheduler_plan(
            collision_plan,
            phase_runner=_happy_runner([]),
            now=collision_clock.now,
            sleep=collision_clock.sleep,
            run_id="run-one",
        )
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"


def test_old_success_no_bet_and_failed_markers_do_not_suppress_retry(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    drawing_root = plan.output_dir / "runs" / "5001"
    for marker in (".success", ".no-bet", ".failed"):
        legacy = drawing_root / marker.removeprefix(".")
        legacy.mkdir(parents=True)
        (legacy / marker).write_text("old\n", encoding="utf-8")
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls), run_id="retry")

    assert result.outcome == "no-bet"
    assert len(calls) == 3
    assert find_prior_bet_ready(plan) is None


def test_paper_only_runs_do_not_create_a_prior_bet_ready_marker(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    first = _execute(plan, _happy_runner([]), run_id="published")
    calls: list[SchedulerPhaseContext] = []
    clock = VirtualSchedulerClock(plan.preflight_at)

    duplicate = execute_scheduler_plan(
        plan,
        phase_runner=_happy_runner(calls),
        now=clock.now,
        sleep=clock.sleep,
        run_id="duplicate",
    )

    assert duplicate.outcome == "no-bet"
    assert len(calls) == 3
    assert find_prior_bet_ready(plan) is None
    assert first.marker_path.is_file()


@pytest.mark.parametrize(
    "ended_at",
    [None, "not-a-date", "2030-01-02T12:00:00", "2030-01-02T15:00:00+03:00"],
)
def test_null_or_invalid_ended_at_fails_before_scheduling(
    tmp_path: Path, ended_at: object
):
    with pytest.raises(ValueError, match="ended_at"):
        build_scheduler_plan(
            drawing=5001,
            ended_at=ended_at,  # type: ignore[arg-type]
            bank=4980,
            output_dir=tmp_path / "scheduler",
        )
    assert not (tmp_path / "scheduler").exists()


@pytest.mark.parametrize("minimum_gross_ev", [float("nan"), float("inf")])
def test_scheduler_plan_rejects_non_finite_minimum_gross_ev(
    tmp_path: Path,
    minimum_gross_ev: float,
):
    with pytest.raises(ValueError, match="minimum_gross_ev must be finite"):
        _plan(tmp_path, minimum_gross_ev=minimum_gross_ev)

    assert not (tmp_path / "scheduler").exists()


def test_exact_offsets_and_phase_start_times_are_operational_cutoff_anchored(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    assert plan.tls_preflight_at == ENDED_AT - timedelta(minutes=120)
    assert plan.api_preflight_at == ENDED_AT - timedelta(minutes=90)
    assert plan.freshness_preflight_at == ENDED_AT - timedelta(minutes=60)
    assert plan.preflight_at == ENDED_AT - timedelta(minutes=45)
    assert plan.fallback_at == ENDED_AT - timedelta(minutes=30)
    assert plan.final_at == ENDED_AT - timedelta(minutes=20)
    assert plan.retry_at == ENDED_AT - timedelta(minutes=16)
    assert plan.freeze_at == ENDED_AT - timedelta(minutes=10)
    calls: list[SchedulerPhaseContext] = []

    result = _execute(plan, _happy_runner(calls))

    assert [context.started_at for context in calls] == [
        plan.preflight_at,
        plan.fallback_at,
        plan.final_at,
    ]
    phases = _status(result)["phase_timestamps"]
    assert phases["freeze"]["started_at"] == "2030-01-02T11:50:00Z"
    assert _status(result)["deadlines"] == {
        "ended_at": "2030-01-02T12:00:00Z",
        "operational_cutoff": "2030-01-02T12:00:00Z",
        "t_minus_120": "2030-01-02T10:00:00Z",
        "t_minus_90": "2030-01-02T10:30:00Z",
        "t_minus_60": "2030-01-02T11:00:00Z",
        "t_minus_10": "2030-01-02T11:50:00Z",
        "t_minus_16": "2030-01-02T11:44:00Z",
        "t_minus_20": "2030-01-02T11:40:00Z",
        "t_minus_30": "2030-01-02T11:30:00Z",
        "t_minus_45": "2030-01-02T11:15:00Z",
    }


def test_freshness_checkpoint_has_bounded_end_to_end_canary_window(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    observed = plan.freshness_preflight_at
    contexts: list[SchedulerPhaseContext] = []

    def phase_runner(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        contexts.append(context)
        return SchedulerPhaseResult.completed("canary completed")

    result = execute_scheduler_tick(
        plan,
        phase_runner=phase_runner,
        now=lambda: observed,
        sleep=lambda _seconds: None,
    )

    assert result is None
    assert len(contexts) == 1
    assert contexts[0].scheduler_phase == "freshness_preflight"
    assert contexts[0].phase == "preflight"
    assert contexts[0].phase_deadline == plan.preflight_at - timedelta(seconds=5)


def test_generated_artifacts_are_credential_free_generic_and_exclusive(
    tmp_path: Path,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5003,
        drawing_id=12003,
        ended_at=ENDED_AT,
        bank=5010,
        output_dir=tmp_path / "generated",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )

    artifacts = prepare_scheduler_artifacts(plan)
    plan_text = artifacts.plan_path.read_text(encoding="utf-8")
    wrapper_text = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist_text = artifacts.launch_agent_path.read_text(encoding="utf-8")
    combined = plan_text + wrapper_text + plist_text

    assert "API_SPORTS_KEY" not in combined
    assert "api-sports-test-secret" not in combined
    assert "4947" not in combined
    assert "4950" not in combined
    assert "--drawing" not in wrapper_text
    assert "scheduler-execute" in wrapper_text
    assert json.loads(plan_text)["config"]["minimum_gross_ev"] == 1.0
    assert os.stat(artifacts.wrapper_path).st_mode & 0o111
    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    assert launch_agent["Label"].startswith("com.totoai.production-scheduler.")
    assert len(launch_agent["StartCalendarInterval"]) == 8
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        prepare_scheduler_artifacts(plan)


def test_generated_artifacts_quote_paths_without_shell_injection(
    tmp_path: Path,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5004,
        drawing_id=12004,
        ended_at=ENDED_AT,
        bank=4980,
        output_dir=tmp_path / "generated safe;$(touch escaped)",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )

    artifacts = prepare_scheduler_artifacts(plan)

    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    subprocess.run(
        [str(artifacts.wrapper_path), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert not (tmp_path / "injected").exists()
    assert not (tmp_path / "escaped").exists()


def test_generated_artifacts_reject_shell_script_executable(tmp_path: Path):
    executable = tmp_path / "python-probe"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    plan = _plan(tmp_path)

    with pytest.raises(ValueError, match="current interpreter"):
        prepare_scheduler_artifacts(plan, python_command=executable)

    assert not plan.output_dir.exists()


@pytest.mark.parametrize(
    "python_command",
    ["python", "python; touch unsafe", "", "relative/path"],
)
def test_generated_artifacts_reject_unsafe_python_command(
    tmp_path: Path,
    python_command: str,
):
    plan = _plan(tmp_path)

    with pytest.raises(ValueError, match="python executable"):
        prepare_scheduler_artifacts(plan, python_command=python_command)

    assert not plan.output_dir.exists()


def test_phase_command_rejects_shell_command_instead_of_executable(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)

    with pytest.raises(ValueError, match="absolute path"):
        build_run_drawing_phase_command(
            context,
            python_executable="python -c 'raise SystemExit()'",
        )


def test_command_phase_preflight_validates_data_before_subprocess(tmp_path: Path):
    plan = _plan(tmp_path)
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="preflight",
        run_dir=tmp_path / "run",
        work_dir=tmp_path / "run" / "work" / "preflight",
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"}
    )

    with pytest.raises(SchedulerPhaseError, match="database"):
        runner(context)


def test_command_phase_preflight_runs_mandatory_prepare_drawing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    init_db(plan.db).dispose()
    plan.aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="preflight-ready",
        run_dir=plan.output_dir / "run",
        work_dir=plan.output_dir / "run" / "work" / "preflight",
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    calls = []

    def completed(command, **kwargs):
        calls.append((tuple(command), kwargs))
        return subprocess.CompletedProcess(
            command, 0, stdout='{"status":"ready"}', stderr=""
        )

    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    runner = CommandSchedulerPhaseRunner(
        environment={
            "API_SPORTS_KEY": "not-persisted",
            "TOTO_LEGACY_NAME_MATCHING": "1",
        },
        target_validator=lambda _plan, _started_at: None,
    )

    result = runner(context)

    assert result.status == "complete"
    assert calls[0][0][3] == "prepare-drawing"
    assert "--open" not in calls[0][0]
    assert calls[0][0][calls[0][0].index("--drawing-id") + 1] == str(
        plan.drawing_id
    )
    assert "TOTO_LEGACY_NAME_MATCHING" not in calls[0][1]["env"]
    assert calls[0][1]["cwd"] == plan.project_root


def test_command_phase_preflight_uses_fresh_post_preparation_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    init_db(plan.db).dispose()
    plan.aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="preflight-fresh-clock",
        run_dir=plan.output_dir / "run",
        work_dir=plan.output_dir / "run" / "work" / "preflight",
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    preparation_completed_at = plan.preflight_at + timedelta(minutes=4)
    validator_observations = []

    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout='{"status":"ready"}', stderr=""
        ),
    )
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"},
        target_validator=lambda _plan, observed: validator_observations.append(
            observed
        ),
        now=lambda: preparation_completed_at,
    )

    result = runner(context)

    assert result.status == "complete"
    assert validator_observations == [preparation_completed_at]


def test_freshness_preflight_runs_full_end_to_end_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    base = _manifest_context(tmp_path, phase="preflight")
    context = replace(
        base,
        scheduler_phase="freshness_preflight",
        scheduled_at=base.plan.freshness_preflight_at,
        started_at=base.plan.freshness_preflight_at,
        phase_deadline=base.plan.preflight_at - timedelta(seconds=5),
    )
    fallback_context = replace(
        context,
        phase="fallback",
        work_dir=context.run_dir / "fallback",
        atomic_final=False,
    )
    calls = []

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == context.plan.drawing_id
            return _atomic_final_payload(context.plan)

    def completed(command, **kwargs):
        calls.append((tuple(command), kwargs))
        _write_runner_manifest(
            fallback_context,
            _valid_runner_manifest(fallback_context),
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"},
        target_validator=lambda _plan, _observed: None,
        now=lambda: context.plan.freshness_preflight_at,
    )
    monkeypatch.setattr(runner, "_preflight", lambda _plan, _work_dir: None)

    result = runner(context)

    assert result.status == "complete"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[command.index("--final-lead-minutes") + 1] == "60"
    assert kwargs["timeout"] == pytest.approx(
        (
            context.phase_deadline - context.plan.freshness_preflight_at
        ).total_seconds()
    )


def test_command_final_subprocess_timeout_preserves_publication_reserve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    assert plan.requested_bank == 4_980
    assert plan.minimum_final_runtime_seconds == 300
    payload = _atomic_final_payload(plan)
    recorded_timeouts = []

    class Clock:
        current = plan.final_at

        def now(self):
            return self.current

        def advance(self, seconds):
            self.current += timedelta(seconds=seconds)

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == plan.drawing_id
            clock.advance(9)
            return payload

    def time_out(command, **kwargs):
        recorded_timeouts.append(kwargs["timeout"])
        expected = (
            plan.publish_deadline
            - timedelta(seconds=plan.publication_reserve_seconds)
            - clock.now()
        ).total_seconds()
        assert kwargs["timeout"] == pytest.approx(expected)
        clock.advance(20)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    clock = Clock()
    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", time_out)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"},
        now=clock.now,
    )

    result = execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=clock.advance,
    )

    assert result is None
    assert len(recorded_timeouts) >= 2
    assert recorded_timeouts == sorted(recorded_timeouts, reverse=True)


def test_command_package_timeout_persists_sanitized_phase_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    context = replace(
        _manifest_context(tmp_path, phase="fallback"),
        scheduler_phase="warmup",
    )
    context = replace(
        context,
        phase_deadline=context.plan.fallback_at - timedelta(seconds=5),
    )
    secret = "timeout-secret-must-not-leak"

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == context.plan.drawing_id
            return _atomic_final_payload(context.plan)

    def time_out(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command,
            kwargs["timeout"],
            output=f"\x1b[31mCollecting fresh API-Sports odds\x1b[0m {secret}\n",
            stderr=b"provider still unavailable\n",
        )

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", time_out)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": secret},
        now=lambda: context.plan.preflight_at,
    )

    with pytest.raises(SchedulerTransientError) as error:
        runner(context)

    message = str(error.value)
    assert "warmup phase timed out" in message
    assert "T-10 cutoff" not in message
    diagnostics = context.work_dir / "run-drawing-timeout-01.json"
    payload = json.loads(diagnostics.read_text(encoding="utf-8"))
    assert payload["scheduler_phase"] == "warmup"
    assert payload["runner_phase"] == "fallback"
    assert payload["deadline"] == context.phase_deadline.isoformat()
    assert payload["configured_timeout_seconds"] > 0
    assert payload["stdout_tail"] == (
        "Collecting fresh API-Sports odds [REDACTED]"
    )
    assert payload["stderr_tail"] == "provider still unavailable"
    assert secret not in diagnostics.read_text(encoding="utf-8")
    assert str(diagnostics) in message


def test_command_final_rechecks_runtime_budget_after_snapshot_capture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    payload = _atomic_final_payload(plan)
    subprocess_calls = []

    class Clock:
        current = plan.retry_at

        def now(self):
            return self.current

        def advance(self, seconds):
            self.current += timedelta(seconds=seconds)

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == plan.drawing_id
            clock.advance(20)
            return payload

    def must_not_start(command, **_kwargs):
        subprocess_calls.append(command)
        raise AssertionError("heavy final subprocess must not start")

    clock = Clock()
    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", must_not_start)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"},
        now=clock.now,
    )

    result = execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=clock.advance,
    )

    assert result is not None
    assert result.outcome == "no-bet"
    assert "insufficient final runtime budget" in result.reason
    assert subprocess_calls == []
    state = json.loads(
        (plan.output_dir / "scheduler-state.json").read_text(encoding="utf-8")
    )
    assert state["phases"]["final"]["status"] == "no_bet"
    assert state["terminal"] == "no_bet"


def test_command_package_phase_reserves_collection_and_optimizer_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    context = replace(
        _manifest_context(tmp_path, phase="fallback"),
        scheduler_phase="refresh",
    )
    deadline = context.plan.final_at - timedelta(seconds=5)
    context = replace(context, phase_deadline=deadline)
    observed = deadline - timedelta(
        seconds=context.plan.minimum_final_runtime_seconds + 29
    )
    subprocess_calls = []

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == context.plan.drawing_id
            return _atomic_final_payload(context.plan)

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda command, **_kwargs: subprocess_calls.append(command),
    )
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"},
        now=lambda: observed,
    )

    with pytest.raises(
        SchedulerTransientError,
        match="insufficient refresh phase runtime budget",
    ):
        runner(context)

    assert subprocess_calls == []


def test_prepare_command_uses_absolute_raw_and_reusable_provider_cache(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    command = build_prepare_drawing_command(
        plan,
        plan.output_dir / "runs" / "one" / "work" / "preflight",
    )

    assert "--open" not in command
    assert command[command.index("--drawing-id") + 1] == str(plan.drawing_id)
    assert command[command.index("--raw-cache-dir") + 1] == str(
        tmp_path / "data" / "raw"
    )
    assert command[command.index("--cache-root") + 1] == str(
        tmp_path / "data" / "external-cache" / "api-sports"
    )
    assert command[command.index("--schedule-evidence-ledger") + 1] == str(
        tmp_path / "data" / "schedule-evidence" / "ledger.json"
    )
    assert (
        command[command.index("--expected-schedule-evidence-sha256") + 1]
        == plan.schedule_evidence_ledger_sha256
    )
    assert (
        command[command.index("--expected-schedule-evidence-semantic-hash") + 1]
        == plan.schedule_evidence_semantic_hash
    )
    assert Path(command[command.index("--raw-cache-dir") + 1]).is_absolute()
    assert Path(command[command.index("--cache-root") + 1]).is_absolute()
    assert Path(command[command.index("--schedule-evidence-ledger") + 1]).is_absolute()


def test_package_phases_keep_run_isolated_cache(tmp_path: Path):
    context = _manifest_context(tmp_path, phase="final")

    command = build_run_drawing_phase_command(context)

    assert command[command.index("--cache-root") + 1] == str(context.work_dir / "cache")
    assert command[command.index("--schedule-evidence-ledger") + 1] == str(
        context.plan.schedule_evidence_ledger
    )
    assert (
        command[command.index("--expected-schedule-evidence-sha256") + 1]
        == context.plan.schedule_evidence_ledger_sha256
    )
    assert (
        command[command.index("--expected-schedule-evidence-semantic-hash") + 1]
        == context.plan.schedule_evidence_semantic_hash
    )
    assert command[command.index("--cache-root") + 1] != str(
        context.plan.project_root / "data" / "external-cache" / "api-sports"
    )
    assert command[command.index("--shared-schedule-cache-root") + 1] == str(
        context.plan.output_dir / "shared-cache" / "api-sports-schedule"
    )


def test_package_subprocess_runs_from_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    context = _manifest_context(tmp_path, phase="final")
    calls = []

    def completed(command, **kwargs):
        calls.append((tuple(command), kwargs))
        _write_runner_manifest(context, _valid_runner_manifest(context))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"}
    )

    result = runner(context)

    assert result.decision == "NO BET"
    assert calls[0][1]["cwd"] == context.plan.project_root


def test_atomic_final_subprocess_retry_reuses_persisted_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    context = replace(
        _manifest_context(tmp_path, phase="final"),
        atomic_final=True,
    )
    detail_calls = 0
    subprocess_calls = 0

    class Client:
        def drawing_info(self, drawing_id):
            nonlocal detail_calls
            detail_calls += 1
            assert drawing_id == context.plan.drawing_id
            return _atomic_final_payload(context.plan)

    def completed(command, **kwargs):
        nonlocal subprocess_calls
        subprocess_calls += 1
        if subprocess_calls == 1:
            return subprocess.CompletedProcess(
                command, 75, stdout="", stderr="temporary provider failure"
            )
        report_dir = context.work_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "drawing_run_retry.json").write_text("{}")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    monkeypatch.setattr(
        scheduler,
        "parse_runner_manifest_phase_result",
        lambda _context, _path: SchedulerPhaseResult.no_bet("safe retry"),
    )
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"}
    )

    with pytest.raises(SchedulerPhaseError, match="temporary provider failure"):
        runner(context)
    result = runner(context)

    assert result.decision == "NO BET"
    assert detail_calls == 1
    assert subprocess_calls == 2
    assert (context.run_dir / "final-input.json").is_file()


def test_fallback_subprocess_binds_snapshot_ledger_and_scheduler_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    context = replace(
        _manifest_context(tmp_path, phase="fallback"),
        scheduler_phase="refresh",
    )
    prepare_scheduler_artifacts(context.plan)
    captured_environment = {}

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == context.plan.drawing_id
            return _atomic_final_payload(context.plan)

    def completed(command, **kwargs):
        captured_environment.update(kwargs["env"])
        _write_runner_manifest(context, _valid_runner_manifest(context))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler, "TotoBriefClient", Client)
    monkeypatch.setattr(scheduler.subprocess, "run", completed)
    runner = CommandSchedulerPhaseRunner(
        environment={"API_SPORTS_KEY": "not-persisted"}
    )

    result = runner(context)

    snapshot = context.run_dir / "final-input.json"
    plan_path = context.plan.output_dir / "scheduler-plan.json"
    assert result.decision == "NO BET"
    assert snapshot.is_file()
    assert captured_environment["TOTO_FINAL_INPUT"] == str(snapshot)
    assert captured_environment["TOTO_SCHEDULER_PLAN"] == str(plan_path)
    manifest_path = context.work_dir / "reports" / "drawing_run_fixture.json"
    assert json.loads(manifest_path.read_text())["schema_version"] == 5


def test_production_manifest_parser_accepts_strict_paper_only_structural_pass(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.effective_bank is None
    assert result.selected_count is None
    assert result.selected_cost is None
    assert result.package_bytes is None


def test_legacy_play_manifest_without_package_safety_fails_closed(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    del payload["ev"]["package_safety"]
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="runner EV payload"):
        parse_runner_manifest_phase_result(context, manifest)


def test_play_manifest_without_selector_provenance_fails_closed(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["ev"]["selection_diagnostics"] = None
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="lacks probability-bound selector diagnostics",
    ):
        parse_runner_manifest_phase_result(context, manifest)


def test_selector_ledger_provenance_mismatch_fails_closed(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    diagnostics = payload["ev"]["selection_diagnostics"]
    diagnostics["schedule_evidence_ledger_sha256"] = "f" * 64
    diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(diagnostics)
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="schedule-evidence provenance mismatch",
    ):
        parse_runner_manifest_phase_result(context, manifest)


def test_structural_play_is_no_bet_while_release_gate_is_paper_only(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    diagnostics = payload["ev"]["selection_diagnostics"]
    diagnostics["release_gate_reason"] = "prospective thresholds not met"
    diagnostics["real_money_actionable"] = False
    diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(diagnostics)
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.package_bytes is None
    assert result.reason == "quality-v2 paper-only release gate"


def test_explicit_plan_bound_experimental_authorization_enables_fresh_final(
    tmp_path: Path,
):
    context = replace(_manifest_context(tmp_path), scheduler_phase="final")
    authorize_experimental_manual_release(
        context.plan,
        acknowledged=True,
        now=datetime(2029, 12, 31, 12, tzinfo=UTC),
    )
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "PLAY"
    assert result.package_bytes is not None
    assert result.selected_count == 2
    assert result.selected_cost == 60
    assert "profitability is unproven" in result.reason


def test_experimental_authorization_never_promotes_warmup_package(tmp_path: Path):
    context = replace(
        _manifest_context(tmp_path, phase="fallback"),
        scheduler_phase="warmup",
    )
    authorize_experimental_manual_release(
        context.plan,
        acknowledged=True,
        now=datetime(2029, 12, 31, 12, tzinfo=UTC),
    )
    payload = _valid_runner_manifest(context)
    payload["config"]["final_lead_minutes"] = 45
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.package_bytes is not None


def test_tampered_experimental_authorization_fails_closed(tmp_path: Path):
    context = replace(_manifest_context(tmp_path), scheduler_phase="final")
    path = authorize_experimental_manual_release(
        context.plan,
        acknowledged=True,
        now=datetime(2029, 12, 31, 12, tzinfo=UTC),
    )
    authorization = json.loads(path.read_text())
    authorization["requested_bank"] = 9960
    path.write_text(json.dumps(authorization), encoding="utf-8")
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    with pytest.raises(
        SchedulerIntegrityError,
        match="does not match scheduler plan",
    ):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("release_gate_decision", "PLAY"),
        ("real_money_actionable", True),
        ("release_evidence_id", "self-declared-evidence"),
        ("release_evidence_sha256", "a" * 64),
    ],
)
def test_self_declared_release_evidence_never_enables_real_money(
    tmp_path: Path,
    field: str,
    value: object,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    diagnostics = payload["ev"]["selection_diagnostics"]
    diagnostics[field] = value
    diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(diagnostics)
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="cannot self-declare|not backed by a trusted registry",
    ):
        parse_runner_manifest_phase_result(context, manifest)


def test_scheduler_plan_binds_complete_quality_v2_configuration(tmp_path: Path):
    plan = _plan(tmp_path)
    expected = quality_v2_config_payload(plan.quality_v2_ev_config)
    expected_context = bound_selection_context(plan.quality_v2_ev_config)
    payload = plan.to_payload()
    plan.output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan.output_dir / "scheduler-plan.json"
    plan_path.write_text(scheduler.scheduler_plan_json(plan), encoding="utf-8")

    loaded = scheduler.load_scheduler_plan(plan_path)

    assert payload["config"]["quality_v2"] == expected
    assert payload["config"]["selection_context"] == expected_context
    assert payload["config"]["selection_context_sha256"] == (
        selection_context_sha256(expected_context)
    )
    assert quality_v2_config_payload(loaded.quality_v2_ev_config) == expected
    assert bound_selection_context(loaded.quality_v2_ev_config) == expected_context
    assert set(expected) == {
        "exposure_floor_scale",
        "exposure_floor_exponent",
        "concentration_headroom_share",
        "repair_iterations",
        "candidate_count",
        "optimization_samples",
        "evaluation_samples",
        "optimization_stream",
        "evaluation_stream",
        "objective_order",
        "objective_tolerances",
        "diversity_close_distance",
        "diversity_score_definition",
        "release_protocol_version",
        "rng",
        "numpy_version",
        "exposure_boundary_policy",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bank", 9_960),
        ("minimum_gross_ev", 1.01),
        ("near_fixed_share_limit", 0.90),
        ("package_safety_enabled", False),
        ("provenance_required", False),
    ],
)
def test_manifest_selection_context_mismatch_fails_closed(
    tmp_path: Path,
    field: str,
    value: object,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    forged = payload["config"]["selection_context"]
    forged[field] = value
    payload["config"]["selection_context_sha256"] = selection_context_sha256(forged)
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="config does not match"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_algorithm_selection_context_mismatch_fails_closed(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    forged = payload["config"]["selection_context"]
    forged["quality_v2"]["exposure_floor_scale"] = 0.16
    payload["config"]["selection_context_sha256"] = selection_context_sha256(forged)
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="config does not match"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_quality_v2_configuration_hash_mismatch_fails_closed(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    diagnostics = payload["ev"]["selection_diagnostics"]
    diagnostics["quality_v2_config_sha256"] = "f" * 64
    diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(diagnostics)
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="quality-v2 config mismatch"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_cannot_play_after_package_safety_rejection(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    safety = payload["ev"]["package_safety"]
    safety["decision"] = "NO BET"
    safety["reason_codes"] = ["extreme_concentration"]
    safety["reasons"] = [{"code": "extreme_concentration"}]
    safety["uploadable_coupons"] = []
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="canonical recomputation|does not match scheduler plan",
    ):
        parse_runner_manifest_phase_result(context, manifest)


def test_current_manifest_tampered_safety_decision_fails_recomputation(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    safety = payload["ev"]["package_safety"]
    safety["probabilities"] = (
        (0.05, 0.05, 0.90),
        *safety["probabilities"][1:],
    )
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="canonical recomputation|does not match scheduler plan",
    ):
        parse_runner_manifest_phase_result(context, manifest)


def test_canonically_safe_manifest_still_remains_paper_only(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preflight ready")
        manifest = _write_runner_manifest(
            context,
            _valid_runner_manifest(context),
        )
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="safe-package")

    assert result.outcome == "no-bet"
    assert result.decision == "NO BET"
    assert result.package_path is None
    assert result.marker_path.name == ".no-bet"


@pytest.mark.parametrize("value", [0.0, "nan", "inf", -0.1, 1.1])
def test_manifest_uses_canonical_package_safety_threshold_validation(
    tmp_path: Path,
    value: object,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["ev"]["package_safety"]["config"]["near_fixed_share"] = value
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="config is invalid"):
        parse_runner_manifest_phase_result(context, manifest)


def test_self_consistent_relaxed_manifest_config_cannot_override_plan(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    relaxed = PackageSafetyConfig(material_probability_threshold=0.30)
    safety = evaluate_package_safety(
        ("1" * 15, "X" * 15),
        ((0.40, 0.40, 0.20),) * 15,
        config=relaxed,
    )
    assert safety.decision == "PLAY"
    payload["ev"]["package_safety"] = safety.to_dict()
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="does not match scheduler plan"):
        parse_runner_manifest_phase_result(context, manifest)


def test_custom_plan_safety_config_is_forwarded_and_accepts_matching_manifest(
    tmp_path: Path,
):
    context = _manifest_context(
        tmp_path,
        package_material_probability_threshold=0.30,
    )
    payload = _valid_runner_manifest(context)
    manifest = _write_runner_manifest(context, payload)
    command = build_run_drawing_phase_command(context)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert (
        command[command.index("--package-material-probability-threshold") + 1]
        == "0.29999999999999999"
    )


def test_warmup_manifest_uses_same_45_minute_lead_as_command(tmp_path: Path):
    context = replace(
        _manifest_context(tmp_path, phase="fallback"),
        scheduler_phase="warmup",
    )
    payload = _valid_runner_manifest(context)
    config = payload["config"]
    assert isinstance(config, dict)
    config["final_lead_minutes"] = 45
    manifest = _write_runner_manifest(context, payload)

    command = build_run_drawing_phase_command(context)
    result = parse_runner_manifest_phase_result(context, manifest)

    option = command.index("--final-lead-minutes")
    assert command[option + 1] == "45"
    assert result.decision == "NO BET"


def test_production_manifest_parser_ignores_offline_replay_as_non_production(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["replay"] = {
        "mode": "offline-replay",
        "actionable": False,
    }
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.status == "ignored"
    assert result.decision is None
    assert result.reason == "non-production offline replay manifest ignored"


def test_full_scheduler_ignores_replay_manifest_without_any_marker(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("diagnostic fallback")
        payload = _valid_runner_manifest(context)
        payload["replay"] = {
            "mode": "offline-replay",
            "actionable": False,
        }
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="ignored-offline-replay")

    assert result.outcome == "ignored"
    assert result.decision == "IGNORED"
    assert result.marker_path is None
    assert result.reason == "non-production offline replay manifest ignored"
    assert not any(
        path.name in {".bet-ready", ".no-bet", ".failed", ".ignored"}
        for path in result.run_dir.rglob("*")
    )
    status = _status(result)
    assert status["state"] == "ignored"
    assert status["outcome"] == "ignored"
    assert status["decision"] == "IGNORED"


def test_full_scheduler_invalid_live_manifest_retains_failed_marker(tmp_path: Path):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("diagnostic fallback")
        payload = _valid_runner_manifest(context)
        del payload["timeline"]
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="invalid-live-manifest")

    assert result.outcome == "failed"
    assert result.decision == "FAILED"
    assert result.marker_path == result.run_dir / ".failed"
    assert result.marker_path.is_file()


def test_scheduler_manifest_pin_revalidation_failure_publishes_no_bet_marker(
    tmp_path: Path,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed("preparation ready")
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("fallback cannot authorize play")
        payload = _valid_runner_manifest(context)
        collection = payload["collection"]
        assert isinstance(collection, dict)
        summary = collection["pinned_revalidation"]
        assert isinstance(summary, dict)
        summary["matched_count"] = 14
        summary["provider_failure_event_orders"] = [14]
        summary["stale_event_orders"] = [14]
        summary["schedule_fresh"] = False
        summary["provider_checks_passed"] = False
        summary["fixture_checks_passed"] = False
        summary["team_checks_passed"] = False
        summary["orientation_checks_passed"] = False
        summary["start_time_checks_passed"] = False
        summary["ready_for_play"] = False
        events = list(summary["events"])
        summary["events"] = events
        event = events[14]
        assert isinstance(event, dict)
        event["status"] = "provider_failure"
        event["reason"] = "pinned fixture revalidation schedule is stale"
        manifest = _write_runner_manifest(context, payload)
        return parse_runner_manifest_phase_result(context, manifest)

    result = _execute(plan, run, run_id="stale-pin-manifest")

    assert result.outcome == "no-bet"
    assert result.marker_path.name == ".no-bet"
    assert result.marker_path.is_file()
    assert not (result.run_dir / ".bet-ready").exists()


def test_scheduler_plan_threshold_is_forwarded_and_enforced(tmp_path: Path):
    context = _manifest_context(tmp_path, minimum_gross_ev=1.1)
    command = build_run_drawing_phase_command(context)
    manifest = _write_runner_manifest(context, _valid_runner_manifest(context))

    result = parse_runner_manifest_phase_result(context, manifest)

    assert command[command.index("--min-gross-ev") + 1] == "1.1000000000000001"
    assert result.decision == "NO BET"


def test_production_manifest_parser_accepts_explicit_schema_v4_no_bet(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    payload["decision"] = "NO BET"
    payload["terminal_reason"] = "authoritative threshold NO BET"
    ev = payload["ev"]
    assert isinstance(ev, dict)
    ev.update(
        {
            "computed": False,
            "effective_budget": None,
            "selected_cost": None,
            "unused_requested_bank": None,
            "input_fetched_at": None,
            "minimum_gross_ev": None,
            "prize_fund_factor": None,
            "possible_winnings_source": None,
            "jackpot_source": None,
            "self_dilution_ratio": None,
            "model_supported": None,
            "package_safety": None,
            "selection_diagnostics": None,
        }
    )
    package = ev["package"]
    assert isinstance(package, dict)
    package.update(
        {
            "decision": "NO BET",
            "decision_reason": "threshold not met",
            "coupons": [],
            "selected_count": None,
            "cost": None,
            "unused_bank": None,
            "expected_payout": None,
            "modeled_roi": None,
            "derived_brief": [],
            "structural_status": "NOT_EVALUATED",
            "artifact_class": "NONE",
            "paper_coupons": [],
            "paper_selected_count": 0,
            "paper_cost": 0,
            "paper_expected_payout": 0.0,
            "paper_modeled_roi": None,
            "paper_derived_brief": [],
        }
    )
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.package_bytes is None


def test_rejected_4952_safety_is_recomputed_before_coupon_free_no_bet(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _unsafe_4952_no_bet_manifest(context)
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.package_bytes is None
    assert payload["ev"]["package"]["coupons"] == []
    assert len(payload["ev"]["package_safety"]["evaluated_coupons"]) == 166


@pytest.mark.parametrize(
    "field",
    ["evaluated_coupons", "package_sha256", "reasons", "config", "probabilities"],
)
def test_rejected_4952_safety_tampering_fails_before_no_bet_return(
    tmp_path: Path,
    field: str,
):
    context = _manifest_context(tmp_path)
    payload = _unsafe_4952_no_bet_manifest(context)
    safety = payload["ev"]["package_safety"]
    if field == "evaluated_coupons":
        safety[field] = [*safety[field][:-1], "1" * 15]
    elif field == "package_sha256":
        safety[field] = "0" * 64
    elif field == "reasons":
        safety[field] = []
    elif field == "config":
        safety[field]["near_fixed_share"] = 0.90
    else:
        safety[field] = [
            [0.05, 0.05, 0.90],
            *safety[field][1:],
        ]
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="canonical recomputation|does not match scheduler plan",
    ):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize(
    "terminal_reason",
    [
        "timing:multi_day",
        "self_dilution:package_cost_exceeds_1_percent_pool",
    ],
)
def test_non_safety_no_bet_accepts_recomputed_passing_safety_without_package(
    tmp_path: Path,
    terminal_reason: str,
):
    context = _manifest_context(tmp_path)
    payload = _passing_safety_no_bet_manifest(
        context,
        terminal_reason=terminal_reason,
    )
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.reason == terminal_reason
    assert result.package_bytes is None
    assert payload["ev"]["package"]["coupons"] == []
    assert payload["ev"]["package_safety"]["decision"] == "PLAY"


@pytest.mark.parametrize("field", ["package_sha256", "config", "probabilities"])
def test_non_safety_no_bet_rejects_tampered_passing_safety(
    tmp_path: Path,
    field: str,
):
    context = _manifest_context(tmp_path)
    payload = _passing_safety_no_bet_manifest(
        context,
        terminal_reason="timing:multi_day",
    )
    safety = payload["ev"]["package_safety"]
    if field == "package_sha256":
        safety[field] = "0" * 64
    elif field == "config":
        safety[field]["material_probability_threshold"] = 0.30
    else:
        safety[field] = [
            [0.05, 0.05, 0.90],
            *safety[field][1:],
        ]
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(
        SchedulerPhaseError,
        match="canonical recomputation|does not match scheduler plan",
    ):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("schema", "schema_version"),
        ("command", "command_status"),
        ("nested-play", "nested package decision NO BET"),
        ("bad-coupon", "15 characters"),
        ("count", "count"),
        ("cost", "inconsistent"),
        ("missing-effective", "missing fields"),
        ("timing", "status is inconsistent"),
        ("ev-not-computed", "uncomputed NO BET"),
        ("requested-bank", "requested_bank"),
        ("effective-bank", "effective_budget is inconsistent"),
        ("stake", "config"),
        ("missing-timeline", "missing fields"),
    ],
)
def test_production_manifest_parser_rejects_review_malformed_cases(
    tmp_path: Path,
    case: str,
    expected: str,
):
    context = _manifest_context(tmp_path)
    payload = copy.deepcopy(_valid_runner_manifest(context))
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    coupons = package["paper_coupons"]
    assert isinstance(coupons, list)
    if case == "schema":
        payload["schema_version"] = 999
    elif case == "command":
        payload["command_status"] = "failed"
    elif case == "nested-play":
        package["decision"] = "PLAY"
    elif case == "bad-coupon":
        coupon = coupons[0]
        assert isinstance(coupon, dict)
        coupon["coupon"] = "BAD"
    elif case == "count":
        package["paper_selected_count"] = 3
    elif case == "cost":
        package["paper_cost"] = 30
    elif case == "missing-effective":
        del ev["effective_budget"]
    elif case == "timing":
        eligibility = payload["eligibility"]
        assert isinstance(eligibility, dict)
        effective = eligibility["effective"]
        assert isinstance(effective, dict)
        effective["status"] = "unknown"
    elif case == "ev-not-computed":
        ev["computed"] = False
    elif case == "requested-bank":
        ev["requested_bank"] = 5000
    elif case == "effective-bank":
        ev["effective_budget"] = 31
    elif case == "stake":
        config = payload["config"]
        assert isinstance(config, dict)
        config["stake"] = 10
    elif case == "missing-timeline":
        del payload["timeline"]
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match=expected):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_cannot_lower_plan_threshold_to_publish_half_ev_coupon(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    ev["minimum_gross_ev"] = 0.0
    package = ev["package"]
    assert isinstance(package, dict)
    coupons = package["paper_coupons"]
    assert isinstance(coupons, list)
    first = coupons[0]
    assert isinstance(first, dict)
    first["gross_ev"] = 0.5
    first["net_ev"] = -0.5
    expected_payout = sum(float(row["gross_ev"]) * 30 for row in coupons)
    package["paper_expected_payout"] = expected_payout
    package["paper_modeled_roi"] = expected_payout / 60 - 1.0
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="does not match scheduler plan"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_playable_timing_cannot_hide_missing_events(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["missing_event_orders"] = [14]
        timing["totobrief_count"] = 14
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="status is inconsistent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_timing_source_counts_must_total_known_events(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["provider_count"] = 1
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="source counts"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_playable_timing_rejects_multi_day_span(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    effective = eligibility["effective"]
    assert isinstance(effective, dict)
    for timing in (eligibility, effective):
        timing["span_days"] = 3
        timing["earliest_start"] = "2030-01-02T00:00:00Z"
        timing["latest_start"] = "2030-01-04T00:00:00Z"
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="status is inconsistent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_forged_override_without_configured_catalog(
    tmp_path: Path,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    eligibility["override"] = {
        "status": "not_applied",
        "preflight_catalog_sha256": None,
        "timing_catalog_sha256": None,
        "package_catalog_sha256": None,
        "override_id": None,
        "reviewer": None,
        "reviewed_at": None,
        "source_ref": None,
        "overlay_complete": False,
        "applied_events": [],
        "preserved_event_orders": [],
        "diagnostics": ["forged audit"],
    }
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="must be absent"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_non_string_decision_reason(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    package["decision_reason"] = 7
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="decision_reason"):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize("location", ["manifest", "target", "coupon"])
def test_manifest_rejects_unknown_schema_v4_fields(
    tmp_path: Path,
    location: str,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    if location == "manifest":
        payload["unauthorized"] = True
    elif location == "target":
        target = payload["target"]
        assert isinstance(target, dict)
        target["unauthorized"] = True
    else:
        ev = payload["ev"]
        assert isinstance(ev, dict)
        package = ev["package"]
        assert isinstance(package, dict)
        coupons = package["paper_coupons"]
        assert isinstance(coupons, list)
        coupon = coupons[0]
        assert isinstance(coupon, dict)
        coupon["unauthorized"] = True
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="unknown fields"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_rejects_boolean_integer_field(tmp_path: Path):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    ev = payload["ev"]
    assert isinstance(ev, dict)
    package = ev["package"]
    assert isinstance(package, dict)
    package["selected_count"] = True
    manifest = _write_runner_manifest(context, payload)

    with pytest.raises(SchedulerPhaseError, match="must be an integer"):
        parse_runner_manifest_phase_result(context, manifest)


def test_manifest_accepts_complete_pinned_override_for_incomplete_raw_timing(
    tmp_path: Path,
):
    catalog_path = tmp_path / "timing-overrides.json"
    catalog_hash = _write_complete_catalog(catalog_path)
    context = _manifest_context(
        tmp_path,
        timing_overrides=catalog_path,
        override_sha256=catalog_hash,
    )
    payload = _valid_runner_manifest(context)
    eligibility = payload["eligibility"]
    assert isinstance(eligibility, dict)
    raw = eligibility["raw"]
    effective = eligibility["effective"]
    assert isinstance(raw, dict)
    assert isinstance(effective, dict)
    raw.update(
        {
            "status": "unknown",
            "reason": "two starts unresolved",
            "missing_event_orders": [13, 14],
            "totobrief_count": 13,
        }
    )
    effective.update(
        {
            "reason": "complete reviewed timing overlay",
            "totobrief_count": 13,
            "operator_override_count": 2,
        }
    )
    for field in scheduler._TIMING_PAYLOAD_FIELDS:
        eligibility[field] = effective[field]
    eligibility["override"] = {
        "status": "applied",
        "preflight_catalog_sha256": catalog_hash,
        "timing_catalog_sha256": catalog_hash,
        "package_catalog_sha256": catalog_hash,
        "override_id": "reviewed-complete",
        "reviewer": "release-reviewer",
        "reviewed_at": "2030-01-02T11:30:00+00:00",
        "source_ref": "offline-review:complete",
        "overlay_complete": True,
        "applied_events": [
            {
                "event_order": order,
                "event_id": 70001 + order,
                "starts_at": (
                    datetime(2030, 1, 2, 12, 30, tzinfo=UTC)
                    + timedelta(minutes=5 * order)
                ).isoformat(),
                "source_ref": "offline-review:complete",
            }
            for order in (13, 14)
        ],
        "preserved_event_orders": list(range(13)),
        "diagnostics": [],
    }
    manifest = _write_runner_manifest(context, payload)

    result = parse_runner_manifest_phase_result(context, manifest)

    assert result.decision == "NO BET"
    assert result.override_sha256 is None


@pytest.mark.parametrize("non_finite", ["NaN", "Infinity", "-Infinity"])
def test_production_manifest_parser_rejects_non_finite_json_metrics(
    tmp_path: Path,
    non_finite: str,
):
    context = _manifest_context(tmp_path)
    payload = _valid_runner_manifest(context)
    raw = json.dumps(payload).replace('"gross_ev": 1.2', f'"gross_ev": {non_finite}')
    manifest = _write_runner_manifest(context, payload, raw=raw)

    with pytest.raises(SchedulerPhaseError, match="non-finite"):
        parse_runner_manifest_phase_result(context, manifest)


@pytest.mark.parametrize(
    "package",
    [
        b"rank,coupon,gross_ev,net_ev\n",
        b"rank,coupon,gross_ev,net_ev\n1,BAD,1.1,0.1\n",
        (b"rank,coupon,gross_ev,net_ev\n1,111111111111111,nan,0.1\n"),
        (b"rank,coupon,gross_ev,net_ev\n1,111111111111111,inf,0.1\n"),
        b"coupon,rank,gross_ev,net_ev\n111111111111111,1,1.1,0.1\n",
        b'"rank",coupon,gross_ev,net_ev\n1,111111111111111,1.1,0.1\n',
        (
            b"rank,coupon,gross_ev,net_ev\n"
            b"1,111111111111111,1.1,0.1\n"
            b"2,111111111111111,1.05,0.05\n"
        ),
    ],
)
def test_capture_path_rejects_malformed_or_empty_package_csv(
    tmp_path: Path,
    package: bytes,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return SchedulerPhaseResult.play(
            package,
            effective_bank=4980,
            override_sha256=context.override_sha256,
            package_sha256=hashlib.sha256(package).hexdigest(),
        )

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()
    assert not (result.run_dir / "package.csv").exists()


@pytest.mark.parametrize(
    ("selected_count", "selected_cost"),
    [(2, 30), (1, 60)],
)
def test_capture_path_rejects_count_or_cost_mismatch(
    tmp_path: Path,
    selected_count: int,
    selected_cost: int,
):
    plan = _plan(tmp_path)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return SchedulerPhaseResult.play(
            FINAL_PACKAGE,
            effective_bank=4980,
            selected_count=selected_count,
            selected_cost=selected_cost,
            override_sha256=context.override_sha256,
        )

    result = _execute(plan, run)

    assert result.outcome == "no-bet"
    assert "real-money release gate closed" in result.reason
    assert not (result.run_dir / ".bet-ready").exists()


def test_symlinked_runs_directory_is_rejected_without_escape(tmp_path: Path):
    plan = _plan(tmp_path)
    plan.output_dir.mkdir(parents=True)
    escaped = tmp_path / "escaped-runs"
    escaped.mkdir()
    (plan.output_dir / "runs").symlink_to(escaped, target_is_directory=True)

    with pytest.raises(SchedulerError, match="symlink"):
        _execute(plan, _happy_runner([]))

    assert tuple(escaped.iterdir()) == ()


def test_symlinked_source_package_is_rejected_without_escape(tmp_path: Path):
    plan = _plan(tmp_path)
    external_package = tmp_path / "external-package.csv"
    external_package.write_bytes(FINAL_PACKAGE)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        source = context.work_dir / "source-package.csv"
        source.symlink_to(external_package)
        return SchedulerPhaseResult.play(
            source,
            effective_bank=4980,
            selected_count=1,
            selected_cost=30,
            override_sha256=context.override_sha256,
        )

    result = _execute(plan, run)

    assert result.outcome == "failed"
    assert not (result.run_dir / ".bet-ready").exists()
    assert external_package.read_bytes() == FINAL_PACKAGE


def test_symlinked_status_escape_is_rejected_without_external_write(
    tmp_path: Path,
):
    plan = _plan(tmp_path)
    external_status = tmp_path / "external-status.json"
    external_status.write_text("unchanged\n", encoding="utf-8")

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        if context.phase == "preflight":
            status = context.run_dir / "status.json"
            status.unlink()
            status.symlink_to(external_status)
            return SchedulerPhaseResult.completed()
        return _play(FINAL_PACKAGE, context)

    with pytest.raises(SchedulerError, match="symlink"):
        _execute(plan, run)

    assert external_status.read_text(encoding="utf-8") == "unchanged\n"
    assert not any(plan.output_dir.rglob(".bet-ready"))


def test_symlinked_snapshot_package_cannot_create_bet_ready(tmp_path: Path):
    plan = _plan(tmp_path)
    external_package = tmp_path / "external-snapshot.csv"
    external_package.write_bytes(FINAL_PACKAGE)
    captured: dict[str, Path] = {}

    class SymlinkingClock(VirtualSchedulerClock):
        def sleep(self, seconds: float) -> None:
            super().sleep(seconds)
            if self.current == plan.freeze_at and "run_dir" in captured:
                package = captured["run_dir"] / "snapshots" / "final" / "package.csv"
                package.unlink()
                package.symlink_to(external_package)

    clock = SymlinkingClock(plan.preflight_at)

    def run(context: SchedulerPhaseContext) -> SchedulerPhaseResult:
        captured["run_dir"] = context.run_dir
        if context.phase == "preflight":
            return SchedulerPhaseResult.completed()
        if context.phase == "fallback":
            return SchedulerPhaseResult.no_bet("no fallback")
        return _play(FINAL_PACKAGE, context)

    result = _execute(plan, run, clock=clock)

    assert result.outcome == "failed"
    assert not (result.run_dir / ".bet-ready").exists()
    assert external_package.read_bytes() == FINAL_PACKAGE


def test_runner_manifest_symlink_is_rejected(tmp_path: Path):
    context = _manifest_context(tmp_path)
    outside = tmp_path / "outside-manifest.json"
    outside.write_text(
        json.dumps(_valid_runner_manifest(context)),
        encoding="utf-8",
    )
    report_dir = context.work_dir / "reports"
    report_dir.mkdir()
    manifest = report_dir / "drawing_run_fixture.json"
    manifest.symlink_to(outside)

    with pytest.raises(SchedulerPhaseError, match="symlink|escapes"):
        parse_runner_manifest_phase_result(context, manifest)
