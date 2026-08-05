from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote

OUTCOMES = ("1", "X", "2")
BIN_LABELS = tuple(f"{start}-{start + 5}%" for start in range(0, 100, 5))


def run_calibration_study(session: Session) -> dict[str, Any]:
    rows = _finished_event_rows(session)
    observations = []
    for event, quote in rows:
        result = normalize_result(event.result)
        bookmaker = _outcome_probabilities(quote, "bk")
        pool = _outcome_probabilities(quote, "pool")
        if result is None or bookmaker is None:
            continue
        observations.append(
            {
                "event": event,
                "result": result,
                "bk": bookmaker,
                "pool": pool,
            }
        )

    bookmaker_bins = _calibration_bins(observations, provider="bk")
    pool_observations = [
        observation
        for observation in observations
        if observation["pool"] is not None
    ]
    pool_bins = _calibration_bins(pool_observations, provider="pool")

    return {
        "overall": _overall_scores(observations),
        "bookmaker_bins": bookmaker_bins,
        "pool_bins": pool_bins,
        "reliability": bookmaker_bins,
        "pool_calibration": _provider_summary(pool_bins),
        "pool_vs_bookmaker_bias": _bias_summary(observations),
        "draw_calibration": _slice_summary(observations, outcomes=("X",)),
        "favorites": _slice_summary(
            observations,
            predicate=lambda probability: probability >= 0.60,
        ),
        "underdogs": _slice_summary(
            observations,
            predicate=lambda probability: probability <= 0.25,
        ),
    }


