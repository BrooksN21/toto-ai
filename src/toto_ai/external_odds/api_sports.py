from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
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
_CACHE_SCHEMA_VERSION = 2
_DIAGNOSTIC_MESSAGE_LIMIT = 240
_SECRET_FIELD_PATTERN = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|x-apisports-key|api[_-]?key|token|secret|password)\b"
    r"[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?[^,\s;}&\"']+"
)
_SECRET_QUERY_PATTERN = re.compile(
    r"(?i)([?&](?:api[_-]?key|key|token|access[_-]?token|auth|authorization|"
    r"password|secret)=)[^&#\s]+"
)
_URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]*", re.IGNORECASE)
_PROVIDER_ERROR_CODE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
_DIAGNOSTIC_CATEGORIES = frozenset(
    {
        "success",
        "semantic_error",
        "http_retry",
        "http_failure",
        "transport_retry",
        "transport_failure",
        "invalid_json",
        "invalid_quota_headers",
    }
)


@dataclass(frozen=True)
class APISportsProviderError:
    code: str
    message: str


@dataclass(frozen=True)
class APISportsDiagnostic:
    category: str
    endpoint: str
    attempt: int
    http_status: int | None = None
    provider_errors: tuple[APISportsProviderError, ...] = ()
    quota_daily_limit: int | None = None
    quota_daily_remaining: int | None = None
    quota_minute_limit: int | None = None
    quota_minute_remaining: int | None = None
    quota_daily_reset: int | None = None
    quota_minute_reset: int | None = None

    def payload(self) -> dict[str, object]:
        return {
            "category": (
                self.category
                if self.category in _DIAGNOSTIC_CATEGORIES
                else "semantic_error"
            ),
            "endpoint": _safe_endpoint(self.endpoint),
            "attempt": (
                self.attempt
                if isinstance(self.attempt, int)
                and not isinstance(self.attempt, bool)
                and self.attempt >= 1
                else 1
            ),
            "http_status": _safe_http_status(self.http_status),
            "provider_errors": [
                {
                    "code": _normalize_provider_error_code(item.code)
                    or "provider_error",
                    "message": sanitize_api_sports_message(item.message),
                }
                for item in self.provider_errors[:10]
                if isinstance(item, APISportsProviderError)
            ],
            "quota_daily_limit": _safe_nonnegative_int(self.quota_daily_limit),
            "quota_daily_remaining": _safe_nonnegative_int(
                self.quota_daily_remaining
            ),
            "quota_minute_limit": _safe_nonnegative_int(self.quota_minute_limit),
            "quota_minute_remaining": _safe_nonnegative_int(
                self.quota_minute_remaining
            ),
            "quota_daily_reset": _safe_nonnegative_int(self.quota_daily_reset),
            "quota_minute_reset": _safe_nonnegative_int(self.quota_minute_reset),
        }

    def summary(self) -> str:
        payload = self.payload()
        fields = [
            str(payload["category"]),
            f"endpoint={payload['endpoint']}",
            f"attempt={payload['attempt']}",
        ]
        if payload["http_status"] is not None:
            fields.append(f"http={payload['http_status']}")
        for field in (
            "quota_daily_limit",
            "quota_daily_remaining",
            "quota_minute_limit",
            "quota_minute_remaining",
            "quota_daily_reset",
            "quota_minute_reset",
        ):
            if payload[field] is not None:
                fields.append(f"{field}={payload[field]}")
        provider_errors = payload["provider_errors"]
        if isinstance(provider_errors, list) and provider_errors:
            errors = ",".join(
                f"{item['code']}:{item['message']}" for item in provider_errors
            )
            fields.append(f"provider={errors}")
        return " ".join(fields)


class APISportsError(RuntimeError):
    """Sanitized API-Sports provider failure."""

    def __init__(
        self,
        message: str,
        *,
        diagnostic: APISportsDiagnostic | None = None,
    ) -> None:
        safe_message = sanitize_api_sports_message(message)
        super().__init__(safe_message)
        self.diagnostic = diagnostic

    def diagnostic_payload(self) -> dict[str, object] | None:
        return None if self.diagnostic is None else self.diagnostic.payload()


class QuotaExhausted(APISportsError):
    """Raised when the provider quota reserve has been reached."""


