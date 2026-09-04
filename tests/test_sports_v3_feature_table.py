from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table

UTC = timezone.utc
TARGET_KICKOFF = datetime(2026, 9, 10, 18, tzinfo=UTC)


def _target(
    event_id: str = "target-1",
    *,
    event_order: int = 0,
    home_team_id: str | None = "home",
    away_team_id: str | None = "away",
    kickoff: datetime = TARGET_KICKOFF,
) -> dict:
    return {
        "event_id": event_id,
        "event_order": event_order,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "kickoff": kickoff,
    }


def _match(
    match_id: str,
    days_before: float,
    home_team_id: str,
    away_team_id: str,
    home_goals: int,
    away_goals: int,
    *,
    venue_id: str | None = None,
) -> dict:
    return {
        "event_id": match_id,
        "kickoff": TARGET_KICKOFF - timedelta(days=days_before),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "venue_id": venue_id,
        "status": "FT",
    }


def _history() -> tuple[dict, ...]:
    return (
        _match("h-1", 12, "home", "h-old-1", 2, 0, venue_id="home-ground"),
        _match("h-2", 6, "h-old-2", "home", 1, 1, venue_id="other-1"),
        _match("h-3", 3, "home", "h-old-3", 3, 1, venue_id="home-ground"),
        _match("a-1", 11, "a-old-1", "away", 0, 2, venue_id="other-2"),
        _match("a-2", 5, "away", "a-old-2", 1, 0, venue_id="away-ground"),
        _match("a-3", 2, "a-old-3", "away", 2, 1, venue_id="other-3"),
    )


def _build(
    *,
    target_events: tuple[dict, ...] = (_target(),),
    completed_matches: tuple[dict, ...] | None = None,
    minimum_prior_matches: int = 2,
):
    return build_sports_v3_feature_table(
        target_events=target_events,
        completed_matches=(
            _history() if completed_matches is None else completed_matches
        ),
        rolling_window=5,
        minimum_prior_matches=minimum_prior_matches,
    )


def test_exact_event_and_team_identity_is_required_and_fails_closed():
    with pytest.raises(ValueError, match="event identity"):
        _build(target_events=(_target(event_id=""),))

    with pytest.raises(ValueError, match="duplicate.*event identity"):
        _build(target_events=(_target(), _target(event_order=1)))

    with pytest.raises(ValueError, match="team identity"):
        _build(target_events=(_target(home_team_id=None),))

    case_variant_history = (
        _match("wrong-case-1", 4, "HOME", "x", 4, 0),
        _match("wrong-case-2", 2, "y", "HOME", 0, 3),
        *_history()[3:],
    )
    row = _build(completed_matches=case_variant_history).rows[0]
    assert row.features["home_prior_match_count"] == 0
    assert row.features["home_rolling_ppg"] is None
    assert "home_prior_matches_below_minimum" in row.missing_reasons


def test_only_completed_history_strictly_before_target_kickoff_is_used():
    history = (
        _match("eligible", 1, "home", "old", 2, 0),
        {
            **_match("same-kickoff", 0, "home", "same", 9, 0),
            "kickoff": TARGET_KICKOFF,
        },
        {
            **_match("future", -1, "home", "future-opponent", 9, 0),
            "kickoff": TARGET_KICKOFF + timedelta(days=1),
        },
        {
            **_match("not-complete", 2, "home", "unfinished", 9, 0),
            "status": "NS",
        },
    )

    row = _build(completed_matches=history, minimum_prior_matches=1).rows[0]

    assert row.features["home_prior_match_count"] == 1
    assert row.features["home_rolling_ppg"] == pytest.approx(3.0)
    assert row.features["home_rolling_goals_for_per_game"] == pytest.approx(2.0)
    assert row.features["home_rolling_goals_against_per_game"] == pytest.approx(0.0)


