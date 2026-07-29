from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any, Literal

from toto_ai.external_odds.countries import (
    countries_equivalent,
    country_identity,
)
from toto_ai.external_odds.domain import ProviderEvent, TargetEvent
from toto_ai.external_odds.matching import normalize_team_name
from toto_ai.external_odds.team_registry import (
    ReviewedTeamAlias,
    lookup_reviewed_alias,
    lookup_reviewed_alias_by_provider_id,
    transliterate_team_name,
)

RESOLVER_VERSION = "systematic-team-v2"
MAX_KNOWN_START_DELTA = timedelta(hours=3)
MAX_MISSING_START_HORIZON = timedelta(days=5)
MIN_PAIR_SCORE = 0.62
MIN_TEAM_SCORE = 0.52
MIN_MARGIN = 0.10
MIN_HIGH_CONFIDENCE_TEAM_SCORE = 0.74
ResolutionStatus = Literal[
    "matched",
    "missing",
    "ambiguous",
    "rejected",
    "source_missing_competition",
]
Orientation = Literal["same", "reversed"]

_CONTEXT_STOP_WORDS = frozenset(
    {
        "football",
        "hockey",
        "league",
        "лига",
        "кубок",
        "cup",
        "match",
        "fixture",
        "drawing",
        "real",
        "чемпионат",
    }
)
_WOMEN_MARKERS = frozenset(
    {
        "female",
        "femenino",
        "feminine",
        "ladies",
        "woman",
        "women",
        "жен",
        "женская",
        "женский",
        "ж",
    }
)
_NON_SENIOR_MARKERS = frozenset(
    {
        "academy",
        "reserve",
        "reserves",
        "res",
        "u17",
        "u18",
        "u19",
        "u20",
        "u21",
        "u23",
        "youth",
    }
)

@dataclass(frozen=True)
class ResolutionContext:
    provider: str
    country: str | None = None
    league: str | None = None
    sport: str | None = None
    competition: str | None = None
    derived: bool = False


def derive_resolution_context(
    target: TargetEvent, *, provider: str
) -> ResolutionContext:
    """Derive conservative structured context from TotoBrief championship text."""
    parts = tuple(
        part.strip()
        for part in re.split(r"\s*(?:\.|\||/|\s+-\s+)\s*", target.championship)
        if part.strip()
    )
    country = parts[0] if len(parts) >= 2 else None
    league = ". ".join(parts[1:]) if len(parts) >= 2 else parts[0]
    return ResolutionContext(
        provider=provider,
        country=country,
        league=league,
        sport=target.sport,
        competition=target.championship,
        derived=True,
    )


@dataclass(frozen=True)
class CandidateEvidence:
    provider_event_id: str
    orientation: Orientation
    pair_score: float
    home_score: float
    away_score: float
    exact_team_count: int
    transliterated_equal_count: int
    reviewed_team_count: int
    provider_id_count: int
    context_evidence: tuple[str, ...]
    rejected_reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateResolution:
    status: ResolutionStatus
    provider_event_id: str | None
    orientation: Orientation | None
    confidence: float
    margin: float
    reason: str
    candidates: tuple[CandidateEvidence, ...]
    canonical_home_team_id: int | None = None
    canonical_away_team_id: int | None = None


@dataclass(frozen=True)
class _TeamEvidence:
    score: float
    exact: bool
    transliterated_equal: bool
    reviewed: bool
    provider_id: bool
    team_id: int | None


