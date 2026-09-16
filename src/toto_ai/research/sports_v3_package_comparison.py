"""JOB B: isolated frozen-probability research package plumbing, never live.

Selects TOP COUPON PRODUCT PROBABILITY, not quality-v2 or union-P13 optimization.
Late research captures cannot enter FrozenStrategyInput's pre-deadline domain;
reuse its unchanged numerical selector, never forge admissible timestamps.
"""

import hashlib
import json
import signal
import threading
import time
from dataclasses import asdict
from pathlib import Path

from toto_ai.optimizer.coupon_probabilities import top_probability_coupons
from toto_ai.research import sports_v3_retrospective_predict as predictor
from toto_ai.research.closed_market_scenario_replay import validate_input
from toto_ai.research.package_selection_diagnostics import evaluate_fixed_package
from toto_ai.sports_stats.v3_probability import (
    _bk,
    _check,
    _hash,
    _sealed,
    digest,
    seal,
)

REQUEST_KIND = "FROZEN_SPORTS_V3_PACKAGE_RESEARCH_REQUEST_V1"
SELECTION = "TOP_COUPON_PRODUCT_PROBABILITY"
FLAGS = dict(
    operator_compatible=False,
    automatic_wagering=False,
    activation_allowed=False,
    profitability_proven=False,
    blind_holdout=False,
)
SEED = "JOB-B-fixed-product-package-independent-evaluation-v1"


def select_package(matrix):
    _check(len(matrix) == 15, "fifteen-event probability matrix")
    matrix = tuple(_bk(row) for row in matrix)
    coupons = tuple(top_probability_coupons(matrix, limit=166))
    _check(
        len(coupons) == len(set(coupons)) == 166
        and all(len(c) == 15 and not set(c) - set("1X2") for c in coupons),
        "166 unique coupons",
    )
    return coupons


def bind_rows(scenario, rows):
    native = validate_input(scenario)
    drawing = scenario["market"]["number"]
    selected = [r for r in rows if r["drawing_number"] == drawing]
    _check(
        [r["event_order"] for r in selected] == list(range(15)),
        "ordered complete prediction roster",
    )
    bk = tuple(tuple(row) for row in native.ev.true_probabilities)
    mixed, applied, changed, reasons = [], 0, 0, []
    for i, (event, row) in enumerate(
        zip(scenario["market"]["events"], selected, strict=True)
    ):
        _check(
            row["target_event_id"] == event["id"]
            and row["bk_input_sha256"] == scenario["sha256"]
            and tuple(row["bk_probabilities"]) == bk[i],
            "source/input/BK identity binding",
        )
        probabilities = _bk(row["probabilities"])
        _check(
            sum(abs(a - b) for a, b in zip(probabilities, bk[i], strict=True)) <= 0.2,
            "Sports L1 cap",
        )
        _check(row["status"] in {"SPORTS_APPLIED", "BK_FALLBACK"}, "prediction status")
        if row["status"] == "BK_FALLBACK":
            _check(
                probabilities == bk[i] and row["reliability"] == 0.0,
                "exact BK fallback",
            )
            reasons.append(
                dict(event_order=i, reason=row["fallback_or_application_reason"])
            )
        else:
            _hash(row["feature_sha256"])
            _check(
                bool(row["provider_fixture_id"]) and 0 < row["reliability"] <= 0.2,
                "approved Sports feature identity/reliability",
            )
            applied += 1
        changed += probabilities != bk[i]
        mixed.append(probabilities)
    return (
        bk,
        tuple(mixed),
        dict(
            denominator=15,
            sports_applied=applied,
            changed_probability_rows=changed,
            bk_fallback=15 - applied,
            fallback_reasons=reasons,
        ),
    )


