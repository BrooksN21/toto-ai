from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from math import isfinite

from toto_ai.external_odds.domain import (
    OutcomeTriplet,
    Sport,
    TargetDrawing,
    TargetEvent,
)

HOCKEY_CHAMPIONSHIP_TOKENS = (
    "кхл",
    "вхл",
    "мхл",
    "nhl",
    "ahl",
    "shl",
    "liiga",
    "del",
    "hockey",
    "хоккей",
)
_TEAM_SEPARATORS = ("—", "–", " - ")


def classify_sport(championship: str, explicit_sport: object) -> Sport:
    explicit = str(explicit_sport or "").strip().casefold()
    if explicit in {"football", "футбол", "soccer"}:
        return "football"
    if explicit in {"hockey", "хоккей", "ice hockey"}:
        return "hockey"

    normalized = unicodedata.normalize("NFKC", championship).casefold()
    if any(token in normalized for token in HOCKEY_CHAMPIONSHIP_TOKENS):
        return "hockey"
    if championship.strip():
        return "football"
    return "unknown"


def parse_target_drawing(
    payload: Mapping[str, object], fetched_at: datetime | str
) -> TargetDrawing:
    data = _require_mapping(payload.get("data"), "payload data")
    drawing_id = _require_positive_int(data.get("id"), "drawing id")
    drawing_number = _optional_positive_int(data.get("number"), "drawing number")
    deadline = _parse_utc_datetime(data.get("ended_at"), "ended_at")
    resolved_fetched_at = _parse_utc_datetime(fetched_at, "fetched_at")
    raw_events = data.get("events")
    if not isinstance(raw_events, list) or len(raw_events) != 15:
        raise ValueError("drawing must contain exactly 15 events")

    events = tuple(
        sorted(
            (
                _parse_target_event(
                    _require_mapping(raw_event, "event"),
                    drawing_id=drawing_id,
                    drawing_number=drawing_number,
                    deadline=deadline,
                )
                for raw_event in raw_events
            ),
            key=lambda event: event.event_order,
        )
    )
    return TargetDrawing(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        deadline=deadline,
        fetched_at=resolved_fetched_at,
        events=events,
    )


def _parse_target_event(
    raw_event: Mapping[str, object],
    *,
    drawing_id: int,
    drawing_number: int | None,
    deadline: datetime,
) -> TargetEvent:
    championship = _require_text(raw_event.get("championship"), "championship")
    home_team, away_team = _split_teams(
        _require_text(raw_event.get("name"), "name"), "name"
    )
    name_en = raw_event.get("name_en")
    home_team_en, away_team_en = (
        _split_teams(_require_text(name_en, "name_en"), "name_en")
        if name_en is not None
        else (None, None)
    )
    return TargetEvent(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        event_id=_require_positive_int(raw_event.get("id"), "event id"),
        event_order=_require_event_order(raw_event.get("order")),
        sport=classify_sport(championship, raw_event.get("sport")),
        championship=championship,
        starts_at=_parse_utc_datetime(raw_event.get("start_at"), "start_at"),
        deadline=deadline,
        home_team=home_team,
        away_team=away_team,
        home_team_en=home_team_en,
        away_team_en=away_team_en,
        bk_probabilities=_normalized_bk_probabilities(raw_event.get("quotes")),
    )


def _normalized_bk_probabilities(quotes: object) -> OutcomeTriplet:
    values = _require_mapping(quotes, "quotes")
    raw_values = (
        values.get("bk_win_1"),
        values.get("bk_draw"),
        values.get("bk_win_2"),
    )
    numbers = tuple(
        _finite_positive_number(value, "BK probability") for value in raw_values
    )
    total = sum(numbers)
    return numbers[0] / total, numbers[1] / total, numbers[2] / total


def _split_teams(value: str, field_name: str) -> tuple[str, str]:
    for separator in _TEAM_SEPARATORS:
        if separator in value:
            home_team, away_team = (part.strip() for part in value.split(separator, 1))
            if home_team and away_team:
                return home_team, away_team
            break
    raise ValueError(f"{field_name} must contain non-empty home and away teams")


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _optional_positive_int(value: object, name: str) -> int | None:
    return None if value is None else _require_positive_int(value, name)


def _require_event_order(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in range(15):
        raise ValueError("event order must be in range 0 through 14")
    return value


def _finite_positive_number(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite and positive")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite and positive") from error
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _parse_utc_datetime(value: object, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError(
                f"{name} must be an ISO timezone-aware UTC datetime"
            ) from error
    else:
        raise ValueError(f"{name} must be an ISO timezone-aware UTC datetime")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)
