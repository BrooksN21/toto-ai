from __future__ import annotations

import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean

from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing
from toto_ai.optimizer.brief_backtest import best_coupon_hits
from toto_ai.optimizer.coupon_candidates import (
    generate_candidate_coupons,
    sample_scenarios,
)
from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    top_probability_coupons,
)
from toto_ai.optimizer.direct_package import (
    estimate_package_coverage,
    select_hybrid_package,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyConfig,
    StrategyPackage,
    _validate_strategy_config,
)
from toto_ai.optimizer.strategy_diagnostics import (
    _config_from_manifest,
    _load_development_inputs,
    _load_development_result,
    _validate_frozen_result_fields,
    development_drawing_ids,
    load_frozen_development_rows,
    package_overlap_metrics,
    package_structure_metrics,
)

HYBRID_CORE_FRACTIONS = (0.50, 0.75, 0.90)
HYBRID_FOLD_COUNT = 5
HYBRID_BANK = 5000
HYBRID_STAKE = 30
HYBRID_CATEGORY = 13
HYBRID_MAX_COUPONS = HYBRID_BANK // HYBRID_STAKE


@dataclass(frozen=True)
class HybridEvaluationRow:
    drawing_id: int
    drawing_number: int | None
    fold: int
    strategy: str
    core_fraction: float | None
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    timed_out: bool
    mean_log_probability: float
    mean_pairwise_hamming: float
    top_intersection_size: int
    top_jaccard: float


@dataclass(frozen=True)
class HybridDecision:
    status: str
    selected_core_fraction: float | None
    passing_core_fractions: tuple[float, ...]
    reason: str


@dataclass(frozen=True)
class HybridEvaluationResult:
    rows: list[HybridEvaluationRow]
    summary: dict[str, object]
    decision: HybridDecision
    manifest: dict[str, object]


def run_hybrid_evaluation(
    session: Session,
    manifest: dict[str, object],
    frozen_csv_path: str | Path,
    progress_callback=None,
) -> HybridEvaluationResult:
    development_ids = development_drawing_ids(manifest)
    folds = assign_chronological_folds(development_ids)
    config = _config_from_manifest(manifest)
    _validate_hybrid_protocol(config)
    frozen_rows = load_frozen_development_rows(frozen_csv_path, manifest)
    rows = []

    for drawing_index, drawing_id in enumerate(development_ids, start=1):
        if progress_callback is not None:
            progress_callback(
                {
                    "drawing_id": drawing_id,
                    "drawing_index": drawing_index,
                    "drawing_total": len(development_ids),
                }
            )
        probabilities, _analyses = _load_development_inputs(session, drawing_id)
        packages = _build_hybrid_packages(probabilities, drawing_id, config)
        _validate_hybrid_package_set(packages, config, len(probabilities))
        packages_by_strategy = {package.strategy: package for package in packages}
        top_package = packages_by_strategy["top_probability"]
        top_frozen = frozen_rows[(drawing_id, "top_probability")]
        _verify_top_package_hash(top_package, top_frozen, drawing_id)

        result_string = _load_development_result(session, drawing_id)
        top_best_hits = best_coupon_hits(top_package.coupons, result_string)
        _validate_frozen_result_fields(top_frozen, top_best_hits)

        drawing = session.get(Drawing, drawing_id)
        if drawing is None:
            raise ValueError(f"Development drawing {drawing_id} was not found.")
        rows.extend(
            _build_hybrid_evaluation_rows(
                drawing_id=drawing_id,
                drawing_number=drawing.number,
                fold=folds[drawing_id],
                packages=packages,
                probabilities=probabilities,
                result_string=result_string,
                stake=config.stake,
            )
        )

    summary = summarize_hybrid_evaluation(rows)
    decision = decide_hybrid_experiment(summary)
    return HybridEvaluationResult(rows, summary, decision, manifest)


def _validate_hybrid_protocol(config: StrategyConfig) -> None:
    if (
        config.bank,
        config.stake,
        config.category,
        config.max_coupons,
    ) != (
        HYBRID_BANK,
        HYBRID_STAKE,
        HYBRID_CATEGORY,
        HYBRID_MAX_COUPONS,
    ):
        raise ValueError(
            "Hybrid evaluation requires the fixed protocol: bank=5000, "
            "stake=30, category=13."
        )
    _validate_strategy_config(config)


