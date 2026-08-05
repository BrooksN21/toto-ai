from pathlib import Path

from typer.testing import CliRunner

from toto_ai.cli import app
from toto_ai.sports_stats.operation import load_api_sports_key


def test_collect_sports_stats_help_exposes_safe_selectors():
    result = CliRunner().invoke(app, ["collect-sports-stats", "--help"])

    assert result.exit_code == 0
    assert "--open" in result.output
    assert "--drawing-id" in result.output
    assert "--drawing-number" in result.output
    assert "--historical-as-of" in result.output
    assert "--raw-cache-dir" in result.output
    assert "AUDIT ONLY" in result.output


def test_secure_env_key_is_read_without_mutating_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("API_SPORTS_KEY=secret-value\n", encoding="utf-8")
    path.chmod(0o600)

    assert load_api_sports_key(path) == "secret-value"


def test_insecure_env_file_is_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    path = Path(tmp_path / ".env")
    path.write_text("API_SPORTS_KEY=secret-value\n", encoding="utf-8")
    path.chmod(0o644)

    try:
        load_api_sports_key(path)
    except ValueError as error:
        assert "permissions" in str(error)
    else:
        raise AssertionError("insecure env file was accepted")
