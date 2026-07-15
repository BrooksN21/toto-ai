from __future__ import annotations

from types import SimpleNamespace

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
    collect = runner.invoke(
        app,
        ["collect-external-odds", "--help"],
        terminal_width=120,
    )
    audit = runner.invoke(
        app,
        ["audit-external-coverage", "--help"],
        terminal_width=120,
    )

    assert collect.exit_code == 0
    assert "--open" in collect.output
    assert "--provider" in collect.output
    assert "--fresh" in collect.output
    assert "--reuse-cache" in collect.output
    assert "--max-passes" in collect.output
    assert "--retry-delay-sec" in collect.output
    assert "--cache-root" in collect.output
    assert audit.exit_code == 0
    assert "--last" in audit.output
    assert "--min-bookmakers" in audit.output


def test_collect_cli_uses_fresh_multi_pass_mode_by_default(monkeypatch, tmp_path):
    import toto_ai.cli as cli

    snapshot = _collection(1, ())
    captured = {}
    orchestration = SimpleNamespace(
        snapshot=snapshot,
        passes=(SimpleNamespace(snapshot=snapshot), SimpleNamespace(snapshot=snapshot)),
        total_requests=15,
        total_cache_hits=10,
        elapsed_seconds=71.25,
        stop_reason="no_retryable_fallbacks",
    )

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return orchestration

    monkeypatch.setenv("API_SPORTS_KEY", "secret")
    monkeypatch.setattr(cli, "init_db", lambda _db: "engine")
    monkeypatch.setattr(cli, "get_session_factory", lambda _engine: "factory")
    monkeypatch.setattr(cli, "load_aliases", lambda _path: {})
    monkeypatch.setattr(cli, "TotoBriefClient", lambda: "totobrief")
    monkeypatch.setattr(
        cli,
        "collect_fresh_open_external_odds",
        fake_collect,
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "collect-external-odds",
            "--open",
            "--db",
            str(tmp_path / "toto.db"),
            "--cache-root",
            str(tmp_path / "cache"),
            "--max-passes",
            "2",
            "--retry-delay-seconds",
            "61",
        ],
    )

    assert result.exit_code == 0
    assert captured["totobrief_client"] == "totobrief"
    assert captured["session_factory"] == "factory"
    assert captured["max_passes"] == 2
    assert captured["retry_delay_seconds"] == 61.0
    assert captured["cache_root"] == tmp_path / "cache"
    assert "passes" in result.output
    assert "2" in result.output
    assert "total requests" in result.output
    assert "15" in result.output
    assert "total cache hits" in result.output
    assert "10" in result.output
    assert "no_retryable_fallbacks" in result.output


def test_collect_cli_reuse_cache_keeps_single_pass_path(monkeypatch, tmp_path):
    import toto_ai.cli as cli

    snapshot = _collection(1, ())
    constructed = []
    collection_calls = []

    class FakeProvider:
        def __init__(self, api_key, **kwargs):
            constructed.append((api_key, kwargs))

    monkeypatch.setenv("API_SPORTS_KEY", "secret")
    monkeypatch.setattr(cli, "init_db", lambda _db: "engine")
    monkeypatch.setattr(cli, "get_session_factory", lambda _engine: "factory")
    monkeypatch.setattr(cli, "load_aliases", lambda _path: {})
    monkeypatch.setattr(cli, "TotoBriefClient", lambda: "totobrief")
    monkeypatch.setattr(cli, "APISportsClient", FakeProvider)
    monkeypatch.setattr(
        cli,
        "collect_open_external_odds",
        lambda *args, **kwargs: (collection_calls.append((args, kwargs)) or snapshot),
    )

    result = runner.invoke(
        app,
        [
            "collect-external-odds",
            "--open",
            "--reuse-cache",
            "--db",
            str(tmp_path / "toto.db"),
            "--cache-root",
            str(tmp_path / "cache"),
        ],
    )

    assert result.exit_code == 0
    assert len(collection_calls) == 1
    assert constructed == [
        (
            "secret",
            {
                "cache_dir": tmp_path / "cache",
                "quota_reserve": 10,
            },
        )
    ]
    assert "passes" not in result.output
