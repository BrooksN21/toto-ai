"""Synthetic whole-drawing protocol; never real training evidence."""

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from toto_ai.sports_stats import v3_probability as v3

_spec = importlib.util.spec_from_file_location(
    "f4_core_fixtures", Path(__file__).with_name("test_sports_v3_probability.py")
)
fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures)


def protocol(count=7):
    folds, labels = [], {}
    for draw in range(1, count + 1):
        rows = [fixtures.feature(draw, i, float(i % 3 - 1)) for i in range(15)]
        label = v3.seal(
            {
                "kind": "SPORTS_V3_F4_LABELS",
                "drawing_number": draw,
                "available_at": (
                    datetime.fromisoformat(rows[0]["kickoff"]) + timedelta(hours=3)
                ).isoformat(),
                "snapshot_sha256": "c" * 64,
                "events": [
                    {"event_id": r["event_id"], "event_order": i, "outcome": i % 3}
                    for i, r in enumerate(rows)
                ],
            }
        )
        raw = v3.canonical_json(label).encode()
        labels[draw] = raw
        v2 = v3.seal(
            {
                "model_version": "sports-analytics-v2-poisson-venue-shrunk-v1",
                "final_input_sha256": "a" * 64,
                "event_ids": [r["event_id"] for r in rows],
                "probabilities": [r["bk_probabilities"] for r in rows],
            }
        )
        folds.append(
            v3.seal(
                {
                    "kind": "SPORTS_V3_F4_FOLD_INPUT",
                    "drawing_number": draw,
                    "as_of": rows[0]["as_of"],
                    "final_input_sha256": "a" * 64,
                    "scheduler_plan_sha256": "e" * 64,
                    "drawing_fingerprint": "f" * 64,
                    "bank": 4980,
                    "stake": 30,
                    "features": rows,
                    "v2": v2,
                    "expected_label_file_sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        )
    receipt = v3.seal(
        {
            "kind": "SPORTS_V3_COMMON_SCOPE_RECEIPT",
            "domain": "SYNTHETIC_TEST_ONLY",
            "verified_feature_sha256s": [
                r["sha256"] for f in folds for r in f["features"]
            ],
            "review_evidence_sha256s": ["b" * 64],
        }
    )
    return folds, labels, receipt


def test_missing_real_scope_bridge_blocks_before_fit_labels_or_output(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, _, _ = protocol()

    def forbidden(_):
        pytest.fail("target labels must not be read without training authority")

    result = run_f4(
        folds,
        output_dir=tmp_path / "absent",
        load_labels=forbidden,
        training_domain="FROZEN_HISTORICAL_INPUT",
        scope_receipt=None,
        expected_scope_receipt_sha256=None,
    )
    assert result["status"] == "BLOCKED_MISSING_TRAINING_EVIDENCE"
    assert not (tmp_path / "absent").exists()


def test_predictions_persist_before_target_labels_and_train_whole_earlier_draws(
    tmp_path,
):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol()
    observed = []

    def load(fold):
        path = tmp_path / f"f4-{fold['drawing_number']}.prediction.json"
        frozen = json.loads(path.read_bytes())
        assert "actual" not in frozen and "labels" not in frozen
        for model in frozen["models"].values():
            assert all(d < fold["drawing_number"] for d in model["train_drawings"])
        observed.append(fold["drawing_number"])
        return labels[fold["drawing_number"]]

    result = run_f4(
        folds,
        output_dir=tmp_path,
        load_labels=load,
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    assert observed == list(range(1, 8))
    assert result["event_count"] == 105
    assert result["bootstrap"]["sample_count"] == 10_000
    assert result["status"] == "SYNTHETIC_SCREEN_ONLY"
    assert result["activation_allowed"] is False
    first = result["folds"][0]["prediction"]
    assert all(m["status"] == "COLD_START" for m in first["models"].values())
    fourth = result["folds"][3]["prediction"]
    assert all(m["train_drawings"] == [1, 2, 3] for m in fourth["models"].values())
    assert all(m["status"] == "TRAINED_EXPERIMENTAL" for m in fourth["models"].values())


def test_wrong_scope_receipt_and_incomplete_drawing_fail_closed(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol(1)
    kwargs = dict(
        output_dir=tmp_path,
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="scope receipt"):
        run_f4(folds, **kwargs)
    kwargs["expected_scope_receipt_sha256"] = receipt["sha256"]
    folds[0] = v3.seal({**folds[0], "features": folds[0]["features"][:-1]})
    with pytest.raises(ValueError, match="15"):
        run_f4(folds, **kwargs)


def test_future_available_drawing_is_excluded_whole_from_training(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol(4)
    changed = v3.seal(
        {**json.loads(labels[1]), "available_at": "2025-01-05T12:00:00+00:00"}
    )
    labels[1] = v3.canonical_json(changed).encode()
    folds[0] = v3.seal(
        {
            **folds[0],
            "expected_label_file_sha256": hashlib.sha256(labels[1]).hexdigest(),
        }
    )
    result = run_f4(
        folds,
        output_dir=tmp_path,
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    assert result["folds"][1]["prediction"]["models"]["A4"]["train_drawings"] == []
    assert result["folds"][3]["prediction"]["models"]["A4"]["train_drawings"] == [2, 3]
    assert result["gate_predicates"]["seven_folds_105_events"] is False


def test_f4_rejects_status_metrics_and_probability_tampering(tmp_path):
    from copy import deepcopy

    from toto_ai.sports_stats.v3_f4 import bytes_hash, run_f4
    from toto_ai.sports_stats.v3_f4_gate import build_f4_gate, validate_f4_gate

    folds, labels, receipt = protocol(1)
    result = run_f4(
        folds,
        output_dir=tmp_path,
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    gate = build_f4_gate(result)
    with pytest.raises(ValueError, match="screen not passed"):
        validate_f4_gate(gate, result["sha256"])
    changed = deepcopy(result)
    changed["metrics"]["A4"]["log_loss"] = 0.01
    changed["status"] = "PASS_RESEARCH_ONLY"
    with pytest.raises(ValueError, match="recomputation"):
        build_f4_gate(v3.seal(changed))
    changed = deepcopy(result)
    pred = changed["folds"][0]["prediction"]
    pred["events"][0]["A4"]["probabilities"] = [0.9, 0.05, 0.05]
    pred["events"][0]["A4"] = v3.seal(pred["events"][0]["A4"])
    changed["folds"][0]["prediction"] = v3.seal(pred)
    changed["folds"][0]["prediction_file_sha256"] = bytes_hash(v3.seal(pred))
    with pytest.raises(ValueError, match="recomputed V3"):
        build_f4_gate(v3.seal(changed))


def test_all_missing_rows_remain_exact_bk_and_report_zero_full_coverage(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol(1)
    rows = [
        v3.seal(
            {
                **r,
                "features": dict.fromkeys(v3.FEATURE_NAMES),
                "prior_counts": [0, 0],
                "scope_verified": False,
            }
        )
        for r in folds[0]["features"]
    ]
    folds[0] = v3.seal({**folds[0], "features": rows})
    result = run_f4(
        folds,
        output_dir=tmp_path,
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    assert result["coverage"] == 0
    assert result["gate_predicates"]["mandatory_missing_exact_bk"]
    assert result["subsets"]["missing_events"]["A4"]["event_count"] == 15
    assert result["subsets"]["covered_events"]["A4"]["event_count"] == 0


def test_full_protocol_hash_is_independent_of_output_directory(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol(4)
    kwargs = dict(
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    first = run_f4(folds, output_dir=tmp_path / "first" / "nested", **kwargs)
    second = run_f4(folds, output_dir=tmp_path / "second", **kwargs)
    assert first == second
    with pytest.raises(FileExistsError):
        run_f4(folds, output_dir=tmp_path / "second", **kwargs)


def test_target_feature_changes_cannot_change_its_training_transform(tmp_path):
    from toto_ai.sports_stats.v3_f4 import run_f4

    folds, labels, receipt = protocol(4)
    kwargs = dict(
        load_labels=lambda f: labels[f["drawing_number"]],
        training_domain="SYNTHETIC_TEST_ONLY",
        scope_receipt=receipt,
        expected_scope_receipt_sha256=receipt["sha256"],
    )
    first = run_f4(folds, output_dir=tmp_path / "first", **kwargs)
    rows = [
        v3.seal({**r, "features": {**r["features"], "difference_rolling_ppg": 1e9}})
        for r in folds[-1]["features"]
    ]
    folds[-1] = v3.seal({**folds[-1], "features": rows})
    receipt = v3.seal(
        {
            **receipt,
            "verified_feature_sha256s": [
                r["sha256"] for f in folds for r in f["features"]
            ],
        }
    )
    kwargs.update(
        scope_receipt=receipt, expected_scope_receipt_sha256=receipt["sha256"]
    )
    changed = run_f4(folds, output_dir=tmp_path / "changed", **kwargs)
    assert (
        first["folds"][-1]["prediction"]["models"]
        == changed["folds"][-1]["prediction"]["models"]
    )
