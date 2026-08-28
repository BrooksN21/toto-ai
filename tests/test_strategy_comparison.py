from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.ev.models import EVConfig, EVPackage, EVSurface, RankedCoupon
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    StrategyComparisonBundle,
    StrategyResult,
    run_bk_probability_only,
    run_cover_14_bk_fill,
    run_equal_input_comparison,
    run_ev_crowd_current,
    run_totobrief_style_cover,
)
from toto_ai.optimizer.strategy_execution import frozen_input_from_snapshot
from toto_ai.optimizer.strategy_reports import write_strategy_comparison_reports


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


@pytest.mark.parametrize(("bank", "expected_count"), [(4_980, 166), (9_960, 332)])
def test_cover_14_bk_fill_preserves_guarantee_and_uses_dynamic_bank(
    bank,
    expected_count,
):
    frozen = _strategy_input(events=_events(), bank=bank)
    cover = run_totobrief_style_cover(frozen, category=14)

    result = run_cover_14_bk_fill(frozen)

    assert result.strategy_id == "COVER_14_BK_FILL"
    assert result.category == 14
    assert result.coupon_count == expected_count
    assert result.cost == bank
    assert result.unused_bank == 0
    assert result.guarantee_pass is True
    assert result.coverage_rate == 1.0
    assert set(cover.coupons) <= set(result.coupons)
    assert (
        result.probability_at_least_13
        >= cover.probability_at_least_13
    )


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


def test_equal_input_comparison_rejects_a_foreign_result():
    frozen = _strategy_input(events=_events())
    config = EVConfig(bank=4_980, stake=30, mode="research")
    valid = _result(frozen, "EV_CROWD_CURRENT", ("1" * 15,))
    foreign = replace(
        _result(frozen, "BK_PROBABILITY_ONLY", ("X" * 15,)),
        input_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="same frozen input"):
        run_equal_input_comparison(
            frozen,
            ev_config=config,
            ev_runner=lambda *_args, **_kwargs: valid,
            bk_runner=lambda *_args, **_kwargs: foreign,
            cover_runner=lambda _frozen, *, category: _result(
                frozen,
                f"TOTOBRIEF_STYLE_COVER_{category}",
                ("2" * 15,),
                category=category,
            ),
            cover_fill_runner=lambda _frozen: _result(
                frozen,
                "COVER_14_BK_FILL",
                ("1X2" * 5,),
                category=14,
            ),
        )


def test_strategy_report_bundle_writes_five_hash_bound_packages(tmp_path):
    frozen = _strategy_input(events=_events())
    results = (
        _result(frozen, "EV_CROWD_CURRENT", ("1" * 15,)),
        _result(frozen, "BK_PROBABILITY_ONLY", ("X" * 15,)),
        _result(
            frozen,
            "TOTOBRIEF_STYLE_COVER_13",
            ("2" * 15,),
            category=13,
        ),
        _result(
            frozen,
            "TOTOBRIEF_STYLE_COVER_14",
            ("1X2" * 5,),
            category=14,
        ),
        _result(
            frozen,
            "COVER_14_BK_FILL",
            ("12X" * 5,),
            category=14,
        ),
    )
    bundle = StrategyComparisonBundle(frozen_input=frozen, results=results)

    paths = write_strategy_comparison_reports(bundle, tmp_path)

    assert paths.manifest.is_file()
    assert paths.json.is_file()
    assert paths.csv.is_file()
    assert paths.markdown.is_file()
    assert len(paths.packages) == 5
    assert paths.packages["EV_CROWD_CURRENT"].read_text() == (
        "30; " + "; ".join("1" * 15) + "\n"
    )
    manifest = __import__("json").loads(paths.manifest.read_text())
    assert manifest["input_sha256"] == frozen.input_sha256
    assert manifest["strategy_count"] == 5
    assert len({row["package_sha256"] for row in manifest["strategies"]}) == 5


def test_final_snapshot_builder_reuses_ev_probability_normalization():
    snapshot = SimpleNamespace(
        drawing_id=12_033,
        drawing_number=4_975,
        target_fingerprint="a" * 64,
        captured_at=datetime(2026, 8, 14, 13, 40, tzinfo=timezone.utc),
        payload={
            "data": {
                "id": 12_033,
                "number": 4_975,
                "pool_sum": 2_000_000,
                "jackpot": 1_000_000,
                "events": [
                    {
                        "order": order,
                        "name": f"Match {order + 1}",
                        "quotes": {
                            "bk_win_1": 55,
                            "bk_draw": 25,
                            "bk_win_2": 20,
                            "pool_win_1": 50,
                            "pool_draw": 30,
                            "pool_win_2": 20,
                        },
                    }
                    for order in range(15)
                ],
            }
        },
    )
    plan = SimpleNamespace(
        drawing=4_975,
        drawing_id=12_033,
        ended_at=datetime(2026, 8, 14, 14, 0, tzinfo=timezone.utc),
        requested_bank=4_980,
        stake=30,
    )

    frozen = frozen_input_from_snapshot(snapshot, plan)

    assert frozen.source_captured_at == "2026-08-14T13:40:00.000000Z"
    assert frozen.as_of == frozen.source_captured_at
    assert frozen.bk_probability_matrix[0] == (0.55, 0.25, 0.2)
    assert frozen.crowd_probability_matrix[0] != (0.5, 0.3, 0.2)
    assert sum(frozen.crowd_probability_matrix[0]) == pytest.approx(1.0)


def test_compare_package_strategies_cli_help():
    result = CliRunner().invoke(app, ["compare-package-strategies", "--help"])

    assert result.exit_code == 0
    assert "--final-input" in result.stdout
    assert "--scheduler-plan" in result.stdout


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


def _result(
    frozen: FrozenStrategyInput,
    strategy_id: str,
    coupons: tuple[str, ...],
    *,
    category: int = 13,
) -> StrategyResult:
    import hashlib

    package_sha = hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode()
    ).hexdigest()
    return StrategyResult(
        strategy_id=strategy_id,
        strategy_version="v1",
        source_engine="test",
        category=category,
        input_sha256=frozen.input_sha256,
        config_sha256="c" * 64,
        package_sha256=package_sha,
        requested_bank=frozen.bank,
        stake=frozen.stake,
        coupons=coupons,
        cost=len(coupons) * frozen.stake,
        unused_bank=frozen.bank - len(coupons) * frozen.stake,
        probability_at_least_13=0.10,
        probability_at_least_14=0.05,
        probability_at_least_15=0.01,
        runtime_seconds=0.1,
        timed_out=False,
    )
