from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from toto_ai.collector.lifecycle import (
    RawArchive,
    import_archived_detail,
)
from toto_ai.collector.sync import Collector
from toto_ai.db.models import (
    Base,
    Drawing,
    DrawingRawSnapshot,
    DrawingResultSnapshot,
    Event,
    Quote,
)
from toto_ai.operations.finished_draw import sync_finished_drawing

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _payload(
    *,
    drawing_id: int = 11975,
    number: int = 4954,
    status: str = "finished",
    complete: bool = True,
    zero_pool: bool = False,
    blank_fields: bool = False,
    void_order: int | None = None,
):
    events = []
    for order in range(15):
        result = ("1", "X", "2")[order % 3] if complete else None
        score = "2 : 1" if complete else None
        result_status = "resolved" if complete else None
        if order == void_order:
            result = "*"
            score = ""
            result_status = "void"
        event = {
                "id": drawing_id * 100 + order,
                "order": order,
                "name": "" if blank_fields else f"Home {order} — Away {order}",
                "championship": (
                    "" if blank_fields else "Test championship"
                ),
                "sport": "" if blank_fields else "football",
                "result": result,
                "result_status": result_status,
                "score": score,
                "quotes": {
                    "pool_win_1": 0 if zero_pool else 40,
                    "pool_draw": 0 if zero_pool else 30,
                    "pool_win_2": 0 if zero_pool else 30,
                    "bk_win_1": 41,
                    "bk_draw": 29,
                    "bk_win_2": 30,
                    "norm_win_1": 2.2,
                    "norm_draw": 3.3,
                    "norm_win_2": 3.4,
                },
            }
        if order == void_order:
            event["void_source"] = "https://example.test/official-void"
        events.append(event)
    return {
        "data": {
            "id": drawing_id,
            "number": number,
            "name": "baltbet-main",
            "status": status,
            "pool_sum": 1000,
            "jackpot": 200,
            "started_at": None,
            "ended_at": "2026-07-30T10:00:00Z",
            "events": events,
        }
    }


def _archive(tmp_path, payload, *, source="test"):
    return RawArchive(tmp_path / "raw-archive").archive(
        payload,
        captured_at=NOW,
        source=source,
        lifecycle_status=payload["data"]["status"],
    )


def test_active_cache_cannot_satisfy_finished_lifecycle(tmp_path):
    factory = _factory(tmp_path)
    active = _payload(status="active", complete=False)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11975,
                number=4954,
                name="baltbet-main",
                status="active",
                ended_at="2026-07-30T10:00:00Z",
            )
        )
    archive = _archive(tmp_path, active)
    import_archived_detail(factory, archive)
    with factory.begin() as session:
        session.get(Drawing, 11975).status = "finished"

    collector = Collector(
        client=object(),
        session_factory=factory,
        raw_archive_dir=tmp_path / "raw-archive",
    )

    assert collector.drawing_needs_detail(11975) is True


def test_finished_is_current_only_with_terminal_snapshot_bound_to_raw(tmp_path):
    factory = _factory(tmp_path)
    archive = _archive(tmp_path, _payload())
    result = import_archived_detail(factory, archive)

    assert result.terminal_result_count == 15
    assert result.result_snapshot_created is True
    assert (
        Collector(
            client=object(),
            session_factory=factory,
            raw_archive_dir=tmp_path / "raw-archive",
        ).drawing_needs_detail(11975)
        is False
    )
    with factory() as session:
        snapshot = session.scalar(select(DrawingResultSnapshot))
        assert snapshot.raw_snapshot_sha256 == archive.snapshot_sha256


def test_raw_is_durable_before_sql_and_retry_is_idempotent(tmp_path):
    factory = _factory(tmp_path)
    archive = _archive(tmp_path, _payload())

    def fail_before_commit(_session):
        raise RuntimeError("injected SQL failure")

    with pytest.raises(RuntimeError, match="injected"):
        import_archived_detail(
            factory,
            archive,
            before_commit=fail_before_commit,
        )

    assert archive.payload_path.is_file()
    assert archive.metadata_path.is_file()
    with factory() as session:
        assert session.get(Drawing, 11975) is None

    first = import_archived_detail(factory, archive)
    second = import_archived_detail(factory, archive)
    assert first.events_created == 15
    assert second.events_created == 0
    assert second.logical_changes == 0
    with factory() as session:
        assert len(session.scalars(select(DrawingRawSnapshot)).all()) == 1
        assert len(session.scalars(select(DrawingResultSnapshot)).all()) == 1


