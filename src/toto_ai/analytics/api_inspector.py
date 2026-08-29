import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from toto_ai.api.detail_cache import (
    drawing_detail_cache_path,
    write_drawing_detail_cache,
)
from toto_ai.api.safe_paths import prepare_contained_parent
from toto_ai.db.models import Drawing, Event, Quote
from toto_ai.totobrief_time import parse_totobrief_timestamp

RAW_TO_DB_MAPPINGS = {
    "data.id": "drawings.id",
    "data.number": "drawings.number",
    "data.name": "drawings.name",
    "data.status": "drawings.status",
    "data.pool_sum": "drawings.pool_sum",
    "data.jackpot": "drawings.jackpot",
    "data.started_at": "drawings.started_at",
    "data.ended_at": "drawings.ended_at",
    "data.events[].order": "events.event_order",
    "data.events[].name": "events.name",
    "data.events[].championship": "events.championship",
    "data.events[].sport": "events.sport",
    "data.events[].result": "events.result",
    "data.events[].score": "events.score",
    "data.events[].quotes.pool_win_1": "quotes.pool_win_1",
    "data.events[].quotes.pool_draw": "quotes.pool_draw",
    "data.events[].quotes.pool_win_2": "quotes.pool_win_2",
    "data.events[].quotes.bk_win_1": "quotes.bk_win_1",
    "data.events[].quotes.bk_draw": "quotes.bk_draw",
    "data.events[].quotes.bk_win_2": "quotes.bk_win_2",
    "data.events[].quotes.pin_win_1": "quotes.pin_win_1",
    "data.events[].quotes.pin_draw": "quotes.pin_draw",
    "data.events[].quotes.pin_win_2": "quotes.pin_win_2",
    "data.events[].quotes.norm_win_1": "quotes.norm_win_1",
    "data.events[].quotes.norm_draw": "quotes.norm_draw",
    "data.events[].quotes.norm_win_2": "quotes.norm_win_2",
}


@dataclass(frozen=True)
class DrawingReference:
    drawing_id: int
    number: int | None
    community: str | None
    status: str | None
    ended_at: str | None = None


def resolve_drawing_reference(
    session: Session,
    *,
    drawing_id: int | None = None,
    number: int | None = None,
    latest_finished: bool = False,
    live: bool = False,
    open: bool = False,
    now: datetime | str | None = None,
    community: str = "baltbet-main",
    operational_cutoffs: Mapping[int, datetime] | None = None,
) -> DrawingReference:
    selected_options = sum(
        (drawing_id is not None, number is not None, latest_finished, live, open)
    )
    if selected_options != 1:
        raise ValueError(
            "Use exactly one of --drawing-id, --number, --latest-finished, "
            "--live, or --open."
        )

    if drawing_id is not None:
        drawing = session.get(Drawing, drawing_id)
        return _reference_from_id(drawing_id, drawing)

    if number is not None:
        drawing = session.scalar(
            select(Drawing)
            .where(Drawing.number == number)
            .where(Drawing.name == community)
            .order_by(Drawing.id.desc())
        )
        if drawing is None:
            drawing = session.scalar(
                select(Drawing)
                .where(Drawing.number == number)
                .order_by(Drawing.id.desc())
            )
        if drawing is None:
            raise ValueError(f"Drawing number {number} was not found in the database.")
        return _reference_from_drawing(drawing)

    if latest_finished:
        drawing = session.scalar(
            select(Drawing)
            .where(Drawing.name == community)
            .where(Drawing.status == "finished")
            .order_by(Drawing.number.desc(), Drawing.id.desc())
        )
        if drawing is None:
            raise ValueError(
                f"No finished {community} drawing was found in the database."
            )
        return _reference_from_drawing(drawing)

    current_time = _coerce_datetime(now)
    candidates = session.scalars(
        select(Drawing)
        .where(Drawing.name == community)
        .where(Drawing.status.in_(("active", "expected")))
        .where(Drawing.ended_at.is_not(None))
        .order_by(Drawing.number.desc(), Drawing.id.desc())
    ).all()
    drawing = _select_time_based_drawing(
        candidates,
        now=current_time,
        require_future=open,
        operational_cutoffs=operational_cutoffs,
    )
    if drawing is None:
        mode = "open" if open else "live"
        raise ValueError(f"No {mode} {community} drawing was found in the database.")
    return _reference_from_drawing(drawing)


