"""O1: pure, additive evidence annotations; never a model or eligibility gate.

ReviewedReference is an explicit trust boundary supplied by the reviewing caller,
not discovered from a manifest, the frozen candidate index, or payload claims.
Hash verification establishes byte integrity, not reviewer authority. This module
does not read files, issue receipts, import the legacy auditor, or calculate any
of the 28 predictors. Target projections must exclude results before invocation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

POLICY_VERSION = "sports-v3-family-evidence-o1-v1"
THRESHOLDS = (1, 3, 5, 10)
SIDES = ("home", "away")
SCOPE_FIELDS = ("gender", "age_group", "squad_type")
FAMILIES = {
    "prior_count": ("prior_match_count",),
    "rolling_form": (
        "rolling_ppg",
        "rolling_goal_difference_per_game",
        "rolling_goals_for_per_game",
        "rolling_goals_against_per_game",
    ),
    "opponent_form": (
        "opponent_rolling_ppg",
        "opponent_rolling_goal_difference_per_game",
    ),
    "rest_intervals": ("days_since_last_match", "rest_days"),
    "congestion": ("matches_in_last_7_days", "matches_in_last_14_days"),
    "venue_count": ("venue_prior_match_count",),
    "venue_form": ("venue_goals_for_per_game", "venue_goals_against_per_game"),
}
_TARGET_FIELDS = frozenset(
    {
        "schema_version",
        "provider",
        "drawing_id",
        "event_order",
        "target_event_id",
        "provider_fixture_id",
        "home_team_id",
        "away_team_id",
        "home_entity_kind",
        "away_entity_kind",
        "kickoff",
        "as_of",
        "final_captured_at",
        "scope",
        "league_id",
        "season",
        "final_input_sha256",
        "scheduler_plan_sha256",
    }
)
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "provider",
        "endpoint",
        "params",
        "request_fingerprint",
        "fetched_at",
        "response_hash",
        "payload",
    }
)


class EvidenceIntegrityError(ValueError):
    """Do not turn integrity/chronology rejection into missing-source coverage."""

    status = "INCOMPLETE"
    exit_code = 2


@dataclass(frozen=True)
class EvidenceBytes:
    path: str
    content: bytes


@dataclass(frozen=True)
class ReviewedReference:
    path: str
    sha256: str
    kind: str
    provider: str
    drawing_id: int
    event_order: int
    target_event_id: str
    side: str | None = None


def _check(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceIntegrityError(reason)


def _hash(value: Any, *, ensure_ascii: bool = False) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=ensure_ascii,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _id(value: Any) -> str:
    _check(type(value) in (str, int) and str(value) != "", "INVALID_IDENTITY")
    return str(value)


def _time(value: Any) -> datetime:
    _check(isinstance(value, str), "INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceIntegrityError("INVALID_TIMESTAMP") from exc
    _check(
        result.tzinfo is not None and result.utcoffset() is not None, "NAIVE_TIMESTAMP"
    )
    return result.astimezone(timezone.utc)


def _literal(value: Any) -> Any:
    _check(
        value is None or (type(value) in (str, int) and value != ""),
        "INVALID_SCOPE_LITERAL",
    )
    return value


def _goals(value: Any) -> int:
    # Preserve the legacy auditor's validated int/digit-string domain. Parse
    # only after provider and outer-file hashes have verified the original bytes.
    _check(
        not isinstance(value, bool)
        and isinstance(value, (int, str))
        and str(value).isdigit(),
        "TERMINAL_SCORE",
    )
    try:
        return int(value)
    except ValueError as exc:
        raise EvidenceIntegrityError("TERMINAL_SCORE") from exc


def _object(pairs):
    document = {}
    for key, value in pairs:
        _check(key not in document, "DUPLICATE_JSON_KEY")
        document[key] = value
    return document


def _read(blob, refs, kind, *, event=None, side=None):
    _check(isinstance(blob, EvidenceBytes), "TYPED_EVIDENCE_BYTES_REQUIRED")
    path = blob.path
    _check(
        isinstance(path, str)
        and not path.startswith(("/", "\\"))
        and "\\" not in path
        and all(p not in ("", ".", "..") for p in path.split("/")),
        "UNSAFE_REFERENCE_PATH",
    )
    candidates = [ref for ref in refs if ref.path == path]
    _check(len(candidates) == 1, "UNREVIEWED_REFERENCE")
    ref = candidates[0]
    _check(ref.kind == kind and ref.side == side, "REFERENCE_ROLE_MISMATCH")
    _check(
        type(blob.content) is bytes and len(blob.content) <= 2_000_000,
        "INVALID_EVIDENCE_BYTES",
    )
    _check(hashlib.sha256(blob.content).hexdigest() == ref.sha256, "FILE_HASH_MISMATCH")
    try:
        document = json.loads(
            blob.content,
            object_pairs_hook=_object,
            parse_constant=lambda _: _check(False, "NONFINITE_JSON"),
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise EvidenceIntegrityError("UNREADABLE_SOURCE") from exc
    _check(isinstance(document, dict), "SOURCE_OBJECT_REQUIRED")
    binding = document if event is None else event
    _check(
        all(
            getattr(ref, key) == binding.get(key)
            for key in ("provider", "drawing_id", "event_order", "target_event_id")
        ),
        "EVENT_REFERENCE_BINDING",
    )
    return document


def _target(document):
    _check(set(document) == _TARGET_FIELDS, "TARGET_PROJECTION_ALLOWLIST")
    _check(
        type(document["schema_version"]) is int and document["schema_version"] == 1,
        "TARGET_SCHEMA",
    )
    _check(document["provider"] == "goal-api-v1", "PROVIDER_NAMESPACE")
    _check(
        type(document["drawing_id"]) is int
        and document["drawing_id"] > 0
        and type(document["event_order"]) is int
        and 0 <= document["event_order"] < 15,
        "TARGET_EVENT_IDENTITY",
    )
    _check(type(document["target_event_id"]) is str, "TARGET_IDENTITY_TYPE")
    _id(document["target_event_id"])
    missing_fixture = document["provider_fixture_id"] is None
    if missing_fixture:
        _check(
            all(
                document[k] is None
                for k in (
                    "home_team_id",
                    "away_team_id",
                    "home_entity_kind",
                    "away_entity_kind",
                    "kickoff",
                )
            ),
            "PARTIAL_TARGET_IDENTITY",
        )
    for key in (
        ()
        if missing_fixture
        else ("provider_fixture_id", "home_team_id", "away_team_id")
    ):
        _check(type(document[key]) is str, "TARGET_IDENTITY_TYPE")
        _id(document[key])
    if not missing_fixture:
        _check(
            document["home_team_id"] != document["away_team_id"], "SAME_TARGET_TEAMS"
        )
    asof = _time(document["as_of"])
    _check(asof <= _time(document["final_captured_at"]), "ASOF_AFTER_FINAL_INPUT")
    if not missing_fixture:
        _check(asof < _time(document["kickoff"]), "TARGET_KICKOFF_CHRONOLOGY")
    _check(
        isinstance(document["scope"], dict) and set(document["scope"]) == set(SIDES),
        "TARGET_SCOPE",
    )
    for scope in document["scope"].values():
        _check(
            isinstance(scope, dict) and set(scope) <= set(SCOPE_FIELDS), "TARGET_SCOPE"
        )
        for value in scope.values():
            _literal(value)
    for field in ("league_id", "season"):
        _literal(document[field])
    for field in ("final_input_sha256", "scheduler_plan_sha256"):
        _check(_digest(document[field]), "FINAL_PLAN_HASH_REQUIRED")
    return document


def _merge(first, second):
    combined = {}
    for key in first:
        one, two = first[key], second[key]
        _check(
            one is None or two is None or (type(one) is type(two) and one == two),
            "CONFLICTING_FIXTURE",
        )
        combined[key] = one if one is not None else two
    return combined


def _check_scope(row, target, side):
    for field in SCOPE_FIELDS:
        expected = target["scope"][side].get(field)
        observed = row.get(field)
        _check(
            expected != "CONFLICT"
            and observed != "CONFLICT"
            and (expected is None or observed is None or expected == observed),
            "SCOPE_CONFLICT_" + field.upper(),
        )


def _source(document, target, side, witnesses):
    team = target[side + "_team_id"]
    _check(set(document) == _ENVELOPE_FIELDS, "RAW_ENVELOPE_FIELDS")
    _check(
        type(document["schema_version"]) is int
        and document["schema_version"] == 1
        and document["provider"] == target["provider"],
        "PROVIDER_SCHEMA",
    )
    endpoint = f"/teams/{team}/results"
    _check(document["endpoint"] == endpoint, "SOURCE_TEAM_ORIENTATION")
    _check(document["params"] == [["limit", "10"]], "REQUEST_LIMIT")
    request = {
        "provider": target["provider"],
        "base_url": "https://api.goal-api.com/v1",
        "endpoint": endpoint,
        "params": document["params"],
    }
    # GOAL writer hashes escaped Unicode; annotation/lineage hashes keep their
    # existing separate canonicalization. Never accept multiple provider hashes.
    _check(
        document["request_fingerprint"] == _hash(request, ensure_ascii=True),
        "REQUEST_HASH",
    )
    capture = _time(document["fetched_at"])
    _check(capture <= _time(target["as_of"]), "POST_ASOF_CAPTURE")
    payload = document["payload"]
    _check(
        isinstance(payload, dict)
        and document["response_hash"] == _hash(payload, ensure_ascii=True),
        "PAYLOAD_HASH",
    )
    _check(
        payload.get("success") is True and _id(payload.get("teamId")) == team,
        "PAYLOAD_TEAM_IDENTITY",
    )
    raw_rows = payload.get("data")
    _check(isinstance(raw_rows, list) and len(raw_rows) <= 10, "RAW_HISTORY_LIMIT")
    rows = {}
    nonterminal = 0
    for raw in raw_rows:
        _check(isinstance(raw, dict), "HISTORY_ROW_OBJECT")
        identity = _id(raw.get("id"))
        _check(identity != target["provider_fixture_id"], "TARGET_FIXTURE_IN_HISTORY")
        witness = {
            key: raw.get(key)
            for key in (
                "matchStatus",
                "kickoffUtc",
                "homeTeamId",
                "awayTeamId",
                "homeTeamScore",
                "awayTeamScore",
                "leagueId",
                "leagueYear",
                *SCOPE_FIELDS,
            )
        }
        terminal = raw.get("matchStatus") in ("FINISHED", "AFTER_ET", "AFTER_PEN")
        if terminal:
            for field in ("homeTeamScore", "awayTeamScore"):
                witness[field] = _goals(raw.get(field))
        witnesses[identity] = (
            _merge(witnesses[identity], witness) if identity in witnesses else witness
        )
        if not terminal:
            nonterminal += 1
            continue
        kickoff = _time(raw.get("kickoffUtc"))
        _check(kickoff < capture, "HISTORY_CAPTURE_CHRONOLOGY")
        home, away = _id(raw.get("homeTeamId")), _id(raw.get("awayTeamId"))
        _check(home != away and team in (home, away), "HISTORY_TEAM_IDENTITY")
        row = {
            "event_id": identity,
            "kickoff": kickoff.isoformat(),
            "home_team_id": home,
            "away_team_id": away,
            "home_goals": witness["homeTeamScore"],
            "away_goals": witness["awayTeamScore"],
            "status": raw["matchStatus"],
            "league_id": _literal(raw.get("leagueId")),
            "season": _literal(raw.get("leagueYear")),
            **{f: _literal(raw.get(f)) for f in SCOPE_FIELDS},
        }
        _check_scope(row, target, side)
        rows[identity] = _merge(rows[identity], row) if identity in rows else row
    return rows, len(raw_rows), nonterminal


def _side(target, side, captures, refs):
    scope = {
        f: "VERIFIED" if target["scope"][side].get(f) is not None else "UNKNOWN"
        for f in SCOPE_FIELDS
    }
    state = {
        "source_status": "SOURCE_UNAVAILABLE",
        "scope_status": scope,
        "missing_reasons": ["SOURCE_UNAVAILABLE"],
        "observed_history_count": None,
        "raw_payload_row_count": None,
        "nonterminal_count": None,
        "cross_league_count": None,
        "cross_season_count": None,
        "normalized_history": [],
        "_fixture_witnesses": {},
        "_source_witnesses": [],
    }
    if not captures:
        if target["provider_fixture_id"] is None:
            state["missing_reasons"].append("TARGET_FIXTURE_MISSING")
        return state
    try:
        _check(
            target["provider_fixture_id"] is not None, "HISTORY_WITHOUT_TARGET_FIXTURE"
        )
        _check(target[side + "_entity_kind"] == "TEAM_ENTITY", "AMBIGUOUS_TEAM_ENTITY")
        _check_scope({}, target, side)
        rows, raw_count, nonterminal = {}, 0, 0
        for blob in captures:
            document = _read(
                blob, refs, "raw_goal_team_results_response", event=target, side=side
            )
            matches, count, skipped = _source(
                document, target, side, state["_fixture_witnesses"]
            )
            state["_source_witnesses"].append(
                {
                    "path": blob.path,
                    "file_sha256": hashlib.sha256(blob.content).hexdigest(),
                    "provider": document["provider"],
                    "endpoint": document["endpoint"],
                    "request_fingerprint": document["request_fingerprint"],
                    "response_hash": document["response_hash"],
                    "fetched_at": document["fetched_at"],
                    "requested_limit": 10,
                    "completeness_status": "UNKNOWN",
                }
            )
            raw_count += count
            nonterminal += skipped
            for key, row in matches.items():
                rows[key] = _merge(rows[key], row) if key in rows else row
        state.update(
            source_status="AVAILABLE",
            missing_reasons=[],
            raw_payload_row_count=raw_count,
            nonterminal_count=nonterminal,
            normalized_history=list(rows.values()),
        )
    except EvidenceIntegrityError as exc:
        _reject(state, str(exc))
    return state


def _reject(state, reason):
    state.update(
        source_status="REJECTED",
        missing_reasons=[reason],
        normalized_history=[],
        observed_history_count=None,
        raw_payload_row_count=None,
        nonterminal_count=None,
    )
    for field in SCOPE_FIELDS:
        if reason == "SCOPE_CONFLICT_" + field.upper():
            state["scope_status"][field] = "CONFLICT"


def _reconcile(target, states):
    # Union is strictly within this call/event; a missing side is never filled.
    if all(states[s]["source_status"] == "AVAILABLE" for s in SIDES):
        home = states["home"]["_fixture_witnesses"]
        away = states["away"]["_fixture_witnesses"]
        try:
            for key in home.keys() & away.keys():
                _merge(home[key], away[key])
        except EvidenceIntegrityError as exc:
            for side in SIDES:
                _reject(states[side], str(exc))
            return
    by_side = {
        s: {r["event_id"]: r for r in states[s]["normalized_history"]} for s in SIDES
    }
    merged = dict(by_side["home"])
    for key, row in by_side["away"].items():
        try:
            merged[key] = _merge(merged[key], row) if key in merged else row
        except EvidenceIntegrityError as exc:
            for side in SIDES:
                _reject(states[side], str(exc))
            return
    for side, state in states.items():
        if state["source_status"] != "AVAILABLE":
            continue
        team = target[side + "_team_id"]
        history = [
            r for r in merged.values() if team in (r["home_team_id"], r["away_team_id"])
        ]
        try:
            for row in history:
                _check_scope(row, target, side)
        except EvidenceIntegrityError as exc:
            _reject(state, str(exc))
            continue
        state["normalized_history"] = sorted(
            history, key=lambda r: (r["kickoff"], r["event_id"]), reverse=True
        )
        state["observed_history_count"] = len(history)
        for field in ("league_id", "season"):
            state[
                "cross_" + ("league" if field == "league_id" else field) + "_count"
            ] = (
                sum(r[field] is not None and r[field] != target[field] for r in history)
                if target[field] is not None
                else None
            )


def _cutoff(blob, target, refs):
    if blob is None:
        return "UNKNOWN", None
    document = _read(blob, refs, "cutoff_projection", event=target)
    _check(
        set(document)
        == {
            "schema_version",
            "cutoff",
            "plan_sha256",
            "final_input_sha256",
            "issued_at",
        },
        "CUTOFF_PROJECTION_ALLOWLIST",
    )
    _check(
        type(document["schema_version"]) is int
        and document["schema_version"] == 1
        and document["plan_sha256"] == target["scheduler_plan_sha256"]
        and document["final_input_sha256"] == target["final_input_sha256"],
        "CUTOFF_BINDING",
    )
    cutoff = _time(document["cutoff"])
    _check(
        _time(target["as_of"]) < cutoff < _time(target["kickoff"])
        and _time(target["final_captured_at"]) < cutoff,
        "CUTOFF_CHRONOLOGY",
    )
    issued = document["issued_at"]
    if issued is not None:
        _check(_time(issued) < cutoff, "CUTOFF_ISSUANCE_CHRONOLOGY")
    return ("VERIFIED" if issued is not None else "BOUND_ISSUANCE_UNKNOWN"), document


def _families(target, states, side, threshold, cutoff_status, lineage_hash):
    state = states[side]
    other = states["away" if side == "home" else "home"]
    window = state["normalized_history"][:10]
    venue = [r for r in window if r[side + "_team_id"] == target[side + "_team_id"]]
    families = {}
    for family, suffixes in FAMILIES.items():
        # Common target integrity is checked before annotations. Source/time
        # readiness is local to the history actually used by this family.
        dependency = other if family == "opponent_form" else state
        available = dependency["source_status"] == "AVAILABLE"
        reasons = list(dependency["missing_reasons"])
        count = (
            len(venue)
            if family == "venue_form"
            else min(dependency["observed_history_count"] or 0, 10)
        )
        if (
            family in ("rolling_form", "opponent_form", "rest_intervals", "venue_form")
            and count < threshold
        ):
            reasons.append(
                "VENUE_HISTORY_BELOW_THRESHOLD"
                if family == "venue_form"
                else "HISTORY_BELOW_THRESHOLD"
            )
        families[family] = {
            "feature_names": [side + "_" + suffix for suffix in suffixes],
            "descriptive_computability": available and not reasons,
            "identity_status": (
                "VERIFIED_ENTITY" if available else dependency["source_status"]
            ),
            "history_time_status": (
                "VERIFIED" if available else dependency["source_status"]
            ),
            "cutoff_status": cutoff_status,
            "required_scope_status": "NOT_REQUIRED_FOR_OBSERVED_ENTITY",
            "missing_reasons": sorted(set(reasons)),
            "interpretation": "OBSERVED_ONLY"
            if family in ("rest_intervals", "congestion")
            else "SOURCE_BOUNDED",
            "dependency_side": ("away" if side == "home" else "home")
            if family == "opponent_form"
            else side,
            "lineage_hash": lineage_hash,
        }
    return families


def assess_family_evidence(
    *,
    event: EvidenceBytes,
    verified_event_local_histories: Mapping[str, Sequence[EvidenceBytes]],
    reviewed_refs: Sequence[ReviewedReference],
    cutoff_evidence: EvidenceBytes | None = None,
    legacy_strict_scoped_eligible: bool = False,
    policy_version: str = POLICY_VERSION,
) -> dict[str, Any]:
    """Annotate evidence only. Never pass descriptive readiness to F4 or a gate.

    The caller supplies independently reviewed, event-bound references and bytes.
    No reference becomes trusted merely because its hash is self-consistent.
    Legacy eligibility is explicitly passed through, not evaluated or promoted.
    A target/ref failure raises EvidenceIntegrityError (INCOMPLETE/exit2); a side
    failure retains the event and valid other side with INCOMPLETE/exit2 metadata.
    """
    _check(policy_version == POLICY_VERSION, "UNSUPPORTED_POLICY_VERSION")
    _check(type(legacy_strict_scoped_eligible) is bool, "LEGACY_ELIGIBILITY_TYPE")
    _check(
        all(
            isinstance(ref, ReviewedReference)
            and _digest(ref.sha256)
            and type(ref.drawing_id) is int
            and type(ref.event_order) is int
            for ref in reviewed_refs
        ),
        "TYPED_REVIEWED_REFS_REQUIRED",
    )
    _check(
        len({ref.path for ref in reviewed_refs}) == len(reviewed_refs),
        "DUPLICATE_REVIEWED_REF",
    )
    _check(
        set(verified_event_local_histories) == set(SIDES), "EVENT_LOCAL_SIDES_REQUIRED"
    )
    target = _target(_read(event, reviewed_refs, "target_projection"))
    cutoff_status, cutoff = _cutoff(cutoff_evidence, target, reviewed_refs)
    states = {
        s: _side(target, s, verified_event_local_histories[s], reviewed_refs)
        for s in SIDES
    }
    _reconcile(target, states)
    blobs = [event, *(b for s in SIDES for b in verified_event_local_histories[s])]
    if cutoff_evidence is not None:
        blobs.append(cutoff_evidence)
    used_paths = {b.path for b in blobs}
    source_witnesses = {}
    for side, state in states.items():
        state.pop("_fixture_witnesses")
        source_witnesses[side] = sorted(
            state.pop("_source_witnesses"), key=lambda w: w["path"]
        )
    lineage = {
        "policy_version": policy_version,
        "target": target,
        "cutoff": cutoff,
        "reviewed_references": sorted(
            [asdict(ref) for ref in reviewed_refs if ref.path in used_paths],
            key=lambda ref: ref["path"],
        ),
        "source_witnesses": source_witnesses,
        "references": sorted(
            [
                {"path": b.path, "sha256": hashlib.sha256(b.content).hexdigest()}
                for b in blobs
            ],
            key=lambda r: (r["path"], r["sha256"]),
        ),
    }
    lineage_hash = _hash(lineage)
    incomplete = any(s["source_status"] == "REJECTED" for s in states.values())
    missing = any(s["source_status"] == "SOURCE_UNAVAILABLE" for s in states.values())
    result = {
        "schema_version": 1,
        "artifact_class": "SPORTS_V3_O1_FAMILY_EVIDENCE",
        "policy_version": policy_version,
        "target_event_id": target["target_event_id"],
        "drawing_id": target["drawing_id"],
        "event_order": target["event_order"],
        "status": "INCOMPLETE"
        if incomplete
        else "COMPLETE_WITH_GAPS"
        if missing
        else "COMPLETE",
        "exit_code": 2 if incomplete else 0,
        "sides": states,
        "cutoff_status": cutoff_status,
        "strict_scoped_eligible": legacy_strict_scoped_eligible,
        "strict_eligibility_source": "PASSTHROUGH_NOT_REASSESSED",
        "evaluation_authorized": False,
        "activation_allowed": False,
        "prospective_eligible": False,
        "automatic_wagering": False,
        "operator_compatible": False,
        "unsupported_families": {
            "season_standings": {
                "descriptive_computability": False,
                "missing_reasons": ["NOT_IMPLEMENTED"]
                + (["UNKNOWN_TARGET_SEASON"] if target["season"] is None else [])
                + (["UNKNOWN_TARGET_LEAGUE"] if target["league_id"] is None else []),
            }
        },
        "thresholds": {
            str(t): {
                s: _families(target, states, s, t, cutoff_status, lineage_hash)
                for s in SIDES
            }
            for t in THRESHOLDS
        },
    }
    # Byte witness order affects lineage, not the normalized descriptive decision.
    semantic = {k: v for k, v in result.items() if k != "thresholds"}
    semantic["thresholds"] = {
        t: {
            s: {
                f: {k: v for k, v in a.items() if k != "lineage_hash"}
                for f, a in families.items()
            }
            for s, families in sides.items()
        }
        for t, sides in result["thresholds"].items()
    }
    result.update(
        semantic_hash=_hash(semantic), lineage_hash=lineage_hash, lineage=lineage
    )
    return result