def test_full_import_merge_never_degrades_good_fields_or_pool(tmp_path):
    factory = _factory(tmp_path)
    good = _archive(tmp_path, _payload())
    import_archived_detail(factory, good)
    degraded_payload = _payload(zero_pool=True, blank_fields=True)
    degraded_payload["data"]["pool_sum"] = None
    degraded_payload["data"]["events"][0]["quotes"]["bk_win_1"] = None
    degraded = _archive(tmp_path, degraded_payload, source="degraded")

    import_archived_detail(factory, degraded)

    with factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.drawing_id == 11975,
                Event.event_order == 0,
            )
        )
        quote = session.scalar(
            select(Quote).where(
                Quote.drawing_id == 11975,
                Quote.event_order == 0,
            )
        )
        drawing = session.get(Drawing, 11975)
        assert event.name == "Home 0 — Away 0"
        assert event.championship == "Test championship"
        assert quote.pool_win_1 == 40
        assert quote.pool_draw == 30
        assert quote.pool_win_2 == 30
        assert quote.bk_win_1 == 41
        assert drawing.pool_sum == 1000


def test_void_requires_explicit_source_status(tmp_path):
    factory = _factory(tmp_path)
    implicit = _payload()
    implicit["data"]["events"][14]["result"] = "*"
    implicit["data"]["events"][14]["result_status"] = None
    implicit["data"]["events"][14]["score"] = ""
    implicit_archive = _archive(tmp_path, implicit)

    imported = import_archived_detail(factory, implicit_archive)

    assert imported.terminal_result_count == 14
    assert imported.result_snapshot_created is False
    explicit = _archive(tmp_path, _payload(void_order=14), source="explicit-void")
    imported = import_archived_detail(factory, explicit)
    assert imported.terminal_result_count == 15
    assert imported.result_snapshot_created is True
    with factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.drawing_id == 11975,
                Event.event_order == 14,
            )
        )
        assert event.result == "*"
        assert event.result_status == "void"


def test_offline_4954_style_repair_restores_full_detail_without_db_mutation(
    tmp_path,
):
    factory = _factory(tmp_path)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11975,
                number=4954,
                name="baltbet-main",
                status="finished",
                ended_at="2026-07-30T10:00:00Z",
            )
        )
        for order in range(15):
            session.add(Event(drawing_id=11975, event_order=order))
    payload = _payload(void_order=14)
    archive = _archive(tmp_path, payload, source="canonical-raw")

    dry_run = import_archived_detail(factory, archive, dry_run=True)
    with factory() as session:
        assert session.scalar(
            select(Event.name).where(
                Event.drawing_id == 11975,
                Event.event_order == 0,
            )
        ) is None
    assert dry_run.logical_changes > 0

    applied = import_archived_detail(factory, archive)
    assert applied.events_updated == 15
    assert applied.quotes_created == 15
    assert applied.result_snapshot_created is True


def test_archive_metadata_is_content_addressed_and_tamper_evident(tmp_path):
    archive_service = RawArchive(tmp_path / "raw-archive")
    first = archive_service.archive(
        _payload(),
        captured_at=NOW,
        source="totobrief-network",
        lifecycle_status="finished",
    )
    second = archive_service.archive(
        copy.deepcopy(_payload()),
        captured_at=NOW,
        source="totobrief-network",
        lifecycle_status="finished",
    )
    assert first.snapshot_sha256 == second.snapshot_sha256
    metadata = json.loads(first.metadata_path.read_text())
    assert metadata["captured_at"] == NOW.isoformat()
    assert metadata["source"] == "totobrief-network"
    assert metadata["lifecycle_status"] == "finished"
    assert metadata["payload_sha256"] == first.payload_sha256
    first.payload_path.write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        archive_service.verify(first)


def test_archive_recovers_payload_written_before_metadata(tmp_path):
    service = RawArchive(tmp_path / "raw-archive")
    first = service.archive(
        _payload(),
        captured_at=NOW,
        source="totobrief-network",
        lifecycle_status="finished",
    )
    first.metadata_path.unlink()

    recovered = service.archive(
        _payload(),
        captured_at=NOW,
        source="totobrief-network",
        lifecycle_status="finished",
    )

    assert recovered.created is True
    service.verify(recovered)


def test_explicit_finished_sync_uses_raw_first_full_import(tmp_path):
    factory = _factory(tmp_path)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11975,
                number=4954,
                name="baltbet-main",
                status="active",
                ended_at="2026-07-30T10:00:00+00:00",
            )
        )

    class Client:
        def drawing_info(self, drawing_id):
            assert drawing_id == 11975
            return _payload()

    synced = sync_finished_drawing(
        factory,
        Client(),
        drawing_id=11975,
        retrieved_at=NOW,
        raw_archive_root=tmp_path / "raw-archive",
    )

    assert synced.complete is True
    with factory() as session:
        raw = session.scalar(select(DrawingRawSnapshot))
        snapshot = session.scalar(select(DrawingResultSnapshot))
        assert raw is not None
        assert snapshot.raw_snapshot_sha256 == raw.snapshot_sha256
        assert session.scalar(
            select(Event.name).where(
                Event.drawing_id == 11975,
                Event.event_order == 0,
            )
        ) == "Home 0 — Away 0"