class SafetyStopReached(APISportsError):
    """Raised before API-Sports can make work continue past a UTC cutoff."""


class HistoricalCacheUnavailable(APISportsError):
    """Raised when a historical as-of cannot use a lawful cached response."""


class ProviderPlanUnavailable(APISportsError):
    """Raised when the configured API-Sports plan cannot access an endpoint."""


@dataclass(frozen=True)
class _CachePayload:
    quota: QuotaState
    payload: dict[str, Any]
    fetched_at: datetime


@dataclass(frozen=True)
class APISportsJSONPayload:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    payload: dict[str, Any]
    fetched_at: datetime

    @property
    def request_fingerprint(self) -> str:
        return _payload_hash(
            {
                "provider": "api-sports",
                "endpoint": self.endpoint,
                "params": self.params,
            }
        )

    @property
    def payload_sha256(self) -> str:
        return _payload_hash(self.payload)


class APISportsClient:
    provider_name = "api-sports"

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        cache_dir: Path = Path("data/external-cache/api-sports"),
        schedule_cache_dir: Path | None = None,
        schedule_cache_max_age_seconds: float = 3600.0,
        quota_reserve: int = 10,
        timeout: float = 30.0,
        max_retries: int = 2,
        stop_at: datetime | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("API_SPORTS_KEY is required")
        if quota_reserve < 0:
            raise ValueError("quota_reserve must be non-negative")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if (
            not isinstance(schedule_cache_max_age_seconds, (int, float))
            or isinstance(schedule_cache_max_age_seconds, bool)
            or not 0 < float(schedule_cache_max_age_seconds) < float("inf")
        ):
            raise ValueError(
                "schedule_cache_max_age_seconds must be finite and positive"
            )
        self._api_key = api_key
        self._session = session or requests.Session()
        self._cache_dir = Path(cache_dir)
        self._schedule_cache_dir = (
            None if schedule_cache_dir is None else Path(schedule_cache_dir)
        )
        self._schedule_cache_max_age_seconds = float(
            schedule_cache_max_age_seconds
        )
        self._quota_reserve = quota_reserve
        self._timeout = timeout
        self._max_retries = max_retries
        self._quota_state = QuotaState(None, None, None, None)
        self._requests_made = 0
        self._cache_hits = 0
        self._logical_fetches = 0
        self._request_diagnostics: list[APISportsDiagnostic] = []
        self.bind_safety_boundary(stop_at=stop_at, now=now)

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

    @property
    def request_diagnostics(self) -> tuple[APISportsDiagnostic, ...]:
        return tuple(self._request_diagnostics)

    @property
    def last_diagnostic(self) -> APISportsDiagnostic | None:
        if not self._request_diagnostics:
            return None
        return self._request_diagnostics[-1]

    def set_quota_for_test(self, quota_state: QuotaState) -> None:
        self._quota_state = quota_state

    def bind_safety_boundary(
        self,
        *,
        stop_at: datetime | None,
        now: Callable[[], datetime] | None,
    ) -> None:
        _validate_stop_at(stop_at)
        if now is not None and not callable(now):
            raise ValueError("now must be callable")
        self._stop_at = stop_at
        self._now = now or _utc_now

    def fetch_schedule(
        self, sport: Sport, dates: tuple[date, ...]
    ) -> tuple[ProviderEvent, ...]:
        self._logical_fetches += 1
        events: list[ProviderEvent] = []
        for item in dates:
            self._check_safety_stop()
            cached = self._get_json_single_page(
                sport,
                _schedule_path(sport),
                {"date": item.isoformat()},
                cache_dir=self._schedule_cache_dir,
                max_cache_age_seconds=(
                    self._schedule_cache_max_age_seconds
                    if self._schedule_cache_dir is not None
                    else None
                ),
            )
            events.extend(
                _parse_schedule_payload(
                    sport,
                    cached.payload,
                    fetched_at=cached.fetched_at,
                )
            )
        return _dedupe_provider_events(tuple(events))

    def fetch_event_markets(
        self, sport: Sport, provider_event_id: str
    ) -> tuple[ProviderMarket, ...]:
        self._logical_fetches += 1
        self._check_safety_stop()
        payloads = self._get_json_pages(
            sport,
            "/odds",
            _odds_params(sport, provider_event_id),
        )
        markets: list[ProviderMarket] = []
        for cached in payloads:
            markets.extend(
                _parse_market_payload(
                    sport,
                    provider_event_id,
                    cached.payload,
                    fetched_at=cached.fetched_at,
                )
            )
        return _dedupe_provider_markets(tuple(markets))

    def fetch_football_fixture_payload(
        self,
        fixture_id: str,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> APISportsJSONPayload:
        return self._fetch_football_stats_payload(
            "/fixtures",
            {"id": _identifier(fixture_id, "fixture id")},
            as_of=as_of,
            cache_only=cache_only,
        )

    def fetch_football_team_fixtures_payload(
        self,
        team_id: str,
        season: int,
        *,
        limit: int,
        as_of: datetime | None = None,
        cache_only: bool = False,
        historical_from: date | None = None,
        historical_to: date | None = None,
    ) -> APISportsJSONPayload:
        if not isinstance(season, int) or isinstance(season, bool) or season <= 0:
            raise ValueError("season must be a positive integer")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 10
        ):
            raise ValueError("limit must be in range 1 through 10")
        base_params: dict[str, object] = {
            "team": _identifier(team_id, "team id"),
            "season": season,
            "status": "FT-AET-PEN",
            "timezone": "UTC",
        }
        params = dict(base_params)
        compatible_cache_params: tuple[Mapping[str, object], ...] = ()
        if historical_from is None and historical_to is None:
            params["last"] = limit
        elif historical_from is not None and historical_to is not None:
            if historical_from > historical_to:
                raise ValueError("historical fixture date range is invalid")
            params["from"] = historical_from.isoformat()
            params["to"] = historical_to.isoformat()
            compatible_cache_params = (base_params | {"last": limit},)
        else:
            raise ValueError("historical fixture date range must be complete")
        return self._fetch_football_stats_payload(
            "/fixtures",
            params,
            as_of=as_of,
            cache_only=cache_only,
            compatible_cache_params=compatible_cache_params,
        )

    def fetch_football_standings_payload(
        self,
        league_id: str,
        season: int,
        *,
        as_of: datetime | None = None,
        cache_only: bool = False,
    ) -> APISportsJSONPayload:
        if not isinstance(season, int) or isinstance(season, bool) or season <= 0:
            raise ValueError("season must be a positive integer")
        return self._fetch_football_stats_payload(
            "/standings",
            {
                "league": _identifier(league_id, "league id"),
                "season": season,
            },
            as_of=as_of,
            cache_only=cache_only,
        )

    def _fetch_football_stats_payload(
        self,
        path: str,
        params: Mapping[str, object],
        *,
        as_of: datetime | None,
        cache_only: bool,
        compatible_cache_params: tuple[Mapping[str, object], ...] = (),
    ) -> APISportsJSONPayload:
        self._logical_fetches += 1
        if as_of is not None:
            _require_utc_datetime("as_of", as_of)
        selected_params = params
        if cache_only:
            cached = None
            for candidate_params in (params, *compatible_cache_params):
                cache_key = _cache_key(
                    FOOTBALL_BASE_URL,
                    path,
                    candidate_params,
                )
                candidate = self._load_cache(cache_key)
                if candidate is None:
                    continue
                if as_of is not None and candidate.fetched_at > as_of:
                    continue
                cached = candidate
                selected_params = candidate_params
                break
            if cached is None:
                raise HistoricalCacheUnavailable(
                    "historical API-Sports cache is unavailable"
                )
            self._cache_hits += 1
        else:
            cached = self._get_json_single_page("football", path, params)
        if as_of is not None and cached.fetched_at > as_of:
            raise HistoricalCacheUnavailable(
                "API-Sports cache was captured after historical as-of"
            )
        return APISportsJSONPayload(
            endpoint=path,
            params=tuple(
                (key, str(value))
                for key, value in sorted(selected_params.items())
            ),
            payload=cached.payload,
            fetched_at=cached.fetched_at,
        )

    def _get_json_single_page(
        self,
        sport: Sport,
        path: str,
        params: Mapping[str, object],
        *,
        cache_dir: Path | None = None,
        max_cache_age_seconds: float | None = None,
    ) -> _CachePayload:
        self._check_safety_stop()
        cached = self._get_json(
            sport,
            path,
            params,
            cache_dir=cache_dir,
            max_cache_age_seconds=max_cache_age_seconds,
        )
        if (
            _paging_value(cached.payload, "current") != 1
            or _paging_value(cached.payload, "total") != 1
        ):
            raise APISportsError("API-Sports paging is inconsistent")
        return cached

    def _get_json_pages(
        self,
        sport: Sport,
        path: str,
        params: Mapping[str, object],
    ) -> tuple[_CachePayload, ...]:
        self._check_safety_stop()
        first = self._get_json(sport, path, params | {"page": 1})
        total = _paging_value(first.payload, "total")
        if _paging_value(first.payload, "current") != 1:
            raise APISportsError("API-Sports paging is inconsistent")
        pages = [first]
        for page in range(2, total + 1):
            self._check_safety_stop()
            cached = self._get_json(sport, path, params | {"page": page})
            if _paging_value(cached.payload, "current") != page:
                raise APISportsError("API-Sports paging is inconsistent")
            if _paging_value(cached.payload, "total") != total:
                raise APISportsError("API-Sports paging is inconsistent")
            pages.append(cached)
        return tuple(pages)

    def _get_json(
        self,
        sport: Sport,
        path: str,
        params: Mapping[str, object],
        *,
        cache_dir: Path | None = None,
        max_cache_age_seconds: float | None = None,
    ) -> _CachePayload:
        self._check_safety_stop()
        cache_key = _cache_key(self._base_url(sport), path, params)
        selected_cache_dir = self._cache_dir if cache_dir is None else cache_dir
        cached = self._load_cache(
            cache_key,
            cache_dir=selected_cache_dir,
            max_age_seconds=max_cache_age_seconds,
        )
        if cached is not None:
            self._cache_hits += 1
            return cached
        self._ensure_quota_available()

        for attempt in range(self._max_retries + 1):
            self._check_safety_stop()
            connection_failed = False
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{self._base_url(sport)}{path}",
                    headers={"x-apisports-key": self._api_key},
                    params=dict(sorted(params.items())),
                    timeout=self._request_timeout(),
                )
            except requests.ConnectionError:
                connection_failed = True

            if connection_failed:
                diagnostic = APISportsDiagnostic(
                    category=(
                        "transport_failure"
                        if attempt == self._max_retries
                        else "transport_retry"
                    ),
                    endpoint=_safe_endpoint(path),
                    attempt=attempt + 1,
                )
                self._request_diagnostics.append(diagnostic)
                self._check_safety_stop()
                if attempt == self._max_retries:
                    raise APISportsError(
                        "API-Sports transport connection failed",
                        diagnostic=diagnostic,
                    )
                self._sleep_before_retry(attempt)
                continue

            try:
                self._quota_state = quota_from_headers(response.headers)
            except (APISportsError, ValueError):
                diagnostic = _response_diagnostic(
                    response,
                    endpoint=path,
                    attempt=attempt + 1,
                    category="invalid_quota_headers",
                    secrets=(self._api_key,),
                )
                self._request_diagnostics.append(diagnostic)
                raise APISportsError(
                    "API-Sports quota headers are invalid",
                    diagnostic=diagnostic,
                ) from None
            self._check_safety_stop()
            if response.status_code in _RETRY_STATUSES:
                diagnostic = _response_diagnostic(
                    response,
                    endpoint=path,
                    attempt=attempt + 1,
                    category=(
                        "http_failure"
                        if attempt == self._max_retries
                        else "http_retry"
                    ),
                    secrets=(self._api_key,),
                )
                self._request_diagnostics.append(diagnostic)
                if attempt == self._max_retries:
                    raise APISportsError(
                        "API-Sports request failed with status "
                        f"{response.status_code}",
                        diagnostic=diagnostic,
                    )
                self._ensure_quota_available(diagnostic=diagnostic)
                self._sleep_before_retry(attempt)
                continue
            if response.status_code >= 400:
                diagnostic = _response_diagnostic(
                    response,
                    endpoint=path,
                    attempt=attempt + 1,
                    category="http_failure",
                    secrets=(self._api_key,),
                )
                self._request_diagnostics.append(diagnostic)
                raise APISportsError(
                    "API-Sports request failed with status "
                    f"{response.status_code}",
                    diagnostic=diagnostic,
                )

            try:
                payload = _json_mapping(response)
            except APISportsError:
                diagnostic = _response_diagnostic(
                    response,
                    endpoint=path,
                    attempt=attempt + 1,
                    category="invalid_json",
                    inspect_payload=False,
                )
                self._request_diagnostics.append(diagnostic)
                raise APISportsError(
                    "API-Sports returned invalid JSON",
                    diagnostic=diagnostic,
                ) from None
            raw_provider_errors = payload.get("errors")
            provider_errors = _normalize_provider_errors(
                raw_provider_errors,
                secrets=(self._api_key,),
            )
            diagnostic = _response_diagnostic(
                response,
                endpoint=path,
                attempt=attempt + 1,
                category=(
                    "semantic_error"
                    if _has_provider_errors(raw_provider_errors)
                    else "success"
                ),
                provider_errors=provider_errors,
                inspect_payload=False,
                secrets=(self._api_key,),
            )
            self._request_diagnostics.append(diagnostic)
            _validate_top_level_payload(payload, diagnostic=diagnostic)
            fetched_at = _observed_fetched_at(payload)
            self._write_cache(
                cache_key,
                payload,
                self._quota_state,
                fetched_at=fetched_at,
                cache_dir=selected_cache_dir,
            )
            return _CachePayload(
                quota=self._quota_state,
                payload=payload,
                fetched_at=fetched_at,
            )

        raise APISportsError("API-Sports request failed")

    def _base_url(self, sport: Sport) -> str:
        if sport == "football":
            return FOOTBALL_BASE_URL
        if sport == "hockey":
            return HOCKEY_BASE_URL
        raise APISportsError("unsupported sport")

    def _ensure_quota_available(
        self,
        *,
        diagnostic: APISportsDiagnostic | None = None,
    ) -> None:
        if _is_quota_exhausted(self._quota_state, self._quota_reserve):
            raise QuotaExhausted(
                "API-Sports quota reserve reached",
                diagnostic=diagnostic,
            )

    def _check_safety_stop(self) -> None:
        if self._stop_at is None:
            return
        current = self._now()
        _require_utc_datetime("now", current)
        if current >= self._stop_at:
            raise SafetyStopReached("API-Sports safety stop reached")

    def _request_timeout(self) -> float:
        if self._stop_at is None:
            return self._timeout
        current = self._now()
        _require_utc_datetime("now", current)
        remaining_seconds = (self._stop_at - current).total_seconds()
        if remaining_seconds <= 0:
            raise SafetyStopReached("API-Sports safety stop reached")
        return min(self._timeout, remaining_seconds)

    def _sleep_before_retry(self, attempt: int) -> None:
        time.sleep(0.05 * (attempt + 1))

    def _load_cache(
        self,
        cache_key: str,
        *,
        cache_dir: Path | None = None,
        max_age_seconds: float | None = None,
    ) -> _CachePayload | None:
        selected_cache_dir = self._cache_dir if cache_dir is None else cache_dir
        path = selected_cache_dir / f"{cache_key}.json"
        try:
            if not path.exists():
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {
                "quota",
                "payload",
                "fetched_at",
            }:
                raise ValueError("invalid cache envelope")
            quota = raw["quota"]
            payload = raw["payload"]
            fetched_at = _parse_datetime(
                raw["fetched_at"], field_name="cache fetched_at"
            )
            if max_age_seconds is not None:
                current = self._now()
                _require_utc_datetime("now", current)
                if fetched_at > current:
                    raise ValueError("cache fetched_at cannot be in the future")
                if (current - fetched_at).total_seconds() > max_age_seconds:
                    return None
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
            return _CachePayload(
                quota=quota_state,
                payload=payload,
                fetched_at=fetched_at,
            )
        except (APISportsError, OSError, ValueError, TypeError):
            pass
        raise APISportsError("API-Sports cache is invalid")

    def _write_cache(
        self,
        cache_key: str,
        payload: dict[str, Any],
        quota_state: QuotaState,
        *,
        fetched_at: datetime,
        cache_dir: Path | None = None,
    ) -> None:
        body = {
            "fetched_at": fetched_at.isoformat(),
            "quota": {
                "daily_limit": quota_state.daily_limit,
                "daily_remaining": quota_state.daily_remaining,
                "minute_limit": quota_state.minute_limit,
                "minute_remaining": quota_state.minute_remaining,
            },
            "payload": payload,
        }
        selected_cache_dir = self._cache_dir if cache_dir is None else cache_dir
        final_path = selected_cache_dir / f"{cache_key}.json"
        temporary_path: Path | None = None
        error_message: str | None = None
        try:
            selected_cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=selected_cache_dir,
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
        daily_limit=_optional_int(
            _header_value(headers, "x-ratelimit-requests-limit")
        ),
        daily_remaining=_optional_int(
            _header_value(headers, "x-ratelimit-requests-remaining")
        ),
        minute_limit=_optional_int(_header_value(headers, "x-ratelimit-limit")),
        minute_remaining=_optional_int(
            _header_value(headers, "x-ratelimit-remaining")
        ),
    )


