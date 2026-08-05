from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from toto_ai.external_odds.domain import TargetDrawing, TargetEvent
from toto_ai.external_odds.matching import normalize_team_name
from toto_ai.external_odds.team_registry import transliterate_team_name

SCHEDULE_EVIDENCE_SCHEMA_VERSION = 1
DEFAULT_SCHEDULE_EVIDENCE_PATH = Path("data/schedule-evidence/ledger.json")
_MOSCOW = ZoneInfo("Europe/Moscow")

ResolutionState = Literal[
    "RESOLVED",
    "REVIEW_REQUIRED",
    "SOURCE_MISSING",
    "SOURCE_FAILED",
    "CONFLICT",
    "STALE",
]


@dataclass(frozen=True)
class EvidenceClaim:
    source_name: str
    role: Literal["official", "independent"]
    source_url: str


@dataclass(frozen=True)
class ScheduleObservation:
    observation_id: str
    sport: str
    gender_age_class: str
    competition_aliases: tuple[str, ...]
    home_entity: str
    home_aliases: tuple[str, ...]
    away_entity: str
    away_aliases: tuple[str, ...]
    starts_at: datetime
    status: Literal["scheduled"]
    conditional: bool
    reviewer: str
    reviewed_at: datetime
    review_document: Path
    review_document_sha256: str
    claims: tuple[EvidenceClaim, ...]
    semantic_hash: str


@dataclass(frozen=True)
class ScheduleEvidenceLedger:
    path: Path
    generated_at: datetime
    semantic_hash: str
    observations: tuple[ScheduleObservation, ...]


@dataclass(frozen=True)
class EvidenceResolution:
    state: ResolutionState
    reason: str
    observation: ScheduleObservation | None = None
    confidence: Literal["none", "review", "high"] = "none"
    orientation: Literal["same", "reversed"] | None = None


def load_schedule_evidence_ledger(path: Path) -> ScheduleEvidenceLedger:
    """Load reusable, reviewed schedule evidence with local hash verification."""
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("schedule evidence ledger is unreadable") from error
    if set(raw) != {"schema_version", "generated_at", "observations"}:
        raise ValueError("schedule evidence ledger fields are invalid")
    if raw["schema_version"] != SCHEDULE_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("schedule evidence ledger schema_version must be 1")
    generated_at = _utc(raw["generated_at"], "generated_at")
    rows = raw["observations"]
    if not isinstance(rows, list):
        raise ValueError("schedule evidence observations must be a list")
    observations = tuple(_parse_observation(row, path.parent) for row in rows)
    identities = tuple(item.observation_id for item in observations)
    if len(identities) != len(set(identities)):
        raise ValueError("schedule evidence observation_id values must be unique")
    canonical = {
        "schema_version": SCHEDULE_EVIDENCE_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "observations": [item.semantic_hash for item in observations],
    }
    return ScheduleEvidenceLedger(
        path=path,
        generated_at=generated_at,
        semantic_hash=_sha256_json(canonical),
        observations=observations,
    )


def ingest_reviewed_observation(
    path: Path,
    observation: Mapping[str, object],
) -> ScheduleEvidenceLedger:
    """Append one fully reviewed observation after validating the whole ledger.

    This is intentionally not an alias-learning API.  Callers must supply the
    reviewer, hash-checked review document and authoritative HTTPS claims.  A
    repeated byte-equivalent observation is idempotent; changing an existing
    observation ID is rejected.
    """
    path = Path(path).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("schedule evidence ledger is unreadable") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("observations"), list):
        raise ValueError("schedule evidence ledger fields are invalid")
    observation_id = _text(observation.get("observation_id"), "observation_id")
    existing = tuple(
        item
        for item in raw["observations"]
        if isinstance(item, dict) and item.get("observation_id") == observation_id
    )
    candidate = dict(observation)
    if existing:
        if len(existing) != 1 or existing[0] != candidate:
            raise ValueError("schedule evidence observation_id is immutable")
        return load_schedule_evidence_ledger(path)
    raw["observations"].append(candidate)
    temporary = path.with_name(f".{path.name}.validated.tmp")
    if temporary.exists():
        raise ValueError("schedule evidence temporary file already exists")
    try:
        temporary.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        load_schedule_evidence_ledger(temporary)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return load_schedule_evidence_ledger(path)


