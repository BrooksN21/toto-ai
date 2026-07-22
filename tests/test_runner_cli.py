import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

import toto_ai.cli as cli
import toto_ai.runner.reports as runner_reports
import toto_ai.runner.scheduler as scheduler_module
from tests.pinned_revalidation_helpers import ready_pinned_revalidation
from toto_ai.ev.models import PlayTimingEligibility
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.runner import (
    CommandSchedulerPhaseRunner,
    DrawingRunnerConfig,
    DrawingRunnerResult,
    RunnerReportLinks,
    VirtualSchedulerClock,
    parse_runner_manifest_phase_result,
    pin_drawing,
)

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
        offline_replay=False,
        drawing_id=None,
        target_cache=None,
        schedule_cache=None,
        replay_as_of=None,
        replay_root=None,
        bank=4980,
        stake=30,
        mode="playable",
        final_lead_minutes=20,
        safety_stop_minutes=5,
        db="custom.db",
        report_dir="reports",
        provider="api-sports",
        aliases="aliases.json",
        timing_overrides=None,
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
        kwargs["preflight_check"](
            _pinned_target(),
            DEADLINE - timedelta(minutes=20),
        )
        return result

    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_SECRET)
    monkeypatch.setattr(cli, "run_drawing", fake_run_drawing)
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: SimpleNamespace(drawing_info=lambda _drawing_id: _target_payload()),
    )
    monkeypatch.setattr(
        cli,
        "validate_output_paths",
        lambda outputs, **kwargs: captured.setdefault(
            "path_validation", (tuple(outputs), kwargs)
        ),
    )
    monkeypatch.setattr(
        cli,
        "probe_writable_directory",
        lambda path: captured.setdefault("probed_paths", []).append(Path(path)),
    )

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
        "load_ready_drawing_pins",
        lambda *_args, **_kwargs: tuple(f"pin-{index}" for index in range(15)),
    )
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

    def publish(result, **kwargs):
        captured["publication"] = kwargs
        external = (
            (
                Path(kwargs["report_dir"]) / "coverage.csv",
                Path(kwargs["report_dir"]) / "coverage.md",
            )
            if result.audit is not None
            else ()
        )
        ev = (
            (
                Path(kwargs["report_dir"]) / "ev.csv",
                Path(kwargs["report_dir"]) / "ev.md",
            )
            if result.decision != "NO BET" and result.ev_run is not None
            else ()
        )
        links = RunnerReportLinks(external=external, ev=ev)
        captured["runner_report"] = {
            "report_dir": kwargs["report_dir"],
            "links": links,
            "input_paths": kwargs["protected_paths"],
        }
        return SimpleNamespace(
            result=result,
            external=external,
            ev=ev,
            runner=(Path("reports/runner.json"), Path("reports/runner.md")),
        )

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
    monkeypatch.setattr(cli, "publish_drawing_run_artifacts", publish)
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


def test_runner_package_bridge_rejects_second_payload_mutation_before_ev(
    monkeypatch,
):
    expected = _pinned_target()
    mutated_payload = _target_payload()
    mutated_payload["data"]["number"] = 9999
    client = SimpleNamespace(drawing_info=lambda drawing_id: mutated_payload)
    monkeypatch.setattr(
        cli,
        "build_open_ev_package",
        lambda **_kwargs: pytest.fail("heavy EV work must not start"),
    )

    with pytest.raises(
        cli.RunnerTargetMismatch,
        match="fresh EV target does not match pinned target",
    ):
        cli._build_runner_package(
            client=client,
            expected=expected,
            config=DrawingRunnerConfig(bank=4980).ev_config,
            fetched_at=DEADLINE - timedelta(minutes=18),
            progress_callback=None,
            timing_eligibility_resolver=lambda _payload: pytest.fail(
                "timing lookup must not start"
            ),
        )


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
    assert provider_calls == [
        (SENTINEL_SECRET, Path("fresh-cache"), 0),
        (SENTINEL_SECRET, Path("fresh-provider"), 0),
    ]
    captured["audit_coverage"]()
    assert captured["audit"] == (
        ("session-factory",),
        {"last": 30, "minimum_bookmakers": 3},
    )
    captured["build_package"](_pinned_target())
    assert captured["ev"]["drawing_id"] == 11953
    assert captured["ev"]["config"] == config.ev_config
    assert captured["probed_paths"] == [
        Path("custom-reports"),
        Path("fresh-cache"),
    ]
    assert captured["runner_report"]["report_dir"] == "custom-reports"
    assert captured["runner_report"]["links"].external == (
        Path("custom-reports/coverage.csv"),
        Path("custom-reports/coverage.md"),
    )
    assert captured["runner_report"]["links"].ev == ()
    assert captured["runner_report"]["input_paths"] == (
        "custom.db",
        "aliases.json",
    )
    assert "--reuse-cache" not in runner.invoke(
        cli.app, ["run-drawing", "--help"]
    ).output
    assert "--min-gross-ev" not in runner.invoke(
        cli.app, ["run-drawing", "--help"]
    ).output


