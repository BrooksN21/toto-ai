import typer
from rich import print
from rich.json import JSON
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from toto_ai.analytics.api_inspector import (
    DrawingReference,
    compare_raw_json_to_db_model,
    inspect_json_paths,
    resolve_drawing_reference,
    save_raw_response,
)
from toto_ai.analytics.audit import get_database_audit
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
from toto_ai.db.session import get_session_factory, init_db
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


def _format_value(value: object, percent: bool = False) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        suffix = "%" if percent else ""
        return f"{value:.2f}{suffix}"
    return str(value)


if __name__ == "__main__":
    app()
