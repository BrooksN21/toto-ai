import hashlib
import json

import pytest

from toto_ai.research.sports_history_reconstruction import reconstruct, run_manifest


def fixture():
    target = dict(
        fixture_id="target",
        home_team_id="H",
        away_team_id="A",
        kickoff="2026-09-12T14:15:00Z",
        drawing=5004,
        event_order=8,
        close_moscow_wall="2026-09-12T16:00:00.000000Z",
    )
    rows = [
        dict(
            id="target",
            homeTeamId="H",
            awayTeamId="A",
            kickoffUtc=target["kickoff"],
            matchStatus="FINISHED",
            homeTeamScore="DO_NOT_READ",
            awayTeamScore="DO_NOT_READ",
        ),
        dict(
            id="old",
            homeTeamId="H",
            awayTeamId="A",
            kickoffUtc="2026-09-01T10:00:00Z",
            finishedAt="2026-09-01T12:00:00Z",
            matchStatus="FINISHED",
            homeTeamScore="1",
            awayTeamScore="0",
            updatedAt="2026-09-15T12:00:00Z",
        ),
        dict(
            id="future",
            homeTeamId="H",
            awayTeamId="B",
            kickoffUtc="2026-09-12T13:00:00Z",
            matchStatus="FINISHED",
            homeTeamScore="DO_NOT_READ",
            awayTeamScore="DO_NOT_READ",
        ),
    ]
    return target, rows


def bound(rows, team="H"):
    raw = json.dumps(
        dict(
            provider="goal-api-v1",
            endpoint=f"/teams/{team}/results",
            fetched_at="2026-09-15T17:11:13Z",
            payload=dict(teamId=team, data=rows),
        )
    ).encode()
    return dict(content=raw, sha256=hashlib.sha256(raw).hexdigest(), path=team)


def run(target, rows):
    return reconstruct(
        target=target, sources=[bound(rows)], derived_at="2026-09-15T17:20:00Z"
    )


def test_exclusion_before_scores_and_no_false_fit():
    target, rows = fixture()
    result = run(target, rows)
    assert result["decision_cutoff"] == "2026-09-12T12:50:00+00:00"
    assert result["counts"]["retained_unique"] == 1
    assert {x["reason"] for x in result["exclusions"]} == {
        "TARGET",
        "AT_OR_AFTER_DECISION_CUTOFF",
    }
    assert result["features"]["home_prior_match_count"] == 1
    assert not result["fit_eligible"]
    assert result["history"][0]["information_available_at"] is None
    assert result["history"][0]["scope"]["gender"] is None


def test_target_result_mutation_cannot_change_features():
    target, rows = fixture()
    before = run(target, rows)
    rows[0]["homeTeamScore"] = "9999"
    after = run(target, rows)
    assert before["features"] == after["features"]
    assert before["input_sha256"] != after["input_sha256"]


@pytest.mark.parametrize(
    "field,value", [("homeTeamId", "OTHER"), ("kickoffUtc", "2026-09-13T14:15:00Z")]
)
def test_exact_target_identity(field, value):
    target, rows = fixture()
    rows[0][field] = value
    with pytest.raises(ValueError, match="target identity"):
        run(target, rows)


def test_source_hash_tamper():
    target, rows = fixture()
    source = bound(rows)
    source["content"] += b" "
    with pytest.raises(ValueError, match="hash"):
        reconstruct(target=target, sources=[source], derived_at="2026-09-15T17:20Z")


def test_target_must_exist_in_bound_history():
    target, rows = fixture()
    with pytest.raises(ValueError, match="target absent"):
        run(target, rows[1:])


def test_foreign_team_history_is_rejected():
    target, rows = fixture()
    with pytest.raises(ValueError, match="team binding"):
        reconstruct(
            target=target,
            sources=[bound(rows, "WRONG")],
            derived_at="2026-09-15T17:20Z",
        )


def test_unknown_status_excluded_before_score():
    target, rows = fixture()
    rows[1]["matchStatus"] = "POSTPONED"
    rows[1]["homeTeamScore"] = "INVALID"
    assert run(target, rows)["counts"]["retained_unique"] == 0


def test_conflicting_duplicate_rejected():
    target, rows = fixture()
    rows.append({**rows[1], "homeTeamScore": "5"})
    with pytest.raises(ValueError, match="conflicting"):
        run(target, rows)


def test_received_time_cannot_be_backdated():
    target, rows = fixture()
    with pytest.raises(ValueError, match="derived before source"):
        reconstruct(
            target=target, sources=[bound(rows)], derived_at="2026-09-01T17:20Z"
        )


