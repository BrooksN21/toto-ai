"""Documented TheSportsDB v1 schedule provider.

The key is part of the v1 URL path, so request evidence, cache identities,
diagnostics, and exceptions deliberately retain only the key-free endpoint.
Only the documented ``eventsday.php`` and ``searchevents.php`` endpoints are
reachable through this client.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import requests

from toto_ai.external_odds.domain import ProviderEvent, QuotaState, Sport

THESPORTSDB_API_KEY_ENV = "THESPORTSDB_API_KEY"
THESPORTSDB_BASE_URL_ENV = "THESPORTSDB_BASE_URL"
DEFAULT_BASE_URL = "https://www.thesportsdb.com/api/v1/json"
PUBLIC_V1_API_KEY = "123"
PROVIDER_NAME = "thesportsdb-v1"

_ALLOWED_ENDPOINTS = frozenset(("eventsday.php", "searchevents.php"))
_RETRY_STATUSES = frozenset((408, 429, 500, 502, 503, 504))
_CACHE_SCHEMA_VERSION = 1
_MAX_WINDOW_SPAN = timedelta(days=5)
_MAX_WINDOW_DATES = 6
_MAX_RETRIES = 3
_MAX_REQUESTS_PER_MINUTE = 30
_MESSAGE_LIMIT = 240
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SECRET_FIELD_PATTERN = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|"
    r"api[_-]?key|key|token|secret|password)\b"
    r"[\"']?\s*[:=]\s*[\"']?(?:bearer\s+)?[^,\s;}&\"']+"
)
_SECRET_QUERY_PATTERN = re.compile(
    r"(?i)([?&](?:api[_-]?key|key|token|access[_-]?token|auth|authorization|"
    r"password|secret)=)[^&#\s]+"
)
_URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]*", re.IGNORECASE)
_SCHEDULED_STATUSES = frozenset(("scheduled", "not_started"))
_TBD_MARKERS = frozenset(
    (
        "tbd",
        "time tbd",
        "time to be defined",
        "to be defined",
        "unknown",
    )
)
_ZERO_TIME_PATTERN = re.compile(
    r"0{1,2}:0{2}(?::0{2}(?:\.0+)?)?(?:Z|[+-]00:00)?\Z",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TheSportsDBConfig:
    """Secret-safe provider configuration.

    The documented public v1 key is the default. An explicit ``api_key=None``
    remains a valid disabled configuration for offline/test callers.
    """

    api_key: str | None = field(default=PUBLIC_V1_API_KEY, repr=False)
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 10.0
    max_retries: int = 1
    requests_per_minute: int = 30
    cache_ttl: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        if self.api_key is not None and (
            not isinstance(self.api_key, str) or not self.api_key.strip()
        ):
            raise ValueError("TheSportsDB API key must be non-empty or None")
        _validate_base_url(self.base_url)
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not 0 < float(self.timeout) <= 60
        ):
            raise ValueError("TheSportsDB timeout must be in (0, 60]")
        if (
            not isinstance(self.max_retries, int)
            or isinstance(self.max_retries, bool)
            or not 0 <= self.max_retries <= _MAX_RETRIES
        ):
            raise ValueError("TheSportsDB max_retries must be in range 0 through 3")
        if (
            not isinstance(self.requests_per_minute, int)
            or isinstance(self.requests_per_minute, bool)
            or not 1 <= self.requests_per_minute <= _MAX_REQUESTS_PER_MINUTE
        ):
            raise ValueError("TheSportsDB requests_per_minute must be in range 1..30")
        if not isinstance(self.cache_ttl, timedelta) or not (
            timedelta(0) < self.cache_ttl <= timedelta(hours=1)
        ):
            raise ValueError("TheSportsDB cache_ttl must be in (0, 1 hour]")

    @property
    def enabled(self) -> bool:
        return self.api_key is not None


@dataclass(frozen=True)
class TheSportsDBProviderError:
    code: str
    message: str


@dataclass(frozen=True)
class TheSportsDBDiagnostic:
    """API-Sports-shaped secret-safe request diagnostic."""

    category: str
    endpoint: str
    attempt: int
    http_status: int | None = None
    provider_errors: tuple[TheSportsDBProviderError, ...] = ()
    quota_daily_limit: int | None = None
    quota_daily_remaining: int | None = None
    quota_minute_limit: int | None = None
    quota_minute_remaining: int | None = None
    quota_daily_reset: int | None = None
    quota_minute_reset: int | None = None

    def payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "endpoint": self.endpoint,
            "attempt": self.attempt,
            "http_status": self.http_status,
            "provider_errors": [
                {"code": item.code, "message": item.message}
                for item in self.provider_errors
            ],
            "quota_daily_limit": self.quota_daily_limit,
            "quota_daily_remaining": self.quota_daily_remaining,
            "quota_minute_limit": self.quota_minute_limit,
            "quota_minute_remaining": self.quota_minute_remaining,
            "quota_daily_reset": self.quota_daily_reset,
            "quota_minute_reset": self.quota_minute_reset,
        }

    def summary(self) -> str:
        fields = [
            self.category,
            f"endpoint={self.endpoint}",
            f"attempt={self.attempt}",
        ]
        if self.http_status is not None:
            fields.append(f"http={self.http_status}")
        if self.quota_minute_limit is not None:
            fields.append(f"quota_minute_limit={self.quota_minute_limit}")
        if self.quota_minute_remaining is not None:
            fields.append(f"quota_minute_remaining={self.quota_minute_remaining}")
        if self.provider_errors:
            fields.append(
                "provider="
                + ",".join(
                    f"{item.code}:{item.message}" for item in self.provider_errors
                )
            )
        return " ".join(fields)


class TheSportsDBError(RuntimeError):
    """Sanitized TheSportsDB provider failure."""

    def __init__(
        self,
        message: object,
        *,
        diagnostic: TheSportsDBDiagnostic | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        text = str(message)
        if diagnostic is not None and diagnostic.summary() not in text:
            text = f"{text}; {diagnostic.summary()}"
        super().__init__(sanitize_thesportsdb_message(text, secrets=secrets))
        self.diagnostic = diagnostic

    def diagnostic_payload(self) -> dict[str, object] | None:
        return None if self.diagnostic is None else self.diagnostic.payload()


class TheSportsDBDisabledError(TheSportsDBError):
    """Raised before transport when the required key is absent."""


@dataclass(frozen=True)
class TheSportsDBRequestEvidence:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    request_fingerprint: str
    response_hash: str
    fetched_at: datetime
    cache_hit: bool
    snapshot_path: Path
    snapshot_sha256: str


@dataclass(frozen=True)
class TheSportsDBScheduleEvent:
    provider_event_id: str
    sport: Sport
    competition: str
    home_team: str
    away_team: str
    starts_at: datetime
    status: str
    eligible: bool
    source_url: str
    captured_at: datetime
    payload_hash: str
    source_endpoint: str
    request_fingerprint: str
    provider_home_team_id: str | None = None
    provider_away_team_id: str | None = None

    def as_provider_event(self) -> ProviderEvent:
        return ProviderEvent(
            provider=PROVIDER_NAME,
            provider_event_id=self.provider_event_id,
            sport=self.sport,
            league=self.competition,
            starts_at=self.starts_at,
            home_team=self.home_team,
            away_team=self.away_team,
            fetched_at=self.captured_at,
            payload_hash=self.payload_hash,
            provider_home_team_id=self.provider_home_team_id,
            provider_away_team_id=self.provider_away_team_id,
            source_endpoint=self.source_endpoint,
            request_fingerprint=self.request_fingerprint,
        )


@dataclass(frozen=True)
class _Payload:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    body: dict[str, Any]
    fetched_at: datetime
    payload_hash: str
    request_fingerprint: str
    snapshot_path: Path
    snapshot_sha256: str


def load_thesportsdb_config(
    environment: Mapping[str, str] | None = None,
    **overrides: object,
) -> TheSportsDBConfig:
    """Load the optional key override and official base URL configuration."""

    values = os.environ if environment is None else environment
    api_key = overrides.pop("api_key", None)
    if api_key is None:
        api_key = (
            values.get(THESPORTSDB_API_KEY_ENV, "").strip()
            or PUBLIC_V1_API_KEY
        )
    base_url = overrides.pop("base_url", None)
    if base_url is None:
        base_url = values.get(THESPORTSDB_BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL
    return TheSportsDBConfig(api_key=api_key, base_url=str(base_url), **overrides)


class TheSportsDBClient:
    provider_name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str = PUBLIC_V1_API_KEY,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        cache_dir: Path = Path("data/external-cache/thesportsdb-v1"),
        timeout: float = 10.0,
        max_retries: int = 1,
        requests_per_minute: int = 30,
        cache_ttl: timedelta = timedelta(minutes=10),
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise TheSportsDBDisabledError(f"{THESPORTSDB_API_KEY_ENV} is required")
        config = TheSportsDBConfig(
            api_key=api_key.strip(),
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_minute=requests_per_minute,
            cache_ttl=cache_ttl,
        )
        if not config.enabled or config.api_key is None:
            raise TheSportsDBDisabledError(f"{THESPORTSDB_API_KEY_ENV} is required")
        self._api_key = config.api_key
        self._base_url = config.base_url.rstrip("/")
        self._session = session or requests.Session()
        self._cache_dir = Path(cache_dir)
        self._timeout = float(config.timeout)
        self._max_retries = config.max_retries
        self._requests_per_minute = config.requests_per_minute
        self._cache_ttl = config.cache_ttl
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._next_request_at = 0.0
        self._request_ticks: list[float] = []
        self._requests_made = 0
        self._cache_hits = 0
        self._request_diagnostics: list[TheSportsDBDiagnostic] = []
        self._request_evidence: list[TheSportsDBRequestEvidence] = []

    @classmethod
    def from_config(
        cls,
        config: TheSportsDBConfig,
        **kwargs: object,
    ) -> TheSportsDBClient:
        if not config.enabled or config.api_key is None:
            raise TheSportsDBDisabledError(f"{THESPORTSDB_API_KEY_ENV} is required")
        return cls(
            config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
            requests_per_minute=config.requests_per_minute,
            cache_ttl=config.cache_ttl,
            **kwargs,
        )

    @property
    def quota_state(self) -> QuotaState:
        remaining = max(0, self._requests_per_minute - len(self._recent_ticks()))
        return QuotaState(None, None, self._requests_per_minute, remaining)

    @property
    def requests_made(self) -> int:
        return self._requests_made

    @property
    def cache_hits(self) -> int:
        return self._cache_hits

    @property
    def request_diagnostics(self) -> tuple[TheSportsDBDiagnostic, ...]:
        return tuple(self._request_diagnostics)

    @property
    def request_evidence(self) -> tuple[TheSportsDBRequestEvidence, ...]:
        return tuple(self._request_evidence)

    def fetch_schedule(
        self,
        sport: Sport,
        dates: tuple[date, ...],
    ) -> tuple[ProviderEvent, ...]:
        requested = _bounded_dates(dates)
        sport_name = _api_sport(sport)
        events: list[TheSportsDBScheduleEvent] = []
        for requested_date in requested:
            payload = self._get_json(
                "eventsday.php",
                {"d": requested_date.isoformat(), "s": sport_name},
            )
            events.extend(_parse_events(payload, source_origin=self._source_origin))
        allowed_dates = frozenset(requested)
        return _dedupe_provider_events(
            tuple(
                item.as_provider_event()
                for item in events
                if item.eligible
                and item.sport == sport
                and item.starts_at.date() in allowed_dates
            )
        )

    def search_schedule_events(
        self,
        home_team: str,
        away_team: str,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[TheSportsDBScheduleEvent, ...]:
        _require_text("home_team", home_team)
        _require_text("away_team", away_team)
        start = _utc(window_start, "window_start")
        end = _utc(window_end, "window_end")
        if end < start or end - start > _MAX_WINDOW_SPAN:
            raise ValueError("TheSportsDB search window must span at most 5 days")
        payload = self._get_json(
            "searchevents.php",
            {"e": f"{home_team.strip()}_vs_{away_team.strip()}"},
        )
        return tuple(
            item
            for item in _parse_events(payload, source_origin=self._source_origin)
            if start <= item.starts_at <= end
        )

    @property
    def _source_origin(self) -> str:
        parsed = urlsplit(self._base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_json(self, endpoint: str, params: Mapping[str, object]) -> _Payload:
        if endpoint not in _ALLOWED_ENDPOINTS:
            raise ValueError("unsupported TheSportsDB v1 endpoint")
        safe_params = tuple((key, str(value)) for key, value in sorted(params.items()))
        fingerprint = _request_fingerprint(self._base_url, endpoint, safe_params)
        cached = self._load_cache(fingerprint)
        if cached is not None:
            self._cache_hits += 1
            self._record_evidence(cached, cache_hit=True)
            return cached

        for attempt in range(1, self._max_retries + 2):
            self._pace()
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{self._base_url}/{quote(self._api_key, safe='')}/{endpoint}",
                    params=dict(safe_params),
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                diagnostic = self._diagnostic(
                    "transport_failure"
                    if attempt == self._max_retries + 1
                    else "transport_retry",
                    endpoint,
                    attempt,
                )
                self._request_diagnostics.append(diagnostic)
                if attempt == self._max_retries + 1:
                    raise TheSportsDBError(
                        f"TheSportsDB transport failed: {type(error).__name__}",
                        diagnostic=diagnostic,
                        secrets=(self._api_key,),
                    ) from None
                continue

            provider_errors = _provider_errors(response, secrets=(self._api_key,))
            if response.status_code in _RETRY_STATUSES:
                diagnostic = self._diagnostic(
                    "http_failure"
                    if attempt == self._max_retries + 1
                    else "http_retry",
                    endpoint,
                    attempt,
                    http_status=response.status_code,
                    provider_errors=provider_errors,
                )
                self._request_diagnostics.append(diagnostic)
                if attempt == self._max_retries + 1:
                    raise TheSportsDBError(
                        "TheSportsDB request failed",
                        diagnostic=diagnostic,
                        secrets=(self._api_key,),
                    )
                continue
            if response.status_code >= 400:
                diagnostic = self._diagnostic(
                    "http_failure",
                    endpoint,
                    attempt,
                    http_status=response.status_code,
                    provider_errors=provider_errors,
                )
                self._request_diagnostics.append(diagnostic)
                raise TheSportsDBError(
                    "TheSportsDB request failed",
                    diagnostic=diagnostic,
                    secrets=(self._api_key,),
                )
            try:
                body = response.json()
            except (AttributeError, TypeError, ValueError):
                diagnostic = self._diagnostic(
                    "invalid_json",
                    endpoint,
                    attempt,
                    http_status=response.status_code,
                )
                self._request_diagnostics.append(diagnostic)
                raise TheSportsDBError(
                    "TheSportsDB returned invalid JSON",
                    diagnostic=diagnostic,
                    secrets=(self._api_key,),
                ) from None
            if not isinstance(body, dict):
                raise TheSportsDBError(
                    "TheSportsDB payload must be an object",
                    secrets=(self._api_key,),
                )
            provider_errors = _provider_errors_from_payload(
                body, secrets=(self._api_key,)
            )
            category = "semantic_error" if provider_errors else "success"
            diagnostic = self._diagnostic(
                category,
                endpoint,
                attempt,
                http_status=response.status_code,
                provider_errors=provider_errors,
            )
            self._request_diagnostics.append(diagnostic)
            if provider_errors:
                raise TheSportsDBError(
                    "TheSportsDB returned provider errors",
                    diagnostic=diagnostic,
                    secrets=(self._api_key,),
                )
            fetched_at = _utc(self._now(), "now")
            payload = self._freeze_payload(
                endpoint=endpoint,
                params=safe_params,
                body=body,
                fetched_at=fetched_at,
                request_fingerprint=fingerprint,
            )
            self._write_cache_index(payload)
            self._record_evidence(payload, cache_hit=False)
            return payload
        raise TheSportsDBError("TheSportsDB request failed")

    def _diagnostic(
        self,
        category: str,
        endpoint: str,
        attempt: int,
        *,
        http_status: int | None = None,
        provider_errors: tuple[TheSportsDBProviderError, ...] = (),
    ) -> TheSportsDBDiagnostic:
        recent = self._recent_ticks()
        return TheSportsDBDiagnostic(
            category=category,
            endpoint=f"/{endpoint}",
            attempt=attempt,
            http_status=http_status,
            provider_errors=provider_errors,
            quota_minute_limit=self._requests_per_minute,
            quota_minute_remaining=max(0, self._requests_per_minute - len(recent)),
        )

    def _pace(self) -> None:
        current = self._monotonic()
        wait_seconds = self._next_request_at - current
        if wait_seconds > 0:
            self._sleep(wait_seconds)
            current = self._monotonic()
        self._next_request_at = max(current, self._next_request_at) + (
            60.0 / self._requests_per_minute
        )
        self._request_ticks.append(current)
        self._recent_ticks(current)

    def _recent_ticks(self, current: float | None = None) -> list[float]:
        observed = self._monotonic() if current is None else current
        self._request_ticks = [
            item for item in self._request_ticks if observed - item < 60.0
        ]
        return self._request_ticks

    def _freeze_payload(
        self,
        *,
        endpoint: str,
        params: tuple[tuple[str, str], ...],
        body: dict[str, Any],
        fetched_at: datetime,
        request_fingerprint: str,
    ) -> _Payload:
        payload_hash = _sha256_json(body)
        document = {
            "cache_schema": _CACHE_SCHEMA_VERSION,
            "provider": PROVIDER_NAME,
            "endpoint": f"/{endpoint}",
            "params": [list(item) for item in params],
            "request_fingerprint": request_fingerprint,
            "fetched_at": _timestamp(fetched_at),
            "payload_hash": payload_hash,
            "payload": body,
        }
        content = _canonical_bytes(document) + b"\n"
        snapshot_sha256 = hashlib.sha256(content).hexdigest()
        snapshot_path = (
            self._cache_dir
            / "snapshots"
            / f"{request_fingerprint}-{snapshot_sha256[:16]}.json"
        )
        _write_exact(snapshot_path, content)
        return _Payload(
            endpoint=f"/{endpoint}",
            params=params,
            body=body,
            fetched_at=fetched_at,
            payload_hash=payload_hash,
            request_fingerprint=request_fingerprint,
            snapshot_path=snapshot_path.resolve(),
            snapshot_sha256=snapshot_sha256,
        )

    def _write_cache_index(self, payload: _Payload) -> None:
        root = self._cache_dir.resolve()
        relative_snapshot = payload.snapshot_path.relative_to(root)
        index = {
            "cache_schema": _CACHE_SCHEMA_VERSION,
            "provider": PROVIDER_NAME,
            "endpoint": payload.endpoint,
            "params": [list(item) for item in payload.params],
            "request_fingerprint": payload.request_fingerprint,
            "fetched_at": _timestamp(payload.fetched_at),
            "payload_hash": payload.payload_hash,
            "snapshot_path": str(relative_snapshot),
            "snapshot_sha256": payload.snapshot_sha256,
        }
        _write_replace(
            self._cache_dir / "index" / f"{payload.request_fingerprint}.json",
            _canonical_bytes(index) + b"\n",
        )

    def _load_cache(self, fingerprint: str) -> _Payload | None:
        index_path = self._cache_dir / "index" / f"{fingerprint}.json"
        if not index_path.exists():
            return None
        try:
            if index_path.is_symlink() or not index_path.is_file():
                raise ValueError
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index, dict) or set(index) != {
                "cache_schema",
                "provider",
                "endpoint",
                "params",
                "request_fingerprint",
                "fetched_at",
                "payload_hash",
                "snapshot_path",
                "snapshot_sha256",
            }:
                raise ValueError
            fetched_at = _parse_timestamp(index["fetched_at"])
            observed = _utc(self._now(), "now")
            if fetched_at > observed or observed - fetched_at > self._cache_ttl:
                return None
            if (
                index["cache_schema"] != _CACHE_SCHEMA_VERSION
                or index["provider"] != PROVIDER_NAME
                or index["request_fingerprint"] != fingerprint
                or _HASH_PATTERN.fullmatch(str(index["payload_hash"])) is None
                or _HASH_PATTERN.fullmatch(str(index["snapshot_sha256"])) is None
            ):
                raise ValueError
            root = self._cache_dir.resolve()
            snapshot_path = (root / str(index["snapshot_path"])).resolve()
            snapshot_path.relative_to(root)
            if snapshot_path.is_symlink() or not snapshot_path.is_file():
                raise ValueError
            content = snapshot_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != index["snapshot_sha256"]:
                raise ValueError
            document = json.loads(content)
            if (
                not isinstance(document, dict)
                or document.get("request_fingerprint") != fingerprint
                or document.get("payload_hash") != index["payload_hash"]
                or document.get("fetched_at") != index["fetched_at"]
                or document.get("endpoint") != index["endpoint"]
                or document.get("params") != index["params"]
                or _sha256_json(document.get("payload")) != index["payload_hash"]
                or not isinstance(document.get("payload"), dict)
            ):
                raise ValueError
            params = tuple((str(key), str(value)) for key, value in index["params"])
            return _Payload(
                endpoint=str(index["endpoint"]),
                params=params,
                body=document["payload"],
                fetched_at=fetched_at,
                payload_hash=str(index["payload_hash"]),
                request_fingerprint=fingerprint,
                snapshot_path=snapshot_path,
                snapshot_sha256=str(index["snapshot_sha256"]),
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            raise TheSportsDBError("TheSportsDB cache integrity check failed") from None

    def _record_evidence(self, payload: _Payload, *, cache_hit: bool) -> None:
        self._request_evidence.append(
            TheSportsDBRequestEvidence(
                endpoint=payload.endpoint,
                params=payload.params,
                request_fingerprint=payload.request_fingerprint,
                response_hash=payload.payload_hash,
                fetched_at=payload.fetched_at,
                cache_hit=cache_hit,
                snapshot_path=payload.snapshot_path,
                snapshot_sha256=payload.snapshot_sha256,
            )
        )


def diagnostic_payload(error: BaseException) -> dict[str, object] | None:
    if isinstance(error, TheSportsDBError):
        return error.diagnostic_payload()
    return None


def sanitize_thesportsdb_message(
    message: object,
    *,
    secrets: tuple[str, ...] = (),
) -> str:
    text = str(message).replace("\r", " ").replace("\n", " ").strip()
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _URL_QUERY_PATTERN.sub(r"\1?[REDACTED]", text)
    text = _SECRET_QUERY_PATTERN.sub(r"\1[REDACTED]", text)
    text = _SECRET_FIELD_PATTERN.sub(r"\1=[REDACTED]", text)
    text = re.sub(r"\s+", " ", text)
    return (text or "provider failure")[:_MESSAGE_LIMIT]


def _parse_events(
    payload: _Payload,
    *,
    source_origin: str,
) -> tuple[TheSportsDBScheduleEvent, ...]:
    if "events" in payload.body and "event" in payload.body:
        raise TheSportsDBError("TheSportsDB payload has conflicting event fields")
    raw_events = payload.body.get("events" if "events" in payload.body else "event")
    if raw_events is None:
        return ()
    if not isinstance(raw_events, list):
        raise TheSportsDBError("TheSportsDB events field must be a list or null")
    return tuple(
        _parse_event(
            item,
            fetched_at=payload.fetched_at,
            source_origin=source_origin,
            source_endpoint=payload.endpoint,
            request_fingerprint=payload.request_fingerprint,
        )
        for item in raw_events
    )


def _parse_event(
    value: object,
    *,
    fetched_at: datetime,
    source_origin: str,
    source_endpoint: str,
    request_fingerprint: str,
) -> TheSportsDBScheduleEvent:
    if not isinstance(value, Mapping):
        raise TheSportsDBError("TheSportsDB event must be an object")
    event_id = _text(value.get("idEvent"), "idEvent")
    sport = _normalize_sport(value.get("strSport"))
    competition = _text(value.get("strLeague"), "strLeague")
    starts_at = _event_timestamp(value)
    status = _normalize_status(value, starts_at=starts_at)
    eligible = (
        status in _SCHEDULED_STATUSES
        and sport in {"football", "hockey"}
        and fetched_at < starts_at
    )
    return TheSportsDBScheduleEvent(
        provider_event_id=event_id,
        sport=sport,
        competition=competition,
        home_team=_text(value.get("strHomeTeam"), "strHomeTeam"),
        away_team=_text(value.get("strAwayTeam"), "strAwayTeam"),
        starts_at=starts_at,
        status=status,
        eligible=eligible,
        source_url=f"{source_origin}/event/{quote(event_id, safe='')}",
        captured_at=fetched_at,
        payload_hash=_sha256_json(value),
        source_endpoint=source_endpoint,
        request_fingerprint=request_fingerprint,
        provider_home_team_id=_optional_text(value.get("idHomeTeam")),
        provider_away_team_id=_optional_text(value.get("idAwayTeam")),
    )


def _event_timestamp(value: Mapping[str, object]) -> datetime:
    timestamp = _optional_text(value.get("strTimestamp"))
    if timestamp is not None:
        return _parse_event_timestamp(timestamp)
    event_date = _text(value.get("dateEvent"), "dateEvent")
    event_time = _optional_text(value.get("strTime"))
    normalized_time = (
        None
        if event_time is None
        else re.sub(r"[^a-z0-9]+", " ", event_time.casefold()).strip()
    )
    if event_time is None or normalized_time in _TBD_MARKERS:
        try:
            return datetime.fromisoformat(f"{event_date}T00:00:00").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            raise TheSportsDBError(
                "TheSportsDB event date/time is invalid"
            ) from None
    try:
        parsed = datetime.fromisoformat(
            f"{event_date}T{event_time.replace('Z', '+00:00')}"
        )
    except ValueError:
        raise TheSportsDBError("TheSportsDB event date/time is invalid") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_status(
    value: Mapping[str, object],
    *,
    starts_at: datetime,
) -> str:
    postponed = _optional_text(value.get("strPostponed"))
    if postponed is not None and postponed.casefold() in {"yes", "true", "1"}:
        return "postponed"
    raw = _optional_text(value.get("strStatus"))
    if raw is None:
        return "unknown"
    normalized = re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()
    event_time = _optional_text(value.get("strTime"))
    normalized_time = (
        None
        if event_time is None
        else re.sub(r"[^a-z0-9]+", " ", event_time.casefold()).strip()
    )
    if normalized in _TBD_MARKERS or normalized_time in _TBD_MARKERS:
        return "unknown"
    if normalized in {
        "scheduled",
        "fixture",
        "not started",
        "notstarted",
        "ns",
    } and _is_placeholder_event_time(
        starts_at,
        event_time,
    ):
        return "unknown"
    if normalized in {"scheduled", "fixture"}:
        return "scheduled"
    if normalized in {"not started", "notstarted", "ns"}:
        return "not_started"
    if normalized in {"postponed", "postponement"}:
        return "postponed"
    if normalized in {"cancelled", "canceled", "abandoned"}:
        return "cancelled"
    if normalized in {
        "match finished",
        "finished",
        "full time",
        "after extra time",
        "after penalties",
    }:
        return "finished"
    return "unknown"


def _is_placeholder_event_time(
    starts_at: datetime,
    event_time: str | None,
) -> bool:
    """Recognize TheSportsDB's date-only midnight placeholder conservatively."""

    if starts_at.hour or starts_at.minute or starts_at.second or starts_at.microsecond:
        return False
    return (
        event_time is None
        or _ZERO_TIME_PATTERN.fullmatch(event_time.strip()) is not None
    )


