"""Public exports loaded on demand; pure readers do not load other workflows."""

from importlib import import_module

_EXPORTS = {
    "CompletedFixture": "domain",
    "FootballEventFeatureSnapshot": "domain",
    "FootballTeamWindow": "domain",
    "ProviderFixtureContext": "domain",
    "SourceEvidence": "domain",
    "SportsStatsRunSnapshot": "domain",
    "StandingRow": "domain",
    "StatsTargetEvent": "domain",
    "collect_sports_stats": "collection",
    "load_latest_eligible_snapshot": "storage",
    "load_sports_stats_snapshot": "storage",
    "save_sports_stats_snapshot": "storage",
}
__all__ = list(_EXPORTS)


def __dir__():
    return sorted(set(globals()) | set(__all__))


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f"{__name__}.{_EXPORTS[name]}"), name)
    globals()[name] = value
    return value
