from datetime import datetime, timezone

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.runner.preflight_status import _evening_scheduler_status
from toto_ai.runner.scheduler import build_scheduler_plan, prepare_scheduler_artifacts
from toto_ai.runner.scheduler_state import initial_state, save_state, transition

UTC = timezone.utc
DEADLINE = datetime(2030, 1, 2, 16, tzinfo=UTC)


def _record(tmp_path):
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=DEADLINE,
        bank=4980,
        stake=30,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    return plan, {
        "activation_status": "activated",
        "plan_path": str(artifacts.plan_path),
    }


def test_evening_scheduler_status_reports_next_checkpoint_before_first_run(tmp_path):
    plan, record = _record(tmp_path)

    status = _evening_scheduler_status(
        record,
        now=datetime(2030, 1, 2, 13, 30, tzinfo=UTC),
    )

    assert status["state"] == "waiting"
    assert status["plan_id"] == plan.plan_id
    assert status["state_revision"] == 0
    assert status["terminal"] is None
    assert status["next_checkpoint"] == {
        "phase": "tls_preflight",
        "at_utc": "2030-01-02T14:00:00Z",
        "at_msk": "2030-01-02T17:00:00+03:00",
    }
    assert status["overdue_checkpoints"] == []
    assert status["phases"]["tls_preflight"] == {
        "status": "pending",
        "attempt_count": 0,
        "latest_observed_at": None,
        "latest_reason": None,
    }


def test_evening_scheduler_status_reports_completed_phase_and_next_run(tmp_path):
    plan, record = _record(tmp_path)
    state = initial_state(plan.plan_id, datetime(2030, 1, 2, 13, tzinfo=UTC))
    state = transition(
        state,
        phase="tls_preflight",
        status="complete",
        observed_at=datetime(2030, 1, 2, 14, 0, 5, tzinfo=UTC),
        attempt_id="tls-1",
        reason="TLS preflight passed",
    )
    save_state(plan.output_dir / "scheduler-state.json", state)

    status = _evening_scheduler_status(
        record,
        now=datetime(2030, 1, 2, 14, 5, tzinfo=UTC),
    )

    assert status["state"] == "running_schedule"
    assert status["state_revision"] == 1
    assert status["next_checkpoint"]["phase"] == "api_preflight"
    assert status["next_checkpoint"]["at_utc"] == "2030-01-02T14:30:00Z"
    assert status["phases"]["tls_preflight"] == {
        "status": "complete",
        "attempt_count": 1,
        "latest_observed_at": "2030-01-02T14:00:05Z",
        "latest_reason": "TLS preflight passed",
    }
    assert status["last_transition"]["phase"] == "tls_preflight"
    assert status["last_transition"]["reason"] == "TLS preflight passed"


def test_evening_scheduler_status_exposes_missed_checkpoint(tmp_path):
    _plan, record = _record(tmp_path)

    status = _evening_scheduler_status(
        record,
        now=datetime(2030, 1, 2, 14, 35, tzinfo=UTC),
    )

    assert status["state"] == "attention_required"
    assert status["overdue_checkpoints"] == [
        {"phase": "tls_preflight", "at_utc": "2030-01-02T14:00:00Z"},
        {"phase": "api_preflight", "at_utc": "2030-01-02T14:30:00Z"},
    ]
    assert status["next_checkpoint"]["phase"] == "freshness_preflight"


def test_evening_scheduler_status_is_fail_closed_for_tampered_state(tmp_path):
    plan, record = _record(tmp_path)
    path = plan.output_dir / "scheduler-state.json"
    path.write_text(
        '{"schema_version":1,"plan_id":"wrong","phases":{},'
        '"state_sha256":"bad"}',
        encoding="utf-8",
    )

    status = _evening_scheduler_status(
        record,
        now=datetime(2030, 1, 2, 13, 30, tzinfo=UTC),
    )

    assert status["state"] == "invalid"
    assert "state" in status["reason"]
    assert status["next_checkpoint"] is None
