"""Research-only same-input fixed-bank coverage comparison.

This is an independent greedy baseline inspired by documented coverage ideas.
It does not reconstruct an external algorithm, register an operator strategy, or
produce an uploadable package.  It deliberately reads only the sealed
closed-market scenario input and never reads target labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from toto_ai.optimizer.cover import (
    category_max_errors,
    expand_brief,
    greedy_cover,
    verify_cover_package,
)
from toto_ai.research.closed_market_scenario_replay import (
    DOMAIN,
    file_hash,
    validate_input,
    verify_frozen,
)
from toto_ai.research.package_selection_diagnostics import evaluate_fixed_package

OUTCOMES = ("1", "X", "2")
CATEGORY = 13
BANK_RUB = 4980
STAKE_RUB = 30
COUPON_COUNT = 166
SEED_PREFIX = "TOTOAI-RESUME-20260915-fixed-bank-coverage-v1"
DIAGNOSTIC_SEMANTICS = {
    "distinct_forecast_count": 1,
    "reference_model": "common_bk",
    "api_aliases": {"common_bk_duplicate": "common_bk"},
    "alias_purpose": "Identical BK control matrix required by evaluator API arity",
    "alias_results_combined": False,
    "training_stream_used_by_greedy": False,
    "training_fields_meaning": (
        "training_* fields describe diagnostic-only Monte Carlo streams; "
        "greedy selection uses enumerated variants, not these samples. "
        "Aliases are not independent forecasts or optimizer-overfit measurements."
    ),
}


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError("coverage pilot exceeded max_seconds")


def _matrix(matrix: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    result = tuple(tuple(float(value) for value in row) for row in matrix)
    if len(result) != 15 or any(len(row) != 3 for row in result):
        raise ValueError("fifteen three-outcome probability rows required")
    if any(not math.isfinite(value) or value <= 0 for row in result for value in row):
        raise ValueError("probabilities must be finite and positive")
    return result


def build_restricted_brief(matrix: Sequence[Sequence[float]]) -> list[str]:
    """Expand six highest-entropy BK positions; fix every other position."""
    probabilities = _matrix(matrix)
    entropies = [
        -sum(value * math.log(value) for value in row) for row in probabilities
    ]
    expanded = {
        index
        for index in sorted(range(15), key=lambda index: (-entropies[index], index))[:6]
    }
    return [
        "1X2" if index in expanded else OUTCOMES[max(range(3), key=row.__getitem__)]
        for index, row in enumerate(probabilities)
    ]


def _coupon_probability(coupon: str, matrix: tuple[tuple[float, ...], ...]) -> float:
    indexes = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    return math.prod(
        matrix[index][indexes[outcome]] for index, outcome in enumerate(coupon)
    )


def _coverage_metrics(
    coupons: Sequence[str],
    variants: Sequence[str],
    weights: dict[str, float],
) -> dict[str, Any]:
    max_errors = category_max_errors(CATEGORY)
    covered = {
        index
        for index, variant in enumerate(variants)
        if any(
            sum(left != right for left, right in zip(coupon, variant, strict=True))
            <= max_errors
            for coupon in coupons
        )
    }
    total_mass = sum(weights.values())
    covered_mass = sum(weights[variants[index]] for index in covered)
    return {
        "covered_variants_count": len(covered),
        "coverage_rate": len(covered) / len(variants),
        "conditional_brief_mass_coverage_fraction": covered_mass / total_mass
        if total_mass
        else 0.0,
        "brief_mass_total": total_mass,
        "constraint_diagnostics": verify_cover_package(
            list(variants_to_brief(variants)), CATEGORY, list(coupons)
        ),
    }


def variants_to_brief(variants: Sequence[str]) -> tuple[str, ...]:
    """Recover the fixed/expanded positions from an ordered nonempty universe."""
    if not variants:
        raise ValueError("candidate universe cannot be empty")
    return tuple(
        "".join(
            outcome
            for outcome in OUTCOMES
            if any(v[index] == outcome for v in variants)
        )
        for index in range(15)
    )


def select_fixed_bank_packages(
    brief: Sequence[str],
    probability_matrix: Sequence[Sequence[float]],
    *,
    coupon_count: int = COUPON_COUNT,
) -> dict[str, Any]:
    """Choose two deterministic 166-unique-coupon baselines in one universe."""
    if coupon_count != COUPON_COUNT:
        raise ValueError("fixed-bank comparison requires exactly 166 coupons")
    probabilities = _matrix(probability_matrix)
    normalized_brief = list(brief)
    if len(normalized_brief) != 15:
        raise ValueError("brief requires fifteen positions")
    variants = expand_brief(normalized_brief)
    if len(variants) < coupon_count:
        raise ValueError("candidate universe cannot supply 166 unique coupons")
    weights = {
        variant: _coupon_probability(variant, probabilities) for variant in variants
    }
    fill_order = sorted(variants, key=lambda coupon: (-weights[coupon], coupon))

    arms: dict[str, Any] = {}
    for name, greedy_weights in (("weighted", weights), ("unweighted", None)):
        greedy = greedy_cover(
            normalized_brief,
            category=CATEGORY,
            max_coupons=COUPON_COUNT,
            weights=greedy_weights,
        )
        greedy_coupons = tuple(greedy["selected_coupons"])
        coupons = (
            greedy_coupons
            + tuple(
                coupon for coupon in fill_order if coupon not in set(greedy_coupons)
            )[: COUPON_COUNT - len(greedy_coupons)]
        )
        if len(coupons) != COUPON_COUNT or len(set(coupons)) != COUPON_COUNT:
            raise ValueError("deterministic fill failed to produce 166 unique coupons")
        arms[name] = {
            "greedy_coupons": greedy_coupons,
            "coupons": coupons,
            "greedy_count": len(greedy_coupons),
            "fill_count": COUPON_COUNT - len(greedy_coupons),
            "category": CATEGORY,
            "max_errors": category_max_errors(CATEGORY),
            **_coverage_metrics(coupons, variants, weights),
        }
    return {"variant_count": len(variants), "brief": tuple(normalized_brief), **arms}


def _load_verified_scenario(input_path: Path) -> tuple[Any, dict[str, Any]]:
    document = json.loads(input_path.read_text(encoding="utf-8"))
    scenario = validate_input(document)
    root = input_path.parent
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    roster = next(
        (
            row
            for row in manifest.get("roster", [])
            if row.get("drawing") == scenario.ev.drawing_number
        ),
        None,
    )
    if (
        roster is None
        or roster.get("input") != input_path.name
        or roster.get("input_file_sha256") != file_hash(input_path)
        or roster.get("input_sha256") != scenario.input_sha256
    ):
        raise ValueError("scenario manifest/input binding mismatch")
    frozen, _ = verify_frozen(root / f"drawing-{scenario.ev.drawing_number}")
    if frozen["input_sha256"] != scenario.input_sha256:
        raise ValueError("frozen receipt/input binding mismatch")
    return scenario, {
        "manifest_sha256": file_hash(root / "manifest.json"),
        "frozen_sha256": frozen["sha256"],
    }


def _write_reports(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "arm",
                "greedy_count",
                "fill_count",
                "coverage_rate",
                "conditional_brief_mass_coverage_fraction",
                "brief_mass_total",
                "exact_union_p13",
                "exact_union_p14",
                "exact_union_p15",
            ),
        )
        writer.writeheader()
        for arm in report["arms"]:
            selection, exact = arm["selection"], arm["exact_union"]
            writer.writerow(
                {
                    "arm": arm["name"],
                    "greedy_count": selection["greedy_count"],
                    "fill_count": selection["fill_count"],
                    "coverage_rate": selection["coverage_rate"],
                    "conditional_brief_mass_coverage_fraction": selection[
                        "conditional_brief_mass_coverage_fraction"
                    ],
                    "brief_mass_total": selection["brief_mass_total"],
                    **exact,
                }
            )
    lines = [
        "# Fixed-bank coverage pilot (research only)",
        "",
        "**POST-EVENT MARKET SCENARIO ONLY — NOT FOR WAGERING OR UPLOAD.**",
        "",
        f"Input SHA-256: `{report.get('input_sha256', 'unavailable')}`  ",
        f"Seed: `{report.get('seed', 'unavailable')}`  ",
        f"Wall seconds: `{report['timing']['wall_seconds']:.3f}`",
        "",
        "Both arms use the same 729-variant restricted candidate universe and "
        "the same independent-event BK probability matrix. P(13+) is an exact "
        "coupon-union probability under that model, not a sum of coupon probabilities.",
        "",
        "| arm | greedy | fill | variant coverage | "
        "conditional covered mass fraction | "
        "unconditional brief probability | union P(13+) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in report["arms"]:
        selection, exact = arm["selection"], arm["exact_union"]
        lines.append(
            f"| {arm['name']} | {selection['greedy_count']} | "
            f"{selection['fill_count']} | {selection['coverage_rate']:.6f} | "
            f"{selection['conditional_brief_mass_coverage_fraction']:.6f} | "
            f"{selection['brief_mass_total']:.12g} | "
            f"{exact['exact_union_p13']:.12g} |"
        )
    lines += [
        "",
        "Conditional covered mass fraction is P(covered | outcome in brief). "
        "The unconditional brief probability is brief_mass_total (multiply by 100 "
        "for percent). "
        "Full-space Hamming unions also contain outcomes outside the brief, "
        "so their P(13+) can differ despite complete restricted coverage.",
        "",
        "There is one distinct BK forecast. common_bk_duplicate is an identical "
        "control-matrix alias satisfying evaluator API arity; alias results are "
        "not combined. training_* fields are diagnostic-only Monte Carlo streams "
        "unused by greedy selection, which enumerates candidates. These streams "
        "do not measure greedy training overfit or independent forecasts.",
        "",
        "`INDEPENDENT_WEIGHTED_GREEDY_BASELINE` and "
        "`INDEPENDENT_UNWEIGHTED_GREEDY_BASELINE` are native heuristics, not "
        "optimality proofs or replication claims.",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_comparison(
    input_path: str | Path, output_dir: str | Path, max_seconds: int = 60
) -> dict[str, Any]:
    """Run the one bounded 4999 research pilot and save machine/human receipts."""
    if type(max_seconds) is not int or not 1 <= max_seconds <= 60:
        raise ValueError("max_seconds must be an integer from 1 to 60")
    started = time.monotonic()
    deadline = started + max_seconds
    input_file, output = Path(input_path), Path(output_dir)
    try:
        scenario, bindings = _load_verified_scenario(input_file)
        _check_deadline(deadline)
        if (
            scenario.ev.drawing_number != 4999
            or scenario.config.bank != BANK_RUB
            or scenario.config.stake != STAKE_RUB
        ):
            raise ValueError("only frozen drawing 4999 at 4980/30 is admitted")
        matrix = scenario.ev.true_probabilities
        brief = build_restricted_brief(matrix)
        selected = select_fixed_bank_packages(brief, matrix)
        _check_deadline(deadline)
        seed = hashlib.sha256(
            f"{SEED_PREFIX}\0{scenario.input_sha256}".encode()
        ).hexdigest()
        evaluations = {
            name: evaluate_fixed_package(
                coupons=arm["coupons"],
                # The diagnostic helper deliberately requires two named models.
                # They are byte-identical here so both arms share one BK measure.
                probability_models={
                    "common_bk": matrix,
                    "common_bk_duplicate": matrix,
                },
                category=CATEGORY,
                selection_seed_material=seed,
                selection_sample_count=10_000,
                evaluation_sample_count=10_000,
            )
            for name, arm in (
                ("weighted", selected["weighted"]),
                ("unweighted", selected["unweighted"]),
            )
        }
        _check_deadline(deadline)
        arms = []
        for name, label in (
            ("weighted", "INDEPENDENT_WEIGHTED_GREEDY_BASELINE"),
            ("unweighted", "INDEPENDENT_UNWEIGHTED_GREEDY_BASELINE"),
        ):
            model = evaluations[name].models[0]
            selection = {
                key: value
                for key, value in selected[name].items()
                if key not in {"coupons", "greedy_coupons", "constraint_diagnostics"}
            }
            arms.append(
                {
                    "name": label,
                    "coupon_order_sha256": evaluations[name].coupon_order_sha256,
                    "selection": selection,
                    "exact_union": {
                        "exact_union_p13": model.exact_p13,
                        "exact_union_p14": model.exact_p14,
                        "exact_union_p15": model.exact_p15,
                    },
                    "diagnostic": asdict(evaluations[name]),
                }
            )
        report = {
            "status": "COMPLETE_RESEARCH_ONLY",
            "failure": None,
            "evidence_domain": DOMAIN,
            "drawing": scenario.ev.drawing_number,
            "drawing_id": scenario.ev.drawing_id,
            "input_sha256": scenario.input_sha256,
            "input_file_sha256": file_hash(input_file),
            "seed": seed,
            "manifest_sha256": bindings["manifest_sha256"],
            "frozen_sha256": bindings["frozen_sha256"],
            "bank_rub": BANK_RUB,
            "stake_rub": STAKE_RUB,
            "coupon_count": COUPON_COUNT,
            "candidate_universe": {
                "brief": selected["brief"],
                "variant_count": selected["variant_count"],
                "scope": "six-highest-BK-entropy positions only",
            },
            "diagnostic_semantics": DIAGNOSTIC_SEMANTICS,
            "metric_definition": (
                "exact independent-event BK coupon-union P13+/P14+/P15; "
                "never sum coupon probabilities"
            ),
            "operator_compatible": False,
            "activation_allowed": False,
            "automatic_wagering": False,
            "timing": {
                "max_seconds": max_seconds,
                "wall_seconds": time.monotonic() - started,
            },
            "arms": arms,
        }
    except Exception as error:
        report = {
            "status": "TIMEOUT_PARTIAL"
            if isinstance(error, TimeoutError)
            else "FAILED_NO_SELECTION_CLAIM",
            "failure": f"{type(error).__name__}: {error}",
            "operator_compatible": False,
            "activation_allowed": False,
            "automatic_wagering": False,
            "timing": {
                "max_seconds": max_seconds,
                "wall_seconds": time.monotonic() - started,
            },
        }
        _write_reports(output, {**report, "arms": []})
        return report
    _write_reports(output, report)
    return report
