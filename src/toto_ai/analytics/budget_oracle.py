from __future__ import annotations

import csv
import json
import math
import time
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
    timed_out: bool
    candidate_count: int
    processed_candidate_count: int
    skipped_candidate_count: int
    candidate_generation_time: float
    cover_generation_time: float
    verification_time: float
    total_time: float
    generated_candidates: int
    unique_candidates: int
    cover_engine_calls: int
    cache_hits: int
    cache_misses: int
    pruned_by_cost_lower_bound: int
    pruned_by_dominance: int
    pruned_by_incumbent_bound: int
    cover_engine_calls_after_pruning: int
    average_brief_variant_count: float
    max_brief_variant_count: int
    average_cover_call_duration: float
    slowest_candidate_briefs: str


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
    timeout_per_drawing: float | None = 30,
    max_candidates: int | None = None,
    progress_callback=None,
    partial_csv_path: str | Path | None = None,
    profile_workload: bool = False,
    time_func=time.perf_counter,
) -> BudgetOracleResult:
    if last <= 0:
        raise ValueError("Last must be a positive integer.")
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")

    rows = []
    counts = {"processed": 0, "skipped": 0, "timed_out": 0}
    started_at = time_func()
    drawings = select_complete_finished_drawings(session, last, community)
    drawing_total = len(drawings)

    for drawing_index, drawing in enumerate(drawings, start=1):
        drawing_started_at = time_func()
        try:
            events, quotes = _drawing_events_and_quotes(session, drawing.id)
            result_string = build_result_string(events)
            generation_started_at = time_func()
            candidate_briefs = _candidate_oracle_briefs(events, quotes)
            candidate_generation_time = time_func() - generation_started_at
            if not candidate_briefs:
                counts["skipped"] += 1
                _emit_drawing_progress(
                    progress_callback,
                    drawing_number=drawing.number,
                    drawing_index=drawing_index,
                    drawing_total=drawing_total,
                    started_at=started_at,
                    processed_count=counts["processed"],
                    skipped_count=counts["skipped"],
                    timed_out_count=counts["timed_out"],
                    current_best_hits=0,
                    current_best_cost=0,
                    time_func=time_func,
                )
                continue

            oracle = choose_budget_oracle_package(
                candidate_briefs=candidate_briefs,
                result_string=result_string,
                category=category,
                bank=bank,
                stake=stake,
                cover_func=cover_func,
                timeout_per_drawing=timeout_per_drawing,
                max_candidates=max_candidates,
                progress_callback=_drawing_candidate_progress(
                    progress_callback,
                    drawing_number=drawing.number,
                    drawing_index=drawing_index,
                    drawing_total=drawing_total,
                    started_at=started_at,
                    processed_count=lambda counts=counts: counts["processed"],
                    skipped_count=lambda counts=counts: counts["skipped"],
                    timed_out_count=lambda counts=counts: counts["timed_out"],
                    time_func=time_func,
                ),
                profile_workload=profile_workload,
                time_func=time_func,
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
            total_time = time_func() - drawing_started_at
            counts["processed"] += 1
            counts["timed_out"] += int(oracle["timed_out"])

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
                    timed_out=oracle["timed_out"],
                    candidate_count=oracle["candidate_count"],
                    processed_candidate_count=oracle["processed_candidate_count"],
                    skipped_candidate_count=oracle["skipped_candidate_count"],
                    candidate_generation_time=round(candidate_generation_time, 4),
                    cover_generation_time=round(oracle["cover_generation_time"], 4),
                    verification_time=round(oracle["verification_time"], 4),
                    total_time=round(total_time, 4),
                    generated_candidates=oracle["workload"]["generated_candidates"],
                    unique_candidates=oracle["workload"]["unique_candidates"],
                    cover_engine_calls=oracle["workload"]["cover_engine_calls"],
                    cache_hits=oracle["workload"]["cache_hits"],
                    cache_misses=oracle["workload"]["cache_misses"],
                    pruned_by_cost_lower_bound=oracle["workload"][
                        "pruned_by_cost_lower_bound"
                    ],
                    pruned_by_dominance=oracle["workload"]["pruned_by_dominance"],
                    pruned_by_incumbent_bound=oracle["workload"][
                        "pruned_by_incumbent_bound"
                    ],
                    cover_engine_calls_after_pruning=oracle["workload"][
                        "cover_engine_calls_after_pruning"
                    ],
                    average_brief_variant_count=oracle["workload"][
                        "average_brief_variant_count"
                    ],
                    max_brief_variant_count=oracle["workload"][
                        "max_brief_variant_count"
                    ],
                    average_cover_call_duration=oracle["workload"][
                        "average_cover_call_duration"
                    ],
                    slowest_candidate_briefs=json.dumps(
                        oracle["workload"]["slowest_candidate_briefs"],
                        ensure_ascii=True,
                    ),
                )
            )
        except Exception:
            counts["skipped"] += 1

        _emit_drawing_progress(
            progress_callback,
            drawing_number=drawing.number,
            drawing_index=drawing_index,
            drawing_total=drawing_total,
            started_at=started_at,
            processed_count=counts["processed"],
            skipped_count=counts["skipped"],
            timed_out_count=counts["timed_out"],
            current_best_hits=rows[-1].oracle_best_hits if rows else 0,
            current_best_cost=rows[-1].oracle_package_cost if rows else 0,
            time_func=time_func,
        )
        if partial_csv_path is not None and drawing_index % 10 == 0:
            write_budget_oracle_csv(rows, partial_csv_path)

    return BudgetOracleResult(
        rows=rows,
        summary=summarize_budget_oracle(
            rows,
            processed_count=counts["processed"],
            skipped_count=counts["skipped"],
            timed_out_count=counts["timed_out"],
            execution_time=time_func() - started_at,
        ),
    )