def test_actual_observation_and_revision_dates_preserved():
    target, rows = fixture()
    result = run(target, rows)
    evidence = result["history"][0]["evidence"][0]
    assert evidence["observed_at"] == "2026-09-15T17:11:13Z"
    assert evidence["updated_at"] == "2026-09-15T12:00:00Z"
    assert evidence["version_after_cutoff"] is True
    assert result["history"][0]["causal_fit_eligible"] is False


def test_target_alias_is_not_retained_as_history():
    target, rows = fixture()
    rows.append({**rows[0], "id": "different-id"})
    with pytest.raises(ValueError, match="alias collision"):
        run(target, rows)


def test_post_extra_time_uses_regulation_score_only():
    target, rows = fixture()
    rows[1].update(
        matchStatus="AFTER_ET",
        homeTeamFtScore="2",
        awayTeamFtScore="2",
        homeTeamScore="3",
        awayTeamScore="2",
    )
    result = run(target, rows)
    assert result["history"][0]["normalized"]["home_goals"] == 2
    del rows[1]["homeTeamFtScore"]
    result = run(target, rows)
    assert result["counts"]["retained_unique"] == 0
    assert "REGULATION_SCORE_MISSING" in {r["reason"] for r in result["exclusions"]}


def manifest_fixture(tmp_path):
    target, rows = fixture()
    source = bound(rows)
    raw_path = tmp_path / "history.json"
    raw_path.write_bytes(source["content"])
    manifest = dict(
        target=target, sources=[dict(path="history.json", sha256=source["sha256"])]
    )
    metadata = [
        dict(
            target_event_id=123,
            drawing_number=5004,
            event_order=8,
            ended_at=target["close_moscow_wall"],
            name="Home — Away",
        )
    ]
    m = tmp_path / "targets.json"
    m.write_text(json.dumps(metadata))
    manifest["target_metadata_source"] = dict(
        path="targets.json",
        sha256=hashlib.sha256(m.read_bytes()).hexdigest(),
        local_event_id=123,
    )
    mapping = dict(
        target=target,
        local_event_id=123,
        target_metadata_sha256=manifest["target_metadata_source"]["sha256"],
        evidence_grade="TEST_ONLY_NOT_REVIEW_AUTHORITY",
    )
    mp = tmp_path / "mapping.json"
    mp.write_text(json.dumps(mapping))
    manifest["fixture_mapping_source"] = dict(
        path="mapping.json", sha256=hashlib.sha256(mp.read_bytes()).hexdigest()
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def test_manifest_native_end_to_end_and_stable_semantics(tmp_path):
    manifest = manifest_fixture(tmp_path)
    first = run_manifest(manifest, root=tmp_path)
    second = run_manifest(manifest, root=tmp_path)
    assert first["input_sha256"] == second["input_sha256"]
    assert first["features"] == second["features"]
    assert first["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert first["counts"]["retained_unique"] == 1
    assert first["operator_compatible"] is False


def test_manifest_disk_tampering_rejected(tmp_path):
    manifest = manifest_fixture(tmp_path)
    (tmp_path / "history.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        run_manifest(manifest, root=tmp_path)


@pytest.mark.parametrize("path", ["../escape.json", "/outside/history.json"])
def test_manifest_path_escape_rejected(tmp_path, path):
    manifest = manifest_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["sources"][0]["path"] = path
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="outside root"):
        run_manifest(manifest, root=tmp_path)


def test_manifest_source_code_hash_mismatch_rejected(tmp_path):
    manifest = manifest_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    data["code_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="code hash"):
        run_manifest(manifest, root=tmp_path)


def test_manifest_symlink_escape_rejected(tmp_path):
    root = tmp_path / "scoped"
    root.mkdir()
    manifest = manifest_fixture(root)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (root / "history.json").unlink()
    (root / "history.json").symlink_to(outside)
    with pytest.raises(ValueError, match="outside root"):
        run_manifest(manifest, root=root)


def test_generic_utc_offset_not_accepted_as_moscow_wall():
    target, rows = fixture()
    target["close_moscow_wall"] = "2026-09-12T16:00:00+00:00"
    with pytest.raises(ValueError, match="Moscow-wall"):
        run(target, rows)


def test_started_before_but_finished_after_cutoff_excluded_before_scores():
    target, rows = fixture()
    rows[1].update(
        kickoffUtc="2026-09-12T12:49:00Z",
        finishedAt="2026-09-12T14:40:00Z",
        homeTeamScore="INVALID",
    )
    result = run(target, rows)
    assert result["counts"]["retained_unique"] == 0
    assert "COMPLETED_AT_OR_AFTER_CUTOFF" in {r["reason"] for r in result["exclusions"]}


@pytest.mark.parametrize("kickoff", ["2026-09-12T12:49:00Z", "2026-09-01T10:00:00Z"])
def test_late_terminal_capture_with_unknown_completion_not_used(kickoff):
    target, rows = fixture()
    rows[1]["kickoffUtc"] = kickoff
    del rows[1]["finishedAt"]
    rows[1]["homeTeamScore"] = "INVALID"
    result = run(target, rows)
    assert result["counts"]["retained_unique"] == 0
    assert "COMPLETION_BEFORE_CUTOFF_UNPROVEN" in {
        r["reason"] for r in result["exclusions"]
    }


def test_real_terminal_observation_is_completion_upper_bound_not_invented_finish():
    target, rows = fixture()
    del rows[1]["finishedAt"]
    rows[1]["updatedAt"] = "2026-09-01T12:00:00Z"
    source = bound(rows)
    doc = json.loads(source["content"])
    doc["fetched_at"] = "2026-09-11T12:00:00Z"
    source["content"] = json.dumps(doc).encode()
    source["sha256"] = hashlib.sha256(source["content"]).hexdigest()
    result = reconstruct(
        target=target, sources=[source], derived_at="2026-09-15T17:20Z"
    )
    assert result["counts"]["retained_unique"] == 1
    assert result["history"][0]["finished_at"] is None
    assert (
        result["history"][0]["evidence"][0]["completion"]["completed_by"]
        == "2026-09-11T12:00:00Z"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("drawing", 5999),
        ("event_order", 14),
        ("close_moscow_wall", "2026-09-12T15:00:00.000000Z"),
    ],
)
def test_metadata_binding_rejects_target_tamper(tmp_path, field, value):
    p = manifest_fixture(tmp_path)
    m = json.loads(p.read_text())
    m["target"][field] = value
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="target metadata binding"):
        run_manifest(p, root=tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [("sha256", "0" * 64), ("local_event_id", 999), ("path", "../outside.json")],
)
def test_metadata_reference_tampering_rejected(tmp_path, field, value):
    p = manifest_fixture(tmp_path)
    m = json.loads(p.read_text())
    m["target_metadata_source"][field] = value
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        run_manifest(p, root=tmp_path)


def test_fixture_mapping_cannot_be_omitted(tmp_path):
    p = manifest_fixture(tmp_path)
    m = json.loads(p.read_text())
    del m["fixture_mapping_source"]
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="fixture mapping"):
        run_manifest(p, root=tmp_path)


