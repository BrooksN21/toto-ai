import typer
from rich import print

from toto_ai.api.client import TotoBriefClient

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


if __name__ == "__main__":
    app()
