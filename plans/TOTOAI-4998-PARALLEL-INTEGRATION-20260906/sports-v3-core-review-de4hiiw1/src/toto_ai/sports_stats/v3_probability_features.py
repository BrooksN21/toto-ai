"""Reviewed raw evidence -> regulation-90 predictors; no I/O or authority."""

from __future__ import annotations

import hashlib
import json
import math

from toto_ai.sports_stats.goal_probe_research import _nonnegative_int
from toto_ai.sports_stats.v3_family_evidence import (
    ReviewedReference,
    assess_family_evidence,
)
from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table
from toto_ai.sports_stats.v3_probability import (
    DIFFERENCES,
    FEATURE_NAMES,
    _bk,
    _check,
    _time,
    digest,
    seal,
)

SCOPE = ("gender", "age_group", "squad_type")
TERMINAL = {"FINISHED": "FT", "AFTER_ET": "AET", "AFTER_PEN": "PEN"}


def regulation_score(raw):
    """Same field choice/integer parser as the accepted GOAL history importer.

    Differential tests bind this to the scheduler-independent canonical loader.
    Aggregate/extra/penalty scores never reconstruct missing regulation scores.
    """
    _check(raw.get("matchStatus") in TERMINAL, "non_terminal_status")
    suffix = "FtScore" if raw["matchStatus"] in ("AFTER_ET", "AFTER_PEN") else "Score"
    return tuple(
        _nonnegative_int(raw.get(side + suffix), side + suffix)
        for side in ("homeTeam", "awayTeam")
    )


def _verified(blob, refs, kind, *, target=None, side=None):
    _check(len(blob.content) <= 2_000_000, "evidence size cap")
    matches = [
        r for r in refs if isinstance(r, ReviewedReference) and r.path == blob.path
    ]
    _check(len(matches) == 1, "independently reviewed reference required")
    ref = matches[0]
    _check(
        ref.sha256 == hashlib.sha256(blob.content).hexdigest()
        and ref.kind == kind
        and ref.provider == "goal-api-v1"
        and ref.side == side,
        "reviewed evidence binding",
    )
    document = json.loads(blob.content)
    identity = document if target is None else target
    _check(
        (ref.drawing_id, ref.event_order, ref.target_event_id)
        == (
            identity["drawing_id"],
            identity["event_order"],
            identity["target_event_id"],
        ),
        "event-local reference binding",
    )
    return document


def _history(document, *, team, target):
    _check(
        document["schema_version"] == 1 and document["provider"] == "goal-api-v1",
        "history provider/schema",
    )
    _check(document["endpoint"] == f"/teams/{team}/results", "history team orientation")
    capture = _time(document["fetched_at"])
    _check(capture <= _time(target["as_of"]), "post-as_of source")
    params = document["params"]
    if "http_status" in document:
        _check(
            document["http_status"] == 200 and params == {"limit": 10},
            "history HTTP/limit",
        )
    else:
        _check(params == [["limit", "10"]], "history limit")
        request = {
            "provider": "goal-api-v1",
            "base_url": "https://api.goal-api.com/v1",
            "endpoint": document["endpoint"],
            "params": params,
        }
        _check(
            document["request_fingerprint"] == digest(request), "history request hash"
        )
        _check(
            document["response_hash"] == digest(document["payload"]),
            "history payload hash",
        )
    payload = document["payload"]
    _check(
        payload.get("success") is True and str(payload.get("teamId")) == team,
        "history payload team",
    )
    rows = payload["data"]
    _check(isinstance(rows, list) and len(rows) <= 10, "history row cap")
    seen, accepted, excluded = set(), [], []
    for raw in rows:
        _check(isinstance(raw, dict), "history row object")
        if raw.get("matchStatus") not in TERMINAL:
            excluded.append("non_terminal_status")
            continue
        identity = raw.get("id")
        _check(
            isinstance(identity, str) and identity and identity not in seen,
            "duplicate/invalid history identity",
        )
        seen.add(identity)
        _check(identity != target["provider_fixture_id"], "target in history")
        starts = _time(raw["kickoffUtc"])
        _check(
            starts < capture
            and starts < _time(target["as_of"])
            and starts < _time(target["kickoff"]),
            "history chronology",
        )
        home, away = raw.get("homeTeamId"), raw.get("awayTeamId")
        _check(
            isinstance(home, str)
            and home
            and isinstance(away, str)
            and away
            and home != away
            and team in (home, away),
            "history team identity",
        )
        try:
            home_goals, away_goals = regulation_score(raw)
        except ValueError:
            excluded.append(
                "INVALID_OR_MISSING_REGULATION_SCORE"
                if raw["matchStatus"] != "FINISHED"
                else "INVALID_FINISHED_SCORE"
            )
            continue
        accepted.append(
            {
                "event_id": identity,
                "kickoff": starts,
                "home_team_id": home,
                "away_team_id": away,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "status": TERMINAL[raw["matchStatus"]],
                "scope": {k: raw.get(k) for k in SCOPE},
                "league_id": raw.get("leagueId"),
                "season": raw.get("leagueYear"),
                "available_at": capture,
            }
        )
    return accepted, excluded


