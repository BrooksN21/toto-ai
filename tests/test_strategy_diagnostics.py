import csv
import hashlib
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

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
    development_drawing_ids,
    load_frozen_development_rows,
    package_overlap_metrics,
    package_structure_metrics,
    run_strategy_diagnostics,
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
