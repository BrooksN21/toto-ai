from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

TIMING_OVERRIDE_SCHEMA_VERSION = 1

TimingSource = Literal[
    "totobrief", "provider", "operator_override", "unresolved"
]
DiagnosticCode = Literal[
    "override_not_found",
    "target_fingerprint_mismatch",
    "ambiguous_override",
    "partial_override",
    "event_identity_mismatch",
    "event_start_before_drawing_end",
    "event_start_after_override_horizon",
    "reviewed_at_after_pin",
    "reviewed_at_before_review_window",
    "known_start_preserved",
    "unresolved_events_remain",
]

_EVENT_ORDERS = tuple(range(15))
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MOSCOW = ZoneInfo("Europe/Moscow")
_ROOT_FIELDS = frozenset(("overrides",))
_RECORD_COMMON_FIELDS = frozenset(
    (
        "schema_version",
        "override_id",
        "target_fingerprint",
        "reviewer",
        "reviewed_at",
        "source_ref",
        "events",
    )
)
_EVENT_FIELDS = frozenset(("event_order", "event_id", "starts_at"))
_EVENT_FIELDS_WITH_SOURCE = _EVENT_FIELDS | {"source_ref"}
_MAX_OVERRIDE_HORIZON = timedelta(days=5)
_MAX_REVIEW_LEAD = timedelta(days=7)
_BLOCKING_DIAGNOSTICS = frozenset(
    (
        "override_not_found",
        "target_fingerprint_mismatch",
        "ambiguous_override",
        "partial_override",
        "event_identity_mismatch",
        "event_start_before_drawing_end",
        "event_start_after_override_horizon",
        "reviewed_at_after_pin",
        "reviewed_at_before_review_window",
        "unresolved_events_remain",
    )
)


@dataclass(frozen=True)
class TimingOverrideEvent:
    event_order: int
    event_id: int
    starts_at: datetime
    source_ref: str | None = None

    def __post_init__(self) -> None:
        _require_event_order(self.event_order)
        _require_positive_int("event_id", self.event_id)
        object.__setattr__(
            self,
            "starts_at",
            _require_utc_datetime("starts_at", self.starts_at),
        )
        if self.source_ref is not None:
            _require_canonical_text("source_ref", self.source_ref)


@dataclass(frozen=True)
class TimingOverrideRecord:
    schema_version: int
    override_id: str
    drawing_id: int | None
    drawing_number: int | None
    target_fingerprint: str
    reviewer: str
    reviewed_at: datetime
    source_ref: str
    events: tuple[TimingOverrideEvent, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != TIMING_OVERRIDE_SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version must be {TIMING_OVERRIDE_SCHEMA_VERSION}"
            )
        _require_canonical_text("override_id", self.override_id)
        if (self.drawing_id is None) == (self.drawing_number is None):
            raise ValueError(
                "exactly one of drawing_id or drawing_number must be present"
            )
        if self.drawing_id is not None:
            _require_positive_int("drawing_id", self.drawing_id)
        if self.drawing_number is not None:
            _require_positive_int("drawing_number", self.drawing_number)
        _require_target_fingerprint(self.target_fingerprint)
        _require_canonical_text("reviewer", self.reviewer)
        object.__setattr__(
            self,
            "reviewed_at",
            _require_utc_datetime("reviewed_at", self.reviewed_at),
        )
        _require_canonical_text("source_ref", self.source_ref)
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        if not 1 <= len(self.events) <= 15:
            raise ValueError("events must contain between 1 and 15 entries")
        if any(not isinstance(event, TimingOverrideEvent) for event in self.events):
            raise ValueError("events must contain TimingOverrideEvent records")
        event_orders = tuple(event.event_order for event in self.events)
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_orders)) != len(event_orders):
            raise ValueError("override event_order values must be unique")
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("override event_id values must be unique")
        object.__setattr__(
            self,
            "events",
            tuple(sorted(self.events, key=lambda event: event.event_order)),
        )

    @property
    def is_complete(self) -> bool:
        return tuple(event.event_order for event in self.events) == _EVENT_ORDERS


