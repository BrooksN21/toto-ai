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

from toto_ai.external_odds.domain import TargetEvent
from toto_ai.external_odds.matching import (
    MATCHER_VERSION,
    match_event,
    normalize_team_name,
)
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceLedger,
    load_schedule_evidence_ledger,
)
from toto_ai.external_odds.team_registry import transliterate_team_name
from toto_ai.external_odds.thesportsdb import (
    PROVIDER_NAME as THESPORTSDB_PROVIDER,
)
from toto_ai.external_odds.thesportsdb import (
    TheSportsDBClient,
    TheSportsDBConfig,
    TheSportsDBError,
    TheSportsDBScheduleEvent,
    load_thesportsdb_config,
    sanitize_thesportsdb_message,
)

_SEARCH_ENDPOINT = "https://www.sofascore.com/api/v1/search/all?q={query}"
_MAX_DRAWING_SPAN = timedelta(days=5)
_MAX_THESPORTSDB_QUERIES_PER_EVENT = 2
_MAX_ALIAS_CONFLICT_DIAGNOSTICS = 20
_WOMEN_MARKER = re.compile(
    r"(?:^|[^\w])(?:women(?:'s)?|ladies|female|wfc|жфк|жен(?:щины|ский|ская)?\.?|ж)(?:$|[^\w])",
    re.IGNORECASE,
)
_MEN_MARKER = re.compile(
    r"(?:^|[^\w])(?:men(?:'s)?|male|муж(?:чины|ской|ская)?\.?|м)(?:$|[^\w])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScheduleSourceCollection:
    status: str
    queue_sha256: str
    candidate_count: int
    unresolved_count: int
    records: tuple[dict[str, object], ...]
    provider_statuses: dict[str, dict[str, object]]
    report_path: Path


def collect_schedule_source_candidates(
    queue_path: str | Path,
    *,
    output_dir: str | Path,
    fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
    captured_at: datetime | None = None,
    schedule_evidence_ledger: str | Path | None = None,
    thesportsdb_config: TheSportsDBConfig | None = None,
    thesportsdb_client: TheSportsDBClient | None = None,
    team_aliases: Mapping[str, str] | None = None,
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
            f"{home} {away}" for home in canonical_homes for away in canonical_aways
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
        starts_at = datetime.fromtimestamp(int(event["startTimestamp"]), timezone.utc)
        sport = str(
            event.get("homeTeam", {}).get("sport", {}).get("slug") or "football"
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

    sofascore_candidate_count = sum(
        item["status"] == "independent_candidate" for item in records
    )
    provider_statuses: dict[str, dict[str, object]] = {
        "sofascore": {
            "status": "collected",
            "candidate_count": sofascore_candidate_count,
            "ledger_mutated": False,
        }
    }
    thesportsdb_records, thesportsdb_status = _collect_thesportsdb_candidates(
        queue,
        output=output,
        observed=observed,
        deadline=deadline,
        ledger=ledger,
        config=thesportsdb_config,
        client=thesportsdb_client,
        team_aliases=team_aliases,
        lookup_hints=_thesportsdb_lookup_hints(records),
    )
    records.extend(thesportsdb_records)
    provider_statuses[THESPORTSDB_PROVIDER] = thesportsdb_status

    candidate_count = sum(item["status"] == "independent_candidate" for item in records)
    resolved_orders = {
        int(item["event_order"])
        for item in records
        if item["status"] == "independent_candidate"
    }
    unresolved_count = sum(
        int(row["event_order"]) not in resolved_orders for row in queue["records"]
    )
    report: dict[str, object] = {
        "schema_version": 2,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "queue_path": str(Path(queue_path).resolve()),
        "queue_sha256": queue["queue_sha256"],
        "drawing_id": queue["identity"]["drawing_id"],
        "drawing_number": queue["identity"]["drawing_number"],
        "captured_at": _timestamp(observed),
        "candidate_count": candidate_count,
        "unresolved_count": unresolved_count,
        "ledger_mutated": False,
        "providers": provider_statuses,
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
        provider_statuses=provider_statuses,
        report_path=report_path,
    )


def _collect_thesportsdb_candidates(
    queue: Mapping[str, Any],
    *,
    output: Path,
    observed: datetime,
    deadline: datetime,
    ledger: ScheduleEvidenceLedger | None,
    config: TheSportsDBConfig | None,
    client: TheSportsDBClient | None,
    team_aliases: Mapping[str, str] | None,
    lookup_hints: Mapping[int, tuple[str, str]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    aliases, alias_conflicts = _collector_aliases(ledger, team_aliases)
    alias_conflict_diagnostics = _alias_conflict_diagnostics(alias_conflicts)
    if client is None:
        effective_config = config or load_thesportsdb_config()
        if not effective_config.enabled:
            return [], {
                "status": "disabled_missing_key",
                "config_key": "THESPORTSDB_API_KEY",
                "candidate_count": 0,
                "alias_conflicts_skipped": alias_conflict_diagnostics,
                "ledger_mutated": False,
            }
        client = TheSportsDBClient.from_config(
            effective_config,
            cache_dir=output / "thesportsdb-v1",
            now=lambda: observed,
        )

    records: list[dict[str, object]] = []
    window_end = deadline + _MAX_DRAWING_SPAN
    for row in queue["records"]:
        diagnostic_offset = len(client.request_diagnostics)
        evidence_offset = len(client.request_evidence)
        target_home = str(row["home_team"])
        target_away = str(row["away_team"])
        try:
            search_results = []
            query_pairs = _thesportsdb_query_pairs(
                ledger,
                target_home,
                target_away,
                supplied=team_aliases,
                supplied_conflicts=alias_conflicts,
                hints=lookup_hints.get(int(row["event_order"])),
            )
            for search_home, search_away in query_pairs:
                search_results.extend(
                    client.search_schedule_events(
                        search_home,
                        search_away,
                        window_start=deadline,
                        window_end=window_end,
                    )
                )
            normalized = _dedupe_thesportsdb_search_results(search_results)
            selected, orientation, candidate_ids, match_status = (
                _match_thesportsdb_candidates(
                    row,
                    normalized,
                    aliases=aliases,
                    deadline=deadline,
                )
            )
        except Exception as error:
            records.append(
                _base_record(row)
                | {
                    "status": "source_failed",
                    "source_name": "TheSportsDB",
                    "source_provider": THESPORTSDB_PROVIDER,
                    "source_role": "independent",
                    "captured_at": _timestamp(observed),
                    "error": _safe_thesportsdb_error(error),
                    "provider_attempts": _thesportsdb_diagnostics(
                        client, diagnostic_offset
                    ),
                    "ledger_eligible": False,
                    "missing_requirements": ["official_source", "review"],
                }
            )
            continue

        evidence = tuple(client.request_evidence[evidence_offset:])
        snapshot_fields = _thesportsdb_snapshot_fields(evidence, output=output)
        diagnostics = _thesportsdb_diagnostics(client, diagnostic_offset)
        if selected is None:
            status = (
                "status_filtered"
                if normalized and not any(item.eligible for item in normalized)
                else "conflict"
                if match_status == "ambiguous"
                else "not_found"
            )
            records.append(
                _base_record(row)
                | {
                    "status": status,
                    "source_name": "TheSportsDB",
                    "source_provider": THESPORTSDB_PROVIDER,
                    "source_role": "independent",
                    "captured_at": _timestamp(observed),
                    "candidate_ids": list(candidate_ids),
                    "normalized_statuses": [
                        {
                            "source_event_id": item.provider_event_id,
                            "status": item.status,
                            "eligible": item.eligible,
                        }
                        for item in normalized
                    ],
                    "provider_attempts": diagnostics,
                    **snapshot_fields,
                    "ledger_eligible": False,
                    "missing_requirements": ["official_source", "review"],
                }
            )
            continue

        records.append(
            _base_record(row)
            | {
                "status": "independent_candidate",
                "source_name": "TheSportsDB",
                "source_provider": THESPORTSDB_PROVIDER,
                "source_role": "independent",
                "source_url": selected.source_url,
                "source_event_id": selected.provider_event_id,
                "source_home_team_id": selected.provider_home_team_id,
                "source_away_team_id": selected.provider_away_team_id,
                "sport": selected.sport,
                "home_name": selected.home_team,
                "away_name": selected.away_team,
                "orientation": orientation,
                "matcher_version": MATCHER_VERSION,
                "competition": selected.competition,
                "starts_at": _timestamp(selected.starts_at),
                "source_status": selected.status,
                "status_eligible": selected.eligible,
                "captured_at": _timestamp(selected.captured_at),
                "source_endpoint": selected.source_endpoint,
                "request_fingerprint": selected.request_fingerprint,
                "event_payload_sha256": selected.payload_hash,
                "provider_attempts": diagnostics,
                **snapshot_fields,
                "ledger_eligible": False,
                "missing_requirements": ["official_source", "review"],
            }
        )

    candidate_count = sum(item["status"] == "independent_candidate" for item in records)
    return records, {
        "status": "collected",
        "candidate_count": candidate_count,
        "request_count": client.requests_made,
        "cache_hit_count": client.cache_hits,
        "attempted": client.requests_made,
        "skipped": client.requests_skipped,
        "budget_exhausted": client.budget_exhausted,
        "alias_conflicts_skipped": alias_conflict_diagnostics,
        "quota": {
            "daily_limit": client.quota_state.daily_limit,
            "daily_remaining": client.quota_state.daily_remaining,
            "minute_limit": client.quota_state.minute_limit,
            "minute_remaining": client.quota_state.minute_remaining,
        },
        "ledger_mutated": False,
    }


def _match_thesportsdb_candidates(
    row: Mapping[str, Any],
    events: tuple[TheSportsDBScheduleEvent, ...],
    *,
    aliases: dict[str, str],
    deadline: datetime,
) -> tuple[
    TheSportsDBScheduleEvent | None,
    str | None,
    tuple[str, ...],
    str,
]:
    eligible = tuple(
        item
        for item in events
        if item.eligible and _thesportsdb_event_gender_compatible(row, item)
    )
    by_id = {item.provider_event_id: item for item in eligible}
    decisions = []
    for sport in ("football", "hockey"):
        candidates = tuple(
            item.as_provider_event() for item in eligible if item.sport == sport
        )
        if not candidates:
            continue
        target = TargetEvent(
            drawing_id=int(row["drawing_id"]),
            drawing_number=int(row["drawing_number"]),
            event_id=int(row["target_event_id"]),
            event_order=int(row["event_order"]),
            sport=sport,
            championship="TheSportsDB schedule candidate",
            starts_at=None,
            deadline=deadline,
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(1 / 3, 1 / 3, 1 / 3),
        )
        decisions.append(match_event(target, candidates, aliases))
    matched = tuple(
        decision
        for decision in decisions
        if decision.status == "matched" and decision.provider_event_id is not None
    )
    candidate_ids = tuple(
        sorted(
            {
                candidate_id
                for decision in decisions
                for candidate_id in decision.candidate_ids
            }
        )
    )
    if len(matched) == 1:
        decision = matched[0]
        return (
            by_id[decision.provider_event_id],
            decision.orientation,
            candidate_ids,
            decision.status,
        )
    status = (
        "ambiguous"
        if len(matched) > 1 or any(item.status == "ambiguous" for item in decisions)
        else "missing"
    )
    return None, None, candidate_ids, status


def _thesportsdb_event_gender_compatible(
    row: Mapping[str, Any],
    event: TheSportsDBScheduleEvent,
) -> bool:
    target_home = str(row["home_team"])
    target_away = str(row["away_team"])
    return (
        _gender_compatible(target_home, event.home_team)
        and _gender_compatible(target_away, event.away_team)
    ) or (
        _gender_compatible(target_home, event.away_team)
        and _gender_compatible(target_away, event.home_team)
    )


def _dedupe_thesportsdb_search_results(
    events: list[TheSportsDBScheduleEvent],
) -> tuple[TheSportsDBScheduleEvent, ...]:
    by_id: dict[str, TheSportsDBScheduleEvent] = {}
    for event in events:
        previous = by_id.get(event.provider_event_id)
        if previous is not None and (
            previous.sport,
            previous.competition,
            previous.home_team,
            previous.away_team,
            previous.starts_at,
            previous.status,
            previous.eligible,
            previous.provider_home_team_id,
            previous.provider_away_team_id,
        ) != (
            event.sport,
            event.competition,
            event.home_team,
            event.away_team,
            event.starts_at,
            event.status,
            event.eligible,
            event.provider_home_team_id,
            event.provider_away_team_id,
        ):
            raise TheSportsDBError("TheSportsDB duplicate event identity conflicts")
        by_id.setdefault(event.provider_event_id, event)
    return tuple(by_id[key] for key in sorted(by_id))


def _collector_aliases(
    ledger: ScheduleEvidenceLedger | None,
    supplied: Mapping[str, str] | None,
) -> tuple[dict[str, str], frozenset[str]]:
    ledger_aliases: dict[str, str] = {}
    if ledger is not None:
        for observation in ledger.observations:
            for entity, aliases in (
                (observation.home_entity, observation.home_aliases),
                (observation.away_entity, observation.away_aliases),
            ):
                canonical = normalize_team_name(entity)
                for alias in (*aliases, entity):
                    if not _gender_compatible(alias, entity):
                        continue
                    key = normalize_team_name(alias)
                    previous = ledger_aliases.get(key)
                    if previous is not None and previous != canonical:
                        raise ValueError("schedule source ledger aliases conflict")
                    ledger_aliases[key] = canonical

    result = {
        key: value for key, value in ledger_aliases.items() if key != value
    }
    supplied_aliases: dict[str, str] = {}
    conflicts: set[str] = set()
    if supplied is not None:
        for raw_key, raw_value in sorted(
            supplied.items(),
            key=lambda item: (str(item[0]).casefold(), str(item[1]).casefold()),
        ):
            if not _gender_compatible(raw_key, raw_value):
                continue
            key = normalize_team_name(raw_key)
            value = normalize_team_name(raw_value)
            previous = supplied_aliases.get(key)
            if previous is not None and previous != value:
                conflicts.add(key)
                continue
            supplied_aliases[key] = value

    for key, value in sorted(supplied_aliases.items()):
        if key in conflicts:
            continue
        ledger_value = ledger_aliases.get(key)
        if ledger_value is not None:
            if ledger_value != value:
                conflicts.add(key)
            continue
        if key != value:
            result[key] = value
    return result, frozenset(conflicts)


def _alias_conflict_diagnostics(
    conflicts: frozenset[str],
) -> dict[str, object]:
    ordered = sorted(conflicts)
    visible = ordered[:_MAX_ALIAS_CONFLICT_DIAGNOSTICS]
    return {
        "count": len(ordered),
        "normalized_alias_keys": visible,
        "truncated": len(visible) != len(ordered),
    }


def _thesportsdb_query_pairs(
    ledger: ScheduleEvidenceLedger | None,
    target_home: str,
    target_away: str,
    *,
    supplied: Mapping[str, str] | None,
    supplied_conflicts: frozenset[str],
    hints: tuple[str, str] | None,
) -> tuple[tuple[str, str], ...]:
    home_candidates = _query_name_candidates(
        ledger,
        target_home,
        supplied=supplied,
        supplied_conflicts=supplied_conflicts,
        hint=None if hints is None else hints[0],
    )
    away_candidates = _query_name_candidates(
        ledger,
        target_away,
        supplied=supplied,
        supplied_conflicts=supplied_conflicts,
        hint=None if hints is None else hints[1],
    )
    home = _prioritized_query_name(home_candidates)
    away = _prioritized_query_name(away_candidates)
    pairs = ((home, away), (away, home))
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for query_home, query_away in pairs:
        query = f"{query_home}_vs_{query_away}".casefold()
        if query in seen:
            continue
        seen.add(query)
        result.append((query_home, query_away))
        if len(result) == _MAX_THESPORTSDB_QUERIES_PER_EVENT:
            break
    return tuple(result)


def _query_name_candidates(
    ledger: ScheduleEvidenceLedger | None,
    target: str,
    *,
    supplied: Mapping[str, str] | None,
    supplied_conflicts: frozenset[str],
    hint: str | None,
) -> tuple[tuple[str, str], ...]:
    original = _normalize_query_name(target)
    candidates: list[tuple[str, str]] = [(original, "original")]
    candidates.extend(
        (
            _preserve_explicit_gender_marker(
                original, _normalize_query_name(value)
            ),
            "canonical",
        )
        for value in _ledger_canonical_names(ledger, target)
        if _gender_compatible(target, value)
    )
    candidates.extend(
        (
            _preserve_explicit_gender_marker(
                original, _normalize_query_name(value)
            ),
            source,
        )
        for value, source in _supplied_query_names(
            supplied,
            target,
            conflicting_keys=supplied_conflicts,
        )
    )
    transliterated = _normalize_query_name(transliterate_team_name(original))
    transliterated = _preserve_explicit_gender_marker(original, transliterated)
    candidates.append((transliterated, "transliteration"))
    if (
        hint is not None
        and _is_latin_name(hint)
        and _gender_compatible(target, hint)
    ):
        candidates.append(
            (
                _preserve_explicit_gender_marker(
                    original, _normalize_query_name(hint)
                ),
                "hint",
            )
        )

    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, source in candidates:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append((name, source))
    return tuple(result)


def _prioritized_query_name(candidates: tuple[tuple[str, str], ...]) -> str:
    priorities = {
        "canonical": 0,
        "hint": 1,
        "transliteration": 2,
        "original": 3,
    }
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (
            0 if _is_latin_name(item[1][0]) else 1,
            priorities[item[1][1]],
            item[0],
        ),
    )
    return ranked[0][1][0]


def _supplied_query_names(
    supplied: Mapping[str, str] | None,
    target: str,
    *,
    conflicting_keys: frozenset[str],
) -> tuple[tuple[str, str], ...]:
    if supplied is None:
        return ()
    names: dict[str, tuple[str, str]] = {}
    for key, value in sorted(
        supplied.items(),
        key=lambda item: (str(item[0]).casefold(), str(item[1]).casefold()),
    ):
        rendered_key = str(key)
        rendered_value = str(value)
        if not _alias_compatible(target, (rendered_key,)) or not _gender_compatible(
            target, rendered_value
        ):
            continue
        source = (
            "hint"
            if normalize_team_name(rendered_key) in conflicting_keys
            else "canonical"
        )
        name_key = rendered_value.casefold()
        previous = names.get(name_key)
        if previous is None or (previous[1] == "hint" and source == "canonical"):
            names[name_key] = (rendered_value, source)
    return tuple(names.values())


def _thesportsdb_lookup_hints(
    records: list[dict[str, object]],
) -> dict[int, tuple[str, str]]:
    result: dict[int, tuple[str, str]] = {}
    for record in records:
        home = record.get("home_name")
        away = record.get("away_name")
        if (
            record.get("status") != "independent_candidate"
            or record.get("source_name") != "Sofascore"
            or not isinstance(home, str)
            or not isinstance(away, str)
            or not _is_latin_name(home)
            or not _is_latin_name(away)
            or not _gender_compatible(str(record["target_home_team"]), home)
            or not _gender_compatible(str(record["target_away_team"]), away)
        ):
            continue
        result[int(record["event_order"])] = (home, away)
    return result


def _normalize_query_name(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def _is_latin_name(value: str) -> bool:
    letters = [character for character in value if character.isalpha()]
    return bool(letters) and all(
        "LATIN" in unicodedata.name(character, "") for character in letters
    )


def _gender_marker(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value)
    if _WOMEN_MARKER.search(normalized):
        return "women"
    if _MEN_MARKER.search(normalized):
        return "men"
    return None


def _gender_compatible(left: str, right: str) -> bool:
    left_marker = _gender_marker(left)
    right_marker = _gender_marker(right)
    if "women" in {left_marker, right_marker}:
        return left_marker == right_marker
    if left_marker is not None and right_marker is not None:
        return left_marker == right_marker
    return True


def _preserve_explicit_gender_marker(target: str, candidate: str) -> str:
    marker = _gender_marker(target)
    if marker is None or _gender_marker(candidate) == marker:
        return candidate
    suffix = "Women" if marker == "women" else "Men"
    return f"{candidate} {suffix}"


def _thesportsdb_diagnostics(
    client: TheSportsDBClient,
    offset: int,
) -> list[dict[str, object]]:
    return [item.payload() for item in client.request_diagnostics[offset:]]


def _thesportsdb_snapshot_fields(
    evidence: tuple[object, ...],
    *,
    output: Path,
) -> dict[str, object]:
    if not evidence:
        return {}
    item = evidence[-1]
    path = getattr(item, "snapshot_path", None)
    digest = getattr(item, "snapshot_sha256", None)
    if not isinstance(path, Path) or not isinstance(digest, str):
        return {}
    resolved = path.resolve()
    try:
        rendered_path = str(resolved.relative_to(output))
    except ValueError:
        rendered_path = str(resolved)
    return {
        "snapshot_path": rendered_path,
        "snapshot_sha256": digest,
    }


def _safe_thesportsdb_error(error: BaseException) -> str:
    if isinstance(error, TheSportsDBError):
        return str(error)
    return sanitize_thesportsdb_message(f"provider failure: {type(error).__name__}")


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
    translations = team.get("fieldTranslations", {}).get("nameTranslation", {})
    if isinstance(translations, dict):
        aliases.extend(str(value) for value in translations.values() if value)
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
        if not _gender_compatible(target, alias):
            continue
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
