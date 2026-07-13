from dataclasses import replace

import pytest

from toto_ai.optimizer.hybrid_evaluation import (
    HybridEvaluationRow,
    assign_chronological_folds,
    decide_hybrid_experiment,
    summarize_hybrid_evaluation,
)


def test_assigns_five_exact_contiguous_folds():
    drawing_ids = list(range(1, 351))

    folds = assign_chronological_folds(drawing_ids)

    assert [folds[value] for value in drawing_ids[:70]] == [1] * 70
    assert [folds[value] for value in drawing_ids[-70:]] == [5] * 70


def test_rejects_development_count_not_divisible_by_five():
    with pytest.raises(ValueError, match="five equal chronological folds"):
        assign_chronological_folds(list(range(349)))


def test_summary_has_stable_strategy_and_fold_shape():
    rows = []
    top_fold_hits = [2, 1, 1, 1, 1]
    for fold, hit_count in enumerate(top_fold_hits, start=1):
        rows.extend(
            make_rows(
                fold=fold,
                strategy="top_probability",
                core_fraction=None,
                hit_13_count=hit_count,
                best_hits=8.7,
                mean_log_probability=-13.6,
            )
        )
    for core_fraction in (0.50, 0.75, 0.90):
        for fold, hit_count in enumerate(top_fold_hits, start=1):
            rows.extend(
                make_rows(
                    fold=fold,
                    strategy=f"hybrid_{core_fraction:.2f}",
                    core_fraction=core_fraction,
                    hit_13_count=hit_count,
                    best_hits=9.0,
                    mean_log_probability=-13.7,
                )
            )

    summary = summarize_hybrid_evaluation(rows)

    assert summary["drawing_count"] == 350
    assert summary["failure_count"] == 0
    assert summary["strategies"]["top_probability"] == {
        "total": {
            "hit_13": 6,
            "hit_14": 0,
            "hit_15": 0,
            "average_best_hits": 8.7,
        },
        "folds": {
            fold: {
                "hit_13": top_fold_hits[fold - 1],
                "hit_14": 0,
                "hit_15": 0,
                "average_best_hits": 8.7,
            }
            for fold in range(1, 6)
        },
        "average_mean_log_probability": -13.6,
    }
    assert summary["strategies"]["hybrid_0.50"]["strictly_winning_folds"] == 0
    assert summary["strategies"]["hybrid_0.50"]["non_losing_folds"] == 5


def test_summary_rejects_unsupported_strategy_to_keep_its_shape_stable():
    rows = make_rows(
        fold=1,
        strategy="weighted_coverage",
        core_fraction=None,
        hit_13_count=0,
        best_hits=9.0,
        mean_log_probability=-13.6,
    )

    with pytest.raises(ValueError, match="Unsupported hybrid evaluation strategy"):
        summarize_hybrid_evaluation(rows)


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("duplicate", "exactly one row"),
        ("missing", "identical drawing ID sets"),
        ("unpaired", "identical drawing ID sets"),
        ("out_of_range_fold", "fold must be in 1..5"),
        ("unequal_folds", "equal-sized"),
        ("empty_fold", "fold 5 must not be empty"),
        ("unpaired_fold", "same drawing IDs across all"),
        ("non_chronological", "chronological fold assignment"),
        ("top_fraction", "top_probability rows must have core_fraction=None"),
        ("hybrid_fraction", "core_fraction=0.50"),
    ],
)
def test_summary_rejects_invalid_evaluation_rows_before_aggregation(case, error):
    rows = valid_evaluation_rows()

    if case == "duplicate":
        rows.append(rows[0])
    elif case == "missing":
        rows = [
            row
            for row in rows
            if not (row.strategy == "hybrid_0.50" and row.drawing_id == 1)
        ]
    elif case == "unpaired":
        rows[0] = replace(rows[0], drawing_id=351)
    elif case == "out_of_range_fold":
        rows[0] = replace(rows[0], fold=6)
    elif case == "unequal_folds":
        rows[0] = replace(rows[0], fold=2)
    elif case == "empty_fold":
        rows = [row for row in rows if row.fold != 5]
    elif case == "unpaired_fold":
        hybrid_row = next(row for row in rows if row.strategy == "hybrid_0.50")
        rows[rows.index(hybrid_row)] = replace(hybrid_row, fold=2)
    elif case == "non_chronological":
        rows = [
            replace(row, fold={1: 2, 71: 1}.get(row.drawing_id, row.fold))
            for row in rows
        ]
    elif case == "top_fraction":
        rows[0] = replace(rows[0], core_fraction=0.50)
    else:
        hybrid_row = next(row for row in rows if row.strategy == "hybrid_0.50")
        rows[rows.index(hybrid_row)] = replace(hybrid_row, core_fraction=0.75)

    with pytest.raises(ValueError, match=error):
        summarize_hybrid_evaluation(rows)


def test_go_requires_two_extra_hits_four_non_losing_folds_and_no_lower_average():
    summary = fixture_summary(
        top_fold_hits=[2, 1, 1, 1, 1],
        candidates={
            0.50: {"fold_hits": [3, 1, 0, 1, 3], "best_hits": 9.0},
            0.75: {"fold_hits": [2, 1, 1, 1, 2], "best_hits": 10.0},
            0.90: {"fold_hits": [3, 0, 1, 0, 5], "best_hits": 10.0},
        },
    )

    decision = decide_hybrid_experiment(summary)

    assert decision.status == "GO"
    assert decision.selected_core_fraction == 0.50
    assert decision.passing_core_fractions == (0.50,)


