from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
)
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import final_hybrid_sidecar as sidecar
from toto_ai.sports_stats.parallel_g1 import ParallelG1Config

COUPONS = ("X" * 15, "1" * 15, "2" * 15)


@pytest.fixture
def comparison_input(monkeypatch, tmp_path, request):
    coupons = getattr(request, "param", COUPONS)
    bank = 30 * len(coupons)
    now = datetime(2026, 9, 6, 10, tzinfo=timezone.utc)
    paths = {name: tmp_path / (name + ".json") for name in ("plan", "input", "sports")}
    for path in paths.values():
        path.write_text("{}")
    plan = SimpleNamespace(
        plan_id="c" * 16,
        requested_bank=bank,
        stake=30,
        quality_v2_ev_config=EVConfig(
            bank=bank,
            stake=30,
            mode="playable",
            package_safety_enabled=True,
            package_probability_samples=16,
            package_optimization_probability_samples=16,
        ),
        schedule_evidence_ledger=tmp_path / "ledger.json",
    )
    frozen = FrozenStrategyInput(
        drawing_id=12102,
        drawing_number=4998,
        drawing_fingerprint="a" * 64,
        source_captured_at=now.isoformat(),
        as_of=now.isoformat(),
        ended_at="2026-09-06T15:30:00Z",
        bank=bank,
        stake=30,
        pool_sum=1.0,
        jackpot=0.0,
        possible_winnings=1.0,
        events=tuple(
            FrozenStrategyEvent(
                event_order=i,
                name=str(i),
                bk_probabilities=(0.5, 0.3, 0.2),
                crowd_probabilities=(0.4, 0.3, 0.3),
            )
            for i in range(15)
        ),
    )
    snapshot = SimpleNamespace(
        captured_at=now, snapshot_sha256="b" * 64, probability_input_sha256="c" * 64
    )
    sports = SimpleNamespace(
        drawing_id=12102,
        drawing_number=4998,
        drawing_fingerprint="a" * 64,
        authoritative_target_fingerprint="a" * 64,
        as_of=now,
        events=tuple(
            SimpleNamespace(
                event_order=i,
                blend_weight=0.0,
                fallback_reason="BK fallback",
                sports_probabilities=(0.5, 0.3, 0.2),
            )
            for i in range(15)
        ),
        artifact_sha256="d" * 64,
        sports_coverage_count=0,
        fallback_count=15,
    )
    baseline = SimpleNamespace(
        coupons=coupons,
        coupon_count=len(coupons),
        cost=bank,
        unused_bank=0,
        package_sha256="e" * 64,
        runtime_seconds=0.0,
        probability_at_least_13=0.1,
        probability_at_least_14=0.01,
        probability_at_least_15=0.001,
    )
    robust = SimpleNamespace(
        selected_coupons=coupons,
        candidate_count=len(coupons),
        category=13,
        sample_count_per_model=16,
        worst_sampled_category_coverage=0.1,
        mean_sampled_category_coverage=0.1,
        timed_out=False,
        model_metrics=(),
    )

    @dataclass
    class Quality:
        probability_at_least_13: float = 0.1

    for name, value in (
        ("load_scheduler_plan", lambda _: plan),
        ("load_final_input", lambda *a, **k: snapshot),
        ("frozen_input_from_snapshot", lambda *a: frozen),
        ("load_shadow_probability_artifact", lambda _: sports),
        ("effective_selection_budget", lambda **k: bank),
        ("run_ev_crowd_current", lambda *a, **k: baseline),
        ("select_robust_package", lambda **k: robust),
        ("select_uncertainty_package", lambda **k: robust),
        ("package_quality_metrics", lambda *a, **k: Quality()),
    ):
        monkeypatch.setattr(comparison, name, value)
    monkeypatch.setattr(
        comparison,
        "PackageSelectionProvenance",
        SimpleNamespace(from_artifacts=lambda **k: object()),
    )
    return dict(
        final_input_path=paths["input"],
        scheduler_plan_path=paths["plan"],
        sports_artifact_path=paths["sports"],
        output_dir=tmp_path / "out",
        deadline=time.monotonic() + 60,
        g1_config=ParallelG1Config(),
    )


