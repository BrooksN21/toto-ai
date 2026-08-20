"""Automatic, non-promoting public schedule-source candidate collection."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from toto_ai.external_odds.matching import normalize_team_name
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceLedger,
    load_schedule_evidence_ledger,
)
from toto_ai.external_odds.team_registry import transliterate_team_name

_SEARCH_ENDPOINT = "https://www.sofascore.com/api/v1/search/all?q={query}"
_MAX_DRAWING_SPAN = timedelta(days=5)


@dataclass(frozen=True)
class ScheduleSourceCollection:
    status: str
    queue_sha256: str
    candidate_count: int
    unresolved_count: int
    records: tuple[dict[str, object], ...]
    report_path: Path


def collect_schedule_source_candidates(
    queue_path: str | Path,
    *,
    output_dir: str | Path,
    fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
    captured_at: datetime | None = None,
    schedule_evidence_ledger: str | Path | None = None,
) -> ScheduleSourceCollection:
    """Collect immutable independent candidates without mutating the ledger.

    Sofascore is useful discovery evidence, but it is not an official league
    source.  Therefore successful rows remain non-promoting proposals and
    explicitly require an official source plus review before ledger ingestion.
    """

    queue = _load_queue(Path(queue_path))
    observed = _utc(captured_at or datetime.now(timezone.utc))
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("schedule source output cannot be a symlink")
    snapshots = output / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    fetch = fetch_json or _fetch_json
    deadline = _parse_utc(queue["identity"]["deadline"])
    records: list[dict[str, object]] = []
    ledger = _optional_ledger(schedule_evidence_ledger)

    for row in queue["records"]:
        target_home = str(row["home_team"])
        target_away = str(row["away_team"])
        canonical_homes = _ledger_canonical_names(ledger, target_home)
        canonical_aways = _ledger_canonical_names(ledger, target_away)
        historical_queries = tuple(
            f"{home} {away}"
            for home in canonical_homes
            for away in canonical_aways
        )
        queries = tuple(
            dict.fromkeys(
                (
                    f"{row['home_team']} {row['away_team']}",
                    *historical_queries,
                    " ".join(
                        (
                            transliterate_team_name(str(row["home_team"])),
                            transliterate_team_name(str(row["away_team"])),
                        )
                    ),
                )
            )
        )
        attempted_urls: list[str] = []
        matches: list[dict[str, Any]] = []
        selected_url: str | None = None
        snapshot_path: Path | None = None
        snapshot_sha256: str | None = None
        try:
            for query_index, query in enumerate(queries, start=1):
                url = _SEARCH_ENDPOINT.format(query=quote_plus(query))
                attempted_urls.append(url)
                payload = dict(fetch(url))
                snapshot_bytes = _canonical(payload) + b"\n"
                digest = hashlib.sha256(snapshot_bytes).hexdigest()
                snapshot_name = (
                    f"event-{int(row['event_order']) + 1:02d}-q{query_index}-"
                    f"sofascore-{digest[:16]}.json"
                )
                candidate_snapshot = snapshots / snapshot_name
                _write_exact(candidate_snapshot, snapshot_bytes)
                candidate_matches = _matching_events(
                    payload,
                    homes=(target_home, *canonical_homes),
                    aways=(target_away, *canonical_aways),
                    deadline=deadline,
                )
                if candidate_matches:
                    matches = candidate_matches
                    selected_url = url
                    snapshot_path = candidate_snapshot
                    snapshot_sha256 = digest
                    break
        except Exception as error:
            records.append(
                _base_record(row)
                | {
                    "status": "source_failed",
                    "source_name": "Sofascore",
                    "source_role": "independent",
                    "source_url": attempted_urls[-1] if attempted_urls else None,
                    "search_urls": attempted_urls,
                    "captured_at": _timestamp(observed),
                    "error": _safe_error(error),
                    "ledger_eligible": False,
                    "missing_requirements": ["official_source", "review"],
                }
            )
            continue

        if len(matches) != 1:
            selected_snapshot = snapshot_path
            records.append(
                _base_record(row)
                | {
                    "status": "not_found" if not matches else "conflict",
                    "source_name": "Sofascore",
                    "source_role": "independent",
                    "source_url": selected_url,
                    "search_urls": attempted_urls,
                    "captured_at": _timestamp(observed),
                    "candidate_ids": [int(item["id"]) for item in matches],
                    "snapshot_path": (
                        None
                        if selected_snapshot is None
                        else str(selected_snapshot.relative_to(output))
                    ),
                    "snapshot_sha256": snapshot_sha256,
                    "ledger_eligible": False,
                    "missing_requirements": ["official_source", "review"],
                }
            )
            continue

        event = matches[0]
        starts_at = datetime.fromtimestamp(
            int(event["startTimestamp"]), timezone.utc
        )
        sport = str(
            event.get("homeTeam", {}).get("sport", {}).get("slug")
            or "football"
        )
        source_url = (
            f"https://www.sofascore.com/{sport}/match/"
            f"{event.get('slug')}/{event.get('customId')}#id:{event['id']}"
        )
        records.append(
            _base_record(row)
            | {
                "status": "independent_candidate",
                "source_name": "Sofascore",
                "source_role": "independent",
                "source_url": source_url,
                "search_url": selected_url,
                "search_urls": attempted_urls,
                "source_event_id": int(event["id"]),
                "home_name": event["homeTeam"]["name"],
                "away_name": event["awayTeam"]["name"],
                "competition": event.get("tournament", {}).get("name"),
                "starts_at": _timestamp(starts_at),
                "captured_at": _timestamp(observed),
                "snapshot_path": str(snapshot_path.relative_to(output)),
                "snapshot_sha256": snapshot_sha256,
                "ledger_eligible": False,
                "missing_requirements": ["official_source", "review"],
            }
        )

    candidate_count = sum(
        item["status"] == "independent_candidate" for item in records
    )
    unresolved_count = len(records) - candidate_count
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "queue_path": str(Path(queue_path).resolve()),
        "queue_sha256": queue["queue_sha256"],
        "drawing_id": queue["identity"]["drawing_id"],
        "drawing_number": queue["identity"]["drawing_number"],
        "captured_at": _timestamp(observed),
        "candidate_count": candidate_count,
        "unresolved_count": unresolved_count,
        "ledger_mutated": False,
        "records": records,
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    report_path = output / "schedule-source-candidates.json"
    _write_replace(report_path, _pretty(report))
    return ScheduleSourceCollection(
        status=str(report["status"]),
        queue_sha256=str(queue["queue_sha256"]),
        candidate_count=candidate_count,
        unresolved_count=unresolved_count,
        records=tuple(records),
        report_path=report_path,
    )


def _load_queue(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("schedule evidence queue must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("schedule evidence queue must be an object")
    expected = payload.get("queue_sha256")
    unsigned = dict(payload)
    unsigned.pop("queue_sha256", None)
    if expected != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError("schedule evidence queue hash mismatch")
    if payload.get("schema_version") != 1:
        raise ValueError("schedule evidence queue schema is unsupported")
    if payload.get("queue_type") != "reviewed_schedule_evidence":
        raise ValueError("schedule evidence queue type is unsupported")
    if not isinstance(payload.get("identity"), dict) or not isinstance(
        payload.get("records"), list
    ):
        raise ValueError("schedule evidence queue fields are invalid")
    return payload


def _matching_events(
    payload: Mapping[str, Any],
    *,
    homes: tuple[str, ...],
    aways: tuple[str, ...],
    deadline: datetime,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        if not isinstance(item, dict) or item.get("type") != "event":
            continue
        event = item.get("entity")
        if not isinstance(event, dict):
            continue
        try:
            starts_at = datetime.fromtimestamp(
                int(event["startTimestamp"]), timezone.utc
            )
            home_aliases = _team_aliases(event["homeTeam"])
            away_aliases = _team_aliases(event["awayTeam"])
        except (KeyError, TypeError, ValueError):
            continue
        if not deadline <= starts_at <= deadline + _MAX_DRAWING_SPAN:
            continue
        if any(_alias_compatible(home, home_aliases) for home in homes) and any(
            _alias_compatible(away, away_aliases) for away in aways
        ):
            matches.append(event)
    return matches


def _team_aliases(team: Mapping[str, Any]) -> tuple[str, ...]:
    aliases = [str(team["name"])]
    translations = team.get("fieldTranslations", {}).get(
        "nameTranslation", {}
    )
    if isinstance(translations, dict):
        aliases.extend(
            str(value) for value in translations.values() if value
        )
    return tuple(dict.fromkeys(aliases))


def _optional_ledger(path: str | Path | None) -> ScheduleEvidenceLedger | None:
    if path is None:
        return None
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        return None
    return load_schedule_evidence_ledger(source)


def _ledger_canonical_names(
    ledger: ScheduleEvidenceLedger | None, target: str
) -> tuple[str, ...]:
    if ledger is None:
        return ()
    identities: list[tuple[str, tuple[str, ...]]] = []
    for observation in ledger.observations:
        identities.extend(
            (
                (observation.home_entity, observation.home_aliases),
                (observation.away_entity, observation.away_aliases),
            )
        )

    return tuple(
        dict.fromkeys(
            entity
            for entity, aliases in identities
            if _alias_compatible(target, (*aliases, entity))
        )
    )


def _alias_compatible(target: str, aliases: tuple[str, ...]) -> bool:
    target_key = _name_key(target)
    target_tokens = set(target_key.split())
    for alias in aliases:
        try:
            alias_key = _name_key(alias)
        except ValueError:
            continue
        if target_key == alias_key:
            return True
        alias_tokens = set(alias_key.split())
        if target_tokens and (
            target_tokens <= alias_tokens or alias_tokens <= target_tokens
        ):
            return True
    return False


def _name_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character for character in value if not unicodedata.combining(character)
    )
    normalized = normalize_team_name(value)
    normalized = re.sub(
        r"^(?:f\s*c|f\s*k|c\s*f|afc|ac|cd|fk|fc|фк|ск)\s+",
        "",
        normalized,
    )
    normalized = re.sub(
        r"\s+(?:f\s*c|f\s*k|c\s*f|afc|ac|cd|fk|fc|af|фк|ск)$",
        "",
        normalized,
    )
    return transliterate_team_name(normalized)


def _base_record(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        "drawing_id": int(row["drawing_id"]),
        "drawing_number": int(row["drawing_number"]),
        "event_order": int(row["event_order"]),
        "target_event_id": int(row["target_event_id"]),
        "target_home_team": str(row["home_team"]),
        "target_away_team": str(row["away_team"]),
    }


def _fetch_json(url: str) -> Mapping[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TotoAI-Schedule-Research/1.0",
        },
    )
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("public schedule source returned a non-object")
    return payload


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _write_exact(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError("schedule source snapshot conflicts")
        return
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _write_replace(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _safe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {str(error)[:300]}"
