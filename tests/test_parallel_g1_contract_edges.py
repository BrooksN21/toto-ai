from __future__ import annotations

import copy
import json
import time

import pytest

from toto_ai.optimizer import exact_maximin_refinement as core
from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.package.audit import PackageSafetyConfig
from toto_ai.sports_stats import parallel_g1


@pytest.fixture
def positive_result():
    initial = ("X" * 15, "1" * 15, "2" * 15, "1X" * 7 + "1")
    return {
        "initial_coupons": initial,
        "control_coupons": initial,
        "candidate_coupons": (*initial, "X1" * 7 + "X"),
        "probability_models": {"bk": ((0.5, 0.3, 0.2),) * 15},
        "exposure_constraints": ExposureConstraints(
            ((1, 1, 1),) * 15, ((2, 2, 2),) * 15,
        ),
        "input_sha256": "a" * 64, "plan_sha256": "b" * 64,
        "bank": 120, "effective_budget": 120, "stake": 30,
        "safety_config": PackageSafetyConfig(),
        "deadline": time.monotonic() + 30,
    }, None


def test_requested61_effective60_survive_caller_and_worker(positive_result):
    original_args, _ = positive_result
    initial = ("X" * 15, "1" * 15)
    args = {
        **original_args,
        "initial_coupons": initial,
        "control_coupons": initial,
        "candidate_coupons": (*initial, "2" * 15),
        "bank": 61,
        "effective_budget": 60,
        "deadline": time.monotonic() + 30,
        "exposure_constraints": ExposureConstraints(
            ((0, 0, 0),) * 15,
            ((2, 2, 2),) * 15,
        ),
    }
    result = parallel_g1.run_parallel_g1(
        **args,
        config=parallel_g1.ParallelG1Config(reserve_seconds=1),
    )
    assert result["status"] == "UNCHANGED"
    assert result["binding"]["bank"] == 61
    assert result["binding"]["effective_budget"] == 60
    assert result["engine"]["budget_summary"]["cost"] == 60


def test_provisional_improvement_is_rolled_back_at_evaluation_budget(positive_result):
    args, _ = positive_result
    result = parallel_g1.run_parallel_g1(
        **{**args, "deadline": time.monotonic() + 30},
        config=parallel_g1.ParallelG1Config(
            max_swap_evaluations=4,
            max_accepted_swaps=2,
            reserve_seconds=1,
        ),
    )
    assert result["status"] == "BUDGET_EXHAUSTED"
    assert result["engine"]["provisional_swap_count"] == 1
    assert result["engine"]["accepted_swap_count"] == 0
    assert result["selected_coupons"] == list(args["initial_coupons"])


def test_diagnostics_do_not_add_exact_projections_or_change_semantic_hash(
    positive_result,
    monkeypatch,
):
    args, _ = positive_result
    requests = []

    def capture(command, **kwargs):
        requests.append(json.loads(kwargs["input"]))
        raise OSError("capture only, no worker")

    monkeypatch.setattr(parallel_g1.subprocess, "run", capture)
    parallel_g1.run_parallel_g1(
        **{**args, "deadline": time.monotonic() + 30},
        config=parallel_g1.ParallelG1Config(reserve_seconds=1),
    )
    original = core.ExactCategoryCoverage.probabilities_after_swap
    calls = [0]

    def projection(self, *args, **kwargs):
        calls[0] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        core.ExactCategoryCoverage, "probabilities_after_swap", projection
    )
    results = []
    for enabled in (False, True):
        request = copy.deepcopy(requests[0])
        request["runtime_contract"]["diagnostics"] = enabled
        calls[0] = 0
        document = parallel_g1._worker(request)
        results.append((document["engine"]["semantic_hash"], calls[0]))
    assert results[0] == results[1]
    assert results[0][1] > 0