@dataclass(frozen=True)
class TimingOverrideCatalog:
    records: tuple[TimingOverrideRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        if any(not isinstance(record, TimingOverrideRecord) for record in self.records):
            raise ValueError("records must contain TimingOverrideRecord values")

        override_ids = tuple(record.override_id for record in self.records)
        if len(set(override_ids)) != len(override_ids):
            raise ValueError("override_id values must be unique")

        target_keys = tuple(_record_target_key(record) for record in self.records)
        if len(set(target_keys)) != len(target_keys):
            raise ValueError("override target records must be unique")

        object.__setattr__(
            self,
            "records",
            tuple(sorted(self.records, key=lambda record: record.override_id)),
        )


@dataclass(frozen=True)
class PinnedTimingOverrideCatalog:
    """One optional catalog input captured during runner preflight.

    Invalid inputs are retained as a fail-closed diagnostic rather than being
    converted into an unvalidated catalog or a permissive switch.
    """

    path: Path
    catalog: TimingOverrideCatalog | None
    catalog_sha256: str | None
    validation_error: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.catalog is None:
            if self.catalog_sha256 is not None:
                raise ValueError("an invalid catalog cannot have a catalog hash")
            _require_canonical_text("validation_error", self.validation_error)
            return
        if not isinstance(self.catalog, TimingOverrideCatalog):
            raise ValueError("catalog must be a TimingOverrideCatalog")
        _require_target_fingerprint(self.catalog_sha256)
        if self.validation_error is not None:
            raise ValueError("a valid catalog cannot have a validation error")
        if timing_override_catalog_sha256(self.catalog) != self.catalog_sha256:
            raise ValueError("catalog_sha256 does not match catalog content")

    @property
    def valid(self) -> bool:
        return self.catalog is not None


@dataclass(frozen=True)
class TimingOverrideCatalogCheck:
    catalog: TimingOverrideCatalog | None
    observed_sha256: str | None
    matches_preflight: bool
    validation_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.matches_preflight, bool):
            raise ValueError("matches_preflight must be a boolean")
        if self.catalog is None:
            if self.observed_sha256 is not None:
                raise ValueError("an invalid catalog cannot have an observed hash")
            _require_canonical_text("validation_error", self.validation_error)
            if self.matches_preflight:
                raise ValueError("an invalid catalog cannot match preflight")
            return
        if not isinstance(self.catalog, TimingOverrideCatalog):
            raise ValueError("catalog must be a TimingOverrideCatalog")
        _require_target_fingerprint(self.observed_sha256)
        if self.validation_error is not None:
            raise ValueError("a valid catalog check cannot have a validation error")
        if timing_override_catalog_sha256(self.catalog) != self.observed_sha256:
            raise ValueError("observed_sha256 does not match catalog content")


@dataclass(frozen=True)
class TimingSnapshotSummary:
    status: Literal["playable", "multi_day", "unknown"]
    earliest_start: datetime | None
    latest_start: datetime | None
    span_days: int
    missing_event_orders: tuple[int, ...]
    totobrief_count: int
    provider_count: int
    operator_override_count: int
    validated_override_record: TimingOverrideRecord | None = None

    def __post_init__(self) -> None:
        if self.status not in ("playable", "multi_day", "unknown"):
            raise ValueError("invalid timing snapshot status")
        if self.earliest_start is not None:
            object.__setattr__(
                self,
                "earliest_start",
                _require_utc_datetime("earliest_start", self.earliest_start),
            )
        if self.latest_start is not None:
            object.__setattr__(
                self,
                "latest_start",
                _require_utc_datetime("latest_start", self.latest_start),
            )
        if (
            not isinstance(self.span_days, int)
            or isinstance(self.span_days, bool)
            or self.span_days < 0
        ):
            raise ValueError("span_days must be a non-negative integer")
        _require_order_tuple("missing_event_orders", self.missing_event_orders)
        for name, value in (
            ("totobrief_count", self.totobrief_count),
            ("provider_count", self.provider_count),
            ("operator_override_count", self.operator_override_count),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= 15
            ):
                raise ValueError(f"{name} must be an integer from 0 through 15")
        known_count = 15 - len(self.missing_event_orders)
        if (
            self.totobrief_count
            + self.provider_count
            + self.operator_override_count
            != known_count
        ):
            raise ValueError("timing source counts are inconsistent")
        if known_count == 0:
            if self.earliest_start is not None or self.latest_start is not None:
                raise ValueError("known start bounds must be absent")
            expected_span = 0
        else:
            if self.earliest_start is None or self.latest_start is None:
                raise ValueError("known start bounds must be present")
            if self.earliest_start > self.latest_start:
                raise ValueError("earliest_start must not be after latest_start")
            expected_span = _moscow_calendar_span(
                self.earliest_start,
                self.latest_start,
            )
        if self.span_days != expected_span:
            raise ValueError("span_days is inconsistent with start bounds")
        expected_status = (
            "multi_day"
            if self.span_days > 2
            else "unknown"
            if self.missing_event_orders
            else "playable"
        )
        if self.status != expected_status:
            raise ValueError("status is inconsistent with timing completeness")
        if self.validated_override_record is not None:
            if not isinstance(
                self.validated_override_record,
                TimingOverrideRecord,
            ):
                raise ValueError(
                    "validated_override_record must be a TimingOverrideRecord"
                )
            if not self.validated_override_record.is_complete:
                raise ValueError("validated override record must be complete")
            if self.missing_event_orders:
                raise ValueError(
                    "validated override summary cannot retain unresolved starts"
                )


