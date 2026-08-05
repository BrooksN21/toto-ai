from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from toto_ai.external_odds.eligibility import (
    DrawingEligibility,
    EffectiveEventStart,
    classify_drawing_eligibility,
    target_fingerprint,
)

UTC = timezone.utc


def _starts(
    timestamps: list[datetime | None],
    *,
    provider_orders: set[int] | None = None,
) -> tuple[EffectiveEventStart, ...]:
    provider_orders = provider_orders or set()
    return tuple(
        EffectiveEventStart(
            event_order=event_order,
            starts_at=starts_at,
            source=(
                "unresolved"
                if starts_at is None
                else "provider"
                if event_order in provider_orders
                else "totobrief"
            ),
        )
        for event_order, starts_at in enumerate(timestamps)
    )


def _event(event_order: int, *, starts_at: datetime | None = None):
    return SimpleNamespace(
        event_id=1000 + event_order,
        event_order=event_order,
        home_team=f"Home {event_order}",
        away_team=f"Away {event_order}",
        starts_at=starts_at,
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_exactly_15_ordered_starts_are_playable_across_two_moscow_dates():
    timestamps = [
        datetime(2026, 1, 1, 21, tzinfo=UTC) + timedelta(minutes=event_order)
        for event_order in range(7)
    ] + [
        datetime(2026, 1, 2, 21, tzinfo=UTC) + timedelta(minutes=event_order)
        for event_order in range(8)
    ]

    result = classify_drawing_eligibility(_starts(timestamps))

    assert result.status == "playable"
    assert result.earliest_start == timestamps[0]
    assert result.latest_start == timestamps[-1]
    assert result.span_days == 2
    assert result.missing_event_orders == ()
    assert result.totobrief_count == 15
    assert result.provider_count == 0


def test_span_uses_moscow_calendar_dates_at_utc_midnight_boundary():
    timestamps = [
        datetime(2026, 1, 1, 21, tzinfo=UTC),
        datetime(2026, 1, 2, 20, 59, tzinfo=UTC),
    ] + [datetime(2026, 1, 2, 20, tzinfo=UTC)] * 13

    result = classify_drawing_eligibility(_starts(timestamps))

    assert result.status == "playable"
    assert result.span_days == 1


def test_known_dates_separated_by_a_gap_are_multi_day():
    timestamps = [datetime(2026, 1, 1, 21, tzinfo=UTC)] * 14
    timestamps.append(datetime(2026, 1, 3, 21, tzinfo=UTC))

    result = classify_drawing_eligibility(_starts(timestamps))

    assert result.status == "multi_day"
    assert result.span_days == 3


def test_multi_day_known_subset_takes_priority_over_unresolved_events():
    timestamps = [datetime(2026, 1, 1, 21, tzinfo=UTC)] * 13
    timestamps.extend([None, datetime(2026, 1, 3, 21, tzinfo=UTC)])

    result = classify_drawing_eligibility(_starts(timestamps))

    assert result.status == "multi_day"
    assert result.span_days == 3
    assert result.missing_event_orders == (13,)


def test_unresolved_events_inside_a_two_day_span_are_unknown():
    timestamps = [datetime(2026, 1, 1, 21, tzinfo=UTC)] * 6
    timestamps.extend([datetime(2026, 1, 2, 21, tzinfo=UTC)] * 7)
    timestamps.extend([None, None])

    result = classify_drawing_eligibility(
        _starts(timestamps, provider_orders=set(range(6, 13)))
    )

    assert result.status == "unknown"
    assert result.span_days == 2
    assert result.missing_event_orders == (13, 14)
    assert result.totobrief_count == 6
    assert result.provider_count == 7


@pytest.mark.parametrize(
    "starts, message",
    [
        (
            tuple(
                EffectiveEventStart(
                    event_order=event_order,
                    starts_at=datetime(2026, 1, 1, tzinfo=UTC),
                    source="totobrief",
                )
                for event_order in list(range(14)) + [13]
            ),
            "orders",
        ),
        (
            tuple(
                EffectiveEventStart(
                    event_order=event_order,
                    starts_at=datetime(2026, 1, 1, tzinfo=UTC),
                    source="totobrief",
                )
                for event_order in range(14)
            ),
            "15",
        ),
    ],
)
def test_classifier_rejects_duplicate_or_missing_event_orders(starts, message):
    with pytest.raises(ValueError, match=message):
        classify_drawing_eligibility(starts)


def test_effective_start_rejects_naive_timestamp_and_inconsistent_source():
    with pytest.raises(ValueError, match="timezone-aware"):
        EffectiveEventStart(
            event_order=0,
            starts_at=datetime(2026, 1, 1),
            source="totobrief",
        )

    with pytest.raises(ValueError, match="source"):
        EffectiveEventStart(
            event_order=0,
            starts_at=None,
            source="provider",
        )


def _playable_eligibility() -> DrawingEligibility:
    return DrawingEligibility(
        status="playable",
        earliest_start=datetime(2026, 1, 1, 21, tzinfo=UTC),
        latest_start=datetime(2026, 1, 2, 21, tzinfo=UTC),
        span_days=2,
        missing_event_orders=(),
        totobrief_count=15,
        provider_count=0,
    )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"status": "unknown"}, "status"),
        ({"span_days": 1}, "span_days"),
        ({"missing_event_orders": (14,)}, "missing"),
        ({"totobrief_count": 14}, "source counts"),
        ({"earliest_start": None}, "earliest_start"),
        ({"latest_start": None}, "latest_start"),
        (
            {
                "earliest_start": datetime(2026, 1, 3, 21, tzinfo=UTC),
                "latest_start": datetime(2026, 1, 2, 21, tzinfo=UTC),
            },
            "earliest_start",
        ),
    ],
)
def test_drawing_eligibility_rejects_contradictory_construction(changes, message):
    values = _playable_eligibility().__dict__ | changes

    with pytest.raises(ValueError, match=message):
        DrawingEligibility(**values)


