from dataclasses import dataclass
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

NOW = datetime(2026, 7, 23, 14, tzinfo=timezone.utc)
ALIASES_PATH = "data/external-odds/team-aliases.json"


@dataclass(frozen=True)
class ReviewedIdentityCase:
    target_team: str
    provider_team: str
    provider_team_id: str
    fixture_id: str
    similar_variant: str
    country: str
    league: str


DRAWING_4957_IDENTITIES = (
    ReviewedIdentityCase(
        target_team="Феникс Пилар",
        provider_team="Fénix",
        provider_team_id="8374",
        fixture_id="1500012",
        similar_variant="Fénix Reserves",
        country="Argentina",
        league="Primera C",
    ),
    ReviewedIdentityCase(
        target_team="Эстер",
        provider_team="Osters IF",
        provider_team_id="2174",
        fixture_id="osters-if-4957",
        similar_variant="Osters IF U21",
        country="Sweden",
        league="Superettan",
    ),
    ReviewedIdentityCase(
        target_team="Варберг",
        provider_team="Varbergs BoIS FC",
        provider_team_id="2171",
        fixture_id="1497638",
        similar_variant="Varbergs BoIS FC U21",
        country="Sweden",
        league="Superettan",
    ),
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target() -> TargetEvent:
    return TargetEvent(
        drawing_id=1,
        drawing_number=1,
        event_id=1,
        event_order=0,
        sport="football",
        championship="Европа. Лига конференций УЕФА. Квалификация",
        starts_at=None,
        deadline=NOW,
        home_team="Флора",
        away_team="ТНС",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.42, 0.26, 0.32),
    )


def _candidate(
    fixture_id: str,
    *,
    home: str = "Flora Tallinn",
    away: str = "The New Saints",
) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league="UEFA Europa Conference League",
        starts_at=NOW + timedelta(hours=2),
        home_team=home,
        away_team=away,
        fetched_at=NOW,
        payload_hash=f"hash-{fixture_id}",
        country="World",
        provider_home_team_id="687",
        provider_away_team_id="354",
    )


def _context() -> ResolutionContext:
    return ResolutionContext(
        provider="api-sports",
        country="Европа",
        league="Лига конференций УЕФА. Квалификация",
        sport="football",
        competition="Европа. Лига конференций УЕФА. Квалификация",
        derived=True,
    )


def test_reviewed_tns_alias_resolves_unique_api_sports_fixture(session_factory):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _target(),
        (_candidate("1589427"),),
        session_factory=session_factory,
        context=_context(),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "1589427"
    assert result.orientation == "same"
    assert result.candidates[0].reviewed_team_count == 1
    assert result.candidates[0].away_score == 1.0


def test_reviewed_tns_alias_does_not_match_similar_academy_name(session_factory):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _target(),
        (_candidate("academy", away="The New Saints Academy"),),
        session_factory=session_factory,
        context=_context(),
    )

    assert result.status != "matched"
    assert result.provider_event_id is None
    assert result.candidates[0].reviewed_team_count == 0


def test_reviewed_tns_alias_does_not_hide_duplicate_fixture_collision(
    session_factory,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _target(),
        (_candidate("1589427"), _candidate("duplicate")),
        session_factory=session_factory,
        context=_context(),
    )

    assert result.status == "ambiguous"
    assert result.provider_event_id is None
    assert {item.provider_event_id for item in result.candidates} == {
        "1589427",
        "duplicate",
    }


def _drawing_4957_target(case: ReviewedIdentityCase) -> TargetEvent:
    return TargetEvent(
        drawing_id=11983,
        drawing_number=4957,
        event_id=100,
        event_order=0,
        sport="football",
        championship=f"{case.country}. {case.league}",
        starts_at=None,
        deadline=NOW,
        home_team=case.target_team,
        away_team="Verified Opponent",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.42, 0.26, 0.32),
    )


def _drawing_4957_candidate(
    case: ReviewedIdentityCase,
    fixture_id: str,
    *,
    home: str | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league=case.league,
        starts_at=NOW + timedelta(hours=2),
        home_team=home or case.provider_team,
        away_team="Verified Opponent",
        fetched_at=NOW,
        payload_hash=f"hash-{fixture_id}",
        country=case.country,
        provider_home_team_id=case.provider_team_id,
        provider_away_team_id="verified-opponent",
    )


def _drawing_4957_context(case: ReviewedIdentityCase) -> ResolutionContext:
    return ResolutionContext(
        provider="api-sports",
        country=case.country,
        league=case.league,
        sport="football",
        competition=f"{case.country}. {case.league}",
        derived=True,
    )


@pytest.mark.parametrize("case", DRAWING_4957_IDENTITIES)
def test_reviewed_drawing_4957_identity_resolves_exact_candidate(
    session_factory,
    case,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _drawing_4957_target(case),
        (_drawing_4957_candidate(case, case.fixture_id),),
        session_factory=session_factory,
        context=_drawing_4957_context(case),
    )

    assert result.status == "matched"
    assert result.provider_event_id == case.fixture_id
    assert result.orientation == "same"
    assert result.candidates[0].reviewed_team_count == 1
    assert result.candidates[0].home_score == 1.0


@pytest.mark.parametrize("case", DRAWING_4957_IDENTITIES)
def test_reviewed_drawing_4957_identity_does_not_match_similar_variant(
    session_factory,
    case,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _drawing_4957_target(case),
        (
            _drawing_4957_candidate(
                case,
                f"{case.fixture_id}-variant",
                home=case.similar_variant,
            ),
        ),
        session_factory=session_factory,
        context=_drawing_4957_context(case),
    )

    assert result.status != "matched"
    assert result.provider_event_id is None
    assert result.candidates[0].reviewed_team_count == 0


@pytest.mark.parametrize("case", DRAWING_4957_IDENTITIES)
def test_reviewed_drawing_4957_identity_keeps_exact_fixture_collision_ambiguous(
    session_factory,
    case,
):
    seed_reviewed_alias_config(session_factory, ALIASES_PATH)

    result = resolve_event_candidate(
        _drawing_4957_target(case),
        (
            _drawing_4957_candidate(case, case.fixture_id),
            _drawing_4957_candidate(case, f"{case.fixture_id}-duplicate"),
        ),
        session_factory=session_factory,
        context=_drawing_4957_context(case),
    )

    assert result.status == "ambiguous"
    assert result.provider_event_id is None
