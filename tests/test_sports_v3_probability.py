"""Legitimate synthetic earlier drawings; no real outcomes or provider calls."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.sports_stats import v3_probability as v3


def feature(draw, order=0, signal=1.0):
    asof = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=draw)
    values = dict.fromkeys(v3.FEATURE_NAMES, 0.5)
    values["difference_rolling_ppg"] = signal
    return v3.seal(
        {
            "kind": "SPORTS_V3_PREDICTORS",
            "schema_version": 1,
            "drawing_number": draw,
            "event_order": order,
            "event_id": f"{draw}-{order}",
            "provider_fixture_id": f"fixture-{draw}-{order}",
            "home_team_id": "H",
            "away_team_id": "A",
            "as_of": asof.isoformat(),
            "kickoff": (asof + timedelta(hours=2)).isoformat(),
            "bk_captured_at": asof.isoformat(),
            "bk_input_sha256": "a" * 64,
            "bk_probabilities": [0.34, 0.32, 0.34],
            "bk_margin": 0.05,
            "features": values,
            "prior_counts": [10, 10],
            "exact_target": True,
            "scope_verified": True,
            "source_rejected": False,
            "source_hashes": ["b" * 64],
            "missing_reasons": [],
        }
    )


def training(draws=3):
    rows = []
    for draw in range(1, draws + 1):
        for order in range(15):
            signal = float(order % 3 - 1)
            row = feature(draw, order, signal)
            rows.append(
                {
                    "features": row,
                    "label": {
                        "drawing_number": draw,
                        "event_id": row["event_id"],
                        "outcome": order % 3,
                        "snapshot_sha256": "c" * 64,
                        "available_at": (
                            datetime.fromisoformat(row["kickoff"]) + timedelta(hours=3)
                        ).isoformat(),
                    },
                }
            )
    return rows


def fit(rows=None, variant="A5"):
    return v3.train_v3(
        training() if rows is None else rows,
        target_drawing=10,
        prediction_as_of=feature(10)["as_of"],
        variant=variant,
        training_domain="SYNTHETIC_TEST_ONLY",
    )


def test_real_nonzero_fit_serialization_inference_and_hashes():
    model = fit()
    assert model["status"] == "TRAINED_EXPERIMENTAL"
    assert any(abs(v) > 1e-6 for row in model["weights"] for v in row)
    assert model == fit(list(reversed(training())))
    restored = v3.load_model(v3.canonical_json(model))
    result = v3.infer_v3(restored, feature(10))
    assert result["status"] == "PREDICTED_EXPERIMENTAL"
    assert result["probabilities"] != feature(10)["bk_probabilities"]
    assert sum(result["probabilities"]) == pytest.approx(1.0, abs=1e-15)
    assert 0 < result["reliability"] <= 0.2
    assert (
        sum(
            abs(a - b)
            for a, b in zip(
                result["probabilities"], feature(10)["bk_probabilities"], strict=True
            )
        )
        <= 0.2
    )
    assert result["operator_compatible"] is False


def test_cold_start_and_untrusted_source_exact_bk():
    model = fit(training(2))
    assert model["status"] == "COLD_START"
    assert (
        v3.infer_v3(model, feature(10))["probabilities"]
        == feature(10)["bk_probabilities"]
    )
    model = fit()
    for change in (
        {"exact_target": False},
        {"source_rejected": True},
        {"scope_verified": False},
        {"prior_counts": [0, 0]},
    ):
        row = v3.seal({**feature(10), **change})
        result = v3.infer_v3(model, row)
        assert result["probabilities"] == row["bk_probabilities"]
        assert result["probability_sha256"] == v3.digest(row["bk_probabilities"])


def test_train_target_and_label_time_separation():
    rows = training()
    with pytest.raises(ValueError, match="training drawing"):
        v3.train_v3(rows, target_drawing=3, prediction_as_of=feature(10)["as_of"])
    rows[-1]["label"]["available_at"] = feature(10)["as_of"]
    with pytest.raises(ValueError, match="label availability"):
        fit(rows)
    with pytest.raises(ValueError, match="complete drawing"):
        fit(training()[:-1])


def test_train_only_transforms_and_current_bk_rebase():
    model = fit()
    original = deepcopy(model)
    row = feature(10, signal=1e6)
    row["features"]["home_rolling_ppg"] = None
    row = v3.seal(row)
    final = [0.15, 0.2, 0.65]
    result = v3.infer_v3(model, row, bk_probabilities=final, bk_input_sha256="d" * 64)
    assert model == original
    assert result["bk_probabilities"] == final
    assert result["bk_input_sha256"] == "d" * 64
    assert result["status"] == "PREDICTED_EXPERIMENTAL"
    assert (
        sum(abs(a - b) for a, b in zip(result["probabilities"], final, strict=True))
        <= 0.2
    )
    assert (
        v3.infer_v3(fit(variant="A2"), row)["probabilities"] == row["bk_probabilities"]
    )


def test_tampered_version_and_hash_fail_closed():
    model = fit()
    wrong = deepcopy(model)
    wrong["weights"][0][0] += 1
    assert v3.infer_v3(wrong, feature(10))["status"] == "BK_FALLBACK"
    with pytest.raises(ValueError):
        v3.load_model(v3.canonical_json(wrong))
    wrong = v3.seal(
        {**model, "model_version": "sports-analytics-v2-poisson-venue-shrunk-v1"}
    )
    assert (
        v3.infer_v3(wrong, feature(10))["probabilities"]
        == feature(10)["bk_probabilities"]
    )


def test_resealed_future_training_label_is_rejected_on_load_and_infer():
    model = fit(variant="A4")
    model["training_rows"][0]["label_available_at"] = "2099-01-01T00:00:00+00:00"
    model = v3.seal(model)
    with pytest.raises(ValueError):
        v3.load_model(v3.canonical_json(model))
    result = v3.infer_v3(model, feature(10))
    assert result["status"] == "BK_FALLBACK"
    assert result["probabilities"] == feature(10)["bk_probabilities"]


@pytest.mark.parametrize(
    "fault", ["future_label", "target_draw", "count", "eligible", "config", "domain"]
)
def test_rehashed_manifest_cannot_override_training_semantics(fault):
    model = fit()
    if fault == "future_label":
        model["training_rows"][0]["label_available_at"] = "2099-01-01T00:00:00+00:00"
    elif fault == "target_draw":
        model["training_rows"][0]["drawing_number"] = 10
    elif fault == "count":
        model["training_row_count"] += 1
    elif fault == "eligible":
        model["eligible_training_row_count"] = 0
    elif fault == "config":
        model["config"]["weight_cap"] = 0.9
    else:
        model["training_domain"] = "UNREVIEWED_NEW_DOMAIN"
    model["training_manifest_sha256"] = v3.digest(model["training_rows"])
    with pytest.raises(ValueError):
        v3.load_model(v3.canonical_json(v3.seal(model)))


@pytest.mark.parametrize("variant", ["A3", "A4"])
def test_draw_calibrator_is_fitted_only_from_earlier_labels_and_bounded(variant):
    model = fit(variant=variant)
    calibrator = model["draw_calibrator"]
    assert calibrator is not None
    assert calibrator["status"] == "EXPERIMENTAL_NOT_SCREENED"
    assert calibrator["feature_names"] == ["bk_margin", "bk_entropy", "reliability"]
    assert any(abs(v) > 1e-9 for v in calibrator["weights"])
    result = v3.infer_v3(model, feature(10))
    assert result["status"] == "PREDICTED_EXPERIMENTAL"
    assert abs(result["draw_logit_shift"]) <= result["reliability"] <= 0.2
    assert "actual" not in calibrator["feature_names"]
    assert fit(variant="A5")["draw_calibrator"] is None