def _build_hybrid_packages(
    probabilities: ProbabilityMatrix,
    drawing_id: int,
    config: StrategyConfig,
) -> list[StrategyPackage]:
    started = time.perf_counter()
    deadline = (
        None
        if config.timeout_per_drawing is None
        else started + config.timeout_per_drawing
    )

    top_started = time.perf_counter()
    top_coupons = top_probability_coupons(
        probabilities,
        limit=config.max_coupons,
    )
    top_package = StrategyPackage(
        strategy="top_probability",
        coupons=list(top_coupons),
        estimated_coverage=0.0,
        candidate_count=len(top_coupons),
        runtime_seconds=time.perf_counter() - top_started,
        timed_out=False,
    )
    _validate_hybrid_package(top_package, config, len(probabilities))

    candidate_seed = config.seed ^ drawing_id ^ 0xC3C3
    candidates = generate_candidate_coupons(
        probabilities,
        max_coupons=config.max_coupons,
        top_count=config.top_count,
        sample_count=config.candidate_samples,
        mutation_limit=config.mutation_limit,
        seed=candidate_seed,
    )
    optimization_seed = config.seed ^ drawing_id ^ 0xA5A5
    optimization_scenarios = sample_scenarios(
        probabilities,
        count=config.optimization_samples,
        seed=optimization_seed,
    )
    validation_seed = config.seed ^ drawing_id ^ 0x5A5A
    validation_scenarios = sample_scenarios(
        probabilities,
        count=config.validation_samples,
        seed=validation_seed,
    )
    top_package = StrategyPackage(
        strategy=top_package.strategy,
        coupons=top_package.coupons,
        estimated_coverage=estimate_package_coverage(
            top_coupons,
            validation_scenarios,
            config.category,
        ),
        candidate_count=top_package.candidate_count,
        runtime_seconds=top_package.runtime_seconds,
        timed_out=top_package.timed_out,
    )

    packages = [top_package]
    for core_fraction in HYBRID_CORE_FRACTIONS:
        selection_started = time.perf_counter()
        selected = select_hybrid_package(
            candidates=candidates,
            scenarios=optimization_scenarios,
            probabilities=probabilities,
            category=config.category,
            max_coupons=config.max_coupons,
            top_coupons=top_coupons,
            core_fraction=core_fraction,
            deadline=deadline,
        )
        hybrid_package = StrategyPackage(
            strategy=f"hybrid_{core_fraction:.2f}",
            coupons=list(selected.selected_coupons),
            estimated_coverage=0.0,
            candidate_count=len(candidates),
            runtime_seconds=time.perf_counter() - selection_started,
            timed_out=selected.timed_out,
        )
        _validate_hybrid_package(hybrid_package, config, len(probabilities))
        packages.append(
            StrategyPackage(
                strategy=hybrid_package.strategy,
                coupons=hybrid_package.coupons,
                estimated_coverage=estimate_package_coverage(
                    hybrid_package.coupons,
                    validation_scenarios,
                    config.category,
                ),
                candidate_count=hybrid_package.candidate_count,
                runtime_seconds=hybrid_package.runtime_seconds,
                timed_out=hybrid_package.timed_out,
            )
        )
    return packages


def _validate_hybrid_package_set(
    packages: list[StrategyPackage],
    config: StrategyConfig,
    coupon_length: int,
) -> None:
    expected_strategies = (
        "top_probability",
        *(f"hybrid_{fraction:.2f}" for fraction in HYBRID_CORE_FRACTIONS),
    )
    if len(packages) != len(expected_strategies) or {
        package.strategy for package in packages
    } != set(expected_strategies):
        raise ValueError("Hybrid package strategy identities are invalid.")
    for package in packages:
        _validate_hybrid_package(package, config, coupon_length)


def _validate_hybrid_package(
    package: StrategyPackage,
    config: StrategyConfig,
    coupon_length: int,
) -> None:
    package_cost = len(package.coupons) * config.stake
    if package_cost > config.bank:
        raise ValueError("Hybrid package exceeds the configured budget.")
    if len(package.coupons) != config.max_coupons:
        raise ValueError(
            f"Hybrid package must contain exactly {config.max_coupons} coupons."
        )
    if len(set(package.coupons)) != len(package.coupons):
        raise ValueError("Hybrid package must contain unique coupons.")
    if any(len(coupon) != coupon_length for coupon in package.coupons):
        raise ValueError("Hybrid package must contain valid coupon shapes.")
    if any(set(coupon) - set(OUTCOMES) for coupon in package.coupons):
        raise ValueError("Hybrid package must contain valid coupon outcomes.")
    if package.timed_out:
        raise ValueError("Hybrid package generation timed out.")


def _verify_top_package_hash(
    top_package: StrategyPackage,
    frozen_row,
    drawing_id: int,
) -> None:
    actual_hash = sha256(",".join(top_package.coupons).encode("utf-8")).hexdigest()
    if actual_hash != frozen_row.package_hash:
        raise ValueError(f"Development top package hash mismatch for {drawing_id}.")


