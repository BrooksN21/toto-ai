"""Independent short runtime probes, exclusively synthetic local fixtures."""

import hashlib
import importlib.util
import itertools
import json
import random
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tests.test_final_hybrid_runtime_contracts import primary  # noqa: F401
from toto_ai.ev import package_quality as quality
from toto_ai.ev import runtime, ternary
from toto_ai.ev.package_quality import ExactCategoryCoverage, PackageSelectionProvenance
from toto_ai.runner import scheduler
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import final_hybrid_sidecar as sidecar

REAL_VALIDATE = quality.validate_selection_provenance
ROOT = Path(__file__).parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reseal_operator(seed):
    operator = seed["operator"]
    operator["record_sha256"] = scheduler._operator_result_sha256(operator)
    (seed["plan"].output_dir / "operator-result.json").write_text(json.dumps(operator))


@pytest.fixture
def provenance_seed(request, monkeypatch):
    """Real native provenance validator; no export/DB/authority claim."""
    seed = request.getfixturevalue("primary")
    monkeypatch.setattr(quality, "validate_selection_provenance", REAL_VALIDATE)
    root = seed["plan"].output_dir
    run = seed["snapshot"].path.parent
    probability_hash = quality.selection_probability_input_sha256(
        seed["frozen"].bk_probability_matrix
    )
    snapshot_path = run / "final-input.json"
    snapshot_path.write_text(json.dumps({"probability_input_sha256": probability_hash}))
    ledger = root / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-01-01T00:00:00Z",
                "observations": [],
            }
        )
    )
    semantic = {
        "schema_version": quality.SUPPORTED_SCHEDULER_SCHEMA_VERSION,
        "target": {"drawing": 1, "drawing_id": 1, "ended_at": "synthetic"},
        "config": {
            "quality_v2": quality.quality_v2_config_payload(seed["config"]),
            "selection_context": quality.bound_selection_context(seed["config"]),
            "selection_context_sha256": quality.selection_context_sha256(
                seed["config"]
            ),
        },
        "paths": {},
    }
    plan_doc = dict(
        semantic,
        plan_id=digest(
            json.dumps(
                semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        )[:16],
        deadlines={},
    )
    plan_path = root / "scheduler-plan.json"
    plan_path.write_text(json.dumps(plan_doc))
    seed["plan"].plan_id = plan_doc["plan_id"]
    seed["plan"].publish_deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
    seed["snapshot"].snapshot_sha256 = digest(snapshot_path.read_bytes())
    seed["snapshot"].probability_input_sha256 = probability_hash
    archive_path = run / "package-archive.json"
    archive = json.loads(archive_path.read_text())
    archive.pop("archive_manifest_sha256")
    archive.update(
        final_input_sha256=seed["snapshot"].snapshot_sha256,
        probability_input_sha256=probability_hash,
    )
    archive["archive_manifest_sha256"] = digest(comparison._canonical(archive))
    archive_path.write_text(json.dumps(archive))
    upload = run / "baltbet-upload.txt"
    upload.write_bytes(
        (
            "\n".join("30;" + ";".join(c) for c in seed["expected_coupons"]) + "\n"
        ).encode()
    )
    seed["upload_sha256"] = digest(upload.read_bytes())
    seed["operator"].update(
        plan_id=seed["plan"].plan_id,
        package_sha256=seed["upload_sha256"],
        coupon_path=str(upload),
        archive_manifest_sha256=archive["archive_manifest_sha256"],
    )
    reseal_operator(seed)
    seed["provenance"] = PackageSelectionProvenance.from_artifacts(
        probability_snapshot_path=snapshot_path,
        probability_input_sha256=probability_hash,
        schedule_evidence_ledger_path=ledger,
        scheduler_plan_path=plan_path,
        selection_config=seed["config"],
    )
    assert REAL_VALIDATE(
        seed["provenance"],
        seed["frozen"].bk_probability_matrix,
        config=seed["config"],
        required=True,
    )[0]
    return seed


def test_positive_reader_uses_real_provenance_and_exact_metrics(provenance_seed):
    result = comparison._reuse_verified_control(**provenance_seed)
    expected = quality.exact_category_probabilities(
        result.coupons, provenance_seed["frozen"].bk_probability_matrix
    )
    assert result.coupons == provenance_seed["expected_coupons"]
    assert (
        result.probability_at_least_13,
        result.probability_at_least_14,
        result.probability_at_least_15,
    ) == expected


@pytest.mark.parametrize(
    "fault",
    [
        "final_input_bytes",
        "selection_config",
        "run",
        "archive_input",
        "current_record",
        "source_package",
        "authorization",
        "coupon_order",
    ],
)
def test_reuse_adversarial_bindings_with_real_provenance(
    provenance_seed, monkeypatch, fault
):
    seed = provenance_seed
    if fault == "final_input_bytes":
        seed["snapshot"].path.write_text("{}")
    elif fault == "selection_config":
        seed["config"] = replace(seed["config"], package_quality_candidate_count=64)
    elif fault == "run":
        seed["operator"]["run_id"] = "other-run"
        reseal_operator(seed)
    elif fault == "archive_input":
        seed["snapshot"].snapshot_sha256 = "0" * 64
    elif fault == "current_record":
        (seed["plan"].output_dir / "operator-result.json").write_text("{}")
    elif fault == "source_package":
        Path(seed["operator"]["source_package_path"]).write_text("SYNTHETIC_CHANGED")
    elif fault == "authorization":
        seed["operator"]["release_mode"] = "EXPERIMENTAL_MANUAL"
        reseal_operator(seed)

        def reject(_):
            raise ValueError("synthetic authorization rejected")

        monkeypatch.setattr(scheduler, "_validate_experimental_manual_release", reject)
    else:
        seed["expected_coupons"] = tuple(reversed(seed["expected_coupons"]))
    with pytest.raises((ValueError, scheduler.SchedulerError)):
        comparison._reuse_verified_control(**seed)


def test_reuse_rechecks_native_upload_bytes_after_export(provenance_seed):
    seed = provenance_seed
    upload = Path(seed["operator"]["coupon_path"])
    upload.write_text("SYNTHETIC_REPLACEMENT_AFTER_EXPORT")
    with pytest.raises(ValueError, match="reuse"):
        comparison._reuse_verified_control(**seed)


def test_post_compute_primary_byte_substitution_blocks_companion(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    source = tmp_path / "package.csv"
    source.write_bytes(b"SYNTHETIC_CSV")
    upload = tmp_path / "baltbet-upload.txt"
    upload.write_bytes(b"SYNTHETIC_ORIGINAL_UPLOAD")
    (tmp_path / "final-input.json").write_text("{}")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    plan = SimpleNamespace(
        output_dir=tmp_path,
        publish_deadline=now + timedelta(minutes=2),
        stake=30,
        plan_id="synthetic",
        drawing=1,
        drawing_id=1,
    )
    operator = {
        "run_id": "run",
        "source_package_path": str(source),
        "coupon_path": str(upload),
        "package_sha256": digest(upload.read_bytes()),
    }
    (tmp_path / "operator-result.json").write_text(json.dumps(operator))

    def export(*args, **kwargs):
        kwargs["destination"].write_bytes(upload.read_bytes())

    def compute(**kwargs):
        upload.write_bytes(b"SYNTHETIC_CONCURRENT_REPLACEMENT")
        return {}, SimpleNamespace(baseline_package=source, uncertainty_package=source)

    monkeypatch.setattr(sidecar, "export_operator_package", export)
    monkeypatch.setattr(sidecar, "_parse_operator_package", lambda *a: ("1" * 15,))
    monkeypatch.setattr(sidecar, "_parse_research_package", lambda *a: ("1" * 15,))
    monkeypatch.setattr(sidecar, "execute_final_hybrid_comparison", compute)
    monkeypatch.setattr(
        sidecar,
        "_publish_parallel_selection",
        lambda **k: pytest.fail(
            "publication attempted with substituted current primary"
        ),
    )
    result = sidecar._execute(
        plan=plan,
        plan_path=plan_path,
        sports_path=source,
        output_root=tmp_path / "out",
        operator=operator,
        status_path=tmp_path / "status.json",
        started_at=now,
        observed_at=now,
        parallel_authorization_path=tmp_path / "auth.json",
        clock=lambda: now,
    )
    assert result.status.startswith("SKIPPED")
    assert source.read_bytes() == b"SYNTHETIC_CSV"


def test_cache_matches_frozen_original_across_repeated_proposals_and_swaps():
    spec = importlib.util.spec_from_file_location(
        "original_runtime_quality", ROOT / "before/package_quality.py"
    )
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    rng = random.Random(319)
    universe = ["".join(row) for row in itertools.product("1X2", repeat=5)]
    coupons = [s + "1" * 10 for s in rng.sample(universe, 12)]
    for probabilities in [
        ((0.5, 0.3, 0.2),) * 15,
        ((1e-8, 0.99999998, 1e-8),) * 15,
    ]:
        selected = coupons[:4]
        new = ExactCategoryCoverage(tuple(selected), probabilities)
        reference = old.ExactCategoryCoverage(tuple(selected), probabilities)
        for step in range(6):
            candidates = [c for c in coupons if c not in selected]
            for outgoing in selected:
                for incoming in candidates:
                    expected = reference.probabilities_after_swap(outgoing, incoming)
                    assert new.probabilities_after_swap(outgoing, incoming) == expected
                    assert new.probabilities_after_swap(outgoing, incoming) == expected
            outgoing, incoming = selected[step % 4], candidates[step % len(candidates)]
            new.apply_swap(outgoing, incoming)
            reference.apply_swap(outgoing, incoming)
            selected[selected.index(outgoing)] = incoming
            assert not new._swap_mass_cache


def test_nested_budget_cannot_extend_deadline_and_restores_context(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(runtime.time, "perf_counter", lambda: clock[0])
    with runtime.runtime_scope(runtime.RuntimeBudget(deadline=12.0)) as parent:
        with runtime.runtime_scope(runtime.RuntimeBudget(deadline=90.0)) as child:
            assert child.deadline == 12.0
            clock[0] = 12.0
            with pytest.raises(runtime.RuntimeDeadlineExceeded):
                runtime.checkpoint("boundary")
        assert runtime.current_runtime() is parent
    assert runtime.current_runtime() is None
    runtime.checkpoint("unbounded_default")


def test_deadline_checked_between_fft_kernels(monkeypatch):
    budget = runtime.RuntimeBudget()
    original = np.fft.fftn
    calls = []

    def fft(*a, **k):
        calls.append(1)
        result = original(*a, **k)
        budget.deadline = runtime.time.perf_counter() - 1
        return result

    monkeypatch.setattr(np.fft, "fftn", fft)
    with runtime.runtime_scope(budget), pytest.raises(runtime.RuntimeDeadlineExceeded):
        ternary.ternary_convolve(np.ones(27), np.ones(27), 3)
    assert len(calls) == 1


def test_progress_distinguishes_cpu_from_wall_and_resets_phase_counts(monkeypatch):
    clock, cpu = [10.0], [2.0]
    monkeypatch.setattr(runtime.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(runtime.time, "process_time", lambda: cpu[0])
    events = []
    budget = runtime.RuntimeBudget(
        started=10.0,
        cpu_started=2.0,
        phase_started=10.0,
        phase_cpu_started=2.0,
        progress=events.append,
    )
    with runtime.runtime_scope(budget):
        clock[0], cpu[0] = 17.0, 2.25
        runtime.checkpoint("one", processed=10)
        assert events[-1]["wall_seconds"] == 7.0
        assert events[-1]["cpu_seconds"] == 0.25
        runtime.phase("sports_ev")
        assert events[-1]["counts"] == {}
        assert events[-1]["phase"] == "sports_ev"


@pytest.mark.parametrize("is_no_bet", [False, True])
def test_deadline_terminal_retains_partial_research_without_publish(
    tmp_path, monkeypatch, is_no_bet
):
    now = datetime.now(timezone.utc)
    source = tmp_path / "package.csv"
    source.write_text("SYNTHETIC_PRIMARY")
    (tmp_path / "final-input.json").write_text("{}")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    plan = SimpleNamespace(
        output_dir=tmp_path,
        publish_deadline=now + timedelta(seconds=30),
        stake=30,
        plan_id="synthetic",
        drawing=1,
        drawing_id=1,
    )

    def export(*a, **k):
        k["destination"].write_text("SYNTHETIC_EXPORT")

    def expired(**kwargs):
        output = kwargs["output_dir"]
        output.mkdir(parents=True)
        (output / "partial.txt").write_text("RESEARCH_ONLY")
        raise runtime.RuntimeDeadlineExceeded("independent timed checkpoint")

    monkeypatch.setattr(sidecar, "export_operator_package", export)
    monkeypatch.setattr(sidecar, "_parse_operator_package", lambda *a: ("1" * 15,))
    monkeypatch.setattr(sidecar, "execute_final_hybrid_comparison", expired)
    monkeypatch.setattr(
        sidecar, "_publish_parallel_selection", lambda **k: pytest.fail("late publish")
    )
    common = dict(
        plan=plan,
        plan_path=plan_path,
        sports_path=source,
        output_root=tmp_path / "out",
        status_path=tmp_path / "status.json",
        started_at=now,
        observed_at=now,
    )
    if is_no_bet:
        result = sidecar._execute_no_bet_research(
            **common,
            final_input=tmp_path / "final-input.json",
            operator_reason="NO BET",
        )
    else:
        result = sidecar._execute(
            **common,
            operator={"run_id": "run", "source_package_path": str(source)},
            parallel_authorization_path=tmp_path / "auth.json",
            clock=lambda: now,
        )
    assert result.status == "SKIPPED_RUNTIME_DEADLINE"
    assert len(list((tmp_path / "out").glob("*/research-comparison/partial.txt"))) == 1
    assert source.read_text() == "SYNTHETIC_PRIMARY"
    assert not list((tmp_path / "out").glob("*/parallel-operator-result.json"))


@pytest.mark.parametrize("boundary", [1, 2, 4, 5, "existing"])
def test_publication_clock_boundaries_and_existing_records(
    tmp_path, monkeypatch, boundary
):
    before = datetime.now(timezone.utc)
    cutoff = before + timedelta(seconds=1)
    plan = SimpleNamespace(
        publish_deadline=cutoff,
        plan_id="synthetic",
        drawing=1,
        drawing_id=1,
        stake=30,
        requested_bank=30,
    )
    protected = tmp_path / "primary.txt"
    protected.write_text("SYNTHETIC_PROTECTED")
    coupons = ("1" * 15,)
    monkeypatch.setattr(
        sidecar,
        "_validate_parallel_authorization",
        lambda *a: {"record_sha256": "synthetic-auth"},
    )
    monkeypatch.setattr(sidecar, "_parse_operator_package", lambda *a: coupons)
    monkeypatch.setattr(
        sidecar, "_selected_coupon_ranking", lambda **k: {"package_position": 1}
    )
    monkeypatch.setattr(sidecar, "_selected_refinement_lineage", lambda **k: None)
    report = {
        "experimental_selection": {
            "policy_version": sidecar.POLICY_VERSION,
            "selected_strategy_id": "quality-v2",
            "selected_package_sha256": comparison._package_sha256(coupons),
            "candidates": [
                {
                    "strategy_id": "quality-v2",
                    "eligible": True,
                    "coupon_count": 1,
                    "cost": 30,
                }
            ],
        }
    }
    paths = SimpleNamespace(
        sports_package=protected,
        uncertainty_package=protected,
        quality_v3_package=protected,
        robust_package=protected,
    )
    companion = tmp_path / "parallel-operator-result.json"
    if boundary == "existing":
        companion.write_text("SYNTHETIC_IMMUTABLE")
    count = 0

    def clock():
        nonlocal count
        count += 1
        return cutoff if isinstance(boundary, int) and count >= boundary else before

    with pytest.raises(
        ValueError if boundary == "existing" else runtime.RuntimeDeadlineExceeded
    ):
        sidecar._publish_parallel_selection(
            plan=plan,
            report=report,
            paths=paths,
            operator_export=protected,
            output=tmp_path,
            authorization_path=tmp_path / "auth.json",
            observed_at=before,
            now=clock,
        )
    assert protected.read_text() == "SYNTHETIC_PROTECTED"
    assert not (tmp_path / "selected-parallel-operator-package.txt").exists()
    if boundary == "existing":
        assert companion.read_text() == "SYNTHETIC_IMMUTABLE"
    else:
        assert not companion.exists()
