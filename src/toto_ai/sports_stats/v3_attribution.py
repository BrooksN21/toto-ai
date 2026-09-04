"""Canonical leakage-safe attribution aggregate for Sports Analytics v3."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_MODELS = ("bk", "sports_v2")
_STRATEGIES = ("quality-v2", "sports-v2", "quality-v3", "robust")
_OUTCOMES = ("1", "X", "2")
_TOLERANCE = 1e-12


def build_v3_attribution_aggregate(
    report_paths: Sequence[str | Path],
    *,
    final_input_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Aggregate immutable settled attribution using outcomes only for evaluation."""

    sources = _load_attribution_sources(report_paths)
    final_inputs = _load_final_inputs(final_input_paths)
    events: list[dict[str, Any]] = []
    effect_counts: Counter[str] = Counter()
    transition_counts: Counter[str] = Counter()
    fallback_reason_counts: Counter[str] = Counter()
    diagnosis_counts: dict[str, Counter[str]] = defaultdict(Counter)
    strategy_accumulators = {
        strategy: _StrategyAccumulator() for strategy in _STRATEGIES
    }

    for source in sources:
        drawing = source["drawing_number"]
        final_input = final_inputs.get(drawing)
        for raw_event in source["events"]:
            excluded = raw_event.get("excluded_as_void") is True
            actual_value = raw_event.get("actual_outcome")
            if excluded:
                actual: str | None = None
            elif actual_value in _OUTCOMES:
                actual = str(actual_value)
            else:
                raise ValueError("resolved event actual outcome is invalid")

            raw_models = _mapping(raw_event.get("models"), "event models")
            probabilities = {
                model: _probabilities(
                    _mapping(raw_models.get(model), f"{model} model").get(
                        "probabilities"
                    )
                )
                for model in _MODELS
            }
            model_rows = {
                model: _model_event_payload(values, actual)
                for model, values in probabilities.items()
            }
            pre_draw = _pre_draw_payload(probabilities["bk"])
            league, league_status, league_reason = _exact_league(
                source=source,
                raw_event=raw_event,
                final_input=final_input,
            )
            sports_change = _mapping(
                raw_event.get("sports_v2_change"), "sports v2 change"
            )
            covered = sports_change.get("covered") is True
            fallback_reason = sports_change.get("fallback_reason")
            if not covered:
                reason = (
                    str(fallback_reason)
                    if isinstance(fallback_reason, str) and fallback_reason
                    else "UNSPECIFIED_FALLBACK"
                )
                fallback_reason_counts[reason] += int(not excluded)
            if not excluded:
                effect_counts[str(sports_change.get("effect"))] += 1
                transition_counts[str(sports_change.get("top_prediction_effect"))] += 1

            diagnosis = _mapping(raw_event.get("diagnosis"), "event diagnosis")
            if not excluded:
                for comparison, value in diagnosis.items():
                    diagnosis_counts[str(comparison)][str(value)] += 1

            strategies = _mapping(raw_event.get("strategies"), "event strategies")
            if not excluded:
                for strategy in _STRATEGIES:
                    strategy_accumulators[strategy].add(
                        _mapping(strategies.get(strategy), f"{strategy} strategy")
                    )

            event_order = _event_order(raw_event)
            events.append(
                {
                    "drawing_id": source["drawing_id"],
                    "drawing_number": drawing,
                    "plan_id": source["plan_id"],
                    "event_order": event_order,
                    "position": event_order + 1,
                    "event_name": _event_name(raw_event),
                    "actual_outcome": actual,
                    "excluded_as_void": excluded,
                    "league": league,
                    "league_status": league_status,
                    "league_missing_reason": league_reason,
                    "pre_draw": pre_draw,
                    "models": model_rows,
                    "sports_v2": {
                        "covered": covered,
                        "fallback_reason": fallback_reason,
                        "effect": sports_change.get("effect"),
                        "top_prediction_effect": sports_change.get(
                            "top_prediction_effect"
                        ),
                    },
                }
            )

    events.sort(key=lambda row: (row["drawing_number"], row["event_order"]))
    resolved = [event for event in events if not event["excluded_as_void"]]
    if not resolved:
        raise ValueError("attribution aggregate has no resolved events")
    model_metrics = {model: _model_metrics(resolved, model=model) for model in _MODELS}
    covered_count = sum(event["sports_v2"]["covered"] for event in resolved)
    mapped_count = sum(event["league_status"] == "MAPPED_EXACT" for event in events)
    missing_reasons = Counter(
        event["league_missing_reason"]
        for event in events
        if event["league_status"] != "MAPPED_EXACT"
    )
    report: dict[str, Any] = {
        "schema_version": 2,
        "artifact_class": "SPORTS_ANALYTICS_V3_ATTRIBUTION_AGGREGATE",
        "status": "RESEARCH_ONLY_NOT_ACTIVATED",
        "operator_compatible": False,
        "automatic_wagering": False,
        "profitability_proven": False,
        "drawings": [source["drawing_number"] for source in sources],
        "source_reports": [source["public_source"] for source in sources],
        "league_identity_sources": [
            final_inputs[drawing]["public_source"] for drawing in sorted(final_inputs)
        ],
        "source_files": sorted(
            [{"role": "attribution", **source["public_source"]} for source in sources]
            + [
                {"role": "final_input", **record["public_source"]}
                for record in final_inputs.values()
            ],
            key=lambda item: (item["drawing_number"], item["role"]),
        ),
        "event_count": len(events),
        "resolved_event_count": len(resolved),
        "void_event_count": len(events) - len(resolved),
        "events": events,
        "model_metrics": model_metrics,
        "sports_v2_minus_bk": _metric_delta(model_metrics),
        "sports_v2": {
            "covered_event_count": covered_count,
            "fallback_event_count": len(resolved) - covered_count,
            "coverage_rate": covered_count / len(resolved),
            "fallback_reason_counts": dict(sorted(fallback_reason_counts.items())),
            "effect_counts": dict(sorted(effect_counts.items())),
            "top_transition_counts": dict(sorted(transition_counts.items())),
        },
        "league_coverage": {
            "mapped_event_count": mapped_count,
            "missing_event_count": len(events) - mapped_count,
            "coverage_rate": mapped_count / len(events),
            "missing_reason_counts": dict(sorted(missing_reasons.items())),
        },
        "segments": _segments(resolved),
        "diagnosis_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(diagnosis_counts.items())
        },
        "strategy_exposure": {
            strategy: accumulator.payload()
            for strategy, accumulator in strategy_accumulators.items()
        },
        "evaluation_policy": (
            "Pre-draw probabilities, ranks, margins and entropy are recomputed "
            "only from frozen probability vectors. Actual outcomes are used only "
            "to score resolved-event evaluation metrics and evaluation segments."
        ),
        "interpretation": (
            "Descriptive settled evidence only; this report does not train, "
            "activate or select a probability model."
        ),
    }
    report["report_sha256"] = _payload_sha256(report)
    return report