def test_primary_bytes_and_computed_rank_exist_before_optional_g1(
    comparison_input,
    monkeypatch,
):
    output = comparison_input["output_dir"]

    def refine(**kwargs):
        primary = output / "baseline-final-research-coupons.txt"
        rank = json.loads((output / "primary-bk-ranking.json").read_text())
        assert primary.read_text().splitlines()[4:] == list(COUPONS)
        assert rank["highest_p13_single_coupon"]["package_position"] == 2
        assert (
            rank["highest_p13_single_coupon"]["probability_at_least_13"] == 121 / 32768
        )
        assert (
            rank["highest_p13_single_coupon"]["criterion"]
            == "maximum_probability_at_least_13"
        )
        assert rank["final_input_snapshot_sha256"] == "b" * 64
        assert kwargs["initial_coupons"] == COUPONS
        assert kwargs["bank"] == kwargs["effective_budget"] == 90
        assert kwargs["stake"] == 30
        assert (
            kwargs["probability_models"]["sports"] == kwargs["probability_models"]["bk"]
        )
        return {
            "status": "REFINED",
            "selected_coupons": ["1X2" * 5],
            "operator_compatible": False,
            "research_only": True,
        }

    monkeypatch.setattr(comparison, "run_parallel_g1", refine, raising=False)
    report, paths = comparison.execute_final_hybrid_comparison(**comparison_input)
    assert report["g1_research_refinement"]["status"] == "REFINED"
    assert [
        c["strategy_id"] for c in report["experimental_selection"]["candidates"]
    ] == ["quality-v2", "sports-shadow", "quality-v3", "robust"]
    assert report["sports_coverage_count"] == 0
    assert report["sports_fallback_count"] == 15
    assert report["o1_family_readiness"]["status"] == "UNAVAILABLE"
    assert report["o1_family_readiness"]["changes_probabilities"] is False
    assert paths.baseline_package.read_text().splitlines()[4:] == list(COUPONS)


def test_expired_comparison_never_starts_ev(comparison_input, monkeypatch):
    comparison_input["deadline"] = time.perf_counter() - 1
    monkeypatch.setattr(
        comparison, "run_ev_crowd_current", lambda *a, **k: pytest.fail("EV started")
    )
    with pytest.raises(TimeoutError, match="deadline"):
        comparison.execute_final_hybrid_comparison(**comparison_input)


def test_completed_control_preserved_when_sports_expires(comparison_input, monkeypatch):
    original = comparison._rebase_sports_probabilities

    def expire(*args):
        from toto_ai.ev.runtime import current_runtime

        current_runtime().deadline = time.perf_counter() - 1
        return original(*args)

    monkeypatch.setattr(comparison, "_rebase_sports_probabilities", expire)
    with pytest.raises(TimeoutError):
        comparison.execute_final_hybrid_comparison(**comparison_input)
    output = comparison_input["output_dir"]
    assert (output / "primary-bk-ranking.json").is_file()
    assert (output / "baseline-final-research-coupons.txt").is_file()
    assert not (output / "comparison.json").exists()


def test_unexpected_optional_side_failure_keeps_four_candidate_report(
    comparison_input,
    monkeypatch,
):
    def fail(**kwargs):
        raise OSError("side failure")

    monkeypatch.setattr(comparison, "run_parallel_g1", fail, raising=False)
    report, paths = comparison.execute_final_hybrid_comparison(**comparison_input)
    assert report["g1_research_refinement"]["status"] == "FALLBACK"
    assert len(report["experimental_selection"]["candidates"]) == 4
    assert paths.baseline_package.is_file()


def test_primary_mismatch_stops_before_parallel_work(comparison_input, monkeypatch):
    comparison_input["expected_primary_coupons"] = ("2" * 15,)
    monkeypatch.setattr(
        comparison,
        "select_uncertainty_package",
        lambda **k: pytest.fail("parallel work started"),
    )
    with pytest.raises(ValueError, match="primary"):
        comparison.execute_final_hybrid_comparison(**comparison_input)


def test_primary_rank_survives_later_parallel_generation_error(
    comparison_input,
    monkeypatch,
):
    def fail(**kwargs):
        raise RuntimeError("parallel generation failure")

    monkeypatch.setattr(comparison, "select_uncertainty_package", fail)
    with pytest.raises(RuntimeError, match="parallel generation"):
        comparison.execute_final_hybrid_comparison(**comparison_input)
    output = comparison_input["output_dir"]
    assert (output / "primary-bk-ranking.json").is_file()
    assert (output / "baseline-final-research-coupons.txt").read_text().splitlines()[
        4:
    ] == list(COUPONS)


def test_default_off_makes_no_optional_call(comparison_input, monkeypatch):
    comparison_input["g1_config"] = None
    monkeypatch.setattr(
        comparison, "run_parallel_g1", lambda **k: pytest.fail("optional call")
    )
    report, _ = comparison.execute_final_hybrid_comparison(**comparison_input)
    assert report["g1_research_refinement"]["status"] == "DISABLED"


