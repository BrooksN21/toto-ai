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


def test_sports_probability_cli_help_exposes_shadow_only_contract():
    shadow = CliRunner().invoke(app, ["sports-probability-shadow", "--help"])
    evaluation = CliRunner().invoke(
        app,
        ["evaluate-sports-probability-shadow", "--help"],
    )

    assert shadow.exit_code == 0
    assert "NOT_ACTIVATED" in shadow.output
    assert "--as-of" in shadow.output
    assert evaluation.exit_code == 0
    assert "chronological" in evaluation.output.lower()
    assert "--minimum-drawings" in evaluation.output
    assert "--minimum-events" in evaluation.output
    assert "30" in evaluation.output
    assert "450" in evaluation.output


def test_sports_probability_cli_rejects_weakened_activation_policy():
    runner = CliRunner()

    for option, value in (
        ("--minimum-drawings", "29"),
        ("--minimum-events", "449"),
        ("--minimum-sports-coverage", "0.699"),
        ("--calibration-tolerance", "0.021"),
    ):
        result = runner.invoke(
            app,
            ["evaluate-sports-probability-shadow", option, value],
        )
        assert result.exit_code == 2


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
