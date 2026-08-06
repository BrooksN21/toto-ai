from __future__ import annotations

import email.utils
import fcntl
import json
import math
import os
import random as random_module
import re
import socket
import ssl
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from toto_ai.api.safe_paths import (
    fsync_directory,
    prepare_contained_parent,
    resolve_contained_path,
)

RATE_STATE_SCHEMA_VERSION = 2
DEFAULT_RATE_STATE_PATH = Path("data/totobrief-cache/request-state.json")
DEFAULT_MAXIMUM_WAIT_SECONDS = 300.0
DEFAULT_MAXIMUM_PLAUSIBLE_BLOCK_SECONDS = 7 * 24 * 60 * 60.0

_RETRYABLE_TRANSPORT_EXCEPTIONS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
)

TRANSPORT_CATEGORIES = frozenset(
    {
        "ssl_verify",
        "ssl_handshake",
        "dns",
        "connect",
        "timeout",
        "http",
    }
)

_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|api[_-]?key|token|secret|password)\b\s*[:=]\s*"
    r"(?:bearer\s+)?[^,\s;]+"
)
_URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]*", re.IGNORECASE)


class TotoBriefRequestError(RuntimeError):
    """A sanitized, bounded TotoBrief transport failure."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        attempts: int,
        status_code: int | None = None,
        category: str = "http",
        original_transport_message: str | None = None,
        exception_chain: tuple[str, ...] = (),
    ) -> None:
        if category not in TRANSPORT_CATEGORIES:
            raise ValueError("unsupported TotoBrief transport category")
        safe_original = sanitize_transport_message(
            original_transport_message
            if original_transport_message is not None
            else message
        )
        super().__init__(message)
        self.endpoint = endpoint
        self.attempts = attempts
        self.status_code = status_code
        self.category = category
        self.original_transport_message = safe_original
        self.exception_chain = tuple(exception_chain)

    def failure_detail(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "attempt_count": self.attempts,
            "status_code": self.status_code,
            "endpoint": self.endpoint,
            "original_transport_message": self.original_transport_message,
            "exception_chain": list(self.exception_chain),
        }


@dataclass(frozen=True)
class RequestDiagnostic:
    event: str
    endpoint: str
    attempt: int
    wait_seconds: float = 0.0
    status_code: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _RateState:
    written_at: float | None = None
    last_request_at: float | None = None
    blocked_until: float | None = None
    block_source: str | None = None


class TotoBriefRequestCoordinator:
    """Coordinate TotoBrief requests across retries and CLI processes.

    The state file contains only request timing metadata. The lock is held while
    a process waits for and reserves its request slot, so two independent CLI
    invocations cannot issue adjacent requests inside ``minimum_interval``.
    """

    def __init__(
        self,
        *,
        state_path: str | Path = DEFAULT_RATE_STATE_PATH,
        minimum_interval: float = 2.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        jitter_ratio: float = 0.2,
        state_ttl_seconds: float = 3600.0,
        max_future_skew_seconds: float = 300.0,
        maximum_wait_seconds: float = DEFAULT_MAXIMUM_WAIT_SECONDS,
        maximum_plausible_block_seconds: float = (
            DEFAULT_MAXIMUM_PLAUSIBLE_BLOCK_SECONDS
        ),
        allowed_root: str | Path = ".",
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        random: Callable[[], float] | None = None,
        diagnostic_callback: Callable[[RequestDiagnostic], None] | None = None,
    ) -> None:
        if not math.isfinite(minimum_interval) or minimum_interval < 0:
            raise ValueError("minimum_interval must be finite and non-negative")
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        for name, value in (
            ("backoff_base", backoff_base),
            ("backoff_cap", backoff_cap),
            ("state_ttl_seconds", state_ttl_seconds),
            ("max_future_skew_seconds", max_future_skew_seconds),
            ("maximum_wait_seconds", maximum_wait_seconds),
            ("maximum_plausible_block_seconds", maximum_plausible_block_seconds),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not math.isfinite(jitter_ratio) or not 0 <= jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")

        self.allowed_root = Path(allowed_root)
        self.state_path = resolve_contained_path(
            state_path,
            allowed_root=self.allowed_root,
        )
        self.lock_path = resolve_contained_path(
            self.state_path.with_suffix(self.state_path.suffix + ".lock"),
            allowed_root=self.allowed_root,
        )
        self.minimum_interval = float(minimum_interval)
        self.max_retries = max_retries
        self.backoff_base = float(backoff_base)
        self.backoff_cap = float(backoff_cap)
        self.jitter_ratio = float(jitter_ratio)
        self.state_ttl_seconds = float(state_ttl_seconds)
        self.max_future_skew_seconds = float(max_future_skew_seconds)
        self.maximum_wait_seconds = float(maximum_wait_seconds)
        self.maximum_plausible_block_seconds = float(
            maximum_plausible_block_seconds
        )
        self.clock = clock
        self.sleep = sleep
        self.random = random or random_module.random
        self.diagnostic_callback = diagnostic_callback
        self.total_wait_seconds = 0.0
        self.request_attempts = 0
        self.last_request_attempts = 0

    def request(
        self,
        request_call: Callable[[], Any],
        *,
        endpoint: str,
    ) -> Any:
        """Run one sanitized request with bounded retry and shared pacing."""
        safe_endpoint = sanitize_endpoint(endpoint)
        attempts_allowed = self.max_retries + 1
        last_status: int | None = None
        self.last_request_attempts = 0

        for attempt in range(1, attempts_allowed + 1):
            self._reserve_request_slot(endpoint=safe_endpoint, attempt=attempt)
            self.request_attempts += 1
            self.last_request_attempts = attempt
            self._emit("attempt", safe_endpoint, attempt)
            try:
                response = request_call()
            except _RETRYABLE_TRANSPORT_EXCEPTIONS as error:
                delay = self._backoff_delay(attempt)
                self._publish_block(delay, source="backoff")
                category = classify_transport_error(error)
                original_message = sanitize_transport_message(str(error))
                chain = exception_chain_types(error)
                if attempt >= attempts_allowed:
                    self._emit(
                        "failure",
                        safe_endpoint,
                        attempt,
                        reason=type(error).__name__,
                    )
                    raise TotoBriefRequestError(
                        f"TotoBrief request failed after {attempt} attempt(s): "
                        f"{type(error).__name__}",
                        endpoint=safe_endpoint,
                        attempts=attempt,
                        category=category,
                        original_transport_message=original_message,
                        exception_chain=chain,
                    ) from error
                self._emit(
                    "retry",
                    safe_endpoint,
                    attempt,
                    wait_seconds=delay,
                    reason=type(error).__name__,
                )
                continue

            status = getattr(response, "status_code", None)
            if status is not None and type(status) is int:
                last_status = status
            if _is_retryable_status(last_status):
                retry_after = _parse_retry_after(
                    getattr(response, "headers", {}).get("Retry-After"),
                    now=self.clock(),
                )
                delay = max(self._backoff_delay(attempt), retry_after or 0.0)
                self._publish_block(
                    delay,
                    source="retry-after" if retry_after is not None else "backoff",
                )
                if attempt >= attempts_allowed:
                    self._emit(
                        "failure",
                        safe_endpoint,
                        attempt,
                        status_code=last_status,
                        reason="retry budget exhausted",
                    )
                    raise TotoBriefRequestError(
                        f"TotoBrief request returned HTTP {last_status} after "
                        f"{attempt} attempt(s)",
                        endpoint=safe_endpoint,
                        attempts=attempt,
                        status_code=last_status,
                        category="http",
                        original_transport_message=f"HTTP {last_status}",
                        exception_chain=(),
                    )
                self._emit(
                    "retry",
                    safe_endpoint,
                    attempt,
                    wait_seconds=delay,
                    status_code=last_status,
                    reason="Retry-After" if retry_after is not None else "backoff",
                )
                continue

            try:
                response.raise_for_status()
            except requests.RequestException as error:
                status_code = getattr(response, "status_code", last_status)
                self._emit(
                    "failure",
                    safe_endpoint,
                    attempt,
                    status_code=status_code,
                    reason="non-retryable HTTP error",
                )
                raise TotoBriefRequestError(
                    f"TotoBrief request returned HTTP {status_code}",
                    endpoint=safe_endpoint,
                    attempts=attempt,
                    status_code=status_code,
                    category="http",
                    original_transport_message=str(error),
                    exception_chain=exception_chain_types(error),
                ) from error

            self._emit(
                "success",
                safe_endpoint,
                attempt,
                status_code=last_status,
            )
            return response

        raise TotoBriefRequestError(
            "TotoBrief request retry loop ended unexpectedly",
            endpoint=safe_endpoint,
            attempts=attempts_allowed,
            status_code=last_status,
        )

    def _reserve_request_slot(self, *, endpoint: str, attempt: int) -> None:
        self._prepare_paths()
        with self.lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                now = self.clock()
                state, recovered_reason = self._read_state_unlocked(now)
                if recovered_reason is not None:
                    self._emit(
                        "state-recovered",
                        endpoint,
                        attempt,
                        reason=recovered_reason,
                    )
                earliest = now
                if state.last_request_at is not None:
                    earliest = max(
                        earliest,
                        state.last_request_at + self.minimum_interval,
                    )
                if state.blocked_until is not None:
                    earliest = max(earliest, state.blocked_until)
                wait_seconds = max(0.0, earliest - now)
                if wait_seconds:
                    if wait_seconds > self.maximum_wait_seconds:
                        self._emit(
                            "deferred",
                            endpoint,
                            attempt,
                            wait_seconds=wait_seconds,
                            status_code=(
                                429 if state.block_source == "retry-after" else None
                            ),
                            reason="shared wait exceeds configured bound",
                        )
                        raise TotoBriefRequestError(
                            "TotoBrief request deferred because the shared wait "
                            "exceeds the configured bound",
                            endpoint=endpoint,
                            attempts=attempt - 1,
                            status_code=(
                                429 if state.block_source == "retry-after" else None
                            ),
                        )
                    self.total_wait_seconds += wait_seconds
                    self._emit(
                        "wait",
                        endpoint,
                        attempt,
                        wait_seconds=wait_seconds,
                        reason="shared rate limit",
                    )
                    self.sleep(wait_seconds)
                reserved_at = max(self.clock(), earliest)
                self._write_state_unlocked(
                    _RateState(
                        written_at=reserved_at,
                        last_request_at=reserved_at,
                    )
                )
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _publish_block(self, delay: float, *, source: str) -> None:
        self._prepare_paths()
        with self.lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                now = self.clock()
                state, _ = self._read_state_unlocked(now)
                blocked_until = max(state.blocked_until or now, now + delay)
                self._write_state_unlocked(
                    _RateState(
                        written_at=now,
                        last_request_at=state.last_request_at,
                        blocked_until=blocked_until,
                        block_source=(
                            "retry-after"
                            if source == "retry-after"
                            or state.block_source == "retry-after"
                            else "backoff"
                        ),
                    )
                )
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_state_unlocked(self, now: float) -> tuple[_RateState, str | None]:
        if not self.state_path.exists():
            return _RateState(), None
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("state is not an object")
            if raw.get("schema_version") != RATE_STATE_SCHEMA_VERSION:
                raise ValueError("unsupported state schema")
            written_at = _optional_finite_number(raw.get("written_at"))
            last_request_at = _optional_finite_number(raw.get("last_request_at"))
            blocked_until = _optional_finite_number(raw.get("blocked_until"))
            block_source = raw.get("block_source")
            if block_source not in (None, "backoff", "retry-after"):
                raise ValueError("invalid block source")
            if written_at is None:
                raise ValueError("missing state written_at")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            # A corrupt state cannot be treated as permission to burst. Reserve
            # one conservative interval, then replace it atomically.
            return (
                _RateState(
                    written_at=now,
                    last_request_at=now,
                    blocked_until=now + self.minimum_interval,
                    block_source="backoff",
                ),
                "corrupt state reset conservatively",
            )

        if written_at > now + self.max_future_skew_seconds:
            return (
                _RateState(
                    written_at=now,
                    last_request_at=now,
                    blocked_until=now + self.minimum_interval,
                    block_source="backoff",
                ),
                "future written_at reset conservatively",
            )
        if (
            last_request_at is not None
            and last_request_at > written_at + self.max_future_skew_seconds
        ):
            return self._corrupt_state(now, "implausible request timestamp")
        if blocked_until is not None:
            if block_source is None:
                return self._corrupt_state(now, "blocked state has no source")
            block_duration = blocked_until - written_at
            if (
                block_duration < -self.max_future_skew_seconds
                or block_duration > self.maximum_plausible_block_seconds
            ):
                return self._corrupt_state(now, "implausible blocked interval")
        elif block_source is not None:
            return self._corrupt_state(now, "block source without blocked interval")
        if (
            written_at < now - self.state_ttl_seconds
            and (blocked_until is None or blocked_until <= now)
        ):
            return _RateState(), "stale state ignored"
        return _RateState(
            written_at,
            last_request_at,
            blocked_until,
            block_source,
        ), None

    def _write_state_unlocked(self, state: _RateState) -> None:
        payload = {
            "schema_version": RATE_STATE_SCHEMA_VERSION,
            "written_at": state.written_at,
            "last_request_at": state.last_request_at,
            "blocked_until": state.blocked_until,
            "block_source": state.block_source,
        }
        temporary = self.state_path.with_name(
            f".{self.state_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open("xb") as stream:
                stream.write(
                    (
                        json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
            fsync_directory(self.state_path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _backoff_delay(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
        jitter = base * self.jitter_ratio * min(max(self.random(), 0.0), 1.0)
        return min(self.backoff_cap, base + jitter)

    def _prepare_paths(self) -> None:
        self.state_path = prepare_contained_parent(
            self.state_path,
            allowed_root=self.allowed_root,
        )
        self.lock_path = prepare_contained_parent(
            self.lock_path,
            allowed_root=self.allowed_root,
        )

    def _corrupt_state(self, now: float, reason: str) -> tuple[_RateState, str]:
        return (
            _RateState(
                written_at=now,
                last_request_at=now,
                blocked_until=now + self.minimum_interval,
                block_source="backoff",
            ),
            f"{reason} reset conservatively",
        )

    def _emit(
        self,
        event: str,
        endpoint: str,
        attempt: int,
        *,
        wait_seconds: float = 0.0,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        if self.diagnostic_callback is None:
            return
        self.diagnostic_callback(
            RequestDiagnostic(
                event=event,
                endpoint=endpoint,
                attempt=attempt,
                wait_seconds=wait_seconds,
                status_code=status_code,
                reason=reason,
            )
        )


class UncoordinatedRequestCoordinator:
    """Compatibility coordinator for explicitly injected test sessions."""

    total_wait_seconds = 0.0
    request_attempts = 0
    last_request_attempts = 0

    def request(self, request_call: Callable[[], Any], *, endpoint: str) -> Any:
        del endpoint
        self.request_attempts += 1
        self.last_request_attempts = 1
        return request_call()


def _is_retryable_status(status_code: int | None) -> bool:
    return status_code == 429 or (
        status_code is not None and 500 <= status_code <= 599
    )


def _parse_retry_after(value: Any, *, now: float) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, parsed.timestamp() - now)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def _optional_finite_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("state timestamp must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError("state timestamp must be finite and non-negative")
    return parsed


def sanitize_endpoint(endpoint: str) -> str:
    # Query strings may contain caller-controlled data and are unnecessary for
    # operator diagnostics. TotoBrief itself has no credentials in the path.
    return endpoint.split("?", 1)[0]


def sanitize_transport_message(message: object) -> str:
    """Return bounded transport diagnostics without URLs, headers, or secrets."""
    text = str(message).replace("\r", " ").replace("\n", " ").strip()
    text = _URL_QUERY_PATTERN.sub(r"\1?[REDACTED]", text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1=[REDACTED]", text)
    text = re.sub(r"\s+", " ", text)
    return (text or "transport failure")[:512]


def exception_chain_types(error: BaseException) -> tuple[str, ...]:
    """Preserve safe structural cause evidence without exception messages."""
    result: list[str] = []
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        result.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return tuple(result)


def classify_transport_error(error: BaseException) -> str:
    """Classify a transport chain structurally, inspecting SSL text only locally."""
    current: BaseException | None = error
    visited: set[int] = set()
    chain: list[BaseException] = []
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    if any(isinstance(item, (requests.Timeout, TimeoutError)) for item in chain):
        return "timeout"
    if any(isinstance(item, socket.gaierror) for item in chain):
        return "dns"

    ssl_errors = [
        item
        for item in chain
        if isinstance(item, (requests.exceptions.SSLError, ssl.SSLError))
    ]
    if ssl_errors:
        ssl_text = " ".join(str(item).casefold() for item in ssl_errors)
        verify_markers = (
            "certificate verify failed",
            "certificate_verify_failed",
            "hostname mismatch",
            "self signed certificate",
            "unable to get local issuer",
        )
        if any(marker in ssl_text for marker in verify_markers):
            return "ssl_verify"
        return "ssl_handshake"

    if any(
        isinstance(
            item,
            (
                requests.ConnectionError,
                ConnectionError,
                ConnectionResetError,
                ConnectionRefusedError,
            ),
        )
        for item in chain
    ):
        return "connect"
    return "connect"


def utc_now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()
