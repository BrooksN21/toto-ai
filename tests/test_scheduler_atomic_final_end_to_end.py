from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

import pytest
import requests
from sqlalchemy import select
from typer.testing import CliRunner

import toto_ai.runner.scheduler as scheduler
from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai import cli
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.db.models import ArchivedPackage, Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.runner.final_input import persist_final_input
from toto_ai.runner.scheduler import (
    SchedulerIntegrityError,
    SchedulerPhaseResult,
    SchedulerTransientError,
    authorize_experimental_manual_release,
    build_scheduler_plan,
    execute_scheduler_tick,
    export_operator_package,
    load_paper_package,
)
from toto_ai.runner.scheduler_state import initial_state, load_state, save_state
from toto_ai.sports_stats import final_hybrid_sidecar

ENDED_AT = datetime(2032, 2, 3, 12, 0, tzinfo=timezone.utc)


def _plan(tmp_path: Path, *, timing_overrides: Path | None = None):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "aliases.json").write_text("{}")
    write_empty_schedule_evidence_ledger(tmp_path)
    return build_scheduler_plan(
        drawing=5100,
        drawing_id=12100,
        ended_at=ENDED_AT,
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
        timing_overrides=timing_overrides,
    )


def _tick(plan, runner, observed_at, sleeps=None):
    return execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=lambda: observed_at,
        sleep=(lambda seconds: sleeps.append(seconds))
        if sleeps is not None
        else (lambda _seconds: None),
    )


def _seed_atomic_drawing(plan) -> None:
    engine = init_db(plan.db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=plan.drawing_id,
                number=plan.drawing,
                ended_at=plan.ended_at.isoformat(),
                status="active",
            )
        )
    engine.dispose()


def _atomic_payload(plan, *, event_id_base: int = 42000):
    return {
        "data": {
            "id": plan.drawing_id,
            "number": plan.drawing,
            "status": "active",
            "ended_at": plan.ended_at.isoformat(),
            "events": [
                {
                    "id": event_id_base + order,
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


def _playing_runner(plan, payload):
    def runner(context):
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=context.run_id,
            captured_at=context.started_at,
            destination=context.run_dir / "final-input.json",
            timing_override_sha256=context.override_sha256,
        )
        return SchedulerPhaseResult.play(
            b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.2,0.2\n",
            effective_bank=4980,
            override_sha256=context.override_sha256,
        )

    return runner


def test_early_tls_api_and_freshness_plan_is_ordered_and_idempotent(tmp_path):
    plan = _plan(tmp_path)
    calls = []

    def runner(context):
        calls.append((context.scheduled_at, context.run_id))
        return SchedulerPhaseResult.failed("diagnostic-only unavailable")

    assert _tick(plan, runner, plan.tls_preflight_at) is None
    assert _tick(plan, runner, plan.tls_preflight_at) is None
    assert _tick(plan, runner, plan.api_preflight_at) is None
    assert _tick(plan, runner, plan.api_preflight_at) is None
    assert _tick(plan, runner, plan.freshness_preflight_at) is None
    assert _tick(plan, runner, plan.freshness_preflight_at) is None

    assert [scheduled for scheduled, _attempt in calls] == [
        plan.tls_preflight_at,
        plan.api_preflight_at,
        plan.freshness_preflight_at,
    ]
    assert len({attempt for _scheduled, attempt in calls}) == 3

    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.freshness_preflight_at,
    )
    assert state["phases"]["tls_preflight"]["status"] == "retryable_failed"
    assert state["phases"]["api_preflight"]["status"] == "retryable_failed"
    assert state["phases"]["freshness_preflight"]["status"] == "retryable_failed"


def test_transport_failure_detail_is_persisted_and_logged(tmp_path, capsys):
    plan = _plan(tmp_path)
    original = requests.exceptions.SSLError(
        "certificate verify failed https://host/path?token=do-not-log"
    )
    error = TotoBriefRequestError(
        "TotoBrief request failed",
        endpoint="/drawing-info/12100",
        attempts=4,
        category="ssl_verify",
        original_transport_message=str(original),
        exception_chain=("SSLError",),
    )
    error.__cause__ = original

    def failing(_context):
        raise error

    assert _tick(plan, failing, plan.final_at) is None
    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.final_at,
    )
    detail = state["phases"]["final"]["failure_details"][-1]
    assert detail["category"] == "ssl_verify"
    assert detail["attempt_count"] == 4
    assert detail["exception_chain"] == ["TotoBriefRequestError", "SSLError"]
    assert "do-not-log" not in json.dumps(state)
    assert "do-not-log" not in capsys.readouterr().err


def test_stale_early_success_cannot_produce_play_without_fresh_final_network(
    tmp_path,
):
    plan = _plan(tmp_path)
    calls = []

    def runner(context):
        calls.append(context.phase)
        if context.phase == "preflight":
            return SchedulerPhaseResult.failed("cached preparation is stale")
        raise TotoBriefRequestError(
            "fresh final TotoBrief transport unavailable",
            endpoint=f"/drawing-info/{plan.drawing_id}",
            attempts=4,
            category="timeout",
            original_transport_message="read timed out",
            exception_chain=("Timeout",),
        )

    assert _tick(plan, runner, plan.tls_preflight_at) is None
    assert _tick(plan, runner, plan.api_preflight_at) is None
    assert _tick(plan, runner, plan.freshness_preflight_at) is None
    assert _tick(plan, runner, plan.final_at) is None
    result = _tick(plan, runner, plan.publish_deadline)

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.package_path is None
    assert not list(plan.output_dir.rglob(".bet-ready"))
    assert calls[-1] == "final"


def test_warmup_failure_does_not_block_independent_final(tmp_path):
    plan = _plan(tmp_path)
    calls = []

    def runner(context):
        calls.append(context.phase)
        if context.phase == "preflight":
            return SchedulerPhaseResult.failed("temporary cache unavailable")
        return SchedulerPhaseResult.no_bet("fixture final completed safely")

    assert _tick(plan, runner, plan.preflight_at) is None
    result = _tick(plan, runner, plan.final_at)

    assert result is not None
    assert result.outcome == "no-bet"
    assert calls == ["preflight", "final"]
    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.final_at,
    )
    assert state["phases"]["warmup"]["status"] == "retryable_failed"
    assert state["terminal"] == "no_bet"


