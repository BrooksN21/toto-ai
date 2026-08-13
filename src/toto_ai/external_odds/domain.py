from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isclose, isfinite
from typing import Literal, Protocol

OutcomeTriplet = tuple[float, float, float]
TOTO_BRIEF_OUTCOME_ORDER = ("1", "X", "2")
Sport = Literal["football", "hockey", "unknown"]
_SPORTS = frozenset(("football", "hockey", "unknown"))


@dataclass(frozen=True)
class TargetEvent:
    drawing_id: int
    drawing_number: int | None
    event_id: int
    event_order: int
    sport: Sport
    championship: str
    starts_at: datetime | None
    deadline: datetime
    home_team: str
    away_team: str
    home_team_en: str | None
    away_team_en: str | None
    bk_probabilities: OutcomeTriplet
    pool_probabilities: OutcomeTriplet | None = None

    def __post_init__(self) -> None:
        _require_positive_int("drawing_id", self.drawing_id)
        _require_optional_int("drawing_number", self.drawing_number)
        _require_positive_int("event_id", self.event_id)
        if self.event_order not in range(15):
            raise ValueError("event_order must be in range 0 through 14")
        _require_sport(self.sport)
        _require_text("championship", self.championship)
        if self.starts_at is not None:
            _require_utc_datetime("starts_at", self.starts_at)
        _require_utc_datetime("deadline", self.deadline)
        _require_text("home_team", self.home_team)
        _require_text("away_team", self.away_team)
        _require_optional_text("home_team_en", self.home_team_en)
        _require_optional_text("away_team_en", self.away_team_en)
        _require_probability_triplet(self.bk_probabilities)
        if self.pool_probabilities is not None:
            _require_probability_triplet(self.pool_probabilities)


@dataclass(frozen=True)
class TargetDrawing:
    drawing_id: int
    drawing_number: int | None
    deadline: datetime
    fetched_at: datetime
    events: tuple[TargetEvent, ...]

    def __post_init__(self) -> None:
        _require_positive_int("drawing_id", self.drawing_id)
        _require_optional_int("drawing_number", self.drawing_number)
        _require_utc_datetime("deadline", self.deadline)
        _require_utc_datetime("fetched_at", self.fetched_at)
        if len(self.events) != 15:
            raise ValueError("TargetDrawing must contain exactly 15 events")
        if tuple(event.event_order for event in self.events) != tuple(range(15)):
            raise ValueError("TargetDrawing event orders 0 through 14 are required")
        if any(event.drawing_id != self.drawing_id for event in self.events):
            raise ValueError("TargetDrawing events must belong to the drawing")


@dataclass(frozen=True)
class ProviderMarket:
    provider: str
    provider_event_id: str
    bookmaker_id: str
    market_name: str
    updated_at: datetime
    fetched_at: datetime
    payload_hash: str
    home_price: float | None
    draw_price: float | None
    away_price: float | None
    source_endpoint: str | None = None
    request_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_text("provider", self.provider)
        _require_text("provider_event_id", self.provider_event_id)
        _require_text("bookmaker_id", self.bookmaker_id)
        _require_text("market_name", self.market_name)
        _require_utc_datetime("updated_at", self.updated_at)
        _require_utc_datetime("fetched_at", self.fetched_at)
        _require_text("payload_hash", self.payload_hash)
        _require_decimal_price("home_price", self.home_price)
        _require_decimal_price("draw_price", self.draw_price)
        _require_decimal_price("away_price", self.away_price)
        _require_optional_text("source_endpoint", self.source_endpoint)
        _require_optional_text("request_fingerprint", self.request_fingerprint)


@dataclass(frozen=True)
class ProviderEvent:
    provider: str
    provider_event_id: str
    sport: Sport
    league: str
    starts_at: datetime
    home_team: str
    away_team: str
    fetched_at: datetime
    payload_hash: str
    markets: tuple[ProviderMarket, ...] = ()
    country: str | None = None
    provider_home_team_id: str | None = None
    provider_away_team_id: str | None = None
    source_endpoint: str | None = None
    request_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_text("provider", self.provider)
        _require_text("provider_event_id", self.provider_event_id)
        _require_sport(self.sport)
        _require_text("league", self.league)
        _require_utc_datetime("starts_at", self.starts_at)
        _require_text("home_team", self.home_team)
        _require_text("away_team", self.away_team)
        _require_utc_datetime("fetched_at", self.fetched_at)
        _require_text("payload_hash", self.payload_hash)
        _require_optional_text("country", self.country)
        _require_optional_text("provider_home_team_id", self.provider_home_team_id)
        _require_optional_text("provider_away_team_id", self.provider_away_team_id)
        _require_optional_text("source_endpoint", self.source_endpoint)
        _require_optional_text("request_fingerprint", self.request_fingerprint)
        if not isinstance(self.markets, tuple):
            raise ValueError("markets must be a tuple")
        if any(market.provider != self.provider for market in self.markets):
            raise ValueError("markets must use the event provider")
        if any(
            market.provider_event_id != self.provider_event_id
            for market in self.markets
        ):
            raise ValueError("markets must belong to the provider event")


@dataclass(frozen=True)
class QuotaState:
    daily_limit: int | None
    daily_remaining: int | None
    minute_limit: int | None
    minute_remaining: int | None

    def __post_init__(self) -> None:
        _require_optional_nonnegative_int("daily_limit", self.daily_limit)
        _require_optional_nonnegative_int("daily_remaining", self.daily_remaining)
        _require_optional_nonnegative_int("minute_limit", self.minute_limit)
        _require_optional_nonnegative_int("minute_remaining", self.minute_remaining)


class ExternalOddsProvider(Protocol):
    provider_name: str

    @property
    def quota_state(self) -> QuotaState:
        ...

    def fetch_schedule(
        self, sport: Sport, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        ...

    def fetch_event_markets(
        self, sport: Sport, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        ...


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_optional_int(name: str, value: object) -> None:
    if value is not None:
        _require_positive_int(name, value)


def _require_optional_nonnegative_int(name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer or None")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _require_optional_text(name: str, value: object) -> None:
    if value is not None:
        _require_text(name, value)


def _require_sport(value: object) -> None:
    if value not in _SPORTS:
        raise ValueError("sport must be football, hockey, or unknown")


def _require_utc_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _require_probability_triplet(value: object) -> None:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("bk_probabilities must contain exactly three values")
    if any(
        not isinstance(item, (int, float))
        or isinstance(item, bool)
        or not isfinite(float(item))
        or item <= 0
        for item in value
    ):
        raise ValueError("bk_probabilities must contain finite positive values")
    if not isclose(sum(value), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("bk_probabilities must sum to one")


def _require_decimal_price(name: str, value: object) -> None:
    if value is None:
        return
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
        or value <= 0
    ):
        raise ValueError(f"{name} must be a finite positive decimal price or None")
