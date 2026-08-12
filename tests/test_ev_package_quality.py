import hashlib
import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import toto_ai.ev.package as package_module
from toto_ai.ev.models import EVConfig, EVSurface
from toto_ai.ev.package import select_ev_package
from toto_ai.ev.package_quality import (
    EVALUATION_MC_STREAM,
    OPTIMIZATION_MC_STREAM,
    ExactCategoryCoverage,
    PackageSelectionProvenance,
    bound_selection_context,
    continuous_exposure_lower_bounds,
    deterministic_outcome_samples,
    exact_category_probabilities,
    package_quality_metrics,
    quality_v2_config_payload,
    selection_context_sha256,
    selection_probability_input_sha256,
    validate_selection_provenance,
)
from toto_ai.ev.ternary import coupon_from_index

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _surface(values, event_count):
    return EVSurface(
        gross_ev=np.array(values, dtype=np.float64),
        event_count=event_count,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def _provenance(probabilities, tmp_path, config):
    tmp_path.mkdir(parents=True, exist_ok=True)
    probability_hash = selection_probability_input_sha256(probabilities)
    snapshot_path = tmp_path / "probability-snapshot.json"
    snapshot_path.write_text(
        json.dumps({"probability_input_sha256": probability_hash}),
        encoding="utf-8",
    )
    plan_path = tmp_path / "scheduler-plan.json"
    _write_test_scheduler_plan(plan_path, config=config)
    return PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=snapshot_path,
        probability_input_sha256=probability_hash,
        schedule_evidence_ledger_path=(
            PROJECT_ROOT / "data" / "schedule-evidence" / "ledger.json"
        ),
        scheduler_plan_path=plan_path,
        selection_config=config,
    )