def _normalize_sport(value: object) -> Sport:
    raw = _text(value, "strSport").casefold()
    if raw in {"soccer", "football"}:
        return "football"
    if raw in {"ice hockey", "icehockey", "hockey"}:
        return "hockey"
    return "unknown"


def _provider_errors(
    response: object,
    *,
    secrets: tuple[str, ...],
) -> tuple[TheSportsDBProviderError, ...]:
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return ()
    if not isinstance(payload, Mapping):
        return ()
    return _provider_errors_from_payload(payload, secrets=secrets)


def _provider_errors_from_payload(
    payload: Mapping[str, object],
    *,
    secrets: tuple[str, ...],
) -> tuple[TheSportsDBProviderError, ...]:
    raw = payload.get("error", payload.get("errors"))
    if raw in (None, "", [], {}):
        return ()
    if isinstance(raw, Mapping):
        values = tuple(raw.items())
    elif isinstance(raw, (list, tuple)):
        values = tuple(
            (f"provider_error_{index}", item) for index, item in enumerate(raw, 1)
        )
    else:
        values = (("provider_error", raw),)
    return tuple(
        TheSportsDBProviderError(
            code=_error_code(code),
            message=sanitize_thesportsdb_message(message, secrets=secrets),
        )
        for code, message in values[:10]
    )


