import math
from types import SimpleNamespace

from toto_ai.sports_stats.v2 import SportsV2Config, project_event_v2


def _window(*, home: bool):
    return SimpleNamespace(
        requested_count=10,
        fixture_count=10,
        goals_for=16 if home else 13,
        goals_against=10 if home else 14,
        home_played=5,
        home_wins=4,
        home_draws=1,
        home_losses=0,
        home_goals_for=10,
        home_goals_against=3,
        away_played=5,
        away_wins=1,
        away_draws=2,
        away_losses=2,
        away_goals_for=5,
        away_goals_against=8,
    )


def _feature(*, status="complete", sport="football", venue_games=5):
    home = _window(home=True)
    away = _window(home=False)
    home.home_played = venue_games
    away.away_played = venue_games
    return SimpleNamespace(
        event_order=3,
        status=status,
        sport=sport,
        home_window=home,
        away_window=away,
    )


def test_sports_v2_projection_is_normalized_and_capped():
    projection = project_event_v2(
        feature=_feature(),
        bk_probabilities=(0.45, 0.30, 0.25),
    )

    assert projection.status == "research_projection"
    assert projection.fallback_reason is None
    assert math.isclose(sum(projection.poisson_probabilities), 1.0)
    assert math.isclose(sum(projection.candidate_probabilities), 1.0)
    assert 0.0 < projection.blend_weight <= 0.20
    assert projection.expected_home_goals is not None
    assert projection.expected_away_goals is not None


def test_sports_v2_falls_back_when_venue_history_is_too_small():
    bk = (0.45, 0.30, 0.25)

    projection = project_event_v2(
        feature=_feature(venue_games=1),
        bk_probabilities=bk,
    )

    assert projection.status == "bk_fallback"
    assert projection.fallback_reason == "insufficient_venue_history"
    assert projection.candidate_probabilities == bk
    assert projection.blend_weight == 0.0


def test_sports_v2_shrinks_strong_market_disagreement():
    feature = _feature()
    config = SportsV2Config(disagreement_limit=0.20)

    projection = project_event_v2(
        feature=feature,
        bk_probabilities=(0.05, 0.10, 0.85),
        config=config,
    )

    assert projection.disagreement >= config.disagreement_limit
    assert projection.blend_weight == 0.0
    assert projection.candidate_probabilities == (0.05, 0.10, 0.85)