def test_run_drawing_pins_optional_timing_catalog_and_protects_input(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "timing-overrides.json"
    catalog_path.write_text('{"overrides": []}', encoding="utf-8")
    pinned_catalog = object()
    pin_calls = []
    monkeypatch.setattr(cli, "APISportsClient", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        cli,
        "pin_timing_override_catalog",
        lambda path: pin_calls.append(Path(path)) or pinned_catalog,
    )
    captured = _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))

    result = runner.invoke(
        cli.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4980",
            "--timing-overrides",
            str(catalog_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert pin_calls == [catalog_path]
    assert callable(captured["resolve_timing_override"])
    assert callable(captured["verify_timing_override"])
    assert captured["path_validation"][1]["protected_paths"] == (
        "data/toto.db",
        "data/external-odds/team-aliases.json",
        str(catalog_path),
    )
    assert captured["runner_report"]["input_paths"] == (
        "data/toto.db",
        "data/external-odds/team-aliases.json",
        str(catalog_path),
    )


def test_run_drawing_exposes_exact_approved_option_surface():
    command = typer.main.get_command(cli.app).commands["run-drawing"]
    option_names = {
        option
        for parameter in command.params
        for option in (*parameter.opts, *parameter.secondary_opts)
    }

    assert option_names == {
        "--open",
        "--offline-replay",
        "--drawing-id",
        "--target-cache",
        "--schedule-cache",
        "--replay-as-of",
        "--replay-root",
        "--bank",
        "--stake",
        "--mode",
        "--final-lead-minutes",
        "--safety-stop-minutes",
        "--db",
        "--report-dir",
        "--provider",
        "--aliases",
        "--timing-overrides",
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
            "offline_replay": False,
            "drawing_id": None,
            "target_cache": None,
            "schedule_cache": None,
            "replay_as_of": None,
            "replay_root": None,
            "stake": 30,
        "mode": "playable",
        "final_lead_minutes": 20,
        "safety_stop_minutes": 5,
            "db": None,
            "report_dir": None,
        "provider": "api-sports",
        "aliases": "data/external-odds/team-aliases.json",
        "timing_overrides": None,
        "quota_reserve": 10,
        "max_passes": 3,
        "max_expansion_passes": 3,
        "retry_delay_seconds": 65.0,
            "cache_root": None,
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


def test_runner_preflight_rejects_db_output_collision_before_any_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    db_path = report_dir / "external_coverage_last_30_min_bookmakers_3.csv"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"protected-database")

    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args: pytest.fail("database access must not start"),
    )

    with pytest.raises(ValueError, match="protected inputs"):
        cli._prepare_runner_resources(
            config=DrawingRunnerConfig(bank=4980),
            target=_pinned_target(),
            preflight_at=DEADLINE - timedelta(minutes=20),
            db=db_path,
            aliases=tmp_path / "aliases.json",
            report_dir=report_dir,
            cache_root=tmp_path / "cache",
            provider_factory=lambda _path: pytest.fail(
                "provider construction must not start"
            ),
        )

    assert db_path.read_bytes() == b"protected-database"


def test_runner_preflight_rejects_symlink_alias_collision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    aliases = tmp_path / "aliases.json"
    aliases.write_bytes(b"protected-aliases")
    collision = report_dir / "external_coverage_last_30_min_bookmakers_3.csv"
    collision.symlink_to(aliases)
    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args: pytest.fail("database access must not start"),
    )

    with pytest.raises(ValueError, match="protected inputs"):
        cli._prepare_runner_resources(
            config=DrawingRunnerConfig(bank=4980),
            target=_pinned_target(),
            preflight_at=DEADLINE - timedelta(minutes=20),
            db=tmp_path / "toto.sqlite",
            aliases=aliases,
            report_dir=report_dir,
            cache_root=tmp_path / "cache",
            provider_factory=lambda _path: pytest.fail(
                "provider construction must not start"
            ),
        )

    assert aliases.read_bytes() == b"protected-aliases"
    assert collision.is_symlink()