@pytest.mark.parametrize(
    "comparison_input",
    [(*COUPONS, "1X" * 7 + "1")],
    indirect=True,
)
def test_real_refinement_uses_versioned_robust_family_and_unchanged_primary(
    comparison_input,
    monkeypatch,
):
    comparison_input["g1_config"] = replace(
        ParallelG1Config(),
        family_refinement=True,
        reserve_seconds=1,
    )
    incoming = "X1" * 7 + "X"
    original = (*COUPONS, "1X" * 7 + "1")
    uncertainty = SimpleNamespace(
        selected_coupons=(original[0], original[2], original[3], incoming),
        candidate_count=5,
        category=13,
        sample_count_per_model=16,
        worst_sampled_category_coverage=0.1,
        mean_sampled_category_coverage=0.1,
        timed_out=False,
        model_metrics=(),
    )
    monkeypatch.setattr(
        comparison, "select_uncertainty_package", lambda **k: uncertainty
    )
    monkeypatch.setattr(
        comparison,
        "control_relative_exposure_constraints",
        lambda *a, **k: ExposureConstraints(((1, 1, 1),) * 15, ((2, 2, 2),) * 15),
    )
    report, paths = comparison.execute_final_hybrid_comparison(**comparison_input)
    lineage = report["robust"]["refinement_lineage"]
    assert lineage["applied"] is True
    assert lineage["policy_version"] == "robust-family-g1-v1"
    assert lineage["strategy_family"] == "robust"
    assert report["g1_research_refinement"]["engine"]["accepted_swap_count"] == 1
    assert report["experimental_selection"]["selected_strategy_id"] == "robust"
    assert paths.baseline_package.read_text().splitlines()[4:] == list(original)
    assert paths.robust_package.read_text().splitlines()[4:] != list(original)
    assert set(
        c["strategy_id"] for c in report["experimental_selection"]["candidates"]
    ) == {
        "quality-v2",
        "sports-shadow",
        "quality-v3",
        "robust",
    }


def test_primary_delivery_requires_hash_bound_same_run(tmp_path):
    import hashlib

    plan = SimpleNamespace(output_dir=tmp_path, plan_id="a" * 16, drawing_id=12)
    operator = {"run_id": "one", "record_sha256": "b" * 64}
    assert not sidecar._primary_delivery_ready(plan, operator)
    record = {
        "plan_id": plan.plan_id,
        "drawing_id": 12,
        "run_id": "one",
        "published_operator_result_sha256": "b" * 64,
        "delivery_state": "READY",
        "actionable": True,
        "decision": "PLAY",
    }

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    path = tmp_path / "operator-delivery.json"
    path.write_text(json.dumps(record))
    assert sidecar._primary_delivery_ready(plan, operator)
    record["run_id"] = "another"
    path.write_text(json.dumps(record))
    assert not sidecar._primary_delivery_ready(plan, operator)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_lineage",
        "policy",
        "selected_hash",
        "input",
        "opt_in",
        "proof",
        "bank",
    ],
)
def test_publication_requires_explicit_hash_bound_g1_family_lineage(fault):
    import copy
    import hashlib

    coupons = ("1" * 15,)
    package_hash = hashlib.sha256(",".join(coupons).encode()).hexdigest()

    def digest(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    report = {
        "final_input_snapshot_sha256": "a" * 64,
        "bank": 30,
        "effective_budget": 30,
        "stake": 30,
        "robust": {
            "refinement_lineage": {
                "policy_version": "robust-family-g1-v1",
                "strategy_family": "robust",
                "applied": True,
                "selected_package_sha256": package_hash,
            }
        },
        "g1_research_refinement": {
            "status": "REFINED",
            "selected_coupons": list(coupons),
            "family_candidate_verified": True,
            "runtime_contract": {"family_refinement": True},
            "binding": {
                "input_sha256": "a" * 64,
                "bank": 30,
                "effective_budget": 30,
                "stake": 30,
            },
            "engine": {"input_hashes": {"selected_package_sha256": digest(coupons)}},
        },
    }
    expected = copy.deepcopy(report["robust"]["refinement_lineage"])
    if fault == "missing_lineage":
        report["robust"].clear()
    elif fault == "policy":
        report["robust"]["refinement_lineage"]["policy_version"] = "legacy"
    elif fault == "selected_hash":
        report["robust"]["refinement_lineage"]["selected_package_sha256"] = "b" * 64
    elif fault == "input":
        report["g1_research_refinement"]["binding"]["input_sha256"] = "b" * 64
    elif fault == "opt_in":
        report["g1_research_refinement"]["runtime_contract"]["family_refinement"] = (
            False
        )
    elif fault == "proof":
        report["g1_research_refinement"]["family_candidate_verified"] = False
    elif fault == "bank":
        report["g1_research_refinement"]["binding"]["bank"] = 60
    kwargs = dict(
        report=report, selected_id="robust", coupons=coupons, selected_hash=package_hash
    )
    if fault:
        with pytest.raises(ValueError, match="lineage"):
            sidecar._selected_refinement_lineage(**kwargs)
    else:
        assert sidecar._selected_refinement_lineage(**kwargs) == expected
