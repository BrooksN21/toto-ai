from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

EventStartSource = Literal["totobrief", "provider", "unresolved"]
EligibilityStatus = Literal["playable", "multi_day", "unknown"]
_MOSCOW = ZoneInfo("Europe/Moscow")
_EVENT_ORDERS = tuple(range(15))


@dataclass(frozen=True)
class EffectiveEventStart:
    event_order: int
    starts_at: datetime | None
    source: EventStartSource

    def __post_init__(self) -> None:
        if (
            not isinstance(self.event_order, int)
            or isinstance(self.event_order, bool)
            or self.event_order not in _EVENT_ORDERS
        ):
            raise ValueError("event_order must be in range 0 through 14")
        if self.source not in ("totobrief", "provider", "unresolved"):
            raise ValueError("source must be totobrief, provider, or unresolved")
        if self.starts_at is not None:
            _require_aware_datetime("starts_at", self.starts_at)
        if (self.source == "unresolved") != (self.starts_at is None):
            raise ValueError("source must be consistent with starts_at")


@dataclass(frozen=True)
class DrawingEligibility:
    status: EligibilityStatus
    earliest_start: datetime | None
    latest_start: datetime | None
    span_days: int
    missing_event_orders: tuple[int, ...]
    totobrief_count: int
    provider_count: int

    def __post_init__(self) -> None:
        if self.status not in ("playable", "multi_day", "unknown"):
            raise ValueError("status must be playable, multi_day, or unknown")
        if self.earliest_start is not None:
            _require_aware_datetime("earliest_start", self.earliest_start)
        if self.latest_start is not None:
            _require_aware_datetime("latest_start", self.latest_start)
        if (
            not isinstance(self.span_days, int)
            or isinstance(self.span_days, bool)
            or self.span_days < 0
        ):
            raise ValueError("span_days must be a non-negative integer")
        if (
            not isinstance(self.missing_event_orders, tuple)
            or any(
                not isinstance(order, int) or isinstance(order, bool)
                for order in self.missing_event_orders
            )
            or self.missing_event_orders != tuple(sorted(self.missing_event_orders))
            or len(set(self.missing_event_orders)) != len(self.missing_event_orders)
            or any(order not in _EVENT_ORDERS for order in self.missing_event_orders)
        ):
            raise ValueError(
                "missing_event_orders must be an ordered tuple of event orders"
            )
        for name, value in (
            ("totobrief_count", self.totobrief_count),
            ("provider_count", self.provider_count),
        ):
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 0 <= value <= 15
            ):
                raise ValueError(f"{name} must be an integer from 0 through 15")

        known_count = 15 - len(self.missing_event_orders)
        if self.totobrief_count + self.provider_count != known_count:
            raise ValueError(
                "missing_event_orders and source counts are inconsistent"
            )

        if known_count == 0:
            if self.earliest_start is not None:
                raise ValueError("earliest_start must be absent without known starts")
            if self.latest_start is not None:
                raise ValueError("latest_start must be absent without known starts")
            expected_span_days = 0
        else:
            if self.earliest_start is None:
                raise ValueError("earliest_start must be present with known starts")
            if self.latest_start is None:
                raise ValueError("latest_start must be present with known starts")
            if self.earliest_start > self.latest_start:
                raise ValueError("earliest_start must not be after latest_start")
            expected_span_days = _calendar_span_days(
                self.earliest_start, self.latest_start
            )

        if self.span_days != expected_span_days:
            raise ValueError(
                "span_days is inconsistent with earliest_start and latest_start"
            )

        expected_status: EligibilityStatus
        if self.span_days > 2:
            expected_status = "multi_day"
        elif known_count < 15:
            expected_status = "unknown"
        else:
            expected_status = "playable"
        if self.status != expected_status:
            raise ValueError(
                "status is inconsistent with span_days and missing_event_orders"
            )