def write_v3_attribution_aggregate(
    report: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path, Path]:
    """Write or verify canonical hash-bound JSON, CSV and Markdown views."""

    if report.get("report_sha256") != _payload_sha256(report):
        raise ValueError("sports v3 attribution report hash mismatch")
    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("sports v3 output directory must be regular")
    json_path = output / "attribution-aggregate.json"
    csv_path = output / "attribution-aggregate.csv"
    markdown_path = output / "attribution-aggregate.md"
    json_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_or_verify(json_path, json_bytes)
    _write_or_verify(csv_path, _csv_text(report).encode("utf-8"))
    _write_or_verify(markdown_path, _markdown_text(report).encode("utf-8"))
    return json_path, csv_path, markdown_path


def _load_attribution_sources(
    report_paths: Sequence[str | Path],
) -> list[dict[str, Any]]:
    if not report_paths:
        raise ValueError("at least one attribution report is required")
    sources: list[dict[str, Any]] = []
    seen_drawings: set[int] = set()
    for raw_path in report_paths:
        path, content, payload = _json_file(raw_path, "attribution report")
        if payload.get("artifact_class") != "HYBRID_EVENT_LEVEL_ATTRIBUTION":
            raise ValueError("unexpected attribution artifact class")
        declared_hash = payload.get("report_sha256")
        if not _is_sha256(declared_hash):
            raise ValueError("attribution report hash is missing or invalid")
        if declared_hash != _attribution_payload_sha256(payload):
            raise ValueError("attribution report hash mismatch")
        drawing = payload.get("drawing_number")
        drawing_id = payload.get("drawing_id")
        plan_id = payload.get("plan_id")
        if type(drawing) is not int or drawing <= 0 or drawing in seen_drawings:
            raise ValueError("attribution drawing number is invalid or duplicated")
        if type(drawing_id) is not int or drawing_id <= 0:
            raise ValueError("attribution drawing id is invalid")
        if not isinstance(plan_id, str) or not plan_id:
            raise ValueError("attribution plan id is invalid")
        raw_events = payload.get("events")
        if not isinstance(raw_events, list) or len(raw_events) != 15:
            raise ValueError("each attribution report must contain 15 events")
        events = [_mapping(event, "event") for event in raw_events]
        if {_event_order(event) for event in events} != set(range(15)):
            raise ValueError("attribution event orders must be exactly 0..14")
        events.sort(key=_event_order)
        seen_drawings.add(drawing)
        public_source = {
            "drawing_number": drawing,
            "path": str(path),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        sources.append(
            {
                "drawing_id": drawing_id,
                "drawing_number": drawing,
                "plan_id": plan_id,
                "source_hashes": _mapping(
                    payload.get("source_hashes"), "attribution source hashes"
                ),
                "events": events,
                "public_source": public_source,
            }
        )
    sources.sort(key=lambda item: item["drawing_number"])
    return sources


def _load_final_inputs(
    final_input_paths: Sequence[str | Path],
) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for raw_path in final_input_paths:
        path, content, payload = _json_file(raw_path, "final input")
        drawing = payload.get("drawing_number")
        if type(drawing) is not int or drawing <= 0 or drawing in records:
            raise ValueError("final-input drawing number is invalid or duplicated")
        data = _mapping(
            _mapping(payload.get("payload"), "final-input payload").get("data"),
            "final-input data",
        )
        raw_events = data.get("events")
        if not isinstance(raw_events, list) or len(raw_events) != 15:
            raise ValueError("final input must contain 15 events")
        events = {
            _final_event_order(event): _mapping(event, "final-input event")
            for event in raw_events
        }
        if set(events) != set(range(15)):
            raise ValueError("final-input event orders must be exactly 0..14")
        public_source = {
            "drawing_number": drawing,
            "path": str(path),
            "sha256": hashlib.sha256(content).hexdigest(),
            "snapshot_sha256": payload.get("snapshot_sha256"),
        }
        records[drawing] = {
            "drawing_id": payload.get("drawing_id"),
            "drawing_number": drawing,
            "plan_id": payload.get("plan_id"),
            "snapshot_sha256": payload.get("snapshot_sha256"),
            "payload_drawing_id": data.get("id"),
            "payload_drawing_number": data.get("number"),
            "events": events,
            "public_source": public_source,
        }
    return records


def _exact_league(
    *,
    source: Mapping[str, Any],
    raw_event: Mapping[str, Any],
    final_input: Mapping[str, Any] | None,
) -> tuple[str | None, str, str | None]:
    if final_input is None:
        return None, "MISSING", "FINAL_INPUT_NOT_PROVIDED"
    expected_snapshot = source["source_hashes"].get("final_input_sha256")
    if expected_snapshot != final_input.get("snapshot_sha256"):
        return None, "MISSING", "FINAL_INPUT_SNAPSHOT_MISMATCH"
    if (
        source["drawing_id"] != final_input.get("drawing_id")
        or source["drawing_number"] != final_input.get("drawing_number")
        or source["plan_id"] != final_input.get("plan_id")
        or source["drawing_id"] != final_input.get("payload_drawing_id")
        or source["drawing_number"] != final_input.get("payload_drawing_number")
    ):
        return None, "MISSING", "FINAL_INPUT_DRAWING_IDENTITY_MISMATCH"
    final_event = final_input["events"].get(_event_order(raw_event))
    if final_event is None or final_event.get("name") != _event_name(raw_event):
        return None, "MISSING", "FINAL_INPUT_EVENT_IDENTITY_MISMATCH"
    league = final_event.get("championship")
    if not isinstance(league, str) or not league.strip():
        return None, "MISSING", "FINAL_INPUT_LEAGUE_MISSING"
    return league.strip(), "MAPPED_EXACT", None


def _model_event_payload(
    probabilities: Mapping[str, float], actual: str | None
) -> dict[str, Any]:
    top_probability = max(probabilities.values())
    top_outcomes = [
        outcome
        for outcome in _OUTCOMES
        if math.isclose(
            probabilities[outcome],
            top_probability,
            rel_tol=0.0,
            abs_tol=_TOLERANCE,
        )
    ]
    payload: dict[str, Any] = {
        "probabilities": dict(probabilities),
        "top_outcomes": top_outcomes,
        "top_probability": top_probability,
    }
    if actual is None:
        payload.update(
            actual_probability=None,
            actual_rank=None,
            top_correct=None,
            brier_score=None,
            log_loss=None,
        )
        return payload
    actual_probability = probabilities[actual]
    payload.update(
        actual_probability=actual_probability,
        actual_rank=1
        + sum(
            probability > actual_probability + _TOLERANCE
            for probability in probabilities.values()
        ),
        top_correct=actual in top_outcomes,
        brier_score=math.fsum(
            (probabilities[outcome] - float(outcome == actual)) ** 2
            for outcome in _OUTCOMES
        ),
        log_loss=-math.log(max(actual_probability, 1e-15)),
    )
    return payload


def _pre_draw_payload(probabilities: Mapping[str, float]) -> dict[str, Any]:
    ordered = sorted(probabilities.values(), reverse=True)
    top = ordered[0]
    return {
        "bk_top_outcomes": [
            outcome
            for outcome in _OUTCOMES
            if math.isclose(
                probabilities[outcome], top, rel_tol=0.0, abs_tol=_TOLERANCE
            )
        ],
        "bk_top_probability": top,
        "bk_probability_margin": top - ordered[1],
        "bk_normalized_entropy": -math.fsum(
            probability * math.log(probability)
            for probability in probabilities.values()
            if probability > 0.0
        )
        / math.log(len(_OUTCOMES)),
        "bk_market_ranks": {
            outcome: 1
            + sum(
                other > probabilities[outcome] + _TOLERANCE
                for other in probabilities.values()
            )
            for outcome in _OUTCOMES
        },
    }


def _model_metrics(
    events: Sequence[Mapping[str, Any]], *, model: str
) -> dict[str, Any]:
    evaluations = [event["models"][model] for event in events]
    overall = _evaluation_metrics(evaluations)
    overall["per_actual_outcome"] = {
        outcome: _evaluation_metrics(
            [
                event["models"][model]
                for event in events
                if event["actual_outcome"] == outcome
            ],
            empty_status=True,
        )
        for outcome in _OUTCOMES
    }
    calibration = _calibration(evaluations)
    overall["calibration"] = calibration
    overall["top_confidence_ece"] = calibration["ece"]
    return overall


def _evaluation_metrics(
    evaluations: Sequence[Mapping[str, Any]], *, empty_status: bool = False
) -> dict[str, Any]:
    count = len(evaluations)
    if not count:
        if empty_status:
            return {"event_count": 0, "status": "EMPTY"}
        raise ValueError("model has no resolved events")
    correct = sum(item["top_correct"] is True for item in evaluations)
    return {
        "event_count": count,
        "top_correct_count": correct,
        "top_accuracy": correct / count,
        "brier_score": math.fsum(item["brier_score"] for item in evaluations) / count,
        "log_loss": math.fsum(item["log_loss"] for item in evaluations) / count,
    }


def _calibration(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bins: list[dict[str, Any]] = []
    contributions: list[float] = []
    count = len(evaluations)
    for index in range(10):
        lower = index / 10
        upper = (index + 1) / 10
        selected = [
            item
            for item in evaluations
            if min(9, int(item["top_probability"] * 10)) == index
        ]
        key = f"[{lower:.1f},{upper:.1f}{']' if index == 9 else ')'}"
        if not selected:
            bins.append(
                {
                    "key": key,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "event_count": 0,
                    "status": "EMPTY",
                }
            )
            continue
        average_confidence = math.fsum(
            item["top_probability"] for item in selected
        ) / len(selected)
        accuracy = sum(item["top_correct"] is True for item in selected) / len(selected)
        gap = abs(average_confidence - accuracy)
        contribution = len(selected) / count * gap
        contributions.append(contribution)
        bins.append(
            {
                "key": key,
                "lower_bound": lower,
                "upper_bound": upper,
                "event_count": len(selected),
                "average_confidence": average_confidence,
                "accuracy": accuracy,
                "absolute_gap": gap,
                "ece_contribution": contribution,
            }
        )
    return {
        "method": "10-bin equal-width top-confidence calibration",
        "ece": math.fsum(contributions),
        "bins": bins,
    }


def _segments(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    drawings = sorted({event["drawing_number"] for event in events})
    leagues = sorted(
        {event["league"] for event in events if event["league"] is not None}
    )
    return {
        "drawing_number": _segment_dimension(
            "Exact actual drawing number",
            [
                (
                    str(drawing),
                    lambda event, value=drawing: event["drawing_number"] == value,
                )
                for drawing in drawings
            ],
            events,
        ),
        "actual_outcome": _segment_dimension(
            "Resolved actual outcome; evaluation only",
            [
                (outcome, lambda event, value=outcome: event["actual_outcome"] == value)
                for outcome in _OUTCOMES
            ],
            events,
        ),
        "actual_draw": _segment_dimension(
            "Whether the resolved actual outcome is X; evaluation only",
            [
                ("DRAW", lambda event: event["actual_outcome"] == "X"),
                ("NON_DRAW", lambda event: event["actual_outcome"] != "X"),
            ],
            events,
        ),
        "bk_actual_market_rank": _segment_dimension(
            "BK rank of the resolved actual outcome; evaluation only",
            [
                (
                    "RANK_1_FAVORITE",
                    lambda event: event["models"]["bk"]["actual_rank"] == 1,
                ),
                ("RANK_2", lambda event: event["models"]["bk"]["actual_rank"] == 2),
                (
                    "RANK_3_UNDERDOG",
                    lambda event: event["models"]["bk"]["actual_rank"] == 3,
                ),
            ],
            events,
        ),
        "bk_probability_margin": _segment_dimension(
            "Pre-draw BK top-minus-second probability margin",
            [
                (
                    "[0.00,0.05)",
                    lambda event: event["pre_draw"]["bk_probability_margin"] < 0.05,
                ),
                (
                    "[0.05,0.10)",
                    lambda event: (
                        0.05 <= event["pre_draw"]["bk_probability_margin"] < 0.10
                    ),
                ),
                (
                    "[0.10,0.20)",
                    lambda event: (
                        0.10 <= event["pre_draw"]["bk_probability_margin"] < 0.20
                    ),
                ),
                (
                    "[0.20,1.00]",
                    lambda event: event["pre_draw"]["bk_probability_margin"] >= 0.20,
                ),
            ],
            events,
        ),
        "bk_normalized_entropy": _segment_dimension(
            "Pre-draw BK Shannon entropy normalized by log(3)",
            [
                (
                    "[0.00,0.80)",
                    lambda event: event["pre_draw"]["bk_normalized_entropy"] < 0.80,
                ),
                (
                    "[0.80,0.90)",
                    lambda event: (
                        0.80 <= event["pre_draw"]["bk_normalized_entropy"] < 0.90
                    ),
                ),
                (
                    "[0.90,0.95)",
                    lambda event: (
                        0.90 <= event["pre_draw"]["bk_normalized_entropy"] < 0.95
                    ),
                ),
                (
                    "[0.95,1.00]",
                    lambda event: event["pre_draw"]["bk_normalized_entropy"] >= 0.95,
                ),
            ],
            events,
        ),
        "league": _segment_dimension(
            "Exact frozen-final-input championship identity",
            [
                *[
                    (league, lambda event, value=league: event["league"] == value)
                    for league in leagues
                ],
                ("MISSING", lambda event: event["league"] is None),
            ],
            events,
        ),
    }


def _segment_dimension(
    definition: str,
    predicates: Sequence[tuple[str, Any]],
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "definition": definition,
        "segments": [
            _segment_payload(key, [event for event in events if predicate(event)])
            for key, predicate in predicates
        ],
    }


def _segment_payload(key: str, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not events:
        return {"key": key, "event_count": 0, "status": "EMPTY"}
    covered = sum(event["sports_v2"]["covered"] for event in events)
    return {
        "key": key,
        "event_count": len(events),
        "status": "SUPPORTED",
        "model_metrics": {
            model: _model_metrics(events, model=model) for model in _MODELS
        },
        "sports_v2_coverage": {
            "covered_event_count": covered,
            "fallback_event_count": len(events) - covered,
            "coverage_rate": covered / len(events),
        },
    }


def _metric_delta(model_metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, float]:
    return {
        metric: model_metrics["sports_v2"][metric] - model_metrics["bk"][metric]
        for metric in (
            "top_accuracy",
            "brier_score",
            "log_loss",
            "top_confidence_ece",
        )
    }


class _StrategyAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.actual_share: list[float] = []
        self.zero = 0
        self.fixed = 0
        self.universal = 0

    def add(self, payload: Mapping[str, Any]) -> None:
        share = payload.get("actual_share")
        if not isinstance(share, (int, float)) or isinstance(share, bool):
            raise ValueError("strategy actual share must be numeric")
        value = float(share)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("strategy actual share is outside [0, 1]")
        self.count += 1
        self.actual_share.append(value)
        self.zero += int(payload.get("zero_actual_exposure") is True)
        self.fixed += int(payload.get("fixed_wrong") is True)
        self.universal += int(payload.get("best_coupon_universal_miss") is True)

    def payload(self) -> dict[str, Any]:
        if not self.count:
            raise ValueError("strategy has no resolved events")
        return {
            "event_count": self.count,
            "average_actual_share": math.fsum(self.actual_share) / self.count,
            "zero_actual_exposure_count": self.zero,
            "fixed_wrong_count": self.fixed,
            "best_coupon_universal_miss_count": self.universal,
        }


def _csv_text(report: Mapping[str, Any]) -> str:
    fields = [
        "report_sha256",
        "drawing_number",
        "drawing_id",
        "plan_id",
        "position",
        "event_order",
        "event_name",
        "league",
        "league_status",
        "league_missing_reason",
        "actual_outcome",
        "excluded_as_void",
        "sports_covered",
        "sports_fallback_reason",
        "bk_probability_1",
        "bk_probability_X",
        "bk_probability_2",
        "sports_probability_1",
        "sports_probability_X",
        "sports_probability_2",
        "bk_top_correct",
        "sports_top_correct",
        "bk_actual_rank",
        "bk_probability_margin",
        "bk_normalized_entropy",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for event in report["events"]:
        writer.writerow(
            {
                "report_sha256": report["report_sha256"],
                "drawing_number": event["drawing_number"],
                "drawing_id": event["drawing_id"],
                "plan_id": event["plan_id"],
                "position": event["position"],
                "event_order": event["event_order"],
                "event_name": event["event_name"],
                "league": event["league"],
                "league_status": event["league_status"],
                "league_missing_reason": event["league_missing_reason"],
                "actual_outcome": event["actual_outcome"],
                "excluded_as_void": event["excluded_as_void"],
                "sports_covered": event["sports_v2"]["covered"],
                "sports_fallback_reason": event["sports_v2"]["fallback_reason"],
                "bk_probability_1": event["models"]["bk"]["probabilities"]["1"],
                "bk_probability_X": event["models"]["bk"]["probabilities"]["X"],
                "bk_probability_2": event["models"]["bk"]["probabilities"]["2"],
                "sports_probability_1": event["models"]["sports_v2"]["probabilities"][
                    "1"
                ],
                "sports_probability_X": event["models"]["sports_v2"]["probabilities"][
                    "X"
                ],
                "sports_probability_2": event["models"]["sports_v2"]["probabilities"][
                    "2"
                ],
                "bk_top_correct": event["models"]["bk"]["top_correct"],
                "sports_top_correct": event["models"]["sports_v2"]["top_correct"],
                "bk_actual_rank": event["models"]["bk"]["actual_rank"],
                "bk_probability_margin": event["pre_draw"]["bk_probability_margin"],
                "bk_normalized_entropy": event["pre_draw"]["bk_normalized_entropy"],
            }
        )
    return output.getvalue()


def _markdown_text(report: Mapping[str, Any]) -> str:
    event_count = report["event_count"]
    resolved_count = report["resolved_event_count"]
    league_count = report["league_coverage"]["mapped_event_count"]
    sports_count = report["sports_v2"]["covered_event_count"]
    lines = [
        "# Sports Analytics v3 attribution aggregate",
        "",
        "**RESEARCH ONLY — NOT ACTIVATED — NOT OPERATOR COMPATIBLE**",
        "",
        f"- Report SHA-256: `{report['report_sha256']}`",
        f"- Drawings: `{report['drawings']}`",
        f"- Events: **{event_count}**",
        f"- Resolved events: **{resolved_count}**",
        f"- Exact league coverage: **{league_count}/{event_count}**",
        f"- Sports v2 coverage: **{sports_count}/{resolved_count}**",
        "",
        "## Model metrics",
        "",
        "| Model | N | Top accuracy | Brier | Log loss | ECE |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model in _MODELS:
        metrics = report["model_metrics"][model]
        lines.append(
            f"| {model} | {metrics['event_count']} | {metrics['top_accuracy']:.6f} "
            f"| {metrics['brier_score']:.6f} | {metrics['log_loss']:.6f} "
            f"| {metrics['top_confidence_ece']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Events",
            "",
            "| Drawing | Pos | Event | League | Actual | BK rank | "
            "Margin | Entropy | Sports |",
            "|---:|---:|---|---|:---:|---:|---:|---:|---|",
        ]
    )
    for event in report["events"]:
        league = event["league"] or f"MISSING ({event['league_missing_reason']})"
        drawing = event["drawing_number"]
        position = event["position"]
        event_name = event["event_name"]
        lines.append(
            f"| {drawing} | {position} | {event_name} "
            f"| {league} | {event['actual_outcome'] or 'VOID'} "
            f"| {event['models']['bk']['actual_rank'] or ''} "
            f"| {event['pre_draw']['bk_probability_margin']:.6f} "
            f"| {event['pre_draw']['bk_normalized_entropy']:.6f} "
            f"| {'covered' if event['sports_v2']['covered'] else 'fallback'} |"
        )
    lines.extend(
        [
            "",
            "Actual outcomes are used only for resolved-event evaluation; all "
            "pre-draw probability features are recomputed from frozen vectors.",
            "",
        ]
    )
    return "\n".join(lines)


def _probabilities(value: object) -> dict[str, float]:
    payload = _mapping(value, "model probabilities")
    probabilities: dict[str, float] = {}
    for outcome in _OUTCOMES:
        raw = payload.get(outcome)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise ValueError("model probability must be numeric")
        probability = float(raw)
        if not math.isfinite(probability) or probability < 0.0:
            raise ValueError("model probability must be finite and non-negative")
        probabilities[outcome] = probability
    if not math.isclose(math.fsum(probabilities.values()), 1.0, abs_tol=1e-9):
        raise ValueError("model probabilities must sum to one")
    return probabilities


def _json_file(
    raw_path: str | Path, name: str
) -> tuple[Path, bytes, Mapping[str, Any]]:
    path = Path(raw_path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be a regular file: {path}")
    content = path.read_bytes()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} is not valid JSON: {path}") from error
    return path, content, _mapping(payload, name)


def _event_order(event: Mapping[str, Any]) -> int:
    value = event.get("event_order")
    if type(value) is not int or value not in range(15):
        raise ValueError("attribution event order is invalid")
    return value


def _final_event_order(event: object) -> int:
    value = _mapping(event, "final-input event").get("order")
    if type(value) is not int or value not in range(15):
        raise ValueError("final-input event order is invalid")
    return value


def _event_name(event: Mapping[str, Any]) -> str:
    value = event.get("event_name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("attribution event name is invalid")
    return value


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return _canonical_payload_sha256(payload, ensure_ascii=False)


def _attribution_payload_sha256(payload: Mapping[str, Any]) -> str:
    schema_version = payload.get("schema_version")
    if schema_version == 1:
        return _canonical_payload_sha256(payload, ensure_ascii=True)
    if schema_version == 2:
        return _canonical_payload_sha256(payload, ensure_ascii=False)
    raise ValueError("unsupported attribution report schema version")


def _canonical_payload_sha256(
    payload: Mapping[str, Any], *, ensure_ascii: bool
) -> str:
    unsigned = dict(payload)
    unsigned.pop("report_sha256", None)
    encoded = json.dumps(
        unsigned,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"sports v3 aggregate artifact conflicts: {path}")
        return
    path.write_bytes(content)
