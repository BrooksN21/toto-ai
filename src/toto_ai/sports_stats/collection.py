from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from toto_ai.external_odds.api_sports import (
    APISportsError,
    HistoricalCacheUnavailable,
    ProviderPlanUnavailable,
    QuotaExhausted,
)
from toto_ai.external_odds.domain import TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.domain import (
    FootballEventFeatureSnapshot,
    MissingReason,
    SportsStatsRunSnapshot,
    StatsTargetEvent,
    build_event_snapshot,
    build_run_snapshot,
)
from toto_ai.sports_stats.features import build_team_window
from toto_ai.sports_stats.provider import SportsStatsProvider


def stats_targets_from_preparation(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    *,
    provider_name: str,
) -> tuple[StatsTargetEvent, ...]:
    if len(pins) != 15 or tuple(pin.event_order for pin in pins) != tuple(range(15)):
        raise ValueError("preparation_not_ready: exactly 15 ordered pins are required")
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    by_order = {pin.event_order: pin for pin in pins}
    rows: list[StatsTargetEvent] = []
    for event in target.events:
        pin = by_order[event.event_order]
        if pin.drawing_id != target.drawing_id:
            raise ValueError("preparation_not_ready: pin drawing mismatch")
        if pin.drawing_fingerprint != fingerprint:
            raise ValueError("preparation_not_ready: pin fingerprint mismatch")
        starts_at = _parse_utc(pin.starts_at, "pin starts_at")
        provider_available = (
            pin.effective_source_provider == provider_name
            and pin.provider_fixture_id is not None
            and pin.provider_home_team_id is not None
            and pin.provider_away_team_id is not None
        )
        rows.append(
            StatsTargetEvent(
                drawing_id=target.drawing_id,
                drawing_number=target.drawing_number,
                drawing_fingerprint=fingerprint,
                event_id=str(event.event_id),
                event_order=event.event_order,
                sport=event.sport,
                deadline=target.deadline,
                target_starts_at=starts_at,
                provider=provider_name,
                provider_fixture_id=(
                    pin.provider_fixture_id
                    if provider_available
                    else f"unavailable-{event.event_order}"
                ),
                canonical_home_team_id=pin.canonical_home_team_id,
                canonical_away_team_id=pin.canonical_away_team_id,
                provider_home_team_id=(
                    pin.provider_home_team_id
                    if provider_available
                    else f"unavailable-home-{event.event_order}"
                ),
                provider_away_team_id=(
                    pin.provider_away_team_id
                    if provider_available
                    else f"unavailable-away-{event.event_order}"
                ),
                home_team=event.home_team,
                away_team=event.away_team,
                provider_pin_available=provider_available,
            )
        )
    return tuple(rows)


