from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import (
    Base,
    Drawing,
    DrawingRawSnapshot,
    DrawingReconciliationState,
    DrawingResultSnapshot,
    Event,
    Quote,
)
from toto_ai.operations.finished_draw import sync_finished_drawing
from toto_ai.operations.reconciliation import repair_from_canonical_raw

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
DRAWING_ID = 11975
DRAWING_NUMBER = 4954
VOID_SOURCE = "https://example.test/official-postponement"


class _Client:
    def __init__(self, payload):
        self.payload = payload

    def drawing_info(self, drawing_id):
        assert drawing_id == DRAWING_ID
        return self.payload


def _factory(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False), db_path


def _payload(*, complete_void: bool = False):
    events = []
    for order in range(15):
        result = ("1", "X", "2")[order % 3]
        status = "resolved"
        score = "1 : 0"
        event = {
            "id": DRAWING_ID * 100 + order,
            "order": order,
            "name": f"Event {order}",
            "championship": "League",
            "sport": "football",
            "result": result,
            "result_status": status,
            "score": score,
            "quotes": {
                "pool_win_1": 40,
                "pool_draw": 30,
                "pool_win_2": 30,
                "bk_win_1": 40,
                "bk_draw": 30,
                "bk_win_2": 30,
            },
        }
        if order == 14:
            if complete_void:
                event.update(
                    result="*",
                    result_status="void",
                    score="",
                    void_source=VOID_SOURCE,
                )
            else:
                event.update(result="", result_status=None, score="")
        events.append(event)
    return {
        "data": {
            "id": DRAWING_ID,
            "number": DRAWING_NUMBER,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-30T10:00:00Z",
            "events": events,
        }
    }


def _seed_importer_loss(factory) -> None:
    with factory.begin() as session:
        session.add(
            Drawing(
                id=DRAWING_ID,
                number=DRAWING_NUMBER,
                name="baltbet-main",
                status="finished",
                ended_at="2026-07-30T10:00:00Z",
            )
        )
        for order in range(15):
            session.add(
                Event(
                    drawing_id=DRAWING_ID,
                    event_order=order,
                    result=("*" if order == 14 else ("1", "X", "2")[order % 3]),
                    result_status=None if order == 14 else "resolved",
                    score="" if order == 14 else "1 : 0",
                )
            )


def _seed_already_matching(factory) -> None:
    _seed_importer_loss(factory)
    with factory.begin() as session:
        for order in range(15):
            event = session.scalar(
                select(Event).where(
                    Event.drawing_id == DRAWING_ID,
                    Event.event_order == order,
                )
            )
            assert event is not None
            event.name = f"Event {order}"
            event.championship = "League"
            event.sport = "football"
            session.add(
                Quote(
                    drawing_id=DRAWING_ID,
                    event_order=order,
                    pool_win_1=40,
                    pool_draw=30,
                    pool_win_2=30,
                    bk_win_1=40,
                    bk_draw=30,
                    bk_win_2=30,
                )
            )


def _write_cache(tmp_path: Path):
    return write_drawing_detail_cache(
        _payload(),
        drawing_id=DRAWING_ID,
        cache_dir=tmp_path / "raw",
        fetched_at=NOW,
        source="inspect-api",
        allowed_root=tmp_path,
    )