def test_warmup_no_bet_without_package_is_not_reported_complete(tmp_path):
    plan = _plan(tmp_path)

    def runner(_context):
        return SchedulerPhaseResult.no_bet(
            "pinned revalidation is not fresh matched 15/15"
        )

    assert _tick(plan, runner, plan.preflight_at) is None

    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.preflight_at,
    )
    assert state["phases"]["warmup"]["status"] == "retryable_failed"
    assert "did not produce a usable package" in state["transitions"][-1]["reason"]
    assert state["terminal"] is None


def test_final_transient_retry_is_bounded_and_restart_can_resume(tmp_path):
    plan = _plan(tmp_path)
    calls = 0
    sleeps = []

    def failing(_context):
        nonlocal calls
        calls += 1
        raise RuntimeError("temporary provider unavailable")

    assert _tick(plan, failing, plan.final_at, sleeps) is None
    assert calls == 4
    assert sleeps == [2, 5, 10]

    def recovered(_context):
        return SchedulerPhaseResult.no_bet("restarted final completed")

    result = _tick(plan, recovered, plan.retry_at)
    assert result is not None
    assert result.outcome == "no-bet"
    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.retry_at,
    )
    assert len(state["phases"]["final"]["attempts"]) == 2


def test_error_classification_uses_types_and_http_status_not_message_tokens(
    tmp_path,
):
    retryable_errors = (
        RuntimeError("HTTP 503 on API path /fixtures"),
        TimeoutError("timeout reading cached path"),
        SchedulerTransientError(
            "temporary configuration service unavailable",
            category="configuration_service",
        ),
        TotoBriefRequestError(
            "provider unavailable",
            endpoint="/drawing-info/1",
            attempts=4,
            status_code=503,
        ),
    )
    for index, error in enumerate(retryable_errors):
        case_root = tmp_path / f"retryable-{index}"
        case_root.mkdir()
        plan = _plan(case_root)

        def failing(_context, *, error=error):
            raise error

        assert _tick(plan, failing, plan.final_at) is None
        state = load_state(
            plan.output_dir / "scheduler-state.json",
            plan_id=plan.plan_id,
            now=plan.final_at,
        )
        assert state["phases"]["final"]["status"] == "retryable_failed"
        assert state["terminal"] is None


def test_typed_integrity_error_is_terminal_without_message_matching(tmp_path):
    plan = _plan(tmp_path)

    def failing(_context):
        raise SchedulerIntegrityError(
            "cryptographic evidence rejected",
            category="final_input_integrity",
        )

    with pytest.raises(SchedulerIntegrityError):
        _tick(plan, failing, plan.final_at)

    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.final_at,
    )
    assert state["phases"]["final"]["status"] == "integrity_failed"
    assert state["terminal"] == "failed"


def test_bound_ledger_tamper_is_terminal_during_warmup_without_retry(
    tmp_path,
):
    plan = _plan(tmp_path)
    plan.schedule_evidence_ledger.write_text("{}\n", encoding="utf-8")
    calls = []

    with pytest.raises(SchedulerIntegrityError, match="ledger integrity"):
        _tick(plan, lambda context: calls.append(context), plan.preflight_at)

    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.preflight_at,
    )
    assert calls == []
    assert state["phases"]["warmup"]["status"] == "integrity_failed"
    assert state["terminal"] == "failed"


