import hashlib
import json
import sys
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
from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.ev.models import PlayTimingEligibility
from toto_ai.ev.package_quality import (
    EVALUATION_MC_STREAM,
    OPTIMIZATION_MC_STREAM,
    deterministic_outcome_seed,
    diagnostics_payload_sha256,
)
from toto_ai.external_odds.domain import ProviderEvent
from toto_ai.external_odds.eligibility import DrawingEligibility
from toto_ai.external_odds.preparation import prepare_drawing
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_resolution import ResolutionContext
from toto_ai.package.audit import evaluate_package_safety
from toto_ai.runner import (
    CommandSchedulerPhaseRunner,
    DrawingRunnerConfig,
    DrawingRunnerResult,
    RunnerReportLinks,
    SchedulerPhaseContext,
    VirtualSchedulerClock,
    build_run_drawing_phase_command,
    build_scheduler_plan,
    pin_drawing,
    prepare_scheduler_artifacts,
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
                        "pool_win_1": 0.3,
                        "pool_draw": 0.3,
                        "pool_win_2": 0.4,
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
        minimum_gross_ev=1.0,
        package_near_fixed_share=0.95,
        package_low_probability_threshold=0.20,
        package_material_probability_threshold=0.20,
        final_lead_minutes=20,
        safety_stop_minutes=5,
        db="custom.db",
        report_dir="reports",
        provider="api-sports",
        aliases="aliases.json",
        timing_overrides=None,
        reviewed_schedule_catalog=None,
        expected_reviewed_catalog_hash=None,
        schedule_evidence_ledger=str(cli.DEFAULT_SCHEDULE_EVIDENCE_PATH),
        expected_schedule_evidence_sha256=None,
        expected_schedule_evidence_semantic_hash=None,
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
    missing_key = runner.invoke(cli.app, ["run-drawing", "--open", "--bank", "4980"])

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
    monkeypatch.setattr(
        cli,
        "persist_drawing_identity",
        lambda session_factory, target, **kwargs: captured.setdefault(
            "persisted_drawing_identity",
            (session_factory, target, kwargs),
        ),
    )
    monkeypatch.setattr(cli, "open_readonly_db", open_readonly_database)
    monkeypatch.setattr(cli, "load_aliases", lambda aliases: {"aliases": aliases})
    monkeypatch.setattr(
        cli,
        "load_ready_pin_set",
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
        captured["publication_result"] = result
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

    def provider(api_key, *, cache_dir, schedule_cache_dir, quota_reserve):
        provider_calls.append((api_key, cache_dir, quota_reserve))
        assert schedule_cache_dir is None
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
        cli.DEFAULT_SCHEDULE_EVIDENCE_PATH.resolve(),
    )
    assert (
        "--reuse-cache" not in runner.invoke(cli.app, ["run-drawing", "--help"]).output
    )
    assert "--min-gross-ev" in runner.invoke(cli.app, ["run-drawing", "--help"]).output


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
        cli.DEFAULT_SCHEDULE_EVIDENCE_PATH.resolve(),
    )
    assert captured["runner_report"]["input_paths"] == (
        "data/toto.db",
        "data/external-odds/team-aliases.json",
        str(catalog_path),
        cli.DEFAULT_SCHEDULE_EVIDENCE_PATH.resolve(),
    )


