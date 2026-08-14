from toto_ai.sports_stats.preliminary_comparison import (
    _exposure_differences,
    _markdown,
    _package_text,
)


def test_preliminary_comparison_reports_only_changed_event_exposure():
    baseline = ("1" * 15, "X" + "1" * 14)
    sports = ("1" * 15, "2" + "1" * 14)

    assert _exposure_differences(baseline, sports) == [
        {
            "event_order": 0,
            "event_number": 1,
            "baseline": {"1": 1, "X": 1, "2": 0},
            "sports_candidate": {"1": 1, "X": 0, "2": 1},
        }
    ]


def test_preliminary_package_text_is_exact_baltbet_batch_shape():
    payload = _package_text(30, ("1X2" * 5, "2X1" * 5))

    assert payload.decode("utf-8").splitlines() == [
        "30; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2; 1; X; 2",
        "30; 2; X; 1; 2; X; 1; 2; X; 1; 2; X; 1; 2; X; 1",
    ]


def test_preliminary_markdown_marks_ev_as_unvalidated():
    report = {
        "drawing_number": 4975,
        "bank": 4980,
        "stake": 30,
        "sports_coverage_count": 0,
        "sports_fallback_count": 15,
        "interpretation": "same BK-control package",
        "baseline": {
            "coupon_count": 166,
            "cost": 4980,
            "quality": {"probability_at_least_13": 0.001},
        },
        "sports_candidate": {
            "coupon_count": 166,
            "cost": 4980,
            "quality": {"probability_at_least_13": 0.001},
        },
        "comparison": {"overlap_count": 166, "identical": True},
    }

    rendered = _markdown(report)

    assert "PAPER ONLY" in rendered
    assert "same BK-control package" in rendered
    assert "not a profit forecast" in rendered
