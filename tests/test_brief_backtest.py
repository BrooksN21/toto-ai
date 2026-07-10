from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.optimizer.brief import CoverEngineCache, deduplicate_briefs
from toto_ai.optimizer.brief_backtest import (
    count_uncovered_outcomes,
    run_brief_backtest,
    write_brief_backtest_reports,
)


def test_count_uncovered_outcomes_counts_results_outside_brief():
    assert count_uncovered_outcomes(["1", "1X", "2"], "1X2") == 0
    assert count_uncovered_outcomes(["1", "1X", "2"], "221") == 3


def test_cover_cache_hits_for_same_brief_category_and_coupon_limit():
    calls = []

    def cover_func(brief, category, max_coupons):
        calls.append((tuple(brief), category, max_coupons))
        return {
            "selected_coupons": ["111"],
            "full_variants_count": 1,
            "covered_variants_count": 1,
            "coverage_rate": 1.0,
        }

    cache = CoverEngineCache(cover_func=cover_func)

    first = cache.get(["1", "1", "1"], category=13, max_coupons=10)
    second = cache.get(["1", "1", "1"], category=13, max_coupons=10)

    assert first == second
    assert len(calls) == 1
    assert cache.hits == 1
    assert cache.misses == 1


def test_deduplicate_briefs_preserves_order():
    assert deduplicate_briefs(
        [
            ["1", "X"],
            ["1", "X"],
            ["1X", "2"],
        ]
    ) == [["1", "X"], ["1X", "2"]]


def test_run_brief_backtest_limits_exact_evaluation_to_top_candidates(monkeypatch):
    import toto_ai.optimizer.brief as brief_module

    evaluated = []

    monkeypatch.setattr(
        brief_module,
        "_candidate_briefs",
        lambda analyses, max_candidate_briefs=None: [
            ["1"] * 15,
            ["1X"] + ["1"] * 14,
            ["1X2"] + ["1"] * 14,
        ],
    )

    class TrackingCache(brief_module.CoverEngineCache):
        def get(self, brief, category, max_coupons):
            evaluated.append(tuple(brief))
            return super().get(brief, category, max_coupons)

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        run_brief_backtest(
            session,
            last=1,
            bank=90,
            stake=30,
            category=15,
            top_candidates=1,
            cover_cache=TrackingCache(),
        )

    assert len(evaluated) == 1


def test_run_brief_backtest_timeout_keeps_best_candidate_found(monkeypatch):
    import toto_ai.optimizer.brief as brief_module

    current_time = {"value": 0.0}

    def fake_perf_counter():
        current_time["value"] += 2.0
        return current_time["value"]

    monkeypatch.setattr(brief_module.time, "perf_counter", fake_perf_counter)
    monkeypatch.setattr(
        brief_module,
        "_candidate_briefs",
        lambda analyses, max_candidate_briefs=None: [
            ["1"] * 15,
            ["1X"] + ["1"] * 14,
        ],
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        result = run_brief_backtest(
            session,
            last=1,
            bank=90,
            stake=30,
            category=15,
            timeout_per_drawing=1,
        )

    assert result.rows[0].timed_out is True
    assert result.rows[0].package_size > 0


def test_run_brief_backtest_progress_callback_is_safe():
    updates = []
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        run_brief_backtest(
            session,
            last=1,
            bank=90,
            stake=30,
            category=15,
            progress_callback=updates.append,
        )

    assert updates
    assert updates[-1]["drawing_number"] == 1001


def test_run_brief_backtest_excludes_drawings_with_missing_results():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        _add_drawing(session, drawing_id=2, number=1002, results="1" * 14 + "?")

        result = run_brief_backtest(
            session,
            last=10,
            bank=90,
            stake=30,
            category=15,
        )

    assert result.summary["drawings_tested"] == 1
    assert result.rows[0].drawing_number == 1001


def test_run_brief_backtest_skips_drawings_missing_pre_match_quotes():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        _add_drawing(
            session,
            drawing_id=2,
            number=1002,
            results="1" * 15,
            include_bk=False,
        )

        result = run_brief_backtest(
            session,
            last=10,
            bank=90,
            stake=30,
            category=15,
        )

    assert result.summary["drawings_tested"] == 1
    assert result.rows[0].drawing_number == 1001


def test_run_brief_backtest_calculates_containment_hits_and_costs():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)

        result = run_brief_backtest(
            session,
            last=1,
            bank=90,
            stake=30,
            category=15,
        )

    row = result.rows[0]
    assert row.actual_inside_brief is True
    assert row.uncovered_outcomes == 0
    assert row.best_coupon_hits == 15
    assert row.hit_13 is True
    assert row.hit_14 is True
    assert row.hit_15 is True
    assert row.package_size == 1
    assert row.package_cost == 30
    assert row.brief_full_variants == 1
    assert row.category_guarantee == "PASS"
    assert result.summary["brief_containment_rate"] == 100.0
    assert result.summary["average_uncovered_outcomes"] == 0.0
    assert result.summary["hit_15_rate"] == 100.0
    assert result.summary["average_package_cost"] == 30.0


def test_write_brief_backtest_reports_exports_csv_and_markdown(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        result = run_brief_backtest(
            session,
            last=1,
            bank=90,
            stake=30,
            category=15,
        )

    csv_path, markdown_path = write_brief_backtest_reports(
        result,
        last=1,
        report_dir=tmp_path,
    )

    assert csv_path == tmp_path / "backtest_brief_last_1.csv"
    assert markdown_path == tmp_path / "backtest_brief_last_1.md"
    assert "drawing_number" in csv_path.read_text()
    assert "Baseline Brief Backtest" in markdown_path.read_text()


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
            ended_at="2026-01-01T00:00:00Z",
        )
    )
    for event_order, result in enumerate(results):
        session.add(
            Event(
                drawing_id=drawing_id,
                event_order=event_order,
                name=f"Match {event_order + 1}",
                result=None if result == "?" else result,
                score=None if result == "?" else "1:0",
            )
        )
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=event_order,
                pool_win_1=50,
                pool_draw=30,
                pool_win_2=20,
                bk_win_1=70 if include_bk else None,
                bk_draw=20 if include_bk else None,
                bk_win_2=10 if include_bk else None,
            )
        )
    session.commit()
