from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean, median

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.optimizer.brief import EventBriefAnalysis, analyze_event
from toto_ai.optimizer.brief_backtest import best_coupon_hits, build_result_string
from toto_ai.optimizer.coupon_probabilities import (
    ProbabilityMatrix,
    coupon_log_probability,
    normalize_probability_matrix,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyBacktestRow,
    StrategyConfig,
    StrategyPackage,
    build_packages_for_probabilities,
)

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


@dataclass(frozen=True)
class StrategyDiagnosticsRow:
    drawing_id: int
    drawing_number: int | None
    result_string: str
    baseline_brief_best_hits: int
    baseline_brief_nearest_hamming: int
    baseline_brief_hit_13: bool
    baseline_brief_hit_14: bool
    baseline_brief_hit_15: bool
    baseline_brief_package_size: int
    baseline_brief_package_cost: int
    baseline_brief_estimated_coverage: float
    baseline_brief_candidate_count: int
    baseline_brief_runtime_seconds: float
    baseline_brief_min_log_probability: float
    baseline_brief_median_log_probability: float
    baseline_brief_mean_log_probability: float
    baseline_brief_max_log_probability: float
    baseline_brief_mean_pairwise_hamming: float
    top_probability_best_hits: int
    top_probability_nearest_hamming: int
    top_probability_hit_13: bool
    top_probability_hit_14: bool
    top_probability_hit_15: bool
    top_probability_package_size: int
    top_probability_package_cost: int
    top_probability_estimated_coverage: float
    top_probability_candidate_count: int
    top_probability_runtime_seconds: float
    top_probability_min_log_probability: float
    top_probability_median_log_probability: float
    top_probability_mean_log_probability: float
    top_probability_max_log_probability: float
    top_probability_mean_pairwise_hamming: float
    weighted_coverage_best_hits: int
    weighted_coverage_nearest_hamming: int
    weighted_coverage_hit_13: bool
    weighted_coverage_hit_14: bool
    weighted_coverage_hit_15: bool
    weighted_coverage_package_size: int
    weighted_coverage_package_cost: int
    weighted_coverage_estimated_coverage: float
    weighted_coverage_candidate_count: int
    weighted_coverage_runtime_seconds: float
    weighted_coverage_min_log_probability: float
    weighted_coverage_median_log_probability: float
    weighted_coverage_mean_log_probability: float
    weighted_coverage_max_log_probability: float
    weighted_coverage_mean_pairwise_hamming: float
    weighted_minus_top_best_hits: int
    top_weighted_intersection_size: int
    top_weighted_jaccard: float
    top_unique_mean_log_probability: float | None
    weighted_unique_mean_log_probability: float | None


@dataclass(frozen=True)
class StrategyDiagnosticsResult:
    rows: list[StrategyDiagnosticsRow]
    config: StrategyConfig
    manifest: dict[str, object]


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


def run_strategy_diagnostics(
    session: Session,
    manifest: dict[str, object],
    frozen_csv_path: str | Path,
    package_builder=build_packages_for_probabilities,
) -> StrategyDiagnosticsResult:
    development_ids = development_drawing_ids(manifest)
    frozen_rows = load_frozen_development_rows(frozen_csv_path, manifest)
    config = _config_from_manifest(manifest)
    rows = []

    for drawing_id in development_ids:
        probabilities, analyses = _load_development_inputs(session, drawing_id)
        packages = _build_development_packages(
            probabilities,
            analyses,
            drawing_id,
            config,
            package_builder,
        )
        _validate_package_set(packages, max_coupons=config.max_coupons)
        for package in packages:
            frozen = frozen_rows[(drawing_id, package.strategy)]
            actual_hash = sha256(",".join(package.coupons).encode("utf-8")).hexdigest()
            if actual_hash != frozen.package_hash:
                raise ValueError(
                    f"Development package hash mismatch for {drawing_id}."
                )

        result_string = _load_development_result(session, drawing_id)
        frozen_by_strategy = {
            strategy: frozen_rows[(drawing_id, strategy)] for strategy in STRATEGIES
        }
        packages_by_strategy = {package.strategy: package for package in packages}
        best_hits_by_strategy = {}
        for strategy, package in packages_by_strategy.items():
            best_hits = best_coupon_hits(package.coupons, result_string)
            _validate_frozen_result_fields(
                frozen_by_strategy[strategy],
                best_hits,
            )
            best_hits_by_strategy[strategy] = best_hits

        drawing = session.get(Drawing, drawing_id)
        if drawing is None:
            raise ValueError(f"Development drawing {drawing_id} was not found.")
        rows.append(
            _build_diagnostics_row(
                drawing_id=drawing_id,
                drawing_number=drawing.number,
                result_string=result_string,
                packages=packages_by_strategy,
                frozen_rows=frozen_by_strategy,
                best_hits=best_hits_by_strategy,
                probabilities=probabilities,
                stake=config.stake,
            )
        )

    return StrategyDiagnosticsResult(rows=rows, config=config, manifest=manifest)


def _config_from_manifest(manifest: dict[str, object]) -> StrategyConfig:
    config = manifest.get("config")
    if not isinstance(config, dict):
        raise ValueError("Frozen strategy manifest must include a config.")
    try:
        return StrategyConfig(**config)
    except (TypeError, ValueError) as error:
        raise ValueError("Frozen strategy manifest has an invalid config.") from error


