from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from toto_ai.analytics.history import (
    get_crowd_accuracy,
    get_drawings_summary,
    get_outcome_distribution,
    get_position_distribution,
    get_value_buckets,
    normalize_result,
)
from toto_ai.db.models import Drawing, Event, Quote

DRAWING_FIELDS = (
    "id",
    "number",
    "name",
    "status",
    "pool_sum",
    "jackpot",
    "started_at",
    "ended_at",
)

EVENT_FIELDS = (
    "name",
    "championship",
    "sport",
    "result",
    "score",
)

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
    "norm_win_1",
    "norm_draw",
    "norm_win_2",
)


def run_validation(
    session: Session,
    raw_payload: dict[str, Any],
    number: int,
) -> dict[str, Any]:
    raw_vs_sqlite = validate_raw_vs_sqlite(session, raw_payload)
    analytics = validate_analytics(session)
    quote_totals = get_quote_totals(session, raw_payload["data"]["id"])
    result_mapping = validate_event_field_mapping(
        session,
        raw_payload,
        field="result",
        normalize=True,
    )
    score_mapping = validate_event_field_mapping(
        session,
        raw_payload,
        field="score",
    )

    sections = (raw_vs_sqlite, analytics, result_mapping, score_mapping)
    overall_status = (
        "PASS"
        if all(section["status"] == "PASS" for section in sections)
        else "FAIL"
    )

    return {
        "number": number,
        "drawing_id": raw_payload["data"]["id"],
        "overall_status": overall_status,
        "raw_vs_sqlite": raw_vs_sqlite,
        "analytics": analytics,
        "quote_totals": quote_totals,
        "result_mapping": result_mapping,
        "score_mapping": score_mapping,
    }


def validate_raw_vs_sqlite(
    session: Session,
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    data = raw_payload["data"]
    drawing = session.get(Drawing, data["id"])
    mismatches = []

    if drawing is None:
        return {
            "status": "FAIL",
            "mismatches": [
                {
                    "field": "drawings.id",
                    "raw": data["id"],
                    "sqlite": None,
                }
            ],
        }

    for field in DRAWING_FIELDS:
        _append_mismatch(
            mismatches,
            field=f"drawings.{field}",
            raw=data.get(field),
            stored=getattr(drawing, field),
        )

    events = session.scalars(
        select(Event)
        .where(Event.drawing_id == drawing.id)
        .order_by(Event.event_order)
    ).all()
    quotes = {
        quote.event_order: quote
        for quote in session.scalars(
            select(Quote).where(Quote.drawing_id == drawing.id)
        ).all()
    }
    raw_event_orders = {
        raw_event.get("order")
        for raw_event in data.get("events") or []
    }
    stored_event_orders = {event.event_order for event in events}
    for extra_order in sorted(
        stored_event_orders - raw_event_orders,
        key=lambda value: -1 if value is None else value,
    ):
        mismatches.append(
            {
                "field": f"events[{extra_order}]",
                "raw": None,
                "sqlite": extra_order,
            }
        )

    for index, raw_event in enumerate(data.get("events") or []):
        event = next(
            (
                candidate
                for candidate in events
                if candidate.event_order == raw_event.get("order")
            ),
            None,
        )
        if event is None:
            mismatches.append(
                {
                    "field": f"events[{index}]",
                    "raw": raw_event.get("order"),
                    "sqlite": None,
                }
            )
            continue

        _append_mismatch(
            mismatches,
            field=f"events[{index}].order",
            raw=raw_event.get("order"),
            stored=event.event_order,
        )
        for field in EVENT_FIELDS:
            _append_mismatch(
                mismatches,
                field=f"events[{index}].{field}",
                raw=raw_event.get(field),
                stored=getattr(event, field),
            )

        quote = quotes.get(event.event_order)
        raw_quotes = raw_event.get("quotes") or {}
        for field in QUOTE_FIELDS:
            _append_mismatch(
                mismatches,
                field=f"events[{index}].quotes.{field}",
                raw=raw_quotes.get(field),
                stored=getattr(quote, field) if quote is not None else None,
            )

    return {
        "status": "PASS" if not mismatches else "FAIL",
        "mismatches": mismatches,
    }


def validate_analytics(session: Session) -> dict[str, Any]:
    manual = {
        "drawings_summary": _manual_drawings_summary(session),
        "outcome_distribution": _manual_outcome_distribution(session),
        "position_distribution": _manual_position_distribution(session),
        "crowd_accuracy": _manual_crowd_accuracy(session),
        "value_buckets": _manual_value_buckets(session),
    }
    module = {
        "drawings_summary": get_drawings_summary(session),
        "outcome_distribution": get_outcome_distribution(session),
        "position_distribution": get_position_distribution(session),
        "crowd_accuracy": get_crowd_accuracy(session),
        "value_buckets": get_value_buckets(session),
    }
    mismatches = [
        {
            "metric": metric,
            "manual": manual_value,
            "module": module[metric],
        }
        for metric, manual_value in manual.items()
        if manual_value != module[metric]
    ]
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "manual": manual,
        "module": module,
        "mismatches": mismatches,
    }


