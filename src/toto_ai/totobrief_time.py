"""TotoBrief community-specific wall-clock timestamp semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BALTBET_COMMUNITY = "baltbet-main"
MOSCOW = ZoneInfo("Europe/Moscow")


def parse_totobrief_timestamp(
    value: object,
    *,
    community: str | None,
    field_name: str,
) -> datetime:
    """Parse a TotoBrief timestamp into canonical UTC.

    BaltBet publishes drawing wall-clock timestamps in Moscow time even when
    TotoBrief serializes them with ``Z``/UTC-looking offsets.  Preserve that
    source contract by interpreting the displayed date and clock as
    ``Europe/Moscow``.  Other communities keep ordinary ISO offset semantics.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO timestamp")
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if community == BALTBET_COMMUNITY:
        moscow_wall_clock = parsed.replace(tzinfo=None).replace(tzinfo=MOSCOW)
        return moscow_wall_clock.astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)

