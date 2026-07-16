from dataclasses import dataclass
from pathlib import Path

import pytest
from typer.testing import CliRunner

import toto_ai.cli as cli

runner = CliRunner()
SENTINEL_SECRET = "api-sports-test-secret"


def test_run_drawing_requires_open_and_api_key(monkeypatch):
    missing_open = runner.invoke(cli.app, ["run-drawing", "--bank", "4980"])

    assert missing_open.exit_code != 0
    assert "--open is required" in missing_open.output

    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    missing_key = runner.invoke(
        cli.app, ["run-drawing", "--open", "--bank", "4980"]
    )

    assert missing_key.exit_code != 0
    assert "API_SPORTS_KEY is required" in missing_key.output


@dataclass(frozen=True)
class _RunnerResult:
    decision: str
    terminal_reason: str = "test result"
    ev_run: object | None = None
    audit: object | None = None


def _wire_runner(monkeypatch, *, result: _RunnerResult):
    captured: dict[str, object] = {}

    def fake_run_drawing(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_SECRET)
    monkeypatch.setattr(cli, "run_drawing", fake_run_drawing)
    def init_database(db):
        captured["init_db"] = db
        return "engine", db

    def open_readonly_database(db):
        captured["readonly_db"] = db
        return "readonly", db

    monkeypatch.setattr(cli, "init_db", init_database)
    monkeypatch.setattr(cli, "get_session_factory", lambda engine: "session-factory")
    monkeypatch.setattr(cli, "open_readonly_db", open_readonly_database)
    monkeypatch.setattr(cli, "load_aliases", lambda aliases: {"aliases": aliases})
    monkeypatch.setattr(
        cli,
        "collect_fresh_open_external_odds",
        lambda **kwargs: captured.setdefault("collection", kwargs),
    )
    monkeypatch.setattr(
        cli,
        "audit_external_coverage",
        lambda *args, **kwargs: captured.setdefault("audit", (args, kwargs)),
    )
    monkeypatch.setattr(
        cli,
        "build_open_ev_package",
        lambda **kwargs: captured.setdefault("ev", kwargs),
    )
    def write_runner(result, **kwargs):
        captured["runner_report"] = kwargs
        return Path("reports/runner.json"), Path("reports/runner.md")

    monkeypatch.setattr(cli, "write_drawing_run_reports", write_runner)
    monkeypatch.setattr(
        cli,
        "write_external_coverage_reports",
        lambda audit, *, report_dir: (
            Path(report_dir) / "coverage.csv",
            Path(report_dir) / "coverage.md",
        ),
    )
    monkeypatch.setattr(
        cli,
        "write_ev_package_reports",
        lambda ev_run, *, report_dir=None: (
            Path(report_dir or "reports") / "ev.csv",
            Path(report_dir or "reports") / "ev.md",
        ),
    )
    return captured


def test_run_drawing_wires_only_approved_options_and_fresh_dependencies(monkeypatch):
    provider_calls: list[tuple[str, object, int]] = []

    def provider(api_key, *, cache_dir, quota_reserve):
        provider_calls.append((api_key, cache_dir, quota_reserve))
        return object()

    monkeypatch.setattr(cli, "APISportsClient", provider)
    captured = _wire_runner(
        monkeypatch,
        result=_RunnerResult("NO BET", ev_run=object(), audit=object()),
    )

    result = runner.invoke(
        cli.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "60",
            "--stake",
            "20",
            "--mode",
            "research",
            "--final-lead-minutes",
            "25",
            "--safety-stop-minutes",
            "6",
            "--db",
            "custom.db",
            "--report-dir",
            "custom-reports",
            "--provider",
            "api-sports",
            "--aliases",
            "aliases.json",
            "--quota-reserve",
            "0",
            "--max-passes",
            "2",
            "--max-expansion-passes",
            "2",
            "--retry-delay-seconds",
            "0",
            "--cache-root",
            "fresh-cache",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "NO BET" in result.output
    assert "Coupon" not in result.output
    config = captured["config"]
    assert config.bank == 60
    assert config.stake == 20
    assert config.mode == "research"
    assert config.final_lead_minutes == 25
    assert config.safety_stop_minutes == 6
    assert captured["init_db"] == "custom.db"
    assert captured["readonly_db"] == "custom.db"
    assert callable(captured["sleep"])
    captured["collect_target"]("pinned-target", "safety-stop")
    collection = captured["collection"]
    assert collection["target"] == "pinned-target"
    assert collection["stop_at"] == "safety-stop"
    assert collection["cache_root"] == Path("fresh-cache")
    assert collection["max_passes"] == 2
    assert collection["max_expansion_passes"] == 2
    assert collection["retry_delay_seconds"] == 0
    assert collection["session_factory"] == "session-factory"
    assert collection["aliases"] == {"aliases": "aliases.json"}
    assert collection["provider_factory"](Path("fresh-provider")) is not None
    assert provider_calls == [(SENTINEL_SECRET, Path("fresh-provider"), 0)]
    captured["audit_coverage"]()
    assert captured["audit"] == (
        ("session-factory",),
        {"last": 30, "minimum_bookmakers": 3},
    )
    captured["build_package"](11953)
    assert captured["ev"]["drawing_id"] == 11953
    assert captured["ev"]["config"] == config.ev_config
    assert captured["runner_report"]["report_dir"] == "custom-reports"
    assert captured["runner_report"]["links"].external == (
        Path("custom-reports/coverage.csv"),
        Path("custom-reports/coverage.md"),
    )
    assert captured["runner_report"]["links"].ev == (
        Path("custom-reports/ev.csv"),
        Path("custom-reports/ev.md"),
    )
    assert "--reuse-cache" not in runner.invoke(
        cli.app, ["run-drawing", "--help"]
    ).output
    assert "--min-gross-ev" not in runner.invoke(
        cli.app, ["run-drawing", "--help"]
    ).output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--bank", "61", "--stake", "20"], "divisible"),
        (["--bank", "60", "--final-lead-minutes", "5"], "greater"),
        (["--bank", "60", "--safety-stop-minutes", "0"], "x>=1"),
        (["--bank", "60", "--provider", "other"], "provider must be api-sports"),
    ],
)
def test_run_drawing_validates_config_before_provider_access(
    monkeypatch, arguments, message
):
    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_SECRET)
    provider_accessed = False

    def forbidden_provider(*args, **kwargs):
        nonlocal provider_accessed
        provider_accessed = True
        raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(cli, "APISportsClient", forbidden_provider)
    result = runner.invoke(cli.app, ["run-drawing", "--open", *arguments])

    assert result.exit_code != 0
    assert message in result.output
    assert not provider_accessed


def test_run_drawing_sanitizes_provider_errors_and_interruptions(monkeypatch):
    _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))

    def fail_with_secret(**kwargs):
        error = cli.APISportsError(f"provider rejected {SENTINEL_SECRET}")
        error.__cause__ = ValueError(f"nested {SENTINEL_SECRET}")
        raise error

    monkeypatch.setattr(cli, "run_drawing", fail_with_secret)
    failure = runner.invoke(cli.app, ["run-drawing", "--open", "--bank", "4980"])

    assert failure.exit_code != 0
    assert SENTINEL_SECRET not in failure.output
    assert "[redacted]" in failure.output

    monkeypatch.setattr(
        cli,
        "run_drawing",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    interrupted = runner.invoke(
        cli.app, ["run-drawing", "--open", "--bank", "4980"]
    )

    assert interrupted.exit_code != 0
    assert "interrupted" in interrupted.output.lower()
