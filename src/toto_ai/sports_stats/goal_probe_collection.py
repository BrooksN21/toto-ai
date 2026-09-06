"""Collect a frozen 15-event GOAL sports-shadow input — research only."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.goal_api import (
    PROVIDER_NAME,
    GoalAPIClient,
    GoalAPIConfig,
    GoalAPITeamResults,
)
from toto_ai.external_odds.schedule_source_collector import (
    collect_schedule_source_candidates,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.thesportsdb import TheSportsDBConfig

_TERMINAL_STATUSES = frozenset(("FINISHED", "AFTER_ET", "AFTER_PEN"))
_FAILED_CACHE_RETRY_COOLDOWN_SECONDS = 15 * 60
_FAILED_CACHE_RETRY_WINDOW_SECONDS = 60 * 60
_FAILED_CACHE_RETRY_WINDOW_BUDGET = 120


class GoalProbeCacheError(ValueError):
    """Structured retry disposition for the existing caller cadence."""

    def __init__(self, reason: str, *, next_retry_at: datetime | None = None):
        super().__init__(f"GOAL probe {reason}")
        self.reason = reason
        self.retryable = next_retry_at is not None
        self.next_retry_at = next_retry_at


def goal_probe_failure_status(error: Exception) -> dict[str, object]:
    """Unknown validation/integrity errors are not advertised as recoverable."""
    next_retry = getattr(error, "next_retry_at", None)
    return {
        "retryable": bool(getattr(error, "retryable", False)),
        "retry_reason": getattr(error, "reason", "collection_or_validation_error"),
        "next_retry_at": _timestamp(next_retry) if next_retry is not None else None,
    }


@dataclass(frozen=True)
class GoalProbeCollection:
    coverage_summary_path: Path
    schedule_report_path: Path
    captured_at: datetime
    event_count: int
    history_source_count: int
    sports_eligible_count: int
    request_count: int
    quota_daily_remaining: int | None
    reused: bool = False


def ensure_goal_probe_input(
    *,
    drawing_id: int,
    raw_cache_dir: str | Path,
    output_root: str | Path,
    api_key: str,
    request_budget: int = 120,
    project_root: str | Path = ".",
    captured_at: datetime | None = None,
) -> GoalProbeCollection:
    """Reuse good captures; recover failed caches via bounded immutable attempts."""
    root = Path(project_root).resolve()
    output = _contained_directory(root, output_root, create=True)
    observed = _utc(captured_at or datetime.now(timezone.utc))
    marker_path = output / "current.json"
    kwargs = dict(
        drawing_id=drawing_id,
        raw_cache_dir=raw_cache_dir,
        output=output,
        api_key=api_key,
        request_budget=request_budget,
        root=root,
        observed=observed,
    )
    if marker_path.is_file():
        cached = _load_current_collection(
            root=root,
            marker_path=marker_path,
            drawing_id=drawing_id,
        )
        if _failed_goal_source(cached) is None:
            return cached
        return _retry_failed_goal_probe_input(
            cached=cached,
            original_marker=marker_path,
            clock=(lambda: observed)
            if captured_at is not None
            else (lambda: datetime.now(timezone.utc)),
            **kwargs,
        )
    result = _capture_goal_probe_input(marker_path=marker_path, **kwargs)
    _raise_source_failure(result)
    return result


def _raise_source_failure(result: GoalProbeCollection) -> None:
    failure = _failed_goal_source(result)
    if failure is None:
        return
    if failure.get("budget_exhausted") is True:
        raise GoalProbeCacheError("source budget exhausted")
    if result.quota_daily_remaining == 0:
        raise GoalProbeCacheError("source quota exhausted")
    raise GoalProbeCacheError(
        "source failed; no usable fresh cache",
        next_retry_at=result.captured_at
        + timedelta(seconds=_FAILED_CACHE_RETRY_COOLDOWN_SECONDS),
    )


def _retry_failed_goal_probe_input(
    *,
    cached: GoalProbeCollection,
    original_marker: Path,
    drawing_id: int,
    raw_cache_dir: str | Path,
    output: Path,
    api_key: str,
    request_budget: int,
    root: Path,
    observed: datetime,
    clock: Callable[[], datetime],
) -> GoalProbeCollection:
    # Validate before reserving any requests. No retry loop or provider preflight.
    GoalAPIConfig(api_key=api_key, request_budget=request_budget)
    retry_of = _sha256_file(original_marker)
    retry_root = _contained_directory(
        root,
        output / "failed-cache-retry" / retry_of,
        create=True,
    )
    # OS lock is held across collection; process death releases it. A lease alone
    # would allow an expired but still-running collector to overlap its successor.
    with (retry_root / "active.lock").open("ab") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise GoalProbeCacheError(
                "retry already claimed; active collector",
                next_retry_at=observed
                + timedelta(seconds=_FAILED_CACHE_RETRY_COOLDOWN_SECONDS),
            ) from error
        try:
            return _retry_locked(
                cached=cached,
                retry_root=retry_root,
                retry_of=retry_of,
                drawing_id=drawing_id,
                raw_cache_dir=raw_cache_dir,
                output=output,
                api_key=api_key,
                request_budget=request_budget,
                root=root,
                observed=observed,
                clock=clock,
            )
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _retry_locked(
    *,
    cached: GoalProbeCollection,
    retry_root: Path,
    retry_of: str,
    drawing_id: int,
    raw_cache_dir: str | Path,
    output: Path,
    api_key: str,
    request_budget: int,
    root: Path,
    observed: datetime,
    clock: Callable[[], datetime],
) -> GoalProbeCollection:
    cooldown = timedelta(seconds=_FAILED_CACHE_RETRY_COOLDOWN_SECONDS)
    next_eligible = cached.captured_at + cooldown
    quota = cached.quota_daily_remaining
    reserved = 0
    window_claims: list[tuple[datetime, int]] = []
    attempts = retry_root / "attempts"
    # The root entry also supports evidence from the previous one-shot version.
    generations = [retry_root, *sorted(attempts.glob("[0-9]*"))]
    count = 0
    for generation in generations:
        claim_path = generation / "attempt.json"
        marker_path = generation / "current.json"
        if not claim_path.is_file():
            if marker_path.is_file():
                raise GoalProbeCacheError("retry marker without claim")
            continue
        claim = _json_object(claim_path)
        if (
            claim.get("retry_of_sha256") != retry_of
            or claim.get("drawing_id") != drawing_id
        ):
            raise GoalProbeCacheError("retry claim binding mismatch")
        claimed_at = _parse_utc(claim.get("claimed_at"), "claimed_at")
        budget = claim.get("request_budget")
        if (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or not 1 <= budget <= 120
        ):
            raise GoalProbeCacheError("retry claim budget invalid")
        count += 1
        reserved += budget  # Unknown/crashed work spends its full reservation.
        next_eligible = max(next_eligible, claimed_at + cooldown)
        window_claims.append((claimed_at, budget))
        if marker_path.is_file():
            if _json_object(marker_path).get("retry_of_sha256") != retry_of:
                raise GoalProbeCacheError("retry marker binding mismatch")
            result = _load_current_collection(
                root=root,
                marker_path=marker_path,
                drawing_id=drawing_id,
            )
            if _failed_goal_source(result) is None:
                return result
            next_eligible = max(next_eligible, result.captured_at + cooldown)
            if _failed_goal_source(result).get("budget_exhausted") is True:
                raise GoalProbeCacheError("source budget exhausted")
            if result.quota_daily_remaining is not None:
                # Bound remaining requests by every observed quota, including
                # requests reserved after that observation.
                quota = (
                    min(quota, result.quota_daily_remaining + reserved)
                    if quota is not None
                    else result.quota_daily_remaining + reserved
                )
        outcome_path = generation / "outcome.json"
        if outcome_path.is_file():
            outcome = _json_object(outcome_path)
            if outcome.get("claim_sha256") != _sha256_file(claim_path):
                raise GoalProbeCacheError("retry outcome binding mismatch")
            if outcome.get("status") == "FAILED" and outcome.get("retryable") is False:
                raise GoalProbeCacheError(
                    str(outcome.get("retry_reason", "terminal collection failure"))
                )
            next_eligible = max(
                next_eligible,
                _parse_utc(outcome.get("finished_at"), "finished_at") + cooldown,
            )
        elif not marker_path.is_file() and observed >= claimed_at + cooldown:
            # Append crash recovery evidence; never rewrite the original claim.
            _write_exact(
                generation / "expired.json",
                _pretty(
                    {
                        "schema_version": 1,
                        "status": "LEASE_EXPIRED",
                        "claim_sha256": _sha256_file(claim_path),
                        "next_retry_at": _timestamp(claimed_at + cooldown),
                        "reserved_requests": budget,
                    }
                ),
            )
    if _failed_goal_source(cached).get("budget_exhausted") is True:
        raise GoalProbeCacheError("cached source budget exhausted")
    if quota is not None and quota - reserved < request_budget:
        raise GoalProbeCacheError("source quota exhausted or insufficient reservation")
    if observed < next_eligible:
        raise GoalProbeCacheError("retry cooldown active", next_retry_at=next_eligible)
    # Fixed rolling-hour cap cannot be enlarged by changing the caller budget.
    window = timedelta(seconds=_FAILED_CACHE_RETRY_WINDOW_SECONDS)
    recent = [
        (when, budget) for when, budget in window_claims if when + window > observed
    ]
    used = sum(budget for _, budget in recent)
    if used + request_budget > _FAILED_CACHE_RETRY_WINDOW_BUDGET:
        for when, budget in sorted(recent):
            used -= budget
            if used + request_budget <= _FAILED_CACHE_RETRY_WINDOW_BUDGET:
                raise GoalProbeCacheError(
                    "retry request window budget exhausted",
                    next_retry_at=when + window,
                )
    generation = _contained_directory(
        root,
        attempts / f"{count + 1:06d}",
        create=True,
    )
    claim_path = generation / "attempt.json"
    claim = {
        "schema_version": 2,
        "status": "RESERVED",
        "drawing_id": drawing_id,
        "retry_of_sha256": retry_of,
        "claimed_at": _timestamp(observed),
        "lease_expires_at": _timestamp(observed + cooldown),
        "next_retry_at": _timestamp(observed + cooldown),
        "request_budget": request_budget,
        "automatic_wagering": False,
        "package_influence": "NONE",
    }
    _publish_retry_record(
        claim_path, _pretty(claim), durable_root=output, exclusive=True
    )
    outcome = {
        "schema_version": 1,
        "claim_sha256": _sha256_file(claim_path),
        "finished_at": _timestamp(observed),
        "reserved_requests": request_budget,
        "automatic_wagering": False,
        "package_influence": "NONE",
    }
    try:
        result = _capture_goal_probe_input(
            marker_path=generation / "current.json",
            retry_of=retry_of,
            drawing_id=drawing_id,
            raw_cache_dir=raw_cache_dir,
            output=output,
            api_key=api_key,
            request_budget=request_budget,
            root=root,
            observed=observed,
        )
        outcome["finished_at"] = _timestamp(max(observed, result.captured_at, clock()))
        _raise_source_failure(result)
    except Exception as error:
        finished = max(observed, clock())
        outcome["finished_at"] = _timestamp(finished)
        if isinstance(error, GoalProbeCacheError):
            failure = error
            if failure.retryable:
                failure = GoalProbeCacheError(
                    failure.reason,
                    next_retry_at=max(failure.next_retry_at, finished + cooldown),
                )
        elif str(error) in {
            "GOAL probe collection must finish before drawing deadline",
            "GOAL probe collection crossed the drawing deadline",
        }:
            failure = GoalProbeCacheError("drawing deadline expired")
        else:
            failure = GoalProbeCacheError(
                "retry collection interrupted",
                next_retry_at=finished + cooldown,
            )
        outcome.update(status="FAILED", **goal_probe_failure_status(failure))
        _publish_retry_record(
            generation / "outcome.json", _pretty(outcome), durable_root=output
        )
        raise failure from error
    outcome.update(status="READY", retryable=False, next_retry_at=None)
    _publish_retry_record(
        generation / "outcome.json", _pretty(outcome), durable_root=output
    )
    return result


def _publish_retry_record(
    path: Path, content: bytes, *, durable_root: Path, exclusive: bool = False
) -> None:
    """Publish complete retry metadata without exposing partial committed JSON.

    Staging files are append-only evidence. No provider request starts before the
    claim is linked; an interrupted outcome leaves the complete claim recoverable.
    The enclosing flock remains held throughout publication and collection.
    """
    if not path.parent.is_relative_to(durable_root):
        raise ValueError("retry publication escapes durability root")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if exclusive:
            raise FileExistsError(f"GOAL probe retry claim already exists: {path}")
        if path.read_bytes() != content:
            raise ValueError(f"GOAL probe artifact conflict: {path}")
        _sync_retry_directories(path.parent, durable_root)
        return
    pending = path.with_name(f".{path.name}.{uuid4().hex}.pending")
    with pending.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    # Same-directory hard-link publication is atomic and cannot replace evidence.
    os.link(pending, path)
    _sync_retry_directories(path.parent, durable_root)


def _sync_retry_directories(directory: Path, durable_root: Path) -> None:
    # Bottom-up syncing persists the final link and every newly-created ancestor
    # through the already-existing cache root, before collection or acknowledgement.
    while True:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if directory == durable_root:
            return
        directory = directory.parent


def _capture_goal_probe_input(
    *,
    marker_path: Path,
    drawing_id: int,
    raw_cache_dir: str | Path,
    output: Path,
    api_key: str,
    request_budget: int,
    root: Path,
    observed: datetime,
    retry_of: str | None = None,
) -> GoalProbeCollection:
    capture_id = observed.strftime("%Y%m%dT%H%M%S%fZ")
    capture = output / "captures" / capture_id
    client = GoalAPIClient(
        api_key,
        snapshot_dir=capture / "schedule" / "goal-api-v1",
        request_budget=request_budget,
    )
    result = collect_goal_probe_input(
        drawing_id=drawing_id,
        queue_path=None,
        raw_cache_dir=raw_cache_dir,
        output_dir=capture,
        client=client,
        project_root=root,
        captured_at=observed,
    )
    marker = {
        "schema_version": 1,
        "status": "PAPER_ONLY_COVERAGE_PROBE_READY",
        "drawing_id": drawing_id,
        "captured_at": _timestamp(result.captured_at),
        "coverage_summary_path": result.coverage_summary_path.relative_to(
            root
        ).as_posix(),
        "coverage_summary_sha256": _sha256_file(result.coverage_summary_path),
        "schedule_report_path": result.schedule_report_path.relative_to(
            root
        ).as_posix(),
        "schedule_report_sha256": _sha256_file(result.schedule_report_path),
        "event_count": result.event_count,
        "history_source_count": result.history_source_count,
        "sports_eligible_count": result.sports_eligible_count,
        "request_count": result.request_count,
        "quota_daily_remaining": result.quota_daily_remaining,
        "package_influence": "NONE",
        "automatic_wagering": False,
    }
    if retry_of is not None:
        marker["retry_of_sha256"] = retry_of
    _write_exact(marker_path, _pretty(marker))
    return result


def _failed_goal_source(collection: GoalProbeCollection) -> Mapping[str, Any] | None:
    """A persisted paper report is not evidence that its provider succeeded."""
    report = _json_object(collection.schedule_report_path)
    providers = report.get("providers")
    if not isinstance(providers, Mapping):
        raise ValueError("GOAL probe provider status is missing")
    status = providers.get(PROVIDER_NAME)
    if not isinstance(status, Mapping):
        raise ValueError("GOAL probe provider status is missing")
    return status if status.get("status") == "source_failed" else None


def collect_goal_probe_input(
    *,
    drawing_id: int,
    queue_path: str | Path | None,
    raw_cache_dir: str | Path,
    output_dir: str | Path,
    client: GoalAPIClient,
    project_root: str | Path = ".",
    captured_at: datetime | None = None,
) -> GoalProbeCollection:
    """Freeze exact GOAL fixture/team bindings and 30 team histories.

    The output is accepted only by the research-only GOAL adapter. It cannot
    mutate scheduler state, influence production probabilities, or place a bet.
    """

    root = Path(project_root).resolve()
    output = _contained_directory(root, output_dir, create=True)
    observed = _utc(captured_at or datetime.now(timezone.utc))
    raw_root = _contained_directory(root, raw_cache_dir, create=False)
    record = load_drawing_detail_cache(
        drawing_id,
        cache_dir=raw_root,
        max_age_seconds=None,
        now=observed,
        allowed_root=root,
    )
    target = parse_target_drawing(record.payload, record.fetched_at)
    if target.drawing_id != drawing_id:
        raise ValueError("drawing cache identity mismatch")
    if observed >= target.deadline:
        raise ValueError("GOAL probe collection must finish before drawing deadline")

    queue = (
        _write_research_queue(output, target, record.payload, observed)
        if queue_path is None
        else _contained_file(root, queue_path)
    )
    collection = collect_schedule_source_candidates(
        queue,
        output_dir=output / "schedule",
        fetch_json=lambda _url: {"results": []},
        captured_at=observed,
        thesportsdb_config=TheSportsDBConfig(api_key=None),
        goal_api_client=client,
    )
    schedule_report = _json_object(collection.report_path)
    goal_rows = _ordered_goal_rows(schedule_report)
    goal_rows_by_order = {int(row["event_order"]): row for row in goal_rows}

    target_events = tuple(sorted(target.events, key=lambda item: item.event_order))
    coverage_events: list[dict[str, Any]] = []
    latest_capture = observed
    for event in target_events:
        schedule_row = goal_rows_by_order.get(event.event_order)
        if schedule_row is None:
            coverage_events.append(
                {
                    "event_order": event.event_order,
                    "event_number": event.event_order + 1,
                    "target_event_id": event.event_id,
                    "home_team": event.home_team,
                    "away_team": event.away_team,
                    "provider_fixture_id": None,
                    "provider_home_team_id": None,
                    "provider_away_team_id": None,
                    "target_starts_at": None,
                    "sports_eligible": False,
                    "fallback_reason": "target_fixture_missing",
                    "sources": [],
                }
            )
            continue
        _validate_schedule_binding(event, schedule_row)
        target_start = _parse_utc(schedule_row.get("starts_at"), "starts_at")
        home_id = _text(schedule_row.get("source_home_team_id"), "home team id")
        away_id = _text(schedule_row.get("source_away_team_id"), "away team id")
        fixture_id = _text(schedule_row.get("source_event_id"), "fixture id")
        sources = []
        for side, team_id in (("home", home_id), ("away", away_id)):
            history = client.fetch_team_results(team_id, limit=10)
            latest_capture = max(latest_capture, history.evidence.fetched_at)
            history_path = _write_normalized_history(output, history)
            history_count, venue_count = _history_counts(
                history.payload,
                team_id=team_id,
                side=side,
                target_fixture_id=fixture_id,
                target_starts_at=target_start,
                as_of=history.evidence.fetched_at,
            )
            sources.append(
                {
                    "side": side,
                    "success": True,
                    "http_status": history.http_status,
                    "history_count": history_count,
                    "venue_count": venue_count,
                    "quota_remaining": history.quota_daily_remaining,
                    "snapshot_path": history_path.relative_to(root).as_posix(),
                }
            )
        coverage_events.append(
            {
                "event_order": event.event_order,
                "event_number": event.event_order + 1,
                "target_event_id": event.event_id,
                "home_team": event.home_team,
                "away_team": event.away_team,
                "provider_fixture_id": fixture_id,
                "provider_home_team_id": home_id,
                "provider_away_team_id": away_id,
                "target_starts_at": _timestamp(target_start),
                "sports_eligible": True,
                "sources": sources,
            }
        )

    finished_at = max(latest_capture, observed)
    if finished_at >= target.deadline:
        raise ValueError("GOAL probe collection crossed the drawing deadline")
    sports_eligible_count = len(goal_rows)
    history_source_count = sports_eligible_count * 2
    coverage = {
        "schema_version": 1,
        "status": "PAPER_ONLY_COVERAGE_PROBE",
        "captured_at": _timestamp(finished_at),
        "drawing_id": target.drawing_id,
        "drawing_number": target.drawing_number,
        "event_count": 15,
        "sports_eligible_count": sports_eligible_count,
        "history_source_count": history_source_count,
        "package_influence": "NONE",
        "automatic_wagering": False,
        "source_schedule_report": collection.report_path.relative_to(root).as_posix(),
        "events": coverage_events,
    }
    coverage_path = output / "coverage-summary.json"
    _write_exact(coverage_path, _pretty(coverage))
    return GoalProbeCollection(
        coverage_summary_path=coverage_path,
        schedule_report_path=collection.report_path,
        captured_at=finished_at,
        event_count=15,
        history_source_count=history_source_count,
        sports_eligible_count=sports_eligible_count,
        request_count=client.requests_made,
        quota_daily_remaining=client.quota_state.daily_remaining,
    )


def _write_research_queue(
    output: Path,
    target: Any,
    detail_payload: Mapping[str, Any],
    observed: datetime,
) -> Path:
    events = tuple(sorted(target.events, key=lambda item: item.event_order))
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        events,
    )
    records = [
        {
            "status": "research_shadow_input",
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "target_fingerprint": fingerprint,
            "event_order": event.event_order,
            "target_event_id": event.event_id,
            "home_team": event.home_team,
            "away_team": event.away_team,
            "championship": event.championship,
            "source_fixture_id": None,
            "requirements": {},
            "template": {},
        }
        for event in events
    ]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": _timestamp(observed),
        "identity": {
            "drawing_id": target.drawing_id,
            "drawing_number": target.drawing_number,
            "drawing_fingerprint": fingerprint,
            "deadline": _timestamp(target.deadline),
            "detail_sha256": hashlib.sha256(_canonical(detail_payload)).hexdigest(),
        },
        "records": records,
    }
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = output / "goal-shadow-queue.json"
    _write_exact(path, _pretty(payload))
    return path


def _load_current_collection(
    *,
    root: Path,
    marker_path: Path,
    drawing_id: int,
) -> GoalProbeCollection:
    marker = _json_object(marker_path)
    if (
        marker.get("schema_version") != 1
        or marker.get("status") != "PAPER_ONLY_COVERAGE_PROBE_READY"
        or marker.get("drawing_id") != drawing_id
        or marker.get("package_influence") != "NONE"
        or marker.get("automatic_wagering") is not False
    ):
        raise ValueError("GOAL probe current marker is invalid")
    coverage_path = _marker_file(root, marker, "coverage_summary_path")
    schedule_path = _marker_file(root, marker, "schedule_report_path")
    if _sha256_file(coverage_path) != marker.get("coverage_summary_sha256"):
        raise ValueError("GOAL probe coverage hash mismatch")
    if _sha256_file(schedule_path) != marker.get("schedule_report_sha256"):
        raise ValueError("GOAL probe schedule hash mismatch")
    coverage = _json_object(coverage_path)
    if (
        coverage.get("drawing_id") != drawing_id
        or coverage.get("status") != "PAPER_ONLY_COVERAGE_PROBE"
        or coverage.get("event_count") != 15
        or not isinstance(coverage.get("sports_eligible_count"), int)
        or not 0 <= int(coverage["sports_eligible_count"]) <= 15
        or coverage.get("history_source_count")
        != 2 * int(coverage["sports_eligible_count"])
    ):
        raise ValueError("GOAL probe coverage marker is invalid")
    return GoalProbeCollection(
        coverage_summary_path=coverage_path,
        schedule_report_path=schedule_path,
        captured_at=_parse_utc(marker.get("captured_at"), "captured_at"),
        event_count=int(marker["event_count"]),
        history_source_count=int(marker["history_source_count"]),
        sports_eligible_count=int(marker["sports_eligible_count"]),
        request_count=int(marker["request_count"]),
        quota_daily_remaining=(
            None
            if marker.get("quota_daily_remaining") is None
            else int(marker["quota_daily_remaining"])
        ),
        reused=True,
    )


def _marker_file(root: Path, marker: Mapping[str, Any], name: str) -> Path:
    value = marker.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"GOAL probe {name} is invalid")
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"GOAL probe {name} escapes project root") from error
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"GOAL probe {name} is missing")
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ordered_goal_rows(report: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    if report.get("status") != "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE":
        raise ValueError("GOAL schedule report status is unsupported")
    if report.get("ledger_mutated") is not False:
        raise ValueError("GOAL schedule report must not mutate the ledger")
    values = report.get("records")
    if not isinstance(values, list):
        raise ValueError("GOAL schedule report records are invalid")
    rows = tuple(
        sorted(
            (
                row
                for row in values
                if isinstance(row, Mapping)
                and row.get("source_provider") == PROVIDER_NAME
                and row.get("status") in {"independent_candidate", "timing_conflict"}
            ),
            key=lambda row: int(row["event_order"]),
        )
    )
    orders = tuple(int(row["event_order"]) for row in rows)
    if any(order not in range(15) for order in orders) or len(set(orders)) != len(
        orders
    ):
        raise ValueError("GOAL schedule report event orders are invalid")
    return rows


def _validate_schedule_binding(event: Any, row: Mapping[str, Any]) -> None:
    expected = {
        "event_order": event.event_order,
        "target_event_id": event.event_id,
        "target_home_team": event.home_team,
        "target_away_team": event.away_team,
        "orientation": "same",
        "source_status": "scheduled",
        "ledger_eligible": False,
    }
    for name, value in expected.items():
        if row.get(name) != value:
            raise ValueError(f"GOAL schedule binding mismatch: {name}")
    for name in ("source_event_id", "source_home_team_id", "source_away_team_id"):
        _text(row.get(name), name)


def _write_normalized_history(
    output: Path,
    history: GoalAPITeamResults,
) -> Path:
    document = {
        "schema_version": 1,
        "provider": PROVIDER_NAME,
        "endpoint": history.evidence.endpoint,
        "params": {"limit": 10},
        "fetched_at": _timestamp(history.evidence.fetched_at),
        "http_status": history.http_status,
        "payload": history.payload,
    }
    content = _canonical(document) + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    path = output / f"{digest[:16]}.json"
    _write_exact(path, content)
    return path


def _history_counts(
    payload: Mapping[str, Any],
    *,
    team_id: str,
    side: str,
    target_fixture_id: str,
    target_starts_at: datetime,
    as_of: datetime,
) -> tuple[int, int]:
    values = payload.get("data")
    if not isinstance(values, list):
        raise ValueError("GOAL history data is invalid")
    accepted = []
    for row in values:
        if not isinstance(row, Mapping):
            continue
        if row.get("matchStatus") not in _TERMINAL_STATUSES:
            continue
        if str(row.get("id")) == target_fixture_id:
            continue
        try:
            starts_at = _parse_utc(row.get("kickoffUtc"), "history kickoff")
        except ValueError:
            continue
        if starts_at >= min(target_starts_at, as_of):
            continue
        if team_id not in (str(row.get("homeTeamId")), str(row.get("awayTeamId"))):
            continue
        accepted.append(row)
    venue_key = "homeTeamId" if side == "home" else "awayTeamId"
    return len(accepted), sum(str(row.get(venue_key)) == team_id for row in accepted)


def _contained_directory(root: Path, value: str | Path, *, create: bool) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("GOAL probe path must stay inside project root") from error
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    elif not resolved.is_dir():
        raise ValueError(f"GOAL probe directory is missing: {resolved}")
    if resolved.is_symlink():
        raise ValueError("GOAL probe directory cannot be a symlink")
    return resolved


def _contained_file(root: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("GOAL probe file must stay inside project root") from error
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"GOAL probe file is missing: {resolved}")
    return resolved


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"GOAL probe JSON must be an object: {path}")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"GOAL probe {name} is invalid")
    text = str(value).strip()
    if not text:
        raise ValueError(f"GOAL probe {name} is empty")
    return text


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"GOAL probe {name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"GOAL probe {name} is invalid") from None
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("GOAL probe time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_exact(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"GOAL probe artifact conflict: {path}")
        return
    path.write_bytes(content)
