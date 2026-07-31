import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import typer
from rich import print
from rich.json import JSON
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from sqlalchemy.exc import SQLAlchemyError

from toto_ai.analytics.api_inspector import (
    DrawingReference,
    compare_raw_json_to_db_model,
    inspect_json_paths,
    resolve_drawing_reference,
    save_raw_response,
)
from toto_ai.analytics.audit import get_database_audit
from toto_ai.analytics.brief_oracle import (
    run_brief_oracle_research,
    write_brief_oracle_reports,
)
from toto_ai.analytics.budget_oracle import (
    run_budget_oracle,
    write_budget_oracle_reports,
)
from toto_ai.analytics.calibration import (
    run_calibration_study,
    write_calibration_reports,
)
from toto_ai.analytics.data_health import (
    DATA_QUALITY_EXIT_CODE,
    EXECUTION_ERROR_EXIT_CODE,
    DataHealthReport,
    audit_data_health,
    write_data_health_reports,
)
from toto_ai.analytics.data_health import (
    USE_CASES as DATA_HEALTH_USE_CASES,
)
from toto_ai.analytics.history import (
    get_crowd_accuracy,
    get_drawings_summary,
    get_event_diagnostics,
    get_outcome_distribution,
    get_value_buckets,
)
from toto_ai.analytics.research_bk_vs_norm import (
    run_bk_vs_norm_study,
    write_bk_vs_norm_report,
)
from toto_ai.analytics.validation import run_validation, write_validation_report
from toto_ai.api.client import TotoBriefClient
from toto_ai.api.detail_cache import (
    load_drawing_detail_cache,
)
from toto_ai.api.rate_limit import (
    DEFAULT_RATE_STATE_PATH,
    RequestDiagnostic,
    TotoBriefRequestCoordinator,
    TotoBriefRequestError,
)
from toto_ai.api.safe_paths import resolve_contained_path
from toto_ai.collector.sync import Collector
from toto_ai.db.session import get_session_factory, init_db, open_readonly_db
from toto_ai.ev.backtest import (
    EVBacktestConfig,
    EVBacktestResult,
    ev_backtest_checkpoint_path,
    ev_backtest_configuration_hash,
    load_frozen_holdout_ids,
    run_ev_backtest,
)
from toto_ai.ev.benchmark import benchmark_ev_engine
from toto_ai.ev.drawing import (
    EVPackageRun,
    build_open_ev_package,
    resolve_open_drawing_from_api,
)
from toto_ai.ev.models import EVConfig, PlayTimingEligibility
from toto_ai.ev.reports import write_ev_backtest_reports, write_ev_package_reports
from toto_ai.external_odds.api_sports import APISportsClient, APISportsError
from toto_ai.external_odds.audit import CoverageAudit, audit_external_coverage
from toto_ai.external_odds.collection import (
    collect_open_external_odds,
    pinned_revalidation_is_ready,
)
from toto_ai.external_odds.eligibility import DrawingEligibility, target_fingerprint
from toto_ai.external_odds.matching import load_aliases
from toto_ai.external_odds.preparation import (
    fetch_preparation_schedule,
    load_local_schedule,
    persist_drawing_identity,
    preparation_probability_sha256,
    prepare_drawing,
    refresh_ready_preparation_for_target,
)
from toto_ai.external_odds.prospective import (
    ProspectiveCollectionResult,
    collect_fresh_open_external_odds,
)
from toto_ai.external_odds.reports import write_external_coverage_reports
from toto_ai.external_odds.reviewed_schedule import (
    load_reviewed_schedule_catalog,
    revalidate_reviewed_catalog,
    reviewed_catalog_input_paths,
)
from toto_ai.external_odds.storage import load_current_drawing_eligibility
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import (
    DrawingEventPinRecord,
    load_ready_drawing_pins,
    load_ready_pin_set,
    seed_reviewed_alias_config,
)
from toto_ai.external_odds.timing_overrides import (
    PinnedTimingOverrideCatalog,
    TimingOverrideRecord,
    TimingSnapshotSummary,
    check_pinned_timing_override_catalog,
    classify_timing_snapshot,
    drawing_timing_snapshot_from_collection,
    overlay_timing_override,
    pin_timing_override_catalog,
)
from toto_ai.operations.finished_draw import (
    PostDrawRetryConfig,
    archive_package,
    import_prebet_package_manifest,
    prepare_post_draw_scheduler_artifacts,
    resolve_explicit_drawing,
    run_post_draw,
    settle_package_file,
    sync_finished_drawing,
)
from toto_ai.operations.nightly_reconciliation import (
    DEFAULT_BACKUP_RETENTION,
    DEFAULT_HOUR,
    DEFAULT_MAX_NETWORK_ATTEMPTS,
    DEFAULT_MINUTE,
    DEFAULT_RECENT_FINISHED,
    DEFAULT_TIMEOUT_SECONDS,
    NightlyReconciliationConfig,
    generate_nightly_reconciliation_artifacts,
    run_nightly_reconciliation,
)
from toto_ai.operations.reconciliation import (
    ReconciliationConfig,
    reconcile_finished_drawings,
    repair_from_canonical_raw,
)
from toto_ai.operations.sync_prepare import (
    DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS,
    synchronize_open_drawing,
)
from toto_ai.optimizer.brief import build_brief_for_drawing
from toto_ai.optimizer.brief_backtest import (
    run_brief_backtest,
    write_brief_backtest_reports,
)
from toto_ai.optimizer.cover import (
    greedy_cover,
    load_cover_package_csv,
    parse_brief,
    verify_cover_package,
    write_cover_package_csv,
)
from toto_ai.optimizer.cover_benchmark import benchmark_cover
from toto_ai.optimizer.hybrid_evaluation import (
    hybrid_evaluation_report_paths,
    run_hybrid_evaluation,
    seal_hybrid_development,
    write_hybrid_evaluation_reports,
)
from toto_ai.optimizer.strategy_backtest import (
    StrategyConfig,
    freeze_strategy_experiment_manifest,
    load_strategy_experiment_manifest,
    run_strategy_backtest,
    strategy_protocol_hash,
    verify_strategy_experiment_manifest_data,
    write_strategy_backtest_reports,
)
from toto_ai.optimizer.strategy_diagnostics import (
    run_strategy_diagnostics,
    summarize_strategy_diagnostics,
    write_strategy_diagnostics_reports,
)
from toto_ai.package.audit import (
    PackageStrategy,
    build_package_audit,
    parse_package,
)
from toto_ai.package.audit_reports import write_package_audit_reports
from toto_ai.package.backtest import run_mvp_backtest, write_backtest_reports
from toto_ai.package.mvp import generate_mvp_package
from toto_ai.path_safety import probe_writable_directory, validate_output_paths
from toto_ai.runner import (
    DEFAULT_MINIMUM_GROSS_EV,
    AppliedTimingOverrideEvent,
    CommandSchedulerPhaseRunner,
    DrawingRunnerConfig,
    DrawingRunPublication,
    MorningDispatchConfig,
    MorningExpectedIdentity,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    OfflineReplayProvenance,
    PinnedDrawing,
    RunnerTargetMismatch,
    RunnerTimingResolution,
    SchedulerError,
    SimulatedSchedulerPhaseRunner,
    TimingOverrideAudit,
    VirtualSchedulerClock,
    activate_scheduler_launch_agent,
    build_scheduler_plan,
    dispatch_morning,
    drawing_run_candidate_paths,
    execute_scheduler_plan,
    execute_scheduler_tick,
    load_scheduler_plan,
    pin_drawing,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
    publish_drawing_run_artifacts,
    run_drawing,
    run_drawing_from_final_input,
    scheduler_plan_json,
    write_drawing_run_reports,
)
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.offline_replay import (
    OfflineReplayInputs,
    OfflineScheduleProvider,
    load_offline_replay_inputs,
    resolve_offline_replay_paths,
)
from toto_ai.runner.preflight_status import build_preflight_status
from toto_ai.sports_stats.operation import (
    collect_and_store_sports_stats,
    parse_historical_as_of,
)

app = typer.Typer(help="TotoBrief API commands.")


def _validate_cached_reference(
    payload: dict[str, object],
    reference: DrawingReference,
) -> None:
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("id") != reference.drawing_id:
        raise ValueError("synchronized target cache drawing id mismatch")
    if reference.number is not None and data.get("number") != reference.number:
        raise ValueError("synchronized target cache drawing number mismatch")
    if reference.status is not None and data.get("status") != reference.status:
        raise ValueError("synchronized target cache drawing status mismatch")
    if reference.ended_at is not None and data.get("ended_at") != reference.ended_at:
        raise ValueError("synchronized target cache deadline mismatch")


@app.command()
def supported() -> None:
    """Show supported drawing names."""
    client = TotoBriefClient()
    print(client.supported_drawings())


@app.command()
def drawings(name: str = "baltbet-main", page: int = 1) -> None:
    """Show drawings for a drawing name."""
    client = TotoBriefClient()
    data = client.drawings(name=name, page=page)

    for drawing in data.get("data", []):
        print(
            drawing.get("id"),
            drawing.get("number"),
            drawing.get("status"),
            drawing.get("ended_at"),
            drawing.get("pool_sum"),
            drawing.get("jackpot"),
        )


@app.command()
def info(drawing_id: int) -> None:
    """Show details for one drawing."""
    client = TotoBriefClient()
    data = client.drawing_info(drawing_id).get("data", {})

    print(f"Drawing {data.get('number')} | {data.get('name')} | {data.get('status')}")

    for event in sorted(data.get("events", []), key=lambda item: item.get("order", 0)):
        quotes = event.get("quotes") or {}
        print(
            f"{event.get('order', 0) + 1:02d}. {event.get('name')} | "
            f"result={event.get('result')} score={event.get('score')} | "
            f"pool=({quotes.get('pool_win_1')}, "
            f"{quotes.get('pool_draw')}, {quotes.get('pool_win_2')}) | "
            f"bk=({quotes.get('bk_win_1')}, "
            f"{quotes.get('bk_draw')}, {quotes.get('bk_win_2')})"
        )


@app.command()
def collect(name: str = "baltbet-main", db: str = "data/toto.db") -> None:
    """Collect historical drawings into a SQLite database."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    collector = Collector(
        client=TotoBriefClient(),
        session_factory=session_factory,
        raw_cache_dir="data/raw",
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        result = collector.sync(name=name, progress=progress)

    print(
        f"Collected {result.drawings_saved} new drawings "
        f"from {result.drawings_seen} seen across {result.pages_fetched} pages. "
        f"Updated {result.drawings_updated} summaries; saved "
        f"{result.events_saved} events and {result.quotes_saved} quotes; "
        f"deferred {result.details_deferred} detail(s)."
    )


@app.command("sync-finished-results")
def sync_finished_results_command(
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    void_event: list[int] | None = typer.Option(  # noqa: B008
        None,
        "--void-event",
        min=1,
        max=15,
        help="Reviewed 1-based event order settled as void; repeat as needed.",
    ),
    void_source: str | None = typer.Option(
        None,
        "--void-source",
        help="HTTP(S) evidence URL required when --void-event is used.",
    ),
    db: str = typer.Option("data/toto.db", "--db"),
    raw_archive_root: str = typer.Option(
        "data/raw/archive",
        "--raw-archive-root",
    ),
) -> None:
    """Force one exact finished drawing-info snapshot by explicit identity."""
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    try:
        factory = get_session_factory(init_db(db))
        result = sync_finished_drawing(
            factory,
            TotoBriefClient(),
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            void_event_orders=tuple(void_event or ()),
            void_source=void_source,
            raw_archive_root=raw_archive_root,
        )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


@app.command("settle-drawing")
def settle_drawing_command(
    package_file: str = typer.Option(..., "--package-file"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    stake: int = typer.Option(30, "--stake", min=1),
    db: str = typer.Option("data/toto.db", "--db"),
) -> None:
    """Settle an archived/package file against the latest complete snapshot."""
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    try:
        result = settle_package_file(
            get_session_factory(init_db(db)),
            package_file,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            stake=stake,
        )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))


@app.command("reconcile-finished")
def reconcile_finished_command(
    db: str = typer.Option("data/toto.db", "--db"),
    from_drawing: int | None = typer.Option(None, "--from-drawing", min=1),
    to_drawing: int | None = typer.Option(None, "--to-drawing", min=1),
    last: int | None = typer.Option(None, "--last", min=1),
    batch_size: int | None = typer.Option(None, "--batch-size", min=1),
    max_attempts: int = typer.Option(3, "--max-attempts", min=1),
    initial_backoff_seconds: float = typer.Option(
        1.0, "--initial-backoff-seconds", min=0
    ),
    max_backoff_seconds: float = typer.Option(30.0, "--max-backoff-seconds", min=0),
    backoff_multiplier: float = typer.Option(2.0, "--backoff-multiplier", min=1),
    rate_limit_seconds: float = typer.Option(0.5, "--rate-limit-seconds", min=0),
    state_file: str = typer.Option(
        "data/reconciliation/finished-state.json",
        "--state-file",
    ),
    raw_archive_root: str = typer.Option(
        "data/raw/archive",
        "--raw-archive-root",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run/--apply",
        help="Select and report only; dry-run never performs network calls.",
    ),
    force: bool = typer.Option(
        False,
        "--force/--no-force",
        help=(
            "Explicitly bypass persisted cooldown/quarantine for this run; "
            "the default is fail-safe no force."
        ),
    ),
) -> None:
    """Reconcile incomplete finished drawings; never generates or places bets."""
    engine = None
    try:
        engine = open_readonly_db(db) if dry_run else init_db(db)
        report = reconcile_finished_drawings(
            get_session_factory(engine),
            TotoBriefClient(),
            archive_root=raw_archive_root,
            state_path=state_file,
            config=ReconciliationConfig(
                max_attempts=max_attempts,
                initial_backoff_seconds=initial_backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
                backoff_multiplier=backoff_multiplier,
                rate_limit_seconds=rate_limit_seconds,
                batch_size=batch_size,
                dry_run=dry_run,
            ),
            from_drawing=from_drawing,
            to_drawing=to_drawing,
            last=last,
            force=force,
        )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    finally:
        if engine is not None:
            engine.dispose()
    typer.echo(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    if not dry_run and (
        report.source_incomplete
        or report.transient_error
        or any(item.status == "quarantined" for item in report.items)
    ):
        raise typer.Exit(code=2)


@app.command("repair-canonical-raw")
def repair_canonical_raw_command(
    drawing_number: list[int] = typer.Option(  # noqa: B008
        ...,
        "--drawing-number",
        min=1,
        help="Exact visible number; repeat for each drawing.",
    ),
    db: str = typer.Option("data/toto.db", "--db"),
    raw_cache_root: str = typer.Option("data/raw", "--raw-cache-root"),
    raw_archive_root: str = typer.Option(
        "data/raw/archive",
        "--raw-archive-root",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help="Dry-run is default and never mutates SQLite.",
    ),
) -> None:
    """Repair only losses proven by validated canonical local RAW."""
    engine = None
    try:
        engine = open_readonly_db(db) if dry_run else init_db(db)
        report = repair_from_canonical_raw(
            get_session_factory(engine),
            raw_cache_root=raw_cache_root,
            archive_root=raw_archive_root,
            drawing_numbers=tuple(drawing_number),
            dry_run=dry_run,
        )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    finally:
        if engine is not None:
            engine.dispose()
    typer.echo(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    if report.invalid:
        raise typer.Exit(code=2)


@app.command("nightly-reconciliation-run")
def nightly_reconciliation_run_command(
    db: str = typer.Option("data/toto.db", "--db"),
    project_root: str = typer.Option(".", "--project-root"),
    last_finished: int = typer.Option(
        DEFAULT_RECENT_FINISHED,
        "--last-finished",
        min=1,
    ),
    max_network_attempts: int = typer.Option(
        DEFAULT_MAX_NETWORK_ATTEMPTS,
        "--max-network-attempts",
        min=1,
    ),
    timeout_seconds: float = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout-seconds",
        min=1,
    ),
    request_timeout_seconds: int = typer.Option(
        20,
        "--request-timeout-seconds",
        min=1,
    ),
    backup_retention: int = typer.Option(
        DEFAULT_BACKUP_RETENTION,
        "--backup-retention",
        min=1,
    ),
    state_root: str = typer.Option(
        "data/nightly-reconciliation",
        "--state-root",
    ),
    raw_archive_root: str = typer.Option(
        "data/raw/archive",
        "--raw-archive-root",
    ),
    backup_root: str = typer.Option("data/backups", "--backup-root"),
    request_state_file: str = typer.Option(
        DEFAULT_RATE_STATE_PATH,
        "--request-state-file",
    ),
    force: bool = typer.Option(
        False,
        "--force/--no-force",
        hidden=True,
        help="Operator-only override; generated nightly artifacts always use no-force.",
    ),
) -> None:
    """Run bounded results-only reconciliation; never creates betting artifacts."""
    root = Path(project_root).resolve()
    try:
        config = NightlyReconciliationConfig(
            project_root=root,
            db_path=Path(db),
            state_root=Path(state_root),
            raw_archive_root=Path(raw_archive_root),
            backup_root=Path(backup_root),
            recent_finished=last_finished,
            max_network_attempts=max_network_attempts,
            timeout_seconds=timeout_seconds,
            backup_retention=backup_retention,
        )
        result = run_nightly_reconciliation(
            config,
            client=TotoBriefClient(
                timeout=min(request_timeout_seconds, int(timeout_seconds)),
                max_retries=0,
                rate_state_path=request_state_file,
                rate_state_root=root,
            ),
            force_for_test=force,
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)
    )
    if result.classification == "FAILED":
        raise typer.Exit(code=1)
    if result.classification == "PARTIAL":
        raise typer.Exit(code=2)


@app.command("nightly-reconciliation-plan")
def nightly_reconciliation_plan_command(
    output_dir: str = typer.Option(
        "reports/nightly-reconciliation",
        "--output-dir",
    ),
    project_root: str = typer.Option(".", "--project-root"),
    db: str = typer.Option("data/toto.db", "--db"),
    hour: int = typer.Option(DEFAULT_HOUR, "--hour", min=0, max=23),
    minute: int = typer.Option(DEFAULT_MINUTE, "--minute", min=0, max=59),
    last_finished: int = typer.Option(
        DEFAULT_RECENT_FINISHED,
        "--last-finished",
        min=1,
    ),
    max_network_attempts: int = typer.Option(
        DEFAULT_MAX_NETWORK_ATTEMPTS,
        "--max-network-attempts",
        min=1,
    ),
    timeout_seconds: float = typer.Option(
        DEFAULT_TIMEOUT_SECONDS,
        "--timeout-seconds",
        min=1,
    ),
    backup_retention: int = typer.Option(
        DEFAULT_BACKUP_RETENTION,
        "--backup-retention",
        min=1,
    ),
    python_executable: str | None = typer.Option(
        None,
        "--python-executable",
    ),
) -> None:
    """Generate passive nightly wrapper/plist artifacts without installing them."""
    root = Path(project_root).resolve()
    try:
        artifacts = generate_nightly_reconciliation_artifacts(
            project_root=root,
            output_dir=output_dir,
            db_path=db,
            python_executable=python_executable,
            hour=hour,
            minute=minute,
            recent_finished=last_finished,
            max_network_attempts=max_network_attempts,
            timeout_seconds=timeout_seconds,
            backup_retention=backup_retention,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Wrapper: {artifacts.wrapper_path}")
    typer.echo(f"LaunchAgent candidate: {artifacts.launch_agent_path}")
    typer.echo("Generated only; nothing was installed or launched.")


@app.command("archive-package")
def archive_package_command(
    package_file: str = typer.Option(..., "--package-file"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    stake: int = typer.Option(30, "--stake", min=1),
    pre_bet_manifest: str | None = typer.Option(
        None,
        "--pre-bet-manifest",
        help="Verified scheduler package-archive manifest for pre-bet provenance.",
    ),
    db: str = typer.Option("data/toto.db", "--db"),
) -> None:
    """Explicitly import auditable legacy package evidence."""
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    try:
        factory = get_session_factory(init_db(db))
        resolved_id, resolved_number = resolve_explicit_drawing(
            factory,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
        )
        if pre_bet_manifest is None:
            result = archive_package(
                factory,
                package_file,
                drawing_id=resolved_id,
                drawing_number=resolved_number,
                stake=stake,
                provenance="legacy_import",
            )
        else:
            result = import_prebet_package_manifest(
                factory,
                pre_bet_manifest,
                package_file,
            )
            if (
                result.drawing_id != resolved_id
                or result.drawing_number != resolved_number
                or result.stake != stake
            ):
                raise ValueError(
                    "pre-bet manifest does not match requested identity/stake"
                )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))


@app.command("post-draw-run")
def post_draw_run_command(
    package_file: str = typer.Option(..., "--package-file"),
    state_file: str = typer.Option(..., "--state-file"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    stake: int = typer.Option(30, "--stake", min=1),
    db: str = typer.Option("data/toto.db", "--db"),
    raw_archive_root: str = typer.Option(
        "data/raw/archive",
        "--raw-archive-root",
    ),
    max_attempts: int = typer.Option(6, "--max-attempts", min=1),
    initial_delay_seconds: float = typer.Option(
        60.0,
        "--initial-delay-seconds",
        min=0,
    ),
    max_delay_seconds: float = typer.Option(
        900.0,
        "--max-delay-seconds",
        min=0,
    ),
    backoff_multiplier: float = typer.Option(
        2.0,
        "--backoff-multiplier",
        min=1,
    ),
) -> None:
    """Boundedly poll and settle one explicit ended drawing; never places bets."""
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    try:
        state = run_post_draw(
            get_session_factory(init_db(db)),
            TotoBriefClient(),
            package_file=package_file,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            stake=stake,
            config=PostDrawRetryConfig(
                max_attempts=max_attempts,
                initial_delay_seconds=initial_delay_seconds,
                max_delay_seconds=max_delay_seconds,
                backoff_multiplier=backoff_multiplier,
            ),
            state_path=state_file,
            raw_archive_root=raw_archive_root,
        )
    except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True))
    if state.status != "complete":
        raise typer.Exit(code=2 if state.status == "pending" else 1)


@app.command("post-draw-plan")
def post_draw_plan_command(
    package_file: str = typer.Option(..., "--package-file"),
    ended_at: str = typer.Option(..., "--ended-at"),
    state_file: str = typer.Option(..., "--state-file"),
    output_dir: str = typer.Option(..., "--output-dir"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    stake: int = typer.Option(30, "--stake", min=1),
    db: str = typer.Option("data/toto.db", "--db"),
    project_root: str | None = typer.Option(None, "--project-root"),
    python_executable: str = typer.Option(
        sys.executable,
        "--python-executable",
    ),
    max_attempts: int = typer.Option(6, "--max-attempts", min=1),
    initial_delay_seconds: float = typer.Option(
        60.0,
        "--initial-delay-seconds",
        min=0,
    ),
    max_delay_seconds: float = typer.Option(
        900.0,
        "--max-delay-seconds",
        min=0,
    ),
) -> None:
    """Generate uninstalled non-betting post-draw launchd artifacts."""
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    try:
        plan, wrapper, plist = prepare_post_draw_scheduler_artifacts(
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            ended_at=ended_at,
            package_file=package_file,
            stake=stake,
            db=db,
            state_file=state_file,
            output_dir=output_dir,
            project_root=project_root or Path.cwd(),
            python_executable=python_executable,
            max_attempts=max_attempts,
            initial_delay_seconds=initial_delay_seconds,
            max_delay_seconds=max_delay_seconds,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    print(f"Plan: {plan}")
    print(f"Wrapper: {wrapper}")
    print(f"LaunchAgent candidate: {plist}")
    print("Artifacts were generated only; nothing was installed and no bet is placed.")


@app.command()
def research(db: str = "data/toto.db") -> None:
    """Show research analytics for a collected SQLite database."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        summary = get_drawings_summary(session)
        outcome_distribution = get_outcome_distribution(session)
        crowd_accuracy = get_crowd_accuracy(session)
        value_buckets = get_value_buckets(session)

    print(_summary_table(summary))
    print(_outcome_table(outcome_distribution))
    print(_accuracy_table(crowd_accuracy))
    print(_value_buckets_table(value_buckets))


