from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.analytics.budget_oracle import (
    choose_budget_oracle_package,
    run_budget_oracle,
    summarize_budget_oracle,
    write_budget_oracle_reports,
)
from toto_ai.db.models import Base, Drawing, Event, Quote


def test_choose_budget_oracle_package_maximizes_hits_then_cost_and_size():
    cover_results = {
        ("1", "1X"): {"selected_coupons": ["11"]},
        ("1X", "1X"): {"selected_coupons": ["1X", "11"]},
        ("1X", "1X2"): {"selected_coupons": ["12", "XX"]},
    }

    result = choose_budget_oracle_package(
        candidate_briefs=[
            ["1", "1X"],
            ["1X", "1X"],
            ["1X", "1X2"],
        ],
        result_string="1X",
        category=13,
        bank=60,
        stake=30,
        cover_func=lambda brief, category, max_coupons: cover_results[tuple(brief)],
    )

    assert result["brief"] == ["1X", "1X"]
    assert result["best_coupon_hits"] == 2
    assert result["package_size"] == 2
    assert result["package_cost"] == 60


def test_run_budget_oracle_filters_incomplete_drawings_and_compares_baseline():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1X2" * 5)
        _add_drawing(session, drawing_id=2, number=1002, results="1" * 14 + "?")

        result = run_budget_oracle(
            session,
            last=10,
            bank=60,
            stake=30,
            category=13,
            cover_func=_exact_result_cover,
            baseline_func=_baseline_stub,
        )

    assert result.summary["drawings_tested"] == 1
    row = result.rows[0]
    assert row.drawing_number == 1001
    assert row.oracle_best_hits == 15
    assert row.oracle_hit_13 is True
    assert row.baseline_best_hits == 12
    assert row.oracle_baseline_gap == 3


def test_summarize_budget_oracle_computes_required_metrics():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        _add_drawing(session, drawing_id=2, number=1002, results="1X2" * 5)

        result = run_budget_oracle(
            session,
            last=2,
            bank=90,
            stake=30,
            category=13,
            cover_func=_exact_result_cover,
            baseline_func=_baseline_stub,
        )
        summary = summarize_budget_oracle(result.rows)

    assert summary["drawings_tested"] == 2
    assert summary["oracle_average_best_hits"] == 15.0
    assert summary["oracle_hit13_count"] == 2
    assert summary["oracle_hit13_rate"] == 100.0
    assert summary["oracle_hit14_count"] == 2
    assert summary["oracle_hit15_count"] == 2
    assert summary["baseline_average_best_hits"] == 12.0
    assert summary["average_oracle_baseline_gap"] == 3.0


