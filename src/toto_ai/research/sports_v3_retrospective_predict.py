"""INACTIVE mixed retrospective A5 inference, never an operator probability input.

The request's file digest is an external review trust anchor. Hashes authenticate
bytes, not the truth of evidence: identity decisions must come from independent
review. Missing Sports never acquires invented fixture IDs or kickoff times.
"""

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from toto_ai.research.sports_v3_retrospective_fit import (
    DOMAIN,
    _code_bindings,
    _validate_row,
)
from toto_ai.sports_stats.v3_probability import (
    FEATURE_NAMES,
    _bk,
    _check,
    _hash,
    _sealed,
    _time,
    _transform,
    digest,
    seal,
)
from toto_ai.sports_stats.v3_residual_kernel import softmax

KIND = "MIXED_RETROSPECTIVE_FIXED_A5_BK_V1"
CURRENT_KIND = "CURRENT_SEALED_MIXED_SPORTS_V3_PREDICTION_V1"
REVIEWED = "INDEPENDENT_ENTITY_LINEAGE_REVIEWED"
FLAGS = dict(
    operator_compatible=False,
    automatic_wagering=False,
    activation_allowed=False,
    profitability_proven=False,
    blind_holdout=False,
)
ROSTER_FIELDS = set(
    "row_id drawing_number event_order target_event_id decision_cutoff "
    "bk_probabilities bk_input_sha256 bk_input_file_sha256 bk_fetched_at "
    "bk_quote_available_at evidence_grade taxonomy feature_missing_mask "
    "identity_status "
    "operator_compatible automatic_wagering status kickoff provider_fixture_id "
    "sports_numeric_features feature_sha256 source_binding_grade missing_fields".split()
)


def _path(root, path):
    root = Path(root).resolve()
    p = Path(path)
    p = (root / p).resolve() if not p.is_absolute() else p.resolve()
    _check(p.is_relative_to(root), "path outside research root")
    return p


def read_checked(root, path, expected_file_sha256):
    """Physical-file check, deliberately distinct from any JSON payload seal."""
    p = _path(root, path)
    _hash(expected_file_sha256)
    data = p.read_bytes()
    _check(
        hashlib.sha256(data).hexdigest() == expected_file_sha256, "file hash mismatch"
    )
    return json.loads(data)


def validate_model(model):
    _sealed(model)
    _check(
        model["kind"] == "RETROSPECTIVE_SPORTS_V3_MODEL_V1"
        and model["domain"] == DOMAIN
        and model["variant"] == "A5",
        "research model kind",
    )
    _check(
        all(model[k] is False for k in FLAGS if k != "blind_holdout"), "research only"
    )
    _check(
        model["status"] == "TRAINED_EXPERIMENTAL" and model["fit_completed"],
        "not fitted",
    )
    prep = model["preparation"]
    _sealed(prep)
    _check(prep["sha256"] == model["preparation_sha256"], "preparation binding")
    _check(model["code_sha256"] == _code_bindings(), "model code binding")
    _check(model["training_sha256"] == prep["training_sha256"], "training binding")
    _check(
        model["training_drawings"] == prep["train_drawings"]
        and all(d < model["target_drawing"] for d in model["training_drawings"]),
        "training target separation",
    )
    _check(prep["heldout_pending"], "partial contract requires pending heldout model")
    _check(model["feature_names"] == list(FEATURE_NAMES), "feature schema")
    w = np.array(model["weights"])
    _check(w.shape == (107, 3) and np.all(np.isfinite(w)), "weights shape/finite")
    return w


