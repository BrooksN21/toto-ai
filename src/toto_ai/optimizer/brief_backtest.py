from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.analytics.data_health import (
    DATA_HEALTH_CONTRACT_VERSION,
    require_data_health,
)
from toto_ai.analytics.history import normalize_result
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.optimizer.brief import (
    CoverEngineCache,
    analyze_event,
    build_baseline_brief,
)


@dataclass(frozen=True)
class BriefBacktestRow:
    drawing_id: int
    drawing_number: int | None
    result_string: str
    brief: list[str]
    actual_inside_brief: bool
    uncovered_outcomes: int
    best_coupon_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    brief_full_variants: int
    category_guarantee: str
    timed_out: bool
    candidate_generation_time: float
    scoring_time: float
    cover_time: float
    total_time: float


@dataclass(frozen=True)
class BriefBacktestResult:
    rows: list[BriefBacktestRow]
    summary: dict[str, Any]


def run_brief_backtest(
    session: Session,
    last: int,
    bank: int,
    stake: int = 30,
    category: int = 13,
    community: str = "baltbet-main",
    top_candidates: int = 20,
    max_candidate_briefs: int = 200,
    timeout_per_drawing: float | None = 30,
    cover_cache: CoverEngineCache | None = None,
    progress_callback=None,
    allow_unhealthy_research: bool = False,
) -> BriefBacktestResult:
    if last <= 0:
        raise ValueError("Last must be a positive integer.")

    started_at = time.perf_counter()
    rows = []
    cache = cover_cache or CoverEngineCache()
    drawings = select_complete_finished_drawings(session, last, community)
    gate = require_data_health(
        session,
        use_case="backtest_probability",
        drawing_ids=tuple(drawing.id for drawing in drawings),
        allow_unhealthy_research=allow_unhealthy_research,
    )
    for drawing in drawings:
        events, quotes = _drawing_events_and_quotes(session, drawing.id)
        result_string = build_result_string(events)
        try:
            analyses = [
                analyze_event(event, quotes[event.event_order])
                for event in events
                if event.event_order is not None and event.event_order in quotes
            ]
        except ValueError:
            continue
        if len(analyses) != 15:
            continue

        package = build_baseline_brief(
            analyses,
            category=category,
            bank=bank,
            stake=stake,
            top_candidates=top_candidates,
            max_candidate_briefs=max_candidate_briefs,
            timeout_per_drawing=timeout_per_drawing,
            cover_cache=cache,
            progress_callback=_drawing_progress_callback(
                progress_callback,
                drawing.number,
            ),
        )
        brief = package["brief"]
        uncovered = count_uncovered_outcomes(brief, result_string)
        best_hits = best_coupon_hits(package["selected_coupons"], result_string)

        rows.append(
            BriefBacktestRow(
                drawing_id=drawing.id,
                drawing_number=drawing.number,
                result_string=result_string,
                brief=brief,
                actual_inside_brief=uncovered == 0,
                uncovered_outcomes=uncovered,
                best_coupon_hits=best_hits,
                hit_13=best_hits >= 13,
                hit_14=best_hits >= 14,
                hit_15=best_hits == 15,
                package_size=len(package["selected_coupons"]),
                package_cost=package["cost"],
                brief_full_variants=package["full_brief_size"],
                category_guarantee=package["category_guarantee"],
                timed_out=package["timed_out"],
                candidate_generation_time=package["candidate_generation_time"],
                scoring_time=package["scoring_time"],
                cover_time=package["cover_time"],
                total_time=package["total_time"],
            )
        )

    execution_time = time.perf_counter() - started_at
    summary = summarize_brief_backtest(rows, execution_time)
    summary.update(
        {
            "data_health_contract_version": DATA_HEALTH_CONTRACT_VERSION,
            "data_health_override": gate.override_applied,
        }
    )
    return BriefBacktestResult(rows=rows, summary=summary)