def test_run_drawing_protects_reviewed_snapshots_and_fails_closed_on_toctou(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "reviewed-catalog.json"
    official_path = tmp_path / "official.html"
    independent_path = tmp_path / "independent.html"
    for path in (catalog_path, official_path, independent_path):
        path.write_text("pinned", encoding="utf-8")
    catalog = SimpleNamespace(
        path=catalog_path.resolve(),
        semantic_hash="c" * 64,
        records=(
            SimpleNamespace(
                claims=(
                    SimpleNamespace(snapshot_path=Path("official.html")),
                    SimpleNamespace(snapshot_path=Path("independent.html")),
                )
            ),
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_reviewed_schedule_catalog",
        lambda *args, **kwargs: catalog,
    )
    monkeypatch.setattr(
        cli,
        "revalidate_reviewed_catalog",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("reviewed source snapshot hash mismatch")
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_ready_pin_set",
        lambda *_args, **_kwargs: tuple(f"pin-{index}" for index in range(15)),
    )
    captured = _wire_runner(
        monkeypatch,
        result=_RunnerResult("PLAY", ev_run=object()),
    )

    result = runner.invoke(
        cli.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4980",
            "--reviewed-schedule-catalog",
            str(catalog_path),
        ],
    )

    assert result.exit_code == 0, result.output
    protected = captured["runner_report"]["input_paths"]
    assert protected == (
        "data/toto.db",
        "data/external-odds/team-aliases.json",
        cli.DEFAULT_SCHEDULE_EVIDENCE_PATH.resolve(),
        catalog_path.resolve(),
        independent_path.resolve(),
        official_path.resolve(),
    )
    publication_result = captured["publication_result"]
    assert publication_result.decision == "NO BET"
    assert "TOCTOU" in publication_result.terminal_reason
    assert publication_result.ev_run is None


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
        "--min-gross-ev",
        "--package-near-fixed-share",
        "--package-low-probability-threshold",
        "--package-material-probability-threshold",
        "--final-lead-minutes",
        "--safety-stop-minutes",
        "--db",
        "--report-dir",
        "--provider",
        "--aliases",
        "--timing-overrides",
        "--reviewed-schedule-catalog",
        "--expected-reviewed-catalog-hash",
        "--schedule-evidence-ledger",
        "--expected-schedule-evidence-sha256",
        "--expected-schedule-evidence-semantic-hash",
        "--quota-reserve",
        "--max-passes",
        "--max-expansion-passes",
        "--retry-delay-seconds",
        "--cache-root",
        "--shared-schedule-cache-root",
    }
    forbidden = {
        "--no-open",
        "--reuse-cache",
        "--fresh",
        "--expand-missing-starts",
        "--expansion-horizon-days",
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
        "minimum_gross_ev": 1.0,
        "package_near_fixed_share": 0.95,
        "package_low_probability_threshold": 0.20,
        "package_material_probability_threshold": 0.20,
        "final_lead_minutes": 20,
        "safety_stop_minutes": 5,
        "db": None,
        "report_dir": None,
        "provider": "api-sports",
        "aliases": "data/external-odds/team-aliases.json",
        "timing_overrides": None,
        "reviewed_schedule_catalog": None,
        "expected_reviewed_catalog_hash": None,
        "schedule_evidence_ledger": str(cli.DEFAULT_SCHEDULE_EVIDENCE_PATH),
        "expected_schedule_evidence_sha256": None,
        "expected_schedule_evidence_semantic_hash": None,
        "quota_reserve": 10,
        "max_passes": 3,
        "max_expansion_passes": 3,
            "retry_delay_seconds": 65.0,
            "cache_root": None,
            "shared_schedule_cache_root": None,
        }


def test_scheduler_generated_run_drawing_argv_matches_cli_contract(
    monkeypatch,
    tmp_path,
):
    captured = _wire_runner(monkeypatch, result=_RunnerResult("NO BET"))
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at="2030-01-02T12:00:00Z",
        bank=4980,
        minimum_gross_ev=1.07,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )
    work_dir = tmp_path / "scheduler" / "work"
    context = SchedulerPhaseContext(
        phase="final",
        plan=plan,
        run_id="contract",
        run_dir=work_dir.parent,
        work_dir=work_dir,
        scheduled_at=plan.final_at,
        started_at=plan.final_at,
    )
    command = build_run_drawing_phase_command(context)
    argv = list(command[command.index("run-drawing") :])

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli.app, argv)

    assert result.exit_code == 0, result.output
    assert result.exit_code != 2
    captured["build_package"](_pinned_target())
    assert captured["ev"]["config"].min_gross_ev == 1.07


