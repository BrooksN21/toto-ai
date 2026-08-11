from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.external_odds.domain import OutcomeTriplet

OUTCOMES = ("1", "X", "2")
HARD_MINIMUM_DRAWINGS = 30
HARD_MINIMUM_EVENTS = 450
HARD_MINIMUM_SPORTS_COVERAGE = 0.70
MAXIMUM_CALIBRATION_TOLERANCE = 0.02


@dataclass(frozen=True)
class ShadowEvaluationRecord:
    drawing_id: int
    drawing_number: int | None
    event_order: int
    as_of: datetime
    actual: str
    bk_probabilities: OutcomeTriplet
    sports_probabilities: OutcomeTriplet
    candidate_blend_probabilities: OutcomeTriplet
    sports_used: bool
    fallback_reason: str | None
    validation_failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.actual not in OUTCOMES:
            raise ValueError("actual must be 1, X, or 2")
        if self.event_order not in range(15):
            raise ValueError("event_order must be in range 0 through 14")
        _utc("as_of", self.as_of)
        for row in (
            self.bk_probabilities,
            self.sports_probabilities,
            self.candidate_blend_probabilities,
        ):
            _probability_row(row)
        if self.sports_used and self.fallback_reason is not None:
            raise ValueError("sports-used row cannot have a fallback reason")
        if not self.sports_used and not self.fallback_reason:
            raise ValueError("fallback row requires a reason")


@dataclass(frozen=True)
class ProbabilityMetrics:
    log_loss: float
    brier: float
    ece: float
    event_count: int


@dataclass(frozen=True)
class ActivationGate:
    status: str
    passed: bool
    reasons: tuple[str, ...]
    minimum_drawings: int
    minimum_events: int
    minimum_sports_coverage: float
    calibration_tolerance: float


@dataclass(frozen=True)
class ShadowEvaluationResult:
    status: str
    drawing_count: int
    event_count: int
    sports_coverage_count: int
    fallback_count: int
    coverage_rate: float
    validation_failure_count: int
    fingerprint_failure_count: int
    leakage_failure_count: int
    metrics: Mapping[str, ProbabilityMetrics]
    activation_gate: ActivationGate
    records: tuple[ShadowEvaluationRecord, ...]

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


def evaluate_shadow_records(
    records: tuple[ShadowEvaluationRecord, ...],
    *,
    minimum_drawings: int = 30,
    minimum_events: int = 450,
    minimum_sports_coverage: float = 0.70,
    calibration_tolerance: float = 0.02,
) -> ShadowEvaluationResult:
    if (
        type(minimum_drawings) is not int
        or type(minimum_events) is not int
        or minimum_drawings < HARD_MINIMUM_DRAWINGS
        or minimum_events < HARD_MINIMUM_EVENTS
        or not isinstance(minimum_sports_coverage, (int, float))
        or isinstance(minimum_sports_coverage, bool)
        or not math.isfinite(minimum_sports_coverage)
        or minimum_sports_coverage < HARD_MINIMUM_SPORTS_COVERAGE
        or minimum_sports_coverage > 1.0
        or not isinstance(calibration_tolerance, (int, float))
        or isinstance(calibration_tolerance, bool)
        or not math.isfinite(calibration_tolerance)
        or calibration_tolerance < 0
        or calibration_tolerance > MAXIMUM_CALIBRATION_TOLERANCE
    ):
        raise ValueError("activation policy hard minima/tolerance cannot be weakened")
    ordered = tuple(
        sorted(records, key=lambda row: (row.as_of, row.drawing_id, row.event_order))
    )
    identities = tuple((row.drawing_id, row.event_order) for row in ordered)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate drawing/event evaluation row")

    drawing_count = len({row.drawing_id for row in ordered})
    event_count = len(ordered)
    sports_count = sum(row.sports_used for row in ordered)
    fallback_count = event_count - sports_count
    coverage_rate = 0.0 if not event_count else sports_count / event_count
    validation_failure_count = sum(bool(row.validation_failures) for row in ordered)
    fingerprint_failure_count = sum(
        any("fingerprint" in reason for reason in row.validation_failures)
        for row in ordered
    )
    leakage_failure_count = sum(
        any(
            reason in {"source_after_as_of", "snapshot_after_as_of", "leakage"}
            for reason in row.validation_failures
        )
        for row in ordered
    )
    metrics = {
        "bk": _metrics(ordered, "bk_probabilities"),
        "sports_shadow": _metrics(ordered, "sports_probabilities"),
        "candidate_blend": _metrics(
            ordered,
            "candidate_blend_probabilities",
        ),
    }
    reasons: list[str] = []
    if drawing_count < minimum_drawings:
        reasons.append("minimum_drawings_not_met")
    if event_count < minimum_events:
        reasons.append("minimum_events_not_met")
    if coverage_rate < minimum_sports_coverage:
        reasons.append("sports_coverage_not_met")
    if validation_failure_count:
        reasons.append("validation_failure")
    if fingerprint_failure_count:
        reasons.append("fingerprint_failure")
    if leakage_failure_count:
        reasons.append("leakage_failure")
    if metrics["candidate_blend"].log_loss >= metrics["bk"].log_loss:
        reasons.append("log_loss_not_strictly_improved")
    if metrics["candidate_blend"].brier >= metrics["bk"].brier:
        reasons.append("brier_not_strictly_improved")
    if (
        metrics["candidate_blend"].ece
        > metrics["bk"].ece + calibration_tolerance
    ):
        reasons.append("calibration_tolerance_exceeded")

    passed = not reasons
    gate = ActivationGate(
        status="PASS_REVIEW_REQUIRED" if passed else "FAIL_CLOSED",
        passed=passed,
        reasons=tuple(reasons),
        minimum_drawings=minimum_drawings,
        minimum_events=minimum_events,
        minimum_sports_coverage=minimum_sports_coverage,
        calibration_tolerance=calibration_tolerance,
    )
    return ShadowEvaluationResult(
        status="NOT_ACTIVATED",
        drawing_count=drawing_count,
        event_count=event_count,
        sports_coverage_count=sports_count,
        fallback_count=fallback_count,
        coverage_rate=coverage_rate,
        validation_failure_count=validation_failure_count,
        fingerprint_failure_count=fingerprint_failure_count,
        leakage_failure_count=leakage_failure_count,
        metrics=metrics,
        activation_gate=gate,
        records=ordered,
    )


