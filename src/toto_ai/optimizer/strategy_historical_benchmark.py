"""Leakage-safe historical inputs and actual-outcome package scoring."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from io import StringIO
from itertools import combinations
from pathlib import Path
from random import Random
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.data_health import (
    audit_data_health,
    select_predeadline_raw_snapshots,
)
from toto_ai.collector.lifecycle import (
    RawArchive,
    RawArchiveRecord,
)
from toto_ai.db.models import (
    Drawing,
    DrawingRawSnapshot,
    DrawingResultSnapshot,
)
from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.ev.models import EVConfig
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    StrategyComparisonBundle,
    run_equal_input_comparison,
)

OUTCOMES = frozenset(("1", "X", "2"))
ACTUAL_OUTCOMES = OUTCOMES | {"*"}
BOOTSTRAP_SEED = 20_260_814
BOOTSTRAP_REPLICATES = 10_000


@dataclass(frozen=True)
class StrictHistoricalCase:
    frozen_input: FrozenStrategyInput
    actual: str
    raw_snapshot_sha256: str
    result_snapshot_sha256: str
    staleness_seconds: float


@dataclass(frozen=True)
class CouponPackageScore:
    strategy_id: str
    coupon_count: int
    best_hits: int
    average_hits: float
    median_hits: float
    hit_distribution: tuple[tuple[int, int], ...]
    category_counts: tuple[tuple[int, int], ...]
    actual_outcome_exposure: tuple[float, ...]
    zero_exposure_event_orders: tuple[int, ...]


@dataclass(frozen=True)
class PackageOverlap:
    intersection_count: int
    union_count: int
    jaccard: float


@dataclass(frozen=True)
class HistoricalStrategyRow:
    drawing_id: int
    drawing_number: int
    raw_snapshot_sha256: str
    result_snapshot_sha256: str
    input_sha256: str
    staleness_seconds: float
    actual: str
    bk_top_coupon: str
    bk_top_hits: int
    strategy_id: str
    strategy_version: str
    category: int
    config_sha256: str
    package_sha256: str
    coupon_count: int
    cost: int
    unused_bank: int
    probability_at_least_13: float
    probability_at_least_14: float
    probability_at_least_15: float
    best_hits: int
    average_hits: float
    median_hits: float
    hit_distribution: tuple[tuple[int, int], ...]
    category_counts: tuple[tuple[int, int], ...]
    hit_13: bool
    hit_14: bool
    hit_15: bool
    average_actual_outcome_exposure: float
    minimum_actual_outcome_exposure: float
    zero_exposure_event_orders: tuple[int, ...]
    runtime_seconds: float
    timed_out: bool
    fallback_reason: str | None
    coverage_rate: float | None
    guarantee_pass: bool | None


@dataclass(frozen=True)
class HistoricalOverlapRow:
    drawing_id: int
    drawing_number: int
    left_strategy_id: str
    right_strategy_id: str
    intersection_count: int
    union_count: int
    jaccard: float


@dataclass(frozen=True)
class StrictHistoricalBenchmark:
    rows: tuple[HistoricalStrategyRow, ...]
    overlaps: tuple[HistoricalOverlapRow, ...]
    summary: dict[str, object]
    bank: int
    stake: int


@dataclass(frozen=True)
class StrictHistoricalBenchmarkReportPaths:
    manifest: Path
    json: Path
    rows_csv: Path
    overlaps_csv: Path
    markdown: Path


def historical_ev_config(
    production_config: EVConfig,
    *,
    bank: int,
    stake: int,
) -> EVConfig:
    """Reuse the production objective at a requested historical budget."""
    if not isinstance(production_config, EVConfig):
        raise ValueError("production_config must be an EVConfig")
    return replace(
        production_config,
        bank=bank,
        stake=stake,
        effective_budget=bank,
        mode="research",
        package_provenance_required=False,
    )


def benchmark_strict_historical_cases(
    cases: Sequence[StrictHistoricalCase],
    *,
    ev_config: EVConfig,
    comparison_runner: Callable[..., StrategyComparisonBundle] = (
        run_equal_input_comparison
    ),
    progress_callback: Callable[[int, int, int, str], None] | None = None,
) -> StrictHistoricalBenchmark:
    """Run all equal-input strategies and score them against terminal results."""
    historical_cases = tuple(cases)
    if not historical_cases:
        raise ValueError("strict historical benchmark requires at least one case")
    if not isinstance(ev_config, EVConfig):
        raise ValueError("ev_config must be an EVConfig")
    if any(
        case.frozen_input.bank != ev_config.bank
        or case.frozen_input.stake != ev_config.stake
        for case in historical_cases
    ):
        raise ValueError("case bank and stake must match EV config")

    rows: list[HistoricalStrategyRow] = []
    overlaps: list[HistoricalOverlapRow] = []
    total = len(historical_cases)
    for index, case in enumerate(historical_cases, start=1):
        if progress_callback is not None:
            progress_callback(
                index,
                total,
                case.frozen_input.drawing_number,
                "running",
            )
        bundle = comparison_runner(
            case.frozen_input,
            ev_config=ev_config,
            provenance=None,
        )
        if bundle.frozen_input.input_sha256 != case.frozen_input.input_sha256:
            raise ValueError("comparison returned a foreign frozen input")
        bk_top_coupon, bk_top_hits = score_bk_top_control(
            case.frozen_input.bk_probability_matrix,
            case.actual,
        )
        for result in bundle.results:
            score = score_coupon_package(
                strategy_id=result.strategy_id,
                coupons=result.coupons,
                actual=case.actual,
            )
            rows.append(
                HistoricalStrategyRow(
                    drawing_id=case.frozen_input.drawing_id,
                    drawing_number=case.frozen_input.drawing_number,
                    raw_snapshot_sha256=case.raw_snapshot_sha256,
                    result_snapshot_sha256=case.result_snapshot_sha256,
                    input_sha256=case.frozen_input.input_sha256,
                    staleness_seconds=case.staleness_seconds,
                    actual=case.actual,
                    bk_top_coupon=bk_top_coupon,
                    bk_top_hits=bk_top_hits,
                    strategy_id=result.strategy_id,
                    strategy_version=result.strategy_version,
                    category=result.category,
                    config_sha256=result.config_sha256,
                    package_sha256=result.package_sha256,
                    coupon_count=result.coupon_count,
                    cost=result.cost,
                    unused_bank=result.unused_bank,
                    probability_at_least_13=(
                        result.probability_at_least_13
                    ),
                    probability_at_least_14=(
                        result.probability_at_least_14
                    ),
                    probability_at_least_15=(
                        result.probability_at_least_15
                    ),
                    best_hits=score.best_hits,
                    average_hits=score.average_hits,
                    median_hits=score.median_hits,
                    hit_distribution=score.hit_distribution,
                    category_counts=score.category_counts,
                    hit_13=score.best_hits >= 13,
                    hit_14=score.best_hits >= 14,
                    hit_15=score.best_hits >= 15,
                    average_actual_outcome_exposure=mean(
                        score.actual_outcome_exposure
                    ),
                    minimum_actual_outcome_exposure=min(
                        score.actual_outcome_exposure
                    ),
                    zero_exposure_event_orders=(
                        score.zero_exposure_event_orders
                    ),
                    runtime_seconds=result.runtime_seconds,
                    timed_out=result.timed_out,
                    fallback_reason=result.fallback_reason,
                    coverage_rate=result.coverage_rate,
                    guarantee_pass=result.guarantee_pass,
                )
            )
        for left, right in combinations(bundle.results, 2):
            overlap = package_overlap(left.coupons, right.coupons)
            overlaps.append(
                HistoricalOverlapRow(
                    drawing_id=case.frozen_input.drawing_id,
                    drawing_number=case.frozen_input.drawing_number,
                    left_strategy_id=left.strategy_id,
                    right_strategy_id=right.strategy_id,
                    intersection_count=overlap.intersection_count,
                    union_count=overlap.union_count,
                    jaccard=overlap.jaccard,
                )
            )
        if progress_callback is not None:
            progress_callback(
                index,
                total,
                case.frozen_input.drawing_number,
                "complete",
            )

    summary = _benchmark_summary(rows, overlaps, total)
    return StrictHistoricalBenchmark(
        rows=tuple(rows),
        overlaps=tuple(overlaps),
        summary=summary,
        bank=ev_config.bank,
        stake=ev_config.stake,
    )


def run_strict_historical_benchmark(
    session: Session,
    *,
    db_path: str | Path,
    last: int,
    bank: int,
    stake: int,
    ev_config: EVConfig,
    community: str = "baltbet-main",
    progress_callback: Callable[[int, int, int, str], None] | None = None,
    comparison_runner: Callable[..., StrategyComparisonBundle] = (
        run_equal_input_comparison
    ),
) -> StrictHistoricalBenchmark:
    cases = load_strict_historical_cases(
        session,
        db_path=db_path,
        last=last,
        bank=bank,
        stake=stake,
        community=community,
    )
    return benchmark_strict_historical_cases(
        cases,
        ev_config=ev_config,
        comparison_runner=comparison_runner,
        progress_callback=progress_callback,
    )


def write_strict_historical_benchmark_reports(
    benchmark: StrictHistoricalBenchmark,
    output_dir: str | Path,
) -> StrictHistoricalBenchmarkReportPaths:
    """Write hash-bound strict chronological benchmark artifacts."""
    if not isinstance(benchmark, StrictHistoricalBenchmark):
        raise ValueError("benchmark must be a StrictHistoricalBenchmark")
    root = Path(output_dir).absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("benchmark output directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)

    json_path = root / "benchmark.json"
    rows_path = root / "strategy_rows.csv"
    overlaps_path = root / "package_overlaps.csv"
    markdown_path = root / "benchmark.md"
    _atomic_write(json_path, _json_bytes(_benchmark_payload(benchmark)))
    _atomic_write(rows_path, _rows_csv(benchmark.rows).encode("utf-8"))
    _atomic_write(
        overlaps_path,
        _overlaps_csv(benchmark.overlaps).encode("utf-8"),
    )
    _atomic_write(
        markdown_path,
        _benchmark_markdown(benchmark).encode("utf-8"),
    )
    manifest_unsigned = {
        "schema_version": 1,
        "artifact_class": "RESEARCH/PAPER",
        "evidence_tier": "STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE",
        "release_evidence": False,
        "actionable": False,
        "automatic_wagering": False,
        "bank": benchmark.bank,
        "stake": benchmark.stake,
        "drawings_evaluated": benchmark.summary["drawings_evaluated"],
        "artifacts": {
            "benchmark_json": _artifact(root, json_path),
            "strategy_rows_csv": _artifact(root, rows_path),
            "package_overlaps_csv": _artifact(root, overlaps_path),
            "benchmark_markdown": _artifact(root, markdown_path),
        },
    }
    manifest_path = root / "manifest.json"
    manifest_sha256 = hashlib.sha256(
        _canonical_json_bytes(manifest_unsigned)
    ).hexdigest()
    _atomic_write(
        manifest_path,
        _json_bytes(
            {**manifest_unsigned, "manifest_sha256": manifest_sha256}
        ),
    )
    return StrictHistoricalBenchmarkReportPaths(
        manifest=manifest_path,
        json=json_path,
        rows_csv=rows_path,
        overlaps_csv=overlaps_path,
        markdown=markdown_path,
    )


def load_strict_historical_cases(
    session: Session,
    *,
    db_path: str | Path,
    last: int,
    bank: int,
    stake: int,
    community: str = "baltbet-main",
) -> tuple[StrictHistoricalCase, ...]:
    """Load latest true pre-deadline RAW plus separate terminal outcomes."""
    if type(last) is not int or last <= 0:
        raise ValueError("last must be a positive integer")
    if type(bank) is not int or type(stake) is not int or bank <= 0 or stake <= 0:
        raise ValueError("bank and stake must be positive integers")
    if bank % stake:
        raise ValueError("bank must be divisible by stake")

    resolved_db = Path(db_path).resolve()
    report = audit_data_health(
        session,
        db_path=resolved_db,
        use_case="historical_inventory",
        strict=False,
        community=community,
    )
    eligible_rows = sorted(
        (
            row
            for row in report.drawings
            if row.use_case_eligibility["historical_inventory"]
        ),
        key=lambda row: (
            row.drawing_number if row.drawing_number is not None else -1,
            row.drawing_id,
        ),
        reverse=True,
    )[:last]
    selected_ids = tuple(row.drawing_id for row in eligible_rows)
    if not selected_ids:
        return ()

    drawings = {
        drawing.id: drawing
        for drawing in session.scalars(
            select(Drawing).where(Drawing.id.in_(selected_ids))
        ).all()
    }
    raw_by_drawing = _group_by_drawing(
        session.scalars(
            select(DrawingRawSnapshot)
            .where(DrawingRawSnapshot.drawing_id.in_(selected_ids))
            .order_by(
                DrawingRawSnapshot.drawing_id,
                DrawingRawSnapshot.captured_at,
                DrawingRawSnapshot.snapshot_sha256,
            )
        ).all()
    )
    result_by_drawing = _group_by_drawing(
        session.scalars(
            select(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.drawing_id.in_(selected_ids))
            .order_by(
                DrawingResultSnapshot.drawing_id,
                DrawingResultSnapshot.retrieved_at,
                DrawingResultSnapshot.id,
            )
        ).all()
    )
    raw_root = resolved_db.parent / "raw"
    repository = RawArchive(raw_root / "archive")
    cases = []
    for row in reversed(eligible_rows):
        drawing = drawings[row.drawing_id]
        raw_candidates = select_predeadline_raw_snapshots(
            drawing,
            raw_by_drawing.get(drawing.id, ()),
            canonical_raw_root=raw_root,
        )
        if not raw_candidates:
            raise ValueError("strict drawing lost its pre-deadline RAW evidence")
        selected_raw = raw_candidates[-1]
        payload = repository.load(_raw_record(selected_raw))
        frozen = frozen_input_from_raw_payload(
            payload,
            captured_at=selected_raw.captured_at,
            bank=bank,
            stake=stake,
        )
        if (
            frozen.drawing_id != drawing.id
            or frozen.drawing_number != drawing.number
        ):
            raise ValueError("strict RAW identity does not match SQLite drawing")
        results = tuple(
            snapshot
            for snapshot in result_by_drawing.get(drawing.id, ())
            if snapshot.complete and snapshot.event_count == 15
        )
        if not results:
            raise ValueError("strict drawing lost its terminal result snapshot")
        result = results[-1]
        actual = _validated_actual(result.actual)
        deadline = _aware_datetime(frozen.ended_at, "ended_at")
        captured = _aware_datetime(
            frozen.source_captured_at,
            "source_captured_at",
        )
        cases.append(
            StrictHistoricalCase(
                frozen_input=frozen,
                actual=actual,
                raw_snapshot_sha256=selected_raw.snapshot_sha256,
                result_snapshot_sha256=result.snapshot_sha256,
                staleness_seconds=(deadline - captured).total_seconds(),
            )
        )
    return tuple(cases)


def frozen_input_from_raw_payload(
    payload: Mapping[str, object],
    *,
    captured_at: str | datetime,
    bank: int,
    stake: int,
) -> FrozenStrategyInput:
    """Extract only prediction-time fields from one immutable RAW payload."""
    captured = _aware_datetime(captured_at, "captured_at")
    captured_text = _utc_timestamp(captured)
    target = parse_target_drawing(payload, captured)
    if target.drawing_number is None:
        raise ValueError("historical drawing number must be present")
    ev_input = ev_input_from_payload(
        payload,
        fetched_at=captured_text,
        stake=stake,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    fingerprint = target_fingerprint(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        deadline=target.deadline,
        events=target.events,
    )
    events = tuple(
        FrozenStrategyEvent(
            event_order=event.event_order,
            name=f"{event.home_team} — {event.away_team}",
            bk_probabilities=ev_input.true_probabilities[event.event_order],
            crowd_probabilities=ev_input.crowd_probabilities[event.event_order],
        )
        for event in target.events
    )
    return FrozenStrategyInput(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        drawing_fingerprint=fingerprint,
        source_captured_at=captured_text,
        as_of=captured_text,
        ended_at=_utc_timestamp(target.deadline),
        bank=bank,
        stake=stake,
        pool_sum=ev_input.pool_sum,
        jackpot=ev_input.jackpot,
        possible_winnings=ev_input.possible_winnings,
        events=events,
    )


def score_coupon_package(
    *,
    strategy_id: str,
    coupons: Sequence[str],
    actual: str,
) -> CouponPackageScore:
    actual_value = _validated_actual(actual)
    package = tuple(coupons)
    if not strategy_id:
        raise ValueError("strategy_id must be non-empty")
    if not package:
        raise ValueError("coupon package must be non-empty")
    if len(set(package)) != len(package):
        raise ValueError("coupon package must contain unique coupons")
    if any(len(coupon) != 15 or set(coupon) - OUTCOMES for coupon in package):
        raise ValueError("coupons must contain exactly 15 outcomes")

    hits = tuple(
        sum(
            observed == "*" or predicted == observed
            for predicted, observed in zip(coupon, actual_value, strict=True)
        )
        for coupon in package
    )
    distribution = Counter(hits)
    exposures = []
    zero_exposure = []
    for index, observed in enumerate(actual_value):
        if observed == "*":
            exposures.append(1.0)
            continue
        count = sum(coupon[index] == observed for coupon in package)
        exposures.append(count / len(package))
        if count == 0:
            zero_exposure.append(index + 1)
    return CouponPackageScore(
        strategy_id=strategy_id,
        coupon_count=len(package),
        best_hits=max(hits),
        average_hits=float(mean(hits)),
        median_hits=float(median(hits)),
        hit_distribution=tuple(sorted(distribution.items())),
        category_counts=tuple(
            (category, distribution.get(category, 0))
            for category in range(10, 16)
        ),
        actual_outcome_exposure=tuple(exposures),
        zero_exposure_event_orders=tuple(zero_exposure),
    )


def package_overlap(
    left: Sequence[str],
    right: Sequence[str],
) -> PackageOverlap:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    intersection = left_set & right_set
    return PackageOverlap(
        intersection_count=len(intersection),
        union_count=len(union),
        jaccard=len(intersection) / len(union) if union else 1.0,
    )


def score_bk_top_control(
    probabilities: Sequence[Sequence[float]],
    actual: str,
) -> tuple[str, int]:
    """Return the deterministic single BK-top coupon and its actual hits."""
    actual_value = _validated_actual(actual)
    matrix = tuple(tuple(row) for row in probabilities)
    if len(matrix) != 15 or any(len(row) != 3 for row in matrix):
        raise ValueError("BK control requires a 15x3 probability matrix")
    outcomes = ("1", "X", "2")
    coupon = "".join(
        outcomes[
            max(
                range(3),
                key=lambda outcome_index: (
                    row[outcome_index],
                    -outcome_index,
                ),
            )
        ]
        for row in matrix
    )
    hits = sum(
        observed == "*" or predicted == observed
        for predicted, observed in zip(coupon, actual_value, strict=True)
    )
    return coupon, hits


def _benchmark_summary(
    rows: Sequence[HistoricalStrategyRow],
    overlaps: Sequence[HistoricalOverlapRow],
    drawing_count: int,
) -> dict[str, object]:
    strategy_ids = sorted({row.strategy_id for row in rows})
    strategies: dict[str, object] = {}
    for strategy_id in strategy_ids:
        strategy_rows = tuple(
            row for row in rows if row.strategy_id == strategy_id
        )
        strategies[strategy_id] = {
            "drawings": len(strategy_rows),
            "average_best_hits": mean(row.best_hits for row in strategy_rows),
            "median_best_hits": median(row.best_hits for row in strategy_rows),
            "average_coupon_hits": mean(
                row.average_hits for row in strategy_rows
            ),
            "hit_13_count": sum(row.hit_13 for row in strategy_rows),
            "hit_14_count": sum(row.hit_14 for row in strategy_rows),
            "hit_15_count": sum(row.hit_15 for row in strategy_rows),
            "hit_13_rate": mean(row.hit_13 for row in strategy_rows),
            "hit_14_rate": mean(row.hit_14 for row in strategy_rows),
            "hit_15_rate": mean(row.hit_15 for row in strategy_rows),
            "average_coupon_count": mean(
                row.coupon_count for row in strategy_rows
            ),
            "average_cost": mean(row.cost for row in strategy_rows),
            "average_unused_bank": mean(
                row.unused_bank for row in strategy_rows
            ),
            "average_modeled_probability_at_least_13": mean(
                row.probability_at_least_13 for row in strategy_rows
            ),
            "average_modeled_probability_at_least_14": mean(
                row.probability_at_least_14 for row in strategy_rows
            ),
            "average_modeled_probability_at_least_15": mean(
                row.probability_at_least_15 for row in strategy_rows
            ),
            "average_actual_outcome_exposure": mean(
                row.average_actual_outcome_exposure for row in strategy_rows
            ),
            "zero_exposure_drawings": sum(
                bool(row.zero_exposure_event_orders) for row in strategy_rows
            ),
            "timed_out_count": sum(row.timed_out for row in strategy_rows),
            "fallback_count": sum(
                row.fallback_reason is not None for row in strategy_rows
            ),
            "average_runtime_seconds": mean(
                row.runtime_seconds for row in strategy_rows
            ),
        }
    control_rows = _one_row_per_drawing(rows)
    paired_vs_bk = _paired_strategy_differences(
        rows,
        baseline_strategy_id="BK_PROBABILITY_ONLY",
        drawing_count=drawing_count,
    )
    paired_vs_bk_top = _paired_control_differences(
        rows,
        drawing_count=drawing_count,
    )
    return {
        "drawings_evaluated": drawing_count,
        "strategy_count": len(strategy_ids),
        "bank": rows[0].cost + rows[0].unused_bank,
        "stake": (rows[0].cost // rows[0].coupon_count),
        "evidence_tier": "STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE",
        "release_evidence": False,
        "winner_status": (
            "INCONCLUSIVE_SMALL_SAMPLE"
            if drawing_count < 30
            else "NO_AUTOMATIC_WINNER_SELECTION"
        ),
        "bk_top_control": {
            "drawings": len(control_rows),
            "average_hits": mean(row.bk_top_hits for row in control_rows),
            "median_hits": median(row.bk_top_hits for row in control_rows),
            "hit_13_count": sum(row.bk_top_hits >= 13 for row in control_rows),
            "hit_14_count": sum(row.bk_top_hits >= 14 for row in control_rows),
            "hit_15_count": sum(row.bk_top_hits >= 15 for row in control_rows),
        },
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "confidence_level": 0.95,
            "interpretation_minimum_drawings": 30,
        },
        "paired_best_hits_vs_bk_probability_only": paired_vs_bk,
        "paired_best_hits_vs_bk_top_control": paired_vs_bk_top,
        "strategies": strategies,
        "average_pairwise_jaccard": (
            mean(row.jaccard for row in overlaps) if overlaps else 1.0
        ),
    }


def _one_row_per_drawing(
    rows: Sequence[HistoricalStrategyRow],
) -> tuple[HistoricalStrategyRow, ...]:
    selected = {}
    for row in rows:
        selected.setdefault(row.drawing_id, row)
    return tuple(selected[drawing_id] for drawing_id in sorted(selected))


def paired_bootstrap_interval(
    differences: Sequence[float | int],
    *,
    drawing_count: int,
    seed: int = BOOTSTRAP_SEED,
    replicates: int = BOOTSTRAP_REPLICATES,
) -> dict[str, object]:
    """Deterministic paired bootstrap interval for one per-drawing metric."""
    values = tuple(float(value) for value in differences)
    if not values:
        raise ValueError("paired bootstrap requires at least one difference")
    if drawing_count != len(values):
        raise ValueError("paired bootstrap drawing count mismatch")
    if type(replicates) is not int or replicates <= 0:
        raise ValueError("bootstrap replicates must be positive")
    rng = Random(seed)
    samples = sorted(
        mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(replicates)
    )
    lower = samples[int(0.025 * (replicates - 1))]
    upper = samples[int(0.975 * (replicates - 1))]
    return {
        "paired_drawings": drawing_count,
        "mean_difference": mean(values),
        "ci_95_lower": lower,
        "ci_95_upper": upper,
        "nominal_interval_excludes_zero": lower > 0.0 or upper < 0.0,
        "interpretation_allowed": drawing_count >= 30,
    }


def _paired_strategy_differences(
    rows: Sequence[HistoricalStrategyRow],
    *,
    baseline_strategy_id: str,
    drawing_count: int,
) -> dict[str, object]:
    by_strategy = {
        strategy_id: {
            row.drawing_id: row.best_hits
            for row in rows
            if row.strategy_id == strategy_id
        }
        for strategy_id in sorted({row.strategy_id for row in rows})
    }
    baseline = by_strategy.get(baseline_strategy_id)
    if baseline is None or len(baseline) != drawing_count:
        raise ValueError("paired benchmark baseline is incomplete")
    drawing_ids = tuple(sorted(baseline))
    comparisons = {}
    for strategy_id, values in by_strategy.items():
        if set(values) != set(drawing_ids):
            raise ValueError("paired benchmark strategy drawings do not align")
        comparisons[strategy_id] = paired_bootstrap_interval(
            tuple(
                values[drawing_id] - baseline[drawing_id]
                for drawing_id in drawing_ids
            ),
            drawing_count=drawing_count,
            seed=BOOTSTRAP_SEED ^ int(
                hashlib.sha256(strategy_id.encode()).hexdigest()[:8],
                16,
            ),
        )
    return comparisons


def _paired_control_differences(
    rows: Sequence[HistoricalStrategyRow],
    *,
    drawing_count: int,
) -> dict[str, object]:
    controls = {
        row.drawing_id: row.bk_top_hits for row in _one_row_per_drawing(rows)
    }
    by_strategy = {
        strategy_id: {
            row.drawing_id: row.best_hits
            for row in rows
            if row.strategy_id == strategy_id
        }
        for strategy_id in sorted({row.strategy_id for row in rows})
    }
    if len(controls) != drawing_count:
        raise ValueError("BK-top control drawings are incomplete")
    comparisons = {}
    for strategy_id, values in by_strategy.items():
        if set(values) != set(controls):
            raise ValueError("control comparison drawings do not align")
        comparisons[strategy_id] = paired_bootstrap_interval(
            tuple(
                values[drawing_id] - controls[drawing_id]
                for drawing_id in sorted(controls)
            ),
            drawing_count=drawing_count,
            seed=(
                BOOTSTRAP_SEED
                ^ 0xB170
                ^ int(hashlib.sha256(strategy_id.encode()).hexdigest()[:8], 16)
            ),
        )
    return comparisons


def _benchmark_payload(
    benchmark: StrictHistoricalBenchmark,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_class": "RESEARCH/PAPER",
        "evidence_tier": "STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE",
        "release_evidence": False,
        "actionable": False,
        "automatic_wagering": False,
        "bank": benchmark.bank,
        "stake": benchmark.stake,
        "summary": benchmark.summary,
        "rows": [asdict(row) for row in benchmark.rows],
        "overlaps": [asdict(row) for row in benchmark.overlaps],
    }


def _rows_csv(rows: Sequence[HistoricalStrategyRow]) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    fields = tuple(HistoricalStrategyRow.__dataclass_fields__)
    writer.writerow(fields)
    for row in rows:
        values = asdict(row)
        writer.writerow(
            _csv_value(values[field])
            for field in fields
        )
    return stream.getvalue()


def _overlaps_csv(rows: Sequence[HistoricalOverlapRow]) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    fields = tuple(HistoricalOverlapRow.__dataclass_fields__)
    writer.writerow(fields)
    for row in rows:
        values = asdict(row)
        writer.writerow(values[field] for field in fields)
    return stream.getvalue()


def _benchmark_markdown(benchmark: StrictHistoricalBenchmark) -> str:
    lines = [
        "# Strict Historical Strategy Benchmark",
        "",
        "**RESEARCH/PAPER — NOT ACTIONABLE — NOT RELEASE EVIDENCE.**",
        "",
        "This report uses only immutable RAW snapshots captured at or before "
        "the drawing deadline. The strict sample validates chronology and the "
        "pipeline; it does not prove profitability.",
        "",
        f"- Drawings evaluated: {benchmark.summary['drawings_evaluated']}",
        f"- Bank / stake: {benchmark.bank} / {benchmark.stake}",
        f"- Winner status: `{benchmark.summary['winner_status']}`",
        "- BK top single-coupon average hits: "
        f"{benchmark.summary['bk_top_control']['average_hits']:.3f}",
        "",
        "| Strategy | Avg best | Median best | Hit 13+ | Hit 14+ | Hit 15 | "
        "Avg cost | Avg unused |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    strategies = benchmark.summary["strategies"]
    if not isinstance(strategies, Mapping):
        raise ValueError("benchmark strategy summary must be a mapping")
    for strategy_id in sorted(strategies):
        value = strategies[strategy_id]
        if not isinstance(value, Mapping):
            raise ValueError("strategy summary row must be a mapping")
        lines.append(
            f"| {strategy_id} | {value['average_best_hits']:.3f} | "
            f"{value['median_best_hits']:.3f} | "
            f"{value['hit_13_count']}/{value['drawings']} | "
            f"{value['hit_14_count']}/{value['drawings']} | "
            f"{value['hit_15_count']}/{value['drawings']} | "
            f"{value['average_cost']:.2f} | "
            f"{value['average_unused_bank']:.2f} |"
        )
    lines.extend(
        _paired_markdown_lines(
            benchmark.summary,
            key="paired_best_hits_vs_bk_probability_only",
            title="Paired best-hits difference vs BK probability-only package",
        )
    )
    lines.extend(
        _paired_markdown_lines(
            benchmark.summary,
            key="paired_best_hits_vs_bk_top_control",
            title="Paired best-hits difference vs BK-top single coupon",
        )
    )
    lines.extend(
        (
            "",
            "No strategy winner is declared from a small strict sample. "
            "Release decisions require prospective frozen evidence.",
            "",
        )
    )
    return "\n".join(lines)


def _paired_markdown_lines(
    summary: Mapping[str, object],
    *,
    key: str,
    title: str,
) -> list[str]:
    comparisons = summary.get(key)
    if not isinstance(comparisons, Mapping):
        raise ValueError("paired comparison summary must be a mapping")
    lines = [
        "",
        f"## {title}",
        "",
        "| Strategy | Mean delta | 95% bootstrap CI | Interpretation allowed |",
        "|---|---:|---:|---|",
    ]
    for strategy_id in sorted(comparisons):
        comparison = comparisons[strategy_id]
        if not isinstance(comparison, Mapping):
            raise ValueError("paired comparison row must be a mapping")
        lines.append(
            f"| {strategy_id} | {comparison['mean_difference']:.3f} | "
            f"[{comparison['ci_95_lower']:.3f}, "
            f"{comparison['ci_95_upper']:.3f}] | "
            f"{comparison['interpretation_allowed']} |"
        )
    return lines


def _csv_value(value: object) -> object:
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _artifact(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _raw_record(row: DrawingRawSnapshot) -> RawArchiveRecord:
    return RawArchiveRecord(
        snapshot_sha256=row.snapshot_sha256,
        payload_sha256=row.payload_sha256,
        metadata_sha256=row.metadata_sha256,
        drawing_id=row.drawing_id,
        drawing_number=row.drawing_number,
        captured_at=row.captured_at,
        source=row.source,
        source_endpoint=row.source_endpoint,
        lifecycle_status=row.lifecycle_status,
        payload_path=Path(row.payload_path),
        metadata_path=Path(row.metadata_path),
        created=False,
    )


def _group_by_drawing(rows: Sequence[object]) -> dict[int, tuple[object, ...]]:
    grouped: dict[int, list[object]] = {}
    for row in rows:
        grouped.setdefault(row.drawing_id, []).append(row)
    return {drawing_id: tuple(values) for drawing_id, values in grouped.items()}


def _validated_actual(value: str) -> str:
    if not isinstance(value, str) or len(value) != 15:
        raise ValueError("actual result must contain exactly 15 outcomes")
    if set(value) - ACTUAL_OUTCOMES:
        raise ValueError("actual result contains an unsupported outcome")
    return value


def _aware_datetime(value: str | datetime, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{name} must be an ISO timestamp") from error
    else:
        raise ValueError(f"{name} must be an aware timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _utc_timestamp(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