def _error_code(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "_", str(value).casefold()).strip("_")
    return (normalized or "provider_error")[:64]


def _request_fingerprint(
    base_url: str,
    endpoint: str,
    params: tuple[tuple[str, str], ...],
) -> str:
    parsed = urlsplit(base_url)
    return _sha256_json(
        {
            "cache_schema": _CACHE_SCHEMA_VERSION,
            "provider": PROVIDER_NAME,
            "origin": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "endpoint": f"/{endpoint}",
            "params": params,
        }
    )


def _bounded_dates(values: tuple[date, ...]) -> tuple[date, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError("TheSportsDB dates must be a non-empty tuple")
    if any(not isinstance(item, date) or isinstance(item, datetime) for item in values):
        raise ValueError("TheSportsDB dates must contain date values")
    result = tuple(sorted(set(values)))
    if (
        len(result) != len(values)
        or len(result) > _MAX_WINDOW_DATES
        or result[-1] - result[0] > _MAX_WINDOW_SPAN
    ):
        raise ValueError(
            "TheSportsDB date window must be unique and span at most 5 days"
        )
    return result


def _api_sport(sport: Sport) -> str:
    if sport == "football":
        return "Soccer"
    if sport == "hockey":
        return "Ice Hockey"
    raise TheSportsDBError("unsupported sport")


def _dedupe_provider_events(
    values: tuple[ProviderEvent, ...],
) -> tuple[ProviderEvent, ...]:
    by_id: dict[str, ProviderEvent] = {}
    for item in values:
        previous = by_id.get(item.provider_event_id)
        if previous is not None and previous != item:
            raise TheSportsDBError("TheSportsDB duplicate event identity conflicts")
        by_id[item.provider_event_id] = item
    return tuple(by_id[key] for key in sorted(by_id))


def _validate_base_url(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TheSportsDB base_url must be non-empty")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("TheSportsDB base_url must be a credential-free HTTPS URL")
    if (
        parsed.hostname not in {"www.thesportsdb.com", "thesportsdb.com"}
        or parsed.port is not None
        or parsed.path.rstrip("/") != "/api/v1/json"
    ):
        raise ValueError(
            "TheSportsDB base_url must use the official HTTPS host and v1 path"
        )


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TheSportsDBError("TheSportsDB timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise TheSportsDBError("TheSportsDB timestamp is invalid") from None
    if parsed.tzinfo is None:
        raise TheSportsDBError("TheSportsDB timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_event_timestamp(value: object) -> datetime:
    """Parse provider event time; TheSportsDB documents naive values as UTC."""

    if not isinstance(value, str) or not value.strip():
        raise TheSportsDBError("TheSportsDB timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise TheSportsDBError("TheSportsDB timestamp is invalid") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _text(value: object, name: str) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise TheSportsDBError(f"TheSportsDB {name} is invalid")
    text = str(value).strip()
    if not text:
        raise TheSportsDBError(f"TheSportsDB {name} is invalid")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise TheSportsDBError("TheSportsDB optional text is invalid")
    text = str(value).strip()
    return text or None


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_exact(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise TheSportsDBError("TheSportsDB immutable snapshot conflicts")
        return
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