def drawing_schedule_dates(
    target: TargetDrawing, *, maximum_span_days: int = 5
) -> tuple[date, ...]:
    """Return UTC request dates covering the bounded Moscow drawing window."""
    if not 1 <= maximum_span_days <= 5:
        raise ValueError("maximum_span_days must be from 1 through 5")
    known = tuple(event.starts_at for event in target.events if event.starts_at)
    local_first = target.deadline.astimezone(_MOSCOW).date()
    # A single missing start means that the drawing can still contain a late
    # fixture.  Query the complete bounded drawing window instead of deriving
    # a one-day window from the few starts TotoBrief happened to publish.
    if len(known) != len(target.events):
        local_end_date = local_first + timedelta(days=maximum_span_days)
    else:
        last_known = max(
            (value.astimezone(_MOSCOW).date() for value in known),
            default=local_first,
        )
        local_last = min(
            max(last_known, local_first),
            local_first + timedelta(days=maximum_span_days),
        )
        local_end_date = local_last + timedelta(days=1)
    local_start = datetime.combine(local_first, datetime.min.time(), tzinfo=_MOSCOW)
    local_end = datetime.combine(
        local_end_date,
        datetime.min.time(),
        tzinfo=_MOSCOW,
    )
    first = local_start.astimezone(timezone.utc).date()
    last = (local_end - timedelta(microseconds=1)).astimezone(timezone.utc).date()
    return tuple(
        first + timedelta(days=offset) for offset in range((last - first).days + 1)
    )


def resolve_schedule_evidence(
    target: TargetEvent,
    ledger: ScheduleEvidenceLedger,
    *,
    evaluated_at: datetime,
    maximum_age: timedelta = timedelta(days=30),
    maximum_span_days: int = 5,
    start_tolerance: timedelta = timedelta(minutes=5),
    source_coverage: Mapping[date, Literal["success", "missing", "failed"]]
    | None = None,
) -> EvidenceResolution:
    """Resolve only exact reviewed identities; fuzzy similarity is never executable."""
    evaluated_at = _utc_datetime(evaluated_at, "evaluated_at")
    if maximum_age <= timedelta(0) or start_tolerance < timedelta(0):
        raise ValueError("evidence age/tolerance values are invalid")
    target_class = gender_age_class(target)
    home_entities = _matching_entities(
        target.home_team,
        target.home_team_en,
        ledger,
        sport=target.sport,
        gender_age_class=target_class,
    )
    away_entities = _matching_entities(
        target.away_team,
        target.away_team_en,
        ledger,
        sport=target.sport,
        gender_age_class=target_class,
    )
    if len(home_entities) > 1 or len(away_entities) > 1:
        return EvidenceResolution(
            "CONFLICT",
            "exact normalized alias belongs to multiple canonical entities",
        )
    identity_matches: list[tuple[ScheduleObservation, Literal["same", "reversed"]]] = []
    stale = False
    for observation in ledger.observations:
        if observation.sport != target.sport:
            continue
        if observation.gender_age_class != target_class:
            continue
        same = (
            observation.home_entity in home_entities
            and observation.away_entity in away_entities
        )
        reversed_pair = (
            observation.home_entity in away_entities
            and observation.away_entity in home_entities
        )
        if not same and not reversed_pair:
            continue
        if not _competition_compatible(
            target.championship, observation.competition_aliases
        ):
            continue
        if observation.conditional:
            continue
        if not _time_compatible(
            target,
            observation.starts_at,
            maximum_span_days=maximum_span_days,
            tolerance=start_tolerance,
        ):
            continue
        if evaluated_at - observation.reviewed_at > maximum_age:
            stale = True
            continue
        if source_coverage is not None:
            coverage = source_coverage.get(observation.starts_at.date(), "missing")
            if coverage == "failed":
                return EvidenceResolution(
                    "SOURCE_FAILED",
                    "relevant evidence-source date failed",
                )
            if coverage != "success":
                return EvidenceResolution(
                    "SOURCE_MISSING",
                    "relevant evidence-source date is missing",
                )
        identity_matches.append(
            (observation, "same" if same else "reversed")
        )
    if stale and not identity_matches:
        return EvidenceResolution("STALE", "matching reviewed evidence is stale")
    unique = {
        (
            item.home_entity,
            item.away_entity,
            item.starts_at,
            item.gender_age_class,
            orientation,
        ): (item, orientation)
        for item, orientation in identity_matches
    }
    if len(unique) > 1:
        return EvidenceResolution(
            "CONFLICT", "reviewed evidence has conflicting exact schedules"
        )
    if len(unique) == 1:
        observation, orientation = next(iter(unique.values()))
        return EvidenceResolution(
            "RESOLVED",
            "exact reusable reviewed identity and kickoff evidence",
            observation,
            "high",
            orientation,
        )
    if any(
        _fuzzy_pair_hint(target, item)
        for item in ledger.observations
        if item.sport == target.sport
    ):
        return EvidenceResolution(
            "REVIEW_REQUIRED",
            "only fuzzy or conditional evidence exists; exact identity is required",
        )
    return EvidenceResolution("SOURCE_MISSING", "no exact reviewed schedule evidence")


