import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.research_bk_vs_norm import (
    build_bk_vs_norm_report,
    run_bk_vs_norm_study,
    write_bk_vs_norm_report,
)
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.db.session import init_db


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Drawing(id=1, number=10, name="baltbet-main", status="finished"))
        session.add_all(
            [
                Event(drawing_id=1, event_order=0, name="A", result="win_1"),
                Event(drawing_id=1, event_order=1, name="B", result="draw"),
            ]
        )
        session.add_all(
            [
                Quote(
                    drawing_id=1,
                    event_order=0,
                    bk_win_1=50.0,
                    bk_draw=30.0,
                    bk_win_2=20.0,
                    norm_win_1=2.0,
                    norm_draw=10 / 3,
                    norm_win_2=5.0,
                ),
                Quote(
                    drawing_id=1,
                    event_order=1,
                    bk_win_1=24.0,
                    bk_draw=50.0,
                    bk_win_2=26.0,
                    norm_win_1=4.0,
                    norm_draw=2.0,
                    norm_win_2=4.0,
                ),
            ]
        )
        session.commit()
        yield session

    engine.dispose()


def test_run_bk_vs_norm_study_calculates_error_and_examples(session):
    result = run_bk_vs_norm_study(session, sample_size=20)

    assert result["event_count"] == 2
    assert result["comparison_count"] == 6
    assert result["average_absolute_error"] == pytest.approx(0.3333)
    assert result["maximum_error"] == pytest.approx(1.0)
    assert result["correlation"] == pytest.approx(0.999, abs=0.001)
    assert result["conclusion"] == "BK probabilities are derived from normalized odds."
    assert len(result["examples"]) == 2
    assert result["examples"][0]["event"] == "A"
    assert result["examples"][0]["bk"] == "50.00 / 30.00 / 20.00"
    assert result["examples"][0]["calculated"] == "50.00 / 30.00 / 20.00"


def test_build_and_write_bk_vs_norm_report(session, tmp_path):
    result = run_bk_vs_norm_study(session, sample_size=20)
    report = build_bk_vs_norm_report(result)
    path = write_bk_vs_norm_report(result, report_dir=tmp_path)

    assert "# BK vs Normalized Odds Study" in report
    assert "Average absolute error: 0.3333%" in report
    assert "BK probabilities are derived from normalized odds." in report
    assert path == tmp_path / "bk_vs_norm.md"
    assert path.read_text() == report


def test_init_db_adds_norm_columns_to_existing_sqlite_database(tmp_path):
    db_path = tmp_path / "toto.db"
    engine = init_db(db_path)
    engine.dispose()

    migrated_engine = init_db(db_path)
    column_names = {column.name for column in Quote.__table__.columns}

    assert {"norm_win_1", "norm_draw", "norm_win_2"} <= column_names
    migrated_engine.dispose()