def get_quote_totals(
    session: Session,
    drawing_id: int,
) -> list[dict[str, float | int | None]]:
    quotes = session.scalars(
        select(Quote)
        .where(Quote.drawing_id == drawing_id)
        .order_by(Quote.event_order)
    ).all()
    rows = []
    for quote in quotes:
        total = _sum_present([quote.pool_win_1, quote.pool_draw, quote.pool_win_2])
        rows.append(
            {
                "event_order": quote.event_order + 1
                if quote.event_order is not None
                else None,
                "pool1": quote.pool_win_1,
                "poolX": quote.pool_draw,
                "pool2": quote.pool_win_2,
                "sum": total,
            }
        )
    return rows


def validate_event_field_mapping(
    session: Session,
    raw_payload: dict[str, Any],
    *,
    field: str,
    normalize: bool = False,
) -> dict[str, Any]:
    drawing_id = raw_payload["data"]["id"]
    events = {
        event.event_order: event
        for event in session.scalars(
            select(Event).where(Event.drawing_id == drawing_id)
        ).all()
    }
    mismatches = []
    for raw_event in raw_payload["data"].get("events") or []:
        event_order = raw_event.get("order")
        event = events.get(event_order)
        raw_value = raw_event.get(field)
        stored_value = getattr(event, field) if event is not None else None
        comparable_raw = normalize_result(raw_value) if normalize else raw_value
        comparable_stored = (
            normalize_result(stored_value) if normalize else stored_value
        )
        if comparable_raw != comparable_stored:
            mismatches.append(
                {
                    "event_order": event_order + 1 if event_order is not None else None,
                    "raw": raw_value,
                    "sqlite": stored_value,
                }
            )
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "mismatches": mismatches,
    }


