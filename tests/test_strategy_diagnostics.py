import csv
import hashlib
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.optimizer import strategy_diagnostics as diagnostics_module
from toto_ai.optimizer.coupon_probabilities import (
    coupon_log_probability,
    normalize_probability_matrix,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyBacktestRow,
    StrategyConfig,
    StrategyPackage,
    _configuration_hash,
)
from toto_ai.optimizer.strategy_diagnostics import (
    StrategyDiagnosticsResult,
    StrategyDiagnosticsRow,
    development_drawing_ids,
    load_frozen_development_rows,
    package_overlap_metrics,
    package_structure_metrics,
    run_strategy_diagnostics,
    summarize_strategy_diagnostics,
    write_strategy_diagnostics_reports,
)

probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}] * 2)


def test_development_ids_exclude_holdout():
    manifest = {"last": 5, "holdout_size": 2, "drawing_ids": [1, 2, 3, 4, 5]}

    assert development_drawing_ids(manifest) == [1, 2, 3]


def test_development_ids_reject_duplicate_manifest_ids():
    manifest = {"last": 3, "holdout_size": 1, "drawing_ids": [1, 2, 2]}

    with pytest.raises(ValueError, match="duplicate drawing IDs"):
        development_drawing_ids(manifest)


def test_frozen_rows_require_one_row_per_development_strategy(tmp_path):
    path = write_frozen_rows(tmp_path, drawing_ids=[1], omit="weighted_coverage")

    with pytest.raises(ValueError, match="exactly one frozen row"):
        load_frozen_development_rows(
            path,
            {"last": 2, "holdout_size": 1, "drawing_ids": [1, 2]},
        )


def test_frozen_rows_require_development_segment(tmp_path):
    path = write_frozen_rows(tmp_path, drawing_ids=[1], segment="holdout")

    with pytest.raises(ValueError, match="development segment"):
        load_frozen_development_rows(
            path,
            {"last": 2, "holdout_size": 1, "drawing_ids": [1, 2]},
        )


def test_package_structure_metrics_measure_probability_and_diversity():
    metrics = package_structure_metrics(["11", "1X", "X1"], probabilities)

    assert metrics.mean_pairwise_hamming == pytest.approx(4 / 3)
    assert metrics.max_log_probability == coupon_log_probability(
        "11", probabilities
    )
    assert metrics.min_log_probability == coupon_log_probability("X1", probabilities)


def test_overlap_metrics_report_unique_coupon_probability():
    metrics = package_overlap_metrics(["11", "1X"], ["11", "X1"], probabilities)

    assert metrics.intersection_size == 1
    assert metrics.jaccard == pytest.approx(1 / 3)
    assert metrics.top_unique_mean_log_probability == coupon_log_probability(
        "1X", probabilities
    )
    assert metrics.weighted_unique_mean_log_probability == coupon_log_probability(
        "X1", probabilities
    )


def test_overlap_metrics_report_no_unique_coupon_probabilities_for_identical_packages():
    metrics = package_overlap_metrics(["11", "1X"], ["11", "1X"], probabilities)

    assert metrics.top_unique_mean_log_probability is None
    assert metrics.weighted_unique_mean_log_probability is None


def test_summary_reports_distributions_paired_transitions_and_quantiles():
    rows = [
        fixture_diagnostics_row(top_hits=13, weighted_hits=11),
        fixture_diagnostics_row(top_hits=12, weighted_hits=12),
        fixture_diagnostics_row(top_hits=10, weighted_hits=15),
    ]

    summary = summarize_strategy_diagnostics(rows)

    assert summary["best_hit_distributions"]["top_probability"] == {
        hits: (1 if hits in {10, 12, 13} else 0) for hits in range(16)
    }
    assert summary["weighted_vs_top"] == {"wins": 1, "ties": 1, "losses": 1}
    assert summary["paired_13_transitions"] == {
        "neither": 1,
        "both": 0,
        "top_only": 1,
        "weighted_only": 1,
    }
    assert summary["weighted_minus_top_best_hits"] == {
        "mean": pytest.approx(1),
        "p25": -2,
        "p50": 0,
        "p75": 5,
    }


