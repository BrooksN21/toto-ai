import hashlib
import json
import plistlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.db.models import (
    ArchivedPackage,
    Drawing,
    DrawingResultSnapshot,
    PackageSettlement,
)
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.finished_draw import (
    PostDrawRetryConfig,
    archive_package,
    import_prebet_package_manifest,
    prepare_post_draw_scheduler_artifacts,
    run_post_draw,
    settle_archived_package,
    sync_finished_drawing,
    verify_result_snapshot,
)

ACTUAL_4952 = "1X22X222211X1XX"


class SnapshotClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def drawing_info(self, drawing_id):
        self.calls.append(drawing_id)
        return next(self.payloads)


def finished_payload(actual=ACTUAL_4952, *, payments=None):
    return {
        "data": {
            "id": 11970,
            "number": 4952,
            "name": "baltbet-main",
            "status": "finished",
            "ended_at": "2026-07-22T16:00:00+00:00",
            "pool_sum": 1_000_000,
            "jackpot": 500_000,
            "payments": payments,
            "events": [
                {
                    "id": 20_000 + order,
                    "order": order,
                    "result": result,
                    "score": f"{order}:0",
                }
                for order, result in enumerate(actual)
            ],
        }
    }


def _database(tmp_path):
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11970,
                number=4952,
                name="baltbet-main",
                status="finished",
                ended_at="2026-07-22T16:00:00+00:00",
            )
        )
    return factory


def _legacy_snapshot_database(tmp_path):
    db_path = tmp_path / "legacy-results.db"
    payload = finished_payload()
    events = [
        {
            "order": event["order"],
            "event_id": event["id"],
            "result": event["result"],
            "score": event["score"],
        }
        for event in payload["data"]["events"]
    ]
    canonical = lambda value: json.dumps(  # noqa: E731
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload_json = canonical(payload)
    events_json = canonical(events)
    legacy_content = {
        "drawing_id": 11970,
        "drawing_number": 4952,
        "status": "finished",
        "events": events,
        "payments": None,
        "pool_sum": 1_000_000.0,
        "jackpot": 500_000.0,
    }
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    result_hash = hashlib.sha256(events_json.encode()).hexdigest()
    snapshot_hash = hashlib.sha256(
        canonical(legacy_content).encode()
    ).hexdigest()
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE drawings (
                id INTEGER PRIMARY KEY,
                number INTEGER,
                name VARCHAR,
                status VARCHAR,
                pool_sum FLOAT,
                jackpot FLOAT,
                started_at VARCHAR,
                ended_at VARCHAR
            );
            CREATE TABLE drawing_result_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drawing_id INTEGER NOT NULL,
                drawing_number INTEGER NOT NULL,
                retrieved_at VARCHAR NOT NULL,
                source_endpoint VARCHAR NOT NULL,
                payload_sha256 VARCHAR NOT NULL,
                result_sha256 VARCHAR NOT NULL,
                snapshot_sha256 VARCHAR NOT NULL,
                complete BOOLEAN NOT NULL,
                event_count INTEGER NOT NULL,
                actual VARCHAR NOT NULL,
                events_json TEXT NOT NULL,
                payments_json TEXT,
                pool_sum FLOAT,
                jackpot FLOAT,
                payload_json TEXT NOT NULL,
                UNIQUE (drawing_id, snapshot_sha256)
            );
            """
        )
        connection.execute(
            """
            INSERT INTO drawings
            (id, number, name, status, pool_sum, jackpot, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11970,
                4952,
                "baltbet-main",
                "finished",
                1_000_000,
                500_000,
                "2026-07-22T16:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO drawing_result_snapshots
            (drawing_id, drawing_number, retrieved_at, source_endpoint,
             payload_sha256, result_sha256, snapshot_sha256, complete,
             event_count, actual, events_json, payments_json, pool_sum,
             jackpot, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11970,
                4952,
                "2026-07-23T00:00:00+00:00",
                "/drawing-info/11970",
                payload_hash,
                result_hash,
                snapshot_hash,
                True,
                15,
                ACTUAL_4952,
                events_json,
                None,
                1_000_000,
                500_000,
                payload_json,
            ),
        )
    factory = get_session_factory(init_db(db_path))
    return factory, payload, snapshot_hash


