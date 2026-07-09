from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.validation import (
    generate_validation_report,
    run_validation,
    write_validation_report,
)
from toto_ai.db.models import Base, Drawing, Event, Quote


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Drawing(
                id=11935,
                number=4938,
                name="baltbet-main",
                status="finished",
                pool_sum=100.0,
                jackpot=20.0,
                started_at="2026-01-01T10:00:00Z",
                ended_at="2026-01-01T12:00:00Z",
            )
        )
        session.add_all(
            [
                Event(
                    drawing_id=11935,
                    event_order=0,
                    name="A",
                    championship="League",
                    sport="football",
                    result="win_1",
                    score="2:1",
                ),
                Event(
                    drawing_id=11935,
                    event_order=1,
                    name="B",
                    championship="League",
                    sport="football",
                    result="draw",
                    score="0:0",
                ),
            ]
        )
        session.add_all(
            [
                Quote(
                    drawing_id=11935,
                    event_order=0,
                    pool_win_1=0.50,
                    pool_draw=0.30,
                    pool_win_2=0.20,
                    bk_win_1=0.60,
                    bk_draw=0.25,
                    bk_win_2=0.15,
                ),
                Quote(
                    drawing_id=11935,
                    event_order=1,
                    pool_win_1=0.20,
                    pool_draw=0.50,
                    pool_win_2=0.30,
                    bk_win_1=0.25,
                    bk_draw=0.55,
                    bk_win_2=0.20,
                ),
            ]
        )
        session.commit()
        yield session

    engine.dispose()


def raw_payload():
    return {
        "data": {
            "id": 11935,
            "number": 4938,
            "name": "baltbet-main",
            "status": "finished",
            "pool_sum": 100.0,
            "jackpot": 20.0,
            "started_at": "2026-01-01T10:00:00Z",
            "ended_at": "2026-01-01T12:00:00Z",
            "events": [
                {
                    "order": 0,
                    "name": "A",
                    "championship": "League",
                    "sport": "football",
                    "result": "win_1",
                    "score": "2:1",
                    "quotes": {
                        "pool_win_1": 0.50,
                        "pool_draw": 0.30,
                        "pool_win_2": 0.20,
                        "bk_win_1": 0.60,
                        "bk_draw": 0.25,
                        "bk_win_2": 0.15,
                    },
                },
                {
                    "order": 1,
                    "name": "B",
                    "championship": "League",
                    "sport": "football",
                    "result": "draw",
                    "score": "0:0",
                    "quotes": {
                        "pool_win_1": 0.20,
                        "pool_draw": 0.50,
                        "pool_win_2": 0.30,
                        "bk_win_1": 0.25,
                        "bk_draw": 0.55,
                        "bk_win_2": 0.20,
                    },
                },
            ],
        }
    }


def test_run_validation_passes_when_raw_json_matches_sqlite(session):
    result = run_validation(session, raw_payload(), number=4938)

    assert result["overall_status"] == "PASS"
    assert result["raw_vs_sqlite"]["status"] == "PASS"
    assert result["analytics"]["status"] == "PASS"
    assert result["result_mapping"]["status"] == "PASS"
    assert result["score_mapping"]["status"] == "PASS"
    assert result["quote_totals"] == [
        {
            "event_order": 1,
            "pool1": 0.5,
            "poolX": 0.3,
            "pool2": 0.2,
            "sum": 1.0,
        },
        {
            "event_order": 2,
            "pool1": 0.2,
            "poolX": 0.5,
            "pool2": 0.3,
            "sum": 1.0,
        },
    ]


def test_run_validation_fails_on_raw_sqlite_mismatch(session):
    payload = raw_payload()
    payload["data"]["events"][0]["score"] = "3:1"

    result = run_validation(session, payload, number=4938)

    assert result["overall_status"] == "FAIL"
    assert result["raw_vs_sqlite"]["status"] == "FAIL"
    assert {
        "field": "events[0].score",
        "raw": "3:1",
        "sqlite": "2:1",
    } in result["raw_vs_sqlite"]["mismatches"]
    assert result["score_mapping"]["status"] == "FAIL"


def test_generate_and_write_validation_report(session, tmp_path):
    result = run_validation(session, raw_payload(), number=4938)
    report = generate_validation_report(result)
    path = write_validation_report(result, report_dir=tmp_path)

    assert "# TotoAI Validation 4938" in report
    assert "Overall status: PASS" in report
    assert "| 1 | 0.5 | 0.3 | 0.2 | 1.0 |" in report
    assert path == Path(tmp_path) / "validation_4938.md"
    assert path.read_text() == report
