from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace

import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.optimizer.prospective_quality import (
    IncompletePairedResultsError,
    PairedQualityIntegrityError,
    PairedResultEvent,
    PairedSettledResults,
    QualityV3Config,
    evaluate_paired_quality,
    settle_paired_quality,
)
from toto_ai.optimizer.robust_package import (
    RobustModelMetrics,
    RobustPackageResult,
)
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    StrategyResult,
)

CONTROL_COUPONS = ("1" * 15, "X" * 15)
CHALLENGER_COUPONS = ("2" * 15, "1X" * 7 + "1")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _package_sha256(coupons: tuple[str, ...]) -> str:
    return hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode()
    ).hexdigest()


def _frozen() -> FrozenStrategyInput:
    return FrozenStrategyInput(
        drawing_id=4993,
        drawing_number=12086,
        drawing_fingerprint="b" * 64,
        source_captured_at="2026-08-31T12:00:00+00:00",
        as_of="2026-08-31T12:00:00+00:00",
        ended_at="2026-09-01T17:00:00+00:00",
        bank=60,
        stake=30,
        pool_sum=1_000_000.0,
        jackpot=0.0,
        possible_winnings=500_000.0,
        events=tuple(
            FrozenStrategyEvent(
                event_order=order,
                name=f"Home {order} — Away {order}",
                bk_probabilities=(0.5, 0.3, 0.2),
                crowd_probabilities=(0.45, 0.3, 0.25),
            )
            for order in range(15)
        ),
    )


def _config() -> EVConfig:
    return EVConfig(
        bank=60,
        stake=30,
        mode="research",
        min_gross_ev=0.0,
        package_probability_samples=64,
        package_optimization_probability_samples=32,
        package_quality_candidate_count=8,
        package_quality_repair_iterations=0,
    )


def _control_generator(frozen, *, config, category, provenance):
    del provenance
    p13, p14, p15 = exact_category_probabilities(
        CONTROL_COUPONS, frozen.bk_probability_matrix
    )
    return StrategyResult(
        strategy_id="EV_CROWD_CURRENT",
        strategy_version="v1",
        source_engine="test-control",
        category=category,
        input_sha256=frozen.input_sha256,
        config_sha256=_sha256_json(
            {"category": category, "ev_config": asdict(config)}
        ),
        package_sha256=_package_sha256(CONTROL_COUPONS),
        requested_bank=frozen.bank,
        stake=frozen.stake,
        coupons=CONTROL_COUPONS,
        cost=60,
        unused_bank=0,
        probability_at_least_13=p13,
        probability_at_least_14=p14,
        probability_at_least_15=p15,
        runtime_seconds=0.0,
        timed_out=False,
    )


def _robust_result(coupons, *, sample_count, category):
    return RobustPackageResult(
        selected_coupons=tuple(coupons),
        model_metrics=tuple(
            RobustModelMetrics(name, coverage, p13, p14, p15)
            for name, coverage, p13, p14, p15 in (
                ("bk", 0.40, 0.04, 0.02, 0.01),
                ("flatten_10", 0.35, 0.03, 0.015, 0.005),
                ("flatten_20", 0.30, 0.02, 0.01, 0.002),
            )
        ),
        worst_sampled_category_coverage=0.30,
        mean_sampled_category_coverage=0.35,
        candidate_count=len(coupons),
        sample_count_per_model=sample_count,
        category=category,
        timed_out=False,
    )


def _challenger_generator(**kwargs):
    return _robust_result(
        CHALLENGER_COUPONS,
        sample_count=kwargs["selection_sample_count"],
        category=kwargs["category"],
    )


def _robust_evaluator(**kwargs):
    return _robust_result(
        kwargs["candidates"],
        sample_count=kwargs["sample_count"],
        category=kwargs["category"],
    )


def _pair(*, control_generator=_control_generator):
    return evaluate_paired_quality(
        frozen_input=_frozen(),
        input_kind="final",
        input_sha256="a" * 64,
        plan_id="plan-4993",
        quality_v2_config=_config(),
        quality_v3_config=QualityV3Config(
            top_count=8,
            candidate_sample_count=16,
            mutation_limit=8,
            scenario_sample_count=64,
        ),
        control_generator=control_generator,
        challenger_generator=_challenger_generator,
        robust_evaluator=_robust_evaluator,
    )


def _settled_events() -> tuple[PairedResultEvent, ...]:
    return tuple(
        PairedResultEvent(
            event_order=order,
            result="*" if order == 1 else "1",
            result_status="postponed" if order == 1 else "resolved",
            score=None if order == 1 else "1:0",
        )
        for order in range(15)
    )


