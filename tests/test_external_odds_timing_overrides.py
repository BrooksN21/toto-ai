from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.external_odds.timing_overrides import (
    DrawingTimingSnapshot,
    EventTimingSnapshot,
    check_pinned_timing_override_catalog,
    load_timing_override_catalog,
    overlay_timing_override,
    parse_timing_override_catalog,
    pin_timing_override_catalog,
    timing_override_catalog_sha256,
)

UTC = timezone.utc
DRAWING_ID = 123
DRAWING_NUMBER = 456
FINGERPRINT = "a" * 64
DRAWING_ENDED_AT = datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
PINNED_AT = datetime(2026, 7, 20, 9, 15, tzinfo=UTC)


def _snapshot(
    *,
    known: dict[int, tuple[datetime, str]] | None = None,
    fingerprint: str = FINGERPRINT,
) -> DrawingTimingSnapshot:
    known = known or {}
    events = []
    for event_order in range(15):
        if event_order in known:
            starts_at, source = known[event_order]
        else:
            starts_at, source = None, "unresolved"
        events.append(
            EventTimingSnapshot(
                event_order=event_order,
                event_id=1000 + event_order,
                starts_at=starts_at,
                source=source,
            )
        )
    return DrawingTimingSnapshot(
        drawing_id=DRAWING_ID,
        drawing_number=DRAWING_NUMBER,
        target_fingerprint=fingerprint,
        ended_at=DRAWING_ENDED_AT,
        pinned_at=PINNED_AT,
        events=tuple(events),
    )


def _event(event_order: int) -> dict[str, object]:
    return {
        "event_order": event_order,
        "event_id": 1000 + event_order,
        "starts_at": (
            datetime(2026, 7, 20, 10, tzinfo=UTC)
            + timedelta(minutes=event_order)
        ).isoformat(),
    }


def _record(
    *,
    override_id: str = "drawing-123-reviewed-v1",
    fingerprint: str = FINGERPRINT,
    events: list[dict[str, object]] | None = None,
    drawing_identity: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "override_id": override_id,
        **(drawing_identity or {"drawing_id": DRAWING_ID}),
        "target_fingerprint": fingerprint,
        "reviewer": "operator@example.test",
        "reviewed_at": "2026-07-20T09:00:00+00:00",
        "source_ref": "operator-log:drawing-123",
        "events": events if events is not None else [_event(i) for i in range(15)],
    }


def _catalog(*records: dict[str, object]) -> dict[str, object]:
    return {"overrides": list(records)}


def test_valid_complete_overlay_is_pure_and_fills_only_snapshot_copy(tmp_path):
    payload = _catalog(_record())
    original_payload = copy.deepcopy(payload)
    path = tmp_path / "timing-overrides.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    snapshot = _snapshot()

    result = overlay_timing_override(
        snapshot,
        load_timing_override_catalog(path),
    )

    assert result.complete_overlay is True
    assert result.override_id == "drawing-123-reviewed-v1"
    assert result.applied_event_orders == tuple(range(15))
    assert result.preserved_event_orders == ()
    assert result.unresolved_event_orders == ()
    assert result.diagnostics == ()
    assert all(event.source == "operator_override" for event in result.snapshot.events)
    assert all(event.starts_at is None for event in snapshot.events)
    assert payload == original_payload


def test_partial_override_is_diagnostic_and_cannot_be_complete():
    result = overlay_timing_override(
        _snapshot(),
        parse_timing_override_catalog(_catalog(_record(events=[_event(0), _event(1)]))),
    )

    assert result.complete_overlay is False
    assert result.applied_event_orders == (0, 1)
    assert result.unresolved_event_orders == tuple(range(2, 15))
    assert [item.code for item in result.diagnostics] == [
        "partial_override",
        "unresolved_events_remain",
    ]


def test_partial_override_stays_incomplete_even_if_it_fills_last_unknown_start():
    known_time = datetime(2026, 7, 20, 8, tzinfo=UTC)
    snapshot = _snapshot(
        known={order: (known_time, "provider") for order in range(1, 15)}
    )

    result = overlay_timing_override(
        snapshot,
        parse_timing_override_catalog(_catalog(_record(events=[_event(0)]))),
    )

    assert result.unresolved_event_orders == ()
    assert result.complete_overlay is False
    assert [item.code for item in result.diagnostics] == ["partial_override"]


def test_known_totobrief_and_provider_times_are_never_replaced():
    totobrief_time = datetime(2026, 7, 20, 8, tzinfo=UTC)
    provider_time = datetime(2026, 7, 20, 9, tzinfo=UTC)
    snapshot = _snapshot(
        known={
            0: (totobrief_time, "totobrief"),
            1: (provider_time, "provider"),
        }
    )

    result = overlay_timing_override(
        snapshot,
        parse_timing_override_catalog(_catalog(_record())),
    )

    assert result.complete_overlay is True
    assert result.applied_event_orders == tuple(range(2, 15))
    assert result.preserved_event_orders == (0, 1)
    assert result.snapshot.events[0] == snapshot.events[0]
    assert result.snapshot.events[1] == snapshot.events[1]
    assert [item.code for item in result.diagnostics] == [
        "known_start_preserved",
        "known_start_preserved",
    ]


