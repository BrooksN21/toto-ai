"""Explicit, append-only finished-drawing synchronization and settlement."""

from __future__ import annotations

import copy
import csv
import fcntl
import hashlib
import io
import json
import math
import os
import plistlib
import re
import shlex
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.collector.lifecycle import RawArchive, import_archived_detail
from toto_ai.db.models import (
    ArchivedPackage,
    Drawing,
    DrawingResultSnapshot,
    Event,
    PackageSettlement,
)
from toto_ai.package.audit import OUTCOMES, validate_coupons
from toto_ai.totobrief_time import parse_totobrief_timestamp

EVENT_COUNT = 15
VOID_RESULT = "*"
RESULT_ENDPOINT_TEMPLATE = "/drawing-info/{drawing_id}"
LEGACY_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 1
TIMED_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 2
RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 3
POST_DRAW_PLAN_SCHEMA_VERSION = 2
POST_DRAW_STATE_SCHEMA_VERSION = 2
POST_DRAW_REVIEW_SCHEMA_VERSION = 1
POST_DRAW_TIMEZONE = ZoneInfo("Europe/Moscow")
_POST_DRAW_LAUNCH_AGENT_LABEL = re.compile(r"com\.toto-ai\.post-draw-\d+\Z")


@dataclass(frozen=True)
class ResultSync:
    drawing_id: int
    drawing_number: int
    snapshot_sha256: str
    payload_sha256: str
    result_sha256: str
    actual: str
    void_event_orders: tuple[int, ...]
    complete: bool
    created: bool
    retrieved_at: str
    source_endpoint: str


@dataclass(frozen=True)
class PackageArchive:
    archive_sha256: str
    package_sha256: str
    drawing_id: int
    drawing_number: int
    stake: int
    coupon_count: int
    cost: int
    source_path: str
    source_bytes_sha256: str
    provenance: str
    archive_manifest_sha256: str | None
    final_input_sha256: str | None
    probability_input_sha256: str | None
    final_input_captured_at: str | None
    created: bool


@dataclass(frozen=True)
class Settlement:
    settlement_sha256: str
    drawing_id: int
    drawing_number: int
    snapshot_sha256: str
    archive_sha256: str
    package_sha256: str
    actual: str
    void_event_orders: tuple[int, ...]
    hit_distribution: dict[int, int]
    best_hits: int
    best_coupon_ranks: tuple[int, ...]
    category_counts: dict[int, int] | None
    cost: int
    fixed_miss_events: tuple[int, ...]
    zero_exposure_miss_events: tuple[int, ...]
    known_return: float | None
    roi: float | None
    return_status: str
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PostDrawRetryConfig:
    max_attempts: int = 6
    initial_delay_seconds: float = 60.0
    max_delay_seconds: float = 900.0
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        for name in ("initial_delay_seconds", "max_delay_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be at least initial_delay_seconds"
            )
        if (
            isinstance(self.backoff_multiplier, bool)
            or not isinstance(self.backoff_multiplier, (int, float))
            or not math.isfinite(float(self.backoff_multiplier))
            or self.backoff_multiplier < 1
        ):
            raise ValueError("backoff_multiplier must be finite and at least 1")


@dataclass(frozen=True)
class PostDrawState:
    schema_version: int
    status: Literal["complete", "pending", "failed", "blocked"]
    drawing_id: int
    drawing_number: int
    attempts: int
    max_attempts: int
    updated_at: str
    package_sha256: str | None
    result_snapshot_sha256: str | None
    settlement_sha256: str | None
    reason: str
    attempted_slots: tuple[str, ...] = ()
    due_slot: str | None = None
    error_type: str | None = None
    archive_sha256: str | None = None
    review_request_sha256: str | None = None
    state_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sync_finished_drawing(
    session_factory: sessionmaker[Session],
    client: Any,
    *,
    drawing_id: int | None = None,
    drawing_number: int | None = None,
    retrieved_at: datetime | None = None,
    void_event_orders: Sequence[int] = (),
    void_source: str | None = None,
    raw_archive_root: str | Path | None = None,
) -> ResultSync:
    """Fetch exactly one `/drawing-info/{id}` and append its result snapshot."""
    expected_id, expected_number = _resolve_explicit_drawing(
        session_factory,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
    )
    with session_factory() as session:
        stored_drawing = session.get(Drawing, expected_id)
        authoritative_ended_at = _canonical_timestamp(
            None if stored_drawing is None else stored_drawing.ended_at,
            "stored drawing ended_at",
        )
    payload = client.drawing_info(expected_id)
    fetched_at = _aware_utc(retrieved_at)
    normalized = _normalize_finished_payload(
        payload,
        expected_id=expected_id,
        expected_number=expected_number,
        authoritative_ended_at=authoritative_ended_at,
        void_event_orders=void_event_orders,
        void_source=void_source,
    )
    payload_json = _canonical_json(payload)
    payload_hash = _sha256_text(payload_json)
    result_hash = _sha256_json(normalized["events"])
    snapshot_content = _result_snapshot_hash_content(
        hash_schema_version=RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
        drawing_id=expected_id,
        drawing_number=expected_number,
        ended_at=normalized["ended_at"],
        events=normalized["events"],
        payments=normalized["payments"],
        pool_sum=normalized["pool_sum"],
        jackpot=normalized["jackpot"],
    )
    snapshot_hash = _sha256_json(snapshot_content)
    retrieved_text = fetched_at.isoformat()
    endpoint = RESULT_ENDPOINT_TEMPLATE.format(drawing_id=expected_id)
    raw_snapshot_sha256: str | None = None
    archive_created_snapshot = False
    if raw_archive_root is not None:
        archive_payload = copy.deepcopy(payload)
        for event in normalized["events"]:
            source_event = archive_payload["data"]["events"][event["order"]]
            source_event["result"] = event["result"]
            source_event["result_status"] = event["result_status"]
            source_event["score"] = event["score"]
            if "void_source" in event:
                source_event["void_source"] = event["void_source"]
        archive = RawArchive(raw_archive_root).archive(
            archive_payload,
            captured_at=fetched_at,
            source="totobrief-network",
            source_endpoint=endpoint,
            lifecycle_status="finished",
        )
        imported = import_archived_detail(session_factory, archive)
        raw_snapshot_sha256 = archive.snapshot_sha256
        archive_created_snapshot = imported.result_snapshot_created

    with session_factory.begin() as session:
        values = {
            "drawing_id": expected_id,
            "drawing_number": expected_number,
            "hash_schema_version": RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
            "ended_at": normalized["ended_at"],
            "retrieved_at": retrieved_text,
            "source_endpoint": endpoint,
            "payload_sha256": payload_hash,
            "raw_snapshot_sha256": raw_snapshot_sha256,
            "result_sha256": result_hash,
            "snapshot_sha256": snapshot_hash,
            "complete": True,
            "event_count": EVENT_COUNT,
            "actual": normalized["actual"],
            "events_json": _canonical_json(normalized["events"]),
            "payments_json": (
                None
                if normalized["payments"] is None
                else _canonical_json(normalized["payments"])
            ),
            "pool_sum": normalized["pool_sum"],
            "jackpot": normalized["jackpot"],
            "payload_json": payload_json,
        }
        inserted = session.execute(
            sqlite_insert(DrawingResultSnapshot)
            .values(**values)
            .on_conflict_do_nothing()
        )
        created = inserted.rowcount == 1 or archive_created_snapshot
        _persist_operational_result(
            session,
            normalized,
            drawing_id=expected_id,
            drawing_number=expected_number,
        )
        _verified_snapshot(session, snapshot_hash)

    return ResultSync(
        drawing_id=expected_id,
        drawing_number=expected_number,
        snapshot_sha256=snapshot_hash,
        payload_sha256=payload_hash,
        result_sha256=result_hash,
        actual=normalized["actual"],
        void_event_orders=tuple(normalized["void_event_orders"]),
        complete=True,
        created=created,
        retrieved_at=retrieved_text,
        source_endpoint=endpoint,
    )


def resolve_explicit_drawing(
    session_factory: sessionmaker[Session],
    *,
    drawing_id: int | None = None,
    drawing_number: int | None = None,
) -> tuple[int, int]:
    """Resolve exactly one unambiguous stored drawing identity."""
    return _resolve_explicit_drawing(
        session_factory,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
    )


def resolve_exact_drawing_source_ended_at(
    session_factory: sessionmaker[Session],
    *,
    drawing_id: int,
    drawing_number: int,
) -> datetime:
    """Return raw source ``ended_at`` for one unambiguous ID/number pair."""

    if type(drawing_id) is not int or drawing_id < 1:
        raise ValueError("exact drawing identity requires a positive drawing_id")
    if type(drawing_number) is not int or drawing_number < 1:
        raise ValueError("exact drawing identity requires a positive drawing_number")
    with session_factory() as session:
        drawing = session.get(Drawing, drawing_id)
        numbered = session.scalars(
            select(Drawing)
            .where(Drawing.number == drawing_number)
            .order_by(Drawing.id.desc())
        ).all()
        if (
            drawing is None
            or drawing.number != drawing_number
            or len(numbered) != 1
            or numbered[0].id != drawing_id
        ):
            raise ValueError(
                "exact drawing identity is missing, mismatched, or ambiguous"
            )
        return _parse_timestamp_required(drawing.ended_at)


