from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

import toto_ai.cli as cli
import toto_ai.runner.reports as runner_reports
from toto_ai.ev.models import PlayTimingEligibility
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.runner import DrawingRunnerConfig, DrawingRunnerResult, pin_drawing

runner = CliRunner()
SENTINEL_SECRET = "api-sports-test-secret"
UTC = timezone.utc
DEADLINE = datetime(2026, 7, 17, 15, tzinfo=UTC)


def _target_payload(drawing_id: int = 11953) -> dict[str, object]:
    return {
        "data": {
            "id": drawing_id,
            "number": 4945,
            "ended_at": DEADLINE.isoformat(),
            "events": [
                {
                    "id": 20_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "name_en": None,
                    "championship": "Test League",
                    "sport": "football",
                    "start_at": (DEADLINE + timedelta(hours=order)).isoformat(),
                    "quotes": {
                        "bk_win_1": 0.2,
                        "bk_draw": 0.3,
                        "bk_win_2": 0.5,
                    },
                }
                for order in range(15)
            ],
        }
    }


def _pinned_target():
    target = parse_target_drawing(
        _target_payload(),
        fetched_at=DEADLINE - timedelta(minutes=20),
    )
    return pin_drawing(target)


def _early_no_bet_result() -> DrawingRunnerResult:
    pinned = _pinned_target()
    preflight_at = DEADLINE - timedelta(minutes=5)
    return DrawingRunnerResult(
        config=DrawingRunnerConfig(bank=4980),
        target=pinned,
        preflight_at=preflight_at,
        final_started_at=None,
        final_fingerprint=None,
        collection_finished_at=None,
        timing_finished_at=None,
        audit_finished_at=None,
        ev_finished_at=None,
        finished_at=preflight_at,
        elapsed_seconds=0.0,
        decision="NO BET",
        terminal_reason="safety cutoff reached before final resolve",
        collection=None,
        timing_eligibility=PlayTimingEligibility.not_checked(),
        audit=None,
        ev_run=None,
    )


def _exception_graph(root: BaseException) -> tuple[BaseException, ...]:
    pending = [root]
    seen: set[int] = set()
    exceptions = []
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        exceptions.append(current)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return tuple(exceptions)


def _invoke_command_direct() -> None:
    cli.run_drawing_command(
        open=True,
        bank=4980,
        stake=30,
        mode="playable",
        final_lead_minutes=20,
        safety_stop_minutes=5,
        db="custom.db",
        report_dir="reports",
        provider="api-sports",
        aliases="aliases.json",
        quota_reserve=10,
        max_passes=3,
        max_expansion_passes=3,
        retry_delay_seconds=65.0,
        cache_root="cache-root",
    )


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

    class RecordingProgress:
        def __init__(self, *columns):
            captured["progress_columns"] = columns
            captured["progress_descriptions"] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def add_task(self, description):
            captured["progress_descriptions"].append(description)
            return 1

        def update(self, task_id, *, description):
            assert task_id == 1
            captured["progress_descriptions"].append(description)

    monkeypatch.setattr(cli, "Progress", RecordingProgress)
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


def test_runner_target_bridge_rejects_mismatched_drawing_info(monkeypatch):
    client = SimpleNamespace(drawing_info=lambda drawing_id: _target_payload(99999))
    monkeypatch.setattr(
        cli,
        "resolve_open_drawing_from_api",
        lambda client, now: SimpleNamespace(drawing_id=11953),
    )

    with pytest.raises(ValueError, match="does not match page-one drawing id"):
        cli._resolve_runner_target(client, DEADLINE - timedelta(minutes=20))


def test_runner_target_and_timing_bridges_bind_exact_fingerprint(monkeypatch):
    payload = _target_payload()
    client = SimpleNamespace(drawing_info=lambda drawing_id: payload)
    monkeypatch.setattr(
        cli,
        "resolve_open_drawing_from_api",
        lambda client, now: SimpleNamespace(drawing_id=11953),
    )
    pinned = cli._resolve_runner_target(
        client,
        DEADLINE - timedelta(minutes=20),
    )
    eligibility = DrawingEligibility(
        status="playable",
        earliest_start=pinned.target.events[0].starts_at,
        latest_start=pinned.target.events[-1].starts_at,
        span_days=2,
        missing_event_orders=(),
        totobrief_count=15,
        provider_count=0,
    )
    lookups = []
    monkeypatch.setattr(cli, "open_readonly_db", lambda db: ("readonly", db))
    monkeypatch.setattr(cli, "get_session_factory", lambda engine: "sessions")

    def load_eligibility(session_factory, drawing_id, fingerprint):
        lookups.append((session_factory, drawing_id, fingerprint))
        return eligibility

    monkeypatch.setattr(cli, "load_current_drawing_eligibility", load_eligibility)

    timing = cli._build_runner_timing_resolver("custom.db")(pinned)

    assert pinned.target.drawing_id == 11953
    assert timing.status == "playable"
    assert timing.target_fingerprint == pinned.fingerprint
    assert timing.fingerprint_match is True
    assert lookups == [("sessions", 11953, pinned.fingerprint)]


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


