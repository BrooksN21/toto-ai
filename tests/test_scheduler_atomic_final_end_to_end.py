from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import toto_ai.runner.scheduler as scheduler
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.runner.final_input import persist_final_input
from toto_ai.runner.scheduler import (
    SchedulerIntegrityError,
    SchedulerPhaseResult,
    SchedulerTransientError,
    build_scheduler_plan,
    execute_scheduler_tick,
)
from toto_ai.runner.scheduler_state import initial_state, load_state, save_state

ENDED_AT = datetime(2032, 2, 3, 12, 0, tzinfo=timezone.utc)


def _plan(tmp_path: Path, *, timing_overrides: Path | None = None):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "aliases.json").write_text("{}")
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
