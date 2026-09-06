from __future__ import annotations

import importlib
import json
import subprocess
import time
from dataclasses import replace

import pytest

from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.package.audit import PackageSafetyConfig


def _module():
    return importlib.import_module("toto_ai.sports_stats.parallel_g1")


def _input():
    initial = ("1" * 15, "X" * 15, "2" * 15)
    return {
        "initial_coupons": initial,
        "control_coupons": initial,
        "candidate_coupons": (*initial, "1" + "X" * 14),
        "probability_models": {"bk": ((1 / 3, 1 / 3, 1 / 3),) * 15},
        "exposure_constraints": ExposureConstraints(
            ((0, 0, 0),) * 15, ((2, 2, 2),) * 15
        ),
        "input_sha256": "a" * 64,
        "plan_sha256": "b" * 64,
        "bank": 90,
        "effective_budget": 90,
        "stake": 30,
        "safety_config": PackageSafetyConfig(),
        "deadline": time.monotonic() + 30,
    }


def test_disabled_refinement_keeps_exact_initial_without_worker(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("worker started")
    )
    result = module.run_parallel_g1(**_input(), config=None)
    assert result["status"] == "DISABLED"
    assert result["selected_coupons"] == list(_input()["initial_coupons"])
    assert result["operator_compatible"] is False


def test_deadline_reserve_skips_worker(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("worker started")
    )
    args = _input()
    args["deadline"] = time.monotonic() + 1
    result = module.run_parallel_g1(**args, config=module.ParallelG1Config())
    assert result["status"] == "SKIPPED_DEADLINE_RESERVE"
    assert result["selected_coupons"] == list(args["initial_coupons"])


@pytest.mark.parametrize("mode", ["timeout", "error", "malformed", "wrong_binding"])
def test_worker_failure_cannot_replace_original_candidate(monkeypatch, mode):
    module = _module()

    def worker(*args, **kwargs):
        assert 0 < kwargs["timeout"] <= 2
        if mode == "timeout":
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
        if mode == "error":
            raise OSError("unavailable")
        return subprocess.CompletedProcess(
            args[0], 0, "{}" if mode == "wrong_binding" else "not json", ""
        )

    monkeypatch.setattr(module.subprocess, "run", worker)
    config = replace(
        module.ParallelG1Config(), hard_timeout_seconds=2, reserve_seconds=1
    )
    args = _input()
    result = module.run_parallel_g1(**args, config=config)
    assert result["status"] == "FALLBACK"
    assert result["selected_coupons"] == list(args["initial_coupons"])
    assert result["operator_compatible"] is False
    assert result["automatic_wagering"] is False


@pytest.mark.parametrize(
    "field",
    [
        "initial_package_sha256",
        "candidate_universe_sha256",
        "probability_models_sha256",
        "exposure_constraints_sha256",
        "input_sha256",
        "binding_sha256",
        "budget_sha256",
        "config_sha256",
        "semantic_hash",
        "budget_summary",
        "operator_compatible",
        "status",
    ],
)
def test_malformed_worker_binding_or_contract_rolls_back(monkeypatch, field):
    module = _module()

    def worker(command, **kwargs):
        document = module._worker(json.loads(kwargs["input"]))
        engine = document["engine"]
        if field == "budget_summary":
            engine[field]["cost"] += 30
        elif field == "operator_compatible":
            engine[field] = True
        elif field == "status":
            engine[field] = "UNKNOWN_SUCCESS"
        elif field == "semantic_hash":
            engine[field] = "f" * 64
        else:
            engine["input_hashes"][field] = "f" * 64
        return subprocess.CompletedProcess(command, 0, json.dumps(document), "")

    monkeypatch.setattr(module.subprocess, "run", worker)
    args = _input()
    result = module.run_parallel_g1(
        **args,
        config=module.ParallelG1Config(reserve_seconds=1),
    )
    assert result["status"] == "FALLBACK"
    assert result["selected_coupons"] == list(args["initial_coupons"])


def test_hard_timeout_reaps_only_owned_local_worker(monkeypatch):
    import os
    import sys

    module = _module()
    original_run = module.subprocess.run
    pids = []

    def slow_worker(command, **kwargs):
        try:
            return original_run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "import os,time; print(os.getpid(),flush=True); time.sleep(5)",
                ],
                stdout=subprocess.PIPE,
                text=True,
                timeout=kwargs["timeout"],
                check=True,
            )
        except subprocess.TimeoutExpired as error:
            pids.append(int(error.stdout.strip()))
            raise

    monkeypatch.setattr(module.subprocess, "run", slow_worker)
    started = time.monotonic()
    args = _input()
    result = module.run_parallel_g1(
        **args,
        config=module.ParallelG1Config(hard_timeout_seconds=1.1, reserve_seconds=1),
    )
    assert result["status"] == "FALLBACK"
    assert result["selected_coupons"] == list(args["initial_coupons"])
    assert time.monotonic() - started < 3
    assert len(pids) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(pids[0], 0)


