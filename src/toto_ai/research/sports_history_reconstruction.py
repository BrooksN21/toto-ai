"""Inactive retrospective numerical pilot, never a fit/availability authority.

No network, SQLite, scheduler, labels, class approval or operator integration.
Late source versions are usable ONLY as an explicitly unverified sensitivity
calculation. Native production evidence and dataset gates remain untouched.
"""

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from toto_ai.sports_stats.v3_features import build_sports_v3_feature_table
from toto_ai.sports_stats.v3_probability_features import TERMINAL, regulation_score


def _time(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("aware timestamp required")
    return result


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def completion_evidence(raw, *, observed_at, cutoff):
    """An actual finish claim or archived terminal observation, never duration math.

    updatedAt alone is not completion/publication evidence. Missing completion in
    a late terminal snapshot stays unsupported (also for old kickoffs), rather
    than assigning a fabricated end time or feeding its final score to features.
    A late capture with an explicit prior finishedAt remains reconstructible.
    """
    observed = _time(observed_at)
    kickoff = _time(raw["kickoffUtc"])
    finish = raw.get("finishedAt")
    evidence = dict(
        finished_at=finish,
        completed_by=None,
        observed_at=observed_at,
        updated_at=raw.get("updatedAt"),
        completion_before_cutoff=False,
    )
    if raw.get("matchStatus") not in TERMINAL:
        return False, {**evidence, "reason": "NON_TERMINAL"}
    if finish is not None:
        try:
            end = _time(finish)
        except (ValueError, TypeError, AttributeError):
            return False, {**evidence, "reason": "INVALID_COMPLETION_TIMESTAMP"}
        if end >= cutoff:
            return False, {**evidence, "reason": "COMPLETED_AT_OR_AFTER_CUTOFF"}
        if end < kickoff or end > observed:
            return False, {**evidence, "reason": "CONTRADICTORY_COMPLETION_TIMESTAMP"}
        return True, {
            **evidence,
            "completed_by": finish,
            "completion_before_cutoff": True,
            "reason": "SOURCE_EXPLICIT_FINISH_BEFORE_CUTOFF",
        }
    if kickoff <= observed < cutoff:
        update = raw.get("updatedAt")
        if update and _time(update) > observed:
            return False, {**evidence, "reason": "SOURCE_VERSION_AFTER_OBSERVATION"}
        return True, {
            **evidence,
            "completed_by": observed_at,
            "completion_before_cutoff": True,
            "reason": "TERMINAL_OBSERVED_BEFORE_CUTOFF",
        }
    return False, {**evidence, "reason": "COMPLETION_BEFORE_CUTOFF_UNPROVEN"}


def reconstruct(*, target, sources, derived_at):
    """Sources carry original bytes, their expected SHA256 and provenance path.

    `close_moscow_wall` explicitly represents TotoBrief's Moscow wall clock,
    including its misleading legacy Z suffix; never pass a generic UTC cutoff.
    Derived T-10 is a research policy choice, not an archived operator timestamp.
    """
    now = _time(derived_at)
    kickoff = _time(target["kickoff"])
    wall = target["close_moscow_wall"]
    if not wall.endswith("Z"):
        raise ValueError("explicit legacy Moscow-wall Z field required")
    close = (
        datetime.fromisoformat(wall[:-1])
        .replace(tzinfo=ZoneInfo("Europe/Moscow"))
        .astimezone(timezone.utc)
    )
    cutoff = close - timedelta(minutes=10)
    if cutoff >= kickoff:
        raise ValueError("decision cutoff must precede target kickoff")
    teams = (target["home_team_id"], target["away_team_id"])
    if not all(isinstance(t, str) and t for t in teams) or teams[0] == teams[1]:
        raise ValueError("target team binding")
    histories = {}
    provenance = []
    excluded = []
    target_seen = False
    received = 0
    for source in sources:
        content = source["content"]
        digest = hashlib.sha256(content).hexdigest()
        if digest != source["sha256"]:
            raise ValueError("source hash mismatch")
        doc = json.loads(content)
        if doc.get("provider") != "goal-api-v1":
            raise ValueError("provider mismatch")
        if "http_status" in doc and doc["http_status"] != 200:
            raise ValueError("non-success source")
        observed = _time(doc["fetched_at"])
        if observed > now:
            raise ValueError("derived before source")
        payload = doc["payload"]
        team = payload["teamId"]
        if team not in teams or doc["endpoint"] != f"/teams/{team}/results":
            raise ValueError("source team binding")
        rows = payload["data"]
        if not isinstance(rows, list):
            raise ValueError("history rows must be a list")
        src = dict(
            path=source["path"],
            sha256=digest,
            fetched_at=doc["fetched_at"],
            team_id=team,
            http_status=doc.get("http_status"),
            row_count=len(rows),
        )
        provenance.append(src)
        for raw in rows:
            received += 1
            event_id = raw["id"]
            row_teams = (raw["homeTeamId"], raw["awayTeamId"])
            event_time = _time(raw["kickoffUtc"])
            identity = dict(
                event_id=event_id,
                kickoff=raw["kickoffUtc"],
                home_team_id=row_teams[0],
                away_team_id=row_teams[1],
            )
            if event_id == target["fixture_id"]:
                if row_teams != teams or event_time != kickoff:
                    raise ValueError("target identity mismatch")
                target_seen = True
                excluded.append(
                    {**identity, "source_sha256": digest, "reason": "TARGET"}
                )
                continue
            if team not in row_teams:
                raise ValueError("history row team binding")
            if row_teams == teams and event_time == kickoff:
                raise ValueError("target identity alias collision")
            if event_time >= cutoff:
                excluded.append(
                    {
                        **identity,
                        "source_sha256": digest,
                        "reason": "AT_OR_AFTER_DECISION_CUTOFF",
                    }
                )
                continue
            if raw.get("matchStatus") not in TERMINAL:
                excluded.append(
                    {**identity, "source_sha256": digest, "reason": "NON_TERMINAL"}
                )
                continue
            completed, completion = completion_evidence(
                raw, observed_at=doc["fetched_at"], cutoff=cutoff
            )
            if not completed:
                excluded.append(
                    {
                        **identity,
                        "source_sha256": digest,
                        "reason": completion["reason"],
                        "completion": completion,
                    }
                )
                continue
            try:
                home, away = regulation_score(raw)
            except (ValueError, TypeError):
                excluded.append(
                    {
                        **identity,
                        "source_sha256": digest,
                        "reason": "REGULATION_SCORE_MISSING",
                    }
                )
                continue
            normalized = dict(
                event_id=event_id,
                home_team_id=row_teams[0],
                away_team_id=row_teams[1],
                kickoff=event_time,
                home_goals=home,
                away_goals=away,
                status=TERMINAL[raw["matchStatus"]],
            )
            update = raw.get("updatedAt")
            evidence = dict(
                source_sha256=digest,
                observed_at=doc["fetched_at"],
                updated_at=update,
                source_path=source["path"],
                version_after_cutoff=(_time(update) > cutoff if update else None),
                completion=completion,
            )
            if event_id in histories:
                if histories[event_id]["normalized"] != normalized:
                    raise ValueError("conflicting historical revisions")
                histories[event_id]["evidence"].append(evidence)
            else:
                histories[event_id] = dict(
                    normalized=normalized,
                    evidence=[evidence],
                    information_available_at=None,
                    finished_at=completion["finished_at"],
                    scope=dict(gender=None, age_group=None, squad_type=None),
                    causal_fit_eligible=False,
                )
    if not target_seen:
        raise ValueError("target absent from hash-bound histories")
    native = build_sports_v3_feature_table(
        target_events=[
            dict(
                event_id=target["fixture_id"],
                event_order=target["event_order"],
                home_team_id=teams[0],
                away_team_id=teams[1],
                kickoff=kickoff,
            )
        ],
        completed_matches=[r["normalized"] for r in histories.values()],
        rolling_window=10,
        minimum_prior_matches=5,
    )
    row = native.rows[0]
    history = []
    for key in sorted(histories):
        item = histories[key]
        item["normalized"]["kickoff"] = item["normalized"]["kickoff"].isoformat()
        history.append(item)
    return dict(
        schema_version="sports-retrospective-pilot-v2-completion-bound",
        derived_at=derived_at,
        domain="HISTORICAL_RECONSTRUCTION_SENSITIVITY_UNVERIFIED_ASOF",
        target=target,
        decision_cutoff=cutoff.isoformat(),
        decision_provenance="RECONSTRUCTED_T_MINUS_10_NOT_ARCHIVED_DECISION",
        input_sha256=_hash(
            dict(
                target=target,
                sources=provenance,
                rolling_window=10,
                minimum_prior_matches=5,
            )
        ),
        sources=provenance,
        history=history,
        exclusions=excluded,
        features=row.features,
        missing_features=row.missing_features,
        missing_reasons=row.missing_reasons,
        feature_semantic_hash=native.semantic_hash,
        counts=dict(
            received=received,
            excluded=len(excluded),
            retained_unique=len(history),
            numeric_features=sum(v is not None for v in row.features.values()),
            feature_slots=len(row.features),
            historical_availability_proven=0,
            class_proven=0,
            completion_before_cutoff_evidenced=len(history),
        ),
        numerical_extraction_complete=True,
        fit_eligible=False,
        operator_compatible=False,
        automatic_wagering=False,
        native_dataset_validation="NOT_RUN_UNREVIEWED_RECONSTRUCTION_DOMAIN",
        reasons=[
            "HISTORICAL_AVAILABILITY_UNKNOWN",
            "TEAM_CLASS_UNPROVEN",
            "INCOMPLETE_OPPONENT_HISTORY",
            "LAST10_WINDOW_NOT_FULL_SEASON",
            "NOT_A_REVIEWED_F4_DATASET",
        ],
    )


def _inside(root, path):
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise ValueError("path outside root")
    return result


def _read_json_bytes(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("input exceeds evidence size cap")
    return path.read_bytes()


def validate_target_metadata(manifest, *, root):
    """Require named original target metadata plus pinned research fixture mapping.

    Mapping provenance is not class/reviewer authority. Its exact target/source
    linkage must match; no inference from translated display names occurs here.
    """

    def bound_json(ref, label):
        if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
            raise ValueError(f"missing {label}")
        data = _read_json_bytes(_inside(root, ref["path"]))
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError(f"{label} hash mismatch")
        return json.loads(data)

    ref = manifest.get("target_metadata_source")
    rows = bound_json(ref, "target metadata source")
    target = manifest["target"]
    if not isinstance(rows, list):
        raise ValueError("target metadata rows required")
    local_id = ref.get("local_event_id")
    if type(local_id) is not int:
        raise ValueError("target metadata binding requires integer local event ID")
    matches = [r for r in rows if r.get("target_event_id") == local_id]
    if len(matches) != 1:
        raise ValueError("target metadata binding is missing or ambiguous")
    row = matches[0]
    if (
        type(target.get("drawing")) is not int
        or type(target.get("event_order")) is not int
        or row.get("drawing_number") != target["drawing"]
        or row.get("event_order") != target["event_order"]
        or row.get("ended_at") != target["close_moscow_wall"]
    ):
        raise ValueError("target metadata binding mismatch")
    mapping_ref = manifest.get("fixture_mapping_source")
    mapping = bound_json(mapping_ref, "fixture mapping")
    if (
        mapping.get("target") != target
        or mapping.get("local_event_id") != local_id
        or mapping.get("target_metadata_sha256") != ref["sha256"]
    ):
        raise ValueError("fixture mapping binding mismatch")
    return dict(
        target_metadata_sha256=ref["sha256"],
        local_event_id=local_id,
        fixture_mapping_sha256=mapping_ref["sha256"],
        mapping_evidence_grade=mapping.get("evidence_grade", "UNREVIEWED"),
        class_approval=False,
    )


def run_manifest(manifest_path, *, root):
    """Read only named, hash-bound sources; never fetch or alter original bytes."""
    root = Path(root).resolve()
    manifest_path = _inside(root, manifest_path)
    raw_manifest = _read_json_bytes(manifest_path)
    manifest = json.loads(raw_manifest)
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if manifest.get("code_sha256", code_hash) != code_hash:
        raise ValueError("adapter code hash mismatch")
    target_binding = validate_target_metadata(manifest, root=root)
    sources = []
    for ref in manifest["sources"]:
        path = _inside(root, ref["path"])
        sources.append(
            dict(content=_read_json_bytes(path), path=str(path), sha256=ref["sha256"])
        )
    result = reconstruct(
        target=manifest["target"],
        sources=sources,
        derived_at=datetime.now(timezone.utc).isoformat(),
    )
    result["manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()
    result["adapter_code_sha256"] = code_hash
    result["target_binding"] = target_binding
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    research_root = (root / "reports/rehearsal").resolve()
    output = _inside(root, args.output)
    if not output.is_relative_to(research_root):
        raise ValueError("output must be an isolated research artifact")
    if output.exists():
        raise ValueError("output exists; use a new derived artifact path")
    result = run_manifest(args.manifest, root=root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                output=str(output),
                counts=result["counts"],
                fit_eligible=result["fit_eligible"],
            )
        )
    )


if __name__ == "__main__":
    main()
