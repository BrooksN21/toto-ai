"""Synthetic O1 contracts: no frozen drawing, DB, provider or runtime access."""

import copy
import hashlib
import importlib
import importlib.util
import json

import pytest


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hash(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _target():
    return {
        "schema_version": 1,
        "provider": "goal-api-v1",
        "drawing_id": 900001,
        "event_order": 0,
        "target_event_id": "synthetic-target",
        "provider_fixture_id": "target-fixture",
        "home_team_id": "home",
        "away_team_id": "away",
        "home_entity_kind": "TEAM_ENTITY",
        "away_entity_kind": "TEAM_ENTITY",
        "kickoff": "2020-02-20T18:00:00+00:00",
        "as_of": "2020-02-19T12:00:00+00:00",
        "final_captured_at": "2020-02-19T12:00:00+00:00",
        "scope": {"home": {}, "away": {}},
        "league_id": None,
        "season": None,
        "final_input_sha256": "a" * 64,
        "scheduler_plan_sha256": "b" * 64,
    }


def _match(side="home", *, identity=None, **changes):
    return {
        "id": identity or side + "-prior",
        "kickoffUtc": "2020-02-18T12:00:00+00:00",
        "homeTeamId": side if side == "home" else "opponent",
        "awayTeamId": side if side == "away" else "opponent",
        "matchStatus": "FINISHED",
        "homeTeamScore": 2,
        "awayTeamScore": 1,
        "leagueId": 101,
        "leagueYear": 2019,
        **changes,
    }


def _source(side, rows=None, **changes):
    endpoint = f"/teams/{side}/results"
    payload = {"success": True, "teamId": side, "data": rows or []}
    return {
        "schema_version": 1,
        "provider": "goal-api-v1",
        "endpoint": endpoint,
        "params": [["limit", "10"]],
        "request_fingerprint": _hash(
            {
                "provider": "goal-api-v1",
                "base_url": "https://api.goal-api.com/v1",
                "endpoint": endpoint,
                "params": [["limit", "10"]],
            }
        ),
        "fetched_at": "2020-02-19T12:00:00+00:00",
        "response_hash": _hash(payload),
        "payload": payload,
        **changes,
    }


def _api():
    name = "toto_ai.sports_stats.v3_family_evidence"
    assert importlib.util.find_spec(name) is not None, "O1 implementation missing"
    return importlib.import_module(name)


def _inputs(target=None, sources=None, cutoff=None):
    api = _api()
    target = _target() if target is None else target
    if sources is None:
        sources = {s: [_source(s, [_match(s)])] for s in ("home", "away")}
    refs = []

    def blob(path, value, kind, side=None):
        raw = _encode(value)
        refs.append(
            api.ReviewedReference(
                path=path,
                sha256=hashlib.sha256(raw).hexdigest(),
                kind=kind,
                provider=target["provider"],
                drawing_id=target["drawing_id"],
                event_order=target["event_order"],
                target_event_id=target["target_event_id"],
                side=side,
            )
        )
        return api.EvidenceBytes(path=path, content=raw)

    target_blob = blob("synthetic/target.json", target, "target_projection")
    histories = {
        s: tuple(
            blob(f"synthetic/{s}-{i}.json", doc, "raw_goal_team_results_response", s)
            for i, doc in enumerate(sources.get(s, []))
        )
        for s in ("home", "away")
    }
    cutoff_blob = (
        blob("synthetic/cutoff.json", cutoff, "cutoff_projection")
        if cutoff is not None
        else None
    )
    return dict(
        event=target_blob,
        verified_event_local_histories=histories,
        reviewed_refs=tuple(refs),
        cutoff_evidence=cutoff_blob,
    )


def _assess(target=None, sources=None, cutoff=None, **overrides):
    inputs = _inputs(target, sources, cutoff)
    return _api().assess_family_evidence(**(inputs | overrides))


def _family(result, side="home", family="rolling_form", threshold=1):
    return result["thresholds"][str(threshold)][side][family]


def test_unknown_scope_is_descriptive_only_and_all_28_columns_are_annotated():
    result = _assess()
    assert result["status"] == "COMPLETE"
    assert _family(result)["descriptive_computability"] is True
    assert result["sides"]["home"]["scope_status"] == dict.fromkeys(
        ("gender", "age_group", "squad_type"), "UNKNOWN"
    )
    assert result["strict_scoped_eligible"] is False
    assert result["evaluation_authorized"] is False
    assert result["activation_allowed"] is False
    assert result["prospective_eligible"] is False
    assert result["cutoff_status"] == "UNKNOWN"
    from toto_ai.sports_stats.v3_features import PREDICTOR_FEATURE_NAMES

    names = [
        name
        for side in result["thresholds"]["1"].values()
        for family in side.values()
        for name in family["feature_names"]
    ]
    assert sorted(names) == sorted(PREDICTOR_FEATURE_NAMES)
    assert len(names) == 28
    assert "features" not in result  # annotations never emit/recalculate predictors


@pytest.mark.parametrize("field", ["gender", "age_group", "squad_type"])
def test_scope_conflict_rejects_affected_side_without_promoting_or_dropping_event(
    field,
):
    target = _target()
    target["scope"]["home"][field] = "expected"
    sources = {
        "home": [_source("home", [_match(**{field: "different"})])],
        "away": [_source("away", [_match("away")])],
    }
    result = _assess(target, sources)
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2
    assert not _family(result)["descriptive_computability"]
    assert _family(result, "away")["descriptive_computability"]
    assert result["sides"]["home"]["scope_status"][field] == "CONFLICT"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t, s: t.update(home_entity_kind="CLUB"),
        lambda t, s: s.update(provider="different-provider"),
        lambda t, s: s.update(endpoint="/teams/away/results"),
        lambda t, s: s["payload"].update(teamId="away"),
        lambda t, s: s["payload"]["data"][0].update(homeTeamId="HOME"),
        lambda t, s: s["payload"]["data"][0].update(id="target-fixture"),
        lambda t, s: s["payload"]["data"][0].update(kickoffUtc=s["fetched_at"]),
        lambda t, s: s.update(fetched_at="2020-02-19T12:00:01+00:00"),
        lambda t, s: s["payload"]["data"][0].update(homeTeamScore=True),
    ],
)
def test_invalid_source_or_entity_cannot_become_missing_or_ready(mutate):
    target, source = _target(), _source("home", [_match()])
    mutate(target, source)
    source["response_hash"] = _hash(source["payload"])
    result = _assess(target, {"home": [source]})
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2
    assert not _family(result)["descriptive_computability"]
    assert result["sides"]["home"]["observed_history_count"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"as_of": "2020-02-19T12:00:01+00:00"},
        {"kickoff": "2020-02-19T12:00:00+00:00"},
        {"as_of": "2020-02-19T12:00:00"},
        {"event_order": True},
        {"actual_outcome": "1"},
    ],
)
def test_invalid_target_is_explicit_integrity_failure(updates):
    target = _target() | updates
    with pytest.raises(_api().EvidenceIntegrityError) as caught:
        _assess(target)
    assert caught.value.exit_code == 2
    assert caught.value.status == "INCOMPLETE"