def test_fingerprint_is_deterministic_binds_target_fields_and_excludes_fetch_time():
    events = tuple(
        _event(
            event_order,
            starts_at=datetime(2026, 1, 1, 21, tzinfo=UTC)
            + timedelta(minutes=event_order),
        )
        for event_order in range(15)
    )
    deadline = datetime(2026, 1, 2, 15, tzinfo=UTC)

    first = target_fingerprint(123, 456, deadline, events)
    second = target_fingerprint(123, 456, deadline, events)
    fetched_later = tuple(
        SimpleNamespace(**{**event.__dict__, "fetched_at": deadline})
        for event in events
    )

    assert first == second == target_fingerprint(123, 456, deadline, fetched_later)
    assert first != target_fingerprint(124, 456, deadline, events)
    assert first != target_fingerprint(123, 457, deadline, events)
    assert first != target_fingerprint(
        123, 456, deadline + timedelta(seconds=1), events
    )
    changed_event = tuple(_event(event_order) for event_order in range(15))
    assert first != target_fingerprint(123, 456, deadline, changed_event)


@pytest.mark.parametrize(
    "field, value",
    [
        ("event_id", 9000),
        ("home_team", "Changed Home"),
        ("away_team", "Changed Away"),
    ],
)
def test_target_fingerprint_changes_for_each_event_identity_field(field, value):
    events = tuple(_event(event_order) for event_order in range(15))
    deadline = datetime(2026, 1, 2, 15, tzinfo=UTC)
    changed = list(events)
    changed[0] = SimpleNamespace(
        **{**events[0].__dict__, field: value}
    )

    assert target_fingerprint(123, 456, deadline, changed) != target_fingerprint(
        123, 456, deadline, events
    )


def test_target_fingerprint_changes_when_event_orders_change():
    events = tuple(_event(event_order) for event_order in range(15))
    deadline = datetime(2026, 1, 2, 15, tzinfo=UTC)
    changed = list(events)
    changed[0] = SimpleNamespace(**{**events[0].__dict__, "event_order": 1})
    changed[1] = SimpleNamespace(**{**events[1].__dict__, "event_order": 0})

    assert target_fingerprint(123, 456, deadline, changed) != target_fingerprint(
        123, 456, deadline, events
    )
