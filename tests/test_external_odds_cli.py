from __future__ import annotations

from typer.testing import CliRunner

from tests.test_external_odds_audit import _collection
from toto_ai.cli import app
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.storage import save_collection

runner = CliRunner()


def test_collect_cli_missing_key_makes_no_network_call(monkeypatch, tmp_path):
    import toto_ai.cli as cli

    def forbidden_client(*args, **kwargs):
        raise AssertionError("network provider must not be constructed")

    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    monkeypatch.setattr(cli, "APISportsClient", forbidden_client, raising=False)

    result = runner.invoke(
        app,
        [
            "collect-external-odds",
            "--open",
            "--db",
            str(tmp_path / "toto.db"),
        ],
    )

    assert result.exit_code != 0
    assert "API_SPORTS_KEY" in result.output
    assert "network provider" not in result.output


def test_audit_cli_reads_stored_data_without_api_key(monkeypatch, tmp_path):
    db_path = tmp_path / "toto.db"
    engine = init_db(db_path)
    save_collection(get_session_factory(engine), _collection(1, ()))
    engine.dispose()

    monkeypatch.delenv("API_SPORTS_KEY", raising=False)

    result = runner.invoke(
        app,
        [
            "audit-external-coverage",
            "--db",
            str(db_path),
            "--last",
            "1",
            "--min-bookmakers",
            "3",
            "--report-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "PENDING" in result.output
    assert "Reports written to" in result.output
    assert (tmp_path / "external_coverage_last_1_min_bookmakers_3.csv").exists()
    assert (tmp_path / "external_coverage_last_1_min_bookmakers_3.md").exists()


def test_external_odds_cli_help_lists_approved_commands():
    collect = runner.invoke(app, ["collect-external-odds", "--help"])
    audit = runner.invoke(app, ["audit-external-coverage", "--help"])

    assert collect.exit_code == 0
    assert "--open" in collect.output
    assert "--provider" in collect.output
    assert audit.exit_code == 0
    assert "--last" in audit.output
    assert "--min-bookmakers" in audit.output
