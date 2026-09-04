import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
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
    write_drawing_detail_cache,
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
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    bound_selection_context,
    selection_context_sha256,
    selection_probability_input_sha256,
)
from toto_ai.ev.reports import write_ev_backtest_reports, write_ev_package_reports
from toto_ai.external_odds.api_sports import APISportsClient, APISportsError
from toto_ai.external_odds.audit import CoverageAudit, audit_external_coverage
from toto_ai.external_odds.collection import (
    collect_open_external_odds,
    pinned_revalidation_is_ready,
    resolve_open_target,
)
from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.eligibility import DrawingEligibility, target_fingerprint
from toto_ai.external_odds.goal_api import (
    GoalAPIClient,
    GoalAPIConfig,
    load_goal_api_key,
)
from toto_ai.external_odds.independent_schedule_consensus import (
    promote_independent_schedule_consensus,
)
from toto_ai.external_odds.matching import load_aliases, load_reviewed_alias_names
from toto_ai.external_odds.preparation import (
    DrawingPreparationResult,
    _baseline_probability_input_sha256,
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
    REVIEWED_SCHEDULE_MAX_AGE,
    load_reviewed_schedule_catalog,
    revalidate_reviewed_catalog,
    reviewed_catalog_input_paths,
)
from toto_ai.external_odds.schedule_consensus import (
    promote_uefa_sofascore_consensus,
)
from toto_ai.external_odds.schedule_evidence import (
    DEFAULT_SCHEDULE_EVIDENCE_PATH,
    ScheduleEvidenceIntegrityError,
    load_bound_schedule_evidence_ledger,
)
from toto_ai.external_odds.schedule_evidence_admin import (
    DEFAULT_REVIEWS_DIR,
    DEFAULT_SNAPSHOTS_DIR,
    review_prepared_schedule_evidence,
    schedule_evidence_status,
    verify_schedule_evidence,
)
from toto_ai.external_odds.schedule_source_collector import (
    collect_schedule_source_candidates,
)
from toto_ai.external_odds.storage import load_current_drawing_eligibility
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import (
    DrawingEventPinRecord,
    load_ready_pin_set,
    load_ready_pin_set_reviewed_catalog_hash,
    seed_reviewed_alias_config,
)
from toto_ai.external_odds.the_odds_api import TheOddsAPIClient, TheOddsAPIError
from toto_ai.external_odds.the_odds_checkpoints import collect_shadow_checkpoint
from toto_ai.external_odds.the_odds_shadow import (
    load_the_odds_api_key,
    write_the_odds_shadow_reports,
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
    cleanup_post_draw_launch_agent,
    complete_post_draw_review,
    import_prebet_package_manifest,
    load_post_draw_delivery,
    load_post_draw_plan,
    load_review_request,
    prepare_post_draw_scheduler_artifacts,
    record_post_draw_delivery_receipt,
    resolve_explicit_drawing,
    retry_post_draw_delivery,
    run_post_draw,
    run_post_draw_plan,
    settle_package_file,
    sync_finished_drawing,
    transition_review_request,
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
from toto_ai.operations.post_draw_attribution import (
    PENDING_RESULTS,
    generate_post_draw_attribution_reports,
)
from toto_ai.operations.reconciliation import (
    ReconciliationConfig,
    reconcile_finished_drawings,
    repair_from_canonical_raw,
)
from toto_ai.operations.scheduler_status import (
    scheduler_status,
    watch_scheduler_status,
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
from toto_ai.optimizer.hybrid_replay import execute_historical_hybrid_replay
from toto_ai.optimizer.quality_replay import (
    execute_quality_replay,
    load_historical_final_input,
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
from toto_ai.optimizer.strategy_execution import (
    execute_final_input_category_hit_comparison,
    execute_final_input_comparison,
)
from toto_ai.optimizer.strategy_historical_benchmark import (
    historical_ev_config,
    run_strict_historical_benchmark,
    write_strict_historical_benchmark_reports,
)
from toto_ai.optimizer.strategy_legacy_benchmark import (
    benchmark_legacy_retrospective_cases,
    load_legacy_retrospective_cases,
    write_legacy_retrospective_benchmark_reports,
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
from toto_ai.project_git import ProjectGitError, run_project_git
from toto_ai.runner import (
    DEFAULT_MINIMUM_GROSS_EV,
    MORNING_DEFERRED_EXIT_CODE,
    MORNING_IDENTITY_DRIFT_EXIT_CODE,
    SCHEDULER_INTEGRITY_EXIT_CODE,
    SCHEDULER_SCHEMA_VERSION,
    AppliedTimingOverrideEvent,
    CommandSchedulerPhaseRunner,
    DrawingRunnerConfig,
    DrawingRunPublication,
    MorningDispatchConfig,
    MorningExpectedIdentity,
    MorningIdentityDriftError,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    OfflineReplayProvenance,
    PinnedDrawing,
    RunnerTargetMismatch,
    RunnerTimingResolution,
    SchedulerError,
    SchedulerIntegrityError,
    SimulatedSchedulerPhaseRunner,
    TimingOverrideAudit,
    VirtualSchedulerClock,
    activate_scheduler_launch_agent,
    authorize_experimental_manual_release,
    build_scheduler_plan,
    clone_scheduler_plan_for_recovery,
    dispatch_morning,
    drawing_run_candidate_paths,
    execute_scheduler_plan,
    execute_scheduler_preflight_only,
    execute_scheduler_tick,
    export_operator_package,
    export_paper_package,
    load_paper_package,
    load_scheduler_plan,
    pin_drawing,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
    publish_drawing_run_artifacts,
    run_drawing,
    run_drawing_from_final_input,
    scheduler_plan_json,
    validate_scheduler_final_runtime_budget,
    write_drawing_run_reports,
)
from toto_ai.runner.conservative_cutoff import (
    NoQualifyingKickoffEvidenceError,
    conservative_cutoff_evidence_sha256,
    derive_conservative_cutoff,
    load_conservative_cutoff_evidence,
    write_conservative_cutoff_evidence,
)
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.offline_replay import (
    OfflineReplayInputs,
    OfflineScheduleProvider,
    load_offline_replay_inputs,
    resolve_offline_replay_paths,
)
from toto_ai.runner.operational_selection import load_verified_operational_cutoffs
from toto_ai.runner.preflight_retry_scheduler import (
    cleanup_preflight_retry_launch_agent,
    install_preflight_retry_launch_agent,
    prepare_preflight_retry_artifacts,
)
from toto_ai.runner.preflight_status import build_preflight_status
from toto_ai.runner.training_package import (
    TrainingPackageDeferred,
    ensure_scheduler_training_package,
)
from toto_ai.sports_stats.final_hybrid_comparison import (
    execute_final_hybrid_comparison,
)
from toto_ai.sports_stats.final_hybrid_sidecar import (
    activate_parallel_sidecar_launch_agent,
    authorize_parallel_manual_release,
    prepare_parallel_sidecar_artifacts,
    run_final_hybrid_sidecar,
)
from toto_ai.sports_stats.goal_probe_collection import (
    collect_goal_probe_input,
    ensure_goal_probe_input,
)
from toto_ai.sports_stats.goal_probe_research import (
    load_goal_probe_shadow,
    run_goal_probe_package_comparison,
)
from toto_ai.sports_stats.operation import (
    collect_and_store_sports_stats,
    load_api_sports_key,
    parse_historical_as_of,
)
from toto_ai.sports_stats.preliminary_comparison import (
    compare_preliminary_packages,
)
from toto_ai.sports_stats.probabilities import (
    load_shadow_probability_artifact,
    write_shadow_probability_artifact,
)
from toto_ai.sports_stats.shadow_operation import (
    build_and_write_sports_probability_shadow,
    evaluate_stored_sports_probability_shadow,
)
from toto_ai.sports_stats.v2 import build_sports_v2_shadow_artifact
from toto_ai.totobrief_time import parse_totobrief_timestamp

app = typer.Typer(help="TotoBrief API commands.")


class _ReplayCommandProgress:
    """Emit phase changes and periodic heartbeats for a long replay command."""

    def __init__(
        self,
        *,
        drawing_number: int,
        interval_seconds: float = 10.0,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        if type(drawing_number) is not int or drawing_number <= 0:
            raise ValueError("replay drawing number must be a positive integer")
        if interval_seconds <= 0.0 or interval_seconds >= 30.0:
            raise ValueError(
                "replay heartbeat interval must be between 0 and 30 seconds"
            )
        self._drawing_number = drawing_number
        self._interval_seconds = float(interval_seconds)
        self._emit_line = typer.echo if emit is None else emit
        self._started_at = 0.0
        self._model = "all"
        self._phase = "initializing"
        self._status = "running"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_ReplayCommandProgress":
        self._started_at = time.monotonic()
        self._emit("phase")
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"replay-progress-{self._drawing_number}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is not None:
            with self._lock:
                self._status = "failed"
            self._emit("phase")
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def update(self, payload: Mapping[str, object]) -> None:
        """Adopt the latest replay phase and print it immediately."""

        with self._lock:
            drawing_number = payload.get("drawing_number", self._drawing_number)
            if type(drawing_number) is int and drawing_number > 0:
                self._drawing_number = drawing_number
            self._model = str(payload.get("model", self._model))
            self._phase = str(payload.get("phase", self._phase))
            self._status = str(payload.get("status", self._status))
        self._emit("phase")

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self._emit("heartbeat")

    def _emit(self, kind: str) -> None:
        with self._lock:
            drawing_number = self._drawing_number
            model = self._model
            phase = self._phase
            status = self._status
        elapsed = max(time.monotonic() - self._started_at, 0.0)
        self._emit_line(
            "replay-progress "
            f"drawing={drawing_number} model={model} phase={phase} "
            f"status={status} elapsed={elapsed:.2f}s kind={kind}"
        )


def _replay_drawing_number(final_input: Path) -> int:
    payload = json.loads(final_input.read_text(encoding="utf-8"))
    drawing_number = payload.get("drawing_number")
    if type(drawing_number) is not int or drawing_number <= 0:
        raise ValueError("final input does not contain a valid drawing_number")
    return drawing_number


def _sports_seed_as_of(
    *,
    drawing_id: int,
    requested_as_of: datetime,
    raw_cache_dir: Path,
    project_root: Path,
) -> datetime:
    """Align a reused sports snapshot with the current immutable detail cache."""

    observed = datetime.now(timezone.utc)
    cache = load_drawing_detail_cache(
        drawing_id,
        cache_dir=raw_cache_dir,
        max_age_seconds=None,
        now=max(observed, requested_as_of),
        allowed_root=project_root,
    )
    return max(requested_as_of, cache.fetched_at)


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
    if reference.ended_at is not None:
        cached_deadline = parse_totobrief_timestamp(
            data.get("ended_at"),
            community=str(data.get("name") or reference.community or "").strip()
            or None,
            field_name="synchronized target cache deadline",
        )
        reference_deadline = parse_totobrief_timestamp(
            reference.ended_at,
            community=reference.community,
            field_name="stored target cache deadline",
        )
        if cached_deadline != reference_deadline:
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


@app.command("post-draw-attribution")
def post_draw_attribution_command(
    settled_drawing: str = typer.Option(..., "--settled-drawing"),
    package_dir: str = typer.Option(
        ...,
        "--package-dir",
        help=(
            "Generated package directory containing package.csv, "
            "package-archive.json and final-input.json."
        ),
    ),
    operator_result: str = typer.Option(
        ...,
        "--operator-result",
        help="Hash-bound scheduler schema-v3 PLAY operator-result.json.",
    ),
    output_dir: str = typer.Option(..., "--output-dir"),
) -> None:
    """Attribute a settled generated package; never creates betting artifacts."""

    try:
        report, paths = generate_post_draw_attribution_reports(
            settled_drawing_file=settled_drawing,
            package_dir=package_dir,
            operator_result_file=operator_result,
            output_dir=output_dir,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_id": report["identity"]["drawing_id"],
                "drawing_number": report["identity"]["drawing_number"],
                "excluded_event_orders": report["result_classification"][
                    "excluded_event_orders"
                ],
                "pending_event_orders": report["result_classification"][
                    "pending_event_orders"
                ],
                "reports": paths.to_dict(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if report["status"] == PENDING_RESULTS:
        raise typer.Exit(code=2)


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
    typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
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
    plan: str | None = typer.Option(None, "--plan"),
    package_file: str | None = typer.Option(None, "--package-file"),
    state_file: str | None = typer.Option(None, "--state-file"),
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
    if plan is not None:
        if any(
            value is not None
            for value in (package_file, state_file, drawing_id, drawing_number)
        ):
            raise typer.BadParameter(
                "--plan cannot be combined with package/identity/state options"
            )
        try:
            state = run_post_draw_plan(
                get_session_factory(init_db(db)),
                TotoBriefClient(),
                plan_path=plan,
                notifier=_post_draw_desktop_notifier,
            )
        except (KeyError, OSError, SQLAlchemyError, TypeError, ValueError) as error:
            raise typer.BadParameter(str(error)) from error
        typer.echo(json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True))
        loaded_plan = load_post_draw_plan(plan)
        if loaded_plan.get("automation_installation") is True and (
            state.status in {"complete", "blocked"}
            or state.attempts >= state.max_attempts
        ):
            cleanup_post_draw_launch_agent(plan)
        if state.status != "complete":
            raise typer.Exit(code=2 if state.status == "pending" else 1)
        return
    if (drawing_id is None) == (drawing_number is None):
        raise typer.BadParameter("use exactly one of --drawing-id or --drawing-number")
    if package_file is None or state_file is None:
        raise typer.BadParameter("legacy mode requires --package-file and --state-file")
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


def _post_draw_desktop_notifier(message: str) -> None:
    """Publish a local macOS notification without exposing project data."""

    if sys.platform != "darwin":
        raise RuntimeError("desktop post-draw notification requires macOS")
    subprocess.run(
        (
            "/usr/bin/osascript",
            "-e",
            "on run argv",
            "-e",
            'display notification (item 1 of argv) with title "TotoAI post-draw"',
            "-e",
            "end run",
            message,
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


@app.command("post-draw-plan")
def post_draw_plan_command(
    package_file: str | None = typer.Option(None, "--package-file"),
    paper_result_file: str | None = typer.Option(None, "--paper-result-file"),
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
            paper_result_file=paper_result_file,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    print(f"Plan: {plan}")
    print(f"Wrapper: {wrapper}")
    print(f"LaunchAgent candidate: {plist}")
    print("Artifacts were generated only; nothing was installed and no bet is placed.")


@app.command("post-draw-review-status")
def post_draw_review_status_command(
    request_file: str = typer.Option(..., "--request-file"),
) -> None:
    """Show one hash-verified post-draw review request."""

    try:
        request = load_review_request(request_file)
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    delivery = (
        load_post_draw_delivery(request_file)
        if request["status"] == "REVIEW_COMPLETE"
        else None
    )
    payload = {
        **request,
        "unacknowledged": request["status"] == "AWAITING_USER_REVIEW",
        "owner_delivery_status": (
            "not_ready" if delivery is None else delivery["status"]
        ),
        "owner_delivered": (
            delivery is not None and delivery["status"] == "delivered"
        ),
        "delivery_retryable": (
            False if delivery is None else delivery["retryable"]
        ),
        "delivery_record_sha256": (
            None if delivery is None else delivery["record_sha256"]
        ),
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@app.command("post-draw-review-transition")
def post_draw_review_transition_command(
    request_file: str = typer.Option(..., "--request-file"),
    action: str = typer.Option(..., "--action"),
    at: str = typer.Option(..., "--at"),
    postmortem_file: str | None = typer.Option(None, "--postmortem-file"),
) -> None:
    """Explicitly request, skip, or complete one post-draw review."""

    try:
        transitioned_at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if transitioned_at.tzinfo is None or transitioned_at.utcoffset() is None:
            raise ValueError("--at must be timezone-aware")
        if action in {"request", "skip"}:
            result = transition_review_request(
                request_file,
                transition=action,
                transitioned_at=transitioned_at,
            )
        elif action == "complete":
            if postmortem_file is None:
                raise ValueError("complete requires --postmortem-file")
            result = complete_post_draw_review(
                request_file,
                postmortem_path=postmortem_file,
                completed_at=transitioned_at,
            )
        else:
            raise ValueError("--action must be request, skip, or complete")
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@app.command("post-draw-review-delivery")
def post_draw_review_delivery_command(
    request_file: str = typer.Option(..., "--request-file"),
    action: str = typer.Option(..., "--action"),
    at: str = typer.Option(..., "--at"),
    receipt_file: str | None = typer.Option(None, "--receipt-file"),
) -> None:
    """Retry delivery or bind a durable owner-visible delivery receipt."""

    try:
        observed_at = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("--at must be timezone-aware")
        if action == "retry":
            if receipt_file is not None:
                raise ValueError("retry does not accept --receipt-file")
            result = retry_post_draw_delivery(
                request_file,
                attempted_at=observed_at,
                notifier=_post_draw_desktop_notifier,
            )
        elif action == "receipt":
            if receipt_file is None:
                raise ValueError("receipt requires --receipt-file")
            result = record_post_draw_delivery_receipt(
                request_file,
                receipt_path=receipt_file,
                recorded_at=observed_at,
            )
        else:
            raise ValueError("--action must be retry or receipt")
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


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
    schedule_evidence_ledger_sha256: str | None = None,
    schedule_evidence_semantic_hash: str | None = None,
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
        selection_provenance=(
            None
            if schedule_evidence_ledger_sha256 is None
            or schedule_evidence_semantic_hash is None
            else PackageSelectionProvenance(
                probability_snapshot_sha256=hashlib.sha256(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                probability_input_sha256=selection_probability_input_sha256(
                    tuple(event.bk_probabilities for event in observed.target.events)
                ),
                schedule_evidence_ledger_sha256=(schedule_evidence_ledger_sha256),
                schedule_evidence_semantic_hash=(schedule_evidence_semantic_hash),
                selection_context=bound_selection_context(config),
                selection_context_sha256=selection_context_sha256(config),
            )
        ),
    )


def _api_sports_provider_factory(
    api_key: str,
    quota_reserve: int,
    *,
    schedule_cache_dir: Path | None = None,
) -> Callable[[Path], APISportsClient]:
    return lambda cache_dir: APISportsClient(
        api_key,
        cache_dir=cache_dir,
        schedule_cache_dir=schedule_cache_dir,
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
    schedule_evidence_ledger: Path
    schedule_evidence_ledger_sha256: str
    schedule_evidence_semantic_hash: str


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
    expected_reviewed_catalog_hash: str | None = None,
    schedule_evidence_ledger: str | Path = DEFAULT_SCHEDULE_EVIDENCE_PATH,
    expected_schedule_evidence_sha256: str | None = None,
    expected_schedule_evidence_semantic_hash: str | None = None,
    systematic_resolution: bool = True,
    refresh_probability_evidence: bool = False,
) -> _RunnerResources:
    bound_ledger = load_bound_schedule_evidence_ledger(
        Path(schedule_evidence_ledger),
        expected_content_sha256=expected_schedule_evidence_sha256,
        expected_semantic_hash=expected_schedule_evidence_semantic_hash,
    )
    ledger_content_sha256 = hashlib.sha256(bound_ledger.path.read_bytes()).hexdigest()
    reviewed_catalog = (
        None
        if reviewed_schedule_catalog is None
        else load_reviewed_schedule_catalog(
            Path(reviewed_schedule_catalog),
            evaluated_at=preflight_at,
            max_age=REVIEWED_SCHEDULE_MAX_AGE,
        )
    )
    reviewed_input_paths = (
        ()
        if reviewed_catalog is None
        else reviewed_catalog_input_paths(reviewed_catalog)
    )
    # ``expected_reviewed_catalog_hash`` is the hash of the reviewed evidence
    # selected into the canonical pin set, not the semantic hash of the whole
    # reviewed catalog.  A catalog can legitimately contain records that are
    # not selected for this drawing, so comparing those two different hash
    # domains rejects valid scheduler-bound inputs.  The catalog bytes are
    # independently bound by the scheduler plan and the selected-evidence hash
    # is verified by ``load_ready_pin_set`` below.
    expected_pin_set_hash = (
        reviewed_catalog.semantic_hash
        if reviewed_catalog is not None and expected_reviewed_catalog_hash is None
        else expected_reviewed_catalog_hash
    )
    candidate_paths = drawing_run_candidate_paths(
        config,
        target,
        preflight_at,
        report_dir,
    )
    protected_paths = tuple(
        path
        for path in (
            db,
            aliases,
            timing_overrides,
            bound_ledger.path,
            *reviewed_input_paths,
        )
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
        loader_kwargs = {
            "drawing_id": target.target.drawing_id,
            "drawing_fingerprint": target.fingerprint,
            "expected_probability_sha256": preparation_probability_sha256(
                tuple(event.bk_probabilities for event in target.target.events)
            ),
            "expected_market_probability_sha256": (
                _baseline_probability_input_sha256(target.target)
            ),
            "as_of": preflight_at,
            "expected_reviewed_catalog_hash": expected_pin_set_hash,
        }
        prepared_pins = load_ready_pin_set(session_factory, **loader_kwargs)
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
        schedule_evidence_ledger=bound_ledger.path,
        schedule_evidence_ledger_sha256=ledger_content_sha256,
        schedule_evidence_semantic_hash=bound_ledger.semantic_hash,
    )


def _utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expected_deadline(value: str) -> datetime:
    message = "expected-deadline must be a timezone-aware ISO-8601 datetime"
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(message) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(message)
    return parsed.astimezone(timezone.utc)


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
    expected_reviewed_catalog_hash: str | None = typer.Option(
        None, "--expected-reviewed-catalog-hash"
    ),
    schedule_evidence_ledger: str = typer.Option(
        str(DEFAULT_SCHEDULE_EVIDENCE_PATH),
        "--schedule-evidence-ledger",
    ),
    expected_schedule_evidence_sha256: str | None = typer.Option(
        None, "--expected-schedule-evidence-sha256"
    ),
    expected_schedule_evidence_semantic_hash: str | None = typer.Option(
        None, "--expected-schedule-evidence-semantic-hash"
    ),
    quota_reserve: int = typer.Option(10, min=0),
    max_passes: int = typer.Option(3, min=1),
    max_expansion_passes: int = typer.Option(3, min=1),
    retry_delay_seconds: float = typer.Option(65.0, min=0.0),
    cache_root: str | None = typer.Option(None),
    shared_schedule_cache_root: str | None = typer.Option(
        None,
        "--shared-schedule-cache-root",
    ),
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
    if (expected_schedule_evidence_sha256 is None) != (
        expected_schedule_evidence_semantic_hash is None
    ):
        raise typer.BadParameter(
            "both expected schedule-evidence hashes must be supplied together"
        )
    try:
        resolved_schedule_evidence_ledger = resolve_contained_path(
            schedule_evidence_ledger,
            allowed_root=Path.cwd(),
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
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
        bound_scheduler_plan = (
            None if scheduler_plan is None else load_scheduler_plan(scheduler_plan)
        )
        if bound_scheduler_plan is not None and mode == "playable":
            validate_scheduler_final_runtime_budget(
                bound_scheduler_plan,
                _utc_now_datetime(),
            )
        if bound_scheduler_plan is not None and (
            resolved_schedule_evidence_ledger
            != bound_scheduler_plan.schedule_evidence_ledger
            or expected_schedule_evidence_sha256
            != bound_scheduler_plan.schedule_evidence_ledger_sha256
            or expected_schedule_evidence_semantic_hash
            != bound_scheduler_plan.schedule_evidence_semantic_hash
        ):
            raise ScheduleEvidenceIntegrityError(
                "run-drawing ledger arguments conflict with scheduler plan binding"
            )
        if bound_scheduler_plan is not None:
            config = replace(
                config,
                package_exposure_floor_scale=(
                    bound_scheduler_plan.package_exposure_floor_scale
                ),
                package_exposure_floor_exponent=(
                    bound_scheduler_plan.package_exposure_floor_exponent
                ),
                package_concentration_headroom_share=(
                    bound_scheduler_plan.package_concentration_headroom_share
                ),
                package_diversity_close_distance=(
                    bound_scheduler_plan.package_diversity_close_distance
                ),
                package_quality_repair_iterations=(
                    bound_scheduler_plan.package_quality_repair_iterations
                ),
                package_quality_candidate_count=(
                    bound_scheduler_plan.package_quality_candidate_count
                ),
                package_probability_samples=(
                    bound_scheduler_plan.package_probability_samples
                ),
                package_optimization_probability_samples=(
                    bound_scheduler_plan.package_optimization_probability_samples
                ),
                package_category_probability_tolerance=(
                    bound_scheduler_plan.package_category_probability_tolerance
                ),
                package_diversity_tolerance=(
                    bound_scheduler_plan.package_diversity_tolerance
                ),
                package_robust_ev_tolerance=(
                    bound_scheduler_plan.package_robust_ev_tolerance
                ),
            )
        load_bound_schedule_evidence_ledger(
            resolved_schedule_evidence_ledger,
            expected_content_sha256=expected_schedule_evidence_sha256,
            expected_semantic_hash=expected_schedule_evidence_semantic_hash,
        )
        client = TotoBriefClient()
        atomic_snapshot = (
            None
            if final_input is None
            else load_final_input(
                Path(final_input),
                expected_plan=bound_scheduler_plan,
            )
        )
        provider_factory = _api_sports_provider_factory(
            api_key,
            quota_reserve,
            schedule_cache_dir=(
                None
                if not isinstance(shared_schedule_cache_root, (str, os.PathLike))
                else Path(shared_schedule_cache_root)
            ),
        )
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
                expected_reviewed_catalog_hash=expected_reviewed_catalog_hash,
                schedule_evidence_ledger=resolved_schedule_evidence_ledger,
                expected_schedule_evidence_sha256=(expected_schedule_evidence_sha256),
                expected_schedule_evidence_semantic_hash=(
                    expected_schedule_evidence_semantic_hash
                ),
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
                schedule_evidence_ledger=prepared.schedule_evidence_ledger,
                expected_schedule_evidence_sha256=(
                    prepared.schedule_evidence_ledger_sha256
                ),
                expected_schedule_evidence_semantic_hash=(
                    prepared.schedule_evidence_semantic_hash
                ),
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
                    terminal_decision = update.get("decision")
                    if terminal_decision == "PLAY":
                        terminal_decision = "NO BET"
                    descriptions = {
                        "preflight": "Preflighting open drawing",
                        "final": "Revalidating pinned drawing",
                        "collect": "Collecting fresh API-Sports odds",
                        "timing": "Checking exact timing eligibility",
                        "audit": "Auditing latest 30 collections",
                        "ev": "Building exact EV package",
                        "complete": f"Runner complete: {terminal_decision}",
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
                        schedule_evidence_ledger_sha256=(
                            require_resources().schedule_evidence_ledger_sha256
                        ),
                        schedule_evidence_semantic_hash=(
                            require_resources().schedule_evidence_semantic_hash
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
                        selection_provenance=PackageSelectionProvenance.from_artifacts(
                            probability_snapshot_path=Path(final_input),
                            probability_input_sha256=(
                                atomic_snapshot.probability_input_sha256
                            ),
                            schedule_evidence_ledger_path=(
                                require_resources().schedule_evidence_ledger
                            ),
                            scheduler_plan_path=Path(scheduler_plan),
                            selection_config=config.ev_config,
                        ),
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
                operational_cutoff=(
                    None
                    if bound_scheduler_plan is None
                    else bound_scheduler_plan.operational_cutoff
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
    except (ScheduleEvidenceIntegrityError, SchedulerIntegrityError) as error:
        typer.echo(f"scheduler integrity failure: {error}", err=True)
        raise typer.Exit(code=SCHEDULER_INTEGRITY_EXIT_CODE) from error
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
        SchedulerError,
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
                max_age=REVIEWED_SCHEDULE_MAX_AGE,
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

    if result.decision == "PLAY":
        result = replace(
            result,
            decision="NO BET",
            terminal_reason=(
                "real-money release gate is closed; legacy PLAY result suppressed"
            ),
            ev_run=None,
        )

    try:
        reviewed_inputs = () if resources is None else resources.reviewed_input_paths
        ledger_input = None if resources is None else resources.schedule_evidence_ledger
        publication = publish_drawing_run_artifacts(
            result,
            report_dir=report_dir,
            protected_paths=tuple(
                path
                for path in (
                    db,
                    aliases,
                    timing_overrides,
                    ledger_input,
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


@app.command("scheduler-cutoff")
def scheduler_cutoff_command(
    source_report: str = typer.Option(..., "--source-report"),
    ended_at: str = typer.Option(..., "--ended-at"),
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    drawing_number: int = typer.Option(..., "--drawing-number", min=1),
    output: str = typer.Option(..., "--output"),
    project_root: str = typer.Option(..., "--project-root"),
) -> None:
    """Derive a hash-bound cutoff that can only move scheduling earlier."""
    root = Path(project_root).resolve(strict=True)
    try:
        report_path = resolve_contained_path(source_report, allowed_root=root)
        output_path = resolve_contained_path(output, allowed_root=root)
        evidence = derive_conservative_cutoff(
            report_path,
            source_ended_at=ended_at,
            expected_drawing_id=drawing_id,
            expected_drawing_number=drawing_number,
        )
        written = write_conservative_cutoff_evidence(evidence, output_path)
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": evidence.status,
                "drawing_id": evidence.drawing_id,
                "drawing_number": evidence.drawing_number,
                "source_ended_at": evidence.source_ended_at.isoformat(),
                "earliest_kickoff": evidence.earliest_kickoff.isoformat(),
                "operational_cutoff": evidence.operational_cutoff.isoformat(),
                "t_minus_10": (
                    evidence.operational_cutoff - timedelta(minutes=10)
                ).isoformat(),
                "evidence_path": str(written),
            },
            sort_keys=True,
        )
    )


@app.command("scheduler-plan")
def scheduler_plan_command(
    drawing: int = typer.Option(..., min=1),
    ended_at: str = typer.Option(..., "--ended-at"),
    operational_cutoff: str | None = typer.Option(None, "--operational-cutoff"),
    cutoff_evidence: str | None = typer.Option(None, "--cutoff-evidence"),
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
    schedule_evidence_ledger: str = typer.Option(
        str(DEFAULT_SCHEDULE_EVIDENCE_PATH),
        "--schedule-evidence-ledger",
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
    """Prepare a tracked T-50/T-40/T-30/T-18/T-10 scheduler plan."""
    try:
        plan = build_scheduler_plan(
            drawing=drawing,
            drawing_id=drawing_id,
            ended_at=ended_at,
            operational_cutoff=operational_cutoff,
            cutoff_evidence=cutoff_evidence,
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
            schedule_evidence_ledger=schedule_evidence_ledger,
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


@app.command("scheduler-recover-plan")
def scheduler_recover_plan_command(
    source_plan: str = typer.Option(..., "--source-plan"),
    output_dir: str = typer.Option(..., "--output-dir"),
    python_executable: str = typer.Option(
        sys.executable,
        "--python-executable",
        help=(
            "Current Python executable or exact project .venv interpreter "
            "used by generated scheduler artifacts."
        ),
    ),
) -> None:
    """Clone an immutable scheduler plan for an audited emergency retry."""
    try:
        source = load_scheduler_plan(source_plan)
        recovery = clone_scheduler_plan_for_recovery(
            source,
            output_dir=output_dir,
        )
        artifacts = prepare_scheduler_artifacts(
            recovery,
            python_command=python_executable,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    print(f"Source plan: {Path(source_plan).resolve()}")
    print(f"Source plan id: {source.plan_id}")
    print(f"Recovery plan: {artifacts.plan_path}")
    print(f"Recovery plan id: {recovery.plan_id}")
    print(f"Wrapper: {artifacts.wrapper_path}")
    print(f"LaunchAgent candidate: {artifacts.launch_agent_path}")
    print("All target, budget, probability, and evidence bindings were preserved.")


@app.command("experimental-release-authorize")
def experimental_release_authorize_command(
    plan: str = typer.Option(..., "--plan"),
    acknowledge_unvalidated_manual_risk: bool = typer.Option(
        False,
        "--acknowledge-unvalidated-manual-risk",
        help=(
            "Explicitly authorize one fresh manual package even though "
            "profitability has not been proven."
        ),
    ),
) -> None:
    """Authorize one exact plan for experimental manual export before T-10."""

    try:
        scheduler_plan = load_scheduler_plan(plan)
        authorization_path = authorize_experimental_manual_release(
            scheduler_plan,
            acknowledged=acknowledge_unvalidated_manual_risk,
            now=_utc_now_datetime(),
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Authorization: {authorization_path}")
    typer.echo(
        "EXPERIMENTAL MANUAL ONLY: profitability is unproven; "
        "automatic wagering remains disabled."
    )


@app.command("morning-preanalysis-plan")
def morning_preanalysis_plan_command(
    env_file: str = typer.Option(..., "--env-file"),
    at: list[str] | None = typer.Option(None, "--at"),  # noqa: B008
    bank: int = typer.Option(4980, min=1),
    stake: int = typer.Option(30, min=1),
    discovery_interval_seconds: int = typer.Option(
        900,
        "--discovery-interval-seconds",
        min=900,
    ),
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
            discovery_interval_seconds=discovery_interval_seconds,
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
    state_root: str = typer.Option("data/scheduler/morning-dispatch", "--state-root"),
    scheduler_root: str = typer.Option("reports/rehearsal", "--scheduler-root"),
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
            project_root=Path(
                os.path.commonpath(
                    (
                        Path(db).absolute(),
                        Path(state_root).absolute(),
                        Path(scheduler_root).absolute(),
                    )
                )
            ),
            now=(
                datetime.now(timezone.utc)
                if at is None
                else datetime.fromisoformat(at.replace("Z", "+00:00"))
            ),
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@app.command("preflight-retry-run")
def preflight_retry_run_command(
    plan: Path = typer.Option(..., "--plan"),  # noqa: B008
) -> None:
    """Run one passive identity-bound preflight retry tick."""
    from toto_ai.runner.preflight_retry_scheduler import run_preflight_retry

    raise typer.Exit(run_preflight_retry(plan, now=datetime.now(timezone.utc)))


@app.command("preflight-retry-install")
def preflight_retry_install_command(
    plan: Path = typer.Option(..., "--plan"),  # noqa: B008
) -> None:
    """Explicitly generate and install one passive retry LaunchAgent."""
    from toto_ai.runner.preflight_retry_scheduler import (
        install_preflight_retry_launch_agent,
        prepare_preflight_retry_artifacts,
    )

    artifacts = prepare_preflight_retry_artifacts(plan)
    payload = install_preflight_retry_launch_agent(artifacts)
    typer.echo(json.dumps(payload, sort_keys=True))


@app.command("preflight-retry-rehearsal")
def preflight_retry_rehearsal_command(
    db: Path = typer.Option(..., "--db"),  # noqa: B008
    target_cache: Path = typer.Option(..., "--target-cache"),  # noqa: B008
    schedule_cache: list[Path] = typer.Option(  # noqa: B008
        ..., "--schedule-cache"
    ),
    aliases: Path = typer.Option(..., "--aliases"),  # noqa: B008
    reviewed_schedule_catalog: Path = typer.Option(  # noqa: B008
        ..., "--reviewed-schedule-catalog"
    ),
    output_root: Path = typer.Option(..., "--output-root"),  # noqa: B008
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    drawing_number: int = typer.Option(..., "--drawing-number", min=1),
    at: str = typer.Option(..., "--at"),
    failed_schedule_date: list[str] = typer.Option(  # noqa: B008
        [],
        "--failed-schedule-date",
        help="Inject a failed provider UTC date into the isolated rehearsal.",
    ),
    bank: int = typer.Option(4980, min=1),
    stake: int = typer.Option(30, min=1),
) -> None:
    """Run the deterministic passive retry E2E on an isolated database copy."""
    from toto_ai.runner.preflight_retry_rehearsal import (
        PreflightRetryRehearsalConfig,
        run_preflight_retry_rehearsal,
    )

    try:
        summary = run_preflight_retry_rehearsal(
            PreflightRetryRehearsalConfig(
                source_db=db,
                target_cache=target_cache,
                schedule_caches=tuple(schedule_cache),
                aliases=aliases,
                reviewed_schedule_catalog=reviewed_schedule_catalog,
                output_root=output_root,
                drawing_id=drawing_id,
                drawing_number=drawing_number,
                rehearsal_at=datetime.fromisoformat(at.replace("Z", "+00:00")),
                failed_schedule_dates=tuple(
                    date.fromisoformat(value) for value in failed_schedule_date
                ),
                bank=bank,
                stake=stake,
            )
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def _morning_unresolved_events(
    *,
    target: TargetDrawing,
    prepared: DrawingPreparationResult,
    schedule_diagnostics: tuple[Mapping[str, object], ...],
) -> tuple[MorningUnresolvedEvent, ...]:
    """Expose every unresolved identity or baseline-only kickoff dependency."""

    target_events = target.events
    prepared_events = prepared.events
    unresolved = [
        MorningUnresolvedEvent(
            event_order=item.event_order,
            target_event_id=item.target_event_id,
            home_team=target_events[item.event_order].home_team,
            away_team=target_events[item.event_order].away_team,
            championship=target_events[item.event_order].championship,
            resolution_status=item.status,
            reason=item.reason,
            candidate_evidence=item.candidate_evidence,
            provider_diagnostics=schedule_diagnostics,
        )
        for item in prepared_events
        if item.status not in {"matched", "baseline_only"}
    ]
    if prepared.eligibility.status == "unknown":
        unresolved.extend(
            MorningUnresolvedEvent(
                event_order=order,
                target_event_id=target_events[order].event_id,
                home_team=target_events[order].home_team,
                away_team=target_events[order].away_team,
                championship=target_events[order].championship,
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
                candidate_evidence=(),
                provider_diagnostics=schedule_diagnostics,
            )
            for order in prepared.baseline_only_event_orders
            if target_events[order].starts_at is None
        )
    unresolved.sort(key=lambda item: item.event_order)
    return tuple(unresolved)


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
    state_root: Path,
    env_file: Path,
    schedule_evidence_ledger: Path,
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
            operational_cutoffs=load_verified_operational_cutoffs(
                state_root,
                project_root=project_root,
            ),
        )
        if (
            synchronized.detail.reason_code == "totobrief_pool_not_ready"
            and synchronized.detail.payload is not None
        ):
            target = parse_target_drawing(
                synchronized.detail.payload,
                fetched_at=observed_at,
            )
            if target.drawing_number is None:
                raise ValueError("current drawing visible number is required")
            fingerprint = target_fingerprint(
                target.drawing_id,
                target.drawing_number,
                target.deadline,
                target.events,
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
                drawing_fingerprint=fingerprint,
                detail_sha256=detail_sha256,
                preparation_status="not_ready",
                mapped_count=0,
                eligibility_status="unknown",
                span_days=None,
                not_ready_reason="totobrief_pool_not_ready",
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
        api_key = load_api_sports_key(env_file)
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
            # Morning/preflight must always evaluate the repository-owned
            # reusable evidence ledger.  A missing or invalid ledger is a
            # fail-closed input error, never permission to reuse stale counts.
            schedule_evidence_ledger=schedule_evidence_ledger,
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
        unresolved_events = _morning_unresolved_events(
            target=target,
            prepared=prepared,
            schedule_diagnostics=tuple(schedule.diagnostics),
        )
        return MorningPreparedDrawing(
            drawing_id=target.drawing_id,
            drawing_number=target.drawing_number,
            deadline=target.deadline,
            drawing_fingerprint=prepared.drawing_fingerprint,
            detail_sha256=detail_sha256,
            preparation_status=prepared.status,
            mapped_count=prepared.mapped_count,
            eligibility_status=prepared.eligibility.status,
            span_days=_optional_morning_span_days(prepared.eligibility.span_days),
            external_coverage_count=prepared.external_coverage_count,
            baseline_only_event_orders=prepared.baseline_only_event_orders,
            reviewed_catalog_hash=load_ready_pin_set_reviewed_catalog_hash(
                session_factory,
                drawing_id=target.drawing_id,
                drawing_fingerprint=prepared.drawing_fingerprint,
            ),
            unresolved_events=unresolved_events,
        )
    finally:
        engine.dispose()


def _optional_morning_span_days(span_days: int | None) -> int | None:
    """Map eligibility's zero-known-start sentinel to morning's null contract."""
    if span_days is None:
        return None
    if type(span_days) is not int or span_days < 0:
        raise ValueError("eligibility span_days must be a non-negative integer")
    return span_days or None


def _morning_cutoff_directory(
    config: MorningDispatchConfig,
    evidence: MorningPreparedDrawing,
) -> Path:
    deadline = evidence.deadline.strftime("%Y%m%dT%H%M%SZ")
    return (
        config.state_root
        / "preflight"
        / (
            f"drawing-{evidence.drawing_id}-{deadline}-"
            f"{evidence.drawing_fingerprint[:16]}"
        )
        / "source-collector"
    )


def _attach_persisted_conservative_cutoff(
    config: MorningDispatchConfig,
    evidence: MorningPreparedDrawing,
) -> MorningPreparedDrawing:
    collector_dir = _morning_cutoff_directory(config, evidence)
    source_report = collector_dir / "schedule-source-candidates.json"
    cutoff_path = collector_dir / "conservative-cutoff.json"
    loaded = None
    if cutoff_path.is_file():
        loaded = load_conservative_cutoff_evidence(
            cutoff_path,
            project_root=config.project_root,
            expected_drawing_id=evidence.drawing_id,
            expected_drawing_number=evidence.drawing_number,
            expected_source_ended_at=evidence.deadline,
        )
    if source_report.is_file():
        try:
            derived = derive_conservative_cutoff(
                source_report,
                source_ended_at=evidence.deadline,
                expected_drawing_id=evidence.drawing_id,
                expected_drawing_number=evidence.drawing_number,
            )
        except NoQualifyingKickoffEvidenceError:
            # A candidate report may contain useful schedule candidates from
            # providers that are not authorized to tighten the operational
            # cutoff.  In that case keep TotoBrief ``ended_at`` (or an older
            # persisted cutoff) instead of aborting morning preparation.
            pass
        else:
            write_conservative_cutoff_evidence(derived, cutoff_path)
            loaded = load_conservative_cutoff_evidence(
                cutoff_path,
                project_root=config.project_root,
                expected_drawing_id=evidence.drawing_id,
                expected_drawing_number=evidence.drawing_number,
                expected_source_ended_at=evidence.deadline,
            )
    if loaded is None:
        return evidence
    return replace(
        evidence,
        operational_cutoff=loaded.operational_cutoff,
        cutoff_evidence=cutoff_path,
        cutoff_evidence_sha256=conservative_cutoff_evidence_sha256(loaded),
    )


def _existing_preflight_retry_plan(
    config: MorningDispatchConfig,
    evidence: MorningPreparedDrawing,
) -> Path | None:
    deadline = evidence.deadline.strftime("%Y%m%dT%H%M%SZ")
    path = (
        config.state_root
        / "preflight"
        / (
            f"drawing-{evidence.drawing_id}-{deadline}-"
            f"{evidence.drawing_fingerprint[:16]}"
        )
        / "retry-plan.json"
    )
    return path if path.is_file() else None


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
    schedule_evidence_ledger: str = typer.Option(
        str(DEFAULT_SCHEDULE_EVIDENCE_PATH),
        "--schedule-evidence-ledger",
    ),
    activate: bool = typer.Option(False, "--activate"),
    goal_shadow_auto: bool = typer.Option(
        False,
        "--goal-shadow-auto/--no-goal-shadow-auto",
        help=(
            "Collect one idempotent GOAL sports-shadow snapshot per drawing; "
            "research-only and non-blocking."
        ),
    ),
    parallel_challenger_auto: bool = typer.Option(
        False,
        "--parallel-challenger-auto/--no-parallel-challenger-auto",
        help=(
            "Prepare the isolated quality-v2/sports-shadow/quality-v3/robust "
            "sidecar; never blocks the primary scheduler."
        ),
    ),
    parallel_release_auto: bool = typer.Option(
        False,
        "--parallel-release-auto/--no-parallel-release-auto",
        help=(
            "Create the exact plan-bound experimental parallel manual-release "
            "authorization; automatic wagering remains disabled."
        ),
    ),
    preflight_retry_child: bool = typer.Option(
        False,
        "--preflight-retry-child",
        hidden=True,
    ),
    expected_drawing_id: int | None = typer.Option(
        None, "--expected-drawing-id", min=1
    ),
    expected_drawing_number: int | None = typer.Option(
        None, "--expected-drawing-number", min=1
    ),
    expected_fingerprint: str | None = typer.Option(None, "--expected-fingerprint"),
    expected_deadline: str | None = typer.Option(None, "--expected-deadline"),
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
    resolved_schedule_evidence_ledger = resolve_contained_path(
        schedule_evidence_ledger,
        allowed_root=root,
    )
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
        schedule_evidence_ledger=resolved_schedule_evidence_ledger,
    )
    observed_at = datetime.now(timezone.utc)
    try:
        parsed_expected_deadline = (
            None
            if expected_deadline is None
            else _parse_expected_deadline(expected_deadline)
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    expected_values = (
        expected_drawing_id,
        expected_drawing_number,
        expected_fingerprint,
        parsed_expected_deadline,
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
            deadline=parsed_expected_deadline,
        )
    )
    retry_scheduler_status: dict[str, object] | None = None
    source_collector_status: dict[str, object] | None = None
    training_package_status: dict[str, object] | None = None
    sports_shadow_status: dict[str, object] | None = None
    parallel_challenger_status: dict[str, object] | None = None
    prepared_evidence: MorningPreparedDrawing | None = None

    if parallel_release_auto and not parallel_challenger_auto:
        raise typer.BadParameter(
            "--parallel-release-auto requires --parallel-challenger-auto"
        )
    if parallel_challenger_auto and not goal_shadow_auto:
        raise typer.BadParameter(
            "--parallel-challenger-auto requires --goal-shadow-auto"
        )

    def prepare_for_dispatch(now: datetime) -> MorningPreparedDrawing:
        nonlocal prepared_evidence
        prepared_evidence = _attach_persisted_conservative_cutoff(
            config,
            _prepare_current_for_morning(
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
                state_root=config.state_root,
                env_file=config.env_file,
                schedule_evidence_ledger=config.schedule_evidence_ledger,
                reviewed_schedule_catalog=(
                    None
                    if reviewed_schedule_catalog is None
                    else resolve_contained_path(
                        reviewed_schedule_catalog, allowed_root=root
                    )
                ),
            ),
        )
        return prepared_evidence

    try:
        result = dispatch_morning(
            config,
            observed_at=observed_at,
            prepare_current=prepare_for_dispatch,
            now=lambda: datetime.now(timezone.utc),
            activate=activate_scheduler_launch_agent if activate else None,
            python_command=python_executable,
            expected_identity=expected_identity,
        )
        if (
            activate
            and not preflight_retry_child
            and result.status in {"scheduled", "reused"}
            and prepared_evidence is not None
        ):
            resolved_retry_plan = _existing_preflight_retry_plan(
                config,
                prepared_evidence,
            )
            if resolved_retry_plan is not None:
                retry_artifacts = prepare_preflight_retry_artifacts(
                    resolved_retry_plan,
                    write=False,
                )
                cleanup_preflight_retry_launch_agent(retry_artifacts)
                retry_scheduler_status = {
                    "active": False,
                    "label": retry_artifacts.label,
                    "reason": "drawing_ready",
                }
        if result.plan_path is not None:
            try:
                training = ensure_scheduler_training_package(
                    load_scheduler_plan(result.plan_path),
                    morning_record_path=result.record_path,
                    input_cache_dir=resolved_raw_cache,
                    generated_at=datetime.now(timezone.utc),
                )
            except TrainingPackageDeferred as error:
                training_package_status = {
                    "status": "deferred",
                    "reason": "pool_supported_capacity_infeasible",
                    "detail": str(error),
                }
            except Exception as error:
                training_package_status = {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {str(error)[:300]}",
                }
            else:
                training_package_status = {
                    "status": "ready",
                    "mode": training.mode,
                    "actionable": training.actionable,
                    "pipeline": training.pipeline,
                    "structural_status": training.structural_status,
                    "requested_bank": training.requested_bank,
                    "effective_budget": training.effective_budget,
                    "selected_count": training.selected_count,
                    "selected_cost": training.selected_cost,
                    "unused_requested_bank": training.unused_requested_bank,
                    "bank_usage_reason": training.bank_usage_reason,
                    "source_archive_path": str(training.source_archive_path),
                    "source_archive_snapshot_sha256": (
                        training.source_archive_snapshot_sha256
                    ),
                    "package_sha256": training.package_sha256,
                    "result_path": str(training.result_path),
                    "input_path": str(training.input_path),
                    "paper_path": str(training.paper_path),
                    "diagnostics_path": str(training.diagnostics_path),
                }
        if result.review_queue_path is not None:
            independent_status: dict[str, object]
            source_candidates_report: Path | None = None
            try:
                collected = collect_schedule_source_candidates(
                    result.review_queue_path,
                    output_dir=result.review_queue_path.parent / "source-collector",
                    schedule_evidence_ledger=resolved_schedule_evidence_ledger,
                    goal_api_config=GoalAPIConfig(
                        api_key=load_goal_api_key(config.env_file)
                    ),
                    team_aliases=load_reviewed_alias_names(config.aliases),
                )
            except Exception as error:
                independent_status = {
                    "status": "SOURCE_COLLECTOR_FAILED",
                    "error": f"{type(error).__name__}: {str(error)[:300]}",
                }
            else:
                source_candidates_report = collected.report_path
                cutoff_fields: dict[str, object]
                if prepared_evidence is None:
                    cutoff_fields = {
                        "cutoff_status": "unavailable",
                        "cutoff_reason": (
                            "morning preparation evidence is unavailable"
                        ),
                    }
                else:
                    try:
                        cutoff = derive_conservative_cutoff(
                            collected.report_path,
                            source_ended_at=prepared_evidence.deadline,
                            expected_drawing_id=prepared_evidence.drawing_id,
                            expected_drawing_number=prepared_evidence.drawing_number,
                        )
                        cutoff_path = write_conservative_cutoff_evidence(
                            cutoff,
                            collected.report_path.parent / "conservative-cutoff.json",
                        )
                    except ValueError as error:
                        cutoff_fields = {
                            "cutoff_status": "unavailable",
                            "cutoff_reason": str(error),
                        }
                    else:
                        cutoff_fields = {
                            "cutoff_status": cutoff.status,
                            "operational_cutoff": (
                                cutoff.operational_cutoff.isoformat()
                            ),
                            "cutoff_evidence_path": str(cutoff_path),
                        }
                independent_status = {
                    "status": collected.status,
                    "candidate_count": collected.candidate_count,
                    "unresolved_count": collected.unresolved_count,
                    "providers": getattr(collected, "provider_statuses", {}),
                    "report_path": str(collected.report_path),
                    **cutoff_fields,
                    "ledger_mutated": False,
                }
            consensus_status: dict[str, object]
            consensus_promoted_count = 0
            try:
                consensus = promote_uefa_sofascore_consensus(
                    result.review_queue_path,
                    output_dir=(result.review_queue_path.parent / "source-consensus"),
                    schedule_evidence_ledger=resolved_schedule_evidence_ledger,
                )
            except Exception as error:
                consensus_status = {
                    "status": "CONSENSUS_COLLECTOR_FAILED",
                    "error": f"{type(error).__name__}: {str(error)[:300]}",
                    "ledger_mutated": False,
                }
            else:
                consensus_promoted_count = consensus.promoted_count
                consensus_status = {
                    "status": consensus.status,
                    "promoted_count": consensus.promoted_count,
                    "existing_count": consensus.existing_count,
                    "unresolved_count": consensus.unresolved_count,
                    "report_path": str(consensus.report_path),
                    "ledger_semantic_hash": consensus.ledger_semantic_hash,
                    "ledger_mutated": consensus.promoted_count > 0,
                }
            independent_consensus_status: dict[str, object]
            independent_consensus_promoted_count = 0
            try:
                if source_candidates_report is None:
                    raise ValueError("schedule source candidates are unavailable")
                independent_consensus = promote_independent_schedule_consensus(
                    result.review_queue_path,
                    source_candidates_path=source_candidates_report,
                    output_dir=(
                        result.review_queue_path.parent / "source-independent-consensus"
                    ),
                    schedule_evidence_ledger=resolved_schedule_evidence_ledger,
                )
            except Exception as error:
                independent_consensus_status = {
                    "status": "INDEPENDENT_CONSENSUS_FAILED",
                    "error": f"{type(error).__name__}: {str(error)[:300]}",
                    "ledger_mutated": False,
                }
            else:
                independent_consensus_promoted_count = (
                    independent_consensus.promoted_count
                )
                independent_consensus_status = {
                    "status": independent_consensus.status,
                    "promoted_count": independent_consensus.promoted_count,
                    "existing_count": independent_consensus.existing_count,
                    "unresolved_count": independent_consensus.unresolved_count,
                    "report_path": str(independent_consensus.report_path),
                    "ledger_semantic_hash": (
                        independent_consensus.ledger_semantic_hash
                    ),
                    "ledger_mutated": independent_consensus.promoted_count > 0,
                }
            source_collector_status = {
                "independent": independent_status,
                "consensus": consensus_status,
                "independent_consensus": independent_consensus_status,
            }
            observed_ledger_hashes = {
                str(status["ledger_semantic_hash"])
                for status in (
                    consensus_status,
                    independent_consensus_status,
                )
                if isinstance(status.get("ledger_semantic_hash"), str)
            }
            evidence_ledger_advanced = prepared_evidence is not None and any(
                ledger_hash != prepared_evidence.reviewed_catalog_hash
                for ledger_hash in observed_ledger_hashes
            )
            refresh_dispatch = False
            if prepared_evidence is not None and (
                consensus_promoted_count > 0
                or independent_consensus_promoted_count > 0
                or evidence_ledger_advanced
            ):
                prepared_evidence = prepare_for_dispatch(datetime.now(timezone.utc))
                refresh_dispatch = True
            if (
                prepared_evidence is not None
                and "cutoff_evidence_path" in independent_status
            ):
                persisted_cutoff = load_conservative_cutoff_evidence(
                    str(independent_status["cutoff_evidence_path"]),
                    project_root=config.project_root,
                    expected_drawing_id=prepared_evidence.drawing_id,
                    expected_drawing_number=prepared_evidence.drawing_number,
                    expected_source_ended_at=prepared_evidence.deadline,
                )
                prepared_evidence = replace(
                    prepared_evidence,
                    operational_cutoff=persisted_cutoff.operational_cutoff,
                    cutoff_evidence=Path(
                        str(independent_status["cutoff_evidence_path"])
                    ),
                    cutoff_evidence_sha256=(
                        conservative_cutoff_evidence_sha256(persisted_cutoff)
                    ),
                )
                refresh_dispatch = True
            if prepared_evidence is not None and refresh_dispatch:
                result = dispatch_morning(
                    config,
                    observed_at=datetime.now(timezone.utc),
                    prepare_current=lambda _now: prepared_evidence,
                    now=lambda: datetime.now(timezone.utc),
                    activate=None,
                    python_command=python_executable,
                    expected_identity=expected_identity,
                )
        if (
            goal_shadow_auto
            and prepared_evidence is not None
            and result.status in {"scheduled", "reused"}
        ):
            try:
                goal_api_key = load_goal_api_key(config.env_file)
                if goal_api_key is None:
                    raise ValueError("GOAL_API_KEY is required")
                shadow = ensure_goal_probe_input(
                    drawing_id=prepared_evidence.drawing_id,
                    raw_cache_dir=resolved_raw_cache,
                    output_root=(
                        root
                        / "reports"
                        / "sports-analytics"
                        / str(prepared_evidence.drawing_number)
                        / "goal-auto"
                    ),
                    api_key=goal_api_key,
                    project_root=root,
                )
            except Exception as error:
                sports_shadow_status = {
                    "status": "PAPER_ONLY_COLLECTION_FAILED",
                    "error": f"{type(error).__name__}: {str(error)[:300]}",
                    "package_influence": "NONE",
                    "automatic_wagering": False,
                }
            else:
                sports_shadow_status = {
                    "status": "PAPER_ONLY_COVERAGE_PROBE_READY",
                    "drawing_id": prepared_evidence.drawing_id,
                    "drawing_number": prepared_evidence.drawing_number,
                    "event_count": shadow.event_count,
                    "history_source_count": shadow.history_source_count,
                    "sports_eligible_count": shadow.sports_eligible_count,
                    "request_count": shadow.request_count,
                    "quota_daily_remaining": shadow.quota_daily_remaining,
                    "captured_at": shadow.captured_at.isoformat(),
                    "coverage_summary": str(shadow.coverage_summary_path),
                    "reused": shadow.reused,
                    "package_influence": "NONE",
                    "automatic_wagering": False,
                }
                if parallel_challenger_auto and result.plan_path is not None:
                    try:
                        plan = load_scheduler_plan(result.plan_path)
                        sports_seed_as_of = _sports_seed_as_of(
                            drawing_id=prepared_evidence.drawing_id,
                            requested_as_of=shadow.captured_at,
                            raw_cache_dir=resolved_raw_cache,
                            project_root=root,
                        )
                        bundle = load_goal_probe_shadow(
                            drawing_id=prepared_evidence.drawing_id,
                            as_of=sports_seed_as_of,
                            raw_cache_dir=resolved_raw_cache,
                            coverage_summary_path=shadow.coverage_summary_path,
                            project_root=root,
                        )
                        sports_v2 = build_sports_v2_shadow_artifact(
                            snapshot=bundle.snapshot,
                            base_artifact=bundle.shadow,
                        )
                        sports_artifact_path = write_shadow_probability_artifact(
                            sports_v2,
                            report_dir=(
                                plan.output_dir
                                / "parallel-challenger"
                                / "sports-seed"
                            ),
                        )
                        parallel_root = (
                            plan.output_dir / "parallel-challenger"
                        )
                        authorization_path = (
                            authorize_parallel_manual_release(
                                scheduler_plan_path=result.plan_path,
                                output_root=parallel_root,
                                acknowledged=True,
                            )
                            if parallel_release_auto
                            else None
                        )
                        parallel_artifacts = prepare_parallel_sidecar_artifacts(
                            scheduler_plan_path=result.plan_path,
                            sports_artifact_path=sports_artifact_path,
                            python_command=python_executable,
                            parallel_authorization_path=authorization_path,
                        )
                        bound_sports = load_shadow_probability_artifact(
                            parallel_artifacts.sports_artifact_path
                        )
                        if activate:
                            activate_parallel_sidecar_launch_agent(
                                parallel_artifacts
                            )
                    except Exception as error:
                        parallel_challenger_status = {
                            "status": "PARALLEL_SIDECAR_FAILED_OPEN",
                            "error": (
                                f"{type(error).__name__}: {str(error)[:300]}"
                            ),
                            "primary_scheduler_affected": False,
                            "automatic_wagering": False,
                        }
                    else:
                        parallel_challenger_status = {
                            "status": "PARALLEL_SIDECAR_ACTIVATED"
                            if activate
                            else "PARALLEL_SIDECAR_PREPARED",
                            "drawing_number": plan.drawing,
                            "plan_id": plan.plan_id,
                            "candidate_strategies": [
                                "quality-v2",
                                "sports-shadow",
                                "quality-v3",
                                "robust",
                            ],
                            "scheduled_at": (
                                parallel_artifacts.scheduled_at.isoformat()
                            ),
                            "launch_agent_label": (
                                parallel_artifacts.launch_agent_label
                            ),
                            "sports_artifact": str(
                                parallel_artifacts.sports_artifact_path
                            ),
                            "sports_coverage_count": (
                                bound_sports.sports_coverage_count
                            ),
                            "reused": parallel_artifacts.reused,
                            "parallel_release_authorized": (
                                parallel_artifacts.authorization_path is not None
                            ),
                            "primary_scheduler_affected": False,
                            "automatic_wagering": False,
                        }
        if (
            activate
            and not preflight_retry_child
            and result.retry_plan_path is not None
        ):
            retry_artifacts = prepare_preflight_retry_artifacts(result.retry_plan_path)
            retry_scheduler_status = install_preflight_retry_launch_agent(
                retry_artifacts
            )
    except MorningIdentityDriftError as error:
        typer.echo(
            json.dumps(
                {"status": "terminal", "reason": "identity_drift"},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raise typer.Exit(code=MORNING_IDENTITY_DRIFT_EXIT_CODE) from error
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
                "launch_agent_label": result.launch_agent_label,
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
                "retry_scheduler": retry_scheduler_status,
                "source_collector": source_collector_status,
                "training_package": training_package_status,
                "sports_shadow": sports_shadow_status,
                "parallel_challenger": parallel_challenger_status,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if result.status == "deferred":
        raise typer.Exit(code=MORNING_DEFERRED_EXIT_CODE)


@app.command("collect-schedule-sources")
def collect_schedule_sources_command(
    queue: str = typer.Option(..., "--queue"),
    output_dir: str = typer.Option(..., "--output-dir"),
    env_file: str = typer.Option(".env", "--env-file"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    schedule_evidence_ledger: str | None = typer.Option(
        str(DEFAULT_SCHEDULE_EVIDENCE_PATH), "--schedule-evidence-ledger"
    ),
) -> None:
    """Collect public schedule candidates; never promote them into the ledger."""

    try:
        result = collect_schedule_source_candidates(
            queue,
            output_dir=output_dir,
            schedule_evidence_ledger=schedule_evidence_ledger,
            goal_api_config=GoalAPIConfig(api_key=load_goal_api_key(env_file)),
            team_aliases=load_reviewed_alias_names(aliases),
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "queue_sha256": result.queue_sha256,
                "candidate_count": result.candidate_count,
                "unresolved_count": result.unresolved_count,
                "providers": result.provider_statuses,
                "report_path": str(result.report_path),
                "ledger_mutated": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


SCHEDULE_EVIDENCE_INTEGRITY_EXIT_CODE = 20
SCHEDULE_EVIDENCE_UNRESOLVED_EXIT_CODE = 21
SCHEDULE_EVIDENCE_REVIEW_EXIT_CODE = 22


@app.command("schedule-evidence-status")
def schedule_evidence_status_command(
    ledger: str = typer.Option(str(DEFAULT_SCHEDULE_EVIDENCE_PATH), "--ledger"),
    reviews_dir: str = typer.Option(str(DEFAULT_REVIEWS_DIR), "--reviews-dir"),
    snapshots_dir: str = typer.Option(
        str(DEFAULT_SNAPSHOTS_DIR), "--snapshots-dir"
    ),
) -> None:
    """Print a read-only ledger and drawing/event evidence summary."""

    try:
        result = schedule_evidence_status(
            ledger_path=Path(ledger),
            reviews_dir=Path(reviews_dir),
            snapshots_dir=Path(snapshots_dir),
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(json.dumps({"status": "invalid", "error": str(error)}))
        raise typer.Exit(code=SCHEDULE_EVIDENCE_INTEGRITY_EXIT_CODE) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if int(result["unresolved_count"]) > 0:
        raise typer.Exit(code=SCHEDULE_EVIDENCE_UNRESOLVED_EXIT_CODE)


@app.command("schedule-evidence-review")
def schedule_evidence_review_command(
    review: str = typer.Option(..., "--review"),
    review_sha256: str = typer.Option(..., "--review-sha256"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Atomically ingest after validation; default is a no-write dry-run.",
    ),
    ledger: str = typer.Option(str(DEFAULT_SCHEDULE_EVIDENCE_PATH), "--ledger"),
    reviews_dir: str = typer.Option(str(DEFAULT_REVIEWS_DIR), "--reviews-dir"),
    snapshots_dir: str = typer.Option(
        str(DEFAULT_SNAPSHOTS_DIR), "--snapshots-dir"
    ),
) -> None:
    """Validate a hash-bound prepared review; write only with --apply."""

    try:
        result = review_prepared_schedule_evidence(
            ledger_path=Path(ledger),
            reviews_dir=Path(reviews_dir),
            snapshots_dir=Path(snapshots_dir),
            review_path=Path(review),
            expected_review_sha256=review_sha256,
            apply=apply,
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(json.dumps({"status": "rejected", "error": str(error)}))
        raise typer.Exit(code=SCHEDULE_EVIDENCE_REVIEW_EXIT_CODE) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@app.command("schedule-evidence-verify")
def schedule_evidence_verify_command(
    ledger: str = typer.Option(str(DEFAULT_SCHEDULE_EVIDENCE_PATH), "--ledger"),
    reviews_dir: str = typer.Option(str(DEFAULT_REVIEWS_DIR), "--reviews-dir"),
    snapshots_dir: str = typer.Option(
        str(DEFAULT_SNAPSHOTS_DIR), "--snapshots-dir"
    ),
) -> None:
    """Verify ledger, review and snapshot hashes without mutation."""

    try:
        result = verify_schedule_evidence(
            ledger_path=Path(ledger),
            reviews_dir=Path(reviews_dir),
            snapshots_dir=Path(snapshots_dir),
        )
    except (OSError, TypeError, ValueError) as error:
        typer.echo(json.dumps({"status": "invalid", "error": str(error)}))
        raise typer.Exit(code=SCHEDULE_EVIDENCE_INTEGRITY_EXIT_CODE) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@app.command("scheduler-status")
def scheduler_status_command(
    plan: str = typer.Option(..., "--plan"),
    at: str | None = typer.Option(None, "--at"),
) -> None:
    """Print one read-only, plan-bound scheduler and challenger status."""

    try:
        observed_at = (
            None
            if at is None
            else datetime.fromisoformat(at.replace("Z", "+00:00"))
        )
        result = scheduler_status(
            load_scheduler_plan(plan), observed_at=observed_at
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@app.command("scheduler-status-watch")
def scheduler_status_watch_command(
    plan: str = typer.Option(..., "--plan"),
    latest: str = typer.Option(..., "--latest"),
    history: str = typer.Option(..., "--history"),
    interval_seconds: float = typer.Option(30.0, "--interval-seconds"),
) -> None:
    """Watch one exact plan and persist only read-only status changes."""

    try:
        watch_scheduler_status(
            load_scheduler_plan(plan),
            latest_path=Path(latest),
            history_path=Path(history),
            interval_seconds=interval_seconds,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error


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
        if (
            not simulate
            and scheduler_plan.source_schema_version != SCHEDULER_SCHEMA_VERSION
        ):
            raise ValueError(
                "legacy scheduler plan is inspection-only; regenerate schema "
                f"v{SCHEDULER_SCHEMA_VERSION}"
            )
        if run_id is not None and not simulate:
            raise ValueError(
                "--run-id is simulation-only; production schema-"
                f"v{SCHEDULER_SCHEMA_VERSION} plans "
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
    if result.outcome == "bet-ready":
        print(
            "Operator export: use `operator-export --plan <scheduler-plan.json> "
            "--output <destination.txt>` before T-10"
        )
    if result.outcome == "failed":
        raise typer.Exit(code=1)


@app.command("scheduler-preflight-only")
def scheduler_preflight_only_command(
    plan: str = typer.Option(..., "--plan"),
) -> None:
    """Run one real exact-target preflight without training or packages."""

    try:
        scheduler_plan = load_scheduler_plan(plan)
        environment = dict(os.environ)
        if scheduler_plan.env_file is not None:
            environment["API_SPORTS_KEY"] = load_api_sports_key(scheduler_plan.env_file)
        result = execute_scheduler_preflight_only(
            scheduler_plan,
            phase_runner=CommandSchedulerPhaseRunner(environment=environment),
            now=_utc_now_datetime,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["status"] != "PASS":
        raise typer.Exit(code=1)


@app.command("operator-export")
def operator_export_command(
    plan: str = typer.Option(..., "--plan"),
    output: str = typer.Option(..., "--output"),
) -> None:
    """Export the current verified scheduler-owned PLAY package for BaltBet."""

    try:
        scheduler_plan = load_scheduler_plan(plan)
        destination = export_operator_package(
            scheduler_plan,
            destination=output,
            now=_utc_now_datetime,
        )
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Operator package: {destination}")


@app.command("paper-package-show")
def paper_package_show_command(
    plan: str = typer.Option(..., "--plan"),
    output: str | None = typer.Option(None, "--output"),
) -> None:
    """Show an explicitly non-actionable scheduler-owned PAPER package."""

    try:
        scheduler_plan = load_scheduler_plan(plan)
        result = load_paper_package(scheduler_plan)
        if result.paper_path is None:
            raise SchedulerIntegrityError(
                "paper package has no coupon payload",
                category="paper_package_unavailable",
            )
        if output is None:
            sys.stdout.buffer.write(result.paper_path.read_bytes())
            sys.stdout.buffer.flush()
        else:
            export_paper_package(scheduler_plan, destination=output)
    except (OSError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    print(
        "PAPER / NO BET / DO NOT WAGER — "
        f"drawing={scheduler_plan.drawing} coupons={result.count} cost={result.cost}",
        file=sys.stderr,
    )


@app.command("scheduler-training-package")
def scheduler_training_package_command(
    plan: str = typer.Option(..., "--plan"),
    morning_record: str = typer.Option(..., "--morning-record"),
    input_cache_dir: str = typer.Option("data/raw", "--input-cache-dir"),
    at: str | None = typer.Option(None, "--at"),
) -> None:
    """Calculate or validate a scheduler-bound quality-v2 training package."""

    try:
        scheduler_plan = load_scheduler_plan(plan)
        generated_at = (
            _utc_now_datetime() if at is None else _parse_expected_deadline(at)
        )
        result = ensure_scheduler_training_package(
            scheduler_plan,
            morning_record_path=morning_record,
            input_cache_dir=input_cache_dir,
            generated_at=generated_at,
        )
    except (OSError, SQLAlchemyError, SchedulerError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": "ready",
                "mode": result.mode,
                "actionable": result.actionable,
                "plan_id": result.plan_id,
                "drawing": result.drawing,
                "drawing_id": result.drawing_id,
                "pipeline": result.pipeline,
                "structural_status": result.structural_status,
                "requested_bank": result.requested_bank,
                "effective_budget": result.effective_budget,
                "selected_count": result.selected_count,
                "selected_cost": result.selected_cost,
                "unused_requested_bank": result.unused_requested_bank,
                "bank_usage_reason": result.bank_usage_reason,
                "source_archive_path": str(result.source_archive_path),
                "source_archive_snapshot_sha256": (
                    result.source_archive_snapshot_sha256
                ),
                "package_sha256": result.package_sha256,
                "result_path": str(result.result_path),
                "input_path": str(result.input_path),
                "paper_path": str(result.paper_path),
                "diagnostics_path": str(result.diagnostics_path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


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
            package_provenance_required=(mode == "playable"),
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
    schedule_evidence_ledger: str = typer.Option(
        str(DEFAULT_SCHEDULE_EVIDENCE_PATH),
        "--schedule-evidence-ledger",
    ),
    expected_schedule_evidence_sha256: str | None = typer.Option(
        None, "--expected-schedule-evidence-sha256"
    ),
    expected_schedule_evidence_semantic_hash: str | None = typer.Option(
        None, "--expected-schedule-evidence-semantic-hash"
    ),
) -> None:
    """Prepare exact immutable fixture/team/time pins for one drawing."""
    if open == (drawing_id is not None):
        raise typer.BadParameter("choose exactly one of --open or --drawing-id")
    if provider != "api-sports":
        raise typer.BadParameter("provider must be api-sports")
    if (expected_schedule_evidence_sha256 is None) != (
        expected_schedule_evidence_semantic_hash is None
    ):
        raise typer.BadParameter(
            "both expected schedule-evidence hashes must be supplied together"
        )
    resolved_schedule_evidence_ledger = resolve_contained_path(
        schedule_evidence_ledger,
        allowed_root=Path.cwd(),
    )
    try:
        load_bound_schedule_evidence_ledger(
            resolved_schedule_evidence_ledger,
            expected_content_sha256=expected_schedule_evidence_sha256,
            expected_semantic_hash=expected_schedule_evidence_semantic_hash,
        )
    except ScheduleEvidenceIntegrityError as error:
        typer.echo(f"preparation integrity failure: {error}", err=True)
        raise typer.Exit(code=SCHEDULER_INTEGRITY_EXIT_CODE) from error
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
        try:
            result = prepare_drawing(
                target,
                candidates,
                session_factory=session_factory,
                provider=provider,
                schedule_diagnostics=schedule_diagnostics,
                reviewed_schedule_catalog=reviewed_schedule_catalog,
                schedule_evidence_ledger=resolved_schedule_evidence_ledger,
                expected_schedule_evidence_sha256=(expected_schedule_evidence_sha256),
                expected_schedule_evidence_semantic_hash=(
                    expected_schedule_evidence_semantic_hash
                ),
                evaluated_at=fetched_at,
            )
        except (TypeError, ValueError) as error:
            raise ScheduleEvidenceIntegrityError(
                str(error) or "drawing preparation integrity failure"
            ) from error
    except ScheduleEvidenceIntegrityError as error:
        typer.echo(f"preparation integrity failure: {error}", err=True)
        raise typer.Exit(code=SCHEDULER_INTEGRITY_EXIT_CODE) from error
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
                "external_coverage_count": result.external_coverage_count,
                "baseline_only_event_orders": result.baseline_only_event_orders,
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
    state_root: str = typer.Option(
        "data/scheduler/morning-dispatch",
        "--state-root",
    ),
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
            operational_cutoffs=load_verified_operational_cutoffs(
                state_root,
                project_root=Path.cwd(),
            ),
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
        "external_coverage_count": result.external_coverage_count,
        "baseline_only_event_orders": result.baseline_only_event_orders,
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


@app.command("collect-the-odds-api-shadow")
def collect_the_odds_api_shadow_command(
    open: bool = typer.Option(False),  # noqa: A002
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    quota_reserve: int = typer.Option(50, min=0),
    env_file: str = typer.Option(".env"),
    cache_root: str = typer.Option("data/external-cache/the-odds-api"),
    report_dir: str = typer.Option("reports/the-odds-api-shadow"),
) -> None:
    """Collect an isolated NOT_ACTIVATED The Odds API shadow snapshot."""
    if not open:
        raise typer.BadParameter("--open is required")
    api_key = ""
    try:
        api_key = load_the_odds_api_key(env_file)
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        reviewed_aliases = load_aliases(aliases)
        provider_client = TheOddsAPIClient(
            api_key,
            cache_dir=Path(cache_root),
            quota_reserve=quota_reserve,
        )
        snapshot = collect_open_external_odds(
            TotoBriefClient(),
            provider_client,
            session_factory,
            reviewed_aliases,
            fetched_at=datetime.now(timezone.utc),
        )
        paths = write_the_odds_shadow_reports(
            snapshot,
            request_evidence=provider_client.request_evidence,
            credit_state=provider_client.credit_state,
            credits_spent=provider_client.credits_spent,
            report_dir=report_dir,
        )
    except (
        TheOddsAPIError,
        OSError,
        SQLAlchemyError,
        TotoBriefRequestError,
        ValueError,
    ) as error:
        raise typer.BadParameter(
            _external_error_message(error, secret=api_key)
        ) from error

    consensus_count = sum(
        event.probability_source == "external_consensus" for event in snapshot.events
    )
    fallback_count = len(snapshot.events) - consensus_count
    typer.echo(
        json.dumps(
            {
                "activation_status": "NOT_ACTIVATED",
                "actionable": False,
                "drawing_id": snapshot.drawing_id,
                "drawing_number": snapshot.drawing_number,
                "collection_id": snapshot.collection_id,
                "matched_events": sum(
                    event.match_status == "matched" for event in snapshot.events
                ),
                "external_consensus_events": consensus_count,
                "fallback_events": fallback_count,
                "requests_made": snapshot.requests_made,
                "cache_hits": snapshot.cache_hits,
                "credits_spent": provider_client.credits_spent,
                "credits_remaining": provider_client.credit_state.remaining,
                "json_report": str(paths.json_path),
                "csv_report": str(paths.csv_path),
                "markdown_report": str(paths.markdown_path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command("collect-the-odds-api-checkpoint")
def collect_the_odds_api_checkpoint_command(
    open: bool = typer.Option(False),  # noqa: A002
    checkpoint: str = typer.Option(...),
    db: str = typer.Option("data/toto.db"),
    aliases: str = typer.Option("data/external-odds/team-aliases.json"),
    quota_reserve: int = typer.Option(50, min=0),
    env_file: str = typer.Option(".env"),
    cache_root: str = typer.Option("data/external-cache/the-odds-api"),
    report_dir: str = typer.Option("reports/the-odds-api-shadow"),
) -> None:
    """Collect one idempotent NOT_ACTIVATED prospective checkpoint."""
    if not open:
        raise typer.BadParameter("--open is required")
    api_key = ""
    try:
        api_key = load_the_odds_api_key(env_file)
        engine = init_db(db)
        session_factory = get_session_factory(engine)
        reviewed_aliases = load_aliases(aliases)
        target = resolve_open_target(
            TotoBriefClient(),
            fetched_at=datetime.now(timezone.utc),
        )
        result = collect_shadow_checkpoint(
            target=target,
            checkpoint=checkpoint,
            provider_factory=lambda: TheOddsAPIClient(
                api_key,
                cache_dir=Path(cache_root),
                quota_reserve=quota_reserve,
            ),
            session_factory=session_factory,
            aliases=reviewed_aliases,
            quota_reserve=quota_reserve,
            report_dir=report_dir,
        )
    except (
        TheOddsAPIError,
        OSError,
        SQLAlchemyError,
        TotoBriefRequestError,
        ValueError,
    ) as error:
        raise typer.BadParameter(
            _external_error_message(error, secret=api_key)
        ) from error

    typer.echo(
        json.dumps(
            {
                "activation_status": "NOT_ACTIVATED",
                "actionable": False,
                "drawing_id": target.drawing_id,
                "drawing_number": target.drawing_number,
                "checkpoint": checkpoint,
                "checkpoint_id": result.checkpoint_id,
                "collection_id": result.collection_id,
                "status": result.status,
                "credits_spent": result.credits_spent,
                "credits_spent_this_run": result.credits_spent_this_run,
                "reused": result.reused,
                "manifest_path": str(result.manifest_path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command("audit-external-coverage")
def audit_external_coverage_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(30, min=1),
    min_bookmakers: int = typer.Option(3, min=1),
    provider: str = typer.Option("api-sports"),
    report_dir: str = typer.Option("reports"),
) -> None:
    """Audit stored external-odds coverage without provider network access."""
    try:
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        if provider not in {"api-sports", "the-odds-api"}:
            raise ValueError("provider must be api-sports or the-odds-api")
        audit = audit_external_coverage(
            session_factory,
            last=last,
            minimum_bookmakers=min_bookmakers,
            provider=provider,
        )
        scoped_report_dir = (
            Path(report_dir)
            if provider == "api-sports"
            else Path(report_dir) / provider
        )
        paths = write_external_coverage_reports(
            audit,
            report_dir=scoped_report_dir,
        )
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


@app.command("compare-package-strategies")
def compare_package_strategies_command(
    final_input: Path = typer.Option(  # noqa: B008
        ...,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Immutable scheduler final-input.json.",
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Hash-bound schema-v7 scheduler-plan.json.",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("reports/strategy-comparison"),
        "--output-dir",
        file_okay=False,
        resolve_path=True,
        help="Destination for paper-only comparison artifacts.",
    ),
) -> None:
    """Compare EV, BK-only, Cover-13/14 and BK-filled Cover-14."""
    try:
        executed = execute_final_input_comparison(
            final_input_path=final_input,
            scheduler_plan_path=scheduler_plan,
            output_dir=output_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title="Equal-Input Package Strategy Comparison")
    table.add_column("Strategy")
    table.add_column("Cat", justify="right")
    table.add_column("Coupons", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("P(13+)", justify="right")
    table.add_column("P(14+)", justify="right")
    table.add_column("P(15)", justify="right")
    for result in executed.bundle.results:
        table.add_row(
            result.strategy_id,
            str(result.category),
            str(result.coupon_count),
            str(result.cost),
            f"{result.probability_at_least_13:.8f}",
            f"{result.probability_at_least_14:.8f}",
            f"{result.probability_at_least_15:.8f}",
        )
    print(table)
    print("[yellow]RESEARCH/PAPER — NOT ACTIONABLE[/yellow]")
    print(f"Manifest: {executed.reports.manifest}")


@app.command("compare-category-hit-strategies")
def compare_category_hit_strategies_command(
    final_input: Path = typer.Option(  # noqa: B008
        ...,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Immutable scheduler final-input.json.",
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Hash-bound scheduler-plan.json for the same drawing.",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("reports/category-hit-comparison"),
        "--output-dir",
        file_okay=False,
        resolve_path=True,
        help="Destination for isolated paper-only comparison artifacts.",
    ),
) -> None:
    """Compare fast BK-only and BK-filled Cover-14 candidates."""
    try:
        executed = execute_final_input_category_hit_comparison(
            final_input_path=final_input,
            scheduler_plan_path=scheduler_plan,
            output_dir=output_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title="Lightweight Category-Hit Strategy Comparison")
    table.add_column("Strategy")
    table.add_column("Cat", justify="right")
    table.add_column("Coupons", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("P(13+)", justify="right")
    table.add_column("P(14+)", justify="right")
    table.add_column("P(15)", justify="right")
    for result in executed.bundle.results:
        table.add_row(
            result.strategy_id,
            str(result.category),
            str(result.coupon_count),
            str(result.cost),
            f"{result.probability_at_least_13:.8f}",
            f"{result.probability_at_least_14:.8f}",
            f"{result.probability_at_least_15:.8f}",
        )
    print(table)
    print("[yellow]RESEARCH/PAPER — NOT ACTIONABLE[/yellow]")
    print("[yellow]Scheduler plan and scheduler state are read-only.[/yellow]")
    print(f"Manifest: {executed.reports.manifest}")


@app.command("historical-strategy-benchmark")
def historical_strategy_benchmark_command(
    db: Path = typer.Option(  # noqa: B008
        Path("data/toto.db"),
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="SQLite database with immutable RAW/result snapshots.",
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Scheduler plan whose production objective is reused.",
    ),
    last: int = typer.Option(
        3,
        "--last",
        min=1,
        help="Latest strict chronological drawings to evaluate.",
    ),
    bank: int = typer.Option(
        4_980,
        "--bank",
        min=1,
        help="Research budget; must be divisible by stake.",
    ),
    stake: int = typer.Option(
        30,
        "--stake",
        min=1,
        help="Stake per coupon.",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("reports/research/strict-strategy-benchmark"),
        "--output-dir",
        file_okay=False,
        resolve_path=True,
        help="Destination for strict paper-only benchmark artifacts.",
    ),
) -> None:
    """Score equal-input strategies on true pre-deadline snapshots."""
    try:
        plan = load_scheduler_plan(scheduler_plan)
        config = historical_ev_config(
            plan.quality_v2_ev_config,
            bank=bank,
            stake=stake,
        )
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task(
                "strict benchmark: loading chronological cases",
                total=last,
            )

            def update_progress(
                index: int,
                total: int,
                drawing_number: int,
                status: str,
            ) -> None:
                progress.update(
                    task,
                    total=total,
                    completed=index if status == "complete" else index - 1,
                    description=(f"drawing={drawing_number} {index}/{total} {status}"),
                )

            with session_factory() as session:
                benchmark = run_strict_historical_benchmark(
                    session,
                    db_path=db,
                    last=last,
                    bank=bank,
                    stake=stake,
                    ev_config=config,
                    progress_callback=update_progress,
                )
        paths = write_strict_historical_benchmark_reports(
            benchmark,
            output_dir,
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title="Strict Historical Strategy Benchmark")
    table.add_column("Strategy")
    table.add_column("Drawings", justify="right")
    table.add_column("Avg best", justify="right")
    table.add_column("Hit 13+", justify="right")
    table.add_column("Hit 14+", justify="right")
    table.add_column("Hit 15", justify="right")
    strategies = benchmark.summary["strategies"]
    for strategy_id in sorted(strategies):
        row = strategies[strategy_id]
        table.add_row(
            strategy_id,
            str(row["drawings"]),
            f"{row['average_best_hits']:.3f}",
            f"{row['hit_13_count']}/{row['drawings']}",
            f"{row['hit_14_count']}/{row['drawings']}",
            f"{row['hit_15_count']}/{row['drawings']}",
        )
    control = benchmark.summary["bk_top_control"]
    table.add_row(
        "BK_TOP_SINGLE_CONTROL",
        str(control["drawings"]),
        f"{control['average_hits']:.3f}",
        f"{control['hit_13_count']}/{control['drawings']}",
        f"{control['hit_14_count']}/{control['drawings']}",
        f"{control['hit_15_count']}/{control['drawings']}",
    )
    print(table)
    print(
        "[yellow]STRICT CHRONOLOGICAL PIPELINE EVIDENCE — "
        "NOT RELEASE EVIDENCE — NOT ACTIONABLE[/yellow]"
    )
    print(f"Manifest: {paths.manifest}")


@app.command("legacy-strategy-benchmark")
def legacy_strategy_benchmark_command(
    db: Path = typer.Option(  # noqa: B008
        Path("data/toto.db"),
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="SQLite database with retrospective current-state rows.",
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Scheduler plan whose production objective is reused.",
    ),
    last: int = typer.Option(
        100,
        "--last",
        min=1,
        help="Latest legacy probability-eligible drawings to evaluate.",
    ),
    bank: int = typer.Option(4_980, "--bank", min=1),
    stake: int = typer.Option(30, "--stake", min=1),
    checkpoint_dir: Path = typer.Option(  # noqa: B008
        Path("reports/research/legacy-strategy-checkpoints"),
        "--checkpoint-dir",
        file_okay=False,
        resolve_path=True,
        help="Reusable per-drawing checkpoints for long diagnostics.",
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        Path("reports/research/legacy-strategy-benchmark"),
        "--output-dir",
        file_okay=False,
        resolve_path=True,
        help="Destination for non-release retrospective reports.",
    ),
) -> None:
    """Run resumable legacy diagnostics without claiming chronology."""
    try:
        plan = load_scheduler_plan(scheduler_plan)
        config = historical_ev_config(
            plan.quality_v2_ev_config,
            bank=bank,
            stake=stake,
        )
        engine = open_readonly_db(db)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            cases = load_legacy_retrospective_cases(
                session,
                db_path=db,
                last=last,
                bank=bank,
                stake=stake,
            )
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task(
                "legacy diagnostic: loading current-state rows",
                total=len(cases),
            )

            def update_progress(
                index: int,
                total: int,
                drawing_number: int,
                status: str,
            ) -> None:
                progress.update(
                    task,
                    total=total,
                    completed=index if status != "running" else index - 1,
                    description=(f"drawing={drawing_number} {index}/{total} {status}"),
                )

            benchmark = benchmark_legacy_retrospective_cases(
                cases,
                ev_config=config,
                checkpoint_dir=checkpoint_dir,
                progress_callback=update_progress,
            )
        paths = write_legacy_retrospective_benchmark_reports(
            benchmark,
            output_dir,
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    table = Table(title="Legacy Retrospective Strategy Diagnostic")
    table.add_column("Strategy")
    table.add_column("Drawings", justify="right")
    table.add_column("Avg best", justify="right")
    table.add_column("Hit 13+", justify="right")
    table.add_column("Hit 14+", justify="right")
    table.add_column("Hit 15", justify="right")
    strategies = benchmark.summary["strategies"]
    for strategy_id in sorted(strategies):
        row = strategies[strategy_id]
        table.add_row(
            strategy_id,
            str(row["drawings"]),
            f"{row['average_best_hits']:.3f}",
            f"{row['hit_13_count']}/{row['drawings']}",
            f"{row['hit_14_count']}/{row['drawings']}",
            f"{row['hit_15_count']}/{row['drawings']}",
        )
    control = benchmark.summary["bk_top_control"]
    table.add_row(
        "BK_TOP_SINGLE_CONTROL",
        str(control["drawings"]),
        f"{control['average_hits']:.3f}",
        f"{control['hit_13_count']}/{control['drawings']}",
        f"{control['hit_14_count']}/{control['drawings']}",
        f"{control['hit_15_count']}/{control['drawings']}",
    )
    print(table)
    print(
        "[yellow]LEGACY_RETROSPECTIVE — NOT RELEASE EVIDENCE — NOT ACTIONABLE[/yellow]"
    )
    print(f"Resumed drawings: {benchmark.summary['resumed_drawings']}")
    print(f"Manifest: {paths.manifest}")


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


@app.command("sports-probability-shadow")
def sports_probability_shadow_command(
    drawing_id: int | None = typer.Option(None, "--drawing-id", min=1),
    drawing_number: int | None = typer.Option(None, "--drawing-number", min=1),
    as_of: str = typer.Option(..., "--as-of"),
    db: str = typer.Option("data/toto.db"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    report_dir: str = typer.Option(
        "reports/sports-probability-shadow",
        "--report-dir",
    ),
) -> None:
    """Build a machine-readable NOT_ACTIVATED sports probability shadow."""
    try:
        parsed_as_of = parse_historical_as_of(as_of)
        if parsed_as_of is None:
            raise ValueError("--as-of is required")
        artifact, path = build_and_write_sports_probability_shadow(
            db=db,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            as_of=parsed_as_of,
            raw_cache_dir=raw_cache_dir,
            report_dir=report_dir,
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": artifact.status,
                "model_status": artifact.model_status,
                "drawing_id": artifact.drawing_id,
                "drawing_number": artifact.drawing_number,
                "sports_coverage_count": artifact.sports_coverage_count,
                "fallback_count": artifact.fallback_count,
                "artifact": str(path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


@app.command("compare-preliminary-packages")
def compare_preliminary_packages_command(
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    bank: int = typer.Option(4980, "--bank", min=30),
    stake: int = typer.Option(30, "--stake", min=1),
    as_of: str = typer.Option(..., "--as-of"),
    sports_artifact: str = typer.Option(..., "--sports-artifact"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    output_dir: str = typer.Option(
        "reports/preliminary-package-comparison", "--output-dir"
    ),
    monte_carlo_samples: int = typer.Option(2048, "--monte-carlo-samples", min=1),
) -> None:
    """Compare equal-budget BK and sports-shadow packages — PAPER ONLY."""

    try:
        parsed_as_of = parse_historical_as_of(as_of)
        if parsed_as_of is None:
            raise ValueError("--as-of is required")
        report, json_path, baseline_path, candidate_path = compare_preliminary_packages(
            drawing_id=drawing_id,
            bank=bank,
            stake=stake,
            as_of=parsed_as_of,
            raw_cache_dir=raw_cache_dir,
            sports_artifact_path=sports_artifact,
            output_dir=output_dir,
            monte_carlo_samples=monte_carlo_samples,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_number": report["drawing_number"],
                "sports_coverage_count": report["sports_coverage_count"],
                "sports_fallback_count": report["sports_fallback_count"],
                "comparison": report["comparison"],
                "report": str(json_path),
                "baseline_package": str(baseline_path),
                "sports_package": str(candidate_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("collect-goal-shadow-input")
def collect_goal_shadow_input_command(
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    queue: str = typer.Option(..., "--queue"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    output_dir: str = typer.Option(..., "--output-dir"),
    env_file: str = typer.Option(".env", "--env-file"),
    request_budget: int = typer.Option(120, "--request-budget", min=30, max=120),
) -> None:
    """Freeze a 15-event GOAL sports-shadow input — RESEARCH ONLY."""

    try:
        api_key = load_goal_api_key(env_file)
        if api_key is None:
            raise ValueError("GOAL_API_KEY is required")
        client = GoalAPIClient(
            api_key,
            snapshot_dir=Path(output_dir) / "schedule" / "goal-api-v1",
            request_budget=request_budget,
        )
        result = collect_goal_probe_input(
            drawing_id=drawing_id,
            queue_path=queue,
            raw_cache_dir=raw_cache_dir,
            output_dir=output_dir,
            client=client,
            project_root=Path.cwd(),
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": "PAPER_ONLY_COVERAGE_PROBE",
                "drawing_id": drawing_id,
                "event_count": result.event_count,
                "history_source_count": result.history_source_count,
                "sports_eligible_count": result.sports_eligible_count,
                "request_count": result.request_count,
                "quota_daily_remaining": result.quota_daily_remaining,
                "captured_at": result.captured_at.isoformat(),
                "coverage_summary": str(result.coverage_summary_path),
                "schedule_report": str(result.schedule_report_path),
                "package_influence": "NONE",
                "automatic_wagering": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("compare-goal-shadow-packages")
def compare_goal_shadow_packages_command(
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    bank: int = typer.Option(4980, "--bank", min=30),
    stake: int = typer.Option(30, "--stake", min=1),
    as_of: str = typer.Option(..., "--as-of"),
    coverage_summary: str = typer.Option(..., "--coverage-summary"),
    raw_cache_dir: str = typer.Option("data/raw", "--raw-cache-dir"),
    output_dir: str = typer.Option(
        "reports/research/goal-sports-dual-package",
        "--output-dir",
    ),
    monte_carlo_samples: int = typer.Option(
        2048,
        "--monte-carlo-samples",
        min=1,
    ),
) -> None:
    """Compare frozen BK and GOAL sports-shadow packages — RESEARCH ONLY."""

    try:
        parsed_as_of = parse_historical_as_of(as_of)
        if parsed_as_of is None:
            raise ValueError("--as-of is required")
        report, paths = run_goal_probe_package_comparison(
            drawing_id=drawing_id,
            bank=bank,
            stake=stake,
            as_of=parsed_as_of,
            raw_cache_dir=raw_cache_dir,
            coverage_summary_path=coverage_summary,
            output_dir=output_dir,
            project_root=Path.cwd(),
            monte_carlo_samples=monte_carlo_samples,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_number": report["drawing_number"],
                "sports_coverage_count": report["sports_coverage_count"],
                "sports_fallback_count": report["sports_fallback_count"],
                "overlap_count": report["comparison"]["overlap_count"],
                "manifest": str(paths.manifest),
                "comparison": str(paths.comparison_json),
                "analytics": str(paths.analytics_markdown),
                "baseline_package": str(paths.baseline_txt),
                "sports_package": str(paths.sports_txt),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("build-goal-sports-v2-shadow")
def build_goal_sports_v2_shadow_command(
    drawing_id: int = typer.Option(..., "--drawing-id", min=1),
    as_of: str = typer.Option(..., "--as-of"),
    coverage_summary: Path = typer.Option(  # noqa: B008
        ...,
        "--coverage-summary",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    raw_cache_dir: Path = typer.Option(  # noqa: B008
        Path("data/raw"),
        "--raw-cache-dir",
        exists=True,
        file_okay=False,
        readable=True,
        resolve_path=True,
    ),
    final_input: Path | None = typer.Option(  # noqa: B008
        None,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    scheduler_plan: Path | None = typer.Option(  # noqa: B008
        None,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--output-dir",
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Build a frozen Sports Analytics v2 shadow — RESEARCH ONLY."""

    try:
        parsed_as_of = parse_historical_as_of(as_of)
        if parsed_as_of is None:
            raise ValueError("--as-of is required")
        effective_cache = raw_cache_dir
        if (final_input is None) != (scheduler_plan is None):
            raise ValueError(
                "--final-input and --scheduler-plan must be provided together"
            )
        if final_input is not None and scheduler_plan is not None:
            frozen = load_historical_final_input(
                scheduler_plan_path=scheduler_plan,
                final_input_path=final_input,
            )
            if frozen.drawing_id != drawing_id:
                raise ValueError("final input drawing id mismatch")
            if parsed_as_of != frozen.captured_at:
                raise ValueError("--as-of must equal final-input captured_at")
            effective_cache = output_dir / "final-input-cache"
            write_drawing_detail_cache(
                dict(frozen.payload),
                drawing_id=drawing_id,
                cache_dir=effective_cache,
                fetched_at=frozen.captured_at,
                source=f"final-input:{frozen.snapshot_sha256}",
                allowed_root=Path.cwd(),
            )
        bundle = load_goal_probe_shadow(
            drawing_id=drawing_id,
            as_of=parsed_as_of,
            raw_cache_dir=effective_cache,
            coverage_summary_path=coverage_summary,
            project_root=Path.cwd(),
        )
        artifact = build_sports_v2_shadow_artifact(
            snapshot=bundle.snapshot,
            base_artifact=bundle.shadow,
        )
        path = write_shadow_probability_artifact(
            artifact,
            report_dir=output_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": artifact.status,
                "model_status": artifact.model_status,
                "drawing_number": artifact.drawing_number,
                "sports_coverage_count": artifact.sports_coverage_count,
                "fallback_count": artifact.fallback_count,
                "artifact": str(path),
                "automatic_wagering": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("compare-final-goal-hybrid")
def compare_final_goal_hybrid_command(
    final_input: Path = typer.Option(  # noqa: B008
        ...,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    sports_artifact: Path = typer.Option(  # noqa: B008
        ...,
        "--sports-artifact",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--output-dir",
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Compare production-hybrid BK/sports packages — RESEARCH ONLY."""

    try:
        report, paths = execute_final_hybrid_comparison(
            final_input_path=final_input,
            scheduler_plan_path=scheduler_plan,
            sports_artifact_path=sports_artifact,
            output_dir=output_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_number": report["drawing_number"],
                "sports_coverage_count": report["sports_coverage_count"],
                "sports_fallback_count": report["sports_fallback_count"],
                "comparison": report["comparison"],
                "report": str(paths.report),
                "baseline_package": str(paths.baseline_package),
                "sports_package": str(paths.sports_package),
                "robust_package": str(paths.robust_package),
                "quality_v3_package": str(paths.quality_v3_package),
                "uncertainty_package": str(paths.uncertainty_package),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("replay-quality-v2-v3")
def replay_quality_v2_v3_command(
    final_input: Path = typer.Option(  # noqa: B008
        ...,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    baseline_package: Path = typer.Option(  # noqa: B008
        ...,
        "--baseline-package",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    db: Path = typer.Option(  # noqa: B008
        Path("data/toto.db"),
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--output-dir",
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Replay frozen quality-v2 versus equal-cost quality-v3 — RESEARCH ONLY."""

    try:
        report, report_path = execute_quality_replay(
            final_input_path=final_input,
            scheduler_plan_path=scheduler_plan,
            baseline_package_path=baseline_package,
            db_path=db,
            output_dir=output_dir,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_number": report["drawing_number"],
                "settled": report["settled"],
                "equal_coupon_count": report["equal_coupon_count"],
                "equal_cost": report["equal_cost"],
                "settlement_comparison": report["settlement_comparison"],
                "report": str(report_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("replay-quality-sports-v2-robust")
def replay_quality_sports_v2_robust_command(
    final_input: Path = typer.Option(  # noqa: B008
        ...,
        "--final-input",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    baseline_package: Path = typer.Option(  # noqa: B008
        ...,
        "--baseline-package",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    sports_artifact: Path = typer.Option(  # noqa: B008
        ...,
        "--sports-artifact",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    db: Path = typer.Option(  # noqa: B008
        Path("data/toto.db"),
        "--db",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_dir: Path = typer.Option(  # noqa: B008
        ...,
        "--output-dir",
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Replay quality-v2, Sports v2, quality-v3 and robust — RESEARCH ONLY."""

    try:
        drawing_number = _replay_drawing_number(final_input)
        with _ReplayCommandProgress(drawing_number=drawing_number) as progress:
            report, report_path = execute_historical_hybrid_replay(
                final_input_path=final_input,
                scheduler_plan_path=scheduler_plan,
                baseline_package_path=baseline_package,
                sports_artifact_path=sports_artifact,
                db_path=db,
                output_dir=output_dir,
                progress_callback=progress.update,
            )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": report["status"],
                "drawing_number": report["drawing_number"],
                "equal_coupon_count": report["equal_coupon_count"],
                "equal_cost": report["equal_cost"],
                "quality_v2_reproduced_exactly": report[
                    "quality_v2_reproduced_exactly"
                ],
                "sports_coverage_count": report["sports_coverage_count"],
                "event_attribution": report["event_attribution"],
                "settlements": {
                    name: payload["settlement"]
                    for name, payload in report["strategies"].items()
                },
                "report": str(report_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("run-final-goal-hybrid-sidecar")
def run_final_goal_hybrid_sidecar_command(
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    sports_artifact: Path = typer.Option(  # noqa: B008
        ...,
        "--sports-artifact",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_root: Path = typer.Option(  # noqa: B008
        ...,
        "--output-root",
        file_okay=False,
        resolve_path=True,
    ),
    wait_seconds: int = typer.Option(600, "--wait-seconds", min=0, max=900),
    minimum_runtime_seconds: int = typer.Option(
        240,
        "--minimum-runtime-seconds",
        min=180,
        max=600,
    ),
    parallel_authorization: Path | None = typer.Option(  # noqa: B008
        None,
        "--parallel-authorization",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
) -> None:
    """Wait for final PLAY, then run the non-blocking sports sidecar."""

    try:
        result = run_final_hybrid_sidecar(
            scheduler_plan_path=scheduler_plan,
            sports_artifact_path=sports_artifact,
            output_root=output_root,
            wait_seconds=wait_seconds,
            minimum_runtime_seconds=minimum_runtime_seconds,
            parallel_authorization_path=parallel_authorization,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "result_path": str(result.result_path),
                "output_dir": (
                    None if result.output_dir is None else str(result.output_dir)
                ),
                "reason": result.reason,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if result.status not in {
        "READY_BEFORE_T10",
        "READY_PARALLEL_PLAY_BEFORE_T10",
    }:
        raise typer.Exit(code=1)


@app.command("parallel-release-authorize")
def parallel_release_authorize_command(
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    output_root: Path = typer.Option(  # noqa: B008
        ...,
        "--output-root",
        file_okay=False,
        resolve_path=True,
    ),
    acknowledge_unvalidated_manual_risk: bool = typer.Option(
        False,
        "--acknowledge-unvalidated-manual-risk",
    ),
) -> None:
    """Authorize one plan-bound parallel selector before T-10."""

    try:
        path = authorize_parallel_manual_release(
            scheduler_plan_path=scheduler_plan,
            output_root=output_root,
            acknowledged=acknowledge_unvalidated_manual_risk,
        )
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Authorization: {path}")
    typer.echo(
        "EXPERIMENTAL MANUAL ONLY: no automatic wager and no profitability claim."
    )


@app.command("parallel-sidecar-prepare")
def parallel_sidecar_prepare_command(
    scheduler_plan: Path = typer.Option(  # noqa: B008
        ...,
        "--scheduler-plan",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    coverage_summary: Path = typer.Option(  # noqa: B008
        ...,
        "--coverage-summary",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    as_of: str = typer.Option(..., "--as-of"),
    raw_cache_dir: Path = typer.Option(  # noqa: B008
        Path("data/raw"),
        "--raw-cache-dir",
        exists=True,
        file_okay=False,
        readable=True,
        resolve_path=True,
    ),
    python_executable: Path = typer.Option(  # noqa: B008
        Path(sys.executable),
        "--python-executable",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    activate: bool = typer.Option(False, "--activate"),
    acknowledge_unvalidated_manual_risk: bool = typer.Option(
        False,
        "--acknowledge-unvalidated-manual-risk",
    ),
) -> None:
    """Prepare one exact non-blocking four-strategy sidecar."""

    try:
        parsed_as_of = parse_historical_as_of(as_of)
        if parsed_as_of is None:
            raise ValueError("--as-of is required")
        plan = load_scheduler_plan(scheduler_plan)
        if plan.drawing_id is None:
            raise ValueError("scheduler plan requires drawing_id")
        sports_seed_as_of = _sports_seed_as_of(
            drawing_id=plan.drawing_id,
            requested_as_of=parsed_as_of,
            raw_cache_dir=raw_cache_dir,
            project_root=plan.project_root,
        )
        bundle = load_goal_probe_shadow(
            drawing_id=plan.drawing_id,
            as_of=sports_seed_as_of,
            raw_cache_dir=raw_cache_dir,
            coverage_summary_path=coverage_summary,
            project_root=plan.project_root,
        )
        sports_v2 = build_sports_v2_shadow_artifact(
            snapshot=bundle.snapshot,
            base_artifact=bundle.shadow,
        )
        parallel_root = plan.output_dir / "parallel-challenger"
        sports_path = write_shadow_probability_artifact(
            sports_v2,
            report_dir=parallel_root / "sports-seed",
        )
        authorization_path = (
            authorize_parallel_manual_release(
                scheduler_plan_path=scheduler_plan,
                output_root=parallel_root,
                acknowledged=True,
            )
            if acknowledge_unvalidated_manual_risk
            else None
        )
        artifacts = prepare_parallel_sidecar_artifacts(
            scheduler_plan_path=scheduler_plan,
            sports_artifact_path=sports_path,
            python_command=python_executable,
            parallel_authorization_path=authorization_path,
        )
        bound_sports = load_shadow_probability_artifact(
            artifacts.sports_artifact_path
        )
        if activate:
            activate_parallel_sidecar_launch_agent(artifacts)
    except (OSError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": "PARALLEL_SIDECAR_ACTIVATED"
                if activate
                else "PARALLEL_SIDECAR_PREPARED",
                "drawing_number": plan.drawing,
                "plan_id": plan.plan_id,
                "candidate_strategies": [
                    "quality-v2",
                    "sports-shadow",
                    "quality-v3",
                    "robust",
                ],
                "sports_coverage_count": bound_sports.sports_coverage_count,
                "sports_artifact": str(artifacts.sports_artifact_path),
                "scheduled_at": artifacts.scheduled_at.isoformat(),
                "launch_agent": str(artifacts.launch_agent_path),
                "launch_agent_label": artifacts.launch_agent_label,
                "parallel_release_authorized": (
                    artifacts.authorization_path is not None
                ),
                "reused": artifacts.reused,
                "primary_scheduler_affected": False,
                "automatic_wagering": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@app.command("evaluate-sports-probability-shadow")
def evaluate_sports_probability_shadow_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(100, "--last", min=1),
    minimum_drawings: int = typer.Option(30, "--minimum-drawings", min=30),
    minimum_events: int = typer.Option(450, "--minimum-events", min=450),
    minimum_sports_coverage: float = typer.Option(
        0.70,
        "--minimum-sports-coverage",
        min=0.70,
        max=1.0,
    ),
    calibration_tolerance: float = typer.Option(
        0.02,
        "--calibration-tolerance",
        min=0.0,
        max=0.02,
    ),
    report_dir: str = typer.Option(
        "reports/sports-probability-shadow",
        "--report-dir",
    ),
) -> None:
    """Run chronological OOS shadow evaluation; never activate production."""
    try:
        result, paths = evaluate_stored_sports_probability_shadow(
            db=db,
            last=last,
            report_dir=report_dir,
            minimum_drawings=minimum_drawings,
            minimum_events=minimum_events,
            minimum_sports_coverage=minimum_sports_coverage,
            calibration_tolerance=calibration_tolerance,
        )
    except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        json.dumps(
            {
                "status": result.status,
                "gate_status": result.activation_gate.status,
                "gate_passed": result.activation_gate.passed,
                "drawing_count": result.drawing_count,
                "event_count": result.event_count,
                "sports_coverage_count": result.sports_coverage_count,
                "fallback_count": result.fallback_count,
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
        ("structural status", package.structural_status),
        ("artifact class", package.artifact_class),
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
        revision = run_project_git("rev-parse", "HEAD")
        dirty = run_project_git("status", "--porcelain")
    except ProjectGitError as error:
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
