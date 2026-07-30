#!/usr/bin/env python3
"""Read-only SQLite integrity, row-count, and deterministic logical checksum audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


def encode_value(value: Any) -> bytes:
    if value is None:
        return b"n:"
    if isinstance(value, bytes):
        return b"b:" + value.hex().encode("ascii")
    if isinstance(value, float):
        return b"f:" + value.hex().encode("ascii")
    if isinstance(value, int):
        return b"i:" + str(value).encode("ascii")
    return b"s:" + str(value).encode("utf-8")


def quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    output_path = Path(args.output).resolve()
    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        quick_check = [row[0] for row in connection.execute("PRAGMA quick_check")]
        fk_violations = [
            list(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        table_rows = connection.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        overall = hashlib.sha256()
        tables: dict[str, dict[str, Any]] = {}
        for table_row in table_rows:
            table = table_row["name"]
            schema_sql = table_row["sql"] or ""
            columns = connection.execute(
                f"PRAGMA table_info({quoted(table)})"
            ).fetchall()
            column_names = [row["name"] for row in columns]
            primary_key = [
                row["name"]
                for row in sorted(columns, key=lambda item: item["pk"])
                if row["pk"]
            ]
            ordering = primary_key or column_names
            order_sql = ", ".join(quoted(column) for column in ordering)
            select_sql = f"SELECT * FROM {quoted(table)}"
            if order_sql:
                select_sql += f" ORDER BY {order_sql}"

            table_hash = hashlib.sha256()
            table_hash.update(schema_sql.encode("utf-8"))
            table_hash.update(b"\n")
            row_count = 0
            for row in connection.execute(select_sql):
                row_count += 1
                for column in column_names:
                    encoded = encode_value(row[column])
                    table_hash.update(len(encoded).to_bytes(8, "big"))
                    table_hash.update(encoded)
                table_hash.update(b"\n")

            digest = table_hash.hexdigest()
            overall.update(table.encode("utf-8"))
            overall.update(b"\0")
            overall.update(str(row_count).encode("ascii"))
            overall.update(b"\0")
            overall.update(digest.encode("ascii"))
            overall.update(b"\n")
            tables[table] = {
                "row_count": row_count,
                "sha256": digest,
                "primary_key": primary_key,
            }

        payload = {
            "schema_version": 1,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "database": str(db_path),
            "quick_check": quick_check,
            "foreign_key_violation_count": len(fk_violations),
            "foreign_key_violations": fk_violations,
            "logical_sha256": overall.hexdigest(),
            "tables": tables,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_path.chmod(0o600)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
