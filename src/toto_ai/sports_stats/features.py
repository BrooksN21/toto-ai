from __future__ import annotations

from datetime import datetime

from toto_ai.sports_stats.domain import CompletedFixture, FootballTeamWindow


def build_team_window(
    *,
    team_id: str,
    fixtures: tuple[CompletedFixture, ...],
    requested_count: int,
    target_starts_at: datetime,
    target_fixture_id: str,
    as_of: datetime,
) -> FootballTeamWindow | None:
    cutoff = min(target_starts_at, as_of)
    eligible = tuple(
        sorted(
            (
                fixture
                for fixture in fixtures
                if fixture.provider_fixture_id != target_fixture_id
                and fixture.starts_at < cutoff
                and fixture.status in ("FT", "AET", "PEN")
                and team_id in (fixture.home_team_id, fixture.away_team_id)
            ),
            key=lambda item: (item.starts_at, item.provider_fixture_id),
            reverse=True,
        )[:requested_count]
    )
    if any(fixture.starts_at >= cutoff for fixture in eligible):
        raise ValueError("future fixture reached team feature window")
    if not eligible:
        return None

    overall = _aggregate(team_id, eligible)
    home = _aggregate(
        team_id,
        tuple(fixture for fixture in eligible if fixture.home_team_id == team_id),
    )
    away = _aggregate(
        team_id,
        tuple(fixture for fixture in eligible if fixture.away_team_id == team_id),
    )
    last_five = eligible[:5]
    last5_points = sum(_points(team_id, fixture) for fixture in last_five)
    latest = eligible[0].starts_at
    rest_days = round(
        (target_starts_at - latest).total_seconds() / 86400.0,
        6,
    )
    return FootballTeamWindow(
        team_id=team_id,
        requested_count=requested_count,
        fixture_ids=tuple(fixture.provider_fixture_id for fixture in eligible),
        fixture_count=len(eligible),
        wins=overall["wins"],
        draws=overall["draws"],
        losses=overall["losses"],
        goals_for=overall["goals_for"],
        goals_against=overall["goals_against"],
        home_played=len(
            tuple(fixture for fixture in eligible if fixture.home_team_id == team_id)
        ),
        home_wins=home["wins"],
        home_draws=home["draws"],
        home_losses=home["losses"],
        home_goals_for=home["goals_for"],
        home_goals_against=home["goals_against"],
        away_played=len(
            tuple(fixture for fixture in eligible if fixture.away_team_id == team_id)
        ),
        away_wins=away["wins"],
        away_draws=away["draws"],
        away_losses=away["losses"],
        away_goals_for=away["goals_for"],
        away_goals_against=away["goals_against"],
        points_per_game=round(
            (overall["wins"] * 3 + overall["draws"]) / len(eligible),
            6,
        ),
        last5_form_points=last5_points,
        last_completed_at=latest,
        rest_days=rest_days,
        source_evidence=tuple(
            dict.fromkeys(fixture.source for fixture in eligible)
        ),
    )


def _aggregate(
    team_id: str,
    fixtures: tuple[CompletedFixture, ...],
) -> dict[str, int]:
    wins = draws = losses = goals_for = goals_against = 0
    for fixture in fixtures:
        is_home = fixture.home_team_id == team_id
        team_goals = fixture.home_goals if is_home else fixture.away_goals
        opponent_goals = fixture.away_goals if is_home else fixture.home_goals
        goals_for += team_goals
        goals_against += opponent_goals
        if team_goals > opponent_goals:
            wins += 1
        elif team_goals == opponent_goals:
            draws += 1
        else:
            losses += 1
    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
    }


def _points(team_id: str, fixture: CompletedFixture) -> int:
    is_home = fixture.home_team_id == team_id
    team_goals = fixture.home_goals if is_home else fixture.away_goals
    opponent_goals = fixture.away_goals if is_home else fixture.home_goals
    if team_goals > opponent_goals:
        return 3
    if team_goals == opponent_goals:
        return 1
    return 0