def test_summary_reports_structural_averages_and_fixed_coverage_bins():
    rows = [
        fixture_diagnostics_row(
            drawing_id=1,
            top_hits=12,
            weighted_hits=13,
            top_coverage=0.0,
            weighted_coverage=0.0049,
        ),
        fixture_diagnostics_row(
            drawing_id=2,
            top_hits=13,
            weighted_hits=12,
            top_coverage=0.005,
            weighted_coverage=0.05,
        ),
    ]

    summary = summarize_strategy_diagnostics(rows)
    top_calibration = summary["coverage_calibration"]["top_probability"]
    weighted_calibration = summary["coverage_calibration"]["weighted_coverage"]

    assert summary["structural_averages"]["top_probability"]["package_size"] == 2
    assert summary["structural_averages"]["weighted_coverage"][
        "mean_pairwise_hamming"
    ] == 4
    assert summary["structural_averages"]["top_weighted"]["jaccard"] == 0.5
    assert summary["strategy_averages"]["weighted_coverage"] == {
        "best_hits": 12.5,
        "estimated_coverage": pytest.approx(0.02745),
        "observed_hit13_frequency": 0.5,
    }
    assert len(top_calibration) == 11
    assert top_calibration[0] == {
        "label": "0.000-0.005",
        "count": 1,
        "mean_estimated_coverage": 0.0,
        "observed_hit13_frequency": 0.0,
    }
    assert top_calibration[1]["count"] == 1
    assert weighted_calibration[0]["count"] == 1
    assert weighted_calibration[-1] == {
        "label": "0.050+",
        "count": 1,
        "mean_estimated_coverage": 0.05,
        "observed_hit13_frequency": 0.0,
    }


def test_report_contains_all_hit_bins_and_is_deterministic(tmp_path):
    result = StrategyDiagnosticsResult(
        rows=[fixture_diagnostics_row()],
        config=StrategyConfig(bank=5000, stake=30, category=13),
        manifest={"last": 5},
    )

    first = write_strategy_diagnostics_reports(result, tmp_path)
    first_text = first[1].read_text(encoding="utf-8")
    second = write_strategy_diagnostics_reports(result, tmp_path)

    assert first[0].name == "strategy_diagnostics_development_last_5_bank_5000.csv"
    assert first[1].name == "strategy_diagnostics_development_last_5_bank_5000.md"
    assert second[1].read_text(encoding="utf-8") == first_text
    assert list(csv.DictReader(first[0].open(encoding="utf-8")).fieldnames) == list(
        StrategyDiagnosticsRow.__dataclass_fields__
    )
    assert all(f"| {hits} |" in first_text for hits in range(16))
    assert "development-only; no winner selected" in first_text


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        _add_drawing(database_session, 1, "1" * 15)
        _add_drawing(database_session, 2, "1" * 15)
        _add_drawing(database_session, 3, "X" * 15)
        yield database_session


@pytest.fixture
def manifest():
    config = StrategyConfig(
        bank=90,
        stake=30,
        category=13,
        top_count=3,
        candidate_samples=3,
        optimization_samples=3,
        validation_samples=3,
    )
    return {
        "last": 3,
        "holdout_size": 1,
        "drawing_ids": [1, 2, 3],
        "config": _config_payload(config),
        "configuration_hash": _configuration_hash(config),
    }


@pytest.fixture
def frozen_csv(tmp_path):
    return write_runner_frozen_rows(tmp_path, drawing_ids=[1, 2])


def test_runner_builds_and_verifies_packages_before_loading_result(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
):
    calls = []
    packages = _packages("1" * 15)
    monkeypatch.setattr(
        diagnostics_module,
        "_build_development_packages",
        lambda *args, **kwargs: calls.append("packages") or packages,
    )
    monkeypatch.setattr(
        diagnostics_module,
        "_load_development_result",
        lambda *args, **kwargs: calls.append("result") or "1" * 15,
    )

    run_strategy_diagnostics(session, manifest, frozen_csv)

    assert calls.index("packages") < calls.index("result")


