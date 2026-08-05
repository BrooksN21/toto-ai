from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean, median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote

OUTCOMES = ("1", "X", "2")


@dataclass(frozen=True)
class EventCoverOption:
    cover: str
    actual_result: str
    log_probability: float
    full_variant_count: int


@dataclass(frozen=True)
class OracleBrief:
    brief: list[str]
    full_variant_count: int
    log_brief_probability: float
    actual_result_string: str
    singles_count: int
    doubles_count: int
    triples_count: int


@dataclass(frozen=True)
class BriefOracleRow:
    drawing_id: int
    drawing_number: int | None
    singles_count: int
    doubles_count: int
    triples_count: int
    full_variant_count: int
    log_brief_probability: float
    actual_result_string: str
    oracle_brief_string: str
    actual_bk_top_count: int
    actual_bk_second_count: int
    actual_bk_third_count: int
    average_bk_rank: float
    average_actual_bk_probability: float
    pool_top_differs_from_bk_top_count: int
    actual_contradicts_pool_and_bk_top_count: int


@dataclass(frozen=True)
class BriefOracleEventRow:
    drawing_id: int
    drawing_number: int | None
    event_order: int
    event_name: str
    result: str
    selected_cover: str
    selected_cover_size: int
    bk_rank: int
    actual_bk_probability: float
    bk_top: str
    pool_top: str | None
    pool_top_differs_from_bk_top: bool
    actual_contradicts_pool_and_bk_top: bool
    bookmaker_entropy: float


@dataclass(frozen=True)
class BriefOracleResult:
    rows: list[BriefOracleRow]
    event_rows: list[BriefOracleEventRow]
    summary: dict[str, Any]


def run_brief_oracle_research(
    session: Session,
    last: int = 500,
    community: str = "baltbet-main",
) -> BriefOracleResult:
    if last <= 0:
        raise ValueError("Last must be a positive integer.")

    rows: list[BriefOracleRow] = []
    event_rows: list[BriefOracleEventRow] = []
    for drawing in _select_complete_finished_drawings(session, last, community):
        events, quotes = _drawing_events_and_quotes(session, drawing.id)
        event_inputs = []
        skip_drawing = False
        for event in events:
            if event.event_order is None or event.event_order not in quotes:
                skip_drawing = True
                break
            quote = quotes[event.event_order]
            actual = normalize_result(event.result)
            bk = _outcome_probabilities(quote, "bk")
            if actual is None or bk is None:
                skip_drawing = True
                break
            event_inputs.append((event, quote, actual, bk))
        if skip_drawing or len(event_inputs) != 15:
            continue

        option_groups = [
            choose_event_cover_options(bk_probabilities=bk, actual_result=actual)
            for _, _, actual, bk in event_inputs
        ]
        oracle = choose_oracle_brief(option_groups)
        ranks = [
            outcome_rank(bk, actual)
            for _, _, actual, bk in event_inputs
        ]
        actual_probabilities = [
            bk[actual]
            for _, _, actual, bk in event_inputs
        ]
        pool_differs = 0
        contradicted_both = 0
        drawing_event_rows = []

        for selected_cover, (event, quote, actual, bk), rank in zip(
            oracle.brief,
            event_inputs,
            ranks,
            strict=True,
        ):
            pool = _outcome_probabilities(quote, "pool")
            bk_top = top_outcome(bk)
            pool_top = top_outcome(pool) if pool is not None else None
            pool_top_differs = pool_top is not None and pool_top != bk_top
            contradicted = (
                pool_top is not None and actual != pool_top and actual != bk_top
            )
            pool_differs += int(pool_top_differs)
            contradicted_both += int(contradicted)
            drawing_event_rows.append(
                BriefOracleEventRow(
                    drawing_id=drawing.id,
                    drawing_number=drawing.number,
                    event_order=event.event_order or 0,
                    event_name=event.name or "",
                    result=actual,
                    selected_cover=selected_cover,
                    selected_cover_size=len(selected_cover),
                    bk_rank=rank,
                    actual_bk_probability=round(bk[actual] * 100, 4),
                    bk_top=bk_top,
                    pool_top=pool_top,
                    pool_top_differs_from_bk_top=pool_top_differs,
                    actual_contradicts_pool_and_bk_top=contradicted,
                    bookmaker_entropy=round(_entropy(bk), 6),
                )
            )

        rows.append(
            BriefOracleRow(
                drawing_id=drawing.id,
                drawing_number=drawing.number,
                singles_count=oracle.singles_count,
                doubles_count=oracle.doubles_count,
                triples_count=oracle.triples_count,
                full_variant_count=oracle.full_variant_count,
                log_brief_probability=round(oracle.log_brief_probability, 6),
                actual_result_string=oracle.actual_result_string,
                oracle_brief_string=",".join(oracle.brief),
                actual_bk_top_count=sum(rank == 1 for rank in ranks),
                actual_bk_second_count=sum(rank == 2 for rank in ranks),
                actual_bk_third_count=sum(rank == 3 for rank in ranks),
                average_bk_rank=round(mean(ranks), 4),
                average_actual_bk_probability=round(
                    mean(actual_probabilities) * 100,
                    4,
                ),
                pool_top_differs_from_bk_top_count=pool_differs,
                actual_contradicts_pool_and_bk_top_count=contradicted_both,
            )
        )
        event_rows.extend(drawing_event_rows)

    return BriefOracleResult(
        rows=rows,
        event_rows=event_rows,
        summary=summarize_brief_oracle(rows, event_rows),
    )