def test_missing_empty_and_absent_venue_are_distinct_and_opponent_uses_other_side():
    empty = _assess(sources={"home": [_source("home")]})
    assert empty["sides"]["home"]["observed_history_count"] == 0
    assert empty["sides"]["away"]["observed_history_count"] is None
    assert _family(empty, family="prior_count")["descriptive_computability"]
    assert _family(empty, family="congestion")["descriptive_computability"]
    assert not _family(empty)["descriptive_computability"]
    assert not _family(empty, family="opponent_form")["descriptive_computability"]
    result = _assess(
        sources={
            "home": [_source("home", [_match(homeTeamId="other", awayTeamId="home")])],
            "away": [_source("away", [_match("away")])],
        }
    )
    assert _family(result)["descriptive_computability"]
    assert _family(result, family="opponent_form")["descriptive_computability"]
    assert not _family(result, family="venue_form")["descriptive_computability"]
    assert _family(result, family="venue_count")["descriptive_computability"]
    assert _family(result, family="rest_intervals")["interpretation"] == "OBSERVED_ONLY"


def test_thresholds_use_fixed_ten_window_without_changing_count_semantics():
    rows = [_match(identity=f"prior-{i}") for i in range(5)]
    result = _assess(sources={"home": [_source("home", rows)]})
    assert list(result["thresholds"]) == ["1", "3", "5", "10"]
    assert [
        _family(result, threshold=t)["descriptive_computability"] for t in (1, 3, 5, 10)
    ] == [True, True, True, False]
    assert all(
        _family(result, family="prior_count", threshold=t)["descriptive_computability"]
        for t in (1, 3, 5, 10)
    )