def _roster(rows):
    _check(bool(rows) and len(rows) <= 120, "roster size")
    result = {}
    for r in rows:
        _check(set(r) <= ROSTER_FIELDS, "roster field allowlist")
        d, i = r["drawing_number"], r["event_order"]
        _check(type(d) is int and type(i) is int and 0 <= i < 15, "roster identity")
        _check(
            type(r["target_event_id"]) is int and r["target_event_id"] > 0,
            "source-local identity",
        )
        _check(r["row_id"] == f"{d}:{i}:{r['target_event_id']}", "roster row binding")
        _check((d, i) not in result, "duplicate roster slot")
        _bk(r["bk_probabilities"])
        _hash(r["bk_input_sha256"])
        _hash(r["bk_input_file_sha256"])
        _time(r["decision_cutoff"])
        _time(r["bk_fetched_at"])
        if r["bk_quote_available_at"] is not None:
            _check(
                _time(r["bk_quote_available_at"]) <= _time(r["decision_cutoff"])
                and _time(r["bk_quote_available_at"]) <= _time(r["bk_fetched_at"]),
                "known post-decision quote",
            )
        _check(
            not r.get("operator_compatible") and not r.get("automatic_wagering"),
            "research roster",
        )
        result[d, i] = r
    for d in {d for d, _ in result}:
        group = [r for (draw, _), r in result.items() if draw == d]
        _check(
            len(group) == 15 and len({r["target_event_id"] for r in group}) == 15,
            "complete unique roster required",
        )
        _check(
            len({r["bk_input_sha256"] for r in group}) == 1
            and len({r["decision_cutoff"] for r in group}) == 1,
            "drawing input binding",
        )
    return result


def derive_reviewed(original_rows, decisions, roster):
    """Authorize exactly an independent review's identity-only derived copies."""
    slots = _roster(roster)
    originals = {}
    for r in original_rows:
        _validate_row(
            r, {r["sha256"]}
        )  # schema, provenance and completion, NOT authority
        key = r["sha256"]
        _check(key not in originals, "duplicate original feature")
        originals[key] = r
    result, seen = [], set()
    for decision in decisions:
        if decision["decision"] != "ACCEPT":
            continue
        old = decision["original_row_sha256"]
        _check(
            old in originals and old not in seen, "review original binding/duplicate"
        )
        seen.add(old)
        r = originals[old]
        slot = slots.get((r["drawing_number"], r["event_order"]))
        _check(slot is not None, "review outside roster")
        _check(
            decision["row_id"] == slot["row_id"]
            and decision["event_order"] == r["event_order"]
            and slot.get("feature_sha256") == old,
            "review slot binding",
        )
        raw = decision["raw_identity"]
        _check(
            raw["fixture_id"] == r["event_id"] == slot["provider_fixture_id"]
            and _time(raw["kickoff_utc"])
            == _time(r["kickoff"])
            == _time(slot["kickoff"]),
            "review fixture/time binding",
        )
        _check(
            decision["allowed_identity_status_update"]
            == {"from": "UNKNOWN", "to": REVIEWED}
            and r["identity_status"] == "UNKNOWN",
            "identity-only authorization",
        )
        for name in [
            "bk_probabilities",
            "bk_input_sha256",
            "decision_cutoff",
            "bk_fetched_at",
            "bk_quote_available_at",
        ]:
            _check(r[name] == slot[name], f"Sports/market {name} binding")
        result.append(seal({**r, "identity_status": REVIEWED}))
    return result


