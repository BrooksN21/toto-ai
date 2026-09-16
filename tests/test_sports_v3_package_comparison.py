"""JOB B research package contract: no live admission and no historical labels."""

import hashlib
import json
import runpy
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    run_bk_probability_only,
)
from toto_ai.research import sports_v3_package_comparison as job
from toto_ai.research.closed_market_scenario_replay import extract, validate_input

FIX = runpy.run_path(
    str(Path(__file__).with_name("test_closed_market_scenario_replay.py"))
)


@pytest.fixture
def scenario(tmp_path):
    return extract(FIX["source"](tmp_path))


def test_numeric_selector_is_native_top_product_not_union_optimizer(scenario):
    p = validate_input(scenario).ev.true_probabilities
    frozen = FrozenStrategyInput(
        drawing_id=12107,
        drawing_number=5000,
        drawing_fingerprint="a" * 64,
        source_captured_at="2026-09-01T10:00:00Z",
        as_of="2026-09-01T11:00:00Z",
        ended_at="2026-09-01T12:00:00Z",
        bank=4980,
        stake=30,
        pool_sum=6_000_000,
        jackpot=1_000_000,
        possible_winnings=0,
        events=tuple(
            FrozenStrategyEvent(i, str(i), tuple(r), (0.5, 0.25, 0.25))
            for i, r in enumerate(p)
        ),
    )
    native = run_bk_probability_only(frozen, category=13)
    assert job.select_package(p) == native.coupons
    assert len(native.coupons) == len(set(native.coupons)) == 166
    with pytest.raises(ValueError, match="after as_of"):
        replace(frozen, source_captured_at="2026-09-15T00:00:00Z")


def prediction_rows(scenario):
    native = validate_input(scenario)
    return [
        dict(
            drawing_number=scenario["market"]["number"],
            event_order=i,
            target_event_id=e["id"],
            bk_input_sha256=scenario["sha256"],
            bk_probabilities=list(native.ev.true_probabilities[i]),
            probabilities=list(native.ev.true_probabilities[i]),
            status="BK_FALLBACK",
            reliability=0.0,
            feature_sha256=None,
            provider_fixture_id=None,
            fallback_or_application_reason="NO_APPROVED_FEATURES",
        )
        for i, e in enumerate(scenario["market"]["events"])
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "order",
        "source_id",
        "bk",
        "inputhash",
        "missing",
        "duplicate",
        "fallback",
        "nan",
    ],
)
def test_bound_rows_reject_mismatch(scenario, mutation):
    rows = prediction_rows(scenario)
    if mutation == "order":
        rows[0]["event_order"] = 1
    if mutation == "source_id":
        rows[0]["target_event_id"] += 1
    if mutation == "bk":
        rows[0]["bk_probabilities"] = [0.2, 0.4, 0.4]
    if mutation == "inputhash":
        rows[0]["bk_input_sha256"] = "f" * 64
    if mutation == "missing":
        rows.pop()
    if mutation == "duplicate":
        rows[-1] = deepcopy(rows[0])
    if mutation == "fallback":
        rows[0]["probabilities"] = [0.2, 0.4, 0.4]
    if mutation == "nan":
        rows[0]["probabilities"] = [float("nan"), 0.3, 0.3]
    with pytest.raises(ValueError):
        job.bind_rows(scenario, rows)


def test_all_fallback_exact_same_package(scenario):
    bk, mixed, coverage = job.bind_rows(scenario, prediction_rows(scenario))
    assert job.select_package(bk) == job.select_package(mixed)
    assert coverage["sports_applied"] == 0 and coverage["bk_fallback"] == 15


def test_partial_rows_coverage_honest(scenario):
    rows = prediction_rows(scenario)
    rows[0].update(
        probabilities=[0.45, 0.3, 0.25],
        status="SPORTS_APPLIED",
        reliability=0.1,
        feature_sha256="e" * 64,
        provider_fixture_id="realfixture",
    )
    bk, mixed, c = job.bind_rows(scenario, rows)
    assert (
        c["sports_applied"] == 1
        and c["changed_probability_rows"] == 1
        and c["bk_fallback"] == 14
    )
    assert mixed[1:] == bk[1:]