def test_duplicate_order_is_deterministic_but_changed_bytes_change_lineage():
    one, two = _match(identity="one"), _match(identity="two")
    first = _assess(sources={"home": [_source("home", [one, two, one])]})
    second = _assess(sources={"home": [_source("home", [one, one, two])]})
    assert first["semantic_hash"] == second["semantic_hash"]
    assert first["lineage_hash"] != second["lineage_hash"]
    assert first["sides"]["home"]["observed_history_count"] == 2
    conflict = _assess(
        sources={"home": [_source("home", [one, one | {"leagueYear": 2020}])]}
    )
    assert conflict["status"] == "INCOMPLETE"
    assert "CONFLICTING_FIXTURE" in conflict["sides"]["home"]["missing_reasons"]


def test_unknown_season_does_not_block_observed_form_or_claim_standings():
    unknown = _assess()
    assert _family(unknown)["descriptive_computability"]
    assert (
        "UNKNOWN_TARGET_SEASON"
        in unknown["unsupported_families"]["season_standings"]["missing_reasons"]
    )
    target = _target() | {"season": 2020, "league_id": 102}
    result = _assess(target)
    assert result["sides"]["home"]["cross_season_count"] == 1
    assert result["sides"]["home"]["cross_league_count"] == 1
    assert _family(result)["descriptive_computability"]
    assert not result["unsupported_families"]["season_standings"][
        "descriptive_computability"
    ]


def test_independent_reviewed_refs_are_required_and_do_not_self_authorize():
    inputs = _inputs()
    inputs["reviewed_refs"] = ()
    with pytest.raises(_api().EvidenceIntegrityError, match="UNREVIEWED_REFERENCE"):
        _api().assess_family_evidence(**inputs)
    inputs = _inputs()
    inputs["event"] = _api().EvidenceBytes(inputs["event"].path, b"{}")
    with pytest.raises(_api().EvidenceIntegrityError, match="FILE_HASH_MISMATCH"):
        _api().assess_family_evidence(**inputs)


def test_another_event_capture_cannot_fill_missing_side_and_ref_binding_is_exact():
    from dataclasses import replace

    inputs = _inputs(sources={"home": [_source("home", [_match()])]})
    refs = list(inputs["reviewed_refs"])
    refs[1] = replace(refs[1], target_event_id="later-target")
    result = _api().assess_family_evidence(**(inputs | {"reviewed_refs": tuple(refs)}))
    assert result["status"] == "INCOMPLETE"
    assert not _family(result)["descriptive_computability"]
    assert result["sides"]["away"]["observed_history_count"] is None


def test_labels_cannot_mutate_caller_features_or_legacy_strict_policy():
    # Existing feature arithmetic is separately covered by the unchanged builder tests.
    inputs = _inputs()
    before = copy.deepcopy(inputs)
    false_result = _api().assess_family_evidence(**inputs)
    true_result = _api().assess_family_evidence(
        **inputs, legacy_strict_scoped_eligible=True
    )
    assert inputs == before
    assert false_result["strict_scoped_eligible"] is False
    assert true_result["strict_scoped_eligible"] is True  # pass-through, not recomputed
    target = _target()
    target["scope"]["home"] = {
        "gender": "men",
        "age_group": "senior",
        "squad_type": "first",
    }
    verified = _assess(target)
    assert (
        _family(false_result)["descriptive_computability"]
        == _family(verified)["descriptive_computability"]
    )
    assert verified["strict_scoped_eligible"] is False
    assert (
        not true_result["evaluation_authorized"]
        and not true_result["activation_allowed"]
    )