def diagnostic_payload(error: BaseException) -> dict[str, object] | None:
    if isinstance(error, APISportsError):
        return error.diagnostic_payload()
    return None


def sanitize_api_sports_message(
    message: object,
    *,
    secrets: tuple[str, ...] = (),
) -> str:
    """Bound API-Sports diagnostics without request metadata or raw payloads."""
    text = str(message).replace("\r", " ").replace("\n", " ").strip()
    for secret in sorted(
        (item for item in secrets if isinstance(item, str) and item),
        key=len,
        reverse=True,
    ):
        text = text.replace(secret, "[REDACTED]")
    text = _URL_QUERY_PATTERN.sub(r"\1?[REDACTED]", text)
    text = _SECRET_QUERY_PATTERN.sub(r"\1[REDACTED]", text)
    text = _SECRET_FIELD_PATTERN.sub(r"\1=[REDACTED]", text)
    text = re.sub(r"\s+", " ", text)
    return (text or "provider failure")[:_DIAGNOSTIC_MESSAGE_LIMIT]


def _response_diagnostic(
    response: Any,
    *,
    endpoint: str,
    attempt: int,
    category: str,
    provider_errors: tuple[APISportsProviderError, ...] | None = None,
    inspect_payload: bool = True,
    secrets: tuple[str, ...] = (),
) -> APISportsDiagnostic:
    headers = getattr(response, "headers", {})
    if not isinstance(headers, Mapping):
        headers = {}
    if provider_errors is None:
        provider_errors = (
            _safe_provider_errors_from_response(response, secrets=secrets)
            if inspect_payload
            else ()
        )
    return APISportsDiagnostic(
        category=category,
        endpoint=_safe_endpoint(endpoint),
        attempt=attempt,
        http_status=_safe_http_status(getattr(response, "status_code", None)),
        provider_errors=provider_errors,
        quota_daily_limit=_safe_optional_header_int(
            headers, "x-ratelimit-requests-limit"
        ),
        quota_daily_remaining=_safe_optional_header_int(
            headers, "x-ratelimit-requests-remaining"
        ),
        quota_minute_limit=_safe_optional_header_int(headers, "x-ratelimit-limit"),
        quota_minute_remaining=_safe_optional_header_int(
            headers, "x-ratelimit-remaining"
        ),
        quota_daily_reset=_safe_optional_header_int(
            headers, "x-ratelimit-requests-reset"
        ),
        quota_minute_reset=_safe_optional_header_int(
            headers, "x-ratelimit-reset"
        ),
    )


