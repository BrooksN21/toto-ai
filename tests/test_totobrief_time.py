from datetime import datetime, timezone

import pytest

from toto_ai.totobrief_time import parse_totobrief_timestamp


def test_baltbet_timestamp_is_moscow_wall_clock_despite_z_suffix() -> None:
    assert parse_totobrief_timestamp(
        "2026-08-30T16:00:00.000000Z",
        community="baltbet-main",
        field_name="ended_at",
    ) == datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)


def test_other_totobrief_community_keeps_iso_offset_semantics() -> None:
    assert parse_totobrief_timestamp(
        "2026-08-30T16:00:00Z",
        community="other-toto",
        field_name="ended_at",
    ) == datetime(2026, 8, 30, 16, 0, tzinfo=timezone.utc)


def test_totobrief_timestamp_rejects_naive_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_totobrief_timestamp(
            "2026-08-30T16:00:00",
            community="baltbet-main",
            field_name="ended_at",
        )
