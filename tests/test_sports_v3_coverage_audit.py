"""Synthetic read-only coverage contract, no live inputs or storage calls."""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from toto_ai.sports_stats.v3_coverage_audit import (
    audit_event,
    audit_manifest,
    canonical_hash,
    write_audit,
)

UTC = timezone.utc
ASOF = "2020-01-31T12:00:00Z"
TARGET = "2020-02-01T18:00:00Z"
DEADLINE = "2020-02-01T16:30:00Z"
CUTOFF = "2020-02-01T16:20:00Z"
PLAN = (
    Path(__file__).resolve().parents[1]
    / "plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904"
)


def seal_raw(doc):
    doc["response_hash"] = canonical_hash(doc["payload"])
    doc["request_fingerprint"] = canonical_hash(
        {
            "provider": "goal-api-v1",
            "base_url": "https://api.goal-api.com/v1",
            "endpoint": doc["endpoint"],
            "params": doc["params"],
        }
    )
    return doc


def base():
    spec = json.loads((PLAN / "P1_FIXTURE_CASES.json").read_text())
    event = {
        "event_order": 0,
        "target_event_id": "target-0",
        "provider_fixture_id": "target-0",
        "provider_home_team_id": "H",
        "provider_away_team_id": "A",
        "target_starts_at": TARGET,
        "identity_scope": {
            "gender": "women",
            "age_group": "senior",
            "squad_type": "first_team",
            "league_id": "L",
            "season": "2019-2020",
        },
    }
    documents = {}
    for side, team in (("home", "H"), ("away", "A")):
        rows = []
        for raw in spec["core_event"]["history"]:
            if team not in (raw["home"], raw["away"]):
                continue
            rows.append(
                {
                    "id": raw["id"],
                    "kickoffUtc": raw["kickoff"],
                    "homeTeamId": raw["home"],
                    "awayTeamId": raw["away"],
                    "homeTeamScore": raw["home_goals"],
                    "awayTeamScore": raw["away_goals"],
                    "matchStatus": "FINISHED",
                    "gender": "women",
                    "age_group": "senior",
                    "squad_type": "first_team",
                    "leagueId": "L",
                    "leagueYear": "2019-2020",
                }
            )
        documents[side] = seal_raw(
            {
                "schema_version": 1,
                "provider": "goal-api-v1",
                "endpoint": f"/teams/{team}/results",
                "params": [["limit", "10"]],
                "fetched_at": "2020-01-31T11:00:00Z",
                "payload": {"success": True, "teamId": team, "data": rows},
            }
        )
    return event, documents


def run(event=None, documents=None, **kw):
    e, d = base()
    return audit_event(
        event or e,
        d if documents is None else documents,
        as_of=kw.pop("as_of", ASOF),
        deadline=DEADLINE,
        final_captured_at=kw.pop("final_captured_at", ASOF),
        cutoff=kw.pop("cutoff", CUTOFF),
        **kw,
    )


def test_c01_exact_counts_thresholds_and_features():
    row = run()
    assert row["source_status"] == "complete"
    assert row["counts"]["home"]["raw_payload_row_count"] == 5
    assert row["counts"]["away"]["eligible_prior_count"] == 3
    assert row["counts"]["home"]["venue_prior_count"] == 3
    assert row["counts"]["away"]["venue_prior_count"] == 1
    for t, core, full in [
        (1, True, True),
        (3, True, False),
        (5, False, False),
        (10, False, False),
    ]:
        assert row["thresholds"][str(t)]["both_core"] is core
        assert row["thresholds"][str(t)]["full_current_features"] is full
    f = row["thresholds"]["1"]["features"]
    assert f["home_rolling_ppg"] == pytest.approx(7 / 5)
    assert f["away_rolling_ppg"] == pytest.approx(4 / 3)
    assert f["home_venue_goals_for_per_game"] == pytest.approx(2 / 3)


