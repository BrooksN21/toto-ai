"""Synthetic contract fixtures, never evidence of a real Sports v3 fit."""

from copy import deepcopy

import pytest

from toto_ai.research.sports_v3_retrospective_fit import DOMAIN, prepare_fit
from toto_ai.sports_stats.v3_probability import FEATURE_NAMES, seal


def row(draw, order):
    day = draw - 4998
    return seal(
        {
            "kind": "RETROSPECTIVE_SPORTS_FEATURES_V1",
            "drawing_number": draw,
            "event_order": order,
            "event_id": f"fixture-{draw}-{order}",
            "decision_cutoff": f"2026-09-{day:02}T10:00:00Z",
            "kickoff": f"2026-09-{day:02}T12:00:00Z",
            "fetched_at": "2026-09-15T18:30:00Z",
            "feature_available_at": None,
            "bk_fetched_at": "2026-09-15T18:30:00Z",
            "bk_quote_available_at": None,
            "bk_probabilities": [0.4, 0.3, 0.3],
            "bk_margin": None,
            "bk_input_sha256": "b" * 64,
            "source_hashes": ["a" * 64],
            "features": {
                n: (float(order) if n.endswith("rest_days") else None)
                for n in FEATURE_NAMES
            },
            "prior_counts": [5, 5],
            "identity_status": "INDEPENDENT_ENTITY_LINEAGE_REVIEWED",
            "taxonomy": {"gender": None, "age_group": None, "squad_type": None},
            "history": [
                {
                    "fixture_id": f"past-{draw}-{order}",
                    "kickoff": "2026-08-30T10:00:00Z",
                    "completed_by": "2026-08-30T13:00:00Z",
                    "completion_basis": "TERMINAL_OBSERVATION",
                    "source_sha256": "a" * 64,
                }
            ],
        }
    )


def inputs():
    records = []
    for draw in range(4999, 5002):
        for order in range(15):
            r = row(draw, order)
            records.append(
                {
                    "features": r,
                    "label": seal(
                        {
                            "drawing_number": draw,
                            "event_id": r["event_id"],
                            "outcome": order % 3,
                            "completed_by": r["kickoff"].replace("12:", "15:"),
                            "completion_basis": "EXPLICIT_FINISH",
                            "available_at": None,
                            "fetched_at": r["fetched_at"],
                            "source_sha256": "c" * 64,
                        }
                    ),
                }
            )
    targets = [row(5002, n) for n in range(15)]
    return records, targets


def prepare(records=None, targets=None, **kwargs):
    r, t = inputs()
    records = r if records is None else records
    targets = t if targets is None else targets
    # Trusted review input deliberately supplied separately from self-reported rows.
    reviewed = {x["features"]["sha256"] for x in records} | {
        x["sha256"] for x in targets
    }
    return prepare_fit(
        records,
        targets,
        prediction_as_of="2026-09-04T10:00:00Z",
        target_drawing=5002,
        independently_reviewed_hashes=reviewed,
        **kwargs,
    )


def test_late_fetch_unknown_asof_is_explicit_not_backdated():
    records, _ = inputs()
    before = deepcopy(records)
    result = prepare(records)
    assert result["domain"] == DOMAIN
    assert result["evidence_grade"] == "UNVERIFIED_ASOF_SENSITIVITY"
    assert result["training_row_count"] == 45
    assert result["eligible_training_row_count"] == 45
    assert result["training_sha256"]
    assert records == before
    assert not result["operator_compatible"]
    assert not result["fit_completed"]
    assert result["status"] == "FIT_READY"


def test_training_only_transform():
    records, targets = inputs()
    first = prepare(records, targets)
    altered = deepcopy(targets)
    for r in altered:
        r["features"]["home_rest_days"] = 100000
        r.update(seal(r))
    second = prepare(records, altered)
    assert first["transform"] == second["transform"]
    assert first["training_sha256"] == second["training_sha256"]
    assert first["heldout_features_sha256"] != second["heldout_features_sha256"]


def test_heldout_training_rejected():
    records, _ = inputs()
    records[0]["features"] = row(5002, 0)
    with pytest.raises(ValueError, match="precede"):
        prepare(records)


def test_hash_tamper():
    records, _ = inputs()
    records[0]["features"]["features"]["home_rest_days"] = 99
    with pytest.raises(ValueError, match="hash"):
        prepare(records)


