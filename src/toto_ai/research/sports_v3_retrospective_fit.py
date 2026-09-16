"""Inactive retrospective A5 input preparation; never a production admission bypass.

Uses the shared, equivalence-tested native A5 numerical kernel and train-only
transform. The research admission and model domain stay distinct from production.
No synthetic data are constructed here; tests use explicitly synthetic fixtures.

independently_reviewed_hashes is a trusted reviewer input, NOT a property inferred
from a self-sealed dataset. Hashes bind bytes; they do not establish identity.
"""

from __future__ import annotations

import math
from collections import defaultdict

from toto_ai.sports_stats.v3_probability import (
    FEATURE_NAMES,
    _bk,
    _check,
    _hash,
    _sealed,
    _time,
    _transform,
    digest,
    seal,
)

DOMAIN = "RETROSPECTIVE_SPORTS_V3_RESEARCH_V1"
ROW_FIELDS = {
    "kind",
    "sha256",
    "drawing_number",
    "event_order",
    "event_id",
    "decision_cutoff",
    "kickoff",
    "fetched_at",
    "feature_available_at",
    "bk_fetched_at",
    "bk_quote_available_at",
    "bk_probabilities",
    "bk_margin",
    "bk_input_sha256",
    "source_hashes",
    "features",
    "prior_counts",
    "identity_status",
    "taxonomy",
    "history",
}
COMPLETION_BASES = {"EXPLICIT_FINISH", "TERMINAL_OBSERVATION"}


def _validate_row(row, reviewed):
    _sealed(row)
    _check(set(row) == ROW_FIELDS, "feature field allowlist")
    _check(row["kind"] == "RETROSPECTIVE_SPORTS_FEATURES_V1", "research feature kind")
    _check(row["sha256"] in reviewed, "independent feature/identity review required")
    _check(type(row["drawing_number"]) is int, "drawing identity")
    _check(
        type(row["event_order"]) is int and 0 <= row["event_order"] < 15, "event order"
    )
    _check(
        isinstance(row["event_id"], str) and bool(row["event_id"]),
        "canonical fixture ID",
    )
    cutoff, kickoff = _time(row["decision_cutoff"]), _time(row["kickoff"])
    _check(cutoff < kickoff, "feature decision before kickoff")
    _time(row["fetched_at"])
    _time(row["bk_fetched_at"])
    available = row["feature_available_at"]
    if available is not None:
        _check(_time(available) <= cutoff, "known post-decision features")
        _check(_time(available) <= _time(row["fetched_at"]), "features after fetch")
    quote = row["bk_quote_available_at"]
    if quote is not None:
        _check(_time(quote) <= _time(row["bk_fetched_at"]), "quote after fetch")
        _check(_time(quote) <= cutoff, "known post-decision quote")
    _bk(row["bk_probabilities"])
    _hash(row["bk_input_sha256"])
    _check(bool(row["source_hashes"]), "source provenance required")
    for value in row["source_hashes"]:
        _hash(value)
    _check(set(row["features"]) == set(FEATURE_NAMES), "predictor allowlist")
    _check(
        all(
            v is None or (type(v) in (int, float) and math.isfinite(v))
            for v in row["features"].values()
        ),
        "nonfinite predictor",
    )
    margin = row["bk_margin"]
    _check(
        margin is None or (type(margin) in (int, float) and math.isfinite(margin)),
        "nonfinite margin",
    )
    _check(
        len(row["prior_counts"]) == 2
        and all(type(n) is int and n >= 0 for n in row["prior_counts"]),
        "prior counts",
    )
    _check(
        set(row["taxonomy"]) == {"gender", "age_group", "squad_type"}, "taxonomy schema"
    )
    _check(
        all(v is None or isinstance(v, str) for v in row["taxonomy"].values()),
        "taxonomy values",
    )
    _check(
        row["identity_status"] in {"INDEPENDENT_ENTITY_LINEAGE_REVIEWED", "UNKNOWN"},
        "identity status",
    )
    seen = set()
    for past in row["history"]:
        _check(past["fixture_id"] != row["event_id"], "target in history")
        _check(past["fixture_id"] not in seen, "duplicate history fixture")
        seen.add(past["fixture_id"])
        _check(
            past["completion_basis"] in COMPLETION_BASES, "unsupported completion basis"
        )
        _check(
            _time(past["kickoff"]) < _time(past["completed_by"]) < cutoff,
            "history completion must precede decision",
        )
        _check(
            _time(past["completed_by"]) <= _time(row["fetched_at"]),
            "completion after observation",
        )
        _check(past["source_sha256"] in row["source_hashes"], "history source binding")
    # No fake scope_verified flag: alternate research identity review is explicit.
    observed = sum(row["features"][name] is not None for name in FEATURE_NAMES)
    eligible = row["identity_status"] == "INDEPENDENT_ENTITY_LINEAGE_REVIEWED"
    coverage = observed / len(FEATURE_NAMES)
    weight = 0.2 * min(1.0, min(row["prior_counts"]) / 10) * coverage
    return weight if eligible else 0.0