def test_deadline_miss_is_zero_cost_no_bet_without_phase_work(tmp_path):
    plan = _plan(tmp_path)
    calls = []
    result = _tick(
        plan,
        lambda context: calls.append(context),
        plan.publish_deadline + timedelta(seconds=1),
    )

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.package_path is None
    assert calls == []


def test_final_completion_inside_publication_reserve_is_no_bet(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    observed_at = plan.final_at
    payload = _atomic_payload(plan, event_id_base=44000)

    def now():
        return observed_at

    def runner(context):
        nonlocal observed_at
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=context.run_id,
            captured_at=context.started_at,
            destination=context.run_dir / "final-input.json",
            timing_override_sha256=context.override_sha256,
        )
        observed_at = plan.publish_deadline - timedelta(seconds=30)
        return SchedulerPhaseResult.play(
            b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.2,0.2\n",
            effective_bank=4980,
            override_sha256=context.override_sha256,
        )

    result = execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=now,
        sleep=lambda _seconds: None,
    )

    assert result is not None
    assert result.outcome == "no-bet"
    assert result.package_path is None
    assert not any(plan.output_dir.rglob(".bet-ready"))


def test_final_completed_by_cutoff_publishes_inside_reserve_by_hard_t10(
    tmp_path,
    monkeypatch,
):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    payload = _atomic_payload(plan, event_id_base=44100)
    cutoff = plan.actionable_publication_deadline

    class Clock:
        current = plan.final_at

        def now(self):
            return self.current

    clock = Clock()
    original_write = scheduler._write_exclusive_atomic
    publication_observations = {}

    def write_inside_reserve(output_root, path, content, **kwargs):
        if path.name == "package.csv":
            clock.current = cutoff + timedelta(seconds=1)
        elif path.name == "package-archive.json":
            clock.current = cutoff + timedelta(seconds=15)
        elif path.name == ".bet-ready":
            clock.current = plan.publish_deadline
        if path.name in {"package.csv", "package-archive.json", ".bet-ready"}:
            publication_observations[path.name] = clock.current
        return original_write(output_root, path, content, **kwargs)

    monkeypatch.setattr(
        scheduler,
        "_write_exclusive_atomic",
        write_inside_reserve,
    )

    def runner(context):
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=context.run_id,
            captured_at=context.started_at,
            destination=context.run_dir / "final-input.json",
            timing_override_sha256=context.override_sha256,
        )
        clock.current = cutoff
        return SchedulerPhaseResult.play(
            b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.2,0.2\n",
            effective_bank=4980,
            override_sha256=context.override_sha256,
        )

    result = execute_scheduler_tick(
        plan,
        phase_runner=runner,
        now=clock.now,
        sleep=lambda _seconds: None,
    )

    assert result is not None
    assert result.outcome == "bet-ready"
    assert result.package_path is not None and result.package_path.is_file()
    assert result.marker_path is not None and result.marker_path.is_file()
    assert publication_observations == {
        "package.csv": cutoff + timedelta(seconds=1),
        "package-archive.json": cutoff + timedelta(seconds=15),
        ".bet-ready": plan.publish_deadline,
    }


def test_bet_ready_publication_creates_verified_operator_export(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45100)),
        plan.final_at,
    )

    assert published is not None and published.outcome == "bet-ready"
    operator_result = json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    assert operator_result["decision"] == "PLAY"
    assert operator_result["actionable"] is True
    assert operator_result["schema_version"] == 3
    assert operator_result["release_mode"] == "STANDARD"
    assert operator_result["profitability_proven"] is False
    assert operator_result["risk_acknowledged"] is False
    assert operator_result["run_id"] == published.run_id
    assert operator_result["expires_at"] == plan.publish_deadline.isoformat().replace(
        "+00:00", "Z"
    )
    delivery = json.loads(
        (plan.output_dir / "operator-delivery.json").read_text(encoding="utf-8")
    )
    assert delivery["delivery_state"] == "READY"
    assert delivery["actionable"] is True
    assert delivery["coupon_path"] == operator_result["coupon_path"]
    assert delivery["package_sha256"] == operator_result["package_sha256"]
    assert delivery["selected_count"] == operator_result["selected_count"]
    assert delivery["selected_cost"] == operator_result["selected_cost"]
    assert delivery["expires_at"] == operator_result["expires_at"]
    assert delivery["automatic_wagering"] is False
    assert delivery["record_sha256"] == scheduler._operator_result_sha256(delivery)

    destination = tmp_path / "exports" / "drawing-5100.txt"
    exported = export_operator_package(
        plan,
        destination=destination,
        observed_at=plan.final_at + timedelta(minutes=1),
    )

    assert exported == destination
    assert destination.read_bytes() == (
        published.run_dir / "baltbet-upload.txt"
    ).read_bytes()
    assert destination.read_text(encoding="utf-8") == (
        "30; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1\n"
    )


