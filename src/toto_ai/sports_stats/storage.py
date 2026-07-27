from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from toto_ai.db.models import SportsEventFeatureSnapshot, SportsStatsRun
from toto_ai.sports_stats.domain import (
    FootballEventFeatureSnapshot,
    FootballTeamWindow,
    SourceEvidence,
    SportsStatsRunSnapshot,
    StandingRow,
    canonical_json,
    canonical_sha256,
)


def save_sports_stats_snapshot(
    session_factory: Any,
    snapshot: SportsStatsRunSnapshot,
) -> SportsStatsRunSnapshot:
    _verify_hashes(snapshot)
    encoded = canonical_json(snapshot)
    with session_factory.begin() as session:
        existing = session.get(SportsStatsRun, snapshot.run_id)
        if existing is not None:
            if existing.snapshot_json != encoded:
                raise ValueError("sports-stat run content-address conflict")
            return snapshot
        same_identity = session.scalar(
            select(SportsStatsRun).where(
                SportsStatsRun.drawing_id == snapshot.drawing_id,
                SportsStatsRun.drawing_fingerprint == snapshot.drawing_fingerprint,
                SportsStatsRun.provider == snapshot.provider,
                SportsStatsRun.as_of == snapshot.as_of.isoformat(),
            )
        )
        if same_identity is not None:
            stored = _run_from_json(same_identity.snapshot_json)
            _verify_hashes(stored)
            if _same_snapshot_evidence(stored, snapshot):
                return stored
            raise ValueError("sports-stat run identity already has different content")
        session.add(
            SportsStatsRun(
                run_id=snapshot.run_id,
                content_sha256=snapshot.content_sha256,
                schema_version=snapshot.schema_version,
                drawing_id=snapshot.drawing_id,
                drawing_number=snapshot.drawing_number,
                drawing_fingerprint=snapshot.drawing_fingerprint,
                provider=snapshot.provider,
                requested_history_size=snapshot.requested_history_size,
                captured_at=snapshot.captured_at.isoformat(),
                as_of=snapshot.as_of.isoformat(),
                deadline=snapshot.deadline.isoformat(),
                status=snapshot.status,
                complete_count=snapshot.complete_count,
                partial_count=snapshot.partial_count,
                missing_count=snapshot.missing_count,
                unsupported_count=snapshot.unsupported_count,
                requests_made=snapshot.requests_made,
                cache_hits=snapshot.cache_hits,
                source_request_fingerprints_json=canonical_json(
                    snapshot.source_request_fingerprints
                ),
                snapshot_json=encoded,
            )
        )
        for event in snapshot.events:
            session.add(
                SportsEventFeatureSnapshot(
                    run_id=snapshot.run_id,
                    drawing_id=snapshot.drawing_id,
                    event_order=event.event_order,
                    target_event_id=event.event_id,
                    sport=event.sport,
                    status=event.status,
                    missing_reasons_json=canonical_json(event.missing_reasons),
                    provider_fixture_id=event.provider_fixture_id,
                    provider_home_team_id=event.provider_home_team_id,
                    provider_away_team_id=event.provider_away_team_id,
                    league_id=event.league_id,
                    season=event.season,
                    target_starts_at=event.target_starts_at.isoformat(),
                    feature_sha256=event.feature_sha256,
                    feature_json=canonical_json(event),
                    source_evidence_json=canonical_json(event.source_evidence),
                )
            )
        try:
            session.flush()
        except IntegrityError as error:
            raise ValueError("sports-stat snapshot append conflict") from error
    return snapshot


def _same_snapshot_evidence(
    left: SportsStatsRunSnapshot,
    right: SportsStatsRunSnapshot,
) -> bool:
    return (
        left.schema_version == right.schema_version
        and left.drawing_id == right.drawing_id
        and left.drawing_number == right.drawing_number
        and left.drawing_fingerprint == right.drawing_fingerprint
        and left.provider == right.provider
        and left.requested_history_size == right.requested_history_size
        and left.captured_at == right.captured_at
        and left.as_of == right.as_of
        and left.deadline == right.deadline
        and left.status == right.status
        and left.events == right.events
        and left.complete_count == right.complete_count
        and left.partial_count == right.partial_count
        and left.missing_count == right.missing_count
        and left.unsupported_count == right.unsupported_count
        and (
            left.source_request_fingerprints
            == right.source_request_fingerprints
        )
    )


def load_sports_stats_snapshot(
    session_factory: Any,
    run_id: str,
) -> SportsStatsRunSnapshot | None:
    with session_factory() as session:
        row = session.get(SportsStatsRun, run_id)
    if row is None:
        return None
    snapshot = _run_from_json(row.snapshot_json)
    _verify_hashes(snapshot)
    return snapshot