@pytest.mark.parametrize(
    ("decision", "mode", "expected_decision"),
    [
        ("PLAY", "playable", "NO BET"),
        ("RESEARCH ONLY", "research", "RESEARCH ONLY"),
    ],
)
def test_run_drawing_prints_actionable_decisions_and_rich_progress(
    monkeypatch,
    decision,
    mode,
    expected_decision,
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
    assert f"Decision: {expected_decision}" in result.output
    assert captured["publication_result"].decision == expected_decision
    assert captured["progress_descriptions"] == [
        "Preflighting open drawing",
        "Preflighting open drawing",
        "Waiting for T-10.0 final window",
        "Revalidating pinned drawing",
        "Collecting fresh API-Sports odds",
        "Checking exact timing eligibility",
        "Auditing latest 30 collections",
        "Building exact EV package",
        f"Runner complete: {expected_decision}",
    ]


def test_run_drawing_cli_cannot_publish_injected_legacy_play(monkeypatch):
    captured = _wire_runner(monkeypatch, result=_RunnerResult("PLAY"))

    result = runner.invoke(
        cli.app,
        ["run-drawing", "--open", "--bank", "4980", "--mode", "playable"],
    )

    assert result.exit_code == 0, result.output
    assert "Decision: NO BET" in result.output
    assert "Decision: PLAY" not in result.output
    published = captured["publication_result"]
    assert published.decision == "NO BET"
    assert published.ev_run is None


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--bank", "61", "--stake", "20"], "divisible"),
        (["--bank", "60", "--final-lead-minutes", "5"], "greater"),
        (["--bank", "60", "--safety-stop-minutes", "0"], "x>=1"),
        (["--bank", "60", "--min-gross-ev", "nan"], "must be finite"),
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
    interrupted = runner.invoke(cli.app, ["run-drawing", "--open", "--bank", "4980"])

    assert interrupted.exit_code != 0
    assert "interrupted" in interrupted.output.lower()


def _local_scheduler_manifest(
    *,
    final_lead_minutes: int,
    safety_stop_minutes: int = 10,
    probability_snapshot_sha256: str,
    probability_input_sha256: str,
    schedule_evidence_ledger_sha256: str,
    schedule_evidence_semantic_hash: str,
    quality_v2_config: dict[str, object],
    selection_context: dict[str, object],
    selection_context_sha256: str,
) -> dict[str, object]:
    fingerprint = "b" * 64
    coupons = [
        {
            "rank": 1,
            "coupon": "111111111111111",
            "gross_ev": 1.2,
            "net_ev": 0.2,
        },
        {
            "rank": 2,
            "coupon": "XXXXXXXXXXXXXXX",
            "gross_ev": 1.1,
            "net_ev": 0.1,
        },
    ]
    safety = evaluate_package_safety(
        tuple(str(row["coupon"]) for row in coupons),
        ((0.45, 0.45, 0.10),) * 15,
    ).to_dict()
    assert safety["probability_input_sha256"] == probability_input_sha256
    selection_diagnostics = {
        "post_package_sha256": hashlib.sha256(
            ",".join(str(row["coupon"]) for row in coupons).encode("utf-8")
        ).hexdigest(),
        "probability_snapshot_sha256": probability_snapshot_sha256,
        "probability_input_sha256": probability_input_sha256,
        "schedule_evidence_ledger_sha256": schedule_evidence_ledger_sha256,
        "schedule_evidence_semantic_hash": schedule_evidence_semantic_hash,
        "provenance_complete": True,
        "monte_carlo_seed_material_sha256": "4" * 64,
        "optimization_monte_carlo_seed": deterministic_outcome_seed(
            seed_material="4" * 64, stream=OPTIMIZATION_MC_STREAM
        ),
        "evaluation_monte_carlo_seed": deterministic_outcome_seed(
            seed_material="4" * 64, stream=EVALUATION_MC_STREAM
        ),
        "optimization_monte_carlo_samples": quality_v2_config["optimization_samples"],
        "evaluation_monte_carlo_samples": quality_v2_config["evaluation_samples"],
        "optimization_monte_carlo_stream": OPTIMIZATION_MC_STREAM,
        "evaluation_monte_carlo_stream": EVALUATION_MC_STREAM,
        "numpy_version": quality_v2_config["numpy_version"],
        "quality_v2_config_sha256": hashlib.sha256(
            json.dumps(
                quality_v2_config,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        "selection_context_sha256": selection_context_sha256,
        "release_protocol_version": "quality-v2-paper-only-v1",
        "release_evidence_id": None,
        "release_evidence_sha256": None,
        "release_gate_decision": "NO BET",
        "release_gate_reason": "trusted prospective evidence registry absent",
        "real_money_actionable": False,
        "diagnostics_sha256": "",
    }
    selection_diagnostics["diagnostics_sha256"] = diagnostics_payload_sha256(
        selection_diagnostics
    )
    return {
        "schema_version": 5,
        "run_id": f"local-{final_lead_minutes}",
        "command_status": "success",
        "decision": "NO BET",
        "terminal_reason": "quality-v2 paper-only release gate",
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
            "safety_stop_minutes": safety_stop_minutes,
            "provider": "api-sports",
            "quality_v2": quality_v2_config,
            "selection_context": selection_context,
            "selection_context_sha256": selection_context_sha256,
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
                ready_pinned_revalidation(datetime(2030, 1, 2, 11, 46, tzinfo=UTC))
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
            "effective_budget": 60,
            "selected_cost": 0,
            "unused_requested_bank": 4980,
            "input_fetched_at": "2030-01-02T11:45:00Z",
            "minimum_gross_ev": 1.0,
            "prize_fund_factor": 1.0,
            "possible_winnings_source": "pool_sum proxy",
            "jackpot_source": "totobrief payload",
            "self_dilution_ratio": 0.001,
            "model_supported": True,
            "model_warning": None,
            "package_safety": safety,
            "selection_diagnostics": selection_diagnostics,
            "package": {
                "decision": "NO BET",
                "decision_reason": "quality_v2_real_money_release_gate_closed",
                "coupons": [],
                "selected_count": 0,
                "cost": 0,
                "unused_bank": 4980,
                "expected_payout": 0.0,
                "modeled_roi": None,
                "derived_brief": [],
                "structural_status": "STRUCTURAL_PASS",
                "artifact_class": "TRAINING/PAPER",
                "paper_coupons": coupons,
                "paper_selected_count": 2,
                "paper_cost": 60,
                "paper_expected_payout": 69.0,
                "paper_modeled_roi": 69.0 / 60.0 - 1.0,
                "paper_derived_brief": ["1X"] * 15,
            },
            "sensitivity": [],
        },
        "report_links": {"external": [], "ev": []},
        "replay": None,
        "final_input": {
            "path": "final-input.json",
            "captured_at": "2030-01-02T11:40:00Z",
            "snapshot_sha256": "1" * 64,
            "detail_payload_sha256": "2" * 64,
            "probability_input_sha256": "3" * 64,
            "attempt_id": "local",
        },
        "warnings": [],
    }


def _seed_scheduler_drawing(
    db: Path,
    *,
    drawing_id: int,
    drawing_number: int,
    ended_at: str,
) -> None:
    engine = init_db(db)
    with get_session_factory(engine).begin() as session:
        session.add(
            Drawing(
                id=drawing_id,
                number=drawing_number,
                name="scheduler-cli-fixture",
                status="active",
                ended_at=ended_at,
            )
        )
    engine.dispose()


def _seed_scheduler_preparation(
    db: Path,
    *,
    detail_payload: dict[str, object],
    deadline: datetime,
) -> None:
    """Persist the real READY precondition required by an atomic final run."""
    fetched_at = deadline - timedelta(minutes=30)
    target = parse_target_drawing(detail_payload, fetched_at=fetched_at)
    engine = init_db(db)
    try:
        result = prepare_drawing(
            target,
            tuple(
                ProviderEvent(
                    provider="api-sports",
                    provider_event_id=f"fixture-{event.event_order}",
                    sport=event.sport,
                    league=event.championship,
                    starts_at=deadline
                    + timedelta(minutes=30 + event.event_order),
                    home_team=event.home_team,
                    away_team=event.away_team,
                    fetched_at=fetched_at,
                    payload_hash=f"hash-{event.event_order}",
                    country=None,
                    provider_home_team_id=f"home-{event.event_order}",
                    provider_away_team_id=f"away-{event.event_order}",
                )
                for event in target.events
            ),
            session_factory=get_session_factory(engine),
            event_contexts={
                event.event_order: ResolutionContext(
                    "api-sports",
                    league=event.championship,
                )
                for event in target.events
            },
            evaluated_at=fetched_at,
        )
    finally:
        engine.dispose()
    assert result.status == "ready"
    assert result.mapped_count == 15
    assert len(result.pins) == 15


def test_scheduler_cli_plan_simulated_execute_and_operator_pickup_are_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
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
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
        ],
    )

    assert prepared.exit_code == 0, prepared.output
    plan_path = output_dir / "scheduler-plan.json"
    assert plan_path.is_file()
    assert (output_dir / "run-scheduler.sh").is_file()
    assert (output_dir / "totoai-scheduler.plist").is_file()
    _seed_scheduler_drawing(
        tmp_path / "data" / "toto.db",
        drawing_id=12001,
        drawing_number=5001,
        ended_at="2030-01-02T12:00:00Z",
    )

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
    assert "Outcome: no-bet" in executed.output
    assert "Decision: NO BET" in executed.output
    run_dir = output_dir / "runs" / "5001" / "cli-acceptance"
    status_path = run_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["outcome"] == "no-bet"
    assert status["decision"] == "NO BET"
    assert status["package_path"] is None
    assert status["package_sha256"] is None
    assert not (run_dir / "package.csv").exists()
    assert (run_dir / ".no-bet").is_file()
    assert not (run_dir / ".success").exists()