@pytest.mark.parametrize(
    "finish,reason",
    [
        ("2026-09-12T12:50:00Z", "COMPLETED_AT_OR_AFTER_CUTOFF"),
        ("2026-08-31T10:00:00Z", "CONTRADICTORY_COMPLETION_TIMESTAMP"),
        ("not-a-time", "INVALID_COMPLETION_TIMESTAMP"),
    ],
)
def test_completion_boundary_and_invalid_times(finish, reason):
    target, rows = fixture()
    rows[1]["finishedAt"] = finish
    result = run(target, rows)
    assert result["counts"]["retained_unique"] == 0
    assert reason in {r["reason"] for r in result["exclusions"]}


def test_late_capture_with_actual_prior_finish_remains_reconstructible():
    target, rows = fixture()
    result = run(target, rows)
    assert result["counts"]["retained_unique"] == 1
    assert result["history"][0]["finished_at"] == rows[1]["finishedAt"]
    assert result["history"][0]["evidence"][0]["completion"]["completion_before_cutoff"]
    assert not result["fit_eligible"]


def test_missing_target_metadata_rejected(tmp_path):
    p = manifest_fixture(tmp_path)
    manifest = json.loads(p.read_text())
    del manifest["target_metadata_source"]
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="target metadata"):
        run_manifest(p, root=tmp_path)


def test_mapping_content_conflict_even_with_matching_file_hash(tmp_path):
    p = manifest_fixture(tmp_path)
    manifest = json.loads(p.read_text())
    mapping_path = tmp_path / "mapping.json"
    mapping = json.loads(mapping_path.read_text())
    mapping["target"]["home_team_id"] = "OTHER"
    mapping_path.write_text(json.dumps(mapping))
    manifest["fixture_mapping_source"]["sha256"] = hashlib.sha256(
        mapping_path.read_bytes()
    ).hexdigest()
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="fixture mapping binding"):
        run_manifest(p, root=tmp_path)
