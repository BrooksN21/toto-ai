import csv
import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from itertools import islice, product

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from toto_ai import cli as cli_module
from toto_ai.cli import app
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.optimizer import hybrid_evaluation as hybrid_module
from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix
from toto_ai.optimizer.direct_package import DirectPackageResult
from toto_ai.optimizer.hybrid_evaluation import (
    HybridDecision,
    HybridEvaluationResult,
    HybridEvaluationRow,
    assign_chronological_folds,
    decide_hybrid_experiment,
    run_hybrid_evaluation,
    summarize_hybrid_evaluation,
    write_hybrid_evaluation_reports,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyBacktestRow,
    StrategyConfig,
    StrategyPackage,
    _configuration_hash,
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


def fixture_evaluation_result(status="STOP"):
    config = StrategyConfig(
        bank=5000,
        stake=30,
        category=13,
        top_count=166,
        candidate_samples=1,
        mutation_limit=0,
        optimization_samples=2,
        validation_samples=3,
        timeout_per_drawing=None,
    )
    rows = valid_evaluation_rows()
    return HybridEvaluationResult(
        rows=rows,
        summary=summarize_hybrid_evaluation(rows),
        decision=HybridDecision(
            status=status,
            selected_core_fraction=0.50 if status == "GO" else None,
            passing_core_fractions=(0.50,) if status == "GO" else (),
            reason="No hybrid core fraction met every GO predicate.",
        ),
        manifest={
            "last": 500,
            "holdout_size": 150,
            "drawing_ids": list(range(1, 501)),
            "config": _config_payload(config),
            "configuration_hash": _configuration_hash(config),
        },
    )


def test_reports_are_deterministic_and_include_decision(tmp_path):
    result = fixture_evaluation_result(status="STOP")

    first_csv_path, first_markdown_path = write_hybrid_evaluation_reports(
        result,
        tmp_path,
    )
    first_csv = first_csv_path.read_bytes()
    first_markdown = first_markdown_path.read_bytes()
    second_csv_path, second_markdown_path = write_hybrid_evaluation_reports(
        result,
        tmp_path,
    )

    assert second_csv_path.read_bytes() == first_csv
    assert second_markdown_path.read_bytes() == first_markdown
    assert first_csv_path.name == "hybrid_evaluation_development_last_500_bank_5000.csv"
    rows = list(csv.DictReader(first_csv_path.open(encoding="utf-8")))
    assert [(int(row["drawing_id"]), row["strategy"]) for row in rows] == [
        (drawing_id, strategy)
        for drawing_id in range(1, 351)
        for strategy in (
            "top_probability",
            "hybrid_0.50",
            "hybrid_0.75",
            "hybrid_0.90",
        )
    ]
    markdown = first_markdown_path.read_text(encoding="utf-8")
    for text_value in (
        "## Configuration",
        "Development drawings: 350",
        "## Total Strategy Metrics",
        "## Fold 1 Metrics",
        "## Fold 5 Metrics",
        "## Structural Metrics",
        "Mean log probability",
        "Mean pairwise Hamming distance",
        "Top intersection",
        "Top Jaccard",
        "## GO Predicate Evaluation",
        "Decision: STOP",
        "Selected core fraction: none",
        "development-only",
        "no profitability",
    ):
        assert text_value in markdown


def test_report_failure_leaves_no_temporary_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        hybrid_module,
        "_render_hybrid_markdown",
        lambda *args: (_ for _ in ()).throw(OSError("render failed")),
    )

    with pytest.raises(OSError, match="render failed"):
        write_hybrid_evaluation_reports(fixture_evaluation_result(), tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_evaluate_hybrid_cli_uses_readonly_db_and_writes_reports(monkeypatch, tmp_path):
    db_path = tmp_path / "hybrid.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    config = StrategyConfig(bank=5000, stake=30, category=13)
    manifest = {
        "schema_version": 1,
        "code_version": "frozen",
        "last": 500,
        "holdout_size": 150,
        "drawing_ids": list(range(1, 501)),
        "input_data_hash": "data",
        "configuration_hash": _configuration_hash(config),
        "protocol_hash": "protocol",
        "config": _config_payload(config),
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    frozen_csv = tmp_path / "backtest.csv"
    frozen_csv.write_text("drawing_id\\n", encoding="utf-8")

    def fake_run(session, frozen_manifest, frozen_path, progress_callback):
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        with pytest.raises(OperationalError, match="readonly"):
            session.execute(text("CREATE TABLE forbidden (id INTEGER)"))
        assert frozen_manifest == manifest
        assert frozen_path == str(frozen_csv)
        progress_callback(
            {"drawing_id": 1, "drawing_index": 1, "drawing_total": 350}
        )
        return fixture_evaluation_result()

    monkeypatch.setattr(cli_module, "run_hybrid_evaluation", fake_run)
    monkeypatch.setattr(
        cli_module,
        "init_db",
        lambda *args: pytest.fail("evaluate-hybrid must not call init_db"),
    )

    result = CliRunner().invoke(
        app,
        [
            "evaluate-hybrid",
            "--db",
            str(db_path),
            "--manifest",
            str(manifest_path),
            "--backtest-csv",
            str(frozen_csv),
            "--report-dir",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 0
    assert "Hybrid Development Evaluation" in result.output
    assert "Decision" in result.output
    assert "Reports written to" in result.output


def test_evaluate_hybrid_help_exposes_only_fixed_path_options():
    result = CliRunner().invoke(app, ["evaluate-hybrid", "--help"])

    assert result.exit_code == 0
    for option in ("--db", "--manifest", "--backtest-csv", "--report-dir"):
        assert option in result.output
    for option in (
        "--bank",
        "--stake",
        "--category",
        "--fraction",
        "--fold",
        "--seed",
        "--timeout",
    ):
        assert option not in result.output


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


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        for drawing_id in range(1, 13):
            database_session.add(
                Drawing(
                    id=drawing_id,
                    number=1000 + drawing_id,
                    name="baltbet-main",
                    status="finished",
                )
            )
            for event_order in range(15):
                database_session.add(
                    Event(
                        drawing_id=drawing_id,
                        event_order=event_order,
                        name=f"Match {event_order + 1}",
                        result="1",
                    )
                )
                database_session.add(
                    Quote(
                        drawing_id=drawing_id,
                        event_order=event_order,
                        pool_win_1=50,
                        pool_draw=30,
                        pool_win_2=20,
                        bk_win_1=60,
                        bk_draw=30,
                        bk_win_2=10,
                    )
                )
        database_session.commit()
        yield database_session


@pytest.fixture
def manifest():
    config = StrategyConfig(
        bank=5000,
        stake=30,
        category=13,
        top_count=166,
        candidate_samples=1,
        mutation_limit=0,
        optimization_samples=2,
        validation_samples=3,
        timeout_per_drawing=None,
    )
    return {
        "last": 12,
        "holdout_size": 2,
        "drawing_ids": list(range(1, 13)),
        "config": _config_payload(config),
        "configuration_hash": _configuration_hash(config),
    }


@pytest.fixture
def coupons():
    return _valid_coupons(166)


@pytest.fixture
def frozen_csv(tmp_path, manifest, coupons):
    return _write_frozen_rows(
        tmp_path,
        drawing_ids=manifest["drawing_ids"][:10],
        top_coupons=coupons,
    )


def test_runner_never_loads_holdout_and_loads_results_after_top_hash(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
):
    calls = []
    input_ids = []
    result_ids = []
    _patch_valid_generation(monkeypatch, coupons)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda database_session, drawing_id: input_ids.append(drawing_id)
        or _fixture_inputs(),
    )
    monkeypatch.setattr(
        hybrid_module,
        "_verify_top_package_hash",
        lambda _package, _frozen, drawing_id: calls.append(("hash", drawing_id)),
    )
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda database_session, drawing_id: result_ids.append(drawing_id)
        or calls.append(("result", drawing_id))
        or "1" * 15,
    )

    result = run_hybrid_evaluation(session, manifest, frozen_csv)

    assert input_ids == manifest["drawing_ids"][:10]
    assert result_ids == manifest["drawing_ids"][:10]
    for drawing_id in manifest["drawing_ids"][:10]:
        assert calls.index(("hash", drawing_id)) < calls.index(("result", drawing_id))
    assert len(result.rows) == 40
    assert {row.strategy for row in result.rows} == {
        "top_probability",
        "hybrid_0.50",
        "hybrid_0.75",
        "hybrid_0.90",
    }


def test_runner_real_result_sql_follows_top_hash_for_every_development_drawing(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
):
    calls = []
    original_verify = hybrid_module._verify_top_package_hash
    _patch_valid_generation(monkeypatch, coupons)

    def record_hash(package, frozen_row, drawing_id):
        original_verify(package, frozen_row, drawing_id)
        calls.append(("hash", drawing_id))

    monkeypatch.setattr(hybrid_module, "_verify_top_package_hash", record_hash)

    with _capture_sql(session, calls):
        run_hybrid_evaluation(session, manifest, frozen_csv)

    development_ids = manifest["drawing_ids"][:10]
    assert [call for call in calls if call[0] == "result_sql"] == [
        ("result_sql", drawing_id) for drawing_id in development_ids
    ]
    for drawing_id in development_ids:
        assert calls.index(("hash", drawing_id)) < calls.index(
            ("result_sql", drawing_id)
        )


def test_runner_rejects_top_hash_before_loading_any_result(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
):
    _patch_valid_generation(monkeypatch, coupons)
    monkeypatch.setattr(
        hybrid_module,
        "top_probability_coupons",
        lambda *args, **kwargs: ["2" * 15, *coupons[1:]],
    )
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: pytest.fail("result loader must follow a verified top hash"),
    )

    with pytest.raises(ValueError, match="top package hash"):
        run_hybrid_evaluation(session, manifest, frozen_csv)


def test_runner_stops_at_later_top_hash_mismatch_before_result_or_holdout(
    monkeypatch,
    session,
    manifest,
    tmp_path,
    coupons,
):
    frozen_csv = _write_frozen_rows(
        tmp_path,
        drawing_ids=manifest["drawing_ids"][:10],
        top_coupons=coupons,
        top_hash_overrides={2: "mismatch"},
    )
    input_ids = []
    result_ids = []
    _patch_valid_generation(monkeypatch, coupons)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda database_session, drawing_id: input_ids.append(drawing_id)
        or _fixture_inputs(),
    )
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda database_session, drawing_id: result_ids.append(drawing_id)
        or "1" * 15,
    )

    with pytest.raises(ValueError, match="top package hash"):
        run_hybrid_evaluation(session, manifest, frozen_csv)

    assert input_ids == [1, 2]
    assert result_ids == [1]
    assert not set(manifest["drawing_ids"][-2:]) & set(input_ids + result_ids)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("best_hits", 14),
        ("hit_13", False),
        ("hit_14", False),
        ("hit_15", False),
    ],
)
def test_runner_rejects_altered_frozen_top_result_fields(
    monkeypatch,
    session,
    manifest,
    tmp_path,
    coupons,
    field_name,
    value,
):
    frozen_csv = _write_frozen_rows(
        tmp_path,
        drawing_ids=manifest["drawing_ids"][:10],
        top_coupons=coupons,
        top_overrides={field_name: value},
    )
    _patch_valid_generation(monkeypatch, coupons)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: "1" * 15,
    )

    with pytest.raises(ValueError, match="frozen result fields"):
        run_hybrid_evaluation(session, manifest, frozen_csv)


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("malformed", "valid coupon outcomes"),
        ("duplicate", "unique coupons"),
        ("short_coupon", "valid coupon shape"),
        ("over_budget", "exceeds the configured budget"),
        ("incomplete", "exactly 166 coupons"),
        ("timed_out", "timed out"),
    ],
)
def test_runner_fails_closed_on_invalid_hybrid_package_before_result_loading(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
    case,
    error,
):
    _patch_valid_generation(monkeypatch, coupons, hybrid_case=case)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: pytest.fail("invalid packages must not load results"),
    )

    with pytest.raises(ValueError, match=error):
        run_hybrid_evaluation(session, manifest, frozen_csv)


