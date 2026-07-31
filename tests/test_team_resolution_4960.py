from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base
from toto_ai.external_odds.domain import ProviderEvent, TargetEvent
from toto_ai.external_odds.team_registry import seed_reviewed_alias_config
from toto_ai.external_odds.team_resolution import (
    ResolutionContext,
    resolve_event_candidate,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
ALIASES_PATH = "data/external-odds/team-aliases.json"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target() -> TargetEvent:
    return TargetEvent(
        drawing_id=11990,
        drawing_number=4960,
        event_id=178965,
        event_order=12,
        sport="football",
        championship="Южная Америка. Южноамериканский Кубок",
        starts_at=None,
        deadline=datetime(2026, 7, 30, 16, tzinfo=timezone.utc),
        home_team="Каракас",
        away_team="Индепендьенте СФ",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.32, 0.28, 0.40),
    )


def _fixture() -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id="1547782",
        sport="football",
        league="CONMEBOL Sudamericana",
        starts_at=NOW + timedelta(hours=6),
        home_team="Caracas FC",
        away_team="Santa Fe",
        fetched_at=NOW,
        payload_hash="fixture-1547782",
        country="World",
        provider_home_team_id="2808",
        provider_away_team_id="1139",
    )


def _context() -> ResolutionContext:
    return ResolutionContext(
        provider="api-sports",
        country="Южная Америка",
        league="Южноамериканский Кубок",
        sport="football",
        competition="Южная Америка. Южноамериканский Кубок",
        derived=True,
    )


def test_4960_exact_provider_fixture_requires_reviewed_identity(session_factory):
    before = resolve_event_candidate(
        _target(),
        (_fixture(),),
        session_factory=session_factory,
        context=_context(),
    )
    assert before.status == "ambiguous"

    aliases = seed_reviewed_alias_config(session_factory, ALIASES_PATH)
    assert any(
        item.provider_team_id == "2808" and item.reviewer == "totoai-operator"
        for item in aliases
    )
    assert any(
        item.provider_team_id == "1139" and item.reviewer == "totoai-operator"
        for item in aliases
    )

    after = resolve_event_candidate(
        _target(),
        (_fixture(),),
        session_factory=session_factory,
        context=_context(),
    )

    assert after.status == "matched"
    assert after.provider_event_id == "1547782"
    assert after.candidates[0].provider_id_count == 2
    assert after.canonical_home_team_id is not None
    assert after.canonical_away_team_id is not None


def test_reviewed_alias_catalog_does_not_auto_learn_unknown_team(session_factory):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)
    unknown = ProviderEvent(
        provider="api-sports",
        provider_event_id="unknown",
        sport="football",
        league="CONMEBOL Sudamericana",
        starts_at=NOW + timedelta(hours=6),
        home_team="Unreviewed Caracas Clone",
        away_team="Santa Fe",
        fetched_at=NOW,
        payload_hash="unknown",
        country="World",
        provider_home_team_id="999999",
        provider_away_team_id="1139",
    )

    result = resolve_event_candidate(
        _target(),
        (unknown,),
        session_factory=session_factory,
        context=_context(),
    )

    assert result.status != "matched"
    assert result.provider_event_id is None


def test_4960_provider_missing_friendly_requires_reviewed_schedule(
    session_factory,
):
    target = TargetEvent(
        drawing_id=11990,
        drawing_number=4960,
        event_id=178967,
        event_order=14,
        sport="football",
        championship="Товарищеские матчи. Топ-клубы",
        starts_at=None,
        deadline=datetime(2026, 7, 30, 16, tzinfo=timezone.utc),
        home_team="Лидс",
        away_team="Сандерленд",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.40, 0.28, 0.32),
    )
    unrelated = (
        ProviderEvent(
            provider="api-sports",
            provider_event_id="unrelated-1",
            sport="football",
            league="Club Friendlies",
            starts_at=NOW + timedelta(hours=5),
            home_team="Red Star",
            away_team="Chelsea XI",
            fetched_at=NOW,
            payload_hash="unrelated-1",
            country="World",
            provider_home_team_id="1",
            provider_away_team_id="2",
        ),
        ProviderEvent(
            provider="api-sports",
            provider_event_id="unrelated-2",
            sport="football",
            league="Club Friendlies",
            starts_at=NOW + timedelta(hours=6),
            home_team="Linfield",
            away_team="Shelbourne",
            fetched_at=NOW,
            payload_hash="unrelated-2",
            country="World",
            provider_home_team_id="3",
            provider_away_team_id="4",
        ),
    )

    result = resolve_event_candidate(
        target,
        unrelated,
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Товарищеские матчи",
            league="Топ-клубы",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "source_missing_competition"
    assert result.provider_event_id is None
    assert "no identity-bearing candidate" in result.reason
