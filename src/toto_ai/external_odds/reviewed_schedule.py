from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

REVIEWED_SCHEDULE_PROVIDER = "reviewed-schedule"
REVIEWED_SCHEDULE_SCHEMA_VERSION = 1

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ROOT_FIELDS = frozenset(
    ("schema_version", "catalog_id", "generated_at", "records")
)
_RECORD_FIELDS = frozenset(
    (
        "evidence_id",
        "drawing_id",
        "drawing_number",
        "target_fingerprint",
        "event_order",
        "target_event_id",
        "reviewer",
        "reviewed_at",
        "claims",
    )
)
_CLAIM_FIELDS = frozenset(
    (
        "source_name",
        "role",
        "source_url",
        "snapshot_path",
        "snapshot_sha256",
        "captured_at",
        "home_name",
        "away_name",
        "competition",
        "sport",
        "gender_age_class",
        "starts_at",
        "status",
        "native_fixture_id",
        "native_home_team_id",
        "native_away_team_id",
    )
)


@dataclass(frozen=True)
class ReviewedSourceClaim:
    source_name: str
    role: Literal["official", "independent"]
    source_url: str
    snapshot_path: Path
    snapshot_sha256: str
    captured_at: datetime
    home_name: str
    away_name: str
    competition: str
    sport: str
    gender_age_class: str
    starts_at: datetime
    status: Literal["scheduled"]
    native_fixture_id: str | None
    native_home_team_id: str | None
    native_away_team_id: str | None


@dataclass(frozen=True)
class ReviewedScheduleEvidence:
    evidence_id: str
    drawing_id: int
    drawing_number: int
    target_fingerprint: str
    event_order: int
    target_event_id: int
    reviewer: str
    reviewed_at: datetime
    claims: tuple[ReviewedSourceClaim, ...]
    semantic_hash: str
    source_provider: str = REVIEWED_SCHEDULE_PROVIDER
    source_fixture_id: None = None
    schedule_only: bool = True

    @property
    def starts_at(self) -> datetime:
        return self.claims[0].starts_at

    @property
    def sport(self) -> str:
        return self.claims[0].sport

    @property
    def competition(self) -> str:
        return self.claims[0].competition

    @property
    def gender_age_class(self) -> str:
        return self.claims[0].gender_age_class

    @property
    def home_name(self) -> str:
        return self.claims[0].home_name

    @property
    def away_name(self) -> str:
        return self.claims[0].away_name


@dataclass(frozen=True)
class ReviewedScheduleCatalog:
    schema_version: Literal[1]
    catalog_id: str
    generated_at: datetime
    semantic_hash: str
    records: tuple[ReviewedScheduleEvidence, ...]
    path: Path


