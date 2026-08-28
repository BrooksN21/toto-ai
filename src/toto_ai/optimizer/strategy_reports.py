"""Reproducible report bundle for equal-input strategy comparisons."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path

from toto_ai.optimizer.strategy_comparison import (
    CategoryHitComparisonBundle,
    StrategyComparisonBundle,
)

ComparisonBundle = StrategyComparisonBundle | CategoryHitComparisonBundle


@dataclass(frozen=True)
class StrategyComparisonReportPaths:
    manifest: Path
    json: Path
    csv: Path
    markdown: Path
    packages: dict[str, Path]


def write_strategy_comparison_reports(
    bundle: ComparisonBundle,
    output_dir: str | Path,
) -> StrategyComparisonReportPaths:
    if not isinstance(
        bundle, (StrategyComparisonBundle, CategoryHitComparisonBundle)
    ):
        raise ValueError("bundle must be a supported comparison bundle")
    root = Path(output_dir).absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("strategy output directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    packages_dir = root / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    package_paths: dict[str, Path] = {}
    package_artifacts = []
    for result in bundle.results:
        package_path = packages_dir / f"{result.strategy_id.lower()}.txt"
        package_bytes = _package_bytes(result.coupons, result.stake)
        _atomic_write(package_path, package_bytes)
        package_paths[result.strategy_id] = package_path
        package_artifacts.append(
            {
                "strategy_id": result.strategy_id,
                "path": str(package_path.relative_to(root)),
                "file_sha256": hashlib.sha256(package_bytes).hexdigest(),
            }
        )

    json_path = root / "comparison.json"
    csv_path = root / "comparison.csv"
    markdown_path = root / "comparison.md"
    _atomic_write(json_path, _json_bytes(_comparison_payload(bundle)))
    _atomic_write(csv_path, _comparison_csv(bundle).encode("utf-8"))
    _atomic_write(markdown_path, _comparison_markdown(bundle).encode("utf-8"))

    manifest_unsigned = {
        "schema_version": 1,
        "drawing_id": bundle.frozen_input.drawing_id,
        "drawing_number": bundle.frozen_input.drawing_number,
        "drawing_fingerprint": bundle.frozen_input.drawing_fingerprint,
        "input_sha256": bundle.frozen_input.input_sha256,
        "as_of": bundle.frozen_input.as_of,
        "source_captured_at": bundle.frozen_input.source_captured_at,
        "ended_at": bundle.frozen_input.ended_at,
        "bank": bundle.frozen_input.bank,
        "stake": bundle.frozen_input.stake,
        "strategy_count": len(bundle.results),
        "strategies": [
            {
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "category": result.category,
                "config_sha256": result.config_sha256,
                "package_sha256": result.package_sha256,
                "coupon_count": result.coupon_count,
                "cost": result.cost,
            }
            for result in bundle.results
        ],
        "artifacts": {
            "comparison_json": _artifact(root, json_path),
            "comparison_csv": _artifact(root, csv_path),
            "comparison_markdown": _artifact(root, markdown_path),
            "packages": package_artifacts,
        },
        "automatic_wagering": False,
        "actionable": False,
        "artifact_class": "RESEARCH/PAPER",
    }
    manifest_hash = hashlib.sha256(_canonical_json_bytes(manifest_unsigned)).hexdigest()
    manifest_path = root / "manifest.json"
    _atomic_write(
        manifest_path,
        _json_bytes({**manifest_unsigned, "manifest_sha256": manifest_hash}),
    )
    return StrategyComparisonReportPaths(
        manifest=manifest_path,
        json=json_path,
        csv=csv_path,
        markdown=markdown_path,
        packages=package_paths,
    )


def _comparison_payload(bundle: ComparisonBundle) -> dict[str, object]:
    return {
        "schema_version": 1,
        "input": {
            "drawing_id": bundle.frozen_input.drawing_id,
            "drawing_number": bundle.frozen_input.drawing_number,
            "drawing_fingerprint": bundle.frozen_input.drawing_fingerprint,
            "input_sha256": bundle.frozen_input.input_sha256,
            "source_captured_at": bundle.frozen_input.source_captured_at,
            "as_of": bundle.frozen_input.as_of,
            "ended_at": bundle.frozen_input.ended_at,
            "bank": bundle.frozen_input.bank,
            "stake": bundle.frozen_input.stake,
        },
        "results": [asdict(result) for result in bundle.results],
        "actionable": False,
        "automatic_wagering": False,
        "artifact_class": "RESEARCH/PAPER",
    }


def _comparison_csv(bundle: ComparisonBundle) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "strategy_id",
            "category",
            "coupon_count",
            "cost",
            "unused_bank",
            "probability_at_least_13",
            "probability_at_least_14",
            "probability_at_least_15",
            "coverage_rate",
            "guarantee_pass",
            "runtime_seconds",
            "timed_out",
            "input_sha256",
            "config_sha256",
            "package_sha256",
        )
    )
    for result in bundle.results:
        writer.writerow(
            (
                result.strategy_id,
                result.category,
                result.coupon_count,
                result.cost,
                result.unused_bank,
                result.probability_at_least_13,
                result.probability_at_least_14,
                result.probability_at_least_15,
                result.coverage_rate,
                result.guarantee_pass,
                result.runtime_seconds,
                result.timed_out,
                result.input_sha256,
                result.config_sha256,
                result.package_sha256,
            )
        )
    return stream.getvalue()


def _comparison_markdown(bundle: ComparisonBundle) -> str:
    lines = [
        f"# Strategy comparison for drawing {bundle.frozen_input.drawing_number}",
        "",
        "**RESEARCH/PAPER — NOT ACTIONABLE.**",
        "",
        f"- Frozen input: `{bundle.frozen_input.input_sha256}`",
        f"- As of: `{bundle.frozen_input.as_of}`",
        f"- Bank / stake: {bundle.frozen_input.bank} / {bundle.frozen_input.stake}",
        "",
        "| Strategy | Cat | Coupons | Cost | P(13+) | P(14+) | P(15) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in bundle.results:
        lines.append(
            "| "
            f"{result.strategy_id} | {result.category} | {result.coupon_count} | "
            f"{result.cost} | {result.probability_at_least_13:.8f} | "
            f"{result.probability_at_least_14:.8f} | "
            f"{result.probability_at_least_15:.8f} |"
        )
    lines.extend(
        (
            "",
            "Modeled probabilities are not proof of profitability. Strategy "
            "selection requires historical and prospective outcome evidence.",
            "",
        )
    )
    return "\n".join(lines)


def _package_bytes(coupons: tuple[str, ...], stake: int) -> bytes:
    return "".join(
        f"{stake}; {'; '.join(coupon)}\n" for coupon in coupons
    ).encode("utf-8")


def _artifact(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists() and path.is_symlink():
        raise ValueError(f"refusing to replace symlink: {path}")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