def _complete_groups(rows, exclusions=()):
    groups = defaultdict(list)
    excluded = defaultdict(set)
    for row in rows:
        groups[row["drawing_number"]].append(row)
    for item in exclusions:
        _check(
            set(item) == {"drawing_number", "event_order", "reason", "source_sha256"},
            "exclusion fields",
        )
        draw, order = item["drawing_number"], item["event_order"]
        _check(
            draw in groups and type(order) is int and 0 <= order < 15,
            "exclusion drawing/order",
        )
        _check(
            order not in excluded[draw] and bool(item["reason"]), "duplicate exclusion"
        )
        _hash(item["source_sha256"])
        excluded[draw].add(order)
    for draw, group in groups.items():
        orders = {r["event_order"] for r in group}
        _check(not orders & excluded[draw], "exclusion overlaps included row")
        _check(
            len(orders) == len(group)
            and orders | excluded[draw] == set(range(15))
            and len({r["event_id"] for r in group}) == len(group),
            "complete drawing denominator/exclusions required",
        )
    return groups


def prepare_fit(
    records,
    heldout_rows,
    *,
    target_drawing,
    prediction_as_of,
    independently_reviewed_hashes,
    training_exclusions=(),
    heldout_pending=False,
):
    """Validate/freeze the research cohort before fitting; no heldout labels accepted.

    Historical label availability may be unknown (scenario grade), but actual
    completion before the validation cutoff is mandatory. Heldout labels are not
    accepted by this API. Repeated canonical train/heldout fixtures fail closed.
    """
    cutoff = _time(prediction_as_of)
    _check(type(target_drawing) is int and len(records) <= 1920, "target/training cap")
    _check(
        type(heldout_pending) is bool
        and len(heldout_rows) <= 120
        and (bool(heldout_rows) or heldout_pending),
        "heldout row cap",
    )
    _check(not (heldout_pending and heldout_rows), "pending heldout must be empty")
    rows, eligible, labels, weights = [], [], [], []
    unknown_asof = False
    train_ids = set()
    for record in sorted(
        records,
        key=lambda r: (r["features"]["drawing_number"], r["features"]["event_order"]),
    ):
        _check(set(record) == {"features", "label"}, "training record fields")
        row, label = record["features"], record["label"]
        _check(
            row["drawing_number"] < target_drawing,
            "training drawing must precede target",
        )
        weight = _validate_row(row, independently_reviewed_hashes)
        _check(_time(row["kickoff"]) < cutoff, "training kickoff after prediction")
        _check(
            row["event_id"] not in train_ids,
            "duplicate complete drawing/canonical fixture",
        )
        train_ids.add(row["event_id"])
        _sealed(label)
        _check(
            set(label)
            == {
                "drawing_number",
                "event_id",
                "outcome",
                "completed_by",
                "completion_basis",
                "available_at",
                "fetched_at",
                "source_sha256",
                "sha256",
            },
            "label fields",
        )
        _check(
            (label["drawing_number"], label["event_id"])
            == (row["drawing_number"], row["event_id"]),
            "label identity",
        )
        _check(
            type(label["outcome"]) is int and 0 <= label["outcome"] <= 2,
            "label outcome",
        )
        _check(
            label["completion_basis"] in COMPLETION_BASES,
            "training label completion basis",
        )
        completion = _time(label["completed_by"])
        _check(_time(row["kickoff"]) < completion < cutoff, "training label completion")
        _check(completion <= _time(label["fetched_at"]), "label completed after fetch")
        available = label["available_at"]
        if available is not None:
            _check(
                completion <= _time(available) <= _time(label["fetched_at"]),
                "label availability chronology",
            )
            _check(_time(available) < cutoff, "known unavailable training label")
        _hash(label["source_sha256"])
        unknown_asof |= (
            available is None
            or row["bk_quote_available_at"] is None
            or row["feature_available_at"] is None
        )
        rows.append(row)
        if weight > 0:
            eligible.append(row)
            labels.append(label["outcome"])
            weights.append(weight)
    groups = _complete_groups(rows, training_exclusions)
    target_ids = set()
    for row in heldout_rows:
        _validate_row(row, independently_reviewed_hashes)
        _check(
            row["drawing_number"] >= target_drawing
            and _time(row["decision_cutoff"]) >= cutoff,
            "heldout chronology",
        )
        _check(
            row["event_id"] not in train_ids, "train/heldout canonical fixture overlap"
        )
        _check(row["event_id"] not in target_ids, "duplicate heldout canonical fixture")
        target_ids.add(row["event_id"])
        unknown_asof |= (
            row["bk_quote_available_at"] is None or row["feature_available_at"] is None
        )
    _complete_groups(heldout_rows)
    matrix, transform = (None, {})
    if eligible:
        matrix, transform = _transform(eligible, FEATURE_NAMES)
    ready = len(groups) >= 3 and len(records) >= 45 and bool(eligible)
    return seal(
        {
            "kind": "RETROSPECTIVE_A5_FIT_PREPARATION",
            "domain": DOMAIN,
            "evidence_grade": "UNVERIFIED_ASOF_SENSITIVITY"
            if unknown_asof
            else "STRICT_RECONSTRUCTED",
            "status": "FIT_READY" if ready else "COLD_START",
            "reason": "NUMERICAL_LOOP_NOT_SEPARATELY_EXPORTED"
            if ready
            else "MINIMUM_3_DRAWS_45_ROWS_AND_ELIGIBLE_ROWS",
            "training_row_count": len(records),
            "training_roster_denominator": len(records) + len(training_exclusions),
            "excluded_training_row_count": len(training_exclusions),
            "training_exclusions": list(training_exclusions),
            "eligible_training_row_count": len(eligible),
            "ineligible_training_row_count": len(records) - len(eligible),
            "unknown_taxonomy_training_row_count": sum(
                any(v is None for v in r["taxonomy"].values()) for r in rows
            ),
            "late_fetched_training_row_count": sum(
                _time(r["fetched_at"]) > _time(r["decision_cutoff"]) for r in rows
            ),
            "train_drawings": sorted(groups),
            "target_drawing": target_drawing,
            "prediction_as_of": prediction_as_of,
            "training_sha256": digest(records),
            "training_fixture_ids": sorted(train_ids),
            "heldout_pending": heldout_pending,
            "heldout_features_sha256": digest(heldout_rows),
            "independent_review_bindings_sha256": digest(
                sorted(independently_reviewed_hashes)
            ),
            "feature_names": list(FEATURE_NAMES),
            "transform": transform,
            "matrix_shape": list(matrix.shape) if matrix is not None else [0, 107],
            "effective_reliability_sum": math.fsum(weights),
            "eligible_labels_sha256": digest(labels),
            "historically_blind": False,
            "known_evaluation_outcomes_previously_inspected": True,
            "fit_completed": False,
            "weights": [],
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
            "profitability_proven": False,
        }
    )


