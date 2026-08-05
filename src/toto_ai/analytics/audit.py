from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from toto_ai.db.models import Drawing, Event, Quote

QUOTE_FIELDS = (
    "pool_win_1",
    "pool_draw",
    "pool_win_2",
    "bk_win_1",
    "bk_draw",
    "bk_win_2",
    "pin_win_1",
    "pin_draw",
    "pin_win_2",
)

PROVIDERS = {
    "pool": ("pool_win_1", "pool_draw", "pool_win_2"),
    "bk": ("bk_win_1", "bk_draw", "bk_win_2"),
    "pin": ("pin_win_1", "pin_draw", "pin_win_2"),
}


def get_database_audit(session: Session) -> dict[str, Any]:
    quote_completeness = get_quote_completeness(session)
    probability_validation = get_probability_validation(session)
    duplicates = get_duplicate_detection(session)

    return {
        "drawings": get_drawings_audit(session),
        "sports": get_sports_audit(session),
        "championships": get_championships_audit(session),
        "result_values": get_result_values_audit(session),
        "score": get_score_audit(session),
        "quote_completeness": quote_completeness,
        "probability_validation": probability_validation,
        "duplicates": duplicates,
        "quality_score": get_quality_score(
            session=session,
            quote_completeness=quote_completeness,
            probability_validation=probability_validation,
            duplicates=duplicates,
        ),
    }


def get_drawings_audit(session: Session) -> dict[str, Any]:
    statuses = Counter(
        status or "missing"
        for (status,) in session.execute(select(Drawing.status)).all()
    )
    return {
        "total": sum(statuses.values()),
        "finished": statuses["finished"],
        "active": statuses["active"],
        "other_statuses": {
            status: count
            for status, count in sorted(statuses.items())
            if status not in {"finished", "active"}
        },
    }


def get_sports_audit(session: Session) -> list[dict[str, int | str]]:
    return _dimension_counts(session, Event.sport, "sport")


def get_championships_audit(session: Session) -> list[dict[str, int | str]]:
    return _dimension_counts(session, Event.championship, "championship", limit=30)


def get_result_values_audit(session: Session) -> list[dict[str, int | str]]:
    return _dimension_counts(session, Event.result, "result")


def get_score_audit(session: Session) -> dict[str, int]:
    scores = session.execute(select(Event.score)).all()
    filled = sum(1 for (score,) in scores if score)
    return {
        "filled": filled,
        "empty": len(scores) - filled,
    }


def get_quote_completeness(session: Session) -> dict[str, dict[str, int]]:
    total_quotes = session.scalar(select(func.count(Quote.id))) or 0
    completeness = {}
    for field in QUOTE_FIELDS:
        column = getattr(Quote, field)
        filled = session.scalar(select(func.count(Quote.id)).where(column.is_not(None)))
        completeness[field] = {
            "filled": filled or 0,
            "missing": total_quotes - (filled or 0),
        }
    return completeness


def get_probability_validation(session: Session) -> dict[str, dict[str, float | int]]:
    quotes = session.scalars(select(Quote)).all()
    return {
        provider: _probability_stats(_probability_sums(quotes, fields))
        for provider, fields in PROVIDERS.items()
    }


def get_duplicate_detection(session: Session) -> dict[str, int]:
    drawing_duplicates = session.execute(
        select(Drawing.id)
        .group_by(Drawing.id)
        .having(func.count(Drawing.id) > 1)
    ).all()
    event_duplicates = session.execute(
        select(Event.drawing_id, Event.event_order)
        .group_by(Event.drawing_id, Event.event_order)
        .having(func.count(Event.id) > 1)
    ).all()
    return {
        "drawings": len(drawing_duplicates),
        "events": len(event_duplicates),
    }


def get_quality_score(
    session: Session,
    quote_completeness: dict[str, dict[str, int]],
    probability_validation: dict[str, dict[str, float | int]],
    duplicates: dict[str, int],
) -> float:
    score = get_score_audit(session)
    total_scores = score["filled"] + score["empty"]
    score_fill_rate = _ratio(score["filled"], total_scores)

    quote_filled = sum(field["filled"] for field in quote_completeness.values())
    quote_total = quote_filled + sum(
        field["missing"] for field in quote_completeness.values()
    )
    quote_fill_rate = _ratio(quote_filled, quote_total)

    quote_count = session.scalar(select(func.count(Quote.id))) or 0
    provider_total = quote_count * len(PROVIDERS)
    invalid_probability_sums = sum(
        int(stats["diff_gt_0_01"]) for stats in probability_validation.values()
    )
    probability_valid_rate = _ratio(
        provider_total - invalid_probability_sums,
        provider_total,
    )

    duplicate_penalty = min(1.0, (duplicates["drawings"] + duplicates["events"]) / 10)
    quality = (
        score_fill_rate
        + quote_fill_rate
        + probability_valid_rate
        + (1 - duplicate_penalty)
    ) / 4
    return round(quality * 100, 2)


def _dimension_counts(
    session: Session,
    column: Any,
    label: str,
    limit: int | None = None,
) -> list[dict[str, int | str]]:
    rows = session.execute(
        select(column, func.count(Event.id))
        .group_by(column)
        .order_by(func.count(Event.id).desc(), column)
        .limit(limit)
    ).all()
    return [
        {
            label: value or "missing",
            "count": count,
        }
        for value, count in rows
    ]


def _probability_stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {
            "min": 0.0,
            "max": 0.0,
            "average": 0.0,
            "diff_gt_0_001": 0,
            "diff_gt_0_01": 0,
            "diff_gt_0_05": 0,
        }

    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "average": round(sum(values) / len(values), 4),
        "diff_gt_0_001": _diff_count(values, 0.001),
        "diff_gt_0_01": _diff_count(values, 0.01),
        "diff_gt_0_05": _diff_count(values, 0.05),
    }


def _probability_sums(
    quotes: list[Quote],
    fields: tuple[str, str, str],
) -> list[float]:
    values = []
    for quote in quotes:
        value = _probability_sum(quote, fields)
        if value is not None:
            values.append(value)
    return values


def _probability_sum(quote: Quote, fields: tuple[str, str, str]) -> float | None:
    probabilities = []
    for field in fields:
        probability = _to_probability(getattr(quote, field))
        if probability is None:
            return None
        probabilities.append(probability)
    return round(sum(probabilities), 10)


def _to_probability(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    if value <= 1:
        return value
    return 1 / value


def _diff_count(values: list[float], threshold: float) -> int:
    return sum(1 for value in values if abs(value - 1) > threshold)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