def test_write_budget_oracle_reports_exports_csv_and_markdown(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        result = run_budget_oracle(
            session,
            last=1,
            bank=90,
            stake=30,
            category=13,
            cover_func=_exact_result_cover,
            baseline_func=_baseline_stub,
        )

    csv_path, markdown_path = write_budget_oracle_reports(
        result,
        last=1,
        report_dir=tmp_path,
    )

    assert csv_path == tmp_path / "budget_oracle_last_1.csv"
    assert markdown_path == tmp_path / "budget_oracle_last_1.md"
    assert "oracle_best_hits" in csv_path.read_text()
    assert "Budget-Constrained Brief Oracle" in markdown_path.read_text()


def test_choose_budget_oracle_timeout_keeps_best_candidate_found():
    ticks = iter([0.0, 0.2, 0.4, 0.6, 2.0])

    def clock():
        try:
            return next(ticks)
        except StopIteration:
            return 2.0

    result = choose_budget_oracle_package(
        candidate_briefs=[
            ["1", "1"],
            ["1X", "1X"],
        ],
        result_string="1X",
        category=13,
        bank=60,
        stake=30,
        cover_func=lambda brief, category, max_coupons: {
            "selected_coupons": ["11" if brief == ["1", "1"] else "1X"]
        },
        timeout_per_drawing=1,
        time_func=clock,
    )

    assert result["best_coupon_hits"] == 1
    assert result["timed_out"] is True
    assert result["candidate_count"] == 2
    assert result["processed_candidate_count"] == 1


def test_choose_budget_oracle_max_candidates_only_limits_when_passed():
    calls = []
    candidate_briefs = [["1"], ["X"], ["2"]]

    choose_budget_oracle_package(
        candidate_briefs=candidate_briefs,
        result_string="1",
        category=13,
        bank=90,
        stake=30,
        cover_func=lambda brief, category, max_coupons: _tracking_cover(
            calls,
            brief,
        ),
    )
    assert len(calls) == 3

    calls.clear()
    choose_budget_oracle_package(
        candidate_briefs=candidate_briefs,
        result_string="1",
        category=13,
        bank=90,
        stake=30,
        cover_func=lambda brief, category, max_coupons: _tracking_cover(
            calls,
            brief,
        ),
        max_candidates=2,
    )
    assert len(calls) == 2


def test_choose_budget_oracle_profiles_workload_without_changing_selection():
    calls = []

    def cover(brief, category, max_coupons):
        calls.append(tuple(brief))
        return {
            "selected_coupons": ["1X" if brief == ["1X", "1X"] else "11"],
            "full_variants_count": 1,
            "covered_variants_count": 1,
            "coverage_rate": 1.0,
        }

    plain = choose_budget_oracle_package(
        candidate_briefs=[
            ["1", "1"],
            ["1", "1"],
            ["1X", "1X"],
        ],
        result_string="1X",
        category=13,
        bank=60,
        stake=30,
        cover_func=cover,
    )
    calls.clear()

    profiled = choose_budget_oracle_package(
        candidate_briefs=[
            ["1", "1"],
            ["1", "1"],
            ["1X", "1X"],
        ],
        result_string="1X",
        category=13,
        bank=60,
        stake=30,
        cover_func=cover,
        profile_workload=True,
    )

    assert profiled["brief"] == plain["brief"]
    assert profiled["best_coupon_hits"] == plain["best_coupon_hits"]
    assert profiled["workload"]["generated_candidates"] == 3
    assert profiled["workload"]["unique_candidates"] == 2
    assert profiled["workload"]["cover_engine_calls"] == 2
    assert profiled["workload"]["cache_hits"] == 1
    assert profiled["workload"]["cache_misses"] == 2
    assert profiled["workload"]["max_brief_variant_count"] == 4
    assert len(profiled["workload"]["slowest_candidate_briefs"]) == 2


def test_run_budget_oracle_aggregates_profiled_workload():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        _add_drawing(session, drawing_id=2, number=1002, results="X" * 15)

        result = run_budget_oracle(
            session,
            last=2,
            bank=60,
            stake=30,
            category=13,
            cover_func=_exact_result_cover,
            baseline_func=_baseline_stub,
            profile_workload=True,
        )

    assert result.rows[0].generated_candidates > 0
    assert result.rows[0].unique_candidates > 0
    assert result.rows[0].cover_engine_calls > 0
    assert result.summary["generated_candidates_total"] >= 2
    assert result.summary["unique_candidates_total"] >= 2
    assert result.summary["cover_engine_calls_total"] >= 2
    assert result.summary["cache_misses_total"] >= 2
    assert result.summary["max_brief_variant_count"] >= 1
    assert isinstance(result.summary["slowest_candidate_briefs"], list)


def test_run_budget_oracle_reports_progress_and_partial_csv(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for drawing_id in range(1, 11):
            _add_drawing(
                session,
                drawing_id=drawing_id,
                number=1000 + drawing_id,
                results="1" * 15,
            )

        updates = []
        result = run_budget_oracle(
            session,
            last=10,
            bank=60,
            stake=30,
            category=13,
            cover_func=_exact_result_cover,
            baseline_func=_baseline_stub,
            progress_callback=updates.append,
            partial_csv_path=tmp_path / "partial.csv",
        )

    assert result.summary["drawings_tested"] == 10
    assert result.summary["processed_count"] == 10
    assert updates
    assert updates[-1]["processed_count"] == 10
    assert updates[-1]["drawing_index"] == 10
    assert "average_time_per_drawing" in updates[-1]
    assert "eta_seconds" in updates[-1]
    assert "candidate_generation_time" in result.rows[0].__dict__
    assert "cover_generation_time" in result.rows[0].__dict__
    assert "verification_time" in result.rows[0].__dict__
    assert "total_time" in result.rows[0].__dict__
    assert "drawing_number" in (tmp_path / "partial.csv").read_text()


def test_run_budget_oracle_skips_failed_drawing_without_failing_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_drawing(session, drawing_id=1, number=1001, results="1" * 15)
        _add_drawing(session, drawing_id=2, number=1002, results="X" * 15)

        def flaky_cover(brief, category, max_coupons):
            if "X" in brief[0]:
                raise RuntimeError("cover failed")
            return _exact_result_cover(brief, category, max_coupons)

        result = run_budget_oracle(
            session,
            last=2,
            bank=60,
            stake=30,
            category=13,
            cover_func=flaky_cover,
            baseline_func=_baseline_stub,
        )

    assert result.summary["processed_count"] == 1
    assert result.summary["skipped_count"] == 1


def _add_drawing(
    session: Session,
    drawing_id: int,
    number: int,
    results: str,
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
        session.add(
            Quote(
                drawing_id=drawing_id,
                event_order=index,
                bk_win_1=0.60 if result == "1" else 0.45,
                bk_draw=0.30 if result == "X" else 0.25,
                bk_win_2=0.30 if result == "2" else 0.15,
                pool_win_1=0.50,
                pool_draw=0.30,
                pool_win_2=0.20,
            )
        )
    session.commit()


def _exact_result_cover(brief, category, max_coupons):
    del category, max_coupons
    coupon = "".join(position[-1] for position in brief)
    return {
        "selected_coupons": [coupon],
        "full_variants_count": 1,
        "covered_variants_count": 1,
        "coverage_rate": 1.0,
    }


def _tracking_cover(calls, brief):
    calls.append(tuple(brief))
    return {
        "selected_coupons": ["1"],
        "full_variants_count": 1,
        "covered_variants_count": 1,
        "coverage_rate": 1.0,
    }


def _baseline_stub(events, quotes, result_string, category, bank, stake):
    del events, quotes, result_string, category, bank, stake
    return {
        "baseline_best_hits": 12,
        "baseline_package_size": 1,
        "baseline_package_cost": 30,
    }
