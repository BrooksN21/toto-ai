"""Secret-safe schedule adapter for the documented GOAL API v1."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from toto_ai.external_odds.domain import ProviderEvent, QuotaState

GOAL_API_KEY_ENV = "GOAL_API_KEY"
GOAL_API_BASE_URL_ENV = "GOAL_API_BASE_URL"
DEFAULT_BASE_URL = "https://api.goal-api.com/v1"
PROVIDER_NAME = "goal-api-v1"
USER_AGENT = "TotoAI/1.0 schedule-coverage-canary"

_RETRY_STATUSES = frozenset((408, 429, 500, 502, 503, 504))
_SCHEDULED_STATUSES = frozenset(("scheduled", "not_started"))
_MAX_RETRIES = 3
_MAX_REQUEST_BUDGET = 120
_MAX_WINDOW_SPAN = timedelta(days=5)
_MESSAGE_LIMIT = 240
_OFFICIAL_HOST = "api.goal-api.com"
_OFFICIAL_PATH = "/v1"


@dataclass(frozen=True)
class GoalAPIConfig:
    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 10.0
    max_retries: int = 1
    request_budget: int = 120

    def __post_init__(self) -> None:
        if self.api_key is not None and (
            not isinstance(self.api_key, str) or not self.api_key.strip()
        ):
            raise ValueError("GOAL API key must be non-empty or None")
        _validate_base_url(self.base_url)
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not 0 < float(self.timeout) <= 60
        ):
            raise ValueError("GOAL API timeout must be in (0, 60]")
        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or not 0 <= self.max_retries <= _MAX_RETRIES
        ):
            raise ValueError("GOAL API max_retries must be in range 0 through 3")
        if (
            isinstance(self.request_budget, bool)
            or not isinstance(self.request_budget, int)
            or not 1 <= self.request_budget <= _MAX_REQUEST_BUDGET
        ):
            raise ValueError("GOAL API request_budget must be in range 1..120")

    @property
    def enabled(self) -> bool:
        return self.api_key is not None


@dataclass(frozen=True)
class GoalAPIDiagnostic:
    category: str
    endpoint: str
    attempt: int
    http_status: int | None = None
    quota_daily_limit: int | None = None
    quota_daily_remaining: int | None = None
    quota_daily_reset: int | None = None
    attempted: int = 0
    skipped: int = 0
    budget_exhausted: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "endpoint": self.endpoint,
            "attempt": self.attempt,
            "http_status": self.http_status,
            "quota_daily_limit": self.quota_daily_limit,
            "quota_daily_remaining": self.quota_daily_remaining,
            "quota_daily_reset": self.quota_daily_reset,
            "attempted": self.attempted,
            "skipped": self.skipped,
            "budget_exhausted": self.budget_exhausted,
        }


class GoalAPIError(RuntimeError):
    def __init__(self, message: object, *, secret: str = "") -> None:
        super().__init__(_sanitize(message, secret=secret))


class GoalAPIDisabledError(GoalAPIError):
    pass


@dataclass(frozen=True)
class GoalAPIRequestEvidence:
    endpoint: str
    params: tuple[tuple[str, str], ...]
    request_fingerprint: str
    response_hash: str
    fetched_at: datetime
    snapshot_path: Path
    snapshot_sha256: str


@dataclass(frozen=True)
class GoalAPITeamResults:
    """One secret-safe, frozen GOAL team-results response."""

    team_id: str
    payload: Mapping[str, Any]
    http_status: int
    evidence: GoalAPIRequestEvidence
    quota_daily_remaining: int | None


@dataclass(frozen=True)
class GoalAPIScheduleEvent:
    provider_event_id: str
    competition: str
    home_team: str
    away_team: str
    starts_at: datetime
    status: str
    eligible: bool
    captured_at: datetime
    payload_hash: str
    source_endpoint: str
    request_fingerprint: str
    provider_home_team_id: str | None = None
    provider_away_team_id: str | None = None

    @property
    def source_url(self) -> str:
        return "https://goal-api.com"

    def as_provider_event(self) -> ProviderEvent:
        return ProviderEvent(
            provider=PROVIDER_NAME,
            provider_event_id=self.provider_event_id,
            sport="football",
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


def load_goal_api_config(
    environment: Mapping[str, str] | None = None,
    **overrides: object,
) -> GoalAPIConfig:
    values = os.environ if environment is None else environment
    sentinel = object()
    api_key = overrides.pop("api_key", sentinel)
    if api_key is sentinel:
        api_key = values.get(GOAL_API_KEY_ENV, "").strip() or None
    base_url = overrides.pop("base_url", None)
    if base_url is None:
        base_url = values.get(GOAL_API_BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL
    return GoalAPIConfig(api_key=api_key, base_url=str(base_url), **overrides)


def load_goal_api_key(env_file: str | Path = ".env") -> str | None:
    environment_value = os.environ.get(GOAL_API_KEY_ENV, "").strip()
    if environment_value:
        return environment_value
    path = Path(env_file)
    if not path.is_file():
        return None
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("GOAL API env file permissions must be 0600 or stricter")
    key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if separator and name.strip() == GOAL_API_KEY_ENV:
            candidate = value.strip().strip('"').strip("'")
            if candidate:
                key = candidate
    return key


class GoalAPIClient:
    provider_name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        snapshot_dir: Path = Path("data/external-cache/goal-api-v1"),
        timeout: float = 10.0,
        max_retries: int = 1,
        request_budget: int = 120,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise GoalAPIDisabledError(f"{GOAL_API_KEY_ENV} is required")
        config = GoalAPIConfig(
            api_key=api_key.strip(),
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            request_budget=request_budget,
        )
        self._api_key = api_key.strip()
        self._base_url = config.base_url.rstrip("/")
        self._session = session or requests.Session()
        self._snapshot_dir = Path(snapshot_dir)
        self._timeout = float(config.timeout)
        self._max_retries = config.max_retries
        self._request_budget = config.request_budget
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep or time.sleep
        self._requests_made = 0
        self._requests_skipped = 0
        self._budget_exhausted = False
        self._daily_limit: int | None = None
        self._daily_remaining: int | None = None
        self._daily_reset: int | None = None
        self._diagnostics: list[GoalAPIDiagnostic] = []
        self._evidence: list[GoalAPIRequestEvidence] = []

    @classmethod
    def from_config(cls, config: GoalAPIConfig, **kwargs: object) -> GoalAPIClient:
        if not config.enabled or config.api_key is None:
            raise GoalAPIDisabledError(f"{GOAL_API_KEY_ENV} is required")
        return cls(
            config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
            request_budget=config.request_budget,
            **kwargs,
        )

    @property
    def requests_made(self) -> int:
        return self._requests_made

    @property
    def requests_skipped(self) -> int:
        return self._requests_skipped

    @property
    def budget_exhausted(self) -> bool:
        return self._budget_exhausted

    @property
    def request_diagnostics(self) -> tuple[GoalAPIDiagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def request_evidence(self) -> tuple[GoalAPIRequestEvidence, ...]:
        return tuple(self._evidence)

    @property
    def quota_state(self) -> QuotaState:
        return QuotaState(self._daily_limit, self._daily_remaining, None, None)

    def fetch_schedule(
        self,
        dates: tuple[date, ...],
    ) -> tuple[GoalAPIScheduleEvent, ...]:
        requested = _bounded_dates(dates)
        events: dict[str, GoalAPIScheduleEvent] = {}
        for requested_date in requested:
            offset = 0
            while True:
                endpoint = f"/fixtures/date/{requested_date.isoformat()}"
                payload, pagination = self._get_page(
                    endpoint,
                    {"limit": 100, "offset": offset},
                )
                for raw in payload:
                    event = _parse_event(
                        raw,
                        fetched_at=self._evidence[-1].fetched_at,
                        endpoint=endpoint,
                        request_fingerprint=self._evidence[-1].request_fingerprint,
                    )
                    previous = events.get(event.provider_event_id)
                    if previous is not None and previous != event:
                        raise GoalAPIError(
                            "GOAL API duplicate event identity conflicts"
                        )
                    events[event.provider_event_id] = event
                if not pagination.get("hasMore"):
                    break
                next_offset = pagination.get("nextOffset")
                candidate = (
                    next_offset
                    if type(next_offset) is int
                    else offset + max(1, len(payload))
                )
                if candidate <= offset:
                    raise GoalAPIError("GOAL API pagination did not advance")
                offset = candidate
        allowed = frozenset(requested)
        return tuple(
            event
            for _, event in sorted(events.items())
            if event.starts_at.date() in allowed
        )

    def fetch_team_results(
        self,
        team_id: str,
        *,
        limit: int = 10,
    ) -> GoalAPITeamResults:
        """Fetch and freeze a bounded team history for research-only use."""

        normalized_team_id = _team_identifier(team_id)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 10
        ):
            raise ValueError("GOAL API team-results limit must be in range 1..10")
        endpoint = f"/teams/{normalized_team_id}/results"
        safe_params = (("limit", str(limit)),)
        fingerprint = _request_fingerprint(self._base_url, endpoint, safe_params)
        for attempt in range(1, self._max_retries + 2):
            if self._requests_made >= self._request_budget:
                self._requests_skipped += 1
                self._budget_exhausted = True
                self._record_diagnostic("budget_exhausted", endpoint, attempt)
                raise GoalAPIError("GOAL API request budget exhausted")
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{self._base_url}{endpoint}",
                    params=dict(safe_params),
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                self._record_diagnostic("transport_failure", endpoint, attempt)
                if attempt == self._max_retries + 1:
                    raise GoalAPIError(
                        f"GOAL API transport failed: {type(error).__name__}",
                        secret=self._api_key,
                    ) from None
                self._sleep(0.25 * attempt)
                continue
            self._update_quota(response.headers)
            if response.status_code in _RETRY_STATUSES:
                self._record_diagnostic(
                    "http_retry", endpoint, attempt, response.status_code
                )
                if attempt == self._max_retries + 1:
                    raise GoalAPIError("GOAL API request failed", secret=self._api_key)
                self._sleep(0.25 * attempt)
                continue
            if response.status_code >= 400:
                self._record_diagnostic(
                    "http_failure", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API request failed", secret=self._api_key)
            try:
                body = response.json()
            except (AttributeError, TypeError, ValueError):
                self._record_diagnostic(
                    "invalid_json", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API returned invalid JSON") from None
            if not isinstance(body, Mapping) or body.get("success") is not True:
                self._record_diagnostic(
                    "semantic_error", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API returned an unsuccessful payload")
            if str(body.get("teamId")) != normalized_team_id:
                raise GoalAPIError("GOAL API team-results identity mismatch")
            data = body.get("data")
            if not isinstance(data, list) or len(data) > limit:
                raise GoalAPIError("GOAL API team-results payload shape is invalid")
            observed = _utc(self._now())
            evidence = self._freeze(
                endpoint=endpoint,
                params=safe_params,
                body=dict(body),
                fetched_at=observed,
                request_fingerprint=fingerprint,
            )
            self._evidence.append(evidence)
            self._record_diagnostic("success", endpoint, attempt, response.status_code)
            return GoalAPITeamResults(
                team_id=normalized_team_id,
                payload=dict(body),
                http_status=response.status_code,
                evidence=evidence,
                quota_daily_remaining=self._daily_remaining,
            )
        raise GoalAPIError("GOAL API request failed")

    def _get_page(
        self,
        endpoint: str,
        params: Mapping[str, object],
    ) -> tuple[list[object], Mapping[str, object]]:
        if re.fullmatch(r"/fixtures/date/\d{4}-\d{2}-\d{2}", endpoint) is None:
            raise ValueError("unsupported GOAL API endpoint")
        safe_params = tuple((key, str(value)) for key, value in sorted(params.items()))
        fingerprint = _request_fingerprint(self._base_url, endpoint, safe_params)
        for attempt in range(1, self._max_retries + 2):
            if self._requests_made >= self._request_budget:
                self._requests_skipped += 1
                self._budget_exhausted = True
                self._record_diagnostic("budget_exhausted", endpoint, attempt)
                raise GoalAPIError("GOAL API request budget exhausted")
            try:
                self._requests_made += 1
                response = self._session.get(
                    f"{self._base_url}{endpoint}",
                    params=dict(safe_params),
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=self._timeout,
                )
            except requests.RequestException as error:
                self._record_diagnostic("transport_failure", endpoint, attempt)
                if attempt == self._max_retries + 1:
                    raise GoalAPIError(
                        f"GOAL API transport failed: {type(error).__name__}",
                        secret=self._api_key,
                    ) from None
                self._sleep(0.25 * attempt)
                continue
            self._update_quota(response.headers)
            if response.status_code in _RETRY_STATUSES:
                self._record_diagnostic(
                    "http_retry", endpoint, attempt, response.status_code
                )
                if attempt == self._max_retries + 1:
                    raise GoalAPIError("GOAL API request failed", secret=self._api_key)
                self._sleep(0.25 * attempt)
                continue
            if response.status_code >= 400:
                self._record_diagnostic(
                    "http_failure", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API request failed", secret=self._api_key)
            try:
                body = response.json()
            except (AttributeError, TypeError, ValueError):
                self._record_diagnostic(
                    "invalid_json", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API returned invalid JSON") from None
            if not isinstance(body, Mapping) or body.get("success") is not True:
                self._record_diagnostic(
                    "semantic_error", endpoint, attempt, response.status_code
                )
                raise GoalAPIError("GOAL API returned an unsuccessful payload")
            data = body.get("data")
            pagination = body.get("pagination") or {}
            if not isinstance(data, list) or not isinstance(pagination, Mapping):
                raise GoalAPIError("GOAL API payload shape is invalid")
            observed = _utc(self._now())
            evidence = self._freeze(
                endpoint=endpoint,
                params=safe_params,
                body=dict(body),
                fetched_at=observed,
                request_fingerprint=fingerprint,
            )
            self._evidence.append(evidence)
            self._record_diagnostic("success", endpoint, attempt, response.status_code)
            return data, pagination
        raise GoalAPIError("GOAL API request failed")

    def _update_quota(self, headers: Mapping[str, object]) -> None:
        lowered = {str(key).casefold(): value for key, value in headers.items()}
        self._daily_limit = _optional_int(lowered.get("x-ratelimit-limit"))
        self._daily_remaining = _optional_int(lowered.get("x-ratelimit-remaining"))
        self._daily_reset = _optional_int(lowered.get("x-ratelimit-reset"))

    def _record_diagnostic(
        self,
        category: str,
        endpoint: str,
        attempt: int,
        http_status: int | None = None,
    ) -> None:
        self._diagnostics.append(
            GoalAPIDiagnostic(
                category=category,
                endpoint=endpoint,
                attempt=attempt,
                http_status=http_status,
                quota_daily_limit=self._daily_limit,
                quota_daily_remaining=self._daily_remaining,
                quota_daily_reset=self._daily_reset,
                attempted=self._requests_made,
                skipped=self._requests_skipped,
                budget_exhausted=self._budget_exhausted,
            )
        )

    def _freeze(
        self,
        *,
        endpoint: str,
        params: tuple[tuple[str, str], ...],
        body: dict[str, Any],
        fetched_at: datetime,
        request_fingerprint: str,
    ) -> GoalAPIRequestEvidence:
        response_hash = _sha256_json(body)
        document = {
            "schema_version": 1,
            "provider": PROVIDER_NAME,
            "endpoint": endpoint,
            "params": [list(item) for item in params],
            "request_fingerprint": request_fingerprint,
            "fetched_at": _timestamp(fetched_at),
            "response_hash": response_hash,
            "payload": body,
        }
        content = _canonical(document) + b"\n"
        snapshot_sha256 = hashlib.sha256(content).hexdigest()
        path = (
            self._snapshot_dir
            / "snapshots"
            / f"{request_fingerprint}-{snapshot_sha256[:16]}.json"
        )
        _write_exact(path, content)
        return GoalAPIRequestEvidence(
            endpoint=endpoint,
            params=params,
            request_fingerprint=request_fingerprint,
            response_hash=response_hash,
            fetched_at=fetched_at,
            snapshot_path=path.resolve(),
            snapshot_sha256=snapshot_sha256,
        )


def _parse_event(
    value: object,
    *,
    fetched_at: datetime,
    endpoint: str,
    request_fingerprint: str,
) -> GoalAPIScheduleEvent:
    if not isinstance(value, Mapping):
        raise GoalAPIError("GOAL API fixture must be an object")
    starts_at = _parse_timestamp(value.get("kickoffUtc"))
    status = _normalize_status(value.get("matchStatus"))
    return GoalAPIScheduleEvent(
        provider_event_id=_identifier(value.get("id") or value.get("apiId"), "id"),
        competition=_text(value.get("leagueName"), "leagueName"),
        home_team=_text(value.get("homeTeamName"), "homeTeamName"),
        away_team=_text(value.get("awayTeamName"), "awayTeamName"),
        starts_at=starts_at,
        status=status,
        eligible=status in _SCHEDULED_STATUSES and fetched_at < starts_at,
        captured_at=fetched_at,
        payload_hash=_sha256_json(value),
        source_endpoint=endpoint,
        request_fingerprint=request_fingerprint,
        provider_home_team_id=_optional_identifier(value.get("homeTeamId")),
        provider_away_team_id=_optional_identifier(value.get("awayTeamId")),
    )


def _bounded_dates(values: tuple[date, ...]) -> tuple[date, ...]:
    if not values:
        raise ValueError("GOAL API dates cannot be empty")
    if any(not isinstance(item, date) for item in values):
        raise TypeError("GOAL API dates must contain date values")
    unique = tuple(sorted(set(values)))
    if unique[-1] - unique[0] > _MAX_WINDOW_SPAN:
        raise ValueError("GOAL API date window must span at most 5 days")
    return unique


def _validate_base_url(value: object) -> None:
    if not isinstance(value, str):
        raise TypeError("GOAL API base URL must be a string")
    parsed = urlsplit(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or parsed.hostname != _OFFICIAL_HOST
        or parsed.port is not None
        or parsed.path != _OFFICIAL_PATH
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("GOAL API base URL must be the official HTTPS v1 endpoint")


def _normalize_status(value: object) -> str:
    raw = _text(value, "matchStatus")
    normalized = re.sub(r"[^a-z0-9]+", " ", raw.casefold()).strip()
    if normalized in {"scheduled", "fixture"}:
        return "scheduled"
    if normalized in {"not started", "notstarted", "ns"}:
        return "not_started"
    if normalized in {"postponed", "postponement", "pst"}:
        return "postponed"
    if normalized in {"cancelled", "canceled", "abandoned", "canc"}:
        return "cancelled"
    if normalized in {"finished", "full time", "ft", "aet", "pen"}:
        return "finished"
    return "unknown"


def _request_fingerprint(
    base_url: str,
    endpoint: str,
    params: tuple[tuple[str, str], ...],
) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "provider": PROVIDER_NAME,
                "base_url": base_url,
                "endpoint": endpoint,
                "params": [list(item) for item in params],
            }
        )
    ).hexdigest()


def _sanitize(value: object, *, secret: str = "") -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    return (re.sub(r"\s+", " ", text) or "provider failure")[:_MESSAGE_LIMIT]


def _parse_timestamp(value: object) -> datetime:
    text = _text(value, "kickoffUtc")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise GoalAPIError("GOAL API kickoffUtc is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GoalAPIError("GOAL API kickoffUtc must include a timezone")
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("GOAL API time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoalAPIError(f"GOAL API {name} must be non-empty")
    return value.strip()


def _identifier(value: object, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise GoalAPIError(f"GOAL API {name} must be a string or integer")
    text = str(value).strip()
    if not text:
        raise GoalAPIError(f"GOAL API {name} must be non-empty")
    return text


def _optional_identifier(value: object) -> str | None:
    if value is None:
        return None
    return _identifier(value, "team ID")


def _team_identifier(value: object) -> str:
    identifier = _identifier(value, "team ID")
    if re.fullmatch(r"[A-Za-z0-9_-]+", identifier) is None:
        raise ValueError("GOAL API team ID contains unsupported characters")
    return identifier


def _optional_int(value: object) -> int | None:
    try:
        return None if value is None else int(str(value))
    except ValueError:
        return None


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_exact(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != content:
            raise GoalAPIError("GOAL API immutable snapshot conflicts") from None