def frozen_fixture(root, number=4993, covered=1):
    from toto_ai.external_odds.eligibility import target_fingerprint
    from toto_ai.external_odds.targets import parse_target_drawing
    from toto_ai.package.audit import canonical_probability_input_sha256

    root.mkdir(parents=True)
    payload = {
        "version": "test",
        "data": {
            "id": 990001 + number,
            "number": number,
            "name": "baltbet-main",
            "ended_at": "2020-02-01T19:30:00Z",
            "status": "open",
            "pool_sum": 100000,
            "jackpot": 0,
            "payments": [],
            "events": [
                {
                    "id": 190000 + i,
                    "order": i,
                    "name": f"Home {i} — Away {i}",
                    "name_en": None,
                    "championship": "Test football",
                    "start_at": None,
                    "quotes": {
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                    },
                    "result": None,
                    "score": None,
                }
                for i in range(15)
            ],
        },
    }
    target = parse_target_drawing(
        payload, datetime.fromisoformat(ASOF.replace("Z", "+00:00"))
    )
    fingerprint = target_fingerprint(
        target.drawing_id, target.drawing_number, target.deadline, target.events
    )

    def write(name, doc, seal=None):
        if seal:
            doc.pop(seal, None)
            doc[seal] = canonical_hash(doc)
        data = json.dumps(doc, sort_keys=True).encode()
        (root / name).write_bytes(data)
        return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}

    final = {
        "schema_version": 1,
        "plan_id": "synthetic",
        "attempt_id": "synthetic",
        "drawing_id": target.drawing_id,
        "drawing_number": number,
        "deadline": target.deadline.isoformat(),
        "captured_at": ASOF,
        "target_fingerprint": fingerprint,
        "detail_payload_sha256": canonical_hash(payload),
        "probability_input_sha256": canonical_probability_input_sha256(
            tuple(e.bk_probabilities for e in target.events)
        ),
        "timing_override_sha256": None,
        "payload": payload,
    }
    final_ref = write("final.json", final, "snapshot_sha256")
    final_ref["artifact_type"] = "frozen_final_input"
    events, records = [], []
    for target_event in target.events:
        e, docs = base()
        i = target_event.event_order
        e.update(
            event_order=i,
            provider_fixture_id=f"target-{i}",
            target_event_id=str(target_event.event_id),
            home_team=target_event.home_team,
            away_team=target_event.away_team,
            sport="football",
        )
        available = i < covered
        if not available:
            e.update(
                provider_fixture_id=None,
                provider_home_team_id=None,
                provider_away_team_id=None,
                target_starts_at=None,
            )
        e["sources"] = {}
        for side in ("home", "away"):
            if available:
                ref = write(f"raw-{i}-{side}.json", docs[side])
                e["sources"][side] = {
                    **ref,
                    "status": "available",
                    "artifact_type": "raw_goal_team_results_response",
                }
            else:
                e["sources"][side] = {
                    "status": "unavailable",
                    "reason": "target_fixture_missing",
                }
        records.append(
            {
                "event_order": i,
                "target_event_id": target_event.event_id,
                "target_home_team": target_event.home_team,
                "target_away_team": target_event.away_team,
                "source_provider": "goal-api-v1",
                "status": "independent_candidate" if available else "not_found",
                "orientation": "same" if available else None,
                "source_event_id": e["provider_fixture_id"],
                "source_home_team_id": e["provider_home_team_id"],
                "source_away_team_id": e["provider_away_team_id"],
                "starts_at": e["target_starts_at"],
                "source_status": "scheduled" if available else None,
                "ledger_eligible": False,
            }
        )
        events.append(e)
    schedule = {
        "schema_version": 2,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "drawing_id": target.drawing_id,
        "drawing_number": number,
        "captured_at": ASOF,
        "ledger_mutated": False,
        "records": records,
    }
    schedule_ref = write("schedule.json", schedule, "report_sha256")
    manifest = {
        "schema_version": 1,
        "artifact_class": "SPORTS_HISTORY_RAW_CAPTURE_BACKFILL_MANIFEST",
        "snapshots": [
            {
                "drawing_id": target.drawing_id,
                "drawing_number": number,
                "drawing_fingerprint": fingerprint,
                "provider": "goal-api-v1",
                "requested_history_size": 10,
                "as_of": ASOF,
                "deadline": target.deadline.isoformat(),
                "target_detail": final_ref,
                "schedule_binding": schedule_ref,
                "events": events,
            }
        ],
    }
    write("manifest.json", manifest, "manifest_sha256")
    return root / "manifest.json", manifest, write


