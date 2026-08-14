from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from toto_ai.ev.models import EVConfig, EVPackage, EVSurface, RankedCoupon
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    run_bk_probability_only,
    run_ev_crowd_current,
    run_totobrief_style_cover,
)


def test_frozen_strategy_input_rejects_future_or_incomplete_evidence():
    events = _events()

    with pytest.raises(ValueError, match="captured after as_of"):
        _strategy_input(
            events=events,
            source_captured_at="2026-08-14T13:01:00Z",
            as_of="2026-08-14T13:00:00Z",
        )

    with pytest.raises(ValueError, match="exactly orders 0 through 14"):
        _strategy_input(events=events[:-1])

    with pytest.raises(ValueError, match="divisible by stake"):
        _strategy_input(events=events, bank=4_981)


def test_bk_probability_strategy_ignores_crowd_and_scales_with_bank():
    frozen = _strategy_input(events=_events())
    changed_crowd = replace(
        frozen,
        events=tuple(
            replace(event, crowd_probabilities=(0.20, 0.20, 0.60))
            for event in frozen.events
        ),
    )

    baseline = run_bk_probability_only(frozen, category=13)
    crowd_changed = run_bk_probability_only(changed_crowd, category=13)
    larger_bank = run_bk_probability_only(
        replace(frozen, bank=9_960),
        category=13,
    )

    assert baseline.strategy_id == "BK_PROBABILITY_ONLY"
    assert baseline.coupons == crowd_changed.coupons
    assert baseline.package_sha256 == crowd_changed.package_sha256
    assert baseline.input_sha256 != crowd_changed.input_sha256
    assert baseline.coupon_count == 166
    assert baseline.cost == 4_980
    assert larger_bank.coupon_count == 332
    assert larger_bank.cost == 9_960


@pytest.mark.parametrize("category", [13, 14])
def test_totobrief_cover_strategy_has_exact_declared_guarantee(category):
    balanced = tuple(
        replace(
            event,
            bk_probabilities=(0.34, 0.33, 0.33),
            crowd_probabilities=(0.34, 0.33, 0.33),
        )
        if event.event_order < 4
        else event
        for event in _events()
    )

    result = run_totobrief_style_cover(
        _strategy_input(events=balanced),
        category=category,
    )

    assert result.strategy_id == f"TOTOBRIEF_STYLE_COVER_{category}"
    assert result.category == category
    assert result.guarantee_pass is True
    assert result.coverage_rate == 1.0
    assert result.cost <= 4_980
    assert len(result.brief) == 15


def test_ev_adapter_uses_the_same_frozen_matrices_and_config():
    frozen = _strategy_input(events=_events())
    observed = {}

    def component_builder(ev_input):
        observed["ev_input"] = ev_input
        return object()

    def surface_materializer(components, possible_winnings, jackpot):
        observed["materialized"] = (components, possible_winnings, jackpot)
        return EVSurface(
            gross_ev=np.array([1.0]),
            event_count=15,
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=1.0,
        )

    def package_selector(surface, config, *, probabilities, provenance):
        observed["selection"] = (surface, config, probabilities, provenance)
        coupons = tuple(
            RankedCoupon(
                rank=index,
                coupon="1" * 14 + outcome,
                gross_ev=2.0,
                net_ev=1.0,
            )
            for index, outcome in enumerate(("1", "X", "2"), start=1)
        )
        return (
            EVPackage(
                decision="RESEARCH ONLY",
                coupons=coupons,
                cost=90,
                unused_bank=4_890,
                expected_payout=180.0,
                modeled_roi=1.0,
                derived_brief=tuple("1" for _ in range(14)) + ("1X2",),
            ),
            (),
        )

    config = EVConfig(bank=4_980, stake=30, mode="research")
    result = run_ev_crowd_current(
        frozen,
        config=config,
        component_builder=component_builder,
        surface_materializer=surface_materializer,
        package_selector=package_selector,
    )

    ev_input = observed["ev_input"]
    assert ev_input.true_probabilities == frozen.bk_probability_matrix
    assert ev_input.crowd_probabilities == frozen.crowd_probability_matrix
    assert ev_input.fetched_at == frozen.source_captured_at
    assert observed["materialized"][1:] == (
        frozen.possible_winnings,
        frozen.jackpot,
    )
    assert observed["selection"][1] == config
    assert observed["selection"][2] == frozen.bk_probability_matrix
    assert result.strategy_id == "EV_CROWD_CURRENT"
    assert result.coupons == ("1" * 15, "1" * 14 + "X", "1" * 14 + "2")
    assert result.cost == 90


def _events() -> tuple[FrozenStrategyEvent, ...]:
    return tuple(
        FrozenStrategyEvent(
            event_order=event_order,
            name=f"Match {event_order + 1}",
            bk_probabilities=(0.55, 0.25, 0.20),
            crowd_probabilities=(0.50, 0.30, 0.20),
        )
        for event_order in range(15)
    )


def _strategy_input(
    *,
    events: tuple[FrozenStrategyEvent, ...],
    bank: int = 4_980,
    source_captured_at: str = "2026-08-14T12:55:00Z",
    as_of: str = "2026-08-14T13:00:00Z",
) -> FrozenStrategyInput:
    return FrozenStrategyInput(
        drawing_id=12_033,
        drawing_number=4_975,
        drawing_fingerprint="a" * 64,
        source_captured_at=source_captured_at,
        as_of=as_of,
        ended_at="2026-08-14T14:00:00Z",
        bank=bank,
        stake=30,
        pool_sum=2_000_000.0,
        jackpot=1_000_000.0,
        possible_winnings=2_000_000.0,
        events=events,
    )