@pytest.mark.parametrize("blocked_name", ("report", "cache"))
def test_runner_preflight_rejects_unwritable_output_roots_before_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blocked_name: str,
) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_bytes(b"protected")
    report_dir = blocked if blocked_name == "report" else tmp_path / "reports"
    cache_root = blocked if blocked_name == "cache" else tmp_path / "cache"
    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args: pytest.fail("database access must not start"),
    )

    with pytest.raises(OSError):
        cli._prepare_runner_resources(
            config=DrawingRunnerConfig(bank=4980),
            target=_pinned_target(),
            preflight_at=DEADLINE - timedelta(minutes=20),
            db=tmp_path / "toto.sqlite",
            aliases=tmp_path / "aliases.json",
            report_dir=report_dir,
            cache_root=cache_root,
            provider_factory=lambda _path: pytest.fail(
                "provider construction must not start"
            ),
        )

    assert blocked.read_bytes() == b"protected"


def test_corrupt_stored_timing_is_a_controlled_nonzero_failure(monkeypatch):
    captured = _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))
    pinned = _pinned_target()

    def corrupt_state(*args):
        raise ValueError("corrupt stored eligibility")

    def resolve_timing(**kwargs):
        kwargs["preflight_check"](
            pinned,
            DEADLINE - timedelta(minutes=20),
        )
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
        "publish_drawing_run_artifacts",
        runner_reports.publish_drawing_run_artifacts,
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
            "--db",
            str(tmp_path / "toto.sqlite"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--cache-root",
            str(tmp_path / "cache"),
        ],
    )

    assert interrupted.exit_code != 0
    assert "no final manifest was published" in interrupted.output
    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == ()


