"""Admission-only regressions; never replay a dense exact optimization."""

import json
import subprocess
from itertools import islice, product

import pytest

from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.package.audit import PackageSafetyConfig
from toto_ai.sports_stats import parallel_g1 as g1


def _arguments(universe=489):
    coupons = tuple("".join(c) for c in islice(product("1X2", repeat=15), universe))
    return {
        "initial_coupons": coupons[:166],
        "control_coupons": coupons[:166],
        "candidate_coupons": coupons,
        "probability_models": {
            name: ((0.2, 0.3, 0.5),) * 15
            for name in ("bk", "sports", "flatten_10", "flatten_20")
        },
        "exposure_constraints": ExposureConstraints(
            ((0, 0, 0),) * 15, ((166, 166, 166),) * 15
        ),
        "input_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "bank": 4980,
        "effective_budget": 4980,
        "stake": 30,
        "safety_config": PackageSafetyConfig(),
        "deadline": 200.0,
    }


@pytest.mark.parametrize(
    "universe,cap,expected_pairs",
    [
        (489, None, 53618),
        (489, 53_618, 53618),
        (560, None, 65404),
        (600, 100_000, 72044),
    ],
)
def test_complete_universe_reaches_worker_with_bound_budget(
    monkeypatch, universe, cap, expected_pairs
):
    arguments = _arguments(universe)
    monkeypatch.setattr(g1.time, "monotonic", lambda: 100.0)
    requests = []

    def timeout_worker(command, **kwargs):
        request = json.loads(kwargs["input"])
        requests.append((request, kwargs["timeout"]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(g1.subprocess, "run", timeout_worker)
    config = g1.ParallelG1Config(
        family_refinement=True, **({"max_swap_evaluations": cap} if cap else {})
    )
    result = g1.run_parallel_g1(**arguments, config=config)
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request["candidate_coupons"] == list(arguments["candidate_coupons"])
    assert request["initial_coupons"] == list(arguments["initial_coupons"])
    assert len(request["probability_models"]) == 4
    assert request["limits"]["max_swap_evaluations"] == (cap or 65_536)
    assert request["limits"]["time_budget_seconds"] == 50.0
    assert request["limits"]["max_accepted_swaps"] == 1
    assert request["runtime_contract"]["reserve_seconds"] == 30.0
    assert request["runtime_contract"]["family_refinement"] is True
    assert timeout == 60.0
    assert result["admission"]["round_pairs"] == expected_pairs
    assert result["admission"]["models"] == 4
    assert result["status"] == "FALLBACK"
    assert result["selected_coupons"] == list(arguments["initial_coupons"])
    assert result["operator_compatible"] is False
    assert result["automatic_wagering"] is False
    assert result["activation_allowed"] is False


@pytest.mark.parametrize(
    "universe,cap", [(561, None), (1000, None), (489, 50_000), (489, 53_617)]
)
def test_above_cap_rejected_without_candidate_truncation(monkeypatch, universe, cap):
    arguments = _arguments(universe)
    monkeypatch.setattr(g1.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        g1.subprocess, "run", lambda *a, **k: pytest.fail("worker must not start")
    )
    config = g1.ParallelG1Config(
        **({"max_swap_evaluations": cap} if cap else {})
    )
    result = g1.run_parallel_g1(**arguments, config=config)
    assert result["status"] == "SKIPPED_EVALUATION_BUDGET"
    assert result["admission"]["round_pairs"] == 166 * (universe - 166)
    assert len(arguments["candidate_coupons"]) == universe
    assert result["selected_coupons"] == list(arguments["initial_coupons"])


def test_profile_does_not_spend_publication_reserve(monkeypatch):
    arguments = _arguments()
    arguments["deadline"] = 131.0
    monkeypatch.setattr(g1.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        g1.subprocess, "run", lambda *a, **k: pytest.fail("reserve must hold")
    )
    result = g1.run_parallel_g1(**arguments, config=g1.ParallelG1Config())
    assert result["status"] == "SKIPPED_DEADLINE_RESERVE"
    assert result["selected_coupons"] == list(arguments["initial_coupons"])