def test_ready_publication_retries_prior_skipped_sidecar_exactly_once(
    tmp_path,
    monkeypatch,
):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    plan_path = plan.output_dir / "scheduler-plan.json"
    plan.output_dir.mkdir(parents=True)
    plan_path.write_text(scheduler.scheduler_plan_json(plan), encoding="utf-8")
    sidecar_root = plan.output_dir / "parallel-challenger"
    wrapper_path = (
        sidecar_root / final_hybrid_sidecar.PARALLEL_SIDECAR_WRAPPER_FILENAME
    )
    wrapper_path.parent.mkdir(parents=True)
    wrapper_path.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
    wrapper_path.chmod(0o700)
    sidecar_status_path = sidecar_root / "output" / "sidecar-status.json"
    sidecar_status_path.parent.mkdir(parents=True)
    sidecar_status = {
        "schema_version": 2,
        "status": "SKIPPED_OPERATOR_NOT_READY",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "scheduler_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "started_at": (plan.final_at - timedelta(minutes=15)).isoformat(),
        "observed_at": (plan.final_at - timedelta(minutes=1)).isoformat(),
        "reason": "operator PLAY was not ready before sidecar safe start",
        "automatic_wagering": False,
    }
    sidecar_status["record_sha256"] = hashlib.sha256(
        scheduler._canonical_json_bytes(sidecar_status)
    ).hexdigest()
    sidecar_status_path.write_bytes(
        scheduler._canonical_json_bytes(sidecar_status) + b"\n"
    )
    launched = []
    original_retry = (
        final_hybrid_sidecar.retry_parallel_sidecar_after_operator_publication
    )

    def launch(*args, **kwargs):
        launched.append((args, kwargs))

    def retry_with_fake_process(**kwargs):
        return original_retry(**kwargs, process_launcher=launch)

    monkeypatch.setattr(
        final_hybrid_sidecar,
        "retry_parallel_sidecar_after_operator_publication",
        retry_with_fake_process,
    )

    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45105)),
        plan.final_at,
    )
    operator_path = plan.output_dir / "operator-result.json"
    operator_bytes = operator_path.read_bytes()
    duplicate = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45105)),
        plan.final_at,
    )

    assert published is not None and published.outcome == "bet-ready"
    assert duplicate == published
    assert len(launched) == 1
    assert launched[0][0][0] == [str(wrapper_path)]
    assert operator_path.read_bytes() == operator_bytes
    marker = json.loads(
        (sidecar_root / "parallel-sidecar-retry.json").read_text(encoding="utf-8")
    )
    operator = json.loads(operator_bytes)
    assert marker["operator_result_sha256"] == operator["record_sha256"]
    assert marker["sidecar_status_sha256"] == sidecar_status["record_sha256"]
    assert marker["automatic_wagering"] is False


def test_ready_publication_ignores_mismatched_sidecar_without_primary_degradation(
    tmp_path,
    monkeypatch,
):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    plan_path = plan.output_dir / "scheduler-plan.json"
    plan.output_dir.mkdir(parents=True)
    plan_path.write_text(scheduler.scheduler_plan_json(plan), encoding="utf-8")
    sidecar_root = plan.output_dir / "parallel-challenger"
    wrapper_path = (
        sidecar_root / final_hybrid_sidecar.PARALLEL_SIDECAR_WRAPPER_FILENAME
    )
    wrapper_path.parent.mkdir(parents=True)
    wrapper_path.write_text("#!/bin/zsh\nexit 0\n", encoding="utf-8")
    wrapper_path.chmod(0o700)
    sidecar_status_path = sidecar_root / "output" / "sidecar-status.json"
    sidecar_status_path.parent.mkdir(parents=True)
    sidecar_status = {
        "schema_version": 2,
        "status": "SKIPPED_OPERATOR_NOT_READY",
        "plan_id": "fedcba9876543210",
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "scheduler_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "started_at": (plan.final_at - timedelta(minutes=15)).isoformat(),
        "observed_at": (plan.final_at - timedelta(minutes=1)).isoformat(),
        "reason": "operator PLAY was not ready before sidecar safe start",
        "automatic_wagering": False,
    }
    sidecar_status["record_sha256"] = hashlib.sha256(
        scheduler._canonical_json_bytes(sidecar_status)
    ).hexdigest()
    sidecar_status_path.write_bytes(
        scheduler._canonical_json_bytes(sidecar_status) + b"\n"
    )
    launched = []
    original_retry = (
        final_hybrid_sidecar.retry_parallel_sidecar_after_operator_publication
    )

    def launch(*args, **kwargs):
        launched.append((args, kwargs))

    def retry_with_fake_process(**kwargs):
        return original_retry(**kwargs, process_launcher=launch)

    monkeypatch.setattr(
        final_hybrid_sidecar,
        "retry_parallel_sidecar_after_operator_publication",
        retry_with_fake_process,
    )

    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45106)),
        plan.final_at,
    )

    assert published is not None and published.outcome == "bet-ready"
    operator = json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    assert operator["decision"] == "PLAY"
    assert operator["actionable"] is True
    assert launched == []
    assert not (sidecar_root / "parallel-sidecar-retry.json").exists()