def test_opponent_rolling_ppg_and_goal_difference_are_pre_kickoff_features():
    row = _build().rows[0]

    # The target home side sees the target away side's prior form, and vice versa.
    assert row.features["home_opponent_rolling_ppg"] == pytest.approx(2.0)
    assert row.features[
        "home_opponent_rolling_goal_difference_per_game"
    ] == pytest.approx(2 / 3)
    assert row.features["away_opponent_rolling_ppg"] == pytest.approx(7 / 3)
    assert row.features[
        "away_opponent_rolling_goal_difference_per_game"
    ] == pytest.approx(4 / 3)


def test_prior_match_minimum_emits_null_features_and_an_explicit_missing_reason():
    history = (
        _match("home-only", 3, "home", "old", 2, 0),
        _match("away-1", 4, "away", "old-a", 1, 0),
        _match("away-2", 2, "old-b", "away", 1, 1),
    )

    row = _build(completed_matches=history, minimum_prior_matches=2).rows[0]

    assert row.features["home_prior_match_count"] == 1
    assert row.features["home_rolling_ppg"] is None
    assert row.features["home_rolling_goal_difference_per_game"] is None
    assert row.features["home_rolling_goals_for_per_game"] is None
    assert row.features["home_rolling_goals_against_per_game"] is None
    assert row.features["home_rest_days"] is None
    assert "home_prior_matches_below_minimum" in row.missing_reasons
    assert "home_rolling_ppg" in row.missing_features
    assert "home_rest_days" in row.missing_features
    assert row.features["away_rolling_ppg"] is not None


def test_home_away_rolling_goals_and_recency_congestion_venue_fields():
    row = _build().rows[0]

    assert row.features["home_rolling_goals_for_per_game"] == pytest.approx(2.0)
    assert row.features["home_rolling_goals_against_per_game"] == pytest.approx(2 / 3)
    assert row.features["away_rolling_goals_for_per_game"] == pytest.approx(4 / 3)
    assert row.features["away_rolling_goals_against_per_game"] == pytest.approx(2 / 3)

    assert row.features["home_days_since_last_match"] == pytest.approx(3.0)
    assert row.features["away_days_since_last_match"] == pytest.approx(2.0)
    assert row.features["home_rest_days"] == pytest.approx(3.0)
    assert row.features["away_rest_days"] == pytest.approx(2.0)
    assert row.features["home_matches_in_last_7_days"] == 2
    assert row.features["away_matches_in_last_7_days"] == 2
    assert row.features["home_matches_in_last_14_days"] == 3
    assert row.features["away_matches_in_last_14_days"] == 3

    assert row.features["home_venue_prior_match_count"] == 2
    assert row.features["home_venue_goals_for_per_game"] == pytest.approx(2.5)
    assert row.features["home_venue_goals_against_per_game"] == pytest.approx(0.5)
    assert row.features["away_venue_prior_match_count"] == 2
    assert row.features["away_venue_goals_for_per_game"] == pytest.approx(1.5)
    assert row.features["away_venue_goals_against_per_game"] == pytest.approx(1.0)


def test_semantic_hash_is_deterministic_order_independent_and_content_sensitive():
    history = _history()
    first = _build(completed_matches=history)
    reordered = _build(completed_matches=tuple(reversed(history)))
    changed_history = tuple(
        {**match, "home_goals": match["home_goals"] + 1}
        if match["event_id"] == "h-1"
        else match
        for match in history
    )
    changed = _build(completed_matches=changed_history)

    assert reordered == first
    assert len(first.semantic_hash) == 64
    assert set(first.semantic_hash) <= set("0123456789abcdef")
    assert changed.semantic_hash != first.semantic_hash


def test_predictor_feature_names_exclude_outcome_and_post_match_labels():
    table = _build()
    forbidden_fragments = ("result", "actual", "target", "score", "outcome")
    predictor_names = tuple(name.lower() for name in table.predictor_feature_names)

    assert predictor_names
    assert set(table.predictor_feature_names) == set(table.rows[0].features)
    assert not {
        "event_id",
        "event_order",
        "home_team_id",
        "away_team_id",
        "kickoff",
    } & set(predictor_names)
    assert all(
        fragment not in name
        for name in predictor_names
        for fragment in forbidden_fragments
    )
