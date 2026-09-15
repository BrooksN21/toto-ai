"""Read-only delivery observations, never a release or a delivery acknowledgement."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.runner.final_input import load_final_input
from toto_ai.runner.scheduler import SchedulerPlan


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("publication timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("publication timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def timestamp_actionable(
    record: Mapping[str, object] | None, plan: SchedulerPlan, now: datetime
) -> bool:
    """A stored boolean can never extend the plan's release window."""
    if (
        record is None
        or record.get("decision") != "PLAY"
        or record.get("actionable") is not True
    ):
        return False
    try:
        expiry = plan.deadlines["t_minus_10"]
        published = _time(record.get("published_at", record.get("completed_at")))
        if "expires_at" in record and _time(record["expires_at"]) != expiry:
            return False
        if "completed_at" in record and _time(record["completed_at"]) > now:
            return False
        return published <= now < expiry and published < expiry
    except (TypeError, ValueError, OverflowError):
        return False


def _regular(path: Path, root: Path) -> Path:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or not path.is_relative_to(root)
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("delivery path outside bound output")
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError("delivery symlink forbidden")
    if not path.is_file():
        raise ValueError("delivery file missing")
    return path


def _sealed(path: Path, root: Path, key: str = "record_sha256") -> tuple[dict, str]:
    content = _regular(path, root).read_bytes()
    record = json.loads(content)
    if not isinstance(record, dict):
        raise ValueError("delivery record is not an object")
    if record.get(key) != _hash({k: v for k, v in record.items() if k != key}):
        raise ValueError("delivery record hash mismatch")
    return record, hashlib.sha256(content).hexdigest()


def _identity(record: dict, plan: SchedulerPlan) -> None:
    if (
        record.get("plan_id") != plan.plan_id
        or record.get("drawing", record.get("drawing_number")) != plan.drawing
        or ("drawing_id" in record and record["drawing_id"] != plan.drawing_id)
    ):
        raise ValueError("delivery record plan/drawing mismatch")


def _record(path: Path, root: Path, plan: SchedulerPlan) -> tuple[dict, str]:
    record, digest = _sealed(path, root)
    _identity(record, plan)
    return record, digest


def _input_binding(primary: dict, plan: SchedulerPlan, now: datetime):
    """Read the native archive/input chain; no DB, capture or calculation."""
    root = plan.output_dir.resolve()
    run_id = primary.get("run_id")
    _run_dir(root, run_id)  # validate a single run component before joining
    run = root / "attempts" / run_id
    source = _regular(run / "package.csv", root)
    archive_path = run / "package-archive.json"
    if (
        primary.get("source_package_path") != str(source)
        or primary.get("source_package_sha256")
        != hashlib.sha256(source.read_bytes()).hexdigest()
        or primary.get("archive_manifest_path") != str(archive_path)
    ):
        raise ValueError("primary source/run binding mismatch")
    archive, _ = _sealed(archive_path, root, "archive_manifest_sha256")
    snapshot = load_final_input(
        _regular(run / "final-input.json", root), expected_plan=plan
    )
    if (
        archive["archive_manifest_sha256"] != primary.get("archive_manifest_sha256")
        or archive.get("source_bytes_sha256") != primary["source_package_sha256"]
        or archive.get("source_path") != str(source)
        or archive.get("drawing_number") != plan.drawing
        or archive.get("drawing_id") != plan.drawing_id
        or archive.get("final_input_sha256") != snapshot.snapshot_sha256
        or archive.get("probability_input_sha256") != snapshot.probability_input_sha256
        or snapshot.attempt_id != run_id
        or snapshot.captured_at
        > min(now, _time(primary.get("published_at", primary.get("completed_at"))))
        or archive.get("stake") != plan.stake
        or archive.get("coupon_count") != primary.get("selected_count")
    ):
        raise ValueError("primary archive/final-input binding mismatch")
    plan_bytes = _regular(root / "scheduler-plan.json", root).read_bytes()
    if json.loads(plan_bytes) != plan.to_payload():
        raise ValueError("scheduler plan file differs from current plan")
    return snapshot, archive, hashlib.sha256(plan_bytes).hexdigest()