def _code_bindings():
    from hashlib import sha256
    from pathlib import Path

    from toto_ai.sports_stats import v3_probability, v3_residual_kernel

    return {
        name: sha256(Path(path).read_bytes()).hexdigest()
        for name, path in {
            "research": __file__,
            "native": v3_probability.__file__,
            "kernel": v3_residual_kernel.__file__,
        }.items()
    }


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _sports_signal_summary(rows, matrix, weights):
    import numpy as np

    sports = [i for i, n in enumerate(FEATURE_NAMES) if not n.startswith("bk_")]
    observed = {
        FEATURE_NAMES[i]: sum(r["features"][FEATURE_NAMES[i]] is not None for r in rows)
        for i in sports
    }
    active = [
        i
        for i in sports
        if np.any(np.abs(weights[1 + i]) > 1e-12)
        and np.any(np.abs(matrix[:, 1 + i]) > 1e-12)
    ]
    return {
        "nonzero_sports_numeric_observation_rows": sum(
            any(
                r["features"][FEATURE_NAMES[i]] is not None
                and r["features"][FEATURE_NAMES[i]] != 0
                for i in sports
            )
            for r in rows
        ),
        "observed_sports_feature_names": [n for n, count in observed.items() if count],
        "sports_observed_cells_by_feature": observed,
        "missing_sports_cells": len(rows) * len(sports) - sum(observed.values()),
        "active_numeric_sports_coefficient_count": int(
            sum(np.count_nonzero(np.abs(weights[1 + i]) > 1e-12) for i in active)
        ),
        "active_numeric_sports_features": [FEATURE_NAMES[i] for i in active],
        "active_missing_indicator_coefficient_count": int(
            sum(
                np.count_nonzero(np.abs(weights[1 + len(FEATURE_NAMES) + i]) > 1e-12)
                for i in sports
            )
        ),
        "intercept_coefficients": weights[0].tolist(),
        "bk_numeric_coefficients": {
            n: weights[1 + i].tolist()
            for i, n in enumerate(FEATURE_NAMES)
            if n.startswith("bk_")
        },
        "supports_numeric_sports_residual": bool(active),
        "coverage_is_not_independent_predictive_gain": True,
    }


