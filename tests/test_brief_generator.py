import math
from dataclasses import replace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.optimizer.brief import (
    analyze_event,
    brief_hit_probability,
    build_baseline_brief,
    build_brief_for_drawing,
    rank_candidate_key,
)


def test_brief_probability_uses_sum_of_logs_for_bk_included_outcomes():
    analyses = [
        _analysis(pool=(0.50, 0.30, 0.20), bk=(0.60, 0.25, 0.15)),
        _analysis(pool=(0.40, 0.35, 0.25), bk=(0.45, 0.35, 0.20)),
    ]

    probability = brief_hit_probability(["1X", "12"], analyses)

    assert probability == math.exp(math.log(0.85) + math.log(0.65))


def test_value_against_crowd_is_weak_secondary_ranking_criterion():
    high_probability_low_value = {
        "brief_probability": 0.90,
        "coverage_rate": 0.50,
        "value_score": 0.01,
        "cost": 90,
    }
    lower_probability_high_value = {
        "brief_probability": 0.89,
        "coverage_rate": 0.50,
        "value_score": 10.0,
        "cost": 30,
    }

    assert rank_candidate_key(high_probability_low_value) > rank_candidate_key(
        lower_probability_high_value
    )


def test_analyze_event_selects_single_double_and_triple_reasons():
    clear = _analysis(pool=(0.50, 0.30, 0.20), bk=(0.70, 0.20, 0.10))
    uncertain = _analysis(pool=(0.45, 0.30, 0.25), bk=(0.48, 0.35, 0.17))
    balanced = _analysis(pool=(0.34, 0.33, 0.33), bk=(0.34, 0.33, 0.33))

    assert clear.base_pick == "1"
    assert clear.reason == "clear bookmaker favorite"
    assert uncertain.base_pick == "1X"
    assert uncertain.reason == "uncertain event"
    assert balanced.base_pick == "1X2"
    assert balanced.reason == "highly balanced event"


def test_build_baseline_brief_filters_candidates_by_bank_and_stake():
    analyses = [
        _analysis(pool=(0.50, 0.30, 0.20), bk=(0.70, 0.20, 0.10))
        for _ in range(15)
    ]
    result = build_baseline_brief(
        analyses,
        category=15,
        bank=95,
        stake=30,
    )

    assert result["cost"] <= 95
    assert len(result["selected_coupons"]) <= 3
    assert result["brief"] == ["1"] * 15
    assert result["category_guarantee"] == "PASS"


def test_build_baseline_brief_never_selects_partial_cover_as_category_seed():
    probability_rows = (
        (42.0, 25.0, 33.0),
        (38.0, 28.0, 33.0),
        (36.0, 27.0, 37.0),
        (42.0, 27.0, 31.0),
        (38.0, 29.0, 33.0),
        (37.0, 27.0, 37.0),
        (31.0, 25.0, 44.0),
        (27.0, 28.0, 45.0),
        (30.0, 30.0, 40.0),
        (42.0, 29.0, 29.0),
        (29.0, 25.0, 46.0),
        (28.0, 29.0, 43.0),
        (30.0, 31.0, 39.0),
        (27.0, 28.0, 46.0),
        (36.0, 28.0, 35.0),
    )
    analyses = [
        replace(_analysis(pool=row, bk=row), event_order=event_order)
        for event_order, row in enumerate(probability_rows)
    ]

    result = build_baseline_brief(
        analyses,
        category=14,
        bank=480,
        stake=30,
    )

    assert result["cost"] <= 480
    assert result["category_guarantee"] == "PASS"


def test_build_brief_for_drawing_loads_open_drawing_events_and_exports(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        drawing = Drawing(
            id=42,
            number=5001,
            name="baltbet-main",
            status="expected",
            ended_at="2030-01-01T00:00:00Z",
        )
        session.add(drawing)
        for event_order in range(15):
            session.add(
                Event(
                    drawing_id=42,
                    event_order=event_order,
                    name=f"Match {event_order + 1}",
                    championship="League",
                    sport="football",
                )
            )
            session.add(
                Quote(
                    drawing_id=42,
                    event_order=event_order,
                    pool_win_1=50,
                    pool_draw=30,
                    pool_win_2=20,
                    bk_win_1=70,
                    bk_draw=20,
                    bk_win_2=10,
                )
            )
        session.commit()

        result = build_brief_for_drawing(
            session,
            drawing_id=42,
            category=13,
            bank=1000,
            stake=30,
            report_dir=tmp_path,
        )

    assert result["drawing_number"] == 5001
    assert len(result["matches"]) == 15
    assert result["brief_path"] == tmp_path / "brief_5001.csv"
    assert result["package_path"] == tmp_path / "package_5001.csv"
    assert result["brief_path"].exists()
    assert result["package_path"].exists()


def _analysis(
    pool: tuple[float, float, float],
    bk: tuple[float, float, float],
):
    quote = Quote(
        pool_win_1=pool[0],
        pool_draw=pool[1],
        pool_win_2=pool[2],
        bk_win_1=bk[0],
        bk_draw=bk[1],
        bk_win_2=bk[2],
    )
    event = Event(event_order=0, name="Match")
    return analyze_event(event, quote)
