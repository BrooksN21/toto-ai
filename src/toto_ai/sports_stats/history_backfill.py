"""Offline, explicit-manifest import of frozen raw sports history."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.db.models import SportsStatsRun
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.package.audit import canonical_probability_input_sha256
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    SourceEvidence,
    SportsStatsRunSnapshot,
    build_event_snapshot,
    build_run_snapshot,
)
from toto_ai.sports_stats.features import build_team_window
from toto_ai.sports_stats.storage import save_sports_stats_snapshot

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_ARTIFACT_CLASS = "SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_MANIFEST"
AUDIT_SCHEMA_VERSION = 1
AUDIT_ARTIFACT_CLASS = "SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_AUDIT"
RAW_GOAL_ARTIFACT_TYPE = "raw_goal_team_results_response"
GOAL_PROVIDER = "goal-api-v1"
GOAL_BASE_URL = "https://api.goal-api.com/v1"

_EXPECTED_ORDERS = tuple(range(15))
_TERMINAL_STATUSES = {
    "FINISHED": "FT",
    "AFTER_ET": "AET",
    "AFTER_PEN": "PEN",
}
_UNAVAILABLE_SCHEDULE_STATUSES = frozenset(("not_found", "source_failed"))
_UNAVAILABLE_REASONS = frozenset(
    ("source_not_captured", "target_fixture_missing")
)


@dataclass(frozen=True)
class SportsHistoryBackfillAuditPaths:
    json: Path
    csv: Path
    markdown: Path


@dataclass(frozen=True)
class _RawSource:
    available: bool
    reason: str | None
    fixtures: tuple[CompletedFixture, ...]
    evidence: SourceEvidence | None
    fetched_at: datetime | None
    audit: dict[str, Any]


@dataclass(frozen=True)
class _PreparedEvent:
    target: Any
    target_starts_at: datetime
    provider_fixture_id: str | None
    provider_home_team_id: str | None
    provider_away_team_id: str | None
    home: _RawSource
    away: _RawSource


@dataclass(frozen=True)
class _BuiltSnapshot:
    snapshot: SportsStatsRunSnapshot
    available_source_count: int
    unavailable_source_count: int
    event_audit: tuple[dict[str, Any], ...]
    source_artifacts: tuple[dict[str, Any], ...]


def backfill_sports_history_manifest(
    *,
    manifest_path: str | Path,
    db: str | Path | None,
    output_dir: str | Path,
    project_root: str | Path = ".",
    validate_only: bool = False,
) -> tuple[dict[str, Any], SportsHistoryBackfillAuditPaths]:
    """Validate raw captures, persist each snapshot, and write audit files.

    No network client is constructed. All manifest snapshots are validated in
    full before the database is opened or initialized. If none pass input
    validation, a missing or old-schema database remains untouched.
    A rejected snapshot does not prevent an independent valid snapshot in the
    same manifest from being committed and audited.
    """

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise ValueError("project root is missing")
    manifest_file = _contained_file(root, manifest_path, "manifest")
    manifest_file_sha256 = _file_sha256(manifest_file)
    manifest = _json_object(manifest_file, "manifest")
    manifest_semantic_sha256, raw_snapshots = _validate_manifest(manifest)

    output = _contained_output_path(root, output_dir, "audit output")
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("audit output must be a non-symlink directory")

    database = None
    if not validate_only:
        if db is None:
            raise ValueError("database path is required unless validate_only is set")
        database = _contained_output_path(root, db, "database")

    prepared: list[tuple[int, _BuiltSnapshot]] = []
    results: list[dict[str, Any]] = []
    for index, raw_snapshot in enumerate(raw_snapshots):
        try:
            built = _build_snapshot(root=root, value=raw_snapshot)
        except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
            results.append(
                _rejected_result(
                    index=index,
                    raw_snapshot=raw_snapshot,
                    error=error,
                    root=root,
                )
            )
        else:
            prepared.append((index, built))

    session_factory = None
    if prepared and database is not None:
        session_factory = get_session_factory(init_db(database))
    for index, built in prepared:
        try:
            if validate_only:
                persisted = built.snapshot
                status = "validated"
            else:
                if session_factory is None:
                    raise ValueError("database session is unavailable")
                existed = _persistence_slot_exists(
                    session_factory,
                    built.snapshot,
                )
                persisted = save_sports_stats_snapshot(
                    session_factory,
                    built.snapshot,
                )
                status = (
                    "reused"
                    if existed or persisted.run_id != built.snapshot.run_id
                    else "inserted"
                )
            results.append(
                _successful_result(
                    index=index,
                    status=status,
                    persisted=persisted,
                    built=built,
                )
            )
        except (OSError, SQLAlchemyError, TypeError, ValueError) as error:
            results.append(
                _rejected_result(
                    index=index,
                    raw_snapshot=raw_snapshots[index],
                    error=error,
                    root=root,
                )
            )

    results.sort(key=lambda row: row["manifest_index"])
    inserted_count = sum(row["status"] == "inserted" for row in results)
    reused_count = sum(row["status"] == "reused" for row in results)
    validated_count = sum(row["status"] == "validated" for row in results)
    rejected_count = sum(row["status"] == "rejected" for row in results)
    if rejected_count == 0:
        status = "SUCCESS"
    elif rejected_count == len(results):
        status = "REJECTED"
    else:
        status = "PARTIAL"
    report: dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "artifact_class": AUDIT_ARTIFACT_CLASS,
        "status": status,
        "mode": "OFFLINE_RAW_CAPTURE_ONLY",
        "validation_only": validate_only,
        "network_requests": 0,
        "database_writes": 0 if validate_only else inserted_count,
        "package_influence": "NONE",
        "automatic_wagering": False,
        "manifest_path": _relative(manifest_file, root),
        "manifest_file_sha256": manifest_file_sha256,
        "manifest_semantic_sha256": manifest_semantic_sha256,
        "snapshot_count": len(results),
        "inserted_count": inserted_count,
        "reused_count": reused_count,
        "validated_count": validated_count,
        "rejected_count": rejected_count,
        "snapshots": results,
    }
    report["audit_sha256"] = _sha256_json(report)
    paths = _write_audit(report, output)
    return report, paths


def _build_snapshot(*, root: Path, value: object) -> _BuiltSnapshot:
    raw = _mapping(value, "snapshot")
    drawing_id = _positive_int(raw.get("drawing_id"), "drawing_id")
    drawing_number = _positive_int(
        raw.get("drawing_number"), "drawing_number"
    )
    drawing_fingerprint = _sha256(
        raw.get("drawing_fingerprint"), "drawing_fingerprint"
    )
    _require_exact(raw.get("provider"), GOAL_PROVIDER, "provider")
    history_size = _positive_int(
        raw.get("requested_history_size"), "requested_history_size"
    )
    if history_size != 10:
        raise ValueError("requested_history_size must equal 10")
    as_of = _parse_utc(raw.get("as_of"), "as_of")
    deadline = _parse_utc(raw.get("deadline"), "deadline")
    if as_of >= deadline:
        raise ValueError("as_of must be strictly before deadline")

    target, target_captured_at = _load_target_binding(
        root=root,
        value=raw.get("target_detail"),
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        drawing_fingerprint=drawing_fingerprint,
        as_of=as_of,
        deadline=deadline,
    )

    schedule_ref = _mapping(raw.get("schedule_binding"), "schedule_binding")
    schedule_path = _verified_file(
        root,
        schedule_ref.get("path"),
        schedule_ref.get("sha256"),
        "schedule binding",
    )
    schedule = _json_object(schedule_path, "schedule binding")
    schedule_captured_at, schedule_rows = _validate_schedule(
        schedule,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        as_of=as_of,
        deadline=deadline,
    )

    event_values = raw.get("events")
    if not isinstance(event_values, list) or len(event_values) != 15:
        raise ValueError("snapshot manifest requires exactly 15 events")
    manifest_events = tuple(_mapping(item, "event") for item in event_values)
    if tuple(row.get("event_order") for row in manifest_events) != _EXPECTED_ORDERS:
        raise ValueError("snapshot manifest event orders must be exactly 0 through 14")

    latest_capture = max(target_captured_at, schedule_captured_at)
    prepared: list[_PreparedEvent] = []
    source_artifacts: list[dict[str, Any]] = []
    available_source_count = 0
    unavailable_source_count = 0
    for target_event, event_raw in zip(
        target.events,
        manifest_events,
        strict=True,
    ):
        order = target_event.event_order
        _require_exact(event_raw.get("event_order"), order, "event_order")
        _require_exact(
            event_raw.get("target_event_id"),
            str(target_event.event_id),
            "target_event_id",
        )
        _require_exact(
            event_raw.get("home_team"), target_event.home_team, "home_team"
        )
        _require_exact(
            event_raw.get("away_team"), target_event.away_team, "away_team"
        )
        _require_exact(event_raw.get("sport"), target_event.sport, "sport")
        if target_event.sport != "football":
            raise ValueError("GOAL history backfill supports football only")

        fixture_id = _optional_text(
            event_raw.get("provider_fixture_id"), "provider_fixture_id"
        )
        home_team_id = _optional_text(
            event_raw.get("provider_home_team_id"), "provider_home_team_id"
        )
        away_team_id = _optional_text(
            event_raw.get("provider_away_team_id"), "provider_away_team_id"
        )
        sources = _mapping(event_raw.get("sources"), "sources")
        if set(sources) != {"home", "away"}:
            raise ValueError("event sources must contain exact home and away entries")
        schedule_row = schedule_rows.get(order)

        if fixture_id is None:
            if home_team_id is not None or away_team_id is not None:
                raise ValueError("missing provider fixture cannot retain team ids")
            _require_exact(
                event_raw.get("target_starts_at"),
                None,
                "missing target_starts_at",
            )
            if schedule_row is not None:
                raise ValueError("manifest omits an available GOAL schedule binding")
            home = _load_unavailable_source(
                sources.get("home"),
                side="home",
                required_reason="target_fixture_missing",
            )
            away = _load_unavailable_source(
                sources.get("away"),
                side="away",
                required_reason="target_fixture_missing",
            )
            target_starts_at = target_event.starts_at or deadline
        else:
            if home_team_id is None or away_team_id is None:
                raise ValueError(
                    "provider fixture requires exact home and away team ids"
                )
            if schedule_row is None:
                raise ValueError(
                    "provider fixture is missing its GOAL schedule binding"
                )
            target_starts_at = _parse_utc(
                event_raw.get("target_starts_at"), "target_starts_at"
            )
            if as_of >= target_starts_at:
                raise ValueError("as_of must be strictly before target kickoff")
            if target_event.starts_at is not None:
                _require_exact(
                    target_event.starts_at,
                    target_starts_at,
                    "target detail kickoff",
                )
            _validate_schedule_event(
                schedule_row,
                target_event=target_event,
                target_starts_at=target_starts_at,
                provider_fixture_id=fixture_id,
                provider_home_team_id=home_team_id,
                provider_away_team_id=away_team_id,
            )
            home = _load_source(
                root=root,
                value=sources.get("home"),
                side="home",
                team_id=home_team_id,
                target_fixture_id=fixture_id,
                target_starts_at=target_starts_at,
                as_of=as_of,
                deadline=deadline,
                history_size=history_size,
            )
            away = _load_source(
                root=root,
                value=sources.get("away"),
                side="away",
                team_id=away_team_id,
                target_fixture_id=fixture_id,
                target_starts_at=target_starts_at,
                as_of=as_of,
                deadline=deadline,
                history_size=history_size,
            )
        for source in (home, away):
            source_artifacts.append(
                {
                    "event_order": order,
                    **source.audit,
                }
            )
            if source.available:
                available_source_count += 1
                if source.fetched_at is None:
                    raise ValueError("available source is missing fetched_at")
                latest_capture = max(latest_capture, source.fetched_at)
            else:
                unavailable_source_count += 1
        prepared.append(
            _PreparedEvent(
                target=target_event,
                target_starts_at=target_starts_at,
                provider_fixture_id=fixture_id,
                provider_home_team_id=home_team_id,
                provider_away_team_id=away_team_id,
                home=home,
                away=away,
            )
        )

    if latest_capture > as_of or latest_capture >= deadline:
        raise ValueError("latest source capture is outside the frozen boundary")
    event_snapshots = []
    event_audit = []
    for item in prepared:
        event = item.target
        if item.provider_fixture_id is None:
            status = "missing"
            missing_reasons = ("target_fixture_missing",)
            home_window = away_window = None
            source_evidence: tuple[SourceEvidence, ...] = ()
            canonical_home_id = canonical_away_id = None
        else:
            home_window = (
                build_team_window(
                    team_id=str(item.provider_home_team_id),
                    fixtures=item.home.fixtures,
                    requested_count=history_size,
                    target_starts_at=item.target_starts_at,
                    target_fixture_id=item.provider_fixture_id,
                    as_of=as_of,
                )
                if item.home.available
                else None
            )
            away_window = (
                build_team_window(
                    team_id=str(item.provider_away_team_id),
                    fixtures=item.away.fixtures,
                    requested_count=history_size,
                    target_starts_at=item.target_starts_at,
                    target_fixture_id=item.provider_fixture_id,
                    as_of=as_of,
                )
                if item.away.available
                else None
            )
            reasons: set[str] = set()
            if not item.home.available or not item.away.available:
                reasons.add("historical_asof_unavailable")
            if (
                (item.home.available and home_window is None)
                or (item.away.available and away_window is None)
            ):
                reasons.add("no_completed_fixtures")
            missing_reasons = tuple(sorted(reasons))
            if home_window is not None and away_window is not None:
                status = "complete"
            elif item.home.available or item.away.available:
                status = "partial"
            else:
                status = "missing"
            source_evidence = tuple(
                source.evidence
                for source in (item.home, item.away)
                if source.evidence is not None
            )
            canonical_home_id = event.event_id * 2
            canonical_away_id = event.event_id * 2 + 1
        snapshot_event = build_event_snapshot(
            schema_version=1,
            drawing_id=drawing_id,
            drawing_number=drawing_number,
            drawing_fingerprint=drawing_fingerprint,
            event_id=str(event.event_id),
            event_order=event.event_order,
            sport="football",
            provider=GOAL_PROVIDER,
            status=status,
            missing_reasons=missing_reasons,
            captured_at=latest_capture,
            as_of=as_of,
            deadline=deadline,
            target_starts_at=item.target_starts_at,
            provider_fixture_id=item.provider_fixture_id,
            canonical_home_team_id=canonical_home_id,
            canonical_away_team_id=canonical_away_id,
            provider_home_team_id=item.provider_home_team_id,
            provider_away_team_id=item.provider_away_team_id,
            league_id=None,
            season=None,
            home_window=home_window,
            away_window=away_window,
            home_standing=None,
            away_standing=None,
            source_evidence=source_evidence,
        )
        event_snapshots.append(snapshot_event)
        event_audit.append(
            {
                "event_order": event.event_order,
                "target_event_id": str(event.event_id),
                "status": status,
                "missing_reasons": list(missing_reasons),
                "provider_fixture_id": item.provider_fixture_id,
                "provider_home_team_id": item.provider_home_team_id,
                "provider_away_team_id": item.provider_away_team_id,
                "target_starts_at": _iso(item.target_starts_at),
                "home_source_status": (
                    "available" if item.home.available else "unavailable"
                ),
                "away_source_status": (
                    "available" if item.away.available else "unavailable"
                ),
            }
        )

    snapshot = build_run_snapshot(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        drawing_fingerprint=drawing_fingerprint,
        provider=GOAL_PROVIDER,
        requested_history_size=history_size,
        captured_at=latest_capture,
        as_of=as_of,
        deadline=deadline,
        events=tuple(event_snapshots),
        requests_made=0,
        cache_hits=available_source_count,
    )
    return _BuiltSnapshot(
        snapshot=snapshot,
        available_source_count=available_source_count,
        unavailable_source_count=unavailable_source_count,
        event_audit=tuple(event_audit),
        source_artifacts=tuple(source_artifacts),
    )


def _load_target_binding(
    *,
    root: Path,
    value: object,
    drawing_id: int,
    drawing_number: int,
    drawing_fingerprint: str,
    as_of: datetime,
    deadline: datetime,
) -> tuple[Any, datetime]:
    reference = _mapping(value, "target_detail")
    artifact_type = reference.get("artifact_type")
    if artifact_type == "frozen_final_input":
        path = _verified_file(
            root,
            reference.get("path"),
            reference.get("sha256"),
            "frozen final input",
        )
        document = _json_object(path, "frozen final input")
        required_fields = {
            "schema_version",
            "plan_id",
            "attempt_id",
            "drawing_id",
            "drawing_number",
            "deadline",
            "captured_at",
            "target_fingerprint",
            "detail_payload_sha256",
            "probability_input_sha256",
            "timing_override_sha256",
            "payload",
            "snapshot_sha256",
        }
        if set(document) != required_fields:
            raise ValueError("frozen final input fields are invalid")
        _require_exact(document.get("schema_version"), 1, "final input schema")
        _text(document.get("plan_id"), "final input plan_id")
        _text(document.get("attempt_id"), "final input attempt_id")
        declared_snapshot = _sha256(
            document.get("snapshot_sha256"), "final input snapshot_sha256"
        )
        unsigned = dict(document)
        unsigned.pop("snapshot_sha256", None)
        _require_exact(
            declared_snapshot,
            _sha256_json(unsigned),
            "final input snapshot hash",
        )
        _require_exact(
            document.get("drawing_id"), drawing_id, "final input drawing_id"
        )
        _require_exact(
            document.get("drawing_number"),
            drawing_number,
            "final input drawing_number",
        )
        captured_at = _parse_utc(
            document.get("captured_at"), "final input captured_at"
        )
        declared_deadline = _parse_utc(
            document.get("deadline"), "final input deadline"
        )
        _require_exact(declared_deadline, deadline, "final input deadline")
        if captured_at > as_of or captured_at >= deadline:
            raise ValueError("final input was captured after the frozen boundary")
        payload = _mapping(document.get("payload"), "final input payload")
        detail_payload_sha256 = _sha256(
            document.get("detail_payload_sha256"),
            "final input detail_payload_sha256",
        )
        _require_exact(
            detail_payload_sha256,
            _sha256_json(payload),
            "final input detail payload hash",
        )
        target = parse_target_drawing(payload, captured_at)
        expected_probability_hash = canonical_probability_input_sha256(
            tuple(event.bk_probabilities for event in target.events)
        )
        _require_exact(
            document.get("probability_input_sha256"),
            expected_probability_hash,
            "final input probability hash",
        )
        declared_fingerprint = _sha256(
            document.get("target_fingerprint"),
            "final input target_fingerprint",
        )
        expected_fingerprint = target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        )
        _require_exact(
            declared_fingerprint,
            expected_fingerprint,
            "final input target fingerprint",
        )
    elif artifact_type is None:
        detail_path = _verified_file(
            root,
            reference.get("path"),
            reference.get("sha256"),
            "target detail",
        )
        metadata_path = _verified_file(
            root,
            reference.get("metadata_path"),
            reference.get("metadata_sha256"),
            "target detail metadata",
        )
        expected_detail_name = f"drawing_{drawing_id}.json"
        if detail_path.name != expected_detail_name:
            raise ValueError("target detail path does not bind drawing_id")
        if metadata_path != detail_path.with_suffix(".meta.json"):
            raise ValueError(
                "target detail metadata path is not the exact sidecar"
            )
        record = load_drawing_detail_cache(
            drawing_id,
            cache_dir=detail_path.parent,
            max_age_seconds=None,
            now=as_of,
            allowed_root=root,
        )
        if record.path.resolve() != detail_path:
            raise ValueError("target detail loader resolved a different file")
        if record.fetched_at > as_of or record.fetched_at >= deadline:
            raise ValueError(
                "target detail was captured after the frozen boundary"
            )
        captured_at = record.fetched_at
        target = parse_target_drawing(record.payload, record.fetched_at)
        expected_fingerprint = target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        )
    else:
        raise ValueError("target_detail artifact_type is unsupported")

    _require_exact(target.drawing_id, drawing_id, "target drawing_id")
    _require_exact(target.drawing_number, drawing_number, "target drawing_number")
    _require_exact(target.deadline, deadline, "target deadline")
    _require_exact(
        drawing_fingerprint,
        expected_fingerprint,
        "drawing_fingerprint",
    )
    return target, captured_at


def _load_source(
    *,
    root: Path,
    value: object,
    side: str,
    team_id: str,
    target_fixture_id: str,
    target_starts_at: datetime,
    as_of: datetime,
    deadline: datetime,
    history_size: int,
) -> _RawSource:
    raw = _mapping(value, f"{side} source")
    if raw.get("status") == "unavailable":
        return _load_unavailable_source(
            raw,
            side=side,
            required_reason="source_not_captured",
        )
    _require_exact(raw.get("status"), "available", f"{side} source status")
    if raw.get("artifact_type") != RAW_GOAL_ARTIFACT_TYPE:
        raise ValueError(f"{side} source is not a raw GOAL team-results capture")
    path = _verified_file(
        root,
        raw.get("path"),
        raw.get("sha256"),
        f"{side} raw history capture",
    )
    document = _json_object(path, f"{side} raw history capture")
    required_fields = {
        "schema_version",
        "provider",
        "endpoint",
        "params",
        "request_fingerprint",
        "fetched_at",
        "response_hash",
        "payload",
    }
    if set(document) != required_fields:
        raise ValueError(f"{side} source is not a raw GOAL team-results capture")
    _require_exact(document.get("schema_version"), 1, f"{side} source schema")
    _require_exact(document.get("provider"), GOAL_PROVIDER, f"{side} provider")
    endpoint = _text(document.get("endpoint"), f"{side} endpoint")
    _require_exact(endpoint, f"/teams/{team_id}/results", f"{side} endpoint")
    params = document.get("params")
    _require_exact(params, [["limit", str(history_size)]], f"{side} params")
    expected_request_fingerprint = _sha256_json(
        {
            "provider": GOAL_PROVIDER,
            "base_url": GOAL_BASE_URL,
            "endpoint": endpoint,
            "params": params,
        }
    )
    request_fingerprint = _sha256(
        document.get("request_fingerprint"), f"{side} request_fingerprint"
    )
    _require_exact(
        request_fingerprint,
        expected_request_fingerprint,
        f"{side} request_fingerprint",
    )
    fetched_at = _parse_utc(document.get("fetched_at"), f"{side} fetched_at")
    if fetched_at >= target_starts_at:
        raise ValueError(f"{side} capture must be strictly before target kickoff")
    if fetched_at > as_of or fetched_at >= deadline:
        raise ValueError(f"{side} capture is outside the frozen as_of boundary")

    payload = _mapping(document.get("payload"), f"{side} payload")
    response_hash = _sha256(
        document.get("response_hash"), f"{side} response_hash"
    )
    _require_exact(response_hash, _sha256_json(payload), f"{side} response_hash")
    _require_exact(payload.get("success"), True, f"{side} payload success")
    _require_exact(str(payload.get("teamId")), team_id, f"{side} payload team")
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > history_size:
        raise ValueError(f"{side} payload data must contain at most ten rows")

    evidence = SourceEvidence(
        provider=GOAL_PROVIDER,
        endpoint=endpoint,
        request_fingerprint=request_fingerprint,
        payload_sha256=response_hash,
        fetched_at=fetched_at,
    )
    fixtures = []
    seen_fixture_ids: set[str] = set()
    for raw_row in rows:
        row = _mapping(raw_row, f"{side} history row")
        status = _TERMINAL_STATUSES.get(row.get("matchStatus"))
        if status is None:
            continue
        fixture_id = _text(row.get("id"), f"{side} history fixture id")
        if fixture_id in seen_fixture_ids:
            raise ValueError(f"{side} history contains duplicate fixture ids")
        seen_fixture_ids.add(fixture_id)
        starts_at = _parse_utc(
            row.get("kickoffUtc"), f"{side} history kickoff"
        )
        home_team_id = _text(
            row.get("homeTeamId"), f"{side} history home team id"
        )
        away_team_id = _text(
            row.get("awayTeamId"), f"{side} history away team id"
        )
        if team_id not in (home_team_id, away_team_id):
            raise ValueError(f"{side} history row has unrelated team identity")
        if starts_at >= fetched_at:
            raise ValueError(f"{side} history fixture is not before capture time")
        if starts_at >= as_of or starts_at >= target_starts_at:
            raise ValueError(f"{side} history fixture crosses the target boundary")
        if fixture_id == target_fixture_id:
            raise ValueError(f"{side} history contains the target fixture")
        fixtures.append(
            CompletedFixture(
                provider_fixture_id=fixture_id,
                starts_at=starts_at,
                status=status,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_goals=_nonnegative_int(
                    row.get("homeTeamScore"), f"{side} history home score"
                ),
                away_goals=_nonnegative_int(
                    row.get("awayTeamScore"), f"{side} history away score"
                ),
                source=evidence,
            )
        )
    ordered_fixtures = tuple(
        sorted(
            fixtures,
            key=lambda item: (item.starts_at, item.provider_fixture_id),
            reverse=True,
        )
    )
    return _RawSource(
        available=True,
        reason=None,
        fixtures=ordered_fixtures,
        evidence=evidence,
        fetched_at=fetched_at,
        audit={
            "side": side,
            "status": "available",
            "reason": None,
            "artifact_type": RAW_GOAL_ARTIFACT_TYPE,
            "path": _relative(path, root),
            "sha256": _file_sha256(path),
            "fetched_at": _iso(fetched_at),
            "request_fingerprint": request_fingerprint,
            "payload_sha256": response_hash,
            "accepted_fixture_count": len(ordered_fixtures),
        },
    )


def _load_unavailable_source(
    value: object,
    *,
    side: str,
    required_reason: str | None = None,
) -> _RawSource:
    raw = _mapping(value, f"{side} source")
    if set(raw) != {"status", "reason"}:
        raise ValueError(f"{side} unavailable source has unsupported fields")
    _require_exact(raw.get("status"), "unavailable", f"{side} source status")
    reason = _text(raw.get("reason"), f"{side} unavailable reason")
    if reason not in _UNAVAILABLE_REASONS:
        raise ValueError(f"{side} unavailable reason is unsupported")
    if required_reason is not None:
        _require_exact(reason, required_reason, f"{side} unavailable reason")
    return _RawSource(
        available=False,
        reason=reason,
        fixtures=(),
        evidence=None,
        fetched_at=None,
        audit={
            "side": side,
            "status": "unavailable",
            "reason": reason,
            "artifact_type": None,
            "path": None,
            "sha256": None,
            "fetched_at": None,
            "request_fingerprint": None,
            "payload_sha256": None,
            "accepted_fixture_count": 0,
        },
    )


def _validate_schedule(
    value: Mapping[str, Any],
    *,
    drawing_id: int,
    drawing_number: int,
    as_of: datetime,
    deadline: datetime,
) -> tuple[datetime, dict[int, Mapping[str, Any]]]:
    _require_exact(value.get("schema_version"), 2, "schedule schema")
    _require_exact(
        value.get("status"),
        "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "schedule status",
    )
    _require_exact(value.get("drawing_id"), drawing_id, "schedule drawing_id")
    _require_exact(
        value.get("drawing_number"),
        drawing_number,
        "schedule drawing_number",
    )
    _require_exact(value.get("ledger_mutated"), False, "schedule ledger flag")
    captured_at = _parse_utc(value.get("captured_at"), "schedule captured_at")
    if captured_at > as_of or captured_at >= deadline:
        raise ValueError("schedule binding was captured after the frozen boundary")
    report_sha256 = _sha256(value.get("report_sha256"), "schedule report_sha256")
    unsigned = dict(value)
    unsigned.pop("report_sha256", None)
    _require_exact(
        report_sha256,
        _sha256_json(unsigned),
        "schedule semantic hash",
    )
    records = value.get("records")
    if not isinstance(records, list):
        raise ValueError("schedule records must be a list")
    rows: dict[int, Mapping[str, Any]] = {}
    seen_orders: set[int] = set()
    for raw_row in records:
        row = _mapping(raw_row, "schedule record")
        if row.get("source_provider") != GOAL_PROVIDER:
            continue
        order = _event_order(row.get("event_order"))
        if order in seen_orders:
            raise ValueError("GOAL schedule contains duplicate event orders")
        seen_orders.add(order)
        status = row.get("status")
        if status in _UNAVAILABLE_SCHEDULE_STATUSES:
            if any(
                row.get(name) is not None
                for name in (
                    "source_event_id",
                    "source_home_team_id",
                    "source_away_team_id",
                    "starts_at",
                )
            ):
                raise ValueError(
                    "unavailable GOAL schedule record retains source identity"
                )
            _require_exact(
                row.get("ledger_eligible"),
                False,
                "unavailable schedule ledger flag",
            )
            continue
        if status not in {"independent_candidate", "timing_conflict"}:
            raise ValueError("GOAL schedule record status is unsupported")
        rows[order] = row
    return captured_at, rows


def _validate_schedule_event(
    row: Mapping[str, Any],
    *,
    target_event: Any,
    target_starts_at: datetime,
    provider_fixture_id: str,
    provider_home_team_id: str,
    provider_away_team_id: str,
) -> None:
    expected = {
        "event_order": target_event.event_order,
        "target_event_id": target_event.event_id,
        "target_home_team": target_event.home_team,
        "target_away_team": target_event.away_team,
        "orientation": "same",
        "source_provider": GOAL_PROVIDER,
        "source_event_id": provider_fixture_id,
        "source_home_team_id": provider_home_team_id,
        "source_away_team_id": provider_away_team_id,
        "starts_at": _iso(target_starts_at),
        "source_status": "scheduled",
        "ledger_eligible": False,
    }
    for name, expected_value in expected.items():
        _require_exact(row.get(name), expected_value, f"schedule {name}")


def _validate_manifest(
    value: Mapping[str, Any],
) -> tuple[str, tuple[object, ...]]:
    _require_exact(
        value.get("schema_version"),
        MANIFEST_SCHEMA_VERSION,
        "manifest schema_version",
    )
    _require_exact(
        value.get("artifact_class"),
        MANIFEST_ARTIFACT_CLASS,
        "manifest artifact_class",
    )
    manifest_sha256 = _sha256(
        value.get("manifest_sha256"), "manifest_sha256"
    )
    unsigned = dict(value)
    unsigned.pop("manifest_sha256", None)
    _require_exact(
        manifest_sha256,
        _sha256_json(unsigned),
        "manifest semantic hash",
    )
    snapshots = value.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("manifest snapshots must be a non-empty list")
    return manifest_sha256, tuple(snapshots)


def _persistence_slot_exists(
    session_factory: Any,
    snapshot: SportsStatsRunSnapshot,
) -> bool:
    with session_factory() as session:
        if session.get(SportsStatsRun, snapshot.run_id) is not None:
            return True
        row = session.scalar(
            select(SportsStatsRun.run_id).where(
                SportsStatsRun.drawing_id == snapshot.drawing_id,
                SportsStatsRun.drawing_fingerprint == snapshot.drawing_fingerprint,
                SportsStatsRun.provider == snapshot.provider,
                SportsStatsRun.as_of == snapshot.as_of.isoformat(),
            )
        )
    return row is not None


def _successful_result(
    *,
    index: int,
    status: str,
    persisted: SportsStatsRunSnapshot,
    built: _BuiltSnapshot,
) -> dict[str, Any]:
    return {
        "manifest_index": index,
        "drawing_id": persisted.drawing_id,
        "drawing_number": persisted.drawing_number,
        "drawing_fingerprint": persisted.drawing_fingerprint,
        "provider": persisted.provider,
        "status": status,
        "error": None,
        "run_id": persisted.run_id,
        "snapshot_content_sha256": persisted.content_sha256,
        "semantic_persistence_sha256": persisted.semantic_persistence_sha256(),
        "captured_at": _iso(persisted.captured_at),
        "as_of": _iso(persisted.as_of),
        "deadline": _iso(persisted.deadline),
        "complete_count": persisted.complete_count,
        "partial_count": persisted.partial_count,
        "missing_count": persisted.missing_count,
        "unsupported_count": persisted.unsupported_count,
        "available_source_count": built.available_source_count,
        "unavailable_source_count": built.unavailable_source_count,
        "event_audit": list(built.event_audit),
        "source_artifacts": list(built.source_artifacts),
    }


def _rejected_result(
    *,
    index: int,
    raw_snapshot: object,
    error: Exception,
    root: Path,
) -> dict[str, Any]:
    raw = raw_snapshot if isinstance(raw_snapshot, Mapping) else {}
    return {
        "manifest_index": index,
        "drawing_id": _safe_positive_int(raw.get("drawing_id")),
        "drawing_number": _safe_positive_int(raw.get("drawing_number")),
        "drawing_fingerprint": _safe_sha256(raw.get("drawing_fingerprint")),
        "provider": (
            raw.get("provider")
            if isinstance(raw.get("provider"), str)
            else None
        ),
        "status": "rejected",
        "error": _bounded_error(error, root),
        "run_id": None,
        "snapshot_content_sha256": None,
        "semantic_persistence_sha256": None,
        "captured_at": None,
        "as_of": raw.get("as_of") if isinstance(raw.get("as_of"), str) else None,
        "deadline": (
            raw.get("deadline")
            if isinstance(raw.get("deadline"), str)
            else None
        ),
        "complete_count": 0,
        "partial_count": 0,
        "missing_count": 0,
        "unsupported_count": 0,
        "available_source_count": 0,
        "unavailable_source_count": 0,
        "event_audit": [],
        "source_artifacts": [],
    }


def _write_audit(
    report: Mapping[str, Any],
    output: Path,
) -> SportsHistoryBackfillAuditPaths:
    paths = SportsHistoryBackfillAuditPaths(
        json=output / "sports-history-backfill.json",
        csv=output / "sports-history-backfill.csv",
        markdown=output / "sports-history-backfill.md",
    )
    _write_atomic(
        paths.json,
        (
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n"
        ).encode("utf-8"),
    )
    columns = (
        "manifest_index",
        "drawing_id",
        "drawing_number",
        "provider",
        "status",
        "run_id",
        "snapshot_content_sha256",
        "semantic_persistence_sha256",
        "as_of",
        "complete_count",
        "partial_count",
        "missing_count",
        "available_source_count",
        "unavailable_source_count",
        "error",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in report["snapshots"]:
        writer.writerow({name: row.get(name) for name in columns})
    _write_atomic(paths.csv, stream.getvalue().encode("utf-8"))
    _write_atomic(paths.markdown, _audit_markdown(report).encode("utf-8"))
    return paths


def _audit_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# OFFLINE RAW-CAPTURE BACKFILL",
        "",
        "- Artifact class: `SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_AUDIT`",
        f"- Status: `{report['status']}`",
        f"- Validation only: `{str(report['validation_only']).lower()}`",
        "- Network requests: `0`",
        f"- Database writes: `{report['database_writes']}`",
        "- Package influence: `NONE`",
        "- Automatic wagering: `false`",
        f"- Manifest SHA-256: `{report['manifest_semantic_sha256']}`",
        f"- Audit SHA-256: `{report['audit_sha256']}`",
        "",
        "| Index | Drawing | Provider | Result | Complete | Partial | Missing | "
        "Available sources | Unavailable sources | Error |",
        "|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["snapshots"]:
        lines.append(
            "| "
            + " | ".join(
                (
                    str(row["manifest_index"]),
                    _markdown(row["drawing_number"]),
                    _markdown(row["provider"]),
                    _markdown(row["status"]),
                    str(row["complete_count"]),
                    str(row["partial_count"]),
                    str(row["missing_count"]),
                    str(row["available_source_count"]),
                    str(row["unavailable_source_count"]),
                    _markdown(row["error"]),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _verified_file(
    root: Path,
    path_value: object,
    sha256_value: object,
    name: str,
) -> Path:
    path = _contained_file(root, path_value, name)
    expected = _sha256(sha256_value, f"{name} SHA-256")
    observed = _file_sha256(path)
    if observed != expected:
        raise ValueError(f"{name} SHA-256 mismatch")
    return path


def _contained_file(root: Path, value: object, name: str) -> Path:
    text = str(value) if isinstance(value, Path) else _text(value, f"{name} path")
    candidate = Path(text)
    candidate = candidate if candidate.is_absolute() else root / candidate
    if candidate.is_symlink():
        raise ValueError(f"{name} cannot be a symlink")
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{name} must stay inside project root") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{name} cannot traverse a symlink")
    if not resolved.is_file():
        raise ValueError(f"{name} is missing")
    return resolved


def _contained_output_path(root: Path, value: str | Path, name: str) -> Path:
    candidate = Path(value)
    candidate = candidate if candidate.is_absolute() else root / candidate
    if candidate.is_symlink():
        raise ValueError(f"{name} cannot be a symlink")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{name} must stay inside project root") from error
    return resolved


def _json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{name} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} JSON must be an object")
    return value


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _require_exact(observed: object, expected: object, name: str) -> None:
    if observed != expected:
        raise ValueError(f"{name} mismatch")


def _text(value: object, name: str) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError(f"{name} must be text")
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _safe_positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a non-negative integer") from None
    if parsed < 0 or str(value).strip() != str(parsed):
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


def _event_order(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in range(15):
        raise ValueError("schedule event_order must be in range 0 through 14")
    return value


def _sha256(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _safe_sha256(value: object) -> str | None:
    try:
        return _sha256(value, "SHA-256")
    except ValueError:
        return None


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _bounded_error(error: Exception, root: Path) -> str:
    text = " ".join(str(error).split()).replace(str(root), "<project>")
    return (text or type(error).__name__)[:500]


def _markdown(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