def _build_hybrid_evaluation_rows(
    drawing_id: int,
    drawing_number: int | None,
    fold: int,
    packages: list[StrategyPackage],
    probabilities: ProbabilityMatrix,
    result_string: str,
    stake: int,
) -> list[HybridEvaluationRow]:
    core_fractions = {
        "top_probability": None,
        **{
            f"hybrid_{fraction:.2f}": fraction
            for fraction in HYBRID_CORE_FRACTIONS
        },
    }
    packages_by_strategy = {package.strategy: package for package in packages}
    top_coupons = packages_by_strategy["top_probability"].coupons
    rows = []
    for package in packages:
        best_hits = best_coupon_hits(package.coupons, result_string)
        structure = package_structure_metrics(package.coupons, probabilities)
        overlap = package_overlap_metrics(
            top_coupons,
            package.coupons,
            probabilities,
        )
        rows.append(
            HybridEvaluationRow(
                drawing_id=drawing_id,
                drawing_number=drawing_number,
                fold=fold,
                strategy=package.strategy,
                core_fraction=core_fractions[package.strategy],
                best_hits=best_hits,
                hit_13=best_hits >= 13,
                hit_14=best_hits >= 14,
                hit_15=best_hits == 15,
                package_size=len(package.coupons),
                package_cost=len(package.coupons) * stake,
                estimated_coverage=package.estimated_coverage,
                candidate_count=package.candidate_count,
                runtime_seconds=package.runtime_seconds,
                timed_out=package.timed_out,
                mean_log_probability=structure.mean_log_probability,
                mean_pairwise_hamming=structure.mean_pairwise_hamming,
                top_intersection_size=overlap.intersection_size,
                top_jaccard=overlap.jaccard,
            )
        )
    return rows


def assign_chronological_folds(drawing_ids: list[int]) -> dict[int, int]:
    if len(drawing_ids) % HYBRID_FOLD_COUNT:
        raise ValueError(
            "Development drawings must form five equal chronological folds."
        )
    fold_size = len(drawing_ids) // HYBRID_FOLD_COUNT
    if fold_size == 0:
        raise ValueError(
            "Development drawings must form five equal chronological folds."
        )
    return {
        drawing_id: index // fold_size + 1
        for index, drawing_id in enumerate(drawing_ids)
    }


def summarize_hybrid_evaluation(rows: list[HybridEvaluationRow]) -> dict[str, object]:
    strategy_names = (
        "top_probability",
        *(f"hybrid_{fraction:.2f}" for fraction in HYBRID_CORE_FRACTIONS),
    )
    rows_by_strategy = {strategy: [] for strategy in strategy_names}
    for row in rows:
        if row.strategy not in rows_by_strategy:
            raise ValueError(f"Unsupported hybrid evaluation strategy: {row.strategy}")
        rows_by_strategy[row.strategy].append(row)

    _validate_hybrid_evaluation_rows(rows_by_strategy)

    strategies = {
        strategy: _summarize_strategy(strategy_rows)
        for strategy, strategy_rows in rows_by_strategy.items()
    }
    top_folds = strategies["top_probability"]["folds"]
    for fraction in HYBRID_CORE_FRACTIONS:
        strategy = strategies[f"hybrid_{fraction:.2f}"]
        folds = strategy["folds"]
        strategy["strictly_winning_folds"] = sum(
            folds[fold]["hit_13"] > top_folds[fold]["hit_13"]
            for fold in range(1, HYBRID_FOLD_COUNT + 1)
        )
        strategy["non_losing_folds"] = sum(
            folds[fold]["hit_13"] >= top_folds[fold]["hit_13"]
            for fold in range(1, HYBRID_FOLD_COUNT + 1)
        )

    return {
        "drawing_count": len({row.drawing_id for row in rows}),
        "failure_count": sum(row.timed_out for row in rows),
        "strategies": strategies,
    }


