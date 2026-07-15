from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from toto_ai.external_odds.collection import (
    ExternalCollectionSnapshot,
    collect_target_external_odds,
    resolve_open_target,
)
from toto_ai.external_odds.domain import ExternalOddsProvider, TargetDrawing

ProspectiveStopReason = Literal["no_retryable_fallbacks", "max_passes"]
ProviderFactory = Callable[[Path], ExternalOddsProvider]
_RETRYABLE_EXACT_REASONS = frozenset(("quota reserve reached",))
_RETRYABLE_REASON_PREFIXES = (
    "provider schedule failure:",
    "provider odds failure:",
)


@dataclass(frozen=True)
class ProspectiveCollectionPass:
    snapshot: ExternalCollectionSnapshot
    elapsed_seconds: float


@dataclass(frozen=True)
class ProspectiveCollectionResult:
    snapshot: ExternalCollectionSnapshot
    passes: tuple[ProspectiveCollectionPass, ...]
    cache_dir: Path
    elapsed_seconds: float
    stop_reason: ProspectiveStopReason
    total_requests: int
    total_cache_hits: int


def fresh_cache_session_dir(
    cache_root: Path,
    target: TargetDrawing,
    started_at: datetime,
) -> Path:
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")
    drawing_label = target.drawing_number or target.drawing_id
    timestamp = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return Path(cache_root) / "runs" / f"{drawing_label}-{timestamp}-{uuid4().hex}"


def is_retryable_snapshot(snapshot: ExternalCollectionSnapshot) -> bool:
    return any(
        _is_retryable_reason(event.fallback_reason) for event in snapshot.events
    )


def collect_fresh_open_external_odds(
    *,
    totobrief_client: Any,
    provider_factory: ProviderFactory,
    session_factory: Any,
    aliases: dict[str, str],
    cache_root: Path,
    max_passes: int = 3,
    retry_delay_seconds: float = 65.0,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> ProspectiveCollectionResult:
    _validate_options(max_passes, retry_delay_seconds)
    started = monotonic()
    started_at = now()
    target = resolve_open_target(totobrief_client, fetched_at=started_at)
    cache_dir = fresh_cache_session_dir(cache_root, target, started_at)
    passes: list[ProspectiveCollectionPass] = []
    stop_reason: ProspectiveStopReason = "max_passes"

    for pass_index in range(max_passes):
        pass_started = monotonic()
        snapshot = collect_target_external_odds(
            target,
            provider_factory(cache_dir),
            session_factory,
            aliases,
        )
        passes.append(
            ProspectiveCollectionPass(
                snapshot=snapshot,
                elapsed_seconds=monotonic() - pass_started,
            )
        )
        if not is_retryable_snapshot(snapshot):
            stop_reason = "no_retryable_fallbacks"
            break
        if pass_index + 1 < max_passes:
            sleep(retry_delay_seconds)

    final_snapshot = passes[-1].snapshot
    return ProspectiveCollectionResult(
        snapshot=final_snapshot,
        passes=tuple(passes),
        cache_dir=cache_dir,
        elapsed_seconds=monotonic() - started,
        stop_reason=stop_reason,
        total_requests=sum(item.snapshot.requests_made for item in passes),
        total_cache_hits=sum(item.snapshot.cache_hits for item in passes),
    )


def _is_retryable_reason(reason: str | None) -> bool:
    if reason is None:
        return False
    return reason in _RETRYABLE_EXACT_REASONS or reason.startswith(
        _RETRYABLE_REASON_PREFIXES
    )


def _validate_options(max_passes: int, retry_delay_seconds: float) -> None:
    if (
        not isinstance(max_passes, int)
        or isinstance(max_passes, bool)
        or max_passes <= 0
    ):
        raise ValueError("max_passes must be a positive integer")
    if (
        not isinstance(retry_delay_seconds, (int, float))
        or isinstance(retry_delay_seconds, bool)
        or not isfinite(float(retry_delay_seconds))
        or retry_delay_seconds < 0
    ):
        raise ValueError("retry_delay_seconds must be finite and non-negative")
