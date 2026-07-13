from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

from toto_ai.optimizer.coupon_probabilities import (
    ProbabilityMatrix,
    coupon_log_probability,
)
from toto_ai.optimizer.strategy_backtest import StrategyBacktestRow

STRATEGIES = ("baseline_brief", "top_probability", "weighted_coverage")


@dataclass(frozen=True)
class PackageStructureMetrics:
    min_log_probability: float
    median_log_probability: float
    mean_log_probability: float
    max_log_probability: float
    mean_pairwise_hamming: float


@dataclass(frozen=True)
class PackageOverlapMetrics:
    intersection_size: int
    jaccard: float
    top_unique_mean_log_probability: float | None
    weighted_unique_mean_log_probability: float | None


def _hamming(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right, strict=True))


def package_structure_metrics(
    coupons: list[str],
    probabilities: ProbabilityMatrix,
) -> PackageStructureMetrics:
    logs = sorted(coupon_log_probability(coupon, probabilities) for coupon in coupons)
    distances = [
        _hamming(left, right)
        for index, left in enumerate(coupons)
        for right in coupons[index + 1 :]
    ]
    return PackageStructureMetrics(
        min(logs),
        median(logs),
        mean(logs),
        max(logs),
        mean(distances) if distances else 0.0,
    )


def package_overlap_metrics(
    top_coupons: list[str],
    weighted_coupons: list[str],
    probabilities: ProbabilityMatrix,
) -> PackageOverlapMetrics:
    top = set(top_coupons)
    weighted = set(weighted_coupons)
    union = top | weighted
    top_unique_logs = sorted(
        coupon_log_probability(coupon, probabilities)
        for coupon in top - weighted
    )
    weighted_unique_logs = sorted(
        coupon_log_probability(coupon, probabilities)
        for coupon in weighted - top
    )
    return PackageOverlapMetrics(
        len(top & weighted),
        len(top & weighted) / len(union) if union else 0.0,
        mean(top_unique_logs) if top_unique_logs else None,
        mean(weighted_unique_logs) if weighted_unique_logs else None,
    )


def development_drawing_ids(manifest: dict[str, object]) -> list[int]:
    last = int(manifest["last"])
    holdout = int(manifest["holdout_size"])
    drawing_ids = list(manifest["drawing_ids"])
    if len(set(drawing_ids)) != len(drawing_ids):
        raise ValueError("Manifest contains duplicate drawing IDs.")
    if len(drawing_ids) != last or holdout < 0 or holdout > last:
        raise ValueError("Invalid frozen development split.")
    return drawing_ids[: last - holdout]


def load_frozen_development_rows(
    path: str | Path,
    manifest: dict[str, object],
) -> dict[tuple[int, str], StrategyBacktestRow]:
    development = set(development_drawing_ids(manifest))
    rows: dict[tuple[int, str], StrategyBacktestRow] = {}
    with Path(path).open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            drawing_id = int(raw["drawing_id"])
            if drawing_id not in development:
                continue
            row = _parse_strategy_backtest_row(raw)
            if row.segment != "development":
                raise ValueError(
                    "Frozen development rows must use the development segment."
                )
            key = (drawing_id, row.strategy)
            if key in rows:
                raise ValueError("Expected exactly one frozen row per strategy.")
            rows[key] = row
    expected = {
        (drawing_id, strategy)
        for drawing_id in development
        for strategy in STRATEGIES
    }
    if set(rows) != expected:
        raise ValueError("Expected exactly one frozen row per strategy.")
    return rows


def _parse_strategy_backtest_row(raw: dict[str, str | None]) -> StrategyBacktestRow:
    return StrategyBacktestRow(
        drawing_id=int(raw["drawing_id"]),
        drawing_number=(
            None
            if not raw["drawing_number"]
            else int(raw["drawing_number"])
        ),
        segment=raw["segment"],
        strategy=raw["strategy"],
        best_hits=int(raw["best_hits"]),
        hit_13=_parse_bool(raw["hit_13"]),
        hit_14=_parse_bool(raw["hit_14"]),
        hit_15=_parse_bool(raw["hit_15"]),
        package_size=int(raw["package_size"]),
        package_cost=int(raw["package_cost"]),
        estimated_coverage=float(raw["estimated_coverage"]),
        candidate_count=int(raw["candidate_count"]),
        runtime_seconds=float(raw["runtime_seconds"]),
        package_hash=raw["package_hash"],
    )


def _parse_bool(value: str | None) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError("Frozen strategy boolean fields must be True or False.")
