"""Read-only integrity bridge between a frozen CSV and canonical settlement.

The upload-file hash, CSV byte hash and ordered-coupon semantic hash are separate
namespaces. Only the producer-validated post-draw binding supplies the latter.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from toto_ai.operations.finished_draw import load_post_draw_plan


def _regular_bytes(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("retrospective input must be an absolute regular file")
    return path.read_bytes()


def validate_retrospective_primary(
    *,
    state_path: Path,
    post_draw_plan_path: Path,
    expected_plan_sha256: str,
    drawing_id: int,
    drawing_number: int,
    baseline_package: Path,
    baseline_file_sha256: str,
    stake: int,
    coupon_count: int,
    cost: int,
) -> dict[str, Any] | None:
    """Validate the entire frozen-source -> producer binding -> state chain.

    This never modifies plans, archives, states or the database. A missing or
    pending state is not completion; malformed/foreign inputs fail closed.
    """
    _regular_bytes(post_draw_plan_path)
    plan = load_post_draw_plan(post_draw_plan_path)
    if plan["plan_sha256"] != expected_plan_sha256:
        raise ValueError("retrospective primary plan SHA-256 mismatch")
    if (plan["drawing_id"], plan["drawing_number"]) != (drawing_id, drawing_number):
        raise ValueError("retrospective primary plan identity mismatch")
    if Path(plan["state_file"]) != state_path:
        raise ValueError("retrospective primary state path mismatch")

    baseline_sha256 = hashlib.sha256(_regular_bytes(baseline_package)).hexdigest()
    binding = plan["package_binding"]
    if (
        binding["kind"] != "package"
        or baseline_sha256 != baseline_file_sha256
        or binding["source_bytes_sha256"] != baseline_file_sha256
    ):
        raise ValueError("retrospective primary source bytes SHA-256 mismatch")
    # load_post_draw_plan already re-hashed and parsed that exact source,
    # verified ordered coupon identity, declared stake, count and cost.
    if (binding["stake"], binding["coupon_count"], binding["cost"]) != (
        stake,
        coupon_count,
        cost,
    ):
        raise ValueError("retrospective primary package cost identity mismatch")

    if not state_path.exists() and not state_path.is_symlink():
        return None
    state = json.loads(_regular_bytes(state_path))
    if not isinstance(state, dict) or state.get("schema_version") != 2:
        raise ValueError("unsupported retrospective primary state schema")
    unsigned = dict(state)
    state_sha256 = unsigned.pop("state_sha256", None)
    encoded = json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != state_sha256:
        raise ValueError("retrospective primary state SHA-256 mismatch")
    if (state.get("drawing_id"), state.get("drawing_number")) != (
        drawing_id,
        drawing_number,
    ):
        raise ValueError("retrospective primary state identity mismatch")
    if state.get("status") not in {"complete", "pending", "failed", "blocked"}:
        raise ValueError("unsupported retrospective primary state status")
    if (
        state.get("status") == "complete"
        and state.get("package_sha256") != binding["package_sha256"]
    ):
        raise ValueError("post-draw state canonical package SHA-256 mismatch")
    return state
