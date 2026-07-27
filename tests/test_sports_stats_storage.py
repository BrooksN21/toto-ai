import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select

from toto_ai.db.models import ArchivedPackage
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.sports_stats.domain import build_event_snapshot, build_run_snapshot
from toto_ai.sports_stats.storage import (
    load_latest_eligible_snapshot,
    load_sports_stats_snapshot,
    save_sports_stats_snapshot,
)

UTC = timezone.utc


def snapshot():
    captured = datetime(2026, 7, 29, 9, tzinfo=UTC)
    as_of = captured + timedelta(minutes=1)
    deadline = captured + timedelta(hours=3)
    events = tuple(
        build_event_snapshot(
            schema_version=1,
            drawing_id=7,
            drawing_number=5001,
            drawing_fingerprint="d" * 64,
            event_id=str(100 + order),
            event_order=order,
            sport="football",
            provider="api-sports",
            status="missing",
            missing_reasons=("provider_error",),
            captured_at=captured,
            as_of=as_of,
            deadline=deadline,
            target_starts_at=deadline + timedelta(hours=1),
            provider_fixture_id=None,
            canonical_home_team_id=None,
            canonical_away_team_id=None,
            provider_home_team_id=None,
            provider_away_team_id=None,
            league_id=None,
            season=None,
            home_window=None,
            away_window=None,
            home_standing=None,
            away_standing=None,
            source_evidence=(),
        )
        for order in range(15)
    )
    return build_run_snapshot(
        drawing_id=7,
        drawing_number=5001,
        drawing_fingerprint="d" * 64,
        provider="api-sports",
        requested_history_size=10,
        captured_at=captured,
        as_of=as_of,
        deadline=deadline,
        events=events,
        requests_made=0,
        cache_hits=0,
    )


def test_append_only_storage_is_idempotent_and_asof_bounded(tmp_path):
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    expected = snapshot()

    save_sports_stats_snapshot(factory, expected)
    save_sports_stats_snapshot(factory, expected)

    assert load_sports_stats_snapshot(factory, expected.run_id) == expected
    assert (
        load_latest_eligible_snapshot(
            factory,
            drawing_id=7,
            drawing_fingerprint="d" * 64,
            as_of=expected.as_of - timedelta(seconds=1),
        )
        is None
    )
    assert (
        load_latest_eligible_snapshot(
            factory,
            drawing_id=7,
            drawing_fingerprint="d" * 64,
            as_of=expected.as_of,
        )
        == expected
    )


def test_existing_database_initialization_adds_sports_tables_without_data_loss(
    tmp_path,
):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE drawings ("
            "id INTEGER PRIMARY KEY, number INTEGER, name VARCHAR, "
            "status VARCHAR, pool_sum FLOAT, jackpot FLOAT, "
            "started_at VARCHAR, ended_at VARCHAR)"
        )
        connection.execute(
            "INSERT INTO drawings VALUES "
            "(7, 5001, 'baltbet-main', 'finished', 1.0, 2.0, NULL, NULL)"
        )

    engine = init_db(path)

    assert {
        "sports_stats_runs",
        "sports_event_feature_snapshots",
    } <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT number FROM drawings WHERE id = 7"
        ).scalar_one() == 5001


def test_sports_snapshot_persistence_does_not_change_archived_package_markers(
    tmp_path,
):
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    marker = ArchivedPackage(
        archive_sha256="a" * 64,
        package_sha256="b" * 64,
        drawing_id=7,
        drawing_number=5001,
        stake=30,
        coupon_count=1,
        cost=30,
        source_path="package.csv",
        source_bytes_sha256="c" * 64,
        source_bytes=b"30;1;X;2\n",
        coupons_json='["1X2"]',
        archived_at="2026-07-29T08:00:00+00:00",
        provenance="PLAY",
        archive_manifest_sha256=None,
    )
    with factory.begin() as session:
        session.add(marker)

    save_sports_stats_snapshot(factory, snapshot())

    with factory() as session:
        stored = session.scalar(select(ArchivedPackage))
        assert stored is not None
        assert stored.archive_sha256 == "a" * 64
        assert stored.package_sha256 == "b" * 64
        assert stored.provenance == "PLAY"
        assert stored.source_bytes == b"30;1;X;2\n"
