"""Conservative research projection for Sports Analytics v2.

V2 combines venue W/D/L evidence with a smoothed independent-Poisson goals
projection.  It remains a shadow model: the bookmaker row is always the anchor,
the sports influence is capped, and strong disagreement reduces that influence.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Any

from toto_ai.external_odds.domain import OutcomeTriplet
from toto_ai.sports_stats.domain import (
    FootballEventFeatureSnapshot,
    SportsStatsRunSnapshot,
    canonical_sha256,
)
from toto_ai.sports_stats.probabilities import (
    SHADOW_STATUS,
    ShadowEventProbability,
    SportsShadowArtifact,
)

MODEL_VERSION = "sports-analytics-v2-poisson-venue-shrunk-v1"


@dataclass(frozen=True)
class SportsV2Config:
    minimum_venue_matches: int = 2
    prior_matches: float = 3.0
    maximum_blend_weight: float = 0.20
    disagreement_limit: float = 0.45
    poisson_max_goals: int = 10

    def __post_init__(self) -> None:
        if (
            type(self.minimum_venue_matches) is not int
            or self.minimum_venue_matches < 1
        ):
            raise ValueError("minimum_venue_matches must be a positive integer")
        if not math.isfinite(self.prior_matches) or self.prior_matches <= 0.0:
            raise ValueError("prior_matches must be finite and positive")
        if not 0.0 < self.maximum_blend_weight <= 0.25:
            raise ValueError("maximum_blend_weight must be in (0, 0.25]")
        if not 0.0 < self.disagreement_limit <= 1.0:
            raise ValueError("disagreement_limit must be in (0, 1]")
        if type(self.poisson_max_goals) is not int or self.poisson_max_goals < 6:
            raise ValueError("poisson_max_goals must be at least 6")

    def payload(self) -> dict[str, Any]:
        return {"model_version": MODEL_VERSION, **asdict(self)}


@dataclass(frozen=True)
class SportsV2Projection:
    event_order: int
    status: str
    fallback_reason: str | None
    bk_probabilities: OutcomeTriplet
    venue_wdl_probabilities: OutcomeTriplet
    poisson_probabilities: OutcomeTriplet
    sports_probabilities: OutcomeTriplet
    candidate_probabilities: OutcomeTriplet
    expected_home_goals: float | None
    expected_away_goals: float | None
    venue_confidence: float
    disagreement: float
    blend_weight: float
    model_version: str = MODEL_VERSION


def build_sports_v2_shadow_artifact(
    *,
    snapshot: SportsStatsRunSnapshot,
    base_artifact: SportsShadowArtifact,
    config: SportsV2Config | None = None,
) -> SportsShadowArtifact:
    """Build a hash-bound v2 candidate from validated frozen v1 evidence.

    The base artifact remains the identity, chronology and orientation
    authority.  V2 can alter probabilities only for rows that already passed
    those checks; every base fallback remains an event-local BK fallback.
    """

    resolved = SportsV2Config() if config is None else config
    if base_artifact.status != SHADOW_STATUS:
        raise ValueError("base sports artifact must remain NOT_ACTIVATED")
    if snapshot.drawing_id != base_artifact.drawing_id:
        raise ValueError("sports v2 drawing id mismatch")
    if snapshot.drawing_number != base_artifact.drawing_number:
        raise ValueError("sports v2 drawing number mismatch")
    if snapshot.drawing_fingerprint != base_artifact.drawing_fingerprint:
        raise ValueError("sports v2 drawing fingerprint mismatch")
    if snapshot.content_sha256 != base_artifact.snapshot_content_sha256:
        raise ValueError("sports v2 snapshot hash mismatch")
    if len(snapshot.events) != 15 or len(base_artifact.events) != 15:
        raise ValueError("sports v2 requires exactly 15 events")

    events: list[ShadowEventProbability] = []
    for feature, base in zip(snapshot.events, base_artifact.events, strict=True):
        if feature.event_order != base.event_order or feature.event_id != base.event_id:
            raise ValueError("sports v2 event identity mismatch")
        projection = project_event_v2(
            feature=feature,
            bk_probabilities=base.bk_probabilities,
            config=resolved,
        )
        fallback_reason = (
            base.fallback_reason
            if base.probability_source != "sports_shadow"
            else projection.fallback_reason
        )
        if fallback_reason is not None:
            sports = base.bk_probabilities
            candidate = base.bk_probabilities
            source = "totobrief_bk_fallback"
            weight = 0.0
        else:
            sports = projection.sports_probabilities
            candidate = projection.candidate_probabilities
            source = "sports_shadow"
            weight = projection.blend_weight
        events.append(
            replace(
                base,
                sports_probabilities=sports,
                candidate_blend_probabilities=candidate,
                probability_source=source,
                blend_weight=weight,
                fallback_reason=fallback_reason,
                features={
                    **base.features,
                    "sports_v2": {
                        "model_version": MODEL_VERSION,
                        "expected_home_goals": projection.expected_home_goals,
                        "expected_away_goals": projection.expected_away_goals,
                        "venue_confidence": projection.venue_confidence,
                        "disagreement": projection.disagreement,
                        "blend_weight": weight,
                    },
                },
                provenance={
                    **base.provenance,
                    "sports_model": MODEL_VERSION if fallback_reason is None else None,
                    "sports_v2_config": resolved.payload(),
                    "base_artifact_sha256": base_artifact.artifact_sha256,
                },
            )
        )

    coverage = sum(event.probability_source == "sports_shadow" for event in events)
    candidate_artifact = replace(
        base_artifact,
        model_status=(
            "EXPERIMENTAL_UNTRAINED_V2" if coverage else "INSUFFICIENT_EVIDENCE"
        ),
        model_definition=(
            "Sports Analytics v2: venue W/D/L plus smoothed independent-Poisson "
            "goals, anchored to TotoBrief BK with capped confidence/disagreement "
            "shrinkage and event-local fallback"
        ),
        sports_coverage_count=coverage,
        fallback_count=15 - coverage,
        events=tuple(events),
        artifact_sha256="0" * 64,
    )
    return replace(
        candidate_artifact,
        artifact_sha256=canonical_sha256(candidate_artifact.canonical_payload()),
    )


def project_event_v2(
    *,
    feature: FootballEventFeatureSnapshot,
    bk_probabilities: OutcomeTriplet,
    config: SportsV2Config | None = None,
) -> SportsV2Projection:
    """Project one event without allowing sports data to dominate BK."""

    resolved = SportsV2Config() if config is None else config
    bk = _normalize(bk_probabilities)
    home = feature.home_window
    away = feature.away_window
    if feature.sport != "football" or feature.status != "complete":
        return _fallback(feature.event_order, bk, "feature_not_complete_or_football")
    if home is None or away is None:
        return _fallback(feature.event_order, bk, "team_history_missing")
    if (
        home.home_played < resolved.minimum_venue_matches
        or away.away_played < resolved.minimum_venue_matches
    ):
        return _fallback(feature.event_order, bk, "insufficient_venue_history")

    venue_wdl = _normalize(
        (
            home.home_wins + away.away_losses + 0.5,
            home.home_draws + away.away_draws + 0.5,
            home.home_losses + away.away_wins + 0.5,
        )
    )
    home_prior_for = home.goals_for / home.fixture_count
    home_prior_against = home.goals_against / home.fixture_count
    away_prior_for = away.goals_for / away.fixture_count
    away_prior_against = away.goals_against / away.fixture_count
    home_attack = _smoothed_rate(
        home.home_goals_for,
        home.home_played,
        home_prior_for,
        resolved.prior_matches,
    )
    away_defence = _smoothed_rate(
        away.away_goals_against,
        away.away_played,
        away_prior_against,
        resolved.prior_matches,
    )
    away_attack = _smoothed_rate(
        away.away_goals_for,
        away.away_played,
        away_prior_for,
        resolved.prior_matches,
    )
    home_defence = _smoothed_rate(
        home.home_goals_against,
        home.home_played,
        home_prior_against,
        resolved.prior_matches,
    )
    expected_home = _bounded_goal_rate((home_attack + away_defence) / 2.0)
    expected_away = _bounded_goal_rate((away_attack + home_defence) / 2.0)
    poisson = _poisson_wdl(
        expected_home,
        expected_away,
        max_goals=resolved.poisson_max_goals,
    )
    sports = _normalize(
        tuple(
            0.5 * venue + 0.5 * goals
            for venue, goals in zip(venue_wdl, poisson, strict=True)
        )
    )
    venue_confidence = min(
        1.0,
        min(home.home_played, away.away_played)
        / max(home.requested_count, away.requested_count),
    )
    disagreement = 0.5 * math.fsum(
        abs(left - right) for left, right in zip(bk, sports, strict=True)
    )
    disagreement_shrink = max(
        0.0,
        1.0 - disagreement / resolved.disagreement_limit,
    )
    blend_weight = (
        resolved.maximum_blend_weight * venue_confidence * disagreement_shrink
    )
    candidate = _normalize(
        tuple(
            (1.0 - blend_weight) * market + blend_weight * projection
            for market, projection in zip(bk, sports, strict=True)
        )
    )
    return SportsV2Projection(
        event_order=feature.event_order,
        status="research_projection",
        fallback_reason=None,
        bk_probabilities=bk,
        venue_wdl_probabilities=venue_wdl,
        poisson_probabilities=poisson,
        sports_probabilities=sports,
        candidate_probabilities=candidate,
        expected_home_goals=expected_home,
        expected_away_goals=expected_away,
        venue_confidence=venue_confidence,
        disagreement=disagreement,
        blend_weight=blend_weight,
    )


def _fallback(
    event_order: int,
    bk: OutcomeTriplet,
    reason: str,
) -> SportsV2Projection:
    return SportsV2Projection(
        event_order=event_order,
        status="bk_fallback",
        fallback_reason=reason,
        bk_probabilities=bk,
        venue_wdl_probabilities=bk,
        poisson_probabilities=bk,
        sports_probabilities=bk,
        candidate_probabilities=bk,
        expected_home_goals=None,
        expected_away_goals=None,
        venue_confidence=0.0,
        disagreement=0.0,
        blend_weight=0.0,
    )


def _smoothed_rate(
    goals: int,
    matches: int,
    prior_rate: float,
    prior_matches: float,
) -> float:
    return (goals + prior_rate * prior_matches) / (matches + prior_matches)


def _bounded_goal_rate(value: float) -> float:
    return min(4.0, max(0.2, value))


def _poisson_wdl(
    home_rate: float,
    away_rate: float,
    *,
    max_goals: int,
) -> OutcomeTriplet:
    home = _poisson_probabilities(home_rate, max_goals)
    away = _poisson_probabilities(away_rate, max_goals)
    win_1 = draw = win_2 = 0.0
    for home_goals, home_probability in enumerate(home):
        for away_goals, away_probability in enumerate(away):
            probability = home_probability * away_probability
            if home_goals > away_goals:
                win_1 += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                win_2 += probability
    return _normalize((win_1, draw, win_2))


def _poisson_probabilities(rate: float, max_goals: int) -> tuple[float, ...]:
    values = [math.exp(-rate)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * rate / goals)
    values[-1] += max(0.0, 1.0 - math.fsum(values))
    return tuple(values)


def _normalize(values: tuple[float, float, float]) -> OutcomeTriplet:
    total = math.fsum(values)
    if total <= 0.0 or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("probability row must be finite and non-negative")
    return tuple(value / total for value in values)  # type: ignore[return-value]
