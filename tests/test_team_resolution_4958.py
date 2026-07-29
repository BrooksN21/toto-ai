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

NOW = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
ALIASES_PATH = "data/external-odds/team-aliases.json"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target(
    *,
    event_order: int,
    championship: str,
    home: str,
    away: str,
    home_en: str | None = None,
    away_en: str | None = None,
) -> TargetEvent:
    return TargetEvent(
        drawing_id=11986,
        drawing_number=4958,
        event_id=20_000 + event_order,
        event_order=event_order,
        sport="football",
        championship=championship,
        starts_at=None,
        deadline=NOW,
        home_team=home,
        away_team=away,
        home_team_en=home_en,
        away_team_en=away_en,
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
    starts_at: datetime | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league=league,
        starts_at=starts_at or NOW + timedelta(hours=4),
        home_team=home,
        away_team=away,
        fetched_at=NOW,
        payload_hash=f"hash-{fixture_id}",
        country=country,
        provider_home_team_id=home_id,
        provider_away_team_id=away_id,
    )


def test_4958_fixture_1557935_resolves_after_israel_country_normalization(
    session_factory,
):
    target = _target(
        event_order=6,
        championship="Израиль. Кубок Тото",
        home="Хапоэль Хайфа",
        away="Ирони Тибериас",
    )
    candidate = _candidate(
        "1557935",
        country="Israel",
        league="Toto Cup Ligat Al",
        home="Hapoel Haifa",
        away="Ironi Tiberias",
        home_id="2253",
        away_id="6181",
        starts_at=datetime(2026, 7, 28, 16, 45, tzinfo=timezone.utc),
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Израиль",
            league="Кубок Тото",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "1557935"
    assert result.orientation == "same"
    assert "country" in result.candidates[0].context_evidence


def test_4958_fixture_1516080_resolves_with_reviewed_uzbek_aliases(
    session_factory,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)
    target = _target(
        event_order=11,
        championship="Узбекистан. Суперлига",
        home="Хорезм",
        away="Термез Сурхан",
    )
    candidate = _candidate(
        "1516080",
        country="Uzbekistan",
        league="Super League",
        home="Xorazm",
        away="Surkhon",
        home_id="16381",
        away_id="4225",
        starts_at=datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc),
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Узбекистан",
            league="Суперлига",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "1516080"
    assert result.orientation == "same"
    assert result.candidates[0].reviewed_team_count == 2
    assert result.candidates[0].home_score == 1.0
    assert result.candidates[0].away_score == 1.0


@pytest.mark.parametrize(
    ("fixture_id", "home", "away", "league"),
    (
        ("1493023", "Gimnasia L.P.", "River Plate", "Liga Profesional Argentina"),
        ("male", "Huracan", "River Plate", "Liga Profesional Argentina"),
        ("reserve", "Huracan Reserves", "River Plate Res.", "Reserve League"),
        ("u20", "Huracan U20", "River Plate U20", "U20 League"),
    ),
)
def test_4958_women_target_rejects_male_reserve_and_u20_candidates(
    session_factory,
    fixture_id,
    home,
    away,
    league,
):
    target = _target(
        event_order=4,
        championship="Аргентина. Чемпионат (ж)",
        home="Уракан(ж)",
        away="Ривер Плэйт(ж)",
    )
    candidate = _candidate(
        fixture_id,
        country="Argentina",
        league=league,
        home=home,
        away=away,
        home_id=f"{fixture_id}-home",
        away_id=f"{fixture_id}-away",
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Аргентина",
            league="Чемпионат (ж)",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "missing"
    assert result.provider_event_id is None
    assert result.candidates
    assert all(
        "gender mismatch" in item.rejected_reasons for item in result.candidates
    )


def test_4958_women_target_allows_explicit_women_provider_context(
    session_factory,
):
    target = _target(
        event_order=4,
        championship="Аргентина. Чемпионат (ж)",
        home="Уракан(ж)",
        away="Ривер Плэйт(ж)",
        home_en="Huracan Women",
        away_en="River Plate Women",
    )
    candidate = _candidate(
        "women-fixture",
        country="Argentina",
        league="Primera Division Women",
        home="Huracan W",
        away="River Plate Women",
        home_id="women-home",
        away_id="women-away",
    )

    result = resolve_event_candidate(
        target,
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext(
            provider="api-sports",
            country="Аргентина",
            league="Primera Division Women",
            sport="football",
            competition=target.championship,
            derived=True,
        ),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "women-fixture"
    assert all(
        "gender mismatch" not in item.rejected_reasons
        for item in result.candidates
    )
