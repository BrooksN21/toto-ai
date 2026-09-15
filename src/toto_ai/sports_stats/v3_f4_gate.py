"""Independently recomputed saved F4 screen; never production authority."""

from toto_ai.sports_stats.v3_f4 import (
    bytes_hash,
    validate_labels,
    validate_prediction,
    validate_scope_receipt,
)
from toto_ai.sports_stats.v3_f4_metrics import (
    paired_cluster_bootstrap,
    probability_metrics,
)
from toto_ai.sports_stats.v3_probability import (
    FEATURE_NAMES,
    MODEL_VERSION,
    VARIANTS,
    _check,
    _sealed,
    _time,
    digest,
    seal,
)

ALL_VARIANTS = ("A0", "A1", *VARIANTS)


def _delta(left, right, key):
    if left[key] is None or right[key] is None:
        return None
    return left[key] - right[key]


def _le(value, bound):
    return value is not None and value <= bound


def evaluate_f4(
    folds, *, training_domain, scope_receipt, expected_scope_receipt_sha256
):
    _check(
        training_domain in ("SYNTHETIC_TEST_ONLY", "FROZEN_HISTORICAL_INPUT"),
        "F4 domain",
    )
    _check(0 < len(folds) <= 7, "F4 at most seven folds")
    inputs = [f["prediction"]["input"] for f in folds]
    validate_scope_receipt(
        scope_receipt, expected_scope_receipt_sha256, training_domain, inputs
    )
    numbers = [f["drawing_number"] for f in inputs]
    _check(numbers == sorted(set(numbers)), "unique chronological drawing IDs")
    _check(
        all(
            _time(a["as_of"]) < _time(b["as_of"])
            for a, b in zip(inputs, inputs[1:], strict=False)
        ),
        "chronological fold as-of",
    )
    flat = {v: [] for v in ALL_VARIANTS}
    labels, covered, per_fold, bootstrap_inputs = [], [], [], []
    fallback_ok = True
    fits_complete = True
    configs = []
    for index, item in enumerate(folds):
        prediction, label = item["prediction"], item["labels"]
        validate_prediction(prediction, folds[:index])
        fold = prediction["input"]
        _check(
            prediction["training_domain"] == training_domain
            and prediction["scope_receipt_sha256"] == scope_receipt["sha256"],
            "prediction domain/scope",
        )
        _check(
            bytes_hash(prediction) == item["prediction_file_sha256"],
            "frozen prediction bytes",
        )
        validate_labels(fold, label, item["label_file_sha256"])
        actual = [r["outcome"] for r in label["events"]]
        probabilities = {v: [] for v in ALL_VARIANTS}
        for row, event in zip(fold["features"], prediction["events"], strict=True):
            mandatory = (
                row["source_rejected"]
                or not row["exact_target"]
                or not row["scope_verified"]
                or min(row["prior_counts"]) == 0
            )
            covered.append(
                not mandatory
                and all(row["features"][n] is not None for n in FEATURE_NAMES)
            )
            for variant in ALL_VARIANTS:
                p = (
                    event[variant]
                    if variant in ("A0", "A1")
                    else event[variant]["probabilities"]
                )
                probabilities[variant].append(p)
                if mandatory and variant in VARIANTS:
                    fallback_ok = fallback_ok and (
                        all(
                            abs(a - b) <= 1e-15
                            for a, b in zip(p, event["A0"], strict=True)
                        )
                        and event[variant]["probability_sha256"] == digest(event["A0"])
                    )
            for variant in VARIANTS:
                _check(
                    sum(
                        abs(a - b)
                        for a, b in zip(
                            probabilities[variant][-1], event["A0"], strict=True
                        )
                    )
                    <= 0.20,
                    "F4 residual cap",
                )
        metrics = {
            v: probability_metrics(probabilities[v], actual) for v in ALL_VARIANTS
        }
        per_fold.append(
            {
                "drawing_number": fold["drawing_number"],
                "metrics": metrics,
                "A4_minus_A0": {
                    k: _delta(metrics["A4"], metrics["A0"], k)
                    for k in ("log_loss", "brier", "ece", "draw_brier", "top_correct")
                },
            }
        )
        bootstrap_inputs.append(
            {"A0": probabilities["A0"], "A4": probabilities["A4"], "labels": actual}
        )
        labels.extend(actual)
        for v in ALL_VARIANTS:
            flat[v].extend(probabilities[v])
        for model in prediction["models"].values():
            fits_complete = fits_complete and model["status"] != "FIT_BUDGET_EXHAUSTED"
            configs.append(model["config"])
    _check(all(c == configs[0] for c in configs), "same predeclared training config")
    metrics = {v: probability_metrics(flat[v], labels) for v in ALL_VARIANTS}
    subsets = {}
    for name, choice in (("covered_events", True), ("missing_events", False)):
        indices = [i for i, flag in enumerate(covered) if flag == choice]
        subsets[name] = {
            v: probability_metrics(
                [flat[v][i] for i in indices], [labels[i] for i in indices]
            )
            for v in ALL_VARIANTS
        }
    paired = {
        name: {
            k: _delta(metrics[a], metrics[b], k)
            for k in (
                "log_loss",
                "brier",
                "ece",
                "draw_brier",
                "non_draw_log_loss",
                "top_correct",
            )
        }
        for name, a, b in (
            ("A4_minus_A0", "A4", "A0"),
            ("A3_minus_A2", "A3", "A2"),
            ("A4_minus_A5", "A4", "A5"),
            ("A4_minus_A3", "A4", "A3"),
        )
    }
    coverage = sum(covered) / len(covered)
    predicates = {
        "seven_folds_105_events": len(folds) == 7 and len(labels) == 105,
        "historical_expected_drawings": training_domain == "SYNTHETIC_TEST_ONLY"
        or numbers == list(range(4990, 4997)),
        "full_feature_coverage_at_least_70_percent": coverage >= 0.70,
        "aggregate_log_loss": _le(paired["A4_minus_A0"]["log_loss"], -0.0015),
        "aggregate_brier": _le(paired["A4_minus_A0"]["brier"], -0.0010),
        "aggregate_ece": _le(paired["A4_minus_A0"]["ece"], 0.0),
        "top_correct_count": _le(-paired["A4_minus_A0"]["top_correct"], 1),
        "fold_log_loss_stability": all(
            _le(f["A4_minus_A0"]["log_loss"], 0.020) for f in per_fold
        ),
        "fold_brier_stability": all(
            _le(f["A4_minus_A0"]["brier"], 0.010) for f in per_fold
        ),
        "mandatory_missing_exact_bk": fallback_ok,
        "missing_ablation_A4_vs_A3": _le(paired["A4_minus_A3"]["log_loss"], 0.0010),
        "fit_runtime_completed": fits_complete,
    }
    draw_checks = {}
    for calibrated, no_draw in (("A3", "A2"), ("A4", "A5")):
        checks = {
            "draw_brier_vs_BK": _le(
                _delta(metrics[calibrated], metrics["A0"], "draw_brier"), -0.0010
            ),
            "non_draw_log_loss_vs_BK": _le(
                _delta(metrics[calibrated], metrics["A0"], "non_draw_log_loss"), 0.0010
            ),
            "log_loss_vs_no_draw": _le(
                _delta(metrics[calibrated], metrics[no_draw], "log_loss"), 0.0
            ),
        }
        draw_checks[calibrated] = checks
        predicates[calibrated + "_draw_block"] = all(checks.values())
    passed = all(predicates.values())
    return seal(
        {
            "kind": "SPORTS_V3_F4_EVALUATION",
            "training_domain": training_domain,
            "status": (
                "SYNTHETIC_SCREEN_ONLY"
                if training_domain == "SYNTHETIC_TEST_ONLY"
                else "PASS_RESEARCH_ONLY"
                if passed
                else "FAIL_CLOSED"
            ),
            "fold_count": len(folds),
            "event_count": len(labels),
            "coverage": coverage,
            "coverage_definition": (
                "all53 numeric features and reviewed common source/identity; "
                "denominator includes every event"
            ),
            "scope_receipt": scope_receipt,
            "expected_scope_receipt_sha256": expected_scope_receipt_sha256,
            "folds": folds,
            "model_config": configs[0],
            "metrics": metrics,
            "subsets": subsets,
            "per_fold": per_fold,
            "paired_deltas": paired,
            "draw_checks": draw_checks,
            "gate_predicates": predicates,
            "failed_predicates": [k for k, ok in predicates.items() if not ok],
            "draw_calibration_screen_passed": all(
                all(c.values()) for c in draw_checks.values()
            ),
            "draw_calibration_disposition": "REVIEW_ONLY"
            if all(all(c.values()) for c in draw_checks.values())
            else "DISABLE_FOR_CANDIDACY_NO_SILENT_VARIANT_SWITCH",
            "bootstrap": paired_cluster_bootstrap(bootstrap_inputs),
            "leakage_violation_count": 0,
            "numerical_integrity_rows": len(labels),
            "prospective_requirement": {"drawings": 30, "events": 450},
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
            "profitability_proven": False,
        }
    )