@pytest.mark.parametrize(
    "case",
    [
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
    ],
)
def test_declarative_cases(case, tmp_path):
    e, d = base()
    if case == 2:
        d["home"] = None
        r = run(e, d)
        assert r["counts"]["home"]["raw_payload_row_count"] is None
        assert r["source_status"] == "partial"
    elif case == 3:
        d["home"]["payload"]["data"] = []
        seal_raw(d["home"])
        assert run(e, d)["counts"]["home"]["raw_payload_row_count"] == 0
    elif case == 4:
        d["home"]["payload"]["data"].append({"matchStatus": "LIVE"})
        seal_raw(d["home"])
        r = run(e, d)
        assert r["counts"]["home"]["raw_payload_row_count"] == 6
        assert r["counts"]["home"]["eligible_prior_count"] == 5
    elif case == 5:
        d["home"]["fetched_at"] = ASOF
        assert run(e, d)["source_status"] == "complete"
    elif case in (6, 7, 8, 10, 11, 12, 13, 17, 18, 20, 22):
        if case == 6:
            d["home"]["fetched_at"] = "2020-01-31T12:00:00.000001Z"
        elif case == 7:
            with pytest.raises(ValueError, match="cutoff"):
                run(e, d, as_of=CUTOFF, final_captured_at=CUTOFF)
            return
        elif case == 8:
            d["home"]["payload"]["data"][0]["id"] = "target-0"
            seal_raw(d["home"])
        elif case == 10:
            with pytest.raises(ValueError, match="ASOF_AFTER_FINAL"):
                run(e, d, final_captured_at="2020-01-31T11:59:59Z")
            return
        elif case == 11:
            d["home"]["fetched_at"] = "2020-01-31T11:00:00"
        elif case == 12:
            d["home"]["endpoint"] = "/teams/wrong/results"
            seal_raw(d["home"])
        elif case == 13:
            d["home"]["payload"]["data"][0]["gender"] = "men"
            seal_raw(d["home"])
        elif case == 17:
            x = deepcopy(d["home"]["payload"]["data"][0])
            x.update(homeTeamId="H", awayTeamId="A")
            d["home"]["payload"]["data"][0] = x
            x = deepcopy(x)
            x["leagueYear"] = "2018-2019"
            d["away"]["payload"]["data"].append(x)
            seal_raw(d["home"])
            seal_raw(d["away"])
        elif case == 18:
            d["home"]["payload"]["data"].append(
                deepcopy(d["home"]["payload"]["data"][0])
            )
            seal_raw(d["home"])
        elif case == 20:
            x = deepcopy(d["home"]["payload"]["data"][0])
            x.update(homeTeamId="H", awayTeamId="A", homeTeamScore=9)
            d["away"]["payload"]["data"].append(x)
            seal_raw(d["away"])
        elif case == 22:
            d["home"]["payload"]["data"][0]["homeTeamScore"] = 9
        with pytest.raises(ValueError):
            run(e, d)
    elif case == 9:
        assert run(e, d, cutoff=None)["cutoff_verified"] is False
    elif case == 14:
        e["identity_scope"].pop("gender")
        r = run(e, d)
        assert r["identity"]["gender"] == "UNKNOWN"
        assert not r["strict_scoped_eligible"]
        assert r["counts"]["home"]["eligible_prior_count"] == 5
    elif case == 15:
        e["identity_scope"].pop("season")
        assert run(e, d)["identity"]["season"] == "UNKNOWN"
    elif case == 16:
        d["home"]["payload"]["data"][0]["leagueYear"] = "2018-2019"
        seal_raw(d["home"])
        assert run(e, d)["counts"]["home"]["cross_season_count"] == 1
    elif case == 19:
        x = deepcopy(d["home"]["payload"]["data"][0])
        x.update(awayTeamId="A")
        d["home"]["payload"]["data"][0] = x
        d["away"]["payload"]["data"].append(deepcopy(x))
        seal_raw(d["home"])
        seal_raw(d["away"])
        assert run(e, d)["duplicate_witness_count"] == 1
    elif case == 21:
        early = deepcopy(d)
        early["home"] = None
        run(e, d)
        assert run(e, early)["counts"]["home"]["raw_payload_row_count"] is None
    elif case == 23:
        first = run(e, d)
        d["home"]["fetched_at"] = "2020-01-31T10:00:00Z"
        second = run(e, d)
        assert first["feature_semantic_hash"] == second["feature_semantic_hash"]
        assert first["lineage_hash"] != second["lineage_hash"]
    elif case == 24:
        from toto_ai.sports_stats.v3_coverage_audit import VerifiedReader

        reader = VerifiedReader(tmp_path)
        with pytest.raises(ValueError):
            reader.read({"path": "../escape", "sha256": "0" * 64})
        with pytest.raises(ValueError):
            write_audit({}, output_root=tmp_path, output_dir=tmp_path.parent / "escape")
    elif case == 25:
        first = run(e, d)
        e.update(actual_outcome="X", target_score="99:0")
        assert run(e, d)["feature_semantic_hash"] == first["feature_semantic_hash"]
    elif case in (26, 27, 31):
        path, manifest, write = frozen_fixture(tmp_path / "input", covered=0)
        if case == 26:
            manifest["snapshots"][0]["deadline"] = "2020-02-01T16:31:00Z"
            write("manifest.json", manifest, "manifest_sha256")
        elif case == 31:
            manifest["snapshots"][0]["schedule_binding"]["sha256"] = "0" * 64
            write("manifest.json", manifest, "manifest_sha256")
        r = audit_manifest(
            input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
        )
        assert len(r["rows"]) == 15
        if case != 27:
            assert r["status"] == "INCOMPLETE"
            assert all(x["source_status"] == "SOURCE_REJECTED" for x in r["rows"])
            if case == 26:
                assert r["folds"][0]["reason"] == "final input deadline mismatch"
        if case == 27:
            assert r["status"] == "COMPLETE_WITH_GAPS"
            assert r["folds"][0]["source_missing_count"] == 15
            e.update(
                provider_fixture_id=None,
                provider_home_team_id=None,
                provider_away_team_id=None,
                target_starts_at=None,
            )
            r = run(e, {"home": None, "away": None})
            assert r["source_status"] == "missing"
            assert all(not b["both_core"] for b in r["thresholds"].values())
    elif case == 28:
        spec = json.loads((PLAN / "P1_FIXTURE_CASES.json").read_text())
        for b in spec["threshold_boundaries"]:
            assert b["passing_thresholds"] == [
                t for t in [1, 3, 5, 10] if b["eligible_prior_count"] >= t
            ]
        r = run(e, d)
        assert [
            r["thresholds"][str(t)]["full_current_features"] for t in [1, 3, 5, 10]
        ] == [True, False, False, False]
    elif case == 29:
        first = run(e, d)
        d["home"]["payload"]["data"].reverse()
        seal_raw(d["home"])
        assert run(e, d)["feature_semantic_hash"] == first["feature_semantic_hash"]
    elif case == 30:
        script = (
            "import sys; import toto_ai.sports_stats.v3_coverage_audit; "
            "assert not any(n.startswith(('sqlalchemy','toto_ai.db',"
            "'toto_ai.operations','toto_ai.cli')) for n in sys.modules)"
        )
        subprocess.run([sys.executable, "-B", "-c", script], check=True)
        assert not list(tmp_path.rglob("*.db"))
    elif case == 32:
        assert run(e, d)["congestion_scope"] == "OBSERVED_CAPTURE_ONLY"