def test_cutoff_binding_and_issuance_are_separate_and_never_prospective():
    cutoff = {
        "schema_version": 1,
        "cutoff": "2020-02-20T17:50:00+00:00",
        "plan_sha256": "b" * 64,
        "final_input_sha256": "a" * 64,
        "issued_at": None,
    }
    unknown = _assess(cutoff=cutoff)
    assert unknown["cutoff_status"] == "BOUND_ISSUANCE_UNKNOWN"
    assert not unknown["prospective_eligible"]
    bound = _assess(cutoff=cutoff | {"issued_at": "2020-02-18T12:00:00+00:00"})
    assert bound["cutoff_status"] == "VERIFIED"
    assert not bound["prospective_eligible"]  # no pre-cutoff feature artifact
    with pytest.raises(_api().EvidenceIntegrityError, match="CUTOFF_BINDING"):
        _assess(cutoff=cutoff | {"plan_sha256": "c" * 64})


def test_no_io_or_side_effects_are_needed_after_import(monkeypatch):
    import builtins
    import os
    import socket
    import sqlite3
    import subprocess

    inputs = _inputs()

    def forbidden(*args, **kwargs):
        raise AssertionError("O1 attempted I/O, environment or external execution")

    with monkeypatch.context() as guard:
        for obj, name in (
            (builtins, "open"),
            (os, "open"),
            (os, "getenv"),
            (socket, "socket"),
            (sqlite3, "connect"),
            (subprocess, "Popen"),
        ):
            guard.setattr(obj, name, forbidden)
        result = _api().assess_family_evidence(**inputs)
    assert result["status"] == "COMPLETE"


def test_family_dependencies_and_validation_status_follow_the_actual_input_side():
    result = _assess(sources={"home": [_source("home", [_match()])]})
    assert _family(result)["dependency_side"] == "home"
    assert _family(result, family="opponent_form")["dependency_side"] == "away"
    assert (
        _family(result, family="opponent_form")["identity_status"]
        == "SOURCE_UNAVAILABLE"
    )
    assert (
        _family(result, family="opponent_form")["history_time_status"]
        == "SOURCE_UNAVAILABLE"
    )


def test_terminal_and_nonterminal_witnesses_of_same_fixture_conflict():
    row = _match()
    result = _assess(
        sources={"home": [_source("home", [row, row | {"matchStatus": "LIVE"}])]}
    )
    assert result["status"] == "INCOMPLETE"
    assert "CONFLICTING_FIXTURE" in result["sides"]["home"]["missing_reasons"]


def test_cross_capture_status_conflict_is_not_hidden_by_nonterminal_filter():
    row = _match()
    result = _assess(
        sources={
            "home": [
                _source("home", [row]),
                _source("home", [row | {"matchStatus": "LIVE"}]),
            ]
        }
    )
    assert result["status"] == "INCOMPLETE"


def test_lineage_retains_reference_roles_and_raw_capture_timestamps():
    result = _assess()
    lineage = result["lineage"]
    home = next(r for r in lineage["reviewed_references"] if r["side"] == "home")
    assert home["kind"] == "raw_goal_team_results_response"
    assert home["target_event_id"] == "synthetic-target"
    witness = lineage["source_witnesses"]["home"][0]
    assert witness["fetched_at"] == "2020-02-19T12:00:00+00:00"
    assert witness["endpoint"] == "/teams/home/results"
    assert witness["requested_limit"] == 10
    assert witness["completeness_status"] == "UNKNOWN"


def test_shared_fixture_scope_conflict_after_union_rejects_only_affected_side():
    target = _target()
    target["scope"] = {"home": {"gender": "men"}, "away": {"gender": "women"}}
    row = _match(identity="common", homeTeamId="home", awayTeamId="away")
    result = _assess(
        target,
        {
            "home": [_source("home", [row])],
            "away": [_source("away", [row | {"gender": "women"}])],
        },
    )
    assert result["status"] == "INCOMPLETE"
    assert not _family(result)["descriptive_computability"]
    assert _family(result, "away")["descriptive_computability"]