def test_future_completion_rejected():
    records, _ = inputs()
    r = records[0]["features"]
    r["history"][0]["completed_by"] = "2026-09-02T10:00:00Z"
    records[0]["features"] = seal(r)
    with pytest.raises(ValueError, match="history completion"):
        prepare(records)


def test_target_in_history_rejected_before_numerics():
    records, _ = inputs()
    r = records[0]["features"]
    r["history"][0]["fixture_id"] = r["event_id"]
    records[0]["features"] = seal(r)
    with pytest.raises(ValueError, match="target in history"):
        prepare(records)


def test_training_label_after_prediction_rejected():
    records, _ = inputs()
    records[0]["label"]["completed_by"] = "2026-09-04T11:00:00Z"
    records[0]["label"] = seal(records[0]["label"])
    with pytest.raises(ValueError, match="training label completion"):
        prepare(records)


def test_duplicate_and_incomplete_groups_rejected():
    records, _ = inputs()
    with pytest.raises(ValueError, match="complete drawing"):
        prepare(records[:-1])
    records[-1] = deepcopy(records[-2])
    with pytest.raises(ValueError, match="complete drawing"):
        prepare(records)


def test_unreviewed_hash_not_self_approved():
    records, targets = inputs()
    with pytest.raises(ValueError, match="independent"):
        prepare_fit(
            records,
            targets,
            prediction_as_of="2026-09-04T10:00:00Z",
            target_drawing=5002,
            independently_reviewed_hashes=set(),
        )


def test_label_not_allowed_in_feature_row():
    records, _ = inputs()
    records[0]["features"] = seal({**records[0]["features"], "outcome": 1})
    with pytest.raises(ValueError, match="feature field"):
        prepare(records)


def test_cold_start_not_fit_success():
    records, _ = inputs()
    assert prepare(records[:30])["status"] == "COLD_START"


def test_canonical_fixture_cannot_be_in_train_and_heldout():
    records, targets = inputs()
    targets[0]["event_id"] = records[0]["features"]["event_id"]
    targets[0] = seal(targets[0])
    with pytest.raises(ValueError, match="canonical fixture overlap"):
        prepare(records, targets)


def test_unknown_identity_zero_weight_not_fake_scope():
    records, _ = inputs()
    for record in records:
        record["features"]["identity_status"] = "UNKNOWN"
        record["features"] = seal(record["features"])
    result = prepare(records)
    assert result["eligible_training_row_count"] == 0
    assert result["status"] == "COLD_START"
    assert result["transform"] == {}


def test_late_feature_capture_not_historical_availability_proof():
    records, targets = inputs()
    for record in records:
        r = record["features"]
        r["bk_quote_available_at"] = r["decision_cutoff"]
        record["features"] = seal(r)
        record["label"]["available_at"] = record["label"]["completed_by"]
        record["label"] = seal(record["label"])
    for n, r in enumerate(targets):
        r["bk_quote_available_at"] = r["decision_cutoff"]
        targets[n] = seal(r)
    assert prepare(records, targets)["evidence_grade"] == "UNVERIFIED_ASOF_SENSITIVITY"


@pytest.mark.parametrize(
    "name,value", [("home_rest_days", float("inf")), ("result", 1)]
)
def test_numeric_schema_rejects_leak_or_nonfinite(name, value):
    records, _ = inputs()
    r = records[0]["features"]
    r["features"][name] = value
    with pytest.raises(ValueError):
        records[0]["features"] = seal(r)
        prepare(records)


def fit_case(records=None, targets=None):
    from toto_ai.research.sports_v3_retrospective_fit import fit_research

    r, t = inputs()
    records = r if records is None else records
    targets = t if targets is None else targets
    reviewed = {x["features"]["sha256"] for x in records} | {
        x["sha256"] for x in targets
    }
    return fit_research(
        records,
        targets,
        target_drawing=5002,
        prediction_as_of="2026-09-04T10:00:00Z",
        independently_reviewed_hashes=reviewed,
    )


def test_same_kernel_real_weights_on_synthetic_contract_fixture():
    model = fit_case()
    assert model["kind"] == "RETROSPECTIVE_SPORTS_V3_MODEL_V1"
    assert model["status"] == "TRAINED_EXPERIMENTAL"
    assert model["fit_completed"]
    assert any(abs(w) > 1e-8 for row in model["weights"] for w in row)
    assert not model["operator_compatible"]
    assert model["training_drawings"] == [4999, 5000, 5001]
    assert model["fitted_at"] > model["prediction_as_of"]  # Never backdated.


