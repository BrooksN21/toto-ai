"""Deterministic, pre-kickoff feature tables for sports-v3 research."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

_COMPLETED_STATUSES = frozenset({"FT", "AET", "PEN"})
_SIDES = ("home", "away")

PREDICTOR_FEATURE_NAMES = tuple(
    f"{side}_{suffix}"
    for side in _SIDES
    for suffix in (
        "prior_match_count",
        "rolling_ppg",
        "rolling_goal_difference_per_game",
        "rolling_goals_for_per_game",
        "rolling_goals_against_per_game",
        "opponent_rolling_ppg",
        "opponent_rolling_goal_difference_per_game",
        "days_since_last_match",
        "rest_days",
        "matches_in_last_7_days",
        "matches_in_last_14_days",
        "venue_prior_match_count",
        "venue_goals_for_per_game",
        "venue_goals_against_per_game",
    )
)


@dataclass(frozen=True)
class SportsV3FeatureRow:
    """One target event and its strictly pre-kickoff predictor values."""

    event_id: str
    event_order: int
    home_team_id: str
    away_team_id: str
    kickoff: datetime
    features: dict[str, int | float | None]
    missing_reasons: tuple[str, ...]
    missing_features: tuple[str, ...]


@dataclass(frozen=True)
class SportsV3FeatureTable:
    """Canonical sports-v3 rows with an output-semantic digest."""

    rows: tuple[SportsV3FeatureRow, ...]
    predictor_feature_names: tuple[str, ...]
    semantic_hash: str


@dataclass(frozen=True)
class _Match:
    event_id: str
    kickoff: datetime
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    venue_id: str | None


@dataclass(frozen=True)
class _TeamMetrics:
    prior_match_count: int
    rolling_ppg: float | None
    rolling_goal_difference_per_game: float | None
    rolling_goals_for_per_game: float | None
    rolling_goals_against_per_game: float | None
    days_since_last_match: float | None
    rest_days: float | None
    matches_in_last_7_days: int
    matches_in_last_14_days: int
    venue_prior_match_count: int
    venue_goals_for_per_game: float | None
    venue_goals_against_per_game: float | None
    missing_reasons: tuple[str, ...]


def build_sports_v3_feature_table(
    *,
    target_events: Sequence[Mapping[str, Any]],
    completed_matches: Sequence[Mapping[str, Any]],
    rolling_window: int,
    minimum_prior_matches: int,
) -> SportsV3FeatureTable:
    """Build a deterministic feature table without using target-time information.

    Identities are validated, never normalized or fuzzily matched. Only completed
    matches whose kickoff is strictly earlier than each target kickoff contribute.
    """

    _validate_limits(rolling_window, minimum_prior_matches)
    targets = _validated_targets(target_events)
    history = _validated_completed_matches(completed_matches)

    rows = tuple(
        _build_row(
            target=target,
            history=history,
            rolling_window=rolling_window,
            minimum_prior_matches=minimum_prior_matches,
        )
        for target in targets
    )
    semantic_hash = _semantic_hash(
        rows=rows,
        rolling_window=rolling_window,
        minimum_prior_matches=minimum_prior_matches,
    )
    return SportsV3FeatureTable(
        rows=rows,
        predictor_feature_names=PREDICTOR_FEATURE_NAMES,
        semantic_hash=semantic_hash,
    )


def _validate_limits(rolling_window: int, minimum_prior_matches: int) -> None:
    if not isinstance(rolling_window, int) or isinstance(rolling_window, bool):
        raise ValueError("rolling_window must be an integer")
    if not isinstance(minimum_prior_matches, int) or isinstance(
        minimum_prior_matches, bool
    ):
        raise ValueError("minimum_prior_matches must be an integer")
    if rolling_window < 1:
        raise ValueError("rolling_window must be positive")
    if minimum_prior_matches < 1:
        raise ValueError("minimum_prior_matches must be positive")
    if minimum_prior_matches > rolling_window:
        raise ValueError("minimum_prior_matches cannot exceed rolling_window")


def _validated_targets(
    target_events: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    targets: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    event_orders: set[int] = set()

    for raw in target_events:
        event_id = _identity(raw, "event_id", "event identity")
        if event_id in event_ids:
            raise ValueError(f"duplicate event identity: {event_id}")
        event_ids.add(event_id)

        event_order = raw.get("event_order")
        if not isinstance(event_order, int) or isinstance(event_order, bool):
            raise ValueError("event identity requires an integer event_order")
        if event_order in event_orders:
            raise ValueError(f"duplicate event identity order: {event_order}")
        event_orders.add(event_order)

        home_team_id = _identity(raw, "home_team_id", "team identity")
        away_team_id = _identity(raw, "away_team_id", "team identity")
        if home_team_id == away_team_id:
            raise ValueError("team identity must differ between home and away")

        targets.append(
            {
                "event_id": event_id,
                "event_order": event_order,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "kickoff": _aware_datetime(raw, "kickoff"),
            }
        )

    return tuple(
        sorted(targets, key=lambda item: (item["event_order"], item["event_id"]))
    )


def _validated_completed_matches(
    completed_matches: Sequence[Mapping[str, Any]],
) -> tuple[_Match, ...]:
    matches: list[_Match] = []
    event_ids: set[str] = set()

    for raw in completed_matches:
        event_id = _identity(raw, "event_id", "event identity")
        if event_id in event_ids:
            raise ValueError(f"duplicate completed event identity: {event_id}")
        event_ids.add(event_id)

        home_team_id = _identity(raw, "home_team_id", "team identity")
        away_team_id = _identity(raw, "away_team_id", "team identity")
        if home_team_id == away_team_id:
            raise ValueError("team identity must differ between home and away")
        kickoff = _aware_datetime(raw, "kickoff")

        if raw.get("status") not in _COMPLETED_STATUSES:
            continue

        home_goals = _goals(raw, "home_goals")
        away_goals = _goals(raw, "away_goals")
        venue_id = raw.get("venue_id")
        if venue_id is not None and (
            not isinstance(venue_id, str) or not venue_id
        ):
            raise ValueError("venue identity must be a non-empty string or null")

        matches.append(
            _Match(
                event_id=event_id,
                kickoff=kickoff,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_goals=home_goals,
                away_goals=away_goals,
                venue_id=venue_id,
            )
        )

    return tuple(sorted(matches, key=lambda match: (match.kickoff, match.event_id)))


def _identity(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} requires a non-empty {key}")
    return value


def _aware_datetime(raw: Mapping[str, Any], key: str) -> datetime:
    value = raw.get(key)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{key} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{key} must be a timezone-aware datetime")
    return value


def _goals(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _build_row(
    *,
    target: Mapping[str, Any],
    history: tuple[_Match, ...],
    rolling_window: int,
    minimum_prior_matches: int,
) -> SportsV3FeatureRow:
    home = _team_metrics(
        side="home",
        team_id=target["home_team_id"],
        target_kickoff=target["kickoff"],
        history=history,
        rolling_window=rolling_window,
        minimum_prior_matches=minimum_prior_matches,
    )
    away = _team_metrics(
        side="away",
        team_id=target["away_team_id"],
        target_kickoff=target["kickoff"],
        history=history,
        rolling_window=rolling_window,
        minimum_prior_matches=minimum_prior_matches,
    )

    features: dict[str, int | float | None] = {}
    metrics_by_side = {"home": home, "away": away}
    for side in _SIDES:
        metrics = metrics_by_side[side]
        opponent = metrics_by_side["away" if side == "home" else "home"]
        features.update(
            {
                f"{side}_prior_match_count": metrics.prior_match_count,
                f"{side}_rolling_ppg": metrics.rolling_ppg,
                f"{side}_rolling_goal_difference_per_game": (
                    metrics.rolling_goal_difference_per_game
                ),
                f"{side}_rolling_goals_for_per_game": (
                    metrics.rolling_goals_for_per_game
                ),
                f"{side}_rolling_goals_against_per_game": (
                    metrics.rolling_goals_against_per_game
                ),
                f"{side}_opponent_rolling_ppg": opponent.rolling_ppg,
                f"{side}_opponent_rolling_goal_difference_per_game": (
                    opponent.rolling_goal_difference_per_game
                ),
                f"{side}_days_since_last_match": metrics.days_since_last_match,
                f"{side}_rest_days": metrics.rest_days,
                f"{side}_matches_in_last_7_days": metrics.matches_in_last_7_days,
                f"{side}_matches_in_last_14_days": metrics.matches_in_last_14_days,
                f"{side}_venue_prior_match_count": metrics.venue_prior_match_count,
                f"{side}_venue_goals_for_per_game": (
                    metrics.venue_goals_for_per_game
                ),
                f"{side}_venue_goals_against_per_game": (
                    metrics.venue_goals_against_per_game
                ),
            }
        )

    if tuple(features) != PREDICTOR_FEATURE_NAMES:
        raise AssertionError("feature construction diverged from predictor allowlist")

    return SportsV3FeatureRow(
        event_id=target["event_id"],
        event_order=target["event_order"],
        home_team_id=target["home_team_id"],
        away_team_id=target["away_team_id"],
        kickoff=target["kickoff"],
        features=features,
        missing_reasons=tuple(sorted((*home.missing_reasons, *away.missing_reasons))),
        missing_features=tuple(
            name for name, value in features.items() if value is None
        ),
    )


def _team_metrics(
    *,
    side: str,
    team_id: str,
    target_kickoff: datetime,
    history: tuple[_Match, ...],
    rolling_window: int,
    minimum_prior_matches: int,
) -> _TeamMetrics:
    eligible = [
        match
        for match in history
        if match.kickoff < target_kickoff
        and team_id in (match.home_team_id, match.away_team_id)
    ]
    eligible.sort(key=lambda match: (match.kickoff, match.event_id), reverse=True)
    window = eligible[:rolling_window]
    venue_window = [
        match
        for match in window
        if (side == "home" and match.home_team_id == team_id)
        or (side == "away" and match.away_team_id == team_id)
    ]
    enough_history = len(window) >= minimum_prior_matches
    enough_venue_history = len(venue_window) >= minimum_prior_matches

    reasons: list[str] = []
    if not enough_history:
        reasons.append(f"{side}_prior_matches_below_minimum")
    if not enough_venue_history:
        reasons.append(f"{side}_venue_prior_matches_below_minimum")

    points, goals_for, goals_against = _totals(team_id, window)
    _, venue_goals_for, venue_goals_against = _totals(team_id, venue_window)
    days_since_last_match = (
        _days_between(target_kickoff, window[0].kickoff) if enough_history else None
    )

    return _TeamMetrics(
        prior_match_count=len(window),
        rolling_ppg=points / len(window) if enough_history else None,
        rolling_goal_difference_per_game=(
            (goals_for - goals_against) / len(window) if enough_history else None
        ),
        rolling_goals_for_per_game=(
            goals_for / len(window) if enough_history else None
        ),
        rolling_goals_against_per_game=(
            goals_against / len(window) if enough_history else None
        ),
        days_since_last_match=days_since_last_match,
        rest_days=days_since_last_match,
        matches_in_last_7_days=_recent_count(eligible, target_kickoff, days=7),
        matches_in_last_14_days=_recent_count(eligible, target_kickoff, days=14),
        venue_prior_match_count=len(venue_window),
        venue_goals_for_per_game=(
            venue_goals_for / len(venue_window) if enough_venue_history else None
        ),
        venue_goals_against_per_game=(
            venue_goals_against / len(venue_window) if enough_venue_history else None
        ),
        missing_reasons=tuple(reasons),
    )


def _totals(team_id: str, matches: Sequence[_Match]) -> tuple[int, int, int]:
    points = 0
    goals_for = 0
    goals_against = 0
    for match in matches:
        if match.home_team_id == team_id:
            team_goals = match.home_goals
            opponent_goals = match.away_goals
        else:
            team_goals = match.away_goals
            opponent_goals = match.home_goals
        goals_for += team_goals
        goals_against += opponent_goals
        points += (
            3 if team_goals > opponent_goals else int(team_goals == opponent_goals)
        )
    return points, goals_for, goals_against


def _days_between(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / timedelta(days=1).total_seconds()


def _recent_count(
    matches: Sequence[_Match], target_kickoff: datetime, *, days: int
) -> int:
    boundary = target_kickoff - timedelta(days=days)
    return sum(boundary <= match.kickoff < target_kickoff for match in matches)


def _semantic_hash(
    *,
    rows: tuple[SportsV3FeatureRow, ...],
    rolling_window: int,
    minimum_prior_matches: int,
) -> str:
    payload = {
        "minimum_prior_matches": minimum_prior_matches,
        "predictor_feature_names": PREDICTOR_FEATURE_NAMES,
        "rolling_window": rolling_window,
        "rows": [
            {
                "away_team_id": row.away_team_id,
                "event_id": row.event_id,
                "event_order": row.event_order,
                "features": row.features,
                "home_team_id": row.home_team_id,
                "kickoff": row.kickoff.isoformat(),
                "missing_features": row.missing_features,
                "missing_reasons": row.missing_reasons,
            }
            for row in rows
        ],
        "schema_version": 1,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PREDICTOR_FEATURE_NAMES",
    "SportsV3FeatureRow",
    "SportsV3FeatureTable",
    "build_sports_v3_feature_table",
]