def test_progress_exit_interrupts_before_any_publication(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _early_no_bet_result()
    _wire_runner(monkeypatch, result=result)

    class InterruptingProgress:
        def __init__(self, *_columns):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            raise KeyboardInterrupt("progress shutdown interrupted")

        def add_task(self, _description):
            return 1

        def update(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(cli, "Progress", InterruptingProgress)

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
    assert tuple(path for path in tmp_path.rglob("*") if path.is_file()) == ()


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


def _local_scheduler_manifest(*, final_lead_minutes: int) -> dict[str, object]:
    fingerprint = "b" * 64
    return {
        "schema_version": 4,
        "run_id": f"local-{final_lead_minutes}",
        "command_status": "success",
        "decision": "PLAY",
        "terminal_reason": "local production-parser fixture",
        "target": {
            "drawing_id": 12001,
            "drawing_number": 5001,
            "deadline": "2030-01-02T12:00:00Z",
            "preflight_fingerprint": fingerprint,
            "final_fingerprint": fingerprint,
        },
        "config": {
            "bank": 4980,
            "stake": 30,
            "mode": "playable",
            "final_lead_minutes": final_lead_minutes,
            "safety_stop_minutes": 10,
            "provider": "api-sports",
        },
        "timeline": {
            "preflight_at": "2030-01-02T11:15:00Z",
            "final_started_at": "2030-01-02T11:45:00Z",
            "collection_finished_at": "2030-01-02T11:46:00Z",
            "timing_finished_at": "2030-01-02T11:47:00Z",
            "audit_finished_at": "2030-01-02T11:48:00Z",
            "ev_finished_at": "2030-01-02T11:49:00Z",
            "finished_at": "2030-01-02T11:49:00Z",
            "elapsed_seconds": 1.0,
        },
        "collection": {
            "final_collection_id": "c" * 64,
            "collection_ids": ["c" * 64],
            "pass_count": 1,
            "base_pass_count": 1,
            "expansion_pass_count": 0,
            "expanded": False,
            "final_horizon_days": 2,
            "stop_reason": "no_retryable_fallbacks",
            "total_requests": 5,
            "total_cache_hits": 0,
            "requested_schedule_date_count": 2,
            "successful_schedule_date_count": 2,
            "failed_schedule_date_count": 0,
            "elapsed_seconds": 1.0,
            "pinned_revalidation": asdict(
                ready_pinned_revalidation(
                    datetime(2030, 1, 2, 11, 46, tzinfo=UTC)
                )
            ),
        },
        "eligibility": {
            "status": "playable",
            "reason": "local playable timing",
            "target_fingerprint": fingerprint,
            "fingerprint_match": True,
            "span_days": 1,
            "missing_event_orders": [],
            "totobrief_count": 15,
            "provider_count": 0,
            "operator_override_count": 0,
            "earliest_start": "2030-01-02T12:30:00Z",
            "latest_start": "2030-01-02T14:30:00Z",
            "effective": {
                "status": "playable",
                "reason": "local playable timing",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "raw": {
                "status": "playable",
                "reason": "local playable timing",
                "target_fingerprint": fingerprint,
                "fingerprint_match": True,
                "span_days": 1,
                "missing_event_orders": [],
                "totobrief_count": 15,
                "provider_count": 0,
                "operator_override_count": 0,
                "earliest_start": "2030-01-02T12:30:00Z",
                "latest_start": "2030-01-02T14:30:00Z",
            },
            "override": None,
        },
        "coverage": {
            "gate_decision": "PENDING",
            "gate_reasons": ["prospective sample is incomplete"],
            "drawings": 1,
            "events": 15,
            "unique_match_rate": 0.8,
            "consensus_rate": 0.7,
            "ambiguous_matches": 0,
            "explicit_dispositions": 15,
            "operational_failures": 0,
        },
        "ev": {
            "computed": True,
            "requested_bank": 4980,
            "effective_budget": 30,
            "selected_cost": 30,
            "unused_requested_bank": 4950,
            "input_fetched_at": "2030-01-02T11:45:00Z",
            "minimum_gross_ev": 1.0,
            "prize_fund_factor": 1.0,
            "possible_winnings_source": "pool_sum proxy",
            "jackpot_source": "totobrief payload",
            "self_dilution_ratio": 0.001,
            "model_supported": True,
            "model_warning": None,
            "package": {
                "decision": "PLAY",
                "decision_reason": None,
                "coupons": [
                    {
                        "rank": 1,
                        "coupon": "111111111111111",
                        "gross_ev": 1.2,
                        "net_ev": 0.2,
                    }
                ],
                "selected_count": 1,
                "cost": 30,
                "unused_bank": 4950,
                "expected_payout": 36.0,
                "modeled_roi": 0.2,
                "derived_brief": ["1"] * 15,
            },
            "sensitivity": [],
        },
        "report_links": {"external": [], "ev": []},
        "replay": None,
        "warnings": [],
    }


def test_scheduler_cli_plan_simulated_execute_and_operator_pickup_are_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "production-scheduler"
    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: (_ for _ in ()).throw(AssertionError("network client used")),
    )

    prepared = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5001",
            "--drawing-id",
            "12001",
            "--ended-at",
            "2030-01-02T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert prepared.exit_code == 0, prepared.output
    plan_path = output_dir / "scheduler-plan.json"
    assert plan_path.is_file()
    assert (output_dir / "run-scheduler.sh").is_file()
    assert (output_dir / "totoai-scheduler.plist").is_file()

    executed = runner.invoke(
        cli.app,
        [
            "scheduler-execute",
            "--plan",
            str(plan_path),
            "--simulate",
            "--run-id",
            "cli-acceptance",
        ],
    )

    assert executed.exit_code == 0, executed.output
    assert "Outcome: bet-ready" in executed.output
    assert "Decision: PLAY" in executed.output
    run_dir = output_dir / "runs" / "5001" / "cli-acceptance"
    status_path = run_dir / "status.json"
    package_path = run_dir / "package.csv"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    package = package_path.read_bytes()
    assert status["outcome"] == "bet-ready"
    assert status["decision"] == "PLAY"
    assert status["package_path"] == str(package_path)
    assert status["package_sha256"] == hashlib.sha256(package).hexdigest()
    assert package.startswith(b"rank,coupon,gross_ev,net_ev\n")
    assert package.count(b"\n") >= 3
    assert (run_dir / ".bet-ready").is_file()
    assert not (run_dir / ".success").exists()


def test_scheduler_cli_real_production_parser_and_capture_are_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "production-parser-scheduler"
    plan_result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5001",
            "--drawing-id",
            "12001",
            "--ended-at",
            "2030-01-02T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output

    clock = VirtualSchedulerClock(
        datetime(2030, 1, 2, 11, 15, tzinfo=UTC)
    )

    class LocalCommandRunner(CommandSchedulerPhaseRunner):
        def _preflight(self, _plan, _work_dir):
            return None

    production_runner = LocalCommandRunner(
        environment={},
        target_validator=lambda _plan, _started_at: None,
    )
    monkeypatch.setattr(cli, "CommandSchedulerPhaseRunner", lambda: production_runner)
    monkeypatch.setattr(cli, "_utc_now_datetime", clock.now)
    monkeypatch.setattr(cli.time, "sleep", clock.sleep)

    subprocess_calls: list[tuple[str, ...]] = []

    def local_subprocess(command, **_kwargs):
        command = tuple(command)
        subprocess_calls.append(command)
        report_dir = Path(command[command.index("--report-dir") + 1])
        final_lead = int(command[command.index("--final-lead-minutes") + 1])
        report_dir.mkdir(parents=True)
        (report_dir / f"drawing_run_local_{final_lead}.json").write_text(
            json.dumps(
                _local_scheduler_manifest(final_lead_minutes=final_lead)
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="Decision: PLAY\n", stderr="")

    parsed: list[Path] = []
    production_parser = parse_runner_manifest_phase_result

    def tracked_parser(context, manifest_path):
        parsed.append(Path(manifest_path))
        return production_parser(context, manifest_path)

    monkeypatch.setattr(scheduler_module.subprocess, "run", local_subprocess)
    monkeypatch.setattr(
        scheduler_module,
        "parse_runner_manifest_phase_result",
        tracked_parser,
    )

    executed = runner.invoke(
        cli.app,
        [
            "scheduler-execute",
            "--plan",
            str(output_dir / "scheduler-plan.json"),
            "--run-id",
            "real-local-acceptance",
        ],
    )

    assert executed.exit_code == 0, executed.output
    assert "Outcome: bet-ready" in executed.output
    assert len(subprocess_calls) == 2
    assert all(
        command[command.index("--min-gross-ev") + 1] == "1"
        for command in subprocess_calls
    )
    assert len(parsed) == 2
    run_dir = output_dir / "runs" / "5001" / "real-local-acceptance"
    package = run_dir / "package.csv"
    assert package.read_text(encoding="utf-8") == (
        "rank,coupon,gross_ev,net_ev\n"
        "1,111111111111111,1.2,0.20000000000000001\n"
    )
    assert (run_dir / ".bet-ready").is_file()
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["selected_snapshot"] == "final"
    assert status["selected_count"] == 1
    assert status["selected_cost"] == 30


def test_scheduler_cli_dry_run_outputs_plan_without_writes(tmp_path: Path) -> None:
    output_dir = tmp_path / "dry-run-scheduler"

    result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5002",
            "--ended-at",
            "2030-01-03T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["target"]["drawing"] == 5002
    assert payload["config"]["minimum_gross_ev"] == 1.0
    assert payload["deadlines"]["t_minus_45"] == "2030-01-03T11:15:00Z"
    assert payload["deadlines"]["t_minus_10"] == "2030-01-03T11:50:00Z"
    assert not output_dir.exists()


def test_scheduler_cli_rejects_null_ended_at_before_artifact_creation(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "invalid-scheduler"

    result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5002",
            "--ended-at",
            "null",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    assert "ended_at" in result.output
    assert not output_dir.exists()


def test_scheduler_cli_rejects_shell_script_python_executable(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "unsafe-executable-scheduler"
    executable = tmp_path / "python-probe"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5002",
            "--ended-at",
            "2030-01-03T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--python-executable",
            str(executable),
        ],
    )

    assert result.exit_code != 0
    assert "current interpreter" in result.output
    assert not output_dir.exists()