def test_manifest_determinism_and_no_input_mutation(tmp_path):
    path, manifest, _ = frozen_fixture(tmp_path / "input")
    before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
    first = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )
    assert first["status"] == "COMPLETE_WITH_GAPS"
    assert first["folds"][0]["source_complete_count"] == 1
    assert (
        audit_manifest(
            input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
        )
        == first
    )
    assert before == {p.name: p.read_bytes() for p in path.parent.iterdir()}


def test_manifest_unicode_hash_matches_reviewed_backfill_contract():
    payload = {"team": "Женская команда"}
    expected = hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert canonical_hash(payload) == expected


def test_all_missing_preserves_source_status_without_chronology_permission(tmp_path):
    path, manifest, write = frozen_fixture(tmp_path / "input", covered=0)
    manifest["snapshots"][0]["as_of"] = "2020-01-31T12:00:01Z"
    write("manifest.json", manifest, "manifest_sha256")
    report = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )
    assert report["folds"][0]["source_missing_count"] == 15
    assert report["status"] == "INCOMPLETE"
    assert report["unexpected_rejections"] == 1
    assert report["unexpected_chronology_fold_count"] == 1
    assert report["folds"][0]["reason"] == "ASOF_AFTER_FINAL_INPUT"
    for row in report["rows"]:
        assert not row["feature_chronology_eligible"]
        assert row["chronology_reasons"] == ["ASOF_AFTER_FINAL_INPUT"]
        assert row["source_status"] == "missing"
        assert row["provenance_class"] == "CHRONOLOGY_INELIGIBLE"
        assert all(
            row["provenance"][key]["sha256"]
            for key in ("manifest", "final", "schedule")
        )
        assert row["source_references"]["home"]["fetched_at"] is None
        assert all(
            value is None
            for block in row["thresholds"].values()
            for value in block["features"].values()
        )