def predict_partial(model, roster, original_rows, decisions):
    """Pure inference; caller supplies independently authenticated evidence only.

    No labels, optimizer, package generator or production registration is used.
    Exactly the old native row transform/residual/softmax/L1-cap arithmetic.
    """
    weights = validate_model(model)
    slots = _roster(roster)
    derived = derive_reviewed(original_rows, decisions, roster)
    approved = {(r["drawing_number"], r["event_order"]): r for r in derived}
    _check(len(approved) == len(derived), "duplicate approved slot")
    train_ids = set(model["preparation"]["training_fixture_ids"])
    known_ids = set()
    active = [
        name
        for i, name in enumerate(FEATURE_NAMES)
        if name not in {"bk_margin", "bk_entropy"} and np.any(weights[i + 1] != 0)
    ]
    output = []
    for key, slot in sorted(slots.items()):
        _check(
            key[0] >= model["target_drawing"]
            and _time(slot["decision_cutoff"]) >= _time(model["prediction_as_of"]),
            "heldout chronology",
        )
        fixture = slot.get("provider_fixture_id")
        if fixture is not None:
            _check(fixture not in train_ids, "train/heldout canonical fixture overlap")
            _check(fixture not in known_ids, "duplicate heldout fixture")
            known_ids.add(fixture)
        r = approved.get(key)
        bk = np.array(slot["bk_probabilities"])
        probabilities = bk.copy()
        weight, observed = 0.0, []
        status, reason = (
            "BK_FALLBACK",
            "NO_INDEPENDENTLY_APPROVED_SPORTS:" + slot["status"],
        )
        if r is not None:
            weight = _validate_row(r, {x["sha256"] for x in derived})
            observed = [n for n in active if r["features"][n] is not None]
            genuine = any(
                v is not None
                for n, v in r["features"].items()
                if n not in {"bk_margin", "bk_entropy"}
            )
            if weight > 0 and genuine:
                matrix, _ = _transform([r], FEATURE_NAMES, model["transform"])
                residual = np.einsum("i,ij->j", matrix[0], weights, optimize=False)
                residual -= residual.mean()
                logits = np.log(bk)
                logits -= logits.mean()
                probabilities = softmax(logits + weight * residual)
                distance = float(np.sum(np.abs(probabilities - bk)))
                if distance > 0.2:
                    probabilities = bk + ((0.2 - 1e-14) / distance) * (
                        probabilities - bk
                    )
                status, reason = (
                    "SPORTS_APPLIED",
                    "REVIEWED_IDENTITY_GENUINE_PAST_FEATURES",
                )
            else:
                weight = 0.0
                reason = "NO_GENUINE_SPORTS_OR_ZERO_RELIABILITY"
        _check(
            np.all(np.isfinite(probabilities))
            and np.all(probabilities > 0)
            and abs(float(probabilities.sum()) - 1) <= 1e-12
            and float(np.sum(np.abs(probabilities - bk))) <= 0.2,
            "prediction caps",
        )
        output.append(
            {
                k: deepcopy(slot[k])
                for k in [
                    "row_id",
                    "drawing_number",
                    "event_order",
                    "target_event_id",
                    "bk_input_sha256",
                    "bk_input_file_sha256",
                    "decision_cutoff",
                    "bk_quote_available_at",
                    "bk_fetched_at",
                ]
            }
            | dict(
                provider_fixture_id=fixture,
                kickoff=slot.get("kickoff"),
                probabilities=probabilities.tolist(),
                bk_probabilities=list(slot["bk_probabilities"]),
                feature_sha256=r["sha256"] if r else None,
                reliability=weight,
                status=status,
                fallback_or_application_reason=reason,
                observed_active_sports=observed,
                missing_active_sports=[n for n in active if n not in observed],
            )
        )
    count = sum(r["status"] == "SPORTS_APPLIED" for r in output)
    return seal(
        dict(
            kind=KIND,
            domain=DOMAIN,
            model_payload_sha256=model["sha256"],
            model_code_sha256=model["code_sha256"],
            model_training_sha256=model["training_sha256"],
            roster_sha256=digest(roster),
            derived_features_sha256=digest(derived),
            rows=output,
            sports_applied=count,
            bk_fallback=len(output) - count,
            active_sports_feature_names=active,
            denominator=len(output),
            frozen_at=datetime.now(timezone.utc).isoformat(),
            evidence_grade="UNVERIFIED_ASOF_SENSITIVITY",
            protocol="CHRONOLOGICAL_PREVIOUSLY_SEEN_NONBLIND",
            **FLAGS,
        )
    )