def _sports(root, request, scenario):
    def read(ref):
        return predictor.read_checked(root, ref["path"], ref["file_sha256"])

    pred = read(request["sports_predictions"])
    _sealed(pred)
    _check(
        pred["kind"] == predictor.KIND and all(pred[k] is False for k in FLAGS),
        "non-operator prediction contract",
    )
    _check(
        pred["sha256"] == request["sports_predictions"]["payload_sha256"],
        "prediction payload hash",
    )
    freeze = read(request["prediction_freeze"])
    _check(
        freeze["status"] == "PREDICTIONS_FROZEN_BEFORE_LABELS"
        and freeze["prediction_file_sha256"]
        == request["sports_predictions"]["file_sha256"]
        and freeze["prediction_payload_sha256"] == pred["sha256"]
        and freeze["labels_read"] is False
        and freeze["fit_executed"] is False,
        "pre-label prediction freeze binding",
    )
    model = read(request["model"])
    predictor.validate_model(model)
    _check(
        model["sha256"]
        == pred["model_payload_sha256"]
        == request["model"]["payload_sha256"]
        and request["model"]["file_sha256"] == pred["model_file_sha256"],
        "model hash roles",
    )
    pred_request = request["prediction_request"]
    _check(
        pred_request["file_sha256"]
        == pred["request_file_sha256"]
        == freeze["request_file_sha256"],
        "prediction request binding",
    )
    _check(
        pred["adapter_file_sha256"]
        == hashlib.sha256(Path(predictor.__file__).read_bytes()).hexdigest(),
        "frozen predictor code binding",
    )
    # Deterministic inference-only verification of already frozen probabilities.
    # No optimizer fit, labels, new prediction output or source mutation.
    verified = predictor.predict_request(
        root, pred_request["path"], pred_request["file_sha256"]
    )
    _check(
        verified["rows"] == pred["rows"]
        and verified["model_payload_sha256"] == model["sha256"],
        "identity/provenance/numerical prediction replay mismatch",
    )
    bk, mixed, coverage = bind_rows(scenario, pred["rows"])
    return bk, mixed, coverage


