import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.analytics.data_health import (
    DATA_HEALTH_CONTRACT_VERSION,
    DataHealthFailure,
    audit_data_health,
    require_data_health,
    write_data_health_reports,
)
from toto_ai.db.models import (
    ArchivedPackage,
    Drawing,
    DrawingResultSnapshot,
    Event,
    PackageSettlement,
    Quote,
)
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.optimizer.brief import build_brief_for_drawing
from toto_ai.package.backtest import run_mvp_backtest

runner = CliRunner()


def _add_drawing(
    session: Session,
    *,
    drawing_id: int,
    number: int,
    status: str = "finished",
    results: list[str | None] | None = None,
    pool: tuple[float | None, float | None, float | None] = (50, 30, 20),
    bk: tuple[float | None, float | None, float | None] = (50, 30, 20),
    event_count: int = 15,
    blank_names: bool = False,
    quote_count: int | None = None,
) -> None:
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status=status,
            ended_at="2030-01-01T00:00:00+00:00",
        )
    )
    outcomes = results if results is not None else ["1"] * event_count
    quotes_to_add = event_count if quote_count is None else quote_count
    for order in range(event_count):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=order,
                name="" if blank_names else f"Match {number}-{order + 1}",
                championship="League",
                sport="football",
                result=outcomes[order],
                result_status=(
                    outcomes[order]
                    if outcomes[order] in ("void", "cancelled", "canceled")
                    else "void"
                    if outcomes[order] == "*"
                    else "resolved"
                    if outcomes[order] in ("1", "X", "2")
                    else None
                ),
            )
        )
        if order < quotes_to_add:
            session.add(
                Quote(
                    drawing_id=drawing_id,
                    event_order=order,
                    pool_win_1=pool[0],
                    pool_draw=pool[1],
                    pool_win_2=pool[2],
                    bk_win_1=bk[0],
                    bk_draw=bk[1],
                    bk_win_2=bk[2],
                )
            )


def _add_result_snapshot(session: Session, drawing_id: int, number: int) -> None:
    session.add(
        DrawingResultSnapshot(
            drawing_id=drawing_id,
            drawing_number=number,
            hash_schema_version=3,
            ended_at="2030-01-01T00:00:00+00:00",
            retrieved_at="2030-01-02T00:00:00+00:00",
            source_endpoint=f"/drawing-info/{drawing_id}",
            payload_sha256=f"payload-{drawing_id}",
            raw_snapshot_sha256=f"raw-{drawing_id}",
            result_sha256=f"result-{drawing_id}",
            snapshot_sha256=f"snapshot-{drawing_id}",
            complete=True,
            event_count=15,
            actual="1" * 15,
            events_json="[]",
            payload_json="{}",
        )
    )


def _database(tmp_path: Path):
    path = tmp_path / "data" / "toto.db"
    engine = init_db(path)
    return path, get_session_factory(engine)


def _record(result, number: int):
    return next(row for row in result.drawings if row.drawing_number == number)


def test_contract_classifies_zero_pool_void_results_and_use_cases(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            results=["1"] * 13 + ["*", "cancelled"],
        )
        _add_result_snapshot(session, 1, 100)
        _add_drawing(
            session,
            drawing_id=2,
            number=101,
            results=["1"] * 15,
            pool=(0, 0, 0),
        )

    with factory() as session:
        result = audit_data_health(session, db_path=db)

    void_row = _record(result, 100)
    assert void_row.terminal_result_count == 15
    assert void_row.void_result_count == 2
    assert "incomplete_results" not in void_row.observed_reason_codes
    assert void_row.use_case_eligibility["result_settlement"] is True

    zero_row = _record(result, 101)
    assert "invalid_zero_pool" in zero_row.observed_reason_codes
    assert zero_row.use_case_eligibility["prospective_generation"] is False
    assert zero_row.use_case_eligibility["backtest_probability"] is False


