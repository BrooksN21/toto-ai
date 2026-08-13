from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

import requests

from toto_ai.external_odds.api_sports import QuotaExhausted, SafetyStopReached
from toto_ai.external_odds.domain import (
    ProviderEvent,
    ProviderMarket,
    QuotaState,
    Sport,
)

BASE_URL = "https://api.the-odds-api.com"
_RETRY_STATUSES = frozenset((408, 429, 500, 502, 503, 504))
_CACHE_SCHEMA_VERSION = 1
_SPORT_GROUPS = {
    "football": "soccer",
    "hockey": "ice hockey",
}


class TheOddsAPIError(RuntimeError):
    """Sanitized The Odds API provider failure."""


class TheOddsAPIQuotaExhausted(QuotaExhausted, TheOddsAPIError):
    """Raised before an optional credit-bearing call crosses the reserve."""


@dataclass(frozen=True)
class CreditState:
    remaining: int | None
    used: int | None
    last_cost: int | None

    @property
    def limit(self) -> int | None:
        if self.remaining is None or self.used is None:
            return None
        return self.remaining + self.used


@dataclass(frozen=True)
class RequestEvidence:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    request_fingerprint: str
    response_hash: str
    fetched_at: datetime
    credit_remaining: int | None
    credit_used: int | None
    credit_cost: int | None
    cache_hit: bool


@dataclass(frozen=True)
class _SportDefinition:
    key: str
    group: str
    title: str


@dataclass(frozen=True)
class _Payload:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    body: object
    fetched_at: datetime
    payload_hash: str
    request_fingerprint: str
    credit_state: CreditState


