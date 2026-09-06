"""Independent synthetic acceptance probes against hash-bound O1 candidate bytes.

The three regression groups intentionally fail on the reviewed candidate.
No candidate files, raw drawing artifacts, network or databases are accessed.
"""

import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime

import pytest

from toto_ai.external_odds.goal_api import _sha256_json as provider_hash
from toto_ai.sports_stats.v3_coverage_audit import _goals as legacy_goals
from toto_ai.sports_stats.v3_family_evidence import (
    EvidenceBytes,
    EvidenceIntegrityError,
    ReviewedReference,
    assess_family_evidence,
)
from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table


def target():
    return {
        "schema_version": 1,
        "provider": "goal-api-v1",
        "drawing_id": 900099,
        "event_order": 4,
        "target_event_id": "independent-synthetic-event",
        "provider_fixture_id": "target",
        "home_team_id": "H",
        "away_team_id": "A",
        "home_entity_kind": "TEAM_ENTITY",
        "away_entity_kind": "TEAM_ENTITY",
        "kickoff": "2020-03-04T12:00:00+00:00",
        "as_of": "2020-03-03T12:00:00+00:00",
        "final_captured_at": "2020-03-03T12:00:00+00:00",
        "scope": {"home": {}, "away": {}},
        "league_id": None,
        "season": None,
        "final_input_sha256": "a" * 64,
        "scheduler_plan_sha256": "b" * 64,
    }


def match(side="home", **changes):
    team = "H" if side == "home" else "A"
    return {
        "id": "prior-" + team,
        "homeTeamId": team,
        "awayTeamId": "opponent",
        "kickoffUtc": "2020-03-02T12:00:00+00:00",
        "matchStatus": "FINISHED",
        "homeTeamScore": 2,
        "awayTeamScore": 1,
        **changes,
    }


def source(side="home", rows=None, **changes):
    team = "H" if side == "home" else "A"
    endpoint = f"/teams/{team}/results"
    params = [["limit", "10"]]
    payload = {"success": True, "teamId": team, "data": rows or []}
    return {
        "schema_version": 1,
        "provider": "goal-api-v1",
        "endpoint": endpoint,
        "params": params,
        "request_fingerprint": provider_hash(
            {
                "provider": "goal-api-v1",
                "base_url": "https://api.goal-api.com/v1",
                "endpoint": endpoint,
                "params": params,
            }
        ),
        "fetched_at": "2020-03-03T12:00:00+00:00",
        "response_hash": provider_hash(payload),
        "payload": payload,
        **changes,
    }


def inputs(event=None, sources=None):
    event = target() if event is None else event
    sources = sources if sources is not None else {"home": [source(rows=[match()])]}
    refs = []

    def bind(path, doc, kind, side=None):
        raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        refs.append(
            ReviewedReference(
                path=path,
                sha256=hashlib.sha256(raw).hexdigest(),
                kind=kind,
                provider=event["provider"],
                drawing_id=event["drawing_id"],
                event_order=event["event_order"],
                target_event_id=event["target_event_id"],
                side=side,
            )
        )
        return EvidenceBytes(path, raw)

    event_blob = bind("independent/target.json", event, "target_projection")
    histories = {
        side: tuple(
            bind(
                f"independent/{side}-{i}.json",
                doc,
                "raw_goal_team_results_response",
                side,
            )
            for i, doc in enumerate(sources.get(side, []))
        )
        for side in ("home", "away")
    }
    return {
        "event": event_blob,
        "verified_event_local_histories": histories,
        "reviewed_refs": tuple(refs),
    }


def family(result, side="home", name="rolling_form"):
    return result["thresholds"]["1"][side][name]


def test_ascii_control_and_immutable_inputs():
    data = inputs()
    before = copy.deepcopy(data)
    result = assess_family_evidence(**data, legacy_strict_scoped_eligible=True)
    assert data == before
    assert family(result)["descriptive_computability"]
    assert result["strict_scoped_eligible"] is True
    assert all(
        result[key] is False
        for key in (
            "evaluation_authorized",
            "activation_allowed",
            "prospective_eligible",
            "automatic_wagering",
            "operator_compatible",
        )
    )
    assert "features" not in result