def test_duplicate_target_fixture_fails_without_dropping_rows(tmp_path):
    path, manifest, write = frozen_fixture(tmp_path / "input", covered=2)
    events = manifest["snapshots"][0]["events"]
    events[1]["provider_fixture_id"] = events[0]["provider_fixture_id"]
    write("manifest.json", manifest, "manifest_sha256")
    report = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )
    assert len(report["rows"]) == 15
    assert report["status"] == "INCOMPLETE"
    assert report["folds"][0]["reason"] == "duplicate provider target fixture"


def test_lazy_exports_preserve_public_identity():
    from toto_ai.package import PackageAudit
    from toto_ai.package.audit import PackageAudit as DirectAudit
    from toto_ai.sports_stats import CompletedFixture
    from toto_ai.sports_stats.domain import CompletedFixture as DirectFixture

    assert PackageAudit is DirectAudit
    assert CompletedFixture is DirectFixture


def test_declared_scope_and_cutoff_are_not_verified_evidence():
    e, d = base()
    e.update(
        cutoff_verified=True,
        verified_identity_scope=True,
        verified_evidence={"trusted": True},
    )
    for doc in d.values():
        for raw in doc["payload"]["data"]:
            for field in (
                "gender",
                "age_group",
                "squad_type",
                "leagueId",
                "leagueYear",
            ):
                raw.pop(field)
        seal_raw(doc)
    row = run(e, d)
    assert set(row["identity"].values()) == {"UNKNOWN"}
    assert row["declared_identity_scope"] == e["identity_scope"]
    assert not row["cutoff_verified"]
    assert not row["strict_scoped_eligible"]


def test_chronology_and_source_failures_count_independently_per_fold(tmp_path):
    root = tmp_path / "input"
    folds = []
    for folder, number in (("a", 4992), ("b", 4993)):
        _, manifest, _ = frozen_fixture(root / folder, number=number, covered=0)
        fold = manifest["snapshots"][0]
        for key in ("target_detail", "schedule_binding"):
            fold[key]["path"] = folder + "/" + fold[key]["path"]
        if number == 4992:
            fold["deadline"] = "2020-02-01T16:31:00Z"
        else:
            fold["as_of"] = "2020-01-31T12:00:01Z"
        folds.append(fold)
    manifest["snapshots"] = folds
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = canonical_hash(manifest)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest))
    report = audit_manifest(
        input_root=root, manifest_path=path, expected_drawings=(4992, 4993)
    )
    assert report["status"] == "INCOMPLETE"
    assert report["unexpected_rejections"] == 2
    assert report["unexpected_source_fold_count"] == 1
    assert report["unexpected_chronology_fold_count"] == 1
    assert len(report["rows"]) == 30
    assert report["folds"][1]["source_missing_count"] == 15


def test_rejected_sources_keep_only_verified_witness_fields(tmp_path):
    path, manifest, write = frozen_fixture(tmp_path / "input")
    # The frozen JSON writer sorts keys: away is read before damaged home.
    manifest["snapshots"][0]["events"][0]["sources"]["home"]["sha256"] = "0" * 64
    write("manifest.json", manifest, "manifest_sha256")
    row = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )["rows"][0]
    assert row["provenance"]["final"]["binding_verified"]
    assert row["provenance"]["schedule"]["binding_verified"]
    assert row["source_references"]["away"]["file_verified"]
    assert not row["source_references"]["away"]["envelope_verified"]
    assert row["source_references"]["away"]["fetched_at"] is None
    assert row["source_references"]["home"]["path"] is None


