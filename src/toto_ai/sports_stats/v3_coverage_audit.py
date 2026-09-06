"""Offline, read-only sports feature coverage. No storage or operational imports."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.package.audit import canonical_probability_input_sha256
from toto_ai.sports_stats.v3_features import (
    PREDICTOR_FEATURE_NAMES,
    build_sports_v3_feature_table,
)

THRESHOLDS = (1, 3, 5, 10)
DRAWINGS = (4990, 4991, 4992, 4993, 4994, 4995)
PROVIDER = "goal-api-v1"
TERMINAL = {"FINISHED": "FT", "AFTER_ET": "AET", "AFTER_PEN": "PEN"}
SCOPE_FIELDS = ("gender", "age_group", "squad_type", "league_id", "season")
_TIME_ORDER_REJECTION_REASONS = frozenset(
    {
        "ASOF_AFTER_FINAL_INPUT",
        "capture/as_of chronology",
        "history chronology",
        "deadline chronology",
        "cutoff chronology",
        "target kickoff chronology",
        "evidence cutoff/capture chronology",
        "final input captured after as_of",
        "schedule after as_of",
    }
)


def _is_chronology_rejection(reason: str) -> bool:
    """Classify explicit time-order checks, not timestamp syntax/identity errors."""
    return reason in _TIME_ORDER_REJECTION_REASONS


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(_encode(value)).hexdigest()


def _encode(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _check(condition, reason):
    if not condition:
        raise ValueError(reason)


def _dt(value):
    _check(isinstance(value, str), "timestamp required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _check(
        parsed.tzinfo is not None and parsed.utcoffset() is not None,
        "timezone required",
    )
    return parsed


def _text(value):
    _check(isinstance(value, str) and bool(value), "exact string identity required")
    return value


def _goals(value):
    _check(not isinstance(value, bool), "invalid goals")
    _check(isinstance(value, (int, str)) and str(value).isdigit(), "invalid goals")
    return int(value)


def _seal(document, name):
    unsigned = {k: v for k, v in document.items() if k != name}
    _check(document.get(name) == canonical_hash(unsigned), name + " mismatch")


class VerifiedReader:
    """Allow only explicit relative references; recheck all read bytes at finish."""

    def __init__(self, root):
        _check(not Path(root).is_symlink(), "input root symlink")
        self.root = Path(root).resolve(strict=True)
        self.files: dict[str, str] = {}

    def path(self, value):
        relative = Path(value)
        _check(
            not relative.is_absolute() and ".." not in relative.parts,
            "input path escape",
        )
        path = self.root / relative
        current = self.root
        for part in relative.parts:
            current /= part
            _check(not current.is_symlink(), "input symlink")
        _check(path.resolve().is_relative_to(self.root), "input path escape")
        return path

    def read(self, reference):
        path = self.path(reference["path"])
        _check(
            path.is_file() and path.stat().st_size <= 2_000_000, "input file size/type"
        )
        data = path.read_bytes()
        observed = hashlib.sha256(data).hexdigest()
        _check(observed == reference["sha256"], "input file hash mismatch")
        old = self.files.setdefault(reference["path"], observed)
        _check(old == observed, "INPUT_CHANGED")
        document = json.loads(data)
        _check(isinstance(document, dict), "JSON object required")
        return document

    def verify_unchanged(self):
        for relative, expected in self.files.items():
            observed = hashlib.sha256(self.path(relative).read_bytes()).hexdigest()
            _check(observed == expected, "INPUT_CHANGED")


def _parse_source(document, *, team, fixture, kickoff, as_of, scope):
    if document is None:
        return [], {
            "raw_payload_row_count": None,
            "terminal_row_count": None,
            "unique_fixture_count": None,
            "eligible_prior_count": 0,
            "nonterminal_count": None,
            "cross_season_count": None,
            "cross_league_count": None,
            "reason": "source_unavailable",
        }
    _check(
        set(document)
        == {
            "schema_version",
            "provider",
            "endpoint",
            "params",
            "request_fingerprint",
            "fetched_at",
            "response_hash",
            "payload",
        },
        "raw envelope fields",
    )
    _check(
        document["schema_version"] == 1 and document["provider"] == PROVIDER,
        "provider/schema mismatch",
    )
    _check(document["endpoint"] == f"/teams/{team}/results", "endpoint identity")
    _check(document["params"] == [["limit", "10"]], "request limit mismatch")
    expected = canonical_hash(
        {
            "provider": PROVIDER,
            "base_url": "https://api.goal-api.com/v1",
            "endpoint": document["endpoint"],
            "params": document["params"],
        }
    )
    _check(document["request_fingerprint"] == expected, "request hash mismatch")
    capture = _dt(document["fetched_at"])
    _check(capture <= as_of and capture < kickoff, "capture/as_of chronology")
    payload = document["payload"]
    _check(isinstance(payload, dict), "raw payload object")
    _check(document["response_hash"] == canonical_hash(payload), "payload hash")
    _check(
        payload.get("success") is True and str(payload.get("teamId")) == team,
        "payload team identity",
    )
    raw_rows = payload.get("data")
    _check(isinstance(raw_rows, list) and len(raw_rows) <= 10, "raw history limit")
    fixtures, seen = [], set()
    counts = Counter()
    for raw in raw_rows:
        _check(isinstance(raw, dict), "history row object")
        if raw.get("matchStatus") not in TERMINAL:
            counts["nonterminal"] += 1
            continue
        identity = _text(raw.get("id"))
        _check(identity not in seen, "duplicate fixture within response")
        seen.add(identity)
        starts = _dt(raw.get("kickoffUtc"))
        _check(
            starts < capture and starts < as_of and starts < kickoff,
            "history chronology",
        )
        _check(identity != fixture, "target fixture in history")
        home, away = _text(raw.get("homeTeamId")), _text(raw.get("awayTeamId"))
        _check(home != away and team in (home, away), "history team identity")
        for field in ("gender", "age_group", "squad_type"):
            if scope.get(field) is not None and raw.get(field) is not None:
                _check(scope[field] == raw[field], field + " conflict")
        season = raw.get("leagueYear")
        league = raw.get("leagueId")
        counts["cross_season"] += int(
            scope.get("season") is not None
            and season is not None
            and str(season) != str(scope["season"])
        )
        counts["cross_league"] += int(
            scope.get("league_id") is not None
            and league is not None
            and str(league) != str(scope["league_id"])
        )
        fixtures.append(
            {
                "event_id": identity,
                "kickoff": starts,
                "home_team_id": home,
                "away_team_id": away,
                "home_goals": _goals(raw.get("homeTeamScore")),
                "away_goals": _goals(raw.get("awayTeamScore")),
                "status": TERMINAL[raw["matchStatus"]],
                "season": season,
                "league": league,
                **{f: raw.get(f) for f in ("gender", "age_group", "squad_type")},
            }
        )
    return fixtures, {
        "raw_payload_row_count": len(raw_rows),
        "terminal_row_count": len(fixtures),
        "unique_fixture_count": len(seen),
        "eligible_prior_count": len(fixtures),
        "nonterminal_count": counts["nonterminal"],
        "cross_season_count": counts["cross_season"],
        "cross_league_count": counts["cross_league"],
        "reason": None if fixtures else "no_completed_fixtures",
    }


def audit_event(event, documents, *, as_of, deadline, final_captured_at, cutoff=None):
    """Pure event-local diagnostic; no probabilities and no source discovery."""
    asof, end, captured = _dt(as_of), _dt(deadline), _dt(final_captured_at)
    chronology_reasons = ["ASOF_AFTER_FINAL_INPUT"] if asof > captured else []
    # Missing-source evidence is a fact, not permission to compute features.
    # Keep the chronology failure visible without reclassifying absence as corruption.
    if any(document is not None for document in documents.values()):
        _check(not chronology_reasons, "ASOF_AFTER_FINAL_INPUT")
    _check(asof < end and captured < end, "deadline chronology")
    if cutoff is not None:
        _check(asof < _dt(cutoff) <= end, "cutoff chronology")
    scope = event.get("identity_scope", {})
    _check(isinstance(scope, dict), "identity scope object")
    # This public helper accepts declarations, never proof of reviewed provenance.
    # Only the file-verifying manifest adapter below may promote these states.
    identity = dict.fromkeys(SCOPE_FIELDS, "UNKNOWN")
    fixture = event.get("provider_fixture_id")
    rows, counts = {}, {}
    if fixture is None:
        _check(
            all(
                event.get(k) is None
                for k in (
                    "provider_home_team_id",
                    "provider_away_team_id",
                    "target_starts_at",
                )
            ),
            "missing fixture retains identity",
        )
        _check(
            all(v is None for v in documents.values()),
            "missing fixture retains history",
        )
        kickoff = None
    else:
        kickoff = _dt(event["target_starts_at"])
        _check(asof < kickoff, "target kickoff chronology")
        home = _text(event.get("provider_home_team_id"))
        away = _text(event.get("provider_away_team_id"))
        _check(home != away, "same target teams")
    for side in ("home", "away"):
        rows[side], counts[side] = _parse_source(
            documents.get(side),
            team=event.get(f"provider_{side}_team_id"),
            fixture=fixture,
            kickoff=kickoff,
            as_of=asof,
            scope=scope,
        )
        counts[side]["venue_prior_count"] = (
            sum(
                m[f"{side}_team_id"] == event[f"provider_{side}_team_id"]
                for m in rows[side]
            )
            if documents.get(side) is not None
            else None
        )
        counts[side]["window_span_days"] = (
            (
                max(m["kickoff"] for m in rows[side])
                - min(m["kickoff"] for m in rows[side])
            ).total_seconds()
            / 86400
            if rows[side]
            else None
        )
    merged, duplicate_witnesses = {}, 0
    for match in (*rows["home"], *rows["away"]):
        key = match["event_id"]
        if key in merged:
            other = merged[key]
            for field in match:
                if match[field] is not None and other[field] is not None:
                    _check(match[field] == other[field], "conflicting fixture")
            duplicate_witnesses += 1
        else:
            merged[key] = match
    blocks = {}
    for threshold in THRESHOLDS:
        if fixture is None:
            features = dict.fromkeys(PREDICTOR_FEATURE_NAMES)
            missing = ["target_fixture_missing"]
        else:
            table = build_sports_v3_feature_table(
                target_events=[
                    {
                        "event_id": str(event["target_event_id"]),
                        "event_order": event["event_order"],
                        "home_team_id": event["provider_home_team_id"],
                        "away_team_id": event["provider_away_team_id"],
                        "kickoff": kickoff,
                    }
                ],
                completed_matches=list(merged.values()),
                rolling_window=10,
                minimum_prior_matches=threshold,
            )
            features = dict(table.rows[0].features)
            missing = list(table.rows[0].missing_reasons)
            # A missing side is never filled from the other side's capture.
            for side in ("home", "away"):
                if documents.get(side) is None:
                    for name in features:
                        if name.startswith(side + "_"):
                            features[name] = None
                    other = "away" if side == "home" else "home"
                    for suffix in ("ppg", "goal_difference_per_game"):
                        features[f"{other}_opponent_rolling_{suffix}"] = None
                    missing.append(side + "_source_unavailable")
        home_ok = counts["home"]["eligible_prior_count"] >= threshold
        away_ok = counts["away"]["eligible_prior_count"] >= threshold
        blocks[str(threshold)] = {
            "home_core": home_ok,
            "away_core": away_ok,
            "both_core": home_ok and away_ok,
            "full_current_features": all(v is not None for v in features.values()),
            "features": features,
            "missing_reasons": sorted(set(missing)),
        }
    complete = all(counts[s]["eligible_prior_count"] > 0 for s in counts)
    source_status = (
        "complete"
        if complete
        else "partial"
        if any(d is not None for d in documents.values())
        else "missing"
    )
    return {
        "event_order": event["event_order"],
        "target_event_id": str(event["target_event_id"]),
        "source_status": source_status,
        "reason": None,
        "counts": counts,
        "identity": identity,
        "declared_identity_scope": scope,
        "identity_evidence": None,
        "strict_scoped_eligible": False,
        "cutoff_verified": False,
        "feature_chronology_eligible": not chronology_reasons,
        "chronology_reasons": chronology_reasons,
        "provenance_class": "CHRONOLOGY_INELIGIBLE"
        if chronology_reasons
        else "SOURCE_UNAVAILABLE"
        if not any(d is not None for d in documents.values())
        else "PRE_KICKOFF_CAPTURE_CUTOFF_UNVERIFIED",
        "as_of": as_of,
        "final_captured_at": final_captured_at,
        "deadline": deadline,
        "target_kickoff": event.get("target_starts_at"),
        "cutoff": cutoff,
        "thresholds": blocks,
        "duplicate_witness_count": duplicate_witnesses,
        "congestion_scope": "OBSERVED_CAPTURE_ONLY",
        "feature_semantic_hash": canonical_hash(blocks),
        "lineage_hash": canonical_hash(
            {
                "event": {
                    k: v
                    for k, v in event.items()
                    if k not in ("actual_outcome", "target_score", "score", "result")
                },
                "sources": documents,
                "as_of": as_of,
                "final_captured_at": final_captured_at,
                "deadline": deadline,
                "cutoff": cutoff,
            }
        ),
    }


def _witness(reference, *, binding_verified=False):
    return {
        "path": reference["path"],
        "sha256": reference["sha256"],
        "file_verified": True,
        "binding_verified": binding_verified,
    }


def _source_witness(reference=None, document=None, *, envelope_verified=False):
    return {
        "status": reference.get("status", "unknown") if reference else "unknown",
        "reason": reference.get("reason") if reference else None,
        "path": reference.get("path") if reference else None,
        "sha256": reference.get("sha256") if reference else None,
        "file_verified": document is not None,
        "envelope_verified": envelope_verified,
        **{
            field: document.get(field) if envelope_verified else None
            for field in (
                "fetched_at",
                "provider",
                "endpoint",
                "params",
                "request_fingerprint",
                "response_hash",
            )
        },
    }


def _attach_provenance(row, context, order):
    event_context = context["events"].get(order, {})
    row["provenance"] = {
        key: context.get(key) for key in ("manifest", "final", "schedule")
    }
    row["event_binding_verified"] = event_context.get("binding_verified", False)
    row["source_references"] = {
        side: event_context.get("sources", {}).get(side, _source_witness())
        for side in ("home", "away")
    }
    row["lineage_hash"] = canonical_hash(
        {
            "diagnostic_lineage": row["lineage_hash"],
            "provenance": row["provenance"],
            "source_references": row["source_references"],
            "event_binding_verified": row["event_binding_verified"],
            "identity_evidence": row["identity_evidence"],
        }
    )


def _bound_evidence(reader, references, fold, event, final, context):
    """Trusted adapter boundary: references come ONLY from a reviewed receipt.

    Hashes establish binding, not authority: callers must not auto-discover or
    promote manifest/caller declarations into this allowlist. Public audit_event
    has no proof argument and cannot confer VERIFIED status. Explicit entity
    evidence may cover absent raw scope fields only for these exact source bytes.
    """
    matches = [
        r
        for r in references
        if r["drawing_number"] == fold["drawing_number"]
        and r["event_order"] == event["event_order"]
    ]
    _check(len(matches) <= 1, "ambiguous reviewed evidence")
    if not matches:
        return None
    reference = matches[0]
    _check(
        type(reference["drawing_number"]) is int
        and type(reference["event_order"]) is int
        and 0 <= reference["event_order"] < 15,
        "typed reviewed evidence selector",
    )
    _check(
        set(reference)
        == {"path", "sha256", "artifact_type", "drawing_number", "event_order"}
        and reference["artifact_type"] == "sports_v3_bound_identity_cutoff",
        "typed reviewed evidence reference required",
    )
    proof = reader.read(reference)
    _check(
        all(
            type(proof.get(key)) is int
            for key in ("schema_version", "drawing_id", "drawing_number", "event_order")
        ),
        "typed evidence identity",
    )
    expected = {
        "schema_version": 1,
        "artifact_class": "SPORTS_V3_BOUND_IDENTITY_CUTOFF_EVIDENCE",
        "provider": PROVIDER,
        "orientation": "same",
        "scope_applies_to": "TARGET_TEAMS_AND_HASH_BOUND_HISTORY",
        "plan_id": _text(final.get("plan_id")),
        "manifest_file_sha256": context["manifest"]["sha256"],
        "final_input_file_sha256": context["final"]["sha256"],
        "source_file_sha256": {
            side: event["sources"][side].get("sha256") for side in ("home", "away")
        },
        "as_of": fold["as_of"],
        **{
            key: fold[key]
            for key in ("drawing_id", "drawing_number", "drawing_fingerprint")
        },
        **{
            key: event[key]
            for key in (
                "event_order",
                "target_event_id",
                "provider_fixture_id",
                "provider_home_team_id",
                "provider_away_team_id",
                "target_starts_at",
            )
        },
    }
    _check(
        set(proof) == set(expected) | {"captured_at", "cutoff", "identity_scope"},
        "evidence fields",
    )
    _check(
        all(proof[key] == value for key, value in expected.items()),
        "evidence binding mismatch",
    )
    _check(
        event["provider_fixture_id"] is not None
        and all(expected["source_file_sha256"].values()),
        "evidence requires exact sources/fixture",
    )
    _check(
        _dt(proof["captured_at"])
        <= _dt(fold["as_of"])
        < _dt(proof["cutoff"])
        <= _dt(fold["deadline"]),
        "evidence cutoff/capture chronology",
    )
    scope = proof["identity_scope"]
    _check(
        isinstance(scope, dict) and set(scope) == set(SCOPE_FIELDS),
        "typed evidence scope",
    )
    _check(
        all(isinstance(value, str) and value for value in scope.values()),
        "typed evidence scope values",
    )
    declared = event.get("identity_scope", {})
    _check(
        all(declared.get(key) in (None, value) for key, value in scope.items()),
        "declared/evidence scope conflict",
    )
    return {
        "scope": scope,
        "cutoff": proof["cutoff"],
        "reference": _witness(reference, binding_verified=True),
    }


def _rejected_row(fold, order, reason, context):
    event_context = context["events"].get(order, {})
    chronology = [reason] if _is_chronology_rejection(reason) else []
    blocks = {
        str(t): {
            "home_core": False,
            "away_core": False,
            "both_core": False,
            "full_current_features": False,
            "features": dict.fromkeys(PREDICTOR_FEATURE_NAMES),
            "missing_reasons": ["SOURCE_REJECTED"],
        }
        for t in THRESHOLDS
    }
    row = {
        "drawing_number": fold["drawing_number"],
        "event_order": order,
        "target_event_id": event_context.get("target_event_id"),
        "source_status": "SOURCE_REJECTED",
        "reason": reason,
        "counts": None,
        "identity": dict.fromkeys(SCOPE_FIELDS, "UNKNOWN"),
        "declared_identity_scope": {},
        "identity_evidence": None,
        "strict_scoped_eligible": False,
        "cutoff_verified": False,
        "feature_chronology_eligible": False,
        "chronology_reasons": chronology,
        "provenance_class": "SOURCE_REJECTED",
        "as_of": fold.get("as_of"),
        "final_captured_at": context.get("final_captured_at"),
        "deadline": fold.get("deadline"),
        "target_kickoff": event_context.get("target_kickoff"),
        "cutoff": None,
        "thresholds": blocks,
        "duplicate_witness_count": 0,
        "congestion_scope": "OBSERVED_CAPTURE_ONLY",
        "feature_semantic_hash": canonical_hash(blocks),
        "lineage_hash": canonical_hash(
            {"reason": reason, "manifest": context["manifest"], "order": order}
        ),
    }
    _attach_provenance(row, context, order)
    return row


def _validate_fold(reader, fold, context, reviewed_evidence_references):
    _check(fold["provider"] == PROVIDER, "provider mismatch")
    _check(fold["requested_history_size"] == 10, "history size mismatch")
    events = fold["events"]
    target_fixture_ids = [
        event["provider_fixture_id"]
        for event in events
        if event.get("provider_fixture_id") is not None
    ]
    _check(
        len(target_fixture_ids) == len(set(target_fixture_ids)),
        "duplicate provider target fixture",
    )
    _check([e["event_order"] for e in events] == list(range(15)), "event orders")
    _check(len({e["target_event_id"] for e in events}) == 15, "duplicate event IDs")
    _check(
        fold["target_detail"].get("artifact_type") == "frozen_final_input",
        "frozen final input required",
    )
    final = reader.read(fold["target_detail"])
    _seal(final, "snapshot_sha256")
    context["final"] = _witness(fold["target_detail"])
    _dt(final["captured_at"])
    context["final_captured_at"] = final["captured_at"]
    _check(final.get("schema_version") == 1, "final schema")
    for field in ("drawing_id", "drawing_number"):
        _check(final[field] == fold[field], "final input " + field + " mismatch")
    _check(
        _dt(final["deadline"]) == _dt(fold["deadline"]), "final input deadline mismatch"
    )
    _check(
        canonical_hash(final["payload"]) == final["detail_payload_sha256"],
        "detail payload hash",
    )
    target = parse_target_drawing(final["payload"], _dt(final["captured_at"]))
    _check(
        target.drawing_id == fold["drawing_id"]
        and target.drawing_number == fold["drawing_number"],
        "target drawing mismatch",
    )
    _check(target.deadline == _dt(fold["deadline"]), "target deadline mismatch")
    fp = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )
    _check(
        fp == final["target_fingerprint"] == fold["drawing_fingerprint"],
        "target fingerprint mismatch",
    )
    _check(
        final["probability_input_sha256"]
        == canonical_probability_input_sha256(
            tuple(e.bk_probabilities for e in target.events)
        ),
        "probability input hash",
    )
    _check(
        _dt(final["captured_at"]) <= _dt(fold["as_of"]),
        "final input captured after as_of",
    )
    context["final"]["binding_verified"] = True
    schedule = reader.read(fold["schedule_binding"])
    _seal(schedule, "report_sha256")
    context["schedule"] = _witness(fold["schedule_binding"])
    _check(
        schedule["schema_version"] == 2
        and schedule["status"] == "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE"
        and schedule["ledger_mutated"] is False,
        "schedule schema/status",
    )
    _check(
        schedule["drawing_id"] == fold["drawing_id"]
        and schedule["drawing_number"] == fold["drawing_number"],
        "schedule drawing",
    )
    _check(_dt(schedule["captured_at"]) <= _dt(fold["as_of"]), "schedule after as_of")
    schedule_rows = {}
    for record in schedule["records"]:
        if record.get("source_provider") != PROVIDER:
            continue
        order = record["event_order"]
        _check(order not in schedule_rows, "duplicate schedule order")
        schedule_rows[order] = record
    context["schedule"]["binding_verified"] = True
    result = []
    for event, target_event in zip(events, target.events, strict=True):
        order = event["event_order"]
        _check(
            event["target_event_id"] == str(target_event.event_id)
            and event["home_team"] == target_event.home_team
            and event["away_team"] == target_event.away_team
            and event["sport"] == target_event.sport == "football",
            "target event identity",
        )
        record = schedule_rows.get(order)
        docs = {}
        _check(set(event["sources"]) == {"home", "away"}, "exact source sides")
        if event["provider_fixture_id"] is None:
            _check(
                record is None or record["status"] in ("not_found", "source_failed"),
                "missing fixture has available schedule",
            )
            if record is not None:
                _check(
                    all(
                        record.get(f) is None
                        for f in (
                            "source_event_id",
                            "source_home_team_id",
                            "source_away_team_id",
                            "starts_at",
                        )
                    ),
                    "missing schedule retains identity",
                )
        else:
            _check(record is not None, "fixture schedule missing")
            expected = {
                "target_event_id": target_event.event_id,
                "orientation": "same",
                "source_event_id": event["provider_fixture_id"],
                "source_home_team_id": event["provider_home_team_id"],
                "source_away_team_id": event["provider_away_team_id"],
                "starts_at": event["target_starts_at"],
                "source_status": "scheduled",
                "ledger_eligible": False,
                "target_home_team": target_event.home_team,
                "target_away_team": target_event.away_team,
            }
            _check(
                all(record.get(k) == v for k, v in expected.items()),
                "schedule identity mismatch",
            )
            _check(
                record["status"] in ("independent_candidate", "timing_conflict"),
                "schedule source disposition",
            )
            if target_event.starts_at is not None:
                _check(
                    target_event.starts_at == _dt(event["target_starts_at"]),
                    "target kickoff mismatch",
                )
        event_context = context["events"][order] = {
            "target_event_id": str(target_event.event_id),
            "target_kickoff": event.get("target_starts_at"),
            "binding_verified": True,
            "sources": {},
        }
        for side, reference in event["sources"].items():
            if reference["status"] == "available":
                _check(
                    reference.get("artifact_type") == "raw_goal_team_results_response",
                    "raw source type",
                )
                docs[side] = reader.read(reference)
                event_context["sources"][side] = _source_witness(reference, docs[side])
            else:
                _check(
                    set(reference) == {"status", "reason"}
                    and reference["status"] == "unavailable"
                    and reference["reason"]
                    in ("source_not_captured", "target_fixture_missing"),
                    "unavailable source contract",
                )
                docs[side] = None
                event_context["sources"][side] = _source_witness(reference)
        evidence = _bound_evidence(
            reader, reviewed_evidence_references, fold, event, final, context
        )
        audited_event = dict(event)
        if evidence is not None:
            audited_event["identity_scope"] = evidence["scope"]
        row = audit_event(
            audited_event,
            docs,
            as_of=fold["as_of"],
            deadline=fold["deadline"],
            final_captured_at=final["captured_at"],
            cutoff=evidence["cutoff"] if evidence else None,
        )
        if evidence is not None:
            row["declared_identity_scope"] = event.get("identity_scope", {})
            row["identity"] = dict.fromkeys(SCOPE_FIELDS, "VERIFIED")
            row["identity_evidence"] = evidence["reference"]
            row["cutoff_verified"] = True
            row["strict_scoped_eligible"] = (
                row["source_status"] == "complete"
                and row["feature_chronology_eligible"]
            )
            if row["feature_chronology_eligible"]:
                row["provenance_class"] = "PRE_CUTOFF_CAPTURE_RECONSTRUCTED_FEATURES"
        for side in ("home", "away"):
            event_context["sources"][side] = _source_witness(
                event["sources"][side],
                docs[side],
                envelope_verified=docs[side] is not None,
            )
        _attach_provenance(row, context, order)
        row["drawing_number"] = fold["drawing_number"]
        result.append(row)
    return result


def audit_manifest(
    *,
    input_root,
    manifest_path,
    expected_drawings=DRAWINGS,
    manifest_sha256=None,
    progress=None,
    reviewed_evidence_references=(),
):
    reader = VerifiedReader(input_root)
    absolute = Path(manifest_path)
    if not absolute.is_absolute():
        absolute = reader.root / absolute
    _check(absolute.is_relative_to(reader.root), "manifest path escape")
    rel = str(absolute.relative_to(reader.root))
    manifest_path_checked = reader.path(rel)
    observed = hashlib.sha256(manifest_path_checked.read_bytes()).hexdigest()
    manifest = reader.read({"path": rel, "sha256": manifest_sha256 or observed})
    _seal(manifest, "manifest_sha256")
    _check(
        manifest["schema_version"] == 1
        and manifest["artifact_class"]
        == "SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_MANIFEST",
        "manifest schema",
    )
    folds = manifest["snapshots"]
    _check(
        tuple(f["drawing_number"] for f in folds) == expected_drawings,
        "drawing set/order",
    )
    rows, summaries = [], []
    started = time.monotonic()
    unexpected = 0
    unexpected_chronology = 0
    unexpected_source = 0
    for fold in folds:
        _check(time.monotonic() - started < 300, "audit runtime exceeded")
        if progress:
            progress(f"coverage drawing {fold['drawing_number']}")
        context = {
            "manifest": _witness(
                {"path": rel, "sha256": observed}, binding_verified=True
            ),
            "final": None,
            "schedule": None,
            "events": {},
        }
        try:
            fold_rows = _validate_fold(
                reader, fold, context, reviewed_evidence_references
            )
            chronology_reasons = sorted(
                {reason for row in fold_rows for reason in row["chronology_reasons"]}
            )
            unexpected_chronology += int(bool(chronology_reasons))
            unexpected += int(bool(chronology_reasons))
            summary = {
                "drawing_number": fold["drawing_number"],
                "status": "CHRONOLOGY_INELIGIBLE"
                if chronology_reasons
                else "validated",
                "reason": "; ".join(chronology_reasons) or None,
                "chronology_reasons": chronology_reasons,
            }
        except (ValueError, KeyError, TypeError, OSError) as error:
            reason = str(error)
            expected = (
                fold["drawing_number"] == 4990
                and reason == "final input deadline mismatch"
                and observed
                == "07463e8831c8e1cbcd146b9243555c2efce72a160b4c527c3243573ade270e49"
            )
            unexpected += int(not expected)
            is_chronology = _is_chronology_rejection(reason)
            unexpected_chronology += int(not expected and is_chronology)
            unexpected_source += int(not expected and not is_chronology)
            fold_rows = [_rejected_row(fold, i, reason, context) for i in range(15)]
            summary = {
                "drawing_number": fold["drawing_number"],
                "status": "SOURCE_REJECTED",
                "reason": reason,
                "expected_rejection": expected,
                "chronology_reasons": [reason] if is_chronology else [],
            }
        summary["source_complete_count"] = sum(
            r["source_status"] == "complete" for r in fold_rows
        )
        summary["source_missing_count"] = sum(
            r["source_status"] == "missing" for r in fold_rows
        )
        summaries.append(summary)
        rows.extend(fold_rows)
    reader.verify_unchanged()
    coverage = {}
    for t in THRESHOLDS:
        blocks = [r["thresholds"][str(t)] for r in rows]
        coverage[str(t)] = {
            "denominator": len(rows),
            "both_core_count": sum(b["both_core"] for b in blocks),
            "full_current_feature_count": sum(
                b["full_current_features"] for b in blocks
            ),
            "strict_scoped_full_count": sum(
                r["strict_scoped_eligible"]
                and r["thresholds"][str(t)]["full_current_features"]
                for r in rows
            ),
            "per_feature_non_null": {
                name: sum(b["features"][name] is not None for b in blocks)
                for name in PREDICTOR_FEATURE_NAMES
            },
        }
        coverage[str(t)]["per_feature_non_null_rate"] = {
            name: count / len(rows)
            for name, count in coverage[str(t)]["per_feature_non_null"].items()
        }
        coverage[str(t)]["missing_reason_counts"] = dict(
            sorted(
                Counter(
                    reason for block in blocks for reason in block["missing_reasons"]
                ).items()
            )
        )
    distributions = {}
    for side in ("home", "away"):
        distributions[side] = {}
        for field in (
            "raw_payload_row_count",
            "eligible_prior_count",
            "venue_prior_count",
        ):
            values = [
                row["counts"][side][field] if row["counts"] is not None else None
                for row in rows
            ]
            distributions[side][field] = {
                "unavailable_or_rejected_count": values.count(None),
                "histogram": dict(
                    sorted(
                        Counter(
                            str(value) for value in values if value is not None
                        ).items()
                    )
                ),
            }
    report = {
        "schema_version": 1,
        "artifact_class": "SPORTS_V3_READ_ONLY_COVERAGE",
        "status": "INCOMPLETE" if unexpected else "COMPLETE_WITH_GAPS",
        "operator_compatible": False,
        "automatic_wagering": False,
        "profitability_proven": False,
        "activation_allowed": False,
        "thresholds": list(THRESHOLDS),
        "production_minimum_prior_matches": None,
        "rows": rows,
        "folds": summaries,
        "coverage": coverage,
        "count_distributions": distributions,
        "source_disposition_counts": dict(
            sorted(Counter(row["source_status"] for row in rows).items())
        ),
        "raw_history_row_count": sum(
            row["counts"][side]["raw_payload_row_count"] or 0
            for row in rows
            if row["counts"] is not None
            for side in ("home", "away")
        ),
        "raw_history_count_scope": "READ_AVAILABLE_SOURCES_ONLY_NOT_UNIQUE_FIXTURES",
        "input_hashes": dict(sorted(reader.files.items())),
        "inputs_unchanged": True,
        "unexpected_rejections": unexpected,
        "unexpected_chronology_fold_count": unexpected_chronology,
        "unexpected_source_fold_count": unexpected_source,
        "network_requests": 0,
        "database_accesses": 0,
        "leakage_violation_count": 0,
        "post_as_of_source_used_count": 0,
        "same_or_future_kickoff_history_used_count": 0,
        "feature_semantic_hash": canonical_hash([r["thresholds"] for r in rows]),
    }
    report["audit_sha256"] = canonical_hash(report)
    return report


def write_audit(report, *, output_root, output_dir):
    root, output = Path(output_root).resolve(), Path(output_dir)
    _check(
        output.is_absolute() and output.resolve().is_relative_to(root),
        "output path escape",
    )
    current = output
    while current != root:
        _check(not current.is_symlink(), "output symlink")
        current = current.parent
    _check(not output.exists(), "output already exists")
    output.mkdir(parents=True)
    path = output / "coverage-audit.json"
    with path.open("xb") as stream:
        stream.write(_encode(report) + b"\n")
    return path