@dataclass(frozen=True)
class EventTimingSnapshot:
    event_order: int
    event_id: int
    starts_at: datetime | None
    source: TimingSource

    def __post_init__(self) -> None:
        _require_event_order(self.event_order)
        _require_positive_int("event_id", self.event_id)
        if self.source not in (
            "totobrief",
            "provider",
            "operator_override",
            "unresolved",
        ):
            raise ValueError(
                "source must be totobrief, provider, operator_override, or unresolved"
            )
        if self.starts_at is not None:
            object.__setattr__(
                self,
                "starts_at",
                _require_utc_datetime("starts_at", self.starts_at),
            )
        if (self.source == "unresolved") != (self.starts_at is None):
            raise ValueError("source must be consistent with starts_at")


@dataclass(frozen=True)
class DrawingTimingSnapshot:
    drawing_id: int
    drawing_number: int | None
    target_fingerprint: str
    ended_at: datetime
    pinned_at: datetime
    events: tuple[EventTimingSnapshot, ...]
    validated_override_record: TimingOverrideRecord | None = None

    def __post_init__(self) -> None:
        _require_positive_int("drawing_id", self.drawing_id)
        if self.drawing_number is not None:
            _require_positive_int("drawing_number", self.drawing_number)
        _require_target_fingerprint(self.target_fingerprint)
        object.__setattr__(
            self,
            "ended_at",
            _require_utc_datetime("ended_at", self.ended_at),
        )
        object.__setattr__(
            self,
            "pinned_at",
            _require_utc_datetime("pinned_at", self.pinned_at),
        )
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        if len(self.events) != 15:
            raise ValueError("snapshot must contain exactly 15 events")
        if any(not isinstance(event, EventTimingSnapshot) for event in self.events):
            raise ValueError("events must contain EventTimingSnapshot records")
        if tuple(event.event_order for event in self.events) != _EVENT_ORDERS:
            raise ValueError("snapshot event orders 0 through 14 are required")
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("snapshot event_id values must be unique")
        if self.validated_override_record is not None:
            _require_validated_override_record(
                self.validated_override_record,
                self,
            )


@dataclass(frozen=True)
class TimingOverlayDiagnostic:
    code: DiagnosticCode
    message: str
    override_id: str | None = None
    event_order: int | None = None
    snapshot_event_id: int | None = None
    override_event_id: int | None = None

    def __post_init__(self) -> None:
        if self.code not in (
            "override_not_found",
            "target_fingerprint_mismatch",
            "ambiguous_override",
            "partial_override",
            "event_identity_mismatch",
            "event_start_before_drawing_end",
            "event_start_after_override_horizon",
            "reviewed_at_after_pin",
            "reviewed_at_before_review_window",
            "known_start_preserved",
            "unresolved_events_remain",
        ):
            raise ValueError("unsupported timing override diagnostic code")
        _require_canonical_text("message", self.message)
        if self.override_id is not None:
            _require_canonical_text("override_id", self.override_id)
        if self.event_order is not None:
            _require_event_order(self.event_order)
        if self.snapshot_event_id is not None:
            _require_positive_int("snapshot_event_id", self.snapshot_event_id)
        if self.override_event_id is not None:
            _require_positive_int("override_event_id", self.override_event_id)


