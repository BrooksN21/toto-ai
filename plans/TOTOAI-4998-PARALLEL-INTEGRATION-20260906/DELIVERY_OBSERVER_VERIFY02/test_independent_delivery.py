"""Independent synthetic observer acceptance tests. No real coupons or jobs."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_scheduler_delivery import EXPIRED, NOW, parallel, primary, seal
from tests.test_scheduler_status import _plan, _write
from toto_ai.operations.scheduler_status import scheduler_status, watch_scheduler_status


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
    input_dir.mkdir(parents=True)
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
    record = primary(plan)
    proof = {
        "schema_version": 1,
        "artifact_class": "PRIMARY_CONTROL_RANKING_ANALYSIS_ONLY",
        "plan_id": plan.plan_id,
        "plan_file_sha256": "1" * 64,
        "final_input_snapshot_sha256": "2" * 64,
        "probability_input_sha256": "3" * 64,
        "package_sha256": "4" * 64,
        "operator_package_sha256": record["package_sha256"],
        "operator_control_verified": True,
        "highest_p13_single_coupon": {
            "coupon": "1" * 15,
            "package_position": 1,
            "criterion": "maximum_probability_at_least_13",
            "reference_model": "bk",
            "probability_at_least_13": 0.01,
        },
        "automatic_wagering": False,
        "operator_compatible": False,
    }
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
    real_replace = Path.replace

    def replace(path, target):
        replacement.append((path.name, Path(target).name))
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace)
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
