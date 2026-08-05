import math

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.brief_oracle import (
    choose_event_cover_options,
    choose_oracle_brief,
    outcome_rank,
    run_brief_oracle_research,
    summarize_brief_oracle,
    write_brief_oracle_reports,
)
from toto_ai.db.models import Base, Drawing, Event, Quote


def test_outcome_rank_uses_bk_probability_order():
    probabilities = {"1": 0.50, "X": 0.30, "2": 0.20}

    assert outcome_rank(probabilities, "1") == 1
    assert outcome_rank(probabilities, "X") == 2
    assert outcome_rank(probabilities, "2") == 3


def test_event_cover_options_always_include_actual_result():
    options = choose_event_cover_options(
        bk_probabilities={"1": 0.55, "X": 0.20, "2": 0.25},
        actual_result="X",
    )

    assert [option.cover for option in options] == ["1X", "1X2"]
    assert all("X" in option.cover for option in options)


def test_choose_oracle_brief_minimizes_size_then_tie_breaks_probability():
    event_options = [
        choose_event_cover_options({"1": 0.70, "X": 0.20, "2": 0.10}, "1"),
        choose_event_cover_options({"1": 0.45, "X": 0.40, "2": 0.15}, "X"),
        choose_event_cover_options({"1": 0.50, "X": 0.20, "2": 0.30}, "2"),
    ]

    brief = choose_oracle_brief(event_options)

    assert brief.brief == ["1", "1X", "12"]
    assert brief.full_variant_count == 4
    assert brief.singles_count == 1
    assert brief.doubles_count == 2
    assert brief.triples_count == 0
    assert brief.actual_result_string == "1X2"
    assert brief.log_brief_probability == pytest.approx(
        math.log(0.70) + math.log(0.85) + math.log(0.80)
    )


def test_run_brief_oracle_filters_incomplete_results_and_missing_bk():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1X2" * 5)
        _add_drawing(session, drawing_id=2, number=1002, results="1" * 14 + "?")
        _add_drawing(
            session,
            drawing_id=3,
            number=1003,
            results="1" * 15,
            include_bk=False,
        )

        result = run_brief_oracle_research(session, last=10)

    assert result.summary["drawings_tested"] == 1
    assert result.rows[0].drawing_number == 1001
    assert result.rows[0].actual_result_string == "1X21X21X21X21X2"


def test_run_brief_oracle_returns_drawing_and_event_metrics():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1X2" * 5)

        result = run_brief_oracle_research(session, last=1)

    row = result.rows[0]
    assert row.singles_count == 5
    assert row.doubles_count == 10
    assert row.triples_count == 0
    assert row.full_variant_count == 1024
    assert row.actual_bk_top_count == 5
    assert row.actual_bk_second_count == 5
    assert row.actual_bk_third_count == 5
    assert row.pool_top_differs_from_bk_top_count == 15
    assert row.actual_contradicts_pool_and_bk_top_count == 5
    assert len(result.event_rows) == 15


def test_summarize_brief_oracle_computes_aggregate_metrics():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1X2" * 5)
        _add_drawing(session, drawing_id=2, number=1002, results="1" * 15)

        result = run_brief_oracle_research(session, last=2)
        summary = summarize_brief_oracle(result.rows, result.event_rows)

    assert summary["drawings_tested"] == 2
    assert summary["average_singles"] == 10.0
    assert summary["median_full_variant_count"] == pytest.approx(512.5)
    assert summary["bk_rank_frequency"][1]["count"] == 20
    assert summary["bk_rank_frequency"][2]["count"] == 5
    assert summary["bk_rank_frequency"][3]["count"] == 5
    assert summary["entropy_by_cover_size"][1]["event_count"] == 20
    assert summary["entropy_by_cover_size"][2]["event_count"] == 10


def test_write_brief_oracle_reports_exports_expected_files(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1X2" * 5)
        result = run_brief_oracle_research(session, last=1)

    csv_path, markdown_path, event_csv_path = write_brief_oracle_reports(
        result,
        report_dir=tmp_path,
    )

    assert csv_path == tmp_path / "brief_oracle.csv"
    assert markdown_path == tmp_path / "brief_oracle.md"
    assert event_csv_path == tmp_path / "brief_oracle_by_event.csv"
    assert "drawing_number" in csv_path.read_text()
    assert "Brief Oracle Research" in markdown_path.read_text()
    assert "event_order" in event_csv_path.read_text()


def _add_drawing(
    session: Session,
    drawing_id: int,
    number: int,
    results: str,
    include_bk: bool = True,
) -> None:
    session.add(
        Drawing(
            id=drawing_id,
            number=number,
            name="baltbet-main",
            status="finished",
        )
    )
    for index, result in enumerate(results):
        normalized = None if result == "?" else result
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=index,
                name=f"Event {index + 1}",
                championship="Test League",
                result=normalized,
                score="1:0" if normalized else None,
            )
        )
        if include_bk:
            bk = _bk_for_result_pattern(result)
        else:
            bk = (None, None, None)
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=index,
                bk_win_1=bk[0],
                bk_draw=bk[1],
                bk_win_2=bk[2],
                pool_win_1=0.20,
                pool_draw=0.60,
                pool_win_2=0.20,
            )
        )
    session.commit()


def _bk_for_result_pattern(result: str) -> tuple[float, float, float]:
    if result == "1":
        return (0.60, 0.25, 0.15)
    if result == "X":
        return (0.55, 0.30, 0.15)
    return (0.55, 0.30, 0.15)