def test_runner_rejects_invalid_package_strategy_identity_before_hash(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
):
    _patch_valid_generation(monkeypatch, coupons)
    monkeypatch.setattr(
        hybrid_module,
        "_build_hybrid_packages",
        lambda *args: [
            StrategyPackage(
                strategy="top_probability",
                coupons=list(coupons),
                estimated_coverage=1.0,
                candidate_count=166,
                runtime_seconds=0.01,
                timed_out=False,
            ),
            *[
                StrategyPackage(
                    strategy="weighted_coverage",
                    coupons=list(coupons),
                    estimated_coverage=1.0,
                    candidate_count=166,
                    runtime_seconds=0.01,
                    timed_out=False,
                )
                for _ in range(3)
            ],
        ],
    )
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: pytest.fail("invalid package set must not load results"),
    )

    with pytest.raises(ValueError, match="strategy identities"):
        run_hybrid_evaluation(session, manifest, frozen_csv)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("bank", 4999), ("stake", 29), ("category", 14)],
)
def test_runner_rejects_any_non_fixed_protocol_configuration(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    field_name,
    value,
):
    config = dict(manifest["config"])
    config[field_name] = value
    altered = StrategyConfig(**config)
    manifest["config"] = _config_payload(altered)
    manifest["configuration_hash"] = _configuration_hash(altered)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda *args: pytest.fail("protocol must be validated before database access"),
    )

    with pytest.raises(ValueError, match="fixed protocol"):
        run_hybrid_evaluation(session, manifest, frozen_csv)


