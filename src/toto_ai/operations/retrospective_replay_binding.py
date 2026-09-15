"""Strict retrospective reuse contract for frozen-input post-draw audit.

Callers must derive expectations from verified frozen plan/source bindings, and
pass the primary state's exact result_snapshot_sha256 to load_bound_result.
Never infer that identity from the report or the latest database row.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toto_ai.db.session import get_session_factory, open_readonly_db
from toto_ai.operations.finished_draw import _verified_snapshot

INPUT_KEYS = frozenset(
    {
        "final_input_sha256",
        "probability_input_sha256",
        "sports_artifact_sha256",
        "sports_probability_input_sha256",
        "scheduler_plan_sha256",
    }
)
STRATEGIES = frozenset({"quality-v2", "sports-v2", "quality-v3", "robust"})


@dataclass(frozen=True)
class BoundResult:
    snapshot_sha256: str
    drawing_id: int
    drawing_number: int
    actual: str


def load_bound_result(
    database: Path,
    *,
    snapshot_sha256: str,
    drawing_id: int,
    drawing_number: int,
) -> BoundResult:
    """Read and fully verify EXACT primary snapshot in one read-only transaction."""
    if not isinstance(snapshot_sha256, str) or len(snapshot_sha256) != 64:
        raise ValueError("canonical result snapshot hash is required")
    engine = open_readonly_db(database)
    try:
        with get_session_factory(engine)() as session:
            row = _verified_snapshot(session, snapshot_sha256)
            if (row.drawing_id, row.drawing_number) != (drawing_id, drawing_number):
                raise ValueError("canonical result snapshot drawing mismatch")
            return BoundResult(
                row.snapshot_sha256, row.drawing_id, row.drawing_number, row.actual
            )
    finally:
        engine.dispose()


def validate_replay_contract(
    report: dict[str, Any],
    *,
    drawing_id: int,
    drawing_number: int,
    plan_id: str,
    expected_input_hashes: Mapping[str, str],
    result: BoundResult,
    bank: int,
    stake: int,
    baseline_coupons: Sequence[str],
    legacy_result_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject stale same-plan outputs, including honestly re-signed mismatches.

    Old reports missing result identity are not migrated or silently accepted.
    Generator integration must supply this identity AFTER coupon generation;
    actual results must never enter prediction objectives.
    """
    unsigned = dict(report)
    supplied_hash = unsigned.pop("report_sha256", None)
    digest = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if supplied_hash != digest:
        raise ValueError("replay report self-hash mismatch")
    expected = {
        "schema_version": 2,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "plan_id": plan_id,
    }
    if any(report.get(k) != v for k, v in expected.items()):
        raise ValueError("replay identity mismatch")
    if report.get("quality_v2_reproduced_exactly") is not True or any(
        report.get(k) is not False
        for k in (
            "automatic_wagering",
            "operator_compatible",
            "scheduler_state_mutated",
            "profitability_proven",
        )
    ):
        raise ValueError("replay safety contract mismatch")
    if (result.drawing_id, result.drawing_number) != (drawing_id, drawing_number):
        raise ValueError("bound result identity mismatch")
    bound_snapshot = report.get("result_snapshot_sha256")
    if bound_snapshot is None and legacy_result_binding is not None:
        # Explicit append-only audit binding of EXACT legacy report; never rewrite it.
        if dict(legacy_result_binding) != {
            "report_sha256": supplied_hash,
            "result_snapshot_sha256": result.snapshot_sha256,
            "actual": result.actual,
        }:
            raise ValueError("legacy replay audit binding mismatch")
        bound_snapshot = result.snapshot_sha256
    if (
        bound_snapshot != result.snapshot_sha256
        or report.get("actual") != result.actual
    ):
        raise ValueError("replay canonical result binding mismatch")
    if set(expected_input_hashes) != INPUT_KEYS or report.get("inputs") != dict(
        expected_input_hashes
    ):
        raise ValueError("replay frozen input binding mismatch")
    for sha in expected_input_hashes.values():
        if (
            not isinstance(sha, str)
            or len(sha) != 64
            or set(sha) - set("0123456789abcdef")
        ):
            raise ValueError("invalid expected input SHA-256")
    coupons = tuple(baseline_coupons)
    if (
        type(bank) is not int
        or type(stake) is not int
        or bank < 1
        or stake < 1
        or not coupons
        or len(set(coupons)) != len(coupons)
        or any(len(c) != 15 or set(c) - set("1X2") for c in coupons)
    ):
        raise ValueError("invalid frozen budget or baseline coupons")
    cost = len(coupons) * stake
    if cost > bank:
        raise ValueError("baseline exceeds requested bank")
    for k, value in {
        "bank": bank,
        "stake": stake,
        "equal_cost": cost,
        "equal_coupon_count": len(coupons),
    }.items():
        if type(report.get(k)) is not int or report[k] != value:
            raise ValueError(f"replay equal-budget mismatch: {k}")
    effective = report.get("effective_budget")
    if (
        type(effective) is not int
        or effective // stake != len(coupons)
        or not (cost <= effective <= bank)
    ):
        raise ValueError("replay effective budget mismatch")
    strategies = report.get("strategies")
    if not isinstance(strategies, dict) or set(strategies) != STRATEGIES:
        raise ValueError("replay strategy set mismatch")
    for name, strategy in strategies.items():
        if (
            not isinstance(strategy, dict)
            or type(strategy.get("coupon_count")) is not int
            or type(strategy.get("cost")) is not int
            or strategy["coupon_count"] != len(coupons)
            or strategy["cost"] != cost
        ):
            raise ValueError(f"replay strategy budget mismatch: {name}")
    baseline_hash = hashlib.sha256(",".join(coupons).encode()).hexdigest()
    if strategies["quality-v2"].get("package_sha256") != baseline_hash:
        raise ValueError("replay issued control package mismatch")
    return report