def predict_request(root, request_path, request_file_sha256):
    """Validate pinned input/review/source files; freeze function takes no labels."""
    request = read_checked(root, request_path, request_file_sha256)
    _check(request["kind"] == "R3_MIXED_RESEARCH_REQUEST_V2", "request kind")
    source_path = _path(root, request["source_request_path"])
    source = read_checked(root, source_path, request["source_request_file_sha256"])
    _check(
        source["labels_included"] is False
        and source["fit_allowed"] is False
        and source["operator_compatible"] is False,
        "source research boundary",
    )
    _check(
        source["model_sha256"] == request["model_payload_sha256"]
        and source["model_file_sha256"] == request["model_file_sha256"],
        "model request binding",
    )
    model = read_checked(root, source["model_path"], request["model_file_sha256"])
    _sealed(model)
    _check(model["sha256"] == request["model_payload_sha256"], "model payload hash")

    def local(name):
        return read_checked(root, source_path.parent / name, source["hashes"][name])

    roster = local("evaluation-denominator.json")
    originals = local("r3-evaluation-features.json") + local(
        "r3-provisional-features-not-admitted.json"
    )
    sources = local("source-hashes.json")
    # Historical/target RAW archives are not parsed here: independent review pins
    # identity/source bytes. Closed-market inputs contain no target labels.
    for draw in source["drawing_numbers"]:
        paths = [p for p in sources if Path(p).name == f"input-{draw}.json"]
        _check(len(paths) == 1, "unique market source")
        path = paths[0]
        market = read_checked(root, path, sources[path])
        from toto_ai.research.closed_market_scenario_replay import validate_input

        native = validate_input(market)
        group = sorted(
            (r for r in roster if r["drawing_number"] == draw),
            key=lambda r: r["event_order"],
        )
        _check(
            len(group) == 15 and market["market"]["number"] == draw,
            "market drawing binding",
        )
        for i, slot in enumerate(group):
            event = market["market"]["events"][i]
            _check(
                event["order"] == slot["event_order"] == i
                and event["id"] == slot["target_event_id"]
                and slot["bk_input_sha256"] == market["sha256"]
                and slot["bk_input_file_sha256"] == sources[path]
                and slot["bk_probabilities"] == list(native.ev.true_probabilities[i])
                and slot["bk_fetched_at"] == market["captured_at"]
                and slot["bk_quote_available_at"] == market["quote_available_at"],
                "RAW-market roster binding",
            )
    _check(
        sorted({r["drawing_number"] for r in roster}) == source["drawing_numbers"],
        "drawing roster",
    )
    decisions = []
    verified_bytes = {}
    for ref in request["identity_reviews"]:
        review = read_checked(root, ref["path"], ref["file_sha256"])
        for decision in review["decisions"]:
            for src in decision.get(
                "selected_source_hash_checks", decision.get("source_hash_checks", [])
            ):
                p = _path(root, src["path"])
                if p not in verified_bytes:
                    verified_bytes[p] = hashlib.sha256(p.read_bytes()).hexdigest()
                _check(
                    verified_bytes[p] == src["sha256"], "review source bytes changed"
                )
            decisions.append(decision)
    result = predict_partial(model, roster, originals, decisions)
    return seal(
        {
            **result,
            "request_file_sha256": request_file_sha256,
            "source_request_file_sha256": request["source_request_file_sha256"],
            "model_file_sha256": request["model_file_sha256"],
            "identity_reviews": request["identity_reviews"],
            "adapter_file_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
        }
    )


def predict_current_sealed_request(root, request_path, request_file_sha256):
    """Replay a reviewed current-drawing sealed input, without labels or fitting.

    This deliberately uses the same ``predict_partial`` arithmetic as the frozen
    retrospective adapter.  The request binds every consumed file, and is only a
    research bridge: it does not make a current market an operator input.
    """
    request = read_checked(root, request_path, request_file_sha256)
    _check(request["kind"] == "CURRENT_SEALED_SPORTS_V3_REQUEST_V1", "request kind")
    _check(all(request[k] is False for k in FLAGS), "research-only current request")

    def read(ref):
        return read_checked(root, ref["path"], ref["file_sha256"])

    model = read(request["model"])
    roster_doc = read(request["roster"])
    rows_doc = read(request["original_rows"])
    decisions_doc = read(request["consumer_decisions"])
    manifest = read(request["manifest"])
    final = read(request["final_input"])
    _check(
        manifest["drawing_number"] == request["drawing_number"]
        and manifest["inputs"]["model_sha256"] == request["model"]["file_sha256"]
        and manifest["inputs"]["final_input_file_sha256"]
        == request["final_input"]["file_sha256"]
        and manifest["inputs"]["probability_input_sha256"]
        == final["probability_input_sha256"],
        "sealed manifest input binding",
    )
    _check(
        roster_doc["drawing_number"]
        == rows_doc["drawing_number"]
        == decisions_doc["drawing_number"]
        == request["drawing_number"]
        and decisions_doc["review_verdict"] == "ACCEPT_12_EXACTLY_BK_FALLBACK_3"
        and all(
            x is False
            for x in (
                roster_doc["operator_compatible"],
                roster_doc["automatic_wagering"],
            )
        ),
        "sealed reviewed drawing contract",
    )
    roster, rows, decisions = (
        roster_doc["slots"],
        rows_doc["rows"],
        decisions_doc["decisions"],
    )
    _check(
        all(
            r["bk_input_file_sha256"] == request["final_input"]["file_sha256"]
            for r in roster
        )
        and all(
            r["bk_input_sha256"] == final["probability_input_sha256"] for r in roster
        ),
        "roster final input binding",
    )
    result = predict_partial(model, roster, rows, decisions)
    _check(
        result["sports_applied"] == 12 and result["bk_fallback"] == 3, "review coverage"
    )
    return seal(
        {
            **result,
            "kind": CURRENT_KIND,
            "request_file_sha256": request_file_sha256,
            "model_file_sha256": request["model"]["file_sha256"],
            "final_input_file_sha256": request["final_input"]["file_sha256"],
            "final_input_snapshot_sha256": final["snapshot_sha256"],
            "adapter_file_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
        }
    )


