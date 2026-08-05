from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from toto_ai.analytics.data_health import audit_data_health
from toto_ai.api.rate_limit import TotoBriefRequestError
from toto_ai.cli import app
from toto_ai.db.models import (
    Drawing,
    DrawingReconciliationState,
    Event,
    Quote,
)
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.reconciliation import (
    ReconciliationConfig,
    ReconciliationRetryPolicy,
    reconcile_finished_drawings,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
POLICY = ReconciliationRetryPolicy(
    source_incomplete_base_seconds=3600,
    source_incomplete_max_seconds=7200,
    source_incomplete_quarantine_after=3,
    quarantine_seconds=86400,
    transient_base_seconds=60,
    transient_max_seconds=300,
)


class SequenceClient:
    def __init__(self, values):
        self.values = list(values)
        self.calls: list[int] = []

    def drawing_info(self, drawing_id: int):
        self.calls.append(drawing_id)
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _factory(tmp_path, *, numbers=(4946,)):
    db_path = tmp_path / "test.db"
    factory = get_session_factory(init_db(db_path))
    with factory.begin() as session:
        for offset, number in enumerate(numbers):
            drawing_id = 11955 + offset * 2
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
                        name=f"Event {number}-{order}",
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
    return db_path, factory


def _payload(
    drawing_id: int,
    number: int,
    *,
    terminal_count: int,
    revision: str = "a",
):
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
                    "name": f"Event {number}-{order}-{revision}",
                    "championship": "League",
                    "sport": "football",
                    "result": (
                        ("1", "X", "2")[order % 3]
                        if order < terminal_count
                        else None
                    ),
                    "result_status": (
                        "resolved" if order < terminal_count else None
                    ),
                    "score": "1 : 0" if order < terminal_count else None,
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


def _run(
    factory: sessionmaker,
    client: SequenceClient,
    tmp_path,
    *,
    at: datetime = NOW,
    force: bool = False,
    dry_run: bool = False,
    batch_size: int | None = None,
    state_name: str = "state.json",
):
    return reconcile_finished_drawings(
        factory,
        client,
        archive_root=tmp_path / "archive",
        state_path=tmp_path / state_name,
        config=ReconciliationConfig(
            max_attempts=1,
            initial_backoff_seconds=0,
            batch_size=batch_size,
            dry_run=dry_run,
        ),
        retry_policy=POLICY,
        force=force,
        now=lambda: at,
    )


def _state(factory: sessionmaker, drawing_id: int = 11955):
    with factory() as session:
        return session.scalar(
            select(DrawingReconciliationState).where(
                DrawingReconciliationState.drawing_id == drawing_id,
                DrawingReconciliationState.provider == "totobrief",
                DrawingReconciliationState.source
                == f"/drawing-info/{drawing_id}",
            )
        )


def test_repeated_same_14_of_15_cools_down_then_quarantines(tmp_path):
    _, factory = _factory(tmp_path)
    partial = _payload(11955, 4946, terminal_count=14)

    first_client = SequenceClient([partial])
    first = _run(factory, first_client, tmp_path)
    assert first.items[0].status == "source_incomplete"
    assert first.items[0].classification == "source_incomplete"
    assert first.items[0].next_eligible_at == (
        NOW + timedelta(hours=1)
    ).isoformat()
    assert first_client.calls == [11955]

    blocked_client = SequenceClient([])
    blocked = _run(factory, blocked_client, tmp_path)
    assert blocked.items[0].status == "cooldown"
    assert blocked_client.calls == []

    second = _run(
        factory,
        SequenceClient([partial]),
        tmp_path,
        at=NOW + timedelta(hours=1),
    )
    assert second.items[0].status == "source_incomplete"
    assert second.items[0].next_eligible_at == (
        NOW + timedelta(hours=3)
    ).isoformat()

    third = _run(
        factory,
        SequenceClient([partial]),
        tmp_path,
        at=NOW + timedelta(hours=3),
    )
    assert third.items[0].status == "quarantined"
    persisted = _state(factory)
    assert persisted is not None
    assert persisted.classification == "source_incomplete"
    assert persisted.retry_state == "quarantined"
    assert persisted.attempt_count == 3
    assert persisted.unchanged_observation_count == 3
    assert persisted.next_eligible_at == (
        NOW + timedelta(days=1, hours=3)
    ).isoformat()


def test_quarantine_blocks_until_policy_expiry_then_allows_one_probe(tmp_path):
    _, factory = _factory(tmp_path)
    partial = _payload(11955, 4946, terminal_count=14)
    _run(factory, SequenceClient([partial]), tmp_path)
    _run(
        factory,
        SequenceClient([partial]),
        tmp_path,
        at=NOW + timedelta(hours=1),
    )
    _run(
        factory,
        SequenceClient([partial]),
        tmp_path,
        at=NOW + timedelta(hours=3),
    )
    blocked_client = SequenceClient([])
    blocked = _run(
        factory,
        blocked_client,
        tmp_path,
        at=NOW + timedelta(days=1, hours=2),
    )
    assert blocked.items[0].status == "quarantined"
    assert blocked_client.calls == []

    probe_client = SequenceClient([partial])
    probe = _run(
        factory,
        probe_client,
        tmp_path,
        at=NOW + timedelta(days=1, hours=3),
    )
    assert probe_client.calls == [11955]
    assert probe.items[0].status == "quarantined"
    assert _state(factory).attempt_count == 4


def test_changed_fingerprint_same_count_resets_stagnation(tmp_path):
    _, factory = _factory(tmp_path)
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
    )
    changed = _run(
        factory,
        SequenceClient(
            [_payload(11955, 4946, terminal_count=14, revision="b")]
        ),
        tmp_path,
        at=NOW + timedelta(hours=1),
    )
    state = _state(factory)
    assert changed.items[0].status == "source_incomplete"
    assert state is not None
    assert state.unchanged_observation_count == 1
    assert state.attempt_count == 2
    assert state.next_eligible_at == (
        NOW + timedelta(hours=2)
    ).isoformat()