@dataclass(frozen=True)
class TimingOverlayResult:
    snapshot: DrawingTimingSnapshot
    override_id: str | None
    applied_event_orders: tuple[int, ...]
    preserved_event_orders: tuple[int, ...]
    complete_overlay: bool
    diagnostics: tuple[TimingOverlayDiagnostic, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, DrawingTimingSnapshot):
            raise ValueError("snapshot must be a DrawingTimingSnapshot")
        if self.override_id is not None:
            _require_canonical_text("override_id", self.override_id)
        _require_order_tuple("applied_event_orders", self.applied_event_orders)
        _require_order_tuple("preserved_event_orders", self.preserved_event_orders)
        if set(self.applied_event_orders) & set(self.preserved_event_orders):
            raise ValueError("applied and preserved event orders must be disjoint")
        if not isinstance(self.complete_overlay, bool):
            raise ValueError("complete_overlay must be a boolean")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, TimingOverlayDiagnostic) for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain TimingOverlayDiagnostic values")
        if self.override_id is None and (
            self.applied_event_orders
            or self.preserved_event_orders
            or self.complete_overlay
        ):
            raise ValueError("an override_id is required for overlay results")
        if self.complete_overlay:
            if self.unresolved_event_orders:
                raise ValueError("a complete overlay cannot retain unresolved starts")
            if self.snapshot.validated_override_record is None:
                raise ValueError(
                    "a complete overlay requires one validated override record"
                )
            if (
                self.override_id
                != self.snapshot.validated_override_record.override_id
            ):
                raise ValueError(
                    "complete overlay override_id must match its validated record"
                )
            if any(item.code in _BLOCKING_DIAGNOSTICS for item in self.diagnostics):
                raise ValueError(
                    "a complete overlay cannot contain blocking diagnostics"
                )

    @property
    def unresolved_event_orders(self) -> tuple[int, ...]:
        return tuple(
            event.event_order
            for event in self.snapshot.events
            if event.starts_at is None
        )


def load_timing_override_catalog(path: str | Path) -> TimingOverrideCatalog:
    """Load one strict JSON catalog without retaining or mutating its payload."""

    try:
        payload = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_mapping_without_duplicate_fields,
        )
    except JSONDecodeError as error:
        raise ValueError("timing override catalog must be valid JSON") from error
    return parse_timing_override_catalog(payload)


def pin_timing_override_catalog(path: str | Path) -> PinnedTimingOverrideCatalog:
    """Strictly load and semantically hash one catalog at runner preflight."""

    catalog_path = Path(path)
    try:
        catalog = load_timing_override_catalog(catalog_path)
    except (OSError, ValueError) as error:
        return PinnedTimingOverrideCatalog(
            path=catalog_path,
            catalog=None,
            catalog_sha256=None,
            validation_error=f"strict catalog validation failed: {error}",
        )
    return PinnedTimingOverrideCatalog(
        path=catalog_path,
        catalog=catalog,
        catalog_sha256=timing_override_catalog_sha256(catalog),
        validation_error=None,
    )


def check_pinned_timing_override_catalog(
    pinned: PinnedTimingOverrideCatalog,
) -> TimingOverrideCatalogCheck:
    """Reload through the strict parser and compare semantic preflight content."""

    if not isinstance(pinned, PinnedTimingOverrideCatalog):
        raise ValueError("pinned must be a PinnedTimingOverrideCatalog")
    if not pinned.valid:
        return TimingOverrideCatalogCheck(
            catalog=None,
            observed_sha256=None,
            matches_preflight=False,
            validation_error=pinned.validation_error,
        )
    try:
        catalog = load_timing_override_catalog(pinned.path)
    except (OSError, ValueError) as error:
        return TimingOverrideCatalogCheck(
            catalog=None,
            observed_sha256=None,
            matches_preflight=False,
            validation_error=f"strict catalog validation failed: {error}",
        )
    observed_sha256 = timing_override_catalog_sha256(catalog)
    return TimingOverrideCatalogCheck(
        catalog=catalog,
        observed_sha256=observed_sha256,
        matches_preflight=observed_sha256 == pinned.catalog_sha256,
        validation_error=None,
    )


def parse_timing_override_catalog(payload: object) -> TimingOverrideCatalog:
    """Validate an already supplied JSON-compatible timing override catalog."""

    root = _require_exact_mapping(payload, _ROOT_FIELDS, "catalog")
    raw_records = root["overrides"]
    if not isinstance(raw_records, list):
        raise ValueError("catalog overrides must be a list")
    return TimingOverrideCatalog(
        records=tuple(_parse_override_record(item) for item in raw_records)
    )