def _merge(matches):
    result = {}
    for match in matches:
        identity = match["event_id"]
        if identity in result:

            def comparable(row):
                return {k: v for k, v in row.items() if k != "available_at"}

            _check(
                comparable(result[identity]) == comparable(match),
                "conflicting duplicate history",
            )
            result[identity] = {
                **match,
                "available_at": min(
                    result[identity]["available_at"], match["available_at"]
                ),
            }
        else:
            result[identity] = match
    return sorted(
        result.values(), key=lambda m: (m["kickoff"], m["event_id"]), reverse=True
    )


def _points(match, team):
    home = match["home_team_id"] == team
    scored = match["home_goals"] if home else match["away_goals"]
    conceded = match["away_goals"] if home else match["home_goals"]
    return (3 if scored > conceded else int(scored == conceded)), scored - conceded


def _extras(features, matches, target, side, independent, minimum):
    team = target[side + "_team_id"]
    window = [m for m in matches if team in (m["home_team_id"], m["away_team_id"])][:10]
    if len(window) < minimum:
        return
    latest = window[0]["kickoff"]
    weighted = [
        (
            math.exp(
                -math.log(2) * (latest - m["kickoff"]).total_seconds() / (30 * 86400)
            ),
            _points(m, team),
        )
        for m in window
    ]
    total = math.fsum(w for w, _ in weighted)
    features[side + "_recency_ppg"] = math.fsum(w * p[0] for w, p in weighted) / total
    features[side + "_recency_goal_difference"] = (
        math.fsum(w * p[1] for w, p in weighted) / total
    )
    strengths, adjusted = [], []
    for match in window:
        opponent = (
            match["away_team_id"]
            if match["home_team_id"] == team
            else match["home_team_id"]
        )
        # Crucially earlier than that historical match, not merely target as_of.
        prior = [
            m
            for m in independent.get(opponent, ())
            if m["kickoff"] < match["kickoff"]
            and m["available_at"] < match["kickoff"]
            and m["event_id"] != match["event_id"]
        ][:10]
        if len(prior) < minimum:
            return  # Never replace missing independent opponent form with target form.
        strength = math.fsum(_points(m, opponent)[0] for m in prior) / len(prior)
        strengths.append(strength)
        adjusted.append(_points(match, team)[0] + strength - 1.0)
    features[side + "_independent_opponent_ppg"] = math.fsum(strengths) / len(strengths)
    features[side + "_opponent_adjusted_ppg"] = math.fsum(adjusted) / len(adjusted)


