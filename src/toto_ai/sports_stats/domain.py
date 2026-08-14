from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Literal

SPORTS_STATS_SCHEMA_VERSION = 1
FeatureStatus = Literal["complete", "partial", "missing", "unsupported"]
RunStatus = Literal["complete", "partial", "failed"]
MissingReason = Literal[
    "unsupported_sport",
    "preparation_not_ready",
    "target_fixture_missing",
    "league_or_season_missing",
    "provider_error",
    "provider_plan_unavailable",
    "quota_exhausted",
    "no_completed_fixtures",
    "standings_unavailable",
    "historical_asof_unavailable",
    "future_data_rejected",
    "stale_or_conflicting_cache",
]

_FEATURE_STATUSES = frozenset(("complete", "partial", "missing", "unsupported"))
_RUN_STATUSES = frozenset(("complete", "partial", "failed"))
_MISSING_REASONS = frozenset(
    (
        "unsupported_sport",
        "preparation_not_ready",
        "target_fixture_missing",
        "league_or_season_missing",
        "provider_error",
        "provider_plan_unavailable",
        "quota_exhausted",
        "no_completed_fixtures",
        "standings_unavailable",
        "historical_asof_unavailable",
        "future_data_rejected",
        "stale_or_conflicting_cache",
    )
)


@dataclass(frozen=True)
class SourceEvidence:
    provider: str
    endpoint: str
    request_fingerprint: str
    payload_sha256: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        _text("provider", self.provider)
        _text("endpoint", self.endpoint)
        _sha256("request_fingerprint", self.request_fingerprint)
        _sha256("payload_sha256", self.payload_sha256)
        _utc("fetched_at", self.fetched_at)


@dataclass(frozen=True)
class StatsTargetEvent:
    drawing_id: int
    drawing_number: int | None
    drawing_fingerprint: str
    event_id: str
    event_order: int
    sport: str
    deadline: datetime
    target_starts_at: datetime
    provider: str
    provider_fixture_id: str
    canonical_home_team_id: int
    canonical_away_team_id: int
    provider_home_team_id: str
    provider_away_team_id: str
    home_team: str
    away_team: str
    provider_pin_available: bool = True

    def __post_init__(self) -> None:
        _positive_int("drawing_id", self.drawing_id)
        if self.drawing_number is not None:
            _positive_int("drawing_number", self.drawing_number)
        _sha256("drawing_fingerprint", self.drawing_fingerprint)
        _text("event_id", self.event_id)
        if self.event_order not in range(15):
            raise ValueError("event_order must be in range 0 through 14")
        if self.sport not in ("football", "hockey", "unknown"):
            raise ValueError("sport is invalid")
        _utc("deadline", self.deadline)
        _utc("target_starts_at", self.target_starts_at)
        _text("provider", self.provider)
        _text("provider_fixture_id", self.provider_fixture_id)
        _positive_int("canonical_home_team_id", self.canonical_home_team_id)
        _positive_int("canonical_away_team_id", self.canonical_away_team_id)
        _text("provider_home_team_id", self.provider_home_team_id)
        _text("provider_away_team_id", self.provider_away_team_id)
        _text("home_team", self.home_team)
        _text("away_team", self.away_team)
        if not isinstance(self.provider_pin_available, bool):
            raise ValueError("provider_pin_available must be a bool")


@dataclass(frozen=True)
class ProviderFixtureContext:
    provider_fixture_id: str
    starts_at: datetime
    home_team_id: str
    away_team_id: str
    league_id: str | None
    season: int | None
    standings_supported: bool | None
    source: SourceEvidence

    def __post_init__(self) -> None:
        _text("provider_fixture_id", self.provider_fixture_id)
        _utc("starts_at", self.starts_at)
        _text("home_team_id", self.home_team_id)
        _text("away_team_id", self.away_team_id)
        if self.league_id is not None:
            _text("league_id", self.league_id)
        if self.season is not None:
            _positive_int("season", self.season)
        if self.standings_supported not in (True, False, None):
            raise ValueError("standings_supported must be bool or None")


@dataclass(frozen=True)
class CompletedFixture:
    provider_fixture_id: str
    starts_at: datetime
    status: str
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    source: SourceEvidence

    def __post_init__(self) -> None:
        _text("provider_fixture_id", self.provider_fixture_id)
        _utc("starts_at", self.starts_at)
        if self.status not in ("FT", "AET", "PEN"):
            raise ValueError("completed fixture status must be FT, AET, or PEN")
        _text("home_team_id", self.home_team_id)
        _text("away_team_id", self.away_team_id)
        _nonnegative_int("home_goals", self.home_goals)
        _nonnegative_int("away_goals", self.away_goals)
        if self.home_team_id == self.away_team_id:
            raise ValueError("fixture teams must differ")