@pytest.mark.parametrize(
    ("drawing_ids", "last", "holdout_size", "error"),
    [
        (list(range(1, 11)) + [10, 12], 12, 2, "duplicate drawing IDs"),
        (list(range(1, 14)), 13, 2, "five equal chronological folds"),
    ],
)
def test_runner_rejects_invalid_development_manifest_before_database_access(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    drawing_ids,
    last,
    holdout_size,
    error,
):
    manifest["drawing_ids"] = drawing_ids
    manifest["last"] = last
    manifest["holdout_size"] = holdout_size
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda *args: pytest.fail("fold validation must precede database access"),
    )

    with pytest.raises(ValueError, match=error):
        run_hybrid_evaluation(session, manifest, frozen_csv)


def test_runner_generates_shared_inputs_once_and_keeps_hybrid_outputs_isolated(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    coupons,
):
    candidate_calls = 0
    optimization_calls = 0
    validation_calls = 0
    observations = []
    structure_coupon_ids = []
    shared_outputs = {}

    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda *args: _fixture_inputs(),
    )
    monkeypatch.setattr(
        hybrid_module,
        "top_probability_coupons",
        lambda *args, **kwargs: list(coupons),
    )

    def fake_candidates(*args, **kwargs):
        nonlocal candidate_calls
        candidate_calls += 1
        return list(coupons)

    def fake_scenarios(probabilities, count, seed):
        nonlocal optimization_calls, validation_calls
        if count == 2:
            optimization_calls += 1
        elif count == 3:
            validation_calls += 1
        else:
            pytest.fail(f"unexpected scenario count: {count}")
        return {"1" * 15: count}

    def fake_selector(*, candidates, scenarios, top_coupons, core_fraction, **kwargs):
        observations.append((core_fraction, id(candidates), id(scenarios)))
        output = shared_outputs.setdefault(id(candidates), list(top_coupons))
        return DirectPackageResult(output, 1, 1, 1.0, False)

    original_structure = hybrid_module.package_structure_metrics

    def capture_structure(coupon_list, probabilities):
        structure_coupon_ids.append(id(coupon_list))
        return original_structure(coupon_list, probabilities)

    monkeypatch.setattr(hybrid_module, "generate_candidate_coupons", fake_candidates)
    monkeypatch.setattr(hybrid_module, "sample_scenarios", fake_scenarios)
    monkeypatch.setattr(hybrid_module, "select_hybrid_package", fake_selector)
    monkeypatch.setattr(hybrid_module, "package_structure_metrics", capture_structure)
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: "1" * 15,
    )

    run_hybrid_evaluation(session, manifest, frozen_csv)

    assert candidate_calls == 10
    assert optimization_calls == 10
    assert validation_calls == 10
    assert [fraction for fraction, _, _ in observations] == [
        0.50,
        0.75,
        0.90,
    ] * 10
    for offset in range(0, len(observations), 3):
        assert len({value[1] for value in observations[offset : offset + 3]}) == 1
        assert len({value[2] for value in observations[offset : offset + 3]}) == 1
    for offset in range(0, len(structure_coupon_ids), 4):
        assert len(set(structure_coupon_ids[offset : offset + 4])) == 4


