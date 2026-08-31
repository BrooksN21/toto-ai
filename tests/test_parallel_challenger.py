from __future__ import annotations

import pytest

from toto_ai.optimizer.parallel_challenger import (
    ExactCategoryMetrics,
    ParallelCandidate,
    select_parallel_candidate,
)

MODELS = ("bk", "sports", "flat-10", "flat-20")


def _candidate(
    strategy_id: str,
    *,
    bk: tuple[float, float, float] = (0.10, 0.02, 0.001),
    other_p13: float = 0.08,
    maximum_outcome_share: float = 0.80,
    eligible: bool = True,
    package_sha256: str | None = None,
) -> ParallelCandidate:
    rows = [ExactCategoryMetrics("bk", *bk)]
    rows.extend(
        ExactCategoryMetrics(name, other_p13, 0.01, 0.0005)
        for name in MODELS[1:]
    )
    return ParallelCandidate(
        strategy_id=strategy_id,
        package_sha256=package_sha256 or ("a" * 64),
        coupon_count=10,
        cost=300,
        maximum_outcome_share=maximum_outcome_share,
        eligible=eligible,
        rejection_reasons=() if eligible else ("safety",),
        models=tuple(rows),
    )


def test_control_wins_when_challenger_trades_away_bk_probability() -> None:
    control = _candidate("quality-v2")
    challenger = _candidate(
        "quality-v3",
        bk=(0.099, 0.02, 0.001),
        other_p13=0.09,
    )

    result = select_parallel_candidate((control, challenger))

    assert result.selected_strategy_id == "quality-v2"
    assert result.promoted is False
    assert result.rejections["quality-v3"] == ("bk_p13_below_control",)


def test_challenger_must_strictly_improve_worst_model_p13() -> None:
    control = _candidate("quality-v2", other_p13=0.08)
    challenger = _candidate("quality-v3", other_p13=0.08)

    result = select_parallel_candidate((control, challenger))

    assert result.selected_strategy_id == "quality-v2"
    assert result.rejections["quality-v3"] == (
        "worst_model_p13_not_improved",
    )


def test_promotable_challenger_wins_by_predeclared_lexicographic_order() -> None:
    control = _candidate("quality-v2", other_p13=0.07)
    sports = _candidate("sports-shadow", other_p13=0.08)
    robust = _candidate("robust", other_p13=0.09)

    result = select_parallel_candidate((control, sports, robust))

    assert result.selected_strategy_id == "robust"
    assert result.promoted is True
    assert result.selection_reason == "eligible_challenger_dominates_control_gate"


def test_ineligible_or_more_concentrated_challenger_cannot_win() -> None:
    control = _candidate("quality-v2", other_p13=0.07)
    unsafe = _candidate("quality-v3", other_p13=0.10, eligible=False)
    concentrated = _candidate(
        "robust",
        other_p13=0.10,
        maximum_outcome_share=0.81,
    )

    result = select_parallel_candidate((control, unsafe, concentrated))

    assert result.selected_strategy_id == "quality-v2"
    assert result.rejections["quality-v3"] == ("safety",)
    assert result.rejections["robust"] == (
        "concentration_above_control",
    )


def test_candidate_model_sets_and_control_are_fail_closed() -> None:
    control = _candidate("quality-v2")
    missing_model = ParallelCandidate(
        strategy_id="quality-v3",
        package_sha256="a" * 64,
        coupon_count=10,
        cost=300,
        maximum_outcome_share=0.5,
        eligible=True,
        rejection_reasons=(),
        models=(ExactCategoryMetrics("bk", 0.1, 0.02, 0.001),),
    )

    with pytest.raises(ValueError, match="identical model sets"):
        select_parallel_candidate((control, missing_model))
    with pytest.raises(ValueError, match="quality-v2 control"):
        select_parallel_candidate((_candidate("quality-v3"),))


def test_hash_is_deterministic_final_tie_breaker() -> None:
    control = _candidate("quality-v2", other_p13=0.07)
    first = _candidate(
        "sports-shadow",
        other_p13=0.09,
        package_sha256="1" * 64,
    )
    second = _candidate(
        "robust",
        other_p13=0.09,
        package_sha256="2" * 64,
    )

    result = select_parallel_candidate((control, second, first))

    assert result.selected_strategy_id == "sports-shadow"