def collect_sports_stats(
    target: TargetDrawing,
    pins: tuple[DrawingEventPinRecord, ...],
    provider: SportsStatsProvider,
    *,
    history_size: int = 10,
    now: Callable[[], datetime] | None = None,
    historical_as_of: datetime | None = None,
) -> SportsStatsRunSnapshot:
    if not isinstance(history_size, int) or isinstance(history_size, bool):
        raise ValueError("history_size must be an integer")
    if not 1 <= history_size <= 10:
        raise ValueError("history_size must be in range 1 through 10")
    clock = now or (lambda: datetime.now(timezone.utc))
    captured_at = clock()
    _require_utc("captured_at", captured_at)
    fixed_as_of = historical_as_of
    if fixed_as_of is not None:
        _require_utc("historical_as_of", fixed_as_of)
        if fixed_as_of >= target.deadline:
            raise ValueError("historical as-of must be before drawing deadline")
        if fixed_as_of > captured_at:
            raise ValueError("historical as-of must not be in the future")
    elif captured_at >= target.deadline:
        raise ValueError("prospective collection is after the drawing deadline")

    targets = stats_targets_from_preparation(
        target,
        pins,
        provider_name=provider.provider_name,
    )
    if any(item.provider != provider.provider_name for item in targets):
        raise ValueError("preparation_not_ready: provider identity mismatch")
    context_cache: dict[str, Any] = {}
    history_cache: dict[tuple[str, int], Any] = {}
    standings_cache: dict[tuple[str, int], Any] = {}
    unavailable_history_seasons: set[int] = set()
    unavailable_standing_seasons: set[int] = set()
    pending: list[tuple[StatsTargetEvent, dict[str, Any]]] = []

    cache_only = fixed_as_of is not None
    for item in targets:
        if not item.provider_pin_available:
            pending.append(
                (
                    item,
                    {
                        "status": "missing",
                        "reasons": ("preparation_not_ready",),
                    },
                )
            )
            continue
        if item.sport != "football":
            pending.append(
                (
                    item,
                    {
                        "status": "unsupported",
                        "reasons": ("unsupported_sport",),
                    },
                )
            )
            continue
        try:
            context = context_cache.get(item.provider_fixture_id)
            if context is None:
                context = provider.fetch_target_fixture(
                    item.provider_fixture_id,
                    as_of=fixed_as_of,
                    cache_only=cache_only,
                )
                context_cache[item.provider_fixture_id] = context
            _validate_context(item, context)
        except Exception as error:
            pending.append(
                (
                    item,
                    {
                        "status": "missing",
                        "reasons": (_reason_for_error(error, target=True),),
                    },
                )
            )
            continue
        if context.league_id is None or context.season is None:
            pending.append(
                (
                    item,
                    {
                        "status": "missing",
                        "reasons": ("league_or_season_missing",),
                        "context": context,
                    },
                )
            )
            continue
        cutoff = min(item.target_starts_at, fixed_as_of or captured_at)
        reasons: list[MissingReason] = []
        windows: dict[str, Any] = {}
        for side, team_id in (
            ("home", item.provider_home_team_id),
            ("away", item.provider_away_team_id),
        ):
            key = (team_id, context.season)
            try:
                if context.season in unavailable_history_seasons:
                    raise ProviderPlanUnavailable(
                        "API-Sports plan does not provide current-season history"
                    )
                fixtures = history_cache.get(key)
                if fixtures is None:
                    fixtures = provider.fetch_completed_fixtures(
                        team_id,
                        context.season,
                        cutoff=cutoff,
                        limit=history_size,
                        target_fixture_id=item.provider_fixture_id,
                        as_of=fixed_as_of,
                        cache_only=cache_only,
                    )
                    history_cache[key] = fixtures
                window = build_team_window(
                    team_id=team_id,
                    fixtures=fixtures,
                    requested_count=history_size,
                    target_starts_at=item.target_starts_at,
                    target_fixture_id=item.provider_fixture_id,
                    as_of=cutoff,
                )
                windows[side] = window
                if window is None:
                    reasons.append("no_completed_fixtures")
            except Exception as error:
                if isinstance(error, ProviderPlanUnavailable):
                    unavailable_history_seasons.add(context.season)
                reasons.append(_reason_for_error(error))
                windows[side] = None

        standings: dict[str, Any] = {"home": None, "away": None}
        standings_key = (context.league_id, context.season)
        if context.standings_supported is False:
            reasons.append("standings_unavailable")
        else:
            try:
                if context.season in unavailable_standing_seasons:
                    raise ProviderPlanUnavailable(
                        "API-Sports plan does not provide current standings"
                    )
                table = standings_cache.get(standings_key)
                if table is None:
                    table = provider.fetch_standings(
                        context.league_id,
                        context.season,
                        as_of=fixed_as_of,
                        cache_only=cache_only,
                    )
                    standings_cache[standings_key] = table
                by_team = {row.team_id: row for row in table}
                standings = {
                    "home": by_team.get(item.provider_home_team_id),
                    "away": by_team.get(item.provider_away_team_id),
                }
                if standings["home"] is None or standings["away"] is None:
                    reasons.append("standings_unavailable")
            except Exception as error:
                if isinstance(error, ProviderPlanUnavailable):
                    unavailable_standing_seasons.add(context.season)
                mapped = _reason_for_error(error)
                reasons.append(
                    mapped
                    if mapped
                    in (
                        "historical_asof_unavailable",
                        "provider_plan_unavailable",
                    )
                    else "standings_unavailable"
                )
        pending.append(
            (
                item,
                {
                    "status": "complete" if not reasons else "partial",
                    "reasons": tuple(sorted(set(reasons))),
                    "context": context,
                    "home_window": windows["home"],
                    "away_window": windows["away"],
                    "home_standing": standings["home"],
                    "away_standing": standings["away"],
                },
            )
        )

    as_of = fixed_as_of or clock()
    _require_utc("as_of", as_of)
    if as_of >= target.deadline:
        raise ValueError("sports-stat collection crossed the drawing deadline")
    events = tuple(
        _materialize_event(
            item,
            state,
            captured_at=captured_at if fixed_as_of is None else fixed_as_of,
            as_of=as_of,
        )
        for item, state in pending
    )
    return build_run_snapshot(
        drawing_id=target.drawing_id,
        drawing_number=target.drawing_number,
        drawing_fingerprint=targets[0].drawing_fingerprint,
        provider=provider.provider_name,
        requested_history_size=history_size,
        captured_at=captured_at if fixed_as_of is None else fixed_as_of,
        as_of=as_of,
        deadline=target.deadline,
        events=events,
        requests_made=provider.requests_made,
        cache_hits=provider.cache_hits,
    )