def test_improved_15_of_15_completes_and_future_run_skips_network(tmp_path):
    _, factory = _factory(tmp_path)
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
    )
    completed = _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=15)]),
        tmp_path,
        force=True,
    )
    assert completed.items[0].status == "repaired"
    state = _state(factory)
    assert state is not None
    assert state.classification == "complete"
    assert state.retry_state == "complete"
    assert state.terminal_count == 15
    assert state.next_eligible_at is None
    assert state.unchanged_observation_count == 0

    no_calls = SequenceClient([])
    resumed = _run(factory, no_calls, tmp_path, state_name="new-state.json")
    assert resumed.selected == 0
    assert no_calls.calls == []


def test_improved_local_terminal_count_reenables_before_cooldown_expiry(
    tmp_path,
):
    _, factory = _factory(tmp_path)
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
    )
    with factory.begin() as session:
        event = session.scalar(
            select(Event).where(
                Event.drawing_id == 11955,
                Event.event_order == 14,
            )
        )
        event.result = "2"
        event.result_status = "resolved"
        event.score = "1 : 0"
    client = SequenceClient([_payload(11955, 4946, terminal_count=15)])
    report = _run(factory, client, tmp_path)
    assert client.calls == [11955]
    assert report.items[0].status == "repaired"


def test_transient_timeout_uses_short_policy_and_not_source_incomplete(tmp_path):
    _, factory = _factory(tmp_path)
    report = _run(
        factory,
        SequenceClient([TimeoutError("timeout")]),
        tmp_path,
    )
    state = _state(factory)
    assert report.items[0].status == "transient_error"
    assert report.items[0].classification == "transient_error"
    assert report.items[0].last_error_code == "transport_error"
    assert state is not None
    assert state.next_eligible_at == (NOW + timedelta(minutes=1)).isoformat()


def test_http_429_has_explicit_transient_error_code(tmp_path):
    _, factory = _factory(tmp_path)
    error = TotoBriefRequestError(
        "rate limited",
        endpoint="/drawing-info/11955",
        attempts=1,
        status_code=429,
    )
    report = _run(factory, SequenceClient([error]), tmp_path)
    assert report.items[0].status == "transient_error"
    assert report.items[0].last_error_code == "http_429"
    assert _state(factory).classification == "transient_error"


def test_http_503_uses_transient_policy_not_source_incomplete(tmp_path):
    _, factory = _factory(tmp_path)
    error = TotoBriefRequestError(
        "service unavailable",
        endpoint="/drawing-info/11955",
        attempts=1,
        status_code=503,
    )
    report = _run(factory, SequenceClient([error]), tmp_path)
    assert report.items[0].classification == "transient_error"
    assert report.items[0].last_error_code == "http_503"
    assert report.items[0].next_eligible_at == (
        NOW + timedelta(minutes=1)
    ).isoformat()