def choose_budget_oracle_package(
    candidate_briefs: list[list[str]],
    result_string: str,
    category: int,
    bank: int,
    stake: int,
    cover_func=greedy_cover,
    timeout_per_drawing: float | None = None,
    max_candidates: int | None = None,
    progress_callback=None,
    profile_workload: bool = False,
    time_func=time.perf_counter,
) -> dict[str, Any]:
    if bank <= 0:
        raise ValueError("Bank must be a positive integer.")
    if stake <= 0:
        raise ValueError("Stake must be a positive integer.")

    max_coupons = bank // stake
    best = None
    started_at = time_func()
    cover_generation_time = 0.0
    verification_time = 0.0
    processed_candidate_count = 0
    skipped_candidate_count = 0
    timed_out = False
    all_candidates = _deduplicate_briefs(candidate_briefs)
    profiles = _candidate_profiles(
        all_candidates,
        result_string=result_string,
        category=category,
        stake=stake,
    )
    profiles = _prune_by_cost_lower_bound(profiles, bank=bank)
    pruned_by_cost_lower_bound = len(all_candidates) - len(profiles)
    if cover_func is greedy_cover:
        profiles, pruned_by_dominance = _prune_dominated_candidates(profiles)
    else:
        pruned_by_dominance = 0
    profiles = sorted(profiles, key=_candidate_sort_key)
    if max_candidates is not None:
        profiles = profiles[:max_candidates]
    cover_call_records = []
    pruned_by_incumbent_bound = 0

    for candidate_index, profile in enumerate(profiles, start=1):
        brief = profile["brief"]
        if processed_candidate_count > 0 and _timed_out(
            started_at,
            timeout_per_drawing,
            time_func,
        ):
            timed_out = True
            break
        if best is not None and _cannot_beat_incumbent(profile, best):
            pruned_by_incumbent_bound += 1
            continue

        cover_started_at = time_func()
        cover = cover_func(
            brief=brief,
            category=category,
            max_coupons=max_coupons,
        )
        cover_duration = time_func() - cover_started_at
        cover_generation_time += cover_duration
        processed_candidate_count += 1
        if profile_workload:
            cover_call_records.append(
                {
                    "brief": ",".join(brief),
                    "duration": round(cover_duration, 6),
                    "brief_variants": _brief_variants(brief),
                }
            )
        coupons = cover["selected_coupons"]
        cost = len(coupons) * stake
        if cost > bank:
            skipped_candidate_count += 1
            continue
        verification_started_at = time_func()
        hits = best_coupon_hits(coupons, result_string)
        verification_time += time_func() - verification_started_at
        candidate = {
            "brief": brief,
            "selected_coupons": coupons,
            "best_coupon_hits": hits,
            "package_size": len(coupons),
            "package_cost": cost,
            "brief_variants": profile["brief_variants"],
            "original_index": profile["original_index"],
        }
        if best is None or _oracle_rank_key(candidate) > _oracle_rank_key(best):
            best = candidate

        if progress_callback is not None:
            progress_callback(
                {
                    "candidate_index": candidate_index,
                    "candidate_total": len(profiles),
                    "current_best_hits": best["best_coupon_hits"] if best else 0,
                    "current_best_cost": best["package_cost"] if best else 0,
                }
            )

        if _timed_out(started_at, timeout_per_drawing, time_func):
            timed_out = True
            break

    if best is None:
        raise ValueError("No budget-constrained oracle package could be generated.")
    return {
        **best,
        "timed_out": timed_out,
        "candidate_count": len(all_candidates),
        "processed_candidate_count": processed_candidate_count,
        "skipped_candidate_count": skipped_candidate_count,
        "cover_generation_time": cover_generation_time,
        "verification_time": verification_time,
        "workload": _workload_profile(
            generated_candidates=len(candidate_briefs),
            all_candidates=all_candidates,
            evaluated_candidates=[profile["brief"] for profile in profiles],
            processed_candidate_count=processed_candidate_count,
            cover_call_records=cover_call_records,
            pruned_by_cost_lower_bound=pruned_by_cost_lower_bound,
            pruned_by_dominance=pruned_by_dominance,
            pruned_by_incumbent_bound=pruned_by_incumbent_bound,
        ),
    }


