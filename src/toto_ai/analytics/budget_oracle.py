from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from toto_ai.analytics.brief_oracle import (
    choose_event_cover_options,
    ranked_outcomes,
)
from toto_ai.db.models import Event, Quote
from toto_ai.optimizer.brief import (
    CoverEngineCache,
    analyze_event,
    build_baseline_brief,
)
from toto_ai.optimizer.brief_backtest import (
    best_coupon_hits,
    build_result_string,
    select_complete_finished_drawings,
)
from toto_ai.optimizer.cover import greedy_cover

OUTCOMES = ("1", "X", "2")


@dataclass(frozen=True)
class BudgetOracleRow:
    drawing_id: int
    drawing_number: int | None
    result_string: str
    oracle_brief: str
    oracle_best_hits: int
    oracle_hit_13: bool
    oracle_hit_14: bool
    oracle_hit_15: bool
    singles_count: int
    doubles_count: int
    triples_count: int
    oracle_package_size: int
    oracle_package_cost: int
    oracle_brief_variants: int
    baseline_best_hits: int
    baseline_package_size: int
    baseline_package_cost: int
    oracle_baseline_gap: int


@dataclass(frozen=True)
class BudgetOracleResult:
    rows: list[BudgetOracleRow]
    summary: dict[str, Any]


def run_budget_oracle(
    session: Session,
    last: int,
    bank: int,
    stake: int = 30,
    category: int = 13,
    community: str = "baltbet-main",
    cover_func=greedy_cover,
    baseline_func=None,
) -> BudgetOracleResult:
    if last <= 0:
        raise ValueError("Last must be a positive integer.")
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")

    rows = []
    for drawing in select_complete_finished_drawings(session, last, community):
        events, quotes = _drawing_events_and_quotes(session, drawing.id)
        result_string = build_result_string(events)
        candidate_briefs = _candidate_oracle_briefs(events, quotes)
        if not candidate_briefs:
            continue

        oracle = choose_budget_oracle_package(
            candidate_briefs=candidate_briefs,
            result_string=result_string,
            category=category,
            bank=bank,
            stake=stake,
            cover_func=cover_func,
        )
        baseline = _baseline_result(
            events=events,
            quotes=quotes,
            result_string=result_string,
            category=category,
            bank=bank,
            stake=stake,
            baseline_func=baseline_func,
        )

        rows.append(
            BudgetOracleRow(
                drawing_id=drawing.id,
                drawing_number=drawing.number,
                result_string=result_string,
                oracle_brief=",".join(oracle["brief"]),
                oracle_best_hits=oracle["best_coupon_hits"],
                oracle_hit_13=oracle["best_coupon_hits"] >= 13,
                oracle_hit_14=oracle["best_coupon_hits"] >= 14,
                oracle_hit_15=oracle["best_coupon_hits"] == 15,
                singles_count=sum(len(pick) == 1 for pick in oracle["brief"]),
                doubles_count=sum(len(pick) == 2 for pick in oracle["brief"]),
                triples_count=sum(len(pick) == 3 for pick in oracle["brief"]),
                oracle_package_size=oracle["package_size"],
                oracle_package_cost=oracle["package_cost"],
                oracle_brief_variants=oracle["brief_variants"],
                baseline_best_hits=baseline["baseline_best_hits"],
                baseline_package_size=baseline["baseline_package_size"],
                baseline_package_cost=baseline["baseline_package_cost"],
                oracle_baseline_gap=(
                    oracle["best_coupon_hits"] - baseline["baseline_best_hits"]
                ),
            )
        )

    return BudgetOracleResult(
        rows=rows,
        summary=summarize_budget_oracle(rows),
    )


def choose_budget_oracle_package(
    candidate_briefs: list[list[str]],
    result_string: str,
    category: int,
    bank: int,
    stake: int,
    cover_func=greedy_cover,
) -> dict[str, Any]:
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")

    max_coupons = bank // stake
    best = None
    for brief in _deduplicate_briefs(candidate_briefs):
        cover = cover_func(
            brief=brief,
            category=category,
            max_coupons=max_coupons,
        )
        coupons = cover["selected_coupons"]
        cost = len(coupons) * stake
        if cost > bank:
            continue
        candidate = {
            "brief": brief,
            "selected_coupons": coupons,
            "best_coupon_hits": best_coupon_hits(coupons, result_string),
            "package_size": len(coupons),
            "package_cost": cost,
            "brief_variants": _brief_variants(brief),
        }
        if best is None or _oracle_rank_key(candidate) > _oracle_rank_key(best):
            best = candidate

    if best is None:
        raise ValueError("No budget-constrained oracle package could be generated.")
    return best


