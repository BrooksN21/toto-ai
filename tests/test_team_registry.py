import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    DrawingEventPin,
    DrawingPinSet,
    DrawingPinSetItem,
    DrawingPreparation,
    TeamAlias,
    TeamEntity,
    TeamRegistryReview,
)
from toto_ai.db.session import init_db
from toto_ai.external_odds.team_registry import (
    enqueue_review,
    invalidate_pin,
    load_pin,
    load_ready_pin_set,
    lookup_reviewed_alias,
    lookup_reviewed_alias_by_provider_id,
    publish_canonical_pin_set,
    resolve_review,
    upsert_reviewed_alias,
    upsert_team_entity,
    write_pin,
)

REGISTRY_TABLES = {
    "drawing_event_pins",
    "drawing_pin_sets",
    "drawing_pin_set_items",
    "team_aliases",
    "team_entities",
    "team_registry_reviews",
}


def _canonical_specs(session_factory, *, reviewed_orders=(14,)):
    home, away = _teams(session_factory)
    return tuple(
        {
            "target_event_id": str(800 + order),
            "event_order": order,
            "source_provider": (
                "reviewed-schedule"
                if order in reviewed_orders
                else "api-sports"
            ),
            "source_fixture_id": (
                None if order in reviewed_orders else f"fixture-{order}"
            ),
            "reviewed_evidence_id": (
                f"evidence-{order}" if order in reviewed_orders else None
            ),
            "canonical_home_team_id": home.id,
            "canonical_away_team_id": away.id,
            "source_home_team_id": (
                None if order in reviewed_orders else f"home-{order}"
            ),
            "source_away_team_id": (
                None if order in reviewed_orders else f"away-{order}"
            ),
            "starts_at": datetime(
                2026, 7, 29, 17 + order // 6, order % 6, tzinfo=timezone.utc
            ),
            "schedule_only": order in reviewed_orders,
            "provenance": (
                {
                    "evidence_id": f"evidence-{order}",
                    "evidence_hash": f"{order:064x}",
                    "catalog_hash": "c" * 64,
                }
                if order in reviewed_orders
                else {"payload_hash": f"{order:064x}", "orientation": "same"}
            ),
        }
        for order in range(15)
    )


def _4967_persisted_specs(
    session_factory,
    *,
    upgraded: bool,
    baseline_start: datetime | None = None,
):
    home, away = _teams(session_factory)
    upgrade_orders = {1, 8, 13, 14}
    specs = []
    for order in range(15):
        if order not in upgrade_orders:
            specs.append(
                {
                    "target_event_id": str(179253 + order),
                    "event_order": order,
                    "source_provider": "api-sports",
                    "source_fixture_id": f"fixture-{order}",
                    "reviewed_evidence_id": None,
                    "canonical_home_team_id": home.id,
                    "canonical_away_team_id": away.id,
                    "source_home_team_id": f"home-{order}",
                    "source_away_team_id": f"away-{order}",
                    "starts_at": datetime(
                        2026, 8, 6, 15 + order // 5, order % 5, tzinfo=timezone.utc
                    ),
                    "schedule_only": False,
                    "provenance": {
                        "orientation": "same",
                        "payload_hash": f"{order:064x}",
                    },
                }
            )
            continue
        if not upgraded:
            specs.append(
                {
                    "target_event_id": str(179253 + order),
                    "event_order": order,
                    "source_provider": "totobrief-baseline",
                    "source_fixture_id": None,
                    "reviewed_evidence_id": None,
                    "canonical_home_team_id": home.id,
                    "canonical_away_team_id": away.id,
                    "source_home_team_id": None,
                    "source_away_team_id": None,
                    "starts_at": baseline_start,
                    "schedule_only": True,
                    "provenance": {
                        "reason_code": "baseline_only_external_unavailable",
                        "totobrief_event_id": 179253 + order,
                        "totobrief_event_order": order,
                        "bk_probabilities": [0.4, 0.3, 0.3],
                    },
                }
            )
            continue
        specs.append(
            {
                "target_event_id": str(179253 + order),
                "event_order": order,
                "source_provider": "schedule-evidence",
                "source_fixture_id": None,
                "reviewed_evidence_id": f"4967-event-{order + 1}",
                "canonical_home_team_id": home.id,
                "canonical_away_team_id": away.id,
                "source_home_team_id": None,
                "source_away_team_id": None,
                "starts_at": datetime(
                    2026, 8, 6, 16 + order // 5, order % 5, tzinfo=timezone.utc
                ),
                "schedule_only": True,
                "provenance": {
                    "orientation": "reversed" if order == 13 else "same",
                    "evidence_id": f"4967-event-{order + 1}",
                    "evidence_hash": f"{order + 100:064x}",
                    "ledger_hash": "e" * 64,
                },
            }
        )
    return tuple(specs)


