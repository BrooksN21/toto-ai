"""Isolated partial research inference; synthetic fixtures are not real evidence."""

import runpy
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from toto_ai.research.sports_v3_retrospective_fit import (
    fit_research,
    freeze_predictions,
)
from toto_ai.research.sports_v3_retrospective_predict import (
    derive_reviewed,
    predict_partial,
    read_checked,
    score_frozen,
    validate_model,
    write_frozen,
)
from toto_ai.sports_stats.v3_probability import FEATURE_NAMES, seal

FIX = runpy.run_path(
    str(Path(__file__).with_name("test_sports_v3_retrospective_fit.py"))
)


@pytest.fixture(scope="module")
def model():
    records, _ = FIX["inputs"]()
    return fit_research(
        records,
        [],
        target_drawing=5002,
        prediction_as_of="2026-09-04T10:00:00Z",
        heldout_pending=True,
        independently_reviewed_hashes={r["features"]["sha256"] for r in records},
    )


def case(n=13):
    rows = [
        seal({**FIX["row"](5002, i), "identity_status": "UNKNOWN"}) for i in range(n)
    ]
    roster = []
    for i in range(15):
        r = FIX["row"](5002, i)
        roster.append(
            dict(
                row_id=f"5002:{i}:{100 + i}",
                drawing_number=5002,
                event_order=i,
                target_event_id=100 + i,
                decision_cutoff=r["decision_cutoff"],
                bk_probabilities=r["bk_probabilities"],
                bk_input_sha256=r["bk_input_sha256"],
                bk_input_file_sha256="d" * 64,
                bk_fetched_at=r["bk_fetched_at"],
                bk_quote_available_at=None,
                provider_fixture_id=r["event_id"] if i < n else None,
                kickoff=r["kickoff"] if i < n else None,
                status="MISSING_SPORTS",
                feature_sha256=rows[i]["sha256"] if i < n else None,
            )
        )
    decisions = [
        dict(
            decision="ACCEPT",
            row_id=roster[i]["row_id"],
            event_order=i,
            original_row_sha256=r["sha256"],
            raw_identity=dict(fixture_id=r["event_id"], kickoff_utc=r["kickoff"]),
            allowed_identity_status_update=dict(
                **{"from": "UNKNOWN", "to": "INDEPENDENT_ENTITY_LINEAGE_REVIEWED"}
            ),
        )
        for i, r in enumerate(rows)
    ]
    return roster, rows, decisions


def test_partial_native_exact_parity_and_immutable(model):
    roster, rows, decisions = case(15)
    before = deepcopy(model)
    derived = derive_reviewed(rows, decisions, roster)
    native = freeze_predictions(
        model, derived, independently_reviewed_hashes={r["sha256"] for r in derived}
    )
    mixed = predict_partial(model, roster, rows, decisions)
    assert [r["probabilities"] for r in mixed["rows"]] == [
        r["probabilities"] for r in native["rows"]
    ]
    assert model == before


def test_13_sports_2_exact_bk(model):
    roster, rows, decisions = case()
    p = predict_partial(model, roster, rows, decisions)
    assert p["sports_applied"] == 13 and p["bk_fallback"] == 2
    assert len(p["rows"]) == 15
    assert p["rows"][13]["probabilities"] == roster[13]["bk_probabilities"]
    assert p["rows"][13]["provider_fixture_id"] is None
    assert not p["operator_compatible"] and not p["blind_holdout"]


def test_unreviewed_all_bk(model):
    roster, rows, _ = case()
    p = predict_partial(model, roster, rows, [])
    assert p["sports_applied"] == 0
    assert [r["probabilities"] for r in p["rows"]] == [
        r["bk_probabilities"] for r in roster
    ]


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("duplicate", "roster"),
        ("missing", "roster"),
        ("slot", "binding"),
        ("bk", "binding"),
        ("fixture", "binding"),
        ("future", "history completion"),
        ("target", "target in history"),
        ("label", "allowlist"),
        ("overlap", "overlap"),
        ("tamper", "hash"),
    ],
)
def test_invalid_inputs_failclosed(model, mutation, match):
    roster, rows, decisions = case()
    if mutation == "duplicate":
        roster[-1] = deepcopy(roster[0])
    elif mutation == "missing":
        roster.pop()
    elif mutation == "slot":
        decisions[0]["row_id"] = roster[1]["row_id"]
    elif mutation == "bk":
        roster[0]["bk_probabilities"] = [0.3, 0.3, 0.4]
    elif mutation == "fixture":
        roster[0]["provider_fixture_id"] = "another"
    elif mutation == "tamper":
        rows[0]["features"]["home_rest_days"] = 77
    else:
        if mutation == "future":
            rows[0]["history"][0]["completed_by"] = rows[0]["decision_cutoff"]
        if mutation == "target":
            rows[0]["history"][0]["fixture_id"] = rows[0]["event_id"]
        if mutation == "label":
            rows[0]["outcome"] = 1
        if mutation == "overlap":
            rows[0]["event_id"] = model["preparation"]["training_fixture_ids"][0]
            roster[0]["provider_fixture_id"] = rows[0]["event_id"]
            decisions[0]["raw_identity"]["fixture_id"] = rows[0]["event_id"]
        rows[0] = seal(rows[0])
        decisions[0]["original_row_sha256"] = rows[0]["sha256"]
        roster[0]["feature_sha256"] = rows[0]["sha256"]
    with pytest.raises(ValueError, match=match):
        predict_partial(model, roster, rows, decisions)


