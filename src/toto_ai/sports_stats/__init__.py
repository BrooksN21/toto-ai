"""Audit-only sports-statistics evidence collection."""

from toto_ai.sports_stats.collection import collect_sports_stats
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    FootballEventFeatureSnapshot,
    FootballTeamWindow,
    ProviderFixtureContext,
    SourceEvidence,
    SportsStatsRunSnapshot,
    StandingRow,
    StatsTargetEvent,
)
from toto_ai.sports_stats.storage import (
    load_latest_eligible_snapshot,
    load_sports_stats_snapshot,
    save_sports_stats_snapshot,
)

__all__ = [
    "CompletedFixture",
    "FootballEventFeatureSnapshot",
    "FootballTeamWindow",
    "ProviderFixtureContext",
    "SourceEvidence",
    "SportsStatsRunSnapshot",
    "StandingRow",
    "StatsTargetEvent",
    "collect_sports_stats",
    "load_latest_eligible_snapshot",
    "load_sports_stats_snapshot",
    "save_sports_stats_snapshot",
]