def build_v3_predictors(
    *,
    event,
    verified_event_local_histories,
    reviewed_refs,
    drawing_number,
    bk_probabilities,
    deadline,
    minimum_prior_matches=3,
    bk_margin=None,
    opponent_histories=None,
    standings=None,
):
    """ReviewedReference is caller review authority, never auto-discovered.

    O1 stays descriptive. V3's strict source/scope checks are separately performed;
    their success does not grant F3/F4 or operator eligibility.
    """
    target = _verified(event, reviewed_refs, "target_projection")
    _bk(bk_probabilities)
    _check(
        set(verified_event_local_histories) == {"home", "away"}, "event-local histories"
    )
    _check(
        type(minimum_prior_matches) is int and 1 <= minimum_prior_matches <= 10,
        "prior threshold",
    )
    _check(
        _time(target["as_of"]) <= _time(target["final_captured_at"]) < _time(deadline),
        "target deadline chronology",
    )
    exact = target["provider_fixture_id"] is not None
    if exact:
        _check(
            target["home_team_id"] != target["away_team_id"]
            and _time(target["as_of"]) < _time(target["kickoff"]),
            "target identity/chronology",
        )
    features = dict.fromkeys(FEATURE_NAMES)
    reasons, matches, sources = (
        [],
        {"home": [], "away": []},
        [hashlib.sha256(event.content).hexdigest()],
    )
    rejected = False
    scoped = exact and target["league_id"] is not None and target["season"] is not None
    for side in ("home", "away"):
        scoped = scoped and all(target["scope"][side].get(k) is not None for k in SCOPE)
        blobs = verified_event_local_histories[side]
        _check(len(blobs) <= 4, "history capture cap")
        if not blobs:
            reasons.append(side + "_HISTORY_MISSING")
        for blob in blobs:
            sources.append(hashlib.sha256(blob.content).hexdigest())
            try:
                document = _verified(
                    blob,
                    reviewed_refs,
                    "raw_goal_team_results_response",
                    target=target,
                    side=side,
                )
                _check(
                    exact and target[side + "_entity_kind"] == "TEAM_ENTITY",
                    "exact team target required",
                )
                rows, exclusions = _history(
                    document, team=target[side + "_team_id"], target=target
                )
                reasons.extend(side + "_" + e for e in exclusions)
                for row in rows:
                    for key in SCOPE:
                        wanted, actual = (
                            target["scope"][side].get(key),
                            row["scope"].get(key),
                        )
                        _check(
                            wanted is None or actual is None or wanted == actual,
                            "scope conflict",
                        )
                        scoped = scoped and wanted is not None and actual == wanted
                    scoped = (
                        scoped
                        and row["league_id"] == target["league_id"]
                        and str(row["season"]) == str(target["season"])
                    )
                matches[side].extend(rows)
            except (ValueError, KeyError, TypeError) as error:
                rejected = True
                reasons.append(side + "_SOURCE_REJECTED:" + str(error))
        matches[side] = _merge(matches[side])
    independent = {}
    for team, blobs in (opponent_histories or {}).items():
        _check(len(independent) < 20 and len(blobs) <= 4, "opponent evidence cap")
        rows = []
        for blob in blobs:
            document = _verified(
                blob, reviewed_refs, "independent_opponent_history", target=target
            )
            parsed, exclusions = _history(document, team=team, target=target)
            rows.extend(parsed)
            reasons.extend("opponent_" + r for r in exclusions)
            sources.append(hashlib.sha256(blob.content).hexdigest())
        independent[team] = _merge(rows)
    if exact:
        merged = _merge([*matches["home"], *matches["away"]])
        table = build_sports_v3_feature_table(
            target_events=[
                {
                    "event_id": target["provider_fixture_id"],
                    "event_order": target["event_order"],
                    "home_team_id": target["home_team_id"],
                    "away_team_id": target["away_team_id"],
                    "kickoff": _time(target["kickoff"]),
                }
            ],
            completed_matches=merged,
            rolling_window=10,
            minimum_prior_matches=minimum_prior_matches,
        )
        features.update(table.rows[0].features)
        for suffix in DIFFERENCES:
            home, away = features["home_" + suffix], features["away_" + suffix]
            features["difference_" + suffix] = (
                home - away if home is not None and away is not None else None
            )
        for side in ("home", "away"):
            _extras(
                features,
                matches[side],
                target,
                side,
                independent,
                minimum_prior_matches,
            )
    for side, blob in (standings or {}).items():
        _check(side in ("home", "away"), "standings side")
        document = _verified(
            blob, reviewed_refs, "season_standings", target=target, side=side
        )
        _check(
            _time(document["captured_at"]) <= _time(target["as_of"]), "late standings"
        )
        _check(
            document["team_id"] == target[side + "_team_id"]
            and document["league_id"] == target["league_id"]
            and str(document["season"]) == str(target["season"]),
            "standings exact scope",
        )
        for suffix in ("rank", "points", "goal_difference"):
            value = document[suffix]
            _check(
                type(value) in (int, float) and math.isfinite(value), "standings value"
            )
            features[side + "_standings_" + suffix] = value
        sources.append(hashlib.sha256(blob.content).hexdigest())
    features["bk_margin"] = bk_margin
    features["bk_entropy"] = -math.fsum(p * math.log(p) for p in bk_probabilities)
    o1 = None
    try:
        o1 = assess_family_evidence(
            event=event,
            verified_event_local_histories=verified_event_local_histories,
            reviewed_refs=reviewed_refs,
        )
    except ValueError:
        reasons.append("O1_ANNOTATION_UNAVAILABLE")
    return seal(
        {
            "kind": "SPORTS_V3_PREDICTORS",
            "schema_version": 1,
            "drawing_number": drawing_number,
            "drawing_id": target["drawing_id"],
            "event_order": target["event_order"],
            "event_id": target["target_event_id"],
            "provider_fixture_id": target["provider_fixture_id"],
            "home_team_id": target["home_team_id"],
            "away_team_id": target["away_team_id"],
            "as_of": target["as_of"],
            "bk_captured_at": target["final_captured_at"],
            "kickoff": target["kickoff"],
            "deadline": deadline,
            "bk_input_sha256": target["final_input_sha256"],
            "scheduler_plan_sha256": target["scheduler_plan_sha256"],
            "bk_probabilities": list(bk_probabilities),
            "bk_margin": bk_margin,
            "features": features,
            "prior_counts": [min(len(matches[s]), 10) for s in ("home", "away")],
            "exact_target": exact,
            "scope_verified": bool(scoped),
            "source_rejected": rejected,
            "source_hashes": sorted(set(sources)),
            "missing_reasons": sorted(set(reasons)),
            "o1_lineage_hash": None if o1 is None else o1["lineage_hash"],
            "o1_strict_eligibility": False,
            "evaluation_authorized": False,
            "feature_policy": {
                "rolling_window": 10,
                "minimum_prior_matches": minimum_prior_matches,
                "recency_half_life_days": 30,
                "regulation_score_basis": "EXPLICIT_FT_FOR_AET_PEN",
            },
        }
    )