def inspect_json_paths(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    _inspect_value(payload, path="", rows=rows)
    deduped = {}
    for row in rows:
        deduped.setdefault(row["path"], row)
    return list(deduped.values())


def save_raw_response(
    payload: dict[str, Any],
    drawing_id: int,
    output_dir: str | Path = "data/raw",
    *,
    allowed_root: str | Path = ".",
) -> Path:
    try:
        return write_drawing_detail_cache(
            payload,
            drawing_id=drawing_id,
            cache_dir=output_dir,
            source="inspect-api",
            allowed_root=allowed_root,
        ).path
    except ValueError:
        # The inspector is also used to save malformed/experimental payloads
        # for schema diagnostics. Such a file has no validated sidecar and is
        # therefore rejected by the operational detail-cache loader.
        path = prepare_contained_parent(
            drawing_detail_cache_path(
                drawing_id,
                output_dir,
                allowed_root=allowed_root,
            ),
            allowed_root=allowed_root,
        )
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return path


def compare_raw_json_to_db_model(payload: dict[str, Any]) -> dict[str, list[str]]:
    raw_paths = {
        row["path"]
        for row in inspect_json_paths(payload)
        if row["type"] not in {"object", "array"}
    }
    mapped_raw_paths = set(RAW_TO_DB_MAPPINGS)
    stored_fields = _stored_db_fields()

    return {
        "json_not_stored": sorted(raw_paths - mapped_raw_paths),
        "stored_fields": stored_fields,
        "missing_mappings": sorted(mapped_raw_paths - raw_paths),
    }


def _inspect_value(value: Any, path: str, rows: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if path and not path.endswith("[]"):
            rows.append({"path": path, "type": "object", "sample": "{}"})
        for key, nested_value in value.items():
            nested_path = f"{path}.{key}" if path else key
            _inspect_value(nested_value, nested_path, rows)
        return

    if isinstance(value, list):
        array_path = f"{path}[]"
        rows.append(
            {
                "path": array_path,
                "type": "array",
                "sample": f"{len(value)} item(s)",
            }
        )
        for item in value:
            _inspect_value(item, array_path, rows)
        return

    rows.append(
        {
            "path": path,
            "type": _json_type(value),
            "sample": value,
        }
    )


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _reference_from_id(
    drawing_id: int,
    drawing: Drawing | None,
) -> DrawingReference:
    if drawing is None:
        return DrawingReference(
            drawing_id=drawing_id,
            number=None,
            community=None,
            status=None,
            ended_at=None,
        )
    return _reference_from_drawing(drawing)


def _reference_from_drawing(drawing: Drawing) -> DrawingReference:
    return DrawingReference(
        drawing_id=drawing.id,
        number=drawing.number,
        community=drawing.name,
        status=drawing.status,
        ended_at=drawing.ended_at,
    )


def _select_time_based_drawing(
    drawings: list[Drawing],
    *,
    now: datetime,
    require_future: bool,
    operational_cutoffs: Mapping[int, datetime] | None = None,
) -> Drawing | None:
    parsed = [
        (
            drawing,
            _selection_deadline(
                drawing,
                _parse_drawing_deadline(drawing),
                operational_cutoffs,
            ),
        )
        for drawing in drawings
    ]
    valid = [
        (drawing, ended_at)
        for drawing, ended_at in parsed
        if ended_at is not None
    ]
    if require_future:
        future = [
            (drawing, ended_at)
            for drawing, ended_at in valid
            if ended_at > now
        ]
        if not future:
            return None
        return min(future, key=lambda item: (item[1], item[0].id))[0]

    locked = [
        (drawing, ended_at)
        for drawing, ended_at in valid
        if ended_at <= now
    ]
    if not locked:
        return None
    return max(locked, key=lambda item: (item[1], item[0].id))[0]


def _selection_deadline(
    drawing: Drawing,
    identity_deadline: datetime | None,
    operational_cutoffs: Mapping[int, datetime] | None,
) -> datetime | None:
    if identity_deadline is None:
        return None
    if operational_cutoffs is None or drawing.id not in operational_cutoffs:
        return identity_deadline
    cutoff = operational_cutoffs[drawing.id]
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
        raise ValueError("operational selection cutoff must be timezone-aware")
    normalized = cutoff.astimezone(timezone.utc)
    if normalized > identity_deadline:
        raise ValueError("operational selection cutoff cannot extend ended_at")
    return normalized


def _coerce_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"Invalid datetime: {value}")
    return parsed


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_drawing_deadline(drawing: Drawing) -> datetime | None:
    try:
        return parse_totobrief_timestamp(
            drawing.ended_at,
            community=drawing.name,
            field_name="stored drawing ended_at",
        )
    except ValueError:
        return None


def _stored_db_fields() -> list[str]:
    fields = []
    for model, table_name in (
        (Drawing, "drawings"),
        (Event, "events"),
        (Quote, "quotes"),
    ):
        fields.extend(
            f"{table_name}.{column.name}"
            for column in model.__table__.columns
        )
    return sorted(fields)
