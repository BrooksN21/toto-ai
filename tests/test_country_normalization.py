from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base
from toto_ai.external_odds.countries import (
    countries_equivalent,
    country_identity,
)
from toto_ai.external_odds.domain import ProviderEvent, TargetEvent
from toto_ai.external_odds.team_registry import (
    lookup_reviewed_alias,
    upsert_reviewed_alias,
    upsert_team_entity,
)
from toto_ai.external_odds.team_resolution import (
    ResolutionContext,
    resolve_event_candidate,
)

NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.mark.parametrize(
    "value",
    (
        "США",
        "USA",
        "US",
        "U.S.A.",
        "United States",
        "United States of America",
    ),
)
def test_country_identity_unifies_russian_english_and_iso_us_forms(value):
    assert country_identity(value) == "US"


def test_country_identity_keeps_real_country_mismatch():
    assert countries_equivalent("Россия", "RUS")
    assert not countries_equivalent("США", "Canada")


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("IL", "IL"),
        ("ISR", "IL"),
        ("Israel", "IL"),
        ("Израиль", "IL"),
        ("UZ", "UZ"),
        ("UZB", "UZ"),
        ("Uzbekistan", "UZ"),
        ("Узбекистан", "UZ"),
    ),
)
def test_country_identity_unifies_israel_and_uzbekistan_forms(value, expected):
    assert country_identity(value) == expected


def test_resolution_country_context_accepts_equivalence_and_rejects_mismatch(
    session_factory,
):
    target = TargetEvent(
        drawing_id=1,
        drawing_number=1,
        event_id=10,
        event_order=0,
        sport="football",
        championship="США. National League",
        starts_at=NOW + timedelta(hours=1),
        deadline=NOW,
        home_team="Alpha",
        away_team="Beta",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )

    def candidate(country):
        return ProviderEvent(
            provider="api-sports",
            provider_event_id=country,
            sport="football",
            league="National League",
            starts_at=target.starts_at,
            home_team="Alpha",
            away_team="Beta",
            fetched_at=NOW,
            payload_hash=f"hash-{country}",
            country=country,
            provider_home_team_id="alpha",
            provider_away_team_id="beta",
        )

    context = ResolutionContext(
        "api-sports",
        country="США",
        league="National League",
        sport="football",
        competition="США. National League",
    )
    equivalent = resolve_event_candidate(
        target,
        (candidate("United States"),),
        session_factory=session_factory,
        context=context,
    )
    mismatch = resolve_event_candidate(
        target,
        (candidate("Canada"),),
        session_factory=session_factory,
        context=context,
    )

    assert equivalent.status == "matched"
    assert "country" in equivalent.candidates[0].context_evidence
    assert mismatch.status == "missing"
    assert "country mismatch" in mismatch.candidates[0].rejected_reasons


def test_reviewed_registry_country_context_uses_stable_identity(session_factory):
    team = upsert_team_entity(
        session_factory,
        sport="football",
        canonical_name="New York Club",
        country="USA",
        context="National League",
    )
    upsert_reviewed_alias(
        session_factory,
        team_id=team.id,
        alias="Нью-Йорк Клуб",
        source="manual-review",
        provider="api-sports",
        provenance={"review": "country-identity"},
        confidence=1.0,
        reviewer="operator",
    )

    equivalent = lookup_reviewed_alias(
        session_factory,
        sport="football",
        alias="Нью-Йорк Клуб",
        provider="api-sports",
        country="США",
        context="National League",
    )
    mismatch = lookup_reviewed_alias(
        session_factory,
        sport="football",
        alias="Нью-Йорк Клуб",
        provider="api-sports",
        country="Canada",
        context="National League",
    )

    assert equivalent is not None
    assert equivalent.team.id == team.id
    assert mismatch is None