def summarize_budget_oracle(rows: list[BudgetOracleRow]) -> dict[str, Any]:
    tested = len(rows)
    return {
        "drawings_tested": tested,
        "oracle_average_best_hits": _average(
            [row.oracle_best_hits for row in rows]
        ),
        "oracle_hit13_count": sum(row.oracle_hit_13 for row in rows),
        "oracle_hit13_rate": _rate(sum(row.oracle_hit_13 for row in rows), tested),
        "oracle_hit14_count": sum(row.oracle_hit_14 for row in rows),
        "oracle_hit14_rate": _rate(sum(row.oracle_hit_14 for row in rows), tested),
        "oracle_hit15_count": sum(row.oracle_hit_15 for row in rows),
        "oracle_hit15_rate": _rate(sum(row.oracle_hit_15 for row in rows), tested),
        "average_singles": _average([row.singles_count for row in rows]),
        "average_doubles": _average([row.doubles_count for row in rows]),
        "average_triples": _average([row.triples_count for row in rows]),
        "average_package_size": _average(
            [row.oracle_package_size for row in rows]
        ),
        "average_package_cost": _average(
            [row.oracle_package_cost for row in rows]
        ),
        "baseline_average_best_hits": _average(
            [row.baseline_best_hits for row in rows]
        ),
        "average_oracle_baseline_gap": _average(
            [row.oracle_baseline_gap for row in rows]
        ),
    }


def write_budget_oracle_reports(
    result: BudgetOracleResult,
    last: int,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"budget_oracle_last_{last}.csv"
    markdown_path = output_dir / f"budget_oracle_last_{last}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(BudgetOracleRow.__dataclass_fields__.keys()),
        )
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row.__dict__)

    markdown_path.write_text(
        build_budget_oracle_markdown(result),
        encoding="utf-8",
    )
    return csv_path, markdown_path


def build_budget_oracle_markdown(result: BudgetOracleResult) -> str:
    lines = [
        "# Budget-Constrained Brief Oracle",
        "",
        "This is an oracle benchmark that uses actual results to build candidate "
        "briefs. It is not a playable prediction method.",
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
            "| Drawing | Oracle Hits | Baseline Hits | Gap | Cost | Brief |",
            "| ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in result.rows:
        lines.append(
            "| "
            f"{row.drawing_number or row.drawing_id} | "
            f"{row.oracle_best_hits} | "
            f"{row.baseline_best_hits} | "
            f"{row.oracle_baseline_gap} | "
            f"{row.oracle_package_cost} | "
            f"{row.oracle_brief} |"
        )
    lines.append("")
    return "\n".join(lines)


def _candidate_oracle_briefs(
    events: list[Event],
    quotes: dict[int, Quote],
) -> list[list[str]]:
    option_groups = []
    result_string = build_result_string(events)
    for event, result in zip(events, result_string, strict=True):
        if event.event_order is None or event.event_order not in quotes:
            return []
        quote = quotes[event.event_order]
        bk = _quote_probabilities(quote, "bk")
        if bk is None:
            return []
        option_groups.append(
            [option.cover for option in choose_event_cover_options(bk, result)]
        )
    return [
        list(candidate)
        for candidate in product(*option_groups)
    ]


def _baseline_result(
    events: list[Event],
    quotes: dict[int, Quote],
    result_string: str,
    category: int,
    bank: int,
    stake: int,
    baseline_func,
) -> dict[str, int]:
    if baseline_func is not None:
        return baseline_func(events, quotes, result_string, category, bank, stake)

    try:
        analyses = [
            analyze_event(event, quotes[event.event_order])
            for event in events
            if event.event_order is not None and event.event_order in quotes
        ]
        if len(analyses) != 15:
            raise ValueError("Missing baseline analyses.")
        package = build_baseline_brief(
            analyses,
            category=category,
            bank=bank,
            stake=stake,
            cover_cache=CoverEngineCache(),
        )
    except ValueError:
        return {
            "baseline_best_hits": 0,
            "baseline_package_size": 0,
            "baseline_package_cost": 0,
        }

    coupons = package["selected_coupons"]
    return {
        "baseline_best_hits": best_coupon_hits(coupons, result_string),
        "baseline_package_size": len(coupons),
        "baseline_package_cost": package["cost"],
    }


def _drawing_events_and_quotes(
    session: Session,
    drawing_id: int,
) -> tuple[list[Event], dict[int, Quote]]:
    from sqlalchemy import select

    events = list(
        session.scalars(
            select(Event)
            .where(Event.drawing_id == drawing_id)
            .order_by(Event.event_order)
        ).all()
    )
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


def _quote_probabilities(quote: Quote, prefix: str) -> dict[str, float] | None:
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
    normalized = {
        outcome: probability / total
        for outcome, probability in probabilities.items()
    }
    ranked_outcomes(normalized)
    return normalized


def _to_probability(value: float) -> float:
    return value / 100 if value > 1 else value


def _deduplicate_briefs(briefs: list[list[str]]) -> list[list[str]]:
    deduped = []
    seen = set()
    for brief in briefs:
        key = tuple(brief)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(brief)
    return deduped


def _oracle_rank_key(candidate: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(candidate["best_coupon_hits"]),
        -int(candidate["package_cost"]),
        -int(candidate["brief_variants"]),
    )


def _brief_variants(brief: list[str]) -> int:
    return math.prod(len(position) for position in brief)


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)
