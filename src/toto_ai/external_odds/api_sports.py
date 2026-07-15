from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from toto_ai.external_odds.consensus import (
    FOOTBALL_THREE_WAY,
    HOCKEY_REGULATION_THREE_WAY,
)
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
        self._requests_made = 0
        self._cache_hits = 0
        self._logical_fetches = 0

    @property
    def quota_state(self) -> QuotaState:
        return self._quota_state

    @property
    def requests_made(self) -> int:
        return self._requests_made

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def logical_fetches(self) -> int:
        return self._logical_fetches

    def set_quota_for_test(self, quota_state: QuotaState) -> None:
        self._quota_state = quota_state

    def fetch_schedule(
        self, sport: Sport, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self._logical_fetches += 1
        events: list[ProviderEvent] = []
        for item in dates:
            payloads = self._get_json_pages(
                sport,
                _schedule_path(sport),
                {"date": item.isoformat()},
            )
            for payload in payloads:
                events.extend(_parse_schedule_payload(sport, payload))
        return _dedupe_provider_events(tuple(events))

    def fetch_event_markets(
        self, sport: Sport, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        self._logical_fetches += 1
        payloads = self._get_json_pages(
            sport,
            "/odds",
            _odds_params(sport, provider_event_id),
        )
        markets: list[ProviderMarket] = []
        for payload in payloads:
            markets.extend(_parse_market_payload(sport, provider_event_id, payload))
        return _dedupe_provider_markets(tuple(markets))

    def _get_json_pages(
        self,
        sport: Sport,
        path: str,
        params: Mapping[str, object],
    ) -> tuple[dict[str, Any], ...]:
        first = self._get_json(sport, path, params | {"page": 1})
        total = _paging_value(first, "total")
        if _paging_value(first, "current") != 1:
            raise APISportsError("API-Sports paging is inconsistent")
        pages = [first]
        for page in range(2, total + 1):
            payload = self._get_json(sport, path, params | {"page": page})
            if _paging_value(payload, "current") != page:
                raise APISportsError("API-Sports paging is inconsistent")
            if _paging_value(payload, "total") != total:
                raise APISportsError("API-Sports paging is inconsistent")
            pages.append(payload)
        return tuple(pages)

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
            self._cache_hits += 1
            return cached.payload
        self._ensure_quota_available()

        for attempt in range(self._max_retries + 1):
            connection_failed = False
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{self._base_url(sport)}{path}",
                    headers={"x-apisports-key": self._api_key},
                    params=dict(sorted(params.items())),
                    timeout=self._timeout,
                )
            except requests.ConnectionError:
                connection_failed = True

            if connection_failed:
                if attempt == self._max_retries:
                    raise APISportsError("API-Sports transport connection failed")
                self._sleep_before_retry(attempt)
                continue

            self._quota_state = quota_from_headers(response.headers)
            if response.status_code in _RETRY_STATUSES:
                if attempt == self._max_retries:
                    raise APISportsError(
                        f"API-Sports request failed with status {response.status_code}"
                    )
                self._ensure_quota_available()
                self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                raise APISportsError(
                    f"API-Sports request failed with status {response.status_code}"
                )

            payload = _json_mapping(response)
            _validate_top_level_payload(payload)
            self._write_cache(cache_key, payload, self._quota_state)
            return payload

        raise APISportsError("API-Sports request failed")

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
        try:
            if not path.exists():
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {"quota", "payload"}:
                raise ValueError("invalid cache envelope")
            quota = raw["quota"]
            payload = raw["payload"]
            quota_fields = {
                "daily_limit",
                "daily_remaining",
                "minute_limit",
                "minute_remaining",
            }
            if not isinstance(quota, dict) or set(quota) != quota_fields:
                raise ValueError("invalid cache quota")
            if not isinstance(payload, dict):
                raise ValueError("invalid cache payload")
            _validate_top_level_payload(payload)
            quota_state = QuotaState(
                daily_limit=quota["daily_limit"],
                daily_remaining=quota["daily_remaining"],
                minute_limit=quota["minute_limit"],
                minute_remaining=quota["minute_remaining"],
            )
            return _CachePayload(quota=quota_state, payload=payload)
        except (APISportsError, OSError, ValueError, TypeError):
            pass
        raise APISportsError("API-Sports cache is invalid")

    def _write_cache(
        self,
        cache_key: str,
        payload: dict[str, Any],
        quota_state: QuotaState,
    ) -> None:
        body = {
            "quota": {
                "daily_limit": quota_state.daily_limit,
                "daily_remaining": quota_state.daily_remaining,
                "minute_limit": quota_state.minute_limit,
                "minute_remaining": quota_state.minute_remaining,
            },
            "payload": payload,
        }
        final_path = self._cache_dir / f"{cache_key}.json"
        temporary_path: Path | None = None
        error_message: str | None = None
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=self._cache_dir,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
            ) as output:
                temporary_path = Path(output.name)
                output.write(json.dumps(body, sort_keys=True))
            temporary_path.replace(final_path)
        except (OSError, ValueError, TypeError):
            error_message = "API-Sports cache write failed"
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    error_message = "API-Sports cache cleanup failed"
        if error_message is not None:
            raise APISportsError(error_message)


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