def bound_evidence_fixture(root):
    path, manifest, write = frozen_fixture(root)
    fold = manifest["snapshots"][0]
    event = fold["events"][0]
    for ref in event["sources"].values():
        doc = json.loads((root / ref["path"]).read_text())
        for raw in doc["payload"]["data"]:
            for field in (
                "gender",
                "age_group",
                "squad_type",
                "leagueId",
                "leagueYear",
            ):
                raw.pop(field)
        seal_raw(doc)
        ref.update(write(ref["path"], doc))
    write("manifest.json", manifest, "manifest_sha256")
    evidence = {
        "schema_version": 1,
        "artifact_class": "SPORTS_V3_BOUND_IDENTITY_CUTOFF_EVIDENCE",
        "provider": "goal-api-v1",
        "drawing_id": fold["drawing_id"],
        "drawing_number": fold["drawing_number"],
        "drawing_fingerprint": fold["drawing_fingerprint"],
        "event_order": 0,
        "target_event_id": event["target_event_id"],
        "provider_fixture_id": event["provider_fixture_id"],
        "provider_home_team_id": event["provider_home_team_id"],
        "provider_away_team_id": event["provider_away_team_id"],
        "target_starts_at": event["target_starts_at"],
        "orientation": "same",
        "plan_id": "synthetic",
        "manifest_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "final_input_file_sha256": fold["target_detail"]["sha256"],
        "source_file_sha256": {
            side: ref["sha256"] for side, ref in event["sources"].items()
        },
        "as_of": ASOF,
        "captured_at": ASOF,
        "cutoff": CUTOFF,
        "identity_scope": event["identity_scope"],
        "scope_applies_to": "TARGET_TEAMS_AND_HASH_BOUND_HISTORY",
    }
    reference = {
        **write("evidence.json", evidence),
        "artifact_type": "sports_v3_bound_identity_cutoff",
        "drawing_number": 4993,
        "event_order": 0,
    }
    return path, evidence, reference, write


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "unlisted",
        "team",
        "source",
        "final",
        "manifest",
        "scope_type",
        "captured",
        "plan",
    ],
)
def test_reviewed_typed_evidence_binding(tmp_path, damage):
    path, proof, reference, write = bound_evidence_fixture(tmp_path / "input")
    if damage == "team":
        proof["provider_home_team_id"] = "wrong"
    elif damage == "source":
        proof["source_file_sha256"]["home"] = "0" * 64
    elif damage == "final":
        proof["final_input_file_sha256"] = "0" * 64
    elif damage == "manifest":
        proof["manifest_file_sha256"] = "0" * 64
    elif damage == "scope_type":
        proof["identity_scope"]["gender"] = {"claim": "women"}
    elif damage == "captured":
        proof["captured_at"] = TARGET
    elif damage == "plan":
        proof["plan_id"] = "wrong"
    reference.update(write("evidence.json", proof))
    report = audit_manifest(
        input_root=path.parent,
        manifest_path=path,
        expected_drawings=(4993,),
        reviewed_evidence_references=() if damage == "unlisted" else (reference,),
    )
    row = report["rows"][0]
    if damage is None:
        assert report["status"] == "COMPLETE_WITH_GAPS"
        assert row["strict_scoped_eligible"]
        assert row["cutoff_verified"]
        assert set(row["identity"].values()) == {"VERIFIED"}
        assert row["identity_evidence"]["sha256"] == reference["sha256"]
    elif damage == "unlisted":
        assert not row["strict_scoped_eligible"]
        assert "evidence.json" not in report["input_hashes"]
    else:
        assert report["status"] == "INCOMPLETE"
        assert not row["strict_scoped_eligible"]


def test_row_provenance_available_missing_and_rejected(tmp_path):
    path, manifest, write = frozen_fixture(tmp_path / "input")
    report = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )
    available, missing = report["rows"][:2]
    source = available["source_references"]["home"]
    assert source["path"] == "raw-0-home.json"
    assert source["file_verified"] and source["envelope_verified"]
    assert source["provider"] == "goal-api-v1"
    assert source["endpoint"] == "/teams/H/results"
    assert source["fetched_at"] == "2020-01-31T11:00:00Z"
    assert source["request_fingerprint"]
    assert missing["provenance_class"] == "SOURCE_UNAVAILABLE"
    manifest["snapshots"][0]["schedule_binding"]["sha256"] = "0" * 64
    write("manifest.json", manifest, "manifest_sha256")
    rejected = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )["rows"][0]
    assert set(rejected) == set(available)
    assert rejected["provenance"]["manifest"]["file_verified"]
    assert rejected["provenance"]["final"]["binding_verified"]
    assert rejected["provenance"]["schedule"] is None
    assert rejected["source_references"]["home"]["path"] is None
    assert rejected["target_kickoff"] is None
    assert rejected["provenance_class"] == "SOURCE_REJECTED"
    assert rejected["lineage_hash"]


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 5, 9, 10])
def test_real_feature_threshold_boundaries(count):
    e, docs = base()
    for side, doc in docs.items():
        template = deepcopy(doc["payload"]["data"][0])
        doc["payload"]["data"] = [
            dict(template, id=f"{side}-{i}") for i in range(count)
        ]
        seal_raw(doc)
    row = run(e, docs)
    for threshold in (1, 3, 5, 10):
        block = row["thresholds"][str(threshold)]
        assert block["both_core"] is (count >= threshold)
        assert (block["features"]["home_rolling_ppg"] is not None) is (
            count >= threshold
        )


