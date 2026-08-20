from datetime import datetime, timezone

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

UTC = timezone.utc
FETCHED_AT = datetime(2026, 8, 20, 6, 40, tzinfo=UTC)
DEADLINE = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)
ALIASES_PATH = "data/external-odds/team-aliases.json"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.mark.parametrize(
    (
        "order",
        "event_id",
        "championship",
        "country",
        "league",
        "target_home",
        "target_away",
        "fixture_id",
        "provider_home",
        "provider_away",
        "home_id",
        "away_id",
        "starts_at",
    ),
    (
        (
            4,
            179917,
            "Италия. Серия B",
            "Italy",
            "Serie B",
            "Виченца",
            "Катанцаро",
            "1601498",
            "Vicenza Virtus",
            "Catanzaro",
            "1584",
            "1687",
            datetime(2026, 8, 21, 18, 30, tzinfo=UTC),
        ),
        (
            8,
            179921,
            "Нидерланды. 1-й дивизион",
            "Netherlands",
            "Eerste Divisie",
            "Эммен",
            "Алкмаар(м)",
            "1551759",
            "Emmen",
            "Jong AZ",
            "208",
            "418",
            datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
        ),
        (
            11,
            179924,
            "Франция. Лига 2",
            "France",
            "Ligue 2",
            "По",
            "Нанси",
            "1552446",
            "PAU",
            "Nancy",
            "1297",
            "102",
            datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
        ),
        (
            12,
            179925,
            "Франция. Лига 2",
            "France",
            "Ligue 2",
            "Клермон",
            "Дижон",
            "1552442",
            "Clermont Foot",
            "Dijon",
            "99",
            "89",
            datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
        ),
        (
            14,
            179927,
            "Франция. Лига 2",
            "France",
            "Ligue 2",
            "Сошо",
            "Генгам",
            "1552448",
            "Sochaux",
            "Guingamp",
            "115",
            "90",
            datetime(2026, 8, 21, 18, 0, tzinfo=UTC),
        ),
    ),
)
def test_4982_verified_team_identities_resolve_exact_api_sports_fixtures(
    session_factory,
    order,
    event_id,
    championship,
    country,
    league,
    target_home,
    target_away,
    fixture_id,
    provider_home,
    provider_away,
    home_id,
    away_id,
    starts_at,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)
    target = TargetEvent(
        drawing_id=12054,
        drawing_number=4982,
        event_id=event_id,
        event_order=order,
        sport="football",
        championship=championship,
        starts_at=None,
        deadline=DEADLINE,
        home_team=target_home,
        away_team=target_away,
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )
    candidate = ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league=league,
        starts_at=starts_at,
        home_team=provider_home,
        away_team=provider_away,
        fetched_at=FETCHED_AT,
        payload_hash=f"fixture-{fixture_id}",
        country=country,
        provider_home_team_id=home_id,
        provider_away_team_id=away_id,
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country=country,
            league=league,
            sport="football",
            competition=championship,
            derived=True,
        ),
    )

    assert result.status == "matched"
    assert result.provider_event_id == fixture_id
    assert result.candidates[0].provider_id_count == 2