@dataclass(frozen=True)
class StandingRow:
    team_id: str
    rank: int
    points: int
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    source: SourceEvidence

    def __post_init__(self) -> None:
        _text("team_id", self.team_id)
        _positive_int("rank", self.rank)
        for name in (
            "points",
            "played",
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
        ):
            _nonnegative_int(name, getattr(self, name))
        if self.wins + self.draws + self.losses != self.played:
            raise ValueError("standing W-D-L must equal played")


@dataclass(frozen=True)
class FootballTeamWindow:
    team_id: str
    requested_count: int
    fixture_ids: tuple[str, ...]
    fixture_count: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    home_played: int
    home_wins: int
    home_draws: int
    home_losses: int
    home_goals_for: int
    home_goals_against: int
    away_played: int
    away_wins: int
    away_draws: int
    away_losses: int
    away_goals_for: int
    away_goals_against: int
    points_per_game: float | None
    last5_form_points: int
    last_completed_at: datetime | None
    rest_days: float | None
    source_evidence: tuple[SourceEvidence, ...]

    def __post_init__(self) -> None:
        _text("team_id", self.team_id)
        _positive_int("requested_count", self.requested_count)
        if self.requested_count > 10:
            raise ValueError("requested_count must be at most 10")
        if not isinstance(self.fixture_ids, tuple):
            raise ValueError("fixture_ids must be a tuple")
        if len(self.fixture_ids) != len(set(self.fixture_ids)):
            raise ValueError("fixture_ids must be unique")
        if self.fixture_count != len(self.fixture_ids):
            raise ValueError("fixture_count must match fixture_ids")
        if not 0 <= self.fixture_count <= self.requested_count:
            raise ValueError("fixture_count is outside requested window")
        if self.fixture_count == 0:
            raise ValueError("an available team window must contain history")
        for name in (
            "wins",
            "draws",
            "losses",
            "goals_for",
            "goals_against",
            "home_played",
            "home_wins",
            "home_draws",
            "home_losses",
            "home_goals_for",
            "home_goals_against",
            "away_played",
            "away_wins",
            "away_draws",
            "away_losses",
            "away_goals_for",
            "away_goals_against",
            "last5_form_points",
        ):
            _nonnegative_int(name, getattr(self, name))
        if self.wins + self.draws + self.losses != self.fixture_count:
            raise ValueError("overall W-D-L must equal fixture_count")
        if self.home_wins + self.home_draws + self.home_losses != self.home_played:
            raise ValueError("home W-D-L must equal home_played")
        if self.away_wins + self.away_draws + self.away_losses != self.away_played:
            raise ValueError("away W-D-L must equal away_played")
        if self.home_played + self.away_played != self.fixture_count:
            raise ValueError("home and away counts must equal fixture_count")
        _optional_finite_nonnegative("points_per_game", self.points_per_game)
        if self.last_completed_at is not None:
            _utc("last_completed_at", self.last_completed_at)
        _optional_finite_nonnegative("rest_days", self.rest_days)
        if self.last_completed_at is None or self.rest_days is None:
            raise ValueError("an available team window requires completion/rest values")