def _coupons(path: Path, plan: SchedulerPlan) -> tuple[str, ...]:
    rows = _regular(path, plan.output_dir.resolve()).read_text().splitlines()
    coupons = []
    for row in rows:
        fields = row.split(";")
        if (
            len(fields) != 16
            or fields[0] != str(plan.stake)
            or any(x not in {"1", "X", "2"} for x in fields[1:])
        ):
            raise ValueError("operator package syntax invalid")
        coupons.append("".join(fields[1:]))
    if not coupons:
        raise ValueError("empty operator package")
    return tuple(coupons)


def _ranking_bound(ranking: object, coupons: tuple[str, ...]) -> dict:
    result = _highest(ranking, len(coupons))
    if (
        result is None
        or result.get("coupon") != coupons[result["package_position"] - 1]
    ):
        raise ValueError("ranking coupon/position is not package-bound")
    for key in ("probability_at_least_14", "probability_at_least_15"):
        if key in result and (
            type(result[key]) not in (int, float)
            or not math.isfinite(result[key])
            or not 0 <= result[key] <= 1
        ):
            raise ValueError("ranking probability invalid")
    return result


def _primary_ranking(primary: dict, plan: SchedulerPlan, now: datetime) -> dict:
    root = plan.output_dir.resolve()
    proof, _ = _sealed(
        _run_dir(root, primary["run_id"])
        / "research-comparison/primary-bk-ranking.json",
        root,
    )
    snapshot, archive, plan_hash = _input_binding(primary, plan, now)
    coupons = _coupons(Path(primary["coupon_path"]), plan)
    if (
        proof.get("schema_version") != 1
        or proof.get("artifact_class") != "PRIMARY_CONTROL_RANKING_ANALYSIS_ONLY"
        or proof.get("plan_id") != plan.plan_id
        or any(
            key in proof and proof[key] != value
            for key, value in (
                ("drawing", plan.drawing),
                ("drawing_number", plan.drawing),
                ("drawing_id", plan.drawing_id),
            )
        )
        or proof.get("plan_file_sha256") != plan_hash
        or proof.get("operator_control_verified") is not True
        or proof.get("operator_package_sha256") != primary["package_sha256"]
        or proof.get("final_input_snapshot_sha256") != snapshot.snapshot_sha256
        or proof.get("probability_input_sha256") != snapshot.probability_input_sha256
        or proof.get("package_sha256")
        != hashlib.sha256(",".join(coupons).encode()).hexdigest()
        or proof.get("package_sha256") != archive.get("canonical_package_sha256")
        or len(coupons) != primary.get("selected_count")
        or proof.get("automatic_wagering") is not False
        or proof.get("operator_compatible") is not False
    ):
        raise ValueError("native ranking input/plan/package binding mismatch")
    ranking = _ranking_bound(proof.get("highest_p13_single_coupon"), coupons)
    if ranking["reference_model"] != "bk":
        raise ValueError("primary ranking must use bound BK input")
    return ranking


