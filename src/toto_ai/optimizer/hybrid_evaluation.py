from dataclasses import dataclass
from statistics import mean

HYBRID_CORE_FRACTIONS = (0.50, 0.75, 0.90)
HYBRID_FOLD_COUNT = 5


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
