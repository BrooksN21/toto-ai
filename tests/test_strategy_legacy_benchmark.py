from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.models import EVConfig
from toto_ai.optimizer.strategy_comparison import StrategyResult
from toto_ai.optimizer.strategy_legacy_benchmark import (
    benchmark_legacy_retrospective_cases,
    load_legacy_retrospective_cases,
    write_legacy_retrospective_benchmark_reports,
)


def test_legacy_loader_labels_unknown_chronology_and_excludes_actual_from_hash(
    tmp_path,
):
    db_path, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100, actual="1" * 15)

    with factory() as session:
        first = load_legacy_retrospective_cases(
            session,
            db_path=db_path,
            last=1,
            bank=120,
            stake=30,
        )[0]

    with factory.begin() as session:
        for event in session.scalars(select(Event)).all():
            event.result = "2"

    with factory() as session:
        second = load_legacy_retrospective_cases(
            session,
            db_path=db_path,
            last=1,
            bank=120,
            stake=30,
        )[0]

    assert first.strategy_input.evidence_tier == "LEGACY_RETROSPECTIVE"
    assert first.strategy_input.chronology_verified is False
    assert first.strategy_input.input_sha256 == second.strategy_input.input_sha256
    assert first.source_data_sha256 == second.source_data_sha256
    assert first.actual == "1" * 15
    assert second.actual == "2" * 15


def test_legacy_benchmark_checkpoints_and_resumes_without_rerunning(tmp_path):
    db_path, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100, actual="1" * 15)
        _add_drawing(session, drawing_id=2, number=101, actual="2" * 15)
    with factory() as session:
        cases = load_legacy_retrospective_cases(
            session,
            db_path=db_path,
            last=2,
            bank=120,
            stake=30,
        )

    calls = []

    def comparison_runner(strategy_input, *, ev_config):
        calls.append(strategy_input.drawing_id)
        return _results(strategy_input)

    config = EVConfig(bank=120, stake=30, mode="research")
    first = benchmark_legacy_retrospective_cases(
        cases,
        ev_config=config,
        checkpoint_dir=tmp_path / "checkpoints",
        comparison_runner=comparison_runner,
    )
    second = benchmark_legacy_retrospective_cases(
        cases,
        ev_config=config,
        checkpoint_dir=tmp_path / "checkpoints",
        comparison_runner=comparison_runner,
    )

    assert calls == [2, 1]
    assert first.rows == second.rows
    assert first.overlaps == second.overlaps
    assert first.summary["drawings_evaluated"] == 2
    assert second.summary["resumed_drawings"] == 2
    assert first.summary["release_evidence"] is False
    assert first.summary["evidence_tier"] == "LEGACY_RETROSPECTIVE"
    checkpoints = sorted((tmp_path / "checkpoints").glob("drawing-*.json"))
    assert len(checkpoints) == 2


def test_legacy_report_is_physically_and_visibly_non_release(tmp_path):
    db_path, factory = _database(tmp_path)
    with factory.begin() as session:
        _add_drawing(session, drawing_id=1, number=100, actual="1" * 15)
    with factory() as session:
        cases = load_legacy_retrospective_cases(
            session,
            db_path=db_path,
            last=1,
            bank=120,
            stake=30,
        )
    benchmark = benchmark_legacy_retrospective_cases(
        cases,
        ev_config=EVConfig(bank=120, stake=30, mode="research"),
        checkpoint_dir=tmp_path / "checkpoints",
        comparison_runner=lambda strategy_input, **_kwargs: _results(
            strategy_input
        ),
    )

    paths = write_legacy_retrospective_benchmark_reports(
        benchmark,
        tmp_path / "report",
    )

    payload = json.loads(paths.json.read_text())
    manifest = json.loads(paths.manifest.read_text())
    assert payload["evidence_tier"] == "LEGACY_RETROSPECTIVE"
    assert payload["release_evidence"] is False
    assert payload["actionable"] is False
    assert manifest["evidence_tier"] == "LEGACY_RETROSPECTIVE"
    assert manifest["automatic_wagering"] is False
    assert "NOT RELEASE EVIDENCE" in paths.markdown.read_text()


def test_legacy_strategy_benchmark_cli_help():
    result = CliRunner().invoke(app, ["legacy-strategy-benchmark", "--help"])

    assert result.exit_code == 0
    assert "--scheduler-plan" in result.stdout
    assert "--checkpoint-dir" in result.stdout
    assert "--last" in result.stdout


def _database(tmp_path: Path):
    path = tmp_path / "data" / "toto.db"
    engine = init_db(path)
    return path, get_session_factory(engine)


def _add_drawing(session, *, drawing_id: int, number: int, actual: str) -> None:
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status="finished",
            pool_sum=1_000_000.0,
            jackpot=2_000_000.0,
            ended_at=f"2030-01-{drawing_id:02d}T00:00:00+00:00",
        )
    )
    for order, result in enumerate(actual):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=order,
                name=f"Home {order} — Away {order}",
                championship="Test league",
                sport="football",
                result=result,
                result_status="resolved",
                score="1:0",
            )
        )
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=order,
                pool_win_1=45.0,
                pool_draw=35.0,
                pool_win_2=20.0,
                bk_win_1=50.0,
                bk_draw=30.0,
                bk_win_2=20.0,
            )
        )


def _results(strategy_input):
    shared = "1" * 15
    return (
        _result(
            strategy_input,
            "EV_CROWD_CURRENT",
            (shared, "X" + "1" * 14),
        ),
        _result(
            strategy_input,
            "BK_PROBABILITY_ONLY",
            ("X" + "1" * 14, "2" + "1" * 14),
        ),
        _result(
            strategy_input,
            "TOTOBRIEF_STYLE_COVER_13",
            (shared,),
        ),
        _result(
            strategy_input,
            "TOTOBRIEF_STYLE_COVER_14",
            ("X" * 15,),
            category=14,
        ),
    )


def _result(strategy_input, strategy_id, coupons, *, category=13):
    import hashlib

    package_sha256 = hashlib.sha256(
        "".join(f"{coupon}\n" for coupon in coupons).encode()
    ).hexdigest()
    return StrategyResult(
        strategy_id=strategy_id,
        strategy_version="v1",
        source_engine="test",
        category=category,
        input_sha256=strategy_input.input_sha256,
        config_sha256="c" * 64,
        package_sha256=package_sha256,
        requested_bank=strategy_input.bank,
        stake=strategy_input.stake,
        coupons=tuple(coupons),
        cost=len(coupons) * strategy_input.stake,
        unused_bank=(
            strategy_input.bank - len(coupons) * strategy_input.stake
        ),
        probability_at_least_13=0.1,
        probability_at_least_14=0.05,
        probability_at_least_15=0.01,
        runtime_seconds=0.01,
        timed_out=False,
    )