def _patch_valid_generation(monkeypatch, coupons, hybrid_case=None):
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda *args: _fixture_inputs(),
    )
    monkeypatch.setattr(
        hybrid_module,
        "top_probability_coupons",
        lambda *args, **kwargs: list(coupons),
    )
    monkeypatch.setattr(
        hybrid_module,
        "generate_candidate_coupons",
        lambda *args, **kwargs: list(coupons),
    )
    monkeypatch.setattr(
        hybrid_module,
        "sample_scenarios",
        lambda probabilities, count, seed: {"1" * 15: count},
    )

    def fake_selector(*, top_coupons, **kwargs):
        selected = list(top_coupons)
        timed_out = False
        if hybrid_case == "malformed":
            selected[0] = "Z" * 15
        elif hybrid_case == "duplicate":
            selected[-1] = selected[0]
        elif hybrid_case == "short_coupon":
            selected[0] = "1" * 14
        elif hybrid_case == "over_budget":
            selected.append(_valid_coupons(167)[-1])
        elif hybrid_case == "incomplete":
            selected.pop()
        elif hybrid_case == "timed_out":
            timed_out = True
        return DirectPackageResult(selected, 1, 1, 1.0, timed_out)

    monkeypatch.setattr(hybrid_module, "select_hybrid_package", fake_selector)