@dataclass(frozen=True)
class FootballEventFeatureSnapshot:
    schema_version: int
    drawing_id: int
    drawing_number: int | None
    drawing_fingerprint: str
    event_id: str
    event_order: int
    sport: str
    provider: str
    status: FeatureStatus
    missing_reasons: tuple[MissingReason, ...]
    captured_at: datetime
    as_of: datetime
    deadline: datetime
    target_starts_at: datetime
    provider_fixture_id: str | None
    canonical_home_team_id: int | None
    canonical_away_team_id: int | None
    provider_home_team_id: str | None
    provider_away_team_id: str | None
    league_id: str | None
    season: int | None
    home_window: FootballTeamWindow | None
    away_window: FootballTeamWindow | None
    home_standing: StandingRow | None
    away_standing: StandingRow | None
    source_evidence: tuple[SourceEvidence, ...]
    feature_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != SPORTS_STATS_SCHEMA_VERSION:
            raise ValueError("unsupported sports-stat schema version")
        _positive_int("drawing_id", self.drawing_id)
        if self.drawing_number is not None:
            _positive_int("drawing_number", self.drawing_number)
        _sha256("drawing_fingerprint", self.drawing_fingerprint)
        _text("event_id", self.event_id)
        if self.event_order not in range(15):
            raise ValueError("event_order must be in range 0 through 14")
        if self.sport not in ("football", "hockey", "unknown"):
            raise ValueError("sport is invalid")
        _text("provider", self.provider)
        if self.status not in _FEATURE_STATUSES:
            raise ValueError("feature status is invalid")
        _missing_reasons(self.missing_reasons)
        _utc("captured_at", self.captured_at)
        _utc("as_of", self.as_of)
        _utc("deadline", self.deadline)
        _utc("target_starts_at", self.target_starts_at)
        if self.captured_at > self.as_of:
            raise ValueError("captured_at must not be after as_of")
        if self.as_of >= self.deadline:
            raise ValueError("as_of must be before deadline")
        if self.status == "complete" and self.missing_reasons:
            raise ValueError("complete feature cannot have missing reasons")
        if self.status != "complete" and not self.missing_reasons:
            raise ValueError("non-complete feature requires missing reasons")
        if self.status == "complete" and (
            self.home_window is None or self.away_window is None
        ):
            raise ValueError("complete feature requires both history windows")
        if (
            self.home_window is not None
            and self.provider_home_team_id != self.home_window.team_id
        ):
            raise ValueError("home window team identity mismatch")
        if (
            self.away_window is not None
            and self.provider_away_team_id != self.away_window.team_id
        ):
            raise ValueError("away window team identity mismatch")
        if any(source.fetched_at > self.as_of for source in self.source_evidence):
            raise ValueError("source evidence must not be after as_of")
        if any(source.fetched_at >= self.deadline for source in self.source_evidence):
            raise ValueError("source evidence must be before deadline")
        if any(source.provider != self.provider for source in self.source_evidence):
            raise ValueError("source evidence provider mismatch")
        _sha256("feature_sha256", self.feature_sha256)

    def canonical_payload(self) -> dict[str, Any]:
        payload = _json_ready(asdict(self))
        payload.pop("feature_sha256")
        # Run observation boundaries are persisted on the row but are not part
        # of the canonical feature identity. Replaying identical immutable
        # provider evidence from cache must reproduce the same feature hash.
        payload.pop("captured_at")
        payload.pop("as_of")
        return payload


@dataclass(frozen=True)
class SportsStatsRunSnapshot:
    schema_version: int
    run_id: str
    content_sha256: str
    drawing_id: int
    drawing_number: int | None
    drawing_fingerprint: str
    provider: str
    requested_history_size: int
    captured_at: datetime
    as_of: datetime
    deadline: datetime
    status: RunStatus
    events: tuple[FootballEventFeatureSnapshot, ...]
    complete_count: int
    partial_count: int
    missing_count: int
    unsupported_count: int
    requests_made: int
    cache_hits: int
    source_request_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SPORTS_STATS_SCHEMA_VERSION:
            raise ValueError("unsupported sports-stat schema version")
        _sha256("run_id", self.run_id)
        _sha256("content_sha256", self.content_sha256)
        _positive_int("drawing_id", self.drawing_id)
        if self.drawing_number is not None:
            _positive_int("drawing_number", self.drawing_number)
        _sha256("drawing_fingerprint", self.drawing_fingerprint)
        _text("provider", self.provider)
        _positive_int("requested_history_size", self.requested_history_size)
        if self.requested_history_size > 10:
            raise ValueError("requested_history_size must be at most 10")
        _utc("captured_at", self.captured_at)
        _utc("as_of", self.as_of)
        _utc("deadline", self.deadline)
        if self.captured_at > self.as_of or self.as_of >= self.deadline:
            raise ValueError("run chronology is invalid")
        if self.status not in _RUN_STATUSES:
            raise ValueError("run status is invalid")
        if len(self.events) != 15:
            raise ValueError("run must contain exactly 15 event snapshots")
        if tuple(event.event_order for event in self.events) != tuple(range(15)):
            raise ValueError("run event orders 0 through 14 are required")
        identity_checks = (
            ("drawing id", lambda event: event.drawing_id == self.drawing_id),
            (
                "drawing number",
                lambda event: event.drawing_number == self.drawing_number,
            ),
            (
                "drawing fingerprint",
                lambda event: (
                    event.drawing_fingerprint == self.drawing_fingerprint
                ),
            ),
            ("provider", lambda event: event.provider == self.provider),
            (
                "captured_at",
                lambda event: event.captured_at == self.captured_at,
            ),
            ("as_of", lambda event: event.as_of == self.as_of),
            ("deadline", lambda event: event.deadline == self.deadline),
        )
        for name, matches in identity_checks:
            if any(not matches(event) for event in self.events):
                raise ValueError(f"event {name} mismatch")
        counts = {
            "complete": self.complete_count,
            "partial": self.partial_count,
            "missing": self.missing_count,
            "unsupported": self.unsupported_count,
        }
        if any(not isinstance(value, int) or value < 0 for value in counts.values()):
            raise ValueError("run counts must be non-negative integers")
        if sum(counts.values()) != 15:
            raise ValueError("run counts must total 15")
        if any(
            counts[key] != sum(e.status == key for e in self.events)
            for key in counts
        ):
            raise ValueError("run counts do not match event statuses")
        _nonnegative_int("requests_made", self.requests_made)
        _nonnegative_int("cache_hits", self.cache_hits)
        if self.source_request_fingerprints != tuple(
            sorted(set(self.source_request_fingerprints))
        ):
            raise ValueError("source request fingerprints must be sorted and unique")
        for value in self.source_request_fingerprints:
            _sha256("source request fingerprint", value)
        expected_fingerprints = tuple(
            sorted(
                {
                    source.request_fingerprint
                    for event in self.events
                    for source in event.source_evidence
                }
            )
        )
        if self.source_request_fingerprints != expected_fingerprints:
            raise ValueError("run source request fingerprints mismatch")

    def canonical_payload(self) -> dict[str, Any]:
        payload = _json_ready(asdict(self))
        payload.pop("run_id")
        payload.pop("content_sha256")
        return payload