def test_contract_distinguishes_missing_all_and_partial_results(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            results=[None] * 15,
        )
        _add_drawing(
            session,
            drawing_id=2,
            number=101,
            results=["1"] * 14 + [None],
        )

    with factory() as session:
        result = audit_data_health(session, db_path=db)

    assert "all_results_missing" in _record(
        result, 100
    ).observed_reason_codes
    assert "incomplete_results" in _record(
        result, 101
    ).observed_reason_codes
    assert _record(result, 100).use_case_eligibility["prospective_generation"]
    assert not _record(result, 100).use_case_eligibility[
        "backtest_probability"
    ]


def test_contract_checks_structure_names_quotes_bk_and_snapshot_separately(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            event_count=14,
            quote_count=14,
        )
        _add_drawing(
            session,
            drawing_id=2,
            number=101,
            blank_names=True,
            quote_count=14,
            bk=(None, 30, 20),
        )

    with factory() as session:
        result = audit_data_health(session, db_path=db)

    assert "invalid_event_count_order" in _record(
        result, 100
    ).observed_reason_codes
    second = _record(result, 101)
    assert {
        "empty_event_names",
        "missing_quotes",
        "incomplete_bk",
        "missing_raw_snapshot",
        "missing_result_snapshot",
    } <= set(second.observed_reason_codes)


def test_unsettled_only_applies_to_real_prebet_archives(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100)
        _add_result_snapshot(session, 1, 100)
        _add_drawing(session, drawing_id=2, number=101)
        _add_result_snapshot(session, 2, 101)
        session.add_all(
            [
                ArchivedPackage(
                    archive_sha256="rehearsal",
                    package_sha256="package-rehearsal",
                    drawing_id=1,
                    drawing_number=100,
                    stake=30,
                    coupon_count=1,
                    cost=30,
                    source_path="reports/rehearsal/package.csv",
                    source_bytes_sha256="bytes-rehearsal",
                    source_bytes=b"",
                    coupons_json='["111111111111111"]',
                    archived_at="2030-01-01T00:00:00+00:00",
                    provenance="legacy_import",
                ),
                ArchivedPackage(
                    archive_sha256="production",
                    package_sha256="package-production",
                    drawing_id=2,
                    drawing_number=101,
                    stake=30,
                    coupon_count=1,
                    cost=30,
                    source_path="reports/package.csv",
                    source_bytes_sha256="bytes-production",
                    source_bytes=b"",
                    coupons_json='["111111111111111"]',
                    archived_at="2030-01-01T00:00:00+00:00",
                    provenance="pre_bet_runner",
                ),
            ]
        )

    with factory() as session:
        result = audit_data_health(session, db_path=db)

    assert "unsettled_package" not in _record(
        result, 100
    ).observed_reason_codes
    assert "unsettled_package" in _record(
        result, 101
    ).observed_reason_codes


def test_settled_production_package_is_not_unsettled(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100)
        _add_result_snapshot(session, 1, 100)
        session.add(
            ArchivedPackage(
                archive_sha256="production",
                package_sha256="package-production",
                drawing_id=1,
                drawing_number=100,
                stake=30,
                coupon_count=1,
                cost=30,
                source_path="reports/package.csv",
                source_bytes_sha256="bytes-production",
                source_bytes=b"",
                coupons_json='["111111111111111"]',
                archived_at="2030-01-01T00:00:00+00:00",
                provenance="pre_bet_runner",
            )
        )
        session.add(
            PackageSettlement(
                settlement_sha256="settlement",
                drawing_id=1,
                drawing_number=100,
                result_snapshot_sha256="snapshot-1",
                archive_sha256="production",
                package_sha256="package-production",
                settled_at="2030-01-02T00:00:00+00:00",
                actual="1" * 15,
                hit_distribution_json='{"15":1}',
                best_hits=15,
                best_coupon_ranks_json="[1]",
                cost=30,
                fixed_miss_events_json="[]",
                zero_exposure_miss_events_json="[]",
                return_status="unknown",
                settlement_json="{}",
            )
        )

    with factory() as session:
        result = audit_data_health(session, db_path=db)

    assert "unsettled_package" not in _record(
        result, 100
    ).observed_reason_codes