def _validate_hybrid_evaluation_rows(
    rows_by_strategy: dict[str, list[HybridEvaluationRow]],
) -> None:
    expected_fractions = {
        "top_probability": None,
        **{
            f"hybrid_{fraction:.2f}": fraction
            for fraction in HYBRID_CORE_FRACTIONS
        },
    }
    seen_pairs = set()
    for strategy, strategy_rows in rows_by_strategy.items():
        expected_fraction = expected_fractions[strategy]
        for row in strategy_rows:
            if row.fold not in range(1, HYBRID_FOLD_COUNT + 1):
                raise ValueError("Hybrid evaluation fold must be in 1..5.")
            if expected_fraction is None:
                if row.core_fraction is not None:
                    raise ValueError(
                        "top_probability rows must have core_fraction=None."
                    )
            elif row.core_fraction != expected_fraction:
                raise ValueError(
                    f"{strategy} rows must have core_fraction={expected_fraction:.2f}."
                )
            pair = (strategy, row.drawing_id)
            if pair in seen_pairs:
                raise ValueError(
                    "Hybrid evaluation requires exactly one row per "
                    "(strategy, drawing_id)."
                )
            seen_pairs.add(pair)

    top_rows = rows_by_strategy["top_probability"]
    top_drawing_ids = {row.drawing_id for row in top_rows}
    for strategy_rows in rows_by_strategy.values():
        if {row.drawing_id for row in strategy_rows} != top_drawing_ids:
            raise ValueError(
                "All hybrid evaluation strategies must have identical drawing ID sets."
            )

    expected_folds = assign_chronological_folds(
        [row.drawing_id for row in top_rows]
    )
    expected_fold_size = len(top_drawing_ids) // HYBRID_FOLD_COUNT
    top_fold_drawing_ids = {
        fold: {row.drawing_id for row in top_rows if row.fold == fold}
        for fold in range(1, HYBRID_FOLD_COUNT + 1)
    }
    for fold, drawing_ids in top_fold_drawing_ids.items():
        if not drawing_ids:
            raise ValueError(f"Hybrid evaluation fold {fold} must not be empty.")
    for drawing_ids in top_fold_drawing_ids.values():
        if len(drawing_ids) != expected_fold_size:
            raise ValueError("Hybrid evaluation folds must be equal-sized.")

    for _strategy, strategy_rows in rows_by_strategy.items():
        for fold in range(1, HYBRID_FOLD_COUNT + 1):
            drawing_ids = {
                row.drawing_id for row in strategy_rows if row.fold == fold
            }
            if drawing_ids != top_fold_drawing_ids[fold]:
                raise ValueError(
                    "Each fold must contain the same drawing IDs across all "
                    "hybrid evaluation strategies."
                )
        for row in strategy_rows:
            if row.fold != expected_folds[row.drawing_id]:
                raise ValueError(
                    "Hybrid evaluation rows must use the chronological fold "
                    "assignment."
                )


def decide_hybrid_experiment(summary: dict[str, object]) -> HybridDecision:
    strategies = summary["strategies"]
    top_strategy = strategies["top_probability"]
    top_total = top_strategy["total"]
    top_average_best_hits = top_total["average_best_hits"]
    failure_count = summary["failure_count"]

    passing_fractions = tuple(
        fraction
        for fraction in HYBRID_CORE_FRACTIONS
        if failure_count == 0
        and _passes_go_predicate(
            strategies[f"hybrid_{fraction:.2f}"],
            top_total["hit_13"],
            top_average_best_hits,
        )
    )
    if not passing_fractions:
        reason = (
            "Operational failures were recorded."
            if failure_count
            else "No hybrid core fraction met every GO predicate."
        )
        return HybridDecision(
            status="STOP",
            selected_core_fraction=None,
            passing_core_fractions=(),
            reason=reason,
        )

    selected_fraction = max(
        passing_fractions,
        key=lambda fraction: _decision_rank(
            strategies[f"hybrid_{fraction:.2f}"], fraction
        ),
    )
    return HybridDecision(
        status="GO",
        selected_core_fraction=selected_fraction,
        passing_core_fractions=passing_fractions,
        reason=(
            "Selected the highest-ranked hybrid core fraction under the approved "
            "GO criteria."
        ),
    )


def _summarize_strategy(rows: list[HybridEvaluationRow]) -> dict[str, object]:
    folds = {
        fold: _summarize_rows([row for row in rows if row.fold == fold])
        for fold in range(1, HYBRID_FOLD_COUNT + 1)
    }
    return {
        "total": _summarize_rows(rows),
        "folds": folds,
        "average_mean_log_probability": (
            mean(row.mean_log_probability for row in rows) if rows else None
        ),
    }


def _summarize_rows(rows: list[HybridEvaluationRow]) -> dict[str, int | float | None]:
    return {
        "hit_13": sum(row.hit_13 for row in rows),
        "hit_14": sum(row.hit_14 for row in rows),
        "hit_15": sum(row.hit_15 for row in rows),
        "average_best_hits": mean(row.best_hits for row in rows) if rows else None,
    }


def _passes_go_predicate(
    strategy: dict[str, object],
    top_total_13: int,
    top_average_best_hits: float,
) -> bool:
    total = strategy["total"]
    return (
        total["hit_13"] >= top_total_13 + 2
        and strategy["non_losing_folds"] >= 4
        and total["average_best_hits"] >= top_average_best_hits
    )


def _decision_rank(strategy: dict[str, object], fraction: float) -> tuple[object, ...]:
    total = strategy["total"]
    return (
        total["hit_13"],
        strategy["strictly_winning_folds"],
        strategy["non_losing_folds"],
        total["average_best_hits"],
        strategy["average_mean_log_probability"],
        fraction,
    )
