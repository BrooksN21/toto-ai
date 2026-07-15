import dataclasses
import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.external_odds.domain import ProviderEvent, TargetEvent


def _matching_module():
    try:
        return importlib.import_module("toto_ai.external_odds.matching")
    except ModuleNotFoundError as error:
        pytest.fail(f"matching module is missing: {error}")


@pytest.fixture
def target():
    starts_at = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)
    deadline = starts_at - timedelta(minutes=5)
    return TargetEvent(
        drawing_id=9000,
        drawing_number=5000,
        event_id=101,
        event_order=0,
        sport="football",
        championship="UEFA Champions League",
        starts_at=starts_at,
        deadline=deadline,
        home_team="Бавария",
        away_team="ПСЖ",
        home_team_en="Bayern Munich",
        away_team_en="PSG",
        bk_probabilities=(0.5, 0.25, 0.25),
    )


@pytest.fixture
def provider_event(target):
    return _provider_event(
        provider_event_id="evt-1",
        sport=target.sport,
        starts_at=target.starts_at,
        home_team="Бавария",
        away_team="ПСЖ",
    )


def _provider_event(
    *,
    provider_event_id: str,
    sport: str,
    starts_at: datetime,
    home_team: str,
    away_team: str,
) -> ProviderEvent:
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=provider_event_id,
        sport=sport,
        league="UEFA Champions League",
        starts_at=starts_at,
        home_team=home_team,
        away_team=away_team,
        fetched_at=starts_at - timedelta(hours=1),
        payload_hash=f"hash-{provider_event_id}",
    )


def test_exact_unique_match_is_accepted(target, provider_event):
    matching = _matching_module()

    result = matching.match_event(target, [provider_event], aliases={})

    assert result.status == "matched"
    assert result.provider_event_id == provider_event.provider_event_id
    assert result.candidate_ids == (provider_event.provider_event_id,)


def test_ambiguous_and_reversed_matches_are_never_consumed(target):
    matching = _matching_module()

    ambiguous = matching.match_event(
        target,
        [
            _provider_event(
                provider_event_id="evt-a",
                sport=target.sport,
                starts_at=target.starts_at,
                home_team="Бавария",
                away_team="ПСЖ",
            ),
            _provider_event(
                provider_event_id="evt-b",
                sport=target.sport,
                starts_at=target.starts_at + timedelta(minutes=15),
                home_team="Бавария",
                away_team="ПСЖ",
            ),
        ],
        aliases={},
    )
    reversed_result = matching.match_event(
        target,
        [
            _provider_event(
                provider_event_id="evt-c",
                sport=target.sport,
                starts_at=target.starts_at,
                home_team="ПСЖ",
                away_team="Бавария",
            )
        ],
        aliases={},
    )

    assert ambiguous.status == "ambiguous"
    assert ambiguous.provider_event_id is None
    assert ambiguous.candidate_ids == ("evt-a", "evt-b")
    assert reversed_result.status == "missing"
    assert reversed_result.provider_event_id is None


def test_time_outside_three_hours_is_missing(target, provider_event):
    matching = _matching_module()
    late = dataclasses.replace(
        provider_event,
        starts_at=target.starts_at + timedelta(hours=3, seconds=1),
    )

    result = matching.match_event(target, [late], aliases={})

    assert result.status == "missing"
    assert result.provider_event_id is None


def test_name_en_and_reviewed_aliases_are_accepted_for_exact_matches(target):
    matching = _matching_module()

    name_en_match = matching.match_event(
        target,
        [
            _provider_event(
                provider_event_id="evt-en",
                sport=target.sport,
                starts_at=target.starts_at,
                home_team="Bayern Munich",
                away_team="PSG",
            )
        ],
        aliases={},
    )
    alias_match = matching.match_event(
        target,
        [
            _provider_event(
                provider_event_id="evt-alias",
                sport=target.sport,
                starts_at=target.starts_at,
                home_team="FC Bayern Munich",
                away_team="Paris SG",
            )
        ],
        aliases={
            "fc bayern munich": "bayern munich",
            "paris sg": "psg",
        },
    )

    assert name_en_match.status == "matched"
    assert name_en_match.provider_event_id == "evt-en"
    assert alias_match.status == "matched"
    assert alias_match.provider_event_id == "evt-alias"


def test_fuzzy_suggestion_never_authorizes_a_match(target):
    matching = _matching_module()
    candidate = _provider_event(
        provider_event_id="evt-fuzzy",
        sport=target.sport,
        starts_at=target.starts_at,
        home_team="Bayern Munchen",
        away_team="Paris Saint-Germain",
    )

    suggestions = matching.suggest_matches(target, [candidate], aliases={})
    decision = matching.match_event(target, [candidate], aliases={})

    assert suggestions[0].provider_event_id == candidate.provider_event_id
    assert 0.0 <= suggestions[0].score <= 1.0
    assert decision.status == "missing"
    assert decision.provider_event_id is None


def test_unknown_sport_short_circuits_matching(provider_event):
    matching = _matching_module()
    target = TargetEvent(
        drawing_id=9000,
        drawing_number=5000,
        event_id=102,
        event_order=1,
        sport="unknown",
        championship="Unknown competition",
        starts_at=datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc),
        deadline=datetime(2026, 7, 15, 17, 55, tzinfo=timezone.utc),
        home_team="Home",
        away_team="Away",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )

    result = matching.match_event(target, [provider_event], aliases={})

    assert result.status == "unknown_sport"
    assert result.provider_event_id is None
    assert result.candidate_ids == ()


def test_load_aliases_normalizes_and_rejects_invalid_schema(tmp_path):
    matching = _matching_module()
    valid_path = tmp_path / "team-aliases.json"
    valid_path.write_text(
        json.dumps(
            {
                "version": 1,
                "aliases": {
                    "FC Bayern Munich": "Bayern Munich",
                    "Paris SG": "PSG",
                },
            }
        ),
        encoding="utf-8",
    )

    aliases = matching.load_aliases(valid_path)

    assert aliases == {
        "fc bayern munich": "bayern munich",
        "paris sg": "psg",
    }

    extra_field_path = tmp_path / "extra-field.json"
    extra_field_path.write_text(
        json.dumps({"version": 1, "aliases": {}, "extra": True}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exact schema"):
        matching.load_aliases(extra_field_path)


def test_load_aliases_rejects_normalized_duplicates_and_cycles(tmp_path):
    matching = _matching_module()

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(
        json.dumps(
            {
                "version": 1,
                "aliases": {
                    "FC-Bayern": "Bayern Munich",
                    "fc bayern": "Bayern",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="normalized alias key"):
        matching.load_aliases(duplicate_path)

    cycle_path = tmp_path / "cycle.json"
    cycle_path.write_text(
        json.dumps({"version": 1, "aliases": {"A": "B", "B": "A"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cycle"):
        matching.load_aliases(cycle_path)