def resolve_event_candidate(
    target: TargetEvent,
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    *,
    session_factory: Any,
    context: ResolutionContext,
) -> CandidateResolution:
    """Resolve one target conservatively; fuzzy/transliteration is evidence only."""
    if target.sport == "unknown":
        return CandidateResolution(
            "rejected", None, None, 0.0, 0.0, "unknown sport", ()
        )
    target_home = _target_alias(session_factory, target, target.home_team, context)
    target_away = _target_alias(session_factory, target, target.away_team, context)
    evidence: list[tuple[CandidateEvidence, int | None, int | None]] = []
    rejected: list[CandidateEvidence] = []

    for candidate in candidates:
        rejected_reasons, context_evidence = _candidate_context(
            target, candidate, context
        )
        for orientation in ("same", "reversed"):
            provider_home_name = (
                candidate.home_team if orientation == "same" else candidate.away_team
            )
            provider_away_name = (
                candidate.away_team if orientation == "same" else candidate.home_team
            )
            provider_home_id = (
                candidate.provider_home_team_id
                if orientation == "same"
                else candidate.provider_away_team_id
            )
            provider_away_id = (
                candidate.provider_away_team_id
                if orientation == "same"
                else candidate.provider_home_team_id
            )
            home = _team_evidence(
                session_factory,
                sport=target.sport,
                provider=context.provider,
                target_name=target.home_team,
                target_english=target.home_team_en,
                target_alias=target_home,
                provider_name=provider_home_name,
                provider_team_id=provider_home_id,
                provider_country=candidate.country,
                provider_league=candidate.league,
            )
            away = _team_evidence(
                session_factory,
                sport=target.sport,
                provider=context.provider,
                target_name=target.away_team,
                target_english=target.away_team_en,
                target_alias=target_away,
                provider_name=provider_away_name,
                provider_team_id=provider_away_id,
                provider_country=candidate.country,
                provider_league=candidate.league,
            )
            item = CandidateEvidence(
                provider_event_id=candidate.provider_event_id,
                orientation=orientation,
                pair_score=(home.score + away.score) / 2.0,
                home_score=home.score,
                away_score=away.score,
                exact_team_count=int(home.exact) + int(away.exact),
                transliterated_equal_count=(
                    int(home.transliterated_equal) + int(away.transliterated_equal)
                ),
                reviewed_team_count=int(home.reviewed) + int(away.reviewed),
                provider_id_count=int(home.provider_id) + int(away.provider_id),
                context_evidence=context_evidence,
                rejected_reasons=rejected_reasons,
            )
            if rejected_reasons:
                rejected.append(item)
            else:
                evidence.append((item, home.team_id, away.team_id))

    evidence.sort(
        key=lambda value: (
            -value[0].provider_id_count,
            -value[0].reviewed_team_count,
            -value[0].exact_team_count,
            -value[0].pair_score,
            value[0].provider_event_id,
            value[0].orientation,
        )
    )
    if not evidence:
        status: ResolutionStatus = (
            "source_missing_competition"
            if _source_missing_domestic_competition(candidates, context)
            else "missing"
        )
        return CandidateResolution(
            status,
            None,
            None,
            0.0,
            0.0,
            (
                "source schedule has no candidate in the confirmed domestic "
                "competition context"
                if status == "source_missing_competition"
                else "no candidates passed sport/date/country/league context"
            ),
            tuple(sorted(rejected, key=_candidate_sort_key)[:10]),
        )

    best, home_id, away_id = evidence[0]
    runner_up = next(
        (
            item
            for item, _, _ in evidence[1:]
            if item.provider_event_id != best.provider_event_id
        ),
        None,
    )
    opposite = next(
        (
            item
            for item, _, _ in evidence[1:]
            if item.provider_event_id == best.provider_event_id
        ),
        None,
    )
    margin = best.pair_score - (runner_up.pair_score if runner_up else 0.0)
    if runner_up is not None and _identity_rank(best) > _identity_rank(runner_up):
        margin = best.pair_score
    orientation_margin = best.pair_score - (
        opposite.pair_score if opposite is not None else 0.0
    )
    unique_fixture = margin >= MIN_MARGIN and orientation_margin >= 0.05
    exact_identity = best.provider_id_count == 2 or best.reviewed_team_count == 2
    strong_pair = (
        best.pair_score >= MIN_PAIR_SCORE
        and min(best.home_score, best.away_score) >= MIN_TEAM_SCORE
    )
    one_side_identity = (
        best.exact_team_count >= 1
        or best.reviewed_team_count >= 1
        or best.provider_id_count >= 1
        or best.transliterated_equal_count >= 1
        or max(best.home_score, best.away_score) >= MIN_HIGH_CONFIDENCE_TEAM_SCORE
    )
    strong_context = bool(
        {"country", "league", "competition"}.intersection(best.context_evidence)
    )

    accepted = False
    reason = ""
    if exact_identity and unique_fixture:
        accepted = True
        reason = "unique reviewed/provider-ID exact pair"
    elif unique_fixture and strong_context and strong_pair and one_side_identity:
        accepted = True
        reason = (
            "unique fixture with one-side identity and strong "
            "competition/date/orientation evidence"
        )

    visible = tuple(item for item, _, _ in evidence[:10])
    if accepted:
        return CandidateResolution(
            "matched",
            best.provider_event_id,
            best.orientation,
            min(1.0, best.pair_score),
            margin,
            f"{reason}; score={best.pair_score:.3f}; margin={margin:.3f}",
            visible,
            home_id,
            away_id,
        )
    status: ResolutionStatus
    if _source_missing_domestic_competition(candidates, context):
        status = "source_missing_competition"
    else:
        status = "ambiguous" if len(evidence) > 1 else "missing"
    return CandidateResolution(
        status,
        None,
        None,
        best.pair_score,
        margin,
        (
            "source schedule has no candidate in the confirmed domestic "
            "competition context"
            if status == "source_missing_competition"
            else (
                "candidate evidence is insufficient for conservative auto-accept; "
                f"score={best.pair_score:.3f}; margin={margin:.3f}"
            )
        ),
        visible,
    )


