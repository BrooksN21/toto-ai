"""Safe operator tooling for reviewed schedule evidence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from toto_ai.external_odds.schedule_evidence import (
    DEFAULT_SCHEDULE_EVIDENCE_PATH,
    ScheduleEvidenceLedger,
    ScheduleObservation,
    _name_key,
    ingest_reviewed_observation,
    load_schedule_evidence_ledger,
    validate_reviewed_observation,
)

PREPARED_REVIEW_SCHEMA_VERSION = 1
DEFAULT_REVIEWS_DIR = DEFAULT_SCHEDULE_EVIDENCE_PATH.parent / "reviews"
DEFAULT_SNAPSHOTS_DIR = DEFAULT_SCHEDULE_EVIDENCE_PATH.parent / "snapshots"
KICKOFF_TOLERANCE = timedelta(minutes=5)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_MARKDOWN_EVIDENCE = re.compile(
    r"evidence:\s*`([^`]+)`\s+[^\n]*SHA-256\s*`([0-9a-f]{64})`"
)
_MULTIPART_PUBLIC_SUFFIXES = frozenset(
    {"co.uk", "com.au", "com.br", "com.tr", "co.jp", "co.kr", "co.nz"}
)
_KNOWN_PUBLISHERS = {
    "goal-api.com": "goal-api",
    "thesportsdb.com": "thesportsdb",
    "sofascore.com": "sofascore",
    "mlsz.hu": "mlsz",
}


@dataclass(frozen=True)
class PreparedReview:
    path: Path
    sha256: str
    target: Mapping[str, object]
    observation: Mapping[str, object]
    snapshot_paths: tuple[Path, ...]


def review_prepared_schedule_evidence(
    *,
    ledger_path: Path,
    reviews_dir: Path,
    snapshots_dir: Path,
    review_path: Path,
    expected_review_sha256: str,
    apply: bool = False,
) -> dict[str, object]:
    """Validate a prepared review and optionally atomically ingest it."""

    prepared = load_prepared_review(
        ledger_path=ledger_path,
        reviews_dir=reviews_dir,
        snapshots_dir=snapshots_dir,
        review_path=review_path,
        expected_review_sha256=expected_review_sha256,
    )
    if apply:
        with _ledger_lock(Path(ledger_path)):
            before = _file_sha256(ledger_path)
            already_present = validate_reviewed_observation(
                ledger_path, prepared.observation
            )
            ledger = (
                load_schedule_evidence_ledger(ledger_path)
                if already_present
                else ingest_reviewed_observation(ledger_path, prepared.observation)
            )
            after = _file_sha256(ledger_path)
    else:
        before = _file_sha256(ledger_path)
        already_present = validate_reviewed_observation(
            ledger_path, prepared.observation
        )
        ledger = load_schedule_evidence_ledger(ledger_path)
        after = _file_sha256(ledger_path)
        if after != before:
            raise ValueError("dry-run changed the schedule evidence ledger")
    return {
        "status": (
            "already_present"
            if already_present
            else "applied"
            if apply
            else "validated_dry_run"
        ),
        "dry_run": not apply,
        "ledger_mutated": bool(apply and not already_present),
        "observation_id": prepared.observation["observation_id"],
        "drawing_number": prepared.target["drawing_number"],
        "event_order": prepared.target["event_order"],
        "ledger_sha256": after,
        "ledger_semantic_hash": ledger.semantic_hash,
    }


def load_prepared_review(
    *,
    ledger_path: Path,
    reviews_dir: Path,
    snapshots_dir: Path,
    review_path: Path,
    expected_review_sha256: str,
) -> PreparedReview:
    """Load one strict, externally hash-bound prepared-review document."""

    ledger_path = _regular_file(ledger_path, "ledger")
    reviews_dir = _directory(reviews_dir, "reviews")
    snapshots_dir = _directory(snapshots_dir, "snapshots")
    review_path = _contained_regular_file(review_path, reviews_dir, "review")
    expected_review_sha256 = _digest(expected_review_sha256, "review sha256")
    actual_review_sha256 = _file_sha256(review_path)
    if actual_review_sha256 != expected_review_sha256:
        raise ValueError("prepared review hash mismatch")
    try:
        raw = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("prepared review JSON is unreadable") from error
    _exact_fields(raw, {"schema_version", "target", "observation", "sources"}, "review")
    if raw["schema_version"] != PREPARED_REVIEW_SCHEMA_VERSION:
        raise ValueError("prepared review schema_version must be 1")
    target = _mapping(raw["target"], "target")
    _exact_fields(
        target,
        {
            "drawing_id",
            "drawing_number",
            "event_order",
            "target_event_id",
            "sport",
            "championship",
            "home_team",
            "away_team",
        },
        "target",
    )
    for name in ("drawing_id", "drawing_number", "event_order", "target_event_id"):
        if type(target[name]) is not int or int(target[name]) < 0:
            raise ValueError(f"target {name} must be a non-negative integer")
    observation = _mapping(raw["observation"], "observation")
    _exact_fields(
        observation,
        {
            "observation_id",
            "sport",
            "gender_age_class",
            "competition_aliases",
            "home_entity",
            "home_aliases",
            "away_entity",
            "away_aliases",
            "starts_at",
            "status",
            "conditional",
            "reviewer",
            "reviewed_at",
        },
        "observation",
    )
    if observation["status"] != "scheduled" or observation["conditional"] is not False:
        raise ValueError("prepared observation must be unconditional and scheduled")
    if observation["sport"] != target["sport"]:
        raise ValueError("target and observation sport conflict")
    starts_at = _utc_z(observation["starts_at"], "observation starts_at")
    reviewed_at = _utc_z(observation["reviewed_at"], "observation reviewed_at")
    sources = raw["sources"]
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("prepared review requires at least two sources")
    parsed_sources = tuple(
        _validate_source(item, snapshots_dir=snapshots_dir, starts_at=starts_at)
        for item in sources
    )
    publishers = {item["publisher"] for item in parsed_sources}
    registrable_domains = {item["registrable_domain"] for item in parsed_sources}
    if len(publishers) != len(parsed_sources):
        raise ValueError("review sources must use independent publishers")
    if len(registrable_domains) != len(parsed_sources):
        raise ValueError("review sources must use independent registrable domains")
    if (
        not any(item["role"] == "official" for item in parsed_sources)
        and sum(item["role"] == "independent" for item in parsed_sources) < 2
    ):
        raise ValueError("review requires an official or two independent sources")
    if reviewed_at < max(item["captured_at"] for item in parsed_sources):
        raise ValueError("reviewed_at precedes source capture")
    if reviewed_at >= starts_at:
        raise ValueError("reviewed_at must be before kickoff")
    _validate_team_orientation(target, observation, parsed_sources)
    ledger_root = ledger_path.parent.resolve()
    if ledger_root not in review_path.parents:
        raise ValueError("prepared review must remain under the ledger directory")
    claims = [
        {
            "source_name": item["source_name"],
            "role": item["role"],
            "source_url": item["source_url"],
        }
        for item in parsed_sources
    ]
    candidate = dict(observation) | {
        "review_document": str(review_path.relative_to(ledger_root)),
        "review_document_sha256": actual_review_sha256,
        "claims": claims,
    }
    return PreparedReview(
        path=review_path,
        sha256=actual_review_sha256,
        target=target,
        observation=candidate,
        snapshot_paths=tuple(item["snapshot_path"] for item in parsed_sources),
    )


def verify_schedule_evidence(
    *, ledger_path: Path, reviews_dir: Path, snapshots_dir: Path
) -> dict[str, object]:
    """Verify ledger -> review -> snapshot provenance without mutation."""

    ledger_path = _regular_file(ledger_path, "ledger")
    reviews_dir = _directory(reviews_dir, "reviews")
    snapshots_dir = _directory(snapshots_dir, "snapshots")
    before = _file_sha256(ledger_path)
    ledger = load_schedule_evidence_ledger(ledger_path)
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    raw_by_id = {item["observation_id"]: item for item in raw["observations"]}
    snapshot_paths: set[Path] = set()
    prepared_count = 0
    legacy_without_snapshots = 0
    for observation in ledger.observations:
        review = _contained_regular_file(
            observation.review_document, reviews_dir, "review"
        )
        if review.suffix.casefold() == ".json":
            prepared = load_prepared_review(
                ledger_path=ledger_path,
                reviews_dir=reviews_dir,
                snapshots_dir=snapshots_dir,
                review_path=review,
                expected_review_sha256=observation.review_document_sha256,
            )
            if prepared.observation != raw_by_id[observation.observation_id]:
                raise ValueError("prepared review and ledger observation differ")
            snapshot_paths.update(prepared.snapshot_paths)
            prepared_count += 1
            continue
        references = _MARKDOWN_EVIDENCE.findall(review.read_text(encoding="utf-8"))
        if not references:
            legacy_without_snapshots += 1
        for relative, digest in references:
            snapshot = _contained_regular_file(
                ledger_path.parent / relative, snapshots_dir, "snapshot"
            )
            if _file_sha256(snapshot) != digest:
                raise ValueError("review snapshot hash mismatch")
            snapshot_paths.add(snapshot)
    if _file_sha256(ledger_path) != before:
        raise ValueError("verify observed a changing ledger")
    return {
        "status": "verified",
        "ledger_sha256": before,
        "ledger_semantic_hash": ledger.semantic_hash,
        "observation_count": len(ledger.observations),
        "review_count": len(ledger.observations),
        "prepared_review_count": prepared_count,
        "verified_snapshot_count": len(snapshot_paths),
        "legacy_review_without_snapshot_count": legacy_without_snapshots,
        "mutated": False,
    }


def schedule_evidence_status(
    *, ledger_path: Path, reviews_dir: Path, snapshots_dir: Path
) -> dict[str, object]:
    """Summarize the evidence-artifact event scope by drawing/event."""

    verification = verify_schedule_evidence(
        ledger_path=ledger_path,
        reviews_dir=reviews_dir,
        snapshots_dir=snapshots_dir,
    )
    ledger = load_schedule_evidence_ledger(Path(ledger_path))
    groups: dict[tuple[int, int, int], dict[str, Any]] = {}
    prepared_targets = _prepared_target_index(reviews_dir, ledger)
    for snapshot in _iter_json_files(_directory(snapshots_dir, "snapshots")):
        try:
            row = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or not all(
            name in row for name in ("drawing_number", "event_order", "target_event_id")
        ):
            continue
        key = (
            int(row["drawing_number"]),
            int(row["event_order"]),
            int(row["target_event_id"]),
        )
        group = groups.setdefault(
            key,
            {
                "drawing_number": key[0],
                "event_order": key[1],
                "target_event_id": key[2],
                "home_team": str(
                    row.get("target_home_team") or row.get("home_name") or ""
                ),
                "away_team": str(
                    row.get("target_away_team") or row.get("away_name") or ""
                ),
                "providers": set(),
                "snapshots": [],
            },
        )
        group["providers"].add(
            str(row.get("source_provider") or row.get("source_name") or "unknown")
        )
        group["snapshots"].append(row)
    events: list[dict[str, object]] = []
    for key in sorted(groups):
        group = groups[key]
        observation = prepared_targets.get(key)
        unsupported = 0
        if observation is None:
            observation, unsupported = _matching_observation(group["snapshots"], ledger)
        consensus = bool(observation and _is_consensus(observation))
        events.append(
            {
                "drawing_number": group["drawing_number"],
                "event_order": group["event_order"],
                "target_event_id": group["target_event_id"],
                "home_team": group["home_team"],
                "away_team": group["away_team"],
                "provider_count": len(group["providers"]),
                "reviewed": observation is not None,
                "consensus": consensus,
                "observation_id": None
                if observation is None
                else observation.observation_id,
                "unsupported_alias_count": unsupported,
            }
        )
    reviewed = sum(bool(item["reviewed"]) for item in events)
    consensus = sum(bool(item["consensus"]) for item in events)
    return verification | {
        "status": "attention_required" if len(events) > reviewed else "ok",
        "scope": "evidence_artifacts",
        "event_count": len(events),
        "unresolved_count": len(events) - reviewed,
        "reviewed_count": reviewed,
        "consensus_count": consensus,
        "unsupported_alias_count": sum(
            int(item["unsupported_alias_count"]) for item in events
        ),
        "events": events,
    }


def _validate_source(
    value: object, *, snapshots_dir: Path, starts_at: datetime
) -> dict[str, Any]:
    source = _mapping(value, "source")
    _exact_fields(
        source,
        {
            "source_name",
            "role",
            "source_url",
            "snapshot",
            "snapshot_sha256",
            "home_team",
            "away_team",
            "starts_at",
            "status",
            "captured_at",
        },
        "source",
    )
    if source["role"] not in {"official", "independent"}:
        raise ValueError("source role is invalid")
    parsed = urlparse(_text(source["source_url"], "source_url"))
    domain = (parsed.hostname or "").casefold().removeprefix("www.")
    if parsed.scheme != "https" or not domain:
        raise ValueError("source URL must use a valid HTTPS domain")
    source_start = _utc_z(source["starts_at"], "source starts_at")
    captured_at = _utc_z(source["captured_at"], "source captured_at")
    if abs(source_start - starts_at) > KICKOFF_TOLERANCE:
        raise ValueError("source kickoff conflicts with observation")
    if source["status"] not in {"scheduled", "not_started"}:
        raise ValueError("source status is not acceptable")
    if captured_at >= source_start:
        raise ValueError("source evidence was captured after kickoff")
    snapshot = _contained_regular_file(
        snapshots_dir / _text(source["snapshot"], "snapshot"),
        snapshots_dir,
        "snapshot",
    )
    digest = _digest(source["snapshot_sha256"], "snapshot sha256")
    if _file_sha256(snapshot) != digest:
        raise ValueError("source snapshot hash mismatch")
    return dict(source) | {
        "domain": domain,
        "registrable_domain": _registrable_domain(domain),
        "publisher": _publisher_identity(
            _text(source["source_name"], "source_name"), domain
        ),
        "starts_at_value": source_start,
        "captured_at": captured_at,
        "snapshot_path": snapshot,
    }


def _validate_team_orientation(
    target: Mapping[str, object],
    observation: Mapping[str, object],
    sources: tuple[Mapping[str, Any], ...],
) -> None:
    home_keys = {_name_key(_text(observation["home_entity"], "home_entity"))}
    away_keys = {_name_key(_text(observation["away_entity"], "away_entity"))}
    home_keys.update(
        _name_key(_text(value, "home_alias"))
        for value in _list(observation["home_aliases"], "home_aliases")
    )
    away_keys.update(
        _name_key(_text(value, "away_alias"))
        for value in _list(observation["away_aliases"], "away_aliases")
    )
    if _name_key(_text(target["home_team"], "target home_team")) not in home_keys:
        raise ValueError("target home team is not bound to observation home aliases")
    if _name_key(_text(target["away_team"], "target away_team")) not in away_keys:
        raise ValueError("target away team is not bound to observation away aliases")
    for source in sources:
        home = _name_key(_text(source["home_team"], "source home_team"))
        away = _name_key(_text(source["away_team"], "source away_team"))
        if home not in home_keys or away not in away_keys:
            raise ValueError("source teams do not match exact home/away orientation")
        if home in away_keys or away in home_keys:
            raise ValueError("source team orientation is ambiguous")


def _matching_observation(
    rows: list[Mapping[str, object]], ledger: ScheduleEvidenceLedger
) -> tuple[ScheduleObservation | None, int]:
    unsupported = 0
    for row in rows:
        home = _safe_name_key(str(row.get("home_name") or ""))
        away = _safe_name_key(str(row.get("away_name") or ""))
        if home is None or away is None:
            unsupported += 1
            continue
        try:
            starts = _utc_z(row.get("starts_at"), "starts_at")
        except ValueError:
            continue
        for observation in ledger.observations:
            home_keys, skipped_home = _safe_alias_keys(
                (observation.home_entity, *observation.home_aliases)
            )
            away_keys, skipped_away = _safe_alias_keys(
                (observation.away_entity, *observation.away_aliases)
            )
            unsupported += skipped_home + skipped_away
            if (
                home in home_keys
                and away in away_keys
                and abs(starts - observation.starts_at) <= KICKOFF_TOLERANCE
            ):
                return observation, unsupported
    return None, unsupported


def _prepared_target_index(
    reviews_dir: Path, ledger: ScheduleEvidenceLedger
) -> dict[tuple[int, int, int], ScheduleObservation]:
    observations = {item.observation_id: item for item in ledger.observations}
    result: dict[tuple[int, int, int], ScheduleObservation] = {}
    for path in sorted(reviews_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            target = raw["target"]
            observation = observations[raw["observation"]["observation_id"]]
            key = (
                int(target["drawing_number"]),
                int(target["event_order"]),
                int(target["target_event_id"]),
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        result[key] = observation
    return result


def _safe_name_key(value: str) -> str | None:
    try:
        return _name_key(value)
    except ValueError:
        return None


def _safe_alias_keys(values: tuple[str, ...]) -> tuple[set[str], int]:
    keys: set[str] = set()
    skipped = 0
    for value in values:
        key = _safe_name_key(value)
        if key is None:
            skipped += 1
        else:
            keys.add(key)
    return keys, skipped


def _registrable_domain(domain: str) -> str:
    labels = tuple(item for item in domain.split(".") if item)
    if len(labels) < 2:
        raise ValueError("source domain is not registrable")
    suffix = ".".join(labels[-2:])
    if suffix in _MULTIPART_PUBLIC_SUFFIXES:
        if len(labels) < 3:
            raise ValueError("source domain is not registrable")
        return ".".join(labels[-3:])
    return suffix


def _publisher_identity(source_name: str, domain: str) -> str:
    registrable = _registrable_domain(domain)
    if registrable in _KNOWN_PUBLISHERS:
        return _KNOWN_PUBLISHERS[registrable]
    normalized = re.sub(r"[^a-z0-9]+", "", source_name.casefold())
    if not normalized:
        raise ValueError("source publisher identity is empty")
    return normalized


@contextmanager
def _ledger_lock(ledger_path: Path):
    lock_path = ledger_path.resolve().with_name(f".{ledger_path.name}.lock")
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_consensus(observation: ScheduleObservation) -> bool:
    domains = {
        (urlparse(claim.source_url).hostname or "").casefold().removeprefix("www.")
        for claim in observation.claims
    }
    return len(observation.claims) >= 2 and len(domains) >= 2


def _iter_json_files(root: Path):
    for path in sorted(root.rglob("*.json")):
        if path.is_file() and not path.is_symlink():
            yield path


def _regular_file(path: Path, name: str) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise ValueError(f"{name} must not be a symlink")
    resolved = raw.resolve()
    if not resolved.is_file():
        raise ValueError(f"{name} must be a regular file")
    return resolved


def _directory(path: Path, name: str) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise ValueError(f"{name} directory must not be a symlink")
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{name} directory is missing")
    return resolved


def _contained_regular_file(path: Path, root: Path, name: str) -> Path:
    resolved = _regular_file(path, name)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"{name} escapes its configured directory")
    return resolved


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(_regular_file(path, "file").read_bytes()).hexdigest()


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _exact_fields(value: object, fields: set[str], name: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{name} fields are invalid")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    return value


def _digest(value: object, name: str) -> str:
    text = _text(value, name)
    if not _DIGEST.fullmatch(text):
        raise ValueError(f"{name} must be sha256")
    return text


def _utc_z(value: object, name: str) -> datetime:
    text = _text(value, name)
    if not text.endswith("Z"):
        raise ValueError(f"{name} must be explicit UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO UTC datetime") from error
    return parsed.astimezone(timezone.utc)
