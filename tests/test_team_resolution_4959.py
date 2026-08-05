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

NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
ALIASES_PATH = "data/external-odds/team-aliases.json"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target(order: int, championship: str, home: str, away: str) -> TargetEvent:
    return TargetEvent(
        drawing_id=12000,
        drawing_number=4959,
        event_id=30_000 + order,
        event_order=order,
        sport="football",
        championship=championship,
        starts_at=None,
        deadline=NOW,
        home_team=home,
        away_team=away,
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )


def _candidate(
    fixture_id: str,
    *,
    country: str,
    league: str,
    home: str,
    away: str,
    home_id: str,
    away_id: str,
) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league=league,
        starts_at=NOW + timedelta(hours=4),
        home_team=home,
        away_team=away,
        fetched_at=NOW,
        payload_hash=f"hash-{fixture_id}",
        country=country,
        provider_home_team_id=home_id,
        provider_away_team_id=away_id,
    )


def test_4959_event_4_resolves_by_contextual_verified_team_ids(session_factory):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)
    target = _target(
        3,
        "Аргентина. Чемпионат",
        "Химнасия и Эсгрима ЛП",
        "Ривер Плэйт Буэнос-Айрес",
    )
    candidate = _candidate(
        "provider-fixture",
        country="Argentina",
        league="Liga Profesional Argentina",
        home="Gimnasia L.P.",
        away="River Plate",
        home_id="434",
        away_id="435",
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Аргентина",
            league="Чемпионат",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "provider-fixture"
    assert result.candidates[0].provider_id_count == 2
    assert result.canonical_home_team_id is not None
    assert result.canonical_away_team_id is not None


def test_domestic_event_does_not_match_global_friendly_even_with_same_names(
    session_factory,
):
    target = _target(3, "Аргентина. Чемпионат", "Gimnasia L.P.", "River Plate")
    friendly = _candidate(
        "friendly",
        country="World",
        league="Club Friendlies",
        home="Gimnasia L.P.",
        away="River Plate",
        home_id="434",
        away_id="435",
    )

    result = resolve_event_candidate(
        target,
        (friendly,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Argentina",
            league="Liga Profesional Argentina",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "missing"
    assert result.provider_event_id is None
    assert "domestic target cannot use global competition" in (
        result.candidates[0].rejected_reasons
    )


def test_4959_event_9_reports_observed_missing_competition_without_forcing_match(
    session_factory,
):
    target = _target(
        8,
        "Исландия. 3-й дивизион",
        "КВ Вестурбеяр",
        "Рейнир Сандгерди",
    )
    other_iceland_fixture = _candidate(
        "other-iceland",
        country="Iceland",
        league="Úrvalsdeild",
        home="Valur",
        away="Vikingur Reykjavik",
        home_id="100",
        away_id="101",
    )

    result = resolve_event_candidate(
        target,
        (other_iceland_fixture,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Исландия",
            league="3-й дивизион",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "source_missing_competition"
    assert result.provider_event_id is None
    assert result.orientation is None