def canonical_timing_override_catalog_bytes(
    catalog: TimingOverrideCatalog,
) -> bytes:
    """Return the canonical semantic catalog representation used for hashing."""

    if not isinstance(catalog, TimingOverrideCatalog):
        raise ValueError("catalog must be a TimingOverrideCatalog")
    payload = {
        "overrides": [
            _canonical_override_record(record) for record in catalog.records
        ]
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def timing_override_catalog_sha256(catalog: TimingOverrideCatalog) -> str:
    """Hash canonical validated content for later preflight/TOCTOU binding."""

    return hashlib.sha256(canonical_timing_override_catalog_bytes(catalog)).hexdigest()


def drawing_timing_snapshot_from_collection(
    collection: object,
) -> DrawingTimingSnapshot:
    """Project an immutable raw collection into the strict overlay boundary."""

    from toto_ai.external_odds.collection import ExternalCollectionSnapshot

    if not isinstance(collection, ExternalCollectionSnapshot):
        raise ValueError("collection must be an ExternalCollectionSnapshot")
    events: list[EventTimingSnapshot] = []
    for event in collection.events:
        if event.effective_start_source not in (
            "totobrief",
            "provider",
            "unresolved",
        ):
            raise ValueError("raw collection timing source is invalid")
        starts_at = (
            None
            if event.effective_starts_at is None
            else _parse_canonical_utc_datetime(
                "effective_starts_at",
                event.effective_starts_at,
            )
        )
        events.append(
            EventTimingSnapshot(
                event_order=event.event_order,
                event_id=event.target_event_id,
                starts_at=starts_at,
                source=event.effective_start_source,
            )
        )
    return DrawingTimingSnapshot(
        drawing_id=collection.drawing_id,
        drawing_number=collection.drawing_number,
        target_fingerprint=collection.target_fingerprint,
        ended_at=_parse_canonical_utc_datetime(
            "deadline",
            collection.deadline,
        ),
        pinned_at=_parse_canonical_utc_datetime(
            "target_fetched_at",
            collection.target_fetched_at,
        ),
        events=tuple(events),
    )


def classify_timing_snapshot(
    snapshot: DrawingTimingSnapshot,
) -> TimingSnapshotSummary:
    """Classify raw or overlaid starts with separate source accounting."""

    if not isinstance(snapshot, DrawingTimingSnapshot):
        raise ValueError("snapshot must be a DrawingTimingSnapshot")
    known = tuple(event for event in snapshot.events if event.starts_at is not None)
    known_times = tuple(event.starts_at for event in known)
    local_dates = tuple(value.astimezone(_MOSCOW).date() for value in known_times)
    if known_times:
        earliest_start = min(known_times)
        latest_start = max(known_times)
        span_days = (max(local_dates) - min(local_dates)).days + 1
    else:
        earliest_start = None
        latest_start = None
        span_days = 0
    missing_event_orders = tuple(
        event.event_order for event in snapshot.events if event.starts_at is None
    )
    status: Literal["playable", "multi_day", "unknown"]
    if span_days > 2:
        status = "multi_day"
    elif missing_event_orders:
        status = "unknown"
    else:
        status = "playable"
    return TimingSnapshotSummary(
        status=status,
        earliest_start=earliest_start,
        latest_start=latest_start,
        span_days=span_days,
        missing_event_orders=missing_event_orders,
        totobrief_count=sum(event.source == "totobrief" for event in snapshot.events),
        provider_count=sum(event.source == "provider" for event in snapshot.events),
        operator_override_count=sum(
            event.source == "operator_override" for event in snapshot.events
        ),
        validated_override_record=snapshot.validated_override_record,
    )


def overlay_timing_override(
    snapshot: DrawingTimingSnapshot,
    catalog: TimingOverrideCatalog,
) -> TimingOverlayResult:
    """Purely overlay one exact reviewed record without classifying eligibility.

    Partial records are useful diagnostics and may fill matching unresolved
    entries, but ``complete_overlay`` remains false. Callers must not perform an
    eligibility classification unless they separately require a complete overlay.
    """

    if not isinstance(snapshot, DrawingTimingSnapshot):
        raise ValueError("snapshot must be a DrawingTimingSnapshot")
    if not isinstance(catalog, TimingOverrideCatalog):
        raise ValueError("catalog must be a TimingOverrideCatalog")

    identity_matches = tuple(
        record for record in catalog.records if _matches_drawing(record, snapshot)
    )
    if not identity_matches:
        return _unchanged_result(
            snapshot,
            TimingOverlayDiagnostic(
                code="override_not_found",
                message="no override matches the exact drawing identity",
            ),
        )

    fingerprint_matches = tuple(
        record
        for record in identity_matches
        if record.target_fingerprint == snapshot.target_fingerprint
    )
    if not fingerprint_matches:
        diagnostics = tuple(
            TimingOverlayDiagnostic(
                code="target_fingerprint_mismatch",
                message="override target_fingerprint does not match the snapshot",
                override_id=record.override_id,
            )
            for record in identity_matches
        )
        return TimingOverlayResult(
            snapshot=snapshot,
            override_id=None,
            applied_event_orders=(),
            preserved_event_orders=(),
            complete_overlay=False,
            diagnostics=diagnostics,
        )
    if len(fingerprint_matches) != 1:
        return _unchanged_result(
            snapshot,
            TimingOverlayDiagnostic(
                code="ambiguous_override",
                message="multiple overrides match the exact drawing and fingerprint",
            ),
        )

    record = fingerprint_matches[0]
    snapshot_by_order = {event.event_order: event for event in snapshot.events}
    mismatches = tuple(
        (event, snapshot_by_order[event.event_order])
        for event in record.events
        if event.event_id != snapshot_by_order[event.event_order].event_id
    )
    if mismatches:
        diagnostics = tuple(
            TimingOverlayDiagnostic(
                code="event_identity_mismatch",
                message="override event_id does not match the snapshot event order",
                override_id=record.override_id,
                event_order=override_event.event_order,
                snapshot_event_id=snapshot_event.event_id,
                override_event_id=override_event.event_id,
            )
            for override_event, snapshot_event in mismatches
        )
        return TimingOverlayResult(
            snapshot=snapshot,
            override_id=record.override_id,
            applied_event_orders=(),
            preserved_event_orders=(),
            complete_overlay=False,
            diagnostics=diagnostics,
        )

    admissibility_diagnostics = _override_admissibility_diagnostics(
        record,
        snapshot,
    )
    if admissibility_diagnostics:
        return TimingOverlayResult(
            snapshot=snapshot,
            override_id=record.override_id,
            applied_event_orders=(),
            preserved_event_orders=(),
            complete_overlay=False,
            diagnostics=admissibility_diagnostics,
        )

    diagnostics: list[TimingOverlayDiagnostic] = []
    if not record.is_complete:
        diagnostics.append(
            TimingOverlayDiagnostic(
                code="partial_override",
                message="override does not contain all event orders 0 through 14",
                override_id=record.override_id,
            )
        )

    output_events = list(snapshot.events)
    applied_orders: list[int] = []
    preserved_orders: list[int] = []
    for override_event in record.events:
        current = snapshot_by_order[override_event.event_order]
        if current.starts_at is not None:
            preserved_orders.append(current.event_order)
            diagnostics.append(
                TimingOverlayDiagnostic(
                    code="known_start_preserved",
                    message="known TotoBrief or provider start was preserved",
                    override_id=record.override_id,
                    event_order=current.event_order,
                    snapshot_event_id=current.event_id,
                    override_event_id=override_event.event_id,
                )
            )
            continue
        output_events[current.event_order] = replace(
            current,
            starts_at=override_event.starts_at,
            source="operator_override",
        )
        applied_orders.append(current.event_order)

    output_snapshot = replace(
        snapshot,
        events=tuple(output_events),
        validated_override_record=record if record.is_complete else None,
    )
    unresolved_orders = tuple(
        event.event_order
        for event in output_snapshot.events
        if event.starts_at is None
    )
    if unresolved_orders:
        diagnostics.append(
            TimingOverlayDiagnostic(
                code="unresolved_events_remain",
                message="one or more event starts remain unresolved after overlay",
                override_id=record.override_id,
            )
        )

    return TimingOverlayResult(
        snapshot=output_snapshot,
        override_id=record.override_id,
        applied_event_orders=tuple(applied_orders),
        preserved_event_orders=tuple(preserved_orders),
        complete_overlay=record.is_complete and not unresolved_orders,
        diagnostics=tuple(diagnostics),
    )


def _override_admissibility_diagnostics(
    record: TimingOverrideRecord,
    snapshot: DrawingTimingSnapshot,
) -> tuple[TimingOverlayDiagnostic, ...]:
    diagnostics: list[TimingOverlayDiagnostic] = []
    if record.reviewed_at > snapshot.pinned_at:
        diagnostics.append(
            TimingOverlayDiagnostic(
                code="reviewed_at_after_pin",
                message=(
                    "override reviewed_at is later than the pinned target time"
                ),
                override_id=record.override_id,
            )
        )
    if record.reviewed_at < snapshot.ended_at - _MAX_REVIEW_LEAD:
        diagnostics.append(
            TimingOverlayDiagnostic(
                code="reviewed_at_before_review_window",
                message=(
                    "override reviewed_at is more than seven days before "
                    "drawing ended_at"
                ),
                override_id=record.override_id,
            )
        )

    latest_admissible_start = snapshot.ended_at + _MAX_OVERRIDE_HORIZON
    for event in record.events:
        if event.starts_at < snapshot.ended_at:
            diagnostics.append(
                TimingOverlayDiagnostic(
                    code="event_start_before_drawing_end",
                    message=(
                        "override event start is before drawing ended_at"
                    ),
                    override_id=record.override_id,
                    event_order=event.event_order,
                    snapshot_event_id=snapshot.events[event.event_order].event_id,
                    override_event_id=event.event_id,
                )
            )
        elif event.starts_at > latest_admissible_start:
            diagnostics.append(
                TimingOverlayDiagnostic(
                    code="event_start_after_override_horizon",
                    message=(
                        "override event start is later than drawing ended_at "
                        "plus five days"
                    ),
                    override_id=record.override_id,
                    event_order=event.event_order,
                    snapshot_event_id=snapshot.events[event.event_order].event_id,
                    override_event_id=event.event_id,
                )
            )
    return tuple(diagnostics)


def _require_validated_override_record(
    record: object,
    snapshot: DrawingTimingSnapshot,
) -> None:
    if not isinstance(record, TimingOverrideRecord):
        raise ValueError(
            "validated_override_record must be a TimingOverrideRecord"
        )
    if not record.is_complete:
        raise ValueError("validated override record must be complete")
    if not _matches_drawing(record, snapshot):
        raise ValueError("validated override record drawing identity mismatch")
    if record.target_fingerprint != snapshot.target_fingerprint:
        raise ValueError("validated override record fingerprint mismatch")
    record_by_order = {event.event_order: event for event in record.events}
    if any(
        record_by_order[event.event_order].event_id != event.event_id
        for event in snapshot.events
    ):
        raise ValueError("validated override record event identity mismatch")
    diagnostics = _override_admissibility_diagnostics(record, snapshot)
    if diagnostics:
        codes = ", ".join(item.code for item in diagnostics)
        raise ValueError(f"validated override record is inadmissible: {codes}")
    if any(event.starts_at is None for event in snapshot.events):
        raise ValueError("validated override snapshot must resolve all event starts")
    for event in snapshot.events:
        if (
            event.source == "operator_override"
            and event.starts_at != record_by_order[event.event_order].starts_at
        ):
            raise ValueError(
                "operator override start must match the validated record"
            )


def _parse_override_record(value: object) -> TimingOverrideRecord:
    mapping = _require_mapping(value, "override record")
    identity_fields = frozenset(mapping) & frozenset(
        ("drawing_id", "drawing_number")
    )
    if len(identity_fields) != 1:
        raise ValueError(
            "override record must contain exactly one drawing identity field"
        )
    identity_field = next(iter(identity_fields))
    expected_fields = _RECORD_COMMON_FIELDS | {identity_field}
    _require_exact_fields(mapping, expected_fields, "override record")

    raw_events = mapping["events"]
    if not isinstance(raw_events, list):
        raise ValueError("override events must be a list")
    return TimingOverrideRecord(
        schema_version=mapping["schema_version"],
        override_id=mapping["override_id"],
        drawing_id=(
            mapping["drawing_id"] if identity_field == "drawing_id" else None
        ),
        drawing_number=(
            mapping["drawing_number"]
            if identity_field == "drawing_number"
            else None
        ),
        target_fingerprint=mapping["target_fingerprint"],
        reviewer=mapping["reviewer"],
        reviewed_at=_parse_canonical_utc_datetime(
            "reviewed_at", mapping["reviewed_at"]
        ),
        source_ref=mapping["source_ref"],
        events=tuple(_parse_override_event(item) for item in raw_events),
    )


def _parse_override_event(value: object) -> TimingOverrideEvent:
    mapping = _require_mapping(value, "override event")
    if set(mapping) not in (_EVENT_FIELDS, _EVENT_FIELDS_WITH_SOURCE):
        raise ValueError("override event must use the exact schema")
    return TimingOverrideEvent(
        event_order=mapping["event_order"],
        event_id=mapping["event_id"],
        starts_at=_parse_canonical_utc_datetime("starts_at", mapping["starts_at"]),
        source_ref=mapping.get("source_ref"),
    )


def _canonical_override_record(record: TimingOverrideRecord) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": record.schema_version,
        "override_id": record.override_id,
        "target_fingerprint": record.target_fingerprint,
        "reviewer": record.reviewer,
        "reviewed_at": _canonical_utc_datetime(record.reviewed_at),
        "source_ref": record.source_ref,
        "events": [
            {
                "event_order": event.event_order,
                "event_id": event.event_id,
                "starts_at": _canonical_utc_datetime(event.starts_at),
                **(
                    {"source_ref": event.source_ref}
                    if event.source_ref is not None
                    else {}
                ),
            }
            for event in record.events
        ],
    }
    if record.drawing_id is not None:
        payload["drawing_id"] = record.drawing_id
    else:
        payload["drawing_number"] = record.drawing_number
    return payload