def summarize_budget_oracle(
    rows: list[BudgetOracleRow],
    processed_count: int | None = None,
    skipped_count: int = 0,
    timed_out_count: int | None = None,
    execution_time: float = 0.0,
) -> dict[str, Any]:
    tested = len(rows)
    processed = tested if processed_count is None else processed_count
    timed_out = (
        sum(row.timed_out for row in rows)
        if timed_out_count is None
        else timed_out_count
    )
    summary = {
        "drawings_tested": tested,
        "processed_count": processed,
        "skipped_count": skipped_count,
        "timed_out_count": timed_out,
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
        "average_candidate_generation_time": _average_float(
            [row.candidate_generation_time for row in rows]
        ),
        "average_cover_generation_time": _average_float(
            [row.cover_generation_time for row in rows]
        ),
        "average_verification_time": _average_float(
            [row.verification_time for row in rows]
        ),
        "average_total_time": _average_float([row.total_time for row in rows]),
        "execution_time_seconds": round(execution_time, 4),
    }
    summary.update(_summarize_workload(rows))
    return summary


def write_budget_oracle_reports(
    result: BudgetOracleResult,
    last: int,
    report_dir: str | Path = "reports",
) -> tuple[Path, Path]:
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"budget_oracle_last_{last}.csv"
    markdown_path = output_dir / f"budget_oracle_last_{last}.md"

    write_budget_oracle_csv(result.rows, csv_path)
    markdown_path.write_text(
        build_budget_oracle_markdown(result),
        encoding="utf-8",
    )
    return csv_path, markdown_path