def _materialize_event(
    item: StatsTargetEvent,
    state: dict[str, Any],
    *,
    captured_at: datetime,
    as_of: datetime,
) -> FootballEventFeatureSnapshot:
    context = state.get("context")
    home_window = away_window = None
    if context is not None and "home_window" in state:
        home_window = state["home_window"]
        away_window = state["away_window"]
    sources = []
    if context is not None:
        sources.append(context.source)
    for window in (home_window, away_window):
        if window is not None:
            sources.extend(window.source_evidence)
    for standing in (state.get("home_standing"), state.get("away_standing")):
        if standing is not None:
            sources.append(standing.source)
    unique_sources = tuple(
        sorted(
            set(sources),
            key=lambda source: (
                source.endpoint,
                source.request_fingerprint,
                source.fetched_at,
            ),
        )
    )
    return build_event_snapshot(
        schema_version=1,
        drawing_id=item.drawing_id,
        drawing_number=item.drawing_number,
        drawing_fingerprint=item.drawing_fingerprint,
        event_id=item.event_id,
        event_order=item.event_order,
        sport=item.sport,
        provider=item.provider,
        status=state["status"],
        missing_reasons=state["reasons"],
        captured_at=captured_at,
        as_of=as_of,
        deadline=item.deadline,
        target_starts_at=item.target_starts_at,
        provider_fixture_id=(
            item.provider_fixture_id if context is not None else None
        ),
        canonical_home_team_id=(
            item.canonical_home_team_id if context is not None else None
        ),
        canonical_away_team_id=(
            item.canonical_away_team_id if context is not None else None
        ),
        provider_home_team_id=(
            item.provider_home_team_id if context is not None else None
        ),
        provider_away_team_id=(
            item.provider_away_team_id if context is not None else None
        ),
        league_id=None if context is None else context.league_id,
        season=None if context is None else context.season,
        home_window=home_window,
        away_window=away_window,
        home_standing=state.get("home_standing"),
        away_standing=state.get("away_standing"),
        source_evidence=unique_sources,
    )


def _validate_context(item: StatsTargetEvent, context: Any) -> None:
    if context.provider_fixture_id != item.provider_fixture_id:
        raise ValueError("provider fixture identity changed")
    if (
        context.home_team_id != item.provider_home_team_id
        or context.away_team_id != item.provider_away_team_id
    ):
        raise ValueError("provider team orientation changed")
    if context.starts_at != item.target_starts_at:
        raise ValueError("provider target start changed")


def _reason_for_error(
    error: Exception,
    *,
    target: bool = False,
) -> MissingReason:
    if isinstance(error, QuotaExhausted):
        return "quota_exhausted"
    if isinstance(error, HistoricalCacheUnavailable):
        return "historical_asof_unavailable"
    if isinstance(error, ProviderPlanUnavailable):
        return "provider_plan_unavailable"
    if isinstance(error, APISportsError):
        return "target_fixture_missing" if target else "provider_error"
    if isinstance(error, ValueError):
        return "stale_or_conflicting_cache"
    return "provider_error"


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO datetime") from error
    _require_utc(name, parsed)
    return parsed.astimezone(timezone.utc)


def _require_utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