def test_stop_selects_no_fraction_when_no_candidate_passes():
    summary = fixture_summary(
        top_fold_hits=[2, 1, 1, 1, 1],
        candidates={
            0.50: {"fold_hits": [2, 1, 1, 1, 2], "best_hits": 10.0},
            0.75: {"fold_hits": [3, 1, 1, 1, 2], "best_hits": 8.9},
            0.90: {"fold_hits": [3, 1, 1, 1, 2], "best_hits": 10.0},
        },
        timed_out=True,
    )

    decision = decide_hybrid_experiment(summary)

    assert decision.status == "STOP"
    assert decision.selected_core_fraction is None
    assert decision.passing_core_fractions == ()


def candidate(
    *,
    total_13=8,
    strictly_winning=1,
    non_losing=4,
    average_best=9.0,
    mean_log_probability=-13.6,
):
    return {
        "total": {
            "hit_13": total_13,
            "hit_14": 0,
            "hit_15": 0,
            "average_best_hits": average_best,
        },
        "folds": {},
        "strictly_winning_folds": strictly_winning,
        "non_losing_folds": non_losing,
        "average_mean_log_probability": mean_log_probability,
    }


@pytest.mark.parametrize(
    ("candidates", "expected_fraction"),
    [
        (
            {
                0.50: candidate(total_13=8, strictly_winning=1),
                0.75: candidate(total_13=9, strictly_winning=1),
                0.90: candidate(total_13=8, strictly_winning=1),
            },
            0.75,
        ),
        (
            {
                0.50: candidate(strictly_winning=1),
                0.75: candidate(strictly_winning=2),
                0.90: candidate(strictly_winning=1),
            },
            0.75,
        ),
        (
            {
                0.50: candidate(non_losing=4),
                0.75: candidate(non_losing=5),
                0.90: candidate(non_losing=4),
            },
            0.75,
        ),
        (
            {
                0.50: candidate(average_best=9.0),
                0.75: candidate(average_best=10.0),
                0.90: candidate(average_best=9.0),
            },
            0.75,
        ),
        (
            {
                0.50: candidate(mean_log_probability=-13.7),
                0.75: candidate(mean_log_probability=-13.6),
                0.90: candidate(mean_log_probability=-13.7),
            },
            0.75,
        ),
        (
            {
                0.50: candidate(),
                0.75: candidate(),
                0.90: candidate(),
            },
            0.90,
        ),
    ],
)
def test_go_tie_breaks_by_the_exact_deterministic_order(candidates, expected_fraction):
    summary = decision_summary(candidates)

    decision = decide_hybrid_experiment(summary)

    assert decision.status == "GO"
    assert decision.selected_core_fraction == expected_fraction


def make_rows(
    *,
    fold,
    strategy,
    core_fraction,
    hit_13_count,
    best_hits,
    mean_log_probability,
    timed_out=False,
):
    drawing_start = (fold - 1) * 70 + 1
    return [
        HybridEvaluationRow(
            drawing_id=drawing_start + index,
            drawing_number=drawing_start + index,
            fold=fold,
            strategy=strategy,
            core_fraction=core_fraction,
            best_hits=best_hits,
            hit_13=index < hit_13_count,
            hit_14=False,
            hit_15=False,
            package_size=166,
            package_cost=4980,
            estimated_coverage=0.01,
            candidate_count=100,
            runtime_seconds=0.1,
            timed_out=timed_out and fold == 1 and index == 0,
            mean_log_probability=mean_log_probability,
            mean_pairwise_hamming=4.0,
            top_intersection_size=166,
            top_jaccard=1.0,
        )
        for index in range(70)
    ]


def valid_evaluation_rows():
    rows = []
    for fold in range(1, 6):
        rows.extend(
            make_rows(
                fold=fold,
                strategy="top_probability",
                core_fraction=None,
                hit_13_count=0,
                best_hits=9.0,
                mean_log_probability=-13.6,
            )
        )
    for core_fraction in (0.50, 0.75, 0.90):
        for fold in range(1, 6):
            rows.extend(
                make_rows(
                    fold=fold,
                    strategy=f"hybrid_{core_fraction:.2f}",
                    core_fraction=core_fraction,
                    hit_13_count=0,
                    best_hits=9.0,
                    mean_log_probability=-13.7,
                )
            )
    return rows


def fixture_summary(top_fold_hits, candidates, timed_out=False):
    rows = []
    for fold, hit_count in enumerate(top_fold_hits, start=1):
        rows.extend(
            make_rows(
                fold=fold,
                strategy="top_probability",
                core_fraction=None,
                hit_13_count=hit_count,
                best_hits=9.0,
                mean_log_probability=-13.6,
            )
        )
    for core_fraction, candidate_values in candidates.items():
        for fold, hit_count in enumerate(candidate_values["fold_hits"], start=1):
            rows.extend(
                make_rows(
                    fold=fold,
                    strategy=f"hybrid_{core_fraction:.2f}",
                    core_fraction=core_fraction,
                    hit_13_count=hit_count,
                    best_hits=candidate_values["best_hits"],
                    mean_log_probability=-13.7,
                    timed_out=timed_out and core_fraction == 0.50,
                )
            )
    return summarize_hybrid_evaluation(rows)


def decision_summary(candidates):
    return {
        "drawing_count": 350,
        "failure_count": 0,
        "strategies": {
            "top_probability": candidate(total_13=6, average_best=9.0),
            **{
                f"hybrid_{core_fraction:.2f}": values
                for core_fraction, values in candidates.items()
            },
        },
    }