@pytest.mark.parametrize("field", ["code_sha256", "feature_names", "weights"])
def test_model_contract(model, field):
    m = deepcopy(model)
    if field == "code_sha256":
        m[field]["research"] = "f" * 64
    if field == "feature_names":
        m[field] = list(reversed(m[field]))
    if field == "weights":
        m[field] = [[0, 0, 0]]
    with pytest.raises(ValueError):
        validate_model(seal(m))


def test_order_and_imputation_parity(model):
    roster, rows, decisions = case()
    p = predict_partial(model, roster, rows, decisions)
    # Dictionary order has no role in a sealed JSON object or frozen transform.
    for r in rows:
        r["features"] = dict(reversed(list(r["features"].items())))
    q = predict_partial(
        model, list(reversed(roster)), list(reversed(rows)), list(reversed(decisions))
    )
    assert p["rows"] == q["rows"]


@pytest.mark.parametrize("count", [0, 5, 10])
def test_reliability_exact_zero_observed(model, count):
    roster, rows, decisions = case(1)
    rows[0]["features"] = {n: None for n in FEATURE_NAMES}
    rows[0]["features"]["home_rest_days"] = 0.0
    rows[0]["prior_counts"] = [count, count]
    rows[0] = seal(rows[0])
    decisions[0]["original_row_sha256"] = rows[0]["sha256"]
    roster[0]["feature_sha256"] = rows[0]["sha256"]
    p = predict_partial(model, roster, rows, decisions)
    assert p["rows"][0]["reliability"] == 0.2 * min(1.0, count / 10) * (1 / 53)


@pytest.mark.parametrize("only_market", [False, True])
def test_no_sports_values_no_intercept_only_claim(model, only_market):
    roster, rows, decisions = case(1)
    rows[0]["features"] = {n: None for n in FEATURE_NAMES}
    if only_market:
        rows[0]["features"]["bk_entropy"] = 1.0
    rows[0] = seal(rows[0])
    decisions[0]["original_row_sha256"] = rows[0]["sha256"]
    roster[0]["feature_sha256"] = rows[0]["sha256"]
    p = predict_partial(model, roster, rows, decisions)
    assert p["sports_applied"] == 0
    assert p["rows"][0]["probabilities"] == roster[0]["bk_probabilities"]


def test_full120_fallback(model):
    roster, _, _ = case(0)
    allrows = []
    for draw in range(5002, 5010):
        for r in roster:
            r = deepcopy(r)
            r["drawing_number"] = draw
            r["row_id"] = f"{draw}:{r['event_order']}:{r['target_event_id']}"
            allrows.append(r)
    p = predict_partial(model, allrows, [], [])
    assert len(p["rows"]) == 120 and p["bk_fallback"] == 120


def test_file_hash_path_and_scoring_after_freeze(model, tmp_path):
    import json
    from hashlib import sha256

    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    filehash = sha256(path.read_bytes()).hexdigest()
    assert read_checked(tmp_path, path, filehash) == model
    with pytest.raises(ValueError, match="file hash"):
        read_checked(tmp_path, path, model["sha256"])
    with pytest.raises(ValueError, match="path"):
        read_checked(tmp_path, tmp_path / "../outside", "0" * 64)
    p = predict_partial(model, *case())
    labels = [
        dict(
            drawing_number=5002,
            event_order=i,
            target_event_id=100 + i,
            outcome=i % 3,
            source_sha256="a" * 64,
        )
        for i in range(15)
    ]
    seen = []

    def load():
        seen.append(1)
        return labels

    with pytest.raises((ValueError, FileNotFoundError)):
        score_frozen(tmp_path / "none", "0" * 64, load)
    assert not seen
    ref = write_frozen(tmp_path / "predictions.json", p)
    with pytest.raises(FileExistsError):
        write_frozen(tmp_path / "predictions.json", p)
    score = score_frozen(tmp_path / "predictions.json", ref, load)
    assert seen == [1] and score["count"] == 15
    assert np.isfinite(score["mixed"]["brier"])


