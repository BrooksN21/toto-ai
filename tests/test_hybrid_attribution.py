from types import SimpleNamespace

from toto_ai.optimizer.hybrid_attribution import (
    build_hybrid_event_attribution,
    write_hybrid_event_attribution,
)


def _packages():
    rows = [list("1" * 15) for _ in range(4)]
    rows[0][0], rows[0][2] = "X", "X"
    rows[1][0], rows[1][2], rows[1][4] = "X", "X", "X"
    rows[2][0], rows[2][2], rows[2][5] = "X", "X", "2"
    rows[3][1], rows[3][6] = "X", "X"
    package = tuple("".join(row) for row in rows)
    return {"quality-v2": package, "sports-v2": tuple(reversed(package))}


def _attribution(*, actual="1" * 15):
    bk = [(0.60, 0.25, 0.15) for _ in range(15)]
    bk[1] = (0.20, 0.60, 0.20)
    bk[2] = (0.20, 0.60, 0.20)
    sports = list(bk)
    sports[0] = (0.70, 0.20, 0.10)
    sports[1] = (0.10, 0.70, 0.20)
    sports_events = tuple(
        SimpleNamespace(
            event_order=order,
            blend_weight=0.0 if order == 2 else 0.2,
            fallback_reason="missing" if order == 2 else None,
        )
        for order in range(15)
    )
    return build_hybrid_event_attribution(
        drawing_id=12077,
        drawing_number=4990,
        plan_id="plan",
        event_names=tuple(f"Home {order} — Away {order}" for order in range(15)),
        actual=actual,
        probability_models={"bk": bk, "sports_v2": sports},
        packages=_packages(),
        sports_events=sports_events,
        source_hashes={"final_input_sha256": "a" * 64},
    )


def test_hybrid_attribution_separates_probability_and_package_misses():
    report = _attribution()

    assert report["events"][0]["diagnosis"]["quality-v2-vs-bk"] == (
        "PACKAGE_ALIGNMENT_MISS"
    )
    assert report["events"][1]["diagnosis"]["quality-v2-vs-bk"] == (
        "PROBABILITY_RANKING_MISS"
    )
    assert report["events"][2]["diagnosis"]["quality-v2-vs-bk"] == (
        "JOINT_PROBABILITY_AND_PACKAGE_MISS"
    )
    assert report["events"][3]["diagnosis"]["quality-v2-vs-bk"] == (
        "NO_RANKING_OR_ALIGNMENT_MISS"
    )
    assert report["events"][0]["sports_v2_change"]["effect"] == (
        "HELPED_ACTUAL_PROBABILITY"
    )
    assert report["events"][1]["sports_v2_change"]["effect"] == (
        "HURT_ACTUAL_PROBABILITY"
    )
    assert report["events"][2]["sports_v2_change"]["effect"] == "FALLBACK"
    assert report["events"][1]["sports_v2_change"]["top_prediction_effect"] == (
        "RETAINED_TOP_MISS"
    )


def test_hybrid_attribution_reports_exposure_and_best_coupon_misses():
    report = _attribution()
    event = report["events"][0]["strategies"]["quality-v2"]

    assert event["actual_count"] == 1
    assert event["actual_share"] == 0.25
    assert event["actual_exposure_rank"] == 2
    assert event["actual_is_max_exposure"] is False
    assert report["summary"]["strategies"]["quality-v2"]["best_hits"] == 13


def test_hybrid_attribution_excludes_void_from_diagnosis():
    actual = list("1" * 15)
    actual[3] = "*"
    report = _attribution(actual="".join(actual))
    event = report["events"][3]

    assert event["excluded_as_void"] is True
    assert event["models"]["bk"]["actual_rank"] is None
    assert event["strategies"]["quality-v2"]["actual_share"] is None
    assert event["diagnosis"]["quality-v2-vs-bk"] == "VOID_EXCLUDED"
    assert report["summary"]["resolved_event_count"] == 14


def test_hybrid_attribution_writes_three_research_views(tmp_path):
    report = _attribution()

    paths = write_hybrid_event_attribution(report, output_dir=tmp_path)

    assert set(paths) == {"json", "csv", "markdown"}
    assert all(path.is_file() for path in paths.values())
    assert "Hybrid event attribution: 4990" in paths["markdown"].read_text()
    assert "event_name" in paths["csv"].read_text()
    assert "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE" in paths["json"].read_text()