def test_different_optional_metadata_is_merged_independently_of_witness_order():
    row = _match()
    first = _source("home", [row | {"leagueYear": None}])
    second = _source("home", [row])
    a = _assess(sources={"home": [first, second]})
    b = _assess(sources={"home": [second, first]})
    assert a["semantic_hash"] == b["semantic_hash"]
    assert a["sides"]["home"]["normalized_history"][0]["season"] == 2019


@pytest.mark.parametrize(
    "field,value",
    [
        ("fetched_at", "2020-02-19T12:00:00"),
        ("response_hash", "0" * 64),
        ("request_fingerprint", "0" * 64),
    ],
)
def test_time_or_internal_hash_mutation_fails_even_if_outer_ref_is_reviewed(
    field, value
):
    result = _assess(sources={"home": [_source("home", [_match()], **{field: value})]})
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2


@pytest.mark.parametrize(
    "raw", [b"{", b'{"schema_version": 1, "schema_version": 1}', b"NaN"]
)
def test_unreadable_source_is_rejected_not_empty(raw):
    from dataclasses import replace

    inputs = _inputs()
    home = inputs["verified_event_local_histories"]["home"][0]
    inputs["verified_event_local_histories"]["home"] = (
        _api().EvidenceBytes(home.path, raw),
    )
    inputs["reviewed_refs"] = tuple(
        replace(ref, sha256=hashlib.sha256(raw).hexdigest())
        if ref.path == home.path
        else ref
        for ref in inputs["reviewed_refs"]
    )
    result = _api().assess_family_evidence(**inputs)
    assert result["status"] == "INCOMPLETE"
    assert result["sides"]["home"]["observed_history_count"] is None


def test_nonterminal_only_capture_is_an_observed_zero_not_missing():
    result = _assess(sources={"home": [_source("home", [_match(matchStatus="LIVE")])]})
    assert result["sides"]["home"]["nonterminal_count"] == 1
    assert result["sides"]["home"]["observed_history_count"] == 0
    assert _family(result, family="congestion")["descriptive_computability"]


def test_explicit_scope_conflict_cannot_authorize_even_empty_capture_counts():
    target = _target()
    target["scope"]["home"]["gender"] = "CONFLICT"
    result = _assess(target, {"home": [_source("home")]})
    assert result["status"] == "INCOMPLETE"
    assert not _family(result, family="prior_count")["descriptive_computability"]


def test_missing_target_fixture_preserves_an_all_missing_event_without_synthetic_ids():
    target = _target()
    target.update(
        provider_fixture_id=None,
        home_team_id=None,
        away_team_id=None,
        home_entity_kind=None,
        away_entity_kind=None,
        kickoff=None,
    )
    result = _assess(target, {})
    assert result["status"] == "COMPLETE_WITH_GAPS"
    assert result["target_event_id"] == "synthetic-target"
    assert result["lineage"]["target"]["provider_fixture_id"] is None
    for side in ("home", "away"):
        assert result["sides"][side]["observed_history_count"] is None
        assert "TARGET_FIXTURE_MISSING" in _family(result, side)["missing_reasons"]
        assert not _family(result, side, "prior_count")["descriptive_computability"]