def fit_research(
    records,
    heldout_rows,
    *,
    target_drawing,
    prediction_as_of,
    independently_reviewed_hashes,
    training_exclusions=(),
    heldout_pending=False,
):
    """Fit A5 through the shared unchanged optimizer. No heldout labels accepted."""
    import time

    import numpy as np

    from toto_ai.sports_stats.v3_residual_kernel import fit_residual

    started = time.monotonic()
    prep = prepare_fit(
        records,
        heldout_rows,
        target_drawing=target_drawing,
        prediction_as_of=prediction_as_of,
        independently_reviewed_hashes=independently_reviewed_hashes,
        training_exclusions=training_exclusions,
        heldout_pending=heldout_pending,
    )
    model = {
        "kind": "RETROSPECTIVE_SPORTS_V3_MODEL_V1",
        "schema_version": 1,
        "domain": DOMAIN,
        "variant": "A5",
        "preparation": prep,
        "preparation_sha256": prep["sha256"],
        "training_sha256": prep["training_sha256"],
        "heldout_features_sha256": prep["heldout_features_sha256"],
        "training_drawings": prep["train_drawings"],
        "prediction_as_of": prediction_as_of,
        "target_drawing": target_drawing,
        "feature_names": list(FEATURE_NAMES),
        "transform": {},
        "weights": [],
        "config": {
            "l2": 0.1,
            "steps": 240,
            "time_budget_seconds": 10.0,
            "weight_cap": 0.2,
            "l1_cap": 0.2,
            "hyperparameter_search": False,
        },
        "code_sha256": _code_bindings(),
        "fitted_at": _utc_now(),
        "status": "COLD_START",
        "fit_completed": False,
        "evidence_grade": prep["evidence_grade"],
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
        "profitability_proven": False,
        "sports_fully_integrated": False,
    }
    if prep["status"] == "COLD_START":
        return seal(model)
    eligible = []
    reliability_weights = []
    for record in sorted(
        records,
        key=lambda r: (r["features"]["drawing_number"], r["features"]["event_order"]),
    ):
        weight = _validate_row(record["features"], independently_reviewed_hashes)
        if weight > 0:
            eligible.append(record)
            reliability_weights.append(weight)
    rows = [r["features"] for r in eligible]
    matrix, transform = _transform(rows, FEATURE_NAMES)
    targets = np.eye(3)[[r["label"]["outcome"] for r in eligible]]
    prior = np.log(np.array([r["bk_probabilities"] for r in rows]))
    prior -= prior.mean(axis=1, keepdims=True)
    try:
        weights = fit_residual(
            matrix,
            targets,
            prior,
            np.array(reliability_weights)[:, None],
            l2=0.1,
            steps=240,
            started=started,
            time_budget_seconds=10.0,
        )
    except TimeoutError:
        model.update(status="FIT_BUDGET_EXHAUSTED", fitted_at=_utc_now())
        return seal(model)
    _check(np.all(np.isfinite(weights)), "nonfinite fitted weights")
    model.update(
        status="TRAINED_EXPERIMENTAL",
        fit_completed=True,
        transform=transform,
        weights=weights.tolist(),
        fitted_at=_utc_now(),
        elapsed_seconds=time.monotonic() - started,
        sports_signal_summary=_sports_signal_summary(rows, matrix, weights),
    )
    return seal(model)