def bin_probability(probability: float) -> str:
    bounded = min(max(probability, 0.0), 1.0)
    index = min(int(bounded * 100 // 5), 19)
    return BIN_LABELS[index]


def write_calibration_reports(
    result: dict[str, Any],
    report_dir: str | Path = "reports",
) -> tuple[Path, Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "calibration.md"
    calibration_csv = output_dir / "calibration.csv"
    reliability_csv = output_dir / "reliability.csv"

    markdown_path.write_text(_calibration_markdown(result), encoding="utf-8")
    _write_calibration_csv(result, calibration_csv)
    _write_reliability_csv(result, reliability_csv)
    return markdown_path, calibration_csv, reliability_csv


def _finished_event_rows(session: Session) -> list[tuple[Event, Quote]]:
    return list(
        session.execute(
            select(Event, Quote)
            .join(Drawing, Drawing.id == Event.drawing_id)
            .join(
                Quote,
                (Quote.drawing_id == Event.drawing_id)
                & (Quote.event_order == Event.event_order),
            )
            .where(Drawing.status == "finished")
            .where(Event.result.is_not(None))
        ).all()
    )


def _outcome_probabilities(
    quote: Quote,
    prefix: str,
) -> dict[str, float] | None:
    raw = {
        "1": getattr(quote, f"{prefix}_win_1"),
        "X": getattr(quote, f"{prefix}_draw"),
        "2": getattr(quote, f"{prefix}_win_2"),
    }
    if any(value is None or value <= 0 for value in raw.values()):
        return None

    probabilities = {
        outcome: _to_probability(value)
        for outcome, value in raw.items()
        if value is not None
    }
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {
        outcome: probability / total
        for outcome, probability in probabilities.items()
    }


def _to_probability(value: float) -> float:
    return value / 100 if value > 1 else value


def _calibration_bins(
    observations: list[dict[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    bucket_data: dict[tuple[str, str], list[dict[str, float | int]]] = {}
    for observation in observations:
        probabilities = observation[provider]
        if probabilities is None:
            continue
        pool = observation["pool"]
        for outcome in OUTCOMES:
            probability = probabilities[outcome]
            bucket_data.setdefault((outcome, bin_probability(probability)), []).append(
                {
                    "probability": probability,
                    "pool_probability": pool[outcome] if pool else 0.0,
                    "hit": int(outcome == observation["result"]),
                }
            )

    rows = []
    for outcome in OUTCOMES:
        for label in BIN_LABELS:
            items = bucket_data.get((outcome, label), [])
            count = len(items)
            observed = _average([item["hit"] for item in items])
            expected = _average([item["probability"] for item in items])
            avg_pool = _average([item["pool_probability"] for item in items])
            rows.append(
                {
                    "provider": provider,
                    "outcome": outcome,
                    "bin": label,
                    "event_count": count,
                    "observed_frequency": round(observed * 100, 4),
                    "expected_frequency": round(expected * 100, 4),
                    "calibration_error": round(abs(observed - expected) * 100, 4),
                    "average_pool_probability": round(avg_pool * 100, 4),
                    "average_bookmaker_probability": round(
                        expected * 100 if provider == "bk" else 0.0,
                        4,
                    ),
                }
            )
    return rows


def _overall_scores(observations: list[dict[str, Any]]) -> dict[str, float | int]:
    if not observations:
        return {
            "event_count": 0,
            "outcome_count": 0,
            "brier_score": 0.0,
            "log_loss": 0.0,
            "ece": 0.0,
        }

    brier_total = 0.0
    log_loss_total = 0.0
    for observation in observations:
        for outcome in OUTCOMES:
            hit = 1 if outcome == observation["result"] else 0
            probability = observation["bk"][outcome]
            brier_total += (probability - hit) ** 2
            if hit:
                log_loss_total += -math.log(max(probability, 1e-15))

    return {
        "event_count": len(observations),
        "outcome_count": len(observations) * len(OUTCOMES),
        "brier_score": round(brier_total / len(observations), 6),
        "log_loss": round(log_loss_total / len(observations), 6),
        "ece": _expected_calibration_error(_calibration_bins(observations, "bk")),
    }


def _expected_calibration_error(rows: list[dict[str, Any]]) -> float:
    total = sum(row["event_count"] for row in rows)
    if total == 0:
        return 0.0
    weighted = sum(
        row["event_count"] * row["calibration_error"]
        for row in rows
    )
    return round(weighted / total, 4)


def _provider_summary(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    total = sum(row["event_count"] for row in rows)
    if total == 0:
        return {"outcome_count": 0, "ece": 0.0}
    return {"outcome_count": total, "ece": _expected_calibration_error(rows)}


def _bias_summary(observations: list[dict[str, Any]]) -> dict[str, float | int]:
    values = []
    hits = []
    roi_values = []
    for observation in observations:
        pool = observation["pool"]
        if pool is None:
            continue
        for outcome in OUTCOMES:
            bookmaker_probability = observation["bk"][outcome]
            pool_probability = pool[outcome]
            hit = int(outcome == observation["result"])
            values.append(pool_probability - bookmaker_probability)
            hits.append(hit)
            roi_values.append(hit - pool_probability)

    return {
        "outcome_count": len(values),
        "average_bias": round(_average(values) * 100, 4),
        "hit_rate": round(_average(hits) * 100, 4),
        "roi_style_value": round(_average(roi_values) * 100, 4),
    }


def _slice_summary(
    observations: list[dict[str, Any]],
    outcomes: tuple[str, ...] = OUTCOMES,
    predicate=None,
) -> dict[str, float | int]:
    probabilities = []
    hits = []
    for observation in observations:
        for outcome in outcomes:
            probability = observation["bk"][outcome]
            if predicate is not None and not predicate(probability):
                continue
            probabilities.append(probability)
            hits.append(int(outcome == observation["result"]))

    return {
        "event_count": len(probabilities),
        "observed_frequency": round(_average(hits) * 100, 4),
        "expected_frequency": round(_average(probabilities) * 100, 4),
        "calibration_error": round(
            abs(_average(hits) - _average(probabilities)) * 100,
            4,
        ),
    }


def _average(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def _calibration_markdown(result: dict[str, Any]) -> str:
    overall = result["overall"]
    lines = [
        "# Bookmaker Calibration",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in overall.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")

    lines.extend(
        [
            "",
            "## Additional Analyses",
            "",
            f"- Pool ECE: {result['pool_calibration']['ece']}",
            f"- Average pool vs bookmaker bias: "
            f"{result['pool_vs_bookmaker_bias']['average_bias']}",
            f"- Draw calibration error: "
            f"{result['draw_calibration']['calibration_error']}",
            f"- Favorite calibration error: "
            f"{result['favorites']['calibration_error']}",
            f"- Underdog calibration error: "
            f"{result['underdogs']['calibration_error']}",
            "",
        ]
    )
    return "\n".join(lines)


def _write_calibration_csv(result: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["metric", "value"])
        for key, value in result["overall"].items():
            writer.writerow([key, value])
        for section in (
            "pool_calibration",
            "pool_vs_bookmaker_bias",
            "draw_calibration",
            "favorites",
            "underdogs",
        ):
            for key, value in result[section].items():
                writer.writerow([f"{section}.{key}", value])


def _write_reliability_csv(result: dict[str, Any], path: Path) -> None:
    rows = result["bookmaker_bins"] + result["pool_bins"]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "provider",
                "outcome",
                "bin",
                "event_count",
                "observed_frequency",
                "expected_frequency",
                "calibration_error",
                "average_pool_probability",
                "average_bookmaker_probability",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
