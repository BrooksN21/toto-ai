import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.audit import QUOTE_FIELDS, get_database_audit
from toto_ai.db.models import Base, Drawing, Event, Quote


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Drawing(id=1, number=1, status="finished"),
                Drawing(id=2, number=2, status="active"),
                Drawing(id=3, number=3, status="pending"),
            ]
        )
        session.add_all(
            [
                Event(
                    drawing_id=1,
                    event_order=0,
                    name="A",
                    championship="Premier",
                    sport="football",
                    result="win_1",
                    score="2:1",
                ),
                Event(
                    drawing_id=1,
                    event_order=1,
                    name="B",
                    championship="Premier",
                    sport="football",
                    result="draw",
                    score="",
                ),
                Event(
                    drawing_id=2,
                    event_order=0,
                    name="C",
                    championship="Cup",
                    sport=None,
                    result=None,
                    score=None,
                ),
            ]
        )
        session.add_all(
            [
                Quote(
                    drawing_id=1,
                    event_order=0,
                    pool_win_1=0.50,
                    pool_draw=0.30,
                    pool_win_2=0.20,
                    bk_win_1=0.60,
                    bk_draw=0.30,
                    bk_win_2=0.20,
                    pin_win_1=2.0,
                    pin_draw=4.0,
                    pin_win_2=4.0,
                ),
                Quote(
                    drawing_id=1,
                    event_order=1,
                    pool_win_1=0.40,
                    pool_draw=0.30,
                    pool_win_2=None,
                    bk_win_1=0.40,
                    bk_draw=0.35,
                    bk_win_2=0.25,
                    pin_win_1=None,
                    pin_draw=None,
                    pin_win_2=None,
                ),
            ]
        )
        session.commit()
        yield session

    engine.dispose()


def test_database_audit_counts_drawings_and_event_dimensions(session):
    audit = get_database_audit(session)

    assert audit["drawings"] == {
        "total": 3,
        "finished": 1,
        "active": 1,
        "other_statuses": {"pending": 1},
    }
    assert audit["sports"] == [
        {"sport": "football", "count": 2},
        {"sport": "missing", "count": 1},
    ]
    assert audit["championships"] == [
        {"championship": "Premier", "count": 2},
        {"championship": "Cup", "count": 1},
    ]
    assert audit["result_values"] == [
        {"result": "missing", "count": 1},
        {"result": "draw", "count": 1},
        {"result": "win_1", "count": 1},
    ]
    assert audit["score"] == {"filled": 1, "empty": 2}


def test_database_audit_quote_completeness_and_probability_validation(session):
    audit = get_database_audit(session)

    assert set(audit["quote_completeness"]) == set(QUOTE_FIELDS)
    assert audit["quote_completeness"]["pool_win_2"] == {"filled": 1, "missing": 1}
    assert audit["quote_completeness"]["bk_win_2"] == {"filled": 2, "missing": 0}
    assert audit["quote_completeness"]["pin_win_1"] == {"filled": 1, "missing": 1}

    assert audit["probability_validation"]["pool"] == {
        "min": 1.0,
        "max": 1.0,
        "average": 1.0,
        "diff_gt_0_001": 0,
        "diff_gt_0_01": 0,
        "diff_gt_0_05": 0,
    }
    assert audit["probability_validation"]["bk"] == {
        "min": 1.0,
        "max": 1.1,
        "average": 1.05,
        "diff_gt_0_001": 1,
        "diff_gt_0_01": 1,
        "diff_gt_0_05": 1,
    }
    assert audit["probability_validation"]["pin"] == {
        "min": 1.0,
        "max": 1.0,
        "average": 1.0,
        "diff_gt_0_001": 0,
        "diff_gt_0_01": 0,
        "diff_gt_0_05": 0,
    }


def test_database_audit_duplicates_and_quality_score(session):
    audit = get_database_audit(session)

    assert audit["duplicates"] == {
        "drawings": 0,
        "events": 0,
    }
    assert audit["quality_score"] == pytest.approx(73.61, abs=0.01)
