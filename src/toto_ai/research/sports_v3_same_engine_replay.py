"""Reproducible, research-only BK/Sports-v3 same-engine package replay.

This module deliberately accepts frozen JSON artifacts and writes only a local
research record.  It has no scheduler, operator, consent, or upload-format
dependency.  In particular, the saved coupon arrays are JSON analysis data,
not a BaltBet package.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from toto_ai.ev.package_quality import (
    exact_category_probabilities,
    selection_probability_input_sha256,
)
from toto_ai.optimizer.robust_package import RobustPackageResult, select_robust_package
from toto_ai.optimizer.uncertainty_package import flatten_probabilities

RESEARCH_CLASSIFICATION = {
    "research_only": True,
    "operator_compatible": False,
    "automatic_wagering": False,
    "coupon_encoding": "JSON_ARRAY_ANALYSIS_ONLY_NOT_BALTBET_UPLOAD",
}


@dataclass(frozen=True)
class SameEngineReplaySettings:
    category: int = 13
    max_coupons: int = 166
    sample_count: int = 10_000
    seed_material: str = "quality-v2-vs-v3-prospective-v1-selector"
    flatten_weights: tuple[float, float] = (0.1, 0.2)
    exposure_constraints: None = None


def replay_same_engine(
    *,
    bk_package_path: str | Path,
    sports_package_path: str | Path,
    predictions_path: str | Path,
    old_comparison_path: str | Path,
    output_dir: str | Path,
    settings: SameEngineReplaySettings | None = None,
) -> dict[str, Any]:
    """Select two fixed research packages from one frozen candidate universe.

    The candidate union is frozen once, before either arm is selected.  Both
    arms use the same selector settings and their own base matrix plus the same
    two flatten transforms.  The returned 2x2 table evaluates both *fixed*
    packages under COMMON_BK and COMMON_SPORTS_V3; it is not an in-sample arm
    comparison and makes no profitability or calibration claim.
    """

    settings = settings or SameEngineReplaySettings()
    paths = {
        "bk_top_product": _regular_file(bk_package_path),
        "sports_v3_top_product": _regular_file(sports_package_path),
        "frozen_predictions": _regular_file(predictions_path),
        "old_comparison": _regular_file(old_comparison_path),
    }
    output = Path(output_dir)
    if output.exists() and (not output.is_dir() or output.is_symlink()):
        raise ValueError("replay output directory must be a regular directory")
    if output.exists() and any(output.iterdir()):
        raise ValueError("replay output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)

    bk_package = _load_json(paths["bk_top_product"])
    sports_package = _load_json(paths["sports_v3_top_product"])
    prediction = _load_json(paths["frozen_predictions"])
    old_comparison = _load_json(paths["old_comparison"])
    bk_coupons = _coupons(bk_package, "BK top-product")
    sports_coupons = _coupons(sports_package, "Sports-v3 top-product")
    candidate_universe = tuple(dict.fromkeys((*bk_coupons, *sports_coupons)))
    if len(candidate_universe) < settings.max_coupons:
        raise ValueError("frozen candidate universe cannot fill requested package")

    bk_matrix, sports_matrix, statuses = _matrices(prediction)
    _validate_frozen_identity(
        bk_package,
        sports_package,
        prediction,
        old_comparison,
        bk_matrix,
        sports_matrix,
    )
    arms = {
        "BK": _select_arm(candidate_universe, bk_matrix, settings),
        "SPORTS_V3": _select_arm(candidate_universe, sports_matrix, settings),
    }
    selected = {name: result.selected_coupons for name, result in arms.items()}
    if any(len(coupons) != settings.max_coupons for coupons in selected.values()):
        raise RuntimeError("selector did not produce complete fixed research packages")
    expected_hashes = _old_hashes(old_comparison)
    hashes = {name: _coupon_hash(coupons) for name, coupons in selected.items()}
    recovered = hashes == expected_hashes
    classification = "ORIGINAL_SELECTION_RECOVERED" if recovered else "NEW_REPLICATION"

    universe_document = {
        **RESEARCH_CLASSIFICATION,
        "candidate_universe": list(candidate_universe),
        "candidate_count": len(candidate_universe),
        "order": "persisted_BK_then_persisted_MIXED_V3_first_occurrence",
        "coupon_order_sha256": _coupon_hash(candidate_universe),
    }
    matrices_document = {
        **RESEARCH_CLASSIFICATION,
        "COMMON_BK": bk_matrix,
        "COMMON_SPORTS_V3": sports_matrix,
        "sports_row_statuses": statuses,
        "sports_applied_count": statuses.count("SPORTS_APPLIED"),
        "bk_fallback_count": statuses.count("BK_FALLBACK"),
        "same_bk_fallback_across_arms": True,
    }
    selected_document = {
        **RESEARCH_CLASSIFICATION,
        "classification": classification,
        "expected_old_coupon_order_sha256": expected_hashes,
        "selected_coupon_arrays": {
            name: list(coupons) for name, coupons in selected.items()
        },
        "actual_coupon_order_sha256": hashes,
    }
    comparison = {
        **RESEARCH_CLASSIFICATION,
        "kind": "FROZEN_5008_SAME_ENGINE_REPLAY_V2",
        "classification": classification,
        "selection": {
            "candidate_count": len(candidate_universe),
            "candidate_universe_sha256": universe_document["coupon_order_sha256"],
            "settings": asdict(settings),
            "arms": {name: _selection_record(result) for name, result in arms.items()},
        },
        "common_fixed_package_p13_table": _common_p13_table(
            selected, bk_matrix, sports_matrix
        ),
        "limitations": [
            "2x2 values are exact conditional probabilities under the named common "
            "matrices, not empirical profitability or calibration.",
            "The frozen 293-candidate top-product union restricts both arms and is "
            "not the production 14,140-candidate quality-v3 universe.",
            "maximum_outcome_share=1.0 is recorded, not an exposure constraint; "
            "no explicit exposure constraints were used.",
            "Sports-v3 is nonblind retrospective sensitivity with frozen BK fallback; "
            "no promotion, operator eligibility, or wagering conclusion follows.",
        ],
    }
    inputs = {
        **RESEARCH_CLASSIFICATION,
        "source_paths": {name: str(path) for name, path in paths.items()},
        "source_sha256": {name: _sha256(path) for name, path in paths.items()},
        "final_input_file_sha256": prediction.get("final_input_file_sha256"),
        "final_input_snapshot_sha256": prediction.get("final_input_snapshot_sha256"),
        "prediction_payload_sha256": prediction.get("prediction_payload_sha256"),
        "frozen_model_file_sha256": prediction.get("model_file_sha256"),
    }
    _write(output / "candidate-universe.json", universe_document)
    _write(output / "probability-matrices.json", matrices_document)
    _write(output / "selected-packages.json", selected_document)
    _write(output / "inputs.json", inputs)
    _write(output / "settings.json", {**RESEARCH_CLASSIFICATION, **asdict(settings)})
    _write(output / "comparison.json", comparison)
    manifest = _manifest(output)
    _write(output / "hashmanifest.json", manifest)
    return comparison


def _select_arm(candidates, base_matrix, settings):
    models = {"base": base_matrix}
    for weight in settings.flatten_weights:
        models[f"flatten_{int(weight * 100):02d}"] = flatten_probabilities(
            base_matrix, weight=weight
        )
    return select_robust_package(
        candidates=candidates,
        probability_models=models,
        category=settings.category,
        max_coupons=settings.max_coupons,
        sample_count=settings.sample_count,
        seed_material=settings.seed_material,
        exposure_constraints=settings.exposure_constraints,
        fallback_coupons=(),
    )


def _common_p13_table(selected, bk_matrix, sports_matrix):
    return {
        package: {
            "COMMON_BK": exact_category_probabilities(coupons, bk_matrix)[0],
            "COMMON_SPORTS_V3": exact_category_probabilities(coupons, sports_matrix)[0],
        }
        for package, coupons in selected.items()
    }


def _selection_record(result: RobustPackageResult) -> dict[str, Any]:
    return {
        "coupon_count": len(result.selected_coupons),
        "coupon_order_sha256": _coupon_hash(result.selected_coupons),
        "candidate_count": result.candidate_count,
        "maximum_outcome_share": _maximum_outcome_share(result.selected_coupons),
        "worst_sampled_category_coverage": result.worst_sampled_category_coverage,
        "mean_sampled_category_coverage": result.mean_sampled_category_coverage,
        "timed_out": result.timed_out,
    }


def _matrices(prediction):
    rows = prediction.get("rows")
    if not isinstance(rows, list) or len(rows) != 15:
        raise ValueError("frozen predictions must contain exactly 15 rows")
    ordered = sorted(rows, key=lambda row: row.get("event_order"))
    if [row.get("event_order") for row in ordered] != list(range(15)):
        raise ValueError("frozen predictions have invalid event ordering")
    bk = tuple(
        tuple(float(value) for value in row["bk_probabilities"]) for row in ordered
    )
    sports = tuple(
        tuple(float(value) for value in row["probabilities"]) for row in ordered
    )
    statuses = [str(row.get("status")) for row in ordered]
    if statuses.count("SPORTS_APPLIED") != 12 or statuses.count("BK_FALLBACK") != 3:
        raise ValueError(
            "frozen prediction must retain 12 sports rows and 3 BK fallbacks"
        )
    if any(
        not math.isclose(sum(row), 1.0, rel_tol=0.0, abs_tol=1e-12)
        for row in (*bk, *sports)
    ):
        raise ValueError("probability rows must sum to one")
    return bk, sports, statuses


def _validate_frozen_identity(
    bk_package,
    sports_package,
    prediction,
    old,
    bk_matrix,
    sports_matrix,
):
    if bk_package.get("predictor_matrix_sha256") != prediction.get("rows", [{}])[0].get(
        "bk_input_sha256"
    ):
        raise ValueError("BK package is not bound to frozen predictions")
    sports_matrix_hash = selection_probability_input_sha256(sports_matrix)
    if sports_package.get("predictor_matrix_sha256") != sports_matrix_hash:
        raise ValueError("Sports package is not bound to frozen predictions")
    final = old.get("final_input", {})
    if final.get("file_sha256") != prediction.get(
        "final_input_file_sha256"
    ) or final.get("snapshot_sha256") != prediction.get("final_input_snapshot_sha256"):
        raise ValueError(
            "old comparison and frozen predictions do not share final input"
        )


def _old_hashes(old: Mapping[str, Any]) -> dict[str, str]:
    records = {
        str(row.get("arm")): row.get("coupon_order_sha256")
        for row in old.get("arms", [])
    }
    result = {"BK": records.get("BK"), "SPORTS_V3": records.get("SPORTS_V3")}
    if not all(
        isinstance(value, str) and len(value) == 64 for value in result.values()
    ):
        raise ValueError("old comparison does not contain both exact package hashes")
    return result  # type: ignore[return-value]


def _coupons(document: Mapping[str, Any], label: str) -> tuple[str, ...]:
    coupons = document.get("coupons")
    if (
        not isinstance(coupons, list)
        or not coupons
        or any(not isinstance(item, str) for item in coupons)
    ):
        raise ValueError(f"{label} must contain coupon strings")
    return tuple(coupons)


def _maximum_outcome_share(coupons: Sequence[str]) -> float:
    return max(
        sum(coupon[event] == outcome for coupon in coupons) / len(coupons)
        for event in range(len(coupons[0]))
        for outcome in "1X2"
    )


def _regular_file(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"required source must be a regular file: {path}")
    return path


def _load_json(path: Path) -> Mapping[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"JSON object required: {path}")
    return document


def _coupon_hash(coupons: Sequence[str]) -> str:
    return hashlib.sha256(",".join(coupons).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest(output: Path) -> dict[str, Any]:
    files = sorted(path for path in output.iterdir() if path.is_file())
    return {
        **RESEARCH_CLASSIFICATION,
        "files": {path.name: _sha256(path) for path in files},
    }
