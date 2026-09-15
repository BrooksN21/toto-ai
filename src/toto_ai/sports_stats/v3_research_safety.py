"""Independent native safety/provenance checks; never operator eligibility."""

import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from toto_ai.ev.models import EVConfig
from toto_ai.ev.package_quality import (
    PackageSelectionProvenance,
    continuous_exposure_lower_bounds,
    exact_category_probabilities,
    validate_selection_provenance,
)
from toto_ai.package.audit import evaluate_package_safety, validate_coupons
from toto_ai.sports_stats.v3_probability import (
    _bk,
    _check,
    _hash,
    _sealed,
    digest,
    seal,
)


def concentration(coupons):
    counts = [
        [sum(c[i] == outcome for c in coupons) for outcome in "1X2"] for i in range(15)
    ]
    shares = [[c / len(coupons) for c in row] for row in counts]
    hhi = [math.fsum(p * p for p in row) for row in shares]
    return {
        "counts": counts,
        "max_outcome_share": max(max(r) for r in shares),
        "mean_hhi": math.fsum(hhi) / 15,
        "max_hhi": max(hhi),
        "zero_exposure_count": sum(c == 0 for row in counts for c in row),
    }


def audit_research_candidate(coupons, *, controls, probabilities, config):
    coupons = validate_coupons(coupons)
    _check(
        set(controls) == {"quality-v2", "robust"}, "both immutable controls required"
    )
    _check(0 < len(coupons) == config.max_coupons <= 512, "exact candidate capacity")
    _check(
        bool(probabilities) and "BK" in probabilities, "exact BK safety model required"
    )
    controls = {name: validate_coupons(values) for name, values in controls.items()}
    _check(
        all(len(v) == len(coupons) for v in controls.values()), "equal control capacity"
    )
    own = concentration(coupons)
    control_stats = {name: concentration(values) for name, values in controls.items()}
    bounds_pass = all(
        own["max_outcome_share"] <= c["max_outcome_share"]
        and own["max_hhi"] <= c["max_hhi"]
        for c in control_stats.values()
    )
    hard_count = math.ceil(config.package_near_fixed_share * len(coupons)) - 1
    hard_cap = all(n <= hard_count for row in own["counts"] for n in row)
    models = {}
    for name, rows in probabilities.items():
        _check(len(rows) == 15, "15 safety probability rows")
        rows = tuple(_bk(r) for r in rows)
        native = evaluate_package_safety(
            coupons, rows, config=config.package_safety_config
        )
        floors = [
            continuous_exposure_lower_bounds(
                row,
                package_size=len(coupons),
                scale=config.package_exposure_floor_scale,
                exponent=config.package_exposure_floor_exponent,
            )
            for row in rows
        ]
        floor_ok = all(
            n >= minimum
            for counts, limits in zip(own["counts"], floors, strict=True)
            for n, minimum in zip(counts, limits, strict=True)
        )
        candidate = exact_category_probabilities(coupons, rows)
        comparisons = {}
        for control, values in controls.items():
            baseline = exact_category_probabilities(values, rows)
            comparisons[control] = {
                "probability_at_least_13_14_15": list(baseline),
                "non_degrading": all(
                    a + 1e-12 >= b for a, b in zip(candidate, baseline, strict=True)
                ),
            }
        models[name] = {
            "probability_input_sha256": digest(rows),
            "candidate_probability_at_least_13_14_15": list(candidate),
            "controls": comparisons,
            "native_safety_pass": native.decision == "PLAY",
            "native_reason_codes": list(native.reason_codes),
            "native_safety_sha256": native.safety_sha256,
            "continuous_exposure_floors": floors,
            "exposure_floors_pass": floor_ok,
        }
    passed = (
        bounds_pass
        and hard_cap
        and own["zero_exposure_count"] == 0
        and all(
            m["native_safety_pass"]
            and m["exposure_floors_pass"]
            and all(c["non_degrading"] for c in m["controls"].values())
            for m in models.values()
        )
    )
    overlaps = {
        name: {
            "intersection": len(set(coupons) & set(values)),
            "jaccard": len(set(coupons) & set(values))
            / len(set(coupons) | set(values)),
        }
        for name, values in controls.items()
    }
    return seal(
        {
            "kind": "SPORTS_V3_INDEPENDENT_RESEARCH_SAFETY",
            "research_checks_passed": passed,
            "ordered_package_sha256": digest(coupons),
            "control_hashes": {k: digest(v) for k, v in controls.items()},
            "config_sha256": digest(asdict(config)),
            "concentration": own,
            "control_concentration": control_stats,
            "control_relative_bounds_pass": bounds_pass,
            "hard_concentration_cap_pass": hard_cap,
            "hard_maximum_count": hard_count,
            "models": models,
            "package_overlaps": overlaps,
            "scope": "EXISTING_GENERATOR_RESEARCH_NOT_ROBUST_V2_HISTORICAL_ACCEPTANCE",
            "control_preserved": True,
            "operator_compatible": False,
            "automatic_wagering": False,
            "activation_allowed": False,
        }
    )


def validate_research_provenance(
    payload,
    *,
    probabilities,
    config,
    expected_config_sha256,
    expected_plan_sha256,
    expected_probability_snapshot_sha256,
    expected_model_sha256=None,
    expected_final_input_sha256=None,
):
    _check(isinstance(payload, dict), "independent research provenance required")
    for value in (
        expected_config_sha256,
        expected_plan_sha256,
        expected_probability_snapshot_sha256,
        expected_model_sha256,
        expected_final_input_sha256,
    ):
        _hash(value)
    resolved = EVConfig(**config)
    _check(
        resolved.package_safety_enabled and resolved.package_provenance_required,
        "research provenance/safety config required",
    )
    _check(
        digest(asdict(resolved)) == expected_config_sha256, "exact EV config receipt"
    )
    provenance = PackageSelectionProvenance(**payload)
    _check(
        provenance.scheduler_plan_sha256 == expected_plan_sha256
        and provenance.probability_snapshot_sha256
        == expected_probability_snapshot_sha256,
        "research provenance plan/probability binding",
    )
    for name in (
        "probability_snapshot_path",
        "schedule_evidence_ledger_path",
        "scheduler_plan_path",
    ):
        value = getattr(provenance, name)
        _check(isinstance(value, str), "research provenance path missing")
        path = Path(value)
        _check(
            path.suffix == ".json"
            and not any(p.is_symlink() for p in (path, *path.parents))
            and path.is_file()
            and path.stat().st_size <= 2_000_000,
            "bounded JSON provenance artifact",
        )
    raw = Path(provenance.probability_snapshot_path).read_bytes()
    _check(
        hashlib.sha256(raw).hexdigest() == expected_probability_snapshot_sha256,
        "research probability artifact exact bytes",
    )
    snapshot = json.loads(raw)
    _sealed(snapshot)
    _check(
        snapshot.get("kind") == "SPORTS_V3_RESEARCH_PROBABILITY_INPUT"
        and snapshot.get("model_sha256") == expected_model_sha256
        and snapshot.get("final_input_sha256") == expected_final_input_sha256
        and snapshot.get("probability_input_sha256") == digest(probabilities)
        and snapshot.get("probabilities") == [list(r) for r in probabilities]
        and snapshot.get("operator_compatible") is False
        and snapshot.get("automatic_wagering") is False,
        "actual V3 probability projection",
    )
    complete, reasons, _, _ = validate_selection_provenance(
        provenance, probabilities, config=resolved, required=True
    )
    _check(complete and not reasons, "native provenance: " + ",".join(reasons))
    return provenance
