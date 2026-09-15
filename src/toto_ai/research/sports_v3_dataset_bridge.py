"""Read-only research provenance bridge; never grants review or fit authority.

Schedule consensus is supporting identity evidence, not approval of every prior
match's gender/age/squad. Missing historical scope remains missing. Callers may
persist returned bytes as NEW research artifacts; this module writes nothing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from toto_ai.external_odds.schedule_evidence import (
    load_bound_schedule_evidence_ledger,
    resolve_schedule_evidence,
)
from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import load_scheduler_plan
from toto_ai.sports_stats.v3_family_evidence import EvidenceBytes
from toto_ai.sports_stats.v3_probability import (
    _check,
    _hash,
    _time,
    seal,
    validate_feature_row,
)
from toto_ai.sports_stats.v3_probability_features import _history, build_v3_predictors

SCOPE = ("gender", "age_group", "squad_type")


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _iso(value):
    return value if isinstance(value, str) else value.isoformat()


def bind_projection(projection, *, snapshot, event_id, plan_sha256):
    """Pure component; snapshot must come from load_final_input (prepare_bridge)."""
    _hash(snapshot.snapshot_sha256)
    _hash(plan_sha256)
    _check(projection["drawing_id"] == snapshot.drawing_id, "drawing binding")
    _check(str(projection["target_event_id"]) == str(event_id), "event binding")
    _check(
        _time(projection["as_of"]) == _time(_iso(snapshot.captured_at)),
        "as_of input binding",
    )
    _check(
        _time(projection["final_captured_at"]) == _time(_iso(snapshot.captured_at)),
        "capture input binding",
    )
    _check(
        projection.get("final_input_sha256", snapshot.snapshot_sha256)
        == snapshot.snapshot_sha256,
        "final input hash binding",
    )
    result = copy.deepcopy(projection)
    result["final_input_sha256"] = snapshot.snapshot_sha256
    result["scheduler_plan_sha256"] = plan_sha256
    return result


def history_readiness(blob, *, target, side):
    """Run native chronology/identity checks; never fill classes from target."""
    _check(side in ("home", "away"), "history side")
    document = json.loads(blob.content)
    rows, exclusions = _history(document, team=target[side + "_team_id"], target=target)
    for raw in document["payload"]["data"]:
        if raw.get("updatedAt") is not None:
            _check(
                _time(raw["updatedAt"]) <= _time(target["as_of"]),
                "post-asof history source version",
            )
    missing = {key: sum(row["scope"].get(key) is None for row in rows) for key in SCOPE}
    return {
        "path": blob.path,
        "sha256": _sha(blob.content),
        "native_history_status": "PASS",
        "rows": len(rows),
        "scope_complete_rows": sum(
            all(row["scope"].get(k) is not None for k in SCOPE) for row in rows
        ),
        "missing_scope_fields": missing,
        "exclusions": exclusions,
        "scope_authorized": False,
        "missing_policy": "PRESERVE_UNKNOWN_NO_TARGET_SCOPE_INHERITANCE",
    }


def link_schedule_evidence(target, *, review, expected_review_sha256, sources):
    """Link pre-existing review bytes to exact source bytes, not new authority.

    prepare_bridge additionally verifies native ledger/target resolution and
    review chronology. This helper alone does not confer schedule authority.
    """
    _check(_sha(review.content) == expected_review_sha256, "review hash binding")
    links = dict(
        re.findall(
            r"evidence: `([^`]+)` — SHA-256 `([a-f0-9]{64})`", review.content.decode()
        )
    )
    providers, bound = set(), []
    for blob in sources:
        _check(links.get(blob.path) == _sha(blob.content), "review source hash binding")
        source = json.loads(blob.content)
        _check(
            (
                source["drawing_id"],
                source["event_order"],
                str(source["target_event_id"]),
            )
            == (target["drawing_id"], target["event_order"], target["target_event_id"]),
            "review source event binding",
        )
        _check(
            source["orientation"] == "same"
            and source["status_eligible"] is True
            and source["source_status"] in ("scheduled", "not_started"),
            "source orientation/status",
        )
        _check(
            _time(source["captured_at"]) <= _time(target["as_of"]),
            "late schedule source",
        )
        _check(
            _time(source["starts_at"]) == _time(target["kickoff"]),
            "source kickoff binding",
        )
        provider = source["source_provider"]
        if provider == "goal-api-v1":
            _check(
                (
                    source["source_event_id"],
                    source["source_home_team_id"],
                    source["source_away_team_id"],
                )
                == (
                    target["provider_fixture_id"],
                    target["home_team_id"],
                    target["away_team_id"],
                ),
                "provider fixture/team binding",
            )
        else:
            _check(
                provider in ("sofascore-v1", "thesportsdb-v1"),
                "unsupported independent provider",
            )
        providers.add(provider)
        bound.append(
            {
                "path": blob.path,
                "sha256": _sha(blob.content),
                "provider": provider,
                "captured_at": source["captured_at"],
            }
        )
    _check(
        "goal-api-v1" in providers and len(providers) >= 2,
        "independent provider required; GOAL is not independent of itself",
    )
    return {
        "status": "HASH_LINKED_SUPPORTING_EVIDENCE",
        "review_sha256": expected_review_sha256,
        "sources": bound,
        "reviewed_references": [],
        "training_authorized": False,
    }


def _relative_path(path, review_root):
    _check(isinstance(review_root, (str, Path)), "one explicit review root required")
    root = Path(review_root)
    _check(root.is_absolute() and root.is_dir(), "absolute review root required")
    _check(root == root.resolve(), "symlink/ambiguous review root")
    raw = str(path)
    parts = raw[1:].split("/") if raw.startswith("/") else raw.split("/")
    _check(
        "\\" not in raw
        and "\x00" not in raw
        and all(p not in ("", ".", "..") for p in parts),
        "unsafe evidence path",
    )
    physical = Path(raw) if Path(raw).is_absolute() else root / raw
    _check(physical.is_relative_to(root), "evidence path escapes review root")
    for part in (physical, *physical.parents):
        _check(not part.is_symlink(), "symlink evidence path")
        if part == root:
            break
    _check(physical.resolve().is_relative_to(root), "resolved evidence path escape")
    relative = physical.relative_to(root).as_posix()
    _check(relative not in ("", "."), "evidence cannot be review root")
    return relative, physical


def relative_evidence_bundle(event, histories, reviewed_refs, *, review_root):
    """Relocate existing byte-bound review references; never mint authority.

    Exactly one canonical physical root defines the logical namespace. Review
    metadata and all bytes stay unchanged; hashes are checked before relocation.
    New projection bytes may be in-memory, existing files must match exactly.
    """
    blobs = [event, *(b for side in ("home", "away") for b in histories[side])]
    converted, physical_paths = {}, {}
    for blob in blobs:
        logical, physical = _relative_path(blob.path, review_root)
        _check(logical not in converted, "ambiguous/duplicate evidence path")
        if physical.exists():
            _check(
                physical.is_file() and physical.read_bytes() == blob.content,
                "physical evidence bytes mismatch",
            )
        else:
            _check(blob is event, "missing physical history")
        converted[logical] = EvidenceBytes(logical, blob.content)
        physical_paths[blob.path] = logical
    refs = []
    for ref in reviewed_refs:
        logical, _ = _relative_path(ref.path, review_root)
        _check(logical in converted, "review reference outside evidence bundle")
        _check(
            _sha(converted[logical].content) == ref.sha256,
            "reviewed bytes hash mismatch",
        )
        _check(not any(r.path == logical for r in refs), "ambiguous review references")
        refs.append(replace(ref, path=logical))
    return (
        converted[physical_paths[event.path]],
        {
            side: [converted[physical_paths[b.path]] for b in histories[side]]
            for side in ("home", "away")
        },
        tuple(refs),
    )


def prepare_bridge(
    *,
    plan_path,
    final_input_path,
    expected_final_input_sha256,
    projection,
    projection_path,
    histories,
    schedule_sources,
    derived_at,
    reviewed_refs=(),
    review_root=None,
):
    """Build one deterministic research derivation using native immutable inputs.

    schedule_sources are explicit EvidenceBytes with original review-relative
    paths. No discovery, network, DB, inference, training or implicit review.
    reviewed_refs may ONLY be provided by a separately authorized reviewer.
    """
    plan = load_scheduler_plan(Path(plan_path))
    snapshot = load_final_input(Path(final_input_path), expected_plan=plan)
    _check(
        snapshot.snapshot_sha256 == expected_final_input_sha256,
        "expected final input hash binding",
    )
    parsed = parse_target_drawing(snapshot.payload, snapshot.captured_at)
    order = projection["event_order"]
    _check(type(order) is int and 0 <= order < 15, "event order")
    event = parsed.events[order]
    target = bind_projection(
        projection,
        snapshot=snapshot,
        event_id=event.event_id,
        plan_sha256=_sha(Path(plan_path).read_bytes()),
    )
    _check(_time(derived_at) >= snapshot.captured_at, "backdated derivation")
    raw_plan = json.loads(Path(plan_path).read_bytes())
    cfg = raw_plan["config"]
    ledger = load_bound_schedule_evidence_ledger(
        Path(raw_plan["paths"]["schedule_evidence_ledger"]),
        expected_content_sha256=cfg["schedule_evidence_ledger_sha256"],
        expected_semantic_hash=cfg["schedule_evidence_semantic_hash"],
    )
    resolution = resolve_schedule_evidence(
        event, ledger, evaluated_at=snapshot.captured_at
    )
    _check(
        resolution.state == "RESOLVED" and resolution.orientation == "same",
        "native schedule resolution: " + resolution.state,
    )
    observation = resolution.observation
    _check(observation.reviewed_at <= snapshot.captured_at, "post-asof review")
    review = EvidenceBytes(
        str(observation.review_document), observation.review_document.read_bytes()
    )
    linked = link_schedule_evidence(
        target,
        review=review,
        expected_review_sha256=observation.review_document_sha256,
        sources=schedule_sources,
    )
    _check(set(histories) == {"home", "away"}, "two history sides required")
    raw_checks = []
    for side, blobs in histories.items():
        _check(0 < len(blobs) <= 4, "history capture count")
        raw_checks.extend(history_readiness(b, target=target, side=side) for b in blobs)
    content = json.dumps(
        target,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    projection_blob = EvidenceBytes(str(projection_path), content)
    projection_blob, histories, reviewed_refs = relative_evidence_bundle(
        projection_blob, histories, reviewed_refs, review_root=review_root
    )
    row, native_error = None, None
    try:
        row = build_v3_predictors(
            event=projection_blob,
            verified_event_local_histories=histories,
            reviewed_refs=reviewed_refs,
            drawing_number=plan.drawing,
            bk_probabilities=event.bk_probabilities,
            deadline=plan.operational_cutoff.isoformat(),
        )
        validate_feature_row(row)
    except ValueError as error:
        row = None
        native_error = str(error)
    pending = []
    entries = [(projection_blob, "target_projection", None)]
    entries += [
        (b, "raw_goal_team_results_response", side)
        for side, blobs in histories.items()
        for b in blobs
    ]
    for b, kind, side in entries:
        pending.append(
            {
                "path": b.path,
                "sha256": _sha(b.content),
                "kind": kind,
                "provider": "goal-api-v1",
                "drawing_id": target["drawing_id"],
                "event_order": order,
                "target_event_id": target["target_event_id"],
                "side": side,
            }
        )
    manifest = seal(
        {
            "kind": "SPORTS_V3_DATASET_BRIDGE_RESEARCH",
            "derived_at": derived_at,
            "source_as_of": target["as_of"],
            "drawing_number": plan.drawing,
            "event_order": order,
            "final_input_sha256": snapshot.snapshot_sha256,
            "scheduler_plan_sha256": target["scheduler_plan_sha256"],
            "projection_sha256": _sha(content),
            "projection_path": projection_blob.path,
            "review_root": str(Path(review_root)),
            "schedule_evidence": linked,
            "pending_reference_bindings_NOT_REVIEW_AUTHORITY": pending,
            "history_readiness": raw_checks,
            "native_predictor_error": native_error,
            "native_feature_sha256": None if row is None else row["sha256"],
            "fit_executed": False,
            "training_authorized": False,
            "automatic_wagering": False,
            "missing_policy": "NO_SCOPE_INHERITANCE_NO_AUTOMATIC_REVIEW_RECEIPT",
        }
    )
    return projection_blob, manifest, row


def derive_native_history_envelope(
    blob, *, source_reference, target, side, review_root, derived_path, derived_at
):
    """Lossless representation adapter for the audited HTTP-200 archive schema.

    This is NOT a new provider capture or an independent review. The returned
    sidecar records original bytes, canonical payload (not HTTP wire-body),
    original capture time and today's derivation time. Original files stay intact.
    A caller/reviewer must bind the new bytes before using them as reviewed input.
    """
    from toto_ai.sports_stats.v3_family_evidence import (
        _hash as native_hash,
    )
    from toto_ai.sports_stats.v3_family_evidence import (
        _read as native_read,
    )
    from toto_ai.sports_stats.v3_family_evidence import (
        _source as native_source,
    )

    logical, physical = _relative_path(blob.path, review_root)
    reference_logical, _ = _relative_path(source_reference.path, review_root)
    destination, destination_file = _relative_path(derived_path, review_root)
    _check(destination != logical, "derived envelope must not replace source")
    _check(logical == reference_logical, "source reference path binding")
    _check(
        physical.is_file() and physical.read_bytes() == blob.content,
        "physical source bytes mismatch",
    )
    document = native_read(
        EvidenceBytes(logical, blob.content),
        [replace(source_reference, path=logical)],
        "raw_goal_team_results_response",
        event=target,
        side=side,
    )
    _check(
        set(document)
        == {
            "schema_version",
            "provider",
            "endpoint",
            "params",
            "http_status",
            "fetched_at",
            "payload",
        },
        "unsupported original envelope fields",
    )
    _check(
        type(document["http_status"]) is int and document["http_status"] == 200,
        "successful original HTTP capture required",
    )
    _check(document["params"] == {"limit": 10}, "original limit contract")
    _check(
        _time(derived_at) >= _time(document["fetched_at"]),
        "backdated envelope derivation",
    )
    history_readiness(blob, target=target, side=side)
    params = [["limit", "10"]]
    request = {
        "provider": document["provider"],
        "base_url": "https://api.goal-api.com/v1",
        "endpoint": document["endpoint"],
        "params": params,
    }
    derived = {
        "schema_version": document["schema_version"],
        "provider": document["provider"],
        "endpoint": document["endpoint"],
        "params": params,
        "request_fingerprint": native_hash(request, ensure_ascii=True),
        "fetched_at": document["fetched_at"],
        "response_hash": native_hash(document["payload"], ensure_ascii=True),
        "payload": copy.deepcopy(document["payload"]),
    }
    # Verify the entire native source contract, not one field per iteration.
    native_source(derived, target, side, {})
    content = json.dumps(
        derived,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    if destination_file.exists():
        _check(
            destination_file.is_file() and destination_file.read_bytes() == content,
            "immutable derived path conflict",
        )
    chain = seal(
        {
            "artifact_class": "DERIVED_ENVELOPE_NOT_ORIGINAL_CAPTURE",
            "adapter_version": "sports-v3-native-envelope-representation-v1",
            "derived_at": derived_at,
            "original_path": logical,
            "original_file_sha256": _sha(blob.content),
            "original_reference": {
                "path": reference_logical,
                "sha256": source_reference.sha256,
                "kind": source_reference.kind,
                "drawing_id": source_reference.drawing_id,
                "event_order": source_reference.event_order,
                "target_event_id": source_reference.target_event_id,
                "side": source_reference.side,
                "provider": source_reference.provider,
            },
            "source_http_status": document["http_status"],
            "original_http_body_sha256": None,
            "original_http_body_availability": "NOT_PRESERVED_IN_ARCHIVE_WRAPPER",
            "source_payload_canonical_sha256": derived["response_hash"],
            "source_observed_at": None,
            "source_captured_at": document["fetched_at"],
            "observation_basis": "ORIGINAL_FETCHED_AT_ONLY_NO_NEW_SOURCE_OBSERVATION",
            "request_fingerprint_basis": "RECONSTRUCTED_NATIVE_CANONICAL_REQUEST",
            "payload_unchanged": derived["payload"] == document["payload"],
            "derived_path": destination,
            "derived_file_sha256": _sha(content),
            "review_authority_issued": False,
            "fit_executed": False,
            "automatic_wagering": False,
        }
    )
    return EvidenceBytes(destination, content), chain
