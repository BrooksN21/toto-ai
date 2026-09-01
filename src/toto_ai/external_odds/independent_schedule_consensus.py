"""Fail-closed GOAL API plus Sofascore schedule consensus promotion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from toto_ai.external_odds.domain import TargetEvent
from toto_ai.external_odds.schedule_consensus import (
    ScheduleConsensusPromotion,
    _fetch_json,
    _freeze_snapshot,
    _require_mapping,
    _safe_directory,
)
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceLedger,
    gender_age_class,
    ingest_reviewed_observation,
    load_schedule_evidence_ledger,
)
from toto_ai.external_odds.schedule_source_collector import (
    _alias_compatible,
    _base_record,
    _canonical,
    _load_queue,
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

_SEARCH_ENDPOINT = "https://www.sofascore.com/api/v1/search/all?q={query}"
_EVENT_ENDPOINT = "https://www.sofascore.com/api/v1/event/{event_id}"
_ALLOWED_GOAL_STATUSES = {"independent_candidate", "timing_conflict"}
_ALLOWED_MATCH_MODES = {"matched"}
_EXACT_TARGET_BINDING = "exact_same_target_event_v1"
_KICKOFF_TOLERANCE = timedelta(minutes=5)
_PROVIDER_DOMAINS = {
    "goal-api-v1": frozenset({"goal-api.com", "api.goal-api.com"}),
    "sofascore-v1": frozenset({"sofascore.com"}),
    "thesportsdb-v1": frozenset({"thesportsdb.com"}),
}


@dataclass(frozen=True)
class _IndependentCandidate:
    provider: str
    source_name: str
    source_event_id: str
    source_url: str
    domain: str
    home: str
    away: str
    canonical_home: str
    canonical_away: str
    starts_at: datetime
    captured_at: datetime
    competition: str
    raw: Mapping[str, Any]


def promote_independent_schedule_consensus(
    queue_path: str | Path,
    *,
    source_candidates_path: str | Path,
    output_dir: str | Path,
    schedule_evidence_ledger: str | Path,
    fetch_json: Callable[[str], object] | None = None,
    captured_at: datetime | None = None,
) -> ScheduleConsensusPromotion:
    """Promote any strict pair of allowlisted independent schedule providers."""

    queue_path = Path(queue_path)
    queue = _load_queue(queue_path)
    source_path = Path(source_candidates_path).resolve()
    source = _load_source_report(source_path, queue_sha256=str(queue["queue_sha256"]))
    observed = _utc(captured_at or datetime.now(timezone.utc))
    output = _safe_directory(Path(output_dir))
    ledger_path = Path(schedule_evidence_ledger).resolve()
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ValueError("schedule evidence ledger must be a regular file")
    ledger = load_schedule_evidence_ledger(ledger_path)
    deadline = _parse_utc(queue["identity"]["deadline"])
    records: list[dict[str, object]] = []

    for row in queue["records"]:
        base = _base_record(row)
        raw_candidates = tuple(
            item
            for item in source["records"]
            if isinstance(item, Mapping)
            and item.get("status") == "independent_candidate"
            and int(item.get("event_order", -1)) == int(row["event_order"])
            and _provider_name(item) in _PROVIDER_DOMAINS
        )
        try:
            candidates = tuple(
                _strict_candidate(item, row=row, observed=observed)
                for item in raw_candidates
            )
            pair = _strict_consensus_pair(candidates)
        except ValueError as error:
            records.append(
                base
                | {
                    "status": "independent_consensus_failed",
                    "captured_at": _timestamp(observed),
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
            continue
        if pair is None:
            # Backward compatibility for historical GOAL reports whose
            # independently fetched Sofascore detail was not stored as a row.
            if len(candidates) == 1 and candidates[0].provider == "goal-api-v1":
                return _promote_goal_sofascore_consensus_legacy(
                    queue_path,
                    source_candidates_path=source_path,
                    output_dir=output,
                    schedule_evidence_ledger=ledger_path,
                    fetch_json=fetch_json,
                    captured_at=observed,
                )
            records.append(
                base
                | {
                    "status": "independent_pair_not_found",
                    "captured_at": _timestamp(observed),
                    "ledger_promoted": False,
                }
            )
            continue

        first, second = pair
        starts_at = min(first.starts_at, second.starts_at)
        observation_id = _generic_observation_id(first, second, row=row)
        try:
            existing = _find_existing(
                ledger,
                observation_id=observation_id,
                starts_at=starts_at,
                home=first.home,
                away=first.away,
            )
        except ValueError as error:
            records.append(
                base
                | {
                    "status": "ledger_conflict",
                    "captured_at": _timestamp(observed),
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
                    "starts_at": _timestamp(starts_at),
                    "observation_id": observation_id,
                    "providers": [first.provider, second.provider],
                    "ledger_promoted": False,
                }
            )
            continue

        frozen = []
        for candidate in pair:
            snapshot, digest = _freeze_snapshot(
                ledger_path.parent,
                source=candidate.provider,
                source_id=candidate.source_event_id,
                payload=candidate.raw,
            )
            frozen.append((candidate, snapshot, digest))
        review_path = ledger_path.parent / "reviews" / f"auto-{observation_id}.md"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review = _render_generic_review(
            row=row,
            pair=pair,
            frozen=tuple(frozen),
            observed=observed,
            starts_at=starts_at,
            ledger_root=ledger_path.parent,
        )
        _write_exact(review_path, review.encode("utf-8"))
        observation = _generic_observation(
            row=row,
            pair=pair,
            observation_id=observation_id,
            starts_at=starts_at,
            observed=observed,
            review_path=review_path,
            ledger_root=ledger_path.parent,
            deadline=deadline,
        )
        try:
            ledger = ingest_reviewed_observation(ledger_path, observation)
        except Exception as error:
            records.append(
                base
                | {
                    "status": "ledger_rejected",
                    "captured_at": _timestamp(observed),
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
                "starts_at": _timestamp(starts_at),
                "observation_id": observation_id,
                "providers": [first.provider, second.provider],
                "review_document": str(review_path.relative_to(ledger_path.parent)),
                "ledger_promoted": True,
            }
        )

    return _finish(
        queue_path=queue_path,
        source_path=source_path,
        queue=queue,
        records=records,
        output=output,
        ledger=ledger,
    )


def _provider_name(record: Mapping[str, Any]) -> str:
    provider = str(record.get("source_provider") or "").strip()
    if not provider and record.get("source_name") == "Sofascore":
        provider = "sofascore-v1"
    return provider


def _strict_candidate(
    record: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    observed: datetime,
) -> _IndependentCandidate:
    provider = _provider_name(record)
    if provider not in _PROVIDER_DOMAINS or record.get("source_role") != "independent":
        raise ValueError("source provider is not allowlisted and independent")
    if int(record.get("target_event_id", -1)) != int(row["target_event_id"]):
        raise ValueError("source candidate target identity conflicts")
    if (
        record.get("target_home_team") != row["home_team"]
        or record.get("target_away_team") != row["away_team"]
        or record.get("identity_binding") != _EXACT_TARGET_BINDING
    ):
        raise ValueError("source candidate target binding is missing or conflicts")
    if record.get("orientation") != "same" or record.get("match_mode") != "matched":
        raise ValueError("source candidate is fuzzy, reversed, or ambiguous")
    if record.get("source_status") not in {"scheduled", "not_started"}:
        raise ValueError("source candidate status is not acceptable")
    if record.get("status_eligible") is not True:
        raise ValueError("source candidate is not status eligible")
    source_url = str(record.get("source_url") or "").strip()
    parsed = urlparse(source_url)
    domain = (parsed.hostname or "").casefold()
    if domain.startswith("www."):
        domain = domain[4:]
    if parsed.scheme != "https" or domain not in _PROVIDER_DOMAINS[provider]:
        raise ValueError("source candidate domain is not allowlisted")
    home = str(record.get("home_name") or "").strip()
    away = str(record.get("away_name") or "").strip()
    event_id = str(record.get("source_event_id") or "").strip()
    if not home or not away or not event_id:
        raise ValueError("source candidate identity is incomplete")
    starts_at = _parse_utc(record["starts_at"])
    captured_at = _parse_utc(record["captured_at"])
    if captured_at >= starts_at or observed >= starts_at:
        raise ValueError("source evidence was captured too late")
    return _IndependentCandidate(
        provider=provider,
        source_name=str(record.get("source_name") or provider),
        source_event_id=event_id,
        source_url=source_url,
        domain=domain,
        home=home,
        away=away,
        canonical_home=_candidate_canonical_key(record, "home", home),
        canonical_away=_candidate_canonical_key(record, "away", away),
        starts_at=starts_at,
        captured_at=captured_at,
        competition=str(record.get("competition") or "").strip(),
        raw=record,
    )


def _strict_consensus_pair(
    candidates: tuple[_IndependentCandidate, ...],
) -> tuple[_IndependentCandidate, _IndependentCandidate] | None:
    by_provider: dict[str, _IndependentCandidate] = {}
    for candidate in candidates:
        if candidate.provider in by_provider:
            raise ValueError("ambiguous duplicate provider candidates")
        by_provider[candidate.provider] = candidate
    ordered = tuple(by_provider[key] for key in sorted(by_provider))
    if len(ordered) < 2:
        return None
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if left.provider == right.provider or left.domain == right.domain:
                raise ValueError(
                    "independent sources must use different providers/domains"
                )
            if (
                left.canonical_home != right.canonical_home
                or left.canonical_away != right.canonical_away
            ):
                raise ValueError("independent source team identities conflict")
            if abs(left.starts_at - right.starts_at) > _KICKOFF_TOLERANCE:
                raise ValueError("independent source kickoff values conflict")
    return ordered[0], ordered[1]


def _candidate_canonical_key(
    record: Mapping[str, Any], side: str, fallback: str
) -> str:
    value = record.get(f"canonical_{side}_name")
    return _name_key(str(value).strip() if value else fallback)


def _generic_observation_id(
    first: _IndependentCandidate,
    second: _IndependentCandidate,
    *,
    row: Mapping[str, Any],
) -> str:
    identity = {
        "sources": sorted(
            (
                (first.provider, first.source_event_id),
                (second.provider, second.source_event_id),
            )
        ),
        "drawing_id": int(row["drawing_id"]),
        "target_event_id": int(row["target_event_id"]),
        "championship": str(row.get("championship") or "").strip(),
    }
    return (
        "independent-consensus-v3-"
        + hashlib.sha256(_canonical(identity)).hexdigest()[:20]
    )


def _generic_observation(
    *,
    row: Mapping[str, Any],
    pair: tuple[_IndependentCandidate, _IndependentCandidate],
    observation_id: str,
    starts_at: datetime,
    observed: datetime,
    review_path: Path,
    ledger_root: Path,
    deadline: datetime,
) -> dict[str, object]:
    first, second = pair
    target = TargetEvent(
        drawing_id=int(row["drawing_id"]),
        drawing_number=int(row["drawing_number"]),
        event_id=int(row["target_event_id"]),
        event_order=int(row["event_order"]),
        sport="football",
        championship=str(row.get("championship") or "football"),
        starts_at=None,
        deadline=deadline,
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        home_team_en=first.home,
        away_team_en=first.away,
        bk_probabilities=(1 / 3, 1 / 3, 1 / 3),
    )
    competitions = [
        str(row.get("championship") or "").strip(),
        first.competition,
        second.competition,
    ]
    return {
        "observation_id": observation_id,
        "sport": "football",
        "gender_age_class": gender_age_class(target),
        "competition_aliases": list(
            dict.fromkeys(item for item in competitions if item)
        ),
        "home_entity": first.home,
        "home_aliases": list(
            dict.fromkeys((str(row["home_team"]), first.home, second.home))
        ),
        "away_entity": first.away,
        "away_aliases": list(
            dict.fromkeys((str(row["away_team"]), first.away, second.away))
        ),
        "starts_at": _timestamp(starts_at),
        "status": "scheduled",
        "conditional": False,
        "reviewer": "automated-independent-provider-consensus-v1",
        "reviewed_at": _timestamp(observed),
        "review_document": str(review_path.relative_to(ledger_root)),
        "review_document_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "claims": [
            {
                "source_name": item.source_name,
                "role": "independent",
                "source_url": item.source_url,
            }
            for item in pair
        ],
    }


def _render_generic_review(
    *,
    row: Mapping[str, Any],
    pair: tuple[_IndependentCandidate, _IndependentCandidate],
    frozen: tuple[tuple[_IndependentCandidate, Path, str], ...],
    observed: datetime,
    starts_at: datetime,
    ledger_root: Path,
) -> str:
    title = (
        "# Automated independent schedule consensus: "
        f"{row['home_team']} — {row['away_team']}"
    )
    lines = [
        title,
        "",
        f"Reviewed at **{_timestamp(observed)}**.",
        f"Scheduled kickoff: **{_timestamp(starts_at)}**.",
        "",
        "Two allowlisted independent providers match exact home/away ",
        "orientation, acceptable pre-kickoff status and UTC kickoff within ",
        "tolerance.",
        "",
    ]
    for candidate, snapshot, digest in frozen:
        identity = (
            f"  - provider: `{candidate.provider}`; "
            f"event: `{candidate.source_event_id}`"
        )
        evidence = (
            f"  - evidence: `{snapshot.relative_to(ledger_root)}` — "
            f"SHA-256 `{digest}`"
        )
        lines.extend(
            (
                f"- {candidate.source_name}: {candidate.source_url}",
                identity,
                evidence,
            )
        )
    lines.extend(
        (
            "",
            "Single-source, fuzzy, reversed, ambiguous, late, started or ",
            "conflicting evidence remains fail-closed.",
            "",
        )
    )
    return "\n".join(lines)


def _promote_goal_sofascore_consensus_legacy(
    queue_path: str | Path,
    *,
    source_candidates_path: str | Path,
    output_dir: str | Path,
    schedule_evidence_ledger: str | Path,
    fetch_json: Callable[[str], object] | None = None,
    captured_at: datetime | None = None,
) -> ScheduleConsensusPromotion:
    """Promote two-source schedule evidence with exact names and kickoff.

    GOAL remains candidate-only by itself.  Promotion requires a separately
    fetched Sofascore search result and event detail with the same canonical
    home/away identities and exact UTC kickoff.  Fuzzy GOAL-to-target
    candidates are accepted only after the second source confirms GOAL's pair
    and kickoff; the original matcher mode remains frozen in the review.
    """

    queue_path = Path(queue_path)
    queue = _load_queue(queue_path)
    source_path = Path(source_candidates_path).resolve()
    source = _load_source_report(source_path, queue_sha256=str(queue["queue_sha256"]))
    observed = _utc(captured_at or datetime.now(timezone.utc))
    output = _safe_directory(Path(output_dir))
    ledger_path = Path(schedule_evidence_ledger).resolve()
    if ledger_path.is_symlink() or not ledger_path.is_file():
        raise ValueError("schedule evidence ledger must be a regular file")
    ledger = load_schedule_evidence_ledger(ledger_path)
    fetch = fetch_json or _fetch_json
    deadline = _parse_utc(queue["identity"]["deadline"])
    records: list[dict[str, object]] = []

    for row in queue["records"]:
        base = _base_record(row)
        candidates = _goal_records(source, event_order=int(row["event_order"]))
        if len(candidates) != 1:
            records.append(
                base
                | {
                    "status": "goal_not_found" if not candidates else "goal_conflict",
                    "captured_at": _timestamp(observed),
                    "goal_candidate_ids": [
                        str(item.get("source_event_id")) for item in candidates
                    ],
                    "ledger_promoted": False,
                }
            )
            continue
        goal = candidates[0]
        try:
            goal_id, goal_home, goal_away, starts_at = _validate_goal_record(
                goal,
                observed=observed,
            )
            sofa_candidates = _sofascore_records(
                source,
                event_order=int(row["event_order"]),
            )
            if len(sofa_candidates) > 1:
                raise ValueError("multiple Sofascore candidates match target event")
            verification_home = goal_home
            verification_away = goal_away
            expected_sofa_id: int | None = None
            if sofa_candidates:
                (
                    expected_sofa_id,
                    verification_home,
                    verification_away,
                ) = _validate_sofascore_source_record(
                    sofa_candidates[0],
                    row=row,
                    starts_at=starts_at,
                    observed=observed,
                )
            search_url = _SEARCH_ENDPOINT.format(
                query=quote_plus(f"{verification_home} {verification_away}")
            )
            search_payload = _require_mapping(fetch(search_url), "Sofascore search")
            search_snapshot, search_digest = _freeze_snapshot(
                ledger_path.parent,
                source="sofascore-search",
                source_id=goal_id,
                payload=search_payload,
            )
            matches = _matching_sofascore_events(
                search_payload,
                home=verification_home,
                away=verification_away,
                starts_at=starts_at,
            )
            if expected_sofa_id is not None:
                matches = tuple(
                    item for item in matches if int(item["id"]) == expected_sofa_id
                )
            if len(matches) != 1:
                records.append(
                    base
                    | {
                        "status": (
                            "sofascore_not_found"
                            if not matches
                            else "sofascore_conflict"
                        ),
                        "captured_at": _timestamp(observed),
                        "goal_event_id": goal_id,
                        "sofascore_candidate_ids": [
                            int(item["id"]) for item in matches
                        ],
                        "ledger_promoted": False,
                    }
                )
                continue
            search_event = matches[0]
            sofa_id = int(search_event["id"])
            event_endpoint = _EVENT_ENDPOINT.format(event_id=sofa_id)
            event_payload = _require_mapping(fetch(event_endpoint), "Sofascore event")
            event = _require_mapping(
                event_payload.get("event"), "Sofascore event entity"
            )
            _validate_sofascore_detail(
                search_event,
                event,
                home=verification_home,
                away=verification_away,
                starts_at=starts_at,
                observed=observed,
            )
        except Exception as error:
            records.append(
                base
                | {
                    "status": "independent_consensus_failed",
                    "captured_at": _timestamp(observed),
                    "goal_event_id": str(goal.get("source_event_id") or ""),
                    "error": _safe_error(error),
                    "ledger_promoted": False,
                }
            )
            continue

        observation_id = _observation_id(goal_id, sofa_id, row=row)
        try:
            existing = _find_existing(
                ledger,
                observation_id=observation_id,
                starts_at=starts_at,
                home=goal_home,
                away=goal_away,
            )
        except ValueError as error:
            records.append(
                base
                | {
                    "status": "ledger_conflict",
                    "captured_at": _timestamp(observed),
                    "goal_event_id": goal_id,
                    "sofascore_event_id": sofa_id,
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
                    "goal_event_id": goal_id,
                    "sofascore_event_id": sofa_id,
                    "starts_at": _timestamp(starts_at),
                    "observation_id": observation_id,
                    "ledger_promoted": False,
                }
            )
            continue

        goal_snapshot, goal_digest = _freeze_snapshot(
            ledger_path.parent,
            source="goal-candidate",
            source_id=goal_id,
            payload=goal,
        )
        sofa_snapshot, sofa_digest = _freeze_snapshot(
            ledger_path.parent,
            source="sofascore",
            source_id=str(sofa_id),
            payload=event_payload,
        )
        goal_url = f"{str(goal['source_url']).rstrip('/')}/#fixture-{goal_id}"
        sofa_url = _sofascore_public_url(event)
        review_path = ledger_path.parent / "reviews" / f"auto-{observation_id}.md"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review = _render_review(
            row=row,
            goal=goal,
            event=event,
            observed=observed,
            starts_at=starts_at,
            goal_url=goal_url,
            sofa_url=sofa_url,
            goal_snapshot=goal_snapshot,
            goal_digest=goal_digest,
            search_snapshot=search_snapshot,
            search_digest=search_digest,
            sofa_snapshot=sofa_snapshot,
            sofa_digest=sofa_digest,
            ledger_root=ledger_path.parent,
        )
        _write_exact(review_path, review.encode("utf-8"))
        observation = _observation(
            row=row,
            goal=goal,
            event=event,
            observation_id=observation_id,
            starts_at=starts_at,
            observed=observed,
            review_path=review_path,
            ledger_root=ledger_path.parent,
            goal_url=goal_url,
            sofa_url=sofa_url,
            deadline=deadline,
        )
        try:
            ledger = ingest_reviewed_observation(ledger_path, observation)
        except Exception as error:
            records.append(
                base
                | {
                    "status": "ledger_rejected",
                    "captured_at": _timestamp(observed),
                    "goal_event_id": goal_id,
                    "sofascore_event_id": sofa_id,
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
                "goal_event_id": goal_id,
                "sofascore_event_id": sofa_id,
                "starts_at": _timestamp(starts_at),
                "observation_id": observation_id,
                "review_document": str(review_path.relative_to(ledger_path.parent)),
                "ledger_promoted": True,
            }
        )

    return _finish(
        queue_path=queue_path,
        source_path=source_path,
        queue=queue,
        records=records,
        output=output,
        ledger=ledger,
    )


def promote_goal_sofascore_consensus(
    queue_path: str | Path,
    *,
    source_candidates_path: str | Path,
    output_dir: str | Path,
    schedule_evidence_ledger: str | Path,
    fetch_json: Callable[[str], object] | None = None,
    captured_at: datetime | None = None,
) -> ScheduleConsensusPromotion:
    """Backward-compatible name for generic independent-provider consensus."""

    return promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source_candidates_path,
        output_dir=output_dir,
        schedule_evidence_ledger=schedule_evidence_ledger,
        fetch_json=fetch_json,
        captured_at=captured_at,
    )


def _load_source_report(path: Path, *, queue_sha256: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("schedule source report must be a regular file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 2:
        raise ValueError("schedule source report is invalid")
    if payload.get("queue_sha256") != queue_sha256:
        raise ValueError("schedule source report queue hash mismatch")
    if not isinstance(payload.get("records"), list):
        raise ValueError("schedule source report records are invalid")
    expected = payload.get("report_sha256")
    unsigned = dict(payload)
    unsigned.pop("report_sha256", None)
    if expected != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError("schedule source report hash mismatch")
    return payload


def _goal_records(
    source: Mapping[str, Any], *, event_order: int
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        item
        for item in source["records"]
        if isinstance(item, Mapping)
        and item.get("source_provider") == "goal-api-v1"
        and item.get("status") in _ALLOWED_GOAL_STATUSES
        and item.get("source_status") in {"scheduled", "not_started"}
        and int(item.get("event_order", -1)) == event_order
    )


def _sofascore_records(
    source: Mapping[str, Any], *, event_order: int
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        item
        for item in source["records"]
        if isinstance(item, Mapping)
        and item.get("source_name") == "Sofascore"
        and item.get("status") == "independent_candidate"
        and int(item.get("event_order", -1)) == event_order
    )


def _validate_sofascore_source_record(
    record: Mapping[str, Any],
    *,
    row: Mapping[str, Any],
    starts_at: datetime,
    observed: datetime,
) -> tuple[int, str, str]:
    if int(record.get("target_event_id", -1)) != int(row["target_event_id"]):
        raise ValueError("Sofascore source candidate target identity conflicts")
    sofa_id = int(record.get("source_event_id", -1))
    home = str(record.get("home_name") or "").strip()
    away = str(record.get("away_name") or "").strip()
    if sofa_id <= 0 or not home or not away:
        raise ValueError("Sofascore source candidate identity is incomplete")
    source_start = _parse_utc(record["starts_at"])
    source_capture = _parse_utc(record["captured_at"])
    if source_start != starts_at:
        raise ValueError("independent source kickoff values conflict")
    if source_capture >= source_start or observed >= source_start:
        raise ValueError("Sofascore source evidence was captured too late")
    source_url = str(record.get("source_url") or "")
    if not source_url.startswith("https://www.sofascore.com/"):
        raise ValueError("Sofascore source candidate URL is invalid")
    return sofa_id, home, away


def _validate_goal_record(
    goal: Mapping[str, Any], *, observed: datetime
) -> tuple[str, str, str, datetime]:
    goal_id = str(goal.get("source_event_id") or "").strip()
    home = str(goal.get("home_name") or "").strip()
    away = str(goal.get("away_name") or "").strip()
    if not goal_id or not home or not away:
        raise ValueError("GOAL candidate identity is incomplete")
    if goal.get("orientation") != "same":
        raise ValueError("GOAL candidate orientation is not exact")
    match_mode = str(goal.get("match_mode") or "")
    if match_mode not in _ALLOWED_MATCH_MODES and not match_mode.startswith(
        "fuzzy_candidate_margin_"
    ):
        raise ValueError("GOAL candidate matcher mode is not eligible")
    starts_at = _parse_utc(goal["starts_at"])
    source_capture = _parse_utc(goal["captured_at"])
    if source_capture >= starts_at or observed >= starts_at:
        raise ValueError("schedule consensus was captured at or after kickoff")
    source_url = str(goal.get("source_url") or "")
    if not source_url.startswith("https://"):
        raise ValueError("GOAL candidate source URL is invalid")
    return goal_id, home, away, starts_at


def _matching_sofascore_events(
    payload: Mapping[str, Any],
    *,
    home: str,
    away: str,
    starts_at: datetime,
) -> tuple[Mapping[str, Any], ...]:
    matches = []
    for item in payload.get("results", []):
        if not isinstance(item, Mapping) or item.get("type") != "event":
            continue
        event = item.get("entity")
        if not isinstance(event, Mapping):
            continue
        try:
            event_start = datetime.fromtimestamp(
                int(event["startTimestamp"]), timezone.utc
            )
            home_aliases = _team_aliases(
                _require_mapping(event["homeTeam"], "homeTeam")
            )
            away_aliases = _team_aliases(
                _require_mapping(event["awayTeam"], "awayTeam")
            )
        except (KeyError, TypeError, ValueError):
            continue
        if (
            event_start == starts_at
            and _exact_alias(home, home_aliases)
            and _exact_alias(away, away_aliases)
        ):
            matches.append(event)
    return tuple(matches)


def _validate_sofascore_detail(
    search: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    home: str,
    away: str,
    starts_at: datetime,
    observed: datetime,
) -> None:
    if int(detail.get("id", -1)) != int(search["id"]):
        raise ValueError("Sofascore identity changed between search and detail")
    if detail.get("status", {}).get("type") != "notstarted":
        raise ValueError("Sofascore event is not scheduled")
    detail_start = datetime.fromtimestamp(int(detail["startTimestamp"]), timezone.utc)
    if detail_start != starts_at or observed >= detail_start:
        raise ValueError("Sofascore kickoff changed or evidence is too late")
    if not _exact_alias(
        home, _team_aliases(_require_mapping(detail["homeTeam"], "homeTeam"))
    ) or not _exact_alias(
        away, _team_aliases(_require_mapping(detail["awayTeam"], "awayTeam"))
    ):
        raise ValueError("Sofascore orientation or exact names conflict with GOAL")


def _exact_alias(value: str, aliases: tuple[str, ...]) -> bool:
    try:
        key = _name_key(value)
    except ValueError:
        return False
    alias_keys = set()
    for alias in aliases:
        try:
            alias_keys.add(_name_key(alias))
        except ValueError:
            continue
    return key in alias_keys or any(
        _alias_compatible(value, (alias,)) for alias in aliases
    )


def _observation_id(
    goal_id: str,
    sofa_id: int,
    *,
    row: Mapping[str, Any],
) -> str:
    """Bind v2 evidence identity to the exact target event and competition."""
    identity = {
        "goal_id": goal_id,
        "sofascore_id": sofa_id,
        "drawing_id": int(row["drawing_id"]),
        "target_event_id": int(row["target_event_id"]),
        "championship": str(row.get("championship") or "").strip(),
    }
    digest = hashlib.sha256(_canonical(identity)).hexdigest()[:20]
    return f"independent-consensus-v2-{digest}"


def _find_existing(
    ledger: ScheduleEvidenceLedger,
    *,
    observation_id: str,
    starts_at: datetime,
    home: str,
    away: str,
):
    matches = [
        item for item in ledger.observations if item.observation_id == observation_id
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("duplicate independent consensus observation")
    item = matches[0]
    if (
        item.starts_at != starts_at
        or not _alias_compatible(home, item.home_aliases)
        or not _alias_compatible(away, item.away_aliases)
    ):
        raise ValueError("existing independent consensus conflicts")
    return item


def _competition_aliases(
    row: Mapping[str, Any], goal: Mapping[str, Any], event: Mapping[str, Any]
) -> list[str]:
    values = [row.get("championship"), goal.get("competition")]
    tournament = event.get("tournament")
    if isinstance(tournament, Mapping):
        values.append(tournament.get("name"))
    result = [str(item).strip() for item in values if str(item or "").strip()]
    if not result:
        raise ValueError("independent consensus has no competition aliases")
    return list(dict.fromkeys(result))


def _observation(
    *,
    row: Mapping[str, Any],
    goal: Mapping[str, Any],
    event: Mapping[str, Any],
    observation_id: str,
    starts_at: datetime,
    observed: datetime,
    review_path: Path,
    ledger_root: Path,
    goal_url: str,
    sofa_url: str,
    deadline: datetime,
) -> dict[str, object]:
    goal_home = str(goal["home_name"])
    goal_away = str(goal["away_name"])
    sofa_home = _team_aliases(_require_mapping(event["homeTeam"], "homeTeam"))
    sofa_away = _team_aliases(_require_mapping(event["awayTeam"], "awayTeam"))
    target = TargetEvent(
        drawing_id=int(row["drawing_id"]),
        drawing_number=int(row["drawing_number"]),
        event_id=int(row["target_event_id"]),
        event_order=int(row["event_order"]),
        sport="football",
        championship=str(
            row.get("championship") or goal.get("competition") or "football"
        ),
        starts_at=None,
        deadline=deadline,
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        home_team_en=goal_home,
        away_team_en=goal_away,
        bk_probabilities=(1 / 3, 1 / 3, 1 / 3),
    )
    return {
        "observation_id": observation_id,
        "sport": "football",
        "gender_age_class": gender_age_class(target),
        "competition_aliases": _competition_aliases(row, goal, event),
        "home_entity": goal_home,
        "home_aliases": list(
            dict.fromkeys((str(row["home_team"]), goal_home, *sofa_home))
        ),
        "away_entity": goal_away,
        "away_aliases": list(
            dict.fromkeys((str(row["away_team"]), goal_away, *sofa_away))
        ),
        "starts_at": _timestamp(starts_at),
        "status": "scheduled",
        "conditional": False,
        "reviewer": "automated-independent-exact-consensus-v1",
        "reviewed_at": _timestamp(observed),
        "review_document": str(review_path.relative_to(ledger_root)),
        "review_document_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "claims": [
            {
                "source_name": "GOAL API",
                "role": "independent",
                "source_url": goal_url,
            },
            {
                "source_name": "Sofascore event",
                "role": "independent",
                "source_url": sofa_url,
            },
        ],
    }


def _sofascore_public_url(event: Mapping[str, Any]) -> str:
    event_id = int(event["id"])
    slug = str(event.get("slug") or "event")
    custom_id = str(event.get("customId") or event_id)
    return f"https://www.sofascore.com/football/match/{slug}/{custom_id}#id:{event_id}"


def _render_review(
    *,
    row: Mapping[str, Any],
    goal: Mapping[str, Any],
    event: Mapping[str, Any],
    observed: datetime,
    starts_at: datetime,
    goal_url: str,
    sofa_url: str,
    goal_snapshot: Path,
    goal_digest: str,
    search_snapshot: Path,
    search_digest: str,
    sofa_snapshot: Path,
    sofa_digest: str,
    ledger_root: Path,
) -> str:
    return "\n".join(
        (
            "# Automated independent schedule consensus: "
            f"{row['home_team']} — {row['away_team']}",
            "",
            f"Reviewed at **{_timestamp(observed)}** for drawing "
            f"{row['drawing_number']}, "
            f"event #{int(row['event_order']) + 1}.",
            "",
            f"Scheduled kickoff: **{_timestamp(starts_at)}**.",
            "",
            "GOAL API and a separately fetched Sofascore event independently match "
            "the target orientation and agree exactly on UTC kickoff. Canonical "
            "spelling variants are retained as aliases. This evidence is used only "
            "for schedule timing and does not alter probabilities.",
            "",
            f"- GOAL API: {goal_url}",
            f"- Sofascore: {sofa_url}",
            f"- GOAL matcher mode: `{goal.get('match_mode')}`",
            f"- Sofascore event ID: `{event.get('id')}`",
            "",
            "## Frozen snapshots",
            "",
            f"- `{goal_snapshot.relative_to(ledger_root)}` — SHA-256 `{goal_digest}`",
            f"- `{search_snapshot.relative_to(ledger_root)}` — "
            f"SHA-256 `{search_digest}`",
            f"- `{sofa_snapshot.relative_to(ledger_root)}` — SHA-256 `{sofa_digest}`",
            "",
            "Conflicting, ambiguous, started, or late evidence remains fail-closed.",
            "",
        )
    )


def _finish(
    *,
    queue_path: Path,
    source_path: Path,
    queue: Mapping[str, Any],
    records: list[dict[str, object]],
    output: Path,
    ledger: ScheduleEvidenceLedger,
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
        "source_candidates_path": str(source_path),
        "drawing_id": queue["identity"]["drawing_id"],
        "drawing_number": queue["identity"]["drawing_number"],
        "promoted_count": promoted,
        "existing_count": existing,
        "unresolved_count": unresolved,
        "ledger_semantic_hash": ledger.semantic_hash,
        "records": records,
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    report_path = output / "independent-schedule-consensus.json"
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
