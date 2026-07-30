from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import Base, Drawing, Event, Quote
from toto_ai.operations.reconciliation import (
    ReconciliationConfig,
    reconcile_finished_drawings,
    repair_from_canonical_raw,
    select_incomplete_finished_drawings,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def _factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _seed(factory, numbers=(4954, 4955, 4956)):
    with factory.begin() as session:
        for offset, number in enumerate(numbers):
            drawing_id = 11975 + offset * 2
            session.add(
                Drawing(
                    id=drawing_id,
                    number=number,
                    name="baltbet-main",
                    status="finished",
                    ended_at="2026-07-30T10:00:00Z",
                )
            )
            for order in range(15):
                session.add(
                    Event(
                        drawing_id=drawing_id,
                        event_order=order,
                        name=f"Event {order}",
                    )
                )
                session.add(
                    Quote(
                        drawing_id=drawing_id,
                        event_order=order,
                        pool_win_1=40,
                        pool_draw=30,
                        pool_win_2=30,
                        bk_win_1=40,
                        bk_draw=30,
                        bk_win_2=30,
                    )
                )


def _payload(drawing_id, number, *, complete):
    return {
        "data": {
            "id": drawing_id,
            "number": number,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-30T10:00:00Z",
            "events": [
                {
                    "id": drawing_id * 100 + order,
                    "order": order,
                    "name": f"Event {order}",
                    "championship": "League",
                    "sport": "football",
                    "result": ("1", "X", "2")[order % 3] if complete else None,
                    "result_status": "resolved" if complete else None,
                    "score": "1 : 0" if complete else None,
                    "quotes": {
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }


class SequenceClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def drawing_info(self, drawing_id):
        self.calls.append(drawing_id)
        value = self.payloads.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def test_selectors_and_dry_run_make_no_network_calls(tmp_path):
    factory = _factory(tmp_path)
    _seed(factory)
    selected = select_incomplete_finished_drawings(
        factory,
        from_drawing=4955,
        to_drawing=4956,
    )
    assert [item.number for item in selected] == [4955, 4956]
    assert [
        item.number
        for item in select_incomplete_finished_drawings(factory, last=1)
    ] == [4956]

    client = SequenceClient([])
    report = reconcile_finished_drawings(
        factory,
        client,
        archive_root=tmp_path / "archive",
        state_path=tmp_path / "state.json",
        config=ReconciliationConfig(max_attempts=2, dry_run=True),
        last=2,
        now=lambda: NOW,
    )
    assert client.calls == []
    assert report.selected == 2
    assert report.dry_run is True
    assert all(item.status == "would_reconcile" for item in report.items)


def test_partial_cools_down_then_forced_complete_resumes_as_fresh(tmp_path):
    factory = _factory(tmp_path)
    _seed(factory, numbers=(4954,))
    partial = _payload(11975, 4954, complete=False)
    complete = _payload(11975, 4954, complete=True)
    client = SequenceClient([partial])
    state_path = tmp_path / "state.json"
    sleeps = []

    report = reconcile_finished_drawings(
        factory,
        client,
        archive_root=tmp_path / "archive",
        state_path=state_path,
        config=ReconciliationConfig(
            max_attempts=2,
            initial_backoff_seconds=1,
            max_backoff_seconds=2,
        ),
        now=lambda: NOW,
        sleep=sleeps.append,
    )

    assert client.calls == [11975]
    assert sleeps == []
    assert report.items[0].status == "source_incomplete"
    assert report.items[0].attempts == 1
    completed = reconcile_finished_drawings(
        factory,
        SequenceClient([complete]),
        archive_root=tmp_path / "archive",
        state_path=state_path,
        config=ReconciliationConfig(max_attempts=2),
        force=True,
        now=lambda: NOW,
    )
    assert completed.items[0].status == "repaired"
    assert completed.items[0].attempts == 2
    no_calls = SequenceClient([])
    resumed = reconcile_finished_drawings(
        factory,
        no_calls,
        archive_root=tmp_path / "archive",
        state_path=state_path,
        config=ReconciliationConfig(max_attempts=2),
        now=lambda: NOW,
    )
    assert resumed.selected == 0
    assert no_calls.calls == []


def test_exhaustion_and_resume_state_are_explicit(tmp_path):
    factory = _factory(tmp_path)
    _seed(factory, numbers=(4954,))
    partial = _payload(11975, 4954, complete=False)
    state_path = tmp_path / "state.json"
    client = SequenceClient([partial, partial])

    report = reconcile_finished_drawings(
        factory,
        client,
        archive_root=tmp_path / "archive",
        state_path=state_path,
        config=ReconciliationConfig(
            max_attempts=2,
            initial_backoff_seconds=0,
        ),
        now=lambda: NOW,
    )

    assert report.items[0].status == "source_incomplete"
    assert report.items[0].attempts == 1
    persisted = json.loads(state_path.read_text())
    assert persisted["drawings"]["11975"]["status"] == "source_incomplete"
    assert len(persisted["attempts"]) == 1


def test_network_error_is_exhausted_not_source_missing(tmp_path):
    factory = _factory(tmp_path)
    _seed(factory, numbers=(4954,))
    client = SequenceClient([TimeoutError("timeout")])

    report = reconcile_finished_drawings(
        factory,
        client,
        archive_root=tmp_path / "archive",
        state_path=tmp_path / "state.json",
        config=ReconciliationConfig(max_attempts=1),
        now=lambda: NOW,
    )

    assert report.items[0].status == "transient_error"
    assert report.items[0].reason == "transport_error"


def test_4954_4956_canonical_raw_repair_is_dry_run_then_idempotent(tmp_path):
    factory = _factory(tmp_path)
    _seed(factory)
    raw_root = tmp_path / "raw"
    for offset, number in enumerate((4954, 4955, 4956)):
        drawing_id = 11975 + offset * 2
        write_drawing_detail_cache(
            _payload(drawing_id, number, complete=True),
            drawing_id=drawing_id,
            cache_dir=raw_root,
            fetched_at=NOW,
            source="finished-result",
            allowed_root=tmp_path,
        )

    dry = repair_from_canonical_raw(
        factory,
        raw_cache_root=raw_root,
        archive_root=tmp_path / "archive",
        drawing_numbers=(4954, 4955, 4956),
        dry_run=True,
        now=lambda: NOW,
    )
    assert [item.status for item in dry.items] == ["would_repair"] * 3

    applied = repair_from_canonical_raw(
        factory,
        raw_cache_root=raw_root,
        archive_root=tmp_path / "archive",
        drawing_numbers=(4954, 4955, 4956),
        dry_run=False,
        now=lambda: NOW,
    )
    repeated = repair_from_canonical_raw(
        factory,
        raw_cache_root=raw_root,
        archive_root=tmp_path / "archive",
        drawing_numbers=(4954, 4955, 4956),
        dry_run=False,
        now=lambda: NOW,
    )
    assert applied.repaired == 3
    assert all(
        item.classification == "importer_loss_recoverable_local"
        for item in applied.items
    )
    assert all(item.logical_changes == 0 for item in repeated.items)
