import copy
import sqlite3
from datetime import datetime, timezone

import requests
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.api.rate_limit import TotoBriefRequestError
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
                        "id": drawing_id * 100 + order,
                        "order": order,
                        "name": f"Event {drawing_id}-{order}",
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
                    for order in range(15)
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
    assert result.events_saved == 30
    assert result.quotes_saved == 30

    with session_factory() as session:
        drawings = session.scalars(select(Drawing).order_by(Drawing.id)).all()
        events = session.scalars(select(Event).order_by(Event.drawing_id)).all()
        quotes = session.scalars(select(Quote).order_by(Quote.drawing_id)).all()

    assert [drawing.id for drawing in drawings] == [101, 102]
    assert drawings[0].pool_sum == 1000.5
    assert events[0].name == "Event 101-0"
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
    assert event_count == 30
    assert quote_count == 30


def test_init_db_creates_sqlite_database(tmp_path):
    db_path = tmp_path / "nested" / "toto.db"

    engine = init_db(db_path)

    assert db_path.exists()
    assert set(inspect(engine).get_table_names()) == {
        "archived_packages",
        "drawing_event_pins",
        "drawing_preparations",
        "drawing_result_snapshots",
        "drawings",
        "events",
        "external_bookmaker_quotes",
        "external_collection_runs",
        "external_event_dispositions",
        "package_settlements",
        "quotes",
        "team_aliases",
        "team_entities",
        "team_registry_reviews",
    }
    engine.dispose()