def _write(path, value):
    data = (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    with Path(path).open("xb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def _evaluate(coupons, models):
    return asdict(
        evaluate_fixed_package(
            coupons=coupons,
            probability_models=models,
            category=13,
            selection_seed_material=SEED,
            selection_sample_count=2048,
            evaluation_sample_count=8192,
        )
    )


def compare_frozen_predictions(
    request_path, output_dir, max_seconds=60, *, expected_request_sha256, root=None
):
    """One bounded, non-overwriting paired research attempt; no live side effects."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    _check(
        type(max_seconds) in (int, float) and 0 < max_seconds <= 60,
        "wall budget 0..60s",
    )
    _check(
        threading.current_thread() is threading.main_thread(),
        "run bounded pilot in main thread",
    )
    _check(
        signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
        "existing process timer must not be overwritten",
    )
    request = predictor.read_checked(root, request_path, expected_request_sha256)
    _check(
        request["kind"] == REQUEST_KIND
        and request["selection"] == SELECTION
        and (request["bank"], request["stake"], request["category"], request["count"])
        == (4980, 30, 13, 166),
        "research package contract",
    )
    scenario = predictor.read_checked(
        root,
        request["scenario_input"]["path"],
        request["scenario_input"]["file_sha256"],
    )
    native = validate_input(scenario)
    _check(
        scenario["market"]["number"] == request["drawing_number"],
        "requested drawing binding",
    )
    out = predictor._path(root, output_dir)
    out.mkdir(exist_ok=False, parents=True)
    started = time.perf_counter()
    result = dict(
        kind="FROZEN_SPORTS_V3_RESEARCH_PACKAGE_COMPARISON_V1",
        status="IN_PROGRESS",
        selection=SELECTION,
        category=13,
        selection_is_union_optimizer=False,
        bank=4980,
        stake=30,
        count=166,
        drawing_number=request["drawing_number"],
        scenario_input_file_sha256=request["scenario_input"]["file_sha256"],
        scenario_input_payload_sha256=scenario["sha256"],
        request_file_sha256=expected_request_sha256,
        source_captured_at=scenario["captured_at"],
        source_closed_at=scenario["source_closed_at"],
        quote_available_at=scenario["quote_available_at"],
        evidence_grade="UNVERIFIED_ASOF_SENSITIVITY",
        pool_crowd_source_sha256=digest(scenario["market"]),
        packages={},
        evaluations={},
        sports_status="NOT_CHECKED",
        actual_results_read=False,
        fit_executed=False,
        common_evaluation_seed=SEED,
        deterministic_selector_seed=None,
        max_seconds=max_seconds,
        **FLAGS,
    )

    def note(phase):
        print(
            json.dumps(
                dict(phase=phase, elapsed_seconds=time.perf_counter() - started)
            ),
            flush=True,
        )

    def alarm(signum, frame):
        raise TimeoutError("research package hard wall deadline")

    def package(arm, matrix):
        note("select_" + arm)
        coupons = select_package(matrix)
        obj = seal(
            dict(
                kind="RESEARCH_COUPON_STRINGS_NOT_BET_UPLOAD",
                arm=arm,
                coupons=list(coupons),
                predictor_matrix_sha256=digest(matrix),
                count=166,
                stake=30,
                cost=4980,
                selection=SELECTION,
                **FLAGS,
            )
        )
        physical = _write(out / (arm + ".json"), obj)
        result["packages"][arm] = dict(
            path=str(out / (arm + ".json")),
            file_sha256=physical,
            payload_sha256=obj["sha256"],
            count=166,
            cost=4980,
            predictor_matrix_sha256=digest(matrix),
        )
        return coupons

    previous = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max_seconds)
    try:
        bk = tuple(tuple(r) for r in native.ev.true_probabilities)
        bk_coupons = package("BK", bk)
        try:
            _, mixed, coverage = _sports(root, request, scenario)
        except (ValueError, KeyError, TypeError, OSError) as error:
            result["sports_status"] = "SKIPPED_MISSING_OR_INVALID_SPORTS"
            result["sports_error"] = f"{type(error).__name__}: {error}"
            mixed = None
        else:
            result["coverage"] = coverage
            result["sports_status"] = (
                "VALIDATED_SPORTS_APPLIED"
                if coverage["sports_applied"]
                else "VALIDATED_ALL_BK_FALLBACK"
            )
            mixed_coupons = package("MIXED_V3", mixed)
            result["same_coupon_set"] = set(bk_coupons) == set(mixed_coupons)
            result["common_coupon_count"] = len(set(bk_coupons) & set(mixed_coupons))
        models = {"COMMON_BK": bk}
        if mixed is not None:
            models["COMMON_MIXED_V3"] = mixed
        else:
            # The evaluator requires two names; this is still one BK forecast.
            # Preserve COMMON_BK and its seed; never invent a Sports reference.
            models["COMMON_BK_API_ALIAS"] = bk
            result["diagnostic_semantics"] = dict(
                distinct_forecast_count=1,
                reference_model="COMMON_BK",
                api_aliases={"COMMON_BK_API_ALIAS": "COMMON_BK"},
                alias_purpose=(
                    "Identical BK control matrix satisfying evaluator API arity; "
                    "technical alias, not a second forecast or Sports model"
                ),
                alias_results_combined=False,
                training_stream_used_by_selector=False,
                training_fields_meaning=(
                    "training_* fields are diagnostic-only Monte Carlo streams; "
                    "the top-product selector does not train on these samples"
                ),
            )
        # BOTH packages are frozen before computing paired independent/exact metrics.
        note("evaluate_common_references")
        result["evaluations"]["BK"] = _evaluate(bk_coupons, models)
        if mixed is not None:
            result["evaluations"]["MIXED_V3"] = _evaluate(mixed_coupons, models)
        result["status"] = (
            "COMPLETE_PAIRED_RESEARCH"
            if mixed is not None
            else "BK_CONTROL_ONLY_SPORTS_SKIPPED"
        )
    except TimeoutError as error:
        result["status"] = "TIMED_OUT"
        result["error"] = str(error)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    result["runtime_seconds"] = time.perf_counter() - started
    result["code_sha256"] = {
        name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for name, path in {"adapter": __file__, "predictor": predictor.__file__}.items()
    }
    result = seal(result)
    _write(out / "comparison.json", result)
    note(result["status"])
    return result