def _stored_canonical_state(session_factory):
    with session_factory() as session:
        pin_set = session.scalar(select(DrawingPinSet))
        assert pin_set is not None
        items = tuple(
            session.scalars(
                select(DrawingPinSetItem)
                .where(DrawingPinSetItem.pin_set_id == pin_set.pin_set_id)
                .order_by(DrawingPinSetItem.event_order)
            )
        )
    return pin_set.pin_set_id, tuple(item.pin_hash for item in items)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _teams(session_factory):
    home = upsert_team_entity(
        session_factory,
        sport="football",
        canonical_name="Спартак Москва",
        country="RU",
        context="Premier League",
    )
    away = upsert_team_entity(
        session_factory,
        sport="football",
        canonical_name="Zenit",
        country="RU",
        context="Premier League",
    )
    return home, away


def _pin(session_factory, *, fingerprint="fingerprint-a", event_order=0):
    home, away = _teams(session_factory)
    return write_pin(
        session_factory,
        drawing_id=11968,
        drawing_fingerprint=fingerprint,
        target_event_id=700 + event_order,
        event_order=event_order,
        provider="api-sports",
        canonical_home_team_id=home.id,
        canonical_away_team_id=away.id,
        provider_home_team_id="provider-home",
        provider_away_team_id="provider-away",
        provider_fixture_id=f"fixture-{fingerprint}-{event_order}",
        starts_at=datetime(2026, 7, 22, 18, tzinfo=timezone.utc),
        collection_id="collection-1",
        provenance={"source": "schedule", "payload_hash": "schedule-hash"},
    )


def test_init_db_creates_registry_tables_for_fresh_and_existing_database(tmp_path):
    fresh_path = tmp_path / "fresh.sqlite"
    fresh_engine = init_db(fresh_path)
    assert REGISTRY_TABLES <= set(inspect(fresh_engine).get_table_names())
    fresh_engine.dispose()

    existing_path = tmp_path / "existing.sqlite"
    with sqlite3.connect(existing_path) as connection:
        connection.execute(
            "CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY, value VARCHAR)"
        )
        connection.execute(
            "INSERT INTO legacy_marker (id, value) VALUES (1, 'preserved')"
        )

    existing_engine = init_db(existing_path)
    assert REGISTRY_TABLES <= set(inspect(existing_engine).get_table_names())
    with existing_engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM legacy_marker")).scalar() == (
            "preserved"
        )
    existing_engine.dispose()


