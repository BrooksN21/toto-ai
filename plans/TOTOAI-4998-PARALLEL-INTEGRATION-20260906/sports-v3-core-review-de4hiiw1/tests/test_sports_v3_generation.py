import importlib.util
from dataclasses import asdict
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
from toto_ai.sports_stats import v3_parallel as parallel

_spec = importlib.util.spec_from_file_location(
    "v3_parallel_fixtures", Path(__file__).with_name("test_sports_v3_parallel.py")
)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


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
            FrozenStrategyEvent(i, str(i), (0.2, 0.3, 0.5), (0.3, 0.3, 0.4))
            for i in range(15)
        ),
    )


def test_actual_generator_consumes_v3_not_rescored_control():
    request, context = fixtures.request(), fixtures.context()
    inference = parallel.infer_final_bk(request, context)
    control = ("1" * 15, "X" * 15, "2" * 15)
    result = generation.generate_v3_candidate(
        request=request,
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
    assert result["model_sha256"] == request["model"]["sha256"]
    assert result["final_input_sha256"] == "d" * 64
    assert result["operator_compatible"] is False
    assert result["generator"] == "existing_probability_only"


def test_no_generation_without_probability_gate():
    request = fixtures.request()
    inference = parallel.infer_final_bk(request, fixtures.context())
    with pytest.raises(ValueError, match="gate"):
        generation.generate_v3_candidate(
            request=request,
            inference=inference,
            frozen_payload=asdict(frozen()),
            control_coupons=("1" * 15,),
            gate=None,
        )