def _safe_provider_errors_from_response(
    response: Any,
    *,
    secrets: tuple[str, ...] = (),
) -> tuple[APISportsProviderError, ...]:
    try:
        payload = response.json()
    except (AttributeError, TypeError, ValueError):
        return ()
    if not isinstance(payload, Mapping):
        return ()
    return _normalize_provider_errors(payload.get("errors"), secrets=secrets)


def _normalize_provider_errors(
    value: object,
    *,
    secrets: tuple[str, ...] = (),
) -> tuple[APISportsProviderError, ...]:
    if value in (None, [], {}):
        return ()
    normalized: list[APISportsProviderError] = []
    if isinstance(value, Mapping):
        for raw_code, raw_message in sorted(
            value.items(), key=lambda item: str(item[0]).casefold()
        ):
            code = _normalize_provider_error_code(raw_code, secrets=secrets)
            if code is None:
                continue
            message = _normalize_provider_error_message(
                raw_message,
                secrets=secrets,
            )
            normalized.append(
                APISportsProviderError(
                    code=code,
                    message=message or "provider error",
                )
            )
    elif isinstance(value, (list, tuple)):
        for index, raw_message in enumerate(value[:10], start=1):
            message = _normalize_provider_error_message(
                raw_message,
                secrets=secrets,
            )
            if message is not None:
                normalized.append(
                    APISportsProviderError(
                        code=f"provider_error_{index}",
                        message=message,
                    )
                )
    else:
        message = _normalize_provider_error_message(value, secrets=secrets)
        if message is not None:
            normalized.append(
                APISportsProviderError(code="provider_error", message=message)
            )
    if not normalized:
        normalized.append(
            APISportsProviderError(code="provider_error", message="provider error")
        )
    return tuple(normalized[:10])


