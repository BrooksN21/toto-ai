from __future__ import annotations

import csv
from pathlib import Path

from toto_ai.optimizer.strategy_backtest import StrategyBacktestRow

STRATEGIES = ("baseline_brief", "top_probability", "weighted_coverage")


def development_drawing_ids(manifest: dict[str, object]) -> list[int]:
    last = int(manifest["last"])
    holdout = int(manifest["holdout_size"])
    drawing_ids = list(manifest["drawing_ids"])
    if len(drawing_ids) != last or holdout < 0 or holdout > last:
        raise ValueError("Invalid frozen development split.")
    return drawing_ids[: last - holdout]


def load_frozen_development_rows(
    path: str | Path,
    manifest: dict[str, object],
) -> dict[tuple[int, str], StrategyBacktestRow]:
    development = set(development_drawing_ids(manifest))
    rows: dict[tuple[int, str], StrategyBacktestRow] = {}
    with Path(path).open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            drawing_id = int(raw["drawing_id"])
            if drawing_id not in development:
                continue
            row = _parse_strategy_backtest_row(raw)
            key = (drawing_id, row.strategy)
            if key in rows:
                raise ValueError("Expected exactly one frozen row per strategy.")
            rows[key] = row
    expected = {
        (drawing_id, strategy)
        for drawing_id in development
        for strategy in STRATEGIES
    }
    if set(rows) != expected:
        raise ValueError("Expected exactly one frozen row per strategy.")
    return rows


def _parse_strategy_backtest_row(raw: dict[str, str | None]) -> StrategyBacktestRow:
    return StrategyBacktestRow(
        drawing_id=int(raw["drawing_id"]),
        drawing_number=(
            None
            if not raw["drawing_number"]
            else int(raw["drawing_number"])
        ),
        segment=raw["segment"],
        strategy=raw["strategy"],
        best_hits=int(raw["best_hits"]),
        hit_13=_parse_bool(raw["hit_13"]),
        hit_14=_parse_bool(raw["hit_14"]),
        hit_15=_parse_bool(raw["hit_15"]),
        package_size=int(raw["package_size"]),
        package_cost=int(raw["package_cost"]),
        estimated_coverage=float(raw["estimated_coverage"]),
        candidate_count=int(raw["candidate_count"]),
        runtime_seconds=float(raw["runtime_seconds"]),
        package_hash=raw["package_hash"],
    )


def _parse_bool(value: str | None) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError("Frozen strategy boolean fields must be True or False.")
