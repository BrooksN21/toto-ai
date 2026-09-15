"""F4-1: self-sealing foreign fitted state does not establish train-only origin."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from toto_ai.sports_stats import v3_f4 as driver
from toto_ai.sports_stats import v3_f4_gate as gate
from toto_ai.sports_stats import v3_probability as v3

_spec = importlib.util.spec_from_file_location(
    "f4_fit_binding_fixtures", Path(__file__).with_name("test_sports_v3_f4.py")
)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    folds, labels, receipt = fixtures.protocol(4)
    return driver.run_f4(
        folds,
        output_dir=tmp_path_factory.mktemp("f4-fit-binding"),
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )


def changed_report(report, field):
    result = deepcopy(report)
    item = result["folds"][-1]
    prediction = item["prediction"]
    model = prediction["models"]["A4"]
    if field in ("feature_sha256", "label_sha256"):
        model["training_rows"][0][field] = "0" * 64
        model["training_manifest_sha256"] = v3.digest(model["training_rows"])
    elif field == "transform":
        model["transform"]["means"][0] += 1000
    elif field == "weights":
        model["weights"][0][0] += 1
        model["weights"][0][1] -= 1
    else:
        model["draw_calibrator"]["weights"][0] += 1
    model = v3.seal(model)
    prediction["models"]["A4"] = model
    for event, row in zip(
        prediction["events"], prediction["input"]["features"], strict=True
    ):
        event["A4"] = v3.infer_v3(model, row)
    item["prediction"] = v3.seal(prediction)
    item["prediction_file_sha256"] = driver.bytes_hash(item["prediction"])
    return v3.seal(result)


@pytest.mark.parametrize("entry", ["prediction", "gate"])
@pytest.mark.parametrize(
    "field",
    ["feature_sha256", "label_sha256", "transform", "weights", "draw_calibrator"],
)
def test_true_declared_digest_cannot_authorize_foreign_fitted_state(
    report, field, entry
):
    changed = changed_report(report, field)
    assert (
        changed["folds"][-1]["prediction"]["models"]["A4"]["training_sha256"]
        == (report["folds"][-1]["prediction"]["models"]["A4"]["training_sha256"])
    )
    with pytest.raises(ValueError, match="deterministic earlier-only fitted model"):
        if entry == "prediction":
            driver.validate_prediction(
                changed["folds"][-1]["prediction"], changed["folds"][:-1]
            )
        else:
            gate.build_f4_gate(changed)


def test_independent_refit_receives_only_fixed_config_and_exact_earlier_rows(
    report, monkeypatch
):
    seen = []
    original = driver.train_v3

    def tracked(records, **kwargs):
        seen.append((deepcopy(records), dict(kwargs)))
        return original(records, **kwargs)

    monkeypatch.setattr(driver, "train_v3", tracked)
    before = deepcopy(report)
    driver.validate_prediction(report["folds"][-1]["prediction"], report["folds"][:-1])
    assert report == before
    expected = driver.training_records(
        report["folds"][:-1], report["folds"][-1]["prediction"]["input"]["as_of"]
    )
    assert len(seen) == 4
    for records, config in seen:
        assert records == expected
        assert {r["features"]["drawing_number"] for r in records} == {1, 2, 3}
        assert config["target_drawing"] == 4
        assert config["l2"] == 0.1 and config["steps"] == 240
        assert 0 < config["time_budget_seconds"] <= 5


def test_independent_verification_timeout_is_rejection_not_fitted_state_acceptance(
    report, monkeypatch
):
    monkeypatch.setattr(
        driver, "train_v3", lambda *a, **k: {"status": "FIT_BUDGET_EXHAUSTED"}
    )
    with pytest.raises(ValueError, match="verification budget exhausted"):
        driver.validate_prediction(
            report["folds"][-1]["prediction"], report["folds"][:-1]
        )


@pytest.mark.parametrize("phase", ["last_refit", "last_inference", "last_baseline"])
@pytest.mark.parametrize("completed_at", [4.999, 5.0, 6.0])
def test_final_operation_must_complete_strictly_before_deadline(
    report, monkeypatch, phase, completed_at
):
    clock = [0.0]
    baseline_checks = []
    late_inferences = []
    original_fit = driver.train_v3
    original_infer = driver.infer_v3
    original_check = driver._check
    monkeypatch.setattr(driver.time, "monotonic", lambda: clock[0])

    def fit(records, **kwargs):
        result = original_fit(records, **kwargs)
        if phase == "last_refit" and kwargs["variant"] == "A5":
            clock[0] = completed_at
        return result

    def infer(model, row):
        if clock[0] >= 5.0:
            late_inferences.append(row["event_order"])
        result = original_infer(model, row)
        if (
            phase == "last_inference"
            and model["variant"] == "A5"
            and row["event_order"] == 14
        ):
            clock[0] = completed_at
        return result

    def check(condition, message):
        original_check(condition, message)
        if phase == "last_baseline" and message == "untouched A0/A1":
            baseline_checks.append(message)
            if len(baseline_checks) == 15:
                clock[0] = completed_at

    monkeypatch.setattr(driver, "train_v3", fit)
    monkeypatch.setattr(driver, "infer_v3", infer)
    monkeypatch.setattr(driver, "_check", check)
    prediction, previous = report["folds"][-1]["prediction"], report["folds"][:-1]
    if completed_at >= 5.0:
        with pytest.raises(ValueError, match="verification budget exhausted"):
            driver.validate_prediction(prediction, previous)
    else:
        driver.validate_prediction(prediction, previous)
    assert clock[0] == completed_at
    # A completed-but-late fit must reject before starting event inference.
    assert late_inferences == []