def _candidate_context(
    target: TargetEvent,
    candidate: ProviderEvent,
    context: ResolutionContext,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    rejected: list[str] = []
    accepted = ["sport"]
    if candidate.provider != context.provider:
        rejected.append("provider mismatch")
    if context.sport is not None and context.sport != target.sport:
        rejected.append("target sport context mismatch")
    if candidate.sport != target.sport:
        rejected.append("sport mismatch")
    if not _gender_context_matches(target, candidate):
        rejected.append("gender mismatch")
    if target.starts_at is not None:
        if abs(candidate.starts_at - target.starts_at) > MAX_KNOWN_START_DELTA:
            rejected.append("outside known-start window")
        else:
            accepted.append("date")
    elif not (
        target.deadline - timedelta(hours=6)
        <= candidate.starts_at
        <= target.deadline + MAX_MISSING_START_HORIZON
    ):
        rejected.append("outside drawing horizon")
    else:
        accepted.append("date-window")

    expected_country = context.country
    if (
        expected_country
        and _is_confirmed_domestic_scope(expected_country)
        and candidate.country
        and _is_global_scope(candidate.country)
    ):
        rejected.append("domestic target cannot use global competition")
    if expected_country and candidate.country and not _is_global_scope(
        candidate.country
    ):
        if not _countries_equivalent(expected_country, candidate.country):
            rejected.append("country mismatch")
        else:
            accepted.append("country")

    if context.league is not None:
        if _competition_level_conflicts(context.league, candidate.league):
            rejected.append("league mismatch")
        elif (
            _context_similarity(context.league, candidate.league) >= 0.58
            or _context_anchor_similarity(context.league, candidate.league) >= 0.62
        ):
            accepted.append("league")
        elif not context.derived:
            rejected.append("league mismatch")
        else:
            accepted.append("league-unconfirmed")
    candidate_competition = " ".join(
        value for value in (candidate.country, candidate.league) if value
    )
    expected_competition = context.competition or target.championship
    if (
        _context_similarity(expected_competition, candidate_competition) >= 0.58
        or _context_anchor_similarity(
            expected_competition, candidate_competition
        )
        >= 0.62
    ):
        accepted.append("competition")
    return tuple(rejected), tuple(accepted)


def _gender_context_matches(
    target: TargetEvent,
    candidate: ProviderEvent,
) -> bool:
    target_women = _has_women_context(
        target.home_team,
        target.away_team,
        target.home_team_en,
        target.away_team_en,
        target.championship,
        allow_team_w_marker=False,
    )
    candidate_women = _has_women_context(
        candidate.home_team,
        candidate.away_team,
        candidate.league,
        allow_team_w_marker=True,
    )
    if target_women:
        return candidate_women and not _has_non_senior_context(
            candidate.home_team,
            candidate.away_team,
            candidate.league,
        )
    return not candidate_women


def _has_women_context(
    *values: str | None,
    allow_team_w_marker: bool,
) -> bool:
    for index, value in enumerate(values):
        if not value:
            continue
        tokens = frozenset(normalize_team_name(value).split())
        if tokens & _WOMEN_MARKERS:
            return True
        if allow_team_w_marker and index < 2 and "w" in tokens:
            return True
    return False


def _has_non_senior_context(*values: str) -> bool:
    return any(
        frozenset(normalize_team_name(value).split()) & _NON_SENIOR_MARKERS
        for value in values
    )


def _countries_equivalent(expected: str, actual: str) -> bool:
    return countries_equivalent(expected, actual)


def _team_evidence(
    session_factory: Any,
    *,
    sport: str,
    provider: str,
    target_name: str,
    target_english: str | None,
    target_alias: ReviewedTeamAlias | None,
    provider_name: str,
    provider_team_id: str | None,
    provider_country: str | None,
    provider_league: str,
) -> _TeamEvidence:
    provider_alias = None
    if provider_team_id is not None:
        provider_alias = lookup_reviewed_alias_by_provider_id(
            session_factory,
            sport=sport,
            provider=provider,
            provider_team_id=provider_team_id,
        )
    if provider_alias is None:
        provider_alias = lookup_reviewed_alias(
            session_factory,
            sport=sport,
            alias=provider_name,
            provider=provider,
            country=provider_country,
            context=provider_league,
        )
    provider_identity = provider_alias.team.id if provider_alias else None
    target_identity = target_alias.team.id if target_alias else None
    provider_id_exact = (
        provider_team_id is not None
        and provider_alias is not None
        and target_identity == provider_identity
    )
    reviewed_exact = (
        target_identity is not None and target_identity == provider_identity
    )
    names = (target_name,) if target_english is None else (target_name, target_english)
    normalized_provider = normalize_team_name(provider_name)
    exact = any(normalize_team_name(name) == normalized_provider for name in names)
    if target_alias is not None and (
        target_alias.team.normalized_name == normalized_provider
        or target_alias.normalized_alias == normalized_provider
    ):
        exact = True
    score = max(_name_score(name, provider_name) for name in names)
    transliterated_equal = any(
        transliterate_team_name(name) == transliterate_team_name(provider_name)
        for name in names
    )
    if reviewed_exact:
        score = 1.0
    return _TeamEvidence(
        score=score,
        exact=exact,
        transliterated_equal=transliterated_equal,
        reviewed=reviewed_exact,
        provider_id=provider_id_exact,
        team_id=target_identity or provider_identity,
    )


def _target_alias(
    session_factory: Any,
    target: TargetEvent,
    name: str,
    context: ResolutionContext,
) -> ReviewedTeamAlias | None:
    return lookup_reviewed_alias(
        session_factory,
        sport=target.sport,
        alias=name,
        provider=context.provider,
        country=context.country,
        context=context.league,
    )


def _name_score(left: str, right: str) -> float:
    left_value = transliterate_team_name(left)
    right_value = transliterate_team_name(right)
    if left_value == right_value:
        return 1.0
    left_tokens = _name_tokens(left_value)
    right_tokens = _name_tokens(right_value)
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, left_value, right_value).ratio()
    containment = 0.9 if left_tokens and (
        left_tokens <= right_tokens or right_tokens <= left_tokens
    ) else 0.0
    token_alignment = _token_alignment(left_tokens, right_tokens)
    return max(sequence, overlap, containment, token_alignment)