def build_f4_gate(report):
    """Recompute all metrics/predicates; never accept a declared PASS alone."""
    _sealed(report)
    recomputed = evaluate_f4(
        report["folds"],
        training_domain=report["training_domain"],
        scope_receipt=report["scope_receipt"],
        expected_scope_receipt_sha256=report["expected_scope_receipt_sha256"],
    )
    _check(recomputed == report, "F4 report recomputation mismatch")
    return seal(
        {
            "kind": "SPORTS_V3_F4_PROBABILITY_GATE",
            "status": report["status"],
            "model_version": MODEL_VERSION,
            "model_config_sha256": digest(report["model_config"]),
            "feature_schema_sha256": digest(FEATURE_NAMES),
            "fold_count": report["fold_count"],
            "event_count": report["event_count"],
            "coverage": report["coverage"],
            "leakage_violation_count": report["leakage_violation_count"],
            "evaluation_report_sha256": report["sha256"],
            "evaluation_report": report,
            "activation_allowed": False,
            "operator_compatible": False,
            "automatic_wagering": False,
        }
    )


def validate_f4_gate(gate, expected_report_sha256):
    _sealed(gate)
    _check(
        isinstance(gate.get("evaluation_report"), dict)
        and isinstance(expected_report_sha256, str),
        "independent F4 report required",
    )
    _check(
        gate["evaluation_report_sha256"] == expected_report_sha256,
        "independent F4 review receipt binding",
    )
    _check(
        build_f4_gate(gate["evaluation_report"]) == gate,
        "F4 gate recomputation mismatch",
    )
    _check(gate["status"] == "PASS_RESEARCH_ONLY", "F4 probability screen not passed")