def test_atomic_archive_import_uses_raw_baltbet_deadline_identity(tmp_path):
    plan = _plan(tmp_path)
    raw_source_deadline = plan.ended_at + timedelta(hours=3)
    engine = init_db(plan.db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=plan.drawing_id,
                number=plan.drawing,
                name="baltbet-main",
                ended_at=raw_source_deadline.isoformat(),
                status="active",
            )
        )
    engine.dispose()
    payload = _atomic_payload(plan, event_id_base=45110)
    payload["data"]["name"] = "baltbet-main"
    payload["data"]["ended_at"] = raw_source_deadline.isoformat().replace(
        "+00:00",
        "Z",
    )

    published = _tick(plan, _playing_runner(plan, payload), plan.final_at)

    assert published is not None and published.outcome == "bet-ready"
    archive_payload = json.loads(
        (published.run_dir / "package-archive.json").read_text(encoding="utf-8")
    )
    assert archive_payload["ended_at"] == raw_source_deadline.isoformat().replace(
        "+00:00",
        "Z",
    )
    assert plan.ended_at != raw_source_deadline
    engine = init_db(plan.db)
    with get_session_factory(engine)() as session:
        archived = session.scalar(select(ArchivedPackage))
        assert archived is not None
        assert archived.drawing_id == plan.drawing_id
        assert archived.drawing_number == plan.drawing
        assert archived.archive_manifest_sha256 == archive_payload[
            "archive_manifest_sha256"
        ]
    engine.dispose()


def test_authorized_experimental_result_is_explicitly_bound_and_exportable(
    tmp_path,
):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    authorization_path = authorize_experimental_manual_release(
        plan,
        acknowledged=True,
        now=plan.final_at - timedelta(minutes=1),
    )

    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45125)),
        plan.final_at,
    )

    assert published is not None and published.outcome == "bet-ready"
    operator_result = json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    assert operator_result["release_mode"] == "EXPERIMENTAL_MANUAL"
    assert operator_result["release_authorization_path"] == str(authorization_path)
    assert (
        operator_result["release_authorization_sha256"]
        == authorization["record_sha256"]
    )
    assert operator_result["risk_acknowledged"] is True
    assert operator_result["profitability_proven"] is False
    assert operator_result["automatic_wagering"] is False

    destination = tmp_path / "exports" / "experimental-manual.txt"
    assert export_operator_package(
        plan,
        destination=destination,
        observed_at=plan.final_at + timedelta(minutes=1),
    ) == destination
    assert destination.is_file()


def test_operator_export_cli_uses_only_verified_actionable_result(
    tmp_path,
    monkeypatch,
):
    plan = _plan(tmp_path)
    plan = scheduler.prepare_scheduler_artifacts(plan).plan
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45150)),
        plan.final_at,
    )
    assert published is not None and published.outcome == "bet-ready"
    monkeypatch.setattr(cli, "_utc_now_datetime", lambda: plan.final_at)
    destination = tmp_path / "exports" / "cli-drawing-5100.txt"

    result = CliRunner().invoke(
        cli.app,
        [
            "operator-export",
            "--plan",
            str(plan.output_dir / "scheduler-plan.json"),
            "--output",
            str(destination),
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"Operator package: {destination}" in result.output
    assert destination.is_file()


def test_operator_export_rejects_no_bet_without_writing(tmp_path):
    plan = _plan(tmp_path)
    scheduler._write_operator_no_bet(
        plan,
        reason="release gate closed",
        completed_at=plan.final_at,
    )
    destination = tmp_path / "exports" / "must-not-exist.txt"

    with pytest.raises(SchedulerIntegrityError, match="not actionable"):
        export_operator_package(
            plan,
            destination=destination,
            observed_at=plan.final_at,
        )

    assert not destination.exists()


def test_operator_export_rejects_expired_or_tampered_package(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45200)),
        plan.final_at,
    )
    assert published is not None and published.outcome == "bet-ready"

    expired_destination = tmp_path / "exports" / "expired.txt"
    with pytest.raises(SchedulerIntegrityError, match="expired at T-10"):
        export_operator_package(
            plan,
            destination=expired_destination,
            observed_at=plan.publish_deadline,
        )
    assert not expired_destination.exists()

    upload = published.run_dir / "baltbet-upload.txt"
    upload.write_text(
        "30; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2; 2\n",
        encoding="utf-8",
    )
    tampered_destination = tmp_path / "exports" / "tampered.txt"
    with pytest.raises(SchedulerIntegrityError, match="hash mismatch"):
        export_operator_package(
            plan,
            destination=tampered_destination,
            observed_at=plan.final_at + timedelta(minutes=1),
        )
    assert not tampered_destination.exists()


