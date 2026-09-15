#!/usr/bin/env python3
"""Plan-bound, post-cutoff retrospective runner for drawing 4996.

This generated operational artifact is deliberately outside ``src/``.  It
waits for the canonical post-draw state to become complete, verifies every
frozen input by SHA-256, and only then invokes the existing research-only
four-strategy replay.  It never touches scheduler/operator state and cannot
place a wager.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from toto_ai.operations.retrospective_integrity import validate_retrospective_primary

MOSCOW = ZoneInfo("Europe/Moscow")
TERMINAL_RESULTS = {"1", "X", "2"}
VOID_STATUSES = {"void", "cancelled", "canceled", "postponed", "postpone", "pst"}


def canonical_bytes(value: Any, *, ensure_ascii: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_regular(path: Path, label: str) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an absolute regular non-symlink file")
    return path.read_bytes()


def read_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(read_regular(path, label))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def verify_self_hash(
    document: dict[str, Any], key: str, label: str, *, ensure_ascii: bool = False
) -> None:
    expected = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(expected, str) or sha256_bytes(canonical_bytes(unsigned, ensure_ascii=ensure_ascii)) != expected:
        raise ValueError(f"{label} {key} mismatch")


def atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def write_status(path: Path, payload: dict[str, Any]) -> None:
    unsigned = dict(payload)
    unsigned["status_sha256"] = sha256_bytes(canonical_bytes(unsigned))
    atomic_write(path, json.dumps(unsigned, ensure_ascii=False, indent=2) + "\n")


def load_plan(path: Path) -> dict[str, Any]:
    plan = read_json(path, "retrospective plan")
    verify_self_hash(plan, "plan_sha256", "retrospective plan")
    if plan.get("schema_version") != 1:
        raise ValueError("unsupported retrospective plan schema")
    if plan.get("automatic_wagering") is not False:
        raise ValueError("automatic wagering must be false")
    if plan.get("operator_compatible") is not False:
        raise ValueError("retrospective output must be non-operator-compatible")
    return plan


def verify_bindings(plan: dict[str, Any]) -> dict[str, Path]:
    root = Path(plan["project_root"])
    if root != Path("/Users/turshevr/toto-ai") or root.is_symlink() or not root.is_dir():
        raise ValueError("project root identity mismatch")
    resolved: dict[str, Path] = {}
    for name, binding in plan["bindings"].items():
        path = Path(binding["path"])
        value = read_regular(path, name)
        if root not in path.parents:
            raise ValueError(f"{name} escapes the project root")
        if sha256_bytes(value) != binding["file_sha256"]:
            raise ValueError(f"{name} file SHA-256 mismatch")
        resolved[name] = path

    scheduler = read_json(resolved["scheduler_plan"], "scheduler plan")
    final_input = read_json(resolved["final_input"], "final input")
    sports = read_json(resolved["sports_artifact"], "sports artifact")
    post_draw = read_json(resolved["post_draw_plan"], "post-draw plan")
    delivery = read_json(resolved["operator_delivery"], "operator delivery")
    paper = read_json(resolved["paper_package_result"], "paper package result")

    plan_id = plan["plan_id"]
    drawing_id = plan["drawing_id"]
    drawing_number = plan["drawing_number"]
    if scheduler.get("plan_id") != plan_id or scheduler.get("target", {}).get("drawing") != drawing_number:
        raise ValueError("scheduler identity mismatch")
    if scheduler.get("target", {}).get("drawing_id") != drawing_id:
        raise ValueError("scheduler drawing ID mismatch")
    if final_input.get("plan_id") != plan_id or final_input.get("drawing_number") != drawing_number:
        raise ValueError("final-input identity mismatch")
    if final_input.get("drawing_id") != drawing_id:
        raise ValueError("final-input drawing ID mismatch")
    if sports.get("drawing_number") != drawing_number or sports.get("drawing_id") != drawing_id:
        raise ValueError("sports artifact identity mismatch")
    if sports.get("artifact_sha256") != plan["sports_artifact_semantic_sha256"]:
        raise ValueError("sports artifact semantic SHA-256 mismatch")
    if post_draw.get("drawing_number") != drawing_number or post_draw.get("drawing_id") != drawing_id:
        raise ValueError("post-draw plan identity mismatch")
    if delivery.get("plan_id") != plan_id or delivery.get("drawing") != drawing_number:
        raise ValueError("operator-delivery identity mismatch")
    if paper.get("plan_id") != plan_id or paper.get("drawing") != drawing_number:
        raise ValueError("paper-package identity mismatch")
    if delivery.get("package_sha256") != plan["issued_operator_package"]["package_sha256"]:
        raise ValueError("issued operator-package SHA-256 mismatch")
    if paper.get("paper_sha256") != plan["issued_operator_package"]["package_sha256"]:
        raise ValueError("paper-package SHA-256 mismatch")
    if paper.get("count") != 166 or paper.get("stake") != 30 or paper.get("cost") != 4980:
        raise ValueError("issued operator-package cost identity mismatch")
    return resolved


def database_status(db_path: Path, drawing_id: int, drawing_number: int) -> dict[str, Any]:
    uri = f"file:{db_path}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        drawing = connection.execute(
            "SELECT id, number, status FROM drawings WHERE id=? AND number=?",
            (drawing_id, drawing_number),
        ).fetchone()
        events = connection.execute(
            "SELECT event_order, result, result_status FROM events "
            "WHERE drawing_id=? ORDER BY event_order",
            (drawing_id,),
        ).fetchall()
    finally:
        connection.close()
    resolved = 0
    void = 0
    pending_positions: list[int] = []
    for event in events:
        result = (event["result"] or "").strip().upper()
        result_status = (event["result_status"] or "").strip().lower()
        if result in TERMINAL_RESULTS:
            resolved += 1
        elif result in {"*", "VOID"} or result_status in VOID_STATUSES:
            void += 1
        else:
            pending_positions.append(int(event["event_order"]) + 1)
    return {
        "drawing_present": drawing is not None,
        "drawing_status": None if drawing is None else drawing["status"],
        "event_count": len(events),
        "resolved_count": resolved,
        "void_count": void,
        "terminal_count": resolved + void,
        "pending_count": len(pending_positions),
        "pending_positions": pending_positions,
    }


def next_slot(plan: dict[str, Any], now: datetime) -> str | None:
    for raw in plan["run_slots"]:
        candidate = datetime.fromisoformat(raw)
        if candidate > now:
            return raw
    return None


def validate_primary_state(
    plan: dict[str, Any], bindings: dict[str, Path]
) -> dict[str, Any] | None:
    issued = plan["issued_operator_package"]
    return validate_retrospective_primary(
        state_path=Path(plan["primary_post_draw_state"]),
        post_draw_plan_path=bindings["post_draw_plan"],
        expected_plan_sha256=plan["primary_post_draw_plan_sha256"],
        drawing_id=plan["drawing_id"],
        drawing_number=plan["drawing_number"],
        baseline_package=bindings["baseline_package"],
        baseline_file_sha256=plan["bindings"]["baseline_package"]["file_sha256"],
        stake=issued["stake"],
        coupon_count=issued["coupon_count"],
        cost=issued["cost"],
    )


def validate_replay_report(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    report = read_json(path, "historical hybrid replay")
    verify_self_hash(
        report, "report_sha256", "historical hybrid replay", ensure_ascii=True
    )
    if report.get("schema_version") != 2:
        raise ValueError("unsupported historical hybrid replay schema")
    if (
        report.get("drawing_id") != plan["drawing_id"]
        or report.get("drawing_number") != plan["drawing_number"]
        or report.get("plan_id") != plan["plan_id"]
        or report.get("quality_v2_reproduced_exactly") is not True
        or report.get("automatic_wagering") is not False
        or report.get("operator_compatible") is not False
    ):
        raise ValueError("historical hybrid replay identity/safety mismatch")
    if set(report.get("strategies", {})) != {"quality-v2", "sports-v2", "quality-v3", "robust"}:
        raise ValueError("historical hybrid replay strategy set mismatch")
    return report


def summary_markdown(report: dict[str, Any], plan: dict[str, Any]) -> str:
    lines = [
        "# Drawing 4996 equal-input retrospective",
        "",
        "**POST-CUTOFF RESEARCH ONLY — NOT FOR WAGERING OR UPLOAD**",
        "",
        f"- Plan: `{plan['plan_id']}`",
        f"- Actual/VOID: `{report['actual']}`",
        f"- Equal input/cost: {report['equal_coupon_count']} coupons × {report['stake']} RUB = {report['equal_cost']} RUB",
        f"- Sports-v2 coverage/fallback: {report['sports_coverage_count']}/{report['sports_fallback_count']}",
        "- Issued operator strategy: `quality-v2` control",
        "- Pre-cutoff parallel sidecar: incomplete; owner terminated it before terminal publication",
        "- Return/ROI: unknown unless separate authoritative payout evidence is later verified",
        "",
        "| Strategy | Best hits | 13 | 14 | 15 | P13 BK pre-draw | P13 worst model | Max outcome share | Cost RUB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("quality-v2", "sports-v2", "quality-v3", "robust"):
        strategy = report["strategies"][name]
        settlement = strategy["settlement"]
        models = {item["model"]: item for item in strategy["models"]}
        worst_p13 = min(float(item["p13"]) for item in strategy["models"])
        lines.append(
            f"| {name} | {settlement['best_hits']} | {settlement['hit13']} | "
            f"{settlement['hit14']} | {settlement['hit15']} | "
            f"{float(models['bk']['p13']):.10f} | {worst_p13:.10f} | "
            f"{float(strategy['maximum_outcome_share']):.6f} | {strategy['cost']} |"
        )
    lines.extend(
        [
            "",
            "`P13` values are frozen pre-draw model probabilities, not realized profit evidence.",
            "Coupon-file order is not a probability ranking.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    plan = load_plan(args.plan.absolute())
    status_path = Path(plan["status_file"])
    now = datetime.now(MOSCOW)
    base_status: dict[str, Any] = {
        "schema_version": 1,
        "drawing_id": plan["drawing_id"],
        "drawing_number": plan["drawing_number"],
        "plan_id": plan["plan_id"],
        "retrospective_plan_sha256": plan["plan_sha256"],
        "observed_at": now.isoformat(),
        "automatic_wagering": False,
        "operator_compatible": False,
        "issued_operator_strategy": "quality-v2",
        "pre_cutoff_sidecar_status": "INCOMPLETE_OWNER_TERMINATED",
        "pre_cutoff_models": {
            "quality-v2": "ARCHIVED_CONTROL",
            "sports-shadow": "UNFINISHED_NO_TERMINAL_PACKAGE",
            "quality-v3": "MISSING_NO_TERMINAL_PACKAGE",
            "robust": "MISSING_NO_TERMINAL_PACKAGE",
        },
        "comparison_kind": "POST_DRAW_REPLAY_NOT_PRE_CUTOFF_SIDECAR",
        "next_attempt": next_slot(plan, now),
    }
    try:
        bindings = verify_bindings(plan)
        db = database_status(
            Path(plan["database"]),
            plan["drawing_id"],
            plan["drawing_number"],
        )
        primary = validate_primary_state(plan, bindings)
        base_status["database"] = db
        base_status["primary_post_draw"] = (
            {"status": "not_started"} if primary is None else {
                "status": primary.get("status"),
                "reason": primary.get("reason"),
                "attempts": primary.get("attempts"),
                "state_sha256": primary.get("state_sha256"),
            }
        )
        if primary is None or primary.get("status") != "complete":
            base_status.update(
                status="pending",
                phase="WAITING_FOR_CANONICAL_POST_DRAW_COMPLETION",
                blocker="RESULTS_OR_REVIEWED_VOID_INCOMPLETE",
            )
            write_status(status_path, base_status)
            return 2
        if db["event_count"] != 15 or db["terminal_count"] != 15:
            raise ValueError("canonical post-draw state is complete but DB is not terminal 15/15")

        replay_dir = Path(plan["replay_output_dir"])
        report_path = replay_dir / "historical-hybrid-replay.json"
        if not report_path.exists():
            base_status.update(
                status="running",
                phase="EQUAL_INPUT_FOUR_STRATEGY_REPLAY",
                blocker=None,
            )
            write_status(status_path, base_status)
            stdout_path = Path(plan["stdout_log"])
            stderr_path = Path(plan["stderr_log"])
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                str(Path(plan["python_executable"])),
                "-m",
                "toto_ai.cli",
                "replay-quality-sports-v2-robust",
                "--final-input",
                str(bindings["final_input"]),
                "--scheduler-plan",
                str(bindings["scheduler_plan"]),
                "--baseline-package",
                str(bindings["baseline_package"]),
                "--sports-artifact",
                str(bindings["sports_artifact"]),
                "--db",
                plan["database"],
                "--output-dir",
                str(replay_dir),
            ]
            with stdout_path.open("a", encoding="utf-8") as stdout, stderr_path.open("a", encoding="utf-8") as stderr:
                completed = subprocess.run(
                    command,
                    cwd=plan["project_root"],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=1800,
                    check=False,
                )
            if completed.returncode != 0:
                raise RuntimeError(f"replay command failed with exit {completed.returncode}")

        report = validate_replay_report(report_path, plan)
        summary_path = Path(plan["comparison_summary"])
        atomic_write(summary_path, summary_markdown(report, plan))
        base_status.update(
            status="complete",
            phase="RETROSPECTIVE_COMPLETE",
            blocker=None,
            next_attempt=None,
            replay_report=str(report_path),
            replay_report_sha256=report["report_sha256"],
            comparison_summary=str(summary_path),
            actual=report["actual"],
            quality_v2_reproduced_exactly=True,
        )
        write_status(status_path, base_status)
        return 0
    except Exception as error:  # fail closed and preserve a machine-readable status
        base_status.update(
            status="failed",
            phase="FAIL_CLOSED",
            blocker=f"{type(error).__name__}: {error}",
        )
        write_status(status_path, base_status)
        print(base_status["blocker"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