def _normalize_provider_error_code(
    value: object,
    *,
    secrets: tuple[str, ...] = (),
) -> str | None:
    if not isinstance(value, str):
        return None
    safe_value = value
    for secret in sorted(
        (item for item in secrets if isinstance(item, str) and item),
        key=len,
        reverse=True,
    ):
        safe_value = safe_value.replace(secret, "redacted")
    code = re.sub(
        r"[^a-z0-9_.-]+",
        "_",
        safe_value.strip().casefold(),
    ).strip("_")
    if _PROVIDER_ERROR_CODE_PATTERN.fullmatch(code) is None:
        return None
    return code


def _normalize_provider_error_message(
    value: object,
    *,
    secrets: tuple[str, ...] = (),
) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, float) and not isfinite(value):
        return None
    return sanitize_api_sports_message(value, secrets=secrets)


def _has_provider_errors(value: object) -> bool:
    return value not in (None, [])


def _provider_error_codes(value: object) -> frozenset[str]:
    if not isinstance(value, Mapping):
        return frozenset()
    return frozenset(
        code
        for code in (_normalize_provider_error_code(key) for key in value)
        if code is not None
    )


def _safe_endpoint(endpoint: object) -> str:
    if not isinstance(endpoint, str):
        return "unknown"
    path = endpoint.split("?", 1)[0].strip()
    if not path.startswith("/") or not re.fullmatch(r"/[a-z0-9_./-]{1,127}", path):
        return "unknown"
    return path


