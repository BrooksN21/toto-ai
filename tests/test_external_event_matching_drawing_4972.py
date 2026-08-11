import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base
from toto_ai.external_odds.competition_taxonomy import competition_identity
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing, TargetEvent
from toto_ai.external_odds.preparation import load_local_schedule, prepare_drawing
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_aliases import canonical_team_alias_identity
from toto_ai.external_odds.team_registry import seed_reviewed_alias_config
from toto_ai.external_odds.team_resolution import (
    derive_resolution_context,
    resolve_event_candidate,
)

FIXTURES = Path(__file__).parent / "fixtures"
TARGET_PATH = FIXTURES / "drawing_4972_totobrief_target.json"
SCHEDULE_PATH = FIXTURES / "drawing_4972_api_sports_schedule.json"
ALIASES_PATH = Path("data/external-odds/team-aliases.json")
FETCHED_AT = datetime(2026, 8, 11, 7, 37, 38, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    seed_reviewed_alias_config(factory, ALIASES_PATH)
    yield factory
    engine.dispose()


def _target() -> TargetDrawing:
    return parse_target_drawing(
        json.loads(TARGET_PATH.read_text(encoding="utf-8")),
        fetched_at=FETCHED_AT,
    )


def _candidates() -> tuple[ProviderEvent, ...]:
    return load_local_schedule(SCHEDULE_PATH)


def _resolve(
    target: TargetEvent,
    candidates: tuple[ProviderEvent, ...],
    session_factory,
):
    return resolve_event_candidate(
        target,
        candidates,
        session_factory=session_factory,
        context=derive_resolution_context(target, provider="api-sports"),
    )


@pytest.mark.parametrize(
    ("country", "left", "right", "identity"),
    (
        ("Brazil", "CRB", "Клуб Регатас Бразил", "BR:CLUBE_REGATAS_BRASIL"),
        ("Finland", "JJK", "ЯЮК", "FI:JJK"),
    ),
)
def test_reusable_team_alias_table_is_country_scoped(
    country,
    left,
    right,
    identity,
):
    assert canonical_team_alias_identity(left, country=country) == identity
    assert canonical_team_alias_identity(right, country=country) == identity
    assert canonical_team_alias_identity(left, country="Chile") is None


@pytest.mark.parametrize(
    ("country", "left", "right", "identity"),
    (
        ("Colombia", "1-й дивизион", "Primera B", "CO:PRIMERA_B"),
        ("Chile", "1-й дивизион", "Ascenso", "CL:PRIMERA_B"),
        ("Chile", "1-й дивизион", "Primera B", "CL:PRIMERA_B"),
        ("Finland", "2-й дивизион", "Ykkönen", "FI:YKKONEN"),
    ),
)
def test_country_aware_competition_alias_table(country, left, right, identity):
    assert competition_identity(left, country=country) == identity
    assert competition_identity(right, country=country) == identity
    assert competition_identity(right, country="Brazil") is None


@pytest.mark.parametrize(
    ("event_order", "fixture_id"),
    ((6, "1520801"), (7, "1549593"), (8, "1511644"), (9, "1517240")),
)
def test_all_four_observed_4972_misses_resolve_same_orientation(
    event_order,
    fixture_id,
    session_factory,
):
    target = _target().events[event_order]
    result = _resolve(target, _candidates(), session_factory)

    assert result.status == "matched"
    assert result.provider_event_id == fixture_id
    assert result.orientation == "same"


def test_country_aware_league_alias_rejects_reversed_candidate(session_factory):
    target = _target().events[7]
    candidate = next(
        event for event in _candidates() if event.provider_event_id == "1549593"
    )
    reversed_candidate = replace(
        candidate,
        home_team=candidate.away_team,
        away_team=candidate.home_team,
        provider_home_team_id=candidate.provider_away_team_id,
        provider_away_team_id=candidate.provider_home_team_id,
    )

    result = _resolve(target, (reversed_candidate,), session_factory)

    assert result.status != "matched"
    assert result.provider_event_id is None


def test_country_aware_league_alias_rejects_ambiguous_collision(session_factory):
    target = _target().events[8]
    candidate = next(
        event for event in _candidates() if event.provider_event_id == "1511644"
    )
    collision = replace(candidate, provider_event_id="collision")

    result = _resolve(target, (candidate, collision), session_factory)

    assert result.status == "ambiguous"
    assert result.provider_event_id is None


@pytest.mark.parametrize(
    "mutation",
    (
        {"country": "Colombia"},
        {"starts_at": datetime(2026, 8, 17, 23, 0, tzinfo=timezone.utc)},
    ),
)
def test_country_aware_league_alias_rejects_wrong_country_or_date(
    mutation,
    session_factory,
):
    target = _target().events[8]
    candidate = next(
        event for event in _candidates() if event.provider_event_id == "1511644"
    )

    result = _resolve(target, (replace(candidate, **mutation),), session_factory)

    assert result.status != "matched"
    assert result.provider_event_id is None


def test_drawing_4972_preparation_resolves_all_times_and_is_playable(
    session_factory,
):
    result = prepare_drawing(
        _target(),
        _candidates(),
        session_factory=session_factory,
        evaluated_at=FETCHED_AT,
    )

    assert result.status == "ready"
    assert result.mapped_count == 15
    assert result.external_coverage_count == 15
    assert result.baseline_only_event_orders == ()
    assert result.unresolved_event_orders == ()
    assert result.eligibility.status == "playable"
    assert result.eligibility.span_days == 2
    assert result.eligibility.missing_event_orders == ()
    assert tuple(pin.effective_source_provider for pin in result.pins) == (
        "api-sports",
    ) * 15


def test_existing_4972_baseline_rows_are_not_rewritten_by_provider_refresh(
    session_factory,
):
    target = _target()
    unresolved_ids = {"1520801", "1549593", "1511644", "1517240"}
    partial = tuple(
        event
        for event in _candidates()
        if event.provider_event_id not in unresolved_ids
    )

    initial = prepare_drawing(
        target,
        partial,
        session_factory=session_factory,
        evaluated_at=FETCHED_AT,
    )
    with pytest.raises(
        ValueError,
        match="conflicting immutable ready drawing preparation",
    ):
        prepare_drawing(
            target,
            _candidates(),
            session_factory=session_factory,
            evaluated_at=FETCHED_AT,
        )

    assert initial.status == "ready"
    assert initial.baseline_only_event_orders == (6, 7, 8, 9)
    assert initial.eligibility.status == "unknown"


def test_truly_unresolved_event_preserves_baseline_only_fallback(session_factory):
    target = _target()
    candidates = tuple(
        event
        for event in _candidates()
        if event.provider_event_id != "1520801"
    )

    result = prepare_drawing(
        target,
        candidates,
        session_factory=session_factory,
        evaluated_at=FETCHED_AT,
    )

    assert result.status == "ready"
    assert result.external_coverage_count == 14
    assert result.baseline_only_event_orders == (6,)
    assert result.eligibility.status == "unknown"
    assert result.eligibility.missing_event_orders == (6,)
