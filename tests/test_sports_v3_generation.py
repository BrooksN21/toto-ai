import importlib.util
import math
import time
from dataclasses import asdict
from itertools import combinations
from pathlib import Path

import pytest

from toto_ai.optimizer.coupon_probabilities import (
    best_coupon_by_p13,
    top_probability_coupons,
)
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
)
from toto_ai.sports_stats import v3_generation as generation
from toto_ai.sports_stats import v3_probability as v3

_spec = importlib.util.spec_from_file_location(
    "v3_core_fixtures", Path(__file__).with_name("test_sports_v3_probability.py")
)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


def request():
    """Pure synthetic library input; no parallel worker is imported in Stage A."""
    rows = [
        v3.seal(
            {
                **fixtures.feature(10, i),
                "drawing_id": 100,
                "scheduler_plan_sha256": "e" * 64,
            }
        )
        for i in range(15)
    ]
    bundle = v3.seal(
        {
            "kind": "SPORTS_V3_FEATURE_BUNDLE",
            "feature_version": "sports-v3-probability-feature-bundle-v1",
            "drawing_id": 100,
            "drawing_number": 10,
            "drawing_fingerprint": "f" * 64,
            "scheduler_plan_sha256": "e" * 64,
            "rows": rows,
            "operator_compatible": False,
            "activation_allowed": False,
        }
    )
    model = fixtures.fit()
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
        "captured_at": fixtures.feature(10)["bk_captured_at"],
        "event_ids": [f"10-{i}" for i in range(15)],
        "bk_probabilities": [[0.2, 0.3, 0.5]] * 15,
        "bk_margins": [None] * 15,
    }


def infer_final_bk(req, ctx):
    """Build the generator's input with real library inference, not fake scores.

    Worker-specific input validation belongs to Stage F. Generation still checks
    the complete frozen input, model, event and financial bindings itself.
    """
    model, bundle = req["model"], req["features"]
    events = [
        v3.infer_v3(
            model,
            row,
            bk_probabilities=ctx["bk_probabilities"][i],
            bk_input_sha256=ctx["final_input_sha256"],
            bk_margin=ctx["bk_margins"][i],
        )
        for i, row in enumerate(bundle["rows"])
    ]
    return v3.seal(
        {
            "model_version": v3.MODEL_VERSION,
            "model_sha256": model["sha256"],
            "feature_bundle_sha256": bundle["sha256"],
            "final_input_sha256": ctx["final_input_sha256"],
            "probability_input_sha256": v3.digest(ctx["bk_probabilities"]),
            "final_context": {
                **{
                    key: ctx[key]
                    for key in (
                        "drawing_id",
                        "drawing_number",
                        "drawing_fingerprint",
                        "scheduler_plan_sha256",
                        "captured_at",
                        "event_ids",
                    )
                },
                "frozen_input_sha256": v3.digest(ctx["frozen_input"])
                if "frozen_input" in ctx
                else None,
            },
            "events": events,
            "operator_compatible": False,
            "activation_allowed": False,
        }
    )


def frozen():
    return FrozenStrategyInput(
        drawing_id=100,
        drawing_number=10,
        drawing_fingerprint="f" * 64,
        source_captured_at="2025-01-11T00:00:00+00:00",
        as_of="2025-01-11T00:00:00+00:00",
        ended_at="2025-01-11T02:00:00+00:00",
        bank=90,
        stake=30,
        pool_sum=1.0,
        jackpot=0.0,
        possible_winnings=1.0,
        events=tuple(
            FrozenStrategyEvent(i, f"10-{i}", (0.2, 0.3, 0.5), (0.3, 0.3, 0.4))
            for i in range(15)
        ),
    )


