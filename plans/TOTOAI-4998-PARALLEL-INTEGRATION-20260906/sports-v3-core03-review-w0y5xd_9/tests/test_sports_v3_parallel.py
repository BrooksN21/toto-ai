import importlib.util
import json
import subprocess
import time
from copy import deepcopy
from pathlib import Path

import pytest

from toto_ai.sports_stats import v3_parallel as parallel
from toto_ai.sports_stats import v3_probability as v3

_spec = importlib.util.spec_from_file_location(
    "v3_core_fixtures", Path(__file__).with_name("test_sports_v3_probability.py")
)
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
feature, fit = _fixtures.feature, _fixtures.fit


def request():
    rows = [
        v3.seal(
            {**feature(10, i), "drawing_id": 100, "scheduler_plan_sha256": "e" * 64}
        )
        for i in range(15)
    ]
    bundle = parallel.feature_bundle(
        rows,
        drawing_id=100,
        drawing_number=10,
        drawing_fingerprint="f" * 64,
        scheduler_plan_sha256="e" * 64,
    )
    model = fit()
    return {
        "model": model,
        "features": bundle,
        "expected_model_sha256": model["sha256"],
        "expected_training_sha256": model["training_sha256"],
        "expected_training_manifest_sha256": model["training_manifest_sha256"],
    }


def context():
    return {
        "drawing_id": 100,
        "drawing_number": 10,
        "drawing_fingerprint": "f" * 64,
        "scheduler_plan_sha256": "e" * 64,
        "final_input_sha256": "d" * 64,
        "captured_at": feature(10)["bk_captured_at"],
        "event_ids": [f"10-{i}" for i in range(15)],
        "bk_probabilities": [[0.2, 0.3, 0.5]] * 15,
        "bk_margins": [None] * 15,
    }


def test_version_aware_rebase_not_v2_blending():
    inputs, final = request(), context()
    prediction = parallel.infer_final_bk(inputs, final)
    assert prediction["model_version"] == v3.MODEL_VERSION
    assert prediction["final_input_sha256"] == "d" * 64
    for row, expected_input in zip(
        prediction["events"], inputs["features"]["rows"], strict=True
    ):
        expected = v3.infer_v3(
            inputs["model"],
            expected_input,
            bk_probabilities=final["bk_probabilities"][0],
            bk_input_sha256="d" * 64,
        )
        assert row["probabilities"] == expected["probabilities"]
        assert row["bk_probabilities"] == final["bk_probabilities"][0]


def test_independent_expected_receipt_rejects_new_self_sealed_model():
    inputs = request()
    inputs["model"] = v3.seal(
        {**inputs["model"], "prediction_as_of": "2025-01-10T00:00:00+00:00"}
    )
    with pytest.raises(ValueError, match="receipt binding"):
        parallel.infer_final_bk(inputs, context())


@pytest.mark.parametrize(
    "fault",
    ["version", "hash", "drawing", "fingerprint", "plan", "orientation", "late"],
)
def test_foreign_or_unbound_v3_is_rejected(fault):
    inputs, final = request(), context()
    if fault == "version":
        inputs["model"] = v3.seal({**inputs["model"], "model_version": "sports-v2"})
    elif fault == "hash":
        inputs["features"]["rows"][0]["features"]["home_rolling_ppg"] = 999
    elif fault == "orientation":
        final["event_ids"][0], final["event_ids"][1] = (
            final["event_ids"][1],
            final["event_ids"][0],
        )
    elif fault == "late":
        final["captured_at"] = "2025-01-01T00:00:00+00:00"
    else:
        key = {
            "drawing": "drawing_number",
            "fingerprint": "drawing_fingerprint",
            "plan": "scheduler_plan_sha256",
        }[fault]
        final[key] = 11 if fault == "drawing" else "0" * 64
    with pytest.raises(ValueError):
        parallel.infer_final_bk(inputs, final)


def test_optional_timeout_and_default_off_preserve_control(monkeypatch):
    packages = {name: ("1" * 15, "X" * 15) for name in parallel.STRATEGIES}
    original = deepcopy(packages)
    calls = []

    def timed_out(command, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(parallel.subprocess, "run", timed_out)
    result = parallel.run_v3_parallel_research(
        None, context=context(), packages=packages, deadline=time.monotonic() + 60
    )
    assert result["status"] == "DISABLED" and not calls
    result = parallel.run_v3_parallel_research(
        request(), context=context(), packages=packages, deadline=time.monotonic() + 60
    )
    assert result["status"] == "CONTROL_FALLBACK"
    assert len(calls) == 1 and calls[0]["timeout"] <= 5
    assert packages == original
    assert result["operator_compatible"] is False


def test_native_worker_is_research_only_and_keeps_four_strategy_ids():
    packages = {name: ("1" * 15, "X" * 15) for name in parallel.STRATEGIES}
    result = parallel.run_v3_parallel_research(
        request(), context=context(), packages=packages, deadline=time.monotonic() + 60
    )
    assert result["status"] == "COMPLETE_EXPERIMENTAL_NO_SELECTION"
    assert set(result["candidate_metrics"]) == set(parallel.STRATEGIES)
    assert all(
        "probability_at_least_13" in r for r in result["candidate_metrics"].values()
    )
    assert result["control_preserved"] is True
    assert result["operator_compatible"] is False
    assert "selected_coupons" not in json.dumps(result)
