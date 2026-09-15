"""Train-only, bounded multinomial BK residual. Experimental, never authority."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from toto_ai.sports_stats.v3_draw_calibration import (
    draw_logit_shift,
    fit_draw_calibrator,
)
from toto_ai.sports_stats.v3_features import PREDICTOR_FEATURE_NAMES

MODEL_VERSION = "sports-analytics-v3-bk-residual-l2-v1"
DIFFERENCES = (
    "rolling_ppg",
    "rolling_goal_difference_per_game",
    "rolling_goals_for_per_game",
    "rolling_goals_against_per_game",
    "rest_days",
    "matches_in_last_7_days",
    "matches_in_last_14_days",
    "venue_goals_for_per_game",
    "venue_goals_against_per_game",
)
EXTRA_SIDE_FEATURES = (
    "recency_ppg",
    "recency_goal_difference",
    "independent_opponent_ppg",
    "opponent_adjusted_ppg",
    "standings_rank",
    "standings_points",
    "standings_goal_difference",
)
CORE_NAMES = (*PREDICTOR_FEATURE_NAMES, *(f"difference_{s}" for s in DIFFERENCES))
FEATURE_NAMES = (
    *CORE_NAMES,
    *(f"{side}_{s}" for side in ("home", "away") for s in EXTRA_SIDE_FEATURES),
    "bk_margin",
    "bk_entropy",
)
VARIANTS = ("A2", "A3", "A4", "A5")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def seal(value):
    result = {k: v for k, v in value.items() if k != "sha256"}
    return {**result, "sha256": digest(result)}


def _check(condition, reason):
    if not condition:
        raise ValueError(reason)


def _time(value):
    _check(isinstance(value, str), "timestamp string required")
    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _check(
        value.tzinfo is not None and value.utcoffset() == timezone.utc.utcoffset(value),
        "UTC timestamp required",
    )
    return value


def _hash(value):
    _check(
        isinstance(value, str)
        and len(value) == 64
        and not set(value) - set("0123456789abcdef"),
        "SHA256 required",
    )


def _sealed(value):
    _check(isinstance(value, dict) and seal(value) == value, "artifact hash mismatch")


def _bk(values):
    values = tuple(values)
    _check(
        len(values) == 3
        and all(type(v) in (float, int) and math.isfinite(v) and v > 0 for v in values),
        "invalid BK probabilities",
    )
    _check(abs(math.fsum(values) - 1) <= 1e-12, "BK not normalized")
    return values


def validate_feature_row(row):
    _sealed(row)
    _check(
        row["kind"] == "SPORTS_V3_PREDICTORS" and row["schema_version"] == 1,
        "feature schema",
    )
    _check(set(row["features"]) == set(FEATURE_NAMES), "predictor allowlist")
    _check(
        all(
            v is None or (type(v) in (int, float) and math.isfinite(v))
            for v in row["features"].values()
        ),
        "nonfinite predictor",
    )
    _check(
        type(row["drawing_number"]) is int
        and type(row["event_order"]) is int
        and 0 <= row["event_order"] < 15,
        "event identity",
    )
    _check(isinstance(row["event_id"], str) and bool(row["event_id"]), "event identity")
    chronology = _time(row["as_of"]) <= _time(row["bk_captured_at"])
    if row["kickoff"] is not None:
        chronology = chronology and _time(row["bk_captured_at"]) < _time(row["kickoff"])
    else:
        _check(row["exact_target"] is False, "missing target kickoff")
    _check(chronology or row["source_rejected"] is True, "feature chronology")
    _check(
        len(row["prior_counts"]) == 2
        and all(type(c) is int and c >= 0 for c in row["prior_counts"]),
        "prior counts",
    )
    _check(
        all(
            type(row[k]) is bool
            for k in ("exact_target", "scope_verified", "source_rejected")
        ),
        "source flags",
    )
    _hash(row["bk_input_sha256"])
    for value in row["source_hashes"]:
        _hash(value)
    _bk(row["bk_probabilities"])


def reliability(row, names):
    if row["source_rejected"] or not row["exact_target"] or not row["scope_verified"]:
        return 0.0
    coverage = sum(row["features"][n] is not None for n in names) / len(names)
    return 0.2 * min(1.0, min(row["prior_counts"]) / 10) * coverage


def _values(row, names, bk=None, margin=None):
    values = dict(row["features"])
    probabilities = row["bk_probabilities"] if bk is None else bk
    values["bk_entropy"] = -math.fsum(p * math.log(p) for p in probabilities)
    values["bk_margin"] = row.get("bk_margin") if margin is None else margin
    return [values[n] for n in names]


def _transform(rows, names, fitted=None):
    raw = np.array(
        [[np.nan if v is None else v for v in _values(r, names)] for r in rows],
        dtype=float,
    )
    missing = np.isnan(raw)
    if fitted is None:
        medians = np.array(
            [
                float(np.median(c[~np.isnan(c)])) if np.any(~np.isnan(c)) else 0.0
                for c in raw.T
            ]
        )
        imputed = np.where(missing, medians, raw)
        means = imputed.mean(axis=0)
        scales = imputed.std(axis=0)
        scales = np.where(scales > 1e-12, scales, 1.0)
        fitted = {
            "medians": medians.tolist(),
            "means": means.tolist(),
            "scales": scales.tolist(),
            "clip": 8.0,
        }
    filled = np.where(missing, fitted["medians"], raw)
    standardized = np.clip((filled - fitted["means"]) / fitted["scales"], -8, 8)
    return np.column_stack(
        (np.ones(len(rows)), standardized, missing.astype(float))
    ), fitted


def _softmax(logits):
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    values = np.exp(shifted)
    return values / values.sum(axis=-1, keepdims=True)


def train_v3(
    records,
    *,
    target_drawing,
    prediction_as_of,
    variant="A5",
    l2=0.1,
    steps=240,
    time_budget_seconds=10.0,
    training_domain="FROZEN_HISTORICAL_INPUT",
):
    """Fixed predeclared L2; no hyperparameter search on the target or labels.

    All complete earlier drawings remain in the cohort denominator. Ineligible
    feature rows receive zero training weight, never invented predictors.
    """
    started = time.monotonic()
    _check(variant in VARIANTS and type(target_drawing) is int, "variant/target")
    _check(
        training_domain in ("FROZEN_HISTORICAL_INPUT", "SYNTHETIC_TEST_ONLY"),
        "training domain",
    )
    _check(
        type(steps) is int
        and 1 <= steps <= 1000
        and 0 < l2 <= 100
        and 0 < time_budget_seconds <= 30,
        "fit budget/config",
    )
    _check(len(records) <= 1920, "training row cap")
    cutoff = _time(prediction_as_of)
    records = sorted(
        records,
        key=lambda r: (r["features"]["drawing_number"], r["features"]["event_order"]),
    )
    drawings = defaultdict(list)
    for record in records:
        row, label = record["features"], record["label"]
        validate_feature_row(row)
        draw = row["drawing_number"]
        _check(draw < target_drawing, "training drawing must precede target")
        _check(
            label["drawing_number"] == draw and label["event_id"] == row["event_id"],
            "label identity",
        )
        _check(
            type(label["outcome"]) is int and 0 <= label["outcome"] < 3, "label outcome"
        )
        _check(
            _time(label["available_at"]) < cutoff
            and (
                row["kickoff"] is None
                or _time(row["kickoff"]) < _time(label["available_at"])
            ),
            "label availability",
        )
        _hash(label["snapshot_sha256"])
        drawings[draw].append(row)
    for rows in drawings.values():
        _check(
            len(rows) == 15
            and {r["event_order"] for r in rows} == set(range(15))
            and len({r["event_id"] for r in rows}) == 15,
            "complete drawing required",
        )
    names = CORE_NAMES if variant in ("A2", "A3") else FEATURE_NAMES
    eligible = [
        r
        for r in records
        if reliability(r["features"], names) > 0
        and (
            variant not in ("A2", "A3")
            or all(r["features"]["features"][n] is not None for n in names)
        )
    ]
    model = {
        "schema_version": 1,
        "kind": "SPORTS_V3_PROBABILITY_MODEL",
        "model_version": MODEL_VERSION,
        "training_domain": training_domain,
        "feature_names": list(names),
        "feature_schema_sha256": digest(names),
        "variant": variant,
        "prediction_as_of": prediction_as_of,
        "target_drawing": target_drawing,
        "train_drawings": sorted(drawings),
        "train_drawing_max": max(drawings, default=None),
        "training_row_count": len(records),
        "eligible_training_row_count": len(eligible),
        "training_rows": [
            {
                "drawing_number": r["features"]["drawing_number"],
                "event_id": r["features"]["event_id"],
                "event_order": r["features"]["event_order"],
                "feature_as_of": r["features"]["as_of"],
                "feature_kickoff": r["features"]["kickoff"],
                "fit_eligible": r in eligible,
                "feature_sha256": r["features"]["sha256"],
                "label_sha256": digest(r["label"]),
                "label_available_at": r["label"]["available_at"],
            }
            for r in records
        ],
        "training_sha256": digest(records),
        "leakage_violation_count": 0,
        "config": {
            "l2": l2,
            "steps": steps,
            "weight_cap": 0.2,
            "l1_cap": 0.2,
            "hyperparameter_selection": "FIXED_PREDECLARED_NO_SEARCH",
        },
        "status": "COLD_START",
        "reason": "MINIMUM_3_DRAWINGS_45_EVENTS",
        "transform": {},
        "weights": [],
        "draw_calibrator": None,
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
        "profitability_proven": False,
    }
    model["training_manifest_sha256"] = digest(model["training_rows"])
    if len(drawings) < 3 or len(records) < 45 or not eligible:
        if not eligible:
            model["reason"] = "NO_ELIGIBLE_FEATURE_ROWS"
        return seal(model)
    rows = [r["features"] for r in eligible]
    matrix, transform = _transform(rows, names)
    weights = np.zeros((matrix.shape[1], 3))
    targets = np.eye(3)[[r["label"]["outcome"] for r in eligible]]
    prior = np.log(np.array([r["bk_probabilities"] for r in rows]))
    prior -= prior.mean(axis=1, keepdims=True)
    reliability_weights = np.array([reliability(r, names) for r in rows])[:, None]
    rate = 1.0 / (l2 + 0.5 * np.max(np.sum(matrix * matrix, axis=1)) * 0.2**2)
    for _ in range(steps):
        if time.monotonic() - started > time_budget_seconds:
            return seal(
                {**model, "status": "FIT_BUDGET_EXHAUSTED", "reason": "FIT_TIME_BUDGET"}
            )
        prediction = _softmax(
            prior
            + reliability_weights
            * np.einsum("ij,jk->ik", matrix, weights, optimize=False)
        )
        gradient = (
            np.einsum(
                "ij,ik->jk",
                matrix,
                reliability_weights * (prediction - targets),
                optimize=False,
            )
            / len(rows)
            + l2 * weights
        )
        weights -= rate * gradient
        weights -= weights.mean(axis=1, keepdims=True)
    _check(np.all(np.isfinite(weights)), "nonfinite fitted weights")
    model.update(
        status="TRAINED_EXPERIMENTAL",
        reason=None,
        transform=transform,
        weights=weights.tolist(),
    )
    if variant in ("A3", "A4"):
        probabilities = _softmax(
            prior
            + reliability_weights
            * np.einsum("ij,jk->ik", matrix, weights, optimize=False)
        )
        try:
            model["draw_calibrator"] = fit_draw_calibrator(
                rows,
                [r["label"]["outcome"] for r in eligible],
                probabilities,
                reliability_weights[:, 0],
                l2=l2,
                steps=steps,
                deadline=started + time_budget_seconds,
            )
        except TimeoutError:
            model.update(
                status="FIT_BUDGET_EXHAUSTED",
                reason="DRAW_FIT_TIME_BUDGET",
                weights=[],
                transform={},
            )
    return seal(model)


def validate_model(model):
    _sealed(model)
    _check(
        model["schema_version"] == 1
        and model["kind"] == "SPORTS_V3_PROBABILITY_MODEL"
        and model["model_version"] == MODEL_VERSION,
        "model version",
    )
    _check(model["variant"] in VARIANTS, "model variant")
    _validate_training_manifest(model)
    names = CORE_NAMES if model["variant"] in ("A2", "A3") else FEATURE_NAMES
    _check(
        model["feature_names"] == list(names)
        and model["feature_schema_sha256"] == digest(names),
        "feature schema hash",
    )
    _check(
        all(
            model[k] is False
            for k in (
                "operator_compatible",
                "automatic_wagering",
                "activation_allowed",
                "profitability_proven",
            )
        ),
        "model authority flags",
    )
    _check(
        model["status"]
        in ("TRAINED_EXPERIMENTAL", "COLD_START", "FIT_BUDGET_EXHAUSTED"),
        "model status",
    )
    if model["status"] == "TRAINED_EXPERIMENTAL":
        weights = np.array(model["weights"], dtype=float)
        _check(
            weights.shape == (1 + 2 * len(names), 3) and np.all(np.isfinite(weights)),
            "model weight dimensions",
        )
        _check(np.max(np.abs(weights.sum(axis=1))) < 1e-10, "sum-to-zero logits")
        for field in ("medians", "means", "scales"):
            values = model["transform"][field]
            _check(
                len(values) == len(names) and all(math.isfinite(v) for v in values),
                "transform dimensions",
            )
        _check(all(v > 0 for v in model["transform"]["scales"]), "transform scale")
        calibrator = model["draw_calibrator"]
        _check(
            (calibrator is not None) == (model["variant"] in ("A3", "A4")),
            "draw variant contract",
        )
        if calibrator is not None:
            _check(
                calibrator["status"] == "EXPERIMENTAL_NOT_SCREENED"
                and calibrator["feature_names"]
                == ["bk_margin", "bk_entropy", "reliability"]
                and calibrator["raw_shift_bound"] == 1.0,
                "draw calibrator contract",
            )
            _check(
                len(calibrator["weights"]) == 4
                and all(math.isfinite(v) for v in calibrator["weights"]),
                "draw weights",
            )
            for field in ("medians", "means", "scales"):
                _check(
                    len(calibrator["transform"][field]) == 3
                    and all(math.isfinite(v) for v in calibrator["transform"][field]),
                    "draw transform",
                )
            _check(all(v > 0 for v in calibrator["transform"]["scales"]), "draw scale")


def load_model(text):
    _check(len(text) <= 2_000_000, "model size cap")
    model = json.loads(text)
    validate_model(model)
    return model


def _validate_training_manifest(model):
    cutoff = _time(model["prediction_as_of"])
    _check(type(model["target_drawing"]) is int, "training target type")
    _check(
        model["training_domain"] in ("FROZEN_HISTORICAL_INPUT", "SYNTHETIC_TEST_ONLY"),
        "training domain",
    )
    config = model["config"]
    _check(
        type(config["steps"]) is int
        and 1 <= config["steps"] <= 1000
        and type(config["l2"]) in (int, float)
        and 0 < config["l2"] <= 100
        and config["weight_cap"] == config["l1_cap"] == 0.2
        and config["hyperparameter_selection"] == "FIXED_PREDECLARED_NO_SEARCH",
        "training config",
    )
    rows = model["training_rows"]
    _check(isinstance(rows, list) and len(rows) <= 1920, "training manifest size")
    _hash(model["training_sha256"])
    _check(digest(rows) == model["training_manifest_sha256"], "training manifest hash")
    groups = defaultdict(list)
    for row in rows:
        draw = row["drawing_number"]
        _check(type(draw) is int and draw < model["target_drawing"], "training drawing")
        _check(
            type(row["event_order"]) is int and 0 <= row["event_order"] < 15,
            "training event order",
        )
        _check(
            isinstance(row["event_id"], str) and bool(row["event_id"]),
            "training event identity",
        )
        _check(type(row["fit_eligible"]) is bool, "training eligibility flag")
        available = _time(row["label_available_at"])
        _check(
            _time(row["feature_as_of"]) < available < cutoff,
            "training label chronology",
        )
        if row["feature_kickoff"] is not None:
            _check(
                _time(row["feature_kickoff"]) < available, "training kickoff chronology"
            )
        for key in ("feature_sha256", "label_sha256"):
            _hash(row[key])
        groups[draw].append(row)
    for group in groups.values():
        _check(
            len(group) == 15
            and {r["event_order"] for r in group} == set(range(15))
            and len({r["event_id"] for r in group}) == 15,
            "training complete drawing",
        )
    _check(
        model["train_drawings"] == sorted(groups)
        and model["train_drawing_max"] == max(groups, default=None),
        "training drawing summary",
    )
    _check(
        type(model["training_row_count"]) is int
        and model["training_row_count"] == len(rows)
        and type(model["eligible_training_row_count"]) is int
        and model["eligible_training_row_count"] == sum(r["fit_eligible"] for r in rows)
        and type(model["leakage_violation_count"]) is int
        and model["leakage_violation_count"] == 0,
        "training count summary",
    )
    if model["status"] == "TRAINED_EXPERIMENTAL":
        _check(
            len(groups) >= 3
            and len(rows) >= 45
            and model["eligible_training_row_count"] > 0,
            "trained cold-start boundary",
        )
    else:
        _check(
            model["weights"] == []
            and model["transform"] == {}
            and model["draw_calibrator"] is None,
            "unfitted model state",
        )


def infer_v3(
    model, row, *, bk_probabilities=None, bk_input_sha256=None, bk_margin=None
):
    """Recompute logits against current BK, never blend an already blended V2 q."""
    bk = _bk(row["bk_probabilities"] if bk_probabilities is None else bk_probabilities)
    binding = row["bk_input_sha256"] if bk_input_sha256 is None else bk_input_sha256
    _hash(binding)
    result = {
        "model_version": MODEL_VERSION,
        "status": "BK_FALLBACK",
        "reason": None,
        "probabilities": list(bk),
        "probability_sha256": digest(list(bk)),
        "bk_probabilities": list(bk),
        "bk_input_sha256": binding,
        "reliability": 0.0,
        "feature_sha256": row.get("sha256"),
        "model_sha256": model.get("sha256") if isinstance(model, dict) else None,
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
    }
    try:
        validate_model(model)
        validate_feature_row(row)
        _check(
            model["target_drawing"] <= row["drawing_number"]
            and all(d < row["drawing_number"] for d in model["train_drawings"]),
            "training/target separation",
        )
        _check(
            _time(model["prediction_as_of"]) <= _time(row["as_of"]),
            "model unavailable at as_of",
        )
        _check(
            model["status"] == "TRAINED_EXPERIMENTAL",
            model["reason"] or model["status"],
        )
        names = model["feature_names"]
        weight = reliability(row, names)
        _check(weight > 0, "SOURCE_OR_COVERAGE_FALLBACK")
        if model["variant"] in ("A2", "A3"):
            _check(
                all(row["features"][n] is not None for n in names),
                "STRICT_CORE_MISSING",
            )
        current = {**row, "bk_probabilities": list(bk)}
        if bk_probabilities is not None:
            current["bk_margin"] = bk_margin
        matrix, _ = _transform([current], names, model["transform"])
        residual = np.einsum(
            "i,ij->j", matrix[0], np.array(model["weights"]), optimize=False
        )
        residual -= residual.mean()
        logits = np.log(np.array(bk))
        logits -= logits.mean()
        draw_shift = draw_logit_shift(model["draw_calibrator"], current, weight)
        probabilities = _softmax(
            logits
            + weight * residual
            + np.array([-draw_shift / 3, 2 * draw_shift / 3, -draw_shift / 3])
        )
        distance = float(np.sum(np.abs(probabilities - bk)))
        if distance > 0.2:
            probabilities = np.array(bk) + ((0.2 - 1e-14) / distance) * (
                probabilities - bk
            )
        _check(
            np.all(np.isfinite(probabilities)) and np.all(probabilities > 0),
            "invalid residual output",
        )
        _check(
            abs(float(probabilities.sum()) - 1) <= 1e-12
            and float(np.sum(np.abs(probabilities - bk))) <= 0.2,
            "residual cap integrity",
        )
        result.update(
            status="PREDICTED_EXPERIMENTAL",
            probabilities=probabilities.tolist(),
            reliability=weight,
            draw_logit_shift=draw_shift,
        )
        result["probability_sha256"] = digest(result["probabilities"])
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        result["reason"] = str(error)
    return seal(result)
