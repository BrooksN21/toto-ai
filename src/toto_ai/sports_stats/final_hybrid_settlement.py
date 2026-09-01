"""Settle exact final-input-bound parallel packages after a drawing.

The output is aggregate research evidence. It never emits coupons and never
changes the operator decision or wagering state.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

OUTCOMES = frozenset("1X2")
VOID_RESULT = "*"
STRATEGY_FILES = {
    "quality-v2": "baseline-final-research-coupons.txt",
    "sports-shadow": "sports-final-research-coupons.txt",
    "quality-v3": "quality-v3-final-research-coupons.txt",
    "robust": "robust-final-research-coupons.txt",
}
ARTIFACT_CLASS = "FINAL_HYBRID_POST_DRAW_COMPARISON"


def settle_final_hybrid_comparison(
    *,
    sidecar_status_path: str | Path,
    drawing_id: int,
    drawing_number: int,
    plan_id: str,
    actual: str,
    output_dir: str | Path,
) -> tuple[dict[str, Any], Mapping[str, Path]]:
    """Verify and settle all exact packages frozen by the final sidecar."""

    if type(drawing_id) is not int or drawing_id <= 0:
        raise ValueError("drawing_id must be a positive integer")
    if type(drawing_number) is not int or drawing_number <= 0:
        raise ValueError("drawing_number must be a positive integer")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValueError("plan_id must be non-empty")
    if len(actual) != 15 or set(actual) - (OUTCOMES | {VOID_RESULT}):
        raise ValueError("actual result must contain 15 terminal outcomes")

    status_path = _regular_file(sidecar_status_path, "sidecar status")
    status = _load_hash_bound_json(status_path, hash_field="record_sha256")
    if (
        status.get("status")
        not in {"READY_BEFORE_T10", "READY_PARALLEL_PLAY_BEFORE_T10"}
        or status.get("drawing_id") != drawing_id
        or status.get("drawing") != drawing_number
        or status.get("plan_id") != plan_id
        or status.get("automatic_wagering") is not False
    ):
        raise ValueError("sidecar status identity or safety boundary mismatch")

    report_path = _regular_file(status.get("research_report"), "research report")
    _require_descendant(report_path, status_path.parent)
    if _sha256_file(report_path) != status.get("research_report_sha256"):
        raise ValueError("research report SHA-256 mismatch")
    comparison = _load_hash_bound_json(report_path, hash_field="report_sha256")
    if (
        comparison.get("artifact_class")
        != "FINAL_INPUT_BOUND_GOAL_SPORTS_HYBRID_COMPARISON"
        or comparison.get("drawing_id") != drawing_id
        or comparison.get("drawing_number") != drawing_number
        or comparison.get("plan_id") != plan_id
        or comparison.get("automatic_wagering") is not False
        or comparison.get("operator_compatible") is not False
    ):
        raise ValueError("research comparison identity or safety boundary mismatch")

    stake = comparison.get("stake")
    if type(stake) is not int or stake <= 0:
        raise ValueError("comparison stake must be a positive integer")
    candidates = _candidate_map(comparison)
    strategies: dict[str, dict[str, Any]] = {}
    package_file_hashes: dict[str, str] = {}
    for strategy, filename in STRATEGY_FILES.items():
        candidate = candidates[strategy]
        package_path = _regular_file(
            report_path.parent / filename,
            f"{strategy} package",
        )
        _require_descendant(package_path, report_path.parent)
        coupons, declared_stake, declared_count = _parse_research_package(package_path)
        package_hash = hashlib.sha256(",".join(coupons).encode("ascii")).hexdigest()
        if (
            package_hash != candidate.get("package_sha256")
            or len(coupons) != candidate.get("coupon_count")
            or len(coupons) * stake != candidate.get("cost")
            or declared_stake != stake
            or declared_count != len(coupons)
        ):
            raise ValueError(f"{strategy} package binding mismatch")
        strategies[strategy] = {
            **_score(coupons, actual),
            "coupon_count": len(coupons),
            "cost": len(coupons) * stake,
            "package_sha256": package_hash,
            "modeled_category_probabilities": candidate.get("models"),
        }
        package_file_hashes[strategy] = _sha256_file(package_path)

    control = strategies["quality-v2"]
    sports = strategies["sports-shadow"]
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "COMPLETE",
        "artifact_class": ARTIFACT_CLASS,
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "plan_id": plan_id,
        "actual_result_sha256": hashlib.sha256(actual.encode("ascii")).hexdigest(),
        "resolved_event_count": sum(outcome != VOID_RESULT for outcome in actual),
        "void_event_orders": [
            index
            for index, outcome in enumerate(actual, start=1)
            if outcome == VOID_RESULT
        ],
        "source": {
            "sidecar_status_sha256": _sha256_file(status_path),
            "comparison_report_sha256": _sha256_file(report_path),
            "package_file_sha256": package_file_hashes,
        },
        "strategies": strategies,
        "comparison": {
            "sports_minus_quality_v2_best_hits": (
                sports["best_hits"] - control["best_hits"]
            ),
            "sports_minus_quality_v2_hit13_count": (
                sports["category_counts"]["13"]
                - control["category_counts"]["13"]
            ),
            "sports_minus_quality_v2_hit14_count": (
                sports["category_counts"]["14"]
                - control["category_counts"]["14"]
            ),
            "sports_minus_quality_v2_hit15_count": (
                sports["category_counts"]["15"]
                - control["category_counts"]["15"]
            ),
        },
        "automatic_wagering": False,
        "operator_compatible": False,
        "profitability_proven": False,
        "interpretation": (
            "One settled drawing is descriptive evidence only and cannot prove "
            "causality or profitability."
        ),
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    output = Path(output_dir).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("settlement output directory must be regular")
    paths = {
        "json": output / "final-hybrid-settlement.json",
        "markdown": output / "final-hybrid-settlement.md",
    }
    _write_replace(paths["json"], _pretty(report))
    _write_replace(paths["markdown"], _markdown(report).encode("utf-8"))
    return report, paths


def _candidate_map(comparison: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    selection = comparison.get("experimental_selection")
    rows = None if not isinstance(selection, Mapping) else selection.get("candidates")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("comparison candidates are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("comparison candidate is invalid")
        strategy = row.get("strategy_id")
        if strategy in result:
            raise ValueError("comparison candidate strategy is duplicated")
        if strategy in STRATEGY_FILES:
            result[strategy] = row
    if set(result) != set(STRATEGY_FILES):
        raise ValueError("comparison candidates are incomplete")
    return result


def _parse_research_package(path: Path) -> tuple[tuple[str, ...], int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 5 or lines[0] != "RESEARCH ONLY / NOT ACTIVATED / DO NOT WAGER":
        raise ValueError("research package header is invalid")
    if lines[1] != "NOT A BALTBet UPLOAD FILE":
        raise ValueError("research package safety label is invalid")
    fields = dict(
        token.split("=", 1)
        for token in lines[2].split()
        if "=" in token
    )
    try:
        stake = int(fields["stake"])
        count = int(fields["coupons"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("research package metadata is invalid") from error
    coupons = tuple(
        line for line in lines[4:] if len(line) == 15 and not (set(line) - OUTCOMES)
    )
    if not coupons or len(coupons) != len(set(coupons)):
        raise ValueError("research package coupons are invalid")
    return coupons, stake, count


def _score(coupons: Sequence[str], actual: str) -> dict[str, Any]:
    hits = tuple(
        sum(
            observed == VOID_RESULT or predicted == observed
            for predicted, observed in zip(coupon, actual, strict=True)
        )
        for coupon in coupons
    )
    distribution = Counter(hits)
    zero_exposure: list[int] = []
    fixed_misses: list[int] = []
    actual_exposure: list[dict[str, Any]] = []
    for position, observed in enumerate(actual, start=1):
        if observed == VOID_RESULT:
            actual_exposure.append({"position": position, "count": None, "share": None})
            continue
        outcomes = Counter(coupon[position - 1] for coupon in coupons)
        count = outcomes[observed]
        actual_exposure.append(
            {"position": position, "count": count, "share": count / len(coupons)}
        )
        if count == 0:
            zero_exposure.append(position)
            if len(outcomes) == 1:
                fixed_misses.append(position)
    return {
        "best_hits": max(hits),
        "best_coupon_count": distribution[max(hits)],
        "category_counts": {
            str(category): distribution[category] for category in (13, 14, 15)
        },
        "hit_distribution": {
            str(category): distribution[category] for category in range(16)
        },
        "actual_outcome_exposure": actual_exposure,
        "zero_exposure_miss_positions": zero_exposure,
        "fixed_miss_positions": fixed_misses,
    }


def _load_hash_bound_json(path: Path, *, hash_field: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} is malformed") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    declared = payload.get(hash_field)
    unsigned = dict(payload)
    unsigned.pop(hash_field, None)
    if declared != hashlib.sha256(_canonical(unsigned)).hexdigest():
        raise ValueError(f"{path.name} hash mismatch")
    return payload


def _regular_file(value: object, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise ValueError(f"{name} path is invalid")
    path = Path(value).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{name} must be a regular non-symlink file")
    return path


def _require_descendant(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("comparison artifact escapes the sidecar output") from error


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("settlement output path cannot traverse a symlink")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _markdown(report: Mapping[str, Any]) -> str:
    rows = []
    for name in STRATEGY_FILES:
        strategy = report["strategies"][name]
        categories = strategy["category_counts"]
        rows.append(
            f"| {name} | {strategy['best_hits']}/15 | "
            f"{categories['13']} | {categories['14']} | {categories['15']} | "
            f"{strategy['zero_exposure_miss_positions']} |"
        )
    delta = report["comparison"]["sports_minus_quality_v2_best_hits"]
    return (
        f"# Final hybrid post-draw comparison: {report['drawing_number']}\n\n"
        "| Strategy | Best | 13 | 14 | 15 | Zero-exposure misses |\n"
        "|---|---:|---:|---:|---:|---|\n"
        + "\n".join(rows)
        + "\n\n"
        f"Sports-shadow minus quality-v2 best hits: **{delta:+d}**.\n\n"
        "Research comparison only. No coupon strings are included; one drawing "
        "does not prove causality or profitability. Automatic wagering is disabled.\n"
    )
