from datetime import datetime, timezone

from toto_ai.runner.scheduler_state import (
    initial_state,
    load_state,
    recover_orphan,
    save_state,
    transition,
)

NOW = datetime(2032, 1, 1, tzinfo=timezone.utc)


def test_state_round_trip_and_orphan_recovery(tmp_path):
    path = tmp_path / "state.json"
    state = initial_state("plan", NOW)
    state = transition(
        state,
        phase="final",
        status="running",
        observed_at=NOW,
        attempt_id="attempt-1",
    )
    save_state(path, state)

    recovered = recover_orphan(load_state(path, plan_id="plan", now=NOW), NOW)

    assert recovered["phases"]["final"]["status"] == "retryable_failed"
    assert recovered["phases"]["final"]["attempts"] == ["attempt-1"]
    assert recovered["transitions"][-1]["reason"] == "orphaned_running_attempt"