@pytest.fixture
def request_bundle(model, tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    from toto_ai.research import closed_market_scenario_replay as scenario

    monkeypatch.setattr(
        scenario,
        "validate_input",
        lambda _: SimpleNamespace(
            ev=SimpleNamespace(true_probabilities=[[0.4, 0.3, 0.3]] * 15)
        ),
    )

    def put(name, value):
        path = tmp_path / name
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        return str(path), hashlib.sha256(path.read_bytes()).hexdigest()

    modelpath, modelfile = put("model.json", model)
    roster, rows, decisions = case()
    market = dict(
        sha256="b" * 64,
        captured_at=roster[0]["bk_fetched_at"],
        quote_available_at=None,
        market=dict(number=5002, events=[dict(id=100 + i, order=i) for i in range(15)]),
    )
    marketpath, marketfile = put("input-5002.json", market)
    for r in roster:
        r["bk_input_file_sha256"] = marketfile
    hashes = {}
    for name, value in [
        ("evaluation-denominator.json", roster),
        ("r3-evaluation-features.json", rows),
        ("r3-provisional-features-not-admitted.json", []),
        ("source-hashes.json", {marketpath: marketfile}),
    ]:
        _, hashes[name] = put(name, value)
    source = dict(
        labels_included=False,
        fit_allowed=False,
        operator_compatible=False,
        model_path=modelpath,
        model_sha256=model["sha256"],
        model_file_sha256=modelfile,
        hashes=hashes,
        drawing_numbers=[5002],
    )
    sourcepath, sourcefile = put("source.json", source)
    reviewpath, reviewfile = put("review.json", dict(decisions=decisions))
    request = dict(
        kind="R3_MIXED_RESEARCH_REQUEST_V2",
        source_request_path=sourcepath,
        source_request_file_sha256=sourcefile,
        model_payload_sha256=model["sha256"],
        model_file_sha256=modelfile,
        identity_reviews=[dict(path=reviewpath, file_sha256=reviewfile)],
    )
    path, sha = put("request.json", request)
    return tmp_path, request, put, path, sha


def test_pinned_loader_applies_review_and_both_hash_roles(request_bundle):
    from toto_ai.research.sports_v3_retrospective_predict import predict_request

    root, _, _, path, sha = request_bundle
    p = predict_request(root, path, sha)
    assert p["sports_applied"] == 13 and p["bk_fallback"] == 2
    assert p["model_payload_sha256"] != p["model_file_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "swapped_roles",
        "wrong_payload",
        "source_tamper",
        "review_tamper",
        "roster_tamper",
    ],
)
def test_loader_rejects_tampered_authority(request_bundle, mutation):
    from toto_ai.research.sports_v3_retrospective_predict import predict_request

    root, request, put, path, sha = request_bundle
    if mutation == "swapped_roles":
        request["model_payload_sha256"], request["model_file_sha256"] = (
            request["model_file_sha256"],
            request["model_payload_sha256"],
        )
        path, sha = put("request.json", request)
    elif mutation == "wrong_payload":
        request["model_payload_sha256"] = "1" * 64
        path, sha = put("request.json", request)
    else:
        name = {
            "source_tamper": "input-5002.json",
            "review_tamper": "review.json",
            "roster_tamper": "evaluation-denominator.json",
        }[mutation]
        with (root / name).open("a") as f:
            f.write(" ")
    with pytest.raises(ValueError, match="binding|hash"):
        predict_request(root, path, sha)


def test_extreme_logits_cap_finite_and_exact_native(model):
    roster, rows, decisions = case(15)
    m = deepcopy(model)
    m["weights"][0] = [1e6, -1e6, 0.0]
    m = seal(m)
    derived = derive_reviewed(rows, decisions, roster)
    p = predict_partial(m, roster, rows, decisions)
    n = freeze_predictions(
        m, derived, independently_reviewed_hashes={r["sha256"] for r in derived}
    )
    assert [r["probabilities"] for r in p["rows"]] == [
        r["probabilities"] for r in n["rows"]
    ]
    for r in p["rows"]:
        assert all(v > 0 for v in r["probabilities"])
        assert (
            sum(
                abs(a - b)
                for a, b in zip(r["probabilities"], r["bk_probabilities"], strict=True)
            )
            <= 0.2
        )


def test_stale_derived_bk_placeholders_not_used_as_values(model):
    roster, rows, decisions = case(1)
    outputs = []
    for entropy, margin in [(1.0, 0.2), (999.0, -10.0)]:
        rows[0]["features"]["bk_entropy"] = entropy
        rows[0]["features"]["bk_margin"] = margin
        rows[0] = seal(rows[0])
        decisions[0]["original_row_sha256"] = rows[0]["sha256"]
        roster[0]["feature_sha256"] = rows[0]["sha256"]
        outputs.append(
            predict_partial(model, roster, rows, decisions)["rows"][0]["probabilities"]
        )
    assert outputs[0] == outputs[1]