def _fixture_inputs():
    return normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}] * 15), []


def _valid_coupons(count):
    return [
        "".join(outcomes)
        for outcomes in islice(product(("1", "X", "2"), repeat=15), count)
    ]


def _write_frozen_rows(
    tmp_path,
    drawing_ids,
    top_coupons,
    top_overrides=None,
    top_hash_overrides=None,
):
    path = tmp_path / "hybrid-frozen.csv"
    top_overrides = top_overrides or {}
    top_hash_overrides = top_hash_overrides or {}
    fieldnames = list(StrategyBacktestRow.__dataclass_fields__)
    top_hash = hashlib.sha256(",".join(top_coupons).encode("utf-8")).hexdigest()
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for drawing_id in drawing_ids:
            for strategy in ("baseline_brief", "top_probability", "weighted_coverage"):
                values = {
                    "drawing_id": drawing_id,
                    "drawing_number": 1000 + drawing_id,
                    "segment": "development",
                    "strategy": strategy,
                    "best_hits": 15,
                    "hit_13": True,
                    "hit_14": True,
                    "hit_15": True,
                    "package_size": 166,
                    "package_cost": 4980,
                    "estimated_coverage": 1.0,
                    "candidate_count": 166,
                    "runtime_seconds": 0.01,
                    "package_hash": (
                        top_hash_overrides.get(drawing_id, top_hash)
                        if strategy == "top_probability"
                        else "0"
                    ),
                }
                if strategy == "top_probability":
                    values.update(top_overrides)
                writer.writerow(values)
    return path


def _config_payload(config):
    return {
        field_name: getattr(config, field_name)
        for field_name in StrategyConfig.__dataclass_fields__
    }


@contextmanager
def _capture_sql(session, calls):
    def record(connection, cursor, statement, parameters, context, executemany):
        if "from events" in statement.lower() and "events.result" in statement.lower():
            calls.append(("result_sql", parameters[0]))

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", record)
