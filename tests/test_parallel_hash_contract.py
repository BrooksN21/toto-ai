"""Native writer -> delivery consumer, with no generator or live artifacts."""

import hashlib
import json
from dataclasses import make_dataclass
from types import SimpleNamespace

import pytest

from tests.test_scheduler_delivery import NOW, parallel, seal
from tests.test_scheduler_status import _plan, _write
from toto_ai.operations.scheduler_delivery import _coupons
from toto_ai.operations.scheduler_status import scheduler_status
from toto_ai.optimizer.strategy_comparison import _package_sha256
from toto_ai.package.hash_contract import ordered_comma_sha256, validate_baseline_hashes
from toto_ai.sports_stats.final_hybrid_comparison import _result_payload


def native_baseline(coupons):
    return _result_payload(
        SimpleNamespace(
            coupons=coupons,
            coupon_count=len(coupons),
            cost=len(coupons) * 30,
            unused_bank=0,
            package_sha256=_package_sha256(coupons),
            runtime_seconds=0,
            probability_at_least_13=0.1,
            probability_at_least_14=0.01,
            probability_at_least_15=0.001,
        ),
        make_dataclass("SyntheticQuality", [])(),
    )


def case(tmp_path, *, legacy=False, fault=None):
    plan = _plan(tmp_path)
    run, release, status = parallel(plan)
    path = run / "research-comparison/comparison.json"
    report = json.loads(path.read_text())
    report.update(
        schema_version=1,
        artifact_class="FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON",
    )
    report["baseline"] = native_baseline(("1" * 15,))
    if legacy:
        report["baseline"].pop("package_sha256_semantics", None)
        report["baseline"].pop("canonical_package_sha256", None)
        report["baseline"].pop("canonical_package_sha256_semantics", None)
    if fault == "wrong_final_input":
        report["final_input_snapshot_sha256"] = "0" * 64
    if fault == "wrong_plan":
        report["plan_id"] = "0" * 16
    if fault == "alternate_hash":
        report["baseline"]["package_sha256"] = hashlib.sha256(
            ("1" * 15).encode()
        ).hexdigest()
    if fault == "unknown_semantics":
        report["baseline"]["package_sha256_semantics"] = "anything"
    report.pop("report_sha256", None)
    report["report_sha256"] = seal(report)["record_sha256"]
    _write(path, report)
    status["research_report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if fault == "wrong_filehash":
        status["research_report_sha256"] = "0" * 64
    if fault == "tampered_coupon":
        (run / "operator-bk-package.txt").write_text("30;" + ";".join("2" * 15) + "\n")
    _write(run.parent / "sidecar-status.json", seal(status))
    return plan


@pytest.mark.parametrize("legacy", [False, True])
def test_native_writer_report_passes_delivery(tmp_path, legacy):
    result = scheduler_status(case(tmp_path, legacy=legacy), observed_at=NOW)
    assert not result["delivery"]["blockers"]
    assert [e["event"] for e in result["delivery"]["events"]] == [
        "READY_PRIMARY",
        "READY_PARALLEL",
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_final_input",
        "wrong_plan",
        "wrong_filehash",
        "tampered_coupon",
        "alternate_hash",
        "unknown_semantics",
    ],
)
def test_invalid_parallel_never_hides_valid_primary(tmp_path, fault):
    result = scheduler_status(case(tmp_path, fault=fault), observed_at=NOW)
    assert result["delivery"]["blockers"]
    assert [e["event"] for e in result["delivery"]["events"] if e["actionable"]] == [
        "READY_PRIMARY"
    ]


@pytest.mark.parametrize("legacy", [False, True])
def test_order_sensitive_hashes_reject_reordered_or_modified_control(legacy):
    coupons = ("1" * 15, "X" * 15)
    report = {
        "schema_version": 1,
        "artifact_class": "FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON",
        "baseline": native_baseline(coupons),
    }
    if legacy:
        for key in (
            "package_sha256_semantics",
            "canonical_package_sha256",
            "canonical_package_sha256_semantics",
        ):
            report["baseline"].pop(key)
    canonical = ordered_comma_sha256(coupons)
    validate_baseline_hashes(report, coupons, canonical)
    for changed in (coupons[::-1], ("2" * 15, coupons[1])):
        with pytest.raises(ValueError):
            validate_baseline_hashes(report, changed, canonical)
        # Even re-signing the archive does not excuse a different ordered report.
        with pytest.raises(ValueError):
            validate_baseline_hashes(report, changed, ordered_comma_sha256(changed))


def test_native_space_delimited_export_roundtrips_reader(tmp_path):
    from toto_ai.sports_stats.final_hybrid_sidecar import _operator_package_bytes

    plan = _plan(tmp_path)
    coupons = ("1" * 15, "X" * 15)
    path = plan.output_dir / "native-export.txt"
    path.write_bytes(_operator_package_bytes(30, coupons))
    assert _coupons(path, plan) == coupons
    path.write_bytes(_operator_package_bytes(30, (coupons[0], coupons[0])))
    with pytest.raises(ValueError, match="duplicate"):
        _coupons(path, plan)


def test_explicit_null_semantics_is_not_legacy():
    coupons = ("1" * 15,)
    report = {"baseline": native_baseline(coupons)}
    report["baseline"]["package_sha256_semantics"] = None
    with pytest.raises(ValueError, match="semantics"):
        validate_baseline_hashes(report, coupons, ordered_comma_sha256(coupons))
