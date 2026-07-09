import typer
from rich import print
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from toto_ai.analytics.history import (
    get_crowd_accuracy,
    get_drawings_summary,
    get_outcome_distribution,
    get_value_buckets,
)
from toto_ai.api.client import TotoBriefClient
from toto_ai.collector.sync import Collector
from toto_ai.db.session import get_session_factory, init_db

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


def _format_value(value: object, percent: bool = False) -> str:
    if isinstance(value, float):
        suffix = "%" if percent else ""
        return f"{value:.2f}{suffix}"
    return str(value)


if __name__ == "__main__":
    app()