def _load_development_inputs(
    session: Session,
    drawing_id: int,
) -> tuple[ProbabilityMatrix, list[EventBriefAnalysis]]:
    events = list(
        session.scalars(
            select(Event)
            .options(
                load_only(
                    Event.id,
                    Event.drawing_id,
                    Event.event_order,
                    Event.name,
                    Event.championship,
                    Event.sport,
                )
            )
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
    )
    quotes = {
        quote.event_order: quote
        for quote in session.scalars(
            select(Quote)
            .where(Quote.drawing_id == drawing_id)
            .order_by(Quote.event_order)
        ).all()
        if quote.event_order is not None
    }
    event_orders = [event.event_order for event in events]
    if event_orders != list(range(15)) or set(quotes) != set(range(15)):
        raise ValueError(f"Development drawing {drawing_id} is not eligible.")
    try:
        analyses = [
            analyze_event(event, quotes[event.event_order]) for event in events
        ]
    except (KeyError, ValueError) as error:
        raise ValueError(
            f"Development drawing {drawing_id} is not eligible."
        ) from error
    probabilities = normalize_probability_matrix(
        [analysis.bk for analysis in analyses]
    )
    return probabilities, analyses


def _build_development_packages(
    probabilities: ProbabilityMatrix,
    analyses: list[EventBriefAnalysis],
    drawing_id: int,
    config: StrategyConfig,
    package_builder,
) -> list[StrategyPackage]:
    return package_builder(probabilities, analyses, drawing_id, config)


def _validate_package_set(
    packages: list[StrategyPackage],
    max_coupons: int,
) -> None:
    if len(packages) != len(STRATEGIES) or {
        package.strategy for package in packages
    } != set(STRATEGIES):
        raise ValueError("Invalid development package set.")
    if any(package.timed_out for package in packages):
        raise ValueError("Development package generation timed out.")
    for package in packages:
        if not package.coupons or len(package.coupons) > max_coupons:
            raise ValueError("Invalid development package set.")
        if len(set(package.coupons)) != len(package.coupons):
            raise ValueError("Invalid development package set.")


def _load_development_result(session: Session, drawing_id: int) -> str:
    events = list(
        session.scalars(
            select(Event)
            .options(load_only(Event.id, Event.event_order, Event.result))
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
    )
    return build_result_string(events)


def _validate_frozen_result_fields(
    frozen: StrategyBacktestRow,
    best_hits: int,
) -> None:
    actual = (
        best_hits,
        best_hits >= 13,
        best_hits >= 14,
        best_hits == 15,
    )
    expected = (
        frozen.best_hits,
        frozen.hit_13,
        frozen.hit_14,
        frozen.hit_15,
    )
    if actual != expected:
        raise ValueError("Development frozen result fields do not match.")


def _build_diagnostics_row(
    drawing_id: int,
    drawing_number: int | None,
    result_string: str,
    packages: dict[str, StrategyPackage],
    frozen_rows: dict[str, StrategyBacktestRow],
    best_hits: dict[str, int],
    probabilities: ProbabilityMatrix,
    stake: int,
) -> StrategyDiagnosticsRow:
    values: dict[str, int | float | bool | str | None] = {
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "result_string": result_string,
    }
    for strategy in STRATEGIES:
        package = packages[strategy]
        frozen = frozen_rows[strategy]
        structure = package_structure_metrics(package.coupons, probabilities)
        hits = best_hits[strategy]
        values.update(
            {
                f"{strategy}_best_hits": hits,
                f"{strategy}_nearest_hamming": len(result_string) - hits,
                f"{strategy}_hit_13": hits >= 13,
                f"{strategy}_hit_14": hits >= 14,
                f"{strategy}_hit_15": hits == 15,
                f"{strategy}_package_size": len(package.coupons),
                f"{strategy}_package_cost": len(package.coupons) * stake,
                f"{strategy}_estimated_coverage": frozen.estimated_coverage,
                f"{strategy}_candidate_count": frozen.candidate_count,
                f"{strategy}_runtime_seconds": frozen.runtime_seconds,
                f"{strategy}_min_log_probability": structure.min_log_probability,
                f"{strategy}_median_log_probability": structure.median_log_probability,
                f"{strategy}_mean_log_probability": structure.mean_log_probability,
                f"{strategy}_max_log_probability": structure.max_log_probability,
                f"{strategy}_mean_pairwise_hamming": (
                    structure.mean_pairwise_hamming
                ),
            }
        )
    overlap = package_overlap_metrics(
        packages["top_probability"].coupons,
        packages["weighted_coverage"].coupons,
        probabilities,
    )
    values.update(
        {
            "weighted_minus_top_best_hits": (
                best_hits["weighted_coverage"] - best_hits["top_probability"]
            ),
            "top_weighted_intersection_size": overlap.intersection_size,
            "top_weighted_jaccard": overlap.jaccard,
            "top_unique_mean_log_probability": (
                overlap.top_unique_mean_log_probability
            ),
            "weighted_unique_mean_log_probability": (
                overlap.weighted_unique_mean_log_probability
            ),
        }
    )
    return StrategyDiagnosticsRow(**values)


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
