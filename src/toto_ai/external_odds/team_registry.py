from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update

from toto_ai.db.models import (
    DrawingEventPin,
    DrawingPreparation,
    TeamAlias,
    TeamEntity,
    TeamRegistryReview,
)
from toto_ai.external_odds.countries import countries_equivalent
from toto_ai.external_odds.matching import normalize_team_name

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
class TeamEntityRecord:
    id: int
    sport: str
    canonical_name: str
    normalized_name: str
    transliterated_name: str
    country: str
    context: str
    created_at: str


@dataclass(frozen=True)
class ReviewedTeamAlias:
    id: int
    team: TeamEntityRecord
    alias: str
    normalized_alias: str
    transliterated_alias: str
    source: str
    provider: str
    country: str
    context: str
    provider_team_id: str | None
    provenance: Any
    confidence: float
    reviewer: str
    reviewed_at: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TeamReviewRecord:
    id: int
    drawing_id: int
    drawing_fingerprint: str
    target_event_id: str
    event_order: int
    provider: str
    sport: str
    target_home_team: str
    target_away_team: str
    context: Any
    resolution_reason: str
    candidate_evidence: Any
    matching_hash: str
    status: str
    resolution_home_team_id: int | None
    resolution_away_team_id: int | None
    resolution_provenance: Any | None
    created_at: str
    updated_at: str
    resolved_at: str | None


@dataclass(frozen=True)
class DrawingEventPinRecord:
    id: int
    drawing_id: int
    drawing_fingerprint: str
    target_event_id: str
    event_order: int
    provider: str
    canonical_home_team_id: int
    canonical_away_team_id: int
    provider_home_team_id: str
    provider_away_team_id: str
    provider_fixture_id: str
    starts_at: str | None
    collection_id: str | None
    provenance: Any
    pin_hash: str
    status: str
    created_at: str
    invalidated_at: str | None
    invalidation_reason: str | None


def transliterate_team_name(value: str) -> str:
    normalized = normalize_team_name(value)
    decomposed = unicodedata.normalize("NFKD", normalized)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    transliterated = "".join(
        _CYRILLIC_TO_LATIN.get(character, character)
        for character in without_marks
    )
    collapsed = " ".join(re.sub(r"[^a-z0-9]+", " ", transliterated).split())
    if not collapsed:
        raise ValueError("team name must transliterate to a non-empty value")
    return collapsed


def upsert_team_entity(
    session_factory: Any,
    *,
    sport: str,
    canonical_name: str,
    country: str | None = None,
    context: str | None = None,
) -> TeamEntityRecord:
    sport = _required_text(sport, "sport")
    canonical_name = _required_text(canonical_name, "canonical_name")
    country = _optional_context(country, "country")
    context = _optional_context(context, "context")
    normalized_name = normalize_team_name(canonical_name)
    transliterated_name = transliterate_team_name(canonical_name)

    with session_factory.begin() as session:
        rows = tuple(
            session.scalars(
            select(TeamEntity).where(
                TeamEntity.sport == sport,
                TeamEntity.normalized_name == normalized_name,
                TeamEntity.context == context,
            )
            )
        )
        row = next(
            (
                candidate
                for candidate in sorted(rows, key=lambda item: item.id)
                if _country_context_equal(candidate.country, country)
            ),
            None,
        )
        if row is None:
            row = TeamEntity(
                sport=sport,
                canonical_name=canonical_name,
                normalized_name=normalized_name,
                transliterated_name=transliterated_name,
                country=country,
                context=context,
                created_at=_utc_now(),
            )
            session.add(row)
            session.flush()
        return _team_record(row)


