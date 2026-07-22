import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    DrawingEventPin,
    TeamAlias,
    TeamEntity,
    TeamRegistryReview,
)
from toto_ai.db.session import init_db
from toto_ai.external_odds.team_registry import (
    enqueue_review,
    invalidate_pin,
    load_pin,
    lookup_reviewed_alias,
    lookup_reviewed_alias_by_provider_id,
    resolve_review,
    upsert_reviewed_alias,
    upsert_team_entity,
    write_pin,
)

REGISTRY_TABLES = {
    "drawing_event_pins",
    "team_aliases",
    "team_entities",
    "team_registry_reviews",
}


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
