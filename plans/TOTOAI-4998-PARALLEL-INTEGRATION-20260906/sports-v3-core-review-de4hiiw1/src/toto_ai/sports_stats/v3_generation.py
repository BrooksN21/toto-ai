"""New research coupons generated from V3 probabilities, never operator IDs."""

import time
from dataclasses import asdict, replace

from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import exact_category_probabilities
from toto_ai.optimizer.coupon_probabilities import best_coupon_by_p13
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
    run_bk_probability_only,
    run_ev_crowd_current,
)
from toto_ai.sports_stats.v3_probability import (
    MODEL_VERSION,
    _check,
    _sealed,
    digest,
    seal,
)


def generate_v3_candidate(
    *,
    request,
    inference,
    frozen_payload,
    control_coupons,
    gate,
    generator="existing_probability_only",
    ev_config=None,
):
    """Use unchanged native constructors with V3 as the probability input.

    Real generation requires the saved F4 probability gate. Synthetic protocol
    execution is explicitly tagged and cannot be promoted to historical evidence.
    Results remain separate, with the old control retained regardless of gains.
    """
    started = time.monotonic()
    _check(isinstance(gate, dict), "probability gate required")
    model = request["model"]
    if gate.get("status") == "SYNTHETIC_TEST_ONLY":
        _check(
            model.get("training_domain") == "SYNTHETIC_TEST_ONLY",
            "synthetic gate domain",
        )
    else:
        _sealed(gate)
        _check(
            gate.get("kind") == "SPORTS_V3_F4_PROBABILITY_GATE"
            and gate.get("status") == "PASS_RESEARCH_ONLY",
            "probability gate not passed",
        )
        _check(
            gate.get("model_version") == MODEL_VERSION
            and gate.get("model_config_sha256") == digest(model["config"])
            and gate.get("feature_schema_sha256") == model["feature_schema_sha256"],
            "probability gate model binding",
        )
        _check(
            gate.get("fold_count") == 7
            and gate.get("event_count") == 105
            and gate.get("coverage", 0) >= 0.70
            and gate.get("leakage_violation_count") == 0,
            "probability gate counts",
        )
    _check(
        model["status"] == "TRAINED_EXPERIMENTAL",
        "unfitted model cannot generate V3 candidate",
    )
    _sealed(inference)
    _check(
        inference["model_sha256"] == model["sha256"]
        and inference["feature_bundle_sha256"] == request["features"]["sha256"],
        "inference/model binding",
    )
    frozen = FrozenStrategyInput(
        **{
            **frozen_payload,
            "events": tuple(FrozenStrategyEvent(**e) for e in frozen_payload["events"]),
        }
    )
    _check(
        frozen.drawing_id == request["features"]["drawing_id"]
        and frozen.drawing_number == request["features"]["drawing_number"]
        and frozen.drawing_fingerprint == request["features"]["drawing_fingerprint"],
        "generator final identity",
    )
    _check(0 < frozen.max_coupons <= 512, "generator capacity cap")
    probabilities = tuple(tuple(row["probabilities"]) for row in inference["events"])
    projected = replace(
        frozen,
        events=tuple(
            replace(event, bk_probabilities=probabilities[i])
            for i, event in enumerate(frozen.events)
        ),
    )
    if generator == "existing_probability_only":
        generated = run_bk_probability_only(projected, category=13)
    elif generator == "existing_quality_v2":
        _check(isinstance(ev_config, dict), "exact EV config required")
        generated = run_ev_crowd_current(
            projected, config=EVConfig(**ev_config), category=13
        )
    else:
        raise ValueError("unsupported research generator")
    coupons = tuple(generated.coupons)
    _check(
        len(coupons) == len(set(coupons)) == frozen.max_coupons,
        "generated candidate capacity",
    )
    comparison = {}
    for name, rows in (
        ("exact_final_bk", frozen.bk_probability_matrix),
        (MODEL_VERSION, probabilities),
    ):
        candidate = exact_category_probabilities(coupons, rows)
        control = exact_category_probabilities(control_coupons, rows)
        comparison[name] = {
            "candidate": list(candidate),
            "control": list(control),
            "non_degrading": all(
                c + 1e-12 >= b for c, b in zip(candidate, control, strict=True)
            ),
        }
    best = best_coupon_by_p13(coupons, probabilities)
    return seal(
        {
            "kind": "SPORTS_V3_RESEARCH_GENERATED_CANDIDATE",
            "namespace": "sports-v3-research-generated",
            "label": "RESEARCH ONLY — NOT FOR WAGERING OR UPLOAD",
            "generator": generator,
            "source_engine": generated.source_engine,
            "model_version": MODEL_VERSION,
            "model_sha256": model["sha256"],
            "training_sha256": model["training_sha256"],
            "feature_bundle_sha256": request["features"]["sha256"],
            "final_input_sha256": inference["final_input_sha256"],
            "probability_input_sha256": digest(probabilities),
            "generator_input_sha256": projected.input_sha256,
            "bank": frozen.bank,
            "stake": frozen.stake,
            "candidate_coupons": list(coupons),
            "ordered_package_sha256": digest(coupons),
            "control_package_sha256": digest(control_coupons),
            "candidate_differs_from_control": coupons != tuple(control_coupons),
            "highest_p13": {
                **asdict(best),
                "criterion": "maximum_probability_at_least_13",
                "probability_model": MODEL_VERSION,
            },
            "exact_comparison": comparison,
            "non_degradation_pass": all(
                v["non_degrading"] for v in comparison.values()
            ),
            "elapsed_seconds": time.monotonic() - started,
            "control_preserved": True,
            "selected_for_operator": False,
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
            "profitability_proven": False,
        }
    )