def upsert_reviewed_alias(
    session_factory: Any,
    *,
    team_id: int,
    alias: str,
    source: str,
    provider: str,
    provenance: Any,
    confidence: float,
    reviewer: str,
    provider_team_id: str | None = None,
    country: str | None = None,
    context: str | None = None,
    active: bool = True,
) -> ReviewedTeamAlias:
    team_id = _positive_integer(team_id, "team_id")
    alias = _required_text(alias, "alias")
    source = _required_text(source, "source")
    provider = _required_text(provider, "provider")
    provider_team_id = _optional_identifier(provider_team_id, "provider_team_id")
    reviewer = _required_text(reviewer, "reviewer")
    confidence = _confidence(confidence)
    if not isinstance(active, bool):
        raise ValueError("active must be a boolean")
    provenance_text = _canonical_json(provenance, "provenance")
    normalized_alias = normalize_team_name(alias)
    transliterated_alias = transliterate_team_name(alias)

    with session_factory.begin() as session:
        team = session.get(TeamEntity, team_id)
        if team is None:
            raise ValueError("team does not exist")
        country = _optional_context(
            team.country if country is None else country, "country"
        )
        context = _optional_context(
            team.context if context is None else context, "context"
        )
        provider_row = None
        if provider_team_id is not None:
            provider_row = session.scalar(
                select(TeamAlias).where(
                    TeamAlias.sport == team.sport,
                    TeamAlias.provider == provider,
                    TeamAlias.provider_team_id == provider_team_id,
                )
            )
            if provider_row is not None and provider_row.team_id != team_id:
                raise ValueError("provider team ID is assigned to another team")

        alias_rows = tuple(
            session.scalars(
                select(TeamAlias).where(
                    TeamAlias.sport == team.sport,
                    TeamAlias.provider == provider,
                    TeamAlias.normalized_alias == normalized_alias,
                    TeamAlias.context == context,
                )
            )
        )
        row = next(
            (
                candidate
                for candidate in sorted(alias_rows, key=lambda item: item.id)
                if _country_context_equal(candidate.country, country)
            ),
            None,
        )
        if row is not None and row.team_id != team_id:
            raise ValueError("alias is assigned to another team")
        if provider_row is not None and row is not None and provider_row.id != row.id:
            raise ValueError("provider team ID is assigned to another alias")

        now = _utc_now()
        if row is None:
            row = TeamAlias(
                team_id=team_id,
                sport=team.sport,
                alias=alias,
                normalized_alias=normalized_alias,
                transliterated_alias=transliterated_alias,
                source=source,
                provider=provider,
                country=country,
                context=context,
                provider_team_id=provider_team_id,
                provenance=provenance_text,
                confidence=confidence,
                reviewed=True,
                reviewer=reviewer,
                reviewed_at=now,
                active=active,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
        else:
            requested = (
                alias,
                transliterated_alias,
                source,
                provider_team_id,
                provenance_text,
                confidence,
                reviewer,
                active,
            )
            current = (
                row.alias,
                row.transliterated_alias,
                row.source,
                row.provider_team_id,
                row.provenance,
                row.confidence,
                row.reviewer,
                row.active,
            )
            if requested != current or not row.reviewed:
                row.alias = alias
                row.transliterated_alias = transliterated_alias
                row.source = source
                row.provider_team_id = provider_team_id
                row.provenance = provenance_text
                row.confidence = confidence
                row.reviewed = True
                row.reviewer = reviewer
                row.reviewed_at = now
                row.active = active
                row.updated_at = now
                session.flush()
        return _reviewed_alias_record(row, team)


def lookup_reviewed_alias(
    session_factory: Any,
    *,
    sport: str,
    alias: str,
    provider: str,
    source: str | None = None,
    country: str | None = None,
    context: str | None = None,
) -> ReviewedTeamAlias | None:
    sport = _required_text(sport, "sport")
    alias = normalize_team_name(_required_text(alias, "alias"))
    provider = _required_text(provider, "provider")
    if source is not None:
        source = _required_text(source, "source")
    country = None if country is None else _optional_context(country, "country")
    context = None if context is None else _optional_context(context, "context")
    with session_factory() as session:
        statement = select(TeamAlias).where(
            TeamAlias.sport == sport,
            TeamAlias.provider == provider,
            TeamAlias.normalized_alias == alias,
            TeamAlias.reviewed.is_(True),
            TeamAlias.active.is_(True),
        )
        if source is not None:
            statement = statement.where(TeamAlias.source == source)
        rows = tuple(session.scalars(statement))
        if country is not None or context is not None:
            exact = tuple(
                row
                for row in rows
                if (
                    country is None
                    or _country_context_equal(row.country, country)
                )
                and (context is None or row.context == context)
            )
            if exact:
                rows = exact
            else:
                rows = tuple(
                    row for row in rows if row.country == "" and row.context == ""
                )
        if not rows:
            return None
        team_ids = {row.team_id for row in rows}
        if len(team_ids) != 1:
            return None
        row = sorted(rows, key=lambda item: item.id)[0]
        team = session.get(TeamEntity, row.team_id)
        if team is None:
            raise ValueError("alias references a missing team")
        return _reviewed_alias_record(row, team)


def lookup_reviewed_alias_by_provider_id(
    session_factory: Any,
    *,
    sport: str,
    provider: str,
    provider_team_id: str,
) -> ReviewedTeamAlias | None:
    sport = _required_text(sport, "sport")
    provider = _required_text(provider, "provider")
    provider_team_id = _required_text(provider_team_id, "provider_team_id")
    with session_factory() as session:
        row = session.scalar(
            select(TeamAlias).where(
                TeamAlias.sport == sport,
                TeamAlias.provider == provider,
                TeamAlias.provider_team_id == provider_team_id,
                TeamAlias.reviewed.is_(True),
                TeamAlias.active.is_(True),
            )
        )
        if row is None:
            return None
        team = session.get(TeamEntity, row.team_id)
        if team is None:
            raise ValueError("alias references a missing team")
        return _reviewed_alias_record(row, team)


def seed_reviewed_alias_config(
    session_factory: Any,
    aliases: Mapping[str, str] | str | Path,
    *,
    sport: str = "football",
    provider: str = "api-sports",
    source_path: str | None = None,
) -> tuple[ReviewedTeamAlias, ...]:
    """Idempotently import the reviewed JSON alias catalog into the registry."""
    if isinstance(aliases, (str, Path)):
        path = Path(aliases)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) not in (
            {"version", "aliases"},
            {"version", "aliases", "identities"},
        ):
            raise ValueError("alias file must use the exact schema")
        if payload["version"] not in (1, 2) or not isinstance(
            payload["aliases"], dict
        ):
            raise ValueError("alias file version and aliases are invalid")
        if payload["version"] == 1 and "identities" in payload:
            raise ValueError("alias file v1 cannot contain identities")
        identities = payload.get("identities", [])
        if not isinstance(identities, list):
            raise ValueError("alias identities must be a list")
        mapping = payload["aliases"]
        source_path = source_path or str(path)
    else:
        mapping = aliases
        identities = []
    results = []
    for target_name, provider_name in sorted(mapping.items()):
        if not isinstance(target_name, str) or not isinstance(provider_name, str):
            raise ValueError("aliases must map strings to strings")
        team = upsert_team_entity(
            session_factory,
            sport=sport,
            canonical_name=provider_name,
        )
        provenance = {
            "source": "reviewed-alias-config",
            "source_path": source_path or "in-memory",
            "target_alias": target_name,
            "provider_name": provider_name,
        }
        results.append(
            upsert_reviewed_alias(
                session_factory,
                team_id=team.id,
                alias=target_name,
                source="reviewed-alias-config",
                provider=provider,
                provenance=provenance,
                confidence=1.0,
                reviewer="reviewed-alias-config",
            )
        )
        upsert_reviewed_alias(
            session_factory,
            team_id=team.id,
            alias=provider_name,
            source="provider-canonical-name",
            provider=provider,
            provenance=provenance,
            confidence=1.0,
            reviewer="reviewed-alias-config",
        )
    for identity in identities:
        if not isinstance(identity, dict) or set(identity) != {
            "canonical_name",
            "country",
            "context",
            "provider_team_id",
            "aliases",
        }:
            raise ValueError("reviewed identity must use the exact schema")
        identity_aliases = identity["aliases"]
        if not isinstance(identity_aliases, list) or not identity_aliases:
            raise ValueError("reviewed identity aliases must be a non-empty list")
        if not all(isinstance(alias, str) for alias in identity_aliases):
            raise ValueError("reviewed identity aliases must be strings")
        team = upsert_team_entity(
            session_factory,
            sport=sport,
            canonical_name=identity["canonical_name"],
            country=identity["country"],
            context=identity["context"],
        )
        provenance = {
            "source": "reviewed-contextual-identity",
            "source_path": source_path or "in-memory",
            "provider_team_id": identity["provider_team_id"],
        }
        for index, alias in enumerate(identity_aliases):
            results.append(
                upsert_reviewed_alias(
                    session_factory,
                    team_id=team.id,
                    alias=alias,
                    source="reviewed-contextual-identity",
                    provider=provider,
                    provider_team_id=(
                        identity["provider_team_id"] if index == 0 else None
                    ),
                    country=identity["country"],
                    context=identity["context"],
                    provenance=provenance,
                    confidence=1.0,
                    reviewer="reviewed-alias-config",
                )
            )
    return tuple(results)