def write_budget_oracle_csv(
    rows: list[BudgetOracleRow],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=list(BudgetOracleRow.__dataclass_fields__.keys()),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    return path


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
        if key == "slowest_candidate_briefs":
            continue
        lines.append(f"| {key.replace('_', ' ')} | {value} |")

    if result.summary.get("slowest_candidate_briefs"):
        lines.extend(
            [
                "",
                "## Slowest Candidate Briefs",
                "",
                "| Drawing | Duration | Variants | Brief |",
                "| ---: | ---: | ---: | --- |",
            ]
        )
        for record in result.summary["slowest_candidate_briefs"]:
            lines.append(
                "| "
                f"{record.get('drawing_number') or ''} | "
                f"{record.get('duration', 0)} | "
                f"{record.get('brief_variants', 0)} | "
                f"{record.get('brief', '')} |"
            )

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


def _oracle_rank_key(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(candidate["best_coupon_hits"]),
        -int(candidate["package_cost"]),
        -int(candidate["brief_variants"]),
        -int(candidate.get("original_index", 0)),
    )


def _brief_variants(brief: list[str]) -> int:
    return math.prod(len(position) for position in brief)


def _candidate_profiles(
    candidates: list[list[str]],
    result_string: str,
    category: int,
    stake: int,
) -> list[dict[str, Any]]:
    return [
        _candidate_profile(
            brief=brief,
            result_string=result_string,
            category=category,
            stake=stake,
            original_index=index,
        )
        for index, brief in enumerate(candidates)
    ]


def _candidate_profile(
    brief: list[str],
    result_string: str,
    category: int,
    stake: int,
    original_index: int,
) -> dict[str, Any]:
    brief_variants = _brief_variants(brief)
    lower_bound_coupons = _minimum_coupon_lower_bound(brief, category)
    return {
        "brief": brief,
        "original_index": original_index,
        "potential_best_hits": _potential_best_hits(brief, result_string),
        "brief_variants": brief_variants,
        "lower_bound_coupons": lower_bound_coupons,
        "lower_bound_cost": lower_bound_coupons * stake,
        "actual_covered_positions": frozenset(
            index
            for index, (position, result) in enumerate(
                zip(brief, result_string, strict=False)
            )
            if result in position
        ),
    }


def _minimum_coupon_lower_bound(brief: list[str], category: int) -> int:
    brief_variants = _brief_variants(brief)
    if brief_variants == 0:
        return 0
    max_coverable = _max_unrestricted_hamming_ball_size(len(brief), category)
    return max(1, math.ceil(brief_variants / max_coverable))


def _max_unrestricted_hamming_ball_size(length: int, category: int) -> int:
    max_errors = max(0, 15 - category)
    return sum(
        math.comb(length, errors) * (len(OUTCOMES) - 1) ** errors
        for errors in range(min(max_errors, length) + 1)
    )


def _potential_best_hits(brief: list[str], result_string: str) -> int:
    return sum(
        result in position
        for position, result in zip(brief, result_string, strict=False)
    )


def _prune_by_cost_lower_bound(
    profiles: list[dict[str, Any]],
    bank: int,
) -> list[dict[str, Any]]:
    return [
        profile
        for profile in profiles
        if profile["lower_bound_cost"] <= bank
    ]


def _prune_dominated_candidates(
    profiles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    kept = []
    pruned = 0
    for candidate in profiles:
        if any(
            _dominates_candidate(other, candidate)
            for other in profiles
            if other is not candidate
        ):
            pruned += 1
            continue
        kept.append(candidate)
    return kept, pruned


def _dominates_candidate(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    if left["original_index"] == right["original_index"]:
        return False
    if not right["actual_covered_positions"].issubset(
        left["actual_covered_positions"]
    ):
        return False
    if not _brief_is_position_subset(left["brief"], right["brief"]):
        return False
    return _candidate_bound_rank(left) >= _candidate_bound_rank(right)


def _brief_is_position_subset(left: list[str], right: list[str]) -> bool:
    if len(left) != len(right):
        return False
    return all(
        set(left_position).issubset(set(right_position))
        for left_position, right_position in zip(left, right, strict=True)
    )


def _candidate_bound_rank(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(profile["potential_best_hits"]),
        -int(profile["lower_bound_cost"]),
        -int(profile["brief_variants"]),
        -int(profile["original_index"]),
    )


def _candidate_sort_key(profile: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        -int(profile["potential_best_hits"]),
        int(profile["lower_bound_cost"]),
        int(profile["brief_variants"]),
        int(profile["original_index"]),
    )


def _cannot_beat_incumbent(
    profile: dict[str, Any],
    best: dict[str, Any],
) -> bool:
    best_rank = (
        int(best["best_coupon_hits"]),
        -int(best["package_cost"]),
        -int(best["brief_variants"]),
        -int(best.get("original_index", 0)),
    )
    return _candidate_bound_rank(profile) <= best_rank


def _workload_profile(
    generated_candidates: int,
    all_candidates: list[list[str]],
    evaluated_candidates: list[list[str]],
    processed_candidate_count: int,
    cover_call_records: list[dict[str, Any]],
    pruned_by_cost_lower_bound: int,
    pruned_by_dominance: int,
    pruned_by_incumbent_bound: int,
) -> dict[str, Any]:
    variant_counts = [_brief_variants(brief) for brief in evaluated_candidates]
    slowest = sorted(
        cover_call_records,
        key=lambda record: record["duration"],
        reverse=True,
    )[:10]
    return {
        "generated_candidates": generated_candidates,
        "unique_candidates": len(all_candidates),
        "cover_engine_calls": processed_candidate_count,
        "cache_hits": max(generated_candidates - len(all_candidates), 0),
        "cache_misses": processed_candidate_count,
        "pruned_by_cost_lower_bound": pruned_by_cost_lower_bound,
        "pruned_by_dominance": pruned_by_dominance,
        "pruned_by_incumbent_bound": pruned_by_incumbent_bound,
        "cover_engine_calls_after_pruning": processed_candidate_count,
        "average_brief_variant_count": _average_float(variant_counts),
        "max_brief_variant_count": max(variant_counts, default=0),
        "average_cover_call_duration": _average_float(
            [record["duration"] for record in cover_call_records]
        ),
        "slowest_candidate_briefs": slowest,
    }


def _summarize_workload(rows: list[BudgetOracleRow]) -> dict[str, Any]:
    slowest_records = []
    for row in rows:
        try:
            row_slowest = json.loads(row.slowest_candidate_briefs)
        except json.JSONDecodeError:
            row_slowest = []
        for record in row_slowest:
            slowest_records.append(
                {
                    **record,
                    "drawing_number": row.drawing_number,
                }
            )
    slowest_records.sort(
        key=lambda record: record.get("duration", 0),
        reverse=True,
    )
    return {
        "generated_candidates_total": sum(row.generated_candidates for row in rows),
        "unique_candidates_total": sum(row.unique_candidates for row in rows),
        "cover_engine_calls_total": sum(row.cover_engine_calls for row in rows),
        "cache_hits_total": sum(row.cache_hits for row in rows),
        "cache_misses_total": sum(row.cache_misses for row in rows),
        "pruned_by_cost_lower_bound_total": sum(
            row.pruned_by_cost_lower_bound for row in rows
        ),
        "pruned_by_dominance_total": sum(row.pruned_by_dominance for row in rows),
        "pruned_by_incumbent_bound_total": sum(
            row.pruned_by_incumbent_bound for row in rows
        ),
        "cover_engine_calls_after_pruning_total": sum(
            row.cover_engine_calls_after_pruning for row in rows
        ),
        "average_brief_variant_count": _average_float(
            [row.average_brief_variant_count for row in rows]
        ),
        "max_brief_variant_count": max(
            (row.max_brief_variant_count for row in rows),
            default=0,
        ),
        "average_cover_engine_call_duration": _average_float(
            [row.average_cover_call_duration for row in rows]
        ),
        "slowest_candidate_briefs": slowest_records[:10],
    }


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(count / total * 100, 4)


def _average_float(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(mean(values), 4)


def _timed_out(started_at: float, timeout: float | None, time_func) -> bool:
    return timeout is not None and time_func() - started_at >= timeout


def _drawing_candidate_progress(
    progress_callback,
    drawing_number,
    drawing_index,
    drawing_total,
    started_at,
    processed_count,
    skipped_count,
    timed_out_count,
    time_func,
):
    if progress_callback is None:
        return None

    def callback(update: dict[str, Any]) -> None:
        progress_callback(
            {
                **update,
                **_run_progress_payload(
                    drawing_number=drawing_number,
                    drawing_index=drawing_index,
                    drawing_total=drawing_total,
                    started_at=started_at,
                    processed_count=processed_count(),
                    skipped_count=skipped_count(),
                    timed_out_count=timed_out_count(),
                    current_best_hits=update.get("current_best_hits", 0),
                    current_best_cost=update.get("current_best_cost", 0),
                    time_func=time_func,
                ),
            }
        )

    return callback


def _emit_drawing_progress(
    progress_callback,
    drawing_number,
    drawing_index,
    drawing_total,
    started_at,
    processed_count,
    skipped_count,
    timed_out_count,
    current_best_hits,
    current_best_cost,
    time_func,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        _run_progress_payload(
            drawing_number=drawing_number,
            drawing_index=drawing_index,
            drawing_total=drawing_total,
            started_at=started_at,
            processed_count=processed_count,
            skipped_count=skipped_count,
            timed_out_count=timed_out_count,
            current_best_hits=current_best_hits,
            current_best_cost=current_best_cost,
            time_func=time_func,
        )
    )


def _run_progress_payload(
    drawing_number,
    drawing_index,
    drawing_total,
    started_at,
    processed_count,
    skipped_count,
    timed_out_count,
    current_best_hits,
    current_best_cost,
    time_func,
) -> dict[str, Any]:
    elapsed = max(time_func() - started_at, 0.0)
    average_time = elapsed / drawing_index if drawing_index else 0.0
    remaining = max(drawing_total - drawing_index, 0)
    return {
        "drawing_number": drawing_number,
        "drawing_index": drawing_index,
        "drawing_total": drawing_total,
        "elapsed_time": round(elapsed, 4),
        "average_time_per_drawing": round(average_time, 4),
        "eta_seconds": round(average_time * remaining, 4),
        "current_best_hits": current_best_hits,
        "current_best_cost": current_best_cost,
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "timed_out_count": timed_out_count,
    }