def test_operator_export_rechecks_t10_after_integrity_validation(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45250)),
        plan.final_at,
    )
    assert published is not None and published.outcome == "bet-ready"
    observations = iter((plan.final_at, plan.publish_deadline))
    destination = tmp_path / "exports" / "crossed-t10.txt"

    with pytest.raises(SchedulerIntegrityError, match="expired at T-10"):
        export_operator_package(
            plan,
            destination=destination,
            now=lambda: next(observations),
        )

    assert not destination.exists()


def test_operator_export_rejects_rebound_foreign_package_path(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45275)),
        plan.final_at,
    )
    assert published is not None and published.outcome == "bet-ready"
    operator_path = plan.output_dir / "operator-result.json"
    operator = json.loads(operator_path.read_text(encoding="utf-8"))
    foreign = tmp_path / "research-package.txt"
    foreign.write_bytes((published.run_dir / "baltbet-upload.txt").read_bytes())
    operator["coupon_path"] = str(foreign)
    operator["record_sha256"] = scheduler._operator_result_sha256(operator)
    operator_path.write_text(json.dumps(operator), encoding="utf-8")
    destination = tmp_path / "exports" / "foreign.txt"

    with pytest.raises(SchedulerIntegrityError, match="inside output root"):
        export_operator_package(
            plan,
            destination=destination,
            observed_at=plan.final_at + timedelta(minutes=1),
        )

    assert not destination.exists()


def test_t10_tick_expires_operator_upload_but_retains_audit_archive(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    published = _tick(
        plan,
        _playing_runner(plan, _atomic_payload(plan, event_id_base=45300)),
        plan.final_at,
    )
    assert published is not None and published.outcome == "bet-ready"
    upload = published.run_dir / "baltbet-upload.txt"
    archive = published.run_dir / "package-archive.json"
    marker = published.run_dir / ".bet-ready"
    paper_before = load_paper_package(plan)
    assert upload.is_file()
    assert paper_before.actionable is False
    assert paper_before.paper_path is not None and paper_before.paper_path.is_file()

    repeated = _tick(
        plan,
        lambda _context: (_ for _ in ()).throw(AssertionError("must not rerun")),
        plan.publish_deadline,
    )

    assert repeated is not None and repeated.outcome == "bet-ready"
    assert not upload.exists()
    assert archive.is_file()
    assert marker.is_file()
    operator = json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    assert operator["decision"] == "NO BET"
    assert operator["actionable"] is False
    assert operator["coupon_path"] is None
    delivery = json.loads(
        (plan.output_dir / "operator-delivery.json").read_text(encoding="utf-8")
    )
    assert delivery["delivery_state"] == "EXPIRED"
    assert delivery["actionable"] is False
    assert delivery["coupon_path"] is None
    assert delivery["package_sha256"] is not None
    assert delivery["selected_count"] == 1
    assert delivery["selected_cost"] == plan.stake
    assert delivery["archive_manifest_path"] == str(archive)
    assert delivery["expired_at"] == plan.publish_deadline.isoformat().replace(
        "+00:00", "Z"
    )
    assert delivery["record_sha256"] == scheduler._operator_result_sha256(delivery)
    paper_after = load_paper_package(plan)
    assert paper_after == paper_before
    assert paper_after.paper_path is not None and paper_after.paper_path.is_file()
    assert paper_after.source_package_path is not None
    assert paper_after.source_package_path.is_file()
    with pytest.raises(SchedulerIntegrityError, match="expired at T-10"):
        export_operator_package(
            plan,
            destination=tmp_path / "expired-paper-must-not-export.txt",
            observed_at=plan.publish_deadline + timedelta(seconds=1),
        )


def test_overlapping_ticks_run_one_final_attempt(tmp_path):
    plan = _plan(tmp_path)
    calls = 0

    def runner(_context):
        nonlocal calls
        calls += 1
        return SchedulerPhaseResult.no_bet("single locked final")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                lambda _unused: _tick(plan, runner, plan.final_at),
                range(2),
            )
        )

    assert calls == 1
    assert sum(result is not None for result in results) == 1


def test_overlapping_canary_and_warmup_do_not_run_concurrently(tmp_path):
    plan = _plan(tmp_path)
    entered = Event()
    warmup_entered = Event()
    release = Event()
    calls = []

    def runner(context):
        calls.append(context.scheduler_phase)
        if context.scheduler_phase == "freshness_preflight":
            entered.set()
            assert release.wait(timeout=2)
        if context.scheduler_phase == "warmup":
            warmup_entered.set()
        return SchedulerPhaseResult.completed("phase complete")

    with ThreadPoolExecutor(max_workers=2) as pool:
        canary = pool.submit(
            _tick,
            plan,
            runner,
            plan.freshness_preflight_at,
        )
        assert entered.wait(timeout=2)
        overlapping_warmup = pool.submit(
            _tick,
            plan,
            runner,
            plan.preflight_at,
        )
        assert not warmup_entered.wait(timeout=0.1)
        release.set()
        assert canary.result(timeout=2) is None
        assert overlapping_warmup.result(timeout=2) is None

    assert calls == ["freshness_preflight", "warmup"]