def test_freeze_predictions_and_metrics_separate_from_training():
    from toto_ai.research.sports_v3_retrospective_fit import (
        freeze_predictions,
        score_predictions,
    )

    _, targets = inputs()
    model = fit_case()
    predictions = freeze_predictions(model, targets)
    assert predictions["model_sha256"] == model["sha256"]
    assert len(predictions["rows"]) == 15
    assert all(sum(r["probabilities"]) == pytest.approx(1) for r in predictions["rows"])
    assert all(
        sum(
            abs(p - q)
            for p, q in zip(r["probabilities"], r["bk_probabilities"], strict=True)
        )
        <= 0.2
        for r in predictions["rows"]
    )
    frozen_hash = predictions["sha256"]
    labels = [
        seal(
            {
                "drawing_number": 5002,
                "event_id": r["event_id"],
                "outcome": n % 3,
                "source_sha256": "e" * 64,
            }
        )
        for n, r in enumerate(targets)
    ]
    result = score_predictions(predictions, labels)
    assert result["prediction_sha256"] == frozen_hash
    assert result["event_count"] == 15
    assert result["log_loss"] > 0 and result["brier"] >= 0
    assert not result["blind_holdout"]
    assert predictions["sha256"] == frozen_hash


def test_frozen_model_rejects_swapped_heldout_features():
    from toto_ai.research.sports_v3_retrospective_fit import freeze_predictions

    _, targets = inputs()
    model = fit_case()
    targets[0]["features"]["home_rest_days"] = 900
    targets[0] = seal(targets[0])
    with pytest.raises(ValueError, match="heldout.*binding"):
        freeze_predictions(model, targets)


def test_training_weights_do_not_depend_on_heldout_values():
    _, targets = inputs()
    model = fit_case()
    for n, r in enumerate(targets):
        r["features"]["home_rest_days"] = 1000000
        targets[n] = seal(r)
    other = fit_case(targets=targets)
    assert model["weights"] == other["weights"]
    assert model["transform"] == other["transform"]


def test_native_rejects_research_model_even_if_trained():
    from toto_ai.sports_stats.v3_probability import validate_model

    with pytest.raises(ValueError):
        validate_model(fit_case())


def test_future_row_label_does_not_enter_training_api():
    r, t = inputs()
    t[0] = seal({**t[0], "label": 2})
    with pytest.raises(ValueError, match="feature field"):
        fit_case(r, t)


def test_sports_weight_summary_distinguishes_missingness_and_intercept():
    model = fit_case()
    summary = model["sports_signal_summary"]
    assert summary["nonzero_sports_numeric_observation_rows"] == 42
    assert summary["observed_sports_feature_names"]
    assert summary["missing_sports_cells"] > 0
    assert summary["active_numeric_sports_coefficient_count"] > 0
    assert "active_missing_indicator_coefficient_count" in summary
    assert "intercept_coefficients" in summary
    assert not model["sports_fully_integrated"]


def test_partial_training_groups_require_exact_exclusions_and_real_minimum():
    from toto_ai.research.sports_v3_retrospective_fit import prepare_fit

    records, old_targets = inputs()
    for r in old_targets:
        records.append(
            {
                "features": r,
                "label": seal(
                    {
                        "drawing_number": 5002,
                        "event_id": r["event_id"],
                        "outcome": 1,
                        "completed_by": "2026-09-04T15:00:00Z",
                        "completion_basis": "EXPLICIT_FINISH",
                        "available_at": None,
                        "fetched_at": r["fetched_at"],
                        "source_sha256": "c" * 64,
                    }
                ),
            }
        )
    removed = [records.pop(n) for n in [59, 58, 57, 56, 55, 54, 53]]
    exclusions = [
        {
            "drawing_number": r["features"]["drawing_number"],
            "event_order": r["features"]["event_order"],
            "reason": "NO_VERIFIED_KICKOFF_OR_PROVIDER_ID",
            "source_sha256": "d" * 64,
        }
        for r in removed
    ]
    targets = [row(5003, n) for n in range(15)]
    reviewed = {r["features"]["sha256"] for r in records} | {
        r["sha256"] for r in targets
    }
    options = dict(
        target_drawing=5003,
        prediction_as_of="2026-09-05T10:00:00Z",
        independently_reviewed_hashes=reviewed,
    )
    with pytest.raises(ValueError, match="complete drawing"):
        prepare_fit(records, targets, **options)
    result = prepare_fit(records, targets, training_exclusions=exclusions, **options)
    assert result["status"] == "FIT_READY"
    assert result["training_row_count"] == 53
    assert result["training_roster_denominator"] == 60
    assert result["excluded_training_row_count"] == 7
    with pytest.raises(ValueError, match="exclusion"):
        prepare_fit(
            records, targets, training_exclusions=exclusions + exclusions[:1], **options
        )


