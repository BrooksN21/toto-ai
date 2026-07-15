from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from toto_ai.external_odds.domain import ProviderEvent, TargetEvent

MATCHER_VERSION = "api-sports-v2"
MAX_START_DELTA = timedelta(hours=3)
MatchStatus = Literal["matched", "missing", "ambiguous", "unknown_sport"]


@dataclass(frozen=True)
class MatchDecision:
    status: MatchStatus
    provider_event_id: str | None
    matcher_version: str
    candidate_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class MatchSuggestion:
    provider_event_id: str
    score: float
    home_score: float
    away_score: float
    starts_at_delta_seconds: int
    reason: str


def normalize_team_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("team name must be non-empty")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    collapsed = " ".join(normalized.split())
    if not collapsed:
        raise ValueError("team name must normalize to a non-empty value")
    return collapsed


def load_aliases(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"version", "aliases"}:
        raise ValueError("alias file must use the exact schema")
    if payload["version"] != 1:
        raise ValueError("alias file version must be 1")
    raw_aliases = payload["aliases"]
    if not isinstance(raw_aliases, dict):
        raise ValueError("aliases must be a mapping")

    normalized_aliases: dict[str, str] = {}
    normalized_values: set[str] = set()
    for raw_key, raw_value in raw_aliases.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise ValueError("aliases must map strings to strings")
        key = normalize_team_name(raw_key)
        value = normalize_team_name(raw_value)
        if key in normalized_aliases:
            raise ValueError("normalized alias key must be unique")
        if value in normalized_values:
            raise ValueError("normalized alias value must be unique")
        normalized_aliases[key] = value
        normalized_values.add(value)

    _validate_alias_cycles(normalized_aliases)
    return {key: normalized_aliases[key] for key in sorted(normalized_aliases)}


def suggest_matches(
    target: TargetEvent,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    aliases: dict[str, str],
) -> tuple[MatchSuggestion, ...]:
    suggestions = []
    home_options = _target_team_options(target.home_team, target.home_team_en, aliases)
    away_options = _target_team_options(target.away_team, target.away_team_en, aliases)

    for candidate in candidates:
        if candidate.sport != target.sport:
            continue
        starts_at_delta = (
            abs(candidate.starts_at - target.starts_at)
            if target.starts_at is not None
            else None
        )
        if starts_at_delta is not None and starts_at_delta > MAX_START_DELTA:
            continue
        home_score = _best_similarity(candidate.home_team, home_options, aliases)
        away_score = _best_similarity(candidate.away_team, away_options, aliases)
        score = (home_score + away_score) / 2.0
        suggestions.append(
            MatchSuggestion(
                provider_event_id=candidate.provider_event_id,
                score=score,
                home_score=home_score,
                away_score=away_score,
                starts_at_delta_seconds=(
                    int(starts_at_delta.total_seconds())
                    if starts_at_delta is not None
                    else -1
                ),
                reason="diagnostic similarity only",
            )
        )

    suggestions.sort(key=lambda item: (-item.score, item.provider_event_id))
    return tuple(suggestions[:5])


def match_event(
    target: TargetEvent,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    aliases: dict[str, str],
) -> MatchDecision:
    if target.sport == "unknown":
        return MatchDecision(
            status="unknown_sport",
            provider_event_id=None,
            matcher_version=MATCHER_VERSION,
            candidate_ids=(),
            reason="unknown sport",
        )

    home_options = _target_team_options(target.home_team, target.home_team_en, aliases)
    away_options = _target_team_options(target.away_team, target.away_team_en, aliases)
    matches = tuple(
        candidate
        for candidate in candidates
        if candidate.sport == target.sport
        and (
            target.starts_at is None
            or abs(candidate.starts_at - target.starts_at) <= MAX_START_DELTA
        )
        and _canonical(candidate.home_team, aliases) in home_options
        and _canonical(candidate.away_team, aliases) in away_options
    )
    if len(matches) == 1:
        candidate = matches[0]
        return MatchDecision(
            status="matched",
            provider_event_id=candidate.provider_event_id,
            matcher_version=MATCHER_VERSION,
            candidate_ids=(candidate.provider_event_id,),
            reason=(
                "unique exact match"
                if target.starts_at is not None
                else "unique exact match; target start unavailable"
            ),
        )

    candidate_ids = tuple(sorted(candidate.provider_event_id for candidate in matches))
    return MatchDecision(
        status="missing" if not matches else "ambiguous",
        provider_event_id=None,
        matcher_version=MATCHER_VERSION,
        candidate_ids=candidate_ids,
        reason=f"{len(matches)} exact candidates",
    )


def _target_team_options(
    primary_name: str, english_name: str | None, aliases: dict[str, str]
) -> frozenset[str]:
    options = {_canonical(primary_name, aliases)}
    if english_name is not None:
        options.add(_canonical(english_name, aliases))
    return frozenset(options)


def _canonical(name: str, aliases: dict[str, str]) -> str:
    current = normalize_team_name(name)
    visited = set()
    while current in aliases:
        if current in visited:
            raise ValueError("alias cycle detected")
        visited.add(current)
        current = aliases[current]
    return current


def _best_similarity(
    name: str, options: frozenset[str], aliases: dict[str, str]
) -> float:
    candidate = _canonical(name, aliases)
    return max(SequenceMatcher(None, candidate, option).ratio() for option in options)


def _validate_alias_cycles(aliases: dict[str, str]) -> None:
    for key in aliases:
        current = key
        visited = set()
        while current in aliases:
            if current in visited:
                raise ValueError("alias cycle detected")
            visited.add(current)
            current = aliases[current]
