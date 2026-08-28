"""Artifact-bound execution of the equal-input strategy comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.package_quality import PackageSelectionProvenance
from toto_ai.optimizer.strategy_comparison import (
    CategoryHitComparisonBundle,
    FrozenStrategyEvent,
    FrozenStrategyInput,
    StrategyComparisonBundle,
    run_category_hit_comparison,
    run_equal_input_comparison,
)
from toto_ai.optimizer.strategy_reports import (
    StrategyComparisonReportPaths,
    write_strategy_comparison_reports,
)
from toto_ai.runner.final_input import FinalInputSnapshot, load_final_input
from toto_ai.runner.scheduler import SchedulerPlan, load_scheduler_plan


@dataclass(frozen=True)
class ExecutedStrategyComparison:
    bundle: StrategyComparisonBundle
    reports: StrategyComparisonReportPaths


@dataclass(frozen=True)
class ExecutedCategoryHitComparison:
    bundle: CategoryHitComparisonBundle
    reports: StrategyComparisonReportPaths


def execute_final_input_comparison(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    output_dir: str | Path,
) -> ExecutedStrategyComparison:
    """Run all strategy variants from one validated scheduler final input."""
    plan_path = Path(scheduler_plan_path).absolute()
    snapshot_path = Path(final_input_path).absolute()
    plan = load_scheduler_plan(plan_path)
    snapshot = load_final_input(snapshot_path, expected_plan=plan)
    frozen = frozen_input_from_snapshot(snapshot, plan)
    config = plan.quality_v2_ev_config
    provenance = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=snapshot_path,
        probability_input_sha256=snapshot.probability_input_sha256,
        schedule_evidence_ledger_path=plan.schedule_evidence_ledger,
        scheduler_plan_path=plan_path,
        selection_config=config,
    )
    bundle = run_equal_input_comparison(
        frozen,
        ev_config=config,
        provenance=provenance,
    )
    reports = write_strategy_comparison_reports(bundle, output_dir)
    return ExecutedStrategyComparison(bundle=bundle, reports=reports)


def execute_final_input_category_hit_comparison(
    *,
    final_input_path: str | Path,
    scheduler_plan_path: str | Path,
    output_dir: str | Path,
) -> ExecutedCategoryHitComparison:
    """Run only fast probability-first candidates from a validated final input."""
    plan_path = Path(scheduler_plan_path).absolute()
    snapshot_path = Path(final_input_path).absolute()
    plan = load_scheduler_plan(plan_path)
    snapshot = load_final_input(snapshot_path, expected_plan=plan)
    frozen = frozen_input_from_snapshot(snapshot, plan)
    bundle = run_category_hit_comparison(frozen)
    reports = write_strategy_comparison_reports(bundle, output_dir)
    return ExecutedCategoryHitComparison(bundle=bundle, reports=reports)


def frozen_input_from_snapshot(
    snapshot: FinalInputSnapshot | Any,
    plan: SchedulerPlan | Any,
) -> FrozenStrategyInput:
    """Convert a validated final snapshot through the production EV parser."""
    captured_at = _utc_timestamp(snapshot.captured_at)
    ended_at = _utc_timestamp(plan.ended_at)
    ev_input = ev_input_from_payload(
        snapshot.payload,
        fetched_at=captured_at,
        stake=plan.stake,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    data = snapshot.payload.get("data")
    if not isinstance(data, Mapping):
        raise ValueError("final snapshot payload must contain a data object")
    raw_events = data.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("final snapshot payload must contain an events list")
    ordered = sorted(raw_events, key=lambda event: int(event["order"]))
    if len(ordered) != 15:
        raise ValueError("final snapshot must contain exactly 15 events")
    events = tuple(
        FrozenStrategyEvent(
            event_order=order,
            name=str(raw_event.get("name") or f"Event {order + 1}"),
            bk_probabilities=ev_input.true_probabilities[order],
            crowd_probabilities=ev_input.crowd_probabilities[order],
        )
        for order, raw_event in enumerate(ordered)
    )
    return FrozenStrategyInput(
        drawing_id=snapshot.drawing_id,
        drawing_number=snapshot.drawing_number,
        drawing_fingerprint=snapshot.target_fingerprint,
        source_captured_at=captured_at,
        as_of=captured_at,
        ended_at=ended_at,
        bank=plan.requested_bank,
        stake=plan.stake,
        pool_sum=ev_input.pool_sum,
        jackpot=ev_input.jackpot,
        possible_winnings=ev_input.possible_winnings,
        events=events,
    )


def _utc_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("strategy timestamps must be timezone-aware datetimes")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
