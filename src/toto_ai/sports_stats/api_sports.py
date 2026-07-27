from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from toto_ai.external_odds.api_sports import (
    APISportsClient,
    APISportsError,
    APISportsJSONPayload,
)
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    ProviderFixtureContext,
    SourceEvidence,
    StandingRow,
)

_COMPLETED = frozenset(("FT", "AET", "PEN"))


class APISportsFootballStatsProvider:
    provider_name = "api-sports"

    def __init__(self, client: APISportsClient) -> None:
        self._client = client

    @property
    def quota_state(self):
        return self._client.quota_state

    @property
    def requests_made(self) -> int:
        return self._client.requests_made

    @property
    def cache_hits(self) -> int:
        return self._client.cache_hits

    def fetch_target_fixture(
        self,
        provider_fixture_id: str,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> ProviderFixtureContext:
        response = self._client.fetch_football_fixture_payload(
            provider_fixture_id,
            as_of=as_of,
            cache_only=cache_only,
        )
        rows = _response_rows(response)
        if len(rows) != 1:
            raise APISportsError("API-Sports target fixture must be unique")
        row = rows[0]
        fixture = _mapping(row.get("fixture"), "fixture")
        fixture_id = _identifier(fixture.get("id"), "fixture id")
        if fixture_id != provider_fixture_id:
            raise APISportsError("API-Sports returned mismatched target fixture")
        teams = _mapping(row.get("teams"), "teams")
        home = _mapping(teams.get("home"), "home team")
        away = _mapping(teams.get("away"), "away team")
        league = _mapping(row.get("league"), "league")
        standings_value = league.get("standings")
        if standings_value not in (True, False, None):
            raise APISportsError("API-Sports standings support flag is invalid")
        return ProviderFixtureContext(
            provider_fixture_id=fixture_id,
            starts_at=_datetime(fixture.get("date"), "fixture date"),
            home_team_id=_identifier(home.get("id"), "home team id"),
            away_team_id=_identifier(away.get("id"), "away team id"),
            league_id=_optional_identifier(league.get("id"), "league id"),
            season=_optional_int(league.get("season"), "league season"),
            standings_supported=standings_value,
            source=_source(response),
        )

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
        _utc("cutoff", cutoff)
        historical = as_of is not None and cache_only
        response = self._client.fetch_football_team_fixtures_payload(
            team_id,
            season,
            limit=limit,
            as_of=as_of,
            cache_only=cache_only,
            historical_from=(
                (cutoff - timedelta(days=370)).date() if historical else None
            ),
            historical_to=(
                (cutoff - timedelta(microseconds=1)).date() if historical else None
            ),
        )
        source = _source(response)
        fixtures: list[CompletedFixture] = []
        rejected_future = False
        for row in _response_rows(response):
            fixture = _mapping(row.get("fixture"), "fixture")
            fixture_id = _identifier(fixture.get("id"), "fixture id")
            starts_at = _datetime(fixture.get("date"), "fixture date")
            status = _mapping(fixture.get("status"), "fixture status").get("short")
            if fixture_id == target_fixture_id:
                continue
            if starts_at >= cutoff:
                rejected_future = True
                continue
            if status not in _COMPLETED:
                continue
            teams = _mapping(row.get("teams"), "teams")
            home = _mapping(teams.get("home"), "home team")
            away = _mapping(teams.get("away"), "away team")
            home_team_id = _identifier(home.get("id"), "home team id")
            away_team_id = _identifier(away.get("id"), "away team id")
            if team_id not in (home_team_id, away_team_id):
                continue
            goals = _mapping(row.get("goals"), "goals")
            fixtures.append(
                CompletedFixture(
                    provider_fixture_id=fixture_id,
                    starts_at=starts_at,
                    status=str(status),
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    home_goals=_nonnegative_int(goals.get("home"), "home goals"),
                    away_goals=_nonnegative_int(goals.get("away"), "away goals"),
                    source=source,
                )
            )
        ordered = tuple(
            sorted(
                fixtures,
                key=lambda item: (item.starts_at, item.provider_fixture_id),
                reverse=True,
            )[:limit]
        )
        if rejected_future and not ordered:
            raise APISportsError(
                "API-Sports fixture history contained only future data"
            )
        return ordered

    def fetch_standings(
        self,
        league_id: str,
        season: int,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> tuple[StandingRow, ...]:
        response = self._client.fetch_football_standings_payload(
            league_id,
            season,
            as_of=as_of,
            cache_only=cache_only,
        )
        source = _source(response)
        rows: list[StandingRow] = []
        for response_row in _response_rows(response):
            league = _mapping(response_row.get("league"), "standings league")
            if _identifier(league.get("id"), "standings league id") != league_id:
                raise APISportsError("API-Sports returned mismatched standings league")
            if _positive_int(league.get("season"), "standings season") != season:
                raise APISportsError("API-Sports returned mismatched standings season")
            groups = league.get("standings")
            if not isinstance(groups, list):
                raise APISportsError("API-Sports standings must be a list")
            for group in groups:
                if not isinstance(group, list):
                    raise APISportsError("API-Sports standing group must be a list")
                for item in group:
                    row = _mapping(item, "standing row")
                    team = _mapping(row.get("team"), "standing team")
                    all_record = _mapping(row.get("all"), "standing all record")
                    goals = _mapping(all_record.get("goals"), "standing goals")
                    rows.append(
                        StandingRow(
                            team_id=_identifier(team.get("id"), "standing team id"),
                            rank=_positive_int(row.get("rank"), "standing rank"),
                            points=_nonnegative_int(
                                row.get("points"), "standing points"
                            ),
                            played=_nonnegative_int(
                                all_record.get("played"), "standing played"
                            ),
                            wins=_nonnegative_int(
                                all_record.get("win"), "standing wins"
                            ),
                            draws=_nonnegative_int(
                                all_record.get("draw"), "standing draws"
                            ),
                            losses=_nonnegative_int(
                                all_record.get("lose"), "standing losses"
                            ),
                            goals_for=_nonnegative_int(
                                goals.get("for"), "standing goals for"
                            ),
                            goals_against=_nonnegative_int(
                                goals.get("against"), "standing goals against"
                            ),
                            source=source,
                        )
                    )
        by_team: dict[str, StandingRow] = {}
        for row in rows:
            existing = by_team.get(row.team_id)
            if existing is not None and existing != row:
                raise APISportsError(
                    "API-Sports returned conflicting standing rows"
                )
            by_team[row.team_id] = row
        return tuple(
            sorted(by_team.values(), key=lambda item: (item.rank, item.team_id))
        )


def _source(value: APISportsJSONPayload) -> SourceEvidence:
    return SourceEvidence(
        provider="api-sports",
        endpoint=value.endpoint,
        request_fingerprint=value.request_fingerprint,
        payload_sha256=value.payload_sha256,
        fetched_at=value.fetched_at,
    )


def _response_rows(value: APISportsJSONPayload) -> tuple[Mapping[str, Any], ...]:
    response = value.payload.get("response")
    if not isinstance(response, list):
        raise APISportsError("API-Sports response must be a list")
    return tuple(_mapping(item, "response item") for item in response)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise APISportsError(f"API-Sports {name} must be an object")
    return value


def _identifier(value: object, name: str) -> str:
    if isinstance(value, bool):
        raise APISportsError(f"API-Sports {name} is invalid")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise APISportsError(f"API-Sports {name} is invalid")


def _optional_identifier(value: object, name: str) -> str | None:
    return None if value is None else _identifier(value, name)


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise APISportsError(f"API-Sports {name} is invalid")
    return value


def _optional_int(value: object, name: str) -> int | None:
    return None if value is None else _positive_int(value, name)


def _nonnegative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise APISportsError(f"API-Sports {name} is invalid")
    return value


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise APISportsError(f"API-Sports {name} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise APISportsError(f"API-Sports {name} is invalid") from error
    _utc(name, parsed)
    return parsed


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise APISportsError(f"API-Sports {name} must be UTC")