def _safe_http_status(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
        return value
    return None


def _safe_nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _header_value(headers: Mapping[str, object], name: str) -> object:
    expected = name.casefold()
    for key, value in headers.items():
        if isinstance(key, str) and key.casefold() == expected:
            return value
    return None


def _safe_optional_header_int(
    headers: Mapping[str, object],
    name: str,
) -> int | None:
    value = _header_value(headers, name)
    try:
        parsed = _optional_int(value)
    except APISportsError:
        return None
    if parsed is None or parsed < 0:
        return None
    return parsed


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
        "cache_schema": _CACHE_SCHEMA_VERSION,
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
    except ValueError:
        raise APISportsError("API-Sports returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise APISportsError("API-Sports payload must be an object")
    return payload


def _validate_top_level_payload(
    payload: Mapping[str, Any],
    *,
    diagnostic: APISportsDiagnostic | None = None,
) -> None:
    errors = payload.get("errors")
    if errors not in ([], None):
        provider_errors = (
            diagnostic.provider_errors
            if diagnostic is not None
            else _normalize_provider_errors(errors)
        )
        effective_diagnostic = diagnostic
        if diagnostic is None or diagnostic.provider_errors != provider_errors:
            effective_diagnostic = APISportsDiagnostic(
                category="semantic_error",
                endpoint=("unknown" if diagnostic is None else diagnostic.endpoint),
                attempt=(1 if diagnostic is None else diagnostic.attempt),
                http_status=(None if diagnostic is None else diagnostic.http_status),
                provider_errors=provider_errors,
                quota_daily_limit=(
                    None if diagnostic is None else diagnostic.quota_daily_limit
                ),
                quota_daily_remaining=(
                    None if diagnostic is None else diagnostic.quota_daily_remaining
                ),
                quota_minute_limit=(
                    None if diagnostic is None else diagnostic.quota_minute_limit
                ),
                quota_minute_remaining=(
                    None if diagnostic is None else diagnostic.quota_minute_remaining
                ),
                quota_daily_reset=(
                    None if diagnostic is None else diagnostic.quota_daily_reset
                ),
                quota_minute_reset=(
                    None if diagnostic is None else diagnostic.quota_minute_reset
                ),
            )
        if _provider_error_codes(errors) & {"plan", "subscription"}:
            message = "API-Sports plan does not provide the requested data"
            raise ProviderPlanUnavailable(
                message,
                diagnostic=effective_diagnostic,
            )
        message = "API-Sports returned provider errors"
        raise APISportsError(
            message,
            diagnostic=effective_diagnostic,
        )
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
    sport: Sport,
    payload: Mapping[str, Any],
    *,
    fetched_at: datetime,
) -> tuple[ProviderEvent, ...]:
    events: list[ProviderEvent] = []
    for item in payload["response"]:
        if not isinstance(item, Mapping):
            raise APISportsError("API-Sports event must be an object")
        (
            provider_event_id,
            starts_at,
            league,
            country,
            home,
            away,
            home_id,
            away_id,
        ) = _event_core_fields(item, sport=sport)
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
                country=country,
                provider_home_team_id=home_id,
                provider_away_team_id=away_id,
            )
        )
    return tuple(events)