def test_scheduler_preflight_only_cli_is_explicitly_package_free(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=datetime(2030, 1, 2, 12, tzinfo=timezone.utc),
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    monkeypatch.setattr(
        cli,
        "execute_scheduler_preflight_only",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "package_generation": False,
            "training": False,
        },
    )

    result = runner.invoke(
        cli.app,
        ["scheduler-preflight-only", "--plan", str(artifacts.plan_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "package_generation": False,
        "status": "PASS",
        "training": False,
    }


def test_scheduler_cli_rejects_production_run_id_for_schema_v4(
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
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
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    _seed_scheduler_drawing(
        tmp_path / "data" / "toto.db",
        drawing_id=12001,
        drawing_number=5001,
        ended_at="2030-01-02T12:00:00Z",
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

    assert executed.exit_code == 2
    assert "--run-id is simulation-only" in executed.output
    assert not (output_dir / "runs").exists()


def test_scheduler_cli_atomic_final_binds_safety_manifest_archive_and_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    output_dir = tmp_path / "atomic-production-scheduler"
    deadline = datetime(2030, 1, 2, 12, 0, tzinfo=UTC)
    detail_payload = {
        "data": {
            "id": 12001,
            "number": 5001,
            "status": "active",
            "ended_at": deadline.isoformat(),
            "events": [
                {
                    "id": 30_000 + order,
                    "order": order,
                    "name": f"Home {order} — Away {order}",
                    "championship": "Atomic Fixture League",
                    "quotes": {
                        "bk_win_1": 45,
                        "bk_draw": 45,
                        "bk_win_2": 10,
                        "pool_win_1": 45,
                        "pool_draw": 45,
                        "pool_win_2": 10,
                    },
                }
                for order in range(15)
            ],
        }
    }
    plan_result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5001",
            "--drawing-id",
            "12001",
            "--ended-at",
            deadline.isoformat(),
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    _seed_scheduler_drawing(
        tmp_path / "data" / "toto.db",
        drawing_id=12001,
        drawing_number=5001,
        ended_at=deadline.isoformat(),
    )
    _seed_scheduler_preparation(
        tmp_path / "data" / "toto.db",
        detail_payload=detail_payload,
        deadline=deadline,
    )

    detail_calls = 0

    class LocalClient:
        def drawing_info(self, drawing_id):
            nonlocal detail_calls
            detail_calls += 1
            assert drawing_id == 12001
            return detail_payload

    class LocalCommandRunner(CommandSchedulerPhaseRunner):
        pass

    clock = VirtualSchedulerClock(deadline - timedelta(minutes=20))
    production_runner = LocalCommandRunner(
        environment={},
        target_validator=lambda _plan, _started_at: None,
        now=clock.now,
    )
    monkeypatch.setattr(cli, "CommandSchedulerPhaseRunner", lambda: production_runner)
    monkeypatch.setattr(cli, "_utc_now_datetime", clock.now)
    monkeypatch.setattr(cli.time, "sleep", clock.sleep)
    monkeypatch.setattr(scheduler_module, "TotoBriefClient", LocalClient)

    def local_subprocess(command, **kwargs):
        command = tuple(command)
        report_dir = Path(command[command.index("--report-dir") + 1])
        report_dir.mkdir(parents=True, exist_ok=True)
        final_input_path = Path(kwargs["env"]["TOTO_FINAL_INPUT"])
        final_input = json.loads(final_input_path.read_text(encoding="utf-8"))
        plan_config = json.loads(
            (output_dir / "scheduler-plan.json").read_text(encoding="utf-8")
        )["config"]
        manifest = _local_scheduler_manifest(
            final_lead_minutes=25,
            safety_stop_minutes=16,
            probability_snapshot_sha256=final_input["snapshot_sha256"],
            probability_input_sha256=final_input["probability_input_sha256"],
            schedule_evidence_ledger_sha256=plan_config[
                "schedule_evidence_ledger_sha256"
            ],
            schedule_evidence_semantic_hash=plan_config[
                "schedule_evidence_semantic_hash"
            ],
            quality_v2_config=plan_config["quality_v2"],
            selection_context=plan_config["selection_context"],
            selection_context_sha256=plan_config["selection_context_sha256"],
        )
        fingerprint = final_input["target_fingerprint"]
        manifest["run_id"] = final_input["attempt_id"]
        manifest["target"].update(
            {
                "preflight_fingerprint": fingerprint,
                "final_fingerprint": fingerprint,
            }
        )
        manifest["eligibility"]["target_fingerprint"] = fingerprint
        manifest["eligibility"]["raw"]["target_fingerprint"] = fingerprint
        manifest["eligibility"]["effective"]["target_fingerprint"] = fingerprint
        manifest["final_input"] = {
            "path": str(final_input_path),
            "captured_at": final_input["captured_at"],
            "snapshot_sha256": final_input["snapshot_sha256"],
            "detail_payload_sha256": final_input["detail_payload_sha256"],
            "probability_input_sha256": final_input["probability_input_sha256"],
            "attempt_id": final_input["attempt_id"],
        }
        manifest["timeline"]["final_started_at"] = "2030-01-02T11:40:00Z"
        manifest["ev"]["input_fetched_at"] = final_input["captured_at"]
        (report_dir / "drawing_run_atomic.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        clock.sleep(60)
        return SimpleNamespace(returncode=0, stdout="Decision: NO BET\n", stderr="")

    monkeypatch.setattr(scheduler_module.subprocess, "run", local_subprocess)

    executed = runner.invoke(
        cli.app,
        [
            "scheduler-execute",
            "--plan",
            str(output_dir / "scheduler-plan.json"),
        ],
    )

    assert executed.exit_code == 0, executed.output
    assert "Outcome: no-bet" in executed.output
    assert detail_calls == 1
    attempts = tuple((output_dir / "attempts").iterdir())
    assert len(attempts) == 1
    attempt = attempts[0]
    final_input = json.loads((attempt / "final-input.json").read_text(encoding="utf-8"))
    assert final_input["snapshot_sha256"]
    status_path = next(output_dir.glob("runs/5001/*/status.json"))
    run_dir = status_path.parent
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert not (run_dir / "package-archive.json").exists()
    assert status["decision"] == "NO BET"
    package_path = Path(status["package_path"])
    assert package_path.name == "baltbet-upload.txt"
    upload_lines = package_path.read_text(encoding="utf-8").splitlines()
    assert upload_lines == [
        "30; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1; 1",
        "30; X; X; X; X; X; X; X; X; X; X; X; X; X; X; X",
    ]
    operator = json.loads(
        (output_dir / "operator-result.json").read_text(encoding="utf-8")
    )
    assert operator["coupon_path"] == str(package_path)
    assert operator["selected_count"] == 2
    assert operator["selected_cost"] == 60
    assert operator["stake"] == 30
    assert operator["requested_bank"] == 4980
    assert operator["effective_bank"] == 60
    assert operator["automatic_wagering"] is False
    assert operator["actionable"] is False
    assert (run_dir / ".no-bet").is_file()
    assert not (run_dir / ".bet-ready").exists()


def test_scheduler_cli_dry_run_outputs_plan_without_writes(tmp_path: Path) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    output_dir = tmp_path / "dry-run-scheduler"

    result = runner.invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5002",
            "--drawing-id",
            "12002",
            "--ended-at",
            "2030-01-03T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["target"]["drawing"] == 5002
    assert payload["config"]["minimum_gross_ev"] == 1.0
    assert payload["config"]["minimum_final_runtime_seconds"] == 300
    assert payload["deadlines"]["t_minus_45"] == "2030-01-03T11:15:00Z"
    assert payload["deadlines"]["t_minus_10"] == "2030-01-03T11:50:00Z"
    assert not output_dir.exists()


def test_scheduler_recover_plan_clones_reviewed_binding_without_manual_input(
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    source_dir = tmp_path / "source-scheduler"
    source = build_scheduler_plan(
        drawing=5002,
        drawing_id=12002,
        ended_at="2030-01-03T12:00:00Z",
        bank=4980,
        output_dir=source_dir,
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
        reviewed_catalog_hash="c" * 64,
    )
    scheduler_module.prepare_scheduler_artifacts(source)
    recovery_dir = tmp_path / "recovery-scheduler"

    result = runner.invoke(
        cli.app,
        [
            "scheduler-recover-plan",
            "--source-plan",
            str(source_dir / "scheduler-plan.json"),
            "--output-dir",
            str(recovery_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    recovered = scheduler_module.load_scheduler_plan(
        recovery_dir / "scheduler-plan.json"
    )
    assert recovered.reviewed_catalog_hash == "c" * 64
    assert recovered.schedule_evidence_ledger_sha256 == (
        source.schedule_evidence_ledger_sha256
    )
    assert recovered.schedule_evidence_semantic_hash == (
        source.schedule_evidence_semantic_hash
    )
    assert recovered.requested_bank == source.requested_bank
    assert recovered.drawing_id == source.drawing_id
    assert recovered.output_dir == recovery_dir.resolve()
    assert "Recovery plan:" in result.output


def test_bound_playable_run_rejects_late_manual_final_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    output_dir = tmp_path / "late-final-scheduler"
    plan = build_scheduler_plan(
        drawing=5002,
        drawing_id=12002,
        ended_at="2030-01-03T12:00:00Z",
        bank=4980,
        output_dir=output_dir,
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )
    scheduler_module.prepare_scheduler_artifacts(plan)
    monkeypatch.setenv("API_SPORTS_KEY", SENTINEL_SECRET)
    monkeypatch.setenv("TOTO_FINAL_INPUT", str(tmp_path / "unused-final-input.json"))
    monkeypatch.setenv(
        "TOTO_SCHEDULER_PLAN",
        str(output_dir / "scheduler-plan.json"),
    )
    monkeypatch.setattr(
        cli,
        "_utc_now_datetime",
        lambda: plan.actionable_publication_deadline - timedelta(seconds=299),
    )
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: (_ for _ in ()).throw(AssertionError("network must not start")),
    )

    result = runner.invoke(
        cli.app,
        [
            "run-drawing",
            "--open",
            "--bank",
            "4980",
            "--mode",
            "playable",
        ],
    )

    assert result.exit_code == 2
    assert "insufficient final runtime budget" in result.output
    assert not (tmp_path / "unused-final-input.json").exists()


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
            "--drawing-id",
            "12002",
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
    write_empty_schedule_evidence_ledger(tmp_path)
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
            "--drawing-id",
            "12002",
            "--ended-at",
            "2030-01-03T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
            "--python-executable",
            str(executable),
        ],
    )

    assert result.exit_code != 0
    assert "current interpreter" in result.output
    assert not output_dir.exists()