def gender_age_class(event: TargetEvent) -> str:
    text = " ".join(
        filter(
            None,
            (
                event.championship,
                event.home_team,
                event.away_team,
                event.home_team_en,
                event.away_team_en,
            ),
        )
    ).casefold()
    if any(
        token in text
        for token in (
            "(ж)",
            "(w)",
            " жен",
            "женщ",
            "women",
            "woman",
            "female",
            "femen",
            "damen",
        )
    ):
        return "women-senior"
    if any(token in text for token in ("u19", "u-19", "u21", "u-21", "мол", "youth")):
        return "men-youth"
    return "men-senior"


def _parse_observation(value: object, root: Path) -> ScheduleObservation:
    fields = {
        "observation_id",
        "sport",
        "gender_age_class",
        "competition_aliases",
        "home_entity",
        "home_aliases",
        "away_entity",
        "away_aliases",
        "starts_at",
        "status",
        "conditional",
        "reviewer",
        "reviewed_at",
        "review_document",
        "review_document_sha256",
        "claims",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("schedule evidence observation fields are invalid")
    claims = tuple(_parse_claim(item) for item in value["claims"])
    if not claims or not any(item.role == "official" for item in claims):
        raise ValueError("schedule evidence requires an official claim")
    document = (root / _text(value["review_document"], "review_document")).resolve()
    if root.resolve() not in document.parents:
        raise ValueError("review document escapes ledger directory")
    expected = _digest(value["review_document_sha256"], "review_document_sha256")
    try:
        actual = hashlib.sha256(document.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError("review document is unreadable") from error
    if actual != expected:
        raise ValueError("review document hash mismatch")
    starts_at = _utc(value["starts_at"], "starts_at")
    reviewed_at = _utc(value["reviewed_at"], "reviewed_at")
    if reviewed_at > starts_at:
        raise ValueError("reviewed_at must not be after kickoff")
    if value["status"] != "scheduled" or type(value["conditional"]) is not bool:
        raise ValueError("schedule evidence status/conditional is invalid")
    canonical = {**value, "claims": [item.__dict__ for item in claims]}
    return ScheduleObservation(
        observation_id=_text(value["observation_id"], "observation_id"),
        sport=_text(value["sport"], "sport"),
        gender_age_class=_text(value["gender_age_class"], "gender_age_class"),
        competition_aliases=_strings(
            value["competition_aliases"], "competition_aliases"
        ),
        home_entity=_text(value["home_entity"], "home_entity"),
        home_aliases=_strings(value["home_aliases"], "home_aliases"),
        away_entity=_text(value["away_entity"], "away_entity"),
        away_aliases=_strings(value["away_aliases"], "away_aliases"),
        starts_at=starts_at,
        status="scheduled",
        conditional=value["conditional"],
        reviewer=_text(value["reviewer"], "reviewer"),
        reviewed_at=reviewed_at,
        review_document=document,
        review_document_sha256=expected,
        claims=claims,
        semantic_hash=_sha256_json(canonical),
    )


def _parse_claim(value: object) -> EvidenceClaim:
    if not isinstance(value, dict) or set(value) != {
        "source_name",
        "role",
        "source_url",
    }:
        raise ValueError("schedule evidence claim fields are invalid")
    role = value["role"]
    if role not in {"official", "independent"}:
        raise ValueError("schedule evidence claim role is invalid")
    url = _text(value["source_url"], "source_url")
    if not url.startswith("https://"):
        raise ValueError("schedule evidence claim URL must use HTTPS")
    return EvidenceClaim(_text(value["source_name"], "source_name"), role, url)


def _matching_entities(
    primary: str,
    english: str | None,
    ledger: ScheduleEvidenceLedger,
    *,
    sport: str,
    gender_age_class: str,
) -> frozenset[str]:
    """Resolve an exact alias against all historical reviewed observations."""
    target_keys = {_name_key(primary)}
    if english:
        target_keys.add(_name_key(english))
    matched: set[str] = set()
    for observation in ledger.observations:
        if (
            observation.sport != sport
            or observation.gender_age_class != gender_age_class
        ):
            continue
        for entity, aliases in (
            (
                observation.home_entity,
                (*observation.home_aliases, observation.home_entity),
            ),
            (
                observation.away_entity,
                (*observation.away_aliases, observation.away_entity),
            ),
        ):
            if target_keys & {_name_key(alias) for alias in aliases}:
                matched.add(entity)
    return frozenset(matched)


def _name_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character for character in value if not unicodedata.combining(character)
    )
    value = value.casefold().translate(
        str.maketrans(
            {
                "ø": "o",
                "ł": "l",
                "ð": "d",
                "þ": "th",
                "æ": "ae",
                "œ": "oe",
                "ı": "i",
            }
        )
    )
    normalized = normalize_team_name(value)
    normalized = re.sub(
        r"^(?:f\s*c|f\s*k|c\s*f|s\s*c|afc|ac|cd|\u0444\u043a|\u0441\u043a)\s+",
        "",
        normalized,
    )
    normalized = re.sub(
        r"\s+(?:f\s*c|f\s*k|c\s*f|s\s*c|afc|ac|cd|\u0444\u043a|\u0441\u043a)$",
        "",
        normalized,
    )
    return re.sub(r"\s+", " ", transliterate_team_name(normalized)).strip()


def _competition_compatible(target: str, aliases: tuple[str, ...]) -> bool:
    target_key = _name_key(target)
    return any(
        _name_key(alias) in target_key or target_key in _name_key(alias)
        for alias in aliases
    )


def _time_compatible(
    target: TargetEvent,
    observed: datetime,
    *,
    maximum_span_days: int,
    tolerance: timedelta,
) -> bool:
    if target.starts_at is not None:
        return abs(target.starts_at - observed) <= tolerance
    return (
        target.deadline
        <= observed
        <= target.deadline + timedelta(days=maximum_span_days)
    )


def _fuzzy_pair_hint(target: TargetEvent, observation: ScheduleObservation) -> bool:
    home = set(_name_key(target.home_team).split())
    away = set(_name_key(target.away_team).split())
    return bool(
        home & set(_name_key(" ".join(observation.home_aliases)).split())
    ) and bool(away & set(_name_key(" ".join(observation.away_aliases)).split()))


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO datetime") from error
    return _utc_datetime(parsed, name)


def _utc_datetime(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    result = tuple(_text(item, name) for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must be unique")
    return result


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be sha256")
    return value


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