def _parallel_binding(
    sidecar: dict, release: dict, primary: dict, plan: SchedulerPlan, now: datetime
) -> None:
    root = plan.output_dir.resolve()
    run = _run_dir(root, primary["run_id"])
    control = _regular(run / "operator-bk-package.txt", root)
    control_hash = hashlib.sha256(control.read_bytes()).hexdigest()
    if (
        sidecar.get("operator_package") != str(control)
        or sidecar.get("operator_package_sha256") != control_hash
        or control_hash != primary.get("package_sha256")
        or sidecar.get("baseline_matches_operator") is not True
    ):
        raise ValueError("parallel current primary control hash mismatch")
    snapshot, archive, _ = _input_binding(primary, plan, now)
    report_path = run / "research-comparison/comparison.json"
    report, report_hash = _sealed(report_path, root, "report_sha256")
    _identity(report, plan)
    if (
        sidecar.get("research_report") != str(report_path)
        or sidecar.get("research_report_sha256") != report_hash
        or report.get("final_input_snapshot_sha256") != snapshot.snapshot_sha256
        or report.get("bank") != plan.requested_bank
        or report.get("stake") != plan.stake
        or report.get("baseline", {}).get("package_sha256")
        != archive.get("canonical_package_sha256")
    ):
        raise ValueError("parallel report/final-input binding mismatch")
    reuse = report.get("control_execution", {})
    if reuse.get("mode") == "VERIFIED_PRIMARY_REUSE" and (
        reuse.get("operator_record_sha256") != primary.get("record_sha256")
        or reuse.get("archive_manifest_sha256")
        != primary.get("archive_manifest_sha256")
    ):
        raise ValueError("parallel reused control record mismatch")
    coupons = _coupons(Path(release["selected_package_path"]), plan)
    selection = report.get("experimental_selection", {})
    selected = release.get("selected_strategy_id")
    selected_hash = hashlib.sha256(",".join(coupons).encode()).hexdigest()
    candidates = selection.get("candidates", [])
    candidate = next(
        (
            c
            for c in candidates
            if isinstance(c, dict) and c.get("strategy_id") == selected
        ),
        {},
    )
    ranking = _ranking_bound(release.get("highest_p13_single_coupon"), coupons)
    if (
        selection.get("selected_strategy_id") != selected
        or selection.get("selected_package_sha256") != selected_hash
        or release.get("selected_package_sha256") != selected_hash
        or release.get("selected_coupon_count") != len(coupons)
        or release.get("selected_cost") != len(coupons) * plan.stake
        or candidate.get("eligible") is not True
        or candidate.get("coupon_count") != len(coupons)
        or candidate.get("cost") != len(coupons) * plan.stake
        or selection.get("policy_version") != release.get("selection_policy_version")
        or report.get("highest_p13_single_coupons", {}).get(selected) != ranking
    ):
        raise ValueError("parallel selection/ranking binding mismatch")


def _run_dir(root: Path, run_id: object) -> Path:
    if (
        not isinstance(run_id, str)
        or not run_id
        or Path(run_id).name != run_id
        or run_id in {".", ".."}
    ):
        raise ValueError("canonical sidecar run ID invalid")
    return root / "parallel-challenger" / "output" / f"run-{run_id}"


def _highest(value: object, count: object) -> dict | None:
    if not isinstance(value, Mapping):
        return None
    position = value.get("package_position")
    probability = value.get("probability_at_least_13")
    if (
        type(count) is not int
        or type(position) is not int
        or not 1 <= position <= count
        or type(probability) not in (int, float)
        or not math.isfinite(probability)
        or not 0 <= probability <= 1
        or value.get("criterion") != "maximum_probability_at_least_13"
        or not isinstance(value.get("reference_model"), str)
        or not value["reference_model"]
    ):
        return None
    return dict(value)


def _event(
    kind: str,
    record: dict,
    path: Path,
    file_hash: str,
    plan: SchedulerPlan,
    now: datetime,
) -> dict:
    parallel = kind == "READY_PARALLEL"
    path_key = "selected_package_path" if parallel else "coupon_path"
    hash_key = "selected_package_file_sha256" if parallel else "package_sha256"
    raw_path = record.get(path_key)
    if not isinstance(raw_path, str) or record.get("automatic_wagering") is not False:
        raise ValueError("delivery package/automatic-wagering contract missing")
    package = _regular(Path(raw_path), plan.output_dir.resolve())
    if parallel and package.parent != path.parent:
        raise ValueError("parallel package is not in canonical run directory")
    if hashlib.sha256(package.read_bytes()).hexdigest() != record.get(hash_key):
        raise ValueError("delivery package hash mismatch")
    if record.get("decision") != "PLAY" or record.get("actionable") is not True:
        raise ValueError("record is not a published PLAY")
    if _time(record.get("expires_at")) != plan.deadlines["t_minus_10"]:
        raise ValueError("delivery expiry differs from plan cutoff")
    ranking = None
    if parallel:
        ranking = _highest(
            record.get("highest_p13_single_coupon"), record.get("selected_coupon_count")
        )
        if ranking is None or record.get("selected_strategy_id") not in {
            "quality-v2",
            "quality-v3",
            "robust",
            "sports-shadow",
        }:
            raise ValueError("parallel selected strategy/highest-P13 binding invalid")
    elif record.get("run_id"):
        try:
            ranking = _primary_ranking(record, plan, now)
        except (OSError, ValueError, TypeError, KeyError):
            pass  # Missing/invalid ranking cannot suppress a verified primary PLAY.
    payload = {
        "event": kind,
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "record_path": str(path),
        "record_file_sha256": file_hash,
        "record_sha256": record["record_sha256"],
        "package_path": str(package),
        "package_file_sha256": record[hash_key],
        "published_at": record.get("published_at", record.get("completed_at")),
        "expires_at": plan.deadlines["t_minus_10"].isoformat(),
        "selected_strategy_id": record.get("selected_strategy_id")
        if parallel
        else "quality-v2",
        "probability_model": None if ranking is None else ranking["reference_model"],
        "highest_p13_single_coupon": ranking,
        "highest_p13_status": "AVAILABLE"
        if ranking is not None
        else "NOT_YET_BOUND_DO_NOT_INFER",
    }
    payload["event_id"] = _hash(payload)
    payload["actionable"] = timestamp_actionable(record, plan, now)
    payload["automatic_wagering"] = False
    return payload


