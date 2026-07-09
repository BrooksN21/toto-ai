import pytest

from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.package.backtest import (
    best_coupon_hits,
    build_result_string,
    category_hits,
    count_coupon_hits,
    run_mvp_backtest,
    select_complete_finished_drawings,
)


@pytest.fixture
def session(tmp_path):
    engine = init_db(tmp_path / "test.db")
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        yield session


def test_result_string_building(session):
    drawing = _add_drawing(session, drawing_id=1, number=100)
    _add_events_and_quotes(session, drawing.id, "1X2" * 5)

    events = session.query(Event).filter(Event.drawing_id == drawing.id).all()

    assert build_result_string(events) == "1X21X21X21X21X2"


def test_coupon_hit_counting():
    result_string = "111111111111111"

    assert count_coupon_hits("111111111111111", result_string) == 15
    assert count_coupon_hits("111111111111112", result_string) == 14
    assert best_coupon_hits(
        ["222222222222222", "111111111111112"],
        result_string,
    ) == 14


def test_missing_result_exclusion(session):
    complete = _add_drawing(session, drawing_id=1, number=101)
    incomplete = _add_drawing(session, drawing_id=2, number=102)
    _add_events_and_quotes(session, complete.id, "1" * 15)
    _add_events_and_quotes(session, incomplete.id, "1" * 14 + "?")

    selected = select_complete_finished_drawings(session, last=10)

    assert [drawing.id for drawing in selected] == [complete.id]


@pytest.mark.parametrize(
    ("best_hits", "expected"),
    [
        (12, {"hit_13": False, "hit_14": False, "hit_15": False}),
        (13, {"hit_13": True, "hit_14": False, "hit_15": False}),
        (14, {"hit_13": True, "hit_14": True, "hit_15": False}),
        (15, {"hit_13": True, "hit_14": True, "hit_15": True}),
    ],
)
def test_category_hit_detection(best_hits, expected):
    assert category_hits(best_hits) == expected


def test_backtest_uses_arbitrary_bank_and_stake_for_cost(session):
    drawing = _add_drawing(session, drawing_id=1, number=100)
    _add_events_and_quotes(session, drawing.id, "1" * 15)

    result = run_mvp_backtest(
        session,
        last=100,
        bank=95,
        stake=30,
        category=15,
    )

    assert result.summary["drawings_tested"] == 1
    assert result.rows[0].coupons == 1
    assert result.rows[0].cost == 30
    assert result.summary["total_cost"] == 30
    assert result.summary["hit_15_count"] == 1
    assert result.summary["total_payout"] is None
    assert result.summary["roi"] is None


def _add_drawing(session, drawing_id: int, number: int) -> Drawing:
    drawing = Drawing(
        id=drawing_id,
        number=number,
        name="baltbet-main",
        status="finished",
        pool_sum=1000,
        jackpot=100,
        started_at="2026-01-01T00:00:00",
        ended_at="2026-01-02T00:00:00",
    )
    session.add(drawing)
    session.commit()
    return drawing


def _add_events_and_quotes(session, drawing_id: int, results: str) -> None:
    for event_order in range(15):
        raw_result = results[event_order]
        result = raw_result if raw_result != "?" else None
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=event_order,
                name=f"Event {event_order + 1}",
                championship="League",
                sport="football",
                result=result,
                score="1:0" if result else None,
            )
        )
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=event_order,
                pool_win_1=60,
                pool_draw=25,
                pool_win_2=15,
                bk_win_1=60,
                bk_draw=25,
                bk_win_2=15,
                pin_win_1=None,
                pin_draw=None,
                pin_win_2=None,
                norm_win_1=None,
                norm_draw=None,
                norm_win_2=None,
            )
        )
    session.commit()