def _name_tokens(value: str) -> frozenset[str]:
    ignored = {"fc", "fk", "cf", "sc", "club", "de", "the"}
    return frozenset(token for token in value.split() if token not in ignored)


def _token_alignment(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    left_score = sum(
        max(SequenceMatcher(None, token, candidate).ratio() for candidate in right)
        for token in left
    ) / len(left)
    right_score = sum(
        max(SequenceMatcher(None, token, candidate).ratio() for candidate in left)
        for token in right
    ) / len(right)
    return min(left_score, right_score)


def _context_tokens(value: str | None, *, keep_generic: bool = False) -> frozenset[str]:
    if not value:
        return frozenset()
    tokens = frozenset(re.findall(r"[\w]+", normalize_team_name(value)))
    if keep_generic:
        return tokens
    meaningful = tokens - _CONTEXT_STOP_WORDS
    return meaningful if meaningful != tokens or len(tokens) > 1 else tokens


def _context_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    left_value = transliterate_team_name(left)
    right_value = transliterate_team_name(right)
    left_tokens = _context_transliterated_tokens(left_value)
    right_tokens = _context_transliterated_tokens(right_value)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / min(
        len(left_tokens), len(right_tokens)
    )
    return max(overlap, _token_alignment(left_tokens, right_tokens))


def _context_transliterated_tokens(value: str) -> frozenset[str]:
    ignored = {
        "football",
        "hockey",
        "league",
        "liga",
        "cup",
        "kubok",
        "chempionat",
        "qualification",
        "kvalifikatsiya",
    }
    return frozenset(token for token in value.split() if token not in ignored)


def _context_anchor_similarity(left: str, right: str) -> float:
    left_tokens = _context_transliterated_tokens(transliterate_team_name(left))
    right_tokens = _context_transliterated_tokens(transliterate_team_name(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return max(
        SequenceMatcher(None, left_token, right_token).ratio()
        for left_token in left_tokens
        for right_token in right_tokens
    )


def _competition_level_conflicts(left: str, right: str) -> bool:
    left_levels = _competition_level_tokens(left)
    right_levels = _competition_level_tokens(right)
    return bool(left_levels and right_levels and left_levels.isdisjoint(right_levels))


def _competition_level_tokens(value: str) -> frozenset[str]:
    tokens = transliterate_team_name(value).split()
    return frozenset(
        token
        for token in tokens
        if token.isdigit() or (len(token) == 1 and token.isalpha())
    )


def _is_global_scope(value: str) -> bool:
    return country_identity(value) == "GLOBAL" or normalize_team_name(value) == (
        "international clubs"
    )


def _is_confirmed_domestic_scope(value: str) -> bool:
    identity = country_identity(value)
    return identity != "GLOBAL" and not identity.startswith("NAME:")


def _source_missing_domestic_competition(
    candidates: tuple[ProviderEvent, ...] | list[ProviderEvent],
    context: ResolutionContext,
) -> bool:
    """Classify observed provider coverage, never invent a fixture."""
    if (
        not context.derived
        or not context.country
        or not _is_confirmed_domestic_scope(context.country)
        or not context.league
        or not _competition_level_tokens(context.league)
    ):
        return False
    provider_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.provider == context.provider
        and candidate.sport == (context.sport or candidate.sport)
    )
    if not provider_candidates:
        return False
    domestic = tuple(
        candidate
        for candidate in provider_candidates
        if candidate.country
        and not _is_global_scope(candidate.country)
        and _countries_equivalent(context.country, candidate.country)
    )
    return bool(domestic) and not any(
        _competition_level_tokens(candidate.league)
        == _competition_level_tokens(context.league)
        and (
            _context_similarity(context.league, candidate.league) >= 0.58
            or _context_anchor_similarity(context.league, candidate.league) >= 0.62
        )
        for candidate in domestic
    )


def _identity_rank(item: CandidateEvidence) -> tuple[int, int, int, int]:
    return (
        item.provider_id_count,
        item.reviewed_team_count,
        item.exact_team_count,
        item.transliterated_equal_count,
    )


def _candidate_sort_key(item: CandidateEvidence) -> tuple[float, str, str]:
    return (-item.pair_score, item.provider_event_id, item.orientation)
