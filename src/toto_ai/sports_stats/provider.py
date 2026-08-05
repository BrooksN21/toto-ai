from __future__ import annotations

from datetime import datetime
from typing import Protocol

from toto_ai.external_odds.domain import QuotaState
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    ProviderFixtureContext,
    StandingRow,
)


class SportsStatsProvider(Protocol):
    provider_name: str

    @property
    def quota_state(self) -> QuotaState:
        ...

    @property
    def requests_made(self) -> int:
        ...

    @property
    def cache_hits(self) -> int:
        ...

    def fetch_target_fixture(
        self,
        provider_fixture_id: str,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> ProviderFixtureContext:
        ...

    def fetch_completed_fixtures(
        self,
        team_id: str,
        season: int,
        *,
        cutoff: datetime,
        limit: int,
        target_fixture_id: str,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> tuple[CompletedFixture, ...]:
        ...

    def fetch_standings(
        self,
        league_id: str,
        season: int,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> tuple[StandingRow, ...]:
        ...
