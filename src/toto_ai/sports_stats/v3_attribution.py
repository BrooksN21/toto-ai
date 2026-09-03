"""Leakage-free aggregate diagnostics that seed Sports Analytics v3.

This module does not train or activate a probability model.  It summarizes
immutable, settled, equal-input event attribution reports so the next residual
model is driven by observed failure modes rather than one-off drawing choices.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_MODELS = ("bk", "sports_v2")
_STRATEGIES = ("quality-v2", "sports-v2", "quality-v3", "robust")
_OUTCOMES = ("1", "X", "2")


def build_v3_attribution_aggregate(
    report_paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Aggregate settled event attribution without consulting future data."""

    if not report_paths:
        raise ValueError("at least one attribution report is required")
    sources: list[dict[str, Any]] = []
    rows: list[tuple[int, Mapping[str, Any]]] = []
    seen_drawings: set[int] = set()
    for raw_path in report_paths:
        path = Path(raw_path).resolve()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"attribution report must be a regular file: {path}")
        content = path.read_bytes()
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"attribution report is not valid JSON: {path}") from error
        if not isinstance(payload, Mapping):
            raise ValueError("attribution report must be an object")
        if payload.get("artifact_class") != "HYBRID_EVENT_LEVEL_ATTRIBUTION":
            raise ValueError("unexpected attribution artifact class")
        drawing = payload.get("drawing_number")
        if type(drawing) is not int or drawing <= 0 or drawing in seen_drawings:
            raise ValueError("attribution drawing number is invalid or duplicated")
        events = payload.get("events")
        if not isinstance(events, list) or len(events) != 15:
            raise ValueError("each attribution report must contain 15 events")
        seen_drawings.add(drawing)
        sources.append(
            {
                "drawing_number": drawing,
                "path": str(path),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        rows.extend((drawing, _mapping(event, "event")) for event in events)

    sources.sort(key=lambda item: item["drawing_number"])
    model_accumulators = {model: _ModelAccumulator() for model in _MODELS}
    strategy_accumulators = {
        strategy: _StrategyAccumulator() for strategy in _STRATEGIES
    }
    effect_counts: Counter[str] = Counter()
    transition_counts: Counter[str] = Counter()
    diagnosis_counts: dict[str, Counter[str]] = defaultdict(Counter)
    covered = 0
    void = 0
    for _drawing, event in rows:
        if event.get("excluded_as_void") is True:
            void += 1
            continue
        actual = event.get("actual_outcome")
        if actual not in _OUTCOMES:
            raise ValueError("resolved event actual outcome is invalid")
        models = _mapping(event.get("models"), "event models")
        for model in _MODELS:
            model_payload = _mapping(models.get(model), f"{model} model")
            probabilities = _probabilities(model_payload.get("probabilities"))
            model_accumulators[model].add(probabilities, str(actual))

        sports_change = _mapping(
            event.get("sports_v2_change"), "sports v2 change"
        )
        if sports_change.get("covered") is True:
            covered += 1
        effect_counts[str(sports_change.get("effect"))] += 1
        transition_counts[str(sports_change.get("top_prediction_effect"))] += 1

        diagnosis = _mapping(event.get("diagnosis"), "event diagnosis")
        for comparison, value in diagnosis.items():
            diagnosis_counts[str(comparison)][str(value)] += 1

        strategies = _mapping(event.get("strategies"), "event strategies")
        for strategy in _STRATEGIES:
            strategy_accumulators[strategy].add(
                _mapping(strategies.get(strategy), f"{strategy} strategy")
            )

    resolved = len(rows) - void
    if resolved <= 0:
        raise ValueError("attribution aggregate has no resolved events")
    model_metrics = {
        model: accumulator.payload()
        for model, accumulator in model_accumulators.items()
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "artifact_class": "SPORTS_ANALYTICS_V3_ATTRIBUTION_AGGREGATE",
        "status": "RESEARCH_ONLY_NOT_ACTIVATED",
        "operator_compatible": False,
        "automatic_wagering": False,
        "profitability_proven": False,
        "drawings": [item["drawing_number"] for item in sources],
        "source_reports": sources,
        "resolved_event_count": resolved,
        "void_event_count": void,
        "model_metrics": model_metrics,
        "sports_v2_minus_bk": {
            "top_accuracy": (
                model_metrics["sports_v2"]["top_accuracy"]
                - model_metrics["bk"]["top_accuracy"]
            ),
            "brier_score": (
                model_metrics["sports_v2"]["brier_score"]
                - model_metrics["bk"]["brier_score"]
            ),
            "log_loss": (
                model_metrics["sports_v2"]["log_loss"]
                - model_metrics["bk"]["log_loss"]
            ),
            "top_confidence_ece": (
                model_metrics["sports_v2"]["top_confidence_ece"]
                - model_metrics["bk"]["top_confidence_ece"]
            ),
        },
        "sports_v2": {
            "covered_event_count": covered,
            "fallback_event_count": resolved - covered,
            "effect_counts": dict(sorted(effect_counts.items())),
            "top_transition_counts": dict(sorted(transition_counts.items())),
        },
        "diagnosis_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(diagnosis_counts.items())
        },
        "strategy_exposure": {
            strategy: accumulator.payload()
            for strategy, accumulator in strategy_accumulators.items()
        },
        "interpretation": (
            "Descriptive settled evidence only. Sports Analytics v3 must be "
            "trained and calibrated in later chronological folds before any "
            "package or operator evaluation."
        ),
    }
    report["report_sha256"] = _payload_sha256(report)
    return report


def write_v3_attribution_aggregate(
    report: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write or verify the immutable JSON and concise Markdown aggregate."""

    if report.get("report_sha256") != _payload_sha256(report):
        raise ValueError("sports v3 attribution report hash mismatch")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("sports v3 output directory must not be a symlink")
    json_path = output / "attribution-aggregate.json"
    markdown_path = output / "attribution-aggregate.md"
    json_bytes = (
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    metrics = _mapping(report.get("model_metrics"), "model metrics")
    bk = _mapping(metrics.get("bk"), "bk metrics")
    sports = _mapping(metrics.get("sports_v2"), "sports metrics")
    sports_v2 = _mapping(report.get("sports_v2"), "sports v2")
    markdown = (
        "# Sports Analytics v3 attribution aggregate\n\n"
        "RESEARCH ONLY — NOT ACTIVATED — NOT OPERATOR COMPATIBLE\n\n"
        f"- Drawings: `{report.get('drawings')}`\n"
        f"- Resolved events: **{report.get('resolved_event_count')}**\n"
        f"- Sports v2 coverage: **{sports_v2.get('covered_event_count')}**\n"
        f"- BK top accuracy / Brier / log loss / ECE: "
        f"{bk.get('top_accuracy'):.6f} / {bk.get('brier_score'):.6f} / "
        f"{bk.get('log_loss'):.6f} / {bk.get('top_confidence_ece'):.6f}\n"
        f"- Sports v2 top accuracy / Brier / log loss / ECE: "
        f"{sports.get('top_accuracy'):.6f} / {sports.get('brier_score'):.6f} / "
        f"{sports.get('log_loss'):.6f} / {sports.get('top_confidence_ece'):.6f}\n\n"
        "This aggregate identifies failure modes for the next leakage-safe "
        "residual model. It does not establish superiority or profitability.\n"
    ).encode()
    _write_or_verify(json_path, json_bytes)
    _write_or_verify(markdown_path, markdown)
    return json_path, markdown_path


class _ModelAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.top_correct = 0
        self.brier = 0.0
        self.log_loss = 0.0
        self.bins: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])

    def add(self, probabilities: dict[str, float], actual: str) -> None:
        self.count += 1
        top = max(probabilities.values())
        correct = float(probabilities[actual] == top)
        self.top_correct += int(correct)
        self.brier += math.fsum(
            (probabilities[outcome] - float(outcome == actual)) ** 2
            for outcome in _OUTCOMES
        )
        self.log_loss += -math.log(max(probabilities[actual], 1e-15))
        index = min(9, int(top * 10.0))
        bucket = self.bins[index]
        bucket[0] += 1.0
        bucket[1] += top
        bucket[2] += correct

    def payload(self) -> dict[str, Any]:
        if not self.count:
            raise ValueError("model has no resolved events")
        ece = math.fsum(
            (bucket[0] / self.count)
            * abs(bucket[1] / bucket[0] - bucket[2] / bucket[0])
            for bucket in self.bins.values()
        )
        return {
            "event_count": self.count,
            "top_correct_count": self.top_correct,
            "top_accuracy": self.top_correct / self.count,
            "brier_score": self.brier / self.count,
            "log_loss": self.log_loss / self.count,
            "top_confidence_ece": ece,
        }


class _StrategyAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.actual_share = 0.0
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
        self.actual_share += value
        self.zero += int(payload.get("zero_actual_exposure") is True)
        self.fixed += int(payload.get("fixed_wrong") is True)
        self.universal += int(payload.get("best_coupon_universal_miss") is True)

    def payload(self) -> dict[str, Any]:
        if not self.count:
            raise ValueError("strategy has no resolved events")
        return {
            "event_count": self.count,
            "average_actual_share": self.actual_share / self.count,
            "zero_actual_exposure_count": self.zero,
            "fixed_wrong_count": self.fixed,
            "best_coupon_universal_miss_count": self.universal,
        }


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


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("report_sha256", None)
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_or_verify(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"sports v3 aggregate artifact conflicts: {path}")
        return
    path.write_bytes(content)
