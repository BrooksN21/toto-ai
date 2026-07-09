from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from toto_ai.collector.sync import Collector
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.db.session import init_db


class FakeClient:
    def __init__(self):
        self.drawings_calls = []
        self.info_calls = []

    def drawings(self, name="baltbet-main", page=1):
        self.drawings_calls.append({"name": name, "page": page})
        pages = {
            1: {"data": [{"id": 101, "number": 1}]},
            2: {"data": [{"id": 102, "number": 2}]},
            3: {"data": []},
        }
        return pages[page]

    def drawing_info(self, drawing_id):
        self.info_calls.append(drawing_id)
        return {
            "data": {
                "id": drawing_id,
                "number": drawing_id - 100,
                "name": "baltbet-main",
                "status": "finished",
                "pool_sum": 1000.5,
                "jackpot": 250.0,
                "started_at": "2026-01-01T10:00:00Z",
                "ended_at": "2026-01-01T12:00:00Z",
                "events": [
                    {
                        "order": 0,
                        "name": f"Event {drawing_id}",
                        "championship": "League",
                        "sport": "football",
                        "result": "win_1",
                        "score": "2:1",
                        "quotes": {
                            "pool_win_1": 1.5,
                            "pool_draw": 3.2,
                            "pool_win_2": 5.0,
                            "bk_win_1": 1.6,
                            "bk_draw": 3.3,
                            "bk_win_2": 5.1,
                            "pin_win_1": 1.7,
                            "pin_draw": 3.4,
                            "pin_win_2": 5.2,
                        },
                    }
                ],
            }
        }


def make_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_collector_fetches_all_pages_and_saves_drawings_events_quotes():
    client = FakeClient()
    session_factory = make_session_factory()
    collector = Collector(client=client, session_factory=session_factory)

    result = collector.sync(name="baltbet-main")

    assert client.drawings_calls == [
        {"name": "baltbet-main", "page": 1},
        {"name": "baltbet-main", "page": 2},
        {"name": "baltbet-main", "page": 3},
    ]
    assert client.info_calls == [101, 102]
    assert result.drawings_seen == 2
    assert result.drawings_saved == 2
    assert result.events_saved == 2
    assert result.quotes_saved == 2

    with session_factory() as session:
        drawings = session.scalars(select(Drawing).order_by(Drawing.id)).all()
        events = session.scalars(select(Event).order_by(Event.drawing_id)).all()
        quotes = session.scalars(select(Quote).order_by(Quote.drawing_id)).all()

    assert [drawing.id for drawing in drawings] == [101, 102]
    assert drawings[0].pool_sum == 1000.5
    assert events[0].name == "Event 101"
    assert events[0].event_order == 0
    assert quotes[0].pool_win_1 == 1.5
    assert quotes[0].pin_win_2 == 5.2


def test_collector_is_incremental_and_skips_existing_drawings():
    client = FakeClient()
    session_factory = make_session_factory()
    collector = Collector(client=client, session_factory=session_factory)

    first = collector.sync(name="baltbet-main")
    second = collector.sync(name="baltbet-main")

    assert first.drawings_saved == 2
    assert second.drawings_saved == 0
    assert second.events_saved == 0
    assert second.quotes_saved == 0
    assert client.info_calls == [101, 102]

    with session_factory() as session:
        drawing_count = len(session.scalars(select(Drawing)).all())
        event_count = len(session.scalars(select(Event)).all())
        quote_count = len(session.scalars(select(Quote)).all())

    assert drawing_count == 2
    assert event_count == 2
    assert quote_count == 2


def test_init_db_creates_sqlite_database(tmp_path):
    db_path = tmp_path / "nested" / "toto.db"

    engine = init_db(db_path)

    assert db_path.exists()
    assert set(inspect(engine).get_table_names()) == {"drawings", "events", "quotes"}
    engine.dispose()