def _parse_market_payload(
    sport: Sport,
    provider_event_id: str,
    payload: Mapping[str, Any],
    *,
    fetched_at: datetime,
) -> tuple[ProviderMarket, ...]:
    markets: list[ProviderMarket] = []
    for item in payload["response"]:
        if not isinstance(item, Mapping):
            raise APISportsError("API-Sports odds event must be an object")
        item_event_id = _market_event_id(item, sport=sport)
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


def _observed_fetched_at(payload: Mapping[str, Any]) -> datetime:
    if "timestamp" in payload:
        return _parse_datetime(payload.get("timestamp"), field_name="timestamp")
    return _utc_now()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_stop_at(stop_at: datetime | None) -> None:
    if stop_at is not None:
        _require_utc_datetime("stop_at", stop_at)


def _require_utc_datetime(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _item_updated_at(item: Mapping[str, Any]) -> datetime | None:
    if "update" not in item:
        return None
    return _parse_datetime(item.get("update"), field_name="item update")


def _event_core_fields(
    item: Mapping[str, Any],
    *,
    sport: Sport,
) -> tuple[str, datetime, str, str | None, str, str, str | None, str | None]:
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
    raw_country = league_obj.get("country")
    country = None if raw_country is None else _text(raw_country, "league country")
    teams = item.get("teams")
    if not isinstance(teams, Mapping):
        raise APISportsError("API-Sports teams must be an object")
    home_obj = teams.get("home")
    away_obj = teams.get("away")
    if not isinstance(home_obj, Mapping) or not isinstance(away_obj, Mapping):
        raise APISportsError("API-Sports teams must include home and away")
    home = _text(home_obj.get("name"), "home team")
    away = _text(away_obj.get("name"), "away team")
    home_id = _optional_identifier(home_obj.get("id"), "home team id")
    away_id = _optional_identifier(away_obj.get("id"), "away team id")
    return provider_event_id, starts_at, league, country, home, away, home_id, away_id


def _market_event_id(item: Mapping[str, Any], *, sport: Sport) -> str:
    if sport == "football":
        event_label = "fixture"
    elif sport == "hockey":
        event_label = "game"
    else:
        raise APISportsError("unsupported sport")
    event_data = item.get(event_label)
    if not isinstance(event_data, Mapping):
        raise APISportsError(f"API-Sports {event_label} must be an object")
    return _identifier(event_data.get("id"), f"{event_label} id")


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


def _optional_identifier(value: object, field_name: str) -> str | None:
    return None if value is None else _identifier(value, field_name)


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
        name = _price_label(item.get("value"))
        odd = _text(item.get("odd"), "price odd")
        entries.append({"value": name, "odd": odd})
    return tuple(entries)


def _price_label(value: object) -> str:
    if isinstance(value, bool):
        raise APISportsError("API-Sports price value is invalid")
    if isinstance(value, (int, float)):
        if not isfinite(float(value)):
            raise APISportsError("API-Sports price value is invalid")
        return str(value)
    return _text(value, "price value")


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
        minute_remaining is not None and minute_remaining <= 0
    ) or (
        daily_remaining is not None and daily_remaining <= quota_reserve
    )