def _write_test_scheduler_plan(path: Path, *, config: EVConfig) -> None:
    semantic = {
        "schema_version": 6,
        "target": {"drawing": 0, "drawing_id": 0, "ended_at": "test"},
        "config": {
            "quality_v2": quality_v2_config_payload(config),
            "selection_context": bound_selection_context(config),
            "selection_context_sha256": selection_context_sha256(config),
        },
        "paths": {},
    }
    document = {
        **semantic,
        "plan_id": hashlib.sha256(
            json.dumps(
                semantic,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:16],
        "deadlines": {},
    }
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")


def _paper_coupons(package):
    assert package.decision == "NO BET"
    assert package.structural_status == "STRUCTURAL_PASS"
    assert package.artifact_class == "TRAINING/PAPER"
    assert package.coupons == ()
    return package.paper_coupons


def test_continuous_exposure_floor_is_monotonic_and_sum_feasible():
    rows = [
        continuous_exposure_lower_bounds(
            (probability, 1.0 - probability, 0.0),
            package_size=166,
            scale=0.15,
            exponent=1.0,
        )
        for probability in (0.05, 0.10, 0.199999, 0.20, 0.200001, 0.40)
    ]

    assert [row[0] for row in rows] == sorted(row[0] for row in rows)
    assert rows[2][0] == rows[3][0] == rows[4][0]
    assert rows[3][0] > 1
    assert all(sum(row) <= 166 for row in rows)


def test_continuous_exposure_floor_rejects_globally_infeasible_configuration():
    with pytest.raises(ValueError, match="sum-feasible"):
        continuous_exposure_lower_bounds(
            (0.34, 0.33, 0.33),
            package_size=10,
            scale=1.1,
            exponent=1.0,
        )


def test_exposure_floor_uses_named_ieee754_floor_boundary_without_epsilon():
    exact = continuous_exposure_lower_bounds(
        (0.20, 0.50, 0.30),
        package_size=100,
        scale=0.50,
        exponent=1.0,
    )
    just_below = 0.20 - 1e-12
    below = continuous_exposure_lower_bounds(
        (just_below, 0.50 + (0.20 - just_below), 0.30),
        package_size=100,
        scale=0.50,
        exponent=1.0,
    )

    assert exact[0] == 10
    assert below[0] == 9
    assert quality_v2_config_payload(EVConfig(bank=90))[
        "exposure_boundary_policy"
    ] == "ieee754_floor_without_epsilon"


def test_quality_metrics_expose_hamming_distribution_and_category_metrics():
    probabilities = ((1.0, 0.0, 0.0),) * 15
    metrics = package_quality_metrics(
        ("1" * 15, "X" + "1" * 14, "2" * 15),
        probabilities,
        seed_material="4" * 64,
        monte_carlo_samples=2_000,
    )

    assert metrics.pairwise_distance_distribution == ((1, 1), (15, 2))
    assert metrics.close_pair_count == 1
    assert metrics.minimum_pairwise_hamming == 1
    assert metrics.mean_pairwise_hamming == pytest.approx(31 / 3)
    assert 1.0 <= metrics.effective_pattern_count <= 3.0
    assert metrics.probability_at_least_9 == 1.0
    assert metrics.probability_at_least_13 == 1.0
    assert metrics.probability_at_least_14 == 1.0
    assert metrics.probability_at_least_15 == 1.0
    assert metrics.probability_9_method == "deterministic_monte_carlo"
    assert metrics.probability_13_15_method == "exact_hamming_union"
    assert metrics.monte_carlo_samples == 2_000
    assert metrics.monte_carlo_worst_case_95_error < 0.023


def test_quality_metrics_are_deterministic_for_bound_seed():
    probabilities = ((0.45, 0.35, 0.20),) * 15
    coupons = ("1" * 15, "X" * 15, "2" * 15)

    first = package_quality_metrics(
        coupons,
        probabilities,
        seed_material="5" * 64,
        monte_carlo_samples=1_000,
    )
    second = package_quality_metrics(
        coupons,
        probabilities,
        seed_material="5" * 64,
        monte_carlo_samples=1_000,
    )

    assert first == second


def test_incremental_exact_category_coverage_matches_full_union_after_swap():
    probabilities = tuple(
        (0.46 - event / 1_000, 0.31 + event / 2_000, 0.23 + event / 2_000)
        for event in range(15)
    )
    coupons = ("1" * 15, "X" * 15, "2" * 15, "1X2" * 5)
    outgoing = coupons[1]
    incoming = "X21" * 5
    expected_after = tuple(coupon for coupon in coupons if coupon != outgoing) + (
        incoming,
    )
    coverage = ExactCategoryCoverage(coupons, probabilities)

    assert coverage.probabilities == pytest.approx(
        exact_category_probabilities(coupons, probabilities),
        abs=1e-15,
    )
    assert coverage.probabilities_after_swap(outgoing, incoming) == pytest.approx(
        exact_category_probabilities(expected_after, probabilities),
        abs=1e-15,
    )

    coverage.apply_swap(outgoing, incoming)

    assert coverage.probabilities == pytest.approx(
        exact_category_probabilities(expected_after, probabilities),
        abs=1e-15,
    )


def test_lexicographic_category_objective_never_trades_p13_for_lower_tiers():
    baseline = (0.020, 0.0020, 0.00020, 0.20, 0.1, 1.0)
    lower_p13_with_huge_lower_tiers = (0.019, 1.0, 1.0, 1.0, 1.0, 1e9)
    tolerances = (1e-12,) * 6

    assert (
        package_module._compare_quality_objectives(
            lower_p13_with_huge_lower_tiers,
            baseline,
            tolerances,
        )
        < 0
    )


@pytest.mark.parametrize("higher_tier", range(4))
def test_no_lower_priority_gain_compensates_meaningful_category_loss(higher_tier):
    baseline = [0.020, 0.0020, 0.00020, 0.20, 0.1, 1.0]
    candidate = baseline.copy()
    candidate[higher_tier] -= 2e-12
    for lower_tier in range(higher_tier + 1, len(candidate)):
        candidate[lower_tier] = 1e12

    assert package_module._compare_quality_objectives(
        tuple(candidate), tuple(baseline), (1e-12,) * 6
    ) < 0


@pytest.mark.parametrize("tier", range(6))
def test_lexicographic_objective_advances_each_tier_only_after_higher_ties(tier):
    baseline = (0.020, 0.0020, 0.00020, 0.20, 0.1, 1.0)
    candidate = list(baseline)
    candidate[tier] += 2e-12

    assert (
        package_module._compare_quality_objectives(
            tuple(candidate), baseline, (1e-12,) * 6
        )
        > 0
    )


def test_mc_optimization_and_evaluation_streams_are_domain_separated():
    probabilities = ((0.45, 0.35, 0.20),) * 15
    optimization, optimization_seed = deterministic_outcome_samples(
        probabilities,
        seed_material="7" * 64,
        sample_count=512,
        stream=OPTIMIZATION_MC_STREAM,
    )
    evaluation, evaluation_seed = deterministic_outcome_samples(
        probabilities,
        seed_material="7" * 64,
        sample_count=512,
        stream=EVALUATION_MC_STREAM,
    )

    assert optimization_seed != evaluation_seed
    assert not np.array_equal(optimization, evaluation)


def test_selector_uses_soft_headroom_and_reports_no_headroom_violations(tmp_path):
    values = np.linspace(100.0, 1.0, 27)
    probabilities = ((0.60, 0.25, 0.15),) * 3
    config = EVConfig(
        bank=270,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_concentration_headroom_share=0.20,
        package_quality_repair_iterations=0,
        package_provenance_required=True,
    )

    package = select_ev_package(
        _surface(values, 3),
        config,
        probabilities=probabilities,
        provenance=_provenance(probabilities, tmp_path, config),
    )

    diagnostics = package.selection_diagnostics
    assert len(_paper_coupons(package)) == 9
    assert diagnostics is not None
    assert diagnostics.concentration_headroom_count > 0
    assert diagnostics.headroom_violation_count == 0
    assert all(
        exposure.maximum_count <= diagnostics.concentration_soft_maximum_count
        for exposure in diagnostics.post_exposures
    )


def test_selector_diversity_repair_reduces_close_hamming_clusters():
    values = np.ones(3**5)
    # Make a deliberately clustered high-EV prefix around base-three index zero.
    values[:40] = np.linspace(100.0, 61.0, 40)
    probabilities = ((1 / 3, 1 / 3, 1 / 3),) * 5
    base = dict(
        bank=360,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_concentration_headroom_share=0.0,
    )

    clustered = select_ev_package(
        _surface(values, 5),
        EVConfig(**base, package_quality_repair_iterations=0),
        probabilities=probabilities,
    )
    diversified = select_ev_package(
        _surface(values, 5),
        EVConfig(**base, package_quality_repair_iterations=12),
        probabilities=probabilities,
    )

    before = clustered.selection_diagnostics
    after = diversified.selection_diagnostics
    assert before is not None and after is not None
    assert (
        after.post_diversity.close_pair_count < before.post_diversity.close_pair_count
    )
    assert (
        after.post_diversity.effective_pattern_count
        > before.post_diversity.effective_pattern_count
    )
    assert after.constraint_feasible is True


@pytest.mark.parametrize(
    ("bank", "stake"),
    [(4_980, 30), (9_960, 30), (2_500, 25)],
)
def test_quality_selector_preserves_full_dynamic_exact_unique_coupon_count(
    bank,
    stake,
):
    probabilities = ((1 / 3, 1 / 3, 1 / 3),) * 6
    rng = np.random.default_rng(4971)
    values = rng.permutation(np.arange(1, 3**6 + 1)).astype(np.float64)
    package = select_ev_package(
        _surface(values, 6),
        EVConfig(
            bank=bank,
            stake=stake,
            mode="playable",
            min_gross_ev=0.0,
            package_safety_enabled=True,
            package_near_fixed_share=1.0,
            package_quality_repair_iterations=1,
            package_quality_candidate_count=64,
        ),
        probabilities=probabilities,
    )

    coupons = _paper_coupons(package)
    assert len(coupons) == bank // stake
    assert len({row.coupon for row in coupons}) == bank // stake
    assert package.paper_cost == bank


def test_nested_larger_paper_package_cannot_reduce_modeled_category_unions():
    universe_size = 3**15
    coupons = tuple(
        coupon_from_index((index * 104_729) % universe_size, 15)
        for index in range(332)
    )
    probabilities = tuple(
        (0.46 - event / 1_000, 0.31 + event / 2_000, 0.23 + event / 2_000)
        for event in range(15)
    )
    small = package_quality_metrics(
        coupons[:166],
        probabilities,
        seed_material="8" * 64,
        monte_carlo_samples=2_048,
    )
    large = package_quality_metrics(
        coupons,
        probabilities,
        seed_material="8" * 64,
        monte_carlo_samples=2_048,
    )

    assert large.probability_at_least_9 >= small.probability_at_least_9
    assert large.probability_at_least_13 >= small.probability_at_least_13
    assert large.probability_at_least_14 >= small.probability_at_least_14
    assert large.probability_at_least_15 >= small.probability_at_least_15


def test_selector_fails_closed_on_missing_or_mismatched_provenance():
    probabilities = ((0.50, 0.30, 0.20),) * 3
    config = EVConfig(
        bank=90,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_provenance_required=True,
    )

    missing = select_ev_package(
        _surface(np.linspace(10.0, 1.0, 27), 3),
        config,
        probabilities=probabilities,
    )
    mismatched = select_ev_package(
        _surface(np.linspace(10.0, 1.0, 27), 3),
        config,
        probabilities=probabilities,
        provenance=PackageSelectionProvenance(
            probability_snapshot_sha256="1" * 64,
            probability_input_sha256="f" * 64,
            schedule_evidence_ledger_sha256="2" * 64,
            schedule_evidence_semantic_hash="3" * 64,
        ),
    )

    assert missing.decision == mismatched.decision == "NO BET"
    assert missing.coupons == mismatched.coupons == ()
    assert missing.selection_diagnostics.infeasibility_reasons == (
        "selection_provenance_missing",
    )
    assert mismatched.selection_diagnostics.infeasibility_reasons == (
        "probability_input_sha256_mismatch",
    )
    assert missing.selection_diagnostics.provenance_complete is False
    assert mismatched.selection_diagnostics.provenance_complete is False


def test_selector_rejects_arbitrary_or_mutated_plan_artifacts(tmp_path):
    probabilities = ((0.50, 0.30, 0.20),) * 3
    surface = _surface(np.linspace(10.0, 1.0, 27), 3)
    config = EVConfig(
        bank=90,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_provenance_required=True,
    )

    arbitrary = _provenance(probabilities, tmp_path / "arbitrary", config)
    Path(arbitrary.scheduler_plan_path).write_text(
        '{"plan":"self-declared"}', encoding="utf-8"
    )
    arbitrary = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=arbitrary.probability_snapshot_path,
        probability_input_sha256=arbitrary.probability_input_sha256,
        schedule_evidence_ledger_path=arbitrary.schedule_evidence_ledger_path,
        scheduler_plan_path=arbitrary.scheduler_plan_path,
        selection_config=config,
    )
    rejected_arbitrary = select_ev_package(
        surface,
        config,
        probabilities=probabilities,
        provenance=arbitrary,
    )

    mutation_root = tmp_path / "mutated"
    mutation_root.mkdir()
    mutated = _provenance(probabilities, mutation_root, config)
    Path(mutated.scheduler_plan_path).write_text(
        Path(mutated.scheduler_plan_path).read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    rejected_mutated = select_ev_package(
        surface,
        config,
        probabilities=probabilities,
        provenance=mutated,
    )

    assert rejected_arbitrary.structural_status == "STRUCTURAL_FAIL"
    assert "scheduler_plan_invalid" in (
        rejected_arbitrary.selection_diagnostics.infeasibility_reasons
    )
    assert rejected_mutated.structural_status == "STRUCTURAL_FAIL"
    assert "scheduler_plan_sha256_mismatch" in (
        rejected_mutated.selection_diagnostics.infeasibility_reasons
    )


@pytest.mark.parametrize(
    ("mismatch_class", "changes"),
    [
        ("bank", {"bank": 120}),
        ("stake_capacity", {"stake": 15}),
        ("effective_capacity", {"effective_budget": 60}),
        ("ev_threshold", {"min_gross_ev": 1.01}),
        ("concentration_limit", {"package_near_fixed_share": 0.90}),
        ("safety_flag", {"package_safety_enabled": False}),
        ("provenance_flag", {"package_provenance_required": False}),
        ("algorithm_config", {"package_exposure_floor_scale": 0.16}),
    ],
)
def test_bound_selection_context_mismatch_fails_closed(
    tmp_path,
    mismatch_class,
    changes,
):
    del mismatch_class
    probabilities = ((0.50, 0.30, 0.20),) * 3
    baseline = EVConfig(
        bank=90,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_provenance_required=True,
    )
    provenance = _provenance(probabilities, tmp_path, baseline)

    complete, reasons, _, _ = validate_selection_provenance(
        provenance,
        probabilities,
        config=replace(baseline, **changes),
        required=True,
    )

    assert complete is False
    assert "selection_context_mismatch" in reasons


def test_incomplete_scheduler_plan_selection_context_fails_closed(tmp_path):
    probabilities = ((0.50, 0.30, 0.20),) * 3
    config = EVConfig(
        bank=90,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_provenance_required=True,
    )
    root = tmp_path / "incomplete-plan"
    provenance = _provenance(probabilities, root, config)
    plan_path = Path(provenance.scheduler_plan_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    del plan["config"]["selection_context"]
    semantic = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "deadlines"}
    }
    plan["plan_id"] = hashlib.sha256(
        json.dumps(
            semantic,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    rebound = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=provenance.probability_snapshot_path,
        probability_input_sha256=provenance.probability_input_sha256,
        schedule_evidence_ledger_path=provenance.schedule_evidence_ledger_path,
        scheduler_plan_path=plan_path,
        selection_config=config,
    )

    complete, reasons, _, _ = validate_selection_provenance(
        rebound,
        probabilities,
        config=config,
        required=True,
    )

    assert complete is False
    assert "scheduler_plan_selection_context_mismatch" in reasons


def test_selector_diagnostics_hash_binds_probability_snapshot_input_and_ledger(
    tmp_path,
):
    probabilities = ((0.50, 0.30, 0.20),) * 3
    config = EVConfig(
        bank=90,
        stake=30,
        mode="playable",
        min_gross_ev=0.0,
        package_safety_enabled=True,
        package_near_fixed_share=1.0,
        package_provenance_required=True,
    )
    package = select_ev_package(
        _surface(np.linspace(10.0, 1.0, 27), 3),
        config,
        probabilities=probabilities,
        provenance=_provenance(probabilities, tmp_path, config),
    )

    diagnostics = package.selection_diagnostics
    assert diagnostics is not None
    assert (
        diagnostics.probability_snapshot_sha256
        == hashlib.sha256(
            (tmp_path / "probability-snapshot.json").read_bytes()
        ).hexdigest()
    )
    assert diagnostics.probability_input_sha256 == selection_probability_input_sha256(
        probabilities
    )
    assert (
        diagnostics.schedule_evidence_ledger_sha256
        == hashlib.sha256(
            (PROJECT_ROOT / "data" / "schedule-evidence" / "ledger.json").read_bytes()
        ).hexdigest()
    )
    assert len(diagnostics.diagnostics_sha256) == 64
    assert int(diagnostics.diagnostics_sha256, 16) >= 0
    assert diagnostics.release_gate_decision == "NO BET"
    assert diagnostics.real_money_actionable is False
    assert diagnostics.objective_order == (
        "probability_at_least_13",
        "probability_at_least_14",
        "probability_at_least_15",
        "independent_probability_at_least_9",
        "diversity",
        "robust_ev",
    )
    assert diagnostics.optimization_monte_carlo_seed != (
        diagnostics.evaluation_monte_carlo_seed
    )


def test_provenance_hash_changes_deterministic_metric_seed():
    probabilities = ((0.45, 0.35, 0.20),) * 15
    coupons = ("1" * 15, "X" * 15, "2" * 15)
    first = package_quality_metrics(
        coupons,
        probabilities,
        seed_material="a" * 64,
        monte_carlo_samples=300,
    )
    second = package_quality_metrics(
        coupons,
        probabilities,
        seed_material="b" * 64,
        monte_carlo_samples=300,
    )

    assert first.monte_carlo_seed != second.monte_carlo_seed
    assert (
        hashlib.sha256(("a" * 64).encode()).hexdigest()
        != hashlib.sha256(("b" * 64).encode()).hexdigest()
    )


def _brute_force_best_repair_swap(
    *,
    gross_ev,
    universe_indices,
    universe_ranks,
    universe_digits,
    selected,
    counts,
    lower_bounds,
    upper_bounds,
    soft_upper_bounds,
):
    selected_positions = np.flatnonzero(selected)
    current_hard = package_module._constraint_violation(
        counts, lower_bounds, upper_bounds
    )
    current_soft = package_module._upper_violation(counts, soft_upper_bounds)
    best = None
    pair = None
    for incoming in np.flatnonzero(~selected):
        for outgoing in selected_positions:
            candidate = counts.copy()
            package_module._apply_count_swap(
                candidate,
                universe_digits[outgoing],
                universe_digits[incoming],
            )
            hard = package_module._constraint_violation(
                candidate, lower_bounds, upper_bounds
            )
            soft = package_module._upper_violation(candidate, soft_upper_bounds)
            if not (
                hard < current_hard or (hard == current_hard and soft < current_soft)
            ):
                continue
            key = (
                hard,
                soft,
                float(
                    gross_ev[universe_indices[outgoing]]
                    - gross_ev[universe_indices[incoming]]
                ),
                int(universe_ranks[incoming]),
                int(universe_ranks[outgoing]),
            )
            if best is None or key < best:
                best = key
                pair = (int(incoming), int(outgoing))
    return pair


def test_vectorized_repair_swap_is_objective_equivalent_to_exhaustive_reference():
    rng = np.random.default_rng(4971)
    for _ in range(30):
        event_count = 5
        universe_size = 60
        required = 12
        universe_indices = np.arange(universe_size, dtype=np.int64)
        universe_ranks = np.arange(1, universe_size + 1, dtype=np.int64)
        universe_digits = rng.integers(
            0, 3, size=(universe_size, event_count), dtype=np.int8
        )
        selected = np.zeros(universe_size, dtype=bool)
        selected[rng.choice(universe_size, size=required, replace=False)] = True
        counts = package_module._selection_counts(
            universe_digits[selected], event_count
        )
        lower_bounds = rng.integers(0, 3, size=(event_count, 3), dtype=np.int16)
        upper_bounds = np.full((event_count, 3), 10, dtype=np.int32)
        soft_upper_bounds = np.full((event_count, 3), 7, dtype=np.int32)
        gross_ev = rng.random(universe_size) * 10.0

        expected = _brute_force_best_repair_swap(
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            selected=selected,
            counts=counts,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            soft_upper_bounds=soft_upper_bounds,
        )
        actual = package_module._best_repair_swap(
            gross_ev=gross_ev,
            universe_indices=universe_indices,
            universe_ranks=universe_ranks,
            universe_digits=universe_digits,
            coupon_exposures=package_module._coupon_exposures(universe_digits),
            selected=selected,
            counts=counts,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            soft_upper_bounds=soft_upper_bounds,
            current_violation=package_module._constraint_violation(
                counts, lower_bounds, upper_bounds
            ),
            current_headroom_violation=package_module._upper_violation(
                counts, soft_upper_bounds
            ),
        )

        assert actual == expected


def test_4971_scale_repair_swap_stays_within_practical_iteration_budget():
    rng = np.random.default_rng(4971)
    event_count = 15
    universe_size = 32_768
    required = 166
    universe_indices = np.arange(universe_size, dtype=np.int64)
    universe_ranks = np.arange(1, universe_size + 1, dtype=np.int64)
    universe_digits = rng.integers(
        0, 3, size=(universe_size, event_count), dtype=np.int8
    )
    selected = np.zeros(universe_size, dtype=bool)
    selected[:required] = True
    counts = package_module._selection_counts(universe_digits[:required], event_count)
    lower_bounds = np.full((event_count, 3), 10, dtype=np.int16)
    upper_bounds = np.full((event_count, 3), 157, dtype=np.int32)
    soft_upper_bounds = np.full((event_count, 3), 152, dtype=np.int32)
    # Force both deficit and excess paths while preserving a realistic K=166 shape.
    lower_bounds[0, 2] = int(counts[0, 2]) + 3
    upper_bounds[1, 0] = int(counts[1, 0]) - 2
    gross_ev = np.linspace(100.0, 1.0, universe_size)

    started = time.perf_counter()
    pair = package_module._best_repair_swap(
        gross_ev=gross_ev,
        universe_indices=universe_indices,
        universe_ranks=universe_ranks,
        universe_digits=universe_digits,
        coupon_exposures=package_module._coupon_exposures(universe_digits),
        selected=selected,
        counts=counts,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        soft_upper_bounds=soft_upper_bounds,
        current_violation=package_module._constraint_violation(
            counts, lower_bounds, upper_bounds
        ),
        current_headroom_violation=package_module._upper_violation(
            counts, soft_upper_bounds
        ),
    )
    elapsed = time.perf_counter() - started

    assert pair is not None
    assert elapsed < 2.0


def test_pair_delta_kernel_is_exact_and_materially_faster_than_event_loop():
    rng = np.random.default_rng(4973)
    event_count = 15
    incoming = rng.integers(0, 3, size=(2_048, event_count), dtype=np.int8)
    outgoing = rng.integers(0, 3, size=(166, event_count), dtype=np.int8)
    tables = rng.integers(-2, 3, size=(event_count, 3, 3), dtype=np.int16)

    def event_loop() -> np.ndarray:
        result = np.zeros((incoming.shape[0], outgoing.shape[0]), dtype=np.int16)
        for event in range(event_count):
            result += tables[
                event,
                incoming[:, event, None],
                outgoing[None, :, event],
            ]
        return result

    expected = event_loop()
    actual = package_module._pair_deltas(tables, incoming, outgoing)
    assert np.array_equal(actual, expected)

    package_module._pair_deltas(tables, incoming, outgoing)
    event_loop()
    optimized_samples = []
    reference_samples = []
    for _ in range(7):
        started = time.perf_counter()
        package_module._pair_deltas(tables, incoming, outgoing)
        optimized_samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        event_loop()
        reference_samples.append(time.perf_counter() - started)

    assert statistics.median(optimized_samples) < (
        statistics.median(reference_samples) * 0.75
    )
