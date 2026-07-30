#!/usr/bin/env python3
"""Capture deterministic per-drawing logical state without writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def canonical(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    db = Path(args.db).resolve()
    uri = f"file:{quote(str(db), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = [
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]
        drawing_tables: list[str] = []
        for table in tables:
            columns = {
                row["name"]
                for row in connection.execute(
                    f"PRAGMA table_info({quote_identifier(table)})"
                )
            }
            if "drawing_id" in columns:
                drawing_tables.append(table)

        payload: dict[str, object] = {
            "schema_version": 1,
            "database": str(db),
            "drawing_tables": drawing_tables,
            "drawings": {},
        }
        drawings = connection.execute(
            "SELECT * FROM drawings ORDER BY number, id"
        ).fetchall()
        drawing_output: dict[str, object] = {}
        for drawing in drawings:
            drawing_id = drawing["id"]
            body: dict[str, object] = {
                "drawing": {
                    key: canonical(drawing[key]) for key in drawing.keys()
                },
                "tables": {},
            }
            for table in drawing_tables:
                rows = connection.execute(
                    f"""
                    SELECT *
                    FROM {quote_identifier(table)}
                    WHERE drawing_id = ?
                    ORDER BY rowid
                    """,
                    (drawing_id,),
                ).fetchall()
                body["tables"][table] = [
                    {key: canonical(row[key]) for key in row.keys()}
                    for row in rows
                ]
            encoded = json.dumps(
                body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            table_summaries: dict[str, object] = {}
            for table, rows in body["tables"].items():
                table_encoded = json.dumps(
                    rows,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                table_summaries[table] = {
                    "row_count": len(rows),
                    "sha256": hashlib.sha256(table_encoded).hexdigest(),
                }
            drawing_output[str(drawing["number"])] = {
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "tables": table_summaries,
            }
        payload["drawings"] = drawing_output
    finally:
        connection.close()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)


if __name__ == "__main__":
    main()