def test_actual_generator_consumes_v3_not_rescored_control():
    req, ctx = request(), context()
    ctx["frozen_input"] = asdict(frozen())
    inference = infer_final_bk(req, ctx)
    control = ("1" * 15, "X" * 15, "2" * 15)
    result = generation.generate_v3_candidate(
        request=req,
        inference=inference,
        frozen_payload=asdict(frozen()),
        control_coupons=control,
        gate={"status": "SYNTHETIC_TEST_ONLY"},
    )
    probabilities = [row["probabilities"] for row in inference["events"]]
    expected = tuple(top_probability_coupons(probabilities, limit=3))
    assert tuple(result["candidate_coupons"]) == expected
    assert expected != control
    best = best_coupon_by_p13(expected, probabilities)
    assert result["highest_p13"]["package_position"] == best.package_position
    assert (
        result["highest_p13"]["probability_at_least_13"] == best.probability_at_least_13
    )
    assert result["model_sha256"] == req["model"]["sha256"]
    assert result["final_input_sha256"] == "d" * 64
    assert result["operator_compatible"] is False
    assert result["generator"] == "existing_probability_only"
    assert result["receipt_hash_policy"] == "SEMANTIC_ONLY_RUNTIME_EXCLUDED"
    repeated = generation.generate_v3_candidate(
        request=req,
        inference=inference,
        frozen_payload=asdict(frozen()),
        control_coupons=control,
        gate={"status": "SYNTHETIC_TEST_ONLY"},
    )
    assert result == repeated
    assert result["independent_research_safety"]["operator_compatible"] is False

    # Independent closed form: probability of at most two misses.
    def oracle(coupon):
        hit = [
            row["1X2".index(c)] for row, c in zip(probabilities, coupon, strict=True)
        ]
        odds = [(1 - p) / p for p in hit]
        return math.prod(hit) * (
            1 + math.fsum(odds) + math.fsum(a * b for a, b in combinations(odds, 2))
        )

    values = [oracle(c) for c in expected]
    assert result["highest_p13"]["probability_at_least_13"] == pytest.approx(
        max(values), abs=1e-14
    )
    assert values[result["highest_p13"]["package_position"] - 1] == pytest.approx(
        max(values), abs=1e-14
    )


def test_no_generation_without_probability_gate():
    req = request()
    inference = infer_final_bk(req, context())
    with pytest.raises(ValueError, match="gate"):
        generation.generate_v3_candidate(
            request=req,
            inference=inference,
            frozen_payload=asdict(frozen()),
            control_coupons=("1" * 15,),
            gate=None,
        )


@pytest.mark.parametrize("fault", ["bk", "order", "capture", "bank", "stake"])
def test_generation_rejects_mismatched_consumed_final_input(fault):
    req, ctx = request(), context()
    original = asdict(frozen())
    ctx["frozen_input"] = original
    inference = infer_final_bk(req, ctx)
    from copy import deepcopy

    changed = deepcopy(original)
    if fault == "bk":
        changed["events"][0]["bk_probabilities"] = [0.8, 0.1, 0.1]
    elif fault == "order":
        changed["events"] = tuple(reversed(changed["events"]))
    elif fault == "capture":
        changed["source_captured_at"] = "2025-01-10T00:00:00+00:00"
    else:
        changed[fault] *= 2
    with pytest.raises(ValueError):
        generation.generate_v3_candidate(
            request=req,
            inference=inference,
            frozen_payload=changed,
            control_coupons=("1" * 15, "X" * 15, "2" * 15),
            gate={"status": "SYNTHETIC_TEST_ONLY"},
        )


@pytest.mark.skip(reason="NOT_RUN_FOR_SCOPE: Stage F worker integration, not Stage A")
def test_native_worker_generates_new_v3_candidate_under_explicit_synthetic_gate():
    from toto_ai.sports_stats import v3_parallel as parallel

    req, ctx = request(), context()
    req.update(
        generate_candidate=True, generation_gate={"status": "SYNTHETIC_TEST_ONLY"}
    )
    ctx["frozen_input"] = asdict(frozen())
    packages = {name: ("1" * 15, "X" * 15, "2" * 15) for name in parallel.STRATEGIES}
    result = parallel.run_v3_parallel_research(
        req, context=ctx, packages=packages, deadline=time.monotonic() + 60
    )
    assert result["status"] == "COMPLETE_EXPERIMENTAL_NO_SELECTION"
    candidate = result["generated_candidate"]
    assert candidate["candidate_differs_from_control"] is True
    assert candidate["selected_for_operator"] is False
