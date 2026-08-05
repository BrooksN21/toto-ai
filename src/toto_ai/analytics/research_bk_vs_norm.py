import math
import random
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing, Event, Quote

OUTCOMES = (
    ("1", "bk_win_1", "norm_win_1"),
    ("X", "bk_draw", "norm_draw"),
    ("2", "bk_win_2", "norm_win_2"),
)

DERIVED_MESSAGE = "BK probabilities are derived from normalized odds."
DIFFER_MESSAGE = "BK probabilities differ from normalized odds."


def run_bk_vs_norm_study(
    session: Session,
    sample_size: int = 20,
) -> dict[str, Any]:
    rows = _eligible_rows(session)
    comparisons = []
    examples = []

    for event, quote in rows:
        calculated = _normalized_probabilities_from_norm_odds(quote)
        if calculated is None:
            continue

        bk = {
            "1": _bk_probability(quote.bk_win_1),
            "X": _bk_probability(quote.bk_draw),
            "2": _bk_probability(quote.bk_win_2),
        }
        if any(value is None for value in bk.values()):
            continue

        differences = {
            outcome: abs(bk[outcome] - calculated[outcome])
            for outcome in ("1", "X", "2")
        }
        for outcome in ("1", "X", "2"):
            comparisons.append(
                {
                    "bk": bk[outcome],
                    "calculated": calculated[outcome],
                    "difference": differences[outcome],
                }
            )

        examples.append(
            {
                "event": event.name or f"{event.drawing_id}:{event.event_order}",
                "bk": _triple(bk),
                "calculated": _triple(calculated),
                "difference": _triple(differences),
            }
        )

    avg_error = _average([row["difference"] for row in comparisons])
    max_error = max((row["difference"] for row in comparisons), default=0.0)
    correlation = _correlation(
        [row["bk"] for row in comparisons],
        [row["calculated"] for row in comparisons],
    )
    sampled_examples = _sample_examples(examples, sample_size)
    conclusion = DERIVED_MESSAGE if avg_error < 1 else DIFFER_MESSAGE

    return {
        "event_count": len(examples),
        "comparison_count": len(comparisons),
        "average_absolute_error": round(avg_error, 4),
        "maximum_error": round(max_error, 4),
        "correlation": round(correlation, 4),
        "conclusion": conclusion,
        "examples": sampled_examples,
    }


def build_bk_vs_norm_report(result: dict[str, Any]) -> str:
    lines = [
        "# BK vs Normalized Odds Study",
        "",
        f"Events analyzed: {result['event_count']}",
        f"Comparisons: {result['comparison_count']}",
        f"Average absolute error: {result['average_absolute_error']:.4f}%",
        f"Maximum error: {result['maximum_error']:.4f}%",
        f"Correlation: {result['correlation']:.4f}",
        "",
        result["conclusion"],
        "",
        "## Examples",
        "",
        "| Event | BK | Calculated | Difference |",
        "| --- | --- | --- | --- |",
    ]
    for example in result["examples"]:
        lines.append(
            f"| {example['event']} | {example['bk']} | "
            f"{example['calculated']} | {example['difference']} |"
        )
    return "\n".join(lines) + "\n"


def write_bk_vs_norm_report(
    result: dict[str, Any],
    report_dir: str | Path = "reports",
) -> Path:
    path = Path(report_dir) / "bk_vs_norm.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_bk_vs_norm_report(result))
    return path


def _eligible_rows(session: Session) -> list[tuple[Event, Quote]]:
    return session.execute(
        select(Event, Quote)
        .join(Drawing, Drawing.id == Event.drawing_id)
        .join(
            Quote,
            (Quote.drawing_id == Event.drawing_id)
            & (Quote.event_order == Event.event_order),
        )
        .where(Drawing.status == "finished")
        .where(Quote.norm_win_1.is_not(None))
        .where(Quote.norm_draw.is_not(None))
        .where(Quote.norm_win_2.is_not(None))
    ).all()


def _normalized_probabilities_from_norm_odds(
    quote: Quote,
) -> dict[str, float] | None:
    implied = {
        "1": _safe_inverse(quote.norm_win_1),
        "X": _safe_inverse(quote.norm_draw),
        "2": _safe_inverse(quote.norm_win_2),
    }
    if any(value is None for value in implied.values()):
        return None

    total = sum(value for value in implied.values() if value is not None)
    if total <= 0:
        return None
    return {
        outcome: implied[outcome] / total * 100
        for outcome in ("1", "X", "2")
    }


def _bk_probability(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    if value <= 1:
        return value * 100
    return value


def _safe_inverse(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return 1 / value


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return 0.0
    left_avg = _average(left)
    right_avg = _average(right)
    numerator = sum(
        (left_value - left_avg) * (right_value - right_avg)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_denominator = math.sqrt(
        sum((left_value - left_avg) ** 2 for left_value in left)
    )
    right_denominator = math.sqrt(
        sum((right_value - right_avg) ** 2 for right_value in right)
    )
    if left_denominator == 0 or right_denominator == 0:
        return 0.0
    return numerator / (left_denominator * right_denominator)


def _sample_examples(
    examples: list[dict[str, str]],
    sample_size: int,
) -> list[dict[str, str]]:
    if len(examples) <= sample_size:
        return examples
    return random.Random(0).sample(examples, sample_size)


def _triple(values: dict[str, float]) -> str:
    return f"{values['1']:.2f} / {values['X']:.2f} / {values['2']:.2f}"