def backfill_accepted_matches(
    session_factory: Any,
    matches: Iterable[Mapping[str, Any]],
    *,
    provider: str = "api-sports",
) -> int:
    """Backfill only already accepted exact/reviewed/provider-ID match evidence."""
    inserted_or_seen = 0
    for match in matches:
        reason = str(match.get("reason", ""))
        if not (
            reason.startswith("unique exact")
            or "reviewed/provider-ID exact" in reason
            or match.get("reviewed") is True
        ):
            continue
        sport = _required_text(match.get("sport"), "sport")
        for side in ("home", "away"):
            target_name = _required_text(match.get(f"target_{side}"), f"target_{side}")
            provider_name = _required_text(
                match.get(f"provider_{side}"), f"provider_{side}"
            )
            provider_team_id = match.get(f"provider_{side}_team_id")
            team = upsert_team_entity(
                session_factory,
                sport=sport,
                canonical_name=provider_name,
                country=match.get("country"),
                context=match.get("league"),
            )
            provenance = {
                "source": "accepted-historical-match",
                "drawing_id": match.get("drawing_id"),
                "target_event_id": match.get("target_event_id"),
                "provider_fixture_id": match.get("provider_fixture_id"),
                "reason": reason,
            }
            upsert_reviewed_alias(
                session_factory,
                team_id=team.id,
                alias=target_name,
                source="accepted-historical-match",
                provider=provider,
                provider_team_id=(
                    None
                    if provider_team_id is None
                    or normalize_team_name(target_name)
                    != normalize_team_name(provider_name)
                    else str(provider_team_id)
                ),
                provenance=provenance,
                confidence=float(match.get("confidence", 1.0)),
                reviewer="accepted-history",
            )
            if normalize_team_name(target_name) != normalize_team_name(provider_name):
                upsert_reviewed_alias(
                    session_factory,
                    team_id=team.id,
                    alias=provider_name,
                    source="accepted-historical-match",
                    provider=provider,
                    provider_team_id=(
                        None if provider_team_id is None else str(provider_team_id)
                    ),
                    provenance=provenance,
                    confidence=float(match.get("confidence", 1.0)),
                    reviewer="accepted-history",
                )
            inserted_or_seen += 1
    return inserted_or_seen


def load_drawing_pins(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    provider: str,
    invalidate_stale: bool = True,
) -> tuple[DrawingEventPinRecord, ...]:
    """Load exactly 15 current pins; stale/partial sets fail closed."""
    drawing_id = _positive_integer(drawing_id, "drawing_id")
    drawing_fingerprint = _required_text(drawing_fingerprint, "drawing_fingerprint")
    provider = _required_text(provider, "provider")
    with session_factory.begin() as session:
        rows = tuple(
            session.scalars(
                select(DrawingEventPin)
                .where(
                    DrawingEventPin.drawing_id == drawing_id,
                    DrawingEventPin.provider == provider,
                    DrawingEventPin.status == "valid",
                )
                .order_by(DrawingEventPin.event_order)
            )
        )
        stale = tuple(
            row for row in rows if row.drawing_fingerprint != drawing_fingerprint
        )
        if stale:
            if invalidate_stale:
                now = _utc_now()
                for row in stale:
                    _validate_pin_integrity(row)
                    row.status = "invalidated"
                    row.invalidated_at = now
                    row.invalidation_reason = "drawing fingerprint changed"
                session.flush()
            raise ValueError("stale drawing pins: fingerprint changed")
        exact = tuple(
            row for row in rows if row.drawing_fingerprint == drawing_fingerprint
        )
        if not exact:
            return ()
        if len(exact) != 15 or tuple(row.event_order for row in exact) != tuple(
            range(15)
        ):
            raise ValueError("drawing pins are incomplete")
        if len({row.provider_fixture_id for row in exact}) != 15:
            raise ValueError("drawing pins reuse a provider fixture")
        return tuple(_pin_record(row) for row in exact)