def write_shadow_evaluation_reports(
    result: ShadowEvaluationResult,
    *,
    report_dir: str | Path = "reports/sports-probability-shadow",
) -> tuple[Path, Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "sports_probability_evaluation.json"
    csv_path = output_dir / "sports_probability_evaluation.csv"
    markdown_path = output_dir / "sports_probability_evaluation.md"
    json_path.write_text(
        json.dumps(
            result.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "drawing_id",
                "drawing_number",
                "event_order",
                "as_of",
                "actual",
                "sports_used",
                "fallback_reason",
                "validation_failures",
            ),
        )
        writer.writeheader()
        for row in result.records:
            writer.writerow(
                {
                    "drawing_id": row.drawing_id,
                    "drawing_number": row.drawing_number,
                    "event_order": row.event_order,
                    "as_of": row.as_of.isoformat(),
                    "actual": row.actual,
                    "sports_used": row.sports_used,
                    "fallback_reason": row.fallback_reason or "",
                    "validation_failures": "|".join(row.validation_failures),
                }
            )
    lines = [
        "# Sports Probability Shadow Evaluation",
        "",
        f"- Status: `{result.status}`",
        f"- Activation gate: `{result.activation_gate.status}`",
        f"- Drawings/events: {result.drawing_count}/{result.event_count}",
        f"- Sports coverage: {result.sports_coverage_count}/{result.event_count}",
        "",
        "| Model | Log loss | Brier | ECE |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, metric in result.metrics.items():
        lines.append(
            f"| {name} | {metric.log_loss:.8f} | {metric.brier:.8f} | "
            f"{metric.ece:.8f} |"
        )
    lines.extend(
        [
            "",
            "Gate reasons: "
            + (", ".join(result.activation_gate.reasons) or "none"),
            "",
            "Passing the gate does not activate production probabilities; "
            "manual review and an explicit architecture change are required.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, csv_path, markdown_path


def _metrics(
    rows: tuple[ShadowEvaluationRecord, ...],
    field: str,
) -> ProbabilityMetrics:
    if not rows:
        return ProbabilityMetrics(log_loss=0.0, brier=0.0, ece=0.0, event_count=0)
    log_loss = 0.0
    brier = 0.0
    calibration_bins: dict[int, list[tuple[float, int]]] = {}
    for row in rows:
        probabilities = getattr(row, field)
        actual_index = OUTCOMES.index(row.actual)
        log_loss += -math.log(max(probabilities[actual_index], 1e-15))
        brier += sum(
            (probability - int(index == actual_index)) ** 2
            for index, probability in enumerate(probabilities)
        )
        confidence = max(probabilities)
        predicted = probabilities.index(confidence)
        bin_index = min(int(confidence * 10), 9)
        calibration_bins.setdefault(bin_index, []).append(
            (confidence, int(predicted == actual_index))
        )
    ece = sum(
        len(items)
        / len(rows)
        * abs(
            sum(confidence for confidence, _ in items) / len(items)
            - sum(hit for _, hit in items) / len(items)
        )
        for items in calibration_bins.values()
    )
    return ProbabilityMetrics(
        log_loss=log_loss / len(rows),
        brier=brier / len(rows),
        ece=ece,
        event_count=len(rows),
    )


def _probability_row(row: OutcomeTriplet) -> None:
    if len(row) != 3 or any(
        not math.isfinite(value) or value < 0.0 for value in row
    ):
        raise ValueError("probabilities must be finite and non-negative")
    if not math.isclose(sum(row), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("probabilities must sum to one")


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value