def write_frozen(path, predictions):
    _sealed(predictions)
    _check(predictions["kind"] in {KIND, CURRENT_KIND}, "prediction kind")
    data = (
        json.dumps(predictions, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    with Path(path).open("xb") as f:
        f.write(data)
        f.flush()
        import os

        os.fsync(f.fileno())
    return hashlib.sha256(data).hexdigest()


def score_frozen(path, expected_file_sha256, load_labels):
    """Labels are requested only AFTER the persisted predictions pass both hashes."""
    predictions = read_checked(Path(path).parent, path, expected_file_sha256)
    _sealed(predictions)
    _check(
        predictions["kind"] == KIND and all(predictions[k] is False for k in FLAGS),
        "research predictions",
    )
    labels = load_labels()
    expected = {
        (r["drawing_number"], r["event_order"], r["target_event_id"]): r
        for r in predictions["rows"]
    }
    bound = {}
    for label in labels:
        _check(
            set(label)
            == {
                "drawing_number",
                "event_order",
                "target_event_id",
                "outcome",
                "source_sha256",
            },
            "label schema",
        )
        key = label["drawing_number"], label["event_order"], label["target_event_id"]
        _check(key in expected and key not in bound, "label roster binding")
        _check(
            type(label["outcome"]) is int and label["outcome"] in (0, 1, 2),
            "label outcome",
        )
        _hash(label["source_sha256"])
        bound[key] = label["outcome"]
    _check(set(bound) == set(expected), "label coverage")

    def metrics(keys, field):
        loss = brier = 0.0
        for k in keys:
            p, y = expected[k][field], bound[k]
            loss -= math.log(p[y])
            brier += math.fsum((value - (j == y)) ** 2 for j, value in enumerate(p))
        return dict(log_loss=loss / len(keys), brier=brier / len(keys))

    def report(keys):
        return dict(
            count=len(keys),
            mixed=metrics(keys, "probabilities"),
            bk=metrics(keys, "bk_probabilities"),
        )

    result = report(list(expected))
    sports = [k for k, r in expected.items() if r["status"] == "SPORTS_APPLIED"]
    return seal(
        dict(
            kind="MIXED_RETROSPECTIVE_SCORE_V1",
            **result,
            per_drawing={
                str(d): report([k for k in expected if k[0] == d])
                for d in sorted({k[0] for k in expected})
            },
            sports_subset=report(sports) if sports else None,
            predictions_file_sha256=expected_file_sha256,
            predictions_payload_sha256=predictions["sha256"],
            labels_sha256=digest(labels),
            labels_source_hashes=sorted({label["source_sha256"] for label in labels}),
            scored_at=datetime.now(timezone.utc).isoformat(),
            **FLAGS,
            evidence_grade=predictions["evidence_grade"],
            protocol=predictions["protocol"],
        )
    )