def load_ready_drawing_pins(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    provider: str,
    expected_probability_sha256: str | None = None,
    as_of: datetime | None = None,
    max_probability_age: timedelta = timedelta(hours=24),
) -> tuple[DrawingEventPinRecord, ...]:
    """Require a ready preparation and its exact complete authoritative pin set."""
    with session_factory() as session:
        preparation = session.scalar(
            select(DrawingPreparation).where(
                DrawingPreparation.drawing_id == drawing_id,
                DrawingPreparation.drawing_fingerprint == drawing_fingerprint,
                DrawingPreparation.provider == provider,
            )
        )
    if preparation is None:
        # Preserve stale-pin invalidation and its precise reason.
        load_drawing_pins(
            session_factory,
            drawing_id=drawing_id,
            drawing_fingerprint=drawing_fingerprint,
            provider=provider,
        )
        raise ValueError(
            "ready drawing preparation is missing; run prepare-drawing"
        )
    try:
        unresolved = json.loads(preparation.unresolved_event_orders)
        summary = json.loads(preparation.readiness_summary)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("preparation_fail:invalid_readiness_evidence") from error
    if (
        preparation.status != "ready"
        or preparation.mapped_count != 15
        or unresolved != []
        or preparation.eligibility_status != "playable"
        or not isinstance(summary, dict)
        or summary.get("status") != "ready"
        or summary.get("mapped_count") != 15
        or summary.get("unresolved_event_orders") not in ([], ())
    ):
        raise ValueError("preparation_fail:not_ready_15_of_15")
    if expected_probability_sha256 is not None:
        if summary.get("probability_input_sha256") != expected_probability_sha256:
            raise ValueError("preparation_fail:probability_input_changed_or_missing")
        fetched_at_value = summary.get("target_fetched_at")
        try:
            fetched_at = datetime.fromisoformat(str(fetched_at_value))
        except ValueError as error:
            raise ValueError("preparation_fail:probability_input_not_fresh") from error
        reference = as_of or datetime.now(timezone.utc)
        if (
            fetched_at.tzinfo is None
            or fetched_at > reference
            or reference - fetched_at > max_probability_age
        ):
            raise ValueError("preparation_fail:probability_input_not_fresh")
    pins = load_drawing_pins(
        session_factory,
        drawing_id=drawing_id,
        drawing_fingerprint=drawing_fingerprint,
        provider=provider,
    )
    if len(pins) != 15:
        raise ValueError("ready drawing preparation has no complete pin set")
    return pins


