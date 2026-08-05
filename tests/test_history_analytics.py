import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.history import (
    get_crowd_accuracy,
    get_drawings_summary,
    get_event_diagnostics,
    get_outcome_distribution,
    get_position_distribution,
    get_value_buckets,
    normalize_result,
)
from toto_ai.db.models import Base, Drawing, Event, Quote


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Drawing(
                    id=1,
                    number=1,
                    name="baltbet-main",
                    status="finished",
                    pool_sum=100.0,
                    jackpot=10.0,
                ),
                Drawing(
                    id=2,
                    number=2,
                    name="baltbet-main",
                    status="finished",
                    pool_sum=200.0,
                    jackpot=30.0,
                ),
                Drawing(
                    id=3,
                    number=3,
                    name="baltbet-main",
                    status="open",
                    pool_sum=None,
                    jackpot=None,
                ),
            ]
        )
        session.add_all(
            [
                Event(
                    drawing_id=1,
                    event_order=0,
                    name="A",
                    result="win_1",
                    score="2:1",
                ),
                Event(
                    drawing_id=1,
                    event_order=1,
                    name="B",
                    result="draw",
                    score="0:0",
                ),
                Event(
                    drawing_id=2,
                    event_order=0,
                    name="C",
                    result="win_2",
                    score="0:1",
                ),
                Event(
                    drawing_id=2,
                    event_order=2,
                    name="D",
                    result=None,
                ),
                Event(
                    drawing_id=3,
                    event_order=0,
                    name="Open drawing event",
                    result=None,
                ),
            ]
        )
        session.add_all(
            [
                Quote(
                    drawing_id=1,
                    event_order=0,
                    pool_win_1=0.70,
                    pool_draw=0.20,
                    pool_win_2=0.10,
                    bk_win_1=0.60,
                    bk_draw=0.25,
                    bk_win_2=0.15,
                ),
                Quote(
                    drawing_id=1,
                    event_order=1,
                    pool_win_1=0.60,
                    pool_draw=0.30,
                    pool_win_2=0.10,
                    bk_win_1=0.20,
                    bk_draw=0.50,
                    bk_win_2=0.30,
                ),
                Quote(
                    drawing_id=2,
                    event_order=0,
                    pool_win_1=0.30,
                    pool_draw=0.20,
                    pool_win_2=0.50,
                    bk_win_1=0.40,
                    bk_draw=0.30,
                    bk_win_2=0.30,
                ),
                Quote(
                    drawing_id=2,
                    event_order=2,
                    pool_win_1=0.40,
                    pool_draw=0.30,
                    pool_win_2=0.30,
                    bk_win_1=0.50,
                    bk_draw=0.25,
                    bk_win_2=0.25,
                ),
                Quote(
                    drawing_id=3,
                    event_order=0,
                    pool_win_1=0.90,
                    pool_draw=0.05,
                    pool_win_2=0.05,
                    bk_win_1=0.80,
                    bk_draw=0.10,
                    bk_win_2=0.10,
                ),
            ]
        )
        session.commit()
        yield session

    engine.dispose()


def test_get_drawings_summary(session):
    summary = get_drawings_summary(session)

    assert summary == {
        "total_drawings": 3,
        "finished_drawings": 2,
        "total_events": 5,
        "avg_pool_sum": 150.0,
        "avg_jackpot": 20.0,
    }


def test_get_outcome_distribution(session):
    distribution = get_outcome_distribution(session)

    assert distribution == {
        "1": {"count": 1, "percentage": pytest.approx(33.3333)},
        "X": {"count": 1, "percentage": pytest.approx(33.3333)},
        "2": {"count": 1, "percentage": pytest.approx(33.3333)},
    }


def test_get_position_distribution(session):
    distribution = get_position_distribution(session)

    assert distribution[1] == {
        "1": {"count": 1, "percentage": 50.0},
        "X": {"count": 0, "percentage": 0.0},
        "2": {"count": 1, "percentage": 50.0},
    }
    assert distribution[2] == {
        "1": {"count": 0, "percentage": 0.0},
        "X": {"count": 1, "percentage": 100.0},
        "2": {"count": 0, "percentage": 0.0},
    }
    assert distribution[15] == {
        "1": {"count": 0, "percentage": 0.0},
        "X": {"count": 0, "percentage": 0.0},
        "2": {"count": 0, "percentage": 0.0},
    }


def test_get_crowd_accuracy(session):
    accuracy = get_crowd_accuracy(session)

    assert accuracy == {
        "events_evaluated": 3,
        "crowd_top_hit_rate": pytest.approx(66.6667),
        "bookmaker_top_hit_rate": pytest.approx(66.6667),
        "crowd_vs_bookmaker_agreement_rate": pytest.approx(33.3333),
    }


def test_get_value_buckets(session):
    buckets = get_value_buckets(session)

    assert buckets["<= -20%"] == {"count": 2, "hit_rate": 50.0}
    assert buckets["-20%..-10%"] == {"count": 1, "hit_rate": 100.0}
    assert buckets["-10%..0"] == {"count": 0, "hit_rate": 0.0}
    assert buckets["0..10%"] == {"count": 2, "hit_rate": 0.0}
    assert buckets["10%..20%"] == {"count": 4, "hit_rate": 25.0}
    assert buckets[">20%"] == {"count": 0, "hit_rate": 0.0}


def test_normalize_result_accepts_common_outcome_labels():
    assert normalize_result("win_1") == "1"
    assert normalize_result("1") == "1"
    assert normalize_result("draw") == "X"
    assert normalize_result("X") == "X"
    assert normalize_result("win_2") == "2"
    assert normalize_result("2") == "2"
    assert normalize_result("unknown") is None
    assert normalize_result(None) is None


def test_get_event_diagnostics_reports_pool_and_bookmaker_hits(session):
    rows = get_event_diagnostics(session, limit=20)

    assert rows[0] == {
        "drawing_id": 1,
        "event_order": 1,
        "event_name": "A",
        "score": "2:1",
        "result": "1",
        "pool_1": 0.70,
        "pool_x": 0.20,
        "pool_2": 0.10,
        "bk_1": 0.60,
        "bk_x": 0.25,
        "bk_2": 0.15,
        "pool_top": "1",
        "bk_top": "1",
        "pool_hit": True,
        "bk_hit": True,
    }
    assert rows[1]["pool_top"] == "1"
    assert rows[1]["bk_top"] == "X"
    assert rows[1]["pool_hit"] is False
    assert rows[1]["bk_hit"] is True
    assert rows[2]["pool_top"] == "2"
    assert rows[2]["bk_top"] == "1"
    assert rows[2]["pool_hit"] is True
    assert rows[2]["bk_hit"] is False
