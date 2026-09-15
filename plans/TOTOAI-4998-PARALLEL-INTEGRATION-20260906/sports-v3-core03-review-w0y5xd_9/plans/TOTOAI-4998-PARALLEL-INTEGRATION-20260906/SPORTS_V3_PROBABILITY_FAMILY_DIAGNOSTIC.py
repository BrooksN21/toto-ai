"""Read-only named six-draw evidence; no DB, API, package or 4998 outcome input."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from toto_ai.external_odds.targets import parse_target_drawing
from toto_ai.sports_stats.v3_feature_disposition import feature_disposition
from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table
from toto_ai.sports_stats.v3_probability import FEATURE_NAMES, _time, seal
from toto_ai.sports_stats.v3_probability_features import (
    _history,
    _merge,
    augment_observed_features,
)

ROOT = Path("/Users/turshevr/toto-ai")
PLAN = ROOT / "plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906"
reads = {}


def read(path, expected=None):
    path = Path(path)
    path = path if path.is_absolute() else ROOT / path
    assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    assert expected is None or actual == expected, str(path)
    reads[str(path)] = actual
    return data


manifest = json.loads(
    read(
        ROOT
        / "plans/TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904"
        / "backfill-4990-4995-manifest.json",
        "07463e8831c8e1cbcd146b9243555c2efce72a160b4c527c3243573ade270e49",
    )
)
handoff = read(PLAN / "SPORTS_V3_LABEL_EVIDENCE_HANDOFF.md").decode()
labels = json.loads(handoff.split("```json\n", 1)[1].split("\n```", 1)[0])
labels = {r["drawing_number"]: r for r in labels}
summaries, dispositions = [], []
source_valid_missing, all_missing = Counter(), Counter()
for fold in manifest["snapshots"]:
    draw = fold["drawing_number"]
    assert draw in range(4990, 4996)
    evidence = labels[draw]
    state = json.loads(
        read(evidence["post_draw_state_path"], evidence["post_draw_state_file_sha256"])
    )
    review = json.loads(
        read(evidence["review_request_path"], evidence["review_request_file_sha256"])
    )
    attribution = json.loads(
        read(evidence["attribution_path"], evidence["attribution_file_sha256"])
    )
    assert (
        state["drawing_id"]
        == review["drawing_id"]
        == evidence["drawing_id"]
        == fold["drawing_id"]
    )
    assert (
        state["result_snapshot_sha256"]
        == review["snapshot_sha256"]
        == evidence["snapshot_sha256"]
    )
    assert (
        state["updated_at"]
        == review["requested_at"]
        == evidence["results_available_at"]
    )
    assert review["actual"] == evidence["actual"] and len(review["actual"]) == 15
    final = json.loads(
        read(fold["target_detail"]["path"], fold["target_detail"]["sha256"])
    )
    assert final["drawing_id"] == fold["drawing_id"] and final["drawing_number"] == draw
    target = parse_target_drawing(final["payload"], _time(final["captured_at"]))
    raw_events = sorted(final["payload"]["data"]["events"], key=lambda r: r["order"])
    reasons = Counter()
    raw_count = accepted_count = source_complete = 0
    fold_dispositions = []
    for event in fold["events"]:
        order = event["event_order"]
        assert str(raw_events[order]["id"]) == event["target_event_id"]
        actual = review["actual"][order]
        assert attribution["events"][order]["actual_outcome"] == actual
        row_reasons = []
        rejected = False
        if _time(final["deadline"]) != _time(fold["deadline"]):
            rejected = True
            row_reasons.append("FINAL_DEADLINE_MISMATCH")
        if _time(fold["as_of"]) > _time(final["captured_at"]):
            rejected = True
            row_reasons.append("ASOF_AFTER_FINAL_INPUT")
        matches = {"home": [], "away": []}
        sources = []
        projection = {
            "as_of": fold["as_of"],
            "kickoff": event["target_starts_at"],
            "provider_fixture_id": event["provider_fixture_id"],
            "home_team_id": event["provider_home_team_id"],
            "away_team_id": event["provider_away_team_id"],
        }
        for side in ("home", "away"):
            reference = event["sources"][side]
            if reference["status"] != "available":
                row_reasons.append(side.upper() + "_HISTORY_MISSING")
                continue
            document = json.loads(read(reference["path"], reference["sha256"]))
            sources.append(reference["sha256"])
            raw_count += len(document["payload"]["data"])
            if rejected:
                continue
            try:
                parsed, excluded = _history(
                    document,
                    team=event["provider_" + side + "_team_id"],
                    target=projection,
                )
                matches[side] = parsed
                accepted_count += len(parsed)
                row_reasons.extend(excluded)
            except (ValueError, TypeError, KeyError) as error:
                rejected = True
                row_reasons.append("SOURCE_REJECTED:" + str(error))
        values = dict.fromkeys(FEATURE_NAMES)
        if not rejected and event["provider_fixture_id"] is not None:
            table = build_sports_v3_feature_table(
                target_events=[
                    {
                        "event_id": event["provider_fixture_id"],
                        "event_order": order,
                        "home_team_id": event["provider_home_team_id"],
                        "away_team_id": event["provider_away_team_id"],
                        "kickoff": _time(event["target_starts_at"]),
                    }
                ],
                completed_matches=_merge([*matches["home"], *matches["away"]]),
                rolling_window=10,
                minimum_prior_matches=3,
            )
            values.update(table.rows[0].features)
            augment_observed_features(values, matches, projection, 3)
            source_complete += int(bool(matches["home"]) and bool(matches["away"]))
        # The accepted manifest is byte authority, NOT independently reviewed scope.
        # No ReviewedReference/scope declaration is manufactured from raw identity.
        # Supplied chain has no independent reviewed entity-scope authority.
        # Do not create a reviewed reference or treat this as a family rejection.
        assert not event.get("identity_scope") and not event.get(
            "reviewed_scope_reference"
        )
        values["bk_entropy"] = -math.fsum(
            p * math.log(p) for p in target.events[order].bk_probabilities
        )
        reasons.update(set(row_reasons))
        row = seal(
            {
                "kind": "SPORTS_V3_PREDICTORS",
                "schema_version": 1,
                "drawing_number": draw,
                "drawing_id": fold["drawing_id"],
                "event_order": order,
                "event_id": event["target_event_id"],
                "provider_fixture_id": event["provider_fixture_id"],
                "home_team_id": event["provider_home_team_id"],
                "away_team_id": event["provider_away_team_id"],
                "as_of": fold["as_of"],
                "bk_captured_at": final["captured_at"],
                "kickoff": event["target_starts_at"],
                "bk_input_sha256": fold["target_detail"]["sha256"],
                "bk_probabilities": list(target.events[order].bk_probabilities),
                "bk_margin": None,
                "features": values,
                "prior_counts": [min(len(matches[s]), 10) for s in ("home", "away")],
                "exact_target": event["provider_fixture_id"] is not None,
                "scope_verified": False,
                "source_rejected": rejected,
                "source_hashes": sources,
                "missing_reasons": sorted(set(row_reasons)),
            }
        )
        diagnostic = feature_disposition(row)
        fold_dispositions.append(diagnostic)
        missing = [n for n, value in values.items() if value is None]
        all_missing.update(missing)
        if diagnostic["common_source_valid"]:
            source_valid_missing.update(missing)
        dispositions.append(
            {
                "drawing_number": draw,
                "event_order": order,
                "event_id": row["event_id"],
                **{
                    k: diagnostic[k]
                    for k in (
                        "common_source_valid",
                        "common_rejection_reasons",
                        "core_numeric_complete",
                        "core_source_computable",
                        "core_missing",
                        "common_entity_scope_proof",
                    )
                },
                "raw_scope_observed_counts": {
                    key: sum(
                        m["scope"].get(key) is not None
                        for side in matches.values()
                        for m in side
                    )
                    for key in ("gender", "age_group", "squad_type")
                },
                "family_counts": {
                    family: {
                        "observed": len(fields["observed"]),
                        "missing": len(fields["missing"]),
                    }
                    for family, fields in diagnostic["families"].items()
                },
            }
        )
    summaries.append(
        {
            "drawing_number": draw,
            "label_rows": 15,
            "source_complete_rows": source_complete,
            "raw_history_rows": raw_count,
            "accepted_regulation90_rows": accepted_count,
            "core_source_computable_rows": sum(
                d["core_source_computable"] for d in fold_dispositions
            ),
            "A2_A3_input_contract_rows": sum(
                d["A2_A3"]["input_contract_satisfied"] for d in fold_dispositions
            ),
            "A4_A5_input_contract_rows": sum(
                d["A4_A5"]["input_contract_satisfied"] for d in fold_dispositions
            ),
            "reason_counts": dict(sorted(reasons.items())),
        }
    )
    print("verified drawing", draw, summaries[-1], flush=True)
result = {
    "status": "PER_FAMILY_DIAGNOSTIC_ONLY_NO_FIT",
    "label_rows_bound_and_available": 90,
    "training_drawings_available": 6,
    "source_valid_both_history_rows": sum(
        d["common_source_valid"] for d in dispositions
    ),
    "core_source_computable_rows": sum(
        d["core_source_computable"] for d in dispositions
    ),
    "A2_A3_input_contract_rows": sum(f["A2_A3_input_contract_rows"] for f in summaries),
    "A4_A5_input_contract_rows": sum(f["A4_A5_input_contract_rows"] for f in summaries),
    "proof_gap": (
        "No independent reviewed common entity-scope authority supplied. "
        "No synthetic ReviewedReferences or fit. "
        "Missing league/season affects standings only."
    ),
    "folds": summaries,
    "missing_feature_counts_all_90": dict(sorted(all_missing.items())),
    "missing_feature_counts_source_valid_52": dict(
        sorted(source_valid_missing.items())
    ),
    "rows": dispositions,
    "source_file_hashes": reads,
    "training_authorized": False,
    "operator_compatible": False,
    "automatic_wagering": False,
    "activation_allowed": False,
}
print("RESULT_JSON=" + json.dumps(result, sort_keys=True))