def generate_validation_report(result: dict[str, Any]) -> str:
    lines = [
        f"# TotoAI Validation {result['number']}",
        "",
        f"Drawing id: {result['drawing_id']}",
        f"Overall status: {result['overall_status']}",
        "",
        "## Checks",
        "",
        f"- RAW JSON vs SQLite: {result['raw_vs_sqlite']['status']}",
        f"- Analytics manual SQL comparison: {result['analytics']['status']}",
        f"- Result mapping: {result['result_mapping']['status']}",
        f"- Score mapping: {result['score_mapping']['status']}",
        "",
        "## Quote Totals",
        "",
        "| event_order | pool1 | poolX | pool2 | sum |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in result["quote_totals"]:
        lines.append(
            f"| {row['event_order']} | {row['pool1']} | {row['poolX']} | "
            f"{row['pool2']} | {row['sum']} |"
        )

    for title, section in (
        ("RAW JSON vs SQLite mismatches", result["raw_vs_sqlite"]),
        ("Analytics mismatches", result["analytics"]),
        ("Result mapping mismatches", result["result_mapping"]),
        ("Score mapping mismatches", result["score_mapping"]),
    ):
        lines.extend(["", f"## {title}", ""])
        mismatches = section.get("mismatches") or []
        if not mismatches:
            lines.append("None")
        else:
            for mismatch in mismatches:
                lines.append(f"- `{mismatch}`")

    return "\n".join(lines) + "\n"


def write_validation_report(
    result: dict[str, Any],
    report_dir: str | Path = "reports",
) -> Path:
    path = Path(report_dir) / f"validation_{result['number']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_validation_report(result))
    return path


def _manual_drawings_summary(session: Session) -> dict[str, Any]:
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


def _manual_outcome_distribution(session: Session) -> dict[str, dict[str, float | int]]:
    return _distribution(_finished_results(session))


def _manual_position_distribution(
    session: Session,
) -> dict[int, dict[str, dict[str, float | int]]]:
    by_position = {position: [] for position in range(1, 16)}
    rows = session.execute(
        select(Event.event_order, Event.result)
        .join(Drawing, Drawing.id == Event.drawing_id)
        .where(Drawing.status == "finished")
        .where(Event.result.is_not(None))
    ).all()
    for event_order, result in rows:
        if event_order is None:
            continue
        position = event_order + 1
        normalized = normalize_result(result)
        if position in by_position and normalized:
            by_position[position].append(normalized)
    return {
        position: _distribution(results)
        for position, results in by_position.items()
    }


def _manual_crowd_accuracy(session: Session) -> dict[str, float | int]:
    evaluated = 0
    crowd_hits = 0
    bookmaker_hits = 0
    agreements = 0
    for event, quote in _finished_event_quote_rows(session):
        result = normalize_result(event.result)
        pool = _probabilities(quote, "pool")
        bookmaker = _probabilities(quote, "bk")
        if result is None or pool is None or bookmaker is None:
            continue
        crowd_top = _top_outcome(pool)
        bookmaker_top = _top_outcome(bookmaker)
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


def _manual_value_buckets(session: Session) -> dict[str, dict[str, float | int]]:
    buckets = ("<= -20%", "-20%..-10%", "-10%..0", "0..10%", "10%..20%", ">20%")
    counts = {bucket: 0 for bucket in buckets}
    hits = {bucket: 0 for bucket in buckets}
    for event, quote in _finished_event_quote_rows(session):
        result = normalize_result(event.result)
        pool = _probabilities(quote, "pool")
        bookmaker = _probabilities(quote, "bk")
        if result is None or pool is None or bookmaker is None:
            continue
        for outcome in ("1", "X", "2"):
            bucket = _value_bucket(bookmaker[outcome] - pool[outcome])
            counts[bucket] += 1
            hits[bucket] += int(outcome == result)
    return {
        bucket: {
            "count": counts[bucket],
            "hit_rate": _percentage(hits[bucket], counts[bucket]),
        }
        for bucket in buckets
    }


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


def _finished_event_quote_rows(session: Session) -> list[tuple[Event, Quote]]:
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


def _distribution(results: list[str]) -> dict[str, dict[str, float | int]]:
    total = len(results)
    return {
        outcome: {
            "count": results.count(outcome),
            "percentage": _percentage(results.count(outcome), total),
        }
        for outcome in ("1", "X", "2")
    }


def _probabilities(quote: Quote, prefix: str) -> dict[str, float] | None:
    values = {
        "1": _to_probability(getattr(quote, f"{prefix}_win_1")),
        "X": _to_probability(getattr(quote, f"{prefix}_draw")),
        "2": _to_probability(getattr(quote, f"{prefix}_win_2")),
    }
    if any(value is None for value in values.values()):
        return None
    return values


def _top_outcome(probabilities: dict[str, float]) -> str:
    return max(("1", "X", "2"), key=lambda outcome: probabilities[outcome])


def _to_probability(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    if value <= 1:
        return value
    return 1 / value


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


def _append_mismatch(
    mismatches: list[dict[str, Any]],
    *,
    field: str,
    raw: Any,
    stored: Any,
) -> None:
    if raw != stored:
        mismatches.append(
            {
                "field": field,
                "raw": raw,
                "sqlite": stored,
            }
        )


def _sum_present(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None
    return round(sum(value for value in values if value is not None), 10)


def _percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 4)


def _round_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(float(value), 4)
