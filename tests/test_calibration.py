import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.calibration import (
    bin_probability,
    run_calibration_study,
    write_calibration_reports,
)
from toto_ai.db.models import Base, Drawing, Event, Quote


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Drawing(id=1, number=1, name="baltbet-main", status="finished"))
        _add_event(
            session,
            order=0,
            result="1",
            bk=(0.70, 0.20, 0.10),
            pool=(0.60, 0.25, 0.15),
        )
        _add_event(
            session,
            order=1,
            result="X",
            bk=(0.20, 0.60, 0.20),
            pool=(0.30, 0.40, 0.30),
        )
        _add_event(
            session,
            order=2,
            result="2",
            bk=(0.20, 0.30, 0.50),
            pool=(0.25, 0.25, 0.50),
        )
        _add_event(
            session,
            order=3,
            result=None,
            bk=(0.50, 0.25, 0.25),
            pool=(0.50, 0.25, 0.25),
        )
        session.commit()
        yield session
    engine.dispose()


def test_bin_probability_uses_five_percent_bins():
    assert bin_probability(0.0) == "0-5%"
    assert bin_probability(0.049) == "0-5%"
    assert bin_probability(0.05) == "5-10%"
    assert bin_probability(0.999) == "95-100%"
    assert bin_probability(1.0) == "95-100%"


def test_run_calibration_study_computes_core_scores(session):
    result = run_calibration_study(session)

    assert result["overall"]["event_count"] == 3
    assert result["overall"]["outcome_count"] == 9
    assert result["overall"]["brier_score"] == pytest.approx(0.253333)
    assert result["overall"]["log_loss"] == pytest.approx(0.5202159)
    assert result["overall"]["ece"] >= 0


def test_run_calibration_study_builds_bin_rows_and_slices(session):
    result = run_calibration_study(session)

    rows = result["bookmaker_bins"]
    assert any(row["outcome"] == "1" and row["bin"] == "70-75%" for row in rows)
    target = next(
        row
        for row in rows
        if row["outcome"] == "1" and row["bin"] == "70-75%"
    )
    assert target["event_count"] == 1
    assert target["observed_frequency"] == 100.0
    assert target["expected_frequency"] == pytest.approx(70.0)
    assert target["average_bookmaker_probability"] == pytest.approx(70.0)
    assert target["average_pool_probability"] == pytest.approx(60.0)

    assert result["draw_calibration"]["event_count"] == 3
    assert result["favorites"]["event_count"] == 2
    assert result["underdogs"]["event_count"] == 5
    assert "average_bias" in result["pool_vs_bookmaker_bias"]


def test_write_calibration_reports_exports_expected_files(session, tmp_path):
    result = run_calibration_study(session)

    markdown_path, calibration_csv, reliability_csv = write_calibration_reports(
        result,
        report_dir=tmp_path,
    )

    assert markdown_path == tmp_path / "calibration.md"
    assert calibration_csv == tmp_path / "calibration.csv"
    assert reliability_csv == tmp_path / "reliability.csv"
    assert "Bookmaker Calibration" in markdown_path.read_text()
    assert "metric,value" in calibration_csv.read_text()
    assert "provider,outcome,bin" in reliability_csv.read_text()


def _add_event(
    session: Session,
    order: int,
    result: str | None,
    bk: tuple[float, float, float],
    pool: tuple[float, float, float],
) -> None:
    session.add(
        Event(
            drawing_id=1,
            event_order=order,
            name=f"Event {order}",
            result=result,
            score="1:0" if result else None,
        )
    )
    session.add(
        Quote(
            drawing_id=1,
            event_order=order,
            bk_win_1=bk[0],
            bk_draw=bk[1],
            bk_win_2=bk[2],
            pool_win_1=pool[0],
            pool_draw=pool[1],
            pool_win_2=pool[2],
        )
    )