def request_fixture(tmp_path, scenario):
    def put(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return dict(
            path=str(path), file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )

    req = dict(
        kind=job.REQUEST_KIND,
        drawing_number=5000,
        scenario_input=put("input.json", scenario),
        sports_predictions=dict(
            path=str(tmp_path / "missing.json"), file_sha256="a" * 64
        ),
        selection=job.SELECTION,
        bank=4980,
        stake=30,
        category=13,
        count=166,
    )
    ref = put("request.json", req)
    return ref, put


@pytest.mark.parametrize("sports_input", ["missing", "tampered", "corrupt_json"])
def test_missing_sports_preserves_bk_control_without_fake_success(
    tmp_path, scenario, sports_input
):
    ref, put = request_fixture(tmp_path, scenario)
    if sports_input != "missing":
        request = json.loads(Path(ref["path"]).read_text())
        sports_path = tmp_path / "invalid-sports.json"
        sports_path.write_text("{broken" if sports_input == "corrupt_json" else "{}")
        request["sports_predictions"] = dict(
            path=str(sports_path),
            file_sha256=(
                hashlib.sha256(sports_path.read_bytes()).hexdigest()
                if sports_input == "corrupt_json"
                else "a" * 64
            ),
        )
        ref = put("request.json", request)
    result = job.compare_frozen_predictions(
        ref["path"],
        tmp_path / "out",
        max_seconds=5,
        expected_request_sha256=ref["file_sha256"],
        root=tmp_path,
    )
    assert result["sports_status"] == "SKIPPED_MISSING_OR_INVALID_SPORTS"
    assert set(result["packages"]) == {"BK"}
    assert result["packages"]["BK"]["count"] == 166
    assert result["status"] == "BK_CONTROL_ONLY_SPORTS_SKIPPED"
    assert set(result["evaluations"]) == {"BK"}
    assert not (tmp_path / "out" / "MIXED_V3.json").exists()
    assert not (tmp_path / "out" / "operator-result.json").exists()
    assert all(result[key] is False for key in job.FLAGS)
    saved = json.loads((tmp_path / "out" / "comparison.json").read_text())
    assert saved == json.loads(json.dumps(result))
    job._sealed(saved)
    package_ref = result["packages"]["BK"]
    package_path = Path(package_ref["path"])
    assert (
        hashlib.sha256(package_path.read_bytes()).hexdigest()
        == package_ref["file_sha256"]
    )
    package = json.loads(package_path.read_text())
    job._sealed(package)
    assert package["sha256"] == package_ref["payload_sha256"]
    assert package["stake"] == 30 and package["cost"] == 4980
    assert len(set(package["coupons"])) == 166
    assert all(len(coupon) == 15 for coupon in package["coupons"])
    matrix = validate_input(scenario).ev.true_probabilities
    assert package["coupons"] == list(job.select_package(matrix))
    semantics = result["diagnostic_semantics"]
    assert semantics["distinct_forecast_count"] == 1
    assert semantics["api_aliases"] == {"COMMON_BK_API_ALIAS": "COMMON_BK"}
    assert semantics["alias_results_combined"] is False
    assert semantics["training_stream_used_by_selector"] is False
    metrics = result["evaluations"]["BK"]["models"]
    assert {row["model"] for row in metrics} == {"COMMON_BK", "COMMON_BK_API_ALIAS"}
    for key in ("exact_p13", "exact_p14", "exact_p15"):
        assert metrics[0][key] == metrics[1][key] > 0


def test_timeout_has_no_complete_success_or_operator_result(
    tmp_path, scenario, monkeypatch
):
    ref, _ = request_fixture(tmp_path, scenario)

    def slow(*args):
        raise TimeoutError("synthetic expiry")

    monkeypatch.setattr(job, "select_package", slow)
    out = tmp_path / "timeout"
    result = job.compare_frozen_predictions(
        ref["path"],
        out,
        max_seconds=5,
        expected_request_sha256=ref["file_sha256"],
        root=tmp_path,
    )
    assert result["status"] == "TIMED_OUT" and not result["packages"]
    assert not (out / "operator-result.json").exists()


def test_request_hash_tamper_rejected_before_work(tmp_path, scenario):
    ref, _ = request_fixture(tmp_path, scenario)
    with pytest.raises(ValueError, match="file hash"):
        job.compare_frozen_predictions(
            ref["path"],
            tmp_path / "bad",
            expected_request_sha256="0" * 64,
            root=tmp_path,
        )
    assert not (tmp_path / "bad").exists()


def test_probability_shape_and_budget_fixed():
    with pytest.raises(ValueError):
        job.select_package([[0.4, 0.3, 0.3]] * 14)
    assert job.SELECTION == "TOP_COUPON_PRODUCT_PROBABILITY"