def _paging_value(payload: Mapping[str, Any], field: str) -> int:
    paging = payload.get("paging")
    if not isinstance(paging, Mapping):
        raise APISportsError("API-Sports paging must be an object")
    value = paging.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise APISportsError("API-Sports paging is invalid")
    return value


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
        item_updated_at = _item_updated_at(item)
        bookmakers = item.get("bookmakers")
        if not isinstance(bookmakers, list):
            raise APISportsError("API-Sports bookmakers must be a list")
        for bookmaker in bookmakers:
            markets.extend(
                _parse_bookmaker_markets(
                    sport=sport,
                    provider_event_id=provider_event_id,
                    fetched_at=fetched_at,
                    default_updated_at=item_updated_at,
                    bookmaker=bookmaker,
                )
            )
    return tuple(markets)


def _parse_bookmaker_markets(
    *,
    sport: Sport,
    provider_event_id: str,
    fetched_at: datetime,
    default_updated_at: datetime | None,
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
        price_entries = _price_entries(values)
        if _requires_exact_outcome_validation(sport, market_name):
            prices = _outcome_prices(price_entries)
        else:
            prices = {item["value"]: item["odd"] for item in price_entries}
        provider_markets.append(
            ProviderMarket(
                provider="api-sports",
                provider_event_id=provider_event_id,
                bookmaker_id=bookmaker_id,
                market_name=market_name,
                updated_at=_bookmaker_updated_at(
                    bookmaker,
                    default_updated_at=default_updated_at,
                ),
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


def _item_updated_at(item: Mapping[str, Any]) -> datetime | None:
    if "update" not in item:
        return None
    return _parse_datetime(item.get("update"), field_name="item update")


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


def _bookmaker_updated_at(
    bookmaker: Mapping[str, Any],
    *,
    default_updated_at: datetime | None,
) -> datetime:
    if "update" not in bookmaker:
        if default_updated_at is None:
            raise APISportsError("API-Sports bookmaker update is invalid")
        return default_updated_at
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


def _requires_exact_outcome_validation(sport: Sport, market_name: str) -> bool:
    normalized = unicodedata.normalize("NFKC", market_name).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    if sport == "football":
        return normalized in FOOTBALL_THREE_WAY
    if sport == "hockey":
        return normalized in HOCKEY_REGULATION_THREE_WAY
    return False


def _outcome_prices(values: tuple[dict[str, str], ...]) -> dict[str, str]:
    allowed = {"Home", "Draw", "Away"}
    prices: dict[str, str] = {}
    for item in values:
        label = item["value"]
        if label not in allowed:
            raise APISportsError("API-Sports market has unknown outcome")
        if label in prices:
            raise APISportsError("API-Sports market has duplicate outcome")
        prices[label] = item["odd"]
    if set(prices) != allowed:
        missing = ", ".join(sorted(allowed - set(prices)))
        raise APISportsError(f"API-Sports market is missing outcome {missing}")
    return prices


def _dedupe_provider_events(
    events: tuple[ProviderEvent, ...],
) -> tuple[ProviderEvent, ...]:
    by_id: dict[str, ProviderEvent] = {}
    ordered: list[ProviderEvent] = []
    for event in events:
        existing = by_id.get(event.provider_event_id)
        if existing is None:
            by_id[event.provider_event_id] = event
            ordered.append(event)
            continue
        if existing != event:
            raise APISportsError("API-Sports duplicate provider event identifier")
    return tuple(ordered)


def _dedupe_provider_markets(
    markets: tuple[ProviderMarket, ...],
) -> tuple[ProviderMarket, ...]:
    seen: set[ProviderMarket] = set()
    ordered: list[ProviderMarket] = []
    for market in markets:
        if market in seen:
            continue
        seen.add(market)
        ordered.append(market)
    return tuple(ordered)


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
