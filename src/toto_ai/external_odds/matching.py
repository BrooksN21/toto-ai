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

MATCHER_VERSION = "api-sports-v4"
MAX_START_DELTA = timedelta(hours=3)
MIN_TRANSLITERATED_PAIR_SCORE = 0.74
MIN_TRANSLITERATED_TEAM_SCORE = 0.55
MIN_TRANSLITERATED_MARGIN = 0.15
MatchStatus = Literal["matched", "missing", "ambiguous", "unknown_sport"]
MatchOrientation = Literal["same", "reversed"]

_CYRILLIC_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ы": "y",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ь": "",
    "ъ": "",
}


@dataclass(frozen=True)
class MatchDecision:
    status: MatchStatus
    provider_event_id: str | None
    matcher_version: str
    candidate_ids: tuple[str, ...]
    reason: str
    orientation: MatchOrientation | None = None


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
    if not isinstance(payload, dict):
        raise ValueError("alias file must use the exact schema")
    version = payload.get("version")
    expected_keys = (
        {"version", "aliases"}
        if version == 1
        else {"version", "aliases", "identities"}
        if version == 2
        else None
    )
    if expected_keys is None:
        raise ValueError("alias file version must be 1 or 2")
    if set(payload) != expected_keys:
        raise ValueError("alias file must use the exact schema")
    if version == 2:
        identities = payload["identities"]
        if not isinstance(identities, list):
            raise ValueError("alias identities must be a list")
        for identity in identities:
            if not isinstance(identity, dict) or set(identity) != {
                "canonical_name",
                "country",
                "context",
                "provider_team_id",
                "aliases",
            }:
                raise ValueError("reviewed identity must use the exact schema")
            if (
                any(
                    not isinstance(identity[field], str)
                    or not identity[field].strip()
                    for field in (
                        "canonical_name",
                        "country",
                        "context",
                        "provider_team_id",
                    )
                )
                or not isinstance(identity["aliases"], list)
                or not identity["aliases"]
                or any(
                    not isinstance(alias, str) or not alias.strip()
                    for alias in identity["aliases"]
                )
            ):
                raise ValueError("reviewed identity values are invalid")
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
    same_matches = tuple(
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
    same_ids = frozenset(candidate.provider_event_id for candidate in same_matches)
    reversed_matches = tuple(
        candidate
        for candidate in candidates
        if candidate.provider_event_id not in same_ids
        and candidate.sport == target.sport
        and (
            target.starts_at is None
            or abs(candidate.starts_at - target.starts_at) <= MAX_START_DELTA
        )
        and _canonical(candidate.home_team, aliases) in away_options
        and _canonical(candidate.away_team, aliases) in home_options
    )
    oriented_matches = (
        *((candidate, "same") for candidate in same_matches),
        *((candidate, "reversed") for candidate in reversed_matches),
    )
    if len(oriented_matches) == 1:
        candidate, orientation = oriented_matches[0]
        return MatchDecision(
            status="matched",
            provider_event_id=candidate.provider_event_id,
            matcher_version=MATCHER_VERSION,
            candidate_ids=(candidate.provider_event_id,),
            reason=(
                (
                    "unique exact match"
                    if target.starts_at is not None
                    else "unique exact match; target start unavailable"
                )
                if orientation == "same"
                else (
                    "unique exact reversed match; outcomes swapped"
                    if target.starts_at is not None
                    else (
                        "unique exact reversed match; target start unavailable; "
                        "outcomes swapped"
                    )
                )
            ),
            orientation=orientation,
        )

    if not oriented_matches and _requires_transliterated_matching(target):
        transliterated = _match_transliterated_pair(target, candidates, aliases)
        if transliterated is not None:
            return transliterated

    candidate_ids = tuple(
        sorted(candidate.provider_event_id for candidate, _ in oriented_matches)
    )
    return MatchDecision(
        status="missing" if not oriented_matches else "ambiguous",
        provider_event_id=None,
        matcher_version=MATCHER_VERSION,
        candidate_ids=candidate_ids,
        reason=f"{len(oriented_matches)} exact candidates",
    )


def _match_transliterated_pair(
    target: TargetEvent,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    aliases: dict[str, str],
) -> MatchDecision | None:
    home_options = _target_team_options(target.home_team, None, aliases)
    away_options = _target_team_options(target.away_team, None, aliases)
    scored: list[tuple[float, float, str, MatchOrientation]] = []
    for candidate in candidates:
        if candidate.sport != target.sport:
            continue
        if (
            target.starts_at is not None
            and abs(candidate.starts_at - target.starts_at) > MAX_START_DELTA
        ):
            continue
        same_home = _best_transliterated_similarity(
            candidate.home_team, home_options, aliases
        )
        same_away = _best_transliterated_similarity(
            candidate.away_team, away_options, aliases
        )
        reversed_home = _best_transliterated_similarity(
            candidate.home_team, away_options, aliases
        )
        reversed_away = _best_transliterated_similarity(
            candidate.away_team, home_options, aliases
        )
        scored.extend(
            (
                (
                    (same_home + same_away) / 2.0,
                    min(same_home, same_away),
                    candidate.provider_event_id,
                    "same",
                ),
                (
                    (reversed_home + reversed_away) / 2.0,
                    min(reversed_home, reversed_away),
                    candidate.provider_event_id,
                    "reversed",
                ),
            )
        )

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    best = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best[0] - runner_up_score
    if (
        best[0] < MIN_TRANSLITERATED_PAIR_SCORE
        or best[1] < MIN_TRANSLITERATED_TEAM_SCORE
        or margin < MIN_TRANSLITERATED_MARGIN
    ):
        return None

    timing_note = (
        ""
        if target.starts_at is not None
        else "; target start unavailable"
    )
    return MatchDecision(
        status="matched",
        provider_event_id=best[2],
        matcher_version=MATCHER_VERSION,
        candidate_ids=(best[2],),
        reason=(
            "unique high-confidence transliterated match"
            f"{timing_note}; score={best[0]:.3f}; margin={margin:.3f}"
        ),
        orientation=best[3],
    )


def _requires_transliterated_matching(target: TargetEvent) -> bool:
    return (
        target.home_team_en is None
        and target.away_team_en is None
        and _contains_cyrillic(target.home_team)
        and _contains_cyrillic(target.away_team)
    )


def _contains_cyrillic(value: str) -> bool:
    return any(
        "а" <= character.casefold() <= "я" or character in "Ёё"
        for character in value
    )


def _best_transliterated_similarity(
    name: str, options: frozenset[str], aliases: dict[str, str]
) -> float:
    candidate = _latinized_canonical(name, aliases)
    return max(
        SequenceMatcher(None, candidate, _latinize(option)).ratio()
        for option in options
    )


def _latinized_canonical(name: str, aliases: dict[str, str]) -> str:
    return _latinize(_canonical(name, aliases))


def _latinize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    transliterated = "".join(
        _CYRILLIC_TO_LATIN.get(character, character) for character in without_marks
    )
    normalized = re.sub(r"[^a-z0-9]+", " ", transliterated)
    collapsed = " ".join(normalized.split())
    if not collapsed:
        raise ValueError("team name must latinize to a non-empty value")
    return collapsed


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