def test_runner_fails_on_package_hash_mismatch(session, manifest, frozen_csv):
    with pytest.raises(ValueError, match="package hash"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("X" * 15),
        )


def test_runner_never_loads_holdout_id(monkeypatch, session, manifest, frozen_csv):
    loaded = []
    monkeypatch.setattr(
        diagnostics_module,
        "_load_development_inputs",
        lambda database_session, drawing_id: loaded.append(drawing_id)
        or _fixture_inputs(),
    )
    monkeypatch.setattr(
        diagnostics_module,
        "_load_development_result",
        lambda *args: "1" * 15,
    )

    run_strategy_diagnostics(
        session,
        manifest,
        frozen_csv,
        package_builder=lambda probabilities, *args: _packages(
            "1" * len(probabilities)
        ),
    )

    assert loaded == [1, 2]


def test_runner_reports_development_progress(session, manifest, frozen_csv):
    updates = []

    run_strategy_diagnostics(
        session,
        manifest,
        frozen_csv,
        package_builder=lambda *args: _packages("1" * 15),
        progress_callback=updates.append,
    )

    assert updates == [
        {"drawing_id": 1, "drawing_index": 1, "drawing_total": 2},
        {"drawing_id": 2, "drawing_index": 2, "drawing_total": 2},
    ]


def test_runner_fails_when_recomputed_result_fields_differ(
    session,
    manifest,
    tmp_path,
):
    frozen_csv = write_runner_frozen_rows(
        tmp_path,
        drawing_ids=[1, 2],
        best_hits=14,
    )

    with pytest.raises(ValueError, match="frozen result fields"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("1" * 15),
        )


def test_diagnose_strategies_help():
    result = CliRunner().invoke(app, ["diagnose-strategies", "--help"])

    assert result.exit_code == 0
    assert "--manifest" in result.output
    assert "--backtest-csv" in result.output


def test_diagnose_strategies_rejects_invalid_frozen_data(tmp_path):
    manifest_path = tmp_path / "bad-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    frozen_csv = tmp_path / "bad-backtest.csv"
    frozen_csv.write_text("drawing_id\n", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "diagnose-strategies",
            "--db",
            str(tmp_path / "test.db"),
            "--manifest",
            str(manifest_path),
            "--backtest-csv",
            str(frozen_csv),
        ],
    )

    assert result.exit_code != 0


@pytest.mark.parametrize(
    "coupon",
    ["1" * 14, "1" * 14 + "Z"],
)
def test_runner_rejects_malformed_coupons_before_loading_result(
    monkeypatch,
    session,
    manifest,
    tmp_path,
    coupon,
):
    frozen_csv = write_runner_frozen_rows(
        tmp_path,
        drawing_ids=[1, 2],
        coupon=coupon,
    )
    monkeypatch.setattr(
        diagnostics_module,
        "_load_development_result",
        lambda *args: pytest.fail("results must not load for malformed coupons"),
    )

    with pytest.raises(ValueError, match="Invalid development package set"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages(coupon),
        )


@pytest.mark.parametrize(
    "field_name",
    tuple(StrategyConfig.__dataclass_fields__),
)
def test_runner_requires_every_manifest_config_field(
    session,
    manifest,
    frozen_csv,
    field_name,
):
    manifest["config"].pop(field_name)

    with pytest.raises(ValueError, match="config fields"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("1" * 15),
        )


def test_runner_rejects_extra_manifest_config_fields(session, manifest, frozen_csv):
    manifest["config"]["future_default"] = 1

    with pytest.raises(ValueError, match="config fields"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("1" * 15),
        )


def test_runner_rejects_noncanonical_manifest_configuration_hash(
    session,
    manifest,
    frozen_csv,
):
    manifest["configuration_hash"] = "0" * 64

    with pytest.raises(ValueError, match="configuration hash"):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("1" * 15),
        )