@pytest.mark.parametrize("name", ["Malmö", "Динамо"])
def test_r1_provider_canonical_unicode_hash_is_accepted(name):
    result = assess_family_evidence(
        **inputs(sources={"home": [source(rows=[match(homeTeamName=name)])]})
    )
    assert result["sides"]["home"]["source_status"] == "AVAILABLE", result["sides"][
        "home"
    ]


@pytest.mark.parametrize("score", ["0", "2"])
def test_r2_existing_numeric_string_score_semantics_are_preserved(score):
    assert legacy_goals(score) == int(score)
    result = assess_family_evidence(
        **inputs(sources={"home": [source(rows=[match(homeTeamScore=score)])]})
    )
    assert result["sides"]["home"]["source_status"] == "AVAILABLE", result["sides"][
        "home"
    ]


@pytest.mark.parametrize("missing", ["home", "away"])
def test_r3_opponent_form_depends_only_on_current_opponent_history(missing):
    available = "away" if missing == "home" else "home"
    prior = match(available)
    result = assess_family_evidence(
        **inputs(sources={available: [source(available, [prior])]})
    )
    event = target()
    table = build_sports_v3_feature_table(
        target_events=[
            {
                "event_id": event["target_event_id"],
                "event_order": event["event_order"],
                "home_team_id": "H",
                "away_team_id": "A",
                "kickoff": datetime.fromisoformat(event["kickoff"]),
            }
        ],
        completed_matches=[
            {
                "event_id": prior["id"],
                "home_team_id": prior["homeTeamId"],
                "away_team_id": prior["awayTeamId"],
                "kickoff": datetime.fromisoformat(prior["kickoffUtc"]),
                "home_goals": 2,
                "away_goals": 1,
                "status": "FT",
                "venue_id": None,
            }
        ],
        rolling_window=10,
        minimum_prior_matches=1,
    )
    assert table.rows[0].features[missing + "_rolling_ppg"] is None
    assert table.rows[0].features[missing + "_opponent_rolling_ppg"] == 3.0
    assert family(result, missing, "opponent_form")["descriptive_computability"], (
        family(result, missing, "opponent_form")
    )


@pytest.mark.parametrize("field", ["gender", "age_group", "squad_type"])
def test_explicit_conflict_fails_closed_but_other_side_survives(field):
    event = target()
    event["scope"]["home"][field] = "expected"
    result = assess_family_evidence(
        **inputs(
            event,
            {
                "home": [source(rows=[match(**{field: "different"})])],
                "away": [source("away", [match("away")])],
            },
        )
    )
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2
    assert result["sides"]["home"]["scope_status"][field] == "CONFLICT"
    assert family(result, "away")["descriptive_computability"]


@pytest.mark.parametrize(
    "change",
    [
        {"kickoffUtc": "2020-03-03T12:00:00+00:00"},
        {"kickoffUtc": "2020-03-05T12:00:00+00:00"},
        {"id": "target"},
    ],
)
def test_history_temporal_and_target_fixture_rejections(change):
    result = assess_family_evidence(
        **inputs(sources={"home": [source(rows=[match(**change)])]})
    )
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2


def test_post_asof_source_cannot_fill_event():
    result = assess_family_evidence(
        **inputs(
            sources={
                "home": [source(rows=[match()], fetched_at="2020-03-03T12:00:01+00:00")]
            }
        )
    )
    assert result["sides"]["home"]["missing_reasons"] == ["POST_ASOF_CAPTURE"]


@pytest.mark.parametrize("field", ["actual_outcome", "score", "settlement", "payout"])
def test_target_result_fields_are_never_admitted(field):
    with pytest.raises(EvidenceIntegrityError, match="TARGET_PROJECTION_ALLOWLIST"):
        assess_family_evidence(**inputs(target() | {field: "not-an-input"}))


def test_hashes_alone_do_not_supply_missing_review_authority():
    data = inputs()
    with pytest.raises(EvidenceIntegrityError, match="UNREVIEWED_REFERENCE"):
        assess_family_evidence(**(data | {"reviewed_refs": ()}))


def test_review_binding_is_event_local():
    data = inputs()
    refs = tuple(
        replace(ref, target_event_id="another-event") if ref.side else ref
        for ref in data["reviewed_refs"]
    )
    result = assess_family_evidence(**(data | {"reviewed_refs": refs}))
    assert result["sides"]["home"]["missing_reasons"] == ["EVENT_REFERENCE_BINDING"]
