#!/usr/bin/env python3
"""Create a WAL-aware SQLite online backup and a non-secret manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_checks(path: Path) -> tuple[list[str], list[list[object]]]:
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        quick = [row[0] for row in connection.execute("PRAGMA quick_check")]
        foreign_keys = [
            list(row) for row in connection.execute("PRAGMA foreign_key_check")
        ]
        return quick, foreign_keys
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    backup = Path(args.backup).resolve()
    manifest_path = Path(args.manifest).resolve()
    if backup.exists():
        raise SystemExit(f"backup already exists: {backup}")

    backup.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(backup.parent, 0o700)
    source_sha_before = file_sha256(source)
    wal = Path(str(source) + "-wal")
    shm = Path(str(source) + "-shm")
    source_sidecars_before = {
        "wal_exists": wal.exists(),
        "wal_size": wal.stat().st_size if wal.exists() else 0,
        "shm_exists": shm.exists(),
        "shm_size": shm.stat().st_size if shm.exists() else 0,
    }

    source_uri = f"file:{quote(str(source), safe='/')}?mode=ro"
    source_connection = sqlite3.connect(source_uri, uri=True)
    backup_connection = sqlite3.connect(backup)
    try:
        source_connection.backup(backup_connection)
        backup_connection.commit()
    finally:
        backup_connection.close()
        source_connection.close()

    os.chmod(backup, 0o600)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(backup.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

    source_sha_after = file_sha256(source)
    quick, foreign_keys = sqlite_checks(backup)
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "sqlite3.Connection.backup",
        "source_database": str(source),
        "source_sha256_before": source_sha_before,
        "source_sha256_after": source_sha_after,
        "source_sidecars_before": source_sidecars_before,
        "backup_database": str(backup),
        "backup_sha256": file_sha256(backup),
        "backup_size_bytes": backup.stat().st_size,
        "backup_mode_octal": oct(backup.stat().st_mode & 0o777),
        "quick_check": quick,
        "foreign_key_violation_count": len(foreign_keys),
        "foreign_key_violations": foreign_keys,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