def test_real_input_loader_query_defers_event_results(session):
    with _capture_sql(session) as statements:
        diagnostics_module._load_development_inputs(session, 1)

    event_queries = _event_queries(statements)

    assert event_queries
    assert all(
        "events.result" not in statement.lower()
        for statement, _ in event_queries
    )


def test_real_loaders_query_results_only_after_package_hash_validation(
    session,
    manifest,
    frozen_csv,
):
    calls = []
    with _capture_sql(session, calls) as statements:
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: calls.append("packages")
            or _packages("1" * 15),
        )

    result_queries = [
        index
        for index, call in enumerate(calls)
        if call == "result_sql"
    ]

    assert result_queries
    assert all(
        any(call == "packages" for call in calls[:index])
        for index in result_queries
    )
    assert len(
        [
            statement
            for statement, _ in _event_queries(statements)
            if "events.result" in statement.lower()
        ]
    ) == 2


def test_real_loaders_do_not_query_results_for_package_hash_mismatch(
    session,
    manifest,
    frozen_csv,
):
    with _capture_sql(session) as statements:
        with pytest.raises(ValueError, match="package hash"):
            run_strategy_diagnostics(
                session,
                manifest,
                frozen_csv,
                package_builder=lambda *args: _packages("X" * 15),
            )

    assert not [
        statement
        for statement, _ in _event_queries(statements)
        if "events.result" in statement.lower()
    ]


def test_real_loaders_never_query_holdout_events_or_results(
    session,
    manifest,
    frozen_csv,
):
    with _capture_sql(session) as statements:
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: _packages("1" * 15),
        )

    queried_ids = {
        parameters[0]
        for _, parameters in _event_queries(statements)
    }

    assert queried_ids == {1, 2}


@pytest.mark.parametrize(
    ("packages", "message"),
    [
        ([], "Invalid development package set"),
        (
            [
                StrategyPackage(
                    "baseline_brief",
                    ["1" * 15],
                    0.5,
                    1,
                    0.01,
                    True,
                ),
                StrategyPackage(
                    "top_probability",
                    ["1" * 15],
                    0.5,
                    1,
                    0.01,
                    False,
                ),
                StrategyPackage(
                    "weighted_coverage",
                    ["1" * 15],
                    0.5,
                    1,
                    0.01,
                    False,
                ),
            ],
            "timed out",
        ),
    ],
)
def test_runner_fails_closed_on_invalid_or_timed_out_packages(
    monkeypatch,
    session,
    manifest,
    frozen_csv,
    packages,
    message,
):
    monkeypatch.setattr(
        diagnostics_module,
        "_load_development_result",
        lambda *args: pytest.fail("results must not load for invalid packages"),
    )

    with pytest.raises(ValueError, match=message):
        run_strategy_diagnostics(
            session,
            manifest,
            frozen_csv,
            package_builder=lambda *args: packages,
        )