def load_latest_eligible_snapshot(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    as_of: datetime,
    provider: str = "api-sports",
) -> SportsStatsRunSnapshot | None:
    _utc("as_of", as_of)
    with session_factory() as session:
        rows = tuple(
            session.scalars(
                select(SportsStatsRun)
                .where(
                    SportsStatsRun.drawing_id == drawing_id,
                    SportsStatsRun.drawing_fingerprint == drawing_fingerprint,
                    SportsStatsRun.provider == provider,
                    SportsStatsRun.as_of <= as_of.isoformat(),
                    SportsStatsRun.deadline > SportsStatsRun.as_of,
                )
                .order_by(SportsStatsRun.as_of.desc(), SportsStatsRun.run_id.desc())
            )
        )
    for row in rows:
        snapshot = _run_from_json(row.snapshot_json)
        _verify_hashes(snapshot)
        if snapshot.as_of <= as_of and snapshot.as_of < snapshot.deadline:
            return snapshot
    return None


def _run_from_json(value: str) -> SportsStatsRunSnapshot:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise ValueError("sports-stat snapshot JSON is invalid")
    events = tuple(_event_from_dict(item) for item in raw.pop("events"))
    captured_at = _datetime(raw.pop("captured_at"))
    as_of = _datetime(raw.pop("as_of"))
    deadline = _datetime(raw.pop("deadline"))
    fingerprints = tuple(raw.pop("source_request_fingerprints"))
    return SportsStatsRunSnapshot(
        **raw,
        captured_at=captured_at,
        as_of=as_of,
        deadline=deadline,
        events=events,
        source_request_fingerprints=fingerprints,
    )


def _event_from_dict(raw_value: object) -> FootballEventFeatureSnapshot:
    if not isinstance(raw_value, dict):
        raise ValueError("sports-stat event JSON is invalid")
    raw = dict(raw_value)
    captured_at = _datetime(raw.pop("captured_at"))
    as_of = _datetime(raw.pop("as_of"))
    deadline = _datetime(raw.pop("deadline"))
    target_starts_at = _datetime(raw.pop("target_starts_at"))
    missing_reasons = tuple(raw.pop("missing_reasons"))
    home_window = _window(raw.pop("home_window", None))
    away_window = _window(raw.pop("away_window", None))
    home_standing = _standing(raw.pop("home_standing", None))
    away_standing = _standing(raw.pop("away_standing", None))
    source_evidence = tuple(
        _source(item) for item in raw.pop("source_evidence")
    )
    return FootballEventFeatureSnapshot(
        **raw,
        captured_at=captured_at,
        as_of=as_of,
        deadline=deadline,
        target_starts_at=target_starts_at,
        missing_reasons=missing_reasons,
        home_window=home_window,
        away_window=away_window,
        home_standing=home_standing,
        away_standing=away_standing,
        source_evidence=source_evidence,
    )


def _window(value: object) -> FootballTeamWindow | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("team window JSON is invalid")
    raw = dict(value)
    fixture_ids = tuple(raw.pop("fixture_ids"))
    last_completed_value = raw.pop("last_completed_at")
    source_evidence = tuple(
        _source(item) for item in raw.pop("source_evidence")
    )
    return FootballTeamWindow(
        **raw,
        fixture_ids=fixture_ids,
        last_completed_at=(
            None
            if last_completed_value is None
            else _datetime(last_completed_value)
        ),
        source_evidence=source_evidence,
    )


def _standing(value: object) -> StandingRow | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("standing JSON is invalid")
    raw = dict(value)
    source = _source(raw.pop("source"))
    return StandingRow(**raw, source=source)


def _source(value: object) -> SourceEvidence:
    if not isinstance(value, dict):
        raise ValueError("source evidence JSON is invalid")
    raw = dict(value)
    fetched_at = _datetime(raw.pop("fetched_at"))
    return SourceEvidence(**raw, fetched_at=fetched_at)


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime JSON value is invalid")
    parsed = datetime.fromisoformat(value)
    _utc("datetime", parsed)
    return parsed.astimezone(timezone.utc)


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _verify_hashes(snapshot: SportsStatsRunSnapshot) -> None:
    for event in snapshot.events:
        expected = canonical_sha256(event.canonical_payload())
        if event.feature_sha256 != expected:
            raise ValueError("sports-stat event feature hash mismatch")
    expected_run = canonical_sha256(snapshot.canonical_payload())
    if (
        snapshot.content_sha256 != expected_run
        or snapshot.run_id != expected_run
    ):
        raise ValueError("sports-stat run content hash mismatch")