def freeze_predictions(model, heldout_rows, *, independently_reviewed_hashes=None):
    """Predict only the exact prebound heldout features. Never consumes labels."""
    import numpy as np

    from toto_ai.sports_stats.v3_residual_kernel import softmax

    _sealed(model)
    _check(
        model["kind"] == "RETROSPECTIVE_SPORTS_V3_MODEL_V1"
        and model["domain"] == DOMAIN
        and model["variant"] == "A5",
        "research model kind",
    )
    _check(
        not any(
            model[k]
            for k in [
                "operator_compatible",
                "automatic_wagering",
                "activation_allowed",
                "profitability_proven",
            ]
        ),
        "research only",
    )
    _check(
        model["status"] == "TRAINED_EXPERIMENTAL" and model["fit_completed"],
        "model not fitted",
    )
    prep = model["preparation"]
    _sealed(prep)
    _check(prep["sha256"] == model["preparation_sha256"], "preparation binding")
    _check(model["code_sha256"] == _code_bindings(), "model code binding")
    pending = prep["heldout_pending"]
    if pending:
        _check(
            bool(independently_reviewed_hashes), "independent heldout review required"
        )
        _check(bool(heldout_rows) and len(heldout_rows) <= 120, "heldout row cap")
        _complete_groups(heldout_rows)
        seen = set()
        for row in heldout_rows:
            _validate_row(row, independently_reviewed_hashes)
            _check(
                row["event_id"] not in prep["training_fixture_ids"],
                "train/heldout canonical fixture overlap",
            )
            _check(row["event_id"] not in seen, "duplicate heldout fixture")
            seen.add(row["event_id"])
            _check(
                row["drawing_number"] >= model["target_drawing"]
                and _time(row["decision_cutoff"]) >= _time(model["prediction_as_of"]),
                "heldout chronology",
            )
    else:
        _check(
            digest(heldout_rows)
            == model["heldout_features_sha256"]
            == prep["heldout_features_sha256"],
            "heldout feature binding",
        )
    _check(model["training_sha256"] == prep["training_sha256"], "training binding")
    _check(
        model["training_drawings"] == prep["train_drawings"]
        and all(d < model["target_drawing"] for d in model["training_drawings"]),
        "training target separation",
    )
    _check(model["feature_names"] == list(FEATURE_NAMES), "feature schema")
    weights = np.array(model["weights"])
    _check(
        weights.shape == (107, 3) and np.all(np.isfinite(weights)),
        "weights shape/finite",
    )
    output = []
    for row in heldout_rows:
        # Exact hash belongs to the model's previously validated heldout roster;
        # this is NOT fresh independent authority for arbitrary new input rows.
        weight = _validate_row(row, {row["sha256"]})
        bk = np.array(row["bk_probabilities"])
        probabilities = bk.copy()
        status = "BK_FALLBACK_INELIGIBLE_FEATURES"
        if weight > 0:
            matrix, _ = _transform([row], FEATURE_NAMES, model["transform"])
            residual = np.einsum("i,ij->j", matrix[0], weights, optimize=False)
            residual -= residual.mean()
            logits = np.log(bk)
            logits -= logits.mean()
            probabilities = softmax(logits + weight * residual)
            distance = float(np.sum(np.abs(probabilities - bk)))
            if distance > 0.2:
                probabilities = bk + ((0.2 - 1e-14) / distance) * (probabilities - bk)
            status = "PREDICTED_EXPERIMENTAL"
        _check(
            np.all(np.isfinite(probabilities)) and np.all(probabilities > 0),
            "invalid predictions",
        )
        _check(
            abs(float(probabilities.sum()) - 1) <= 1e-12
            and float(np.sum(np.abs(probabilities - bk))) <= 0.2,
            "prediction caps",
        )
        output.append(
            {
                "drawing_number": row["drawing_number"],
                "event_id": row["event_id"],
                "event_order": row["event_order"],
                "feature_sha256": row["sha256"],
                "bk_input_sha256": row["bk_input_sha256"],
                "probabilities": probabilities.tolist(),
                "bk_probabilities": bk.tolist(),
                "reliability": weight,
                "status": status,
            }
        )
    return seal(
        {
            "kind": "RETROSPECTIVE_SPORTS_V3_FROZEN_PREDICTIONS_V1",
            "domain": DOMAIN,
            "model_sha256": model["sha256"],
            "heldout_features_sha256": digest(heldout_rows),
            "frozen_at": _utc_now(),
            "rows": output,
            "evidence_grade": "UNVERIFIED_ASOF_SENSITIVITY"
            if model["evidence_grade"] == "UNVERIFIED_ASOF_SENSITIVITY"
            or any(
                r["bk_quote_available_at"] is None or r["feature_available_at"] is None
                for r in heldout_rows
            )
            else "STRICT_RECONSTRUCTED",
            "heldout_review_sha256": digest(sorted(independently_reviewed_hashes or []))
            if pending
            else prep["independent_review_bindings_sha256"],
            "blind_holdout": False,
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
            "profitability_proven": False,
        }
    )