def classify_drawing_eligibility(
    starts: Sequence[EffectiveEventStart],
) -> DrawingEligibility:
    items = tuple(starts)
    if len(items) != 15:
        raise ValueError("exactly 15 event starts are required")
    if any(not isinstance(item, EffectiveEventStart) for item in items):
        raise ValueError("starts must contain EffectiveEventStart records")
    if tuple(item.event_order for item in items) != _EVENT_ORDERS:
        raise ValueError("event orders 0 through 14 are required exactly once")

    known = tuple(item for item in items if item.starts_at is not None)
    known_times = tuple(item.starts_at for item in known)
    local_dates = tuple(value.astimezone(_MOSCOW).date() for value in known_times)
    if local_dates:
        earliest_start = min(known_times)
        latest_start = max(known_times)
        span_days = (max(local_dates) - min(local_dates)).days + 1
    else:
        earliest_start = None
        latest_start = None
        span_days = 0

    if span_days > 2:
        status: EligibilityStatus = "multi_day"
    elif len(known) < 15:
        status = "unknown"
    else:
        status = "playable"

    return DrawingEligibility(
        status=status,
        earliest_start=earliest_start,
        latest_start=latest_start,
        span_days=span_days,
        missing_event_orders=tuple(
            item.event_order for item in items if item.starts_at is None
        ),
        totobrief_count=sum(item.source == "totobrief" for item in items),
        provider_count=sum(item.source == "provider" for item in items),
    )


def target_fingerprint(
    drawing_id: int,
    drawing_number: int | None,
    deadline: datetime,
    events: Sequence[object],
) -> str:
    _require_positive_int("drawing_id", drawing_id)
    if drawing_number is not None:
        _require_positive_int("drawing_number", drawing_number)
    _require_aware_datetime("deadline", deadline)

    ordered_events = tuple(events)
    if len(ordered_events) != 15:
        raise ValueError("exactly 15 events are required")

    event_orders = tuple(_event_field(event, "event_order") for event in ordered_events)
    if set(event_orders) != set(_EVENT_ORDERS):
        raise ValueError("event orders 0 through 14 are required exactly once")

    canonical_events = []
    for expected_order, event in zip(
        _EVENT_ORDERS,
        sorted(ordered_events, key=lambda item: _event_field(item, "event_order")),
        strict=True,
    ):
        event_order = _event_field(event, "event_order")
        if event_order != expected_order:
            raise ValueError("event orders 0 through 14 are required exactly once")
        starts_at = _event_start(event)
        if starts_at is not None:
            _require_aware_datetime("event starts_at", starts_at)
        canonical_events.append(
            {
                "event_id": _event_field(event, "event_id"),
                "event_order": event_order,
                "home_team": _require_text(
                    _event_field(event, "home_team"), "home_team"
                ),
                "away_team": _require_text(
                    _event_field(event, "away_team"), "away_team"
                ),
                "starts_at": _canonical_datetime(starts_at),
            }
        )

    payload = {
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "deadline": _canonical_datetime(deadline),
        "events": canonical_events,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _event_field(event: object, name: str) -> object:
    if isinstance(event, Mapping):
        try:
            value = event[name]
        except KeyError as error:
            raise ValueError(f"event must contain {name}") from error
    else:
        try:
            value = getattr(event, name)
        except AttributeError as error:
            raise ValueError(f"event must contain {name}") from error
    if name == "event_id":
        _require_positive_int(name, value)
    elif name == "event_order":
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value not in _EVENT_ORDERS
        ):
            raise ValueError("event_order must be in range 0 through 14")
    return value


def _event_start(event: object) -> datetime | None:
    if isinstance(event, Mapping):
        value = event.get("starts_at", event.get("start_at"))
    else:
        value = getattr(event, "starts_at", getattr(event, "start_at", None))
    if value is not None and not isinstance(value, datetime):
        raise ValueError("event starts_at must be a datetime or None")
    return value


def _canonical_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def _calendar_span_days(earliest: datetime, latest: datetime) -> int:
    return (
        latest.astimezone(_MOSCOW).date()
        - earliest.astimezone(_MOSCOW).date()
    ).days + 1


def _require_aware_datetime(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be timezone-aware")


def _require_positive_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value