def test_force_bypasses_cooldown_but_preserves_attempt_history(tmp_path):
    _, factory = _factory(tmp_path)
    partial = _payload(11955, 4946, terminal_count=14)
    _run(factory, SequenceClient([partial]), tmp_path)
    forced_client = SequenceClient([partial])
    forced = _run(factory, forced_client, tmp_path, force=True)
    assert forced_client.calls == [11955]
    assert forced.items[0].status == "source_incomplete"
    assert _state(factory).attempt_count == 2


def test_dry_run_reports_cooldown_without_state_raw_or_network_mutation(tmp_path):
    _, factory = _factory(tmp_path)
    partial = _payload(11955, 4946, terminal_count=14)
    _run(factory, SequenceClient([partial]), tmp_path)
    before_state = json.loads((tmp_path / "state.json").read_text())
    before_files = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "archive").rglob("*")
        if path.is_file()
    )
    persisted_before = _state(factory)

    client = SequenceClient([])
    report = _run(factory, client, tmp_path, dry_run=True)

    assert report.items[0].status == "would_skip_cooldown"
    assert client.calls == []
    assert json.loads((tmp_path / "state.json").read_text()) == before_state
    assert sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "archive").rglob("*")
        if path.is_file()
    ) == before_files
    persisted_after = _state(factory)
    assert persisted_after.last_attempt_at == persisted_before.last_attempt_at
    assert persisted_after.attempt_count == persisted_before.attempt_count


def test_existing_database_gets_idempotent_reconciliation_state_schema(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE drawings ("
            "id INTEGER PRIMARY KEY, number INTEGER, name VARCHAR, "
            "status VARCHAR, pool_sum FLOAT, jackpot FLOAT, "
            "started_at VARCHAR, ended_at VARCHAR)"
        )
    first = init_db(db_path)
    second = init_db(db_path)
    expected = {
        "drawing_id",
        "provider",
        "source",
        "last_attempt_at",
        "attempt_count",
        "last_source_fingerprint",
        "terminal_count",
        "classification",
        "retry_state",
        "next_eligible_at",
        "last_error_code",
        "unchanged_observation_count",
        "transient_error_count",
        "updated_at",
    }
    assert expected <= {
        column["name"]
        for column in inspect(first).get_columns(
            "drawing_reconciliation_states"
        )
    }
    assert "drawing_reconciliation_states" in inspect(
        second
    ).get_table_names()


def test_database_state_resumes_even_with_a_new_json_state_path(tmp_path):
    _, factory = _factory(tmp_path)
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
        state_name="first.json",
    )
    client = SequenceClient([])
    resumed = _run(
        factory,
        client,
        tmp_path,
        state_name="second.json",
    )
    assert resumed.items[0].status == "cooldown"
    assert client.calls == []
    assert not (tmp_path / "second.json").exists()


def test_batch_limit_is_fair_when_earlier_drawing_is_in_cooldown(tmp_path):
    _, factory = _factory(tmp_path, numbers=(4946, 4947))
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
        batch_size=1,
    )
    client = SequenceClient([_payload(11957, 4947, terminal_count=15)])
    report = _run(factory, client, tmp_path, batch_size=1)
    assert client.calls == [11957]
    assert report.processed == 1
    assert report.repaired == 1
    assert report.skipped_cooldown == 1
    assert [item.drawing_number for item in report.items] == [4946, 4947]


def test_data_health_exposes_reconciliation_cooldown_inventory(tmp_path):
    db_path, factory = _factory(tmp_path)
    _run(
        factory,
        SequenceClient([_payload(11955, 4946, terminal_count=14)]),
        tmp_path,
    )
    with factory() as session:
        report = audit_data_health(
            session,
            db_path=db_path,
            use_case="historical_inventory",
            strict=False,
        )
    row = report.drawings[0]
    assert row.reconciliation_classifications == ("source_incomplete",)
    assert row.reconciliation_retry_states == ("cooldown",)
    assert row.reconciliation_attempt_count == 1
    assert (
        report.summary.inventory_counts["reconciliation_cooldown_drawings"]
        == 1
    )


def test_cli_exposes_force_and_safe_no_force_default():
    result = CliRunner().invoke(app, ["reconcile-finished", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output
    assert "--no-force" in result.output
