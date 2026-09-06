"""Synthetic observer contracts; no live jobs, release or wagering."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_runner_final_input import _payload
from tests.test_scheduler_status import _plan, _write
from toto_ai.operations.scheduler_status import scheduler_status, watch_scheduler_status
from toto_ai.runner.final_input import persist_final_input

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


def primary(plan, *, native=False):
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
    if native:
        package.write_text(str(plan.stake) + ";" + ";".join("1" * 15) + "\n")
        record["package_sha256"] = hashlib.sha256(package.read_bytes()).hexdigest()
        native_chain(plan, record)
    _write(plan.output_dir / "operator-result.json", seal(record))
    return record


def native_chain(plan, record):
    """Only synthetic native-format data; never a real draw or model run."""
    run = plan.output_dir / "attempts" / record["run_id"]
    run.mkdir(parents=True, exist_ok=True)
    payload = _payload()
    payload["data"].update(
        id=plan.drawing_id, number=plan.drawing, ended_at=plan.ended_at.isoformat()
    )
    final = run / "final-input.json"
    if not final.exists():
        persist_final_input(
            payload,
            plan=plan,
            attempt_id=record["run_id"],
            captured_at=NOW - timedelta(minutes=2),
            destination=final,
            timing_override_sha256=None,
        )
    snapshot = json.loads(final.read_text())
    source = run / "package.csv"
    source.write_text("SYNTHETIC_SOURCE_NOT_FOR_WAGERING\n")
    archive = {
        "drawing_number": plan.drawing,
        "drawing_id": plan.drawing_id,
        "source_path": str(source),
        "source_bytes_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "final_input_sha256": snapshot["snapshot_sha256"],
        "probability_input_sha256": snapshot["probability_input_sha256"],
        "canonical_package_sha256": hashlib.sha256(("1" * 15).encode()).hexdigest(),
        "stake": plan.stake,
        "coupon_count": 1,
    }
    archive["archive_manifest_sha256"] = seal(archive)["record_sha256"]
    archive_path = run / "package-archive.json"
    _write(archive_path, archive)
    record.update(
        source_package_path=str(source),
        source_package_sha256=archive["source_bytes_sha256"],
        archive_manifest_path=str(archive_path),
        archive_manifest_sha256=archive["archive_manifest_sha256"],
    )
    _write(plan.output_dir / "scheduler-plan.json", plan.to_payload())


def native_ranking(plan, record):
    run = plan.output_dir / "attempts" / record["run_id"]
    snapshot = json.loads((run / "final-input.json").read_text())
    archive = json.loads((run / "package-archive.json").read_text())
    return {
        "schema_version": 1,
        "artifact_class": "PRIMARY_CONTROL_RANKING_ANALYSIS_ONLY",
        "plan_id": plan.plan_id,
        "plan_file_sha256": hashlib.sha256(
            (plan.output_dir / "scheduler-plan.json").read_bytes()
        ).hexdigest(),
        "final_input_snapshot_sha256": snapshot["snapshot_sha256"],
        "probability_input_sha256": snapshot["probability_input_sha256"],
        "package_sha256": archive["canonical_package_sha256"],
        "operator_package_sha256": record["package_sha256"],
        "operator_control_verified": True,
        "automatic_wagering": False,
        "operator_compatible": False,
        "highest_p13_single_coupon": {
            "coupon": "1" * 15,
            "package_position": 1,
            "criterion": "maximum_probability_at_least_13",
            "reference_model": "bk",
            "probability_at_least_13": 0.01,
        },
    }


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
    control = primary(plan, native=True)
    run = plan.output_dir / "parallel-challenger/output/run-final-01"
    run.mkdir(parents=True, exist_ok=True)
    package = run / "selected-parallel-operator-package.txt"
    package.write_text(str(plan.stake) + ";" + ";".join("1" * 15) + "\n")
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
        "selected_package_sha256": hashlib.sha256(("1" * 15).encode()).hexdigest(),
        "selected_cost": plan.stake,
        "selection_policy_version": "synthetic-policy",
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
    copied_control = run / "operator-bk-package.txt"
    copied_control.write_bytes(Path(control["coupon_path"]).read_bytes())
    snapshot = json.loads(
        (plan.output_dir / "attempts/final-01/final-input.json").read_text()
    )
    report = {
        "plan_id": plan.plan_id,
        "drawing_number": plan.drawing,
        "drawing_id": plan.drawing_id,
        "bank": plan.requested_bank,
        "stake": plan.stake,
        "final_input_snapshot_sha256": snapshot["snapshot_sha256"],
        "baseline": {"package_sha256": release["selected_package_sha256"]},
        "highest_p13_single_coupons": {
            "quality-v3": release["highest_p13_single_coupon"]
        },
        "experimental_selection": {
            "policy_version": release["selection_policy_version"],
            "selected_strategy_id": "quality-v3",
            "selected_package_sha256": release["selected_package_sha256"],
            "candidates": [
                {
                    "strategy_id": "quality-v3",
                    "eligible": True,
                    "coupon_count": 1,
                    "cost": plan.stake,
                }
            ],
        },
    }
    report["report_sha256"] = seal(report)["record_sha256"]
    report_path = run / "research-comparison/comparison.json"
    _write(report_path, report)
    status.update(
        operator_package=str(copied_control),
        operator_package_sha256=control["package_sha256"],
        baseline_matches_operator=True,
        research_report=str(report_path),
        research_report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
    )
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
    record = primary(plan, native=True)
    ranking = native_ranking(plan, record)
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


# Independent DO-1..4 regressions: assertions retained; fixture bindings made native.
def actionable(result):
    return [event for event in result["delivery"]["events"] if event["actionable"]]


def test_primary_parent_traversal_cannot_escape_bound_output(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan)
    outside = tmp_path / "outside-package.txt"
    outside.write_text("SYNTHETIC_OUTSIDE_BOUND_OUTPUT\n")
    record["coupon_path"] = str(plan.output_dir / ".." / outside.name)
    record["package_sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    _write(plan.output_dir / "operator-result.json", seal(record))
    result = scheduler_status(plan, observed_at=NOW)
    assert actionable(result) == [], "outside-output bytes became READY_PRIMARY"


def test_delivery_receipt_symlink_must_not_overwrite_primary(tmp_path):
    plan = _plan(tmp_path)
    primary(plan)
    authority = plan.output_dir / "operator-result.json"
    before = authority.read_bytes()
    latest = plan.output_dir / "status-watch/latest.json"
    latest.parent.mkdir()
    receipt = latest.with_name("delivery-ready.json")
    receipt.symlink_to(authority)
    try:
        watch_scheduler_status(
            plan,
            latest_path=latest,
            history_path=latest.with_name("history.jsonl"),
            max_iterations=1,
            status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
        )
    except ValueError:
        pass
    assert authority.read_bytes() == before, (
        "observer overwrote canonical operator-result"
    )
    assert receipt.is_symlink(), "review should not replace an unsafe link"


def test_parallel_mismatched_primary_control_hash_is_not_actionable(tmp_path):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    control_copy = run / "operator-bk-package.txt"
    control_copy.write_text("SYNTHETIC_OTHER_PRIMARY\n")
    status["operator_package"] = str(control_copy)
    status["operator_package_sha256"] = hashlib.sha256(
        control_copy.read_bytes()
    ).hexdigest()
    _write(run.parent / "sidecar-status.json", seal(status))
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in actionable(result)] == ["READY_PRIMARY"]


@pytest.mark.parametrize(
    "fault", ["substituted_input", "substituted_report", "foreign_input_hash"]
)
def test_parallel_changed_final_input_chain_is_not_actionable(tmp_path, fault):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    input_dir = plan.output_dir / "attempts" / "final-01"
    input_dir.mkdir(parents=True, exist_ok=True)
    final_input = input_dir / "final-input.json"
    final_input.write_text('{"synthetic_snapshot": 1}\n')
    report_path = run / "research-comparison/comparison.json"
    report = {
        "plan_id": plan.plan_id,
        "drawing_number": plan.drawing,
        "drawing_id": plan.drawing_id,
        "final_input_snapshot_sha256": hashlib.sha256(
            final_input.read_bytes()
        ).hexdigest(),
    }
    if fault == "foreign_input_hash":
        report["final_input_snapshot_sha256"] = "0" * 64
    _write(report_path, seal(report))
    status["research_report"] = str(report_path)
    status["research_report_sha256"] = hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()
    _write(run.parent / "sidecar-status.json", seal(status))
    if fault == "substituted_input":
        final_input.write_text('{"synthetic_snapshot": 2}\n')
    if fault == "substituted_report":
        report["final_input_snapshot_sha256"] = "0" * 64
        _write(report_path, seal(report))
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in actionable(result)] == ["READY_PRIMARY"]


def test_primary_ranking_wrong_final_input_not_presented_as_bound(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan)
    ranking = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "operator_package_sha256": record["package_sha256"],
        "operator_control_verified": True,
        "final_input_snapshot_sha256": "0" * 64,
        "highest_p13_single_coupon": {
            "coupon": "1" * 15,
            "package_position": 1,
            "criterion": "maximum_probability_at_least_13",
            "reference_model": "bk",
            "probability_at_least_13": 0.99,
        },
    }
    path = (
        plan.output_dir
        / "parallel-challenger/output/run-final-01"
        / "research-comparison/primary-bk-ranking.json"
    )
    _write(path, seal(ranking))
    result = scheduler_status(plan, observed_at=NOW)
    assert actionable(result)[0]["highest_p13_single_coupon"] is None


def test_native_primary_ranking_schema_is_consumed(tmp_path):
    plan = _plan(tmp_path)
    record = primary(plan, native=True)
    proof = native_ranking(plan, record)
    path = (
        plan.output_dir
        / "parallel-challenger/output/run-final-01"
        / "research-comparison/primary-bk-ranking.json"
    )
    _write(path, seal(proof))
    result = scheduler_status(plan, observed_at=NOW)
    event = actionable(result)[0]
    assert event["highest_p13_single_coupon"] == proof["highest_p13_single_coupon"]


@pytest.mark.parametrize("elapsed", [0, 1, 3600])
def test_both_stale_true_publications_expire_without_writer(tmp_path, elapsed):
    plan = _plan(tmp_path)
    run, _, _ = parallel(plan)
    paths = [
        plan.output_dir / "operator-result.json",
        run / "parallel-operator-result.json",
        run.parent / "sidecar-status.json",
    ]
    before = {p: p.read_bytes() for p in paths}
    result = scheduler_status(plan, observed_at=EXPIRED + timedelta(seconds=elapsed))
    assert actionable(result) == []
    assert result["operator_result"]["actionable"] is False
    assert result["watch_complete"] is True
    assert result["delivery"]["delivery_confirmed"] is False
    assert before == {p: p.read_bytes() for p in paths}


def test_new_parallel_detected_before_watcher_exit(tmp_path):
    plan = _plan(tmp_path)
    primary(plan)
    latest = plan.output_dir / "status-watch/latest.json"
    receipt = latest.with_name("delivery-ready.json")
    observed = []
    exited = False

    def sleep(_):
        assert exited is False
        ready = json.loads(receipt.read_text())
        observed.append([event["event"] for event in ready["events"]])
        assert ready["delivery_confirmed"] is False
        if len(observed) == 1:
            parallel(plan)

    watch_scheduler_status(
        plan,
        latest_path=latest,
        history_path=latest.with_name("history.jsonl"),
        max_iterations=3,
        status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
        sleep=sleep,
    )
    exited = True
    assert observed == [["READY_PRIMARY"], ["READY_PRIMARY", "READY_PARALLEL"]]


def test_same_sidecar_old_run_fails_open_to_current_primary(tmp_path):
    plan = _plan(tmp_path)
    parallel(plan)
    record = primary(plan)
    record["run_id"] = "final-02"
    _write(plan.output_dir / "operator-result.json", seal(record))
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in actionable(result)] == ["READY_PRIMARY"]


def test_direct_package_byte_substitution_rejected(tmp_path):
    plan = _plan(tmp_path)
    run, _, _ = parallel(plan)
    (run / "selected-parallel-operator-package.txt").write_text("SYNTHETIC_CHANGED\n")
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in actionable(result)] == ["READY_PRIMARY"]


def test_correct_receipt_uses_atomic_replace_before_latest(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    primary(plan)
    latest = plan.output_dir / "status-watch/latest.json"
    replacement = []
    real_replace = os.replace

    def replace(path, target, **kwargs):
        assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]
        assert isinstance(kwargs["src_dir_fd"], int)
        replacement.append((Path(path).name, Path(target).name))
        return real_replace(path, target, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    watch_scheduler_status(
        plan,
        latest_path=latest,
        history_path=latest.with_name("history.jsonl"),
        max_iterations=1,
        status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
    )
    assert replacement[:2] == [
        (".delivery-ready.json.tmp", "delivery-ready.json"),
        (".latest.json.tmp", "latest.json"),
    ]
    assert not list(latest.parent.glob("*.tmp"))


@pytest.mark.parametrize(
    "key",
    [
        "probability_input_sha256",
        "final_input_snapshot_sha256",
        "plan_file_sha256",
        "package_sha256",
        "operator_package_sha256",
    ],
)
def test_native_ranking_rejects_each_changed_binding(tmp_path, key):
    plan = _plan(tmp_path)
    record = primary(plan, native=True)
    proof = native_ranking(plan, record)
    proof[key] = "0" * 64
    path = (
        plan.output_dir
        / "parallel-challenger/output/run-final-01/research-comparison"
        / "primary-bk-ranking.json"
    )
    _write(path, seal(proof))
    event = actionable(scheduler_status(plan, observed_at=NOW))[0]
    assert event["event"] == "READY_PRIMARY"
    assert event["highest_p13_single_coupon"] is None


@pytest.mark.parametrize(
    "fault",
    [
        "input_bytes",
        "snapshot_resealed",
        "report_bytes",
        "report_resealed",
        "ranking",
        "archive",
        "control",
    ],
)
def test_native_chain_rejects_each_substitution(tmp_path, fault):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    attempt = plan.output_dir / "attempts/final-01"
    report_path = Path(status["research_report"])
    if fault in {"input_bytes", "snapshot_resealed"}:
        path = attempt / "final-input.json"
        data = json.loads(path.read_text())
        data["payload"]["data"]["events"][0]["quotes"]["bk_win_1"] = 99
        if fault == "snapshot_resealed":
            data.pop("snapshot_sha256")
            data["snapshot_sha256"] = seal(data)["record_sha256"]
        _write(path, data)
    elif fault in {"report_bytes", "report_resealed"}:
        data = json.loads(report_path.read_text())
        data["final_input_snapshot_sha256"] = "0" * 64
        if fault == "report_resealed":
            data.pop("report_sha256")
            data["report_sha256"] = seal(data)["record_sha256"]
            _write(report_path, data)
            status["research_report_sha256"] = hashlib.sha256(
                report_path.read_bytes()
            ).hexdigest()
            _write(run.parent / "sidecar-status.json", seal(status))
        else:
            _write(report_path, data)
    elif fault == "ranking":
        release["highest_p13_single_coupon"]["probability_at_least_13"] = 0.9
        _write(run / "parallel-operator-result.json", seal(release))
        status["parallel_release"] = seal(release)
        _write(run.parent / "sidecar-status.json", seal(status))
    elif fault == "archive":
        (attempt / "package-archive.json").write_text("{}")
    else:
        Path(status["operator_package"]).write_text("SYNTHETIC_SUBSTITUTION")
    result = scheduler_status(plan, observed_at=NOW)
    assert [e["event"] for e in actionable(result)] == ["READY_PRIMARY"]


@pytest.mark.parametrize(
    "kind", ["parent_alias", "broken_receipt", "temporary", "history"]
)
def test_watcher_never_follows_write_symlinks(tmp_path, kind):
    plan = _plan(tmp_path)
    primary(plan)
    authority = plan.output_dir / "operator-result.json"
    before = authority.read_bytes()
    folder = plan.output_dir / "watcher"
    folder.mkdir()
    latest = folder / "latest.json"
    if kind == "parent_alias":
        alias = plan.output_dir / "alias"
        alias.symlink_to(folder, target_is_directory=True)
        latest = alias / "latest.json"
    else:
        name = {
            "broken_receipt": "delivery-ready.json",
            "temporary": ".delivery-ready.json.tmp",
            "history": "history.jsonl",
        }[kind]
        (folder / name).symlink_to(
            authority if kind != "broken_receipt" else folder / "missing.json"
        )
    with pytest.raises(ValueError):
        watch_scheduler_status(
            plan,
            latest_path=latest,
            history_path=latest.with_name("history.jsonl"),
            max_iterations=1,
            status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
        )
    assert authority.read_bytes() == before


def test_atomic_parent_swap_cannot_redirect_write(tmp_path, monkeypatch):
    from toto_ai.operations.scheduler_status import _atomic_text

    folder = tmp_path / "watcher"
    folder.mkdir()
    other = tmp_path / "foreign"
    other.mkdir()
    protected = other / "delivery-ready.json"
    protected.write_text("SYNTHETIC_PROTECTED")
    before = protected.read_bytes()
    real_replace = os.replace
    pinned = tmp_path / "pinned"

    def swap(src, dst, **kwargs):
        folder.rename(pinned)
        folder.symlink_to(other, target_is_directory=True)
        return real_replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", swap)
    _atomic_text(folder / "delivery-ready.json", "SYNTHETIC_RECEIPT")
    assert protected.read_bytes() == before
    assert (pinned / "delivery-ready.json").read_text() == "SYNTHETIC_RECEIPT"


# DO-1b: exact independent hardlink-race regression, assertions unchanged.
def test_history_append_hardlink_swap_cannot_modify_authority(tmp_path, monkeypatch):
    plan = _plan(tmp_path)
    primary(plan)
    authority = plan.output_dir / "operator-result.json"
    before = authority.read_bytes()
    folder = plan.output_dir / "status-watch"
    folder.mkdir()
    latest, history = folder / "latest.json", folder / "history.jsonl"
    history.write_text("")
    real_open = os.open
    swapped = []

    def opening(path, flags, *args, **kwargs):
        if path == history.name and flags & os.O_APPEND:
            history.unlink()
            os.link(authority, history)
            swapped.append(True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opening)
    try:
        watch_scheduler_status(
            plan,
            latest_path=latest,
            history_path=history,
            max_iterations=1,
            status_provider=lambda _: scheduler_status(plan, observed_at=NOW),
        )
    except (OSError, ValueError):
        pass
    assert swapped == [True]
    assert authority.read_bytes() == before, (
        "history append modified canonical authority"
    )


@pytest.mark.parametrize("kind", ["single_link_replacement", "missing_hardlink"])
def test_history_append_requires_intended_inode_or_exclusive_create(
    tmp_path, monkeypatch, kind
):
    from toto_ai.operations.scheduler_status import _append_text

    history = tmp_path / "history.jsonl"
    authority = tmp_path / "authority.json"
    authority.write_text("SYNTHETIC_PROTECTED")
    before = authority.read_bytes()
    replacement = tmp_path / "replacement.json"
    replacement.write_text("SYNTHETIC_OTHER_SINGLE_LINK")
    other_before = replacement.read_bytes()
    if kind == "single_link_replacement":
        history.write_text("ORIGINAL_HISTORY")
    real_open = os.open
    opened = []
    swapped = []

    def opening(path, flags, *args, **kwargs):
        if path == history.name and flags & os.O_APPEND:
            if kind == "single_link_replacement":
                os.replace(replacement, history)
            else:
                os.link(authority, history)
            swapped.append(True)
            descriptor = real_open(path, flags, *args, **kwargs)
            opened.append(descriptor)
            return descriptor
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opening)
    with pytest.raises((ValueError, FileExistsError)):
        _append_text(history, "MUST_NOT_BE_APPENDED")
    assert swapped == [True]
    assert authority.read_bytes() == before
    assert history.read_bytes() == (
        other_before if kind == "single_link_replacement" else before
    )
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)