def archive_package(
    session_factory: sessionmaker[Session],
    package_file: str | Path,
    *,
    drawing_id: int,
    drawing_number: int,
    stake: int,
    archived_at: datetime | None = None,
    provenance: Literal["pre_bet_runner", "legacy_import"] = "legacy_import",
    archive_manifest_sha256: str | None = None,
    final_input_sha256: str | None = None,
    probability_input_sha256: str | None = None,
    final_input_captured_at: str | None = None,
) -> PackageArchive:
    if type(drawing_id) is not int or drawing_id < 1:
        raise ValueError("drawing_id must be a positive integer")
    if type(drawing_number) is not int or drawing_number < 1:
        raise ValueError("drawing_number must be a positive integer")
    if type(stake) is not int or stake < 1:
        raise ValueError("stake must be a positive integer")
    path = Path(package_file)
    if provenance not in ("pre_bet_runner", "legacy_import"):
        raise ValueError("unsupported package archive provenance")
    if provenance == "pre_bet_runner":
        if (
            not isinstance(archive_manifest_sha256, str)
            or len(archive_manifest_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in archive_manifest_sha256
            )
        ):
            raise ValueError("pre-bet archive manifest hash is required")
    elif archive_manifest_sha256 is not None:
        raise ValueError("legacy archive cannot declare a pre-bet manifest hash")
    if provenance == "legacy_import" and any(
        value is not None
        for value in (
            final_input_sha256,
            probability_input_sha256,
            final_input_captured_at,
        )
    ):
        raise ValueError("legacy archive cannot declare atomic-final provenance")
    source_bytes = path.read_bytes()
    coupons, declared_stakes = _parse_package_source(source_bytes)
    if declared_stakes and declared_stakes != {stake}:
        raise ValueError(
            f"package declared stake mismatch: expected {stake}, "
            f"got {sorted(declared_stakes)}"
        )
    package_hash = _sha256_text(",".join(coupons))
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    archive_hash = _sha256_json(
        {
            "drawing_id": drawing_id,
            "drawing_number": drawing_number,
            "stake": stake,
            "coupons": coupons,
            "package_sha256": package_hash,
        }
    )
    archived_text = _aware_utc(archived_at).isoformat()
    with session_factory.begin() as session:
        drawing = session.get(Drawing, drawing_id)
        if drawing is None or drawing.number != drawing_number:
            raise ValueError("package archive drawing identity mismatch")
        if provenance == "pre_bet_runner":
            ended = _parse_totobrief_deadline(drawing)
            if ended is None or _aware_utc(archived_at) >= ended:
                raise ValueError("pre-bet package must be archived before ended_at")
        inserted = session.execute(
            sqlite_insert(ArchivedPackage)
            .values(
                archive_sha256=archive_hash,
                package_sha256=package_hash,
                drawing_id=drawing_id,
                drawing_number=drawing_number,
                stake=stake,
                coupon_count=len(coupons),
                cost=stake * len(coupons),
                source_path=str(path.resolve()),
                source_bytes_sha256=source_hash,
                source_bytes=source_bytes,
                coupons_json=_canonical_json(coupons),
                archived_at=archived_text,
                provenance=provenance,
                archive_manifest_sha256=archive_manifest_sha256,
                final_input_sha256=final_input_sha256,
                probability_input_sha256=probability_input_sha256,
                final_input_captured_at=final_input_captured_at,
            )
            .on_conflict_do_nothing()
        )
        created = inserted.rowcount == 1
        existing = session.get(ArchivedPackage, archive_hash)
        if existing is not None and existing.provenance != provenance:
            raise ValueError("archive provenance cannot be relabeled")
        if (
            existing is not None
            and existing.archive_manifest_sha256 != archive_manifest_sha256
        ):
            raise ValueError("archive manifest hash cannot be changed")
        if existing is not None and (
            existing.final_input_sha256 != final_input_sha256
            or existing.probability_input_sha256 != probability_input_sha256
            or existing.final_input_captured_at != final_input_captured_at
        ):
            raise ValueError("archive final-input provenance cannot be changed")
        _verified_archive(session, archive_hash)
    return PackageArchive(
        archive_sha256=archive_hash,
        package_sha256=package_hash,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        stake=stake,
        coupon_count=len(coupons),
        cost=stake * len(coupons),
        source_path=str(path.resolve()),
        source_bytes_sha256=source_hash,
        provenance=provenance,
        archive_manifest_sha256=archive_manifest_sha256,
        final_input_sha256=final_input_sha256,
        probability_input_sha256=probability_input_sha256,
        final_input_captured_at=final_input_captured_at,
        created=created,
    )