def test_finished_sync_is_explicit_idempotent_and_appends_correction(tmp_path):
    factory = _database(tmp_path)
    first = finished_payload()
    corrected = finished_payload(ACTUAL_4952[:-1] + "2")
    client = SnapshotClient([first, first, corrected])

    one = sync_finished_drawing(
        factory,
        client,
        drawing_number=4952,
        retrieved_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    duplicate = sync_finished_drawing(
        factory,
        client,
        drawing_id=11970,
        retrieved_at=datetime(2026, 7, 23, 0, 1, tzinfo=timezone.utc),
    )
    correction = sync_finished_drawing(
        factory,
        client,
        drawing_id=11970,
        retrieved_at=datetime(2026, 7, 23, 0, 2, tzinfo=timezone.utc),
    )

    assert client.calls == [11970, 11970, 11970]
    assert one.created is True
    assert duplicate.created is False
    assert duplicate.snapshot_sha256 == one.snapshot_sha256
    assert correction.created is True
    assert correction.snapshot_sha256 != one.snapshot_sha256
    with factory() as session:
        snapshots = session.scalars(
            select(DrawingResultSnapshot).order_by(DrawingResultSnapshot.id)
        ).all()
        assert len(snapshots) == 2
        assert snapshots[0].result_sha256 != snapshots[1].result_sha256


def test_finished_sync_rejects_identity_and_partial_results(tmp_path):
    factory = _database(tmp_path)
    mismatch = finished_payload()
    mismatch["data"]["number"] = 9999
    partial = finished_payload()
    partial["data"]["events"][3]["result"] = None
    client = SnapshotClient([mismatch, partial])

    with pytest.raises(ValueError, match="number mismatch"):
        sync_finished_drawing(factory, client, drawing_number=4952)
    with pytest.raises(ValueError, match="15/15"):
        sync_finished_drawing(factory, client, drawing_id=11970)

    with factory() as session:
        assert session.scalar(select(DrawingResultSnapshot)) is None


def test_finished_sync_accepts_reviewed_void_and_settlement_counts_it_as_hit(
    tmp_path,
):
    factory = _database(tmp_path)
    payload = finished_payload(payments=None)
    payload["data"]["events"][14]["result"] = ""
    payload["data"]["events"][14]["score"] = ""
    source = (
        "https://www.oursportscentral.com/services/releases/"
        "new-mexico-united-birmingham-legion-fc-match-postponed-to-later-date/"
        "n-6392681"
    )

    snapshot = sync_finished_drawing(
        factory,
        SnapshotClient([payload]),
        drawing_id=11970,
        void_event_orders=(15,),
        void_source=source,
    )

    assert snapshot.actual == ACTUAL_4952[:-1] + "*"
    assert snapshot.void_event_orders == (15,)
    with factory() as session:
        stored = session.scalar(
            select(DrawingResultSnapshot).where(
                DrawingResultSnapshot.snapshot_sha256
                == snapshot.snapshot_sha256
            )
        )
        events = json.loads(stored.events_json)
        assert events[14] == {
            "event_id": 20_014,
            "order": 14,
            "result": "*",
            "result_status": "void",
            "score": "",
            "void_source": source,
        }

    package = tmp_path / "void-winner.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archived = archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )
    settlement = settle_archived_package(
        factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )

    assert settlement.best_hits == 15
    assert settlement.hit_distribution[15] == 1
    assert settlement.void_event_orders == (15,)
    assert 15 not in settlement.fixed_miss_events
    assert 15 not in settlement.zero_exposure_miss_events


def test_finished_sync_requires_explicit_consistent_void_evidence(tmp_path):
    factory = _database(tmp_path)
    empty = finished_payload()
    empty["data"]["events"][14]["result"] = ""
    empty["data"]["events"][14]["score"] = ""

    with pytest.raises(ValueError, match="unresolved"):
        sync_finished_drawing(
            factory,
            SnapshotClient([empty]),
            drawing_id=11970,
        )
    with pytest.raises(ValueError, match="void_source"):
        sync_finished_drawing(
            factory,
            SnapshotClient([empty]),
            drawing_id=11970,
            void_event_orders=(15,),
        )
    with pytest.raises(ValueError, match="already has a result"):
        sync_finished_drawing(
            factory,
            SnapshotClient([finished_payload()]),
            drawing_id=11970,
            void_event_orders=(15,),
            void_source="https://example.test/official-postponement",
        )
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        sync_finished_drawing(
            factory,
            SnapshotClient([empty]),
            drawing_id=11970,
            void_event_orders=(15,),
            void_source="https://",
        )

    with factory() as session:
        assert session.scalar(select(DrawingResultSnapshot)) is None


@pytest.mark.parametrize(
    "ended_at",
    (
        None,
        "",
        "not-a-timestamp",
        "2026-07-22T16:00:00",
        "2026-07-22T16:00:01+00:00",
    ),
)
def test_finished_sync_rejects_invalid_or_mismatched_ended_at(
    tmp_path,
    ended_at,
):
    factory = _database(tmp_path)
    payload = finished_payload()
    payload["data"]["ended_at"] = ended_at

    with pytest.raises(ValueError, match="ended_at"):
        sync_finished_drawing(
            factory,
            SnapshotClient([payload]),
            drawing_id=11970,
        )

    with factory() as session:
        assert session.get(Drawing, 11970).ended_at == (
            "2026-07-22T16:00:00+00:00"
        )
        assert session.scalar(select(DrawingResultSnapshot)) is None


@pytest.mark.parametrize(
    "payload_ended_at",
    ("2026-07-22T19:00:00+03:00", pytest.param("absent", id="absent")),
)
def test_finished_sync_preserves_authoritative_equivalent_or_absent_ended_at(
    tmp_path,
    payload_ended_at,
):
    factory = _database(tmp_path)
    payload = finished_payload()
    if payload_ended_at == "absent":
        del payload["data"]["ended_at"]
    else:
        payload["data"]["ended_at"] = payload_ended_at

    result = sync_finished_drawing(
        factory,
        SnapshotClient([payload]),
        drawing_id=11970,
    )

    with factory() as session:
        drawing = session.get(Drawing, 11970)
        snapshot = session.scalar(
            select(DrawingResultSnapshot).where(
                DrawingResultSnapshot.snapshot_sha256
                == result.snapshot_sha256
            )
        )
        assert drawing.ended_at == "2026-07-22T16:00:00+00:00"
        assert snapshot.ended_at == "2026-07-22T16:00:00+00:00"


def test_legacy_snapshot_hash_survives_migration_and_current_append(tmp_path):
    factory, payload, legacy_hash = _legacy_snapshot_database(tmp_path)

    assert verify_result_snapshot(factory, legacy_hash) == legacy_hash
    with factory() as session:
        legacy = session.scalar(
            select(DrawingResultSnapshot).where(
                DrawingResultSnapshot.snapshot_sha256 == legacy_hash
            )
        )
        assert legacy.hash_schema_version == 1
        assert legacy.ended_at == "2026-07-22T16:00:00+00:00"

    current = sync_finished_drawing(
        factory,
        SnapshotClient([payload]),
        drawing_id=11970,
    )
    corrected_payload = finished_payload(ACTUAL_4952[:-1] + "2")
    corrected = sync_finished_drawing(
        factory,
        SnapshotClient([corrected_payload]),
        drawing_id=11970,
    )

    assert current.created is True
    assert current.snapshot_sha256 != legacy_hash
    assert corrected.created is True
    assert corrected.snapshot_sha256 not in (legacy_hash, current.snapshot_sha256)
    with factory() as session:
        snapshots = session.scalars(
            select(DrawingResultSnapshot).order_by(DrawingResultSnapshot.id)
        ).all()
        assert [row.hash_schema_version for row in snapshots] == [1, 3, 3]
        assert snapshots[0].snapshot_sha256 == legacy_hash


def test_timed_schema_v2_snapshot_remains_verifiable(tmp_path):
    factory = _database(tmp_path)
    payload = finished_payload()
    events = [
        {
            "order": event["order"],
            "event_id": event["id"],
            "result": event["result"],
            "score": event["score"],
        }
        for event in payload["data"]["events"]
    ]
    canonical = lambda value: json.dumps(  # noqa: E731
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload_json = canonical(payload)
    events_json = canonical(events)
    content = {
        "drawing_id": 11970,
        "drawing_number": 4952,
        "status": "finished",
        "events": events,
        "payments": None,
        "pool_sum": 1_000_000.0,
        "jackpot": 500_000.0,
        "ended_at": "2026-07-22T16:00:00+00:00",
    }
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    result_hash = hashlib.sha256(events_json.encode()).hexdigest()
    snapshot_hash = hashlib.sha256(canonical(content).encode()).hexdigest()
    with factory.begin() as session:
        session.add(
            DrawingResultSnapshot(
                drawing_id=11970,
                drawing_number=4952,
                hash_schema_version=2,
                ended_at="2026-07-22T16:00:00+00:00",
                retrieved_at="2026-07-23T00:00:00+00:00",
                source_endpoint="/drawing-info/11970",
                payload_sha256=payload_hash,
                result_sha256=result_hash,
                snapshot_sha256=snapshot_hash,
                complete=True,
                event_count=15,
                actual=ACTUAL_4952,
                events_json=events_json,
                payments_json=None,
                pool_sum=1_000_000,
                jackpot=500_000,
                payload_json=payload_json,
            )
        )

    assert verify_result_snapshot(factory, snapshot_hash) == snapshot_hash


def test_legacy_snapshot_timing_or_hash_tamper_fails_closed(tmp_path):
    factory, _payload, legacy_hash = _legacy_snapshot_database(tmp_path)
    with factory.begin() as session:
        session.execute(
            update(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.snapshot_sha256 == legacy_hash)
            .values(ended_at="2026-07-22T16:00:01+00:00")
        )
    with pytest.raises(ValueError, match="ended_at evidence mismatch"):
        verify_result_snapshot(factory, legacy_hash)

    with factory.begin() as session:
        session.execute(
            update(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.snapshot_sha256 == legacy_hash)
            .values(
                ended_at="2026-07-22T16:00:00+00:00",
                snapshot_sha256="f" * 64,
            )
        )
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_result_snapshot(factory, "f" * 64)


def test_real_4952_settlement_and_storage_are_idempotent(tmp_path):
    factory = _database(tmp_path)
    snapshot = sync_finished_drawing(
        factory,
        SnapshotClient([finished_payload(payments=None)]),
        drawing_number=4952,
    )
    package_path = (
        "reports/rehearsal/evening-4952/emergency-final/"
        "baltbet_package_4952_4980.txt"
    )
    archived = archive_package(
        factory,
        package_path,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )

    first = settle_archived_package(
        factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )
    duplicate = settle_archived_package(
        factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )

    assert archived.coupon_count == 166
    assert archived.cost == 4980
    assert first.created is True
    assert duplicate.created is False
    assert first.actual == ACTUAL_4952
    assert first.hit_distribution == {
        0: 0,
        1: 5,
        2: 31,
        3: 65,
        4: 51,
        5: 14,
        6: 0,
        7: 0,
        8: 0,
        9: 0,
        10: 0,
        11: 0,
        12: 0,
        13: 0,
        14: 0,
        15: 0,
    }
    assert first.best_hits == 5
    assert first.category_counts is None
    assert first.known_return is None
    assert first.roi is None
    assert first.return_status == "unknown_until_payouts"
    assert first.fixed_miss_events == (1, 5, 14, 15)
    assert 6 in first.zero_exposure_miss_events
    with factory() as session:
        assert len(session.scalars(select(ArchivedPackage)).all()) == 1
        assert len(session.scalars(select(PackageSettlement)).all()) == 1


def test_category_hit_without_payments_keeps_return_unknown(tmp_path):
    factory = _database(tmp_path)
    snapshot = sync_finished_drawing(
        factory,
        SnapshotClient([finished_payload(payments=None)]),
        drawing_id=11970,
    )
    package = tmp_path / "winner.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archived = archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )

    settlement = settle_archived_package(
        factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )

    assert settlement.category_counts is None
    assert settlement.known_return is None
    assert settlement.roi is None
    assert settlement.return_status == "unknown_until_payouts"


def test_explicit_official_category_evidence_allows_known_zero(tmp_path):
    factory = _database(tmp_path)
    payments = {
        "payout_per_winner": {
            str(category): 100 * category for category in range(10, 16)
        }
    }
    snapshot = sync_finished_drawing(
        factory,
        SnapshotClient([finished_payload(payments=payments)]),
        drawing_id=11970,
    )
    package = tmp_path / "loser.txt"
    package.write_text("30; " + "; ".join("2" * 15) + "\n")
    archived = archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )

    settlement = settle_archived_package(
        factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )

    assert settlement.category_counts == {
        10: 0,
        11: 0,
        12: 0,
        13: 0,
        14: 0,
        15: 0,
    }
    assert settlement.known_return == 0
    assert settlement.roi == -1
    assert settlement.return_status == "known_zero_from_official_categories"


def test_post_draw_runner_is_bounded_exact_and_machine_readable(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )
    partial = finished_payload()
    partial["data"]["events"][0]["result"] = None
    client = SnapshotClient([partial, finished_payload()])
    state_path = tmp_path / "post-draw.json"
    sleeps = []

    state = run_post_draw(
        factory,
        client,
        package_file=package,
        drawing_number=4952,
        stake=30,
        config=PostDrawRetryConfig(
            max_attempts=2,
            initial_delay_seconds=1,
            max_delay_seconds=2,
        ),
        state_path=state_path,
        now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
        sleep=sleeps.append,
    )

    assert client.calls == [11970, 11970]
    assert sleeps == [1]
    assert state.status == "complete"
    assert state.attempts == 2
    assert json.loads(state_path.read_text())["status"] == "complete"

    no_calls = SnapshotClient([])
    repeated = run_post_draw(
        factory,
        no_calls,
        package_file=package,
        drawing_number=4952,
        stake=30,
        config=PostDrawRetryConfig(max_attempts=1, initial_delay_seconds=0),
        state_path=state_path,
        now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    assert repeated == state
    assert no_calls.calls == []

    mismatched = json.loads(state_path.read_text())
    mismatched["drawing_id"] = 99999
    state_path.write_text(json.dumps(mismatched))
    with pytest.raises(ValueError, match="state is malformed"):
        run_post_draw(
            factory,
            no_calls,
            package_file=package,
            drawing_number=4952,
            stake=30,
            config=PostDrawRetryConfig(max_attempts=1, initial_delay_seconds=0),
            state_path=state_path,
            now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
        )
    assert no_calls.calls == []


def test_post_draw_exhausts_partial_results_without_open_fallback(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )
    partial = finished_payload()
    partial["data"]["events"].pop()

    class ExactOnlyClient(SnapshotClient):
        def drawings(self, *_args, **_kwargs):
            raise AssertionError("open drawing fallback is forbidden")

    client = ExactOnlyClient([partial, partial, partial])
    sleeps = []
    state = run_post_draw(
        factory,
        client,
        package_file=package,
        drawing_id=11970,
        config=PostDrawRetryConfig(
            max_attempts=3,
            initial_delay_seconds=2,
            max_delay_seconds=3,
            backoff_multiplier=2,
        ),
        state_path=tmp_path / "state.json",
        now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
        sleep=sleeps.append,
    )

    assert client.calls == [11970, 11970, 11970]
    assert sleeps == [2, 3]
    assert state.status == "pending"
    assert state.attempts == 3
    assert "15/15" in state.reason


def test_post_draw_api_failure_is_bounded_failed_state(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )

    class FailingClient:
        calls = []

        def drawing_info(self, drawing_id):
            self.calls.append(drawing_id)
            raise RuntimeError("API unavailable")

    client = FailingClient()
    state = run_post_draw(
        factory,
        client,
        package_file=package,
        drawing_number=4952,
        config=PostDrawRetryConfig(
            max_attempts=2,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        ),
        state_path=tmp_path / "state.json",
        now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
        sleep=lambda _seconds: None,
    )

    assert client.calls == [11970, 11970]
    assert state.status == "failed"
    assert state.reason == "API unavailable"


def test_post_draw_scheduler_plan_is_strictly_after_exact_end(tmp_path):
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    factory = get_session_factory(init_db(tmp_path / "toto.db"))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11970,
                number=4952,
                status="finished",
                ended_at="2026-10-25T02:59:59+02:00",
            )
        )
    plan_path, wrapper, plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=11970,
        drawing_number=None,
        ended_at="2026-10-25T02:59:59+02:00",
        package_file=package,
        stake=30,
        db=tmp_path / "toto.db",
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=3,
        initial_delay_seconds=2,
        max_delay_seconds=8,
    )

    plan = json.loads(plan_path.read_text())
    assert plan["drawing_id"] == 11970
    assert plan["drawing_number"] == 4952
    ended = datetime.fromisoformat(plan["ended_at"])
    first = datetime.fromisoformat(plan["first_run_at"])
    moscow = ZoneInfo("Europe/Moscow")
    assert first > ended
    assert first == datetime(2026, 10, 26, 12, 0, tzinfo=moscow)
    assert first.date() == ended.astimezone(moscow).date().replace(day=26)
    assert plan["timezone"] == "Europe/Moscow"
    assert plan["interval_hours"] == 3
    assert plan["due_slots"] == [
        "2026-10-26T12:00:00+03:00",
        "2026-10-26T15:00:00+03:00",
        "2026-10-26T18:00:00+03:00",
    ]
    assert plan["expires_at"] == plan["due_slots"][-1]
    wrapper_text = wrapper.read_text()
    assert "post-draw-run --plan" in wrapper_text
    assert str(plan_path.resolve()) in wrapper_text
    assert "--drawing-id" not in wrapper_text
    assert "--open" not in wrapper_text
    assert "target-time.time()" not in wrapper_text
    assert "launchctl" not in wrapper_text
    with plist.open("rb") as source:
        launchd = plistlib.load(source)
    assert launchd["ProgramArguments"] == [str(wrapper)]
    assert launchd["StartCalendarInterval"] == [
        {"Year": 2026, "Month": 10, "Day": 26, "Hour": 12, "Minute": 0},
        {"Year": 2026, "Month": 10, "Day": 26, "Hour": 15, "Minute": 0},
        {"Year": 2026, "Month": 10, "Day": 26, "Hour": 18, "Minute": 0},
    ]