def test_late_worker_completion_is_discarded(monkeypatch):
    module = _module()
    now = [1.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])

    def worker(command, **kwargs):
        document = module._worker(json.loads(kwargs["input"]))
        now[0] = 100
        return subprocess.CompletedProcess(command, 0, json.dumps(document), "")

    monkeypatch.setattr(module.subprocess, "run", worker)
    args = _input()
    args["deadline"] = 30
    result = module.run_parallel_g1(
        **args,
        config=module.ParallelG1Config(reserve_seconds=1),
    )
    assert result["status"] == "FALLBACK"
    assert result["reason"] == "POST_WORKER_DEADLINE"
    assert result["selected_coupons"] == list(args["initial_coupons"])


def test_dense_admission_counts_without_running_exact_engine(monkeypatch):
    from itertools import islice, product

    module = _module()
    coupons = tuple("".join(c) for c in islice(product("1X2", repeat=15), 408))
    args = _input()
    args.update(initial_coupons=coupons[:166], candidate_coupons=coupons)
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("dense engine")
    )
    result = module.run_parallel_g1(
        **args,
        config=module.ParallelG1Config(max_swap_evaluations=40171, reserve_seconds=1),
    )
    assert result["status"] == "SKIPPED_EVALUATION_BUDGET"
    assert result["admission"]["round_pairs"] == 40172
    assert result["admission"]["initial"] == 166
    assert result["admission"]["universe"] == 408


def test_progress_is_bounded_and_logging_failure_does_not_change_clock_trace():
    module = _module()
    traces = []
    for enabled, fail in ((False, False), (True, False), (True, True)):
        values = iter(float(i) / 10 for i in range(1000))
        events = []

        def sink(line, events=events, fail=fail):
            events.append(line)
            if fail:
                raise OSError("log unavailable")

        progress = module._Progress(
            enabled=enabled, clock=lambda values=values: next(values), sink=sink
        )
        trace = [progress() for _ in range(1000)]
        traces.append(trace)
        assert progress.events <= 8
        assert progress.bytes <= 2048
        assert all(len(line.encode()) <= 256 for line in events)
        if enabled:
            assert len(events) == 8
            assert json.loads(events[-1])["elapsed_seconds"] == 70
        else:
            assert events == []
    assert traces[0] == traces[1] == traces[2]


def test_real_worker_preserves_binding_and_non_improving_original():
    module = _module()
    config = replace(
        module.ParallelG1Config(), hard_timeout_seconds=5, reserve_seconds=1
    )
    args = _input()
    result = module.run_parallel_g1(**args, config=config)
    assert result["status"] == "UNCHANGED"
    assert result["engine"]["status"] == "UNCHANGED"
    assert result["selected_coupons"] == list(args["initial_coupons"])
    assert result["binding"]["input_sha256"] == "a" * 64
    assert result["binding"]["bank"] == 90
    assert result["lineage"]["strategy_id"] == "robust-g1-v1"
    assert result["lineage"]["operator_selection_included"] is False


def test_invalid_capacity_fails_in_worker_without_candidate_change():
    module = _module()
    args = _input()
    args["bank"] = args["effective_budget"] = 120
    result = module.run_parallel_g1(
        **args, config=module.ParallelG1Config(reserve_seconds=1)
    )
    assert result["status"] == "FALLBACK"
    assert result["selected_coupons"] == list(args["initial_coupons"])


def test_insufficient_pair_budget_skips_without_truncation(monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("worker started")
    )
    args = _input()
    result = module.run_parallel_g1(
        **args,
        config=module.ParallelG1Config(max_swap_evaluations=2, reserve_seconds=1),
    )
    assert result["status"] == "SKIPPED_EVALUATION_BUDGET"
    assert result["admission"] == {
        "initial": 3,
        "universe": 4,
        "models": 1,
        "round_pairs": 3,
    }
    assert result["selected_coupons"] == list(args["initial_coupons"])


def test_worker_cannot_override_nonoperator_flags(monkeypatch):
    module = _module()

    def worker(command, **kwargs):
        document = module._worker(json.loads(kwargs["input"]))
        document["operator_compatible"] = True
        document["automatic_wagering"] = True
        return subprocess.CompletedProcess(command, 0, json.dumps(document), "")

    monkeypatch.setattr(module.subprocess, "run", worker)
    result = module.run_parallel_g1(
        **_input(),
        config=module.ParallelG1Config(reserve_seconds=1),
    )
    assert result["operator_compatible"] is False
    assert result["automatic_wagering"] is False
