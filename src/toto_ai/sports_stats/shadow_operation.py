from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from toto_ai.analytics.api_inspector import resolve_drawing_reference
from toto_ai.analytics.history import normalize_result
from toto_ai.api.detail_cache import load_drawing_detail_cache
from toto_ai.db.models import Event
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.external_odds.team_registry import (
    load_ready_drawing_pins,
)
from toto_ai.sports_stats.evaluation import (
    ShadowEvaluationRecord,
    ShadowEvaluationResult,
    evaluate_shadow_records,
    write_shadow_evaluation_reports,
)
from toto_ai.sports_stats.probabilities import (
    BLOCKING_INTEGRITY_FALLBACKS,
    SportsShadowArtifact,
    build_shadow_probability_artifact,
    load_shadow_probability_artifact,
    write_shadow_probability_artifact,
)
from toto_ai.sports_stats.storage import (
    load_latest_eligible_snapshot,
)


def build_and_write_sports_probability_shadow(
    *,
    db: str,
    drawing_id: int | None,
    drawing_number: int | None,
    as_of: datetime,
    raw_cache_dir: str,
    report_dir: str,
) -> tuple[SportsShadowArtifact, Path]:
    _utc("as_of", as_of)
    if (drawing_id is None) == (drawing_number is None):
        raise ValueError("choose exactly one of --drawing-id or --drawing-number")
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        reference = resolve_drawing_reference(
            session,
            drawing_id=drawing_id,
            number=drawing_number,
        )
    raw_root = Path(raw_cache_dir).resolve()
    record = load_drawing_detail_cache(
        reference.drawing_id,
        cache_dir=raw_root,
        max_age_seconds=None,
        now=as_of,
        allowed_root=raw_root,
    )
    if record.fetched_at > as_of:
        raise ValueError("target payload was captured after shadow as-of")
    target = parse_target_drawing(record.payload, fetched_at=record.fetched_at)
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    snapshot = load_latest_eligible_snapshot(
        session_factory,
        drawing_id=target.drawing_id,
        drawing_fingerprint=fingerprint,
        as_of=as_of,
    )
    if snapshot is None:
        raise ValueError("no immutable pre-match sports-stat snapshot was found")
    pins = load_ready_drawing_pins(
        session_factory,
        drawing_id=target.drawing_id,
        drawing_fingerprint=fingerprint,
        provider=snapshot.provider,
    )
    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=pins,
        as_of=as_of,
    )
    return artifact, write_shadow_probability_artifact(
        artifact,
        report_dir=report_dir,
    )


def evaluate_stored_sports_probability_shadow(
    *,
    db: str,
    last: int,
    report_dir: str,
    minimum_drawings: int,
    minimum_events: int,
    minimum_sports_coverage: float,
    calibration_tolerance: float,
) -> tuple[ShadowEvaluationResult, tuple[Path, Path, Path]]:
    if type(last) is not int or last <= 0:
        raise ValueError("last must be a positive integer")
    engine = init_db(db)
    session_factory = get_session_factory(engine)
    artifact_root = Path(report_dir)
    artifacts = tuple(
        load_shadow_probability_artifact(path)
        for path in sorted(artifact_root.glob("sports_probability_shadow_*_*.json"))
    )
    latest_by_drawing: dict[int, SportsShadowArtifact] = {}
    for artifact in artifacts:
        previous = latest_by_drawing.get(artifact.drawing_id)
        if previous is None or (artifact.as_of, artifact.artifact_sha256) > (
            previous.as_of,
            previous.artifact_sha256,
        ):
            latest_by_drawing[artifact.drawing_id] = artifact
    prediction_rows = tuple(
        sorted(
            latest_by_drawing.values(),
            key=lambda artifact: (
                artifact.as_of,
                artifact.drawing_id,
                artifact.artifact_sha256,
            ),
        )[-last:]
    )

    records: list[ShadowEvaluationRecord] = []
    for artifact in prediction_rows:
        # The evaluator consumes only BK rows embedded in the immutable shadow
        # artifact. Mutable current Quote rows are intentionally never read.
        actual = _load_actual_result(session_factory, artifact.drawing_id)
        if actual is None:
            continue
        for event, outcome in zip(artifact.events, actual, strict=True):
            event_failures = list(artifact.validation_failures)
            if event.fallback_reason in BLOCKING_INTEGRITY_FALLBACKS:
                event_failures.append(str(event.fallback_reason))
            records.append(
                ShadowEvaluationRecord(
                    drawing_id=artifact.drawing_id,
                    drawing_number=artifact.drawing_number,
                    event_order=event.event_order,
                    as_of=artifact.as_of,
                    actual=outcome,
                    bk_probabilities=event.bk_probabilities,
                    sports_probabilities=event.sports_probabilities,
                    candidate_blend_probabilities=(
                        event.candidate_blend_probabilities
                    ),
                    sports_used=event.probability_source == "sports_shadow",
                    fallback_reason=event.fallback_reason,
                    validation_failures=tuple(dict.fromkeys(event_failures)),
                )
            )
    result = evaluate_shadow_records(
        tuple(records),
        minimum_drawings=minimum_drawings,
        minimum_events=minimum_events,
        minimum_sports_coverage=minimum_sports_coverage,
        calibration_tolerance=calibration_tolerance,
    )
    return result, write_shadow_evaluation_reports(result, report_dir=report_dir)


def _load_actual_result(session_factory: Any, drawing_id: int) -> str | None:
    with session_factory() as session:
        events = tuple(
            session.scalars(
                select(Event)
                .where(Event.drawing_id == drawing_id)
                .order_by(Event.event_order)
            )
        )
    if len(events) != 15 or tuple(event.event_order for event in events) != tuple(
        range(15)
    ):
        return None
    outcomes = tuple(normalize_result(event.result) for event in events)
    if any(outcome not in {"1", "X", "2"} for outcome in outcomes):
        return None
    return "".join(str(outcome) for outcome in outcomes)


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