def test_reviewfix_r1_unicode_hash_has_one_provider_canonicalization_only():
    source = _source("home", [_match(homeTeamName="Динамо")])
    accepted = _assess(sources={"home": [source]})
    assert accepted["sides"]["home"]["source_status"] == "AVAILABLE"
    source["response_hash"] = hashlib.sha256(
        json.dumps(
            source["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    rejected = _assess(sources={"home": [source]})
    assert rejected["sides"]["home"]["missing_reasons"] == ["PAYLOAD_HASH"]


def test_reviewfix_r1_unicode_acceptance_does_not_bypass_reviewed_file_hash():
    data = _inputs(sources={"home": [_source("home", [_match(homeTeamName="Malmö")])]})
    blob = data["verified_event_local_histories"]["home"][0]
    data["verified_event_local_histories"]["home"] = (
        _api().EvidenceBytes(
            blob.path, blob.content.replace(b"homeTeamName", b"awayTeamName")
        ),
    )
    result = _api().assess_family_evidence(**data)
    assert result["sides"]["home"]["missing_reasons"] == ["FILE_HASH_MISMATCH"]


@pytest.mark.parametrize("score", [0, 2, "0", "2", "00", "٢"])
def test_reviewfix_r2_legacy_validated_scores_normalize_to_integers(score):
    from toto_ai.sports_stats.v3_coverage_audit import _goals as legacy_goals

    expected = legacy_goals(score)
    data = _inputs(sources={"home": [_source("home", [_match(homeTeamScore=score)])]})
    before = copy.deepcopy(data)
    result = _api().assess_family_evidence(**data)
    assert result["sides"]["home"]["source_status"] == "AVAILABLE"
    actual = result["sides"]["home"]["normalized_history"][0]["home_goals"]
    assert type(actual) is int and actual == expected
    assert data == before


@pytest.mark.parametrize(
    "score", [True, False, -1, "-1", None, "", " 2", "+2", "2.0", 2.0, "²"]
)
def test_reviewfix_r2_malformed_boolean_negative_scores_stay_rejected(score):
    result = _assess(sources={"home": [_source("home", [_match(homeTeamScore=score)])]})
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2
    assert result["sides"]["home"]["missing_reasons"] == ["TERMINAL_SCORE"]


def test_reviewfix_r2_equivalent_raw_score_types_are_compatible_duplicate_witnesses():
    first = _source("home", [_match(homeTeamScore="2", awayTeamScore="1")])
    second = _source("home", [_match(homeTeamScore=2, awayTeamScore=1)])
    a = _assess(sources={"home": [first, second]})
    b = _assess(sources={"home": [second, first]})
    assert a["sides"]["home"]["observed_history_count"] == 1
    assert a["sides"]["home"]["normalized_history"][0]["home_goals"] == 2
    assert a["semantic_hash"] == b["semantic_hash"]


@pytest.mark.parametrize("missing", ["home", "away"])
def test_reviewfix_r3_dependency_metadata_and_thresholds_use_opponent_only(missing):
    other = "away" if missing == "home" else "home"
    result = _assess(sources={other: [_source(other, [_match(other)])]})
    ready = _family(result, missing, "opponent_form")
    assert ready["descriptive_computability"]
    assert ready["dependency_side"] == other
    assert ready["identity_status"] == "VERIFIED_ENTITY"
    assert ready["history_time_status"] == "VERIFIED"
    assert ready["missing_reasons"] == []
    assert not _family(result, missing, "rolling_form")["descriptive_computability"]
    for threshold in (3, 5, 10):
        blocked = _family(result, missing, "opponent_form", threshold)
        assert not blocked["descriptive_computability"]
        assert blocked["missing_reasons"] == ["HISTORY_BELOW_THRESHOLD"]
    assert result["status"] == "COMPLETE_WITH_GAPS"
    assert not result["strict_scoped_eligible"] and not result["evaluation_authorized"]
    assert not result["activation_allowed"]


@pytest.mark.parametrize("missing", ["home", "away"])
def test_reviewfix_r3_actual_opponent_chronology_remains_required(missing):
    other = "away" if missing == "home" else "home"
    result = _assess(
        sources={
            other: [
                _source(other, [_match(other)], fetched_at="2020-02-19T12:00:01+00:00")
            ]
        }
    )
    annotation = _family(result, missing, "opponent_form")
    assert not annotation["descriptive_computability"]
    assert "POST_ASOF_CAPTURE" in annotation["missing_reasons"]
    assert annotation["history_time_status"] == "REJECTED"
    assert result["status"] == "INCOMPLETE" and result["exit_code"] == 2


def test_reviewfix_r3_opponent_only_source_cannot_bypass_common_target_integrity():
    target = _target() | {"as_of": "2020-02-19T12:00:01+00:00"}
    with pytest.raises(_api().EvidenceIntegrityError, match="ASOF_AFTER_FINAL_INPUT"):
        _assess(target, {"away": [_source("away", [_match("away")])]})