def _matches_drawing(
    record: TimingOverrideRecord,
    snapshot: DrawingTimingSnapshot,
) -> bool:
    if record.drawing_id is not None:
        return record.drawing_id == snapshot.drawing_id
    return record.drawing_number == snapshot.drawing_number


def _record_target_key(record: TimingOverrideRecord) -> tuple[object, ...]:
    return (
        "drawing_id" if record.drawing_id is not None else "drawing_number",
        record.drawing_id if record.drawing_id is not None else record.drawing_number,
        record.target_fingerprint,
    )


def _unchanged_result(
    snapshot: DrawingTimingSnapshot,
    diagnostic: TimingOverlayDiagnostic,
) -> TimingOverlayResult:
    return TimingOverlayResult(
        snapshot=snapshot,
        override_id=None,
        applied_event_orders=(),
        preserved_event_orders=(),
        complete_overlay=False,
        diagnostics=(diagnostic,),
    )


def _mapping_without_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_exact_mapping(
    value: object,
    fields: frozenset[str],
    name: str,
) -> Mapping[str, object]:
    mapping = _require_mapping(value, name)
    _require_exact_fields(mapping, fields, name)
    return mapping


def _require_exact_fields(
    mapping: Mapping[str, object],
    fields: frozenset[str],
    name: str,
) -> None:
    if set(mapping) != fields:
        raise ValueError(f"{name} must use the exact schema")


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_event_order(value: object) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value not in _EVENT_ORDERS
    ):
        raise ValueError("event_order must be in range 0 through 14")


def _require_order_tuple(name: str, value: object) -> None:
    if (
        not isinstance(value, tuple)
        or any(
            not isinstance(order, int)
            or isinstance(order, bool)
            or order not in _EVENT_ORDERS
            for order in value
        )
        or value != tuple(sorted(value))
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{name} must be an ordered tuple of unique event orders")


def _require_canonical_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty canonical text")


def _require_target_fingerprint(value: object) -> None:
    if not isinstance(value, str) or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError("target_fingerprint must be a lowercase SHA-256 hex digest")


def _require_utc_datetime(name: str, value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _parse_canonical_utc_datetime(name: str, value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a canonical timezone-aware UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"{name} must be a canonical timezone-aware UTC timestamp"
        ) from error
    parsed = _require_utc_datetime(name, parsed)
    if value != _canonical_utc_datetime(parsed):
        raise ValueError(f"{name} must use canonical UTC ISO format with +00:00")
    return parsed


def _canonical_utc_datetime(value: datetime) -> str:
    return _require_utc_datetime("timestamp", value).isoformat()


def _moscow_calendar_span(earliest: datetime, latest: datetime) -> int:
    return (
        latest.astimezone(_MOSCOW).date()
        - earliest.astimezone(_MOSCOW).date()
    ).days + 1