def score_predictions(predictions, labels):
    """Separate post-freeze diagnostic, not financial return or untouched holdout."""
    _sealed(predictions)
    _check(
        predictions["kind"] == "RETROSPECTIVE_SPORTS_V3_FROZEN_PREDICTIONS_V1"
        and predictions["domain"] == DOMAIN,
        "prediction kind",
    )
    indexed = {}
    for label in labels:
        _sealed(label)
        _check(
            set(label)
            == {"sha256", "drawing_number", "event_id", "outcome", "source_sha256"},
            "scoring label fields",
        )
        _check(type(label["outcome"]) is int and 0 <= label["outcome"] < 3, "outcome")
        _hash(label["source_sha256"])
        key = (label["drawing_number"], label["event_id"])
        _check(key not in indexed, "duplicate scoring label")
        indexed[key] = label["outcome"]
    keys = {(r["drawing_number"], r["event_id"]) for r in predictions["rows"]}
    _check(set(indexed) == keys, "scoring label identity")
    totals = {"log_loss": [], "brier": [], "bk_log_loss": [], "bk_brier": []}
    for row in predictions["rows"]:
        outcome = indexed[(row["drawing_number"], row["event_id"])]
        for field, prefix in [("probabilities", ""), ("bk_probabilities", "bk_")]:
            p = _bk(row[field])
            totals[prefix + "log_loss"].append(-math.log(p[outcome]))
            totals[prefix + "brier"].append(
                math.fsum((x - float(i == outcome)) ** 2 for i, x in enumerate(p))
            )
    count = len(predictions["rows"])
    return seal(
        {
            "kind": "RETROSPECTIVE_SPORTS_V3_SCORE_V1",
            "domain": DOMAIN,
            "prediction_sha256": predictions["sha256"],
            "label_sha256": digest(labels),
            "event_count": count,
            **{k: math.fsum(v) / count for k, v in totals.items()},
            "scored_at": _utc_now(),
            "blind_holdout": False,
            "operator_compatible": False,
            "profitability_proven": False,
        }
    )
