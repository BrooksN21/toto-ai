from __future__ import annotations

import csv
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
from toto_ai.package.mvp import generate_mvp_package

OUTCOMES = ("1", "X", "2")
QUOTE_GROUPS = ("norm", "bk", "pool")


@dataclass(frozen=True)
class BacktestRow:
    drawing_id: int
    drawing_number: int | None
    result_string: str
    brief: str
    coupons: int
    cost: int
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    payout: float | None


@dataclass(frozen=True)
class BacktestResult:
    rows: list[BacktestRow]
    summary: dict[str, Any]


def run_mvp_backtest(
    session: Session,
    last: int,
    bank: int,
    stake: int = 30,
    category: int = 13,
    community: str = "baltbet-main",
    allow_unhealthy_research: bool = False,
) -> BacktestResult:
    if last <= 0:
        raise ValueError("Last must be a positive integer.")

    drawings = select_complete_finished_drawings(session, last, community)
    gate = require_data_health(
        session,
        use_case="backtest_probability",
        drawing_ids=tuple(drawing.id for drawing in drawings),
        allow_unhealthy_research=allow_unhealthy_research,
    )
    rows = []
    for drawing in drawings:
        events, quotes = _drawing_events_and_quotes(session, drawing.id)
        result_string = build_result_string(events)
        brief = build_mvp_brief(events, quotes)
        package = generate_mvp_package(
            brief=brief,
            bank=bank,
            stake=stake,
            category=category,
        )
        best_hits = best_coupon_hits(package.selected_coupons, result_string)
        rows.append(
            BacktestRow(
                drawing_id=drawing.id,
                drawing_number=drawing.number,
                result_string=result_string,
                brief=brief,
                coupons=len(package.selected_coupons),
                cost=package.cost,
                best_hits=best_hits,
                hit_13=best_hits >= 13,
                hit_14=best_hits >= 14,
                hit_15=best_hits == 15,
                payout=None,
            )
        )

    summary = summarize_backtest(rows)
    summary.update(
        {
            "data_health_contract_version": DATA_HEALTH_CONTRACT_VERSION,
            "data_health_override": gate.override_applied,
        }
    )
    return BacktestResult(rows=rows, summary=summary)


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
    ordered_events = sorted(events, key=lambda event: event.event_order or 0)
    if len(ordered_events) != 15:
        raise ValueError("Drawing must contain exactly 15 events.")

    outcomes = []
    for event in ordered_events:
        result = normalize_result(event.result)
        if result is None:
            raise ValueError("Drawing contains a missing or unsupported result.")
        outcomes.append(result)
    return "".join(outcomes)


def count_coupon_hits(coupon: str, result_string: str) -> int:
    if len(coupon) != len(result_string):
        raise ValueError("Coupon and result string must have the same length.")
    return sum(
        coupon_outcome == result_outcome
        for coupon_outcome, result_outcome in zip(coupon, result_string, strict=True)
    )


def best_coupon_hits(coupons: list[str], result_string: str) -> int:
    if not coupons:
        return 0
    return max(count_coupon_hits(coupon, result_string) for coupon in coupons)


def category_hits(best_hits: int) -> dict[str, bool]:
    return {
        "hit_13": best_hits >= 13,
        "hit_14": best_hits >= 14,
        "hit_15": best_hits == 15,
    }


def build_mvp_brief(events: list[Event], quotes: dict[int, Quote]) -> str:
    positions = []
    for event in sorted(events, key=lambda item: item.event_order or 0):
        if event.event_order is None or event.event_order not in quotes:
            raise ValueError("Drawing is missing pre-match quote data.")
        probabilities = _best_available_probabilities(quotes[event.event_order])
        if probabilities is None:
            raise ValueError("Drawing is missing usable pre-match probabilities.")
        positions.append(_brief_position(probabilities))
    return ",".join(positions)