@pytest.mark.parametrize(
    "command",
        (
            "sync-finished-results",
            "archive-package",
            "settle-drawing",
        "post-draw-run",
        "post-draw-plan",
    ),
)
def test_finished_lifecycle_cli_help_is_explicit(command):
    result = CliRunner().invoke(cli.app, [command, "--help"])

    assert result.exit_code == 0
    assert "--drawing-id" in result.output
    assert "--drawing-number" in result.output
    assert "--open" not in result.output


def test_finished_sync_cli_requires_exactly_one_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: pytest.fail("client must not be created for invalid identity"),
    )
    runner = CliRunner()

    missing = runner.invoke(
        cli.app,
        ["sync-finished-results", "--db", str(tmp_path / "toto.db")],
    )
    both = runner.invoke(
        cli.app,
        [
            "sync-finished-results",
            "--drawing-id",
            "11970",
            "--drawing-number",
            "4952",
            "--db",
            str(tmp_path / "toto.db"),
        ],
    )

    assert missing.exit_code != 0
    assert both.exit_code != 0
    assert "exactly one" in missing.output
    assert "exactly one" in both.output


def test_finished_sync_cli_refuses_payload_identity_mismatch(monkeypatch, tmp_path):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11970,
                number=4952,
                status="finished",
                ended_at="2026-07-22T16:00:00+00:00",
            )
        )
    mismatch = finished_payload()
    mismatch["data"]["id"] = 99999
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: SnapshotClient([mismatch]),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "sync-finished-results",
            "--drawing-number",
            "4952",
            "--db",
            str(db),
        ],
    )

    assert result.exit_code != 0
    assert "drawing id mismatch" in result.output


