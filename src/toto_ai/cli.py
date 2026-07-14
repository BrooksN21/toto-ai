import subprocess
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
from toto_ai.collector.sync import Collector
from toto_ai.db.session import get_session_factory, init_db, open_readonly_db
from toto_ai.ev.benchmark import benchmark_ev_engine
from toto_ai.ev.drawing import (
    EVPackageRun,
    build_open_ev_package,
    resolve_open_drawing_from_api,
)
from toto_ai.ev.models import EVConfig
from toto_ai.ev.reports import write_ev_package_reports
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
from toto_ai.package.backtest import run_mvp_backtest, write_backtest_reports
from toto_ai.package.mvp import generate_mvp_package

app = typer.Typer(help="TotoBrief API commands.")


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

    print(
        f"Drawing {data.get('number')} | "
        f"{data.get('name')} | "
        f"{data.get('status')}"
    )

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
    collector = Collector(client=TotoBriefClient(), session_factory=session_factory)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        result = collector.sync(name=name, progress=progress)

    print(
        f"Collected {result.drawings_saved} new drawings "
        f"from {result.drawings_seen} seen across {result.pages_fetched} pages. "
        f"Saved {result.events_saved} events and {result.quotes_saved} quotes."
    )


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
        "Reports written to "
        f"{markdown_path}, {calibration_csv}, and {reliability_csv}"
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


@app.command("ev-package")
def ev_package_command(
    open: bool = typer.Option(False),  # noqa: A002
    mode: str = typer.Option("research"),
    bank: int = typer.Option(...),
    stake: int = typer.Option(30),
    min_gross_ev: float = typer.Option(1.0),
    prize_fund_factor: float = typer.Option(1.0),
    possible_winnings: float | None = typer.Option(None),
    jackpot: float | None = typer.Option(None),
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
            prize_fund_factor=prize_fund_factor,
            possible_winnings=possible_winnings,
        )
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
        TypeError,
        ValueError,
        requests.RequestException,
    ) as error:
        raise typer.BadParameter(str(error)) from error

    print(_ev_input_snapshot_table(result))
    print(_ev_package_summary_table(result))
    print(_ev_top_coupons_table(result))
    print(f"Reports written to {csv_path} and {markdown_path}")


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
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error

    csv_path, markdown_path = write_backtest_reports(result, last=last)
    print(_backtest_summary_table(result.summary))
    print(f"Reports written to {csv_path} and {markdown_path}")


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
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
        progress.update(task_id, description="Baseline brief backtest complete")

    csv_path, markdown_path = write_brief_backtest_reports(result, last=last)
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
                )
            except ValueError as error:
                raise typer.BadParameter(str(error)) from error
        progress.update(task_id, description="Strategy backtest complete")

    csv_path, markdown_path = write_strategy_backtest_reports(result, last=last)
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
    if (
        len(input_paths) != 3
        or len(output_paths) != 2
        or input_paths & output_paths
    ):
        raise typer.BadParameter(
            "Hybrid seal input and output paths must be distinct."
        )
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
        if not isinstance(seal, dict) or seal.get(
            "hybrid_code_version"
        ) != _git_code_version():
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
            raise ValueError(
                "Hybrid report and input paths must be distinct."
            )
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
        ("prize fund factor", f"{result.config.prize_fund_factor:.6f}"),
        ("probability source", "totobrief_bk (15/15)"),
        ("crowd joint model", "independent event marginals"),
    )
    for label, value in rows:
        table.add_row(label, str(value))
    return table


def _ev_package_summary_table(result: EVPackageRun) -> Table:
    package = result.package
    modeled_roi = "n/a" if package.modeled_roi is None else f"{package.modeled_roi:.6f}"
    table = Table(title="EV Package Summary")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    rows = (
        ("decision", package.decision),
        ("selected coupons", len(package.coupons)),
        ("cost", package.cost),
        ("unused bank", package.unused_bank),
        ("expected payout", f"{package.expected_payout:.6f}"),
        ("modeled ROI", modeled_roi),
        ("self-dilution ratio", f"{result.self_dilution_ratio:.6f}"),
        ("model supported", "yes" if result.model_supported else "no"),
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