def import_prebet_package_manifest(
    session_factory: sessionmaker[Session],
    manifest_file: str | Path,
    package_file: str | Path,
) -> PackageArchive:
    try:
        payload = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("pre-bet package manifest is malformed") from error
    if not isinstance(payload, dict):
        raise ValueError("pre-bet package manifest must be an object")
    manifest_hash = payload.get("archive_manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("archive_manifest_sha256", None)
    if (
        not isinstance(manifest_hash, str)
        or hashlib.sha256(
            json.dumps(
                unsigned,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        != manifest_hash
    ):
        raise ValueError("pre-bet package manifest hash mismatch")
    if payload.get("provenance") != "pre_bet_runner":
        raise ValueError("pre-bet package manifest provenance mismatch")
    schema_version = payload.get("schema_version")
    if schema_version not in (1, 2):
        raise ValueError("unsupported pre-bet package manifest schema")
    if schema_version == 2:
        for name in ("final_input_sha256", "probability_input_sha256"):
            value = payload.get(name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise ValueError(f"pre-bet {name} is invalid")
        _parse_timestamp_required(payload.get("final_input_captured_at"))
    elif any(
        payload.get(name) is not None
        for name in (
            "final_input_sha256",
            "probability_input_sha256",
            "final_input_captured_at",
        )
    ):
        raise ValueError("schema-v1 pre-bet manifest has atomic-final fields")
    manifest_ended_at = _parse_timestamp_required(payload.get("ended_at"))
    with session_factory() as session:
        drawing = session.get(Drawing, payload.get("drawing_id"))
        if (
            drawing is None
            or drawing.number != payload.get("drawing_number")
            or _parse_timestamp_required(drawing.ended_at) != manifest_ended_at
        ):
            raise ValueError(
                "pre-bet package manifest drawing identity mismatch"
            )
    source = Path(package_file).read_bytes()
    if hashlib.sha256(source).hexdigest() != payload.get("source_bytes_sha256"):
        raise ValueError("pre-bet package source hash mismatch")
    coupons, _ = _parse_package_source(source)
    if _sha256_text(",".join(coupons)) != payload.get(
        "canonical_package_sha256"
    ):
        raise ValueError("pre-bet canonical package hash mismatch")
    return archive_package(
        session_factory,
        package_file,
        drawing_id=payload.get("drawing_id"),
        drawing_number=payload.get("drawing_number"),
        stake=payload.get("stake"),
        archived_at=_parse_timestamp_required(payload.get("archived_at")),
        provenance="pre_bet_runner",
        archive_manifest_sha256=manifest_hash,
        final_input_sha256=payload.get("final_input_sha256"),
        probability_input_sha256=payload.get("probability_input_sha256"),
        final_input_captured_at=payload.get("final_input_captured_at"),
    )


def settle_archived_package(
    session_factory: sessionmaker[Session],
    *,
    snapshot_sha256: str,
    archive_sha256: str,
    settled_at: datetime | None = None,
) -> Settlement:
    with session_factory.begin() as session:
        snapshot = _verified_snapshot(session, snapshot_sha256)
        package = _verified_archive(session, archive_sha256)
        if snapshot is None:
            raise ValueError("result snapshot was not found")
        if package is None:
            raise ValueError("archived package was not found")
        if not snapshot.complete or snapshot.event_count != EVENT_COUNT:
            raise ValueError("settlement requires complete 15/15 results")
        if (
            snapshot.drawing_id != package.drawing_id
            or snapshot.drawing_number != package.drawing_number
        ):
            raise ValueError("result snapshot and package drawing identity mismatch")

        actual = snapshot.actual
        coupons = tuple(json.loads(package.coupons_json))
        computed = _compute_settlement(
            actual=actual,
            coupons=coupons,
            stake=package.stake,
            payments=(
                None
                if snapshot.payments_json is None
                else json.loads(snapshot.payments_json)
            ),
        )
        settlement_payload = {
            "drawing_id": snapshot.drawing_id,
            "drawing_number": snapshot.drawing_number,
            "result_snapshot_sha256": snapshot.snapshot_sha256,
            "archive_sha256": package.archive_sha256,
            "package_sha256": package.package_sha256,
            **_settlement_payload_fields(computed),
        }
        settlement_hash = _sha256_json(settlement_payload)
        inserted = session.execute(
            sqlite_insert(PackageSettlement)
            .values(
                settlement_sha256=settlement_hash,
                drawing_id=snapshot.drawing_id,
                drawing_number=snapshot.drawing_number,
                result_snapshot_sha256=snapshot.snapshot_sha256,
                archive_sha256=package.archive_sha256,
                package_sha256=package.package_sha256,
                settled_at=_aware_utc(settled_at).isoformat(),
                actual=actual,
                hit_distribution_json=_canonical_json(
                    computed["hit_distribution"]
                ),
                best_hits=computed["best_hits"],
                best_coupon_ranks_json=_canonical_json(
                    computed["best_coupon_ranks"]
                ),
                category_counts_json=(
                    None
                    if computed["category_counts"] is None
                    else _canonical_json(computed["category_counts"])
                ),
                cost=computed["cost"],
                fixed_miss_events_json=_canonical_json(
                    computed["fixed_miss_events"]
                ),
                zero_exposure_miss_events_json=_canonical_json(
                    computed["zero_exposure_miss_events"]
                ),
                known_return=computed["known_return"],
                roi=computed["roi"],
                return_status=computed["return_status"],
                settlement_json=_canonical_json(settlement_payload),
            )
            .on_conflict_do_nothing()
        )
        created = inserted.rowcount == 1
        _verified_settlement(session, settlement_hash)
    return Settlement(
        settlement_sha256=settlement_hash,
        drawing_id=snapshot.drawing_id,
        drawing_number=snapshot.drawing_number,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=package.archive_sha256,
        package_sha256=package.package_sha256,
        actual=actual,
        void_event_orders=tuple(computed["void_event_orders"]),
        hit_distribution={
            int(key): value for key, value in computed["hit_distribution"].items()
        },
        best_hits=computed["best_hits"],
        best_coupon_ranks=tuple(computed["best_coupon_ranks"]),
        category_counts=(
            None
            if computed["category_counts"] is None
            else {
                int(key): value
                for key, value in computed["category_counts"].items()
            }
        ),
        cost=computed["cost"],
        fixed_miss_events=tuple(computed["fixed_miss_events"]),
        zero_exposure_miss_events=tuple(computed["zero_exposure_miss_events"]),
        known_return=computed["known_return"],
        roi=computed["roi"],
        return_status=computed["return_status"],
        created=created,
    )


def settle_package_file(
    session_factory: sessionmaker[Session],
    package_file: str | Path,
    *,
    drawing_id: int | None = None,
    drawing_number: int | None = None,
    stake: int = 30,
) -> Settlement:
    expected_id, expected_number = _resolve_explicit_drawing(
        session_factory,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
    )
    with session_factory() as session:
        snapshot = session.scalar(
            select(DrawingResultSnapshot)
            .where(DrawingResultSnapshot.drawing_id == expected_id)
            .where(DrawingResultSnapshot.complete.is_(True))
            .order_by(DrawingResultSnapshot.id.desc())
        )
    if snapshot is None:
        raise ValueError("no complete 15/15 result snapshot exists for drawing")
    with session_factory() as session:
        snapshot = _verified_snapshot(session, snapshot.snapshot_sha256)
        archived = _verified_archive_for_source(
            session,
            package_file,
            drawing_id=expected_id,
            drawing_number=expected_number,
            stake=stake,
        )
    return settle_archived_package(
        session_factory,
        snapshot_sha256=snapshot.snapshot_sha256,
        archive_sha256=archived.archive_sha256,
    )


def run_post_draw(
    session_factory: sessionmaker[Session],
    client: Any,
    **kwargs: Any,
) -> PostDrawState:
    state_path = kwargs.get("state_path")
    if state_path is None:
        raise ValueError("state_path is required")
    lock_path = Path(state_path).with_name(f"{Path(state_path).name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return _run_post_draw_locked(session_factory, client, **kwargs)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _run_post_draw_locked(
    session_factory: sessionmaker[Session],
    client: Any,
    *,
    package_file: str | Path,
    drawing_id: int | None = None,
    drawing_number: int | None = None,
    stake: int = 30,
    config: PostDrawRetryConfig | None = None,
    state_path: str | Path,
    raw_archive_root: str | Path | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> PostDrawState:
    config = config or PostDrawRetryConfig()
    expected_id, expected_number = _resolve_explicit_drawing(
        session_factory,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
    )
    now = now or (lambda: datetime.now(timezone.utc))
    with session_factory() as session:
        drawing = session.get(Drawing, expected_id)
        ended_at = _parse_totobrief_deadline(drawing)
    current = _aware_utc(now())
    if ended_at is None:
        state = PostDrawState(
            schema_version=1,
            status="pending",
            drawing_id=expected_id,
            drawing_number=expected_number,
            attempts=0,
            max_attempts=config.max_attempts,
            updated_at=current.isoformat(),
            package_sha256=None,
            result_snapshot_sha256=None,
            settlement_sha256=None,
            reason="drawing_ended_at_unavailable",
        )
        _write_state(state_path, state)
        return state

    with session_factory() as session:
        archived_row = _verified_archive_for_source(
            session,
            package_file,
            drawing_id=expected_id,
            drawing_number=expected_number,
            stake=stake,
        )
    archived = _archive_result(archived_row, created=False)
    previous = _load_state(state_path)
    if previous is not None:
        if (
            previous.drawing_id != expected_id
            or previous.drawing_number != expected_number
            or (
                previous.package_sha256 is not None
                and previous.package_sha256 != archived.package_sha256
            )
        ):
            raise ValueError("post-draw state exact target/package identity mismatch")
        if previous.status == "complete":
            _verify_complete_state(session_factory, previous)
            return previous

    delay = float(config.initial_delay_seconds)
    last_error = "results_not_available"
    for attempt in range(1, config.max_attempts + 1):
        current = _aware_utc(now())
        if current < ended_at:
            last_error = "drawing_not_ended"
            if attempt < config.max_attempts:
                wait = min(
                    float(config.max_delay_seconds),
                    max(delay, min((ended_at - current).total_seconds(), delay)),
                )
                sleep(wait)
                delay = min(
                    float(config.max_delay_seconds),
                    delay * float(config.backoff_multiplier),
                )
            continue
        try:
            synced = sync_finished_drawing(
                session_factory,
                client,
                drawing_id=expected_id,
                retrieved_at=now(),
                raw_archive_root=raw_archive_root,
            )
            settlement = settle_archived_package(
                session_factory,
                snapshot_sha256=synced.snapshot_sha256,
                archive_sha256=archived.archive_sha256,
                settled_at=now(),
            )
        except Exception as error:  # bounded adapter/API failures become state
            last_error = _safe_reason(error)
        else:
            state = PostDrawState(
                schema_version=1,
                status="complete",
                drawing_id=expected_id,
                drawing_number=expected_number,
                attempts=attempt,
                max_attempts=config.max_attempts,
                updated_at=_aware_utc(now()).isoformat(),
                package_sha256=archived.package_sha256,
                result_snapshot_sha256=synced.snapshot_sha256,
                settlement_sha256=settlement.settlement_sha256,
                reason="settlement_complete",
            )
            _write_state(state_path, state)
            return state
        if attempt < config.max_attempts:
            sleep(delay)
            delay = min(
                float(config.max_delay_seconds),
                delay * float(config.backoff_multiplier),
            )

    pending = (
        "15/15" in last_error
        or "not finished" in last_error
        or last_error == "drawing_not_ended"
    )
    state = PostDrawState(
        schema_version=1,
        status="pending" if pending else "failed",
        drawing_id=expected_id,
        drawing_number=expected_number,
        attempts=config.max_attempts,
        max_attempts=config.max_attempts,
        updated_at=_aware_utc(now()).isoformat(),
        package_sha256=archived.package_sha256,
        result_snapshot_sha256=None,
        settlement_sha256=None,
        reason=last_error,
    )
    _write_state(state_path, state)
    return state


def prepare_post_draw_scheduler_artifacts(
    *,
    drawing_id: int | None,
    drawing_number: int | None,
    ended_at: str,
    package_file: str | Path | None,
    stake: int,
    db: str | Path,
    state_file: str | Path,
    output_dir: str | Path,
    project_root: str | Path,
    python_executable: str,
    max_attempts: int,
    initial_delay_seconds: float,
    max_delay_seconds: float,
    paper_result_file: str | Path | None = None,
    void_event_orders: Sequence[int] = (),
    void_source: str | None = None,
    automation_installation: bool = False,
    automatic_postmortem: bool = True,
) -> tuple[Path, Path, Path]:
    """Generate a hash-bound local launchd wrapper and plist candidate."""
    if (drawing_id is None) == (drawing_number is None):
        raise ValueError("use exactly one of drawing_id or drawing_number")
    from toto_ai.db.session import get_session_factory, init_db

    factory = get_session_factory(init_db(db))
    resolved_id, resolved_number = _resolve_explicit_drawing(
        factory,
        drawing_id=drawing_id,
        drawing_number=drawing_number,
    )
    with factory() as session:
        drawing = session.get(Drawing, resolved_id)
        stored_ended = _parse_totobrief_deadline(drawing)
        community = None if drawing is None else drawing.name
    if stored_ended is None:
        raise ValueError("stored drawing ended_at is unavailable")
    requested_ended = parse_totobrief_timestamp(
        ended_at,
        community=community,
        field_name="caller ended_at",
    )
    if requested_ended != stored_ended:
        raise ValueError("caller ended_at does not match exact database drawing")
    root = Path(project_root).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target_label = resolved_id
    wrapper = output / f"post-draw-{target_label}.sh"
    plist = output / f"com.toto-ai.post-draw-{target_label}.plist"
    plan = output / f"post-draw-{target_label}.json"
    ended = stored_ended
    first_local_date = ended.astimezone(POST_DRAW_TIMEZONE).date() + timedelta(days=1)
    first_run = datetime.combine(
        first_local_date,
        datetime.min.time().replace(hour=12),
        tzinfo=POST_DRAW_TIMEZONE,
    )
    due_slots = tuple(
        first_run + timedelta(hours=3 * index) for index in range(max_attempts)
    )
    package_binding = _build_post_draw_package_binding(
        package_file=package_file,
        paper_result_file=paper_result_file,
        stake=stake,
    )
    void_orders, reviewed_void_source = _normalize_void_event_orders(
        void_event_orders,
        void_source=void_source,
    )
    plan_payload: dict[str, Any] = {
        "schema_version": POST_DRAW_PLAN_SCHEMA_VERSION,
        "drawing_id": resolved_id,
        "drawing_number": resolved_number,
        "ended_at": ended.isoformat(),
        "timezone": "Europe/Moscow",
        "first_run_at": first_run.isoformat(),
        "interval_hours": 3,
        "due_slots": [value.isoformat() for value in due_slots],
        "expires_at": due_slots[-1].isoformat(),
        "max_attempts": max_attempts,
        "package_binding": package_binding,
        "db": str(Path(db).resolve()),
        "state_file": str(Path(state_file).resolve()),
        "review_request_file": str((output / "review-request.json").resolve()),
        "postmortem_file": str((output / "postmortem.md").resolve()),
        "raw_archive_root": None,
        "void_event_orders": list(void_orders),
        "void_source": reviewed_void_source,
        "automatic_wagering": False,
        "automation_installation": automation_installation,
        "automatic_postmortem": automatic_postmortem,
    }
    plan_payload["plan_sha256"] = _sha256_json(plan_payload)
    plan_bytes = (
        json.dumps(plan_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    _write_immutable_file(plan, plan_bytes, name="post-draw plan")
    argv = [
        str(Path(python_executable)),
        "-m",
        "toto_ai.cli",
        "post-draw-run",
        "--plan",
        str(plan.resolve()),
    ]
    command = "exec " + shlex.join(argv)
    wrapper_bytes = (
        "#!/bin/sh\nset -eu\n"
        f"cd {shlex.quote(str(root))}\n"
        f"{command}\n"
    ).encode()
    _write_immutable_file(wrapper, wrapper_bytes, name="post-draw wrapper")
    wrapper.chmod(0o700)
    plist_bytes = plistlib.dumps(
        {
            "Label": f"com.toto-ai.post-draw-{target_label}",
            "ProgramArguments": [str(wrapper)],
            "WorkingDirectory": str(root),
            "StartCalendarInterval": [
                {
                    "Year": value.year,
                    "Month": value.month,
                    "Day": value.day,
                    "Hour": value.hour,
                    "Minute": value.minute,
                }
                for value in due_slots
            ],
        },
        fmt=plistlib.FMT_XML,
        sort_keys=False,
    )
    _write_immutable_file(plist, plist_bytes, name="post-draw launchd candidate")
    return plan, wrapper, plist


def install_post_draw_launch_agent(
    plan_path: str | Path,
    candidate_path: str | Path,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> dict[str, object]:
    """Install and verify one exact post-draw LaunchAgent candidate."""

    plan = load_post_draw_plan(plan_path)
    if plan.get("automation_installation") is not True:
        raise ValueError("post-draw plan does not authorize automatic installation")
    candidate = Path(candidate_path).resolve()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("post-draw LaunchAgent candidate is invalid")
    try:
        payload = plistlib.loads(candidate.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        raise ValueError("post-draw LaunchAgent candidate is malformed") from error
    label = f"com.toto-ai.post-draw-{plan['drawing_id']}"
    expected_wrapper = candidate.parent / f"post-draw-{plan['drawing_id']}.sh"
    if not _POST_DRAW_LAUNCH_AGENT_LABEL.fullmatch(label):
        raise ValueError("post-draw LaunchAgent label is invalid")
    if not isinstance(payload, dict) or payload.get("Label") != label:
        raise ValueError("post-draw LaunchAgent candidate label mismatch")
    if payload.get("ProgramArguments") != [str(expected_wrapper)]:
        raise ValueError("post-draw LaunchAgent wrapper mismatch")
    if expected_wrapper.is_symlink() or not expected_wrapper.is_file():
        raise ValueError("post-draw LaunchAgent wrapper is unavailable")
    root = (launch_agents_root or Path.home() / "Library/LaunchAgents").resolve()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("LaunchAgents root cannot be a symlink")
    destination = root / f"{label}.plist"
    _write_installed_launch_agent(destination, candidate.read_bytes())
    domain = f"gui/{os.getuid()}"
    loaded = command_runner(
        ("launchctl", "print", f"{domain}/{label}"),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(loaded, "returncode", 1) != 0:
        bootstrapped = command_runner(
            ("launchctl", "bootstrap", domain, str(destination)),
            check=False,
            capture_output=True,
            text=True,
        )
        if getattr(bootstrapped, "returncode", 1) != 0:
            destination.unlink(missing_ok=True)
            raise ValueError("post-draw LaunchAgent bootstrap failed")
    verified = command_runner(
        ("launchctl", "print", f"{domain}/{label}"),
        check=False,
        capture_output=True,
        text=True,
    )
    active = (
        getattr(verified, "returncode", 1) == 0
        and destination.is_file()
        and not destination.is_symlink()
        and destination.read_bytes() == candidate.read_bytes()
    )
    if not active:
        destination.unlink(missing_ok=True)
        raise ValueError("post-draw LaunchAgent did not verify active")
    return {
        "label": label,
        "installed_path": str(destination),
        "installed_verified": True,
        "loaded_verified": True,
        "active": True,
    }


def cleanup_post_draw_launch_agent(
    plan_path: str | Path,
    *,
    launch_agents_root: Path | None = None,
    command_runner: Callable[..., object] = subprocess.run,
) -> None:
    """Unload and remove only the LaunchAgent bound to this post-draw plan."""

    plan = load_post_draw_plan(plan_path)
    label = f"com.toto-ai.post-draw-{plan['drawing_id']}"
    root = (launch_agents_root or Path.home() / "Library/LaunchAgents").resolve()
    destination = root / f"{label}.plist"
    domain = f"gui/{os.getuid()}"
    loaded = command_runner(
        ("launchctl", "print", f"{domain}/{label}"),
        check=False,
        capture_output=True,
        text=True,
    )
    if getattr(loaded, "returncode", 1) == 0:
        stopped = command_runner(
            ("launchctl", "bootout", f"{domain}/{label}"),
            check=False,
            capture_output=True,
            text=True,
        )
        if getattr(stopped, "returncode", 1) != 0:
            raise ValueError("post-draw LaunchAgent bootout failed")
    if destination.is_symlink():
        raise ValueError("installed post-draw plist is a symlink")
    destination.unlink(missing_ok=True)


def _write_installed_launch_agent(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError("installed post-draw LaunchAgent conflicts")
        return
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_immutable_file(path: Path, content: bytes, *, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"{name} conflicts with immutable artifact")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _build_post_draw_package_binding(
    *,
    package_file: str | Path | None,
    paper_result_file: str | Path | None,
    stake: int,
) -> dict[str, Any]:
    if type(stake) is not int or stake < 1:
        raise ValueError("stake must be a positive integer")
    if package_file is None:
        if paper_result_file is None:
            raise ValueError("package-free NO BET requires paper_result_file")
        paper_path = Path(paper_result_file).resolve()
        if paper_path.is_symlink() or not paper_path.is_file():
            raise ValueError("paper result must be a regular file")
        paper_bytes = paper_path.read_bytes()
        try:
            payload = json.loads(paper_bytes)
        except (TypeError, ValueError) as error:
            raise ValueError("paper result is malformed") from error
        if not (
            isinstance(payload, dict)
            and payload.get("decision") == "NO BET"
            and payload.get("actionable") is False
            and payload.get("count") == 0
        ):
            raise ValueError("package-free binding requires zero-coupon NO BET")
        return {
            "kind": "package_free_no_bet",
            "source_path": None,
            "source_bytes_sha256": None,
            "package_sha256": None,
            "paper_result_path": str(paper_path),
            "paper_result_sha256": hashlib.sha256(paper_bytes).hexdigest(),
            "stake": stake,
            "coupon_count": 0,
            "cost": 0,
        }
    if paper_result_file is not None:
        raise ValueError("paper_result_file is only valid for package-free NO BET")
    source = Path(package_file).resolve()
    if source.is_symlink() or not source.is_file():
        raise ValueError("package source must be a regular file")
    source_bytes = source.read_bytes()
    coupons, declared_stakes = _parse_package_source(source_bytes)
    if declared_stakes and declared_stakes != {stake}:
        raise ValueError("package declared stake mismatch")
    return {
        "kind": "package",
        "source_path": str(source),
        "source_bytes_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "package_sha256": _sha256_text(",".join(coupons)),
        "paper_result_path": None,
        "paper_result_sha256": None,
        "stake": stake,
        "coupon_count": len(coupons),
        "cost": len(coupons) * stake,
    }


def load_post_draw_plan(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        if source.is_symlink() or not source.is_file():
            raise ValueError("plan must be a regular file")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("plan must be an object")
        unsigned = dict(payload)
        plan_hash = unsigned.pop("plan_sha256", None)
        if payload.get("schema_version") != POST_DRAW_PLAN_SCHEMA_VERSION:
            raise ValueError("unsupported post-draw plan schema")
        if plan_hash != _sha256_json(unsigned):
            raise ValueError("post-draw plan hash mismatch")
        if payload.get("timezone") != "Europe/Moscow":
            raise ValueError("post-draw timezone mismatch")
        due_slots = tuple(
            _parse_timestamp_required(value) for value in payload.get("due_slots", [])
        )
        if not due_slots or len(due_slots) != payload.get("max_attempts"):
            raise ValueError("post-draw due slots are invalid")
        if any(
            (right - left).total_seconds() != 10_800
            for left, right in zip(due_slots, due_slots[1:], strict=False)
        ):
            raise ValueError("post-draw cadence is invalid")
        first = datetime.fromisoformat(payload["first_run_at"])
        if first.tzinfo is None or first.astimezone(POST_DRAW_TIMEZONE).hour != 12:
            raise ValueError("post-draw first run is invalid")
        if _parse_timestamp_required(payload["first_run_at"]) != due_slots[0]:
            raise ValueError("post-draw first run does not match due slots")
        if _parse_timestamp_required(payload["expires_at"]) != due_slots[-1]:
            raise ValueError("post-draw expiry does not match due slots")
        if payload.get("automatic_wagering") is not False:
            raise ValueError("post-draw plan cannot enable wagering")
        if not isinstance(payload.get("automation_installation"), bool):
            raise ValueError("post-draw automation installation flag is invalid")
        if not isinstance(payload.get("automatic_postmortem", False), bool):
            raise ValueError("post-draw automatic postmortem flag is invalid")
        _validate_post_draw_package_binding(payload.get("package_binding"))
        return payload
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError("post-draw plan is malformed or violates integrity") from error


def _validate_post_draw_package_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("package binding must be an object")
    kind = value.get("kind")
    if kind == "package":
        source = Path(value["source_path"])
        if source.is_symlink() or not source.is_file():
            raise ValueError("bound package source is unavailable")
        source_bytes = source.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != value.get(
            "source_bytes_sha256"
        ):
            raise ValueError("bound package source hash mismatch")
        coupons, declared_stakes = _parse_package_source(source_bytes)
        if declared_stakes and declared_stakes != {value.get("stake")}:
            raise ValueError("bound package stake mismatch")
        if _sha256_text(",".join(coupons)) != value.get("package_sha256"):
            raise ValueError("bound canonical package hash mismatch")
        if value.get("coupon_count") != len(coupons):
            raise ValueError("bound package coupon count mismatch")
        if value.get("cost") != len(coupons) * value.get("stake"):
            raise ValueError("bound package cost mismatch")
    elif kind == "package_free_no_bet":
        paper = Path(value["paper_result_path"])
        if paper.is_symlink() or not paper.is_file():
            raise ValueError("bound paper result is unavailable")
        if hashlib.sha256(paper.read_bytes()).hexdigest() != value.get(
            "paper_result_sha256"
        ):
            raise ValueError("bound paper result hash mismatch")
        if any(
            value.get(name) not in (None, 0)
            for name in (
                "source_path",
                "source_bytes_sha256",
                "package_sha256",
                "coupon_count",
                "cost",
            )
        ):
            raise ValueError("package-free binding contains package evidence")
    else:
        raise ValueError("unsupported post-draw package binding")
    return value


def due_post_draw_attempts(
    plan: Mapping[str, Any],
    *,
    now: datetime,
    attempted_slots: Sequence[str] = (),
) -> tuple[str, ...]:
    current = _aware_utc(now)
    attempted = set(attempted_slots)
    return tuple(
        value
        for value in plan["due_slots"]
        if value not in attempted and _parse_timestamp_required(value) <= current
    )


def run_post_draw_plan(
    session_factory: sessionmaker[Session],
    client: Any,
    *,
    plan_path: str | Path,
    now: Callable[[], datetime] | None = None,
    notifier: Callable[[str], None] | None = None,
) -> PostDrawState:
    """Execute at most one due slot from a hash-bound post-draw plan."""

    clock = now or (lambda: datetime.now(timezone.utc))
    try:
        plan = load_post_draw_plan(plan_path)
    except ValueError as error:
        try:
            unsafe = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            unsafe = {}
        return PostDrawState(
            schema_version=POST_DRAW_STATE_SCHEMA_VERSION,
            status="blocked",
            drawing_id=int(unsafe.get("drawing_id") or 0),
            drawing_number=int(unsafe.get("drawing_number") or 0),
            attempts=0,
            max_attempts=int(unsafe.get("max_attempts") or 0),
            updated_at=_aware_utc(clock()).isoformat(),
            package_sha256=None,
            result_snapshot_sha256=None,
            settlement_sha256=None,
            reason="REVIEW_BLOCKED_INTEGRITY",
            error_type=type(error).__name__,
        )
    state_path = Path(plan["state_file"])
    lock_path = state_path.with_name(f"{state_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return _run_post_draw_plan_locked(
                session_factory,
                client,
                plan=plan,
                state_path=state_path,
                now=clock,
                notifier=notifier,
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _run_post_draw_plan_locked(
    session_factory: sessionmaker[Session],
    client: Any,
    *,
    plan: Mapping[str, Any],
    state_path: Path,
    now: Callable[[], datetime],
    notifier: Callable[[str], None] | None,
) -> PostDrawState:
    current = _aware_utc(now())
    binding = _validate_post_draw_package_binding(plan["package_binding"])
    previous = _load_state(state_path)
    if previous is not None:
        if (
            previous.drawing_id != plan["drawing_id"]
            or previous.drawing_number != plan["drawing_number"]
            or previous.package_sha256 != binding.get("package_sha256")
        ):
            blocked = _post_draw_plan_state(
                plan,
                status="blocked",
                reason="REVIEW_BLOCKED_INTEGRITY",
                updated_at=current,
                attempted_slots=previous.attempted_slots,
                error_type="StateIdentityConflict",
            )
            _write_state(state_path, blocked)
            return blocked
        if previous.status in {"complete", "blocked"}:
            if previous.review_request_sha256 is not None:
                request = load_review_request(plan["review_request_file"])
                if request["request_sha256"] != previous.review_request_sha256:
                    raise ValueError("review request binding mismatch")
            if previous.settlement_sha256 is not None:
                with session_factory() as session:
                    _verified_settlement(session, previous.settlement_sha256)
            return previous

    attempted = () if previous is None else previous.attempted_slots
    due = due_post_draw_attempts(plan, now=current, attempted_slots=attempted)
    if not due:
        reason = (
            "POST_DRAW_SCHEDULE_EXHAUSTED"
            if current > _parse_timestamp_required(plan["expires_at"])
            else "POST_DRAW_NOT_DUE"
        )
        state = _post_draw_plan_state(
            plan,
            status="pending",
            reason=reason,
            updated_at=current,
            attempted_slots=attempted,
        )
        _write_state(state_path, state)
        return state
    due_slot = due[-1]
    attempted = (*attempted, due_slot)
    try:
        synced = sync_finished_drawing(
            session_factory,
            client,
            drawing_id=plan["drawing_id"],
            retrieved_at=current,
            void_event_orders=plan.get("void_event_orders", ()),
            void_source=plan.get("void_source"),
            raw_archive_root=plan.get("raw_archive_root"),
        )
        archive: PackageArchive | None = None
        settlement: Settlement | None = None
        if binding["kind"] == "package":
            try:
                with session_factory() as session:
                    existing_archive = _verified_archive_for_source(
                        session,
                        binding["source_path"],
                        drawing_id=plan["drawing_id"],
                        drawing_number=plan["drawing_number"],
                        stake=binding["stake"],
                    )
            except ValueError:
                archive = archive_package(
                    session_factory,
                    binding["source_path"],
                    drawing_id=plan["drawing_id"],
                    drawing_number=plan["drawing_number"],
                    stake=binding["stake"],
                    provenance="legacy_import",
                )
            else:
                archive = _archive_result(existing_archive, created=False)
            if archive.package_sha256 != binding["package_sha256"]:
                raise ValueError("archived package binding mismatch")
            settlement = settle_archived_package(
                session_factory,
                snapshot_sha256=synced.snapshot_sha256,
                archive_sha256=archive.archive_sha256,
                settled_at=current,
            )
        request = create_review_request(
            plan["review_request_file"],
            drawing_id=plan["drawing_id"],
            drawing_number=plan["drawing_number"],
            package_kind=binding["kind"],
            settlement=(None if settlement is None else settlement.to_dict()),
            snapshot_sha256=synced.snapshot_sha256,
            actual=synced.actual,
            void_event_orders=synced.void_event_orders,
            requested_at=current,
            notifier=notifier,
        )
        _settle_parallel_comparison_if_available(
            plan,
            result=synced,
            completed_at=current,
            notifier=notifier,
        )
        if plan.get("automatic_postmortem", False):
            if request["status"] == "AWAITING_USER_REVIEW":
                request = transition_review_request(
                    plan["review_request_file"],
                    transition="request",
                    transitioned_at=current,
                )
            request = complete_post_draw_review(
                plan["review_request_file"],
                postmortem_path=plan["postmortem_file"],
                completed_at=current,
            )
    except Exception as error:  # classified into durable retry/integrity state
        reason, status = _classify_post_draw_error(error)
        state = _post_draw_plan_state(
            plan,
            status=status,
            reason=reason,
            updated_at=current,
            attempted_slots=attempted,
            due_slot=due_slot,
            error_type=type(error).__name__,
        )
        _write_state(state_path, state)
        return state

    state = _post_draw_plan_state(
        plan,
        status="complete",
        reason=(
            "PACKAGE_FREE_NO_BET_COMPLETE"
            if settlement is None
            else "SETTLEMENT_COMPLETE"
        ),
        updated_at=current,
        attempted_slots=attempted,
        due_slot=due_slot,
        archive_sha256=None if archive is None else archive.archive_sha256,
        result_snapshot_sha256=synced.snapshot_sha256,
        settlement_sha256=(
            None if settlement is None else settlement.settlement_sha256
        ),
        review_request_sha256=request["request_sha256"],
    )
    _write_state(state_path, state)
    return state


def _settle_parallel_comparison_if_available(
    plan: Mapping[str, Any],
    *,
    result: ResultSync,
    completed_at: datetime,
    notifier: Callable[[str], None] | None,
) -> None:
    """Settle exact final sidecar packages without changing primary settlement."""

    post_draw_root = Path(plan["review_request_file"]).resolve().parent
    scheduler_root = post_draw_root.parent
    sidecar_status = (
        scheduler_root
        / "parallel-challenger"
        / "output-final"
        / "sidecar-status.json"
    )
    if not sidecar_status.exists():
        return
    status_path = post_draw_root / "parallel-comparison-status.json"
    try:
        from toto_ai.runner.scheduler import load_scheduler_plan
        from toto_ai.sports_stats.final_hybrid_settlement import (
            settle_final_hybrid_comparison,
        )

        scheduler_plan_path = scheduler_root / "scheduler-plan.json"
        scheduler_plan = load_scheduler_plan(scheduler_plan_path)
        if (
            scheduler_plan.drawing_id != result.drawing_id
            or scheduler_plan.drawing != result.drawing_number
            or scheduler_plan.output_dir.resolve() != scheduler_root
        ):
            raise ValueError("parallel comparison scheduler identity mismatch")
        report, paths = settle_final_hybrid_comparison(
            sidecar_status_path=sidecar_status,
            drawing_id=result.drawing_id,
            drawing_number=result.drawing_number,
            plan_id=scheduler_plan.plan_id,
            actual=result.actual,
            output_dir=post_draw_root / "parallel-comparison",
        )
        payload = {
            "schema_version": 1,
            "status": "complete",
            "drawing_id": result.drawing_id,
            "drawing_number": result.drawing_number,
            "completed_at": _aware_utc(completed_at).isoformat(),
            "report_sha256": report["report_sha256"],
            "json_report": str(paths["json"]),
            "markdown_report": str(paths["markdown"]),
            "automatic_wagering": False,
            "notification": "not_attempted",
        }
        if notifier is not None:
            control = report["strategies"]["quality-v2"]
            sports = report["strategies"]["sports-shadow"]
            try:
                notifier(
                    f"Тираж {result.drawing_number}: quality-v2 "
                    f"{control['best_hits']}/15, sports-shadow "
                    f"{sports['best_hits']}/15. Сравнение: "
                    f"{paths['markdown'].resolve()}"
                )
            except Exception as error:  # advisory only
                payload["notification"] = "failed"
                payload["notification_error"] = _safe_reason(error)
            else:
                payload["notification"] = "sent"
        _write_json_replace(status_path, payload)
    except Exception as error:  # comparison is advisory to primary settlement
        _write_json_replace(
            status_path,
            {
                "schema_version": 1,
                "status": "failed",
                "drawing_id": result.drawing_id,
                "drawing_number": result.drawing_number,
                "completed_at": _aware_utc(completed_at).isoformat(),
                "error_type": type(error).__name__,
                "error": _safe_reason(error),
                "automatic_wagering": False,
            },
        )


def _post_draw_plan_state(
    plan: Mapping[str, Any],
    *,
    status: Literal["complete", "pending", "failed", "blocked"],
    reason: str,
    updated_at: datetime,
    attempted_slots: Sequence[str],
    due_slot: str | None = None,
    error_type: str | None = None,
    archive_sha256: str | None = None,
    result_snapshot_sha256: str | None = None,
    settlement_sha256: str | None = None,
    review_request_sha256: str | None = None,
) -> PostDrawState:
    binding = plan["package_binding"]
    return PostDrawState(
        schema_version=POST_DRAW_STATE_SCHEMA_VERSION,
        status=status,
        drawing_id=plan["drawing_id"],
        drawing_number=plan["drawing_number"],
        attempts=len(attempted_slots),
        max_attempts=plan["max_attempts"],
        updated_at=updated_at.isoformat(),
        package_sha256=binding.get("package_sha256"),
        result_snapshot_sha256=result_snapshot_sha256,
        settlement_sha256=settlement_sha256,
        reason=reason,
        attempted_slots=tuple(attempted_slots),
        due_slot=due_slot,
        error_type=error_type,
        archive_sha256=archive_sha256,
        review_request_sha256=review_request_sha256,
    )


def _classify_post_draw_error(
    error: BaseException,
) -> tuple[str, Literal["pending", "blocked", "failed"]]:
    message = _safe_reason(error).lower()
    if isinstance(error, (ConnectionError, TimeoutError, OSError)) or any(
        token in message
        for token in ("network", "offline", "timeout", "unavailable", "transport")
    ):
        return "PENDING_TRANSPORT", "pending"
    if any(
        token in message
        for token in ("15/15", "unresolved", "not finished", "result", "postpon")
    ):
        return "PENDING_RESULTS", "pending"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "REVIEW_BLOCKED_INTEGRITY", "blocked"
    return "POST_DRAW_FAILED", "failed"


def create_review_request(
    path: str | Path,
    *,
    drawing_id: int,
    drawing_number: int,
    package_kind: Literal["package", "package_free_no_bet"],
    settlement: Mapping[str, Any] | None,
    requested_at: datetime,
    snapshot_sha256: str | None = None,
    actual: str | None = None,
    void_event_orders: Sequence[int] = (),
    notifier: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists():
        existing = load_review_request(destination)
        if (
            existing["drawing_id"] != drawing_id
            or existing["drawing_number"] != drawing_number
            or existing["package_kind"] != package_kind
        ):
            raise ValueError("existing review request identity conflict")
        return existing
    if package_kind == "package" and settlement is None:
        raise ValueError("package review requires settlement")
    if settlement is not None:
        snapshot_sha256 = str(settlement["snapshot_sha256"])
        actual = str(settlement["actual"])
        void_event_orders = settlement.get("void_event_orders", ())
    if snapshot_sha256 is None or actual is None:
        raise ValueError("review request requires result snapshot and actual result")
    question = f"Разбираем пакет тиража {drawing_number}?"
    notification_message = _post_draw_notification_message(
        drawing_number=drawing_number,
        package_kind=package_kind,
        settlement=settlement,
        postmortem_path=Path(path).with_name("postmortem.md"),
    )
    notification: dict[str, Any] = {"status": "not_attempted", "error": None}
    if notifier is not None:
        try:
            notifier(notification_message)
        except Exception as error:  # notification is advisory only
            notification = {"status": "failed", "error": _safe_reason(error)}
        else:
            notification = {"status": "sent", "error": None}
    payload: dict[str, Any] = {
        "schema_version": POST_DRAW_REVIEW_SCHEMA_VERSION,
        "status": "AWAITING_USER_REVIEW",
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "package_kind": package_kind,
        "package_sha256": None if settlement is None else settlement["package_sha256"],
        "snapshot_sha256": snapshot_sha256,
        "settlement_sha256": (
            None if settlement is None else settlement["settlement_sha256"]
        ),
        "actual": actual,
        "void_event_orders": list(void_event_orders),
        "hit_distribution": (
            None if settlement is None else settlement["hit_distribution"]
        ),
        "best_hits": None if settlement is None else settlement["best_hits"],
        "best_coupon_ranks": (
            [] if settlement is None else list(settlement["best_coupon_ranks"])
        ),
        "category_counts": (
            None if settlement is None else settlement["category_counts"]
        ),
        "cost": 0 if settlement is None else settlement["cost"],
        "fixed_miss_events": (
            [] if settlement is None else list(settlement["fixed_miss_events"])
        ),
        "zero_exposure_miss_events": (
            []
            if settlement is None
            else list(settlement["zero_exposure_miss_events"])
        ),
        "known_return": None if settlement is None else settlement["known_return"],
        "roi": None if settlement is None else settlement["roi"],
        "return_status": (
            "package_free_no_bet"
            if settlement is None
            else settlement["return_status"]
        ),
        "question": question,
        "requested_at": _aware_utc(requested_at).isoformat(),
        "transitioned_at": None,
        "postmortem_path": None,
        "postmortem_sha256": None,
        "notification": notification,
    }
    payload["request_sha256"] = _review_request_sha256(payload)
    _write_json_replace(destination, payload)
    return load_review_request(destination)


def _review_request_sha256(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("request_sha256", None)
    normalized = json.loads(json.dumps(unsigned, ensure_ascii=False))
    return _sha256_json(normalized)


def _write_json_replace(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_review_request(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("review request must be an object")
        if payload.get("schema_version") != POST_DRAW_REVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported review request schema")
        if payload.get("request_sha256") != _review_request_sha256(payload):
            raise ValueError("review request hash mismatch")
        if payload.get("status") == "REVIEW_COMPLETE":
            postmortem = Path(payload["postmortem_path"])
            if postmortem.is_symlink() or not postmortem.is_file():
                raise ValueError("completed review postmortem is unavailable")
            if hashlib.sha256(postmortem.read_bytes()).hexdigest() != payload.get(
                "postmortem_sha256"
            ):
                raise ValueError("postmortem hash mismatch")
        return payload
    except (KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and "postmortem hash" in str(error):
            raise
        raise ValueError("review request is malformed") from error


def transition_review_request(
    path: str | Path,
    *,
    transition: Literal["request", "skip"],
    transitioned_at: datetime,
) -> dict[str, Any]:
    payload = load_review_request(path)
    if payload["status"] != "AWAITING_USER_REVIEW":
        raise ValueError("review transition is not allowed from current status")
    if transition not in {"request", "skip"}:
        raise ValueError("unsupported review transition")
    payload["status"] = (
        "REVIEW_REQUESTED" if transition == "request" else "REVIEW_SKIPPED"
    )
    payload["transitioned_at"] = _aware_utc(transitioned_at).isoformat()
    payload["request_sha256"] = _review_request_sha256(payload)
    _write_json_replace(Path(path), payload)
    return load_review_request(path)


def complete_post_draw_review(
    path: str | Path,
    *,
    postmortem_path: str | Path,
    completed_at: datetime,
) -> dict[str, Any]:
    payload = load_review_request(path)
    destination = Path(postmortem_path).resolve()
    if payload["status"] == "REVIEW_COMPLETE":
        if Path(payload["postmortem_path"]) != destination:
            raise ValueError("completed review postmortem path conflict")
        return payload
    if payload["status"] not in {"REVIEW_REQUESTED", "REVIEW_SKIPPED"}:
        raise ValueError("review completion transition is not allowed")
    postmortem = _render_postmortem(payload).encode("utf-8")
    _write_immutable_file(destination, postmortem, name="post-draw postmortem")
    payload["status"] = "REVIEW_COMPLETE"
    payload["transitioned_at"] = _aware_utc(completed_at).isoformat()
    payload["postmortem_path"] = str(destination)
    payload["postmortem_sha256"] = hashlib.sha256(postmortem).hexdigest()
    payload["request_sha256"] = _review_request_sha256(payload)
    _write_json_replace(Path(path), payload)
    return load_review_request(path)


def _render_postmortem(payload: Mapping[str, Any]) -> str:
    improvement_lines = _post_draw_improvement_lines(payload)
    return (
        f"# Post-draw review: drawing {payload['drawing_number']}\n\n"
        f"- Package kind: `{payload['package_kind']}`\n"
        f"- Actual/VOID: `{payload['actual']}` / {payload['void_event_orders']}\n"
        f"- Best hits/ranks: {payload['best_hits']} / {payload['best_coupon_ranks']}\n"
        f"- Hit distribution: {payload['hit_distribution']}\n"
        f"- Categories 13/14/15: {payload['category_counts']}\n"
        f"- Fixed misses: {payload['fixed_miss_events']}\n"
        f"- Zero-exposure misses: {payload['zero_exposure_miss_events']}\n"
        f"- Cost / known return / ROI: {payload['cost']} / "
        f"{payload['known_return']} / {payload['roi']} "
        f"(`{payload['return_status']}`)\n\n"
        "## Probability comparison\n\n"
        "BK / pool / Pin / sports-shadow / selected probabilities: "
        "not embedded in this settlement artifact; inspect the bound scheduler "
        "evidence before attributing errors.\n\n"
        "## Improvement candidates\n\n"
        + "\n".join(f"- {line}" for line in improvement_lines)
        + "\n\n"
        "## Interpretation boundary\n\n"
        "This report is deterministic evidence for error analysis; one drawing "
        "cannot establish causality or profitability.\n"
    )


def _post_draw_notification_message(
    *,
    drawing_number: int,
    package_kind: str,
    settlement: Mapping[str, Any] | None,
    postmortem_path: Path,
) -> str:
    if package_kind == "package_free_no_bet" or settlement is None:
        result = "ставочный пакет отсутствовал"
    else:
        categories = settlement.get("category_counts") or {}
        result = (
            f"лучший купон {settlement['best_hits']}/15; "
            f"13/14/15: {categories.get(13, categories.get('13', 0))}/"
            f"{categories.get(14, categories.get('14', 0))}/"
            f"{categories.get(15, categories.get('15', 0))}"
        )
    return (
        f"Тираж {drawing_number}: {result}. "
        f"Отчёт: {postmortem_path.resolve()}"
    )


def _post_draw_improvement_lines(payload: Mapping[str, Any]) -> tuple[str, ...]:
    if payload["package_kind"] == "package_free_no_bet":
        return (
            "No package was released; diagnose the release gate and data readiness "
            "before changing forecast probabilities.",
        )
    best_hits = int(payload["best_hits"])
    fixed = tuple(int(value) for value in payload["fixed_miss_events"])
    zero = tuple(int(value) for value in payload["zero_exposure_miss_events"])
    lines: list[str] = []
    if best_hits < 13:
        lines.append(
            f"The best coupon reached only {best_hits}/15; keep the current strategy "
            "unproven and compare every challenger at the same bank on frozen "
            "pre-deadline inputs."
        )
    if fixed:
        lines.append(
            "Review single-outcome concentration at events "
            + ", ".join(str(value) for value in fixed)
            + "; broaden only when pre-match evidence supports the alternative."
        )
    if zero:
        lines.append(
            "The actual outcome had zero package exposure at events "
            + ", ".join(str(value) for value in zero)
            + "; enforce an exposure floor before optimizing joint coupons."
        )
    if not fixed and not zero and best_hits < 13:
        lines.append(
            "Every realized outcome appeared somewhere in the package, so the main "
            "failure was joint coupon construction rather than a missing per-event "
            "outcome; test stronger cross-event diversity and robust category "
            "coverage."
        )
    lines.append(
        "Re-score quality-v2, quality-v3, sports-shadow-v2 and robust on the same "
        "settled drawing; do not promote a change from one drawing alone."
    )
    return tuple(lines)


def _resolve_explicit_drawing(
    session_factory: sessionmaker[Session],
    *,
    drawing_id: int | None,
    drawing_number: int | None,
) -> tuple[int, int]:
    if (drawing_id is None) == (drawing_number is None):
        raise ValueError("use exactly one of drawing_id or drawing_number")
    with session_factory() as session:
        if drawing_id is not None:
            if type(drawing_id) is not int or drawing_id < 1:
                raise ValueError("drawing_id must be a positive integer")
            drawing = session.get(Drawing, drawing_id)
        else:
            if type(drawing_number) is not int or drawing_number < 1:
                raise ValueError("drawing_number must be a positive integer")
            drawings = session.scalars(
                select(Drawing)
                .where(Drawing.number == drawing_number)
                .order_by(Drawing.id.desc())
            ).all()
            if len(drawings) != 1:
                raise ValueError(
                    f"drawing number {drawing_number} is ambiguous or missing"
                )
            drawing = drawings[0]
    if drawing is None:
        identity = (
            f"id {drawing_id}"
            if drawing_id is not None
            else f"number {drawing_number}"
        )
        raise ValueError(f"drawing {identity} was not found in the database")
    if drawing.number is None:
        raise ValueError("drawing has no visible number")
    return drawing.id, drawing.number


def _normalize_finished_payload(
    payload: Any,
    *,
    expected_id: int,
    expected_number: int,
    authoritative_ended_at: str,
    void_event_orders: Sequence[int] = (),
    void_source: str | None = None,
) -> dict[str, Any]:
    void_orders, reviewed_void_source = _normalize_void_event_orders(
        void_event_orders,
        void_source=void_source,
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ValueError("drawing-info payload must contain an object data field")
    data = payload["data"]
    if data.get("id") != expected_id:
        raise ValueError(
            f"drawing id mismatch: expected {expected_id}, got {data.get('id')}"
        )
    if data.get("number") != expected_number:
        raise ValueError(
            "drawing number mismatch: "
            f"expected {expected_number}, got {data.get('number')}"
        )
    if data.get("status") != "finished":
        raise ValueError("drawing is not finished")
    if "ended_at" in data:
        payload_ended_at = _canonical_timestamp(
            data.get("ended_at"),
            "finished payload ended_at",
        )
        if payload_ended_at != authoritative_ended_at:
            raise ValueError(
                "finished payload ended_at does not match stored drawing"
            )
    raw_events = data.get("events")
    if not isinstance(raw_events, list) or len(raw_events) != EVENT_COUNT:
        raise ValueError("finished drawing requires complete 15/15 events")
    by_order: dict[int, dict[str, Any]] = {}
    event_ids: set[int] = set()
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise ValueError("finished drawing event must be an object")
        order = raw.get("order")
        if type(order) is not int or order not in range(EVENT_COUNT):
            raise ValueError("finished drawing event order must be 0..14")
        if order in by_order:
            raise ValueError("finished drawing event orders must be unique")
        event_id = raw.get("id")
        if type(event_id) is not int or event_id <= 0 or event_id in event_ids:
            raise ValueError(
                "finished drawing requires 15 positive unique source event IDs"
            )
        event_ids.add(event_id)
        result = raw.get("result")
        score = raw.get("score")
        public_order = order + 1
        if public_order in void_orders:
            if result not in (None, "") or score not in (None, ""):
                raise ValueError(
                    f"void event {public_order} already has a result or score"
                )
            by_order[order] = {
                "order": order,
                "event_id": event_id,
                "result": VOID_RESULT,
                "result_status": "void",
                "score": "",
                "void_source": reviewed_void_source,
            }
            continue
        if result in (None, "") and score in (None, ""):
            raise ValueError(
                f"finished event {public_order} result is unresolved; "
                "a reviewed void override is required"
            )
        if result not in OUTCOMES or not isinstance(score, str) or not score.strip():
            raise ValueError("finished drawing requires complete 15/15 results/scores")
        by_order[order] = {
            "order": order,
            "event_id": event_id,
            "result": result,
            "result_status": "resolved",
            "score": score,
        }
    if set(by_order) != set(range(EVENT_COUNT)):
        raise ValueError("finished drawing event orders must be exactly 0..14")
    events = [by_order[order] for order in range(EVENT_COUNT)]
    return {
        "status": "finished",
        "ended_at": authoritative_ended_at,
        "events": events,
        "actual": "".join(event["result"] for event in events),
        "void_event_orders": sorted(void_orders),
        "payments": _extract_payments(data),
        "pool_sum": _optional_finite_number(data.get("pool_sum"), "pool_sum"),
        "jackpot": _optional_finite_number(data.get("jackpot"), "jackpot"),
    }


def _normalize_void_event_orders(
    values: Sequence[int],
    *,
    void_source: str | None,
) -> tuple[set[int], str | None]:
    orders: set[int] = set()
    for value in values:
        if type(value) is not int or value not in range(1, EVENT_COUNT + 1):
            raise ValueError("void_event_orders must contain integers from 1 to 15")
        if value in orders:
            raise ValueError("void_event_orders must be unique")
        orders.add(value)
    if orders:
        reviewed_source = _normalize_http_evidence_url(void_source)
    elif void_source is not None:
        raise ValueError("void_source requires at least one void event")
    else:
        reviewed_source = None
    return orders, reviewed_source


def _normalize_http_evidence_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("void_source must be a non-empty HTTP(S) evidence URL")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 2048
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("void_source must be a non-empty HTTP(S) evidence URL")
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
    except ValueError as error:
        raise ValueError(
            "void_source must be a non-empty HTTP(S) evidence URL"
        ) from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("void_source must be a non-empty HTTP(S) evidence URL")
    return normalized


def _persist_operational_result(
    session: Session,
    normalized: Mapping[str, Any],
    *,
    drawing_id: int,
    drawing_number: int,
) -> None:
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        drawing = Drawing(id=drawing_id, number=drawing_number)
        session.add(drawing)
    elif (
        _canonical_timestamp(drawing.ended_at, "stored drawing ended_at")
        != normalized["ended_at"]
    ):
        raise ValueError("stored drawing ended_at changed during result sync")
    drawing.number = drawing_number
    drawing.status = "finished"
    drawing.pool_sum = normalized["pool_sum"]
    drawing.jackpot = normalized["jackpot"]
    for item in normalized["events"]:
        session.execute(
            sqlite_insert(Event)
            .values(
                drawing_id=drawing_id,
                event_order=item["order"],
                result=item["result"],
                result_status=item["result_status"],
                score=item["score"],
            )
            .on_conflict_do_update(
                index_elements=("drawing_id", "event_order"),
                set_={
                    "result": item["result"],
                    "result_status": item["result_status"],
                    "score": item["score"],
                },
            )
        )


def _compute_settlement(
    *,
    actual: str,
    coupons: Sequence[str],
    stake: int,
    payments: Any,
) -> dict[str, Any]:
    allowed_results = set(OUTCOMES) | {VOID_RESULT}
    if len(actual) != EVENT_COUNT or any(
        value not in allowed_results for value in actual
    ):
        raise ValueError("settlement requires an actual 15-outcome string")
    if not coupons:
        raise ValueError("settlement package must contain coupons")
    hits = [
        sum(
            right == VOID_RESULT or left == right
            for left, right in zip(coupon, actual, strict=True)
        )
        for coupon in coupons
    ]
    counts = Counter(hits)
    distribution = {category: counts.get(category, 0) for category in range(16)}
    best = max(hits)
    best_ranks = [index for index, value in enumerate(hits, start=1) if value == best]
    payout_by_category = _payout_per_winner(payments)
    categories = (
        None
        if payout_by_category is None
        else {
            category: counts.get(category, 0)
            for category in sorted(payout_by_category)
        }
    )
    fixed_misses: list[int] = []
    zero_exposure_misses: list[int] = []
    for index, outcome in enumerate(actual):
        if outcome == VOID_RESULT:
            continue
        exposed = {coupon[index] for coupon in coupons}
        if outcome not in exposed:
            zero_exposure_misses.append(index + 1)
            if len(exposed) == 1:
                fixed_misses.append(index + 1)
    cost = stake * len(coupons)
    if categories is None:
        known_return = None
        roi = None
        return_status = "unknown_until_payouts"
    else:
        hit_categories = [key for key, value in categories.items() if value]
        if not hit_categories:
            known_return = 0.0
            roi = -1.0
            return_status = "known_zero_from_official_categories"
        else:
            assert payout_by_category is not None
            known_return = sum(
                categories[key] * payout_by_category[key] for key in hit_categories
            )
            roi = known_return / cost - 1
            return_status = "known_from_official_payments"
    return {
        "actual": actual,
        "void_event_orders": [
            index + 1
            for index, outcome in enumerate(actual)
            if outcome == VOID_RESULT
        ],
        "hit_distribution": distribution,
        "best_hits": best,
        "best_coupon_ranks": best_ranks,
        "category_counts": categories,
        "cost": cost,
        "fixed_miss_events": fixed_misses,
        "zero_exposure_miss_events": zero_exposure_misses,
        "known_return": known_return,
        "roi": roi,
        "return_status": return_status,
    }


def _extract_payments(data: Mapping[str, Any]) -> Any:
    for key in ("payments", "payouts", "prizes"):
        if key in data:
            return data[key]
    return None


def _payout_per_winner(payments: Any) -> dict[int, float] | None:
    if payments is None:
        return None
    if isinstance(payments, Mapping):
        explicit = payments.get("payout_per_winner")
        if isinstance(explicit, Mapping):
            return _numeric_category_mapping(explicit)
        return None
    if isinstance(payments, list):
        result: dict[int, float] = {}
        for row in payments:
            if not isinstance(row, Mapping):
                return None
            category = row.get("category", row.get("hits"))
            payout = row.get("payout_per_winner")
            if type(category) is not int or category not in range(10, 16):
                return None
            if payout is None:
                return None
            value = _optional_finite_number(payout, "payout_per_winner")
            if value is None or value < 0:
                return None
            result[category] = value
        return result or None
    return None


def _numeric_category_mapping(values: Mapping[Any, Any]) -> dict[int, float] | None:
    result: dict[int, float] = {}
    for raw_category, raw_value in values.items():
        try:
            category = int(raw_category)
        except (TypeError, ValueError):
            return None
        value = _optional_finite_number(raw_value, "payout_per_winner")
        if category not in range(10, 16) or value is None or value < 0:
            return None
        result[category] = value
    return result or None


def _parse_package_source(source: bytes) -> tuple[tuple[str, ...], set[int]]:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("package source must be UTF-8") from error
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("package must contain coupons")
    header = [cell.strip().lower() for cell in rows[0]]
    coupons: list[str] = []
    stakes: set[int] = set()
    if "coupon" in header:
        coupon_index = header.index("coupon")
        stake_index = header.index("stake") if "stake" in header else None
        for line, row in enumerate(rows[1:], start=2):
            if coupon_index >= len(row):
                raise ValueError(f"missing coupon at CSV line {line}")
            coupons.append(row[coupon_index].strip())
            if stake_index is not None:
                if stake_index >= len(row) or not row[stake_index].strip().isdigit():
                    raise ValueError(f"invalid declared stake at CSV line {line}")
                declared = int(row[stake_index])
                if declared <= 0:
                    raise ValueError(f"invalid declared stake at CSV line {line}")
                stakes.add(declared)
    else:
        for line, row in enumerate(rows, start=1):
            if len(row) != 1:
                raise ValueError(f"unsupported package row at line {line}")
            cells = [cell.strip() for cell in row[0].split(";")]
            if len(cells) == 16 and cells[0].isdigit():
                declared = int(cells[0])
                if declared <= 0:
                    raise ValueError(f"invalid declared stake at line {line}")
                stakes.add(declared)
                coupons.append("".join(cells[1:]))
            elif len(cells) == 1:
                coupons.append(cells[0])
            else:
                raise ValueError(f"malformed package row at line {line}")
    return validate_coupons(coupons), stakes


def _verified_snapshot(
    session: Session,
    snapshot_sha256: str,
) -> DrawingResultSnapshot:
    row = session.scalar(
        select(DrawingResultSnapshot).where(
            DrawingResultSnapshot.snapshot_sha256 == snapshot_sha256
        )
    )
    if row is None:
        raise ValueError("result snapshot was not found")
    try:
        payload = json.loads(row.payload_json)
        events = json.loads(row.events_json)
        payments = (
            None if row.payments_json is None else json.loads(row.payments_json)
        )
    except (TypeError, ValueError) as error:
        raise ValueError("result snapshot JSON is malformed") from error
    if _sha256_text(_canonical_json(payload)) != row.payload_sha256:
        raise ValueError("result snapshot payload hash mismatch")
    data = payload.get("data") if isinstance(payload, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("id") != row.drawing_id
        or data.get("number") != row.drawing_number
    ):
        raise ValueError("result snapshot payload identity mismatch")
    canonical_ended_at = _canonical_timestamp(
        row.ended_at,
        "result snapshot ended_at",
    )
    drawing = session.get(Drawing, row.drawing_id)
    if drawing is None or _canonical_timestamp(
        drawing.ended_at,
        "stored drawing ended_at",
    ) != canonical_ended_at:
        raise ValueError("result snapshot ended_at evidence mismatch")
    if "ended_at" in data and _canonical_timestamp(
        data.get("ended_at"),
        "finished payload ended_at",
    ) != canonical_ended_at:
        raise ValueError("result snapshot payload ended_at mismatch")
    if _sha256_json(events) != row.result_sha256:
        raise ValueError("result snapshot result hash mismatch")
    _validate_snapshot_events(
        events,
        hash_schema_version=row.hash_schema_version,
    )
    if (
        not row.complete
        or row.event_count != EVENT_COUNT
        or len(events) != EVENT_COUNT
        or "".join(event["result"] for event in events) != row.actual
    ):
        raise ValueError("result snapshot completeness mismatch")
    content = _result_snapshot_hash_content(
        hash_schema_version=row.hash_schema_version,
        drawing_id=row.drawing_id,
        drawing_number=row.drawing_number,
        ended_at=canonical_ended_at,
        events=events,
        payments=payments,
        pool_sum=row.pool_sum,
        jackpot=row.jackpot,
    )
    if _sha256_json(content) != row.snapshot_sha256:
        raise ValueError("result snapshot content hash mismatch")
    return row


def verify_result_snapshot(
    session_factory: sessionmaker[Session],
    snapshot_sha256: str,
) -> str:
    """Recompute and verify one legacy/current immutable result snapshot."""
    with session_factory() as session:
        return _verified_snapshot(session, snapshot_sha256).snapshot_sha256


def _verified_archive(session: Session, archive_sha256: str) -> ArchivedPackage:
    row = session.get(ArchivedPackage, archive_sha256)
    if row is None:
        raise ValueError("archived package was not found")
    coupons, declared_stakes = _parse_package_source(row.source_bytes)
    if declared_stakes and declared_stakes != {row.stake}:
        raise ValueError("archived package declared stake mismatch")
    if hashlib.sha256(row.source_bytes).hexdigest() != row.source_bytes_sha256:
        raise ValueError("archived package source hash mismatch")
    if _sha256_text(",".join(coupons)) != row.package_sha256:
        raise ValueError("archived package canonical hash mismatch")
    if _canonical_json(coupons) != row.coupons_json:
        raise ValueError("archived package coupon content mismatch")
    expected = _sha256_json(
        {
            "drawing_id": row.drawing_id,
            "drawing_number": row.drawing_number,
            "stake": row.stake,
            "coupons": coupons,
            "package_sha256": row.package_sha256,
        }
    )
    if expected != row.archive_sha256:
        raise ValueError("archived package identity hash mismatch")
    if row.cost != row.stake * row.coupon_count or row.coupon_count != len(coupons):
        raise ValueError("archived package cost/count mismatch")
    if row.provenance not in ("pre_bet_runner", "legacy_import"):
        raise ValueError("archived package provenance is invalid")
    if row.provenance == "pre_bet_runner":
        if (
            not isinstance(row.archive_manifest_sha256, str)
            or len(row.archive_manifest_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in row.archive_manifest_sha256
            )
        ):
            raise ValueError("archived pre-bet manifest hash is invalid")
    elif row.archive_manifest_sha256 is not None:
        raise ValueError("legacy archive has unexpected manifest hash")
    return row


def _verified_archive_for_source(
    session: Session,
    package_file: str | Path,
    *,
    drawing_id: int,
    drawing_number: int,
    stake: int,
) -> ArchivedPackage:
    source = Path(package_file).read_bytes()
    coupons, declared_stakes = _parse_package_source(source)
    if declared_stakes and declared_stakes != {stake}:
        raise ValueError("package declared stake mismatch")
    package_hash = _sha256_text(",".join(coupons))
    rows = session.scalars(
        select(ArchivedPackage)
        .where(ArchivedPackage.drawing_id == drawing_id)
        .where(ArchivedPackage.drawing_number == drawing_number)
        .where(ArchivedPackage.stake == stake)
        .where(ArchivedPackage.package_sha256 == package_hash)
    ).all()
    if len(rows) != 1:
        raise ValueError(
            "package must match exactly one pre-existing auditable archive"
        )
    row = _verified_archive(session, rows[0].archive_sha256)
    if row.source_bytes_sha256 != hashlib.sha256(source).hexdigest():
        raise ValueError("package source bytes do not match archived evidence")
    return row


def _archive_result(row: ArchivedPackage, *, created: bool) -> PackageArchive:
    return PackageArchive(
        archive_sha256=row.archive_sha256,
        package_sha256=row.package_sha256,
        drawing_id=row.drawing_id,
        drawing_number=row.drawing_number,
        stake=row.stake,
        coupon_count=row.coupon_count,
        cost=row.cost,
        source_path=row.source_path,
        source_bytes_sha256=row.source_bytes_sha256,
        provenance=row.provenance,
        archive_manifest_sha256=row.archive_manifest_sha256,
        final_input_sha256=row.final_input_sha256,
        probability_input_sha256=row.probability_input_sha256,
        final_input_captured_at=row.final_input_captured_at,
        created=created,
    )


def _verified_settlement(
    session: Session,
    settlement_sha256: str,
) -> PackageSettlement:
    row = session.get(PackageSettlement, settlement_sha256)
    if row is None:
        raise ValueError("settlement was not found")
    snapshot = _verified_snapshot(session, row.result_snapshot_sha256)
    package = _verified_archive(session, row.archive_sha256)
    payments = (
        None
        if snapshot.payments_json is None
        else json.loads(snapshot.payments_json)
    )
    computed = _compute_settlement(
        actual=snapshot.actual,
        coupons=tuple(json.loads(package.coupons_json)),
        stake=package.stake,
        payments=payments,
    )
    payload = {
        "drawing_id": snapshot.drawing_id,
        "drawing_number": snapshot.drawing_number,
        "result_snapshot_sha256": snapshot.snapshot_sha256,
        "archive_sha256": package.archive_sha256,
        "package_sha256": package.package_sha256,
        **_settlement_payload_fields(computed),
    }
    if _sha256_json(payload) != row.settlement_sha256:
        raise ValueError("settlement hash mismatch")
    if _canonical_json(payload) != row.settlement_json:
        raise ValueError("settlement content mismatch")
    expected_columns = {
        "drawing_id": snapshot.drawing_id,
        "drawing_number": snapshot.drawing_number,
        "result_snapshot_sha256": snapshot.snapshot_sha256,
        "archive_sha256": package.archive_sha256,
        "package_sha256": package.package_sha256,
        "actual": computed["actual"],
        "hit_distribution_json": _canonical_json(computed["hit_distribution"]),
        "best_hits": computed["best_hits"],
        "best_coupon_ranks_json": _canonical_json(
            computed["best_coupon_ranks"]
        ),
        "category_counts_json": (
            None
            if computed["category_counts"] is None
            else _canonical_json(computed["category_counts"])
        ),
        "cost": computed["cost"],
        "fixed_miss_events_json": _canonical_json(
            computed["fixed_miss_events"]
        ),
        "zero_exposure_miss_events_json": _canonical_json(
            computed["zero_exposure_miss_events"]
        ),
        "known_return": computed["known_return"],
        "roi": computed["roi"],
        "return_status": computed["return_status"],
    }
    if any(getattr(row, key) != value for key, value in expected_columns.items()):
        raise ValueError("settlement stored columns mismatch")
    return row


def _settlement_payload_fields(computed: Mapping[str, Any]) -> dict[str, Any]:
    fields = dict(computed)
    if not fields.get("void_event_orders"):
        fields.pop("void_event_orders", None)
    return fields


def _verify_complete_state(
    session_factory: sessionmaker[Session],
    state: PostDrawState,
) -> None:
    if (
        state.result_snapshot_sha256 is None
        or state.settlement_sha256 is None
        or state.package_sha256 is None
    ):
        raise ValueError("complete state is missing evidence hashes")
    with session_factory() as session:
        snapshot = _verified_snapshot(session, state.result_snapshot_sha256)
        settlement = _verified_settlement(session, state.settlement_sha256)
        package = _verified_archive(session, settlement.archive_sha256)
        drawing = session.get(Drawing, state.drawing_id)
        if (
            drawing is None
            or drawing.number != state.drawing_number
            or snapshot.drawing_id != state.drawing_id
            or snapshot.drawing_number != state.drawing_number
            or settlement.result_snapshot_sha256 != snapshot.snapshot_sha256
            or package.package_sha256 != state.package_sha256
        ):
            raise ValueError("complete state evidence identity mismatch")


def _write_state(path: str | Path, state: PostDrawState) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.tmp"
    )
    try:
        payload = state.to_dict()
        payload.pop("state_sha256", None)
        state_hash = _sha256_json(payload)
        object.__setattr__(state, "state_sha256", state_hash)
        temporary.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _load_state(path: str | Path) -> PostDrawState | None:
    source = Path(path)
    if not source.exists():
        return None
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        state_hash = data.get("state_sha256")
        if not isinstance(state_hash, str):
            raise ValueError("missing state hash")
        unsigned = dict(data)
        unsigned.pop("state_sha256")
        if _sha256_json(unsigned) != state_hash:
            raise ValueError("state hash mismatch")
        if isinstance(data.get("attempted_slots"), list):
            data["attempted_slots"] = tuple(data["attempted_slots"])
        return PostDrawState(**data)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("post-draw state is malformed") from error


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_totobrief_deadline(drawing: Drawing | None) -> datetime | None:
    if drawing is None or not drawing.ended_at:
        return None
    try:
        return parse_totobrief_timestamp(
            drawing.ended_at,
            community=drawing.name,
            field_name="drawing.ended_at",
        )
    except ValueError:
        return None


def _parse_timestamp_required(value: Any) -> datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError("ended_at must be an aware ISO-8601 timestamp")
    return parsed


def _canonical_timestamp(value: Any, name: str) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"{name} must be an aware valid timestamp")
    return parsed.isoformat()


def _aware_utc(value: datetime | None) -> datetime:
    current = datetime.now(timezone.utc) if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return current.astimezone(timezone.utc)


def _optional_finite_number(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number or null")
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _result_snapshot_hash_content(
    *,
    hash_schema_version: int,
    drawing_id: int,
    drawing_number: int,
    ended_at: str,
    events: Any,
    payments: Any,
    pool_sum: float | None,
    jackpot: float | None,
) -> dict[str, Any]:
    content = {
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "status": "finished",
        "events": events,
        "payments": payments,
        "pool_sum": pool_sum,
        "jackpot": jackpot,
    }
    if hash_schema_version in (
        TIMED_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
        RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
    ):
        content["ended_at"] = _canonical_timestamp(
            ended_at,
            "result snapshot ended_at",
        )
    elif hash_schema_version != LEGACY_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION:
        raise ValueError("unsupported result snapshot hash schema version")
    return content


def _validate_snapshot_events(
    events: Any,
    *,
    hash_schema_version: int,
) -> None:
    if not isinstance(events, list) or len(events) != EVENT_COUNT:
        raise ValueError("result snapshot events are invalid")
    for expected_order, event in enumerate(events):
        if not isinstance(event, Mapping) or event.get("order") != expected_order:
            raise ValueError("result snapshot event order is invalid")
        result = event.get("result")
        score = event.get("score")
        if hash_schema_version < RESULT_SNAPSHOT_HASH_SCHEMA_VERSION:
            if (
                result not in OUTCOMES
                or not isinstance(score, str)
                or not score.strip()
            ):
                raise ValueError("legacy result snapshot event is invalid")
            continue
        status = event.get("result_status")
        if result == VOID_RESULT:
            source = event.get("void_source")
            try:
                reviewed_source = _normalize_http_evidence_url(source)
            except ValueError as error:
                raise ValueError(
                    "void result snapshot evidence is invalid"
                ) from error
            if status != "void" or score != "" or source != reviewed_source:
                raise ValueError("void result snapshot evidence is invalid")
        elif (
            result not in OUTCOMES
            or status != "resolved"
            or not isinstance(score, str)
            or not score.strip()
            or "void_source" in event
        ):
            raise ValueError("resolved result snapshot event is invalid")


def _sha256_json(value: Any) -> str:
    return _sha256_text(_canonical_json(value))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_reason(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    return message[:500]
