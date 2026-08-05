#!/usr/bin/env python3
"""Read-only forensic audit of the local TotoAI BaltBet history.

This script intentionally uses only the Python standard library. It never
opens SQLite in write mode and writes artifacts only next to itself.
"""

# Report rows intentionally mirror their generated Markdown text.
# ruff: noqa: E501

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DB = ROOT / "data" / "toto.db"
BOOKMAKER = "baltbet-main"
OUTCOMES = {"1", "X", "2"}
VOID_OUTCOMES = {"*"}
EXPECTED_ORDERS = set(range(15))
IGNORED_PARTS = {
    ".git",
    ".venv",
    ".worktrees",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
JSON_SCAN_ROOTS = (
    ROOT / "data",
    ROOT / "reports",
    ROOT / "tests" / "fixtures",
)


@dataclass(frozen=True)
class RawSnapshot:
    drawing_id: int
    drawing_number: int
    status: str
    ended_at: str
    source: str
    source_kind: str
    payload_sha256: str
    event_count: int
    unique_orders: int
    nonblank_names: int
    pool_complete: int
    bk_complete: int
    norm_complete: int
    pin_complete: int
    resolved_results: int
    missing_results: int
    scores_present: int
    actual: str | None


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def complete_quote_triple(quotes: Any, fields: Sequence[str]) -> bool:
    if not isinstance(quotes, Mapping):
        return False
    values = [quotes.get(field) for field in fields]
    return (
        all(finite_number(value) for value in values)
        and sum(float(value) for value in values) > 0
    )


def iter_json_files() -> Iterator[Path]:
    for scan_root in JSON_SCAN_ROOTS:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.json"):
            if any(part in IGNORED_PARTS for part in path.parts):
                continue
            if OUT == path.parent or OUT in path.parents:
                continue
            if path.is_file():
                yield path


def iter_detail_objects(value: Any, *, depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        events = value.get("events")
        if (
            type(value.get("id")) is int
            and type(value.get("number")) is int
            and value.get("name") == BOOKMAKER
            and isinstance(events, list)
        ):
            yield value
        for child in value.values():
            yield from iter_detail_objects(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from iter_detail_objects(child, depth=depth + 1)


def raw_snapshot_from_detail(
    detail: Mapping[str, Any],
    *,
    source: str,
    source_kind: str,
) -> RawSnapshot:
    events = detail.get("events")
    raw_events = events if isinstance(events, list) else []
    orders = {
        event.get("order")
        for event in raw_events
        if isinstance(event, dict) and type(event.get("order")) is int
    }

    def quote_count(fields: Sequence[str]) -> int:
        return sum(
            complete_quote_triple(event.get("quotes"), fields)
            for event in raw_events
            if isinstance(event, dict)
        )

    results = [
        event.get("result")
        for event in sorted(
            (event for event in raw_events if isinstance(event, dict)),
            key=lambda event: event.get("order", -1),
        )
    ]
    actual = (
        "".join(results)
        if len(results) == 15 and all(result in OUTCOMES for result in results)
        else None
    )
    return RawSnapshot(
        drawing_id=int(detail["id"]),
        drawing_number=int(detail["number"]),
        status=str(detail.get("status") or ""),
        ended_at=str(detail.get("ended_at") or ""),
        source=source,
        source_kind=source_kind,
        payload_sha256=sha256_text(canonical_json(detail)),
        event_count=len(raw_events),
        unique_orders=len(orders),
        nonblank_names=sum(
            nonblank(event.get("name"))
            for event in raw_events
            if isinstance(event, dict)
        ),
        pool_complete=quote_count(("pool_win_1", "pool_draw", "pool_win_2")),
        bk_complete=quote_count(("bk_win_1", "bk_draw", "bk_win_2")),
        norm_complete=quote_count(("norm_win_1", "norm_draw", "norm_win_2")),
        pin_complete=quote_count(("pin_win_1", "pin_draw", "pin_win_2")),
        resolved_results=sum(result in OUTCOMES for result in results),
        missing_results=sum(result not in OUTCOMES for result in results),
        scores_present=sum(
            nonblank(event.get("score"))
            for event in raw_events
            if isinstance(event, dict)
        ),
        actual=actual,
    )


def scan_file_raw_snapshots() -> tuple[list[RawSnapshot], list[dict[str, str]]]:
    snapshots: list[RawSnapshot] = []
    errors: list[dict[str, str]] = []
    for path in sorted(set(iter_json_files())):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            errors.append(
                {
                    "source": str(path.relative_to(ROOT)),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        relative = str(path.relative_to(ROOT))
        for detail in iter_detail_objects(payload):
            snapshots.append(
                raw_snapshot_from_detail(
                    detail,
                    source=relative,
                    source_kind="file",
                )
            )
    return snapshots, errors


def scan_result_snapshot_payloads(
    connection: sqlite3.Connection,
) -> tuple[list[RawSnapshot], list[dict[str, str]]]:
    snapshots: list[RawSnapshot] = []
    errors: list[dict[str, str]] = []
    rows = connection.execute(
        """
        SELECT id, drawing_id, drawing_number, payload_json
        FROM drawing_result_snapshots
        ORDER BY id
        """
    ).fetchall()
    for row in rows:
        source = f"sqlite:drawing_result_snapshots:{row['id']}"
        try:
            payload = json.loads(row["payload_json"])
            details = list(iter_detail_objects(payload))
        except (TypeError, json.JSONDecodeError) as error:
            errors.append(
                {"source": source, "error": f"{type(error).__name__}: {error}"}
            )
            continue
        if len(details) != 1:
            errors.append(
                {
                    "source": source,
                    "error": f"expected one detail object, found {len(details)}",
                }
            )
            continue
        snapshots.append(
            raw_snapshot_from_detail(
                details[0],
                source=source,
                source_kind="result_snapshot_payload",
            )
        )
    return snapshots, errors


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def load_drawings(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, number, name, status, pool_sum, jackpot, started_at, ended_at
        FROM drawings
        WHERE name = ?
        ORDER BY number, id
        """,
        (BOOKMAKER,),
    ).fetchall()


def rows_by_drawing(
    connection: sqlite3.Connection,
    table: str,
    *,
    order_by: str = "drawing_id",
) -> dict[int, list[sqlite3.Row]]:
    if not table_exists(connection, table):
        return {}
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()
    result: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        result[int(row["drawing_id"])].append(row)
    return result


def count_complete_db_triple(row: sqlite3.Row, fields: Sequence[str]) -> bool:
    values = [row[field] for field in fields]
    return (
        all(finite_number(value) for value in values)
        and sum(float(value) for value in values) > 0
    )


def parse_snapshot_status_counts(rows: Sequence[sqlite3.Row]) -> tuple[int, int, int]:
    if not rows:
        return 0, 0, 0
    latest = max(rows, key=lambda row: (str(row["retrieved_at"]), int(row["id"])))
    try:
        events = json.loads(latest["events_json"])
    except (TypeError, json.JSONDecodeError):
        return 0, 0, 15
    resolved = sum(
        isinstance(event, dict) and event.get("result_status") == "resolved"
        for event in events
    )
    voids = sum(
        isinstance(event, dict) and event.get("result_status") == "void"
        for event in events
    )
    return resolved, voids, max(0, 15 - resolved - voids)


def preparation_summary(rows: Sequence[sqlite3.Row]) -> tuple[int, str, int]:
    if not rows:
        return 0, "", 0
    latest = max(rows, key=lambda row: (str(row["updated_at"]), int(row["id"])))
    return len(rows), str(latest["status"]), int(latest["mapped_count"])


def missing_orders(rows: Sequence[sqlite3.Row], field: str) -> str:
    orders = {
        row[field]
        for row in rows
        if type(row[field]) is int and row[field] in EXPECTED_ORDERS
    }
    return "|".join(str(order + 1) for order in sorted(EXPECTED_ORDERS - orders))


def duplicate_orders(rows: Sequence[sqlite3.Row], field: str) -> str:
    counts = Counter(row[field] for row in rows)
    return "|".join(
        str(order + 1)
        for order, count in sorted(counts.items(), key=lambda item: str(item[0]))
        if type(order) is int and count > 1
    )


def root_class(
    *,
    db_value: int,
    target: int,
    raw_values: Sequence[int],
    conflict: bool = False,
) -> tuple[str, str]:
    if db_value >= target:
        return "OK", "SQLite field is complete"
    if conflict:
        return "D", "saved RAW snapshots conflict"
    if not raw_values:
        return "C", "no local RAW/API snapshot is available"
    raw_best = max(raw_values)
    if raw_best > db_value:
        return (
            "A",
            f"saved RAW contains more data ({raw_best}) than SQLite ({db_value})",
        )
    return (
        "B",
        f"available RAW is already incomplete (best={raw_best}, target={target})",
    )


def write_csv(
    path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def anomaly(
    rows: list[dict[str, Any]],
    *,
    severity: str,
    drawing: Mapping[str, Any] | None,
    anomaly_type: str,
    scope: str,
    db_value: Any,
    raw_best_value: Any,
    root_cause_class: str,
    root_cause_reason: str,
    evidence_sources: str = "",
) -> None:
    rows.append(
        {
            "severity": severity,
            "drawing_number": "" if drawing is None else drawing["number"],
            "drawing_id": "" if drawing is None else drawing["id"],
            "year": "" if drawing is None else str(drawing["ended_at"] or "")[:4],
            "anomaly_type": anomaly_type,
            "scope": scope,
            "db_value": db_value,
            "raw_best_value": raw_best_value,
            "root_cause_class": root_cause_class,
            "root_cause_reason": root_cause_reason,
            "evidence_sources": evidence_sources,
        }
    )


def audit() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    drawings = load_drawings(connection)
    events = rows_by_drawing(connection, "events", order_by="drawing_id,event_order,id")
    quotes = rows_by_drawing(connection, "quotes", order_by="drawing_id,event_order,id")
    result_snapshots = rows_by_drawing(
        connection,
        "drawing_result_snapshots",
        order_by="drawing_id,retrieved_at,id",
    )
    preparations = rows_by_drawing(
        connection,
        "drawing_preparations",
        order_by="drawing_id,updated_at,id",
    )
    pins = rows_by_drawing(
        connection,
        "drawing_event_pins",
        order_by="drawing_id,event_order,id",
    )
    packages = rows_by_drawing(
        connection,
        "archived_packages",
        order_by="drawing_id,archived_at,archive_sha256",
    )
    settlements = rows_by_drawing(
        connection,
        "package_settlements",
        order_by="drawing_id,settled_at,settlement_sha256",
    )

    file_raw, file_errors = scan_file_raw_snapshots()
    db_raw, db_raw_errors = scan_result_snapshot_payloads(connection)
    raw_snapshots = file_raw + db_raw
    raw_by_drawing: dict[int, list[RawSnapshot]] = defaultdict(list)
    for snapshot in raw_snapshots:
        raw_by_drawing[snapshot.drawing_id].append(snapshot)

    number_counts = Counter(int(row["number"]) for row in drawings)
    min_number = min(number_counts)
    max_number = max(number_counts)
    gaps = [
        number
        for number in range(min_number, max_number + 1)
        if number not in number_counts
    ]
    duplicate_numbers = {
        number: count for number, count in number_counts.items() if count > 1
    }

    drawing_rows: list[dict[str, Any]] = []
    raw_comparison_rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for gap in gaps:
        anomaly(
            anomalies,
            severity="ERROR",
            drawing=None,
            anomaly_type="visible_number_gap",
            scope=BOOKMAKER,
            db_value=f"missing number {gap}",
            raw_best_value="",
            root_cause_class="C",
            root_cause_reason="no SQLite drawing row; no network verification in this audit",
        )
    for number, count in sorted(duplicate_numbers.items()):
        ids = [str(row["id"]) for row in drawings if int(row["number"]) == number]
        anomaly(
            anomalies,
            severity="ERROR",
            drawing=None,
            anomaly_type="duplicate_visible_number",
            scope=BOOKMAKER,
            db_value=f"{number}: {count} rows ({'|'.join(ids)})",
            raw_best_value="",
            root_cause_class="D",
            root_cause_reason="visible drawing identity is ambiguous inside baltbet-main",
        )

    for drawing in drawings:
        drawing_id = int(drawing["id"])
        event_rows = events.get(drawing_id, [])
        quote_rows = quotes.get(drawing_id, [])
        snapshot_rows = result_snapshots.get(drawing_id, [])
        prep_rows = preparations.get(drawing_id, [])
        pin_rows = pins.get(drawing_id, [])
        package_rows = packages.get(drawing_id, [])
        settlement_rows = settlements.get(drawing_id, [])
        raws = raw_by_drawing.get(drawing_id, [])
        sources = "|".join(sorted({raw.source for raw in raws}))

        event_orders = [row["event_order"] for row in event_rows]
        quote_orders = [row["event_order"] for row in quote_rows]
        blank_names = sum(not nonblank(row["name"]) for row in event_rows)
        pool_complete = sum(
            count_complete_db_triple(row, ("pool_win_1", "pool_draw", "pool_win_2"))
            for row in quote_rows
        )
        bk_complete = sum(
            count_complete_db_triple(row, ("bk_win_1", "bk_draw", "bk_win_2"))
            for row in quote_rows
        )
        norm_complete = sum(
            count_complete_db_triple(row, ("norm_win_1", "norm_draw", "norm_win_2"))
            for row in quote_rows
        )
        pin_complete = sum(
            count_complete_db_triple(row, ("pin_win_1", "pin_draw", "pin_win_2"))
            for row in quote_rows
        )
        resolved = sum(row["result"] in OUTCOMES for row in event_rows)
        voids = sum(row["result"] in VOID_OUTCOMES for row in event_rows)
        missing_results = sum(
            row["result"] is None or str(row["result"]).strip() == ""
            for row in event_rows
        )
        invalid_results = sum(
            row["result"] is not None
            and str(row["result"]).strip() != ""
            and row["result"] not in OUTCOMES | VOID_OUTCOMES
            for row in event_rows
        )
        scores_present = sum(nonblank(row["score"]) for row in event_rows)
        snapshot_resolved, snapshot_voids, snapshot_missing = (
            parse_snapshot_status_counts(snapshot_rows)
        )
        prep_count, prep_status, prep_mapped = preparation_summary(prep_rows)
        valid_pins = sum(
            row["status"] == "valid" and row["invalidated_at"] is None
            for row in pin_rows
        )
        complete_result_snapshots = sum(bool(row["complete"]) for row in snapshot_rows)
        raw_unique_hashes = len({raw.payload_sha256 for raw in raws})

        raw_event_values = [raw.event_count for raw in raws]
        raw_name_values = [raw.nonblank_names for raw in raws]
        raw_pool_values = [raw.pool_complete for raw in raws]
        raw_bk_values = [raw.bk_complete for raw in raws]
        raw_norm_values = [raw.norm_complete for raw in raws]
        raw_result_values = [raw.resolved_results for raw in raws]
        raw_actuals = {raw.actual for raw in raws if raw.actual is not None}
        result_conflict = len(raw_actuals) > 1

        classes = {
            "events": root_class(
                db_value=len(event_rows),
                target=15,
                raw_values=raw_event_values,
            ),
            "names": root_class(
                db_value=15 - blank_names,
                target=15,
                raw_values=raw_name_values,
            ),
            "pool": root_class(
                db_value=pool_complete,
                target=15,
                raw_values=raw_pool_values,
            ),
            "bk": root_class(
                db_value=bk_complete,
                target=15,
                raw_values=raw_bk_values,
            ),
            "norm": root_class(
                db_value=norm_complete,
                target=15,
                raw_values=raw_norm_values,
            ),
            "results": root_class(
                db_value=resolved + voids,
                target=15,
                raw_values=raw_result_values,
                conflict=result_conflict,
            ),
        }

        hard_anomalies_before = len(anomalies)
        if len(event_rows) != 15 or set(event_orders) != EXPECTED_ORDERS:
            cls, reason = classes["events"]
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="event_structure_incomplete",
                scope="events",
                db_value=(
                    f"rows={len(event_rows)},unique_orders={len(set(event_orders))},"
                    f"missing={missing_orders(event_rows, 'event_order')},"
                    f"duplicates={duplicate_orders(event_rows, 'event_order')}"
                ),
                raw_best_value=max(raw_event_values, default=""),
                root_cause_class=cls,
                root_cause_reason=reason,
                evidence_sources=sources,
            )
        if blank_names:
            cls, reason = classes["names"]
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="blank_event_names",
                scope="events.name",
                db_value=f"{blank_names} blank",
                raw_best_value=max(raw_name_values, default=""),
                root_cause_class=cls,
                root_cause_reason=reason,
                evidence_sources=sources,
            )
        if len(quote_rows) != 15 or set(quote_orders) != EXPECTED_ORDERS:
            raw_best = max(raw_pool_values + raw_bk_values, default="")
            cls, reason = root_class(
                db_value=len(quote_rows),
                target=15,
                raw_values=[raw.event_count for raw in raws if raw.pool_complete],
            )
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="quote_structure_incomplete",
                scope="quotes",
                db_value=(
                    f"rows={len(quote_rows)},unique_orders={len(set(quote_orders))},"
                    f"missing={missing_orders(quote_rows, 'event_order')},"
                    f"duplicates={duplicate_orders(quote_rows, 'event_order')}"
                ),
                raw_best_value=raw_best,
                root_cause_class=cls,
                root_cause_reason=reason,
                evidence_sources=sources,
            )
        for metric, value in (("pool", pool_complete), ("bk", bk_complete)):
            if value != 15:
                cls, reason = classes[metric]
                raw_values = raw_pool_values if metric == "pool" else raw_bk_values
                anomaly(
                    anomalies,
                    severity="ERROR",
                    drawing=drawing,
                    anomaly_type=f"{metric}_quotes_incomplete",
                    scope=f"quotes.{metric}",
                    db_value=f"{value}/15",
                    raw_best_value=max(raw_values, default=""),
                    root_cause_class=cls,
                    root_cause_reason=reason,
                    evidence_sources=sources,
                )
        if drawing["status"] == "finished" and resolved + voids != 15:
            cls, reason = classes["results"]
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="finished_results_incomplete",
                scope="events.result",
                db_value=(
                    f"resolved={resolved},void={voids},missing={missing_results},"
                    f"invalid={invalid_results}"
                ),
                raw_best_value=max(raw_result_values, default=""),
                root_cause_class=cls,
                root_cause_reason=reason,
                evidence_sources=sources,
            )
        if invalid_results:
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="invalid_result_value",
                scope="events.result",
                db_value=invalid_results,
                raw_best_value="",
                root_cause_class="D",
                root_cause_reason="SQLite contains unsupported non-empty result values",
                evidence_sources=sources,
            )
        if voids:
            anomaly(
                anomalies,
                severity="INFO",
                drawing=drawing,
                anomaly_type="void_result",
                scope="events.result",
                db_value=voids,
                raw_best_value=max(raw_result_values, default=""),
                root_cause_class="OK",
                root_cause_reason="explicit void is valid when backed by immutable evidence",
                evidence_sources=sources,
            )

        deadline = parse_utc(drawing["ended_at"])
        if drawing["status"] != "finished" and deadline is not None and deadline < now:
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="stale_nonfinished_status",
                scope="drawings.status",
                db_value=f"{drawing['status']} after {drawing['ended_at']}",
                raw_best_value="|".join(sorted({raw.status for raw in raws})),
                root_cause_class="D" if raws else "C",
                root_cause_reason=(
                    "local lifecycle status was not refreshed after deadline"
                    if raws
                    else "no local RAW snapshot exists to distinguish source vs import staleness"
                ),
                evidence_sources=sources,
            )

        if not raws:
            anomaly(
                anomalies,
                severity="WARN",
                drawing=drawing,
                anomaly_type="raw_snapshot_absent",
                scope="raw_provenance",
                db_value="SQLite rows exist",
                raw_best_value=0,
                root_cause_class="C",
                root_cause_reason="no local saved TotoBrief detail snapshot was found",
            )

        if drawing["status"] == "finished" and complete_result_snapshots == 0:
            if raw_result_values:
                cls, reason = root_class(
                    db_value=0,
                    target=15,
                    raw_values=raw_result_values,
                    conflict=result_conflict,
                )
            else:
                cls, reason = (
                    "C",
                    "no immutable result snapshot and no local RAW result evidence",
                )
            anomaly(
                anomalies,
                severity="WARN",
                drawing=drawing,
                anomaly_type="immutable_result_snapshot_absent",
                scope="drawing_result_snapshots",
                db_value=0,
                raw_best_value=max(raw_result_values, default=""),
                root_cause_class=cls,
                root_cause_reason=reason,
                evidence_sources=sources,
            )

        if package_rows and not settlement_rows:
            anomaly(
                anomalies,
                severity="ERROR",
                drawing=drawing,
                anomaly_type="package_without_settlement",
                scope="package_settlements",
                db_value=f"packages={len(package_rows)},settlements=0",
                raw_best_value="",
                root_cause_class="C",
                root_cause_reason="archived package has no persisted post-draw settlement",
                evidence_sources="|".join(
                    str(row["source_path"]) for row in package_rows
                ),
            )

        hard_count = sum(
            item["drawing_id"] == drawing_id and item["severity"] == "ERROR"
            for item in anomalies[hard_anomalies_before:]
        )
        warning_count = sum(
            item["drawing_id"] == drawing_id and item["severity"] == "WARN"
            for item in anomalies[hard_anomalies_before:]
        )
        health = "FAIL" if hard_count else ("WARN" if warning_count else "PASS")

        drawing_rows.append(
            {
                "drawing_number": drawing["number"],
                "drawing_id": drawing_id,
                "bookmaker": drawing["name"],
                "status": drawing["status"],
                "started_at": drawing["started_at"] or "",
                "ended_at": drawing["ended_at"] or "",
                "year": str(drawing["ended_at"] or "")[:4],
                "event_count": len(event_rows),
                "unique_event_orders": len(set(event_orders)),
                "missing_event_orders": missing_orders(event_rows, "event_order"),
                "duplicate_event_orders": duplicate_orders(event_rows, "event_order"),
                "blank_event_names": blank_names,
                "quote_rows": len(quote_rows),
                "unique_quote_orders": len(set(quote_orders)),
                "pool_complete_events": pool_complete,
                "bk_complete_events": bk_complete,
                "norm_complete_events": norm_complete,
                "pin_complete_events": pin_complete,
                "resolved_results": resolved,
                "void_results": voids,
                "missing_results": missing_results,
                "invalid_results": invalid_results,
                "scores_present": scores_present,
                "result_snapshot_rows": len(snapshot_rows),
                "complete_result_snapshots": complete_result_snapshots,
                "snapshot_status_resolved": snapshot_resolved,
                "snapshot_status_void": snapshot_voids,
                "snapshot_status_missing": snapshot_missing,
                "raw_snapshot_records": len(raws),
                "raw_unique_payloads": raw_unique_hashes,
                "raw_sources": sources,
                "raw_best_event_count": max(raw_event_values, default=""),
                "raw_best_nonblank_names": max(raw_name_values, default=""),
                "raw_best_pool_complete": max(raw_pool_values, default=""),
                "raw_best_bk_complete": max(raw_bk_values, default=""),
                "raw_best_norm_complete": max(raw_norm_values, default=""),
                "raw_best_resolved_results": max(raw_result_values, default=""),
                "preparation_rows": prep_count,
                "latest_preparation_status": prep_status,
                "latest_preparation_mapped": prep_mapped,
                "pin_rows": len(pin_rows),
                "valid_pin_rows": valid_pins,
                "package_rows": len(package_rows),
                "package_coupons": sum(
                    int(row["coupon_count"]) for row in package_rows
                ),
                "package_cost": sum(int(row["cost"]) for row in package_rows),
                "settlement_rows": len(settlement_rows),
                "health_status": health,
                "hard_anomaly_count": hard_count,
                "warning_count": warning_count,
            }
        )
        raw_comparison_rows.append(
            {
                "drawing_number": drawing["number"],
                "drawing_id": drawing_id,
                "raw_snapshot_records": len(raws),
                "raw_unique_payloads": raw_unique_hashes,
                "raw_sources": sources,
                "events_class": classes["events"][0],
                "events_reason": classes["events"][1],
                "names_class": classes["names"][0],
                "names_reason": classes["names"][1],
                "pool_class": classes["pool"][0],
                "pool_reason": classes["pool"][1],
                "bk_class": classes["bk"][0],
                "bk_reason": classes["bk"][1],
                "norm_class": classes["norm"][0],
                "norm_reason": classes["norm"][1],
                "results_class": classes["results"][0],
                "results_reason": classes["results"][1],
                "raw_final_result_conflict": result_conflict,
            }
        )

    period_rows = build_period_rows(drawing_rows)
    raw_inventory_rows = build_raw_inventory(raw_snapshots)
    anomaly_fields = (
        "severity",
        "drawing_number",
        "drawing_id",
        "year",
        "anomaly_type",
        "scope",
        "db_value",
        "raw_best_value",
        "root_cause_class",
        "root_cause_reason",
        "evidence_sources",
    )
    write_csv(OUT / "drawing_audit.csv", drawing_rows, tuple(drawing_rows[0]))
    write_csv(
        OUT / "raw_comparison.csv",
        raw_comparison_rows,
        tuple(raw_comparison_rows[0]),
    )
    write_csv(OUT / "anomalies.csv", anomalies, anomaly_fields)
    write_csv(OUT / "period_summary.csv", period_rows, tuple(period_rows[0]))
    write_csv(
        OUT / "raw_snapshot_inventory.csv",
        raw_inventory_rows,
        tuple(raw_inventory_rows[0])
        if raw_inventory_rows
        else (
            "drawing_number",
            "drawing_id",
            "status",
            "ended_at",
            "source",
            "source_kind",
            "payload_sha256",
            "event_count",
            "unique_orders",
            "nonblank_names",
            "pool_complete",
            "bk_complete",
            "norm_complete",
            "pin_complete",
            "resolved_results",
            "missing_results",
            "scores_present",
            "actual",
        ),
    )
    write_csv(
        OUT / "json_scan_errors.csv",
        file_errors + db_raw_errors,
        ("source", "error"),
    )

    summary = build_summary(
        connection=connection,
        drawings=drawings,
        drawing_rows=drawing_rows,
        raw_snapshots=raw_snapshots,
        anomalies=anomalies,
        gaps=gaps,
        duplicate_numbers=duplicate_numbers,
        quick_check=quick_check,
        scan_errors=file_errors + db_raw_errors,
    )
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(summary, period_rows, anomalies, drawing_rows)
    connection.close()
    return summary


def parse_utc(value: Any) -> datetime | None:
    if not nonblank(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def build_raw_inventory(snapshots: Sequence[RawSnapshot]) -> list[dict[str, Any]]:
    return [
        {
            "drawing_number": item.drawing_number,
            "drawing_id": item.drawing_id,
            "status": item.status,
            "ended_at": item.ended_at,
            "source": item.source,
            "source_kind": item.source_kind,
            "payload_sha256": item.payload_sha256,
            "event_count": item.event_count,
            "unique_orders": item.unique_orders,
            "nonblank_names": item.nonblank_names,
            "pool_complete": item.pool_complete,
            "bk_complete": item.bk_complete,
            "norm_complete": item.norm_complete,
            "pin_complete": item.pin_complete,
            "resolved_results": item.resolved_results,
            "missing_results": item.missing_results,
            "scores_present": item.scores_present,
            "actual": item.actual or "",
        }
        for item in sorted(
            snapshots,
            key=lambda item: (
                item.drawing_number,
                item.drawing_id,
                item.source,
                item.payload_sha256,
            ),
        )
    ]


def build_period_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["year"])].append(row)
    result: list[dict[str, Any]] = []
    for year, items in sorted(grouped.items()):
        result.append(
            {
                "year": year,
                "drawings": len(items),
                "min_drawing": min(int(item["drawing_number"]) for item in items),
                "max_drawing": max(int(item["drawing_number"]) for item in items),
                "events": sum(int(item["event_count"]) for item in items),
                "event_structure_complete_drawings": sum(
                    int(item["event_count"]) == 15
                    and int(item["unique_event_orders"]) == 15
                    for item in items
                ),
                "blank_name_drawings": sum(
                    int(item["blank_event_names"]) > 0 for item in items
                ),
                "pool_complete_drawings": sum(
                    int(item["pool_complete_events"]) == 15 for item in items
                ),
                "bk_complete_drawings": sum(
                    int(item["bk_complete_events"]) == 15 for item in items
                ),
                "norm_complete_drawings": sum(
                    int(item["norm_complete_events"]) == 15 for item in items
                ),
                "result_complete_drawings": sum(
                    int(item["resolved_results"]) + int(item["void_results"]) == 15
                    for item in items
                ),
                "result_incomplete_drawings": sum(
                    int(item["missing_results"]) > 0 for item in items
                ),
                "missing_result_events": sum(
                    int(item["missing_results"]) for item in items
                ),
                "raw_available_drawings": sum(
                    int(item["raw_snapshot_records"]) > 0 for item in items
                ),
                "result_snapshot_drawings": sum(
                    int(item["complete_result_snapshots"]) > 0 for item in items
                ),
                "preparation_drawings": sum(
                    int(item["preparation_rows"]) > 0 for item in items
                ),
                "package_drawings": sum(
                    int(item["package_rows"]) > 0 for item in items
                ),
                "settled_drawings": sum(
                    int(item["settlement_rows"]) > 0 for item in items
                ),
                "health_pass": sum(item["health_status"] == "PASS" for item in items),
                "health_warn": sum(item["health_status"] == "WARN" for item in items),
                "health_fail": sum(item["health_status"] == "FAIL" for item in items),
            }
        )
    return result


def build_summary(
    *,
    connection: sqlite3.Connection,
    drawings: Sequence[sqlite3.Row],
    drawing_rows: Sequence[Mapping[str, Any]],
    raw_snapshots: Sequence[RawSnapshot],
    anomalies: Sequence[Mapping[str, Any]],
    gaps: Sequence[int],
    duplicate_numbers: Mapping[int, int],
    quick_check: str,
    scan_errors: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    db_bytes = DB.read_bytes()
    severity = Counter(str(item["severity"]) for item in anomalies)
    root_classes = Counter(
        str(item["root_cause_class"])
        for item in anomalies
        if item["root_cause_class"] in {"A", "B", "C", "D"}
    )
    anomaly_types = Counter(str(item["anomaly_type"]) for item in anomalies)
    unique_raw_drawings = {snapshot.drawing_id for snapshot in raw_snapshots}
    file_raw_drawings = {
        snapshot.drawing_id
        for snapshot in raw_snapshots
        if snapshot.source_kind == "file"
    }
    primary_raw_drawings = {
        snapshot.drawing_id
        for snapshot in raw_snapshots
        if snapshot.source.startswith("data/raw/")
    }
    result_payload_drawings = {
        snapshot.drawing_id
        for snapshot in raw_snapshots
        if snapshot.source_kind == "result_snapshot_payload"
    }
    table_counts = {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "drawings",
            "events",
            "quotes",
            "drawing_result_snapshots",
            "drawing_preparations",
            "drawing_event_pins",
            "archived_packages",
            "package_settlements",
        )
    }
    finished = [row for row in drawing_rows if row["status"] == "finished"]
    initial_rows = [row for row in drawing_rows if int(row["drawing_number"]) <= 4939]
    added_rows = [row for row in drawing_rows if int(row["drawing_number"]) >= 4940]
    all_zero_pool_drawings = sum(
        int(row["quote_rows"]) == 15 and int(row["pool_complete_events"]) == 0
        for row in drawing_rows
    )
    return {
        "task_id": "TOTO-FULL-HISTORY-DATA-AUDIT",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(ROOT),
        "database": {
            "path": str(DB),
            "size_bytes": len(db_bytes),
            "sha256": hashlib.sha256(db_bytes).hexdigest(),
            "quick_check": quick_check,
            "table_counts": table_counts,
        },
        "scope": {
            "bookmaker": BOOKMAKER,
            "drawings": len(drawings),
            "min_visible_number": min(int(row["number"]) for row in drawings),
            "max_visible_number": max(int(row["number"]) for row in drawings),
            "visible_number_gaps": list(gaps),
            "duplicate_visible_numbers": dict(duplicate_numbers),
        },
        "completeness": {
            "started_at_present_drawings": sum(
                nonblank(row["started_at"]) for row in drawing_rows
            ),
            "ended_at_present_drawings": sum(
                nonblank(row["ended_at"]) for row in drawing_rows
            ),
            "event_structure_complete_drawings": sum(
                int(row["event_count"]) == 15 and int(row["unique_event_orders"]) == 15
                for row in drawing_rows
            ),
            "nonblank_name_complete_drawings": sum(
                int(row["blank_event_names"]) == 0 for row in drawing_rows
            ),
            "quote_structure_complete_drawings": sum(
                int(row["quote_rows"]) == 15 and int(row["unique_quote_orders"]) == 15
                for row in drawing_rows
            ),
            "pool_complete_drawings": sum(
                int(row["pool_complete_events"]) == 15 for row in drawing_rows
            ),
            "all_zero_pool_drawings": all_zero_pool_drawings,
            "bk_complete_drawings": sum(
                int(row["bk_complete_events"]) == 15 for row in drawing_rows
            ),
            "norm_complete_drawings": sum(
                int(row["norm_complete_events"]) == 15 for row in drawing_rows
            ),
            "pin_complete_drawings": sum(
                int(row["pin_complete_events"]) == 15 for row in drawing_rows
            ),
            "result_complete_drawings_including_void": sum(
                int(row["resolved_results"]) + int(row["void_results"]) == 15
                for row in drawing_rows
            ),
            "result_incomplete_drawings_all_statuses": sum(
                int(row["missing_results"]) > 0 for row in drawing_rows
            ),
            "finished_drawings": len(finished),
            "finished_result_incomplete_drawings": sum(
                int(row["resolved_results"]) + int(row["void_results"]) != 15
                for row in finished
            ),
            "finished_missing_result_events": sum(
                int(row["missing_results"]) for row in finished
            ),
            "void_events": sum(int(row["void_results"]) for row in drawing_rows),
            "complete_result_snapshot_drawings": sum(
                int(row["complete_result_snapshots"]) > 0 for row in drawing_rows
            ),
            "preparation_drawings": sum(
                int(row["preparation_rows"]) > 0 for row in drawing_rows
            ),
            "pin_drawings": sum(int(row["pin_rows"]) > 0 for row in drawing_rows),
            "package_drawings": sum(
                int(row["package_rows"]) > 0 for row in drawing_rows
            ),
            "settled_drawings": sum(
                int(row["settlement_rows"]) > 0 for row in drawing_rows
            ),
            "health_pass": sum(row["health_status"] == "PASS" for row in drawing_rows),
            "health_warn": sum(row["health_status"] == "WARN" for row in drawing_rows),
            "health_fail": sum(row["health_status"] == "FAIL" for row in drawing_rows),
        },
        "raw_inventory": {
            "snapshot_records": len(raw_snapshots),
            "unique_payloads": len(
                {
                    (snapshot.drawing_id, snapshot.payload_sha256)
                    for snapshot in raw_snapshots
                }
            ),
            "drawings_with_any_snapshot": len(unique_raw_drawings),
            "drawings_with_file_snapshot": len(file_raw_drawings),
            "drawings_with_primary_data_raw_snapshot": len(primary_raw_drawings),
            "drawings_with_result_snapshot_payload": len(result_payload_drawings),
            "drawings_without_any_snapshot": len(drawings)
            - len(unique_raw_drawings & {int(row["id"]) for row in drawings}),
            "json_scan_errors": len(scan_errors),
        },
        "anomalies": {
            "by_severity": dict(sorted(severity.items())),
            "by_root_cause_class": dict(sorted(root_classes.items())),
            "by_type": dict(sorted(anomaly_types.items())),
        },
        "previous_claim_check": {
            "claimed_initial_drawings": 2179,
            "claimed_initial_events": 32685,
            "current_drawings": table_counts["drawings"],
            "current_events": table_counts["events"],
            "initial_corpus_result_incomplete_drawings": sum(
                int(row["resolved_results"]) + int(row["void_results"]) != 15
                for row in initial_rows
            ),
            "initial_corpus_missing_result_events": sum(
                int(row["missing_results"]) for row in initial_rows
            ),
            "added_4940_4959_result_incomplete_drawings": sum(
                int(row["resolved_results"]) + int(row["void_results"]) != 15
                for row in added_rows
            ),
            "added_4940_4959_missing_result_events": sum(
                int(row["missing_results"]) for row in added_rows
            ),
            "arithmetic": "2179 * 15 = 32685",
            "validated_scope": (
                "The retained reports/validation_4938.md proves PASS only for "
                "drawing 4938. The historical validate command accepts one "
                "drawing number, fetches one live RAW detail, and compares "
                "that one payload with SQLite. The row counts prove 15 event "
                "rows per initial drawing, not full-history result/RAW/"
                "snapshot completeness."
            ),
        },
    }


def write_report(
    summary: Mapping[str, Any],
    periods: Sequence[Mapping[str, Any]],
    anomalies: Sequence[Mapping[str, Any]],
    drawing_rows: Sequence[Mapping[str, Any]],
) -> None:
    completeness = summary["completeness"]
    raw = summary["raw_inventory"]
    anomaly_summary = summary["anomalies"]
    db = summary["database"]
    scope = summary["scope"]
    hard_types = Counter(
        str(item["anomaly_type"]) for item in anomalies if item["severity"] == "ERROR"
    )
    a_drawings = sorted(
        {
            int(item["drawing_number"])
            for item in anomalies
            if item["root_cause_class"] == "A" and item["drawing_number"] != ""
        }
    )
    b_drawings = sorted(
        {
            int(item["drawing_number"])
            for item in anomalies
            if item["root_cause_class"] == "B" and item["drawing_number"] != ""
        }
    )
    c_drawings = sorted(
        {
            int(item["drawing_number"])
            for item in anomalies
            if item["root_cause_class"] == "C" and item["drawing_number"] != ""
        }
    )
    d_drawings = sorted(
        {
            int(item["drawing_number"])
            for item in anomalies
            if item["root_cause_class"] == "D" and item["drawing_number"] != ""
        }
    )
    missing_results = [
        row
        for row in drawing_rows
        if row["status"] == "finished"
        and int(row["resolved_results"]) + int(row["void_results"]) != 15
    ]
    full_missing_results = [
        int(row["drawing_number"])
        for row in missing_results
        if int(row["missing_results"]) == 15
    ]
    lines = [
        "# TOTO-FULL-HISTORY-DATA-AUDIT",
        "",
        "## Scope",
        "",
        f"- Audit time (UTC): `{summary['audited_at']}`.",
        f"- Repository: `{summary['repository_root']}`.",
        f"- Database: `{db['path']}`.",
        f"- Database SHA-256: `{db['sha256']}`.",
        f"- SQLite `PRAGMA quick_check`: `{db['quick_check']}`.",
        "- Network was not used.",
        "- Production code and Git were not changed.",
        f"- Bookmaker filter: exact `drawings.name = '{scope['bookmaker']}'`.",
        "",
        "## Executive conclusion",
        "",
        (
            f"The local database contains {scope['drawings']} BaltBet drawings "
            f"({scope['min_visible_number']}–{scope['max_visible_number']}) and "
            f"{db['table_counts']['events']} event rows. Every stored drawing has "
            "15 ordered event rows, but the history is not fully current or "
            "forensically complete."
        ),
        "",
        (
            f"Among {completeness['finished_drawings']} rows marked `finished`, "
            f"{completeness['finished_result_incomplete_drawings']} drawings "
            f"have incomplete results ({completeness['finished_missing_result_events']} "
            "missing event outcomes)."
        ),
        (
            f"Only {raw['drawings_with_any_snapshot']} drawings have any locally "
            f"discoverable TotoBrief RAW/detail evidence, and only "
            f"{completeness['complete_result_snapshot_drawings']} drawings have "
            "immutable result snapshots."
        ),
        (
            f"Three drawings have blank names and no analytical quotes; "
            f"{completeness['settled_drawings']} drawings have persisted settlements."
        ),
        "",
        "Therefore the earlier statement that the complete API history and all "
        "fields were fully validated was too broad and is false for the current "
        "local evidence.",
        "",
        "## Core counts",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Drawings | {scope['drawings']} |",
        f"| Events | {db['table_counts']['events']} |",
        f"| Quotes | {db['table_counts']['quotes']} |",
        f"| Visible number gaps | {', '.join(map(str, scope['visible_number_gaps'])) or 'none'} |",
        f"| Duplicate visible numbers | {len(scope['duplicate_visible_numbers'])} |",
        f"| `started_at` present | {completeness['started_at_present_drawings']} / {scope['drawings']} |",
        f"| `ended_at` present | {completeness['ended_at_present_drawings']} / {scope['drawings']} |",
        f"| Exact 15-event/order structure | {completeness['event_structure_complete_drawings']} / {scope['drawings']} |",
        f"| Complete nonblank names | {completeness['nonblank_name_complete_drawings']} / {scope['drawings']} |",
        f"| Exact 15-quote/order structure | {completeness['quote_structure_complete_drawings']} / {scope['drawings']} |",
        f"| Complete pool triples | {completeness['pool_complete_drawings']} / {scope['drawings']} |",
        f"| Drawings with 15 all-zero pool triples | {completeness['all_zero_pool_drawings']} |",
        f"| Complete BK triples | {completeness['bk_complete_drawings']} / {scope['drawings']} |",
        f"| Complete norm triples | {completeness['norm_complete_drawings']} / {scope['drawings']} |",
        f"| Complete Pin triples | {completeness['pin_complete_drawings']} / {scope['drawings']} |",
        f"| Complete results including void | {completeness['result_complete_drawings_including_void']} / {scope['drawings']} |",
        f"| Finished drawings with incomplete results | {completeness['finished_result_incomplete_drawings']} |",
        f"| Missing event results in finished drawings | {completeness['finished_missing_result_events']} |",
        f"| Explicit void events | {completeness['void_events']} |",
        f"| Drawings with immutable result snapshot | {completeness['complete_result_snapshot_drawings']} |",
        f"| Drawings with preparations | {completeness['preparation_drawings']} |",
        f"| Drawings with pins | {completeness['pin_drawings']} |",
        f"| Drawings with archived packages | {completeness['package_drawings']} |",
        f"| Drawings with settlements | {completeness['settled_drawings']} |",
        "",
        "All `started_at` values are null. Available TotoBrief detail payloads do "
        "not contain a top-level `started_at`, so this is a schema/source coverage "
        "gap rather than evidence that 2,199 imports independently dropped a "
        "present field.",
        "",
        "Normalized and Pin fields are optional/sparse source fields. Their "
        "completeness is reported but they are not treated as hard analytical "
        "input failures; pool and BK are the required three-way inputs.",
        "",
        (
            f"The pool defect is not only the three recent missing quote tables: "
            f"{completeness['all_zero_pool_drawings']} older drawings contain "
            "15 non-null but unusable `0/0/0` pool triples. The previous "
            "non-null field-count audit treated these rows as filled."
        ),
        "",
        "## Result defect",
        "",
        f"- Finished result-incomplete drawings: **{len(missing_results)}**.",
        f"- Missing outcomes in those drawings: **{sum(int(row['missing_results']) for row in missing_results)}**.",
        (
            "- Finished drawings missing all 15 results: "
            + (", ".join(map(str, full_missing_results)) or "none")
            + "."
        ),
        "- The many older one-event gaps are consistent with unresolved/cancelled "
        "source events, but without saved RAW or explicit `result_status=void` "
        "they cannot be distinguished safely and remain unusable for standard "
        "backtests.",
        "",
        "## RAW vs SQLite root-cause classification",
        "",
        "| Class | Meaning | Anomaly rows | Distinct drawing examples |",
        "|---|---|---:|---|",
        (
            f"| A | RAW contains more data; SQLite lost/did not import it | "
            f"{anomaly_summary['by_root_cause_class'].get('A', 0)} | "
            f"{format_numbers(a_drawings)} |"
        ),
        (
            f"| B | Available RAW is already incomplete/stale | "
            f"{anomaly_summary['by_root_cause_class'].get('B', 0)} | "
            f"{format_numbers(b_drawings)} |"
        ),
        (
            f"| C | No local RAW/provenance is available | "
            f"{anomaly_summary['by_root_cause_class'].get('C', 0)} | "
            f"{format_numbers(c_drawings)} |"
        ),
        (
            f"| D | Conflicting/ambiguous local state | "
            f"{anomaly_summary['by_root_cause_class'].get('D', 0)} | "
            f"{format_numbers(d_drawings)} |"
        ),
        "",
        "Classification is per anomaly, not per drawing. One drawing may have "
        "multiple anomaly classes for different fields.",
        "",
        "The clearest class-A defect is 4954–4956: immutable/local finished "
        "payloads contain 15 names and 15 pool/BK quote triples, while operational "
        "SQLite has blank names and zero quote rows. The result-only persistence "
        "path updated outcomes but did not import analytical event fields.",
        "",
        "Recent drawings fetched while active have local RAW snapshots without "
        "final outcomes. Where SQLite later says `finished` but was never "
        "force-refreshed, the result gap is class B: the saved RAW itself is "
        "pre-result/stale.",
        "",
        "## Local RAW inventory",
        "",
        f"- RAW snapshot records found: **{raw['snapshot_records']}**.",
        f"- Unique drawing/payload pairs: **{raw['unique_payloads']}**.",
        f"- Drawings with any local RAW/detail snapshot: **{raw['drawings_with_any_snapshot']} / {scope['drawings']}**.",
        f"- Drawings with file-based snapshot: **{raw['drawings_with_file_snapshot']}**.",
        f"- Drawings with primary `data/raw` snapshot: **{raw['drawings_with_primary_data_raw_snapshot']}**.",
        f"- Drawings with result-snapshot payload: **{raw['drawings_with_result_snapshot_payload']}**.",
        f"- Drawings without any local RAW/detail snapshot: **{raw['drawings_without_any_snapshot']}**.",
        f"- JSON scan errors: **{raw['json_scan_errors']}**.",
        "",
        "Repeated copies in rehearsal/report directories are retained in the "
        "inventory but deduplicated by canonical payload hash for unique counts.",
        "",
        "## Period summary",
        "",
        "| Year | Drawings | Result complete | Result incomplete | Missing outcomes | Pool/BK complete | RAW available | Result snapshots | Health FAIL |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in periods:
        lines.append(
            f"| {row['year']} | {row['drawings']} | "
            f"{row['result_complete_drawings']} | "
            f"{row['result_incomplete_drawings']} | "
            f"{row['missing_result_events']} | "
            f"{row['pool_complete_drawings']}/{row['bk_complete_drawings']} | "
            f"{row['raw_available_drawings']} | "
            f"{row['result_snapshot_drawings']} | "
            f"{row['health_fail']} |"
        )
    lines.extend(
        [
            "",
            "## Hard anomaly types",
            "",
            "| Type | Count |",
            "|---|---:|",
        ]
    )
    for name, count in sorted(hard_types.items()):
        lines.append(f"| `{name}` | {count} |")
    lines.extend(
        [
            "",
            "## What the earlier 2,179 / 32,685 validation actually proved",
            "",
            "- `2,179 × 15 = 32,685`. Those numbers prove that, at that point, "
            "there were 2,179 drawing rows and 15 event rows per drawing.",
            "- The current database has 2,199 drawings and 32,985 events: exactly "
            "20 additional 15-event drawings.",
            (
                "- Inside the original 2,179-drawing corpus, **"
                f"{summary['previous_claim_check']['initial_corpus_result_incomplete_drawings']}"
                "** drawings were already result-incomplete, containing **"
                f"{summary['previous_claim_check']['initial_corpus_missing_result_events']}"
                "** missing event outcomes."
            ),
            (
                "- Among the later 4940–4959 rows, **"
                f"{summary['previous_claim_check']['added_4940_4959_result_incomplete_drawings']}"
                "** are incomplete, containing **"
                f"{summary['previous_claim_check']['added_4940_4959_missing_result_events']}"
                "** missing outcomes."
            ),
            "- The retained validation artifact is `reports/validation_4938.md`. "
            "It reports PASS for drawing **4938** only.",
            "- `toto_ai.analytics.validation.run_validation()` accepts one supplied "
            "RAW payload and compares only that drawing with SQLite.",
            "- The CLI `validate --number N` fetches one live detail payload and "
            "runs that single-drawing comparison.",
            "- The old global audit checked aggregate row/field counts and duplicate "
            "primary keys; it did not prove that every finished drawing had all "
            "results, that every RAW payload was retained, or that every package "
            "was settled.",
            "- Project memory already recorded that hundreds of old finished "
            "drawings were result-incomplete, but that limitation was not carried "
            "into the broad user-facing claim. The broad claim was therefore "
            "incorrect.",
            "",
            "## Root causes visible from local evidence",
            "",
            "1. **Lifecycle refresh defect.** `Collector.drawing_needs_detail()` "
            "considers a drawing current after 15 events plus complete pool/BK "
            "quotes. It does not require final results after a summary changes to "
            "`finished`, so active snapshots can remain permanently result-empty.",
            "2. **Result-only import boundary.** The finished-result operation "
            "persists `result` and `score` but does not import names or quotes. "
            "This produced 4954–4956 result shells despite complete saved payloads.",
            "3. **Historical source incompleteness.** Hundreds of old finished "
            "drawings have one or more unresolved outcomes. With no immutable RAW "
            "or explicit void status, source incompleteness cannot be separated "
            "from import loss.",
            "4. **Insufficient RAW retention.** Most drawings have no local API "
            "payload, so the current database cannot be independently reconstructed "
            "or fully forensically verified offline.",
            "5. **Aggregate audit blind spot.** The earlier quote-completeness "
            "metric counted non-null fields, so 15×`0/0/0` pool rows appeared "
            "filled; its probability helper skipped non-positive triples instead "
            "of reporting them as invalid coverage.",
            "6. **No closed settlement lifecycle.** Only one archived package exists "
            "and it has no settlement; it is a rehearsal artifact rather than "
            "evidence of a placed bet.",
            "",
            "## Artifacts",
            "",
            "- `drawing_audit.csv`: one row for every BaltBet drawing.",
            "- `anomalies.csv`: all structural, lifecycle, RAW, result-snapshot, "
            "and settlement anomalies with A/B/C/D classification.",
            "- `period_summary.csv`: yearly aggregates.",
            "- `raw_snapshot_inventory.csv`: every detected local TotoBrief detail "
            "snapshot and canonical hash.",
            "- `raw_comparison.csv`: per-drawing RAW-vs-SQLite classification.",
            "- `json_scan_errors.csv`: malformed/unreadable JSON diagnostics.",
            "- `summary.json`: machine-readable aggregate summary.",
            "- `queries.sql`: key read-only SQL checks.",
            "- `audit_full_history.py`: complete reproducible audit.",
            "- `run_audit.sh`: reproduction command.",
            "",
            "## Safety conclusion",
            "",
            "Do not use the complete local history as one trusted backtest corpus "
            "without an eligibility gate. A drawing is historically usable only "
            "when event identity/names, required pool/BK input, and authoritative "
            "15/15 results (including explicit reviewed voids) are complete and "
            "its as-of provenance is appropriate for the experiment.",
            "",
        ]
    )
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def format_numbers(values: Sequence[int], *, limit: int = 20) -> str:
    if not values:
        return "none"
    shown = ", ".join(map(str, values[:limit]))
    if len(values) > limit:
        shown += f", … (+{len(values) - limit})"
    return shown


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