def load_reviewed_schedule_catalog(
    path: Path,
    *,
    evaluated_at: datetime,
    max_age: timedelta,
) -> ReviewedScheduleCatalog:
    """Load strict, snapshot-backed schedule evidence.

    This parser is intentionally independent of API-Sports and never creates a
    provider fixture identity.
    """
    path = Path(path).resolve()
    evaluated_at = _utc_datetime("evaluated_at", evaluated_at)
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("reviewed schedule catalog is unreadable") from error
    root = _exact_mapping(payload, _ROOT_FIELDS, "catalog")
    if root["schema_version"] != REVIEWED_SCHEDULE_SCHEMA_VERSION:
        raise ValueError("reviewed schedule catalog schema_version must be 1")
    catalog_id = _text("catalog_id", root["catalog_id"])
    generated_at = _parse_utc("generated_at", root["generated_at"])
    if generated_at > evaluated_at:
        raise ValueError("catalog generated_at is in the future")
    raw_records = root["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("catalog records must be a non-empty list")
    records = tuple(
        _parse_record(
            item,
            catalog_dir=path.parent,
            evaluated_at=evaluated_at,
            max_age=max_age,
        )
        for item in raw_records
    )
    evidence_ids = tuple(record.evidence_id for record in records)
    target_keys = tuple(
        (
            record.drawing_id,
            record.drawing_number,
            record.target_fingerprint,
            record.event_order,
            record.target_event_id,
        )
        for record in records
    )
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("evidence_id values must be unique")
    if len(set(target_keys)) != len(target_keys):
        raise ValueError("reviewed evidence target bindings must be unique")
    canonical = {
        "schema_version": REVIEWED_SCHEDULE_SCHEMA_VERSION,
        "catalog_id": catalog_id,
        "generated_at": _iso(generated_at),
        "records": [
            _canonical_record(record, include_semantic_hash=True)
            for record in sorted(records, key=lambda item: item.evidence_id)
        ],
    }
    return ReviewedScheduleCatalog(
        schema_version=REVIEWED_SCHEDULE_SCHEMA_VERSION,
        catalog_id=catalog_id,
        generated_at=generated_at,
        semantic_hash=_hash(canonical),
        records=tuple(sorted(records, key=lambda item: item.evidence_id)),
        path=path,
    )


def select_reviewed_evidence(
    catalog: ReviewedScheduleCatalog,
    *,
    drawing_id: int,
    drawing_number: int,
    target_fingerprint: str,
    event_order: int,
    target_event_id: int,
) -> ReviewedScheduleEvidence:
    key = (
        drawing_id,
        drawing_number,
        target_fingerprint,
        event_order,
        target_event_id,
    )
    matches = tuple(
        record
        for record in catalog.records
        if (
            record.drawing_id,
            record.drawing_number,
            record.target_fingerprint,
            record.event_order,
            record.target_event_id,
        )
        == key
    )
    if len(matches) != 1:
        raise ValueError("exact reviewed evidence record is missing or ambiguous")
    return matches[0]


def revalidate_reviewed_catalog(
    path: Path,
    *,
    expected_catalog_hash: str,
    evaluated_at: datetime,
    max_age: timedelta,
) -> ReviewedScheduleCatalog:
    catalog = load_reviewed_schedule_catalog(
        path, evaluated_at=evaluated_at, max_age=max_age
    )
    if catalog.semantic_hash != expected_catalog_hash:
        raise ValueError("reviewed schedule catalog changed after preflight")
    return catalog


def reviewed_catalog_input_paths(
    catalog: ReviewedScheduleCatalog,
) -> tuple[Path, ...]:
    """Return the exact catalog and snapshot files that must stay immutable."""
    snapshots = {
        (catalog.path.parent / claim.snapshot_path).resolve()
        for record in catalog.records
        for claim in record.claims
    }
    return (catalog.path.resolve(), *tuple(sorted(snapshots)))


def _parse_record(
    value: object,
    *,
    catalog_dir: Path,
    evaluated_at: datetime,
    max_age: timedelta,
) -> ReviewedScheduleEvidence:
    row = _exact_mapping(value, _RECORD_FIELDS, "reviewed evidence")
    evidence_id = _text("evidence_id", row["evidence_id"])
    drawing_id = _positive_int("drawing_id", row["drawing_id"])
    drawing_number = _positive_int("drawing_number", row["drawing_number"])
    fingerprint = _digest("target_fingerprint", row["target_fingerprint"])
    event_order = row["event_order"]
    if (
        not isinstance(event_order, int)
        or isinstance(event_order, bool)
        or not 0 <= event_order < 15
    ):
        raise ValueError("event_order must be from 0 through 14")
    target_event_id = _positive_int("target_event_id", row["target_event_id"])
    reviewer = _text("reviewer", row["reviewer"])
    reviewed_at = _parse_utc("reviewed_at", row["reviewed_at"])
    if reviewed_at > evaluated_at:
        raise ValueError("reviewed_at is in the future")
    raw_claims = row["claims"]
    if not isinstance(raw_claims, list) or len(raw_claims) < 2:
        raise ValueError(
            "production reviewed evidence requires official and independent claims"
        )
    claims = tuple(
        _parse_claim(
            item,
            catalog_dir=catalog_dir,
            evaluated_at=evaluated_at,
            max_age=max_age,
        )
        for item in raw_claims
    )
    roles = [claim.role for claim in claims]
    if roles.count("official") != 1 or roles.count("independent") < 1:
        raise ValueError(
            "production reviewed evidence requires one official and independent claims"
        )
    if len({claim.source_name for claim in claims}) != len(claims):
        raise ValueError("reviewed claim sources must be unique")
    if reviewed_at < max(claim.captured_at for claim in claims):
        raise ValueError("reviewed_at must not precede claim capture")
    _validate_claim_agreement(claims)
    seed = {
        "evidence_id": evidence_id,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "target_fingerprint": fingerprint,
        "event_order": event_order,
        "target_event_id": target_event_id,
        "reviewer": reviewer,
        "reviewed_at": _iso(reviewed_at),
        "claims": [_canonical_claim(claim) for claim in claims],
    }
    return ReviewedScheduleEvidence(
        evidence_id=evidence_id,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        target_fingerprint=fingerprint,
        event_order=event_order,
        target_event_id=target_event_id,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        claims=tuple(sorted(claims, key=lambda claim: (claim.role, claim.source_name))),
        semantic_hash=_hash(seed),
    )


def _parse_claim(
    value: object,
    *,
    catalog_dir: Path,
    evaluated_at: datetime,
    max_age: timedelta,
) -> ReviewedSourceClaim:
    row = _exact_mapping(value, _CLAIM_FIELDS, "reviewed claim")
    source_name = _text("source_name", row["source_name"])
    role = row["role"]
    if role not in {"official", "independent"}:
        raise ValueError("claim role must be official or independent")
    source_url = _text("source_url", row["source_url"])
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("source_url must be HTTPS")
    snapshot_value = _text("snapshot_path", row["snapshot_path"])
    snapshot_relative = Path(snapshot_value)
    if snapshot_relative.is_absolute() or ".." in snapshot_relative.parts:
        raise ValueError("snapshot_path must be a contained relative path")
    snapshot_path = (catalog_dir / snapshot_relative).resolve()
    try:
        snapshot_path.relative_to(catalog_dir.resolve())
    except ValueError as error:
        raise ValueError("snapshot_path escapes the catalog directory") from error
    if not snapshot_path.is_file():
        raise ValueError("reviewed source snapshot is missing")
    snapshot_sha256 = _digest("snapshot_sha256", row["snapshot_sha256"])
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != snapshot_sha256:
        raise ValueError("reviewed source snapshot hash mismatch")
    captured_at = _parse_utc("captured_at", row["captured_at"])
    if captured_at > evaluated_at:
        raise ValueError("claim capture is in the future")
    if evaluated_at - captured_at > max_age:
        raise ValueError("reviewed schedule claim is stale")
    starts_at = _parse_utc("starts_at", row["starts_at"])
    status = row["status"]
    if status != "scheduled":
        raise ValueError("reviewed claim status must be scheduled")
    return ReviewedSourceClaim(
        source_name=source_name,
        role=role,
        source_url=source_url,
        snapshot_path=snapshot_relative,
        snapshot_sha256=snapshot_sha256,
        captured_at=captured_at,
        home_name=_text("home_name", row["home_name"]),
        away_name=_text("away_name", row["away_name"]),
        competition=_text("competition", row["competition"]),
        sport=_text("sport", row["sport"]),
        gender_age_class=_text("gender_age_class", row["gender_age_class"]),
        starts_at=starts_at,
        status="scheduled",
        native_fixture_id=_optional_text("native_fixture_id", row["native_fixture_id"]),
        native_home_team_id=_optional_text(
            "native_home_team_id", row["native_home_team_id"]
        ),
        native_away_team_id=_optional_text(
            "native_away_team_id", row["native_away_team_id"]
        ),
    )


def _validate_claim_agreement(claims: tuple[ReviewedSourceClaim, ...]) -> None:
    first = claims[0]
    fields = (
        "home_name",
        "away_name",
        "competition",
        "sport",
        "gender_age_class",
        "starts_at",
        "status",
    )
    for claim in claims[1:]:
        if any(getattr(claim, field) != getattr(first, field) for field in fields):
            raise ValueError("reviewed schedule claims disagree")


def _canonical_record(
    record: ReviewedScheduleEvidence, *, include_semantic_hash: bool
) -> dict[str, object]:
    result: dict[str, object] = {
        "evidence_id": record.evidence_id,
        "drawing_id": record.drawing_id,
        "drawing_number": record.drawing_number,
        "target_fingerprint": record.target_fingerprint,
        "event_order": record.event_order,
        "target_event_id": record.target_event_id,
        "reviewer": record.reviewer,
        "reviewed_at": _iso(record.reviewed_at),
        "claims": [_canonical_claim(claim) for claim in record.claims],
    }
    if include_semantic_hash:
        result["semantic_hash"] = record.semantic_hash
    return result


def _canonical_claim(claim: ReviewedSourceClaim) -> dict[str, object]:
    return {
        "source_name": claim.source_name,
        "role": claim.role,
        "source_url": claim.source_url,
        "snapshot_path": claim.snapshot_path.as_posix(),
        "snapshot_sha256": claim.snapshot_sha256,
        "captured_at": _iso(claim.captured_at),
        "home_name": claim.home_name,
        "away_name": claim.away_name,
        "competition": claim.competition,
        "sport": claim.sport,
        "gender_age_class": claim.gender_age_class,
        "starts_at": _iso(claim.starts_at),
        "status": claim.status,
        "native_fixture_id": claim.native_fixture_id,
        "native_home_team_id": claim.native_home_team_id,
        "native_away_team_id": claim.native_away_team_id,
    }


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_mapping(
    value: object, fields: frozenset[str], name: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} must use the exact schema")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be canonical non-empty text")
    return value


def _optional_text(name: str, value: object) -> str | None:
    return None if value is None else _text(name, value)


def _positive_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _digest(name: str, value: object) -> str:
    value = _text(name, value)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _parse_utc(name: str, value: object) -> datetime:
    text = _text(name, value)
    if not text.endswith("Z"):
        raise ValueError(f"{name} must use canonical UTC Z format")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name} must be a valid UTC datetime") from error
    return _utc_datetime(name, parsed)


def _utc_datetime(name: str, value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
