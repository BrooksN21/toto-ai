"""Explicit, append-only finished-drawing synchronization and settlement."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import math
import os
import plistlib
import shlex
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from toto_ai.db.models import (
    ArchivedPackage,
    Drawing,
    DrawingResultSnapshot,
    Event,
    PackageSettlement,
)
from toto_ai.package.audit import OUTCOMES, validate_coupons

EVENT_COUNT = 15
VOID_RESULT = "*"
RESULT_ENDPOINT_TEMPLATE = "/drawing-info/{drawing_id}"
LEGACY_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 1
TIMED_RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 2
RESULT_SNAPSHOT_HASH_SCHEMA_VERSION = 3


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
    status: Literal["complete", "pending", "failed"]
    drawing_id: int
    drawing_number: int
    attempts: int
    max_attempts: int
    updated_at: str
    package_sha256: str | None
    result_snapshot_sha256: str | None
    settlement_sha256: str | None
    reason: str
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

    with session_factory.begin() as session:
        values = {
            "drawing_id": expected_id,
            "drawing_number": expected_number,
            "hash_schema_version": RESULT_SNAPSHOT_HASH_SCHEMA_VERSION,
            "ended_at": normalized["ended_at"],
            "retrieved_at": retrieved_text,
            "source_endpoint": endpoint,
            "payload_sha256": payload_hash,
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
        created = inserted.rowcount == 1
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
            ended = _parse_timestamp(drawing.ended_at)
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
        ended_at = _parse_timestamp(drawing.ended_at if drawing is not None else None)
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
    package_file: str | Path,
    stake: int,
    db: str | Path,
    state_file: str | Path,
    output_dir: str | Path,
    project_root: str | Path,
    python_executable: str,
    max_attempts: int,
    initial_delay_seconds: float,
    max_delay_seconds: float,
) -> tuple[Path, Path, Path]:
    """Generate, but never install, a local launchd wrapper and plist candidate."""
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
        stored_ended = _parse_timestamp_required(
            None if drawing is None else drawing.ended_at
        )
    requested_ended = _parse_timestamp_required(ended_at)
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
    first_run = ended + timedelta(seconds=1)
    plan.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "drawing_id": resolved_id,
                "drawing_number": resolved_number,
                "ended_at": ended.isoformat(),
                "first_run_at": first_run.isoformat(),
                "package_file": str(Path(package_file).resolve()),
                "db": str(Path(db).resolve()),
                "state_file": str(Path(state_file).resolve()),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    argv = [
        str(Path(python_executable)),
        "-m",
        "toto_ai.cli",
        "post-draw-run",
        "--drawing-id",
        str(resolved_id),
        "--package-file",
        str(Path(package_file).resolve()),
        "--stake",
        str(stake),
        "--db",
        str(Path(db).resolve()),
        "--state-file",
        str(Path(state_file).resolve()),
        "--max-attempts",
        str(max_attempts),
        "--initial-delay-seconds",
        str(initial_delay_seconds),
        "--max-delay-seconds",
        str(max_delay_seconds),
    ]
    command = "exec " + shlex.join(argv)
    barrier = shlex.join(
        [
            str(Path(python_executable)),
            "-c",
            (
                "import time; target="
                f"{first_run.timestamp()!r}; "
                "time.sleep(max(0.0, target-time.time()))"
            ),
        ]
    )
    wrapper.write_text(
        "#!/bin/sh\nset -eu\n"
        f"cd {shlex.quote(str(root))}\n"
        f"{barrier}\n"
        f"{command}\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    # launchd has minute precision and interprets calendar fields in local time.
    # launchd is only a wake-up hint. The wrapper's absolute epoch barrier is
    # authoritative across seconds, timezone offsets, and DST transitions.
    start = first_run.astimezone()
    if start.second or start.microsecond:
        start = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
    plist.write_bytes(
        plistlib.dumps(
            {
                "Label": f"com.toto-ai.post-draw-{target_label}",
                "ProgramArguments": [str(wrapper)],
                "WorkingDirectory": str(root),
                "StartCalendarInterval": {
                    "Year": start.year,
                    "Month": start.month,
                    "Day": start.day,
                    "Hour": start.hour,
                    "Minute": start.minute,
                },
            },
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )
    )
    return plan, wrapper, plist


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
                score=item["score"],
            )
            .on_conflict_do_update(
                index_elements=("drawing_id", "event_order"),
                set_={"result": item["result"], "score": item["score"]},
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