def delivery_status(plan: SchedulerPlan, *, observed_at: datetime) -> dict:
    """Resolve only canonical native publications; never scan guessed paths."""
    root = plan.output_dir.resolve()
    events, blockers = [], []
    primary = None
    primary_path = root / "operator-result.json"
    if primary_path.exists():
        try:
            primary, file_hash = _record(primary_path, root, plan)
            if primary.get("decision") == "PLAY":
                events.append(
                    _event(
                        "READY_PRIMARY",
                        primary,
                        primary_path,
                        file_hash,
                        plan,
                        observed_at,
                    )
                )
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            blockers.append(f"primary: {error}")
    sidecar_path = root / "parallel-challenger" / "output" / "sidecar-status.json"
    if sidecar_path.exists():
        try:
            sidecar, _ = _record(sidecar_path, root, plan)
            nested = sidecar.get("parallel_release")
            if nested is not None:
                if (
                    primary is None
                    or not primary.get("run_id")
                    or sidecar.get("run_id") != primary["run_id"]
                ):
                    raise ValueError("parallel run differs from current primary run")
                if (
                    sidecar.get("status") != "READY_PARALLEL_PLAY_BEFORE_T10"
                    or _time(sidecar.get("completed_at")) > observed_at
                ):
                    raise ValueError(
                        "sidecar publication not ready at observation time"
                    )
                companion = (
                    _run_dir(root, sidecar.get("run_id"))
                    / "parallel-operator-result.json"
                )
                release, file_hash = _record(companion, root, plan)
                if release != nested:
                    raise ValueError(
                        "run companion differs from canonical nested release"
                    )
                _parallel_binding(sidecar, release, primary, plan, observed_at)
                event = _event(
                    "READY_PARALLEL", release, companion, file_hash, plan, observed_at
                )
                if not events or not events[0]["actionable"]:
                    event["actionable"] = False
                    blockers.append(
                        "parallel: current verified primary PLAY unavailable"
                    )
                events.append(event)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            blockers.append(f"parallel: {error}")
    ready = [event for event in events if event["actionable"]]
    if any(not event["actionable"] for event in events):
        blockers.append("publication not actionable at observed time")
    return {
        "schema_version": 1,
        "contract": "TOTOAI_LOCAL_DELIVERY_READY_V1",
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "observed_at": observed_at.isoformat(),
        "expires_at": plan.deadlines["t_minus_10"].isoformat(),
        "events": events,
        "preferred_event_id": None if not ready else ready[-1]["event_id"],
        "actionable": bool(ready),
        "blockers": blockers,
        "notification_transport": "LOCAL_FILES_AND_STDOUT_ONLY",
        "delivery_confirmed": False,
        "requires_host_delivery": True,
        "requires_fresh_read_before_delivery": True,
        "automatic_wagering": False,
    }
