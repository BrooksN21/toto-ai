from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from toto_ai.external_odds.domain import (
    ProviderEvent,
    ProviderMarket,
    QuotaState,
    Sport,
)

FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"
HOCKEY_BASE_URL = "https://v1.hockey.api-sports.io"
_RETRY_STATUSES = frozenset((408, 429, 500, 502, 503, 504))


class APISportsError(RuntimeError):
    """Sanitized API-Sports provider failure."""


class QuotaExhausted(APISportsError):
    """Raised when the provider quota reserve has been reached."""


@dataclass(frozen=True)
class _CachePayload:
    quota: QuotaState
    payload: dict[str, Any]


class APISportsClient:
    provider_name = "api-sports"

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache_dir: Path = Path("data/external-cache/api-sports"),
        quota_reserve: int = 10,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key.strip():
            raise ValueError("API_SPORTS_KEY is required")
        if quota_reserve < 0:
            raise ValueError("quota_reserve must be non-negative")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._cache_dir = Path(cache_dir)
        self._quota_reserve = quota_reserve
        self._timeout = timeout
        self._max_retries = max_retries
        self._quota_state = QuotaState(None, None, None, None)

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    def set_quota_for_test(self, quota_state: QuotaState) -> None:
        self._quota_state = quota_state

    def fetch_schedule(
        self, sport: Sport, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        events: list[ProviderEvent] = []
        for item in dates:
            payload = self._get_json(
                sport,
                _schedule_path(sport),
                {"date": item.isoformat()},
            )
            events.extend(_parse_schedule_payload(sport, payload))
        return tuple(events)

    def fetch_event_markets(
        self, sport: Sport, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        payload = self._get_json(
            sport,
            "/odds",
            _odds_params(sport, provider_event_id),
        )
        return _parse_market_payload(sport, provider_event_id, payload)

    def _get_json(
        self,
        sport: Sport,
        path: str,
        params: Mapping[str, object],
    ) -> dict[str, Any]:
        cache_key = _cache_key(self._base_url(sport), path, params)
        cached = self._load_cache(cache_key)
        if cached is not None:
            self._quota_state = cached.quota
            return cached.payload
        self._ensure_quota_available()

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    f"{self._base_url(sport)}{path}",
                    headers={"x-apisports-key": self._api_key},
                    params=dict(sorted(params.items())),
                    timeout=self._timeout,
                )
            except requests.ConnectionError as error:
                last_error = error
                if attempt == self._max_retries:
                    raise APISportsError("API-Sports request failed") from error
                self._sleep_before_retry(attempt)
                continue

            if response.status_code in _RETRY_STATUSES:
                last_error = APISportsError(
                    f"API-Sports request failed with status {response.status_code}"
                )
                if attempt == self._max_retries:
                    raise APISportsError("API-Sports request failed") from last_error
                self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                raise APISportsError(
                    f"API-Sports request failed with status {response.status_code}"
                )

            payload = _json_mapping(response)
            _validate_top_level_payload(payload)
            self._quota_state = quota_from_headers(response.headers)
            self._write_cache(cache_key, payload, self._quota_state)
            return payload

        raise APISportsError("API-Sports request failed") from last_error

    def _base_url(self, sport: Sport) -> str:
        if sport == "football":
            return FOOTBALL_BASE_URL
        if sport == "hockey":
            return HOCKEY_BASE_URL
        raise APISportsError("unsupported sport")

    def _ensure_quota_available(self) -> None:
        if _is_quota_exhausted(self._quota_state, self._quota_reserve):
            raise QuotaExhausted("API-Sports quota reserve reached")

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(0.05 * (attempt + 1))

    def _load_cache(self, cache_key: str) -> _CachePayload | None:
        path = self._cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        raw = json.loads(path.read_text())
        return _CachePayload(
            quota=QuotaState(
                daily_limit=raw["quota"]["daily_limit"],
                daily_remaining=raw["quota"]["daily_remaining"],
                minute_limit=raw["quota"]["minute_limit"],
                minute_remaining=raw["quota"]["minute_remaining"],
            ),
            payload=raw["payload"],
        )

    def _write_cache(
        self,
        cache_key: str,
        payload: dict[str, Any],
        quota_state: QuotaState,
    ) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        body = {
            "quota": {
                "daily_limit": quota_state.daily_limit,
                "daily_remaining": quota_state.daily_remaining,
                "minute_limit": quota_state.minute_limit,
                "minute_remaining": quota_state.minute_remaining,
            },
            "payload": payload,
        }
        (self._cache_dir / f"{cache_key}.json").write_text(
            json.dumps(body, sort_keys=True)
        )


def quota_from_headers(headers: Mapping[str, str]) -> QuotaState:
    return QuotaState(
        daily_limit=_optional_int(headers.get("x-ratelimit-requests-limit")),
        daily_remaining=_optional_int(headers.get("x-ratelimit-requests-remaining")),
        minute_limit=_optional_int(headers.get("x-ratelimit-limit")),
        minute_remaining=_optional_int(headers.get("x-ratelimit-remaining")),
    )


def _schedule_path(sport: Sport) -> str:
    if sport == "football":
        return "/fixtures"
    if sport == "hockey":
        return "/games"
    raise APISportsError("unsupported sport")


def _odds_params(sport: Sport, provider_event_id: str) -> dict[str, str]:
    if sport == "football":
        return {"fixture": provider_event_id}
    if sport == "hockey":
        return {"game": provider_event_id}
    raise APISportsError("unsupported sport")


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise APISportsError("invalid integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise APISportsError("invalid integer value")


def _cache_key(base_url: str, path: str, params: Mapping[str, object]) -> str:
    parsed = urlsplit(base_url)
    canonical = {
        "host": parsed.netloc,
        "path": path,
        "params": [(key, str(value)) for key, value in sorted(params.items())],
    }
    return hashlib.sha256(
        json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _json_mapping(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise APISportsError("API-Sports returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise APISportsError("API-Sports payload must be an object")
    return payload


def _validate_top_level_payload(payload: Mapping[str, Any]) -> None:
    errors = payload.get("errors")
    if errors not in ([], None):
        raise APISportsError("API-Sports returned provider errors")
    paging = payload.get("paging")
    if paging is not None:
        if not isinstance(paging, Mapping):
            raise APISportsError("API-Sports paging must be an object")
        for field in ("current", "total"):
            value = paging.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise APISportsError("API-Sports paging is invalid")
    response = payload.get("response")
    if not isinstance(response, list):
        raise APISportsError("API-Sports response must be a list")


def _parse_schedule_payload(
    sport: Sport, payload: Mapping[str, Any]
) -> tuple[ProviderEvent, ...]:
    fetched_at = _payload_fetched_at(payload)
    events: list[ProviderEvent] = []
    for item in payload["response"]:
        if not isinstance(item, Mapping):
            raise APISportsError("API-Sports event must be an object")
        provider_event_id, starts_at, league, home, away = _event_core_fields(
            item, sport=sport
        )
        events.append(
            ProviderEvent(
                provider="api-sports",
                provider_event_id=provider_event_id,
                sport=sport,
                league=league,
                starts_at=starts_at,
                home_team=home,
                away_team=away,
                fetched_at=fetched_at,
                payload_hash=_payload_hash(item),
            )
        )
    return tuple(events)


def _parse_market_payload(
    sport: Sport, provider_event_id: str, payload: Mapping[str, Any]
) -> tuple[ProviderMarket, ...]:
    fetched_at = _payload_fetched_at(payload)
    markets: list[ProviderMarket] = []
    for item in payload["response"]:
        if not isinstance(item, Mapping):
            raise APISportsError("API-Sports odds event must be an object")
        item_event_id, _, _, _, _ = _event_core_fields(item, sport=sport)
        if item_event_id != provider_event_id:
            raise APISportsError("API-Sports returned mismatched event identifier")
        bookmakers = item.get("bookmakers")
        if not isinstance(bookmakers, list):
            raise APISportsError("API-Sports bookmakers must be a list")
        for bookmaker in bookmakers:
            markets.extend(
                _parse_bookmaker_markets(
                    sport=sport,
                    provider_event_id=provider_event_id,
                    fetched_at=fetched_at,
                    bookmaker=bookmaker,
                )
            )
    return tuple(markets)


def _parse_bookmaker_markets(
    *,
    sport: Sport,
    provider_event_id: str,
    fetched_at: datetime,
    bookmaker: object,
) -> tuple[ProviderMarket, ...]:
    if not isinstance(bookmaker, Mapping):
        raise APISportsError("API-Sports bookmaker must be an object")
    bookmaker_id = _identifier(bookmaker.get("id"), "bookmaker id")
    bets = bookmaker.get("bets")
    if not isinstance(bets, list):
        raise APISportsError("API-Sports bets must be a list")
    provider_markets: list[ProviderMarket] = []
    for bet in bets:
        if not isinstance(bet, Mapping):
            raise APISportsError("API-Sports bet must be an object")
        market_name = _text(bet.get("name"), "market name")
        values = bet.get("values")
        if not isinstance(values, list):
            raise APISportsError("API-Sports market values must be a list")
        prices = {item["value"]: item["odd"] for item in _price_entries(values)}
        provider_markets.append(
            ProviderMarket(
                provider="api-sports",
                provider_event_id=provider_event_id,
                bookmaker_id=bookmaker_id,
                market_name=market_name,
                updated_at=_bookmaker_updated_at(bookmaker),
                fetched_at=fetched_at,
                payload_hash=_payload_hash(
                    {
                        "sport": sport,
                        "bookmaker": bookmaker_id,
                        "market_name": market_name,
                        "values": values,
                    }
                ),
                home_price=_optional_price(prices.get("Home")),
                draw_price=_optional_price(prices.get("Draw")),
                away_price=_optional_price(prices.get("Away")),
            )
        )
    return tuple(provider_markets)


def _payload_fetched_at(payload: Mapping[str, Any]) -> datetime:
    return _parse_datetime(payload.get("timestamp"), field_name="timestamp")


def _event_core_fields(
    item: Mapping[str, Any],
    *,
    sport: Sport,
) -> tuple[str, datetime, str, str, str]:
    if sport == "football":
        event_label = "fixture"
    elif sport == "hockey":
        event_label = "game"
    else:
        raise APISportsError("unsupported sport")
    event_data = item.get(event_label)
    if not isinstance(event_data, Mapping):
        raise APISportsError(f"API-Sports {event_label} must be an object")
    provider_event_id = _identifier(event_data.get("id"), f"{event_label} id")
    starts_at = _parse_datetime(
        event_data.get("date"), field_name=f"{event_label} date"
    )
    league_obj = item.get("league")
    if not isinstance(league_obj, Mapping):
        raise APISportsError("API-Sports league must be an object")
    league = _text(league_obj.get("name"), "league name")
    teams = item.get("teams")
    if not isinstance(teams, Mapping):
        raise APISportsError("API-Sports teams must be an object")
    home_obj = teams.get("home")
    away_obj = teams.get("away")
    if not isinstance(home_obj, Mapping) or not isinstance(away_obj, Mapping):
        raise APISportsError("API-Sports teams must include home and away")
    home = _text(home_obj.get("name"), "home team")
    away = _text(away_obj.get("name"), "away team")
    return provider_event_id, starts_at, league, home, away


def _bookmaker_updated_at(bookmaker: Mapping[str, Any]) -> datetime:
    return _parse_datetime(bookmaker.get("update"), field_name="bookmaker update")


def _identifier(value: object, field_name: str) -> str:
    if isinstance(value, bool):
        raise APISportsError(f"API-Sports {field_name} is invalid")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise APISportsError(f"API-Sports {field_name} is invalid")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise APISportsError(f"API-Sports {field_name} is invalid")
    return value.strip()


def _parse_datetime(value: object, *, field_name: str) -> datetime:
    if isinstance(value, bool):
        raise APISportsError(f"API-Sports {field_name} is invalid")
    if isinstance(value, (int, float)):
        if not isfinite(float(value)):
            raise APISportsError(f"API-Sports {field_name} is invalid")
        try:
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise APISportsError(f"API-Sports {field_name} is invalid") from error
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise APISportsError(f"API-Sports {field_name} is invalid") from error
    else:
        raise APISportsError(f"API-Sports {field_name} is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise APISportsError(f"API-Sports {field_name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _payload_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _price_entries(values: list[object]) -> tuple[dict[str, str], ...]:
    entries: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise APISportsError("API-Sports price entry must be an object")
        name = _text(item.get("value"), "price value")
        odd = _text(item.get("odd"), "price odd")
        entries.append({"value": name, "odd": odd})
    return tuple(entries)


def _optional_price(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise APISportsError("API-Sports price is invalid")
    if isinstance(value, str):
        try:
            price = float(value)
        except ValueError as error:
            raise APISportsError("API-Sports price is invalid") from error
    elif isinstance(value, (int, float)):
        price = float(value)
    else:
        raise APISportsError("API-Sports price is invalid")
    if not isfinite(price) or price <= 0:
        raise APISportsError("API-Sports price is invalid")
    return price


def _is_quota_exhausted(quota_state: QuotaState, quota_reserve: int) -> bool:
    minute_remaining = quota_state.minute_remaining
    daily_remaining = quota_state.daily_remaining
    return (
        minute_remaining is not None
        and minute_remaining <= quota_reserve
        or daily_remaining is not None
        and daily_remaining <= quota_reserve
    )
