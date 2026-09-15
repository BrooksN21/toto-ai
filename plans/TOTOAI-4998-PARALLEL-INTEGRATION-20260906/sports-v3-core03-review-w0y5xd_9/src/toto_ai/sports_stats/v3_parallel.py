"""Optional V3 research scoring; never redefine four-strategy operator consent."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import time

from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.sports_stats.v3_probability import (
    MODEL_VERSION,
    _bk,
    _check,
    _hash,
    _sealed,
    _time,
    canonical_json,
    digest,
    infer_v3,
    seal,
    validate_feature_row,
    validate_model,
)

FEATURE_VERSION = "sports-v3-probability-feature-bundle-v1"
STRATEGIES = ("quality-v2", "sports-shadow", "quality-v3", "robust")


def feature_bundle(
    rows, *, drawing_id, drawing_number, drawing_fingerprint, scheduler_plan_sha256
):
    _check(len(rows) == 15, "15 feature rows required")
    return seal(
        {
            "kind": "SPORTS_V3_FEATURE_BUNDLE",
            "feature_version": FEATURE_VERSION,
            "drawing_id": drawing_id,
            "drawing_number": drawing_number,
            "drawing_fingerprint": drawing_fingerprint,
            "scheduler_plan_sha256": scheduler_plan_sha256,
            "rows": sorted(rows, key=lambda row: row["event_order"]),
            "operator_compatible": False,
            "activation_allowed": False,
        }
    )


def infer_final_bk(request, context):
    """Current final BK replaces the old logit prior; no V2-style second blend."""
    model, bundle = request["model"], request["features"]
    validate_model(model)
    # These expectations are supplied from the caller's separately reviewed
    # model/training receipt, never derived here from a newly self-sealed model.
    _check(
        request["expected_model_sha256"] == model["sha256"]
        and request["expected_training_sha256"] == model["training_sha256"]
        and request["expected_training_manifest_sha256"]
        == model["training_manifest_sha256"],
        "trusted training/model receipt binding",
    )
    _sealed(bundle)
    _check(
        bundle["kind"] == "SPORTS_V3_FEATURE_BUNDLE"
        and bundle["feature_version"] == FEATURE_VERSION,
        "V3 feature version",
    )
    _check(
        bundle["operator_compatible"] is False
        and bundle["activation_allowed"] is False,
        "feature authority",
    )
    for key in (
        "drawing_id",
        "drawing_number",
        "drawing_fingerprint",
        "scheduler_plan_sha256",
    ):
        _check(bundle[key] == context[key], "final binding: " + key)
    for key in ("drawing_fingerprint", "scheduler_plan_sha256", "final_input_sha256"):
        _hash(context[key])
    rows = bundle["rows"]
    _check(
        len(rows) == 15 and [r["event_order"] for r in rows] == list(range(15)),
        "V3 event orders",
    )
    _check(
        len(context["event_ids"])
        == len(set(context["event_ids"]))
        == len(context["bk_probabilities"])
        == 15,
        "final event identities",
    )
    captured = _time(context["captured_at"])
    results = []
    for index, row in enumerate(rows):
        validate_feature_row(row)
        _check(
            row["drawing_number"] == context["drawing_number"]
            and row["drawing_id"] == context["drawing_id"]
            and row["event_id"] == context["event_ids"][index],
            "event orientation/binding",
        )
        _check(
            row["scheduler_plan_sha256"] == context["scheduler_plan_sha256"],
            "row plan binding",
        )
        _check(
            _time(row["as_of"]) <= captured
            and _time(row["bk_captured_at"]) <= captured,
            "final chronology",
        )
        if row["kickoff"] is not None:
            _check(captured < _time(row["kickoff"]), "post-kickoff final")
        if "deadline" in row:
            _check(captured < _time(row["deadline"]), "expired feature")
        _bk(context["bk_probabilities"][index])
        results.append(
            infer_v3(
                model,
                row,
                bk_probabilities=context["bk_probabilities"][index],
                bk_input_sha256=context["final_input_sha256"],
                bk_margin=context["bk_margins"][index],
            )
        )
    return seal(
        {
            "model_version": MODEL_VERSION,
            "model_sha256": model["sha256"],
            "feature_bundle_sha256": bundle["sha256"],
            "final_input_sha256": context["final_input_sha256"],
            "probability_input_sha256": digest(context["bk_probabilities"]),
            "final_context": {
                **{
                    k: context[k]
                    for k in (
                        "drawing_id",
                        "drawing_number",
                        "drawing_fingerprint",
                        "scheduler_plan_sha256",
                        "captured_at",
                        "event_ids",
                    )
                },
                "frozen_input_sha256": (
                    digest(context["frozen_input"])
                    if "frozen_input" in context
                    else None
                ),
            },
            "events": results,
            "operator_compatible": False,
            "activation_allowed": False,
        }
    )


def _worker(payload):
    inference = infer_final_bk(payload["request"], payload["context"])
    packages = payload["packages"]
    _check(set(packages) == set(STRATEGIES), "four existing strategies only")
    probabilities = [r["probabilities"] for r in inference["events"]]
    metrics = {}
    for name in STRATEGIES:
        coupons = packages[name]
        _check(
            0 < len(coupons) <= 512 and len(set(coupons)) == len(coupons),
            "research package size",
        )
        _check(
            all(len(c) == 15 and not set(c) - set("1X2") for c in coupons),
            "coupon syntax",
        )
        p13, p14, p15 = exact_category_probabilities(coupons, probabilities)
        metrics[name] = {
            "package_sha256": digest(coupons),
            "probability_at_least_13": p13,
            "probability_at_least_14": p14,
            "probability_at_least_15": p15,
        }
    result = {
        "status": "COMPLETE_EXPERIMENTAL_NO_SELECTION",
        "request_sha256": digest(payload),
        "inference": inference,
        "candidate_metrics": metrics,
        "control_preserved": True,
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
        "model_version": MODEL_VERSION,
        "release_gate": "UNVALIDATED_RESEARCH_ONLY",
    }
    if payload["request"].get("generate_candidate") is True:
        from toto_ai.sports_stats.v3_generation import generate_v3_candidate

        result["generated_candidate"] = generate_v3_candidate(
            request=payload["request"],
            inference=inference,
            frozen_payload=payload["context"]["frozen_input"],
            control_coupons=packages["quality-v2"],
            gate=payload["request"].get("generation_gate"),
            generator=payload["request"].get("generator", "existing_probability_only"),
            ev_config=payload["context"].get("ev_config"),
        )
    return seal(result)


def run_v3_parallel_research(request, *, context, packages, deadline):
    result = {
        "status": "DISABLED",
        "control_preserved": True,
        "operator_compatible": False,
        "automatic_wagering": False,
        "activation_allowed": False,
        "model_version": MODEL_VERSION,
    }
    if request is None:
        return result
    started = time.monotonic()
    try:
        _check(
            deadline is not None and math.isfinite(deadline),
            "explicit research deadline required",
        )
        timeout = min(5.0, deadline - started - 30.0)
        _check(timeout > 0, "publication reserve")
        payload = {"request": request, "context": context, "packages": packages}
        raw = canonical_json(payload)
        _check(len(raw) <= 2_000_000, "research request size cap")
        timeout = min(timeout, deadline - time.monotonic() - 30.0)
        _check(timeout > 0, "publication reserve")
        completed = subprocess.run(
            [sys.executable, "-B", "-m", "toto_ai.sports_stats.v3_parallel"],
            input=raw,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=True,
        )
        _check(
            time.monotonic() <= deadline - 30.0 and time.monotonic() - started <= 5.0,
            "late V3 result",
        )
        _check(len(completed.stdout) <= 2_000_000, "research result size cap")
        result = json.loads(completed.stdout)
        _sealed(result)
        _check(
            result["request_sha256"] == digest(payload)
            and result["model_version"] == MODEL_VERSION,
            "research worker binding",
        )
        _check(
            result["control_preserved"] is True
            and all(
                result[k] is False
                for k in (
                    "operator_compatible",
                    "automatic_wagering",
                    "activation_allowed",
                )
            ),
            "research authority",
        )
        _check(
            set(result["candidate_metrics"]) == set(STRATEGIES), "research strategies"
        )
        for name in STRATEGIES:
            _check(
                result["candidate_metrics"][name]["package_sha256"]
                == digest(packages[name]),
                "research package binding",
            )
        return result
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        return {
            "status": "CONTROL_FALLBACK",
            "reason": type(error).__name__ + ":" + str(error),
            "control_preserved": True,
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
            "model_version": MODEL_VERSION,
        }


if __name__ == "__main__":
    raw = sys.stdin.read(2_000_001)
    _check(len(raw) <= 2_000_000, "worker request size cap")
    print(canonical_json(_worker(json.loads(raw))))
