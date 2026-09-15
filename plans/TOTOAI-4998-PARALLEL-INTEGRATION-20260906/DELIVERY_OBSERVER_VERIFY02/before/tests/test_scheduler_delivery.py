"""Synthetic observer contracts; no live jobs, release or wagering."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.test_scheduler_status import _plan, _write
from toto_ai.operations.scheduler_status import scheduler_status, watch_scheduler_status

UTC = timezone.utc
NOW = datetime(2026, 9, 3, 15, 31, tzinfo=UTC)
EXPIRED = datetime(2026, 9, 3, 15, 45, tzinfo=UTC)


def seal(record):
    record = {k: v for k, v in record.items() if k != "record_sha256"}
    record["record_sha256"] = hashlib.sha256(
        json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return record


def primary(plan):
    package = plan.output_dir / "operator-package.txt"
    package.write_text("SYNTHETIC_NOT_FOR_WAGERING\n")
    record = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": "final-01",
        "operator_status": "FINAL_FRESH",
        "decision": "PLAY",
        "actionable": True,
        "coupon_path": str(package),
        "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "selected_count": 1,
        "selected_cost": 30,
        "completed_at": "2026-09-03T15:30:00Z",
        "expires_at": "2026-09-03T15:45:00Z",
        "automatic_wagering": False,
    }
    _write(plan.output_dir / "operator-result.json", seal(record))
    return record


def test_expired_snapshot_is_not_actionable_before_operator_rewrite(tmp_path):
    plan = _plan(tmp_path)
    primary(plan)
    before = (plan.output_dir / "operator-result.json").read_bytes()
    result = scheduler_status(plan, observed_at=EXPIRED)
    assert result["operator_result"]["actionable"] is False
    assert not result["delivery"]["actionable"]
    assert (plan.output_dir / "operator-result.json").read_bytes() == before


def test_ready_primary_is_visible_before_process_exit(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan)
    _write(
        plan.output_dir / "attempts/final-01/status.json",
        {
            "plan_id": plan.plan_id,
            "drawing": plan.drawing,
            "run_id": "final-01",
            "state": "running",
            "phase": "final",
        },
    )
    result = scheduler_status(plan, observed_at=NOW)
    event = result["delivery"]["events"][0]
    assert event["event"] == "READY_PRIMARY"
    assert event["actionable"] is True
    assert event["package_path"] == record["coupon_path"]
    assert event["record_path"] == str(plan.output_dir / "operator-result.json")
    assert result["delivery"]["delivery_confirmed"] is False


@pytest.mark.parametrize(
    "timestamp", ["2026-09-03T15:32:00Z", "invalid", "2026-09-03T15:30:00"]
)
def test_future_or_invalid_publication_never_becomes_delivery_ready(
    tmp_path, timestamp
):
    plan = _plan(tmp_path)
    record = primary(plan)
    record["completed_at"] = timestamp
    _write(plan.output_dir / "operator-result.json", seal(record))
    result = scheduler_status(plan, observed_at=NOW)
    assert result["operator_result"]["actionable"] is False
    assert not result["delivery"]["actionable"]


def parallel(plan, *, publish_status=True):
    primary(plan)
    run = plan.output_dir / "parallel-challenger/output/run-final-01"
    run.mkdir(parents=True, exist_ok=True)
    package = run / "selected-parallel-operator-package.txt"
    package.write_text("SYNTHETIC_PARALLEL_NOT_FOR_WAGERING\n")
    release = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "decision": "PLAY",
        "actionable": True,
        "automatic_wagering": False,
        "published_at": "2026-09-03T15:30:30Z",
        "expires_at": "2026-09-03T15:45:00Z",
        "selected_package_path": str(package),
        "selected_package_file_sha256": hashlib.sha256(
            package.read_bytes()
        ).hexdigest(),
        "selected_strategy_id": "quality-v3",
        "selected_coupon_count": 1,
        "highest_p13_single_coupon": {
            "coupon": "1" * 15,
            "package_position": 1,
            "criterion": "maximum_probability_at_least_13",
            "reference_model": "bk",
            "probability_at_least_13": 0.01,
        },
    }
    _write(run / "parallel-operator-result.json", seal(release))
    status = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": "final-01",
        "status": "READY_PARALLEL_PLAY_BEFORE_T10",
        "completed_at": release["published_at"],
        "parallel_release": seal(release),
    }
    if publish_status:
        _write(run.parent / "sidecar-status.json", seal(status))
    return run, release, status


def test_only_canonical_status_resolves_exact_run_companion(tmp_path):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan, publish_status=False)
    for parent in (
        plan.output_dir,
        run.parent,
        plan.output_dir / "parallel-challenger",
    ):
        _write(parent / "parallel-operator-result.json", release)
    first = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in first["delivery"]["events"]] == ["READY_PRIMARY"]
    _write(run.parent / "sidecar-status.json", seal(status))
    second = scheduler_status(plan, observed_at=NOW)
    event = next(
        e for e in second["delivery"]["events"] if e["event"] == "READY_PARALLEL"
    )
    assert event["record_path"] == str(run / "parallel-operator-result.json")
    assert event["package_path"] == release["selected_package_path"]
    assert event["highest_p13_single_coupon"] == release["highest_p13_single_coupon"]
    assert second["delivery"]["preferred_event_id"] == event["event_id"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_companion",
        "different_companion",
        "changed_package",
        "foreign_plan",
        "outside_path",
        "future",
        "extended_expiry",
    ],
)
def test_parallel_invalid_binding_never_hides_valid_primary(tmp_path, fault):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    if fault == "missing_companion":
        (run / "parallel-operator-result.json").unlink()
    elif fault == "changed_package":
        (run / "selected-parallel-operator-package.txt").write_text("changed")
    else:
        if fault == "different_companion":
            release["selected_strategy_id"] = "robust"
        elif fault == "foreign_plan":
            release["plan_id"] = "wrong"
        elif fault == "outside_path":
            release["selected_package_path"] = str(tmp_path / "outside")
        elif fault == "future":
            release["published_at"] = "2026-09-03T15:40:00Z"
        elif fault == "extended_expiry":
            release["expires_at"] = "2026-09-03T16:45:00Z"
        _write(run / "parallel-operator-result.json", seal(release))
        if fault != "different_companion":
            status["parallel_release"] = seal(release)
            _write(run.parent / "sidecar-status.json", seal(status))
    result = scheduler_status(plan, observed_at=NOW)
    assert result["delivery"]["actionable"] is True
    assert [e["event"] for e in result["delivery"]["events"] if e["actionable"]] == [
        "READY_PRIMARY"
    ]
    assert result["delivery"]["blockers"]


def test_watcher_persists_delivery_before_waiting_and_without_terminal_process(
    tmp_path,
):
    plan = _plan(tmp_path)
    primary(plan)
    latest = plan.output_dir / "status-watch/latest.json"
    history = latest.with_name("history.jsonl")
    reads = []

    def sleeping(_seconds):
        ready = json.loads(latest.with_name("delivery-ready.json").read_text())
        reads.append([e["event"] for e in ready["events"]])
        if len(reads) == 1:
            parallel(plan)

    watch_scheduler_status(
        plan,
        latest_path=latest,
        history_path=history,
        status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
        sleep=sleeping,
        max_iterations=3,
    )
    assert reads == [["READY_PRIMARY"], ["READY_PRIMARY", "READY_PARALLEL"]]
    saved = json.loads(latest.with_name("delivery-ready.json").read_text())
    assert saved["delivery_confirmed"] is False
    assert saved["notification_transport"] == "LOCAL_FILES_AND_STDOUT_ONLY"


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_id",
        "unsealed",
        "symlink_package",
        "bad_highest",
        "no_expiry",
        "sidecar_foreign",
        "sidecar_future",
    ],
)
def test_invalid_canonical_metadata_cannot_issue_parallel_ready(tmp_path, fault):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    if fault == "wrong_id":
        release["drawing_id"] += 1
    elif fault == "unsealed":
        _write(run / "parallel-operator-result.json", release)
    elif fault == "symlink_package":
        path = run / "selected-parallel-operator-package.txt"
        data = path.read_bytes()
        path.unlink()
        target = run / "other.txt"
        target.write_bytes(data)
        path.symlink_to(target)
    elif fault == "bad_highest":
        release["highest_p13_single_coupon"]["probability_at_least_13"] = True
    elif fault == "no_expiry":
        del release["expires_at"]
    elif fault == "sidecar_foreign":
        status["plan_id"] = "foreign"
    else:
        status["completed_at"] = "2026-09-03T15:32:00Z"
    if fault not in ("unsealed", "symlink_package"):
        _write(run / "parallel-operator-result.json", seal(release))
        status["parallel_release"] = seal(release)
    _write(run.parent / "sidecar-status.json", seal(status))
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in result["delivery"]["events"] if e["actionable"]] == [
        "READY_PRIMARY"
    ]


def test_delivery_event_ids_stable_and_expire_exactly_at_cutoff(tmp_path):
    plan = _plan(tmp_path)
    parallel(plan)
    from datetime import timedelta

    one = scheduler_status(plan, observed_at=NOW)
    two = scheduler_status(plan, observed_at=NOW + timedelta(seconds=1))
    expired = scheduler_status(plan, observed_at=EXPIRED)
    assert [e["event_id"] for e in one["delivery"]["events"]] == [
        e["event_id"] for e in two["delivery"]["events"]
    ]
    assert not expired["operator_result"]["actionable"]
    assert not expired["delivery"]["actionable"]
    assert all(not e["actionable"] for e in expired["delivery"]["events"])
    assert expired["watch_complete"]


def test_primary_ranking_is_only_consumed_from_exact_hash_bound_proof(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan)
    record["run_id"] = "final-01"
    _write(plan.output_dir / "operator-result.json", seal(record))
    ranking = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "operator_package_sha256": record["package_sha256"],
        "operator_control_verified": True,
        "highest_p13_single_coupon": {
            "coupon": "1" * 15,
            "package_position": 1,
            "criterion": "maximum_probability_at_least_13",
            "reference_model": "bk",
            "probability_at_least_13": 0.01,
        },
    }
    path = (
        plan.output_dir
        / "parallel-challenger/output/run-final-01/research-comparison"
        / "primary-bk-ranking.json"
    )
    _write(path, seal(ranking))
    result = scheduler_status(plan, observed_at=NOW)
    event = result["delivery"]["events"][0]
    assert event["highest_p13_single_coupon"] == ranking["highest_p13_single_coupon"]
    ranking["operator_package_sha256"] = "0" * 64
    _write(path, seal(ranking))
    result = scheduler_status(plan, observed_at=NOW)
    assert result["delivery"]["events"][0]["highest_p13_single_coupon"] is None
    assert result["delivery"]["actionable"]


def test_changed_package_never_retains_actionable_primary_summary(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan)
    Path(record["coupon_path"]).write_text("changed")
    result = scheduler_status(plan, observed_at=NOW)
    assert not result["operator_result"]["actionable"]
    assert not result["delivery"]["actionable"]


def test_previous_run_parallel_cannot_replace_new_current_primary(tmp_path):
    plan = _plan(tmp_path)
    parallel(plan)
    record = primary(plan)
    record["run_id"] = "final-02"
    _write(plan.output_dir / "operator-result.json", seal(record))
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in result["delivery"]["events"] if e["actionable"]] == [
        "READY_PRIMARY"
    ]


def test_stale_cached_delivery_contract_is_explicitly_time_limited(tmp_path):
    plan = _plan(tmp_path)
    parallel(plan)
    cached = scheduler_status(plan, observed_at=NOW)["delivery"]
    assert datetime.fromisoformat(cached["expires_at"]) == EXPIRED
    assert cached["requires_fresh_read_before_delivery"] is True
    assert cached["requires_host_delivery"] is True
    assert cached["delivery_confirmed"] is False


def test_unchanged_ready_events_do_not_repeat_history_each_poll(tmp_path):
    from datetime import timedelta

    plan = _plan(tmp_path)
    parallel(plan)
    times = iter([NOW, NOW + timedelta(seconds=1)])
    latest = plan.output_dir / "status-watch/latest.json"
    history = latest.with_name("history.jsonl")
    watch_scheduler_status(
        plan,
        latest_path=latest,
        history_path=history,
        status_provider=lambda _: scheduler_status(plan, observed_at=next(times)),
        sleep=lambda _: None,
        max_iterations=2,
    )
    assert len(history.read_text().splitlines()) == 1
    assert (
        json.loads(latest.with_name("delivery-ready.json").read_text())["observed_at"]
        == (NOW + timedelta(seconds=1)).isoformat()
    )
