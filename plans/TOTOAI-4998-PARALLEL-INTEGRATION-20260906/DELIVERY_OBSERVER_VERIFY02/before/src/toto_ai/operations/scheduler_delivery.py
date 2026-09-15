"""Read-only delivery observations, never a release or a delivery acknowledgement."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

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
    if not path.is_absolute() or not path.is_relative_to(root):
        raise ValueError("delivery path outside bound output")
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError("delivery symlink forbidden")
    if not path.is_file():
        raise ValueError("delivery file missing")
    return path


def _record(path: Path, root: Path, plan: SchedulerPlan) -> tuple[dict, str]:
    content = _regular(path, root).read_bytes()
    record = json.loads(content)
    if not isinstance(record, dict):
        raise ValueError("delivery record is not an object")
    if (
        record.get("plan_id") != plan.plan_id
        or record.get("drawing", record.get("drawing_number")) != plan.drawing
    ):
        raise ValueError("delivery record plan/drawing mismatch")
    if "drawing_id" in record and record["drawing_id"] != plan.drawing_id:
        raise ValueError("delivery record drawing ID mismatch")
    sealed = {k: v for k, v in record.items() if k != "record_sha256"}
    if record.get("record_sha256") != _hash(sealed):
        raise ValueError("delivery record hash mismatch")
    return record, hashlib.sha256(content).hexdigest()


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
    ranking = _highest(
        record.get("highest_p13_single_coupon"),
        record.get("selected_coupon_count" if parallel else "selected_count"),
    )
    if parallel and (
        ranking is None
        or record.get("selected_strategy_id")
        not in {"quality-v2", "quality-v3", "robust", "sports-shadow"}
    ):
        raise ValueError("parallel selected strategy/highest-P13 binding invalid")
    if not parallel and ranking is None and record.get("run_id"):
        ranking_path = (
            _run_dir(plan.output_dir.resolve(), record["run_id"])
            / "research-comparison"
            / "primary-bk-ranking.json"
        )
        try:
            proof, _ = _record(ranking_path, plan.output_dir.resolve(), plan)
            if (
                proof.get("operator_control_verified") is True
                and proof.get("operator_package_sha256") == record[hash_key]
            ):
                ranking = _highest(
                    proof.get("highest_p13_single_coupon"), record.get("selected_count")
                )
        except (OSError, ValueError, TypeError):
            pass  # Missing ranking never fabricates "first coupon is best".
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
        except (OSError, ValueError, TypeError) as error:
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
                event = _event(
                    "READY_PARALLEL", release, companion, file_hash, plan, observed_at
                )
                if not events or not events[0]["actionable"]:
                    event["actionable"] = False
                    blockers.append(
                        "parallel: current verified primary PLAY unavailable"
                    )
                events.append(event)
        except (OSError, ValueError, TypeError) as error:
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