@app.command()
def inspect_events(db: str = "data/toto.db", limit: int = 20) -> None:
    """Inspect event-level result and quote diagnostics."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        rows = get_event_diagnostics(session, limit=limit)

    print(_event_diagnostics_table(rows))


@app.command()
def audit(db: str = "data/toto.db") -> None:
    """Audit completeness and quality of a collected SQLite database."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        audit_result = get_database_audit(session)

    print(_drawings_audit_table(audit_result["drawings"]))
    print(_dimension_table("Sports", "Sport", audit_result["sports"]))
    print(
        _dimension_table(
            "Top Championships",
            "Championship",
            audit_result["championships"],
        )
    )
    print(_dimension_table("Result Values", "Result", audit_result["result_values"]))
    print(_score_audit_table(audit_result["score"]))
    print(_quote_completeness_table(audit_result["quote_completeness"]))
    print(_probability_validation_table(audit_result["probability_validation"]))
    print(_duplicates_table(audit_result["duplicates"]))
    print(_quality_score_table(audit_result["quality_score"]))


@app.command("data-health")
def data_health_command(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    use_case: str = typer.Option(
        "historical_inventory",
        "--use-case",
        help=(
            "Strict health use case: historical_inventory, "
            "backtest_probability, result_settlement, or "
            "prospective_generation."
        ),
    ),
    from_drawing: int | None = typer.Option(
        None,
        "--from-drawing",
        min=1,
    ),
    to_drawing: int | None = typer.Option(
        None,
        "--to-drawing",
        min=1,
    ),
    last: int | None = typer.Option(None, "--last", min=1),
    output_dir: str = typer.Option(
        "reports/data-health",
        "--output-dir",
    ),
    strict: bool = typer.Option(True, "--strict/--no-strict"),
) -> None:
    """Evaluate the versioned read-only drawing data-health contract."""
    if use_case not in DATA_HEALTH_USE_CASES:
        raise typer.BadParameter(
            "--use-case must be one of: " + ", ".join(DATA_HEALTH_USE_CASES)
        )
    if last is not None and (from_drawing is not None or to_drawing is not None):
        raise typer.BadParameter(
            "--last cannot be combined with --from-drawing or --to-drawing"
        )
    if (
        from_drawing is not None
        and to_drawing is not None
        and from_drawing > to_drawing
    ):
        raise typer.BadParameter("--from-drawing cannot be greater than --to-drawing")
    try:
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            report = audit_data_health(
                session,
                db_path=db,
                use_case=use_case,
                from_drawing=from_drawing,
                to_drawing=to_drawing,
                last=last,
                strict=strict,
            )
        paths = write_data_health_reports(report, output_dir)
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        typer.echo(f"data-health execution error: {error}", err=True)
        raise typer.Exit(EXECUTION_ERROR_EXIT_CODE) from error

    print(_data_health_summary_table(report))
    print("Reports written to " + ", ".join(str(path) for path in paths))
    if strict and not report.summary.passed:
        raise typer.Exit(DATA_QUALITY_EXIT_CODE)


@app.command()
def inspect_api(
    drawing_id: int | None = typer.Option(
        None,
        help="Internal TotoBrief API drawing id for debugging.",
    ),
    number: int | None = typer.Option(
        None,
        help="Public drawing number to resolve from the local database.",
    ),
    latest_finished: bool = typer.Option(
        False,
        help="Inspect latest finished baltbet-main drawing from the local database.",
    ),
    live: bool = typer.Option(
        False,
        help="Inspect active/expected drawing whose ended_at is in the past.",
    ),
    open: bool = typer.Option(
        False,
        help="Inspect next playable active/expected drawing ending in the future.",
    ),
    db: str = typer.Option(
        "data/toto.db",
        help="SQLite database used for drawing resolution.",
    ),
    pretty: bool = typer.Option(False, help="Print formatted raw JSON."),
    diff_db: bool = typer.Option(False, help="Compare raw JSON paths with DB fields."),
) -> None:
    """Fetch and inspect raw TotoBrief drawing-info JSON."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        try:
            reference = resolve_drawing_reference(
                session,
                drawing_id=drawing_id,
                number=number,
                latest_finished=latest_finished,
                live=live,
                open=open,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    payload = TotoBriefClient().drawing_info(reference.drawing_id)
    output_path = save_raw_response(payload, drawing_id=reference.drawing_id)

    print(_drawing_reference_table(reference))
    print(f"Saved raw response to {output_path}")
    if pretty:
        print(JSON.from_data(payload))

    print(_api_paths_table(inspect_json_paths(payload)))
    if diff_db:
        print(_api_db_diff_table(compare_raw_json_to_db_model(payload)))


@app.command()
def predict(
    open: bool = typer.Option(
        False,
        help="Resolve next playable baltbet-main drawing for future prediction.",
    ),
    db: str = "data/toto.db",
) -> None:
    """Placeholder for the future prediction engine."""
    if not open:
        raise typer.BadParameter("Only --open is supported for now.")

    engine = init_db(db)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        try:
            reference = resolve_drawing_reference(session, open=True)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    print(_drawing_reference_table(reference))
    print("Prediction engine placeholder. No predictions are generated yet.")


@app.command()
def validate(
    number: int = typer.Option(..., help="Public drawing number to validate."),
    db: str = "data/toto.db",
) -> None:
    """Validate raw API data, SQLite data, and analytics for a drawing number."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        try:
            reference = resolve_drawing_reference(session, number=number)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        payload = TotoBriefClient().drawing_info(reference.drawing_id)
        result = run_validation(session, payload, number=number)

    report_path = write_validation_report(result)
    print(f"Validation: {result['overall_status']}")
    print(_validation_checks_table(result))
    print(_validation_quote_totals_table(result["quote_totals"]))
    print(f"Report written to {report_path}")


@app.command()
def study_bk(db: str = "data/toto.db") -> None:
    """Study whether BK probabilities are derived from normalized odds."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        result = run_bk_vs_norm_study(session)

    report_path = write_bk_vs_norm_report(result)
    print(_bk_vs_norm_metrics_table(result))
    print(_bk_vs_norm_examples_table(result["examples"]))
    print(result["conclusion"])
    print(f"Report written to {report_path}")


@app.command()
def calibration(db: str = "data/toto.db") -> None:
    """Measure bookmaker and pool probability calibration."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        result = run_calibration_study(session)

    markdown_path, calibration_csv, reliability_csv = write_calibration_reports(result)
    print(_calibration_overall_table(result["overall"]))
    print(_calibration_slices_table(result))
    print(_reliability_table(result["bookmaker_bins"]))
    print(
        f"Reports written to {markdown_path}, {calibration_csv}, and {reliability_csv}"
    )