def test_all_eighteen_lazy_exports_and_dir():
    from importlib import import_module

    import toto_ai.package as package
    import toto_ai.sports_stats as sports

    assert len(package.__all__) + len(sports.__all__) == 18
    for module in (package, sports):
        assert set(module.__all__) <= set(dir(module))
        for name, defining_module in module._EXPORTS.items():
            direct = import_module(f"{module.__name__}.{defining_module}")
            assert getattr(module, name) is getattr(direct, name)


def test_cold_dir_and_all_exports_do_not_connect_to_services():
    script = """
import importlib, sys
def deny(event, args):
    if event in ('socket.connect', 'sqlite3.connect'):
        raise AssertionError(event)
sys.addaudithook(deny)
import toto_ai.package as package
import toto_ai.sports_stats as sports
before = set(sys.modules)
for module in (package, sports):
    assert set(module.__all__) <= set(dir(module))
assert set(sys.modules) == before
for module in (package, sports):
    for name, defining in module._EXPORTS.items():
        direct = importlib.import_module(module.__name__ + '.' + defining)
        assert getattr(module, name) is getattr(direct, name)
"""
    subprocess.run([sys.executable, "-B", "-c", script], check=True, timeout=10)


@pytest.mark.parametrize("late_artifact", ["final", "schedule"])
def test_late_bound_capture_is_chronology_in_fold_and_rejected_rows(
    tmp_path, late_artifact
):
    path, manifest, write = frozen_fixture(tmp_path / "input", covered=0)
    key = "target_detail" if late_artifact == "final" else "schedule_binding"
    seal = "snapshot_sha256" if late_artifact == "final" else "report_sha256"
    filename = late_artifact + ".json"
    artifact = json.loads((path.parent / filename).read_text())
    artifact["captured_at"] = "2020-01-31T12:00:01Z"
    manifest["snapshots"][0][key].update(write(filename, artifact, seal))
    write("manifest.json", manifest, "manifest_sha256")
    report = audit_manifest(
        input_root=path.parent, manifest_path=path, expected_drawings=(4993,)
    )
    reason = (
        "final input captured after as_of"
        if late_artifact == "final"
        else "schedule after as_of"
    )
    assert report["status"] == "INCOMPLETE"
    assert not report["activation_allowed"]
    assert report["unexpected_rejections"] == 1
    assert report["unexpected_chronology_fold_count"] == 1
    assert report["unexpected_source_fold_count"] == 0
    assert report["folds"][0]["chronology_reasons"] == [reason]
    assert len(report["rows"]) == 15
    for row in report["rows"]:
        assert row["chronology_reasons"] == [reason]
        assert not row["feature_chronology_eligible"]
        assert not row["strict_scoped_eligible"]
        assert all(
            value is None
            for block in row["thresholds"].values()
            for value in block["features"].values()
        )


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("ASOF_AFTER_FINAL_INPUT", True),
        ("capture/as_of chronology", True),
        ("history chronology", True),
        ("deadline chronology", True),
        ("cutoff chronology", True),
        ("target kickoff chronology", True),
        ("evidence cutoff/capture chronology", True),
        ("final input captured after as_of", True),
        ("schedule after as_of", True),
        ("final input deadline mismatch", False),
        ("timezone required", False),
    ],
)
def test_explicit_time_order_classifier_does_not_relabel_integrity(reason, expected):
    from toto_ai.sports_stats.v3_coverage_audit import _is_chronology_rejection

    assert _is_chronology_rejection(reason) is expected
