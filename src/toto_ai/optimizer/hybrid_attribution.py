"""Event-level attribution for settled equal-input hybrid replays.

The report is descriptive research output.  It separates probability-ranking
errors from package-exposure errors without claiming that either signal is a
causal explanation or a profitability result.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import secrets
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from toto_ai.optimizer.uncertainty_package import outcome_exposure

OUTCOMES = ("1", "X", "2")
VOID_RESULT = "*"
STATUS = "RESEARCH_ONLY_NOT_OPERATOR_COMPATIBLE"
ARTIFACT_CLASS = "HYBRID_EVENT_LEVEL_ATTRIBUTION"
_TOLERANCE = 1e-12


def build_hybrid_event_attribution(
    *,
    drawing_id: int,
    drawing_number: int,
    plan_id: str,
    event_names: Sequence[str],
    actual: str,
    probability_models: Mapping[str, Sequence[Sequence[float]]],
    packages: Mapping[str, Sequence[str]],
    sports_events: Sequence[Any],
    source_hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Attribute one settled replay at probability and package levels."""

    if type(drawing_id) is not int or drawing_id <= 0:
        raise ValueError("drawing_id must be a positive integer")
    if type(drawing_number) is not int or drawing_number <= 0:
        raise ValueError("drawing_number must be a positive integer")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValueError("plan_id must be non-empty")
    names = tuple(event_names)
    if len(names) != 15 or any(not name.strip() for name in names):
        raise ValueError("attribution requires exactly 15 named events")
    if len(actual) != 15 or set(actual) - (set(OUTCOMES) | {VOID_RESULT}):
        raise ValueError("actual result must contain 15 terminal outcomes")
    models = {
        name: _probability_matrix(rows, label=name)
        for name, rows in probability_models.items()
    }
    if "bk" not in models or "sports_v2" not in models:
        raise ValueError("attribution requires bk and sports_v2 models")
    normalized_packages = {
        name: _package(coupons, label=name) for name, coupons in packages.items()
    }
    if (
        "quality-v2" not in normalized_packages
        or "sports-v2" not in normalized_packages
    ):
        raise ValueError("attribution requires quality-v2 and sports-v2 packages")
    sports_by_order = _sports_events(sports_events)
    hashes = _source_hashes(source_hashes, packages=normalized_packages)

    package_exposures = {
        name: outcome_exposure(coupons)
        for name, coupons in normalized_packages.items()
    }
    best_coupons = {
        name: _best_coupons(coupons, actual)
        for name, coupons in normalized_packages.items()
    }
    rows: list[dict[str, Any]] = []
    for event_order, (event_name, observed) in enumerate(
        zip(names, actual, strict=True)
    ):
        excluded = observed == VOID_RESULT
        model_rows = {
            name: _model_event_payload(matrix[event_order], observed)
            for name, matrix in models.items()
        }
        sports_event = sports_by_order[event_order]
        sports_effect = _sports_effect_payload(
            observed=observed,
            bk=model_rows["bk"],
            sports=model_rows["sports_v2"],
            sports_event=sports_event,
        )
        strategy_rows = {
            name: _strategy_event_payload(
                exposure=package_exposures[name][event_order],
                best_coupons=best_coupons[name]["coupons"],
                observed=observed,
                event_order=event_order,
            )
            for name in normalized_packages
        }
        qv2_diagnosis = _diagnosis(
            excluded=excluded,
            model=model_rows["bk"],
            strategy=strategy_rows["quality-v2"],
        )
        sports_diagnosis = _diagnosis(
            excluded=excluded,
            model=model_rows["sports_v2"],
            strategy=strategy_rows["sports-v2"],
        )
        rows.append(
            {
                "event_order": event_order,
                "position": event_order + 1,
                "event_name": event_name,
                "actual_outcome": None if excluded else observed,
                "excluded_as_void": excluded,
                "models": model_rows,
                "sports_v2_change": sports_effect,
                "strategies": strategy_rows,
                "diagnosis": {
                    "quality-v2-vs-bk": qv2_diagnosis,
                    "sports-v2-vs-sports-model": sports_diagnosis,
                },
            }
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "status": STATUS,
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "plan_id": plan_id,
        "actual_result_sha256": hashlib.sha256(actual.encode("ascii")).hexdigest(),
        "source_hashes": hashes,
        "summary": _summary(rows, best_coupons),
        "events": rows,
        "diagnostic_policy": (
            "ranking and exposure attribution is descriptive, not causal; "
            "VOID events are excluded"
        ),
        "automatic_wagering": False,
        "operator_compatible": False,
        "scheduler_state_mutated": False,
        "profitability_proven": False,
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def write_hybrid_event_attribution(
    report: Mapping[str, Any],
    *,
    output_dir: str | Path,
) -> Mapping[str, Path]:
    """Write deterministic JSON, CSV and Markdown attribution views."""

    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("attribution output directory must be regular")
    paths = {
        "json": output / "historical-hybrid-attribution.json",
        "csv": output / "historical-hybrid-attribution-events.csv",
        "markdown": output / "historical-hybrid-attribution.md",
    }
    _write_replace(paths["json"], _pretty(report))
    _write_replace(paths["csv"], _csv(report).encode("utf-8"))
    _write_replace(paths["markdown"], _markdown(report).encode("utf-8"))
    return paths


def _probability_matrix(
    rows: Sequence[Sequence[float]],
    *,
    label: str,
) -> tuple[tuple[float, float, float], ...]:
    matrix = tuple(tuple(float(value) for value in row) for row in rows)
    if len(matrix) != 15 or any(len(row) != 3 for row in matrix):
        raise ValueError(f"{label} probability matrix must be 15x3")
    normalized = []
    for row in matrix:
        if any(not math.isfinite(value) or value < 0.0 for value in row):
            raise ValueError(f"{label} probability row is invalid")
        total = math.fsum(row)
        if total <= 0.0:
            raise ValueError(f"{label} probability row is empty")
        normalized.append(tuple(value / total for value in row))
    return tuple(normalized)


def _package(coupons: Sequence[str], *, label: str) -> tuple[str, ...]:
    package = tuple(coupons)
    if not package:
        raise ValueError(f"{label} package must not be empty")
    if any(len(coupon) != 15 or set(coupon) - set(OUTCOMES) for coupon in package):
        raise ValueError(f"{label} package contains an invalid coupon")
    if len(set(package)) != len(package):
        raise ValueError(f"{label} package contains duplicate coupons")
    return package


def _sports_events(events: Sequence[Any]) -> Mapping[int, Any]:
    result: dict[int, Any] = {}
    for event in events:
        order = getattr(event, "event_order", None)
        if type(order) is not int or order not in range(15) or order in result:
            raise ValueError("sports event order is invalid")
        result[order] = event
    if set(result) != set(range(15)):
        raise ValueError("attribution requires 15 Sports v2 event rows")
    return result


def _source_hashes(
    values: Mapping[str, str],
    *,
    packages: Mapping[str, Sequence[str]],
) -> Mapping[str, str]:
    result = dict(values)
    for name, coupons in packages.items():
        expected = hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()
        key = f"package:{name}"
        declared = result.get(key)
        if declared is not None and declared != expected:
            raise ValueError(f"{name} package SHA-256 mismatch")
        result[key] = expected
    for name, value in result.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("attribution source hashes must be lowercase SHA-256")
    return dict(sorted(result.items()))


def _model_event_payload(row: Sequence[float], observed: str) -> dict[str, Any]:
    probabilities = dict(zip(OUTCOMES, row, strict=True))
    top_probability = max(probabilities.values())
    top_outcomes = [
        outcome
        for outcome, probability in probabilities.items()
        if math.isclose(probability, top_probability, rel_tol=0.0, abs_tol=_TOLERANCE)
    ]
    if observed == VOID_RESULT:
        return {
            "probabilities": probabilities,
            "top_outcomes": top_outcomes,
            "top_probability": top_probability,
            "actual_probability": None,
            "actual_rank": None,
            "top_correct": None,
        }
    actual_probability = probabilities[observed]
    rank = 1 + sum(
        probability > actual_probability + _TOLERANCE
        for probability in probabilities.values()
    )
    return {
        "probabilities": probabilities,
        "top_outcomes": top_outcomes,
        "top_probability": top_probability,
        "actual_probability": actual_probability,
        "actual_rank": rank,
        "top_correct": observed in top_outcomes,
    }


def _sports_effect_payload(
    *,
    observed: str,
    bk: Mapping[str, Any],
    sports: Mapping[str, Any],
    sports_event: Any,
) -> dict[str, Any]:
    fallback_reason = getattr(sports_event, "fallback_reason", None)
    blend_weight = float(getattr(sports_event, "blend_weight", 0.0))
    if observed == VOID_RESULT:
        effect = "VOID_EXCLUDED"
        delta = None
        rank_delta = None
    else:
        delta = sports["actual_probability"] - bk["actual_probability"]
        rank_delta = sports["actual_rank"] - bk["actual_rank"]
        if fallback_reason is not None:
            effect = "FALLBACK"
        elif delta > _TOLERANCE:
            effect = "HELPED_ACTUAL_PROBABILITY"
        elif delta < -_TOLERANCE:
            effect = "HURT_ACTUAL_PROBABILITY"
        else:
            effect = "UNCHANGED"
    if observed == VOID_RESULT:
        top_effect = "VOID_EXCLUDED"
    elif fallback_reason is not None:
        top_effect = "FALLBACK"
    elif not bk["top_correct"] and sports["top_correct"]:
        top_effect = "CORRECTED_TOP_MISS"
    elif bk["top_correct"] and not sports["top_correct"]:
        top_effect = "BROKE_CORRECT_TOP"
    elif bk["top_correct"]:
        top_effect = "RETAINED_CORRECT_TOP"
    else:
        top_effect = "RETAINED_TOP_MISS"
    return {
        "covered": fallback_reason is None and blend_weight > 0.0,
        "fallback_reason": fallback_reason,
        "blend_weight": blend_weight,
        "actual_probability_delta_vs_bk": delta,
        "actual_rank_delta_vs_bk": rank_delta,
        "effect": effect,
        "top_prediction_effect": top_effect,
    }


def _best_coupons(coupons: Sequence[str], actual: str) -> dict[str, Any]:
    resolved_orders = tuple(
        order for order, outcome in enumerate(actual) if outcome != VOID_RESULT
    )
    scores = tuple(
        sum(coupon[order] == actual[order] for order in resolved_orders)
        for coupon in coupons
    )
    best_hits = max(scores)
    selected = tuple(
        coupon
        for coupon, score in zip(coupons, scores, strict=True)
        if score == best_hits
    )
    return {
        "best_hits": best_hits,
        "best_coupon_count": len(selected),
        "coupons": selected,
    }


def _strategy_event_payload(
    *,
    exposure: Mapping[str, Any],
    best_coupons: Sequence[str],
    observed: str,
    event_order: int,
) -> dict[str, Any]:
    counts = dict(exposure["counts"])
    shares = dict(exposure["shares"])
    if observed == VOID_RESULT:
        return {
            "counts": counts,
            "shares": shares,
            "actual_count": None,
            "actual_share": None,
            "actual_exposure_rank": None,
            "actual_is_max_exposure": None,
            "actual_exposure_gap_to_max": None,
            "zero_actual_exposure": None,
            "fixed_wrong": None,
            "best_coupon_count": len(best_coupons),
            "best_coupon_miss_count": None,
            "best_coupon_miss_share": None,
            "best_coupon_universal_miss": None,
        }
    actual_count = counts[observed]
    actual_share = shares[observed]
    max_share = max(shares.values())
    miss_count = sum(coupon[event_order] != observed for coupon in best_coupons)
    unique_outcomes = sum(count > 0 for count in counts.values())
    return {
        "counts": counts,
        "shares": shares,
        "actual_count": actual_count,
        "actual_share": actual_share,
        "actual_exposure_rank": 1
        + sum(share > actual_share + _TOLERANCE for share in shares.values()),
        "actual_is_max_exposure": math.isclose(
            actual_share, max_share, rel_tol=0.0, abs_tol=_TOLERANCE
        ),
        "actual_exposure_gap_to_max": max_share - actual_share,
        "zero_actual_exposure": actual_count == 0,
        "fixed_wrong": unique_outcomes == 1 and actual_count == 0,
        "best_coupon_count": len(best_coupons),
        "best_coupon_miss_count": miss_count,
        "best_coupon_miss_share": miss_count / len(best_coupons),
        "best_coupon_universal_miss": miss_count == len(best_coupons),
    }


def _diagnosis(
    *,
    excluded: bool,
    model: Mapping[str, Any],
    strategy: Mapping[str, Any],
) -> str:
    if excluded:
        return "VOID_EXCLUDED"
    probability_miss = not model["top_correct"]
    package_miss = not strategy["actual_is_max_exposure"]
    if probability_miss and package_miss:
        return "JOINT_PROBABILITY_AND_PACKAGE_MISS"
    if probability_miss:
        return "PROBABILITY_RANKING_MISS"
    if package_miss:
        return "PACKAGE_ALIGNMENT_MISS"
    return "NO_RANKING_OR_ALIGNMENT_MISS"


def _summary(
    events: Sequence[Mapping[str, Any]],
    best_coupons: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    resolved = tuple(event for event in events if not event["excluded_as_void"])
    sports_effects = Counter(
        event["sports_v2_change"]["effect"] for event in resolved
    )
    sports_top_effects = Counter(
        event["sports_v2_change"]["top_prediction_effect"] for event in resolved
    )
    diagnoses = {
        name: dict(
            sorted(
                Counter(event["diagnosis"][name] for event in resolved).items()
            )
        )
        for name in ("quality-v2-vs-bk", "sports-v2-vs-sports-model")
    }
    strategies = {}
    for name in best_coupons:
        rows = tuple(event["strategies"][name] for event in resolved)
        strategies[name] = {
            "best_hits": best_coupons[name]["best_hits"],
            "best_coupon_count": best_coupons[name]["best_coupon_count"],
            "average_actual_exposure": (
                None
                if not rows
                else math.fsum(row["actual_share"] for row in rows) / len(rows)
            ),
            "zero_actual_exposure_positions": [
                event["position"]
                for event in resolved
                if event["strategies"][name]["zero_actual_exposure"]
            ],
            "fixed_wrong_positions": [
                event["position"]
                for event in resolved
                if event["strategies"][name]["fixed_wrong"]
            ],
            "best_coupon_universal_miss_positions": [
                event["position"]
                for event in resolved
                if event["strategies"][name]["best_coupon_universal_miss"]
            ],
        }
    return {
        "resolved_event_count": len(resolved),
        "void_event_positions": [
            event["position"] for event in events if event["excluded_as_void"]
        ],
        "bk_top_correct_count": sum(
            event["models"]["bk"]["top_correct"] for event in resolved
        ),
        "sports_v2_top_correct_count": sum(
            event["models"]["sports_v2"]["top_correct"] for event in resolved
        ),
        "sports_v2_effect_counts": dict(sorted(sports_effects.items())),
        "sports_v2_top_effect_counts": dict(sorted(sports_top_effects.items())),
        "diagnosis_counts": diagnoses,
        "strategies": strategies,
    }


def _csv(report: Mapping[str, Any]) -> str:
    strategies = tuple(report["summary"]["strategies"])
    fields = [
        "drawing_number",
        "position",
        "event_name",
        "actual_outcome",
        "excluded_as_void",
        "bk_actual_probability",
        "bk_actual_rank",
        "bk_top_correct",
        "sports_actual_probability",
        "sports_actual_rank",
        "sports_top_correct",
        "sports_effect",
        "sports_top_prediction_effect",
        "sports_actual_probability_delta",
        "quality_v2_diagnosis",
        "sports_v2_diagnosis",
    ]
    for strategy in strategies:
        fields.extend(
            (
                f"{strategy}_actual_share",
                f"{strategy}_actual_exposure_rank",
                f"{strategy}_zero_actual_exposure",
                f"{strategy}_best_coupon_universal_miss",
            )
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for event in report["events"]:
        row = {
            "drawing_number": report["drawing_number"],
            "position": event["position"],
            "event_name": event["event_name"],
            "actual_outcome": event["actual_outcome"],
            "excluded_as_void": event["excluded_as_void"],
            "bk_actual_probability": event["models"]["bk"]["actual_probability"],
            "bk_actual_rank": event["models"]["bk"]["actual_rank"],
            "bk_top_correct": event["models"]["bk"]["top_correct"],
            "sports_actual_probability": event["models"]["sports_v2"][
                "actual_probability"
            ],
            "sports_actual_rank": event["models"]["sports_v2"]["actual_rank"],
            "sports_top_correct": event["models"]["sports_v2"]["top_correct"],
            "sports_effect": event["sports_v2_change"]["effect"],
            "sports_top_prediction_effect": event["sports_v2_change"][
                "top_prediction_effect"
            ],
            "sports_actual_probability_delta": event["sports_v2_change"][
                "actual_probability_delta_vs_bk"
            ],
            "quality_v2_diagnosis": event["diagnosis"]["quality-v2-vs-bk"],
            "sports_v2_diagnosis": event["diagnosis"][
                "sports-v2-vs-sports-model"
            ],
        }
        for strategy in strategies:
            payload = event["strategies"][strategy]
            row[f"{strategy}_actual_share"] = payload["actual_share"]
            row[f"{strategy}_actual_exposure_rank"] = payload[
                "actual_exposure_rank"
            ]
            row[f"{strategy}_zero_actual_exposure"] = payload[
                "zero_actual_exposure"
            ]
            row[f"{strategy}_best_coupon_universal_miss"] = payload[
                "best_coupon_universal_miss"
            ]
        writer.writerow(row)
    return output.getvalue()


def _markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Hybrid event attribution: {report['drawing_number']}",
        "",
        "**RESEARCH ONLY — NOT FOR WAGERING OR UPLOAD**",
        "",
        f"- Resolved events: {summary['resolved_event_count']}",
        f"- BK top correct: {summary['bk_top_correct_count']}",
        f"- Sports v2 top correct: {summary['sports_v2_top_correct_count']}",
        "- Sports v2 changes: `"
        f"{json.dumps(summary['sports_v2_effect_counts'], sort_keys=True)}`",
        "",
        "| # | Event | Actual | BK rank | Sports rank | Sports effect | "
        "QV2 diagnosis |",
        "|---:|---|:---:|---:|---:|---|---|",
    ]
    for event in report["events"]:
        lines.append(
            f"| {event['position']} | {event['event_name']} | "
            f"{event['actual_outcome'] or 'VOID'} | "
            f"{event['models']['bk']['actual_rank'] or '—'} | "
            f"{event['models']['sports_v2']['actual_rank'] or '—'} | "
            f"{event['sports_v2_change']['effect']} | "
            f"{event['diagnosis']['quality-v2-vs-bk']} |"
        )
    lines.extend(("", "This attribution does not establish profitability.", ""))
    return "\n".join(lines)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _pretty(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_replace(path: Path, content: bytes) -> None:
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("attribution output path cannot traverse a symlink")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