@app.command()
def brief_oracle(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(500, help="Number of latest complete drawings to test."),
) -> None:
    """Find minimum oracle briefs that contain actual results."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        try:
            result = run_brief_oracle_research(session, last=last)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    csv_path, markdown_path, event_csv_path = write_brief_oracle_reports(result)
    print(_brief_oracle_summary_table(result.summary))
    print(_brief_oracle_rank_table(result.summary["bk_rank_frequency"]))
    print(_brief_oracle_entropy_table(result.summary["entropy_by_cover_size"]))
    print(f"Reports written to {csv_path}, {markdown_path}, and {event_csv_path}")


@app.command()
def budget_oracle(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(500, help="Number of latest complete drawings to test."),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    timeout_per_drawing: float = typer.Option(
        30,
        help="Timeout guard per drawing in seconds.",
    ),
    max_candidates: int | None = typer.Option(
        None,
        help="Optional candidate limit. Omitted means full search.",
    ),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Show live Rich progress.",
    ),
    profile_workload: bool = typer.Option(
        False,
        "--profile-workload",
        help="Print Budget Oracle candidate workload diagnostics.",
    ),
) -> None:
    """Run a budget-constrained oracle benchmark against baseline briefs."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    partial_csv_path = f"reports/budget_oracle_last_{last}.csv"

    if progress:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as rich_progress:
            task_id = rich_progress.add_task("Preparing budget oracle")

            def update_progress(update: dict[str, object]) -> None:
                rich_progress.update(
                    task_id,
                    description=_budget_oracle_progress_description(update),
                )

            with session_factory() as session:
                try:
                    result = run_budget_oracle(
                        session,
                        last=last,
                        bank=bank,
                        stake=stake,
                        category=category,
                        timeout_per_drawing=timeout_per_drawing,
                        max_candidates=max_candidates,
                        progress_callback=update_progress,
                        partial_csv_path=partial_csv_path,
                        profile_workload=profile_workload,
                    )
                except ValueError as error:
                    raise typer.BadParameter(str(error)) from error
            rich_progress.update(task_id, description="Budget oracle complete")
    else:
        with session_factory() as session:
            try:
                result = run_budget_oracle(
                    session,
                    last=last,
                    bank=bank,
                    stake=stake,
                    category=category,
                    timeout_per_drawing=timeout_per_drawing,
                    max_candidates=max_candidates,
                    partial_csv_path=partial_csv_path,
                    profile_workload=profile_workload,
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error

    csv_path, markdown_path = write_budget_oracle_reports(result, last=last)
    print(_budget_oracle_summary_table(result.summary))
    print(_budget_oracle_timing_table(result.summary))
    if profile_workload:
        print(_budget_oracle_workload_table(result.summary))
        print(_budget_oracle_slowest_candidates_table(result.summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command()
def package_mvp(
    brief: str = typer.Option(
        ...,
        help="15-position brief, comma-separated for doubles/triples.",
    ),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
) -> None:
    """Generate an MVP covering approximation package."""
    try:
        result = generate_mvp_package(
            brief=brief,
            bank=bank,
            stake=stake,
            category=category,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    print(result.label)
    print("Not an official TotoBrief guarantee.")
    print(_package_mvp_summary_table(result))
    print(_package_mvp_coupons_table(result.selected_coupons))


@app.command()
def cover(
    brief: str = typer.Option(
        ...,
        help="Comma-separated brief positions, using 1, X, and 2.",
    ),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
) -> None:
    """Generate a greedy covering package from a brief."""
    if bank <= 0:
        raise typer.BadParameter("Bank must be a positive integer.")
    if stake <= 0:
        raise typer.BadParameter("Stake must be a positive integer.")

    try:
        result = greedy_cover(
            brief=parse_brief(brief),
            category=category,
            max_coupons=bank // stake,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    report_path = write_cover_package_csv(result["selected_coupons"])
    print(_cover_summary_table(result, stake=stake))
    print(_cover_coupons_table(result["selected_coupons"][:20]))
    print(f"Report written to {report_path}")


@app.command("package-audit")
def package_audit_command(
    package_path: Path = typer.Option(  # noqa: B008
        ...,
        "--package",
        exists=True,
        dir_okay=False,
        readable=True,
        help="CSV or line-oriented file containing full 15-outcome coupons.",
    ),
    strategy: PackageStrategy = typer.Option(  # noqa: B008
        ...,
        help="Package strategy: cover, ev, or hybrid.",
    ),
    bank: int = typer.Option(..., help="Requested bank; a positive stake multiple."),
    stake: int = typer.Option(30, help="Positive coupon stake."),
    effective_bank: int | None = typer.Option(
        None,
        help="Optional effective bank cap; defaults to requested bank.",
    ),
    drawing_id: int | None = typer.Option(None, help="Optional drawing identifier."),
    open_drawing: bool = typer.Option(
        False,
        "--open",
        help="Resolve the current open drawing from TotoBrief page one.",
    ),
    target_category: int | None = typer.Option(
        None,
        help="Declared Cover target category: 13, 14, or 15.",
    ),
    probabilities_path: Path | None = typer.Option(  # noqa: B008
        None,
        "--probabilities",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional JSON array of 15 normalized 1/X/2 triplets.",
    ),
    report_dir: Path = typer.Option(  # noqa: B008
        Path("reports"),
        help="Directory for deterministic JSON, CSV, and Markdown reports.",
    ),
    max_distance_comparisons: int = typer.Option(
        10_000_000,
        help="Fail-closed limit for exact variant*coupon comparisons.",
    ),
) -> None:
    """Audit any EV, Cover, or Hybrid package without changing its coupons."""
    if open_drawing and drawing_id is not None:
        raise typer.BadParameter("Use either --drawing-id or --open, not both.")
    try:
        resolved_drawing_id = drawing_id
        if open_drawing:
            resolved_drawing_id = resolve_open_drawing_from_api(
                TotoBriefClient()
            ).drawing_id
        probabilities = None
        if probabilities_path is not None:
            loaded = json.loads(probabilities_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded = loaded.get("probabilities")
            if not isinstance(loaded, list):
                raise ValueError("Probability JSON must be an array of triplets.")
            probabilities = loaded
        effective_value = bank if effective_bank is None else effective_bank
        if stake <= 0 or effective_value <= 0:
            raise ValueError("Stake and effective bank must be positive.")
        audit = build_package_audit(
            parse_package(
                package_path,
                max_coupons=effective_value // stake,
            ),
            strategy=strategy,
            requested_bank=bank,
            effective_bank=effective_bank,
            stake=stake,
            drawing_id=resolved_drawing_id,
            target_category=target_category,
            probabilities=probabilities,
            max_distance_comparisons=max_distance_comparisons,
        )
        paths = write_package_audit_reports(audit, report_dir)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(
        json.dumps(
            {
                "schema_version": audit.schema_version,
                "strategy": audit.strategy,
                "package_sha256": audit.package_sha256,
                "audit_sha256": audit.audit_sha256,
                "coupon_count": audit.bank.coupon_count,
                "requested_bank": audit.bank.requested,
                "effective_bank": audit.bank.effective,
                "used_bank": audit.bank.used,
                "union_brief_variant_count": audit.union_brief_variant_count,
                "worst_minimum_distance": audit.worst_minimum_distance,
                "guaranteed_category": audit.guaranteed_category,
                "warnings": list(audit.warnings),
                "reports": [str(path) for path in paths],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command("benchmark-cover")
def benchmark_cover_command(
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    max_coupons: int = typer.Option(333, help="Maximum coupons for the benchmark."),
    profile: bool = typer.Option(True, help="Print cProfile top functions."),
) -> None:
    """Benchmark Cover Engine on a representative brief."""
    try:
        result = benchmark_cover(
            category=category,
            max_coupons=max_coupons,
            profile=profile,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    print(_cover_benchmark_table(result))
    if result["profile"]:
        print(result["profile"])


@app.command("benchmark-ev")
def benchmark_ev_command(
    events: int = typer.Option(15, min=1, max=15),
    samples: int = typer.Option(20, min=1),
) -> None:
    """Benchmark and verify the exact full-space expected-value engine."""
    try:
        result = benchmark_ev_engine(event_count=events, sample_count=samples)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    print(_ev_benchmark_table(result))


def _build_timing_eligibility_resolver(
    db: str,
) -> Callable[[Mapping[str, object]], PlayTimingEligibility]:
    session_factory = None
    database_available = True
    try:
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
    except (OSError, SQLAlchemyError, ValueError):
        database_available = False

    def resolve(payload: Mapping[str, object]) -> PlayTimingEligibility:
        try:
            target = parse_target_drawing(
                payload,
                fetched_at=datetime.now(timezone.utc),
            )
            fingerprint = target_fingerprint(
                target.drawing_id,
                target.drawing_number,
                target.deadline,
                target.events,
            )
        except Exception:
            return PlayTimingEligibility(
                status="absent",
                reason="fresh timing target could not be parsed or fingerprinted",
                target_fingerprint=None,
                fingerprint_match=False,
            )
        if not database_available or session_factory is None:
            return PlayTimingEligibility(
                status="absent",
                reason="timing eligibility database is missing or unreadable",
                target_fingerprint=fingerprint,
                fingerprint_match=False,
            )
        try:
            eligibility = load_current_drawing_eligibility(
                session_factory,
                target.drawing_id,
                fingerprint,
            )
        except (OSError, SQLAlchemyError, ValueError):
            return PlayTimingEligibility(
                status="absent",
                reason="timing eligibility database is missing or unreadable",
                target_fingerprint=fingerprint,
                fingerprint_match=False,
            )
        if eligibility is None:
            return PlayTimingEligibility(
                status="absent",
                reason=(
                    "no complete stored eligibility matches the fresh target "
                    "fingerprint"
                ),
                target_fingerprint=fingerprint,
                fingerprint_match=False,
            )

        return _play_timing_from_eligibility(eligibility, fingerprint)

    return resolve


def _play_timing_from_eligibility(
    eligibility: DrawingEligibility,
    fingerprint: str,
) -> PlayTimingEligibility:
    """Convert the stored exact eligibility verdict into the EV timing contract."""
    if eligibility.status == "playable":
        reason = "all 15 effective event starts fit within two Moscow calendar days"
    elif eligibility.status == "multi_day":
        reason = (
            f"effective event starts span {eligibility.span_days} Moscow calendar days"
        )
    else:
        missing = ",".join(str(order) for order in eligibility.missing_event_orders)
        reason = f"effective event timing is unresolved for event orders {missing}"
    return PlayTimingEligibility(
        status=eligibility.status,
        reason=reason,
        target_fingerprint=fingerprint,
        fingerprint_match=True,
    )


def _build_runner_timing_resolver(
    db: str,
) -> Callable[[PinnedDrawing], PlayTimingEligibility]:
    """Resolve only the stored verdict matching the runner's pinned target."""
    engine = open_readonly_db(db)
    session_factory = get_session_factory(engine)

    def resolve(pinned: PinnedDrawing) -> PlayTimingEligibility:
        eligibility = load_current_drawing_eligibility(
            session_factory,
            pinned.target.drawing_id,
            pinned.fingerprint,
        )
        if eligibility is None:
            return PlayTimingEligibility(
                status="absent",
                reason=(
                    "no complete stored eligibility matches the pinned target "
                    "fingerprint"
                ),
                target_fingerprint=pinned.fingerprint,
                fingerprint_match=False,
            )
        return _play_timing_from_eligibility(eligibility, pinned.fingerprint)

    return resolve


def _resolve_runner_timing_override(
    pinned: PinnedDrawing,
    collection: ProspectiveCollectionResult,
    raw: PlayTimingEligibility,
    catalog_pin: PinnedTimingOverrideCatalog,
) -> RunnerTimingResolution:
    """Apply one strict, immutable timing overlay to the collected snapshot."""

    if not isinstance(pinned, PinnedDrawing):
        raise ValueError("pinned must be a PinnedDrawing")
    if not isinstance(collection, ProspectiveCollectionResult):
        raise ValueError("collection must be a ProspectiveCollectionResult")
    if not isinstance(raw, PlayTimingEligibility):
        raise ValueError("raw must be a PlayTimingEligibility")
    if not isinstance(catalog_pin, PinnedTimingOverrideCatalog):
        raise ValueError("catalog_pin must be a PinnedTimingOverrideCatalog")

    raw_snapshot = drawing_timing_snapshot_from_collection(collection.snapshot)
    if (
        raw_snapshot.drawing_id != pinned.target.drawing_id
        or raw_snapshot.drawing_number != pinned.target.drawing_number
        or raw_snapshot.target_fingerprint != pinned.fingerprint
    ):
        raise ValueError("raw collection timing does not match the pinned target")
    raw_summary = classify_timing_snapshot(raw_snapshot)
    raw_exact = (
        raw.status in {"playable", "multi_day", "unknown"}
        and raw.fingerprint_match
        and raw.target_fingerprint == pinned.fingerprint
        and raw.status == raw_summary.status
    )
    if not raw_exact:
        return _unusable_runner_timing_override(
            raw=raw,
            pinned=pinned,
            status="not_applied",
            catalog_pin=catalog_pin,
            timing_catalog_sha256=None,
            diagnostics=(
                "raw stored timing is not an exact match for the collected snapshot",
            ),
        )

    if not catalog_pin.valid:
        return _unusable_runner_timing_override(
            raw=raw,
            pinned=pinned,
            status="invalid_catalog",
            catalog_pin=catalog_pin,
            timing_catalog_sha256=None,
            diagnostics=(catalog_pin.validation_error or "invalid catalog",),
        )

    catalog_check = check_pinned_timing_override_catalog(catalog_pin)
    if not catalog_check.matches_preflight or catalog_check.catalog is None:
        diagnostics = (
            catalog_check.validation_error
            or "catalog semantic hash changed after preflight",
        )
        return _unusable_runner_timing_override(
            raw=raw,
            pinned=pinned,
            status="catalog_changed",
            catalog_pin=catalog_pin,
            timing_catalog_sha256=catalog_check.observed_sha256,
            diagnostics=diagnostics,
        )

    overlay = overlay_timing_override(raw_snapshot, catalog_check.catalog)
    record = _override_record_for_overlay(catalog_check.catalog.records, overlay)
    diagnostics = tuple(f"{item.code}: {item.message}" for item in overlay.diagnostics)
    if not overlay.complete_overlay or record is None:
        return RunnerTimingResolution(
            raw=raw,
            effective=_unknown_override_eligibility(
                pinned,
                "timing override did not produce one complete exact overlay",
            ),
            override=_timing_override_audit(
                status="not_applied",
                catalog_pin=catalog_pin,
                timing_catalog_sha256=catalog_check.observed_sha256,
                package_catalog_sha256=None,
                record=record,
                overlay_complete=overlay.complete_overlay,
                applied_event_orders=overlay.applied_event_orders,
                preserved_event_orders=overlay.preserved_event_orders,
                diagnostics=diagnostics or ("override was not applied",),
                overlay_summary=None,
            ),
        )

    overlay_summary = classify_timing_snapshot(overlay.snapshot)
    effective = _play_timing_from_summary(
        overlay_summary,
        pinned.fingerprint,
    )
    return RunnerTimingResolution(
        raw=raw,
        effective=effective,
        override=_timing_override_audit(
            status="applied",
            catalog_pin=catalog_pin,
            timing_catalog_sha256=catalog_check.observed_sha256,
            package_catalog_sha256=None,
            record=record,
            overlay_complete=True,
            applied_event_orders=overlay.applied_event_orders,
            preserved_event_orders=overlay.preserved_event_orders,
            diagnostics=diagnostics,
            overlay_summary=overlay_summary,
        ),
    )


def _verify_runner_timing_override(
    resolution: RunnerTimingResolution,
    catalog_pin: PinnedTimingOverrideCatalog,
) -> RunnerTimingResolution:
    """Bind package generation to the same strict semantic catalog hash."""

    if not isinstance(resolution, RunnerTimingResolution):
        raise ValueError("resolution must be a RunnerTimingResolution")
    audit = resolution.override
    if audit is None or audit.status != "applied":
        return resolution
    catalog_check = check_pinned_timing_override_catalog(catalog_pin)
    if (
        catalog_check.catalog is None
        or not catalog_check.matches_preflight
        or catalog_check.observed_sha256 != audit.preflight_catalog_sha256
    ):
        diagnostic = (
            catalog_check.validation_error
            or "catalog semantic hash changed before package generation"
        )
        return RunnerTimingResolution(
            raw=resolution.raw,
            effective=PlayTimingEligibility(
                status="unknown",
                reason="timing override catalog changed before package generation",
                target_fingerprint=resolution.effective.target_fingerprint,
                fingerprint_match=True,
            ),
            override=replace(
                audit,
                status="catalog_changed",
                package_catalog_sha256=None,
                diagnostics=(*audit.diagnostics, diagnostic),
            ),
        )
    return RunnerTimingResolution(
        raw=resolution.raw,
        effective=resolution.effective,
        override=replace(
            audit,
            package_catalog_sha256=catalog_check.observed_sha256,
        ),
    )


def _unusable_runner_timing_override(
    *,
    raw: PlayTimingEligibility,
    pinned: PinnedDrawing,
    status: str,
    catalog_pin: PinnedTimingOverrideCatalog,
    timing_catalog_sha256: str | None,
    diagnostics: tuple[str, ...],
) -> RunnerTimingResolution:
    return RunnerTimingResolution(
        raw=raw,
        effective=_unknown_override_eligibility(
            pinned,
            "timing override is unavailable or does not exactly match the target",
        ),
        override=_timing_override_audit(
            status=status,
            catalog_pin=catalog_pin,
            timing_catalog_sha256=timing_catalog_sha256,
            package_catalog_sha256=None,
            record=None,
            overlay_complete=False,
            applied_event_orders=(),
            preserved_event_orders=(),
            diagnostics=diagnostics,
            overlay_summary=None,
        ),
    )


def _timing_override_audit(
    *,
    status: str,
    catalog_pin: PinnedTimingOverrideCatalog,
    timing_catalog_sha256: str | None,
    package_catalog_sha256: str | None,
    record: TimingOverrideRecord | None,
    overlay_complete: bool,
    applied_event_orders: tuple[int, ...],
    preserved_event_orders: tuple[int, ...],
    diagnostics: tuple[str, ...],
    overlay_summary: TimingSnapshotSummary | None,
) -> TimingOverrideAudit:
    record_events = (
        {} if record is None else {event.event_order: event for event in record.events}
    )
    applied_events = tuple(
        AppliedTimingOverrideEvent(
            event_order=order,
            event_id=record_events[order].event_id,
            starts_at=record_events[order].starts_at,
            source_ref=record_events[order].source_ref or record.source_ref,
        )
        for order in applied_event_orders
    )
    return TimingOverrideAudit(
        status=status,  # type: ignore[arg-type]
        preflight_catalog_sha256=catalog_pin.catalog_sha256,
        timing_catalog_sha256=timing_catalog_sha256,
        package_catalog_sha256=package_catalog_sha256,
        override_id=None if record is None else record.override_id,
        reviewer=None if record is None else record.reviewer,
        reviewed_at=None if record is None else record.reviewed_at,
        source_ref=None if record is None else record.source_ref,
        overlay_complete=overlay_complete,
        applied_events=applied_events,
        preserved_event_orders=preserved_event_orders,
        diagnostics=diagnostics,
        overlay_summary=overlay_summary,
    )


def _override_record_for_overlay(
    records: tuple[TimingOverrideRecord, ...],
    overlay: object,
) -> TimingOverrideRecord | None:
    override_id = getattr(overlay, "override_id", None)
    if override_id is None:
        diagnostic_ids = {
            item.override_id
            for item in getattr(overlay, "diagnostics", ())
            if item.override_id is not None
        }
        if len(diagnostic_ids) == 1:
            override_id = diagnostic_ids.pop()
    matches = tuple(record for record in records if record.override_id == override_id)
    return matches[0] if len(matches) == 1 else None


def _unknown_override_eligibility(
    pinned: PinnedDrawing,
    reason: str,
) -> PlayTimingEligibility:
    return PlayTimingEligibility(
        status="unknown",
        reason=reason,
        target_fingerprint=pinned.fingerprint,
        fingerprint_match=True,
    )


def _play_timing_from_summary(
    summary: TimingSnapshotSummary,
    fingerprint: str,
) -> PlayTimingEligibility:
    if summary.status == "playable":
        reason = (
            "complete reviewed timing overlay resolves all 15 event starts "
            f"within {summary.span_days} Moscow calendar date"
        )
    elif summary.status == "multi_day":
        reason = (
            "complete reviewed timing overlay spans "
            f"{summary.span_days} Moscow calendar days"
        )
    else:
        missing = ",".join(str(order) for order in summary.missing_event_orders)
        reason = f"effective timing remains unresolved for event orders {missing}"
    return PlayTimingEligibility(
        status=summary.status,
        reason=reason,
        target_fingerprint=fingerprint,
        fingerprint_match=True,
    )


def _resolve_runner_target(
    client: TotoBriefClient,
    resolved_at: datetime,
) -> PinnedDrawing:
    reference = resolve_open_drawing_from_api(client, now=resolved_at)
    target = parse_target_drawing(
        client.drawing_info(reference.drawing_id),
        fetched_at=resolved_at,
    )
    if target.drawing_id != reference.drawing_id:
        raise ValueError(
            f"drawing-info data.id {target.drawing_id} does not match page-one "
            f"drawing id {reference.drawing_id}"
        )
    return pin_drawing(target)


def _build_runner_package(
    *,
    client: TotoBriefClient,
    expected: PinnedDrawing,
    config: EVConfig,
    fetched_at: datetime,
    progress_callback: Callable[[dict[str, object]], None] | None,
    timing_eligibility_resolver: Callable[
        [Mapping[str, object]], PlayTimingEligibility
    ],
) -> EVPackageRun:
    payload = client.drawing_info(expected.target.drawing_id)
    observed = pin_drawing(parse_target_drawing(payload, fetched_at=fetched_at))
    if (
        observed.target.drawing_id != expected.target.drawing_id
        or observed.target.drawing_number != expected.target.drawing_number
        or observed.target.deadline != expected.target.deadline
        or observed.fingerprint != expected.fingerprint
    ):
        raise RunnerTargetMismatch("fresh EV target does not match pinned target")
    return build_open_ev_package(
        client=client,
        drawing_id=expected.target.drawing_id,
        config=config,
        progress_callback=progress_callback,
        timing_eligibility_resolver=timing_eligibility_resolver,
        payload=payload,
        fetched_at=fetched_at,
    )


def _api_sports_provider_factory(
    api_key: str,
    quota_reserve: int,
) -> Callable[[Path], APISportsClient]:
    return lambda cache_dir: APISportsClient(
        api_key,
        cache_dir=cache_dir,
        quota_reserve=quota_reserve,
    )


@dataclass(frozen=True)
class _RunnerResources:
    engine: object
    session_factory: object
    reviewed_aliases: dict[str, str]
    readonly_engine: object
    readonly_session_factory: object
    timing_resolver: Callable[[PinnedDrawing], PlayTimingEligibility]
    ev_timing_resolver: Callable[[Mapping[str, object]], PlayTimingEligibility]
    timing_override_pin: PinnedTimingOverrideCatalog | None
    prepared_pins: tuple[DrawingEventPinRecord, ...] | None
    reviewed_catalog_path: Path | None
    reviewed_catalog_hash: str | None
    reviewed_input_paths: tuple[Path, ...]


def _prepare_runner_resources(
    *,
    config: DrawingRunnerConfig,
    target: PinnedDrawing,
    preflight_at: datetime,
    db: str | Path,
    aliases: str | Path,
    report_dir: str | Path,
    cache_root: str | Path,
    provider_factory: Callable[[Path], object],
    timing_overrides: str | Path | None = None,
    reviewed_schedule_catalog: str | Path | None = None,
    systematic_resolution: bool = True,
    refresh_probability_evidence: bool = False,
) -> _RunnerResources:
    reviewed_catalog = (
        None
        if reviewed_schedule_catalog is None
        else load_reviewed_schedule_catalog(
            Path(reviewed_schedule_catalog),
            evaluated_at=preflight_at,
            max_age=timedelta(hours=12),
        )
    )
    reviewed_input_paths = (
        ()
        if reviewed_catalog is None
        else reviewed_catalog_input_paths(reviewed_catalog)
    )
    candidate_paths = drawing_run_candidate_paths(
        config,
        target,
        preflight_at,
        report_dir,
    )
    protected_paths = tuple(
        path
        for path in (db, aliases, timing_overrides, *reviewed_input_paths)
        if path is not None
    )
    validate_output_paths(
        candidate_paths,
        protected_paths=protected_paths,
        protected_roots=(cache_root,),
    )
    probe_writable_directory(report_dir)
    probe_writable_directory(cache_root)
    timing_override_pin = (
        None
        if timing_overrides is None
        else pin_timing_override_catalog(timing_overrides)
    )
    provider_factory(Path(cache_root))

    engine = init_db(db)
    session_factory = get_session_factory(engine)
    if systematic_resolution:
        persist_drawing_identity(
            session_factory,
            target.target,
            require_visible_number=True,
        )
        if refresh_probability_evidence:
            refresh_ready_preparation_for_target(
                target.target,
                session_factory=session_factory,
                provider="api-sports",
            )
    reviewed_aliases = load_aliases(aliases)
    readonly_engine = open_readonly_db(db)
    readonly_session_factory = get_session_factory(readonly_engine)
    if systematic_resolution:
        loader = (
            load_ready_drawing_pins
            if reviewed_schedule_catalog is None
            else load_ready_pin_set
        )
        loader_kwargs = {
            "drawing_id": target.target.drawing_id,
            "drawing_fingerprint": target.fingerprint,
            "expected_probability_sha256": preparation_probability_sha256(
                tuple(event.bk_probabilities for event in target.target.events)
            ),
            "as_of": preflight_at,
        }
        if reviewed_schedule_catalog is None:
            loader_kwargs["provider"] = "api-sports"
        prepared_pins = loader(session_factory, **loader_kwargs)
    else:
        prepared_pins = None
    if systematic_resolution and not prepared_pins:
        raise ValueError("exact prepared drawing pins are missing; run prepare-drawing")
    return _RunnerResources(
        engine=engine,
        session_factory=session_factory,
        reviewed_aliases=reviewed_aliases,
        readonly_engine=readonly_engine,
        readonly_session_factory=readonly_session_factory,
        timing_resolver=_build_runner_timing_resolver(str(db)),
        ev_timing_resolver=_build_timing_eligibility_resolver(str(db)),
        timing_override_pin=timing_override_pin,
        prepared_pins=prepared_pins,
        reviewed_catalog_path=(
            None if reviewed_catalog is None else reviewed_catalog.path
        ),
        reviewed_catalog_hash=(
            None if reviewed_catalog is None else reviewed_catalog.semantic_hash
        ),
        reviewed_input_paths=reviewed_input_paths,
    )


def _utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _require_override_resolution(
    resolution: RunnerTimingResolution | None,
) -> RunnerTimingResolution:
    if not isinstance(resolution, RunnerTimingResolution):
        raise ValueError("effective timing override was not resolved")
    return resolution


class _OfflineTargetClient:
    def __init__(self, inputs: OfflineReplayInputs) -> None:
        self._inputs = inputs

    def drawing_info(self, drawing_id: int) -> dict[str, object]:
        if drawing_id != self._inputs.target.drawing_id:
            raise ValueError("offline replay requested an unexpected drawing id")
        return self._inputs.target_payload


def _run_drawing_offline_replay(
    *,
    drawing_id: int,
    target_cache: str,
    schedule_cache: str,
    replay_as_of: str,
    replay_root: str,
    bank: int,
    stake: int,
    minimum_gross_ev: float,
    final_lead_minutes: int,
    safety_stop_minutes: int,
    db: str | None,
    report_dir: str | None,
    provider: str,
    aliases: str,
    cache_root: str | None,
) -> None:
    paths = resolve_offline_replay_paths(
        replay_root=replay_root,
        db=db,
        report_dir=report_dir,
        cache_root=cache_root,
        project_root=Path(__file__).resolve().parents[2],
    )
    inputs = load_offline_replay_inputs(
        drawing_id=drawing_id,
        target_cache=target_cache,
        schedule_cache=schedule_cache,
        replay_as_of=replay_as_of,
        provider=provider,
    )
    config = DrawingRunnerConfig(
        bank=bank,
        stake=stake,
        mode="research",
        minimum_gross_ev=minimum_gross_ev,
        final_lead_minutes=final_lead_minutes,
        safety_stop_minutes=safety_stop_minutes,
    )
    final_at = inputs.target.deadline - timedelta(minutes=config.final_lead_minutes)
    safety_stop_at = inputs.target.deadline - timedelta(
        minutes=config.safety_stop_minutes
    )
    if not final_at <= inputs.replay_as_of < safety_stop_at:
        raise ValueError(
            "--replay-as-of must be within the runner final window and before "
            "the safety stop"
        )

    paths.root.mkdir(parents=True, exist_ok=True)
    verified_paths = resolve_offline_replay_paths(
        replay_root=paths.root,
        db=paths.db,
        report_dir=paths.reports,
        cache_root=paths.provider_cache,
        project_root=Path(__file__).resolve().parents[2],
    )
    if verified_paths != paths:
        raise ValueError("replay output boundary changed before initialization")

    engine = init_db(paths.db)
    readonly_engine = None
    try:
        session_factory = get_session_factory(engine)
        seed_reviewed_alias_config(session_factory, aliases, provider=provider)
        preparation = prepare_drawing(
            inputs.target,
            inputs.schedule_events,
            session_factory=session_factory,
            provider=provider,
            schedule_diagnostics=(
                {
                    "sport": "all",
                    "date": None,
                    "status": "success",
                    "reason": (
                        "validated offline schedule cache "
                        f"sha256={inputs.schedule_cache_sha256}"
                    ),
                },
            ),
        )
        if preparation.status != "ready" or len(preparation.pins) != 15:
            raise ValueError(
                "offline replay preparation is unresolved: "
                f"mapped={preparation.mapped_count}/15, "
                f"orders={preparation.unresolved_event_orders}"
            )

        aliases_map = load_aliases(aliases)
        readonly_engine = open_readonly_db(paths.db)
        readonly_factory = get_session_factory(readonly_engine)
        timing_resolver = _build_runner_timing_resolver(str(paths.db))
        ev_timing_resolver = _build_timing_eligibility_resolver(str(paths.db))
        cached_client = _OfflineTargetClient(inputs)

        def collect_target(target, stop_at):
            result = collect_fresh_open_external_odds(
                totobrief_client=cached_client,
                provider_factory=lambda _cache_dir: OfflineScheduleProvider(
                    inputs.schedule_events, provider
                ),
                session_factory=session_factory,
                aliases=aliases_map,
                prepared_pins=preparation.pins,
                cache_root=paths.provider_cache,
                target=target,
                stop_at=stop_at,
                max_passes=1,
                max_expansion_passes=1,
                retry_delay_seconds=0.0,
                now=lambda: inputs.replay_as_of,
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: (_ for _ in ()).throw(
                    ValueError("offline replay must never sleep")
                ),
            )
            if not pinned_revalidation_is_ready(result.snapshot):
                summary = result.snapshot.pinned_revalidation
                detail = (
                    "absent"
                    if summary is None
                    else (
                        f"{summary.matched_count}/{summary.expected_count}; "
                        f"stale={summary.stale_event_orders}; "
                        f"provider_failures={summary.provider_failure_event_orders}; "
                        f"date_failures={summary.date_failure_event_orders}"
                    )
                )
                raise ValueError(
                    "offline replay pinned revalidation is not ready: " + detail
                )
            return result

        pinned = pin_drawing(inputs.target)
        result = run_drawing(
            config=config,
            resolve_target=lambda _resolved_at: pinned,
            collect_target=collect_target,
            resolve_timing=timing_resolver,
            audit_coverage=lambda: audit_external_coverage(
                readonly_factory,
                last=30,
                minimum_bookmakers=3,
            ),
            build_package=lambda expected: _build_runner_package(
                client=cached_client,
                expected=expected,
                config=config.ev_config,
                fetched_at=inputs.replay_as_of,
                progress_callback=None,
                timing_eligibility_resolver=ev_timing_resolver,
            ),
            now=lambda: inputs.replay_as_of,
            monotonic=lambda: 0.0,
            sleep=lambda _seconds: (_ for _ in ()).throw(
                ValueError("offline replay must never sleep")
            ),
        )
        if result.decision != "RESEARCH ONLY":
            raise ValueError(
                "offline replay did not finish as RESEARCH ONLY; no report published"
            )
        summary = result.collection.snapshot.pinned_revalidation
        if summary is None or not summary.ready_for_play:
            raise ValueError("offline replay lost authoritative pin revalidation")
        result = replace(
            result,
            terminal_reason=(
                "offline replay completed; research-only and non-actionable"
            ),
            offline_replay=OfflineReplayProvenance(
                replay_root=str(paths.root),
                replay_as_of=inputs.replay_as_of,
                target_cache_path=str(inputs.target_cache_path),
                target_cache_sha256=inputs.target_cache_sha256,
                target_payload_sha256=inputs.target_payload_sha256,
                schedule_cache_path=str(inputs.schedule_cache_path),
                schedule_cache_sha256=inputs.schedule_cache_sha256,
                schedule_payload_sha256=inputs.schedule_payload_sha256,
                provider=inputs.provider,
            ),
        )
        manifest_path, markdown_path = write_drawing_run_reports(
            result,
            report_dir=paths.reports,
            input_paths=(
                paths.db,
                aliases,
                inputs.target_cache_path,
                inputs.schedule_cache_path,
            ),
        )
    finally:
        if readonly_engine is not None:
            readonly_engine.dispose()
        engine.dispose()

    print("Decision: RESEARCH ONLY")
    print("Actionable: no")
    print("Preparation: ready 15/15")
    print("Pinned revalidation: 15/15")
    print(f"Manifest: {manifest_path}")
    print(f"Report: {markdown_path}")


@app.command("run-drawing")
def run_drawing_command(
    open: bool = typer.Option(False, "--open"),  # noqa: A002
    offline_replay: bool = typer.Option(False, "--offline-replay"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    target_cache: str | None = typer.Option(None, "--target-cache"),
    schedule_cache: str | None = typer.Option(None, "--schedule-cache"),
    replay_as_of: str | None = typer.Option(None, "--replay-as-of"),
    replay_root: str | None = typer.Option(None, "--replay-root"),
    bank: int = typer.Option(...),
    stake: int = typer.Option(30),
    mode: str = typer.Option("playable"),
    minimum_gross_ev: float = typer.Option(
        DEFAULT_MINIMUM_GROSS_EV,
        "--min-gross-ev",
    ),
    package_near_fixed_share: float = typer.Option(0.95, "--package-near-fixed-share"),
    package_low_probability_threshold: float = typer.Option(
        0.20, "--package-low-probability-threshold"
    ),
    package_material_probability_threshold: float = typer.Option(
        0.20, "--package-material-probability-threshold"
    ),
    final_lead_minutes: int = typer.Option(20, min=1),
    safety_stop_minutes: int = typer.Option(5, min=1),
    db: str | None = typer.Option(None),
    report_dir: str | None = typer.Option(None),
    provider: str = typer.Option("api-sports"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    timing_overrides: str | None = typer.Option(None, "--timing-overrides"),
    reviewed_schedule_catalog: str | None = typer.Option(
        None, "--reviewed-schedule-catalog"
    ),
    quota_reserve: int = typer.Option(10, min=0),
    max_passes: int = typer.Option(3, min=1),
    max_expansion_passes: int = typer.Option(3, min=1),
    retry_delay_seconds: float = typer.Option(65.0, min=0.0),
    cache_root: str | None = typer.Option(None),
) -> None:
    """Safely run one pinned drawing through collection, audit, and EV."""
    replay_values = (drawing_id, target_cache, schedule_cache, replay_as_of)
    if offline_replay:
        if open:
            raise typer.BadParameter("--offline-replay is incompatible with --open")
        if any(value is None for value in replay_values):
            raise typer.BadParameter(
                "--offline-replay requires --drawing-id, --target-cache, "
                "--schedule-cache, and --replay-as-of"
            )
        if replay_root is None:
            raise typer.BadParameter("--offline-replay requires --replay-root")
        if mode != "research":
            raise typer.BadParameter(
                "--offline-replay requires --mode research; playable is forbidden"
            )
        if timing_overrides is not None:
            raise typer.BadParameter(
                "--offline-replay is incompatible with --timing-overrides"
            )
        try:
            _run_drawing_offline_replay(
                drawing_id=drawing_id,
                target_cache=target_cache,
                schedule_cache=schedule_cache,
                replay_as_of=replay_as_of,
                replay_root=replay_root,
                bank=bank,
                stake=stake,
                minimum_gross_ev=minimum_gross_ev,
                final_lead_minutes=final_lead_minutes,
                safety_stop_minutes=safety_stop_minutes,
                db=db,
                report_dir=report_dir,
                provider=provider,
                aliases=aliases,
                cache_root=cache_root,
            )
        except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
            raise typer.BadParameter(str(error)) from error
        return
    if any(value is not None for value in (*replay_values, replay_root)):
        raise typer.BadParameter(
            "--drawing-id/--target-cache/--schedule-cache/--replay-as-of/"
            "--replay-root require --offline-replay"
        )
    final_input = os.environ.get("TOTO_FINAL_INPUT")
    scheduler_plan = os.environ.get("TOTO_SCHEDULER_PLAN")
    if (final_input is None) != (scheduler_plan is None):
        raise typer.BadParameter("atomic final input environment is incomplete")
    db = db or "data/toto.db"
    report_dir = report_dir or "reports"
    cache_root = cache_root or "data/external-cache/api-sports"
    if not open:
        raise typer.BadParameter("--open is required unless --offline-replay is used")
    try:
        config = DrawingRunnerConfig(
            bank=bank,
            stake=stake,
            mode=mode,  # type: ignore[arg-type]
            minimum_gross_ev=minimum_gross_ev,
            package_near_fixed_share=package_near_fixed_share,
            package_low_probability_threshold=package_low_probability_threshold,
            package_material_probability_threshold=(
                package_material_probability_threshold
            ),
            final_lead_minutes=final_lead_minutes,
            safety_stop_minutes=safety_stop_minutes,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    api_key = os.environ.get("API_SPORTS_KEY", "")
    if not api_key.strip():
        raise typer.BadParameter("API_SPORTS_KEY is required")
    systematic_resolution = os.environ.get(
        "TOTO_LEGACY_NAME_MATCHING", ""
    ).strip().casefold() not in {"1", "true", "yes", "on"}

    command_error: typer.BadParameter | None = None
    result = None
    publication: DrawingRunPublication | None = None
    try:
        client = TotoBriefClient()
        atomic_snapshot = (
            None
            if final_input is None
            else load_final_input(
                Path(final_input),
                expected_plan=load_scheduler_plan(scheduler_plan),
            )
        )
        provider_factory = _api_sports_provider_factory(api_key, quota_reserve)
        resources: _RunnerResources | None = None
        timing_resolution: RunnerTimingResolution | None = None

        def require_resources() -> _RunnerResources:
            if resources is None:
                raise ValueError("runner resources were not preflighted")
            return resources

        def preflight_check(
            target: PinnedDrawing,
            preflight_at: datetime,
        ) -> None:
            nonlocal resources
            resources = _prepare_runner_resources(
                config=config,
                target=target,
                preflight_at=preflight_at,
                db=db,
                aliases=aliases,
                report_dir=report_dir,
                cache_root=cache_root,
                provider_factory=provider_factory,
                timing_overrides=timing_overrides,
                reviewed_schedule_catalog=reviewed_schedule_catalog,
                systematic_resolution=systematic_resolution,
                refresh_probability_evidence=atomic_snapshot is not None,
            )

        def resolve_timing_override(
            target: PinnedDrawing,
            collection: ProspectiveCollectionResult,
            raw: PlayTimingEligibility,
        ) -> RunnerTimingResolution:
            nonlocal timing_resolution
            catalog_pin = require_resources().timing_override_pin
            if catalog_pin is None:
                raise ValueError("timing override catalog was not preflighted")
            timing_resolution = _resolve_runner_timing_override(
                target,
                collection,
                raw,
                catalog_pin,
            )
            return timing_resolution

        def verify_timing_override(
            resolution: RunnerTimingResolution,
        ) -> RunnerTimingResolution:
            nonlocal timing_resolution
            catalog_pin = require_resources().timing_override_pin
            if catalog_pin is None:
                raise ValueError("timing override catalog was not preflighted")
            timing_resolution = _verify_runner_timing_override(
                resolution,
                catalog_pin,
            )
            return timing_resolution

        def collect_target(target, stop_at):
            prepared = require_resources()
            return collect_fresh_open_external_odds(
                totobrief_client=client,
                provider_factory=provider_factory,
                session_factory=prepared.session_factory,
                aliases=prepared.reviewed_aliases,
                prepared_pins=prepared.prepared_pins,
                reviewed_schedule_catalog=reviewed_schedule_catalog,
                cache_root=Path(cache_root),
                target=target,
                stop_at=stop_at,
                max_passes=max_passes,
                max_expansion_passes=max_expansion_passes,
                retry_delay_seconds=retry_delay_seconds,
                now=_utc_now_datetime,
                monotonic=time.monotonic,
                sleep=time.sleep,
            )

        def audit_coverage():
            prepared = require_resources()
            return audit_external_coverage(
                prepared.readonly_session_factory,
                last=30,
                minimum_bookmakers=3,
            )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task("Preflighting open drawing")

            def update_progress(update: dict[str, object]) -> None:
                phase = str(update.get("phase", "preflight"))
                if phase == "waiting":
                    remaining = float(update.get("seconds_until_final", 0.0))
                    description = f"Waiting for T-{remaining / 60:.1f} final window"
                else:
                    descriptions = {
                        "preflight": "Preflighting open drawing",
                        "final": "Revalidating pinned drawing",
                        "collect": "Collecting fresh API-Sports odds",
                        "timing": "Checking exact timing eligibility",
                        "audit": "Auditing latest 30 collections",
                        "ev": "Building exact EV package",
                        "complete": f"Runner complete: {update.get('decision')}",
                    }
                    description = descriptions.get(phase, "Running drawing")
                progress.update(task_id, description=description)

            runner_kwargs = dict(
                config=config,
                collect_target=collect_target,
                resolve_timing=lambda target: require_resources().timing_resolver(
                    target
                ),
                audit_coverage=audit_coverage,
                build_package=lambda expected: (
                    _build_runner_package(
                        client=client,
                        expected=expected,
                        config=config.ev_config,
                        fetched_at=_utc_now_datetime(),
                        progress_callback=update_progress,
                        timing_eligibility_resolver=(
                            require_resources().ev_timing_resolver
                            if timing_overrides is None
                            else lambda _payload: (
                                _require_override_resolution(
                                    timing_resolution
                                ).effective
                            )
                        ),
                    )
                    if atomic_snapshot is None
                    else build_open_ev_package(
                        client=client,
                        drawing_id=expected.target.drawing_id,
                        config=config.ev_config,
                        progress_callback=update_progress,
                        timing_eligibility_resolver=(
                            require_resources().ev_timing_resolver
                            if timing_overrides is None
                            else lambda _payload: (
                                _require_override_resolution(
                                    timing_resolution
                                ).effective
                            )
                        ),
                        payload=atomic_snapshot.payload,
                        fetched_at=atomic_snapshot.captured_at,
                    )
                ),
                now=_utc_now_datetime,
                monotonic=time.monotonic,
                sleep=time.sleep,
                progress_callback=update_progress,
                preflight_check=preflight_check,
                resolve_timing_override=(
                    resolve_timing_override if timing_overrides is not None else None
                ),
                verify_timing_override=(
                    verify_timing_override if timing_overrides is not None else None
                ),
            )
            result = (
                run_drawing(
                    **runner_kwargs,
                    resolve_target=lambda resolved_at: _resolve_runner_target(
                        client, resolved_at
                    ),
                )
                if atomic_snapshot is None
                else run_drawing_from_final_input(
                    **runner_kwargs, snapshot=atomic_snapshot
                )
            )
    except KeyboardInterrupt:
        command_error = typer.BadParameter(
            "Drawing runner interrupted; no final manifest was published"
        )
    except (
        APISportsError,
        FloatingPointError,
        KeyError,
        OSError,
        OverflowError,
        requests.RequestException,
        SQLAlchemyError,
        TypeError,
        ValueError,
    ) as error:
        command_error = typer.BadParameter(
            _external_error_message(error, secret=api_key)
        )

    if command_error is not None:
        raise command_error
    if result is None:
        raise typer.BadParameter("Drawing runner did not produce a result")

    if (
        result.decision != "NO BET"
        and resources is not None
        and resources.reviewed_catalog_path is not None
        and resources.reviewed_catalog_hash is not None
    ):
        try:
            revalidate_reviewed_catalog(
                resources.reviewed_catalog_path,
                expected_catalog_hash=resources.reviewed_catalog_hash,
                evaluated_at=_utc_now_datetime(),
                max_age=timedelta(minutes=90),
            )
        except (OSError, TypeError, ValueError) as error:
            result = replace(
                result,
                decision="NO BET",
                terminal_reason=(
                    "reviewed schedule TOCTOU revalidation failed: "
                    f"{str(error) or type(error).__name__}"
                ),
                ev_run=None,
            )

    try:
        reviewed_inputs = () if resources is None else resources.reviewed_input_paths
        publication = publish_drawing_run_artifacts(
            result,
            report_dir=report_dir,
            protected_paths=tuple(
                path
                for path in (
                    db,
                    aliases,
                    timing_overrides,
                    *reviewed_inputs,
                )
                if path is not None
            ),
            protected_roots=(cache_root,),
            now=_utc_now_datetime,
        )
    except KeyboardInterrupt:
        if publication is None:
            raise typer.BadParameter(
                "Drawing runner interrupted; no final manifest was published"
            ) from None
    except (
        FloatingPointError,
        KeyError,
        OSError,
        OverflowError,
        SQLAlchemyError,
        TypeError,
        ValueError,
    ) as error:
        raise typer.BadParameter(
            _external_error_message(error, secret=api_key)
        ) from None

    if publication is None:
        raise typer.BadParameter("Drawing runner publication did not complete")
    result = publication.result
    runner_paths = publication.runner
    print(f"Decision: {result.decision}")
    print(f"Reason: {result.terminal_reason}")
    raw_timing = getattr(result, "raw_timing_eligibility", None)
    effective_timing = getattr(result, "timing_eligibility", None)
    if raw_timing is not None:
        print(f"Raw timing: {raw_timing.status}")
    if effective_timing is not None:
        print(f"Effective timing: {effective_timing.status}")
    print(f"Reports written to {runner_paths[0]} and {runner_paths[1]}")


@app.command("scheduler-plan")
def scheduler_plan_command(
    drawing: int = typer.Option(..., min=1),
    ended_at: str = typer.Option(..., "--ended-at"),
    bank: int = typer.Option(..., min=1),
    output_dir: str = typer.Option(..., "--output-dir"),
    project_root: str | None = typer.Option(None, "--project-root"),
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    stake: int = typer.Option(30, min=1),
    minimum_gross_ev: float = typer.Option(
        DEFAULT_MINIMUM_GROSS_EV,
        "--min-gross-ev",
    ),
    package_near_fixed_share: float = typer.Option(0.95, "--package-near-fixed-share"),
    package_low_probability_threshold: float = typer.Option(
        0.20, "--package-low-probability-threshold"
    ),
    package_material_probability_threshold: float = typer.Option(
        0.20, "--package-material-probability-threshold"
    ),
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    timing_overrides: str | None = typer.Option(None, "--timing-overrides"),
    reviewed_schedule_catalog: str | None = typer.Option(
        None, "--reviewed-schedule-catalog"
    ),
    env_file: str | None = typer.Option(None, "--env-file"),
    quota_reserve: int = typer.Option(10, min=0),
    max_passes: int = typer.Option(3, min=1),
    max_expansion_passes: int = typer.Option(3, min=1),
    retry_delay_seconds: float = typer.Option(65.0, min=0.0),
    python_executable: str = typer.Option(
        sys.executable,
        "--python-executable",
        help=(
            "Current Python executable or exact project .venv interpreter "
            "used by generated scheduler artifacts."
        ),
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Prepare a tracked T-45/T-30/T-20/T-16/T-12 scheduler plan."""
    try:
        plan = build_scheduler_plan(
            drawing=drawing,
            drawing_id=drawing_id,
            ended_at=ended_at,
            bank=bank,
            stake=stake,
            minimum_gross_ev=minimum_gross_ev,
            package_near_fixed_share=package_near_fixed_share,
            package_low_probability_threshold=package_low_probability_threshold,
            package_material_probability_threshold=(
                package_material_probability_threshold
            ),
            output_dir=output_dir,
            project_root=project_root or Path(__file__).resolve().parents[2],
            db=db,
            aliases=aliases,
            timing_overrides=timing_overrides,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            env_file=env_file,
            quota_reserve=quota_reserve,
            max_passes=max_passes,
            max_expansion_passes=max_expansion_passes,
            retry_delay_seconds=retry_delay_seconds,
        )
        if dry_run:
            typer.echo(scheduler_plan_json(plan), nl=False)
            return
        artifacts = prepare_scheduler_artifacts(
            plan,
            python_command=python_executable,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(f"Plan: {artifacts.plan_path}")
    print(f"Wrapper: {artifacts.wrapper_path}")
    print(f"LaunchAgent candidate: {artifacts.launch_agent_path}")
    print("LaunchAgent was generated only; install/load it manually if desired.")


@app.command("morning-preanalysis-plan")
def morning_preanalysis_plan_command(
    env_file: str = typer.Option(..., "--env-file"),
    at: list[str] | None = typer.Option(None, "--at"),  # noqa: B008
    bank: int = typer.Option(4980, min=1),
    stake: int = typer.Option(30, min=1),
    retry_count: int = typer.Option(2, "--retry-count", min=0),
    retry_delay_seconds: float = typer.Option(
        60.0,
        "--retry-delay-seconds",
        min=0,
    ),
    output_dir: str = typer.Option(..., "--output-dir"),
    project_root: str | None = typer.Option(None, "--project-root"),
    reviewed_schedule_catalog: str | None = typer.Option(
        None, "--reviewed-schedule-catalog"
    ),
    activate_evening: bool = typer.Option(
        False,
        "--activate-evening/--no-activate-evening",
        help=(
            "Allow a ready morning run to install the exact evening scheduler. "
            "Disabled by default until a 15/15 live drill passes."
        ),
    ),
    python_executable: str = typer.Option(
        sys.executable,
        "--python-executable",
    ),
) -> None:
    """Generate a non-betting morning sync/preparation launchd candidate."""
    try:
        artifacts = prepare_morning_preanalysis_artifacts(
            times=tuple(at or ("08:00", "10:30", "12:00")),
            retry_count=retry_count,
            retry_delay_seconds=retry_delay_seconds,
            output_dir=output_dir,
            env_file=env_file,
            project_root=project_root or Path.cwd(),
            bank=bank,
            stake=stake,
            activate_evening=activate_evening,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            python_command=python_executable,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(f"Wrapper: {artifacts.wrapper_path}")
    print(f"LaunchAgent candidate: {artifacts.launch_agent_path}")
    print("LaunchAgent was generated only; no betting markers are created.")


@app.command("preflight-status")
def preflight_status_command(
    open_drawing: bool = typer.Option(False, "--open"),
    db: str = typer.Option("data/toto.db"),
    community: str = typer.Option("baltbet-main"),
    state_root: str = typer.Option(
        "data/scheduler/morning-dispatch", "--state-root"
    ),
    scheduler_root: str = typer.Option(
        "reports/rehearsal", "--scheduler-root"
    ),
    at: str | None = typer.Option(None, "--at"),
) -> None:
    """Show concise read-only preparation and activation status."""
    if not open_drawing:
        raise typer.BadParameter("--open is required")
    try:
        payload = build_preflight_status(
            db=db,
            community=community,
            state_root=state_root,
            scheduler_root=scheduler_root,
            now=(
                datetime.now(timezone.utc)
                if at is None
                else datetime.fromisoformat(at.replace("Z", "+00:00"))
            ),
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _prepare_current_for_morning(
    *,
    observed_at: datetime,
    db: Path,
    community: str,
    aliases: Path,
    provider: str,
    raw_cache_dir: Path,
    totobrief_rate_state: Path,
    cache_root: Path,
    quota_reserve: int,
    api_sports_max_retries: int,
    expansion_horizon_days: int,
    project_root: Path,
    reviewed_schedule_catalog: Path | None = None,
) -> MorningPreparedDrawing:
    """Synchronize and prepare the exact selected drawing from one detail view."""
    engine = init_db(db)
    try:
        session_factory = get_session_factory(engine)
        coordinator = TotoBriefRequestCoordinator(
            state_path=totobrief_rate_state,
            minimum_interval=2.0,
            max_retries=3,
            allowed_root=project_root,
        )
        synchronized = synchronize_open_drawing(
            TotoBriefClient(coordinator=coordinator),
            session_factory,
            now=observed_at,
            community=community,
            raw_cache_dir=raw_cache_dir,
            detail_cache_max_age_seconds=(
                DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS
            ),
            storage_root=project_root,
        )
        if not synchronized.ready or synchronized.detail.payload is None:
            raise ValueError(
                synchronized.detail.error or "current TotoBrief detail is unavailable"
            )
        fetched_at = (
            observed_at
            if synchronized.detail.cache_age_seconds is None
            else observed_at - timedelta(seconds=synchronized.detail.cache_age_seconds)
        )
        target = parse_target_drawing(
            synchronized.detail.payload,
            fetched_at=fetched_at,
        )
        if target.drawing_number is None:
            raise ValueError("current drawing visible number is required")
        seed_reviewed_alias_config(session_factory, aliases, provider=provider)
        api_key = os.environ.get("API_SPORTS_KEY", "")
        if not api_key.strip():
            raise ValueError("API_SPORTS_KEY is required")
        schedule = fetch_preparation_schedule(
            target,
            APISportsClient(
                api_key,
                cache_dir=cache_root,
                quota_reserve=quota_reserve,
                max_retries=api_sports_max_retries,
            ),
            session_factory=session_factory,
            provider=provider,
            missing_start_horizon_days=expansion_horizon_days,
        )
        prepared = prepare_drawing(
            target,
            schedule.candidates,
            session_factory=session_factory,
            provider=provider,
            schedule_diagnostics=schedule.diagnostics,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            evaluated_at=observed_at,
        )
        detail_sha256 = hashlib.sha256(
            json.dumps(
                synchronized.detail.payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        return MorningPreparedDrawing(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            deadline=target.deadline,
            drawing_fingerprint=prepared.drawing_fingerprint,
            detail_sha256=detail_sha256,
            preparation_status=prepared.status,
            mapped_count=sum(
                item.status == "matched" for item in prepared.events
            ),
            eligibility_status=prepared.eligibility.status,
            span_days=prepared.eligibility.span_days,
            unresolved_events=tuple(
                MorningUnresolvedEvent(
                    event_order=item.event_order,
                    target_event_id=item.target_event_id,
                    home_team=target.events[item.event_order].home_team,
                    away_team=target.events[item.event_order].away_team,
                    resolution_status=item.status,
                    reason=item.reason,
                    candidate_evidence=item.candidate_evidence,
                    provider_diagnostics=tuple(schedule.diagnostics),
                )
                for item in prepared.events
                if item.status != "matched"
            ),
        )
    finally:
        engine.dispose()


@app.command("morning-dispatch")
def morning_dispatch_command(
    bank: int = typer.Option(..., min=1),
    stake: int = typer.Option(30, min=1),
    env_file: str = typer.Option(..., "--env-file"),
    project_root: str = typer.Option(..., "--project-root"),
    state_root: str = typer.Option(..., "--state-root"),
    scheduler_root: str = typer.Option(..., "--scheduler-root"),
    db: str = typer.Option("data/toto.db"),
    community: str = typer.Option("baltbet-main"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    provider: str = typer.Option("api-sports"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    totobrief_rate_state: str = typer.Option(
        str(DEFAULT_RATE_STATE_PATH),
        "--totobrief-rate-state",
    ),
    cache_root: str = typer.Option("data/external-cache/api-sports"),
    quota_reserve: int = typer.Option(10, min=0),
    api_sports_max_retries: int = typer.Option(2, "--api-sports-max-retries", min=0),
    expansion_horizon_days: int = typer.Option(5, min=1, max=5),
    reviewed_schedule_catalog: str | None = typer.Option(
        None, "--reviewed-schedule-catalog"
    ),
    activate: bool = typer.Option(False, "--activate"),
    expected_drawing_id: int | None = typer.Option(
        None, "--expected-drawing-id", min=1
    ),
    expected_drawing_number: int | None = typer.Option(
        None, "--expected-drawing-number", min=1
    ),
    expected_fingerprint: str | None = typer.Option(
        None, "--expected-fingerprint"
    ),
    expected_deadline: datetime | None = typer.Option(  # noqa: B008
        None, "--expected-deadline"
    ),
    python_executable: str = typer.Option(sys.executable, "--python-executable"),
) -> None:
    """Prepare one current drawing and hand it to one exact evening scheduler."""
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    root = Path(project_root).absolute()
    resolved_raw_cache = resolve_contained_path(raw_cache_dir, allowed_root=root)
    resolved_rate_state = resolve_contained_path(
        totobrief_rate_state, allowed_root=root
    )
    resolved_cache_root = resolve_contained_path(cache_root, allowed_root=root)
    config = MorningDispatchConfig(
        project_root=root,
        state_root=Path(state_root),
        scheduler_root=Path(scheduler_root),
        env_file=Path(env_file),
        bank=bank,
        stake=stake,
        db=Path(db),
        aliases=Path(aliases),
        reviewed_schedule_catalog=(
            None
            if reviewed_schedule_catalog is None
            else Path(reviewed_schedule_catalog)
        ),
    )
    observed_at = datetime.now(timezone.utc)
    expected_values = (
        expected_drawing_id,
        expected_drawing_number,
        expected_fingerprint,
        expected_deadline,
    )
    if any(value is not None for value in expected_values) and any(
        value is None for value in expected_values
    ):
        raise typer.BadParameter(
            "all expected drawing identity options must be supplied together"
        )
    expected_identity = (
        None
        if expected_drawing_id is None
        else MorningExpectedIdentity(
            drawing_id=expected_drawing_id,
            drawing_number=expected_drawing_number,
            drawing_fingerprint=expected_fingerprint,
            deadline=expected_deadline,
        )
    )
    try:
        result = dispatch_morning(
            config,
            observed_at=observed_at,
            prepare_current=lambda now: _prepare_current_for_morning(
                observed_at=now,
                db=config.db,
                community=community,
                aliases=config.aliases,
                provider=provider,
                raw_cache_dir=resolved_raw_cache,
                totobrief_rate_state=resolved_rate_state,
                cache_root=resolved_cache_root,
                quota_reserve=quota_reserve,
                api_sports_max_retries=api_sports_max_retries,
                expansion_horizon_days=expansion_horizon_days,
                project_root=root,
                reviewed_schedule_catalog=(
                    None
                    if reviewed_schedule_catalog is None
                    else resolve_contained_path(
                        reviewed_schedule_catalog, allowed_root=root
                    )
                ),
            ),
            now=lambda: datetime.now(timezone.utc),
            activate=activate_scheduler_launch_agent if activate else None,
            python_command=python_executable,
            expected_identity=expected_identity,
        )
    except (
        APISportsError,
        OSError,
        SQLAlchemyError,
        SchedulerError,
        TotoBriefRequestError,
        TypeError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "reason": result.reason,
                "record_path": str(result.record_path),
                "plan_id": result.plan_id,
                "plan_path": (
                    None if result.plan_path is None else str(result.plan_path)
                ),
                "launch_agent_path": (
                    None
                    if result.launch_agent_path is None
                    else str(result.launch_agent_path)
                ),
                "activation_status": result.activation_status,
                "attention_path": (
                    None
                    if result.attention_path is None
                    else str(result.attention_path)
                ),
                "retry_plan_path": (
                    None
                    if result.retry_plan_path is None
                    else str(result.retry_plan_path)
                ),
                "review_queue_path": (
                    None
                    if result.review_queue_path is None
                    else str(result.review_queue_path)
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if result.status == "deferred":
        raise typer.Exit(code=2)


@app.command("scheduler-execute")
def scheduler_execute_command(
    plan: str = typer.Option(..., "--plan"),
    run_id: str | None = typer.Option(None, "--run-id"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    simulate: bool = typer.Option(False, "--simulate"),
) -> None:
    """Execute a scheduler plan or perform a network-free simulation."""
    try:
        scheduler_plan = load_scheduler_plan(plan)
        if dry_run:
            typer.echo(scheduler_plan_json(scheduler_plan), nl=False)
            return
        if not simulate and scheduler_plan.source_schema_version != 4:
            raise ValueError(
                "legacy scheduler plan is inspection-only; regenerate schema v4"
            )
        if run_id is not None and not simulate:
            raise ValueError(
                "--run-id is simulation-only; production schema-v4 plans "
                "must use idempotent scheduler ticks"
            )
        if simulate:
            clock = VirtualSchedulerClock(scheduler_plan.preflight_at)
            phase_runner = SimulatedSchedulerPhaseRunner()
            now = clock.now
            sleeper = clock.sleep
        else:
            phase_runner = CommandSchedulerPhaseRunner()
            now = _utc_now_datetime
            sleeper = time.sleep
        if simulate:
            result = execute_scheduler_plan(
                scheduler_plan,
                phase_runner=phase_runner,
                now=now,
                sleep=sleeper,
                run_id=run_id,
            )
        else:
            result = execute_scheduler_tick(
                scheduler_plan,
                phase_runner=phase_runner,
                now=now,
                sleep=sleeper,
            )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    if result is None:
        print("Outcome: no-op")
        print("Reason: no due scheduler phase")
        return
    print(f"Outcome: {result.outcome}")
    print(f"Decision: {result.decision}")
    print(f"Reason: {result.reason}")
    print(f"Status: {result.status_path}")
    if result.package_path is not None:
        print(f"Operator package: {result.package_path}")
        print(f"Package SHA-256: {result.package_sha256}")
    if result.outcome == "failed":
        raise typer.Exit(code=1)


@app.command("ev-package")
def ev_package_command(
    open: bool = typer.Option(False),  # noqa: A002
    mode: str = typer.Option("research"),
    bank: int = typer.Option(...),
    stake: int = typer.Option(30),
    min_gross_ev: float = typer.Option(1.0),
    package_near_fixed_share: float = typer.Option(0.95, "--package-near-fixed-share"),
    package_low_probability_threshold: float = typer.Option(
        0.20, "--package-low-probability-threshold"
    ),
    package_material_probability_threshold: float = typer.Option(
        0.20, "--package-material-probability-threshold"
    ),
    prize_fund_factor: float = typer.Option(1.0),
    possible_winnings: float | None = typer.Option(None),
    jackpot: float | None = typer.Option(None),
    db: str = typer.Option("data/toto.db"),
) -> None:
    """Build a modeled-EV package from a fresh open drawing snapshot."""
    if not open:
        raise typer.BadParameter("--open is required")

    try:
        if mode not in {"research", "playable"}:
            raise ValueError("mode must be 'research' or 'playable'")
        config = EVConfig(
            bank=bank,
            stake=stake,
            mode=mode,
            min_gross_ev=min_gross_ev,
            package_safety_enabled=True,
            package_near_fixed_share=package_near_fixed_share,
            package_low_probability_threshold=package_low_probability_threshold,
            package_material_probability_threshold=(
                package_material_probability_threshold
            ),
            prize_fund_factor=prize_fund_factor,
            possible_winnings=possible_winnings,
        )
        timing_eligibility_resolver = _build_timing_eligibility_resolver(db)
        client = TotoBriefClient()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task("Resolving fresh open drawing")
            reference = resolve_open_drawing_from_api(client)
            progress.update(
                task_id,
                description=f"Fetching drawing {reference.drawing_id}",
            )

            def update_progress(update: dict[str, object]) -> None:
                phase = update.get("phase")
                if phase == "category":
                    description = f"Computing EV category {update.get('category')}"
                elif phase == "sensitivity":
                    description = (
                        "Selecting sensitivity factor "
                        f"{float(update.get('factor', 0.0)):.2f}"
                    )
                elif phase == "package":
                    description = "Selecting exact EV package"
                else:
                    description = "Validating fresh drawing snapshot"
                progress.update(task_id, description=description)

            result = build_open_ev_package(
                client=client,
                drawing_id=reference.drawing_id,
                config=config,
                jackpot_override=jackpot,
                progress_callback=update_progress,
                timing_eligibility_resolver=timing_eligibility_resolver,
            )
            progress.update(task_id, description="Publishing EV reports")
            csv_path, markdown_path = write_ev_package_reports(result)
            progress.update(task_id, description="EV package complete")
    except KeyboardInterrupt as error:
        raise typer.BadParameter(
            "EV calculation interrupted; no recommendation was produced"
        ) from error
    except (
        FloatingPointError,
        KeyError,
        OSError,
        OverflowError,
        TypeError,
        ValueError,
        requests.RequestException,
    ) as error:
        raise typer.BadParameter(str(error)) from error

    print(_ev_input_snapshot_table(result))
    print(_ev_package_summary_table(result))
    if result.timing_diagnostics_suppressed:
        print("Timing-veto diagnostics are suppressed in playable mode.")
    print(_ev_top_coupons_table(result))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("backtest-ev")
def backtest_ev_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(100, min=1),
    banks: str = typer.Option("4800,6000,9600"),
    thresholds: str = typer.Option("0.90,0.95,1.00,1.05"),
    stake: int = typer.Option(30),
    frozen_manifest: str = typer.Option(..., "--frozen-manifest"),
) -> None:
    """Backtest exact modeled-EV packages outside a frozen holdout."""
    try:
        parsed_banks = _parse_csv_ints(banks, "banks")
        parsed_thresholds = _parse_csv_floats(thresholds, "thresholds")
        forbidden_ids = load_frozen_holdout_ids(frozen_manifest)
        config = EVBacktestConfig(
            banks=parsed_banks,
            thresholds=parsed_thresholds,
            stake=stake,
        )
        configuration_hash = ev_backtest_configuration_hash(
            config,
            last=last,
            forbidden_drawing_ids=forbidden_ids,
        )
        checkpoint_path = ev_backtest_checkpoint_path(
            configuration_hash,
            last=last,
            stake=stake,
        )
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task("Preparing modeled EV backtest")

            def update_progress(update: dict[str, object]) -> None:
                phase = str(update.get("phase", "drawing"))
                drawing = update.get("drawing_number") or update.get("drawing_id")
                position = (
                    f"{update.get('drawing_index')}/{update.get('drawing_total')}"
                )
                eta = float(update.get("eta_seconds", 0.0))
                if phase == "category":
                    description = (
                        f"drawing {drawing} {position}, category "
                        f"{update.get('category')}, ETA {eta:.1f}s"
                    )
                else:
                    description = (
                        f"drawing {drawing} {position}, {phase}, ETA {eta:.1f}s"
                    )
                progress.update(task_id, description=description)

            with session_factory() as session:
                result = run_ev_backtest(
                    session,
                    last=last,
                    banks=parsed_banks,
                    thresholds=parsed_thresholds,
                    stake=stake,
                    forbidden_drawing_ids=forbidden_ids,
                    progress_callback=update_progress,
                    checkpoint_path=checkpoint_path,
                )
            progress.update(task_id, description="Publishing modeled EV reports")
            csv_path, markdown_path = write_ev_backtest_reports(
                result,
                last=last,
                input_paths=(db, frozen_manifest),
            )
            progress.update(task_id, description="Modeled EV backtest complete")
    except KeyboardInterrupt as error:
        raise typer.BadParameter(
            "EV backtest interrupted; the partial checkpoint is diagnostic only"
        ) from error
    except (
        FloatingPointError,
        KeyError,
        OSError,
        OverflowError,
        SQLAlchemyError,
        TypeError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from error

    print(_ev_backtest_summary_table(result))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("prepare-drawing")
def prepare_drawing_command(
    open: bool = typer.Option(False, "--open"),  # noqa: A002
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    provider: str = typer.Option("api-sports"),
    schedule_cache: str | None = typer.Option(None, "--schedule-cache"),
    target_cache: str | None = typer.Option(None, "--target-cache"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    detail_cache_max_age_seconds: float = typer.Option(
        DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS,
        "--detail-cache-max-age-seconds",
        min=0,
        max=DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS,
    ),
    refresh_totobrief: bool = typer.Option(
        False,
        "--refresh-totobrief",
        help="Explicitly refresh TotoBrief instead of using synchronized local detail.",
    ),
    cache_root: str = typer.Option("data/external-cache/api-sports"),
    quota_reserve: int = typer.Option(10, min=0),
    max_retries: int = typer.Option(2, min=0),
    expansion_horizon_days: int = typer.Option(5, min=1, max=5),
    reviewed_schedule_catalog: str | None = typer.Option(
        None, "--reviewed-schedule-catalog"
    ),
) -> None:
    """Prepare exact immutable fixture/team/time pins for one drawing."""
    if open == (drawing_id is not None):
        raise typer.BadParameter("choose exactly one of --open or --drawing-id")
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    fetched_at = datetime.now(timezone.utc)
    try:
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        if target_cache is not None:
            if drawing_id is None:
                raise ValueError(
                    "--target-cache requires --drawing-id; operational target "
                    "cache discovery is never inferred from cache contents"
                )
            target_cache_path = resolve_contained_path(
                target_cache,
                allowed_root=Path.cwd(),
            )
            expected_name = f"drawing_{drawing_id}.json"
            if target_cache_path.name != expected_name:
                raise ValueError(
                    "operational --target-cache must use the canonical "
                    f"{expected_name} filename"
                )
            cache_record = load_drawing_detail_cache(
                drawing_id,
                cache_dir=target_cache_path.parent,
                max_age_seconds=detail_cache_max_age_seconds,
                now=fetched_at,
                allowed_root=Path.cwd(),
            )
            with session_factory() as session:
                reference = resolve_drawing_reference(
                    session,
                    drawing_id=drawing_id,
                )
            if reference.community is None:
                raise ValueError(
                    "drawing is not synchronized locally; run sync-prepare "
                    "before using an operational --target-cache"
                )
            _validate_cached_reference(cache_record.payload, reference)
            if reference.status not in {"active", "expected"}:
                raise ValueError("operational target cache drawing is not playable")
            target = parse_target_drawing(
                cache_record.payload,
                fetched_at=cache_record.fetched_at,
            )
        elif refresh_totobrief and open:
            synchronized = synchronize_open_drawing(
                TotoBriefClient(),
                session_factory,
                now=fetched_at,
                raw_cache_dir=raw_cache_dir,
                detail_cache_max_age_seconds=detail_cache_max_age_seconds,
                storage_root=Path.cwd(),
            )
            if not synchronized.ready:
                raise ValueError(
                    "TotoBrief detail synchronization deferred: "
                    f"{synchronized.detail.error or 'detail unavailable'}"
                )
            target = parse_target_drawing(
                synchronized.detail.payload,
                fetched_at=(
                    fetched_at
                    if synchronized.detail.cache_age_seconds is None
                    else fetched_at
                    - timedelta(seconds=synchronized.detail.cache_age_seconds)
                ),
            )
        elif refresh_totobrief:
            client = TotoBriefClient()
            collector = Collector(
                client,
                session_factory,
                raw_cache_dir=raw_cache_dir,
                detail_cache_max_age_seconds=detail_cache_max_age_seconds,
                storage_root=Path.cwd(),
                now=lambda: fetched_at,
            )
            detail = collector.sync_drawing_detail(drawing_id, force=True)
            if detail.status == "deferred" or detail.payload is None:
                raise ValueError(
                    "TotoBrief detail refresh deferred: "
                    f"{detail.error or 'detail unavailable'}"
                )
            target = parse_target_drawing(
                detail.payload,
                fetched_at=fetched_at,
            )
        else:
            if open:
                with session_factory() as session:
                    reference = resolve_drawing_reference(
                        session,
                        open=True,
                        now=fetched_at,
                    )
                selected_drawing_id = reference.drawing_id
            else:
                selected_drawing_id = drawing_id
                with session_factory() as session:
                    reference = resolve_drawing_reference(
                        session,
                        drawing_id=selected_drawing_id,
                    )
                if reference.community is None:
                    raise ValueError(
                        "drawing is not synchronized locally; run sync-prepare "
                        "or use --refresh-totobrief"
                    )
            cache_record = load_drawing_detail_cache(
                selected_drawing_id,
                cache_dir=raw_cache_dir,
                max_age_seconds=detail_cache_max_age_seconds,
                now=fetched_at,
                allowed_root=Path.cwd(),
            )
            _validate_cached_reference(cache_record.payload, reference)
            target = parse_target_drawing(
                cache_record.payload,
                fetched_at=cache_record.fetched_at,
            )
        seed_reviewed_alias_config(session_factory, aliases, provider=provider)
        if schedule_cache is not None:
            candidates = load_local_schedule(schedule_cache, provider=provider)
            schedule_diagnostics = (
                {
                    "sport": "all",
                    "date": None,
                    "status": "success",
                    "reason": f"local schedule cache: {schedule_cache}",
                },
            )
        else:
            api_key = os.environ.get("API_SPORTS_KEY", "")
            if not api_key.strip():
                raise ValueError("API_SPORTS_KEY is required without --schedule-cache")
            provider_client = APISportsClient(
                api_key,
                cache_dir=Path(cache_root),
                quota_reserve=quota_reserve,
                max_retries=max_retries,
            )
            schedule = fetch_preparation_schedule(
                target,
                provider_client,
                session_factory=session_factory,
                provider=provider,
                missing_start_horizon_days=expansion_horizon_days,
            )
            candidates = schedule.candidates
            schedule_diagnostics = schedule.diagnostics
        result = prepare_drawing(
            target,
            candidates,
            session_factory=session_factory,
            provider=provider,
            schedule_diagnostics=schedule_diagnostics,
            reviewed_schedule_catalog=reviewed_schedule_catalog,
            evaluated_at=fetched_at,
        )
    except (APISportsError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    drawing_label = result.drawing_number or result.drawing_id
    table = Table(title=f"Drawing {drawing_label} readiness")
    table.add_column("Status")
    table.add_column("Pins")
    table.add_column("Timing")
    table.add_column("Unresolved")
    table.add_row(
        result.status,
        f"{result.mapped_count}/15",
        result.eligibility.status,
        ",".join(map(str, result.unresolved_event_orders)) or "none",
    )
    print(table)
    typer.echo(
        json.dumps(
            {
                "drawing_id": result.drawing_id,
                "drawing_number": result.drawing_number,
                "drawing_fingerprint": result.drawing_fingerprint,
                "provider": result.provider,
                "status": result.status,
                "mapped_count": result.mapped_count,
                "unresolved_event_orders": result.unresolved_event_orders,
                "eligibility_status": result.eligibility.status,
                "schedule_diagnostics": result.schedule_diagnostics,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if result.status != "ready":
        raise typer.Exit(code=2)


@app.command("sync-prepare")
def sync_prepare_command(
    open: bool = typer.Option(False, "--open"),  # noqa: A002
    db: str = typer.Option("data/toto.db"),
    community: str = typer.Option("baltbet-main"),
    expected_drawing_number: int | None = typer.Option(
        None,
        "--expected-drawing-number",
        min=1,
    ),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    provider: str = typer.Option("api-sports"),
    schedule_cache: str | None = typer.Option(None, "--schedule-cache"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    detail_cache_max_age_seconds: float = typer.Option(
        DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS,
        "--detail-cache-max-age-seconds",
        min=0,
        max=DEFAULT_PREPARATION_DETAIL_CACHE_MAX_AGE_SECONDS,
    ),
    totobrief_rate_state: str = typer.Option(
        str(DEFAULT_RATE_STATE_PATH),
        "--totobrief-rate-state",
    ),
    totobrief_min_interval: float = typer.Option(
        2.0,
        "--totobrief-min-interval",
        min=0,
    ),
    totobrief_max_retries: int = typer.Option(
        3,
        "--totobrief-max-retries",
        min=0,
    ),
    cache_root: str = typer.Option("data/external-cache/api-sports"),
    quota_reserve: int = typer.Option(10, min=0),
    api_sports_max_retries: int = typer.Option(
        2,
        "--api-sports-max-retries",
        min=0,
    ),
    expansion_horizon_days: int = typer.Option(5, min=1, max=5),
    sync_only: bool = typer.Option(
        False,
        "--sync-only",
        help="Synchronize and validate TotoBrief only; do not write preparation/pins.",
    ),
) -> None:
    """Synchronize page one and prepare exact pins with no duplicate detail fetch."""
    if not open:
        raise typer.BadParameter("--open is required")
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")

    fetched_at = datetime.now(timezone.utc)

    def on_diagnostic(item: RequestDiagnostic) -> None:
        parts = [
            f"totobrief event={item.event}",
            f"endpoint={item.endpoint}",
            f"attempt={item.attempt}",
        ]
        if item.wait_seconds:
            parts.append(f"wait={item.wait_seconds:.2f}s")
        if item.status_code is not None:
            parts.append(f"status={item.status_code}")
        if item.reason:
            parts.append(f"reason={item.reason}")
        typer.echo(" ".join(parts))

    try:
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        coordinator = TotoBriefRequestCoordinator(
            state_path=totobrief_rate_state,
            minimum_interval=totobrief_min_interval,
            max_retries=totobrief_max_retries,
            allowed_root=Path.cwd(),
            diagnostic_callback=on_diagnostic,
        )
        client = TotoBriefClient(coordinator=coordinator)
        typer.echo("phase=totobrief-summary status=running page=1")
        synchronized = synchronize_open_drawing(
            client,
            session_factory,
            now=fetched_at,
            community=community,
            expected_drawing_number=expected_drawing_number,
            raw_cache_dir=raw_cache_dir,
            detail_cache_max_age_seconds=detail_cache_max_age_seconds,
            storage_root=Path.cwd(),
        )
        detail = synchronized.detail
        cache_age = (
            detail.cache_age_seconds if detail.cache_age_seconds is not None else "none"
        )
        typer.echo(
            "phase=totobrief-detail "
            f"status={detail.status} drawing={synchronized.reference.number} "
            f"source={detail.source or 'none'} "
            f"cache_age={cache_age} "
            f"wait_total={coordinator.total_wait_seconds:.2f}s "
            f"attempts={coordinator.request_attempts}"
        )
        if not synchronized.ready:
            typer.echo(
                "phase=sync-prepare status=deferred reason="
                f"{detail.error or 'TotoBrief detail unavailable'}"
            )
            raise typer.Exit(code=2)

        target_fetched_at = (
            fetched_at
            if detail.cache_age_seconds is None
            else fetched_at - timedelta(seconds=detail.cache_age_seconds)
        )
        target = parse_target_drawing(
            detail.payload,
            fetched_at=target_fetched_at,
        )
        if sync_only:
            typer.echo(
                json.dumps(
                    {
                        "drawing_id": target.drawing_id,
                        "drawing_number": target.drawing_number,
                        "status": "synchronized",
                        "preparation_written": False,
                        "totobrief_detail_source": detail.source,
                        "totobrief_cache_age_seconds": detail.cache_age_seconds,
                        "totobrief_request_attempts": coordinator.request_attempts,
                        "totobrief_wait_seconds": round(
                            coordinator.total_wait_seconds,
                            3,
                        ),
                        "summary_inserted": synchronized.summary_page.inserted,
                        "summary_updated": synchronized.summary_page.updated,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return
        seed_reviewed_alias_config(session_factory, aliases, provider=provider)

        typer.echo("phase=api-sports-preparation status=running")
        if schedule_cache is not None:
            candidates = load_local_schedule(schedule_cache, provider=provider)
            schedule_diagnostics = (
                {
                    "sport": "all",
                    "date": None,
                    "status": "success",
                    "reason": f"local schedule cache: {schedule_cache}",
                },
            )
        else:
            api_key = os.environ.get("API_SPORTS_KEY", "")
            if not api_key.strip():
                raise ValueError("API_SPORTS_KEY is required without --schedule-cache")
            provider_client = APISportsClient(
                api_key,
                cache_dir=Path(cache_root),
                quota_reserve=quota_reserve,
                max_retries=api_sports_max_retries,
            )
            schedule = fetch_preparation_schedule(
                target,
                provider_client,
                session_factory=session_factory,
                provider=provider,
                missing_start_horizon_days=expansion_horizon_days,
            )
            candidates = schedule.candidates
            schedule_diagnostics = schedule.diagnostics

        result = prepare_drawing(
            target,
            candidates,
            session_factory=session_factory,
            provider=provider,
            schedule_diagnostics=schedule_diagnostics,
        )
    except typer.Exit:
        raise
    except (
        APISportsError,
        OSError,
        SQLAlchemyError,
        TotoBriefRequestError,
        TypeError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from error

    payload = {
        "drawing_id": result.drawing_id,
        "drawing_number": result.drawing_number,
        "drawing_fingerprint": result.drawing_fingerprint,
        "status": result.status,
        "mapped_count": result.mapped_count,
        "unresolved_event_orders": result.unresolved_event_orders,
        "eligibility_status": result.eligibility.status,
        "totobrief_detail_source": synchronized.detail.source,
        "totobrief_cache_age_seconds": synchronized.detail.cache_age_seconds,
        "totobrief_request_attempts": coordinator.request_attempts,
        "totobrief_wait_seconds": round(coordinator.total_wait_seconds, 3),
        "summary_inserted": synchronized.summary_page.inserted,
        "summary_updated": synchronized.summary_page.updated,
    }
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if result.status != "ready":
        raise typer.Exit(code=2)


@app.command("collect-external-odds")
def collect_external_odds_command(
    open: bool = typer.Option(False),  # noqa: A002
    provider: str = typer.Option("api-sports"),
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    quota_reserve: int = typer.Option(10, min=0),
    fresh: bool = typer.Option(True, "--fresh/--reuse-cache"),
    max_passes: int = typer.Option(3, min=1),
    expand_missing_starts: bool = typer.Option(
        True,
        "--expand-missing-starts/--no-expand-missing-starts",
        help="Use --expand-missing-starts or --no-expand-missing-starts.",
    ),
    expansion_horizon_days: int = typer.Option(
        5,
        min=3,
        max=5,
        help="Expanded search limit set by --expansion-horizon-days.",
    ),
    max_expansion_passes: int = typer.Option(
        3,
        min=1,
        help="Expansion retry limit set by --max-expansion-passes.",
    ),
    retry_delay_seconds: float = typer.Option(65.0, min=0.0),
    cache_root: str = typer.Option("data/external-cache/api-sports"),
) -> None:
    """Collect one prospective external-odds snapshot for the open drawing.

    Expansion controls: --expand-missing-starts/--no-expand-missing-starts,
    --expansion-horizon-days, --max-expansion-passes, and
    --retry-delay-seconds.
    """
    if not open:
        raise typer.BadParameter("--open is required")
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    api_key = os.environ.get("API_SPORTS_KEY", "")
    if not api_key.strip():
        raise typer.BadParameter("API_SPORTS_KEY is required")

    sanitized_error: typer.BadParameter | None = None
    prospective_result: ProspectiveCollectionResult | None = None
    try:
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        reviewed_aliases = load_aliases(aliases)
        if fresh:
            prospective_result = collect_fresh_open_external_odds(
                totobrief_client=TotoBriefClient(),
                provider_factory=lambda cache_dir: APISportsClient(
                    api_key,
                    cache_dir=cache_dir,
                    quota_reserve=quota_reserve,
                ),
                session_factory=session_factory,
                aliases=reviewed_aliases,
                cache_root=Path(cache_root),
                max_passes=max_passes,
                expand_missing_starts=expand_missing_starts,
                expansion_horizon_days=expansion_horizon_days,
                max_expansion_passes=max_expansion_passes,
                retry_delay_seconds=retry_delay_seconds,
            )
            result = prospective_result.snapshot
        else:
            provider_client = APISportsClient(
                api_key,
                cache_dir=Path(cache_root),
                quota_reserve=quota_reserve,
            )
            result = collect_open_external_odds(
                TotoBriefClient(),
                provider_client,
                session_factory,
                reviewed_aliases,
                fetched_at=datetime.now(timezone.utc),
            )
    except (APISportsError, OSError, SQLAlchemyError, ValueError) as error:
        sanitized_error = typer.BadParameter(
            _external_error_message(error, secret=api_key)
        )

    if sanitized_error is not None:
        raise sanitized_error

    print(_external_collection_table(result, prospective_result))


@app.command("audit-external-coverage")
def audit_external_coverage_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(30, min=1),
    min_bookmakers: int = typer.Option(3, min=1),
    report_dir: str = typer.Option("reports"),
) -> None:
    """Audit stored external-odds coverage without provider network access."""
    try:
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        audit = audit_external_coverage(
            session_factory,
            last=last,
            minimum_bookmakers=min_bookmakers,
        )
        paths = write_external_coverage_reports(audit, report_dir=report_dir)
    except (OSError, SQLAlchemyError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(_external_coverage_table(audit))
    print(f"Reports written to {paths[0]} and {paths[1]}")


@app.command()
def build_brief(
    open: bool = typer.Option(  # noqa: A002
        False,
        help="Resolve the current open baltbet-main drawing.",
    ),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
) -> None:
    """Build a baseline brief and cover package for the open drawing."""
    if not open:
        raise typer.BadParameter("Only --open is supported for now.")

    engine = init_db(db)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        try:
            reference = resolve_drawing_reference(session, open=True)
            result = build_brief_for_drawing(
                session,
                drawing_id=reference.drawing_id,
                category=category,
                bank=bank,
                stake=stake,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    print(_drawing_reference_table(reference))
    print(_brief_matches_table(result["matches"], result["brief"]))
    print(_brief_summary_table(result))
    print(_cover_coupons_table(result["selected_coupons"][:20]))
    print(f"Brief report written to {result['brief_path']}")
    print(f"Package report written to {result['package_path']}")


@app.command()
def verify_cover(
    brief: str = typer.Option(
        ...,
        help="Comma-separated brief positions, using 1, X, and 2.",
    ),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    package: str = typer.Option(  # noqa: A002
        ...,
        "--package",
        help="CSV package file with a coupon column.",
    ),
) -> None:
    """Verify exact coverage of a cover package against a brief."""
    try:
        coupons = load_cover_package_csv(package)
        result = verify_cover_package(
            brief=parse_brief(brief),
            category=category,
            coupons=coupons,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error

    print(_cover_verification_table(result))
    print(_cover_distance_distribution_table(result["distance_distribution"]))
    if not result["guarantee_pass"]:
        print(_uncovered_variants_table(result["first_uncovered_variants"]))


@app.command()
def backtest(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(100, help="Number of latest complete drawings to test."),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    allow_unhealthy_research: bool = typer.Option(
        False,
        "--allow-unhealthy-research",
        help="Explicit research-only bypass; marks all output as overridden.",
    ),
) -> None:
    """Backtest the MVP package generator on finished drawings."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with session_factory() as session:
        try:
            result = run_mvp_backtest(
                session,
                last=last,
                bank=bank,
                stake=stake,
                category=category,
                allow_unhealthy_research=allow_unhealthy_research,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    csv_path, markdown_path = write_backtest_reports(result, last=last)
    _print_data_health_override(result.summary)
    print(_backtest_summary_table(result.summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("collect-sports-stats")
def collect_sports_stats_command(
    open: bool = typer.Option(False, "--open"),  # noqa: A002
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    db: str = typer.Option("data/toto.db"),
    provider: str = typer.Option("api-sports"),
    last: int = typer.Option(10, "--last", min=1, max=10),
    report_dir: str = typer.Option(
        "reports/sports-stats",
        "--report-dir",
    ),
    cache_root: str = typer.Option(
        "data/external-cache/api-sports",
        "--cache-root",
    ),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    env_file: str = typer.Option(".env", "--env-file"),
    historical_as_of: str | None = typer.Option(
        None,
        "--historical-as-of",
        help=(
            "Explicit cache-only UTC as-of for historical audit. "
            "Never performs a historical network reconstruction."
        ),
    ),
) -> None:
    """Collect immutable football statistics — AUDIT ONLY.

    This command never changes probabilities, packages, PLAY/NO BET, scheduler
    state, or betting markers.
    """
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    try:
        snapshot, paths = collect_and_store_sports_stats(
            db=db,
            open_drawing=open,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            history_size=last,
            report_dir=report_dir,
            cache_root=cache_root,
            raw_cache_dir=raw_cache_dir,
            env_file=env_file,
            historical_as_of=parse_historical_as_of(historical_as_of),
        )
    except (
        APISportsError,
        OSError,
        SQLAlchemyError,
        TotoBriefRequestError,
        TypeError,
        ValueError,
    ) as error:
        raise typer.BadParameter(str(error)) from error

    typer.echo(
        json.dumps(
            {
                "mode": "AUDIT ONLY",
                "package_influence": "NONE",
                "fallback": "MARKET ONLY",
                "run_id": snapshot.run_id,
                "drawing_id": snapshot.drawing_id,
                "drawing_number": snapshot.drawing_number,
                "status": snapshot.status,
                "complete_count": snapshot.complete_count,
                "partial_count": snapshot.partial_count,
                "missing_count": snapshot.missing_count,
                "unsupported_count": snapshot.unsupported_count,
                "requests_made": snapshot.requests_made,
                "cache_hits": snapshot.cache_hits,
                "reports": [str(path) for path in paths],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command()
def backtest_brief(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(100, help="Number of latest complete drawings to test."),
    bank: int = typer.Option(..., help="Any positive integer budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    top_candidates: int = typer.Option(
        20,
        help="Number of top candidate briefs to run through exact cover.",
    ),
    max_candidate_briefs: int = typer.Option(
        200,
        help="Maximum candidate brief structures to generate per drawing.",
    ),
    timeout_per_drawing: float = typer.Option(
        30,
        help="Timeout guard per drawing in seconds.",
    ),
    allow_unhealthy_research: bool = typer.Option(
        False,
        "--allow-unhealthy-research",
        help="Explicit research-only bypass; marks all output as overridden.",
    ),
) -> None:
    """Backtest the baseline brief generator on finished drawings."""
    engine = init_db(db)
    session_factory = get_session_factory(engine)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        task_id = progress.add_task("Preparing baseline brief backtest")

        def update_progress(update: dict[str, object]) -> None:
            progress.update(
                task_id,
                description=(
                    f"drawing={update.get('drawing_number')} "
                    f"candidate={update.get('candidate_index')}/"
                    f"{update.get('candidate_total')} "
                    f"elapsed={float(update.get('elapsed_time', 0)):.2f}s "
                    f"best={float(update.get('best_score', 0)):.6f}"
                ),
            )

        with session_factory() as session:
            try:
                result = run_brief_backtest(
                    session,
                    last=last,
                    bank=bank,
                    stake=stake,
                    category=category,
                    top_candidates=top_candidates,
                    max_candidate_briefs=max_candidate_briefs,
                    timeout_per_drawing=timeout_per_drawing,
                    progress_callback=update_progress,
                    allow_unhealthy_research=allow_unhealthy_research,
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
        progress.update(task_id, description="Baseline brief backtest complete")

    csv_path, markdown_path = write_brief_backtest_reports(result, last=last)
    _print_data_health_override(result.summary)
    print(_brief_backtest_summary_table(result.summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("backtest-strategies")
def backtest_strategies(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(500, help="Latest complete drawings to test."),
    holdout: int = typer.Option(150, help="Newest eligible holdout drawings."),
    bank: int = typer.Option(5000, help="Positive integer package budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    seed: int = typer.Option(42, help="Deterministic base seed."),
    top_count: int = typer.Option(1000, help="Exact top-probability candidates."),
    candidate_samples: int = typer.Option(3000, help="Candidate scenario samples."),
    mutation_limit: int = typer.Option(1000, help="Maximum mutation candidates."),
    optimization_samples: int = typer.Option(2000, help="Optimization scenarios."),
    validation_samples: int = typer.Option(5000, help="Validation scenarios."),
    timeout_per_drawing: float = typer.Option(
        30.0,
        help="Cooperative package-generation deadline per drawing.",
    ),
    manifest_in: str = typer.Option(
        ...,
        help="Required frozen manifest with exact drawing IDs and hashes.",
    ),
    allow_unhealthy_research: bool = typer.Option(
        False,
        "--allow-unhealthy-research",
        help="Explicit research-only bypass; marks all output as overridden.",
    ),
) -> None:
    """Compare baseline and direct package strategies on historical drawings."""
    config = StrategyConfig(
        bank=bank,
        stake=stake,
        category=category,
        seed=seed,
        top_count=top_count,
        candidate_samples=candidate_samples,
        mutation_limit=mutation_limit,
        optimization_samples=optimization_samples,
        validation_samples=validation_samples,
        timeout_per_drawing=timeout_per_drawing,
    )
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    try:
        frozen_manifest = load_strategy_experiment_manifest(manifest_in)
        code_version = _git_code_version()
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    if frozen_manifest["last"] != last:
        raise typer.BadParameter("Manifest last does not match --last.")
    if frozen_manifest["holdout_size"] != holdout:
        raise typer.BadParameter("Manifest holdout does not match --holdout.")
    if frozen_manifest["code_version"] != code_version:
        raise typer.BadParameter("Manifest code version does not match checkout.")
    if frozen_manifest["protocol_hash"] != strategy_protocol_hash(config):
        raise typer.BadParameter("Manifest protocol does not match configuration.")
    with session_factory() as session:
        try:
            drawing_ids = verify_strategy_experiment_manifest_data(
                session,
                frozen_manifest,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        task_id = progress.add_task("Preparing strategy backtest")

        def update_progress(update: dict[str, object]) -> None:
            progress.update(
                task_id,
                description=(
                    f"drawing={update.get('drawing_number')} "
                    f"{update.get('drawing_index')}/{update.get('drawing_total')} "
                    f"eligible={update.get('eligible')} "
                    f"skipped={update.get('skipped')} "
                    f"eta={float(update.get('eta_seconds', 0)):.1f}s"
                ),
            )

        with session_factory() as session:
            try:
                result = run_strategy_backtest(
                    session,
                    last=last,
                    holdout_size=holdout,
                    config=config,
                    progress_callback=update_progress,
                    drawing_ids=drawing_ids,
                    allow_unhealthy_research=allow_unhealthy_research,
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
        progress.update(task_id, description="Strategy backtest complete")

    csv_path, markdown_path = write_strategy_backtest_reports(result, last=last)
    _print_data_health_override(result.summary)
    print(_strategy_backtest_overview_table(result.summary))
    print(_strategy_holdout_table(result.summary["holdout"]))
    print(_strategy_decision_table(result.summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("diagnose-strategies")
def diagnose_strategies(
    manifest: str = typer.Option(
        ...,
        help="Frozen strategy experiment manifest.",
    ),
    backtest_csv: str = typer.Option(
        ...,
        "--backtest-csv",
        help="Frozen strategy backtest CSV.",
    ),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    report_dir: str = typer.Option("reports", help="Report output directory."),
) -> None:
    """Diagnose frozen strategies on the development segment only."""
    try:
        frozen_manifest = load_strategy_experiment_manifest(manifest)
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task("Preparing development diagnostics")

            def update_progress(update: dict[str, object]) -> None:
                progress.update(
                    task_id,
                    description=(
                        f"drawing_id={update.get('drawing_id')} "
                        f"{update.get('drawing_index')}/"
                        f"{update.get('drawing_total')}"
                    ),
                )

            with session_factory() as session:
                result = run_strategy_diagnostics(
                    session,
                    frozen_manifest,
                    backtest_csv,
                    progress_callback=update_progress,
                )
            progress.update(
                task_id,
                description="Development strategy diagnostics complete",
            )

        summary = summarize_strategy_diagnostics(result.rows)
        csv_path, markdown_path = write_strategy_diagnostics_reports(
            result,
            report_dir,
        )
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(_strategy_diagnostics_paired_table(summary))
    print(_strategy_diagnostics_transitions_table(summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("seal-hybrid-development")
def seal_hybrid_development_command(
    manifest: str = typer.Option(..., help="Frozen strategy experiment manifest."),
    backtest_csv: str = typer.Option(
        ..., "--backtest-csv", help="Full frozen strategy backtest CSV."
    ),
    output_manifest: str = typer.Option(
        ..., "--output-manifest", help="Sealed development manifest output."
    ),
    output_csv: str = typer.Option(
        ..., "--output-csv", help="Development-only CSV output."
    ),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
) -> None:
    """Seal the hybrid development inputs, results, protocol, and CSV."""
    input_paths = {
        Path(manifest).resolve(),
        Path(backtest_csv).resolve(),
        Path(db).resolve(),
    }
    output_paths = {
        Path(output_manifest).resolve(),
        Path(output_csv).resolve(),
    }
    if len(input_paths) != 3 or len(output_paths) != 2 or input_paths & output_paths:
        raise typer.BadParameter("Hybrid seal input and output paths must be distinct.")
    try:
        code_version = _git_code_version()
        frozen_manifest = load_strategy_experiment_manifest(manifest)
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            manifest_path, csv_path = seal_hybrid_development(
                session,
                frozen_manifest,
                backtest_csv,
                output_manifest,
                output_csv,
                code_version=code_version,
            )
    except (OSError, SQLAlchemyError, KeyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(f"Development seal written to {manifest_path} and {csv_path}")


@app.command("evaluate-hybrid")
def evaluate_hybrid(
    manifest: str = typer.Option(..., help="Sealed development manifest."),
    backtest_csv: str = typer.Option(
        ..., "--backtest-csv", help="Sealed development-only backtest CSV."
    ),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    report_dir: str = typer.Option("reports", help="Report output directory."),
) -> None:
    """Evaluate fixed hybrid packages on frozen development drawings only."""
    try:
        frozen_manifest = load_strategy_experiment_manifest(manifest)
        seal = frozen_manifest.get("hybrid_development_seal")
        if (
            not isinstance(seal, dict)
            or seal.get("hybrid_code_version") != _git_code_version()
        ):
            raise ValueError("Hybrid development code version does not match.")
        report_paths = {
            path.resolve()
            for path in hybrid_evaluation_report_paths(
                frozen_manifest,
                report_dir,
            )
        }
        input_paths = {
            Path(manifest).resolve(),
            Path(backtest_csv).resolve(),
            Path(db).resolve(),
        }
        if report_paths & input_paths:
            raise ValueError("Hybrid report and input paths must be distinct.")
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task_id = progress.add_task("Preparing hybrid development evaluation")

            def update_progress(update: dict[str, object]) -> None:
                progress.update(
                    task_id,
                    description=(
                        f"drawing_id={update.get('drawing_id')} "
                        f"{update.get('drawing_index')}/"
                        f"{update.get('drawing_total')}"
                    ),
                )

            with session_factory() as session:
                result = run_hybrid_evaluation(
                    session,
                    frozen_manifest,
                    backtest_csv,
                    progress_callback=update_progress,
                )
            progress.update(
                task_id,
                description="Hybrid development evaluation complete",
            )

        csv_path, markdown_path = write_hybrid_evaluation_reports(result, report_dir)
    except (OSError, SQLAlchemyError, KeyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(_hybrid_evaluation_table(result))
    print(f"Reports written to {csv_path} and {markdown_path}")


@app.command("freeze-strategy-experiment")
def freeze_strategy_experiment(
    output: str = typer.Option(..., help="Manifest JSON output path."),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(500, help="Eligible drawings to freeze."),
    holdout: int = typer.Option(150, help="Newest frozen holdout drawings."),
    exclude_latest: int = typer.Option(
        0,
        help="Exclude this many newest eligible drawings before freezing.",
    ),
    bank: int = typer.Option(5000, help="Primary package budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    seed: int = typer.Option(42, help="Deterministic base seed."),
    top_count: int = typer.Option(1000, help="Exact top-probability candidates."),
    candidate_samples: int = typer.Option(3000, help="Candidate scenario samples."),
    mutation_limit: int = typer.Option(1000, help="Maximum mutation candidates."),
    optimization_samples: int = typer.Option(2000, help="Optimization scenarios."),
    validation_samples: int = typer.Option(5000, help="Validation scenarios."),
    timeout_per_drawing: float = typer.Option(
        30.0,
        help="Cooperative drawing deadline.",
    ),
) -> None:
    """Freeze drawing IDs and hashes before evaluating strategy results."""
    config = StrategyConfig(
        bank=bank,
        stake=stake,
        category=category,
        seed=seed,
        top_count=top_count,
        candidate_samples=candidate_samples,
        mutation_limit=mutation_limit,
        optimization_samples=optimization_samples,
        validation_samples=validation_samples,
        timeout_per_drawing=timeout_per_drawing,
    )
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        try:
            path = freeze_strategy_experiment_manifest(
                session,
                last=last,
                holdout_size=holdout,
                config=config,
                code_version=_git_code_version(),
                output_path=output,
                exclude_latest=exclude_latest,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
    print(f"Manifest written to {path}")


def _summary_table(summary: dict[str, object]) -> Table:
    table = Table(title="Database Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in summary.items():
        table.add_row(key.replace("_", " ").title(), _format_value(value))
    return table


def _outcome_table(distribution: dict[str, dict[str, float | int]]) -> Table:
    table = Table(title="Outcome Distribution")
    table.add_column("Outcome")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")
    for outcome, stats in distribution.items():
        table.add_row(
            outcome,
            str(stats["count"]),
            f"{stats['percentage']:.2f}%",
        )
    return table


def _accuracy_table(accuracy: dict[str, float | int]) -> Table:
    table = Table(title="Crowd vs Bookmaker Accuracy")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in accuracy.items():
        label = key.replace("_", " ").title()
        table.add_row(label, _format_value(value, percent=key.endswith("_rate")))
    return table


def _value_buckets_table(buckets: dict[str, dict[str, float | int]]) -> Table:
    table = Table(title="Value Buckets")
    table.add_column("Bucket")
    table.add_column("Count", justify="right")
    table.add_column("Result Hit Rate", justify="right")
    for bucket, stats in buckets.items():
        table.add_row(
            bucket,
            str(stats["count"]),
            f"{stats['hit_rate']:.2f}%",
        )
    return table


def _event_diagnostics_table(rows: list[dict[str, object]]) -> Table:
    table = Table(title="Event Diagnostics")
    columns = [
        "drawing_id",
        "event_order",
        "event name",
        "score",
        "result",
        "pool_1",
        "pool_x",
        "pool_2",
        "bk_1",
        "bk_x",
        "bk_2",
        "pool_top",
        "bk_top",
        "pool_hit",
        "bk_hit",
    ]
    for column in columns:
        justify = "right" if column not in {"event name", "score"} else "left"
        table.add_column(column, justify=justify)

    for row in rows:
        table.add_row(
            _format_value(row["drawing_id"]),
            _format_value(row["event_order"]),
            _format_value(row["event_name"]),
            _format_value(row["score"]),
            _format_value(row["result"]),
            _format_value(row["pool_1"]),
            _format_value(row["pool_x"]),
            _format_value(row["pool_2"]),
            _format_value(row["bk_1"]),
            _format_value(row["bk_x"]),
            _format_value(row["bk_2"]),
            _format_value(row["pool_top"]),
            _format_value(row["bk_top"]),
            _format_value(row["pool_hit"]),
            _format_value(row["bk_hit"]),
        )
    return table


def _drawings_audit_table(drawings: dict[str, object]) -> Table:
    table = Table(title="Drawings")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("total", _format_value(drawings["total"]))
    table.add_row("finished", _format_value(drawings["finished"]))
    table.add_row("active", _format_value(drawings["active"]))

    other_statuses = drawings["other_statuses"]
    if isinstance(other_statuses, dict):
        for status, count in other_statuses.items():
            table.add_row(f"other: {status}", _format_value(count))
    return table


def _dimension_table(
    title: str,
    label: str,
    rows: list[dict[str, object]],
) -> Table:
    key = label.lower()
    table = Table(title=title)
    table.add_column(label)
    table.add_column("Count", justify="right")
    for row in rows:
        table.add_row(_format_value(row[key]), _format_value(row["count"]))
    return table


def _score_audit_table(score: dict[str, int]) -> Table:
    table = Table(title="Score")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("filled", _format_value(score["filled"]))
    table.add_row("empty", _format_value(score["empty"]))
    return table


def _quote_completeness_table(completeness: dict[str, dict[str, int]]) -> Table:
    table = Table(title="Quote Completeness")
    table.add_column("Field")
    table.add_column("Filled", justify="right")
    table.add_column("Missing", justify="right")
    for field, stats in completeness.items():
        table.add_row(
            field,
            _format_value(stats["filled"]),
            _format_value(stats["missing"]),
        )
    return table


def _probability_validation_table(
    validation: dict[str, dict[str, float | int]],
) -> Table:
    table = Table(title="Probability Validation")
    table.add_column("Provider")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Average", justify="right")
    table.add_column(">0.001", justify="right")
    table.add_column(">0.01", justify="right")
    table.add_column(">0.05", justify="right")
    for provider, stats in validation.items():
        table.add_row(
            provider,
            _format_value(stats["min"]),
            _format_value(stats["max"]),
            _format_value(stats["average"]),
            _format_value(stats["diff_gt_0_001"]),
            _format_value(stats["diff_gt_0_01"]),
            _format_value(stats["diff_gt_0_05"]),
        )
    return table


def _duplicates_table(duplicates: dict[str, int]) -> Table:
    table = Table(title="Duplicate Detection")
    table.add_column("Entity")
    table.add_column("Duplicate Groups", justify="right")
    table.add_row("drawings", _format_value(duplicates["drawings"]))
    table.add_row("events", _format_value(duplicates["events"]))
    return table


def _quality_score_table(score: float) -> Table:
    table = Table(title="Overall Data Quality Score")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("score", f"{score:.2f}/100")
    return table


def _data_health_summary_table(report: DataHealthReport) -> Table:
    summary = report.summary
    table = Table(title="Data Health Contract")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("contract version", report.contract_version)
    table.add_row("use case", report.use_case)
    table.add_row("strict", str(report.strict).lower())
    table.add_row("drawings", str(summary.total_drawings))
    table.add_row("healthy", str(summary.healthy_drawings))
    table.add_row("unhealthy", str(summary.unhealthy_drawings))
    table.add_row("gaps", str(summary.gap_count))
    table.add_row("duplicate numbers", str(summary.duplicate_number_count))
    table.add_row(
        "finished incomplete results",
        str(summary.inventory_counts["finished_incomplete_result_drawings"]),
    )
    table.add_row(
        "missing finished outcomes",
        str(summary.inventory_counts["missing_terminal_results_in_finished"]),
    )
    table.add_row(
        "reconciliation cooldown",
        str(summary.inventory_counts["reconciliation_cooldown_drawings"]),
    )
    table.add_row(
        "reconciliation quarantined",
        str(summary.inventory_counts["reconciliation_quarantined_drawings"]),
    )
    table.add_row("exit status", summary.exit_status)
    for reason, count in summary.reason_counts.items():
        table.add_row(f"reason:{reason}", str(count))
    return table


def _print_data_health_override(summary: Mapping[str, object]) -> None:
    if summary.get("data_health_override") is True:
        print(
            "[bold red]DATA-HEALTH OVERRIDE: RESEARCH ONLY; "
            "results are not production-eligible.[/bold red]"
        )


def _api_paths_table(rows: list[dict[str, object]]) -> Table:
    table = Table(title="API JSON Paths")
    table.add_column("Path")
    table.add_column("Type")
    table.add_column("Sample")
    for row in rows:
        table.add_row(
            _format_value(row["path"]),
            _format_value(row["type"]),
            _format_value(row["sample"]),
        )
    return table


def _drawing_reference_table(reference: DrawingReference) -> Table:
    table = Table(title="Drawing")
    table.add_column("Field")
    table.add_column("Value", justify="right")
    table.add_row("Drawing number", _format_value(reference.number))
    table.add_row("Internal id", _format_value(reference.drawing_id))
    table.add_row("Community", _format_value(reference.community))
    table.add_row("Status", _format_value(reference.status))
    return table


def _api_db_diff_table(diff: dict[str, list[str]]) -> Table:
    table = Table(title="API JSON vs Database Model")
    table.add_column("Category")
    table.add_column("Field")
    labels = {
        "json_not_stored": "JSON present, not stored",
        "stored_fields": "Stored in DB",
        "missing_mappings": "Mapped DB field missing in JSON",
    }
    for key in ("json_not_stored", "stored_fields", "missing_mappings"):
        values = diff[key] or [""]
        for value in values:
            table.add_row(labels[key], value)
    return table


def _validation_checks_table(result: dict[str, object]) -> Table:
    table = Table(title="Validation Checks")
    table.add_column("Check")
    table.add_column("Status", justify="right")
    table.add_row("RAW JSON vs SQLite", result["raw_vs_sqlite"]["status"])
    table.add_row("Analytics manual SQL comparison", result["analytics"]["status"])
    table.add_row("Result mapping", result["result_mapping"]["status"])
    table.add_row("Score mapping", result["score_mapping"]["status"])
    return table


def _validation_quote_totals_table(rows: list[dict[str, object]]) -> Table:
    table = Table(title="Quote Totals")
    table.add_column("Event", justify="right")
    table.add_column("pool1", justify="right")
    table.add_column("poolX", justify="right")
    table.add_column("pool2", justify="right")
    table.add_column("sum", justify="right")
    for row in rows:
        table.add_row(
            _format_value(row["event_order"]),
            _format_value(row["pool1"]),
            _format_value(row["poolX"]),
            _format_value(row["pool2"]),
            _format_value(row["sum"]),
        )
    return table


def _bk_vs_norm_metrics_table(result: dict[str, object]) -> Table:
    table = Table(title="BK vs Normalized Odds")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Events analyzed", _format_value(result["event_count"]))
    table.add_row("Comparisons", _format_value(result["comparison_count"]))
    table.add_row(
        "Average absolute error",
        f"{result['average_absolute_error']:.4f}%",
    )
    table.add_row("Maximum error", f"{result['maximum_error']:.4f}%")
    table.add_row("Correlation", f"{result['correlation']:.4f}")
    return table


def _bk_vs_norm_examples_table(rows: list[dict[str, object]]) -> Table:
    table = Table(title="Random Examples")
    table.add_column("Event")
    table.add_column("BK")
    table.add_column("Calculated")
    table.add_column("Difference")
    for row in rows:
        table.add_row(
            _format_value(row["event"]),
            _format_value(row["bk"]),
            _format_value(row["calculated"]),
            _format_value(row["difference"]),
        )
    return table


def _calibration_overall_table(overall: dict[str, object]) -> Table:
    table = Table(title="Bookmaker Calibration")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in overall.items():
        table.add_row(key.replace("_", " "), _format_value(value))
    return table


def _calibration_slices_table(result: dict[str, object]) -> Table:
    table = Table(title="Calibration Slices")
    table.add_column("Slice")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for section in (
        "pool_calibration",
        "pool_vs_bookmaker_bias",
        "draw_calibration",
        "favorites",
        "underdogs",
    ):
        values = result[section]
        if isinstance(values, dict):
            for key, value in values.items():
                table.add_row(section, key.replace("_", " "), _format_value(value))
    return table


def _reliability_table(rows: list[dict[str, object]], limit: int = 20) -> Table:
    table = Table(title="Reliability Table")
    table.add_column("Outcome")
    table.add_column("Bin")
    table.add_column("Count", justify="right")
    table.add_column("Observed", justify="right")
    table.add_column("Expected", justify="right")
    table.add_column("Error", justify="right")
    printed = 0
    for row in rows:
        if row["event_count"] == 0:
            continue
        table.add_row(
            _format_value(row["outcome"]),
            _format_value(row["bin"]),
            _format_value(row["event_count"]),
            _format_value(row["observed_frequency"]),
            _format_value(row["expected_frequency"]),
            _format_value(row["calibration_error"]),
        )
        printed += 1
        if printed == limit:
            break
    return table


def _brief_oracle_summary_table(summary: dict[str, object]) -> Table:
    table = Table(title="Brief Oracle Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "drawings_tested",
        "average_singles",
        "average_doubles",
        "average_triples",
        "median_full_variant_count",
        "p25_full_variant_count",
        "p50_full_variant_count",
        "p75_full_variant_count",
        "p90_full_variant_count",
        "average_actual_result_bk_probability",
    ):
        table.add_row(key.replace("_", " "), _format_value(summary[key]))
    return table


def _brief_oracle_rank_table(rank_frequency: dict[int, dict[str, object]]) -> Table:
    table = Table(title="Actual Result BK Rank")
    table.add_column("Rank", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("Percentage", justify="right")
    for rank, stats in rank_frequency.items():
        table.add_row(
            _format_value(rank),
            _format_value(stats["count"]),
            _format_value(stats["percentage"]),
        )
    return table


def _brief_oracle_entropy_table(
    entropy_by_cover_size: dict[int, dict[str, object]],
) -> Table:
    table = Table(title="Entropy by Required Cover Size")
    table.add_column("Cover Size", justify="right")
    table.add_column("Events", justify="right")
    table.add_column("Average Entropy", justify="right")
    for cover_size, stats in entropy_by_cover_size.items():
        table.add_row(
            _format_value(cover_size),
            _format_value(stats["event_count"]),
            _format_value(stats["average_entropy"]),
        )
    return table


def _budget_oracle_summary_table(summary: dict[str, object]) -> Table:
    table = Table(title="Budget-Constrained Brief Oracle")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "drawings_tested",
        "processed_count",
        "skipped_count",
        "timed_out_count",
        "oracle_average_best_hits",
        "oracle_hit13_count",
        "oracle_hit13_rate",
        "oracle_hit14_count",
        "oracle_hit14_rate",
        "oracle_hit15_count",
        "oracle_hit15_rate",
        "average_singles",
        "average_doubles",
        "average_triples",
        "average_package_size",
        "average_package_cost",
        "baseline_average_best_hits",
        "average_oracle_baseline_gap",
    ):
        table.add_row(key.replace("_", " "), _format_value(summary[key]))
    return table


def _budget_oracle_timing_table(summary: dict[str, object]) -> Table:
    table = Table(title="Budget Oracle Timing")
    table.add_column("Metric")
    table.add_column("Seconds", justify="right")
    for key in (
        "average_candidate_generation_time",
        "average_cover_generation_time",
        "average_verification_time",
        "average_total_time",
        "execution_time_seconds",
    ):
        table.add_row(key.replace("_", " "), _format_value(summary[key]))
    return table


def _budget_oracle_workload_table(summary: dict[str, object]) -> Table:
    table = Table(title="Budget Oracle Workload")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "generated_candidates_total",
        "unique_candidates_total",
        "cover_engine_calls_total",
        "cache_hits_total",
        "cache_misses_total",
        "pruned_by_cost_lower_bound_total",
        "pruned_by_dominance_total",
        "pruned_by_incumbent_bound_total",
        "cover_engine_calls_after_pruning_total",
        "average_brief_variant_count",
        "max_brief_variant_count",
        "average_cover_engine_call_duration",
    ):
        table.add_row(key.replace("_", " "), _format_value(summary[key]))
    return table


def _budget_oracle_slowest_candidates_table(summary: dict[str, object]) -> Table:
    table = Table(title="Slowest Budget Oracle Candidate Briefs")
    table.add_column("Drawing", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Variants", justify="right")
    table.add_column("Brief")
    records = summary.get("slowest_candidate_briefs", [])
    if not isinstance(records, list):
        return table
    for record in records[:10]:
        if not isinstance(record, dict):
            continue
        table.add_row(
            _format_value(record.get("drawing_number", "")),
            _format_value(record.get("duration", 0)),
            _format_value(record.get("brief_variants", 0)),
            str(record.get("brief", "")),
        )
    return table


def _budget_oracle_progress_description(update: dict[str, object]) -> str:
    candidate_index = update.get("candidate_index", 0)
    candidate_total = update.get("candidate_total", 0)
    return (
        f"drawing={update.get('drawing_number')} "
        f"{update.get('drawing_index')}/{update.get('drawing_total')} "
        f"candidate={candidate_index}/{candidate_total} "
        f"elapsed={float(update.get('elapsed_time', 0)):.1f}s "
        f"avg={float(update.get('average_time_per_drawing', 0)):.1f}s "
        f"eta={float(update.get('eta_seconds', 0)):.1f}s "
        f"best_hits={update.get('current_best_hits', 0)} "
        f"best_cost={update.get('current_best_cost', 0)} "
        f"processed={update.get('processed_count', 0)} "
        f"skipped={update.get('skipped_count', 0)} "
        f"timed_out={update.get('timed_out_count', 0)}"
    )


def _package_mvp_summary_table(result: object) -> Table:
    table = Table(title="MVP Covering Approximation")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("bank", _format_value(result.bank))
    table.add_row("stake", _format_value(result.stake))
    table.add_row("category", _format_value(result.category))
    table.add_row("max_errors", _format_value(result.max_errors))
    table.add_row("full brief size", _format_value(result.full_brief_size))
    table.add_row("selected coupons", _format_value(len(result.selected_coupons)))
    table.add_row("cost", _format_value(result.cost))
    table.add_row(
        "estimated coverage",
        f"{result.covered_variants} / {result.full_brief_variants} "
        f"({result.estimated_coverage:.2%})",
    )
    return table


def _package_mvp_coupons_table(coupons: list[str]) -> Table:
    table = Table(title="Selected Coupons")
    table.add_column("#", justify="right")
    table.add_column("Coupon")
    for index, coupon in enumerate(coupons, start=1):
        table.add_row(str(index), coupon)
    return table


def _cover_summary_table(result: dict[str, object], stake: int) -> Table:
    selected_coupons = result["selected_coupons"]
    coupon_count = len(selected_coupons) if isinstance(selected_coupons, list) else 0

    table = Table(title="Cover Package")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("full variants", _format_value(result["full_variants_count"]))
    table.add_row("selected coupons", _format_value(coupon_count))
    table.add_row("cost", _format_value(coupon_count * stake))
    table.add_row("coverage rate", f"{float(result['coverage_rate']):.2%}")
    return table


def _cover_coupons_table(coupons: list[str]) -> Table:
    table = Table(title="First 20 Coupons")
    table.add_column("#", justify="right")
    table.add_column("Coupon")
    for index, coupon in enumerate(coupons, start=1):
        table.add_row(str(index), coupon)
    return table


def _cover_benchmark_table(result: dict[str, object]) -> Table:
    table = Table(title="Cover Engine Benchmark")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "elapsed_seconds",
        "full_variants_count",
        "selected_coupons",
        "covered_variants_count",
        "coverage_rate",
    ):
        table.add_row(key.replace("_", " "), _format_value(result[key]))
    return table


def _ev_input_snapshot_table(result: EVPackageRun) -> Table:
    ev_input = result.ev_input
    table = Table(title="EV Input Snapshot")
    table.add_column("Field")
    table.add_column("Value", justify="right")
    rows = (
        ("drawing id", ev_input.drawing_id),
        ("drawing number", ev_input.drawing_number),
        ("fetched at", ev_input.fetched_at),
        ("pool sum", f"{ev_input.pool_sum:.6f}"),
        ("jackpot", f"{ev_input.jackpot:.6f}"),
        ("possible winnings", f"{ev_input.possible_winnings:.6f}"),
        ("possible winnings source", result.possible_winnings_source),
        ("jackpot source", result.jackpot_source),
        ("prize fund factor", f"{result.config.prize_fund_factor:.6f}"),
        ("probability source", "totobrief_bk (15/15)"),
        ("crowd joint model", "independent event marginals"),
    )
    for label, value in rows:
        table.add_row(label, str(value))
    return table


def _ev_package_summary_table(result: EVPackageRun) -> Table:
    package = result.package
    timing = result.timing_eligibility
    modeled_roi = "n/a" if package.modeled_roi is None else f"{package.modeled_roi:.6f}"
    table = Table(title="EV Package Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    rows = (
        ("decision", package.decision),
        ("requested bank", result.requested_bank),
        ("effective cap", result.effective_budget),
        ("selected coupons", len(package.coupons)),
        ("cost", package.cost),
        ("unused bank", package.unused_bank),
        ("unused requested bank", result.unused_requested_bank),
        ("expected payout", f"{package.expected_payout:.6f}"),
        ("modeled ROI", modeled_roi),
        ("self-dilution ratio", f"{result.self_dilution_ratio:.6f}"),
        ("model supported", "yes" if result.model_supported else "no"),
        ("timing status", timing.status),
        ("fingerprint match", "yes" if timing.fingerprint_match else "no"),
        ("target fingerprint", timing.target_fingerprint or "n/a"),
        ("timing reason", timing.reason),
        ("derived brief", " ".join(value or "-" for value in package.derived_brief)),
    )
    for label, value in rows:
        table.add_row(label, str(value))
    if result.model_warning is not None:
        table.add_row("warning", result.model_warning)
    return table


def _ev_top_coupons_table(result: EVPackageRun) -> Table:
    table = Table(title="Top 20 EV Coupons")
    table.add_column("Rank", justify="right")
    table.add_column("Coupon")
    table.add_column("Gross EV", justify="right")
    table.add_column("Net EV", justify="right")
    if result.timing_diagnostics_suppressed:
        return table
    for row in result.top_coupons:
        table.add_row(
            str(row.rank),
            row.coupon,
            f"{row.gross_ev:.12f}",
            f"{row.net_ev:.12f}",
        )
    return table


def _ev_benchmark_table(result: dict[str, object]) -> Table:
    table = Table(title="Exact EV Engine Benchmark")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    peak_memory = result["peak_memory_bytes"]
    rows = (
        ("event count", str(result["event_count"])),
        ("coupon count", str(result["coupon_count"])),
        ("elapsed time", f"{float(result['elapsed_seconds']):.6f} s"),
        (
            "peak memory",
            "unavailable"
            if peak_memory is None
            else f"{int(peak_memory) / 1024**2:.2f} MiB",
        ),
        ("minimum denominator", f"{float(result['minimum_denominator']):.12g}"),
        (
            "maximum sampled absolute error",
            f"{float(result['maximum_sampled_absolute_error']):.3e}",
        ),
        (
            "maximum sampled crowd-tail error",
            f"{float(result['maximum_sampled_crowd_tail_absolute_error']):.3e}",
        ),
        ("verification", str(result["verification"])),
    )
    for label, value in rows:
        table.add_row(label, value)
    return table


def _ev_backtest_summary_table(result: EVBacktestResult) -> Table:
    table = Table(title="Modeled EV Backtest Thresholds")
    table.add_column("Factor", justify="right")
    table.add_column("Bank", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Drawings", justify="right")
    table.add_column("PLAY", justify="right")
    table.add_column("NO BET", justify="right")
    table.add_column("Unsupported", justify="right")
    table.add_column("Skip", justify="right")
    table.add_column("Avg ROI", justify="right")
    table.add_column("Review")
    for row in result.summaries:
        roi = (
            "n/a"
            if row.average_package_modeled_roi is None
            else f"{row.average_package_modeled_roi:.4f}"
        )
        table.add_row(
            f"{row.prize_fund_factor:.2f}",
            str(row.bank),
            f"{row.threshold:.2f}",
            str(row.drawing_count),
            str(row.play_count),
            str(row.no_bet_count),
            str(row.unsupported_count),
            f"{row.skip_rate:.1%}",
            roi,
            "required" if row.model_review_required else "no",
        )
    return table


def _external_collection_table(
    result,
    prospective_result: ProspectiveCollectionResult | None = None,
) -> Table:
    table = Table(title="External Odds Collection")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    fallback_count = sum(
        row.probability_source == "totobrief_bk_fallback" for row in result.events
    )
    consensus_count = sum(
        row.probability_source == "external_consensus" for row in result.events
    )
    table.add_row("collection id", result.collection_id)
    table.add_row("drawing id", _format_value(result.drawing_id))
    table.add_row("drawing number", _format_value(result.drawing_number))
    table.add_row("provider", result.provider)
    table.add_row("status", result.status)
    table.add_row("events", _format_value(len(result.events)))
    table.add_row("external consensus", _format_value(consensus_count))
    table.add_row("fallback", _format_value(fallback_count))
    table.add_row("requests made", _format_value(result.requests_made))
    table.add_row("cache hits", _format_value(result.cache_hits))
    table.add_row("daily remaining", _format_value(result.daily_remaining))
    table.add_row("minute remaining", _format_value(result.minute_remaining))
    if prospective_result is not None:
        table.add_row("passes", _format_value(len(prospective_result.passes)))
        table.add_row(
            "base passes",
            _format_value(len(prospective_result.base_passes)),
        )
        table.add_row(
            "expansion passes",
            _format_value(len(prospective_result.expansion_passes)),
        )
        table.add_row("expanded", _format_value(prospective_result.expanded))
        table.add_row(
            "final horizon days",
            _format_value(prospective_result.final_horizon_days),
        )
        for item in prospective_result.passes:
            table.add_row(
                f"{item.phase} pass {item.phase_pass_number}",
                (
                    f"horizon={item.horizon_days} "
                    f"failed_schedule_dates="
                    f"{len(item.snapshot.failed_schedule_dates)} "
                    f"requests={item.snapshot.requests_made} "
                    f"cache_hits={item.snapshot.cache_hits} "
                    f"elapsed={item.elapsed_seconds:.2f}s"
                ),
            )
        table.add_row(
            "total requests",
            _format_value(prospective_result.total_requests),
        )
        table.add_row(
            "total cache hits",
            _format_value(prospective_result.total_cache_hits),
        )
        table.add_row(
            "requested schedule dates",
            _format_value(prospective_result.total_requested_schedule_dates),
        )
        table.add_row(
            "successful schedule dates",
            _format_value(prospective_result.total_successful_schedule_dates),
        )
        table.add_row(
            "failed schedule dates",
            _format_value(prospective_result.total_failed_schedule_dates),
        )
        eligibility = prospective_result.eligibility
        table.add_row("eligibility", eligibility.status)
        table.add_row(
            "eligibility span days",
            _format_value(eligibility.span_days),
        )
        table.add_row(
            "eligibility missing event orders",
            ",".join(str(order) for order in eligibility.missing_event_orders)
            or "none",
        )
        table.add_row(
            "eligibility start sources",
            (
                f"totobrief={eligibility.totobrief_count} "
                f"provider={eligibility.provider_count}"
            ),
        )
        table.add_row(
            "elapsed seconds",
            f"{prospective_result.elapsed_seconds:.2f}",
        )
        table.add_row("stop reason", prospective_result.stop_reason)
    return table


def _external_coverage_table(audit: CoverageAudit) -> Table:
    table = Table(title="External Odds Coverage")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("provider", audit.provider)
    table.add_row("drawings", _format_value(audit.drawings))
    table.add_row("events", _format_value(audit.total.target_count))
    table.add_row("unique match rate", f"{audit.total.unique_match_rate:.2%}")
    table.add_row(
        "reversed exact matches",
        _format_value(
            sum(row.match_orientation == "reversed" for row in audit.dispositions)
        ),
    )
    table.add_row("consensus rate", f"{audit.total.usable_consensus_rate:.2%}")
    table.add_row("fallback", _format_value(audit.total.fallback_count))
    table.add_row("ambiguous", _format_value(audit.total.ambiguous_count))
    table.add_row(
        "explicit dispositions",
        _format_value(audit.total.explicit_dispositions),
    )
    table.add_row("decision", audit.gate.decision)
    table.add_row(
        "reasons",
        ", ".join(audit.gate.reasons) if audit.gate.reasons else "none",
    )
    return table


def _external_error_message(error: Exception, *, secret: str) -> str:
    messages: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current)
        if secret:
            message = message.replace(secret, "[redacted]")
        if message and message not in messages:
            messages.append(message)
        current = current.__cause__ or current.__context__
    return ": ".join(messages) or "external provider operation failed"


def _brief_matches_table(matches: list[object], brief: list[str]) -> Table:
    table = Table(title="Baseline Brief Matches")
    table.add_column("#", justify="right")
    table.add_column("Match")
    table.add_column("Pool")
    table.add_column("BK")
    table.add_column("Selected cover")
    table.add_column("Reason")
    for match, pick in zip(matches, brief, strict=True):
        table.add_row(
            _format_value(match.event_order + 1),
            _format_value(match.name),
            _probability_triplet(match.pool),
            _probability_triplet(match.bk),
            pick,
            _format_value(match.reason),
        )
    return table


def _brief_summary_table(result: dict[str, object]) -> Table:
    table = Table(title="Baseline Brief Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("full brief size", _format_value(result["full_brief_size"]))
    table.add_row("package coupons", _format_value(len(result["selected_coupons"])))
    table.add_row("cost", _format_value(result["cost"]))
    table.add_row("category guarantee", _format_value(result["category_guarantee"]))
    table.add_row("brief probability", f"{float(result['brief_probability']):.6f}")
    table.add_row("coverage rate", f"{float(result['coverage_rate']):.2%}")
    table.add_row("value against crowd", f"{float(result['value_score']):.4f}")
    return table


def _probability_triplet(probabilities: dict[str, float]) -> str:
    return (
        f"1={probabilities['1']:.2%} "
        f"X={probabilities['X']:.2%} "
        f"2={probabilities['2']:.2%}"
    )


def _cover_verification_table(result: dict[str, object]) -> Table:
    table = Table(title="Cover Verification")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("total variants", _format_value(result["total_variants"]))
    table.add_row(
        "fully covered variants",
        _format_value(result["fully_covered_variants"]),
    )
    table.add_row("uncovered variants", _format_value(result["uncovered_variants"]))
    table.add_row(
        "worst minimum distance",
        _format_value(result["worst_minimum_distance"]),
    )
    table.add_row(
        "guarantee",
        "PASS" if result["guarantee_pass"] else "FAIL",
    )
    return table


def _cover_distance_distribution_table(distribution: dict[object, int]) -> Table:
    table = Table(title="Minimum Distance Distribution")
    table.add_column("Distance")
    table.add_column("Variants", justify="right")
    for distance in (0, 1, 2, "3+"):
        table.add_row(str(distance), _format_value(distribution[distance]))
    return table


def _uncovered_variants_table(variants: list[str]) -> Table:
    table = Table(title="First 20 Uncovered Variants")
    table.add_column("#", justify="right")
    table.add_column("Variant")
    for index, variant in enumerate(variants, start=1):
        table.add_row(str(index), variant)
    return table


def _backtest_summary_table(summary: dict[str, object]) -> Table:
    table = Table(title="MVP Backtest Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("drawings tested", _format_value(summary["drawings_tested"]))
    table.add_row("avg coupons", _format_value(summary["avg_coupons"]))
    table.add_row("avg cost", _format_value(summary["avg_cost"]))
    table.add_row(
        "hit_13 count/rate",
        f"{summary['hit_13_count']} / {summary['hit_13_rate']:.2f}%",
    )
    table.add_row(
        "hit_14 count/rate",
        f"{summary['hit_14_count']} / {summary['hit_14_rate']:.2f}%",
    )
    table.add_row(
        "hit_15 count/rate",
        f"{summary['hit_15_count']} / {summary['hit_15_rate']:.2f}%",
    )
    table.add_row("total cost", _format_value(summary["total_cost"]))
    table.add_row("total payout", _format_value(summary["total_payout"]))
    table.add_row("ROI", _format_value(summary["roi"], percent=True))
    return table


def _brief_backtest_summary_table(summary: dict[str, object]) -> Table:
    table = Table(title="Baseline Brief Backtest Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("drawings tested", _format_value(summary["drawings_tested"]))
    table.add_row(
        "brief containment rate",
        _format_value(summary["brief_containment_rate"], percent=True),
    )
    table.add_row(
        "average uncovered outcomes",
        _format_value(summary["average_uncovered_outcomes"]),
    )
    table.add_row(
        "best coupon hits",
        _format_value(summary["average_best_coupon_hits"]),
    )
    table.add_row(
        "hit13",
        f"{summary['hit_13_count']} / {summary['hit_13_rate']:.2f}%",
    )
    table.add_row(
        "hit14",
        f"{summary['hit_14_count']} / {summary['hit_14_rate']:.2f}%",
    )
    table.add_row(
        "hit15",
        f"{summary['hit_15_count']} / {summary['hit_15_rate']:.2f}%",
    )
    table.add_row(
        "average package size",
        _format_value(summary["average_package_size"]),
    )
    table.add_row(
        "average package cost",
        _format_value(summary["average_package_cost"]),
    )
    table.add_row(
        "average brief variants",
        _format_value(summary["average_brief_variants"]),
    )
    table.add_row("timed out", _format_value(summary["timed_out_count"]))
    table.add_row(
        "avg candidate generation",
        f"{summary['average_candidate_generation_time']:.4f}s",
    )
    table.add_row("avg scoring", f"{summary['average_scoring_time']:.4f}s")
    table.add_row("avg cover", f"{summary['average_cover_time']:.4f}s")
    table.add_row(
        "avg total per drawing",
        f"{summary['average_total_time_per_drawing']:.4f}s",
    )
    table.add_row(
        "execution time",
        f"{summary['execution_time_seconds']:.4f}s",
    )
    return table


def _strategy_backtest_overview_table(summary: dict[str, object]) -> Table:
    table = Table(title="Direct Strategy Backtest")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in (
        "eligible_drawings",
        "evaluated_drawings",
        "skipped_drawings",
        "development_drawings",
        "holdout_drawings",
        "timed_out_drawings",
    ):
        table.add_row(key.replace("_", " "), _format_value(summary.get(key, 0)))
    return table


def _strategy_holdout_table(
    holdout: dict[str, dict[str, object]],
) -> Table:
    table = Table(title="Holdout Strategies")
    table.add_column("Strategy")
    table.add_column("Hit13", justify="right")
    table.add_column("Hit14", justify="right")
    table.add_column("Hit15", justify="right")
    table.add_column("Avg best hits", justify="right")
    table.add_column("Avg cost", justify="right")
    for strategy in (
        "baseline_brief",
        "top_probability",
        "weighted_coverage",
    ):
        metrics = holdout[strategy]
        table.add_row(
            strategy,
            _format_value(metrics["hit13_count"]),
            _format_value(metrics["hit14_count"]),
            _format_value(metrics["hit15_count"]),
            _format_value(metrics["average_best_hits"]),
            _format_value(metrics["average_package_cost"]),
        )
    return table


def _strategy_decision_table(summary: dict[str, object]) -> Table:
    table = Table(title="Paired Holdout Decision")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row(
        "hit13 difference (pp)",
        _format_value(summary["paired_hit13_difference_pp"]),
    )
    table.add_row(
        "95% interval",
        (
            f"[{summary['paired_hit13_ci_low_pp']}, "
            f"{summary['paired_hit13_ci_high_pp']}]"
        ),
    )
    table.add_row("strategy status", _format_value(summary["strategy_status"]))
    return table


def _strategy_diagnostics_paired_table(summary: dict[str, object]) -> Table:
    comparison = summary["weighted_vs_top"]
    differences = summary["weighted_minus_top_best_hits"]
    table = Table(title="Development Strategy Diagnostics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("drawings", _format_value(summary["drawing_count"]))
    for key in ("wins", "ties", "losses"):
        table.add_row(f"weighted vs top {key}", _format_value(comparison[key]))
    for key in ("mean", "p25", "p50", "p75"):
        table.add_row(
            f"weighted - top {key}",
            _format_value(differences[key]),
        )
    return table


def _strategy_diagnostics_transitions_table(
    summary: dict[str, object],
) -> Table:
    transitions = summary["paired_13_transitions"]
    table = Table(title="Development 13+ Transitions")
    table.add_column("Transition")
    table.add_column("Drawings", justify="right")
    for key in ("neither", "both", "top_only", "weighted_only"):
        table.add_row(key, _format_value(transitions[key]))
    return table


def _hybrid_evaluation_table(result) -> Table:
    summary = result.summary
    top_total = summary["strategies"]["top_probability"]["total"]
    selected_fraction = (
        "none"
        if result.decision.selected_core_fraction is None
        else f"{result.decision.selected_core_fraction:.2f}"
    )
    table = Table(title="Hybrid Development Evaluation")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Development drawings", _format_value(summary["drawing_count"]))
    table.add_row("Top probability 13+", _format_value(top_total["hit_13"]))
    table.add_row("Operational failures", _format_value(summary["failure_count"]))
    table.add_row("Decision", result.decision.status)
    table.add_row("Selected core fraction", selected_fraction)
    return table


def _parse_csv_ints(value: str, name: str) -> tuple[int, ...]:
    parts = _csv_parts(value, name)
    try:
        parsed = tuple(int(part) for part in parts)
    except ValueError as error:
        raise ValueError(f"{name} must be comma-separated integers") from error
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{name} must not contain duplicate values")
    return parsed


def _parse_csv_floats(value: str, name: str) -> tuple[float, ...]:
    parts = _csv_parts(value, name)
    try:
        parsed = tuple(float(part) for part in parts)
    except ValueError as error:
        raise ValueError(f"{name} must be comma-separated numbers") from error
    if not all(math.isfinite(item) for item in parsed):
        raise ValueError(f"{name} must contain finite numbers")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{name} must not contain duplicate values")
    return parsed


def _csv_parts(value: str, name: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be comma-separated values")
    parts = tuple(part.strip() for part in value.split(","))
    if not parts or any(not part for part in parts):
        raise ValueError(f"{name} must not contain empty values")
    return parts


def _git_code_version() -> str:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Unable to resolve the Git code version.") from error
    if dirty:
        raise ValueError("Experiment freeze and evaluation require a clean checkout.")
    return revision


def _format_value(value: object, percent: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        suffix = "%" if percent else ""
        return f"{value:.2f}{suffix}"
    return str(value)


if __name__ == "__main__":
    app()