def test_archive_without_marker_is_recovered_at_hard_t10(tmp_path):
    plan = _plan(tmp_path)
    engine = init_db(plan.db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=plan.drawing_id,
                number=plan.drawing,
                ended_at=plan.ended_at.isoformat(),
                status="active",
            )
        )
    engine.dispose()

    payload = {
        "data": {
            "id": plan.drawing_id,
            "number": plan.drawing,
            "status": "active",
            "ended_at": plan.ended_at.isoformat(),
            "events": [
                {
                    "id": 40000 + order,
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

    def runner(context):
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=context.run_id,
            captured_at=context.started_at,
            destination=context.run_dir / "final-input.json",
            timing_override_sha256=context.override_sha256,
        )
        return SchedulerPhaseResult.play(
            b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.2,0.2\n",
            effective_bank=4980,
        )

    published = _tick(plan, runner, plan.final_at)
    assert published is not None and published.outcome == "bet-ready"
    post_draw_plan = plan.output_dir / "post-draw" / f"post-draw-{plan.drawing_id}.json"
    assert post_draw_plan.is_file()
    post_draw = json.loads(post_draw_plan.read_text())
    assert post_draw["package_binding"]["kind"] == "package"
    assert post_draw["automatic_wagering"] is False
    assert published.marker_path is not None
    published.marker_path.unlink()
    save_state(
        plan.output_dir / "scheduler-state.json",
        initial_state(plan.plan_id, plan.publish_deadline),
    )

    recovered = _tick(
        plan,
        lambda _context: (_ for _ in ()).throw(AssertionError("rerun")),
        plan.publish_deadline,
    )
    assert recovered is not None
    assert recovered.outcome == "bet-ready"
    assert recovered.marker_path is not None and recovered.marker_path.is_file()
    assert not (recovered.run_dir / "baltbet-upload.txt").exists()
    operator = json.loads(
        (plan.output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    assert operator["decision"] == "NO BET"
    assert operator["actionable"] is False


def test_atomic_final_post_draw_uses_raw_baltbet_source_deadline(tmp_path):
    plan = _plan(tmp_path)
    raw_ended_at = plan.ended_at.astimezone(ZoneInfo("Europe/Moscow")).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    engine = init_db(plan.db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=plan.drawing_id,
                number=plan.drawing,
                name="baltbet-main",
                ended_at=raw_ended_at,
                status="active",
            )
        )
    engine.dispose()
    payload = _atomic_payload(plan)
    payload["data"]["name"] = "baltbet-main"
    payload["data"]["ended_at"] = raw_ended_at

    published = _tick(plan, _playing_runner(plan, payload), plan.final_at)

    assert published is not None and published.outcome == "bet-ready"
    post_draw_dir = plan.output_dir / "post-draw"
    assert not (post_draw_dir / "generation-error.json").exists()
    post_draw = json.loads(
        (post_draw_dir / f"post-draw-{plan.drawing_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert post_draw["drawing_id"] == plan.drawing_id
    assert post_draw["drawing_number"] == plan.drawing
    assert datetime.fromisoformat(post_draw["ended_at"]) == plan.ended_at


def test_late_archive_recovery_removes_stale_actionable_files(tmp_path):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    runner = _playing_runner(plan, _atomic_payload(plan, event_id_base=44500))

    published = _tick(plan, runner, plan.final_at)
    assert published is not None and published.outcome == "bet-ready"
    assert published.marker_path is not None
    package_path = published.run_dir / "package.csv"
    archive_manifest_path = published.run_dir / "package-archive.json"
    assert package_path.is_file()
    assert archive_manifest_path.is_file()
    published.marker_path.unlink()
    save_state(
        plan.output_dir / "scheduler-state.json",
        initial_state(plan.plan_id, plan.publish_deadline + timedelta(seconds=1)),
    )

    recovered = _tick(
        plan,
        lambda _context: (_ for _ in ()).throw(AssertionError("rerun")),
        plan.publish_deadline + timedelta(seconds=1),
    )

    assert recovered is not None
    assert recovered.outcome == "no-bet"
    assert recovered.package_path is None
    assert not package_path.exists()
    assert not archive_manifest_path.exists()
    assert not any(plan.output_dir.rglob(".bet-ready"))


def test_terminal_state_still_recovers_archive_without_marker_idempotently(
    tmp_path,
):
    plan = _plan(tmp_path)
    engine = init_db(plan.db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=plan.drawing_id,
                number=plan.drawing,
                ended_at=plan.ended_at.isoformat(),
                status="active",
            )
        )
    engine.dispose()
    payload = {
        "data": {
            "id": plan.drawing_id,
            "number": plan.drawing,
            "status": "active",
            "ended_at": plan.ended_at.isoformat(),
            "events": [
                {
                    "id": 41000 + order,
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

    def runner(context):
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=context.run_id,
            captured_at=context.started_at,
            destination=context.run_dir / "final-input.json",
            timing_override_sha256=context.override_sha256,
        )
        return SchedulerPhaseResult.play(
            b"rank,coupon,gross_ev,net_ev\n1,111111111111111,1.2,0.2\n",
            effective_bank=4980,
        )

    published = _tick(plan, runner, plan.final_at)
    assert published is not None and published.outcome == "bet-ready"
    assert published.marker_path is not None
    published.marker_path.unlink()

    recovered = _tick(
        plan,
        lambda _context: (_ for _ in ()).throw(AssertionError("rerun")),
        plan.final_at + timedelta(minutes=1),
    )
    assert recovered is not None and recovered.outcome == "bet-ready"
    assert recovered.marker_path is not None and recovered.marker_path.is_file()

    repeated = _tick(
        plan,
        lambda _context: (_ for _ in ()).throw(AssertionError("rerun")),
        plan.final_at + timedelta(minutes=1),
    )
    assert repeated is not None and repeated.outcome == "bet-ready"
    assert repeated.run_id == recovered.run_id


def test_bet_ready_state_is_persisted_only_after_marker_publication(
    tmp_path,
    monkeypatch,
):
    plan = _plan(tmp_path)
    _seed_atomic_drawing(plan)
    runner = _playing_runner(plan, _atomic_payload(plan))
    original_write = scheduler._write_exclusive_atomic
    marker_failures = 0

    def fail_first_bet_ready_marker(output_root, path, content, **kwargs):
        nonlocal marker_failures
        if path.name == ".bet-ready" and marker_failures == 0:
            marker_failures += 1
            raise OSError("simulated marker write failure")
        return original_write(output_root, path, content, **kwargs)

    monkeypatch.setattr(
        scheduler,
        "_write_exclusive_atomic",
        fail_first_bet_ready_marker,
    )

    failed = _tick(plan, runner, plan.final_at)

    assert failed is not None and failed.outcome == "failed"
    assert failed.package_path is None
    assert not (failed.run_dir / "package.csv").exists()
    assert not (failed.run_dir / "package-archive.json").exists()
    assert not (failed.run_dir / ".bet-ready").exists()
    assert (failed.run_dir / ".failed").is_file()
    failed_status = json.loads(failed.status_path.read_text(encoding="utf-8"))
    assert failed_status["package_path"] is None
    assert failed_status["package_sha256"] is None
    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.final_at,
    )
    assert state["terminal"] == "failed"
    assert state["phases"]["final"]["status"] == "complete"
    assert state["phases"]["publish"]["status"] == "permanent_failed"

    rerun_calls = 0

    def must_not_rerun(_context):
        nonlocal rerun_calls
        rerun_calls += 1
        raise AssertionError("terminal marker failure must remain fail-closed")

    assert _tick(plan, must_not_rerun, plan.retry_at) is None
    assert rerun_calls == 0
    assert not any(plan.output_dir.rglob(".bet-ready"))
    state = load_state(
        plan.output_dir / "scheduler-state.json",
        plan_id=plan.plan_id,
        now=plan.retry_at,
    )
    assert state["terminal"] == "failed"


def test_archive_recovery_rejects_changed_timing_override(tmp_path):
    timing_overrides = tmp_path / "data" / "timing-overrides.json"
    timing_overrides.parent.mkdir()
    timing_overrides.write_text('{"overrides":[]}\n', encoding="utf-8")
    plan = _plan(tmp_path, timing_overrides=timing_overrides)
    _seed_atomic_drawing(plan)
    runner = _playing_runner(plan, _atomic_payload(plan, event_id_base=43000))

    published = _tick(plan, runner, plan.final_at)
    assert published is not None and published.outcome == "bet-ready"
    assert published.marker_path is not None
    published.marker_path.unlink()
    save_state(
        plan.output_dir / "scheduler-state.json",
        initial_state(plan.plan_id, plan.final_at + timedelta(minutes=1)),
    )
    timing_overrides.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "schema_version": 1,
                        "override_id": "reviewed-change",
                        "drawing_id": plan.drawing_id,
                        "target_fingerprint": "a" * 64,
                        "reviewer": "fixture-reviewer",
                        "reviewed_at": "2032-02-03T10:00:00+00:00",
                        "source_ref": "fixture:changed-after-archive",
                        "events": [
                            {
                                "event_order": 0,
                                "event_id": 43000,
                                "starts_at": "2032-02-03T12:30:00+00:00",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        SchedulerIntegrityError,
        match="timing override.*changed",
    ):
        _tick(
            plan,
            lambda _context: (_ for _ in ()).throw(
                AssertionError("final phase must not rerun during recovery")
            ),
            plan.final_at + timedelta(minutes=1),
        )

    assert not any(plan.output_dir.rglob(".bet-ready"))
