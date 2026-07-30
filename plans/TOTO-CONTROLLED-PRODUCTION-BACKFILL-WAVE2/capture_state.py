#!/usr/bin/env python3
"""Capture a deterministic read-only database and RAW inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_inventory(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    db = Path(args.db).resolve()
    raw_root = Path(args.raw_root).resolve()
    output = Path(args.output).resolve()
    uri = f"file:{quote(str(db), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        schema_rows = connection.execute(
            """
            SELECT type, name, tbl_name, COALESCE(sql, '') AS sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        schema = [dict(row) for row in schema_rows]
        tables: dict[str, dict[str, object]] = {}
        for row in schema_rows:
            if row["type"] != "table":
                continue
            name = row["name"]
            escaped = '"' + name.replace('"', '""') + '"'
            count = connection.execute(
                f"SELECT COUNT(*) FROM {escaped}"
            ).fetchone()[0]
            tables[name] = {"row_count": count}

        payload = {
            "schema_version": 1,
            "database": str(db),
            "database_sha256": file_sha256(db),
            "database_size": db.stat().st_size,
            "quick_check": [
                row[0] for row in connection.execute("PRAGMA quick_check")
            ],
            "foreign_key_violations": [
                list(row)
                for row in connection.execute("PRAGMA foreign_key_check")
            ],
            "schema": schema,
            "tables": tables,
            "sidecars": {
                suffix: {
                    "exists": Path(str(db) + suffix).exists(),
                    "size": (
                        Path(str(db) + suffix).stat().st_size
                        if Path(str(db) + suffix).exists()
                        else 0
                    ),
                }
                for suffix in ("-wal", "-shm")
            },
            "raw_root": str(raw_root),
            "raw_inventory": tree_inventory(raw_root),
        }
    finally:
        connection.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.chmod(0o600)


if __name__ == "__main__":
    main()