def test_paired_evaluation_is_deterministic_and_coupon_free_publicly() -> None:
    first = _pair()
    second = _pair()

    assert first == second
    assert first.control.coupon_capacity == first.challenger.coupon_capacity == 2
    assert first.control.input_sha256 == first.challenger.input_sha256 == "a" * 64
    assert first.control.identity.role == "OPERATOR_CONTROL"
    assert first.challenger.identity.role == "RESEARCH_CHALLENGER_ONLY"
    assert first.control.metrics.monte_carlo_seed == (
        first.challenger.metrics.monte_carlo_seed
    )
    assert len(first.control.metrics.exposures) == 15
    assert first.control.metrics.robust_scenarios.sample_count_per_model == 64
    public = json.dumps(first.public_summary(), sort_keys=True)
    assert CONTROL_COUPONS[0] not in public
    assert CHALLENGER_COUPONS[0] not in public
    assert first.operator_strategy_id == "quality-v2"
    assert first.automatic_operator_switching is False
    assert first.profitability_claimed is False


def test_generation_fails_closed_on_budget_or_strategy_identity_mismatch() -> None:
    with pytest.raises(PairedQualityIntegrityError, match="input budget mismatch"):
        evaluate_paired_quality(
            frozen_input=_frozen(),
            input_kind="final",
            input_sha256="a" * 64,
            plan_id="plan-4993",
            quality_v2_config=replace(_config(), bank=90),
            control_generator=_control_generator,
            challenger_generator=_challenger_generator,
            robust_evaluator=_robust_evaluator,
        )

    def wrong_identity(*args, **kwargs):
        return replace(_control_generator(*args, **kwargs), strategy_id="wrong")

    with pytest.raises(PairedQualityIntegrityError, match="identity mismatch"):
        _pair(control_generator=wrong_identity)


def test_settlement_compares_hits_and_voids_without_coupon_strings() -> None:
    pair = _pair()
    settlement = settle_paired_quality(
        pair,
        PairedSettledResults(
            drawing_id=4993,
            drawing_number=12086,
            input_sha256="a" * 64,
            events=_settled_events(),
        ),
    )

    assert settlement.control.best_hits == 15
    assert settlement.control.best_resolved_hits == 14
    assert settlement.control.hit_15_count == 1
    assert settlement.control.hit_denominator == 14
    assert settlement.control.void_event_orders == (2,)
    void_row = settlement.control.event_miss_attribution[1]
    assert void_row.excluded_from_hit_denominator is True
    assert void_row.actual_exposure_count is None
    challenger_miss = settlement.challenger.event_miss_attribution[3]
    assert challenger_miss.actual_outcome_covered is False
    assert challenger_miss.all_best_coupons_missed is True
    payload = json.dumps(settlement.to_dict(), sort_keys=True)
    assert CONTROL_COUPONS[0] not in payload
    assert CONTROL_COUPONS[1] not in payload
    assert CHALLENGER_COUPONS[0] not in payload
    assert settlement.operator_strategy_id == "quality-v2"
    assert settlement.automatic_operator_switching is False
    assert settlement.profitability_evaluated is False


def test_settlement_fails_closed_on_pending_or_input_mismatch() -> None:
    pair = _pair()
    pending = list(_settled_events())
    pending[3] = PairedResultEvent(
        event_order=3,
        result=None,
        result_status="postponed",
    )
    with pytest.raises(IncompletePairedResultsError, match="pending orders: 3"):
        settle_paired_quality(
            pair,
            PairedSettledResults(
                drawing_id=4993,
                drawing_number=12086,
                input_sha256="a" * 64,
                events=tuple(pending),
            ),
        )

    with pytest.raises(PairedQualityIntegrityError, match="input identity mismatch"):
        settle_paired_quality(
            pair,
            PairedSettledResults(
                drawing_id=4993,
                drawing_number=12086,
                input_sha256="c" * 64,
                events=_settled_events(),
            ),
        )


@pytest.mark.parametrize("status", [None, "", "pending", "mystery"])
def test_settlement_rejects_result_without_recognized_resolved_status(
    status: str | None,
) -> None:
    pair = _pair()
    events = list(_settled_events())
    events[4] = PairedResultEvent(
        event_order=4,
        result="1",
        result_status=status,
        score="1:0",
    )

    with pytest.raises(PairedQualityIntegrityError, match="resolved result"):
        settle_paired_quality(
            pair,
            PairedSettledResults(
                drawing_id=4993,
                drawing_number=12086,
                input_sha256="a" * 64,
                events=tuple(events),
            ),
        )


def test_settlement_policy_invariants_reject_operator_switching() -> None:
    settlement = settle_paired_quality(
        _pair(),
        PairedSettledResults(
            drawing_id=4993,
            drawing_number=12086,
            input_sha256="a" * 64,
            events=_settled_events(),
        ),
    )

    with pytest.raises(PairedQualityIntegrityError, match="quality-v2"):
        replace(settlement, operator_strategy_id="quality-v3")
    with pytest.raises(PairedQualityIntegrityError, match="switching"):
        replace(settlement, automatic_operator_switching=True)