def test_selectors_and_gap_duplicate_metadata(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100)
        _add_drawing(session, drawing_id=2, number=102)
        _add_drawing(session, drawing_id=3, number=102)
        _add_drawing(session, drawing_id=4, number=103)

    with factory() as session:
        ranged = audit_data_health(
            session,
            db_path=db,
            from_drawing=100,
            to_drawing=103,
        )
        latest = audit_data_health(session, db_path=db, last=2)

    assert ranged.metadata.gaps == (101,)
    assert ranged.metadata.duplicates == {102: (2, 3)}
    assert [row.drawing_number for row in latest.drawings] == [102, 102, 103]
    assert latest.metadata.duplicates == {102: (2, 3)}
    with factory() as session:
        with pytest.raises(ValueError, match="cannot be combined"):
            audit_data_health(
                session,
                db_path=db,
                last=1,
                from_drawing=100,
            )


def test_reports_include_contract_version_details_and_aggregates(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100)
    with factory() as session:
        result = audit_data_health(
            session,
            db_path=db,
            use_case="prospective_generation",
            strict=False,
        )

    csv_path, json_path, md_path = write_data_health_reports(
        result,
        tmp_path / "reports",
    )

    payload = json.loads(json_path.read_text())
    assert payload["contract_version"] == DATA_HEALTH_CONTRACT_VERSION
    assert payload["summary"]["total_drawings"] == 1
    assert payload["summary"]["inventory_counts"]["event_rows"] == 15
    assert payload["drawings"][0]["drawing_number"] == 100
    assert "contract_version" in csv_path.read_text().splitlines()[0]
    assert "summary_inventory_counts" in csv_path.read_text().splitlines()[0]
    assert DATA_HEALTH_CONTRACT_VERSION in md_path.read_text()


def test_cli_exit_codes_exports_and_conflicting_selectors(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            pool=(0, 0, 0),
        )
    output_dir = tmp_path / "out"

    failed = runner.invoke(
        cli.app,
        [
            "data-health",
            "--db",
            str(db),
            "--use-case",
            "prospective_generation",
            "--output-dir",
            str(output_dir),
        ],
    )
    non_strict = runner.invoke(
        cli.app,
        [
            "data-health",
            "--db",
            str(db),
            "--use-case",
            "prospective_generation",
            "--no-strict",
            "--output-dir",
            str(output_dir),
        ],
    )
    conflict = runner.invoke(
        cli.app,
        [
            "data-health",
            "--db",
            str(db),
            "--last",
            "1",
            "--from-drawing",
            "100",
        ],
    )
    runtime = runner.invoke(
        cli.app,
        ["data-health", "--db", str(tmp_path / "missing.db")],
    )

    assert failed.exit_code == 3
    assert non_strict.exit_code == 0
    assert conflict.exit_code == 2
    assert runtime.exit_code == 4
    assert (output_dir / "data_health_v1.json").is_file()


def test_reusable_gate_fails_closed_and_research_override_is_explicit(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            pool=(0, 0, 0),
        )

    with factory() as session:
        with pytest.raises(DataHealthFailure):
            require_data_health(
                session,
                use_case="backtest_probability",
                drawing_ids=(1,),
            )
        overridden = require_data_health(
            session,
            use_case="backtest_probability",
            drawing_ids=(1,),
            allow_unhealthy_research=True,
        )

    assert overridden.override_applied is True
    assert overridden.report.summary.unhealthy_drawings == 1


def test_generation_and_backtest_entry_points_apply_health_gate(tmp_path):
    db, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(
            session,
            drawing_id=1,
            number=100,
            status="expected",
            results=[None] * 15,
            pool=(0, 0, 0),
        )
        _add_drawing(
            session,
            drawing_id=2,
            number=99,
            results=["1"] * 15,
            pool=(0, 0, 0),
        )

    with factory() as session:
        with pytest.raises(DataHealthFailure):
            build_brief_for_drawing(
                session,
                drawing_id=1,
                category=13,
                bank=4980,
                report_dir=tmp_path / "brief",
            )
        with pytest.raises(DataHealthFailure):
            run_mvp_backtest(
                session,
                last=1,
                bank=4980,
            )
        overridden = run_mvp_backtest(
            session,
            last=1,
            bank=4980,
            allow_unhealthy_research=True,
        )

    assert overridden.summary["data_health_override"] is True
    assert overridden.summary["data_health_contract_version"] == (
        DATA_HEALTH_CONTRACT_VERSION
    )