@pytest.mark.parametrize(
    ("starts_at", "expected_code"),
    (
        (
            datetime(2025, 7, 20, 10, tzinfo=UTC),
            "event_start_before_drawing_end",
        ),
        (
            datetime(2027, 7, 20, 10, tzinfo=UTC),
            "event_start_after_override_horizon",
        ),
        (
            DRAWING_ENDED_AT - timedelta(microseconds=1),
            "event_start_before_drawing_end",
        ),
        (
            DRAWING_ENDED_AT + timedelta(days=5, microseconds=1),
            "event_start_after_override_horizon",
        ),
    ),
)
def test_override_event_start_outside_pinned_drawing_window_fails_closed(
    starts_at,
    expected_code,
):
    snapshot = _snapshot()
    events = [_event(order) for order in range(15)]
    events[0]["starts_at"] = starts_at.isoformat()

    result = overlay_timing_override(
        snapshot,
        parse_timing_override_catalog(_catalog(_record(events=events))),
    )

    assert result.snapshot is snapshot
    assert result.complete_overlay is False
    assert result.applied_event_orders == ()
    assert [item.code for item in result.diagnostics] == [expected_code]


def test_override_event_start_window_boundaries_are_inclusive():
    events = [_event(order) for order in range(15)]
    events[0]["starts_at"] = DRAWING_ENDED_AT.isoformat()
    events[-1]["starts_at"] = (
        DRAWING_ENDED_AT + timedelta(days=5)
    ).isoformat()

    result = overlay_timing_override(
        _snapshot(),
        parse_timing_override_catalog(_catalog(_record(events=events))),
    )

    assert result.complete_overlay is True
    assert result.diagnostics == ()


@pytest.mark.parametrize(
    ("reviewed_at", "expected_code"),
    (
        (
            PINNED_AT + timedelta(microseconds=1),
            "reviewed_at_after_pin",
        ),
        (
            DRAWING_ENDED_AT - timedelta(days=7, microseconds=1),
            "reviewed_at_before_review_window",
        ),
    ),
)
def test_future_or_stale_review_timestamp_fails_closed(
    reviewed_at,
    expected_code,
):
    snapshot = _snapshot()
    record = _record()
    record["reviewed_at"] = reviewed_at.isoformat()

    result = overlay_timing_override(
        snapshot,
        parse_timing_override_catalog(_catalog(record)),
    )

    assert result.snapshot is snapshot
    assert result.complete_overlay is False
    assert result.applied_event_orders == ()
    assert [item.code for item in result.diagnostics] == [expected_code]


def test_drawing_number_identity_can_match_exact_snapshot():
    record = _record(drawing_identity={"drawing_number": DRAWING_NUMBER})

    result = overlay_timing_override(
        _snapshot(),
        parse_timing_override_catalog(_catalog(record)),
    )

    assert result.complete_overlay is True
    assert result.applied_event_orders == tuple(range(15))


def test_stale_target_fingerprint_leaves_snapshot_unchanged():
    snapshot = _snapshot()
    catalog = parse_timing_override_catalog(
        _catalog(_record(fingerprint="b" * 64))
    )

    result = overlay_timing_override(snapshot, catalog)

    assert result.snapshot is snapshot
    assert result.complete_overlay is False
    assert result.applied_event_orders == ()
    assert [item.code for item in result.diagnostics] == [
        "target_fingerprint_mismatch"
    ]


@pytest.mark.parametrize(
    "events",
    [
        [{**_event(0), "event_id": 9999}] + [_event(i) for i in range(1, 15)],
        [{**_event(0), "event_order": 1}, {**_event(1), "event_order": 0}]
        + [_event(i) for i in range(2, 15)],
    ],
)
def test_wrong_event_id_or_order_rejects_the_whole_override(events):
    snapshot = _snapshot()
    result = overlay_timing_override(
        snapshot,
        parse_timing_override_catalog(_catalog(_record(events=events))),
    )

    assert result.snapshot is snapshot
    assert result.complete_overlay is False
    assert result.applied_event_orders == ()
    assert {item.code for item in result.diagnostics} == {
        "event_identity_mismatch"
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("starts_at", "not-a-timestamp"),
        ("starts_at", "2026-07-20T13:00:00+03:00"),
        ("starts_at", "2026-07-20T10:00:00"),
        ("reviewed_at", "2026-07-20T12:00:00+03:00"),
    ],
)
def test_catalog_rejects_malformed_or_non_utc_timestamps(field, value):
    record = _record()
    if field == "reviewed_at":
        record[field] = value
    else:
        record["events"][0][field] = value

    with pytest.raises(ValueError, match="UTC|timestamp"):
        parse_timing_override_catalog(_catalog(record))