def summarize_backtest(rows: list[BacktestRow]) -> dict[str, Any]:
    drawings_tested = len(rows)
    total_cost = sum(row.cost for row in rows)
    payouts = [row.payout for row in rows if row.payout is not None]
    total_payout = sum(payouts) if payouts else None

    return {
        "drawings_tested": drawings_tested,
        "avg_coupons": round(mean(row.coupons for row in rows), 4)
        if rows
        else 0.0,
        "avg_cost": round(mean(row.cost for row in rows), 4) if rows else 0.0,
        "hit_13_count": sum(row.hit_13 for row in rows),
        "hit_13_rate": _rate(sum(row.hit_13 for row in rows), drawings_tested),
        "hit_14_count": sum(row.hit_14 for row in rows),
        "hit_14_rate": _rate(sum(row.hit_14 for row in rows), drawings_tested),
        "hit_15_count": sum(row.hit_15 for row in rows),
        "hit_15_rate": _rate(sum(row.hit_15 for row in rows), drawings_tested),
        "total_cost": total_cost,
        "total_payout": total_payout,
        "roi": round((total_payout - total_cost) / total_cost * 100, 4)
        if total_payout is not None and total_cost
        else None,
    }


def write_backtest_reports(
    result: BacktestResult,
    last: int,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"backtest_mvp_last_{last}.csv"
    markdown_path = output_dir / f"backtest_mvp_last_{last}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "drawing_id",
                "drawing_number",
                "result_string",
                "brief",
                "coupons",
                "cost",
                "best_hits",
                "hit_13",
                "hit_14",
                "hit_15",
                "payout",
            ],
        )
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row.__dict__)

    markdown_path.write_text(build_backtest_markdown(result), encoding="utf-8")
    return csv_path, markdown_path


def build_backtest_markdown(result: BacktestResult) -> str:
    summary = result.summary
    lines = [
        "# MVP Package Backtest",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in summary.items():
        lines.append(f"| {key.replace('_', ' ')} | {_format_markdown_value(value)} |")

    lines.extend(
        [
            "",
            "## Drawings",
            "",
            "| Drawing | Coupons | Cost | Best hits | 13 | 14 | 15 | Payout |",
            "| ---: | ---: | ---: | ---: | --- | --- | --- | ---: |",
        ]
    )
    for row in result.rows:
        lines.append(
            "| "
            f"{row.drawing_number or row.drawing_id} | "
            f"{row.coupons} | "
            f"{row.cost} | "
            f"{row.best_hits} | "
            f"{_yes_no(row.hit_13)} | "
            f"{_yes_no(row.hit_14)} | "
            f"{_yes_no(row.hit_15)} | "
            f"{_format_markdown_value(row.payout)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _drawing_events_and_quotes(
    session: Session,
    drawing_id: int,
) -> tuple[list[Event], dict[int, Quote]]:
    events = _drawing_events(session, drawing_id)
    quote_rows = session.scalars(
        select(Quote)
        .where(Quote.drawing_id == drawing_id)
        .order_by(Quote.event_order)
    ).all()
    return events, {
        quote.event_order: quote
        for quote in quote_rows
        if quote.event_order is not None
    }


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


def _best_available_probabilities(quote: Quote) -> dict[str, float] | None:
    for group in QUOTE_GROUPS:
        probabilities = _quote_probabilities(quote, group)
        if probabilities is not None:
            return probabilities
    return None


def _quote_probabilities(quote: Quote, group: str) -> dict[str, float] | None:
    raw_values = {
        "1": getattr(quote, f"{group}_win_1"),
        "X": getattr(quote, f"{group}_draw"),
        "2": getattr(quote, f"{group}_win_2"),
    }
    if any(value is None or value <= 0 for value in raw_values.values()):
        return None

    if group == "norm":
        implied = {
            outcome: 1 / value
            for outcome, value in raw_values.items()
            if value is not None
        }
        total = sum(implied.values())
        if total <= 0:
            return None
        return {outcome: value / total for outcome, value in implied.items()}

    probabilities = {
        outcome: _stored_probability(value)
        for outcome, value in raw_values.items()
        if value is not None
    }
    if any(value is None for value in probabilities.values()):
        return None
    return probabilities


def _stored_probability(value: float) -> float | None:
    if value <= 0:
        return None
    return value / 100 if value > 1 else value


def _brief_position(probabilities: dict[str, float]) -> str:
    maximum = max(probabilities.values())
    return "".join(
        outcome
        for outcome in OUTCOMES
        if abs(probabilities[outcome] - maximum) < 1e-12
    )


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_markdown_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