def write_frozen_rows(tmp_path, drawing_ids, omit=None, segment="development"):
    path = tmp_path / "frozen.csv"
    fieldnames = list(StrategyBacktestRow.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for drawing_id in drawing_ids:
            for strategy in (
                "baseline_brief",
                "top_probability",
                "weighted_coverage",
            ):
                if strategy == omit:
                    continue
                writer.writerow(
                    {
                        "drawing_id": drawing_id,
                        "drawing_number": 1000 + drawing_id,
                        "segment": segment,
                        "strategy": strategy,
                        "best_hits": 10,
                        "hit_13": False,
                        "hit_14": False,
                        "hit_15": False,
                        "package_size": 10,
                        "package_cost": 300,
                        "estimated_coverage": 0.5,
                        "candidate_count": 20,
                        "runtime_seconds": 0.1,
                        "package_hash": f"hash-{drawing_id}-{strategy}",
                    }
                )
    return path


def write_runner_frozen_rows(tmp_path, drawing_ids, best_hits=15, coupon=None):
    path = tmp_path / "runner-frozen.csv"
    coupon = coupon or "1" * 15
    package_hash = hashlib.sha256(coupon.encode("utf-8")).hexdigest()
    fieldnames = list(StrategyBacktestRow.__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for drawing_id in drawing_ids:
            for strategy in (
                "baseline_brief",
                "top_probability",
                "weighted_coverage",
            ):
                writer.writerow(
                    {
                        "drawing_id": drawing_id,
                        "drawing_number": 1000 + drawing_id,
                        "segment": "development",
                        "strategy": strategy,
                        "best_hits": best_hits,
                        "hit_13": best_hits >= 13,
                        "hit_14": best_hits >= 14,
                        "hit_15": best_hits == 15,
                        "package_size": 1,
                        "package_cost": 30,
                        "estimated_coverage": 0.5,
                        "candidate_count": 1,
                        "runtime_seconds": 0.01,
                        "package_hash": package_hash,
                    }
                )
    return path


def _packages(coupon):
    return [
        StrategyPackage(strategy, [coupon], 0.5, 1, 0.01, False)
        for strategy in (
            "baseline_brief",
            "top_probability",
            "weighted_coverage",
        )
    ]


def _fixture_inputs():
    return normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}] * 15), []


def fixture_diagnostics_row(
    drawing_id=1,
    top_hits=12,
    weighted_hits=13,
    top_coverage=0.01,
    weighted_coverage=0.02,
):
    values = {
        "drawing_id": drawing_id,
        "drawing_number": 1000 + drawing_id,
        "result_string": "1" * 15,
        "weighted_minus_top_best_hits": weighted_hits - top_hits,
        "top_weighted_intersection_size": 1,
        "top_weighted_jaccard": 0.5,
        "top_unique_mean_log_probability": -2.0,
        "weighted_unique_mean_log_probability": -3.0,
    }
    for strategy, hits, coverage, package_size, diversity in (
        ("baseline_brief", 11, 0.03, 1, 2.0),
        ("top_probability", top_hits, top_coverage, 2, 3.0),
        ("weighted_coverage", weighted_hits, weighted_coverage, 3, 4.0),
    ):
        values.update(
            {
                f"{strategy}_best_hits": hits,
                f"{strategy}_nearest_hamming": 15 - hits,
                f"{strategy}_hit_13": hits >= 13,
                f"{strategy}_hit_14": hits >= 14,
                f"{strategy}_hit_15": hits == 15,
                f"{strategy}_package_size": package_size,
                f"{strategy}_package_cost": package_size * 30,
                f"{strategy}_estimated_coverage": coverage,
                f"{strategy}_candidate_count": package_size * 10,
                f"{strategy}_runtime_seconds": package_size / 10,
                f"{strategy}_min_log_probability": -4.0,
                f"{strategy}_median_log_probability": -3.0,
                f"{strategy}_mean_log_probability": -2.5,
                f"{strategy}_max_log_probability": -1.0,
                f"{strategy}_mean_pairwise_hamming": diversity,
            }
        )
    return StrategyDiagnosticsRow(**values)


def _config_payload(config):
    return {
        field_name: getattr(config, field_name)
        for field_name in StrategyConfig.__dataclass_fields__
    }


@contextmanager
def _capture_sql(session, calls=None):
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))
        if calls is not None and "from events" in statement.lower():
            calls.append(
                "result_sql" if "events.result" in statement.lower() else "input_sql"
            )

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _event_queries(statements):
    return [
        (statement, parameters)
        for statement, parameters in statements
        if "from events" in statement.lower()
    ]


def _add_drawing(session, drawing_id, results):
    session.add(
        Drawing(
            id=drawing_id,
            number=1000 + drawing_id,
            name="baltbet-main",
            status="finished",
        )
    )
    for event_order, result in enumerate(results):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=event_order,
                name=f"Match {event_order + 1}",
                result=result,
            )
        )
        session.add(
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
    session.commit()