def test_catalog_rejects_duplicate_records_event_ids_and_orders():
    record = _record()
    with pytest.raises(ValueError, match="override_id"):
        parse_timing_override_catalog(_catalog(record, copy.deepcopy(record)))

    duplicate_event_id = _record()
    duplicate_event_id["events"][1]["event_id"] = 1000
    with pytest.raises(ValueError, match="event_id"):
        parse_timing_override_catalog(_catalog(duplicate_event_id))

    duplicate_order = _record()
    duplicate_order["events"][1]["event_order"] = 0
    with pytest.raises(ValueError, match="event_order"):
        parse_timing_override_catalog(_catalog(duplicate_order))


def test_catalog_rejects_unknown_fields_and_non_exact_identity():
    record = _record()
    record["unexpected"] = True
    with pytest.raises(ValueError, match="exact schema"):
        parse_timing_override_catalog(_catalog(record))

    both_identities = _record()
    both_identities["drawing_number"] = DRAWING_NUMBER
    with pytest.raises(ValueError, match="exactly one"):
        parse_timing_override_catalog(_catalog(both_identities))


def test_catalog_hash_is_deterministic_over_format_and_input_order(tmp_path):
    first_record = _record()
    second_record = _record(
        override_id="drawing-456-reviewed-v1",
        fingerprint="c" * 64,
        drawing_identity={"drawing_number": 999},
    )
    canonical_payload = _catalog(first_record, second_record)
    reordered_payload = {
        "overrides": [
            {
                **second_record,
                "events": list(reversed(second_record["events"])),
            },
            {
                **first_record,
                "events": list(reversed(first_record["events"])),
            },
        ]
    }
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_text(json.dumps(canonical_payload, indent=2), encoding="utf-8")
    second_path.write_text(
        json.dumps(reordered_payload, separators=(",", ":")),
        encoding="utf-8",
    )

    first_hash = timing_override_catalog_sha256(
        load_timing_override_catalog(first_path)
    )
    second_hash = timing_override_catalog_sha256(
        load_timing_override_catalog(second_path)
    )

    assert first_hash == second_hash
    changed = copy.deepcopy(canonical_payload)
    changed["overrides"][0]["events"][0]["starts_at"] = (
        "2026-07-20T11:00:00+00:00"
    )
    assert first_hash != timing_override_catalog_sha256(
        parse_timing_override_catalog(changed)
    )


def test_event_source_ref_is_optional_strict_and_part_of_semantic_hash():
    legacy = parse_timing_override_catalog(_catalog(_record()))
    assert all(event.source_ref is None for event in legacy.records[0].events)

    sourced_payload = _catalog(_record())
    sourced_payload["overrides"][0]["events"][1]["source_ref"] = (
        "offline-review:event-1"
    )
    sourced = parse_timing_override_catalog(sourced_payload)

    assert sourced.records[0].events[1].source_ref == "offline-review:event-1"
    assert timing_override_catalog_sha256(sourced) != (
        timing_override_catalog_sha256(legacy)
    )

    malformed = copy.deepcopy(sourced_payload)
    malformed["overrides"][0]["events"][1]["source_ref"] = " padded "
    with pytest.raises(ValueError, match="canonical text"):
        parse_timing_override_catalog(malformed)

    unknown_field = copy.deepcopy(sourced_payload)
    unknown_field["overrides"][0]["events"][1]["unexpected"] = True
    with pytest.raises(ValueError, match="exact schema"):
        parse_timing_override_catalog(unknown_field)


def test_pinned_catalog_reloads_strictly_and_detects_semantic_change(tmp_path):
    path = tmp_path / "timing-overrides.json"
    payload = _catalog(_record())
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    pinned = pin_timing_override_catalog(path)
    assert pinned.valid is True
    assert pinned.catalog_sha256 == timing_override_catalog_sha256(pinned.catalog)

    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    formatting_only = check_pinned_timing_override_catalog(pinned)
    assert formatting_only.matches_preflight is True
    assert formatting_only.observed_sha256 == pinned.catalog_sha256

    payload["overrides"][0]["events"][0]["starts_at"] = (
        "2026-07-20T11:00:00+00:00"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    changed = check_pinned_timing_override_catalog(pinned)
    assert changed.matches_preflight is False
    assert changed.catalog is not None
    assert changed.observed_sha256 != pinned.catalog_sha256


@pytest.mark.parametrize(
    "contents",
    (
        "{not-json",
        json.dumps({"overrides": [{"schema_version": 1}]}),
    ),
)
def test_invalid_catalog_pin_is_retained_as_fail_closed_diagnostic(
    tmp_path,
    contents,
):
    path = tmp_path / "timing-overrides.json"
    path.write_text(contents, encoding="utf-8")

    pinned = pin_timing_override_catalog(path)
    check = check_pinned_timing_override_catalog(pinned)

    assert pinned.valid is False
    assert pinned.catalog is None
    assert pinned.catalog_sha256 is None
    assert "strict catalog validation failed" in pinned.validation_error
    assert check.matches_preflight is False
    assert check.catalog is None
    assert check.observed_sha256 is None
