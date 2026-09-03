import hashlib
import json
from pathlib import Path

from toto_ai.sports_stats.v3_attribution import (
    build_v3_attribution_aggregate,
    write_v3_attribution_aggregate,
)


def _write_attribution(path: Path, *, drawing: int, sports_helped: bool) -> Path:
    events = []
    for order in range(15):
        actual = "1" if order % 2 == 0 else "2"
        bk = {"1": 0.5, "X": 0.3, "2": 0.2}
        sports = (
            {"1": 0.4, "X": 0.2, "2": 0.4}
            if sports_helped
            else {"1": 0.6, "X": 0.25, "2": 0.15}
        )
        events.append(
            {
                "actual_outcome": actual,
                "event_order": order,
                "excluded_as_void": False,
                "models": {
                    "bk": {
                        "probabilities": bk,
                        "top_correct": actual == "1",
                    },
                    "sports_v2": {
                        "probabilities": sports,
                        "top_correct": actual in (
                            ("1", "2") if sports_helped else ("1",)
                        ),
                    },
                },
                "sports_v2_change": {
                    "covered": order != 14,
                    "effect": (
                        "HELPED_ACTUAL_PROBABILITY"
                        if sports_helped
                        else "HURT_ACTUAL_PROBABILITY"
                    ),
                    "top_prediction_effect": (
                        "CORRECTED_TOP_MISS"
                        if sports_helped and actual == "2"
                        else "RETAINED_CORRECT_TOP"
                        if actual == "1"
                        else "RETAINED_TOP_MISS"
                    ),
                },
                "diagnosis": {
                    "quality-v2-vs-bk": "NO_RANKING_OR_ALIGNMENT_MISS",
                    "sports-v2-vs-sports-model": "PROBABILITY_RANKING_MISS",
                },
                "strategies": {
                    strategy: {
                        "actual_share": 0.25,
                        "zero_actual_exposure": False,
                        "fixed_wrong": False,
                        "best_coupon_universal_miss": order == 14,
                    }
                    for strategy in (
                        "quality-v2",
                        "sports-v2",
                        "quality-v3",
                        "robust",
                    )
                },
            }
        )
    payload = {
        "artifact_class": "HYBRID_EVENT_LEVEL_ATTRIBUTION",
        "status": "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE",
        "drawing_number": drawing,
        "events": events,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v3_attribution_aggregate_is_hash_bound_and_idempotent(tmp_path):
    first = _write_attribution(
        tmp_path / "first.json", drawing=4990, sports_helped=True
    )
    second = _write_attribution(
        tmp_path / "second.json", drawing=4991, sports_helped=False
    )

    report = build_v3_attribution_aggregate((second, first))

    assert report["drawings"] == [4990, 4991]
    assert report["resolved_event_count"] == 30
    assert report["sports_v2"]["covered_event_count"] == 28
    assert report["sports_v2"]["effect_counts"] == {
        "HELPED_ACTUAL_PROBABILITY": 15,
        "HURT_ACTUAL_PROBABILITY": 15,
    }
    assert report["sports_v2"]["top_transition_counts"]["CORRECTED_TOP_MISS"] == 7
    assert report["strategy_exposure"]["quality-v2"][
        "best_coupon_universal_miss_count"
    ] == 2
    assert report["model_metrics"]["bk"]["event_count"] == 30
    assert report["operator_compatible"] is False
    assert report["automatic_wagering"] is False
    unsigned = dict(report)
    digest = unsigned.pop("report_sha256")
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert digest == hashlib.sha256(encoded).hexdigest()

    json_path, markdown_path = write_v3_attribution_aggregate(
        report, output_dir=tmp_path / "output"
    )
    assert json.loads(json_path.read_text()) == report
    assert "NOT ACTIVATED" in markdown_path.read_text()
    assert write_v3_attribution_aggregate(
        report, output_dir=tmp_path / "output"
    ) == (json_path, markdown_path)