class TheOddsAPIClient:
    provider_name = "the-odds-api"

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache_dir: Path = Path("data/external-cache/the-odds-api"),
        quota_reserve: int = 50,
        timeout: float = 30.0,
        max_retries: int = 2,
        stop_at: datetime | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("THE_ODDS_API_KEY is required")
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
        self._credit_state = CreditState(None, None, None)
        self._requests_made = 0
        self._cache_hits = 0
        self._credits_spent = 0
        self._catalog: tuple[_SportDefinition, ...] | None = None
        self._events_by_sport: dict[Sport, tuple[ProviderEvent, ...]] = {}
        self._events_by_sport_key: dict[str, dict[str, ProviderEvent]] = {}
        self._event_sport_keys: dict[str, str] = {}
        self._markets_by_sport_key: dict[str, tuple[ProviderMarket, ...]] = {}
        self._request_evidence: list[RequestEvidence] = []
        self.bind_safety_boundary(stop_at=stop_at, now=now)

    @property
    def quota_state(self) -> QuotaState:
        return QuotaState(
            daily_limit=self._credit_state.limit,
            daily_remaining=self._credit_state.remaining,
            minute_limit=None,
            minute_remaining=None,
        )

    @property
    def credit_state(self) -> CreditState:
        return self._credit_state

    @property
    def requests_made(self) -> int:
        return self._requests_made

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def credits_spent(self) -> int:
        return self._credits_spent

    @property
    def request_evidence(self) -> tuple[RequestEvidence, ...]:
        return tuple(self._request_evidence)

    def refresh_credit_state(self) -> CreditState:
        """Refresh credit headers through the documented zero-cost catalog call."""
        payload = self._get_json(
            "/v4/sports",
            {},
            paid=False,
            cache_ttl=None,
        )
        self._catalog = _parse_sports(payload.body)
        return self._credit_state

    def bind_safety_boundary(
        self,
        *,
        stop_at: datetime | None,
        now: Callable[[], datetime] | None,
    ) -> None:
        if stop_at is not None:
            _require_utc_datetime("stop_at", stop_at)
        if now is not None and not callable(now):
            raise ValueError("now must be callable")
        self._stop_at = stop_at
        self._now = now or (lambda: datetime.now(timezone.utc))

    def fetch_schedule(
        self,
        sport: Sport,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        if sport not in _SPORT_GROUPS:
            raise TheOddsAPIError("unsupported sport")
        if not dates:
            return ()
        self._check_safety_stop()
        catalog = self._fetch_catalog()
        wanted_group = _SPORT_GROUPS[sport]
        sport_keys = tuple(
            definition
            for definition in catalog
            if definition.group.casefold() == wanted_group
        )
        requested_dates = frozenset(dates)
        events: list[ProviderEvent] = []
        for definition in sport_keys:
            self._check_safety_stop()
            payload = self._get_json(
                f"/v4/sports/{definition.key}/events",
                {
                    "dateFormat": "iso",
                    "commenceTimeFrom": _day_start(min(dates)),
                    "commenceTimeTo": _day_end(max(dates)),
                },
                paid=False,
                cache_ttl=timedelta(minutes=10),
            )
            parsed = _parse_events(payload, sport=sport)
            for event in parsed:
                if event.starts_at.date() not in requested_dates:
                    continue
                self._event_sport_keys[event.provider_event_id] = definition.key
                self._events_by_sport_key.setdefault(definition.key, {})[
                    event.provider_event_id
                ] = event
                events.append(event)
        result = _dedupe_events(tuple(events))
        self._events_by_sport[sport] = _dedupe_events(
            self._events_by_sport.get(sport, ()) + result
        )
        return result

    def fetch_event_markets(
        self,
        sport: Sport,
        provider_event_id: str,
    ) -> tuple[ProviderMarket, ...]:
        if sport not in _SPORT_GROUPS:
            raise TheOddsAPIError("unsupported sport")
        sport_key = self._event_sport_keys.get(provider_event_id)
        if sport_key is None:
            raise TheOddsAPIError("provider event is not present in discovery data")
        if sport_key not in self._markets_by_sport_key:
            self._ensure_paid_quota_available()
            discovered = tuple(self._events_by_sport_key.get(sport_key, {}).values())
            if not discovered:
                raise TheOddsAPIError("sport key has no discovered target events")
            payload = self._get_json(
                f"/v4/sports/{sport_key}/odds",
                {
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                    "commenceTimeFrom": _iso_z(
                        min(event.starts_at for event in discovered)
                        - timedelta(hours=3)
                    ),
                    "commenceTimeTo": _iso_z(
                        max(event.starts_at for event in discovered)
                        + timedelta(hours=3)
                    ),
                },
                paid=True,
                cache_ttl=None,
            )
            self._markets_by_sport_key[sport_key] = _parse_markets(
                payload,
                sport=sport,
            )
        return tuple(
            market
            for market in self._markets_by_sport_key[sport_key]
            if market.provider_event_id == provider_event_id
        )

    def _fetch_catalog(self) -> tuple[_SportDefinition, ...]:
        if self._catalog is None:
            payload = self._get_json(
                "/v4/sports",
                {},
                paid=False,
                cache_ttl=timedelta(hours=1),
            )
            self._catalog = _parse_sports(payload.body)
        return self._catalog

    def _get_json(
        self,
        endpoint: str,
        params: Mapping[str, object],
        *,
        paid: bool,
        cache_ttl: timedelta | None,
    ) -> _Payload:
        self._check_safety_stop()
        safe_params = tuple((key, str(value)) for key, value in sorted(params.items()))
        fingerprint = _request_fingerprint(endpoint, safe_params)
        if cache_ttl is not None:
            cached = self._load_cache(fingerprint, cache_ttl=cache_ttl)
            if cached is not None:
                self._cache_hits += 1
                self._record_request_evidence(cached, cache_hit=True)
                return cached
        if paid:
            self._ensure_paid_quota_available()

        for attempt in range(self._max_retries + 1):
            self._check_safety_stop()
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{BASE_URL}{endpoint}",
                    params={"apiKey": self._api_key, **dict(safe_params)},
                    timeout=self._timeout,
                )
            except requests.RequestException:
                if attempt == self._max_retries:
                    raise TheOddsAPIError(
                        "The Odds API transport connection failed"
                    ) from None
                self._sleep_before_retry(attempt)
                continue

            self._credit_state = credit_state_from_headers(response.headers)
            if self._credit_state.last_cost is not None:
                self._credits_spent += self._credit_state.last_cost
            self._check_safety_stop()
            if response.status_code in _RETRY_STATUSES:
                if attempt == self._max_retries:
                    raise TheOddsAPIError(
                        "The Odds API request failed with status "
                        f"{response.status_code}"
                    )
                if paid:
                    self._ensure_paid_quota_available()
                self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                raise TheOddsAPIError(
                    "The Odds API request failed with status "
                    f"{response.status_code}"
                )
            try:
                body = response.json()
            except ValueError:
                raise TheOddsAPIError("The Odds API returned invalid JSON") from None
            if not isinstance(body, (list, dict)):
                raise TheOddsAPIError("The Odds API payload has invalid shape")
            fetched_at = self._now()
            _require_utc_datetime("now", fetched_at)
            payload = _Payload(
                endpoint=endpoint,
                params=safe_params,
                body=body,
                fetched_at=fetched_at,
                payload_hash=_payload_hash(body),
                request_fingerprint=fingerprint,
                credit_state=self._credit_state,
            )
            if cache_ttl is not None:
                self._write_cache(payload)
            self._write_raw_capture(payload)
            self._record_request_evidence(payload, cache_hit=False)
            return payload
        raise TheOddsAPIError("The Odds API request failed")

    def _ensure_paid_quota_available(self) -> None:
        if self._credit_state.remaining is None:
            self._get_json(
                "/v4/sports",
                {},
                paid=False,
                cache_ttl=None,
            )
        remaining = self._credit_state.remaining
        if remaining is not None and remaining <= self._quota_reserve:
            raise TheOddsAPIQuotaExhausted(
                "The Odds API quota reserve reached"
            )

    def _check_safety_stop(self) -> None:
        if self._stop_at is None:
            return
        current = self._now()
        _require_utc_datetime("now", current)
        if current >= self._stop_at:
            raise SafetyStopReached("The Odds API safety stop reached")

    @staticmethod
    def _sleep_before_retry(attempt: int) -> None:
        time.sleep(0.05 * (attempt + 1))

    def _load_cache(
        self,
        fingerprint: str,
        *,
        cache_ttl: timedelta,
    ) -> _Payload | None:
        path = self._cache_dir / f"{fingerprint}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {
                "cache_schema",
                "credit_state",
                "endpoint",
                "fetched_at",
                "params",
                "payload",
                "payload_hash",
                "request_fingerprint",
            }:
                raise ValueError
            fetched_at = _parse_datetime(raw["fetched_at"], "cache fetched_at")
            current = self._now()
            _require_utc_datetime("now", current)
            if current - fetched_at > cache_ttl or fetched_at > current:
                return None
            params = raw["params"]
            credit = raw["credit_state"]
            if (
                raw["cache_schema"] != _CACHE_SCHEMA_VERSION
                or raw["request_fingerprint"] != fingerprint
                or not isinstance(params, list)
                or not isinstance(credit, dict)
            ):
                raise ValueError
            body = raw["payload"]
            if _payload_hash(body) != raw["payload_hash"]:
                raise ValueError
            return _Payload(
                endpoint=_text(raw["endpoint"], "cache endpoint"),
                params=tuple((str(key), str(value)) for key, value in params),
                body=body,
                fetched_at=fetched_at,
                payload_hash=raw["payload_hash"],
                request_fingerprint=fingerprint,
                credit_state=CreditState(
                    remaining=_optional_int(credit.get("remaining")),
                    used=_optional_int(credit.get("used")),
                    last_cost=_optional_int(credit.get("last_cost")),
                ),
            )
        except (OSError, TypeError, ValueError):
            raise TheOddsAPIError("The Odds API cache is invalid") from None

    def _write_cache(self, payload: _Payload) -> None:
        body = {
            "cache_schema": _CACHE_SCHEMA_VERSION,
            "credit_state": {
                "remaining": payload.credit_state.remaining,
                "used": payload.credit_state.used,
                "last_cost": payload.credit_state.last_cost,
            },
            "endpoint": payload.endpoint,
            "fetched_at": payload.fetched_at.isoformat(),
            "params": payload.params,
            "payload": payload.body,
            "payload_hash": payload.payload_hash,
            "request_fingerprint": payload.request_fingerprint,
        }
        final_path = self._cache_dir / f"{payload.request_fingerprint}.json"
        temporary_path: Path | None = None
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
                output.write(
                    json.dumps(
                        body,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            temporary_path.replace(final_path)
        except (OSError, TypeError, ValueError):
            raise TheOddsAPIError("The Odds API cache write failed") from None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _write_raw_capture(self, payload: _Payload) -> None:
        raw_dir = self._cache_dir / "raw"
        raw_identity = _payload_hash(
            {
                "request_fingerprint": payload.request_fingerprint,
                "payload_hash": payload.payload_hash,
                "fetched_at": payload.fetched_at.isoformat(),
            }
        )
        final_path = raw_dir / f"{raw_identity}.json"
        if final_path.exists():
            return
        body = {
            "credit_state": {
                "remaining": payload.credit_state.remaining,
                "used": payload.credit_state.used,
                "last_cost": payload.credit_state.last_cost,
            },
            "endpoint": payload.endpoint,
            "fetched_at": payload.fetched_at.isoformat(),
            "params": payload.params,
            "payload": payload.body,
            "payload_hash": payload.payload_hash,
            "request_fingerprint": payload.request_fingerprint,
        }
        temporary_path: Path | None = None
        try:
            raw_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=raw_dir,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
            ) as output:
                temporary_path = Path(output.name)
                output.write(
                    json.dumps(
                        body,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            temporary_path.replace(final_path)
        except (OSError, TypeError, ValueError):
            raise TheOddsAPIError("The Odds API raw capture write failed") from None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _record_request_evidence(
        self,
        payload: _Payload,
        *,
        cache_hit: bool,
    ) -> None:
        self._request_evidence.append(
            RequestEvidence(
                endpoint=payload.endpoint,
                params=payload.params,
                request_fingerprint=payload.request_fingerprint,
                response_hash=payload.payload_hash,
                fetched_at=payload.fetched_at,
                credit_remaining=payload.credit_state.remaining,
                credit_used=payload.credit_state.used,
                credit_cost=payload.credit_state.last_cost,
                cache_hit=cache_hit,
            )
        )


def credit_state_from_headers(headers: Mapping[str, str]) -> CreditState:
    return CreditState(
        remaining=_optional_int(headers.get("x-requests-remaining")),
        used=_optional_int(headers.get("x-requests-used")),
        last_cost=_optional_int(headers.get("x-requests-last")),
    )


def _parse_sports(body: object) -> tuple[_SportDefinition, ...]:
    rows = _list(body, "sports")
    parsed = []
    for item in rows:
        row = _mapping(item, "sport")
        active = row.get("active")
        if not isinstance(active, bool):
            raise TheOddsAPIError("The Odds API sport active flag is invalid")
        if not active:
            continue
        definition = _SportDefinition(
            key=_text(row.get("key"), "sport key"),
            group=_text(row.get("group"), "sport group"),
            title=_text(row.get("title"), "sport title"),
        )
        if definition.group.casefold() in frozenset(_SPORT_GROUPS.values()):
            parsed.append(definition)
    return tuple(sorted(parsed, key=lambda item: item.key))


def _parse_events(payload: _Payload, *, sport: Sport) -> tuple[ProviderEvent, ...]:
    events = []
    for item in _list(payload.body, "events"):
        row = _mapping(item, "event")
        event_id = _text(row.get("id"), "event id")
        events.append(
            ProviderEvent(
                provider="the-odds-api",
                provider_event_id=event_id,
                sport=sport,
                league=_text(row.get("sport_title"), "sport title"),
                starts_at=_parse_datetime(row.get("commence_time"), "commence time"),
                home_team=_text(row.get("home_team"), "home team"),
                away_team=_text(row.get("away_team"), "away team"),
                fetched_at=payload.fetched_at,
                payload_hash=_payload_hash(row),
                source_endpoint=payload.endpoint,
                request_fingerprint=payload.request_fingerprint,
            )
        )
    return tuple(events)


def _parse_markets(
    payload: _Payload,
    *,
    sport: Sport,
) -> tuple[ProviderMarket, ...]:
    markets: list[ProviderMarket] = []
    for item in _list(payload.body, "odds"):
        event = _mapping(item, "odds event")
        event_id = _text(event.get("id"), "event id")
        home = _text(event.get("home_team"), "home team")
        away = _text(event.get("away_team"), "away team")
        for raw_bookmaker in _list(event.get("bookmakers"), "bookmakers"):
            bookmaker = _mapping(raw_bookmaker, "bookmaker")
            bookmaker_id = _text(bookmaker.get("key"), "bookmaker key")
            for raw_market in _list(bookmaker.get("markets"), "markets"):
                market = _mapping(raw_market, "market")
                if _text(market.get("key"), "market key") != "h2h":
                    continue
                prices = _outcome_prices(
                    market.get("outcomes"),
                    home=home,
                    away=away,
                )
                has_draw = prices[1] is not None
                market_name = (
                    "1X2"
                    if sport == "football"
                    else "1X2 Regulation Time"
                    if has_draw
                    else "H2H Including Overtime"
                )
                updated_at = _parse_datetime(
                    market.get("last_update") or bookmaker.get("last_update"),
                    "market last update",
                )
                markets.append(
                    ProviderMarket(
                        provider="the-odds-api",
                        provider_event_id=event_id,
                        bookmaker_id=bookmaker_id,
                        market_name=market_name,
                        updated_at=updated_at,
                        fetched_at=payload.fetched_at,
                        payload_hash=_payload_hash(
                            {
                                "bookmaker": bookmaker_id,
                                "event_id": event_id,
                                "market": market,
                            }
                        ),
                        home_price=prices[0],
                        draw_price=prices[1],
                        away_price=prices[2],
                        source_endpoint=payload.endpoint,
                        request_fingerprint=payload.request_fingerprint,
                    )
                )
    return tuple(
        sorted(
            markets,
            key=lambda item: (
                item.provider_event_id,
                item.bookmaker_id,
                item.market_name,
            ),
        )
    )


def _outcome_prices(
    raw: object,
    *,
    home: str,
    away: str,
) -> tuple[float, float | None, float]:
    expected = {home.casefold(): "home", away.casefold(): "away", "draw": "draw"}
    values: dict[str, float] = {}
    for item in _list(raw, "outcomes"):
        row = _mapping(item, "outcome")
        name = _text(row.get("name"), "outcome name").casefold()
        label = expected.get(name)
        if label is None:
            raise TheOddsAPIError("The Odds API h2h has unknown outcome")
        if label in values:
            raise TheOddsAPIError("The Odds API h2h has duplicate outcome")
        values[label] = _decimal_price(row.get("price"))
    if "home" not in values or "away" not in values:
        raise TheOddsAPIError("The Odds API h2h is missing team outcome")
    return values["home"], values.get("draw"), values["away"]


def _request_fingerprint(
    endpoint: str,
    params: tuple[tuple[str, str], ...],
) -> str:
    return _payload_hash(
        {
            "provider": "the-odds-api",
            "endpoint": endpoint,
            "params": params,
        }
    )


def _payload_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _dedupe_events(events: tuple[ProviderEvent, ...]) -> tuple[ProviderEvent, ...]:
    by_id: dict[str, ProviderEvent] = {}
    for event in events:
        existing = by_id.get(event.provider_event_id)
        if existing is not None and existing != event:
            raise TheOddsAPIError("The Odds API event id is not unique")
        by_id[event.provider_event_id] = event
    return tuple(by_id[key] for key in sorted(by_id))


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TheOddsAPIError(f"The Odds API {name} must be an object")
    return value


def _list(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise TheOddsAPIError(f"The Odds API {name} must be a list")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TheOddsAPIError(f"The Odds API {name} must be non-empty")
    return value.strip()


def _parse_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TheOddsAPIError(f"The Odds API {name} must be an ISO datetime")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise TheOddsAPIError(
            f"The Odds API {name} must be an ISO datetime"
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise TheOddsAPIError(f"The Odds API {name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _decimal_price(value: object) -> float:
    if isinstance(value, bool):
        raise TheOddsAPIError("The Odds API decimal price is invalid")
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        raise TheOddsAPIError("The Odds API decimal price is invalid") from None
    if not isfinite(price) or price <= 1.0:
        raise TheOddsAPIError("The Odds API decimal price is invalid")
    return price


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise TheOddsAPIError("The Odds API quota header is invalid")
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise TheOddsAPIError("The Odds API quota header is invalid")


def _require_utc_datetime(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _day_start(value: date) -> str:
    return f"{value.isoformat()}T00:00:00Z"


def _day_end(value: date) -> str:
    return f"{value.isoformat()}T23:59:59Z"


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