def build_event_snapshot(**values: Any) -> FootballEventFeatureSnapshot:
    candidate = FootballEventFeatureSnapshot(feature_sha256="0" * 64, **values)
    return replace(
        candidate,
        feature_sha256=canonical_sha256(candidate.canonical_payload()),
    )


def build_run_snapshot(
    *,
    drawing_id: int,
    drawing_number: int | None,
    drawing_fingerprint: str,
    provider: str,
    requested_history_size: int,
    captured_at: datetime,
    as_of: datetime,
    deadline: datetime,
    events: tuple[FootballEventFeatureSnapshot, ...],
    requests_made: int,
    cache_hits: int,
) -> SportsStatsRunSnapshot:
    counts = {
        key: sum(event.status == key for event in events)
        for key in ("complete", "partial", "missing", "unsupported")
    }
    status: RunStatus
    if counts["complete"] == 15:
        status = "complete"
    elif counts["missing"] + counts["unsupported"] == 15:
        status = "failed"
    else:
        status = "partial"
    fingerprints = tuple(
        sorted(
            {
                source.request_fingerprint
                for event in events
                for source in event.source_evidence
            }
        )
    )
    candidate = SportsStatsRunSnapshot(
        schema_version=SPORTS_STATS_SCHEMA_VERSION,
        run_id="0" * 64,
        content_sha256="0" * 64,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        drawing_fingerprint=drawing_fingerprint,
        provider=provider,
        requested_history_size=requested_history_size,
        captured_at=captured_at,
        as_of=as_of,
        deadline=deadline,
        status=status,
        events=events,
        complete_count=counts["complete"],
        partial_count=counts["partial"],
        missing_count=counts["missing"],
        unsupported_count=counts["unsupported"],
        requests_made=requests_made,
        cache_hits=cache_hits,
        source_request_fingerprints=fingerprints,
    )
    digest = canonical_sha256(candidate.canonical_payload())
    return replace(candidate, run_id=digest, content_sha256=digest)


def canonical_json(value: Any) -> str:
    return json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_ready(asdict(value))
    if isinstance(value, datetime):
        _utc("datetime", value)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _nonnegative_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _sha256(name: str, value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _optional_finite_nonnegative(name: str, value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
        or value < 0
    ):
        raise ValueError(f"{name} must be finite and non-negative or None")


def _missing_reasons(value: object) -> None:
    if not isinstance(value, tuple):
        raise ValueError("missing_reasons must be a tuple")
    if value != tuple(sorted(set(value))):
        raise ValueError("missing_reasons must be sorted and unique")
    if any(item not in _MISSING_REASONS for item in value):
        raise ValueError("missing_reasons contains an unsupported value")
