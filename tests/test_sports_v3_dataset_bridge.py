"""Synthetic bridge contracts only; no training, network or operator actions."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from toto_ai.research.sports_v3_dataset_bridge import (
    bind_projection,
    history_readiness,
    link_schedule_evidence,
)
from toto_ai.sports_stats.v3_family_evidence import EvidenceBytes


def blob(path, value):
    return EvidenceBytes(path, json.dumps(value, sort_keys=True).encode())


def target():
    return dict(
        drawing_id=1,
        event_order=0,
        target_event_id="7",
        provider_fixture_id="fixture",
        home_team_id="home",
        away_team_id="away",
        as_of="2020-02-19T12:00:00+00:00",
        final_captured_at="2020-02-19T12:00:00+00:00",
        kickoff="2020-02-20T12:00:00+00:00",
        scope={"home": {}, "away": {}},
    )


def test_projection_adds_actual_hash_without_mutation():
    old = target()
    snap = SimpleNamespace(
        drawing_id=1, snapshot_sha256="a" * 64, captured_at="2020-02-19T12:00:00+00:00"
    )
    new = bind_projection(old, snapshot=snap, event_id=7, plan_sha256="b" * 64)
    assert new["final_input_sha256"] == "a" * 64
    assert "final_input_sha256" not in old


@pytest.mark.parametrize(
    "patch",
    [
        {"drawing_id": 2},
        {"target_event_id": "8"},
        {"as_of": "2020-02-19T13:00:00+00:00"},
        {"final_input_sha256": "c" * 64},
    ],
)
def test_invalid_input_binding_rejected(patch):
    snap = SimpleNamespace(
        drawing_id=1, snapshot_sha256="a" * 64, captured_at="2020-02-19T12:00:00+00:00"
    )
    with pytest.raises(ValueError):
        bind_projection(
            {**target(), **patch}, snapshot=snap, event_id=7, plan_sha256="b" * 64
        )


def history(**patch):
    row = dict(
        id="prior",
        matchStatus="FINISHED",
        kickoffUtc="2020-02-01T12:00:00Z",
        homeTeamId="home",
        awayTeamId="other",
        homeTeamScore="1",
        awayTeamScore="0",
    )
    return {
        **dict(
            schema_version=1,
            provider="goal-api-v1",
            endpoint="/teams/home/results",
            http_status=200,
            params={"limit": 10},
            fetched_at="2020-02-18T12:00:00Z",
            payload={"success": True, "teamId": "home", "data": [row]},
        ),
        **patch,
    }


def test_current_team_class_never_fills_history():
    t = target()
    t["scope"]["home"] = {"gender": "male", "age_group": "adult", "squad_type": "first"}
    result = history_readiness(blob("history", history()), target=t, side="home")
    assert result["native_history_status"] == "PASS"
    assert result["scope_complete_rows"] == 0
    assert result["missing_scope_fields"] == {
        "gender": 1,
        "age_group": 1,
        "squad_type": 1,
    }
    assert result["scope_authorized"] is False


def test_future_history_capture_rejected():
    with pytest.raises(ValueError, match="post-as_of"):
        history_readiness(
            blob("history", history(fetched_at="2020-02-19T13:00:00Z")),
            target=target(),
            side="home",
        )


def evidence(provider="sofascore-v1", **patch):
    return dict(
        source_provider=provider,
        drawing_id=1,
        event_order=0,
        target_event_id=7,
        orientation="same",
        source_status="scheduled",
        status_eligible=True,
        captured_at="2020-02-18T12:00:00Z",
        starts_at="2020-02-20T12:00:00Z",
        source_event_id="fixture",
        source_home_team_id="home",
        source_away_team_id="away",
        **patch,
    )


def review(sources):
    text = "\n".join(
        f"evidence: `{b.path}` — SHA-256 `{hashlib.sha256(b.content).hexdigest()}`"
        for b in sources
    )
    return EvidenceBytes("review.md", text.encode())


def test_link_does_not_grant_independent_authority():
    sources = [blob("goal", evidence("goal-api-v1")), blob("sofa", evidence())]
    r = review(sources)
    result = link_schedule_evidence(
        target(),
        review=r,
        expected_review_sha256=hashlib.sha256(r.content).hexdigest(),
        sources=sources,
    )
    assert result["status"] == "HASH_LINKED_SUPPORTING_EVIDENCE"
    assert result["reviewed_references"] == []
    assert result["training_authorized"] is False


def test_goal_is_not_its_own_independent_confirmation():
    sources = [blob("goal", evidence("goal-api-v1"))]
    r = review(sources)
    with pytest.raises(ValueError, match="independent provider"):
        link_schedule_evidence(
            target(),
            review=r,
            expected_review_sha256=hashlib.sha256(r.content).hexdigest(),
            sources=sources,
        )


def test_changed_evidence_rejected():
    original = blob("goal", evidence("goal-api-v1"))
    r = review([original])
    with pytest.raises(ValueError, match="source hash"):
        link_schedule_evidence(
            target(),
            review=r,
            expected_review_sha256=hashlib.sha256(r.content).hexdigest(),
            sources=[EvidenceBytes(original.path, original.content + b" ")],
        )


def test_archived_sofascore_not_started_is_pregame():
    sofa = evidence()
    sofa["source_status"] = "not_started"
    sources = [blob("goal", evidence("goal-api-v1")), blob("sofa", sofa)]
    r = review(sources)
    result = link_schedule_evidence(
        target(),
        review=r,
        expected_review_sha256=hashlib.sha256(r.content).hexdigest(),
        sources=sources,
    )
    assert result["status"] == "HASH_LINKED_SUPPORTING_EVIDENCE"


@pytest.mark.parametrize(
    "patch",
    [
        {"source_status": "in_progress"},
        {"orientation": "reversed"},
        {"target_event_id": 9},
        {"captured_at": "2020-02-20T12:00:00Z"},
        {"starts_at": "2020-02-21T12:00:00Z"},
        {"source_provider": "unreviewed-provider"},
    ],
)
def test_bad_independent_source_rejected(patch):
    changed = {**evidence(), **patch}
    sources = [blob("goal", evidence("goal-api-v1")), blob("sofa", changed)]
    r = review(sources)
    with pytest.raises(ValueError):
        link_schedule_evidence(
            target(),
            review=r,
            expected_review_sha256=hashlib.sha256(r.content).hexdigest(),
            sources=sources,
        )


def test_wrong_history_team_rejected():
    with pytest.raises(ValueError, match="history team orientation"):
        history_readiness(
            blob("history", history(endpoint="/teams/wrong/results")),
            target=target(),
            side="home",
        )


def test_future_source_update_is_not_hidden_by_old_capture():
    raw = history()
    raw["payload"]["data"][0]["updatedAt"] = "2020-02-20T13:00:00Z"
    with pytest.raises(ValueError, match="post-asof history source version"):
        history_readiness(blob("history", raw), target=target(), side="home")


def test_archived_prepare_to_native_o1_paths(tmp_path):
    """Real archived research chain, not a synthetic fit or operator action."""
    from dataclasses import asdict
    from pathlib import Path

    from toto_ai.research import sports_v3_dataset_bridge as bridge
    from toto_ai.sports_stats.v3_family_evidence import (
        ReviewedReference,
        assess_family_evidence,
    )

    root = Path(__file__).resolve().parents[1]
    receipt = root / "plans/TOTOAI-RESUME-20260915/C-bridge-reviewed-references.json"
    if not receipt.exists():
        pytest.skip("explicit archived C review fixture not present")
    reviewed = json.loads(receipt.read_text())["events"][0]
    refs = [ReviewedReference(**r) for r in reviewed["references"]]
    blobs = [EvidenceBytes(r.path, Path(r.path).read_bytes()) for r in refs]
    target_doc = json.loads(blobs[0].content)
    inp = (
        root
        / "reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly"
        / "input-validation.json"
    )
    paths = json.loads(inp.read_text())["4999"]
    plan = json.loads(Path(paths["plan_path"]).read_text())
    ledger = json.loads(Path(plan["paths"]["schedule_evidence_ledger"]).read_text())
    observation = next(
        o
        for o in ledger["observations"]
        if target_doc["provider_fixture_id"]
        in (
            Path(plan["paths"]["schedule_evidence_ledger"]).parent
            / o["review_document"]
        ).read_text()
    )
    review_doc = (
        Path(plan["paths"]["schedule_evidence_ledger"]).parent
        / observation["review_document"]
    ).read_text()
    import re

    sources = [
        EvidenceBytes(p, (root / "data/schedule-evidence" / p).read_bytes())
        for p in re.findall(r"evidence: `([^`]+)`", review_doc)
    ]
    kwargs = dict(
        plan_path=paths["plan_path"],
        final_input_path=paths["native_input_path"],
        expected_final_input_sha256=json.loads(receipt.read_text())[
            "native_final_input_identity_sha256"
        ],
        projection=target_doc,
        projection_path=refs[0].path,
        histories={
            s: [b for r, b in zip(refs, blobs, strict=True) if r.side == s]
            for s in ("home", "away")
        },
        schedule_sources=sources,
        derived_at="2026-09-15T15:19:00+00:00",
        reviewed_refs=refs,
    )
    # Set explicitly when the serialization API exists; before the fix native
    # prepare returns absolute paths and the following O1 call is RED.
    if hasattr(bridge, "relative_evidence_bundle"):
        kwargs["review_root"] = root
    event, manifest, native = bridge.prepare_bridge(**kwargs)
    histories = kwargs["histories"]
    native_refs = refs
    if hasattr(bridge, "relative_evidence_bundle"):
        _, histories, native_refs = bridge.relative_evidence_bundle(
            EvidenceBytes(refs[0].path, event.content),
            histories,
            refs,
            review_root=root,
        )
    o1 = assess_family_evidence(
        event=event, verified_event_local_histories=histories, reviewed_refs=native_refs
    )
    assert o1["lineage_hash"]
    # Path compatibility is fixed, not raw-envelope/scope readiness.
    assert o1["status"] == "INCOMPLETE"
    assert all(
        "RAW_ENVELOPE_FIELDS" in state["missing_reasons"]
        for state in o1["sides"].values()
    )
    assert native is not None
    assert native["scope_verified"] is False
    assert all(
        not r["path"].startswith("/")
        for r in manifest["pending_reference_bindings_NOT_REVIEW_AUTHORITY"]
    )
    assert all(
        asdict(r)["sha256"] == old.sha256
        for r, old in zip(native_refs, refs, strict=True)
    )


@pytest.mark.parametrize(
    "unsafe",
    ["../escape", "sub/../escape", "a//b", "a/./b", "\\escape", "/outside-review-root"],
)
def test_relative_path_escape_rejected(tmp_path, unsafe):
    from toto_ai.research.sports_v3_dataset_bridge import _relative_path

    with pytest.raises(ValueError):
        _relative_path(unsafe, tmp_path)


def test_relative_path_symlink_and_ambiguous_root_rejected(tmp_path):
    from toto_ai.research.sports_v3_dataset_bridge import _relative_path

    (tmp_path / "real").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
    for path, root in [
        ("alias/file", tmp_path),
        ("file", tmp_path / "alias"),
        ("file", [tmp_path]),
        ("file", "relative-root"),
    ]:
        with pytest.raises(ValueError):
            _relative_path(path, root)


def test_physical_tampering_rejected(tmp_path):
    from toto_ai.research.sports_v3_dataset_bridge import relative_evidence_bundle

    p = tmp_path / "projection.json"
    p.write_bytes(b"changed")
    with pytest.raises(ValueError, match="physical evidence bytes mismatch"):
        relative_evidence_bundle(
            EvidenceBytes(str(p), b"original"),
            {"home": [], "away": []},
            [],
            review_root=tmp_path,
        )


def test_review_hash_tampering_rejected(tmp_path):
    from toto_ai.research.sports_v3_dataset_bridge import relative_evidence_bundle
    from toto_ai.sports_stats.v3_family_evidence import ReviewedReference

    p = tmp_path / "projection.json"
    p.write_bytes(b"original")
    ref = ReviewedReference(
        str(p), "a" * 64, "target_projection", "goal-api-v1", 1, 0, "7"
    )
    with pytest.raises(ValueError, match="reviewed bytes hash mismatch"):
        relative_evidence_bundle(
            EvidenceBytes(str(p), b"original"),
            {"home": [], "away": []},
            [ref],
            review_root=tmp_path,
        )


def test_derived_envelope_preserves_payload_times_and_source_chain(tmp_path):
    from toto_ai.research.sports_v3_dataset_bridge import derive_native_history_envelope
    from toto_ai.sports_stats.v3_family_evidence import ReviewedReference, _source

    p = tmp_path / "raw.json"
    raw = history()
    b = blob(str(p), raw)
    p.write_bytes(b.content)
    t = {**target(), "provider": "goal-api-v1"}
    ref = ReviewedReference(
        str(p),
        hashlib.sha256(b.content).hexdigest(),
        "raw_goal_team_results_response",
        "goal-api-v1",
        1,
        0,
        "7",
        "home",
    )
    derived, chain = derive_native_history_envelope(
        b,
        source_reference=ref,
        target=t,
        side="home",
        review_root=tmp_path,
        derived_path=tmp_path / "derived.json",
        derived_at="2020-02-21T12:00:00+00:00",
    )
    d = json.loads(derived.content)
    assert d["payload"] == raw["payload"]
    assert d["fetched_at"] == raw["fetched_at"]
    assert chain["source_http_status"] == 200
    assert chain["original_http_body_sha256"] is None
    assert chain["original_file_sha256"] == ref.sha256
    assert chain["artifact_class"] == "DERIVED_ENVELOPE_NOT_ORIGINAL_CAPTURE"
    assert chain["review_authority_issued"] is False
    assert chain["derived_file_sha256"] == hashlib.sha256(derived.content).hexdigest()
    assert _source(d, t, "home", {})[1] == 1
    assert p.read_bytes() == b.content


@pytest.mark.parametrize(
    "mutation",
    [
        {"http_status": 500},
        {"params": {"limit": 20}},
        {"fetched_at": "2020-02-20T12:00:00Z"},
        {"unexpected": True},
    ],
)
def test_derived_envelope_rejects_unrepresentable_capture(tmp_path, mutation):
    from toto_ai.research.sports_v3_dataset_bridge import derive_native_history_envelope
    from toto_ai.sports_stats.v3_family_evidence import ReviewedReference

    p = tmp_path / "raw.json"
    b = blob(str(p), {**history(), **mutation})
    p.write_bytes(b.content)
    ref = ReviewedReference(
        str(p),
        hashlib.sha256(b.content).hexdigest(),
        "raw_goal_team_results_response",
        "goal-api-v1",
        1,
        0,
        "7",
        "home",
    )
    with pytest.raises(ValueError):
        derive_native_history_envelope(
            b,
            source_reference=ref,
            target={**target(), "provider": "goal-api-v1"},
            side="home",
            review_root=tmp_path,
            derived_path=tmp_path / "derived.json",
            derived_at="2020-02-21T12:00:00+00:00",
        )


def test_all_archived_derived_envelopes_native_o1_to_features():
    """Full real contract probe; temporary refs are NOT an approval receipt."""
    from dataclasses import replace
    from pathlib import Path

    from toto_ai.research.sports_v3_dataset_bridge import (
        derive_native_history_envelope,
        relative_evidence_bundle,
    )
    from toto_ai.sports_stats.v3_family_evidence import (
        ReviewedReference,
        assess_family_evidence,
    )
    from toto_ai.sports_stats.v3_probability import (
        FEATURE_NAMES,
        reliability,
        validate_feature_row,
    )
    from toto_ai.sports_stats.v3_probability_features import build_v3_predictors

    root = Path(__file__).resolve().parents[1]
    receipt = root / "plans/TOTOAI-RESUME-20260915/C-bridge-reviewed-references.json"
    if not receipt.exists():
        pytest.skip("real C reviewed archive fixture unavailable")
    out = root / "reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly"
    cached = json.loads((out / "features-no-labels.json").read_text())["rows"]
    events = json.loads(receipt.read_text())["events"]
    assert len(events) == 12
    for e in events:
        refs = [ReviewedReference(**r) for r in e["references"]]
        tr = next(r for r in refs if r.side is None)
        event = EvidenceBytes(tr.path, Path(tr.path).read_bytes())
        target_doc = json.loads(event.content)
        hist = {"home": [], "away": []}
        contract_refs = [tr]
        for ref in (r for r in refs if r.side):
            source = EvidenceBytes(ref.path, Path(ref.path).read_bytes())
            derived, chain = derive_native_history_envelope(
                source,
                source_reference=ref,
                target=target_doc,
                side=ref.side,
                review_root=root,
                derived_path=out
                / "native-envelope-derived"
                / f"envelope-{e['event_order']}-{ref.side}.json",
                derived_at="2026-09-15T15:27:00+00:00",
            )
            # Real persisted derived fixtures were produced by the bounded job;
            # do not generate new inputs or mutate archives during this test.
            if not (root / derived.path).exists():
                pytest.skip("derived research fixture not materialized")
            assert (root / derived.path).read_bytes() == derived.content
            assert chain["review_authority_issued"] is False
            assert source.content == Path(ref.path).read_bytes()
            hist[ref.side].append(derived)
            contract_refs.append(
                replace(
                    ref,
                    path=derived.path,
                    sha256=hashlib.sha256(derived.content).hexdigest(),
                )
            )
        event, hist, contract_refs = relative_evidence_bundle(
            event, hist, contract_refs, review_root=root
        )
        o1 = assess_family_evidence(
            event=event,
            verified_event_local_histories=hist,
            reviewed_refs=contract_refs,
        )
        assert o1["status"] == "COMPLETE"
        assert all(s["source_status"] == "AVAILABLE" for s in o1["sides"].values())
        assert all(s["observed_history_count"] >= 10 for s in o1["sides"].values())
        bk = next(
            x["bk_probabilities"]
            for x in cached
            if x["drawing_number"] == 4999 and x["event_order"] == e["event_order"]
        )
        row = build_v3_predictors(
            event=event,
            verified_event_local_histories=hist,
            reviewed_refs=contract_refs,
            drawing_number=4999,
            bk_probabilities=bk,
            deadline="2026-09-07T14:30:00+00:00",
        )
        validate_feature_row(row)
        assert row["scope_verified"] is False
        assert reliability(row, FEATURE_NAMES) == 0
        assert row["evaluation_authorized"] is False
