from toto_ai.optimizer.prospective_quality import QualityV3Config
from toto_ai.optimizer.quality_replay import compare_quality_packages


def _models():
    row = (0.50, 0.30, 0.20)
    flat = (0.45, 0.32, 0.23)
    return {"bk": (row,) * 15, "flatten_10": (flat,) * 15}


def _compare(*, actual=None):
    return compare_quality_packages(
        drawing_id=1,
        drawing_number=4990,
        plan_id="plan",
        final_input_sha256="a" * 64,
        probability_input_sha256="b" * 64,
        bank=60,
        effective_budget=60,
        stake=30,
        baseline=("1" * 15, "2" * 15),
        quality_v3=("1" * 15, "X" * 15),
        models=_models(),
        actual=actual,
        quality_v3_config=QualityV3Config(
            top_count=2,
            candidate_sample_count=2,
            mutation_limit=0,
            scenario_sample_count=10,
        ),
    )


def test_quality_replay_is_equal_cost_and_research_only():
    report = _compare()

    assert report["equal_coupon_count"] == 2
    assert report["equal_cost"] == 60
    assert report["settled"] is False
    assert report["operator_compatible"] is False
    assert report["scheduler_state_mutated"] is False
    assert report["strategies"]["quality-v2"]["coupon_count"] == 2
    assert report["strategies"]["quality-v3"]["coupon_count"] == 2
    assert [
        row["model"] for row in report["strategies"]["quality-v3"]["models"]
    ] == ["bk", "flatten_10"]


def test_quality_replay_settles_both_packages_with_same_actual():
    report = _compare(actual="X" * 15)

    assert report["settled"] is True
    assert report["strategies"]["quality-v2"]["settlement"]["best_hits"] == 0
    assert report["strategies"]["quality-v3"]["settlement"]["best_hits"] == 15
    assert (
        report["settlement_comparison"][
            "quality_v3_minus_quality_v2_best_hits"
        ]
        == 15
    )
    assert report["strategies"]["quality-v3"]["settlement"]["hit15"] == 1


def test_quality_replay_rejects_unequal_coupon_counts():
    try:
        compare_quality_packages(
            drawing_id=1,
            drawing_number=4990,
            plan_id="plan",
            final_input_sha256="a" * 64,
            probability_input_sha256="b" * 64,
            bank=60,
            effective_budget=60,
            stake=30,
            baseline=("1" * 15,),
            quality_v3=("1" * 15, "X" * 15),
            models=_models(),
            actual=None,
            quality_v3_config=QualityV3Config(),
        )
    except ValueError as error:
        assert "equal-size" in str(error)
    else:
        raise AssertionError("unequal replay packages must fail")
