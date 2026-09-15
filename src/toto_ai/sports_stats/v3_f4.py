"""Whole-drawing train/freeze/read-label protocol. Local research only."""

import hashlib
import json
import os
import time
from pathlib import Path

from toto_ai.sports_stats.v3_probability import (
    VARIANTS,
    _bk,
    _check,
    _hash,
    _sealed,
    _time,
    canonical_json,
    digest,
    infer_v3,
    seal,
    train_v3,
    validate_feature_row,
    validate_model,
)

V2_VERSION = "sports-analytics-v2-poisson-venue-shrunk-v1"
DOMAINS = ("SYNTHETIC_TEST_ONLY", "FROZEN_HISTORICAL_INPUT")
# The existing predeclared F4 fit, not values accepted from a supplied model.
F4_FIT_L2 = 0.1
F4_FIT_STEPS = 240
F4_FIT_VERIFICATION_SECONDS = 5.0


def bytes_hash(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_scope_receipt(receipt, expected_hash, domain, folds):
    _sealed(receipt)
    _check(receipt["sha256"] == expected_hash, "expected scope receipt hash")
    _check(
        receipt["kind"] == "SPORTS_V3_COMMON_SCOPE_RECEIPT"
        and receipt["domain"] == domain,
        "scope receipt kind/domain",
    )
    if domain == "FROZEN_HISTORICAL_INPUT":
        _check(
            receipt.get("status") == "INDEPENDENTLY_REVIEWED_COMMON_ENTITY_SCOPE",
            "independent common scope receipt required",
        )
        _check(
            all(
                f["sha256"] in receipt.get("verified_fold_input_sha256s", [])
                for f in folds
            ),
            "independently reviewed equal-input fold bindings required",
        )
    _check(bool(receipt["review_evidence_sha256s"]), "scope review evidence absent")
    for value in receipt["review_evidence_sha256s"]:
        _hash(value)
    verified = receipt["verified_feature_sha256s"]
    _check(
        isinstance(verified, list) and len(verified) == len(set(verified)),
        "scope feature bindings",
    )
    for value in verified:
        _hash(value)
    for fold in folds:
        for row in fold["features"]:
            if row["scope_verified"]:
                _check(row["sha256"] in verified, "unbound common scope feature")


def validate_fold(fold):
    _sealed(fold)
    _check(fold["kind"] == "SPORTS_V3_F4_FOLD_INPUT", "fold input kind")
    _check(type(fold["drawing_number"]) is int, "fold drawing identity")
    rows = fold["features"]
    _check(
        len(rows) == 15
        and [r["event_order"] for r in rows] == list(range(15))
        and len({r["event_id"] for r in rows}) == 15,
        "15 unique ordered events",
    )
    for key in (
        "final_input_sha256",
        "scheduler_plan_sha256",
        "drawing_fingerprint",
        "expected_label_file_sha256",
    ):
        _hash(fold[key])
    _check(
        type(fold["bank"]) is int
        and type(fold["stake"]) is int
        and fold["bank"] > 0
        and fold["stake"] > 0
        and fold["bank"] % fold["stake"] == 0,
        "equal-input bank/stake",
    )
    for row in rows:
        validate_feature_row(row)
        _check(
            row["drawing_number"] == fold["drawing_number"]
            and row["as_of"] == fold["as_of"]
            and row["bk_input_sha256"] == fold["final_input_sha256"],
            "fold feature equal-input binding",
        )
    v2 = fold["v2"]
    _sealed(v2)
    _check(
        v2["model_version"] == V2_VERSION
        and v2["final_input_sha256"] == fold["final_input_sha256"]
        and v2["event_ids"] == [r["event_id"] for r in rows]
        and len(v2["probabilities"]) == 15,
        "frozen V2 equal-input binding",
    )
    for probabilities in v2["probabilities"]:
        _bk(probabilities)


def validate_labels(fold, label, file_hash):
    _sealed(label)
    _check(
        file_hash == fold["expected_label_file_sha256"] == bytes_hash(label),
        "label bytes binding",
    )
    _check(
        label["kind"] == "SPORTS_V3_F4_LABELS"
        and label["drawing_number"] == fold["drawing_number"],
        "label drawing",
    )
    _hash(label["snapshot_sha256"])
    _check(len(label["events"]) == 15, "15 labels required")
    available = _time(label["available_at"])
    _check(available > _time(fold["as_of"]), "target label chronology")
    for actual, row in zip(label["events"], fold["features"], strict=True):
        _check(
            actual["event_id"] == row["event_id"]
            and actual["event_order"] == row["event_order"],
            "label event identity",
        )
        _check(
            type(actual["outcome"]) is int and actual["outcome"] in (0, 1, 2),
            "label outcome",
        )
        if row["kickoff"] is not None:
            _check(_time(row["kickoff"]) < available, "terminal label availability")


def training_records(previous, as_of):
    records = []
    for item in previous:
        label = item["labels"]
        if _time(label["available_at"]) >= _time(as_of):
            continue  # Exclude the whole drawing, never a convenient subset.
        fold = item["prediction"]["input"]
        for row, actual in zip(fold["features"], label["events"], strict=True):
            records.append(
                {
                    "features": row,
                    "label": {
                        "drawing_number": fold["drawing_number"],
                        "event_id": row["event_id"],
                        "outcome": actual["outcome"],
                        "snapshot_sha256": label["snapshot_sha256"],
                        "available_at": label["available_at"],
                    },
                }
            )
    return records


def validate_prediction(prediction, previous):
    _sealed(prediction)
    _check(prediction["kind"] == "SPORTS_V3_F4_FROZEN_PREDICTION", "prediction kind")
    _check(
        prediction["operator_compatible"] is False
        and prediction["activation_allowed"] is False,
        "prediction authority flags",
    )
    fold = prediction["input"]
    validate_fold(fold)
    _check(prediction["fold_input_sha256"] == fold["sha256"], "prediction input hash")
    _check(set(prediction["models"]) == set(VARIANTS), "all A2–A5 models required")
    expected_train = training_records(previous, fold["as_of"])
    _check(len(prediction["events"]) == 15, "15 probability events")
    verification_deadline = time.monotonic() + F4_FIT_VERIFICATION_SECONDS
    for variant, model in prediction["models"].items():
        validate_model(model)
        _check(
            model["variant"] == variant
            and model["target_drawing"] == fold["drawing_number"]
            and model["prediction_as_of"] == fold["as_of"]
            and model["training_domain"] == prediction["training_domain"]
            and model["training_sha256"] == digest(expected_train),
            "whole earlier drawing training binding",
        )
        remaining = verification_deadline - time.monotonic()
        _check(remaining > 0, "deterministic fit verification budget exhausted")
        # Reconstruct the complete manifest, eligibility, transforms, residual
        # weights and calibrator independently from actual earlier records.
        # Neither a supplied digest nor inference using that supplied state is
        # evidence that the state was fitted from the declared training data.
        expected_model = train_v3(
            expected_train,
            target_drawing=fold["drawing_number"],
            prediction_as_of=fold["as_of"],
            variant=variant,
            training_domain=prediction["training_domain"],
            l2=F4_FIT_L2,
            steps=F4_FIT_STEPS,
            time_budget_seconds=min(F4_FIT_VERIFICATION_SECONDS, remaining),
        )
        _check(
            time.monotonic() < verification_deadline
            and expected_model["status"] != "FIT_BUDGET_EXHAUSTED",
            "deterministic fit verification budget exhausted",
        )
        _check(
            model == expected_model, "deterministic earlier-only fitted model mismatch"
        )
        for event, row in zip(prediction["events"], fold["features"], strict=True):
            _check(
                event["event_order"] == row["event_order"]
                and event["event_id"] == row["event_id"],
                "prediction event identity",
            )
            _check(
                event[variant] == infer_v3(model, row),
                "recomputed V3 probability binding",
            )
    for i, event in enumerate(prediction["events"]):
        _check(
            event["A0"] == fold["features"][i]["bk_probabilities"]
            and event["A1"] == fold["v2"]["probabilities"][i],
            "untouched A0/A1",
        )
    _check(
        time.monotonic() < verification_deadline,
        "deterministic fit verification budget exhausted",
    )


def _persist(prediction, directory):
    directory = Path(directory).absolute()
    _check(
        not any(p.is_symlink() for p in (directory, *directory.parents)),
        "prediction output symlink",
    )
    newly_created = []
    ancestor = directory
    while not ancestor.exists():
        newly_created.append(ancestor)
        ancestor = ancestor.parent
    directory.mkdir(parents=True, exist_ok=True)
    # Persist newly created directory entries as well as the prediction file.
    for created in reversed(newly_created):
        parent_fd = os.open(created.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    path = directory / f"f4-{prediction['input']['drawing_number']}.prediction.json"
    raw = canonical_json(prediction).encode()
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    _check(path.read_bytes() == raw, "persisted prediction readback")
    return hashlib.sha256(raw).hexdigest()


def run_f4(
    folds,
    *,
    output_dir,
    load_labels,
    training_domain,
    scope_receipt,
    expected_scope_receipt_sha256,
    time_budget_seconds=20,
):
    """No real fit when the independent common-scope bridge is missing.

    load_labels is called only after durable exact prediction bytes exist. The
    driver has no network/DB/operational client and generates no coupons.
    """
    _check(training_domain in DOMAINS, "F4 training domain")
    if scope_receipt is None or expected_scope_receipt_sha256 is None:
        return seal(
            {
                "status": "BLOCKED_MISSING_TRAINING_EVIDENCE",
                "missing": [
                    "independently reviewed common entity-scope feature bridge"
                ],
                "fit_executed": False,
                "activation_allowed": False,
                "automatic_wagering": False,
            }
        )
    _check(
        type(time_budget_seconds) in (int, float) and 0 < time_budget_seconds <= 60,
        "F4 bounded runtime",
    )
    _check(0 < len(folds) <= 7, "F4 at most seven folds")
    validate_scope_receipt(
        scope_receipt, expected_scope_receipt_sha256, training_domain, folds
    )
    previous_number, previous_asof = -1, None
    for fold in folds:
        validate_fold(fold)
        asof = _time(fold["as_of"])
        _check(
            fold["drawing_number"] > previous_number
            and (previous_asof is None or asof > previous_asof),
            "chronological whole drawings",
        )
        previous_number, previous_asof = fold["drawing_number"], asof
    deadline = time.monotonic() + time_budget_seconds
    completed = []
    for fold in folds:
        records = training_records(completed, fold["as_of"])
        models = {}
        for variant in VARIANTS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("F4 runtime exhausted; no gate produced")
            models[variant] = train_v3(
                records,
                target_drawing=fold["drawing_number"],
                prediction_as_of=fold["as_of"],
                variant=variant,
                training_domain=training_domain,
                l2=F4_FIT_L2,
                steps=F4_FIT_STEPS,
                time_budget_seconds=min(5.0, remaining),
            )
        prediction = seal(
            {
                "kind": "SPORTS_V3_F4_FROZEN_PREDICTION",
                "training_domain": training_domain,
                "input": fold,
                "fold_input_sha256": fold["sha256"],
                "models": models,
                "scope_receipt_sha256": scope_receipt["sha256"],
                "events": [
                    {
                        "event_id": row["event_id"],
                        "event_order": row["event_order"],
                        "A0": row["bk_probabilities"],
                        "A1": fold["v2"]["probabilities"][i],
                        **{v: infer_v3(m, row) for v, m in models.items()},
                    }
                    for i, row in enumerate(fold["features"])
                ],
                "package_generation": "NOT_RUN_PROBABILITY_STAGE",
                "operator_compatible": False,
                "activation_allowed": False,
            }
        )
        validate_prediction(prediction, completed)
        if time.monotonic() >= deadline:
            raise TimeoutError("F4 deadline before label read")
        saved_hash = _persist(prediction, output_dir)
        raw = load_labels(fold)
        _check(isinstance(raw, bytes) and len(raw) <= 2_000_000, "label byte input")
        label = json.loads(raw)
        label_hash = hashlib.sha256(raw).hexdigest()
        validate_labels(fold, label, label_hash)
        completed.append(
            {
                "prediction": prediction,
                "prediction_file_sha256": saved_hash,
                "labels": label,
                "label_file_sha256": label_hash,
            }
        )
    from toto_ai.sports_stats.v3_f4_gate import evaluate_f4

    return evaluate_f4(
        completed,
        training_domain=training_domain,
        scope_receipt=scope_receipt,
        expected_scope_receipt_sha256=expected_scope_receipt_sha256,
    )