def choose_event_cover_options(
    bk_probabilities: dict[str, float],
    actual_result: str,
) -> list[EventCoverOption]:
    if actual_result not in OUTCOMES:
        raise ValueError(f"Unsupported result: {actual_result}")

    ranked = ranked_outcomes(bk_probabilities)
    top = ranked[0]
    covers: list[str]
    if actual_result == top:
        covers = [actual_result]
    else:
        top_actual = _ordered_cover({top, actual_result})
        covers = [top_actual, "1X2"]

    options = [
        EventCoverOption(
            cover=cover,
            actual_result=actual_result,
            log_probability=math.log(
                max(sum(bk_probabilities[outcome] for outcome in cover), 1e-15)
            ),
            full_variant_count=len(cover),
        )
        for cover in covers
    ]
    return sorted(options, key=lambda option: (option.full_variant_count, option.cover))


def choose_oracle_brief(option_groups: list[list[EventCoverOption]]) -> OracleBrief:
    if not option_groups:
        raise ValueError("At least one event is required.")

    best: tuple[tuple[int, int, int, float], tuple[EventCoverOption, ...]] | None = None
    for selection in product(*option_groups):
        full_variant_count = math.prod(
            option.full_variant_count for option in selection
        )
        non_single_count = sum(option.full_variant_count > 1 for option in selection)
        triples_count = sum(option.full_variant_count == 3 for option in selection)
        log_probability = sum(option.log_probability for option in selection)
        key = (full_variant_count, non_single_count, triples_count, -log_probability)
        if best is None or key < best[0]:
            best = (key, selection)

    if best is None:
        raise ValueError("Could not choose an oracle brief.")

    selection = best[1]
    brief = [option.cover for option in selection]
    return OracleBrief(
        brief=brief,
        full_variant_count=math.prod(len(cover) for cover in brief),
        log_brief_probability=sum(option.log_probability for option in selection),
        actual_result_string="".join(group[0].actual_result for group in option_groups),
        singles_count=sum(len(cover) == 1 for cover in brief),
        doubles_count=sum(len(cover) == 2 for cover in brief),
        triples_count=sum(len(cover) == 3 for cover in brief),
    )


def outcome_rank(probabilities: dict[str, float], outcome: str) -> int:
    return ranked_outcomes(probabilities).index(outcome) + 1


def ranked_outcomes(probabilities: dict[str, float]) -> list[str]:
    missing = [outcome for outcome in OUTCOMES if outcome not in probabilities]
    if missing:
        raise ValueError(f"Missing probabilities for: {', '.join(missing)}")
    return sorted(OUTCOMES, key=lambda outcome: (-probabilities[outcome], outcome))


def top_outcome(probabilities: dict[str, float] | None) -> str | None:
    if probabilities is None:
        return None
    return ranked_outcomes(probabilities)[0]


def summarize_brief_oracle(
    rows: list[BriefOracleRow],
    event_rows: list[BriefOracleEventRow],
) -> dict[str, Any]:
    variant_counts = [row.full_variant_count for row in rows]
    rank_counts = {
        rank: sum(event.bk_rank == rank for event in event_rows)
        for rank in (1, 2, 3)
    }
    event_count = len(event_rows)
    return {
        "drawings_tested": len(rows),
        "average_singles": _average([row.singles_count for row in rows]),
        "average_doubles": _average([row.doubles_count for row in rows]),
        "average_triples": _average([row.triples_count for row in rows]),
        "median_full_variant_count": _median(variant_counts),
        "p25_full_variant_count": _percentile(variant_counts, 25),
        "p50_full_variant_count": _percentile(variant_counts, 50),
        "p75_full_variant_count": _percentile(variant_counts, 75),
        "p90_full_variant_count": _percentile(variant_counts, 90),
        "doubles_distribution": _distribution(
            [row.doubles_count for row in rows]
        ),
        "triples_distribution": _distribution(
            [row.triples_count for row in rows]
        ),
        "bk_rank_frequency": {
            rank: {
                "count": count,
                "percentage": _rate(count, event_count),
            }
            for rank, count in rank_counts.items()
        },
        "average_actual_result_bk_probability": _average(
            [event.actual_bk_probability for event in event_rows]
        ),
        "entropy_by_cover_size": _entropy_by_cover_size(event_rows),
    }