def refresh_ready_drawing_preparation_evidence(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    provider: str,
    readiness_summary: str,
) -> None:
    """Atomically refresh evidence for an unchanged ready authoritative pin set."""
    drawing_id = _positive_integer(drawing_id, "drawing_id")
    drawing_fingerprint = _required_text(
        drawing_fingerprint, "drawing_fingerprint"
    )
    provider = _required_text(provider, "provider")
    try:
        summary = json.loads(readiness_summary)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid readiness summary") from error
    if (
        not isinstance(summary, dict)
        or summary.get("status") != "ready"
        or summary.get("mapped_count") != 15
        or summary.get("unresolved_event_orders") not in ([], ())
        or not isinstance(summary.get("probability_input_sha256"), str)
        or not isinstance(summary.get("target_fetched_at"), str)
    ):
        raise ValueError("invalid ready preparation evidence")
    incoming_hash = summary["probability_input_sha256"]
    try:
        incoming_fetched_at = datetime.fromisoformat(summary["target_fetched_at"])
    except ValueError as error:
        raise ValueError("invalid ready preparation evidence") from error
    if incoming_fetched_at.tzinfo is None:
        raise ValueError("invalid ready preparation evidence")

    while True:
        with session_factory() as session:
            preparation = session.scalar(
                select(DrawingPreparation).where(
                    DrawingPreparation.drawing_id == drawing_id,
                    DrawingPreparation.drawing_fingerprint == drawing_fingerprint,
                    DrawingPreparation.provider == provider,
                )
            )
            if (
                preparation is None
                or preparation.status != "ready"
                or preparation.mapped_count != 15
                or preparation.unresolved_event_orders != "[]"
                or preparation.eligibility_status != "playable"
            ):
                raise ValueError("ready drawing preparation cannot be refreshed")
            rows = tuple(
                session.scalars(
                    select(DrawingEventPin)
                    .where(
                        DrawingEventPin.drawing_id == drawing_id,
                        DrawingEventPin.drawing_fingerprint == drawing_fingerprint,
                        DrawingEventPin.provider == provider,
                        DrawingEventPin.status == "valid",
                    )
                    .order_by(DrawingEventPin.event_order)
                )
            )
            if (
                len(rows) != 15
                or tuple(row.event_order for row in rows) != tuple(range(15))
                or len({row.provider_fixture_id for row in rows}) != 15
            ):
                raise ValueError("ready drawing preparation has incomplete pins")
            for row in rows:
                _validate_pin_integrity(row)
            stored_text = preparation.readiness_summary
            stored_updated_at = preparation.updated_at
            preparation_id = preparation.id

        try:
            stored_summary = json.loads(stored_text)
            stored_fetched_at = datetime.fromisoformat(
                stored_summary["target_fetched_at"]
            )
            stored_hash = stored_summary["probability_input_sha256"]
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("invalid stored ready preparation evidence") from error
        if (
            not isinstance(stored_summary, dict)
            or not isinstance(stored_hash, str)
            or stored_fetched_at.tzinfo is None
        ):
            raise ValueError("invalid stored ready preparation evidence")
        if incoming_fetched_at < stored_fetched_at:
            raise ValueError("older probability evidence cannot replace newer evidence")
        if incoming_fetched_at == stored_fetched_at:
            if incoming_hash != stored_hash:
                raise ValueError("conflicting probability evidence at equal timestamp")
            return

        refreshed_summary = dict(stored_summary)
        refreshed_summary["probability_input_sha256"] = incoming_hash
        refreshed_summary["target_fetched_at"] = summary["target_fetched_at"]
        refreshed_text = json.dumps(
            refreshed_summary,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        with session_factory.begin() as session:
            result = session.execute(
                update(DrawingPreparation)
                .where(
                    DrawingPreparation.id == preparation_id,
                    DrawingPreparation.readiness_summary == stored_text,
                    DrawingPreparation.updated_at == stored_updated_at,
                )
                .values(
                    readiness_summary=refreshed_text,
                    updated_at=_utc_now(),
                )
            )
            if result.rowcount == 1:
                return


def publish_drawing_preparation(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_number: int | None,
    drawing_fingerprint: str,
    provider: str,
    status: str,
    unresolved_event_orders: tuple[int, ...],
    eligibility_status: str,
    readiness_summary: str,
    pin_specs: tuple[Mapping[str, Any], ...] = (),
) -> tuple[DrawingEventPinRecord, ...]:
    """Atomically publish either diagnostics only or one complete ready pin set."""
    if status not in {"ready", "unresolved"}:
        raise ValueError("preparation status must be ready or unresolved")
    if status == "ready":
        if len(pin_specs) != 15:
            raise ValueError("ready preparation requires exactly 15 pins")
        if tuple(sorted(int(spec["event_order"]) for spec in pin_specs)) != tuple(
            range(15)
        ):
            raise ValueError("ready preparation requires event orders 0 through 14")
        if len({str(spec["provider_fixture_id"]) for spec in pin_specs}) != 15:
            raise ValueError("ready preparation reuses a provider fixture")
    elif pin_specs:
        raise ValueError("unresolved preparation cannot publish pins")

    now = _utc_now()
    with session_factory.begin() as session:
        stale_pins = tuple(
            session.scalars(
                select(DrawingEventPin).where(
                    DrawingEventPin.drawing_id == drawing_id,
                    DrawingEventPin.provider == provider,
                    DrawingEventPin.status == "valid",
                    DrawingEventPin.drawing_fingerprint != drawing_fingerprint,
                )
            )
        )
        for row in stale_pins:
            _validate_pin_integrity(row)
            row.status = "invalidated"
            row.invalidated_at = now
            row.invalidation_reason = "drawing fingerprint changed"
        for row in session.scalars(
            select(DrawingPreparation).where(
                DrawingPreparation.drawing_id == drawing_id,
                DrawingPreparation.provider == provider,
                DrawingPreparation.drawing_fingerprint != drawing_fingerprint,
                DrawingPreparation.status != "invalidated",
            )
        ):
            row.status = "invalidated"
            row.updated_at = now

        preparation = session.scalar(
            select(DrawingPreparation).where(
                DrawingPreparation.drawing_id == drawing_id,
                DrawingPreparation.drawing_fingerprint == drawing_fingerprint,
                DrawingPreparation.provider == provider,
            )
        )
        if preparation is not None and preparation.status == "ready":
            if status != "ready" or preparation.readiness_summary != readiness_summary:
                raise ValueError("conflicting immutable ready drawing preparation")
            rows = tuple(
                session.scalars(
                    select(DrawingEventPin)
                    .where(
                        DrawingEventPin.drawing_id == drawing_id,
                        DrawingEventPin.drawing_fingerprint == drawing_fingerprint,
                        DrawingEventPin.provider == provider,
                        DrawingEventPin.status == "valid",
                    )
                    .order_by(DrawingEventPin.event_order)
                )
            )
            if len(rows) != 15:
                raise ValueError("ready drawing preparation has incomplete pins")
            expected = tuple(_pin_content_from_spec(spec) for spec in pin_specs)
            if tuple(_pin_content(row) for row in rows) != expected:
                raise ValueError("conflicting immutable ready drawing pins")
            return tuple(_pin_record(row) for row in rows)

        # Phase-1 interrupted runs may have left partial immutable rows. They were
        # never authoritative because no ready preparation existed.
        session.execute(
            delete(DrawingEventPin).where(
                DrawingEventPin.drawing_id == drawing_id,
                DrawingEventPin.drawing_fingerprint == drawing_fingerprint,
                DrawingEventPin.provider == provider,
            )
        )
        if status == "unresolved":
            if preparation is None:
                preparation = DrawingPreparation(
                    drawing_id=drawing_id,
                    drawing_number=drawing_number,
                    drawing_fingerprint=drawing_fingerprint,
                    provider=provider,
                    status="unresolved",
                    mapped_count=0,
                    unresolved_event_orders=json.dumps(unresolved_event_orders),
                    eligibility_status=eligibility_status,
                    readiness_summary=readiness_summary,
                    created_at=now,
                    updated_at=now,
                )
                session.add(preparation)
            else:
                preparation.drawing_number = drawing_number
                preparation.status = "unresolved"
                preparation.mapped_count = 0
                preparation.unresolved_event_orders = json.dumps(
                    unresolved_event_orders
                )
                preparation.eligibility_status = eligibility_status
                preparation.readiness_summary = readiness_summary
                preparation.updated_at = now
            session.flush()
            return ()

        rows: list[DrawingEventPin] = []
        for spec in pin_specs:
            content = _pin_content_from_spec(spec)
            for team_id in (
                content["canonical_home_team_id"],
                content["canonical_away_team_id"],
            ):
                if session.get(TeamEntity, team_id) is None:
                    raise ValueError("canonical team does not exist")
            row = DrawingEventPin(
                **{
                    **content,
                    "provenance": _canonical_json(
                        content["provenance"], "provenance"
                    ),
                },
                pin_hash=_sha256(content),
                status="valid",
                created_at=now,
                invalidated_at=None,
                invalidation_reason=None,
            )
            session.add(row)
            rows.append(row)
        if preparation is None:
            preparation = DrawingPreparation(
                drawing_id=drawing_id,
                drawing_number=drawing_number,
                drawing_fingerprint=drawing_fingerprint,
                provider=provider,
                status="ready",
                mapped_count=15,
                unresolved_event_orders="[]",
                eligibility_status=eligibility_status,
                readiness_summary=readiness_summary,
                created_at=now,
                updated_at=now,
            )
            session.add(preparation)
        else:
            preparation.drawing_number = drawing_number
            preparation.status = "ready"
            preparation.mapped_count = 15
            preparation.unresolved_event_orders = "[]"
            preparation.eligibility_status = eligibility_status
            preparation.readiness_summary = readiness_summary
            preparation.updated_at = now
        session.flush()
        return tuple(_pin_record(row) for row in rows)


def enqueue_review(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: int | str,
    event_order: int,
    provider: str,
    sport: str,
    target_home_team: str,
    target_away_team: str,
    context: Any,
    candidate_evidence: Any,
    resolution_reason: str = "unspecified resolution",
) -> TeamReviewRecord:
    identity = _validated_event_identity(
        drawing_id,
        drawing_fingerprint,
        target_event_id,
        event_order,
        provider,
    )
    sport = _required_text(sport, "sport")
    target_home_team = _required_text(target_home_team, "target_home_team")
    target_away_team = _required_text(target_away_team, "target_away_team")
    context_text = _canonical_json(context, "context")
    resolution_reason = _required_text(resolution_reason, "resolution_reason")
    evidence_text = _canonical_json(candidate_evidence, "candidate_evidence")
    matching_hash = _sha256(
        {
            "identity": identity,
            "sport": sport,
            "target_home_team": target_home_team,
            "target_away_team": target_away_team,
            "context": json.loads(context_text),
            "resolution_reason": resolution_reason,
            "candidate_evidence": json.loads(evidence_text),
        }
    )

    with session_factory.begin() as session:
        row = session.scalar(_review_identity_query(*identity))
        now = _utc_now()
        if row is None:
            row = TeamRegistryReview(
                drawing_id=identity[0],
                drawing_fingerprint=identity[1],
                target_event_id=identity[2],
                event_order=identity[3],
                provider=identity[4],
                sport=sport,
                target_home_team=target_home_team,
                target_away_team=target_away_team,
                target_home_normalized=normalize_team_name(target_home_team),
                target_away_normalized=normalize_team_name(target_away_team),
                context=context_text,
                resolution_reason=resolution_reason,
                candidate_evidence=evidence_text,
                matching_hash=matching_hash,
                status="pending",
                resolution_home_team_id=None,
                resolution_away_team_id=None,
                resolution_provenance=None,
                created_at=now,
                updated_at=now,
                resolved_at=None,
            )
            session.add(row)
            session.flush()
        elif row.matching_hash != matching_hash:
            if row.status != "pending":
                raise ValueError("resolved review cannot be replaced")
            row.sport = sport
            row.target_home_team = target_home_team
            row.target_away_team = target_away_team
            row.target_home_normalized = normalize_team_name(target_home_team)
            row.target_away_normalized = normalize_team_name(target_away_team)
            row.context = context_text
            row.resolution_reason = resolution_reason
            row.candidate_evidence = evidence_text
            row.matching_hash = matching_hash
            row.updated_at = now
            session.flush()
        return _review_record(row)


def resolve_review(
    session_factory: Any,
    *,
    review_id: int,
    status: str,
    resolution_provenance: Any,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
) -> TeamReviewRecord:
    review_id = _positive_integer(review_id, "review_id")
    if status not in {"resolved", "rejected"}:
        raise ValueError("status must be resolved or rejected")
    provenance_text = _canonical_json(
        resolution_provenance, "resolution_provenance"
    )
    if status == "resolved":
        home_team_id = _positive_integer(home_team_id, "home_team_id")
        away_team_id = _positive_integer(away_team_id, "away_team_id")
    elif home_team_id is not None or away_team_id is not None:
        raise ValueError("rejected review cannot have resolved team IDs")

    with session_factory.begin() as session:
        row = session.get(TeamRegistryReview, review_id)
        if row is None:
            raise ValueError("review does not exist")
        if status == "resolved":
            for team_id in (home_team_id, away_team_id):
                if session.get(TeamEntity, team_id) is None:
                    raise ValueError("resolved team does not exist")
        requested = (status, home_team_id, away_team_id, provenance_text)
        current = (
            row.status,
            row.resolution_home_team_id,
            row.resolution_away_team_id,
            row.resolution_provenance,
        )
        if row.status != "pending":
            if requested != current:
                raise ValueError("review resolution is immutable")
            return _review_record(row)
        now = _utc_now()
        row.status = status
        row.resolution_home_team_id = home_team_id
        row.resolution_away_team_id = away_team_id
        row.resolution_provenance = provenance_text
        row.updated_at = now
        row.resolved_at = now
        session.flush()
        return _review_record(row)


def write_pin(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: int | str,
    event_order: int,
    provider: str,
    canonical_home_team_id: int,
    canonical_away_team_id: int,
    provider_home_team_id: str,
    provider_away_team_id: str,
    provider_fixture_id: str,
    starts_at: str | datetime | None,
    provenance: Any,
    collection_id: str | None = None,
    pin_hash: str | None = None,
) -> DrawingEventPinRecord:
    identity = _validated_event_identity(
        drawing_id,
        drawing_fingerprint,
        target_event_id,
        event_order,
        provider,
    )
    canonical_home_team_id = _positive_integer(
        canonical_home_team_id, "canonical_home_team_id"
    )
    canonical_away_team_id = _positive_integer(
        canonical_away_team_id, "canonical_away_team_id"
    )
    provider_home_team_id = _required_text(
        provider_home_team_id, "provider_home_team_id"
    )
    provider_away_team_id = _required_text(
        provider_away_team_id, "provider_away_team_id"
    )
    provider_fixture_id = _required_text(provider_fixture_id, "provider_fixture_id")
    starts_at = _optional_datetime(starts_at, "starts_at")
    collection_id = _optional_identifier(collection_id, "collection_id")
    provenance_text = _canonical_json(provenance, "provenance")
    content = {
        "drawing_id": identity[0],
        "drawing_fingerprint": identity[1],
        "target_event_id": identity[2],
        "event_order": identity[3],
        "provider": identity[4],
        "canonical_home_team_id": canonical_home_team_id,
        "canonical_away_team_id": canonical_away_team_id,
        "provider_home_team_id": provider_home_team_id,
        "provider_away_team_id": provider_away_team_id,
        "provider_fixture_id": provider_fixture_id,
        "starts_at": starts_at,
        "collection_id": collection_id,
        "provenance": json.loads(provenance_text),
    }
    calculated_hash = _sha256(content)
    if pin_hash is not None and pin_hash != calculated_hash:
        raise ValueError("pin_hash does not match pin content")

    with session_factory.begin() as session:
        for team_id in (canonical_home_team_id, canonical_away_team_id):
            if session.get(TeamEntity, team_id) is None:
                raise ValueError("canonical team does not exist")
        row = session.scalar(_pin_identity_query(*identity))
        if row is not None:
            if _pin_content(row) != content or row.pin_hash != calculated_hash:
                raise ValueError("conflicting pin content")
            return _pin_record(row)
        row = DrawingEventPin(
            **{**content, "provenance": provenance_text},
            pin_hash=calculated_hash,
            status="valid",
            created_at=_utc_now(),
            invalidated_at=None,
            invalidation_reason=None,
        )
        session.add(row)
        session.flush()
        return _pin_record(row)


def load_pin(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: int | str,
    event_order: int,
    provider: str,
    include_invalidated: bool = False,
) -> DrawingEventPinRecord | None:
    identity = _validated_event_identity(
        drawing_id,
        drawing_fingerprint,
        target_event_id,
        event_order,
        provider,
    )
    if not isinstance(include_invalidated, bool):
        raise ValueError("include_invalidated must be a boolean")
    with session_factory() as session:
        row = session.scalar(_pin_identity_query(*identity))
        if row is None or (row.status != "valid" and not include_invalidated):
            return None
        _validate_pin_integrity(row)
        return _pin_record(row)


def invalidate_pin(
    session_factory: Any,
    *,
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: int | str,
    event_order: int,
    provider: str,
    reason: str,
) -> DrawingEventPinRecord | None:
    identity = _validated_event_identity(
        drawing_id,
        drawing_fingerprint,
        target_event_id,
        event_order,
        provider,
    )
    reason = _required_text(reason, "reason")
    with session_factory.begin() as session:
        row = session.scalar(_pin_identity_query(*identity))
        if row is None:
            return None
        _validate_pin_integrity(row)
        if row.status == "invalidated":
            if row.invalidation_reason != reason:
                raise ValueError("pin invalidation is immutable")
            return _pin_record(row)
        if row.status != "valid":
            raise ValueError("pin has an invalid status")
        row.status = "invalidated"
        row.invalidated_at = _utc_now()
        row.invalidation_reason = reason
        session.flush()
        return _pin_record(row)


def _validated_event_identity(
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: int | str,
    event_order: int,
    provider: str,
) -> tuple[int, str, str, int, str]:
    drawing_id = _positive_integer(drawing_id, "drawing_id")
    drawing_fingerprint = _required_text(
        drawing_fingerprint, "drawing_fingerprint"
    )
    if not isinstance(target_event_id, (int, str)) or isinstance(
        target_event_id, bool
    ):
        raise ValueError("target_event_id must be an integer or string")
    target_event_id = _required_text(str(target_event_id), "target_event_id")
    if (
        not isinstance(event_order, int)
        or isinstance(event_order, bool)
        or event_order < 0
    ):
        raise ValueError("event_order must be a non-negative integer")
    provider = _required_text(provider, "provider")
    return drawing_id, drawing_fingerprint, target_event_id, event_order, provider


def _review_identity_query(
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: str,
    event_order: int,
    provider: str,
) -> Any:
    return select(TeamRegistryReview).where(
        TeamRegistryReview.drawing_id == drawing_id,
        TeamRegistryReview.drawing_fingerprint == drawing_fingerprint,
        TeamRegistryReview.target_event_id == target_event_id,
        TeamRegistryReview.event_order == event_order,
        TeamRegistryReview.provider == provider,
    )


def _pin_identity_query(
    drawing_id: int,
    drawing_fingerprint: str,
    target_event_id: str,
    event_order: int,
    provider: str,
) -> Any:
    return select(DrawingEventPin).where(
        DrawingEventPin.drawing_id == drawing_id,
        DrawingEventPin.drawing_fingerprint == drawing_fingerprint,
        DrawingEventPin.target_event_id == target_event_id,
        DrawingEventPin.event_order == event_order,
        DrawingEventPin.provider == provider,
    )


def _pin_content(row: DrawingEventPin) -> dict[str, Any]:
    return {
        "drawing_id": row.drawing_id,
        "drawing_fingerprint": row.drawing_fingerprint,
        "target_event_id": row.target_event_id,
        "event_order": row.event_order,
        "provider": row.provider,
        "canonical_home_team_id": row.canonical_home_team_id,
        "canonical_away_team_id": row.canonical_away_team_id,
        "provider_home_team_id": row.provider_home_team_id,
        "provider_away_team_id": row.provider_away_team_id,
        "provider_fixture_id": row.provider_fixture_id,
        "starts_at": row.starts_at,
        "collection_id": row.collection_id,
        "provenance": json.loads(row.provenance),
    }


def _pin_content_from_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    identity = _validated_event_identity(
        spec.get("drawing_id"),
        spec.get("drawing_fingerprint"),
        spec.get("target_event_id"),
        spec.get("event_order"),
        spec.get("provider"),
    )
    return {
        "drawing_id": identity[0],
        "drawing_fingerprint": identity[1],
        "target_event_id": identity[2],
        "event_order": identity[3],
        "provider": identity[4],
        "canonical_home_team_id": _positive_integer(
            spec.get("canonical_home_team_id"), "canonical_home_team_id"
        ),
        "canonical_away_team_id": _positive_integer(
            spec.get("canonical_away_team_id"), "canonical_away_team_id"
        ),
        "provider_home_team_id": _required_text(
            spec.get("provider_home_team_id"), "provider_home_team_id"
        ),
        "provider_away_team_id": _required_text(
            spec.get("provider_away_team_id"), "provider_away_team_id"
        ),
        "provider_fixture_id": _required_text(
            spec.get("provider_fixture_id"), "provider_fixture_id"
        ),
        "starts_at": _optional_datetime(spec.get("starts_at"), "starts_at"),
        "collection_id": _optional_identifier(
            spec.get("collection_id"), "collection_id"
        ),
        "provenance": json.loads(
            _canonical_json(spec.get("provenance"), "provenance")
        ),
    }


def _validate_pin_integrity(row: DrawingEventPin) -> None:
    try:
        calculated = _sha256(_pin_content(row))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid pin provenance") from error
    if row.pin_hash != calculated:
        raise ValueError("pin content hash mismatch")


def _team_record(row: TeamEntity) -> TeamEntityRecord:
    return TeamEntityRecord(
        id=row.id,
        sport=row.sport,
        canonical_name=row.canonical_name,
        normalized_name=row.normalized_name,
        transliterated_name=row.transliterated_name,
        country=row.country,
        context=row.context,
        created_at=row.created_at,
    )


def _reviewed_alias_record(
    row: TeamAlias, team: TeamEntity
) -> ReviewedTeamAlias:
    if not row.reviewed or row.reviewer is None or row.reviewed_at is None:
        raise ValueError("alias is not reviewed")
    return ReviewedTeamAlias(
        id=row.id,
        team=_team_record(team),
        alias=row.alias,
        normalized_alias=row.normalized_alias,
        transliterated_alias=row.transliterated_alias,
        source=row.source,
        provider=row.provider,
        country=row.country,
        context=row.context,
        provider_team_id=row.provider_team_id,
        provenance=json.loads(row.provenance),
        confidence=row.confidence,
        reviewer=row.reviewer,
        reviewed_at=row.reviewed_at,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _review_record(row: TeamRegistryReview) -> TeamReviewRecord:
    return TeamReviewRecord(
        id=row.id,
        drawing_id=row.drawing_id,
        drawing_fingerprint=row.drawing_fingerprint,
        target_event_id=row.target_event_id,
        event_order=row.event_order,
        provider=row.provider,
        sport=row.sport,
        target_home_team=row.target_home_team,
        target_away_team=row.target_away_team,
        context=json.loads(row.context),
        resolution_reason=row.resolution_reason,
        candidate_evidence=json.loads(row.candidate_evidence),
        matching_hash=row.matching_hash,
        status=row.status,
        resolution_home_team_id=row.resolution_home_team_id,
        resolution_away_team_id=row.resolution_away_team_id,
        resolution_provenance=(
            None
            if row.resolution_provenance is None
            else json.loads(row.resolution_provenance)
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
    )


def _pin_record(row: DrawingEventPin) -> DrawingEventPinRecord:
    _validate_pin_integrity(row)
    return DrawingEventPinRecord(
        id=row.id,
        drawing_id=row.drawing_id,
        drawing_fingerprint=row.drawing_fingerprint,
        target_event_id=row.target_event_id,
        event_order=row.event_order,
        provider=row.provider,
        canonical_home_team_id=row.canonical_home_team_id,
        canonical_away_team_id=row.canonical_away_team_id,
        provider_home_team_id=row.provider_home_team_id,
        provider_away_team_id=row.provider_away_team_id,
        provider_fixture_id=row.provider_fixture_id,
        starts_at=row.starts_at,
        collection_id=row.collection_id,
        provenance=json.loads(row.provenance),
        pin_hash=row.pin_hash,
        status=row.status,
        created_at=row.created_at,
        invalidated_at=row.invalidated_at,
        invalidation_reason=row.invalidation_reason,
    )


def _canonical_json(value: Any, field_name: str) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be JSON serializable") from error
    if value is None or isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{field_name} must be structured JSON")
    return encoded


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_datetime(value: str | datetime | None, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{field_name} must be ISO datetime text") from error
    else:
        raise ValueError(f"{field_name} must be a datetime or ISO datetime text")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.isoformat()


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value.strip()


def _optional_context(value: str | None, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    return value.strip()


def _country_context_equal(left: str, right: str) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    return countries_equivalent(left, right)


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _positive_integer(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _confidence(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError("confidence must be from 0 through 1")
    return float(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Concise aliases for callers that use repository terminology.
create_team = upsert_team_entity
lookup_provider_team = lookup_reviewed_alias_by_provider_id