def test_init_db_migrates_phase1_aliases_to_context_aware_identity(tmp_path):
    path = tmp_path / "phase1.sqlite"
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE team_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport VARCHAR NOT NULL,
                canonical_name VARCHAR NOT NULL,
                normalized_name VARCHAR NOT NULL,
                transliterated_name VARCHAR NOT NULL,
                country VARCHAR NOT NULL,
                context VARCHAR NOT NULL,
                created_at VARCHAR NOT NULL,
                CONSTRAINT uq_team_entity_identity UNIQUE
                    (sport, normalized_name, country, context)
            );
            CREATE TABLE team_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL REFERENCES team_entities(id),
                sport VARCHAR NOT NULL,
                alias VARCHAR NOT NULL,
                normalized_alias VARCHAR NOT NULL,
                transliterated_alias VARCHAR NOT NULL,
                source VARCHAR NOT NULL,
                provider VARCHAR NOT NULL,
                provider_team_id VARCHAR,
                provenance TEXT NOT NULL,
                confidence FLOAT NOT NULL,
                reviewed BOOLEAN NOT NULL,
                reviewer VARCHAR,
                reviewed_at VARCHAR,
                active BOOLEAN NOT NULL,
                created_at VARCHAR NOT NULL,
                updated_at VARCHAR NOT NULL,
                CONSTRAINT uq_team_alias_identity UNIQUE
                    (sport, provider, normalized_alias)
            );
            """
        )
        connection.execute(
            "INSERT INTO team_entities VALUES "
            "(1, 'football', 'United', 'united', 'united', "
            "'England', 'Premier League', ?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO team_aliases VALUES "
            "(1, 1, 'football', 'United', 'united', 'united', "
            "'phase1', 'api-sports', '42', '{}', 1.0, 1, 'operator', ?, 1, ?, ?)",
            (now, now, now),
        )

    engine = init_db(path)
    factory = sessionmaker(engine, expire_on_commit=False)
    columns = {column["name"] for column in inspect(engine).get_columns("team_aliases")}
    migrated = lookup_reviewed_alias(
        factory,
        sport="football",
        alias="United",
        provider="api-sports",
        country="England",
        context="Premier League",
    )

    assert {"country", "context"} <= columns
    assert migrated is not None
    assert migrated.country == "England"
    assert migrated.context == "Premier League"
    engine.dispose()


def test_reviewed_alias_upsert_lookup_and_provider_id_are_exact_and_idempotent(
    session_factory,
):
    team, _ = _teams(session_factory)
    first = upsert_reviewed_alias(
        session_factory,
        team_id=team.id,
        alias="Spartak Moskva",
        source="manual-review",
        provider="api-sports",
        provider_team_id="42",
        provenance={"ticket": "review-1"},
        confidence=1.0,
        reviewer="operator",
    )
    repeated = upsert_reviewed_alias(
        session_factory,
        team_id=team.id,
        alias="Spartak Moskva",
        source="manual-review",
        provider="api-sports",
        provider_team_id="42",
        provenance={"ticket": "review-1"},
        confidence=1.0,
        reviewer="operator",
    )

    assert first == repeated
    assert first.team == team
    assert first.normalized_alias == "spartak moskva"
    assert first.transliterated_alias == "spartak moskva"
    assert lookup_reviewed_alias(
        session_factory,
        sport="football",
        alias="  SPARTAK---MOSKVA ",
        provider="api-sports",
    ) == first
    assert lookup_reviewed_alias_by_provider_id(
        session_factory,
        sport="football",
        provider="api-sports",
        provider_team_id="42",
    ) == first
    assert (
        lookup_reviewed_alias(
            session_factory,
            sport="football",
            alias="Spartak Moskva",
            provider="another-provider",
        )
        is None
    )
    with session_factory() as session:
        assert session.scalar(select(func.count(TeamEntity.id))) == 2
        assert session.scalar(select(func.count(TeamAlias.id))) == 1


def test_lookup_ignores_unreviewed_and_inactive_aliases(session_factory):
    team, _ = _teams(session_factory)
    now = datetime.now(timezone.utc).isoformat()
    with session_factory.begin() as session:
        session.add(
            TeamAlias(
                team_id=team.id,
                sport=team.sport,
                alias="Unreviewed Team",
                normalized_alias="unreviewed team",
                transliterated_alias="unreviewed team",
                source="discovery",
                provider="api-sports",
                provider_team_id="unreviewed-id",
                provenance="{}",
                confidence=0.9,
                reviewed=False,
                reviewer=None,
                reviewed_at=None,
                active=True,
                created_at=now,
                updated_at=now,
            )
        )

    assert (
        lookup_reviewed_alias(
            session_factory,
            sport="football",
            alias="Unreviewed Team",
            provider="api-sports",
        )
        is None
    )
    assert (
        lookup_reviewed_alias_by_provider_id(
            session_factory,
            sport="football",
            provider="api-sports",
            provider_team_id="unreviewed-id",
        )
        is None
    )

    upsert_reviewed_alias(
        session_factory,
        team_id=team.id,
        alias="Inactive Team",
        source="manual-review",
        provider="api-sports",
        provenance={"ticket": "review-2"},
        confidence=1.0,
        reviewer="operator",
        active=False,
    )
    assert (
        lookup_reviewed_alias(
            session_factory,
            sport="football",
            alias="Inactive Team",
            provider="api-sports",
        )
        is None
    )


def test_alias_uniqueness_rejects_conflicting_canonical_team(session_factory):
    home, away = _teams(session_factory)
    upsert_reviewed_alias(
        session_factory,
        team_id=home.id,
        alias="Shared Alias",
        source="manual-review",
        provider="api-sports",
        provenance={"ticket": "review-1"},
        confidence=1.0,
        reviewer="operator",
    )
    with pytest.raises(ValueError, match="assigned to another team"):
        upsert_reviewed_alias(
            session_factory,
            team_id=away.id,
            alias="Shared Alias",
            source="other-source",
            provider="api-sports",
            provenance={"ticket": "review-2"},
            confidence=1.0,
            reviewer="operator",
        )


def test_same_normalized_alias_is_scoped_by_country_and_competition(
    session_factory,
):
    english = upsert_team_entity(
        session_factory,
        sport="football",
        canonical_name="United",
        country="England",
        context="Premier League",
    )
    american = upsert_team_entity(
        session_factory,
        sport="football",
        canonical_name="United",
        country="USA",
        context="MLS",
    )
    english_alias = upsert_reviewed_alias(
        session_factory,
        team_id=english.id,
        alias="United",
        source="manual-review",
        provider="api-sports",
        provenance={"scope": "England"},
        confidence=1.0,
        reviewer="operator",
    )
    american_alias = upsert_reviewed_alias(
        session_factory,
        team_id=american.id,
        alias="United",
        source="manual-review",
        provider="api-sports",
        provenance={"scope": "USA"},
        confidence=1.0,
        reviewer="operator",
    )

    assert english_alias.team.id != american_alias.team.id
    assert (
        lookup_reviewed_alias(
            session_factory,
            sport="football",
            alias="United",
            provider="api-sports",
            country="England",
            context="Premier League",
        )
        == english_alias
    )
    assert (
        lookup_reviewed_alias(
            session_factory,
            sport="football",
            alias="United",
            provider="api-sports",
        )
        is None
    )


def test_review_queue_is_idempotent_unique_and_resolution_is_immutable(
    session_factory,
):
    home, away = _teams(session_factory)
    values = {
        "drawing_id": 11968,
        "drawing_fingerprint": "fingerprint-a",
        "target_event_id": 700,
        "event_order": 0,
        "provider": "api-sports",
        "sport": "football",
        "target_home_team": "Спартак Москва",
        "target_away_team": "Zenit",
        "context": {"country": "RU", "league": "Premier League"},
        "candidate_evidence": [{"fixture_id": "fixture-1", "score": 0.7}],
    }
    first = enqueue_review(session_factory, **values)
    repeated = enqueue_review(session_factory, **values)
    assert first == repeated
    assert first.status == "pending"

    resolved = resolve_review(
        session_factory,
        review_id=first.id,
        status="resolved",
        home_team_id=home.id,
        away_team_id=away.id,
        resolution_provenance={"reviewer": "operator"},
    )
    assert resolved.status == "resolved"
    assert resolve_review(
        session_factory,
        review_id=first.id,
        status="resolved",
        home_team_id=home.id,
        away_team_id=away.id,
        resolution_provenance={"reviewer": "operator"},
    ) == resolved
    with pytest.raises(ValueError, match="immutable"):
        resolve_review(
            session_factory,
            review_id=first.id,
            status="rejected",
            resolution_provenance={"reviewer": "other"},
        )
    with session_factory() as session:
        assert session.scalar(select(func.count(TeamRegistryReview.id))) == 1


def test_database_constraints_prevent_duplicate_reviews_and_pins(session_factory):
    pin = _pin(session_factory)
    with session_factory.begin() as session:
        existing_pin = session.get(DrawingEventPin, pin.id)
        session.expunge(existing_pin)
        duplicate_pin = DrawingEventPin(
            **{
                column.name: getattr(existing_pin, column.name)
                for column in DrawingEventPin.__table__.columns
                if column.name != "id"
            }
        )
        session.add(duplicate_pin)
        with pytest.raises(IntegrityError):
            session.flush()

    review = enqueue_review(
        session_factory,
        drawing_id=11968,
        drawing_fingerprint="fingerprint-a",
        target_event_id=700,
        event_order=0,
        provider="api-sports",
        sport="football",
        target_home_team="Home",
        target_away_team="Away",
        context={},
        candidate_evidence=[],
    )
    with session_factory.begin() as session:
        existing_review = session.get(TeamRegistryReview, review.id)
        session.expunge(existing_review)
        duplicate_review = TeamRegistryReview(
            **{
                column.name: getattr(existing_review, column.name)
                for column in TeamRegistryReview.__table__.columns
                if column.name != "id"
            }
        )
        session.add(duplicate_review)
        with pytest.raises(IntegrityError):
            session.flush()


def test_pin_read_validation_invalidation_and_stale_fingerprint_rejection(
    session_factory,
):
    pin = _pin(session_factory)
    exact = {
        "drawing_id": pin.drawing_id,
        "drawing_fingerprint": pin.drawing_fingerprint,
        "target_event_id": pin.target_event_id,
        "event_order": pin.event_order,
        "provider": pin.provider,
    }
    assert load_pin(session_factory, **exact) == pin
    assert _pin(session_factory) == pin
    assert load_pin(
        session_factory,
        **{**exact, "drawing_fingerprint": "stale-fingerprint"},
    ) is None
    assert load_pin(
        session_factory,
        **{**exact, "target_event_id": "different-event"},
    ) is None
    assert load_pin(
        session_factory,
        **{**exact, "provider": "different-provider"},
    ) is None

    invalidated = invalidate_pin(
        session_factory,
        **exact,
        reason="drawing fingerprint changed",
    )
    assert invalidated is not None
    assert invalidated.status == "invalidated"
    assert load_pin(session_factory, **exact) is None
    assert load_pin(session_factory, **exact, include_invalidated=True) == invalidated
    assert invalidate_pin(
        session_factory,
        **exact,
        reason="drawing fingerprint changed",
    ) == invalidated


def test_pin_load_fails_closed_when_immutable_content_is_tampered(session_factory):
    pin = _pin(session_factory)
    with session_factory.begin() as session:
        session.execute(
            text(
                "UPDATE drawing_event_pins SET provider_fixture_id = 'tampered' "
                "WHERE id = :pin_id"
            ),
            {"pin_id": pin.id},
        )

    with pytest.raises(ValueError, match="hash mismatch"):
        load_pin(
            session_factory,
            drawing_id=pin.drawing_id,
            drawing_fingerprint=pin.drawing_fingerprint,
            target_event_id=pin.target_event_id,
            event_order=pin.event_order,
            provider=pin.provider,
        )


def test_publish_and_load_atomic_mixed_provider_pin_set(session_factory):
    probability_hash = "a" * 64
    pins = publish_canonical_pin_set(
        session_factory,
        drawing_id=11988,
        drawing_number=4959,
        drawing_fingerprint="f" * 64,
        provider="api-sports",
        eligibility_status="playable",
        readiness_summary=(
            '{"mapped_count":15,"probability_input_sha256":"'
            + probability_hash
            + '","status":"ready","target_fetched_at":'
            '"2026-07-29T12:00:00+00:00","unresolved_event_orders":[]}'
        ),
        pin_specs=_canonical_specs(session_factory),
        reviewed_catalog_hash="c" * 64,
    )

    assert len(pins) == 15
    assert [pin.event_order for pin in pins] == list(range(15))
    assert {pin.effective_source_provider for pin in pins} == {
        "api-sports",
        "reviewed-schedule",
    }
    reviewed = pins[14]
    assert reviewed.provider_fixture_id is None
    assert reviewed.reviewed_evidence_id == "evidence-14"
    assert reviewed.schedule_only is True
    assert (
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
            expected_probability_sha256=probability_hash,
            expected_reviewed_catalog_hash="c" * 64,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc),
        )
        == pins
    )
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSet.pin_set_id))) == 1
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 15


def test_persisted_4967_pin_set_accepts_only_atomic_monotonic_schedule_upgrade(
    session_factory,
):
    old = publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="unknown",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(session_factory, upgraded=False),
        reviewed_catalog_hash=None,
    )
    upgraded = publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="playable",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(session_factory, upgraded=True),
        reviewed_catalog_hash="e" * 64,
        allow_baseline_schedule_enrichment=True,
    )

    old_by_order = {pin.event_order: pin for pin in old}
    upgraded_by_order = {pin.event_order: pin for pin in upgraded}
    strict_orders = tuple(order for order in range(15) if order not in {1, 8, 13, 14})
    assert tuple(upgraded_by_order[order].pin_hash for order in strict_orders) == tuple(
        old_by_order[order].pin_hash for order in strict_orders
    )
    reversed_pin = upgraded_by_order[13]
    assert reversed_pin.provenance["orientation"] == "reversed"
    assert reversed_pin.provider_fixture_id is None
    assert reversed_pin.provider_home_team_id is None
    assert reversed_pin.provider_away_team_id is None
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSet.pin_set_id))) == 1
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 15


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_fixture_id", "drifted-fixture"),
        ("source_home_team_id", "drifted-home"),
        ("source_away_team_id", "drifted-away"),
    ),
)
def test_persisted_4967_upgrade_rejects_strict_provider_identity_drift_atomically(
    session_factory,
    field,
    value,
):
    old = publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="unknown",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(session_factory, upgraded=False),
        reviewed_catalog_hash=None,
    )
    replacement = list(_4967_persisted_specs(session_factory, upgraded=True))
    replacement[0] = {**replacement[0], field: value}

    with pytest.raises(ValueError, match="conflicting immutable canonical pin set"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=12010,
            drawing_number=4967,
            drawing_fingerprint="4" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=tuple(replacement),
            reviewed_catalog_hash="e" * 64,
            allow_baseline_schedule_enrichment=True,
        )
    assert _stored_canonical_state(session_factory) == (
        old[0].pin_set_id,
        tuple(pin.pin_hash for pin in old),
    )


def test_persisted_4967_upgrade_rejects_schedule_conflict_and_hash_mismatch(
    session_factory,
):
    known_start = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
    old = publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="unknown",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(
            session_factory,
            upgraded=False,
            baseline_start=known_start,
        ),
        reviewed_catalog_hash=None,
    )
    replacement = _4967_persisted_specs(session_factory, upgraded=True)
    with pytest.raises(ValueError, match="conflicting immutable canonical pin set"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=12010,
            drawing_number=4967,
            drawing_fingerprint="4" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=replacement,
            reviewed_catalog_hash="e" * 64,
            allow_baseline_schedule_enrichment=True,
        )
    with pytest.raises(
        ValueError, match="reviewed catalog hash does not match selected evidence"
    ):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=12010,
            drawing_number=4967,
            drawing_fingerprint="4" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=replacement,
            reviewed_catalog_hash="f" * 64,
            allow_baseline_schedule_enrichment=True,
        )
    assert _stored_canonical_state(session_factory) == (
        old[0].pin_set_id,
        tuple(pin.pin_hash for pin in old),
    )


def test_persisted_4967_upgrade_rejects_downgrade_atomically(session_factory):
    publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="unknown",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(session_factory, upgraded=False),
        reviewed_catalog_hash=None,
    )
    upgraded = publish_canonical_pin_set(
        session_factory,
        drawing_id=12010,
        drawing_number=4967,
        drawing_fingerprint="4" * 64,
        provider="api-sports",
        eligibility_status="playable",
        readiness_summary="{}",
        pin_specs=_4967_persisted_specs(session_factory, upgraded=True),
        reviewed_catalog_hash="e" * 64,
        allow_baseline_schedule_enrichment=True,
    )
    with pytest.raises(ValueError, match="conflicting immutable canonical pin set"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=12010,
            drawing_number=4967,
            drawing_fingerprint="4" * 64,
            provider="api-sports",
            eligibility_status="unknown",
            readiness_summary="{}",
            pin_specs=_4967_persisted_specs(session_factory, upgraded=False),
            reviewed_catalog_hash=None,
            allow_baseline_schedule_enrichment=True,
        )
    assert _stored_canonical_state(session_factory) == (
        upgraded[0].pin_set_id,
        tuple(pin.pin_hash for pin in upgraded),
    )


def test_mixed_pin_set_rejects_missing_or_mismatched_reviewed_catalog_hash(
    session_factory,
):
    publish_canonical_pin_set(
        session_factory,
        drawing_id=11988,
        drawing_number=4959,
        drawing_fingerprint="f" * 64,
        provider="api-sports",
        eligibility_status="playable",
        readiness_summary=(
            '{"mapped_count":15,"probability_input_sha256":"'
            + "a" * 64
            + '","status":"ready","target_fetched_at":'
            '"2026-07-29T12:00:00+00:00","unresolved_event_orders":[]}'
        ),
        pin_specs=_canonical_specs(session_factory),
        reviewed_catalog_hash="c" * 64,
    )

    with pytest.raises(ValueError, match="reviewed catalog hash is required"):
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
            expected_reviewed_catalog_hash=None,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="reviewed catalog hash mismatch"):
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
            expected_reviewed_catalog_hash="d" * 64,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc),
        )


def test_mixed_pin_set_requires_ready_fresh_probability_evidence(session_factory):
    publish_canonical_pin_set(
        session_factory,
        drawing_id=11988,
        drawing_number=4959,
        drawing_fingerprint="f" * 64,
        provider="api-sports",
        eligibility_status="playable",
        readiness_summary=(
            '{"mapped_count":15,"probability_input_sha256":"'
            + "a" * 64
            + '","status":"ready","target_fetched_at":'
            '"2026-07-29T12:00:00+00:00","unresolved_event_orders":[]}'
        ),
        pin_specs=_canonical_specs(session_factory),
        reviewed_catalog_hash="c" * 64,
    )

    with pytest.raises(
        ValueError,
        match="preparation_fail:probability_input_changed_or_missing",
    ):
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
            expected_probability_sha256="b" * 64,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc),
        )
    with pytest.raises(
        ValueError,
        match="preparation_fail:probability_input_not_fresh",
    ):
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
            expected_probability_sha256="a" * 64,
            as_of=datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc),
        )

    with session_factory.begin() as session:
        preparation = session.scalar(
            select(DrawingPreparation).where(
                DrawingPreparation.drawing_id == 11988
            )
        )
        assert preparation is not None
        preparation.status = "unresolved"
    with pytest.raises(
        ValueError,
        match="preparation_fail:not_ready_15_of_15",
    ):
        load_ready_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_fingerprint="f" * 64,
        )


def test_mixed_pin_set_rejects_partial_and_fake_reviewed_fixture(session_factory):
    specs = _canonical_specs(session_factory)
    with pytest.raises(ValueError, match="exactly 15"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_number=4959,
            drawing_fingerprint="f" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=specs[:-1],
            reviewed_catalog_hash="c" * 64,
        )
    invalid = list(specs)
    invalid[14] = {**invalid[14], "source_fixture_id": "fake-api-fixture"}
    with pytest.raises(ValueError, match="forbids fixture"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_number=4959,
            drawing_fingerprint="f" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=tuple(invalid),
            reviewed_catalog_hash="c" * 64,
        )
    invalid = list(specs)
    invalid[14] = {**invalid[14], "source_home_team_id": "fake-api-team"}
    with pytest.raises(ValueError, match="forbids provider team"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_number=4959,
            drawing_fingerprint="f" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=tuple(invalid),
            reviewed_catalog_hash="c" * 64,
        )
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSet.pin_set_id))) == 0
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 0


def test_mixed_pin_set_transaction_rolls_back_on_invalid_team(session_factory):
    specs = list(_canonical_specs(session_factory))
    specs[7] = {**specs[7], "canonical_home_team_id": 999999}
    with pytest.raises(ValueError, match="canonical team"):
        publish_canonical_pin_set(
            session_factory,
            drawing_id=11988,
            drawing_number=4959,
            drawing_fingerprint="f" * 64,
            provider="api-sports",
            eligibility_status="playable",
            readiness_summary="{}",
            pin_specs=tuple(specs),
            reviewed_catalog_hash="c" * 64,
        )
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSet.pin_set_id))) == 0
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 0