def _add_reviewed_void_snapshot(factory, tmp_path: Path) -> str:
    result = sync_finished_drawing(
        factory,
        _Client(_payload()),
        drawing_id=DRAWING_ID,
        retrieved_at=NOW,
        void_event_orders=(15,),
        void_source=VOID_SOURCE,
    )
    assert result.actual.endswith("*")
    return result.snapshot_sha256


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _state_rows(db_path: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(db_path) as connection:
        return tuple(
            connection.execute(
                "SELECT drawing_id, provider, source, last_attempt_at, "
                "attempt_count, last_source_fingerprint, terminal_count, "
                "classification, retry_state, next_eligible_at, "
                "last_error_code, unchanged_observation_count, "
                "transient_error_count, updated_at "
                "FROM drawing_reconciliation_states ORDER BY id"
            )
        )


def _raw_classification(factory) -> str:
    with factory() as session:
        row = session.scalar(select(DrawingRawSnapshot))
        assert row is not None
        return row.classification


def test_first_repair_is_recovered_and_second_apply_is_byte_stable(tmp_path):
    engine, factory, db_path = _factory(tmp_path)
    _seed_importer_loss(factory)
    _write_cache(tmp_path)
    _add_reviewed_void_snapshot(factory, tmp_path)
    with factory() as session:
        before_void = session.scalar(
            select(Event).where(
                Event.drawing_id == DRAWING_ID,
                Event.event_order == 14,
            )
        )
        assert before_void is not None
        before_void_state = (
            before_void.result,
            before_void.result_status,
            before_void.score,
        )

    first = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    assert first.items[0].classification == "offline_repair_recovered"
    assert first.items[0].logical_changes > 0
    with factory() as session:
        event = session.scalar(
            select(Event).where(
                Event.drawing_id == DRAWING_ID,
                Event.event_order == 14,
            )
        )
        assert event is not None
        assert (event.result, event.result_status, event.score) == before_void_state

    engine.dispose()
    before_sha = _sha(db_path)
    before_archive = _tree(tmp_path / "archive")
    before_state = _state_rows(db_path)

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    factory = sessionmaker(engine, expire_on_commit=False)
    second = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    engine.dispose()

    assert second.items[0].status == "no_change"
    assert second.items[0].logical_changes == 0
    assert second.items[0].classification == "offline_repair_recovered"
    assert _sha(db_path) == before_sha
    assert _tree(tmp_path / "archive") == before_archive
    assert _state_rows(db_path) == before_state


def test_erroneous_source_incomplete_is_normalized_once_when_proven(tmp_path):
    engine, factory, db_path = _factory(tmp_path)
    _seed_importer_loss(factory)
    _write_cache(tmp_path)
    _add_reviewed_void_snapshot(factory, tmp_path)
    repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    with factory.begin() as session:
        session.execute(
            update(DrawingRawSnapshot).values(classification="source_incomplete")
        )
    assert _raw_classification(factory) == "source_incomplete"

    corrected = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    assert corrected.items[0].status == "repaired"
    assert corrected.items[0].logical_changes == 1
    assert corrected.items[0].classification == "offline_repair_recovered"

    engine.dispose()
    corrected_sha = _sha(db_path)
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    factory = sessionmaker(engine, expire_on_commit=False)
    second = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    engine.dispose()
    assert second.items[0].logical_changes == 0
    assert second.items[0].classification == "offline_repair_recovered"
    assert _sha(db_path) == corrected_sha


def test_ambiguous_source_incomplete_is_not_normalized(tmp_path):
    _engine, factory, _db_path = _factory(tmp_path)
    _seed_importer_loss(factory)
    _write_cache(tmp_path)
    first = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    assert first.items[0].classification == "offline_repair_recovered"
    with factory.begin() as session:
        session.execute(
            update(DrawingRawSnapshot).values(classification="source_incomplete")
        )
        session.execute(
            DrawingResultSnapshot.__table__.delete().where(
                DrawingResultSnapshot.drawing_id == DRAWING_ID
            )
        )

    ambiguous = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    assert ambiguous.items[0].status == "no_change"
    assert ambiguous.items[0].logical_changes == 0
    assert ambiguous.items[0].classification == "source_incomplete"
    assert ambiguous.items[0].reason == "ambiguous_local_classification_manual_review"
    assert _raw_classification(factory) == "source_incomplete"


def test_matching_local_raw_uses_stable_no_changes_classification(tmp_path):
    _engine, factory, _db_path = _factory(tmp_path)
    _seed_already_matching(factory)
    _write_cache(tmp_path)

    first = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )
    second = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )

    assert first.items[0].classification == "offline_repair_no_changes"
    assert second.items[0].classification == "offline_repair_no_changes"
    assert second.items[0].logical_changes == 0


def test_network_reconciliation_state_is_isolated_from_offline_repair(tmp_path):
    _engine, factory, db_path = _factory(tmp_path)
    _seed_importer_loss(factory)
    _write_cache(tmp_path)
    _add_reviewed_void_snapshot(factory, tmp_path)
    with factory.begin() as session:
        session.add(
            DrawingReconciliationState(
                drawing_id=DRAWING_ID,
                provider="totobrief",
                source=f"/drawing-info/{DRAWING_ID}",
                last_attempt_at=NOW.isoformat(),
                attempt_count=5,
                last_source_fingerprint="a" * 64,
                terminal_count=14,
                classification="source_incomplete",
                retry_state="quarantined",
                next_eligible_at="2026-08-30T12:00:00+00:00",
                last_error_code=None,
                unchanged_observation_count=5,
                transient_error_count=0,
                updated_at=NOW.isoformat(),
            )
        )
    before = _state_rows(db_path)

    repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=False,
        now=lambda: NOW,
    )

    assert _state_rows(db_path) == before


def test_dry_run_reports_recoverable_without_mutation(tmp_path):
    engine, factory, db_path = _factory(tmp_path)
    _seed_importer_loss(factory)
    _write_cache(tmp_path)
    _add_reviewed_void_snapshot(factory, tmp_path)
    engine.dispose()
    before = _sha(db_path)
    before_tree = _tree(tmp_path)

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    factory = sessionmaker(engine, expire_on_commit=False)
    report = repair_from_canonical_raw(
        factory,
        raw_cache_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        drawing_numbers=(DRAWING_NUMBER,),
        dry_run=True,
        now=lambda: NOW,
    )
    engine.dispose()

    assert report.items[0].status == "would_repair"
    assert report.items[0].classification == "offline_repair_recoverable"
    assert _sha(db_path) == before
    assert _tree(tmp_path) == before_tree
