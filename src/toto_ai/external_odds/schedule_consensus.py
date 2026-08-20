"""Fail-closed UEFA plus Sofascore schedule consensus promotion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceLedger,
    ingest_reviewed_observation,
    load_schedule_evidence_ledger,
)
from toto_ai.external_odds.schedule_source_collector import (
    _alias_compatible,
    _base_record,
    _canonical,
    _load_queue,
    _matching_events,
    _name_key,
    _parse_utc,
    _pretty,
    _safe_error,
    _team_aliases,
    _timestamp,
    _utc,
    _write_exact,
    _write_replace,
)

_UEFA_LIST_ENDPOINT = (
    "https://match.uefa.com/v5/matches?fromDate={from_date}&toDate={to_date}"
    "&order=ASC&offset={offset}&limit={limit}"
)
_UEFA_MATCH_ENDPOINT = "https://match.uefa.com/v5/matches/{match_id}/"
_SOFASCORE_SEARCH_ENDPOINT = "https://www.sofascore.com/api/v1/search/all?q={query}"
_SOFASCORE_EVENT_ENDPOINT = "https://www.sofascore.com/api/v1/event/{event_id}"
_MAX_DRAWING_SPAN = timedelta(days=5)
_PAGE_SIZE = 100
_MAX_PAGES = 10


@dataclass(frozen=True)
class ScheduleConsensusPromotion:
    status: str
    queue_sha256: str
    promoted_count: int
    existing_count: int
    unresolved_count: int
    records: tuple[dict[str, object], ...]
    report_path: Path
    ledger_semantic_hash: str


def promote_uefa_sofascore_consensus(
    queue_path: str | Path,
    *,
    output_dir: str | Path,
    schedule_evidence_ledger: str | Path,
    fetch_json: Callable[[str], object] | None = None,
    captured_at: datetime | None = None,
) -> ScheduleConsensusPromotion:
    """Promote only exact official/independent kickoff consensus.

    The UEFA date feed is authoritative discovery evidence.  A selected UEFA
    match is re-fetched by ID and must agree with one independently fetched
    Sofascore event on orientation and kickoff.  Any ambiguity, source error,
    status mismatch, or time conflict remains unresolved and cannot mutate the
    reviewed schedule ledger.
    """

    queue = _load_queue(Path(queue_path))
    observed = _utc(captured_at or datetime.now(timezone.utc))
    output = _safe_directory(Path(output_dir))
    ledger_path = Path(schedule_evidence_ledger).resolve()
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ValueError("schedule evidence ledger must be a regular file")
    ledger = load_schedule_evidence_ledger(ledger_path)
    fetch = fetch_json or _fetch_json
    deadline = _parse_utc(queue["identity"]["deadline"])
    records: list[dict[str, object]] = []

    try:
        official_events, official_listing_urls = _fetch_uefa_events(
            fetch,
            deadline=deadline,
        )
    except Exception as error:
        for row in queue["records"]:
            records.append(
                _base_record(row)
                | {
                    "status": "official_source_failed",
                    "captured_at": _timestamp(observed),
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
        return _finish(
            queue_path=Path(queue_path),
            queue=queue,
            records=records,
            output=output,
            ledger=ledger,
            official_listing_urls=(),
        )

    for row in queue["records"]:
        base = _base_record(row)
        matches = _matching_uefa_events(
            official_events,
            home=str(row["home_team"]),
            away=str(row["away_team"]),
            deadline=deadline,
        )
        if len(matches) != 1:
            records.append(
                base
                | {
                    "status": (
                        "official_not_found" if not matches else "official_conflict"
                    ),
                    "captured_at": _timestamp(observed),
                    "official_candidate_ids": [str(item.get("id")) for item in matches],
                    "ledger_promoted": False,
                }
            )
            continue
        listing_match = matches[0]
        match_id = str(listing_match["id"])
        official_url = _UEFA_MATCH_ENDPOINT.format(match_id=match_id)
        try:
            official = _require_mapping(fetch(official_url), "UEFA match")
            _validate_official_detail(
                listing_match,
                official,
                home=str(row["home_team"]),
                away=str(row["away_team"]),
                deadline=deadline,
            )
            official_start = _official_start(official)
            if observed >= official_start:
                raise ValueError("official evidence was captured at or after kickoff")
            home_aliases = _uefa_team_aliases(official["homeTeam"])
            away_aliases = _uefa_team_aliases(official["awayTeam"])
            search_query = " ".join(
                (
                    _english_team_name(official["homeTeam"]),
                    _english_team_name(official["awayTeam"]),
                )
            )
            search_url = _SOFASCORE_SEARCH_ENDPOINT.format(
                query=quote_plus(search_query)
            )
            search_payload = _require_mapping(fetch(search_url), "Sofascore search")
            independent_matches = _matching_events(
                search_payload,
                homes=home_aliases,
                aways=away_aliases,
                deadline=deadline,
            )
            if len(independent_matches) != 1:
                records.append(
                    base
                    | {
                        "status": (
                            "independent_not_found"
                            if not independent_matches
                            else "independent_conflict"
                        ),
                        "captured_at": _timestamp(observed),
                        "official_match_id": match_id,
                        "independent_candidate_ids": [
                            int(item["id"]) for item in independent_matches
                        ],
                        "ledger_promoted": False,
                    }
                )
                continue
            search_match = independent_matches[0]
            independent_start = datetime.fromtimestamp(
                int(search_match["startTimestamp"]), timezone.utc
            )
            if independent_start != official_start:
                records.append(
                    base
                    | {
                        "status": "kickoff_conflict",
                        "captured_at": _timestamp(observed),
                        "official_match_id": match_id,
                        "official_starts_at": _timestamp(official_start),
                        "independent_event_id": int(search_match["id"]),
                        "independent_starts_at": _timestamp(independent_start),
                        "ledger_promoted": False,
                    }
                )
                continue
            event_id = int(search_match["id"])
            independent_url = _SOFASCORE_EVENT_ENDPOINT.format(event_id=event_id)
            independent_payload = _require_mapping(
                fetch(independent_url), "Sofascore event"
            )
            independent = _require_mapping(
                independent_payload.get("event"), "Sofascore event entity"
            )
            _validate_independent_detail(
                search_match,
                independent,
                official_start=official_start,
                official_home_aliases=home_aliases,
                official_away_aliases=away_aliases,
            )
        except Exception as error:
            records.append(
                base
                | {
                    "status": "consensus_source_failed",
                    "captured_at": _timestamp(observed),
                    "official_match_id": match_id,
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
            continue

        try:
            existing = _find_existing_consensus(
                ledger,
                official_url=official_url,
                independent_url=independent_url,
                starts_at=official_start,
                home_aliases=home_aliases,
                away_aliases=away_aliases,
            )
        except ValueError as error:
            records.append(
                base
                | {
                    "status": "ledger_conflict",
                    "captured_at": _timestamp(observed),
                    "official_match_id": match_id,
                    "independent_event_id": event_id,
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
            continue
        if existing is not None:
            records.append(
                base
                | {
                    "status": "already_promoted",
                    "captured_at": _timestamp(observed),
                    "official_match_id": match_id,
                    "independent_event_id": event_id,
                    "starts_at": _timestamp(official_start),
                    "observation_id": existing.observation_id,
                    "ledger_promoted": False,
                }
            )
            continue

        official_snapshot, official_digest = _freeze_snapshot(
            ledger_path.parent,
            source="uefa",
            source_id=match_id,
            payload=official,
        )
        independent_snapshot, independent_digest = _freeze_snapshot(
            ledger_path.parent,
            source="sofascore",
            source_id=str(event_id),
            payload=independent_payload,
        )

        observation_id = f"uefa-match-{match_id}"
        review_path = ledger_path.parent / "reviews" / f"auto-{observation_id}.md"
        review = _render_review(
            row=row,
            observed=observed,
            official=official,
            independent=independent,
            official_url=official_url,
            independent_url=independent_url,
            official_snapshot=official_snapshot,
            official_digest=official_digest,
            independent_snapshot=independent_snapshot,
            independent_digest=independent_digest,
            ledger_root=ledger_path.parent,
        )
        review_path.parent.mkdir(parents=True, exist_ok=True)
        _write_exact(review_path, review.encode("utf-8"))
        observation = _observation(
            observation_id=observation_id,
            official=official,
            independent=independent,
            target_home=str(row["home_team"]),
            target_away=str(row["away_team"]),
            starts_at=official_start,
            observed=observed,
            review_path=review_path,
            ledger_root=ledger_path.parent,
            official_url=official_url,
            independent_url=independent_url,
        )
        try:
            ledger = ingest_reviewed_observation(ledger_path, observation)
        except Exception as error:
            records.append(
                base
                | {
                    "status": "ledger_rejected",
                    "captured_at": _timestamp(observed),
                    "official_match_id": match_id,
                    "independent_event_id": event_id,
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
            continue
        records.append(
            base
            | {
                "status": "promoted_exact_consensus",
                "captured_at": _timestamp(observed),
                "official_match_id": match_id,
                "independent_event_id": event_id,
                "starts_at": _timestamp(official_start),
                "observation_id": observation_id,
                "review_document": str(review_path.relative_to(ledger_path.parent)),
                "official_snapshot": str(
                    official_snapshot.relative_to(ledger_path.parent)
                ),
                "official_snapshot_sha256": official_digest,
                "independent_snapshot": str(
                    independent_snapshot.relative_to(ledger_path.parent)
                ),
                "independent_snapshot_sha256": independent_digest,
                "ledger_promoted": True,
            }
        )

    return _finish(
        queue_path=Path(queue_path),
        queue=queue,
        records=records,
        output=output,
        ledger=ledger,
        official_listing_urls=official_listing_urls,
    )


def _fetch_uefa_events(
    fetch: Callable[[str], object], *, deadline: datetime
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...]]:
    events: list[Mapping[str, Any]] = []
    urls: list[str] = []
    from_date = deadline.date().isoformat()
    to_date = (deadline + _MAX_DRAWING_SPAN).date().isoformat()
    for page in range(_MAX_PAGES):
        url = _UEFA_LIST_ENDPOINT.format(
            from_date=from_date,
            to_date=to_date,
            offset=page * _PAGE_SIZE,
            limit=_PAGE_SIZE,
        )
        urls.append(url)
        payload = fetch(url)
        if not isinstance(payload, list):
            raise ValueError("UEFA match listing must be an array")
        if any(not isinstance(item, dict) for item in payload):
            raise ValueError("UEFA match listing contains a non-object")
        events.extend(payload)
        if len(payload) < _PAGE_SIZE:
            return tuple(events), tuple(urls)
    raise ValueError("UEFA match listing exceeded the bounded page limit")


def _matching_uefa_events(
    events: Sequence[Mapping[str, Any]],
    *,
    home: str,
    away: str,
    deadline: datetime,
) -> tuple[Mapping[str, Any], ...]:
    home_key = _name_key(home)
    away_key = _name_key(away)
    matches = []
    for event in events:
        try:
            starts_at = _official_start(event)
            home_aliases = _uefa_team_aliases(event["homeTeam"])
            away_aliases = _uefa_team_aliases(event["awayTeam"])
            competition = _require_mapping(event["competition"], "UEFA competition")
        except (KeyError, TypeError, ValueError):
            continue
        if competition.get("sportsType") != "FOOTBALL":
            continue
        if event.get("status") not in {"UPCOMING", "SCHEDULED"}:
            continue
        if not deadline <= starts_at <= deadline + _MAX_DRAWING_SPAN:
            continue
        if home_key in {_name_key(value) for value in home_aliases} and away_key in {
            _name_key(value) for value in away_aliases
        }:
            matches.append(event)
    return tuple(matches)


def _validate_official_detail(
    listing: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    home: str,
    away: str,
    deadline: datetime,
) -> None:
    if str(detail.get("id")) != str(listing.get("id")):
        raise ValueError("UEFA match identity changed between listing and detail")
    if _official_start(detail) != _official_start(listing):
        raise ValueError("UEFA kickoff changed between listing and detail")
    if detail.get("status") not in {"UPCOMING", "SCHEDULED"}:
        raise ValueError("UEFA match is not scheduled")
    if not _matching_uefa_events(
        (detail,), home=home, away=away, deadline=deadline
    ):
        raise ValueError("UEFA match orientation or exact localized aliases changed")


def _validate_independent_detail(
    search: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    official_start: datetime,
    official_home_aliases: tuple[str, ...],
    official_away_aliases: tuple[str, ...],
) -> None:
    if int(detail.get("id", -1)) != int(search["id"]):
        raise ValueError("Sofascore identity changed between search and detail")
    if detail.get("status", {}).get("type") != "notstarted":
        raise ValueError("Sofascore event is not scheduled")
    start = datetime.fromtimestamp(int(detail["startTimestamp"]), timezone.utc)
    if start != official_start:
        raise ValueError("Sofascore event kickoff changed or conflicts with UEFA")
    home_aliases = _team_aliases(_require_mapping(detail["homeTeam"], "homeTeam"))
    away_aliases = _team_aliases(_require_mapping(detail["awayTeam"], "awayTeam"))
    if not any(
        _alias_compatible(value, home_aliases) for value in official_home_aliases
    ) or not any(
        _alias_compatible(value, away_aliases) for value in official_away_aliases
    ):
        raise ValueError("Sofascore orientation conflicts with UEFA")


def _official_start(event: Mapping[str, Any]) -> datetime:
    kickoff = _require_mapping(event["kickOffTime"], "UEFA kickOffTime")
    return _parse_utc(kickoff["dateTime"])


def _uefa_team_aliases(value: object) -> tuple[str, ...]:
    team = _require_mapping(value, "UEFA team")
    aliases = []
    international = team.get("internationalName")
    if isinstance(international, str) and international.strip():
        aliases.append(international.strip())
    translations = team.get("translations")
    if isinstance(translations, Mapping):
        for field in ("displayName", "displayOfficialName", "shortName"):
            values = translations.get(field)
            if isinstance(values, Mapping):
                aliases.extend(
                    str(item).strip()
                    for language, item in values.items()
                    if str(language).upper() in {"EN", "RU"}
                    if isinstance(item, str) and item.strip()
                )
    result = tuple(dict.fromkeys(aliases))
    if not result:
        raise ValueError("UEFA team has no names")
    return result


def _english_team_name(value: object) -> str:
    team = _require_mapping(value, "UEFA team")
    translations = team.get("translations")
    if isinstance(translations, Mapping):
        for field in ("displayOfficialName", "displayName", "shortName"):
            names = translations.get(field)
            if isinstance(names, Mapping):
                name = names.get("EN")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    name = team.get("internationalName")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("UEFA team has no English name")
    return name.strip()


def _competition_aliases(
    official: Mapping[str, Any], independent: Mapping[str, Any]
) -> list[str]:
    aliases = []
    competition = _require_mapping(official["competition"], "UEFA competition")
    metadata = competition.get("metaData")
    if isinstance(metadata, Mapping):
        name = metadata.get("name")
        if isinstance(name, str) and name.strip():
            aliases.append(name.strip())
    translations = competition.get("translations")
    if isinstance(translations, Mapping):
        for field in ("name", "prequalifyingName", "qualifyingName", "tournamentName"):
            values = translations.get(field)
            if isinstance(values, Mapping):
                aliases.extend(
                    str(item).strip()
                    for language, item in values.items()
                    if str(language).upper() in {"EN", "RU"}
                    if isinstance(item, str) and item.strip()
                )
    tournament = independent.get("tournament")
    if isinstance(tournament, Mapping):
        name = tournament.get("name")
        if isinstance(name, str) and name.strip():
            aliases.append(name.strip())
    result = list(dict.fromkeys(aliases))
    if not result:
        raise ValueError("schedule consensus has no competition aliases")
    return result


def _gender_age_class(official: Mapping[str, Any]) -> str:
    competition = _require_mapping(official["competition"], "UEFA competition")
    sex = str(competition.get("sex", "")).upper()
    age = str(competition.get("age", "")).upper()
    gender = "women" if sex == "FEMALE" else "men"
    level = "senior" if age == "ADULT" else "youth"
    return f"{gender}-{level}"


def _observation(
    *,
    observation_id: str,
    official: Mapping[str, Any],
    independent: Mapping[str, Any],
    target_home: str,
    target_away: str,
    starts_at: datetime,
    observed: datetime,
    review_path: Path,
    ledger_root: Path,
    official_url: str,
    independent_url: str,
) -> dict[str, object]:
    home_aliases = list(
        dict.fromkeys(
            (
                target_home,
                *_uefa_team_aliases(official["homeTeam"]),
                *_team_aliases(
                    _require_mapping(independent["homeTeam"], "homeTeam")
                ),
            )
        )
    )
    away_aliases = list(
        dict.fromkeys(
            (
                target_away,
                *_uefa_team_aliases(official["awayTeam"]),
                *_team_aliases(
                    _require_mapping(independent["awayTeam"], "awayTeam")
                ),
            )
        )
    )
    return {
        "observation_id": observation_id,
        "sport": "football",
        "gender_age_class": _gender_age_class(official),
        "competition_aliases": _competition_aliases(official, independent),
        "home_entity": _english_team_name(official["homeTeam"]),
        "home_aliases": home_aliases,
        "away_entity": _english_team_name(official["awayTeam"]),
        "away_aliases": away_aliases,
        "starts_at": _timestamp(starts_at),
        "status": "scheduled",
        "conditional": False,
        "reviewer": "automated-exact-consensus-v1",
        "reviewed_at": _timestamp(observed),
        "review_document": str(review_path.relative_to(ledger_root)),
        "review_document_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "claims": [
            {
                "source_name": "UEFA match feed",
                "role": "official",
                "source_url": official_url,
            },
            {
                "source_name": "Sofascore event",
                "role": "independent",
                "source_url": independent_url,
            },
        ],
    }


def _find_existing_consensus(
    ledger: ScheduleEvidenceLedger,
    *,
    official_url: str,
    independent_url: str,
    starts_at: datetime,
    home_aliases: tuple[str, ...],
    away_aliases: tuple[str, ...],
):
    matches = []
    for observation in ledger.observations:
        urls = {claim.source_url for claim in observation.claims}
        if official_url not in urls:
            continue
        if observation.starts_at != starts_at:
            raise ValueError("existing official observation has a conflicting kickoff")
        if independent_url not in urls:
            raise ValueError("existing official observation lacks the consensus source")
        if not any(
            _alias_compatible(value, observation.home_aliases)
            for value in home_aliases
        ) or not any(
            _alias_compatible(value, observation.away_aliases)
            for value in away_aliases
        ):
            raise ValueError(
                "existing official observation has conflicting orientation"
            )
        matches.append(observation)
    if len(matches) > 1:
        raise ValueError("multiple ledger observations claim the same UEFA match")
    return matches[0] if matches else None


def _freeze_snapshot(
    ledger_root: Path,
    *,
    source: str,
    source_id: str,
    payload: object,
) -> tuple[Path, str]:
    content = _canonical(payload) + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    root = _safe_directory(ledger_root / "snapshots" / "auto")
    path = root / f"{source}-{source_id}-{digest[:16]}.json"
    _write_exact(path, content)
    return path, digest


def _render_review(
    *,
    row: Mapping[str, Any],
    observed: datetime,
    official: Mapping[str, Any],
    independent: Mapping[str, Any],
    official_url: str,
    independent_url: str,
    official_snapshot: Path,
    official_digest: str,
    independent_snapshot: Path,
    independent_digest: str,
    ledger_root: Path,
) -> str:
    starts_at = _official_start(official)
    return "\n".join(
        (
            "# Automated exact schedule consensus: "
            f"{row['home_team']} — {row['away_team']}",
            "",
            f"Reviewed at **{_timestamp(observed)}** for TotoBrief drawing "
            f"{row['drawing_number']}, event #{int(row['event_order']) + 1}.",
            "",
            "## Determination",
            "",
            f"Scheduled kickoff: **{_timestamp(starts_at)}**.",
            "",
            "The official UEFA match and independently fetched Sofascore event "
            "agree exactly on home/away orientation and kickoff. The TotoBrief "
            "team names exactly match localized aliases published by UEFA. No "
            "fuzzy target match or guessed kickoff was promoted.",
            "",
            "## Sources",
            "",
            f"- official: UEFA match feed — {official_url}",
            f"- independent: Sofascore event — {independent_url}",
            "",
            "## Frozen snapshots",
            "",
            f"- `{official_snapshot.relative_to(ledger_root)}` — "
            f"SHA-256 `{official_digest}`",
            f"- `{independent_snapshot.relative_to(ledger_root)}` — "
            f"SHA-256 `{independent_digest}`",
            "",
            "This document was produced by deterministic reviewer "
            "`automated-exact-consensus-v1`; conflicting or incomplete source "
            "evidence remains fail-closed.",
            "",
        )
    )


def _finish(
    *,
    queue_path: Path,
    queue: Mapping[str, Any],
    records: list[dict[str, object]],
    output: Path,
    ledger: ScheduleEvidenceLedger,
    official_listing_urls: tuple[str, ...],
) -> ScheduleConsensusPromotion:
    promoted = sum(item["status"] == "promoted_exact_consensus" for item in records)
    existing = sum(item["status"] == "already_promoted" for item in records)
    unresolved = len(records) - promoted - existing
    status = (
        "CONSENSUS_PROMOTED"
        if promoted and not unresolved
        else "CONSENSUS_PARTIAL"
        if promoted or existing
        else "NO_PROMOTIONS"
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "queue_path": str(queue_path.resolve()),
        "queue_sha256": queue["queue_sha256"],
        "drawing_id": queue["identity"]["drawing_id"],
        "drawing_number": queue["identity"]["drawing_number"],
        "official_listing_urls": list(official_listing_urls),
        "promoted_count": promoted,
        "existing_count": existing,
        "unresolved_count": unresolved,
        "ledger_semantic_hash": ledger.semantic_hash,
        "records": records,
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    report_path = output / "schedule-consensus-promotion.json"
    _write_replace(report_path, _pretty(report))
    return ScheduleConsensusPromotion(
        status=status,
        queue_sha256=str(queue["queue_sha256"]),
        promoted_count=promoted,
        existing_count=existing,
        unresolved_count=unresolved,
        records=tuple(records),
        report_path=report_path,
        ledger_semantic_hash=ledger.semantic_hash,
    )


def _safe_directory(path: Path) -> Path:
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("schedule consensus output must be a regular directory")
    return path


def _require_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _fetch_json(url: str) -> object:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TotoAI-Schedule-Consensus/1.0",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)
