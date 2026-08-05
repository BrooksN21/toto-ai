from collections import Counter
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing, Event, Quote

OUTCOMES = ("1", "X", "2")
VALUE_BUCKETS = (
    "<= -20%",
    "-20%..-10%",
    "-10%..0",
    "0..10%",
    "10%..20%",
    ">20%",
)

RESULT_ALIASES = {
    "1": "1",
    "win_1": "1",
    "home": "1",
    "x": "X",
    "draw": "X",
    "2": "2",
    "win_2": "2",
    "away": "2",
}


def get_drawings_summary(session: Session) -> dict[str, Any]:
    total_drawings = session.scalar(select(func.count(Drawing.id))) or 0
    finished_drawings = (
        session.scalar(
            select(func.count(Drawing.id)).where(Drawing.status == "finished")
        )
        or 0
    )
    total_events = session.scalar(select(func.count(Event.id))) or 0
    avg_pool_sum = session.scalar(select(func.avg(Drawing.pool_sum)))
    avg_jackpot = session.scalar(select(func.avg(Drawing.jackpot)))

    return {
        "total_drawings": total_drawings,
        "finished_drawings": finished_drawings,
        "total_events": total_events,
        "avg_pool_sum": _round_or_zero(avg_pool_sum),
        "avg_jackpot": _round_or_zero(avg_jackpot),
    }


def get_outcome_distribution(session: Session) -> dict[str, dict[str, float | int]]:
    results = _finished_results(session)
    return _distribution(results)


def get_position_distribution(
    session: Session,
) -> dict[int, dict[str, dict[str, float | int]]]:
    rows = session.execute(
        select(Event.event_order, Event.result)
        .join(Drawing, Drawing.id == Event.drawing_id)
        .where(Drawing.status == "finished")
        .where(Event.result.is_not(None))
    ).all()

    by_position: dict[int, list[str]] = {position: [] for position in range(1, 16)}
    for event_order, result in rows:
        if event_order is None:
            continue
        position = event_order + 1
        if position not in by_position:
            continue
        normalized = normalize_result(result)
        if normalized is not None:
            by_position[position].append(normalized)

    return {
        position: _distribution(results)
        for position, results in by_position.items()
    }


def get_crowd_accuracy(session: Session) -> dict[str, float | int]:
    rows = _finished_event_quote_rows(session)
    evaluated = 0
    crowd_hits = 0
    bookmaker_hits = 0
    agreements = 0

    for event, quote in rows:
        result = normalize_result(event.result)
        pool = _outcome_probabilities(quote, "pool")
        bookmaker = _outcome_probabilities(quote, "bk")
        if result is None or pool is None or bookmaker is None:
            continue

        crowd_top = _top_outcome(pool)
        bookmaker_top = _top_outcome(bookmaker)
        if crowd_top is None or bookmaker_top is None:
            continue

        evaluated += 1
        crowd_hits += int(crowd_top == result)
        bookmaker_hits += int(bookmaker_top == result)
        agreements += int(crowd_top == bookmaker_top)

    return {
        "events_evaluated": evaluated,
        "crowd_top_hit_rate": _percentage(crowd_hits, evaluated),
        "bookmaker_top_hit_rate": _percentage(bookmaker_hits, evaluated),
        "crowd_vs_bookmaker_agreement_rate": _percentage(agreements, evaluated),
    }


def get_value_buckets(session: Session) -> dict[str, dict[str, float | int]]:
    bucket_counts: dict[str, int] = {bucket: 0 for bucket in VALUE_BUCKETS}
    bucket_hits: dict[str, int] = {bucket: 0 for bucket in VALUE_BUCKETS}

    for event, quote in _finished_event_quote_rows(session):
        result = normalize_result(event.result)
        pool = _outcome_probabilities(quote, "pool")
        bookmaker = _outcome_probabilities(quote, "bk")
        if result is None or pool is None or bookmaker is None:
            continue

        for outcome in OUTCOMES:
            pool_probability = pool[outcome]
            bookmaker_probability = bookmaker[outcome]
            if pool_probability is None or bookmaker_probability is None:
                continue

            bucket = _value_bucket(bookmaker_probability - pool_probability)
            bucket_counts[bucket] += 1
            bucket_hits[bucket] += int(outcome == result)

    return {
        bucket: {
            "count": bucket_counts[bucket],
            "hit_rate": _percentage(bucket_hits[bucket], bucket_counts[bucket]),
        }
        for bucket in VALUE_BUCKETS
    }


