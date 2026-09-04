import csv
import hashlib
import io
import json
import math
from pathlib import Path

import pytest

from toto_ai.sports_stats.v3_attribution import (
    build_v3_attribution_aggregate,
    write_v3_attribution_aggregate,
)


def _write_attribution(
    path: Path,
    *,
    drawing: int,
    outcomes: tuple[str, ...] = ("1", "X", "2"),
    sports_helped: bool = True,
    outcome_metadata_override: bool = False,
    schema_version: int = 1,
) -> Path:
    events = []
    for order in range(15):
        actual = outcomes[order % len(outcomes)]
        bk = {"1": 0.6, "X": 0.3, "2": 0.1}
        sports = (
            {"1": 0.4, "X": 0.2, "2": 0.4}
            if sports_helped
            else {"1": 0.7, "X": 0.2, "2": 0.1}
        )
        events.append(
            {
                "actual_outcome": actual,
                "event_order": order,
                "position": order + 1,
                "event_name": f"Home {order} — Away {order}",
                "excluded_as_void": False,
                "models": {
                    "bk": {
                        "probabilities": bk,
                        "actual_probability": -1
                        if outcome_metadata_override
                        else bk[actual],
                        "actual_rank": 99 if outcome_metadata_override else None,
                        "top_correct": outcome_metadata_override,
                    },
                    "sports_v2": {
                        "probabilities": sports,
                        "actual_probability": (
                            -1 if outcome_metadata_override else sports[actual]
                        ),
                        "actual_rank": 99 if outcome_metadata_override else None,
                        "top_correct": outcome_metadata_override,
                    },
                },
                "sports_v2_change": {
                    "covered": order != 14,
                    "effect": (
                        "HELPED_ACTUAL_PROBABILITY"
                        if sports_helped
                        else "HURT_ACTUAL_PROBABILITY"
                    ),
                    "fallback_reason": None if order != 14 else "history_missing",
                    "top_prediction_effect": "RETAINED_TOP_MISS",
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
    final_input_sha256 = hashlib.sha256(f"final-{drawing}".encode()).hexdigest()
    payload = {
        "schema_version": schema_version,
        "artifact_class": "HYBRID_EVENT_LEVEL_ATTRIBUTION",
        "status": "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE",
        "drawing_id": drawing + 10000,
        "drawing_number": drawing,
        "plan_id": f"plan-{drawing}",
        "source_hashes": {"final_input_sha256": final_input_sha256},
        "events": events,
    }
    payload["report_sha256"] = _attribution_hash(
        payload, ensure_ascii=schema_version == 1
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _attribution_hash(payload: dict, *, ensure_ascii: bool) -> str:
    unsigned = dict(payload)
    unsigned.pop("report_sha256", None)
    encoded = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_final_input(
    path: Path, *, drawing: int, missing_league: bool = False
) -> Path:
    snapshot_sha256 = hashlib.sha256(f"final-{drawing}".encode()).hexdigest()
    events = [
        {
            "order": order,
            "name": f"Home {order} — Away {order}",
            "championship": None if missing_league else f"League {order % 2}",
        }
        for order in range(15)
    ]
    payload = {
        "schema_version": 1,
        "snapshot_sha256": snapshot_sha256,
        "drawing_id": drawing + 10000,
        "drawing_number": drawing,
        "plan_id": f"plan-{drawing}",
        "payload": {
            "data": {
                "id": drawing + 10000,
                "number": drawing,
                "events": events,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _segment(report: dict, dimension: str, key: str) -> dict:
    return next(
        segment
        for segment in report["segments"][dimension]["segments"]
        if segment["key"] == key
    )


def test_v3_attribution_metrics_calibration_and_three_views_are_correct(tmp_path):
    attribution = _write_attribution(tmp_path / "attribution.json", drawing=4990)
    final_input = _write_final_input(tmp_path / "final-input.json", drawing=4990)

    report = build_v3_attribution_aggregate(
        (attribution,), final_input_paths=(final_input,)
    )

    bk = report["model_metrics"]["bk"]
    assert report["schema_version"] == 2
    assert report["event_count"] == report["resolved_event_count"] == 15
    assert bk["top_accuracy"] == pytest.approx(1 / 3)
    assert bk["brier_score"] == pytest.approx((0.26 + 0.86 + 1.26) / 3)
    assert bk["log_loss"] == pytest.approx(
        (-math.log(0.6) - math.log(0.3) - math.log(0.1)) / 3
    )
    per_outcome = bk["per_actual_outcome"]["1"]
    assert per_outcome["event_count"] == 5
    assert per_outcome["top_correct_count"] == 5
    assert per_outcome["top_accuracy"] == 1.0
    assert per_outcome["brier_score"] == pytest.approx(0.26)
    assert per_outcome["log_loss"] == pytest.approx(-math.log(0.6))
    calibration = bk["calibration"]
    assert calibration["ece"] == pytest.approx(abs(0.6 - 1 / 3))
    occupied = [row for row in calibration["bins"] if row["event_count"]]
    assert len(occupied) == 1
    assert occupied[0]["key"] == "[0.6,0.7)"
    assert occupied[0]["event_count"] == 15
    assert occupied[0]["average_confidence"] == pytest.approx(0.6)
    assert occupied[0]["accuracy"] == pytest.approx(1 / 3)
    assert occupied[0]["absolute_gap"] == pytest.approx(abs(0.6 - 1 / 3))
    assert occupied[0]["ece_contribution"] == pytest.approx(abs(0.6 - 1 / 3))
    assert report["league_coverage"]["mapped_event_count"] == 15
    assert report["sports_v2"]["covered_event_count"] == 14
    assert report["sports_v2"]["fallback_event_count"] == 1

    json_path, csv_path, markdown_path = write_v3_attribution_aggregate(
        report, output_dir=tmp_path / "output"
    )
    assert json.loads(json_path.read_text()) == report
    csv_rows = list(csv.DictReader(io.StringIO(csv_path.read_text())))
    assert len(csv_rows) == 15
    assert {row["report_sha256"] for row in csv_rows} == {report["report_sha256"]}
    markdown = markdown_path.read_text()
    assert report["report_sha256"] in markdown
    assert "Home 14 — Away 14" in markdown
    assert write_v3_attribution_aggregate(report, output_dir=tmp_path / "output") == (
        json_path,
        csv_path,
        markdown_path,
    )


def test_v3_attribution_hash_is_deterministic_for_input_order(tmp_path):
    first = _write_attribution(tmp_path / "first.json", drawing=4990)
    second = _write_attribution(tmp_path / "second.json", drawing=4991)
    first_final = _write_final_input(tmp_path / "first-final.json", drawing=4990)
    second_final = _write_final_input(tmp_path / "second-final.json", drawing=4991)

    forward = build_v3_attribution_aggregate(
        (first, second), final_input_paths=(first_final, second_final)
    )
    reverse = build_v3_attribution_aggregate(
        (second, first), final_input_paths=(second_final, first_final)
    )

    assert reverse == forward
    unsigned = dict(forward)
    digest = unsigned.pop("report_sha256")
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert digest == hashlib.sha256(encoded).hexdigest()


def test_v3_attribution_emits_empty_and_missing_segments(tmp_path):
    attribution = _write_attribution(
        tmp_path / "attribution.json", drawing=4990, outcomes=("1", "2")
    )

    report = build_v3_attribution_aggregate((attribution,))

    assert report["model_metrics"]["bk"]["per_actual_outcome"]["X"] == {
        "event_count": 0,
        "status": "EMPTY",
    }
    assert _segment(report, "actual_draw", "DRAW") == {
        "event_count": 0,
        "key": "DRAW",
        "status": "EMPTY",
    }
    assert report["league_coverage"] == {
        "coverage_rate": 0.0,
        "mapped_event_count": 0,
        "missing_event_count": 15,
        "missing_reason_counts": {"FINAL_INPUT_NOT_PROVIDED": 15},
    }
    assert _segment(report, "league", "MISSING")["event_count"] == 15


def test_v3_attribution_does_not_trust_outcome_derived_probability_metadata(
    tmp_path,
):
    clean = _write_attribution(tmp_path / "clean.json", drawing=4990)
    tainted = _write_attribution(
        tmp_path / "tainted.json",
        drawing=4991,
        outcome_metadata_override=True,
    )

    clean_report = build_v3_attribution_aggregate((clean,))
    tainted_report = build_v3_attribution_aggregate((tainted,))

    clean_event = clean_report["events"][0]
    tainted_event = tainted_report["events"][0]
    assert tainted_event["models"] == clean_event["models"]
    assert tainted_event["pre_draw"] == clean_event["pre_draw"]
    assert tainted_report["model_metrics"] == clean_report["model_metrics"]


def test_v3_attribution_verifies_versioned_unicode_hashes_and_rejects_tampering(
    tmp_path,
):
    legacy = _write_attribution(tmp_path / "legacy.json", drawing=4990)
    current = _write_attribution(
        tmp_path / "current.json", drawing=4991, schema_version=2
    )

    report = build_v3_attribution_aggregate((current, legacy))

    assert report["drawings"] == [4990, 4991]
    tampered = json.loads(legacy.read_text())
    tampered["events"][0]["event_name"] = "Tampered — Event"
    legacy.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="attribution report hash mismatch"):
        build_v3_attribution_aggregate((legacy,))