def test_native_a5_and_research_same_numeric_coefficients():
    import runpy
    from pathlib import Path

    import numpy as np

    from toto_ai.research.sports_v3_retrospective_fit import (
        fit_research,
        freeze_predictions,
    )
    from toto_ai.sports_stats import v3_probability as native

    fixture = runpy.run_path(
        str(Path(__file__).with_name("test_sports_v3_probability.py"))
    )
    original = fixture["training"]()
    expected = fixture["fit"]()

    def adapt(r):
        return seal(
            {
                **{
                    k: r[k]
                    for k in [
                        "drawing_number",
                        "event_order",
                        "event_id",
                        "kickoff",
                        "bk_probabilities",
                        "bk_margin",
                        "bk_input_sha256",
                        "source_hashes",
                        "features",
                        "prior_counts",
                    ]
                },
                "kind": "RETROSPECTIVE_SPORTS_FEATURES_V1",
                "decision_cutoff": r["as_of"],
                "fetched_at": "2026-09-15T12:00:00Z",
                "feature_available_at": None,
                "bk_fetched_at": r["bk_captured_at"],
                "bk_quote_available_at": r["bk_captured_at"],
                "identity_status": "INDEPENDENT_ENTITY_LINEAGE_REVIEWED",
                "taxonomy": {"gender": None, "age_group": None, "squad_type": None},
                "history": [],
            }
        )

    records = []
    for r in original:
        f = adapt(r["features"])
        lab = r["label"]
        records.append(
            {
                "features": f,
                "label": seal(
                    {
                        "drawing_number": lab["drawing_number"],
                        "event_id": lab["event_id"],
                        "outcome": lab["outcome"],
                        "source_sha256": lab["snapshot_sha256"],
                        "available_at": lab["available_at"],
                        "completed_by": lab["available_at"],
                        "completion_basis": "TERMINAL_OBSERVATION",
                        "fetched_at": "2026-09-15T12:00:00Z",
                    }
                ),
            }
        )
    targets = [adapt(fixture["feature"](10, n)) for n in range(15)]
    reviewed = {r["features"]["sha256"] for r in records} | {
        r["sha256"] for r in targets
    }
    actual = fit_research(
        records,
        targets,
        target_drawing=10,
        prediction_as_of=targets[0]["decision_cutoff"],
        independently_reviewed_hashes=reviewed,
    )
    assert actual["transform"] == expected["transform"]
    np.testing.assert_array_equal(actual["weights"], expected["weights"])
    prediction = freeze_predictions(actual, targets)
    np.testing.assert_array_equal(
        prediction["rows"][0]["probabilities"],
        native.infer_v3(expected, fixture["feature"](10))["probabilities"],
    )


def test_fit_can_precede_reviewed_evaluation_matrix_without_using_labels():
    from toto_ai.research.sports_v3_retrospective_fit import (
        fit_research,
        freeze_predictions,
    )

    records, targets = inputs()
    reviewed = {r["features"]["sha256"] for r in records}
    model = fit_research(
        records,
        [],
        target_drawing=5002,
        prediction_as_of="2026-09-04T10:00:00Z",
        independently_reviewed_hashes=reviewed,
        heldout_pending=True,
    )
    assert model["fit_completed"]
    with pytest.raises(ValueError, match="independent"):
        freeze_predictions(model, targets)
    frozen = freeze_predictions(
        model, targets, independently_reviewed_hashes={r["sha256"] for r in targets}
    )
    assert len(frozen["rows"]) == 15
    targets[0]["event_id"] = records[0]["features"]["event_id"]
    targets[0] = seal(targets[0])
    with pytest.raises(ValueError, match="overlap"):
        freeze_predictions(
            model, targets, independently_reviewed_hashes={r["sha256"] for r in targets}
        )
