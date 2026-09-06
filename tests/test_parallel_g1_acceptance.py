from __future__ import annotations

import copy
import hashlib
import json
import runpy
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from toto_ai.optimizer.robust_package import ExposureConstraints
from toto_ai.package.audit import PackageSafetyConfig
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import final_hybrid_sidecar as sidecar
from toto_ai.sports_stats import parallel_g1

ORACLE = runpy.run_path(
    str(Path(__file__).parent / "fixtures" / "parallel_g1_acceptance_oracles.py")
)


@pytest.mark.parametrize("reverse", [False, True])
def test_independent_rational_ranking_and_union_witness(reverse):
    coupons = ORACLE["COUPONS"][:: (-1 if reverse else 1)]
    rows = ((1.0, 0.0, 0.0),) * 11 + ((0.1, 0.1, 0.8),) * 4
    result = comparison._best_single_coupon_payload(coupons, rows, reference_model="bk")
    ORACLE["assert_fixture_ranking"](result, coupons)
    union = comparison.exact_category_probabilities(coupons, rows)
    assert union == pytest.approx((0.9867, 0.8229, 0.4097), abs=1e-12)


@pytest.fixture(scope="module")
def positive_result():
    original = ("X" * 15, "1" * 15, "2" * 15, "1X" * 7 + "1")
    args = dict(
        initial_coupons=original,
        control_coupons=original,
        candidate_coupons=(*original, "X1" * 7 + "X"),
        probability_models={"bk": ((0.5, 0.3, 0.2),) * 15},
        exposure_constraints=ExposureConstraints(((1, 1, 1),) * 15, ((2, 2, 2),) * 15),
        input_sha256="a" * 64,
        plan_sha256="b" * 64,
        bank=120,
        effective_budget=120,
        stake=30,
        safety_config=PackageSafetyConfig(),
        deadline=time.monotonic() + 30,
    )
    result = parallel_g1.run_parallel_g1(
        **args,
        config=parallel_g1.ParallelG1Config(family_refinement=True, reserve_seconds=1),
    )
    assert result["status"] == "REFINED"
    assert result["family_candidate_verified"] is True
    return args, result


@pytest.mark.parametrize(
    "field",
    [
        None,
        "input_sha256",
        "bank",
        "effective_budget",
        "stake",
        "coupon_capacity",
        "initial_package_sha256",
        "candidate_universe_sha256",
        "probability_models_sha256",
        "exposure_constraints_sha256",
        "plan_sha256",
        "selected_coupons",
    ],
)
def test_family_binding_mutation_retains_original(positive_result, field):
    args, original_result = positive_result
    result = copy.deepcopy(original_result)
    if field == "plan_sha256":
        result[field] = "c" * 64
    elif field == "selected_coupons":
        result[field][0] = "2" * 15
    elif field:
        result["binding"][field] = "c" * 64 if "sha256" in field else 1
    selected = parallel_g1.family_refinement_coupons(
        result,
        initial_coupons=args["initial_coupons"],
        candidate_coupons=args["candidate_coupons"],
        models=args["probability_models"],
        bounds=args["exposure_constraints"],
        input_sha256=args["input_sha256"],
        bank=args["bank"],
        effective_budget=args["effective_budget"],
        stake=args["stake"],
        plan_sha256=args["plan_sha256"],
    )
    if field:
        assert selected is None
    else:
        assert selected == tuple(original_result["selected_coupons"])


def test_primary_delivery_barrier_uses_actual_sidecar_call_seam(monkeypatch, tmp_path):
    now = [datetime(2026, 9, 6, 10, tzinfo=timezone.utc)]
    journal = []
    plan = SimpleNamespace(
        plan_id="a" * 16,
        drawing=4998,
        drawing_id=12102,
        output_dir=tmp_path,
        publish_deadline=now[0] + timedelta(minutes=10),
    )
    operator = {
        "plan_id": plan.plan_id,
        "drawing": plan.drawing,
        "drawing_id": plan.drawing_id,
        "run_id": "synthetic-one",
        "decision": "PLAY",
        "actionable": True,
        "record_sha256": "b" * 64,
    }
    primary = tmp_path / "primary.txt"
    primary.write_bytes(b"immutable synthetic primary")
    before = primary.read_bytes()
    (tmp_path / "operator-result.json").write_text(json.dumps(operator))
    journal.append("PRIMARY_PACKAGE_VERIFIED")
    for name in ("plan.json", "sports.json", "auth.json"):
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr(sidecar, "load_scheduler_plan", lambda _: plan)
    monkeypatch.setattr(sidecar, "_validate_parallel_authorization", lambda *a: {})

    def delivery(_seconds):
        record = {
            "plan_id": plan.plan_id,
            "drawing_id": plan.drawing_id,
            "run_id": operator["run_id"],
            "published_operator_result_sha256": operator["record_sha256"],
            "delivery_state": "READY",
            "decision": "PLAY",
            "actionable": True,
        }
        record["record_sha256"] = hashlib.sha256(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()
        (tmp_path / "operator-delivery.json").write_text(json.dumps(record))
        now[0] += timedelta(seconds=1)
        journal.append("PRIMARY_DELIVERY_READY")

    def execute(**kwargs):
        assert kwargs["g1_refinement"] is True
        journal.append("PRIMARY_RANK_START")
        rank = comparison._best_single_coupon_payload(
            ORACLE["COUPONS"],
            ((1.0, 0.0, 0.0),) * 11 + ((0.1, 0.1, 0.8),) * 4,
            reference_model="bk",
        )
        ORACLE["assert_fixture_ranking"](rank)
        (tmp_path / "primary-ranking.json").write_text(json.dumps(rank))
        journal.extend(("PRIMARY_RANK_AVAILABLE", "G1_START", "G1_BLOCKED"))
        ORACLE["assert_primary_rank_not_waiting_for_g1"](journal)
        return sidecar.FinalHybridSidecarResult(
            "SYNTHETIC_BARRIER", tmp_path / "result.json", tmp_path, None
        )

    monkeypatch.setattr(sidecar, "_execute", execute)
    result = sidecar.run_final_hybrid_sidecar(
        scheduler_plan_path=tmp_path / "plan.json",
        sports_artifact_path=tmp_path / "sports.json",
        output_root=tmp_path / "output",
        parallel_authorization_path=tmp_path / "auth.json",
        g1_refinement=True,
        now=lambda: now[0],
        sleeper=delivery,
    )
    assert result.status == "SYNTHETIC_BARRIER"
    ORACLE["assert_primary_first"](journal)
    ORACLE["assert_primary_unchanged"](before, primary.read_bytes())
