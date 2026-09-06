"""Synthetic CLI integration for the accepted offline backfill boundary."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from typer.testing import CliRunner

import toto_ai.cli as cli
import toto_ai.sports_stats.history_backfill as history_backfill
from tests.test_sports_history_backfill import _write_manifest, _write_manifest_fixture


def test_backfill_help_exposes_offline_manifest_contract():
    result = CliRunner().invoke(cli.app, ["backfill-sports-history", "--help"])

    assert result.exit_code == 0
    for expected in (
        "OFFLINE AUDIT ONLY",
        "--manifest",
        "--db",
        "--output-dir",
        "--validate-only",
    ):
        assert expected in result.output


@pytest.mark.parametrize("validate_only", [False, True])
def test_backfill_cli_uses_corrected_module_and_reports_audit(
    monkeypatch, tmp_path, validate_only
):
    fixture = _write_manifest_fixture(tmp_path / "fixture", covered_events=11)
    monkeypatch.chdir(fixture.root)
    if validate_only:

        def forbidden_init(*args, **kwargs):
            pytest.fail("validate-only attempted to initialize SQLite")

        monkeypatch.setattr(history_backfill, "init_db", forbidden_init)
    args = [
        "backfill-sports-history",
        "--manifest",
        str(fixture.manifest_path),
        "--db",
        str(fixture.database),
        "--output-dir",
        str(fixture.root / "audit"),
    ]
    if validate_only:
        args.append("--validate-only")

    result = CliRunner().invoke(cli.app, args)

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "SUCCESS"
    assert report["network_requests"] == 0
    assert report["rejected_count"] == 0
    assert report["validated_count" if validate_only else "inserted_count"] == 1
    assert fixture.database.exists() is not validate_only
    if validate_only:
        assert report["database_writes"] == 0


@pytest.mark.parametrize("existing_database", [False, True])
def test_backfill_cli_rejection_does_not_initialize_or_change_database(
    monkeypatch, tmp_path, existing_database
):
    fixture = _write_manifest_fixture(tmp_path / "fixture", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    manifest["snapshots"][0]["drawing_id"] = -1
    _write_manifest(fixture.manifest_path, manifest)
    if existing_database:
        fixture.database.parent.mkdir(parents=True, exist_ok=True)
        fixture.database.write_bytes(b"existing legacy database sentinel")
    before = fixture.database.read_bytes() if existing_database else None
    monkeypatch.chdir(fixture.root)

    def forbidden_init(*args, **kwargs):
        pytest.fail("rejected input attempted to initialize SQLite")

    monkeypatch.setattr(history_backfill, "init_db", forbidden_init)
    result = CliRunner().invoke(
        cli.app,
        [
            "backfill-sports-history",
            "--manifest",
            str(fixture.manifest_path),
            "--db",
            str(fixture.database),
            "--output-dir",
            str(fixture.root / "audit"),
        ],
    )

    assert result.exit_code == 2, result.output
    report = json.loads(result.output)
    assert report["rejected_count"] == 1
    assert report["inserted_count"] == 0
    assert report["database_writes"] == 0
    after = fixture.database.read_bytes() if fixture.database.exists() else None
    assert after == before


def test_backfill_cli_partial_failure_keeps_success_and_returns_nonzero(
    monkeypatch, tmp_path
):
    fixture = _write_manifest_fixture(tmp_path / "fixture", covered_events=11)
    manifest = deepcopy(fixture.manifest)
    rejected = deepcopy(manifest["snapshots"][0])
    rejected["drawing_id"] = -1
    manifest["snapshots"].append(rejected)
    _write_manifest(fixture.manifest_path, manifest)
    monkeypatch.chdir(fixture.root)

    result = CliRunner().invoke(
        cli.app,
        [
            "backfill-sports-history",
            "--manifest",
            str(fixture.manifest_path),
            "--db",
            str(fixture.database),
            "--output-dir",
            str(fixture.root / "audit"),
        ],
    )

    assert result.exit_code == 2, result.output
    report = json.loads(result.output)
    assert report["status"] == "PARTIAL"
    assert report["inserted_count"] == 1
    assert report["rejected_count"] == 1
    assert fixture.database.exists()