def get_event_diagnostics(
    session: Session,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Event, Quote)
        .join(
            Quote,
            (Quote.drawing_id == Event.drawing_id)
            & (Quote.event_order == Event.event_order),
        )
        .order_by(Event.drawing_id, Event.event_order)
        .limit(limit)
    ).all()
    diagnostics = []

    for event, quote in rows:
        result = normalize_result(event.result)
        pool = _outcome_probabilities(quote, "pool")
        bookmaker = _outcome_probabilities(quote, "bk")
        pool_top = _top_outcome(pool) if pool is not None else None
        bookmaker_top = _top_outcome(bookmaker) if bookmaker is not None else None

        diagnostics.append(
            {
                "drawing_id": event.drawing_id,
                "event_order": event.event_order + 1
                if event.event_order is not None
                else None,
                "event_name": event.name,
                "score": event.score,
                "result": result,
                "pool_1": pool["1"] if pool else None,
                "pool_x": pool["X"] if pool else None,
                "pool_2": pool["2"] if pool else None,
                "bk_1": bookmaker["1"] if bookmaker else None,
                "bk_x": bookmaker["X"] if bookmaker else None,
                "bk_2": bookmaker["2"] if bookmaker else None,
                "pool_top": pool_top,
                "bk_top": bookmaker_top,
                "pool_hit": pool_top == result if result and pool_top else None,
                "bk_hit": bookmaker_top == result if result and bookmaker_top else None,
            }
        )

    return diagnostics


def normalize_result(result: str | None) -> str | None:
    if result is None:
        return None
    return RESULT_ALIASES.get(str(result).strip().lower())


def _finished_results(session: Session) -> list[str]:
    rows = session.execute(
        select(Event.result)
        .join(Drawing, Drawing.id == Event.drawing_id)
        .where(Drawing.status == "finished")
        .where(Event.result.is_not(None))
    ).all()
    return [
        normalized
        for (result,) in rows
        if (normalized := normalize_result(result)) is not None
    ]


def _finished_event_quote_rows(session: Session) -> Iterable[tuple[Event, Quote]]:
    return session.execute(
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


def _distribution(results: Iterable[str]) -> dict[str, dict[str, float | int]]:
    counts = Counter(results)
    total = sum(counts.values())
    return {
        outcome: {
            "count": counts[outcome],
            "percentage": _percentage(counts[outcome], total),
        }
        for outcome in OUTCOMES
    }


def _outcome_probabilities(
    quote: Quote,
    prefix: str,
) -> dict[str, float | None] | None:
    raw = {
        "1": getattr(quote, f"{prefix}_win_1"),
        "X": getattr(quote, f"{prefix}_draw"),
        "2": getattr(quote, f"{prefix}_win_2"),
    }
    probabilities = {
        outcome: _to_probability(value)
        for outcome, value in raw.items()
    }
    if any(value is None for value in probabilities.values()):
        return None
    return probabilities


def _to_probability(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    if value <= 1:
        return value
    return 1 / value


def _top_outcome(probabilities: dict[str, float | None]) -> str | None:
    if any(value is None for value in probabilities.values()):
        return None
    return max(OUTCOMES, key=lambda outcome: probabilities[outcome] or 0)


def _value_bucket(value: float) -> str:
    value = round(value, 10)
    if value <= -0.20:
        return "<= -20%"
    if value <= -0.10:
        return "-20%..-10%"
    if value < 0:
        return "-10%..0"
    if value < 0.10:
        return "0..10%"
    if value <= 0.20:
        return "10%..20%"
    return ">20%"


def _percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 4)


def _round_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(float(value), 4)