def test_init_db_backfills_legacy_preparation_independent_of_archive_migration(
    tmp_path,
):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE drawing_preparations (
                drawing_id INTEGER PRIMARY KEY,
                created_at VARCHAR NOT NULL
            );
            INSERT INTO drawing_preparations (drawing_id, created_at)
            VALUES (11970, '2026-07-22T10:00:00+00:00');
            CREATE TABLE archived_packages (
                archive_sha256 VARCHAR PRIMARY KEY,
                provenance VARCHAR NOT NULL,
                archive_manifest_sha256 VARCHAR
            );
            """
        )

    engine = init_db(db_path)
    columns = {
        column["name"]
        for column in inspect(engine).get_columns("drawing_preparations")
    }
    with sqlite3.connect(db_path) as connection:
        updated_at = connection.execute(
            "SELECT updated_at FROM drawing_preparations WHERE drawing_id = 11970"
        ).fetchone()[0]

    assert "updated_at" in columns
    assert updated_at == "2026-07-22T10:00:00+00:00"
    engine.dispose()


def _live_detail(drawing_id=11970):
    return {
        "data": {
            "id": drawing_id,
            "number": 4952,
            "name": "baltbet-main",
            "status": "active",
            "pool_sum": 1234,
            "jackpot": 500,
            "started_at": None,
            "ended_at": "2026-07-22T16:00:00Z",
            "events": [
                {
                    "id": 20_000 + order,
                    "order": order,
                    "name": f"Home {order} - Away {order}",
                    "championship": "Test League",
                    "sport": "football",
                    "result": None,
                    "score": None,
                    "quotes": {
                        "pool_win_1": 34,
                        "pool_draw": 33,
                        "pool_win_2": 33,
                        "bk_win_1": 34,
                        "bk_draw": 33,
                        "bk_win_2": 33,
                    },
                }
                for order in range(15)
            ],
        }
    }


class LivePageClient:
    def __init__(self, *, fail_detail=False, current_status="active"):
        self.fail_detail = fail_detail
        self.current_status = current_status
        self.info_calls = []

    def drawings(self, name="baltbet-main", page=1):
        assert page == 1
        return {
            "data": [
                {"id": 11966, "number": 4949, "status": "finished"},
                {"id": 11964, "number": 4950, "status": "finished"},
                {"id": 11968, "number": 4951, "status": "finished"},
                {
                    "id": 11970,
                    "number": 4952,
                    "status": self.current_status,
                    "ended_at": "2026-07-22T16:00:00Z",
                },
            ]
        }

    def drawing_info(self, drawing_id):
        self.info_calls.append(drawing_id)
        if self.fail_detail:
            raise TotoBriefRequestError(
                "HTTP 429 after bounded retries",
                endpoint=f"/drawing-info/{drawing_id}",
                attempts=4,
                status_code=429,
            )
        return _live_detail(drawing_id)


def _seed_stale_drawings(factory):
    with factory.begin() as session:
        for drawing_id, number in (
            (11966, 4949),
            (11964, 4950),
            (11968, 4951),
        ):
            session.add(
                Drawing(
                    id=drawing_id,
                    number=number,
                    name="baltbet-main",
                    status="expected",
                )
            )
            for order in range(15):
                session.add(
                    Event(
                        drawing_id=drawing_id,
                        event_order=order,
                        name=f"old {order}",
                    )
                )
                session.add(
                    Quote(
                        drawing_id=drawing_id,
                        event_order=order,
                        pool_win_1=34,
                        pool_draw=33,
                        pool_win_2=33,
                        bk_win_1=34,
                        bk_draw=33,
                        bk_win_2=33,
                    )
                )


def test_page_status_updates_commit_even_when_current_detail_is_deferred():
    factory = make_session_factory()
    _seed_stale_drawings(factory)
    client = LivePageClient(fail_detail=True)
    collector = Collector(client, factory)

    result = collector.sync(max_pages=1)

    assert result.details_deferred == 1
    assert client.info_calls == [11970]
    with factory() as session:
        assert session.get(Drawing, 11966).status == "finished"
        assert session.get(Drawing, 11964).status == "finished"
        assert session.get(Drawing, 11968).status == "finished"
        assert session.get(Drawing, 11970).status == "active"
        assert session.scalar(
            select(Event).where(Event.drawing_id == 11970)
        ) is None


def test_fresh_cached_11970_populates_missing_detail_without_network_or_duplicates(
    tmp_path,
):
    factory = make_session_factory()
    _seed_stale_drawings(factory)
    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        _live_detail(),
        drawing_id=11970,
        cache_dir=tmp_path,
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    client = LivePageClient(fail_detail=True)
    collector = Collector(
        client,
        factory,
        raw_cache_dir=tmp_path,
        storage_root=tmp_path,
        now=lambda: now,
    )

    first = collector.sync(max_pages=1)
    second = collector.sync(max_pages=1)

    assert first.details_deferred == 0
    assert first.detail_results[0].source == "cache:inspect-api"
    assert second.drawings_saved == 0
    assert client.info_calls == []
    with factory() as session:
        assert session.get(Drawing, 11966).status == "finished"
        assert session.get(Drawing, 11964).status == "finished"
        assert session.get(Drawing, 11968).status == "finished"
        assert session.get(Drawing, 11970).status == "active"
        assert len(
            session.scalars(
                select(Event).where(Event.drawing_id == 11970)
            ).all()
        ) == 15
        assert len(
            session.scalars(
                select(Quote).where(Quote.drawing_id == 11970)
            ).all()
        ) == 15


def test_fresh_cached_detail_cannot_roll_back_newer_page_status(tmp_path):
    factory = make_session_factory()
    _seed_stale_drawings(factory)
    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    write_drawing_detail_cache(
        _live_detail(),
        drawing_id=11970,
        cache_dir=tmp_path,
        fetched_at=now,
        source="inspect-api",
        allowed_root=tmp_path,
    )
    client = LivePageClient(fail_detail=True, current_status="finished")
    collector = Collector(
        client,
        factory,
        raw_cache_dir=tmp_path,
        storage_root=tmp_path,
        now=lambda: now,
    )

    result = collector.sync(max_pages=1)

    assert result.detail_results[0].source == "cache:inspect-api"
    assert client.info_calls == []
    with factory() as session:
        assert session.get(Drawing, 11970).status == "finished"


def test_partial_detail_does_not_mutate_complete_drawing_and_can_retry():
    factory = make_session_factory()
    seed_client = FakeClient()
    Collector(seed_client, factory).sync(max_pages=1)
    complete = seed_client.drawing_info(101)
    partial = copy.deepcopy(complete)
    partial["data"]["events"] = partial["data"]["events"][:1]

    class DetailSequenceClient:
        def __init__(self):
            self.payloads = [partial, complete]

        def drawing_info(self, drawing_id):
            assert drawing_id == 101
            return self.payloads.pop(0)

    collector = Collector(DetailSequenceClient(), factory)
    summary = {
        "id": 101,
        "number": 1,
        "status": "finished",
        "ended_at": "2026-01-01T12:00:00Z",
    }

    rejected = collector.sync_drawing_detail(
        101,
        drawing_summary=summary,
        force=True,
    )
    with factory() as session:
        assert len(
            session.scalars(select(Event).where(Event.drawing_id == 101)).all()
        ) == 15
        assert len(
            session.scalars(select(Quote).where(Quote.drawing_id == 101)).all()
        ) == 15
    retried = collector.sync_drawing_detail(
        101,
        drawing_summary=summary,
        force=True,
    )

    assert rejected.status == "deferred"
    assert "exactly 15" in (rejected.error or "")
    assert retried.status == "synchronized"
    with factory() as session:
        assert len(
            session.scalars(select(Event).where(Event.drawing_id == 101)).all()
        ) == 15
        assert len(
            session.scalars(select(Quote).where(Quote.drawing_id == 101)).all()
        ) == 15


def test_existing_partial_sqlite_detail_remains_eligible_for_retry():
    factory = make_session_factory()
    with factory.begin() as session:
        session.add(Drawing(id=101, number=1, name="baltbet-main"))
        session.add(Event(drawing_id=101, event_order=0, name="partial"))
        session.add(
            Quote(
                drawing_id=101,
                event_order=0,
                pool_win_1=34,
                pool_draw=33,
                pool_win_2=33,
                bk_win_1=34,
                bk_draw=33,
                bk_win_2=33,
            )
        )
    client = FakeClient()

    result = Collector(client, factory).sync_drawing_detail(101)

    assert result.status == "synchronized"
    assert client.info_calls == [101]
    with factory() as session:
        assert len(
            session.scalars(select(Event).where(Event.drawing_id == 101)).all()
        ) == 15
        assert len(
            session.scalars(select(Quote).where(Quote.drawing_id == 101)).all()
        ) == 15


def test_collector_diagnostic_sanitizes_raw_transport_url():
    class BrokenClient:
        def drawing_info(self, _drawing_id):
            raise requests.exceptions.ChunkedEncodingError(
                "broken https://totobrief.com/detail?api_key=do-not-print"
            )

    result = Collector(BrokenClient(), make_session_factory()).sync_drawing_detail(
        101,
        force=True,
    )

    assert result.status == "deferred"
    assert "ChunkedEncodingError" in (result.error or "")
    assert "do-not-print" not in (result.error or "")
    assert "https://" not in (result.error or "")
