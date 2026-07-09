import json
from pathlib import Path
from typing import Any

from toto_ai.db.models import Drawing, Event, Quote

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
}


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
) -> Path:
    path = Path(output_dir) / f"drawing_{drawing_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
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
