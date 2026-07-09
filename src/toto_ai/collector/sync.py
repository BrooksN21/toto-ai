from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.api.client import TotoBriefClient
from toto_ai.db.models import Drawing, Event, Quote


@dataclass(frozen=True)
class SyncResult:
    pages_fetched: int = 0
    drawings_seen: int = 0
    drawings_saved: int = 0
    events_saved: int = 0
    quotes_saved: int = 0


class Collector:
    """Incrementally collect TotoBrief drawing history into a database."""

    def __init__(
        self,
        client: TotoBriefClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.client = client
        self.session_factory = session_factory

    def sync(
        self,
        name: str = "baltbet-main",
        progress: Any | None = None,
    ) -> SyncResult:
        pages_fetched = 0
        drawings_seen = 0
        drawings_saved = 0
        events_saved = 0
        quotes_saved = 0
        page = 1
        task_id = None

        if progress is not None:
            task_id = progress.add_task("Collecting drawings", total=None)

        while True:
            payload = self.client.drawings(name=name, page=page)
            pages_fetched += 1
            drawings = payload.get("data", [])

            if not drawings:
                break

            drawings_seen += len(drawings)
            for drawing_summary in drawings:
                drawing_id = drawing_summary["id"]
                if progress is not None and task_id is not None:
                    progress.update(
                        task_id,
                        description=f"Collecting drawing {drawing_id}",
                    )

                if self._drawing_exists(drawing_id):
                    continue

                drawing_info = self.client.drawing_info(drawing_id).get("data", {})
                saved_events, saved_quotes = self._save_drawing(
                    drawing_summary=drawing_summary,
                    drawing_info=drawing_info,
                )
                drawings_saved += 1
                events_saved += saved_events
                quotes_saved += saved_quotes

            page += 1
            if progress is not None and task_id is not None:
                progress.advance(task_id)

        if progress is not None and task_id is not None:
            progress.update(
                task_id,
                description="Collection complete",
                completed=page - 1,
            )

        return SyncResult(
            pages_fetched=pages_fetched,
            drawings_seen=drawings_seen,
            drawings_saved=drawings_saved,
            events_saved=events_saved,
            quotes_saved=quotes_saved,
        )

    def _drawing_exists(self, drawing_id: int) -> bool:
        with self.session_factory() as session:
            return session.get(Drawing, drawing_id) is not None

    def _save_drawing(
        self,
        drawing_summary: dict[str, Any],
        drawing_info: dict[str, Any],
    ) -> tuple[int, int]:
        drawing_data = drawing_summary | drawing_info
        events = drawing_info.get("events") or []
        events_saved = 0
        quotes_saved = 0

        with self.session_factory.begin() as session:
            existing = session.get(Drawing, drawing_data["id"])
            if existing is not None:
                return 0, 0

            session.add(
                Drawing(
                    id=drawing_data["id"],
                    number=drawing_data.get("number"),
                    name=drawing_data.get("name"),
                    status=drawing_data.get("status"),
                    pool_sum=drawing_data.get("pool_sum"),
                    jackpot=drawing_data.get("jackpot"),
                    started_at=drawing_data.get("started_at"),
                    ended_at=drawing_data.get("ended_at"),
                )
            )

            for event in events:
                event_order = event.get("order")
                session.add(
                    Event(
                        drawing_id=drawing_data["id"],
                        event_order=event_order,
                        name=event.get("name"),
                        championship=event.get("championship"),
                        sport=event.get("sport"),
                        result=event.get("result"),
                        score=event.get("score"),
                    )
                )
                events_saved += 1

                quotes = event.get("quotes")
                if quotes:
                    session.add(
                        Quote(
                            drawing_id=drawing_data["id"],
                            event_order=event_order,
                            pool_win_1=quotes.get("pool_win_1"),
                            pool_draw=quotes.get("pool_draw"),
                            pool_win_2=quotes.get("pool_win_2"),
                            bk_win_1=quotes.get("bk_win_1"),
                            bk_draw=quotes.get("bk_draw"),
                            bk_win_2=quotes.get("bk_win_2"),
                            pin_win_1=quotes.get("pin_win_1"),
                            pin_draw=quotes.get("pin_draw"),
                            pin_win_2=quotes.get("pin_win_2"),
                            norm_win_1=quotes.get("norm_win_1"),
                            norm_draw=quotes.get("norm_draw"),
                            norm_win_2=quotes.get("norm_win_2"),
                        )
                    )
                    quotes_saved += 1

        return events_saved, quotes_saved

    def saved_drawing_ids(self) -> set[int]:
        with self.session_factory() as session:
            return set(session.scalars(select(Drawing.id)).all())