def write_brief_oracle_reports(
    result: BriefOracleResult,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "brief_oracle.csv"
    markdown_path = output_dir / "brief_oracle.md"
    event_csv_path = output_dir / "brief_oracle_by_event.csv"

    _write_rows_csv(result.rows, csv_path)
    _write_event_rows_csv(result.event_rows, event_csv_path)
    markdown_path.write_text(build_brief_oracle_markdown(result), encoding="utf-8")
    return csv_path, markdown_path, event_csv_path


def build_brief_oracle_markdown(result: BriefOracleResult) -> str:
    lines = [
        "# Brief Oracle Research",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in result.summary.items():
        if isinstance(value, dict):
            continue
        lines.append(f"| {key.replace('_', ' ')} | {value} |")

    lines.extend(
        [
            "",
            "## BK Rank Frequency",
            "",
            "| Rank | Count | Percentage |",
            "| ---: | ---: | ---: |",
        ]
    )
    for rank, stats in result.summary["bk_rank_frequency"].items():
        lines.append(f"| {rank} | {stats['count']} | {stats['percentage']} |")

    lines.extend(
        [
            "",
            "## Drawings",
            "",
            "| Drawing | Singles | Doubles | Triples | Variants | Log Probability |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in result.rows:
        lines.append(
            "| "
            f"{row.drawing_number or row.drawing_id} | "
            f"{row.singles_count} | "
            f"{row.doubles_count} | "
            f"{row.triples_count} | "
            f"{row.full_variant_count} | "
            f"{row.log_brief_probability} |"
        )
    lines.append("")
    return "\n".join(lines)


def _select_complete_finished_drawings(
    session: Session,
    last: int,
    community: str,
) -> list[Drawing]:
    candidates = session.scalars(
        select(Drawing)
        .where(Drawing.name == community)
        .where(Drawing.status == "finished")
        .order_by(Drawing.number.desc(), Drawing.id.desc())
    ).all()

    selected = []
    for drawing in candidates:
        events = _drawing_events(session, drawing.id)
        if _has_complete_results(events):
            selected.append(drawing)
        if len(selected) == last:
            break
    return selected


def _drawing_events_and_quotes(
    session: Session,
    drawing_id: int,
) -> tuple[list[Event], dict[int, Quote]]:
    events = _drawing_events(session, drawing_id)
    quotes = {
        quote.event_order: quote
        for quote in session.scalars(
            select(Quote)
            .where(Quote.drawing_id == drawing_id)
            .order_by(Quote.event_order)
        ).all()
        if quote.event_order is not None
    }
    return events, quotes


def _drawing_events(session: Session, drawing_id: int) -> list[Event]:
    return list(
        session.scalars(
            select(Event)
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
    )


def _has_complete_results(events: list[Event]) -> bool:
    if len(events) != 15:
        return False
    return all(normalize_result(event.result) is not None for event in events)


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


def _ordered_cover(outcomes: set[str]) -> str:
    return "".join(outcome for outcome in OUTCOMES if outcome in outcomes)


def _entropy(probabilities: dict[str, float]) -> float:
    return -sum(
        probability * math.log(probability)
        for probability in probabilities.values()
        if probability > 0
    )


def _distribution(values: list[int]) -> dict[int, int]:
    return {
        value: values.count(value)
        for value in sorted(set(values))
    }


def _entropy_by_cover_size(
    event_rows: list[BriefOracleEventRow],
) -> dict[int, dict[str, float | int]]:
    result = {}
    for size in (1, 2, 3):
        values = [
            row.bookmaker_entropy
            for row in event_rows
            if row.selected_cover_size == size
        ]
        result[size] = {
            "event_count": len(values),
            "average_entropy": _average(values),
        }
    return result


def _average(values: list[int | float]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(float(median(values)), 4)


def _percentile(values: list[int], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * percentile / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(sorted_values[int(position)])
    lower_value = sorted_values[lower]
    upper_value = sorted_values[upper]
    fraction = position - lower
    return round(lower_value + (upper_value - lower_value) * fraction, 4)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)


def _write_rows_csv(rows: list[BriefOracleRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(BriefOracleRow.__dataclass_fields__.keys()),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def _write_event_rows_csv(rows: list[BriefOracleEventRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(BriefOracleEventRow.__dataclass_fields__.keys()),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