def test_finished_sync_cli_passes_reviewed_void_evidence(monkeypatch, tmp_path):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=11970,
                number=4952,
                status="finished",
                ended_at="2026-07-22T16:00:00+00:00",
            )
        )
    payload = finished_payload()
    payload["data"]["events"][14]["result"] = ""
    payload["data"]["events"][14]["score"] = ""
    source = "https://example.test/official-postponement"
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda: SnapshotClient([payload]),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "sync-finished-results",
            "--drawing-id",
            "11970",
            "--void-event",
            "15",
            "--void-source",
            source,
            "--db",
            str(db),
        ],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["actual"] == ACTUAL_4952[:-1] + "*"
    assert output["void_event_orders"] == [15]
    with factory() as session:
        stored = session.scalar(select(DrawingResultSnapshot))
        assert json.loads(stored.events_json)[14]["void_source"] == source


def test_archive_package_cli_is_explicit_legacy_import(tmp_path):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(Drawing(id=11970, number=4952, status="finished"))
    package = tmp_path / "package.csv"
    package.write_text(f"coupon,stake\n{ACTUAL_4952},30\n")

    result = CliRunner().invoke(
        cli.app,
        [
            "archive-package",
            "--drawing-number",
            "4952",
            "--package-file",
            str(package),
            "--stake",
            "30",
            "--db",
            str(db),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["provenance"] == "legacy_import"


def test_ambiguous_visible_number_and_duplicate_event_ids_fail(tmp_path):
    factory = _database(tmp_path)
    with factory.begin() as session:
        session.add(Drawing(id=11971, number=4952, status="finished"))
    with pytest.raises(ValueError, match="ambiguous"):
        sync_finished_drawing(
            factory,
            SnapshotClient([finished_payload()]),
            drawing_number=4952,
        )

    factory = _database(tmp_path / "other")
    payload = finished_payload()
    payload["data"]["events"][1]["id"] = payload["data"]["events"][0]["id"]
    with pytest.raises(ValueError, match="positive unique source event IDs"):
        sync_finished_drawing(
            factory,
            SnapshotClient([payload]),
            drawing_id=11970,
        )


def test_csv_declared_stake_mismatch_fails(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.csv"
    package.write_text(f"coupon,stake\n{ACTUAL_4952},10\n")

    with pytest.raises(ValueError, match="declared stake mismatch"):
        archive_package(
            factory,
            package,
            drawing_id=11970,
            drawing_number=4952,
            stake=30,
        )


def test_tampered_snapshot_archive_settlement_and_state_fail_closed(tmp_path):
    factory = _database(tmp_path)
    synced = sync_finished_drawing(
        factory,
        SnapshotClient([finished_payload()]),
        drawing_id=11970,
    )
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    archived = archive_package(
        factory,
        package,
        drawing_id=11970,
        drawing_number=4952,
        stake=30,
    )
    settle_archived_package(
        factory,
        snapshot_sha256=synced.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )

    with factory.begin() as session:
        session.execute(
            update(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.snapshot_sha256 == synced.snapshot_sha256)
            .values(actual="2" * 15)
        )
    with pytest.raises(ValueError, match="completeness mismatch"):
        settle_archived_package(
            factory,
            snapshot_sha256=synced.snapshot_sha256,
            archive_sha256=archived.archive_sha256,
        )
    with factory.begin() as session:
        session.execute(
            update(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.snapshot_sha256 == synced.snapshot_sha256)
            .values(actual=ACTUAL_4952)
        )
        session.execute(
            update(ArchivedPackage)
            .where(ArchivedPackage.archive_sha256 == archived.archive_sha256)
            .values(source_bytes=b"tampered")
        )
    with pytest.raises(ValueError, match="Coupon|package"):
        settle_archived_package(
            factory,
            snapshot_sha256=synced.snapshot_sha256,
            archive_sha256=archived.archive_sha256,
        )
    with factory.begin() as session:
        session.execute(
            update(ArchivedPackage)
            .where(ArchivedPackage.archive_sha256 == archived.archive_sha256)
            .values(source_bytes=package.read_bytes())
        )
    state_path = tmp_path / "state.json"
    state = run_post_draw(
        factory,
        SnapshotClient([finished_payload()]),
        package_file=package,
        drawing_id=11970,
        state_path=state_path,
        config=PostDrawRetryConfig(max_attempts=1, initial_delay_seconds=0),
        now=lambda: datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    with factory.begin() as session:
        session.execute(
            update(PackageSettlement)
            .where(PackageSettlement.settlement_sha256 == state.settlement_sha256)
            .values(settlement_json="{}")
        )
    with pytest.raises(ValueError, match="settlement content mismatch"):
        run_post_draw(
            factory,
            SnapshotClient([]),
            package_file=package,
            drawing_id=11970,
            state_path=state_path,
            config=PostDrawRetryConfig(max_attempts=1, initial_delay_seconds=0),
        )
    state_data = json.loads(state_path.read_text())
    state_data["drawing_id"] = 1
    state_path.write_text(json.dumps(state_data))
    with pytest.raises(ValueError, match="state is malformed"):
        run_post_draw(
            factory,
            SnapshotClient([]),
            package_file=package,
            drawing_id=11970,
            state_path=state_path,
            config=PostDrawRetryConfig(max_attempts=1, initial_delay_seconds=0),
        )


def test_concurrent_snapshot_archive_and_settlement_are_idempotent(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")

    def sync_once(_index):
        return sync_finished_drawing(
            factory,
            SnapshotClient([finished_payload()]),
            drawing_id=11970,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(pool.map(sync_once, range(4)))
    assert sum(item.created for item in snapshots) == 1

    def archive_once(_index):
        return archive_package(
            factory,
            package,
            drawing_id=11970,
            drawing_number=4952,
            stake=30,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        archives = list(pool.map(archive_once, range(4)))
    assert sum(item.created for item in archives) == 1

    def settle_once(_index):
        return settle_archived_package(
            factory,
            snapshot_sha256=snapshots[0].snapshot_sha256,
            archive_sha256=archives[0].archive_sha256,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        settlements = list(pool.map(settle_once, range(4)))
    assert sum(item.created for item in settlements) == 1


def test_hostile_scheduler_paths_are_shell_and_plist_safe(tmp_path):
    hostile = tmp_path / "x $(touch PWNED) &'"
    hostile.mkdir()
    db = hostile / "toto &.db"
    factory = get_session_factory(init_db(db))
    ended = "2026-10-25T02:59:59+02:00"
    with factory.begin() as session:
        session.add(
            Drawing(id=11970, number=4952, status="finished", ended_at=ended)
        )
    package = hostile / "pack $(bad) '.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    plan, wrapper, plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=11970,
        drawing_number=None,
        ended_at=ended,
        package_file=package,
        stake=30,
        db=db,
        state_file=hostile / "state &.json",
        output_dir=hostile / "out",
        project_root=hostile,
        python_executable="/usr/bin/python3",
        max_attempts=2,
        initial_delay_seconds=1,
        max_delay_seconds=2,
    )

    assert json.loads(plan.read_text())["drawing_id"] == 11970
    with plist.open("rb") as source:
        parsed = plistlib.load(source)
    assert parsed["ProgramArguments"] == [str(wrapper)]
    assert parsed["WorkingDirectory"] == str(hostile.resolve())
    assert not (tmp_path / "PWNED").exists()


def test_scheduler_rejects_ended_at_mismatch(tmp_path):
    _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    with pytest.raises(ValueError, match="ended_at does not match"):
        prepare_post_draw_scheduler_artifacts(
            drawing_id=11970,
            drawing_number=None,
            ended_at="2026-07-22T16:00:01Z",
            package_file=package,
            stake=30,
            db=tmp_path / "toto.db",
            state_file=tmp_path / "state.json",
            output_dir=tmp_path / "scheduler",
            project_root=tmp_path,
            python_executable="/usr/bin/python3",
            max_attempts=2,
            initial_delay_seconds=1,
            max_delay_seconds=2,
        )


def test_prebet_manifest_binding_and_early_wake_state_lock(tmp_path):
    factory = _database(tmp_path)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join(ACTUAL_4952) + "\n")
    canonical = hashlib.sha256(ACTUAL_4952.encode()).hexdigest()
    manifest = {
        "schema_version": 1,
        "provenance": "pre_bet_runner",
        "drawing_id": 11970,
        "drawing_number": 4952,
        "ended_at": "2026-07-22T16:00:00+00:00",
        "archived_at": "2026-07-22T15:50:00+00:00",
        "stake": 30,
        "coupon_count": 1,
        "cost": 30,
        "source_path": str(package),
        "source_bytes_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "canonical_package_sha256": canonical,
    }
    manifest["archive_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest_path = tmp_path / "package-archive.json"
    manifest_path.write_text(json.dumps(manifest))
    archived = import_prebet_package_manifest(factory, manifest_path, package)
    duplicate = import_prebet_package_manifest(factory, manifest_path, package)
    assert archived.provenance == "pre_bet_runner"
    assert archived.archive_manifest_sha256 == manifest["archive_manifest_sha256"]
    assert duplicate.created is False
    assert duplicate.archive_sha256 == archived.archive_sha256

    current = [datetime(2026, 7, 22, 15, 59, 58, tzinfo=timezone.utc)]

    def now():
        return current[0]

    def sleep(seconds):
        current[0] = current[0].fromtimestamp(
            current[0].timestamp() + seconds,
            tz=timezone.utc,
        )

    client = SnapshotClient([finished_payload()])
    state_path = tmp_path / "state.json"

    def run_once(_index):
        return run_post_draw(
            factory,
            client,
            package_file=package,
            drawing_id=11970,
            state_path=state_path,
            config=PostDrawRetryConfig(
                max_attempts=4,
                initial_delay_seconds=1,
                max_delay_seconds=1,
            ),
            now=now,
            sleep=sleep,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = list(pool.map(run_once, range(2)))
    assert all(state.status == "complete" for state in states)
    assert client.calls == [11970]
    assert state_path.with_name("state.json.lock").exists()
