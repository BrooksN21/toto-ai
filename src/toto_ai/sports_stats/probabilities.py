from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toto_ai.external_odds.domain import OutcomeTriplet, TargetDrawing
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.domain import (
    FootballEventFeatureSnapshot,
    SportsStatsRunSnapshot,
    canonical_sha256,
)

SHADOW_PROBABILITY_SCHEMA_VERSION = 1
SHADOW_STATUS = "NOT_ACTIVATED"
BLOCKING_INTEGRITY_FALLBACKS = frozenset(
    {
        "as_of_not_pre_deadline",
        "authoritative_bk_snapshot_mismatch",
        "authoritative_target_fingerprint_mismatch",
        "authoritative_target_unavailable",
        "drawing_fingerprint_mismatch",
        "drawing_id_mismatch",
        "drawing_number_mismatch",
        "orientation_evidence_missing",
        "orientation_mismatch",
        "orientation_missing",
        "pre_match_boundary_failed",
        "snapshot_after_as_of",
        "snapshot_hash_mismatch",
        "source_after_as_of",
        "target_event_identity_mismatch",
    }
)


@dataclass(frozen=True)
class ShadowEventProbability:
    event_id: str
    event_order: int
    bk_probabilities: OutcomeTriplet
    sports_probabilities: OutcomeTriplet
    candidate_blend_probabilities: OutcomeTriplet
    probability_source: str
    blend_weight: float
    fallback_reason: str | None
    features: Mapping[str, Any]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class SportsShadowArtifact:
    schema_version: int
    status: str
    model_status: str
    model_definition: str
    drawing_id: int
    drawing_number: int | None
    drawing_fingerprint: str
    generated_at: datetime
    as_of: datetime
    deadline: datetime
    snapshot_run_id: str
    snapshot_content_sha256: str
    authority_status: str
    authority_fetched_at: datetime | None
    authoritative_target_fingerprint: str | None
    bk_snapshot_sha256: str | None
    sports_coverage_count: int
    fallback_count: int
    validation_failures: tuple[str, ...]
    events: tuple[ShadowEventProbability, ...]
    artifact_sha256: str

    def canonical_payload(self) -> dict[str, Any]:
        payload = _json_ready(asdict(self))
        payload.pop("artifact_sha256")
        return payload

    def to_payload(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


def build_shadow_probability_artifact(
    *,
    target: TargetDrawing,
    snapshot: SportsStatsRunSnapshot,
    pins: Sequence[DrawingEventPinRecord],
    as_of: datetime,
    generated_at: datetime | None = None,
) -> SportsShadowArtifact:
    """Build an immutable shadow-only probability artifact.

    No value returned by this module is passed into production EV/package
    selection. Invalid or incomplete sports evidence falls back to the exact
    normalized TotoBrief BK row for that event.
    """
    _utc("as_of", as_of)
    produced_at = as_of if generated_at is None else generated_at
    _utc("generated_at", produced_at)
    expected_fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    expected_event_ids = tuple(str(event.event_id) for event in target.events)
    raw_bk_probabilities = tuple(event.bk_probabilities for event in target.events)
    normalized_bk_probabilities = tuple(
        _normalize(row) for row in raw_bk_probabilities
    )
    return build_shadow_probability_artifact_from_snapshot(
        snapshot=snapshot,
        pins=pins,
        bk_probabilities=raw_bk_probabilities,
        as_of=as_of,
        generated_at=produced_at,
        expected_drawing_id=target.drawing_id,
        expected_drawing_number=target.drawing_number,
        expected_fingerprint=expected_fingerprint,
        expected_event_ids=expected_event_ids,
        authority_fetched_at=target.fetched_at,
        authoritative_target_fingerprint=expected_fingerprint,
        bk_snapshot_sha256=_bk_snapshot_sha256(
            drawing_id=target.drawing_id,
            drawing_fingerprint=expected_fingerprint,
            authority_fetched_at=target.fetched_at,
            bk_probabilities=normalized_bk_probabilities,
        ),
    )


def build_shadow_probability_artifact_from_snapshot(
    *,
    snapshot: SportsStatsRunSnapshot,
    pins: Sequence[DrawingEventPinRecord],
    bk_probabilities: Sequence[OutcomeTriplet],
    as_of: datetime,
    expected_drawing_id: int | None = None,
    expected_drawing_number: int | None = None,
    expected_fingerprint: str | None = None,
    expected_event_ids: Sequence[str] | None = None,
    authority_fetched_at: datetime | None = None,
    authoritative_target_fingerprint: str | None = None,
    bk_snapshot_sha256: str | None = None,
    generated_at: datetime | None = None,
) -> SportsShadowArtifact:
    _utc("as_of", as_of)
    produced_at = as_of if generated_at is None else generated_at
    _utc("generated_at", produced_at)
    rows = tuple(_normalize(row) for row in bk_probabilities)
    if len(rows) != 15:
        raise ValueError("exactly 15 normalized BK rows are required")

    failures = _global_validation_failures(
        snapshot=snapshot,
        as_of=as_of,
        expected_drawing_id=expected_drawing_id,
        expected_drawing_number=expected_drawing_number,
        expected_fingerprint=expected_fingerprint,
        expected_event_ids=expected_event_ids,
        generated_at=produced_at,
        authority_fetched_at=authority_fetched_at,
        authoritative_target_fingerprint=authoritative_target_fingerprint,
        bk_snapshot_sha256=bk_snapshot_sha256,
        bk_probabilities=rows,
    )
    ordered_pins = tuple(sorted(pins, key=lambda pin: pin.event_order))
    pin_orders = tuple(pin.event_order for pin in ordered_pins)
    pins_are_valid = (
        all(order in range(15) for order in pin_orders)
        and len(set(pin_orders)) == len(pin_orders)
    )
    if not pins_are_valid:
        failures = (*failures, "orientation_evidence_missing")
    pins_by_order = (
        {pin.event_order: pin for pin in ordered_pins}
        if pins_are_valid
        else {}
    )

    events: list[ShadowEventProbability] = []
    for order, (feature, bk_row) in enumerate(
        zip(snapshot.events, rows, strict=True)
    ):
        pin = pins_by_order.get(order)
        fallback_reason = failures[0] if failures else _event_fallback_reason(
            feature,
            pin,
            snapshot=snapshot,
            as_of=as_of,
        )
        features = _feature_payload(feature)
        feature_scope = features["model_feature_scope"]
        provenance = {
            "snapshot_run_id": snapshot.run_id,
            "snapshot_content_sha256": snapshot.content_sha256,
            "feature_sha256": feature.feature_sha256,
            "source_request_fingerprints": tuple(
                source.request_fingerprint for source in feature.source_evidence
            ),
            "source_payload_sha256": tuple(
                source.payload_sha256 for source in feature.source_evidence
            ),
            "orientation_pin_hash": None if pin is None else pin.pin_hash,
            "model_feature_scope": feature_scope,
            "sports_model": (
                "jeffreys_smoothed_venue_wdl"
                if fallback_reason is None
                else None
            ),
            "aggregate_fallback_used": False,
        }
        if fallback_reason is not None:
            events.append(
                ShadowEventProbability(
                    event_id=feature.event_id,
                    event_order=order,
                    bk_probabilities=bk_row,
                    sports_probabilities=bk_row,
                    candidate_blend_probabilities=bk_row,
                    probability_source="totobrief_bk_fallback",
                    blend_weight=0.0,
                    fallback_reason=fallback_reason,
                    features=features,
                    provenance=provenance,
                )
            )
            continue

        sports_row = _sports_venue_probabilities(feature)
        sample_count = (
            feature.home_window.home_played + feature.away_window.away_played
        )
        prior_count = 2 * snapshot.requested_history_size
        blend_weight = sample_count / (sample_count + prior_count)
        candidate = _normalize(
            tuple(
                (1.0 - blend_weight) * bk_value
                + blend_weight * sports_value
                for bk_value, sports_value in zip(
                    bk_row,
                    sports_row,
                    strict=True,
                )
            )
        )
        events.append(
            ShadowEventProbability(
                event_id=feature.event_id,
                event_order=order,
                bk_probabilities=bk_row,
                sports_probabilities=sports_row,
                candidate_blend_probabilities=candidate,
                probability_source="sports_shadow",
                blend_weight=blend_weight,
                fallback_reason=None,
                features=features,
                provenance=provenance,
            )
        )

    coverage_count = sum(
        event.probability_source == "sports_shadow" for event in events
    )
    candidate_artifact = SportsShadowArtifact(
        schema_version=SHADOW_PROBABILITY_SCHEMA_VERSION,
        status=SHADOW_STATUS,
        model_status=(
            "EXPERIMENTAL_UNTRAINED"
            if coverage_count
            else "INSUFFICIENT_EVIDENCE"
        ),
        model_definition=(
            "untrained Jeffreys-smoothed venue-only WDL projection using "
            "home-team home records and away-team away records; missing "
            "venue evidence falls back to BK without aggregate substitution; "
            "the candidate blend is venue-evidence-count weighted"
        ),
        drawing_id=snapshot.drawing_id,
        drawing_number=snapshot.drawing_number,
        drawing_fingerprint=snapshot.drawing_fingerprint,
        generated_at=produced_at,
        as_of=as_of,
        deadline=snapshot.deadline,
        snapshot_run_id=snapshot.run_id,
        snapshot_content_sha256=snapshot.content_sha256,
        authority_status=(
            "FROZEN_PRE_AS_OF"
            if authority_fetched_at is not None
            and authoritative_target_fingerprint is not None
            and bk_snapshot_sha256 is not None
            and not any(
                reason.startswith("authoritative_") for reason in failures
            )
            else "UNAVAILABLE"
        ),
        authority_fetched_at=authority_fetched_at,
        authoritative_target_fingerprint=authoritative_target_fingerprint,
        bk_snapshot_sha256=bk_snapshot_sha256,
        sports_coverage_count=coverage_count,
        fallback_count=15 - coverage_count,
        validation_failures=tuple(dict.fromkeys(failures)),
        events=tuple(events),
        artifact_sha256="0" * 64,
    )
    return replace(
        candidate_artifact,
        artifact_sha256=_sha256(candidate_artifact.canonical_payload()),
    )


def write_shadow_probability_artifact(
    artifact: SportsShadowArtifact,
    *,
    report_dir: str | Path = "reports/sports-probability-shadow",
) -> Path:
    if artifact.status != SHADOW_STATUS:
        raise ValueError("sports probability artifact must remain NOT_ACTIVATED")
    if artifact.artifact_sha256 != _sha256(artifact.canonical_payload()):
        raise ValueError("sports probability artifact hash mismatch")
    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    drawing = artifact.drawing_number or artifact.drawing_id
    path = output_dir / (
        f"sports_probability_shadow_{drawing}_{artifact.artifact_sha256[:16]}.json"
    )
    encoded = json.dumps(
        artifact.to_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    expected = f"{encoded}\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != expected:
            raise ValueError("immutable sports probability artifact conflict")
    else:
        path.write_text(expected, encoding="utf-8")
    return path


def load_shadow_probability_artifact(
    path: str | Path,
) -> SportsShadowArtifact:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("sports probability artifact must be an object")
    values = dict(raw)
    raw_events = values.pop("events", None)
    if not isinstance(raw_events, list) or len(raw_events) != 15:
        raise ValueError("sports probability artifact requires 15 events")
    events = tuple(_event_from_payload(item) for item in raw_events)
    generated_at = _parse_utc(values.pop("generated_at"))
    as_of = _parse_utc(values.pop("as_of"))
    deadline = _parse_utc(values.pop("deadline"))
    authority_fetched_value = values.pop("authority_fetched_at")
    authority_fetched_at = (
        None
        if authority_fetched_value is None
        else _parse_utc(authority_fetched_value)
    )
    validation_failures = tuple(values.pop("validation_failures"))
    artifact = SportsShadowArtifact(
        **values,
        generated_at=generated_at,
        as_of=as_of,
        deadline=deadline,
        authority_fetched_at=authority_fetched_at,
        validation_failures=validation_failures,
        events=events,
    )
    if artifact.status != SHADOW_STATUS:
        raise ValueError("sports probability artifact is not NOT_ACTIVATED")
    if artifact.artifact_sha256 != _sha256(artifact.canonical_payload()):
        raise ValueError("sports probability artifact hash mismatch")
    authority_failures = _authority_validation_failures(
        snapshot_fingerprint=artifact.drawing_fingerprint,
        as_of=artifact.as_of,
        deadline=artifact.deadline,
        generated_at=artifact.generated_at,
        authority_fetched_at=artifact.authority_fetched_at,
        authoritative_target_fingerprint=(
            artifact.authoritative_target_fingerprint
        ),
        bk_snapshot_sha256=artifact.bk_snapshot_sha256,
        bk_probabilities=tuple(event.bk_probabilities for event in artifact.events),
        drawing_id=artifact.drawing_id,
    )
    if authority_failures:
        raise ValueError(
            "frozen shadow authority validation failed: "
            + ",".join(authority_failures)
        )
    return artifact


def _global_validation_failures(
    *,
    snapshot: SportsStatsRunSnapshot,
    as_of: datetime,
    expected_drawing_id: int | None,
    expected_drawing_number: int | None,
    expected_fingerprint: str | None,
    expected_event_ids: Sequence[str] | None,
    generated_at: datetime,
    authority_fetched_at: datetime | None,
    authoritative_target_fingerprint: str | None,
    bk_snapshot_sha256: str | None,
    bk_probabilities: Sequence[OutcomeTriplet],
) -> tuple[str, ...]:
    failures: list[str] = []
    if expected_drawing_id is not None and snapshot.drawing_id != expected_drawing_id:
        failures.append("drawing_id_mismatch")
    if (
        expected_drawing_number is not None
        and snapshot.drawing_number != expected_drawing_number
    ):
        failures.append("drawing_number_mismatch")
    if (
        expected_fingerprint is not None
        and snapshot.drawing_fingerprint != expected_fingerprint
    ):
        failures.append("drawing_fingerprint_mismatch")
    if expected_event_ids is not None and tuple(
        event.event_id for event in snapshot.events
    ) != tuple(str(value) for value in expected_event_ids):
        failures.append("target_event_identity_mismatch")
    if snapshot.as_of > as_of or snapshot.captured_at > as_of:
        failures.append("snapshot_after_as_of")
    if as_of >= snapshot.deadline:
        failures.append("as_of_not_pre_deadline")
    failures.extend(
        _authority_validation_failures(
            snapshot_fingerprint=snapshot.drawing_fingerprint,
            as_of=as_of,
            deadline=snapshot.deadline,
            generated_at=generated_at,
            authority_fetched_at=authority_fetched_at,
            authoritative_target_fingerprint=authoritative_target_fingerprint,
            bk_snapshot_sha256=bk_snapshot_sha256,
            bk_probabilities=bk_probabilities,
            drawing_id=snapshot.drawing_id,
        )
    )
    expected_snapshot_hash = canonical_sha256(snapshot.canonical_payload())
    if (
        snapshot.run_id != expected_snapshot_hash
        or snapshot.content_sha256 != expected_snapshot_hash
        or any(
            event.feature_sha256 != canonical_sha256(event.canonical_payload())
            for event in snapshot.events
        )
    ):
        failures.append("snapshot_hash_mismatch")
    return tuple(dict.fromkeys(failures))


def _event_fallback_reason(
    feature: FootballEventFeatureSnapshot,
    pin: DrawingEventPinRecord | None,
    *,
    snapshot: SportsStatsRunSnapshot,
    as_of: datetime,
) -> str | None:
    if feature.sport != "football":
        return "unsupported_sport"
    if feature.target_starts_at <= snapshot.as_of or feature.target_starts_at <= as_of:
        return "pre_match_boundary_failed"
    if feature.home_window is None or feature.away_window is None:
        return "sports_history_missing"
    if pin is None:
        return "orientation_evidence_missing"
    if pin.drawing_id != snapshot.drawing_id:
        return "drawing_id_mismatch"
    if pin.drawing_fingerprint != snapshot.drawing_fingerprint:
        return "drawing_fingerprint_mismatch"
    if (
        pin.target_event_id != feature.event_id
        or pin.event_order != feature.event_order
    ):
        return "target_event_identity_mismatch"
    orientation = pin.provenance.get("orientation") if isinstance(
        pin.provenance, Mapping
    ) else None
    if orientation is None:
        return "orientation_missing"
    if orientation != "same":
        return "orientation_mismatch"
    if (
        pin.provider_home_team_id != feature.provider_home_team_id
        or pin.provider_away_team_id != feature.provider_away_team_id
        or pin.provider_fixture_id != feature.provider_fixture_id
        or pin.canonical_home_team_id != feature.canonical_home_team_id
        or pin.canonical_away_team_id != feature.canonical_away_team_id
        or feature.home_window.team_id != feature.provider_home_team_id
        or feature.away_window.team_id != feature.provider_away_team_id
    ):
        return "orientation_mismatch"
    if feature.home_standing is not None and (
        feature.home_standing.team_id != feature.provider_home_team_id
    ):
        return "orientation_mismatch"
    if feature.away_standing is not None and (
        feature.away_standing.team_id != feature.provider_away_team_id
    ):
        return "orientation_mismatch"
    if any(
        source.fetched_at > snapshot.as_of
        or source.fetched_at >= snapshot.deadline
        for source in feature.source_evidence
    ):
        return "source_after_as_of"
    if not _has_complete_venue_history(feature):
        return "venue_history_missing"
    return None


def _has_complete_venue_history(
    feature: FootballEventFeatureSnapshot,
) -> bool:
    home = feature.home_window
    away = feature.away_window
    return (
        home is not None
        and away is not None
        and home.home_played > 0
        and away.away_played > 0
    )


def _sports_venue_probabilities(
    feature: FootballEventFeatureSnapshot,
) -> OutcomeTriplet:
    home = feature.home_window
    away = feature.away_window
    if not _has_complete_venue_history(feature) or home is None or away is None:
        raise ValueError("sports venue probabilities require both venue windows")
    # Jeffreys smoothing avoids fabricated certainty without any fitted
    # coefficient. Only venue-matched W-D-L evidence is used: the home team's
    # home record and the away team's away record.
    return _normalize(
        (
            home.home_wins + away.away_losses + 0.5,
            home.home_draws + away.away_draws + 0.5,
            home.home_losses + away.away_wins + 0.5,
        )
    )


def _feature_payload(feature: FootballEventFeatureSnapshot) -> dict[str, Any]:
    home = feature.home_window
    away = feature.away_window
    feature_scope = (
        "venue" if _has_complete_venue_history(feature) else "non_venue_unavailable"
    )
    return {
        "model_feature_scope": feature_scope,
        "feature_status": feature.status,
        "missing_reasons": feature.missing_reasons,
        "home_fixture_count": None if home is None else home.fixture_count,
        "away_fixture_count": None if away is None else away.fixture_count,
        "home_wdl": None if home is None else (home.wins, home.draws, home.losses),
        "away_wdl": None if away is None else (away.wins, away.draws, away.losses),
        "home_venue_wdl": None
        if home is None
        else (home.home_wins, home.home_draws, home.home_losses),
        "away_venue_wdl": None
        if away is None
        else (away.away_wins, away.away_draws, away.away_losses),
        "home_venue_played": None if home is None else home.home_played,
        "away_venue_played": None if away is None else away.away_played,
        "home_goals": None
        if home is None
        else (home.goals_for, home.goals_against),
        "away_goals": None
        if away is None
        else (away.goals_for, away.goals_against),
        "home_points_per_game": None if home is None else home.points_per_game,
        "away_points_per_game": None if away is None else away.points_per_game,
        "home_last5_form_points": None if home is None else home.last5_form_points,
        "away_last5_form_points": None if away is None else away.last5_form_points,
        "home_rest_days": None if home is None else home.rest_days,
        "away_rest_days": None if away is None else away.rest_days,
        "home_standing": _standing_payload(feature.home_standing),
        "away_standing": _standing_payload(feature.away_standing),
    }


def _standing_payload(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    return {
        "rank": value.rank,
        "points": value.points,
        "played": value.played,
        "goals_for": value.goals_for,
        "goals_against": value.goals_against,
    }


def _normalize(values: Sequence[float]) -> OutcomeTriplet:
    row = tuple(float(value) for value in values)
    if len(row) != 3 or any(not math.isfinite(value) or value < 0 for value in row):
        raise ValueError(
            "probability row must contain three finite non-negative values"
        )
    total = sum(row)
    if total <= 0:
        raise ValueError("probability row total must be positive")
    return row[0] / total, row[1] / total, row[2] / total


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        _utc("datetime", value)
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_ready(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bk_snapshot_sha256(
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    authority_fetched_at: datetime,
    bk_probabilities: Sequence[OutcomeTriplet],
) -> str:
    return _sha256(
        {
            "drawing_id": drawing_id,
            "drawing_fingerprint": drawing_fingerprint,
            "authority_fetched_at": authority_fetched_at,
            "bk_probabilities": tuple(tuple(row) for row in bk_probabilities),
        }
    )


def _authority_validation_failures(
    *,
    snapshot_fingerprint: str,
    as_of: datetime,
    deadline: datetime,
    generated_at: datetime,
    authority_fetched_at: datetime | None,
    authoritative_target_fingerprint: str | None,
    bk_snapshot_sha256: str | None,
    bk_probabilities: Sequence[OutcomeTriplet],
    drawing_id: int,
) -> tuple[str, ...]:
    if (
        authority_fetched_at is None
        or authoritative_target_fingerprint is None
        or bk_snapshot_sha256 is None
    ):
        return ("authoritative_target_unavailable",)
    failures: list[str] = []
    if authority_fetched_at > as_of or authority_fetched_at >= deadline:
        failures.append("authoritative_target_unavailable")
    if generated_at > as_of:
        failures.append("snapshot_after_as_of")
    if authoritative_target_fingerprint != snapshot_fingerprint:
        failures.append("authoritative_target_fingerprint_mismatch")
    expected_bk_hash = _bk_snapshot_sha256(
        drawing_id=drawing_id,
        drawing_fingerprint=authoritative_target_fingerprint,
        authority_fetched_at=authority_fetched_at,
        bk_probabilities=bk_probabilities,
    )
    if bk_snapshot_sha256 != expected_bk_hash:
        failures.append("authoritative_bk_snapshot_mismatch")
    return tuple(failures)


def _event_from_payload(value: object) -> ShadowEventProbability:
    if not isinstance(value, dict):
        raise ValueError("shadow event must be an object")
    raw = dict(value)
    features = _tuples_for_known_fields(raw.pop("features"))
    provenance = _tuples_for_known_fields(raw.pop("provenance"))
    bk_probabilities = tuple(raw.pop("bk_probabilities"))
    sports_probabilities = tuple(raw.pop("sports_probabilities"))
    candidate_blend_probabilities = tuple(
        raw.pop("candidate_blend_probabilities")
    )
    return ShadowEventProbability(
        **raw,
        bk_probabilities=bk_probabilities,
        sports_probabilities=sports_probabilities,
        candidate_blend_probabilities=candidate_blend_probabilities,
        features=features,
        provenance=provenance,
    )


def _tuples_for_known_fields(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("shadow mapping is invalid")
    converted = dict(value)
    for key, item in tuple(converted.items()):
        if isinstance(item, list):
            converted[key] = tuple(item)
    return converted


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("artifact datetime must be a string")
    parsed = datetime.fromisoformat(value)
    _utc("artifact datetime", parsed)
    return parsed.astimezone(timezone.utc)