def select_complete_finished_drawings(
    session: Session,
    last: int,
    community: str = "baltbet-main",
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


def build_result_string(events: list[Event]) -> str:
    ordered = sorted(events, key=lambda event: event.event_order or 0)
    if len(ordered) != 15:
        raise ValueError("Drawing must contain exactly 15 events.")

    outcomes = []
    for event in ordered:
        result = normalize_result(event.result)
        if result is None:
            raise ValueError("Drawing contains a missing or unsupported result.")
        outcomes.append(result)
    return "".join(outcomes)


def count_uncovered_outcomes(brief: list[str], result_string: str) -> int:
    if len(brief) != len(result_string):
        raise ValueError("Brief and result string must have the same length.")
    return sum(
        result not in pick
        for pick, result in zip(brief, result_string, strict=True)
    )


def best_coupon_hits(coupons: list[str], result_string: str) -> int:
    if not coupons:
        return 0
    return max(_coupon_hits(coupon, result_string) for coupon in coupons)


def summarize_brief_backtest(
    rows: list[BriefBacktestRow],
    execution_time: float,
) -> dict[str, Any]:
    tested = len(rows)
    return {
        "drawings_tested": tested,
        "brief_containment_rate": _rate(
            sum(row.actual_inside_brief for row in rows),
            tested,
        ),
        "average_uncovered_outcomes": _average(
            [row.uncovered_outcomes for row in rows]
        ),
        "average_best_coupon_hits": _average(
            [row.best_coupon_hits for row in rows]
        ),
        "hit_13_count": sum(row.hit_13 for row in rows),
        "hit_13_rate": _rate(sum(row.hit_13 for row in rows), tested),
        "hit_14_count": sum(row.hit_14 for row in rows),
        "hit_14_rate": _rate(sum(row.hit_14 for row in rows), tested),
        "hit_15_count": sum(row.hit_15 for row in rows),
        "hit_15_rate": _rate(sum(row.hit_15 for row in rows), tested),
        "average_package_size": _average([row.package_size for row in rows]),
        "average_package_cost": _average([row.package_cost for row in rows]),
        "average_brief_variants": _average(
            [row.brief_full_variants for row in rows]
        ),
        "timed_out_count": sum(row.timed_out for row in rows),
        "average_candidate_generation_time": _average_float(
            [row.candidate_generation_time for row in rows]
        ),
        "average_scoring_time": _average_float([row.scoring_time for row in rows]),
        "average_cover_time": _average_float([row.cover_time for row in rows]),
        "average_total_time_per_drawing": _average_float(
            [row.total_time for row in rows]
        ),
        "execution_time_seconds": round(execution_time, 4),
    }


def write_brief_backtest_reports(
    result: BriefBacktestResult,
    last: int,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"backtest_brief_last_{last}.csv"
    markdown_path = output_dir / f"backtest_brief_last_{last}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "drawing_id",
                "drawing_number",
                "result_string",
                "brief",
                "actual_inside_brief",
                "uncovered_outcomes",
                "best_coupon_hits",
                "hit_13",
                "hit_14",
                "hit_15",
                "package_size",
                "package_cost",
                "brief_full_variants",
                "category_guarantee",
                "timed_out",
                "candidate_generation_time",
                "scoring_time",
                "cover_time",
                "total_time",
            ],
        )
        writer.writeheader()
        for row in result.rows:
            writer.writerow(
                {
                    **row.__dict__,
                    "brief": ",".join(row.brief),
                }
            )

    markdown_path.write_text(
        build_brief_backtest_markdown(result),
        encoding="utf-8",
    )
    return csv_path, markdown_path


def build_brief_backtest_markdown(result: BriefBacktestResult) -> str:
    lines = [
        "# Baseline Brief Backtest",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in result.summary.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")

    lines.extend(
        [
            "",
            "## Drawings",
            "",
            "| Drawing | Inside Brief | Uncovered | Best Hits | 13 | 14 | 15 | "
            "Cost | Timed Out |",
            "| ---: | --- | ---: | ---: | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in result.rows:
        lines.append(
            "| "
            f"{row.drawing_number or row.drawing_id} | "
            f"{_yes_no(row.actual_inside_brief)} | "
            f"{row.uncovered_outcomes} | "
            f"{row.best_coupon_hits} | "
            f"{_yes_no(row.hit_13)} | "
            f"{_yes_no(row.hit_14)} | "
            f"{_yes_no(row.hit_15)} | "
            f"{row.package_cost} | "
            f"{_yes_no(row.timed_out)} |"
        )
    lines.append("")
    return "\n".join(lines)


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


def _coupon_hits(coupon: str, result_string: str) -> int:
    if len(coupon) != len(result_string):
        raise ValueError("Coupon and result string must have the same length.")
    return sum(
        coupon_outcome == result_outcome
        for coupon_outcome, result_outcome in zip(coupon, result_string, strict=True)
    )


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _average_float(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _drawing_progress_callback(progress_callback, drawing_number: int | None):
    if progress_callback is None:
        return None

    def callback(update: dict[str, Any]) -> None:
        progress_callback(
            {
                **update,
                "drawing_number": drawing_number,
            }
        )

    return callback