def test_run_drawing_exposes_exact_approved_option_surface():
    command = typer.main.get_command(cli.app).commands["run-drawing"]
    option_names = {
        option
        for parameter in command.params
        for option in (*parameter.opts, *parameter.secondary_opts)
    }

    assert option_names == {
        "--open",
        "--bank",
        "--stake",
        "--mode",
        "--final-lead-minutes",
        "--safety-stop-minutes",
        "--db",
        "--report-dir",
        "--provider",
        "--aliases",
        "--quota-reserve",
        "--max-passes",
        "--max-expansion-passes",
        "--retry-delay-seconds",
        "--cache-root",
    }
    forbidden = {
        "--no-open",
        "--reuse-cache",
        "--fresh",
        "--expand-missing-starts",
        "--expansion-horizon-days",
        "--min-gross-ev",
        "--prize-fund-factor",
        "--possible-winnings",
        "--jackpot",
        "--bet",
        "--submit-bet",
        "--automatic-bet",
    }
    assert option_names.isdisjoint(forbidden)

    parameters = {parameter.name: parameter for parameter in command.params}
    assert parameters["bank"].required is True
    assert {
        name: parameter.default
        for name, parameter in parameters.items()
        if name != "bank"
    } == {
        "open": False,
        "stake": 30,
        "mode": "playable",
        "final_lead_minutes": 20,
        "safety_stop_minutes": 5,
        "db": "data/toto.db",
        "report_dir": "reports",
        "provider": "api-sports",
        "aliases": "data/external-odds/team-aliases.json",
        "quota_reserve": 10,
        "max_passes": 3,
        "max_expansion_passes": 3,
        "retry_delay_seconds": 65.0,
        "cache_root": "data/external-cache/api-sports",
    }


@pytest.mark.parametrize(
    ("decision", "mode"),
    [("PLAY", "playable"), ("RESEARCH ONLY", "research")],
)
def test_run_drawing_prints_actionable_decisions_and_rich_progress(
    monkeypatch,
    decision,
    mode,
):
    captured = _wire_runner(monkeypatch, result=_RunnerResult(decision))

    def run_with_progress(**kwargs):
        callback = kwargs["progress_callback"]
        for update in (
            {"phase": "preflight"},
            {"phase": "waiting", "seconds_until_final": 600.0},
            {"phase": "final"},
            {"phase": "collect"},
            {"phase": "timing"},
            {"phase": "audit"},
            {"phase": "ev"},
            {"phase": "complete", "decision": decision},
        ):
            callback(update)
        return _RunnerResult(decision)

    monkeypatch.setattr(cli, "run_drawing", run_with_progress)

    result = runner.invoke(
        cli.app,
        ["run-drawing", "--open", "--bank", "4980", "--mode", mode],
    )

    assert result.exit_code == 0, result.output
    assert f"Decision: {decision}" in result.output
    assert captured["progress_descriptions"] == [
        "Preflighting open drawing",
        "Preflighting open drawing",
        "Waiting for T-10.0 final window",
        "Revalidating pinned drawing",
        "Collecting fresh API-Sports odds",
        "Checking exact timing eligibility",
        "Auditing latest 30 collections",
        "Building exact EV package",
        f"Runner complete: {decision}",
    ]


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


def test_corrupt_stored_timing_is_a_controlled_nonzero_failure(monkeypatch):
    captured = _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))
    pinned = _pinned_target()

    def corrupt_state(*args):
        raise ValueError("corrupt stored eligibility")

    def resolve_timing(**kwargs):
        kwargs["resolve_timing"](pinned)
        raise AssertionError("corrupt timing must stop the runner")

    monkeypatch.setattr(cli, "load_current_drawing_eligibility", corrupt_state)
    monkeypatch.setattr(cli, "run_drawing", resolve_timing)

    result = runner.invoke(
        cli.app,
        ["run-drawing", "--open", "--bank", "4980"],
    )

    assert result.exit_code != 0
    assert "corrupt stored eligibility" in result.output
    assert "runner_report" not in captured


def test_run_drawing_sanitizes_entire_recursive_exception_graph(monkeypatch):
    _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))

    def fail_with_secret(**kwargs):
        cause = ValueError(f"cause {SENTINEL_SECRET}")
        context = RuntimeError(f"context {SENTINEL_SECRET}")
        error = cli.APISportsError(f"provider rejected {SENTINEL_SECRET}")
        error.__cause__ = cause
        error.__context__ = context
        raise error

    monkeypatch.setattr(cli, "run_drawing", fail_with_secret)

    with pytest.raises(typer.BadParameter) as excinfo:
        _invoke_command_direct()

    graph = _exception_graph(excinfo.value)
    assert graph == (excinfo.value,)
    assert all(
        SENTINEL_SECRET not in text
        for error in graph
        for text in (str(error), repr(error))
    )
    assert "[redacted]" in str(excinfo.value)


def test_keyboard_interrupt_during_runner_publication_leaves_no_manifest(
    monkeypatch,
    tmp_path,
):
    result = _early_no_bet_result()
    _wire_runner(monkeypatch, result=result)
    monkeypatch.setattr(
        cli,
        "write_drawing_run_reports",
        runner_reports.write_drawing_run_reports,
    )
    real_replace = runner_reports.os.replace
    installs = 0

    def interrupt_second_install(source, destination):
        nonlocal installs
        source_path = Path(source)
        destination_path = Path(destination)
        is_runner_install = (
            source_path.name.endswith(".tmp")
            and not source_path.name.endswith(".bak.tmp")
            and destination_path.suffix in {".json", ".md"}
        )
        if is_runner_install:
            installs += 1
            if installs == 2:
                raise KeyboardInterrupt
        return real_replace(source, destination)

    monkeypatch.setattr(runner_reports.os, "replace", interrupt_second_install)

    interrupted = runner.invoke(
        cli.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4980",
            "--report-dir",
            str(tmp_path),
        ],
    )

    assert interrupted.exit_code != 0
    assert "no final manifest was published" in interrupted.output
    assert tuple(tmp_path.iterdir()) == ()


def test_keyboard_interrupt_before_publication_is_nonzero(monkeypatch):
    _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))

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
