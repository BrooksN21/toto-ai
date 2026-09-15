from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.ev.runtime import RuntimeDeadlineExceeded
from toto_ai.optimizer.strategy_comparison import (
    FrozenStrategyEvent,
    FrozenStrategyInput,
)
from toto_ai.runner import scheduler
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import final_hybrid_sidecar as sidecar


@pytest.fixture
def primary(tmp_path, monkeypatch):
    coupons = ("1" * 15, "X" * 15, "2" * 15)
    run = tmp_path / "attempts" / "synthetic-final"
    run.mkdir(parents=True)
    source = (
        ",".join(scheduler.PACKAGE_CSV_HEADER)
        + "\n"
        + "".join(f"{i},{c},2.0,1.0\n" for i, c in enumerate(coupons, 1))
    ).encode()
    (run / "package.csv").write_bytes(source)
    frozen = FrozenStrategyInput(
        drawing_id=1,
        drawing_number=1,
        drawing_fingerprint="a" * 64,
        source_captured_at="2026-01-01T00:00:00Z",
        as_of="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
        bank=90,
        stake=30,
        pool_sum=1000,
        jackpot=0,
        possible_winnings=1000,
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
    plan = SimpleNamespace(
        output_dir=tmp_path,
        plan_id="synthetic",
        publish_deadline=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    snapshot = SimpleNamespace(
        path=run / "final-input.json",
        attempt_id=run.name,
        snapshot_sha256="s" * 64,
        probability_input_sha256="p" * 64,
    )
    archive = dict(
        final_input_sha256=snapshot.snapshot_sha256,
        probability_input_sha256=snapshot.probability_input_sha256,
        source_bytes_sha256=hashlib.sha256(source).hexdigest(),
        source_path=str(run / "package.csv"),
        drawing_id=1,
        drawing_number=1,
        stake=30,
        cost=90,
        coupon_count=3,
        provenance="pre_bet_runner",
        canonical_package_sha256=comparison._package_sha256(coupons),
    )
    archive["archive_manifest_sha256"] = hashlib.sha256(
        comparison._canonical(archive)
    ).hexdigest()
    (run / "package-archive.json").write_text(json.dumps(archive))
    operator = dict(
        plan_id=plan.plan_id,
        drawing=1,
        drawing_id=1,
        decision="PLAY",
        operator_status="FINAL_FRESH",
        provenance="FINAL_FRESH",
        actionable=True,
        automatic_wagering=False,
        requested_bank=90,
        stake=30,
        effective_bank=90,
        package_sha256="u" * 64,
        run_id=run.name,
        release_mode="STANDARD",
        source_package_path=str(run / "package.csv"),
        source_package_sha256=hashlib.sha256(source).hexdigest(),
        archive_manifest_path=str(run / "package-archive.json"),
        archive_manifest_sha256=archive["archive_manifest_sha256"],
    )
    upload = run / "baltbet-upload.txt"
    upload.write_bytes(
        sidecar._operator_package_bytes(30, coupons).replace(b";", b"; ")
    )
    operator["coupon_path"] = str(upload)
    operator["package_sha256"] = hashlib.sha256(upload.read_bytes()).hexdigest()
    operator["record_sha256"] = scheduler._operator_result_sha256(operator)

    # This older fixture isolates archive/provenance reuse. Native validation
    # itself is exercised separately with real artifacts and an in-memory DAO.
    def native_upload(plan, **kwargs):
        current = json.loads((plan.output_dir / "operator-result.json").read_text())
        return (run / "baltbet-upload.txt").read_bytes() if current else b""

    monkeypatch.setattr(
        scheduler, "_validated_actionable_operator_upload", native_upload
    )
    (tmp_path / "operator-result.json").write_text(json.dumps(operator))
    monkeypatch.setattr(
        "toto_ai.ev.package_quality.validate_selection_provenance",
        lambda *a, **k: (True, (), "p" * 64, "seed"),
    )
    return dict(
        plan=plan,
        snapshot=snapshot,
        frozen=frozen,
        config=EVConfig(bank=90, stake=30),
        provenance=object(),
        operator=operator,
        expected_coupons=coupons,
        upload_sha256=operator["package_sha256"],
    )


def test_reuse_has_identical_exact_metrics_without_ev(primary, monkeypatch):
    monkeypatch.setattr(
        comparison, "run_ev_crowd_current", lambda *a, **k: pytest.fail("EV repeated")
    )
    result = comparison._reuse_verified_control(**primary)
    assert result.coupons == primary["expected_coupons"]
    assert (
        result.probability_at_least_13
        == comparison.exact_category_probabilities(
            result.coupons, primary["frozen"].bk_probability_matrix
        )[0]
    )


@pytest.mark.parametrize(
    "field",
    [
        "record",
        "source",
        "archive",
        "snapshot",
        "probabilities",
        "coupons",
        "upload",
        "bank",
        "stake",
        "current",
        "provenance",
    ],
)
def test_reuse_rejects_changed_binding(primary, field, monkeypatch):
    run = primary["snapshot"].path.parent
    if field == "record":
        primary["operator"]["record_sha256"] = "bad"
    elif field == "source":
        (run / "package.csv").write_bytes(b"tampered")
    elif field == "archive":
        (run / "package-archive.json").write_text("{}")
    elif field == "snapshot":
        primary["snapshot"].snapshot_sha256 = "other"
    elif field == "probabilities":
        primary["snapshot"].probability_input_sha256 = "other"
    elif field == "coupons":
        primary["expected_coupons"] = tuple(reversed(primary["expected_coupons"]))
    elif field == "upload":
        primary["upload_sha256"] = "bad"
    elif field == "bank":
        primary["config"] = replace(primary["config"], bank=120)
    elif field == "stake":
        primary["config"] = replace(primary["config"], stake=10)
    elif field == "current":
        (primary["plan"].output_dir / "operator-result.json").write_text("{}")
    else:
        monkeypatch.setattr(
            "toto_ai.ev.package_quality.validate_selection_provenance",
            lambda *a, **k: (False, ("changed_config",), None, None),
        )
    with pytest.raises(ValueError, match="reuse"):
        comparison._reuse_verified_control(**primary)


@pytest.mark.parametrize("expire_phase", ["ranking", "package_write", "record_write"])
def test_publication_rechecks_live_clock_and_removes_only_own_late_output(
    tmp_path, monkeypatch, expire_phase
):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = [now]
    plan = SimpleNamespace(
        publish_deadline=now + timedelta(seconds=2),
        plan_id="test",
        drawing=1,
        drawing_id=1,
        stake=30,
        requested_bank=90,
    )
    protected = tmp_path / "primary.txt"
    protected.write_bytes(b"PRIMARY_UNCHANGED")
    coupons = ("1" * 15, "X" * 15, "2" * 15)
    monkeypatch.setattr(
        sidecar,
        "_validate_parallel_authorization",
        lambda *a: {"record_sha256": "auth"},
    )
    monkeypatch.setattr(sidecar, "_parse_research_package", lambda *a: coupons)
    monkeypatch.setattr(sidecar, "_selected_refinement_lineage", lambda **k: None)

    def ranking(**kwargs):
        if expire_phase == "ranking":
            clock[0] = plan.publish_deadline
        return {"package_position": 1}

    monkeypatch.setattr(sidecar, "_selected_coupon_ranking", ranking)
    real_write = sidecar._write_replace

    def write(path, data):
        real_write(path, data)
        if (expire_phase == "package_write" and path.suffix == ".txt") or (
            expire_phase == "record_write"
            and path.name == "parallel-operator-result.json"
        ):
            clock[0] = plan.publish_deadline

    monkeypatch.setattr(sidecar, "_write_replace", write)
    paths = SimpleNamespace(
        sports_package=protected,
        quality_v3_package=protected,
        uncertainty_package=protected,
        robust_package=protected,
    )
    report = {
        "experimental_selection": {
            "policy_version": sidecar.POLICY_VERSION,
            "selected_strategy_id": "quality-v3",
            "selected_package_sha256": comparison._package_sha256(coupons),
            "candidates": [
                {
                    "strategy_id": "quality-v3",
                    "eligible": True,
                    "coupon_count": 3,
                    "cost": 90,
                }
            ],
        }
    }
    with pytest.raises(RuntimeDeadlineExceeded):
        sidecar._publish_parallel_selection(
            plan=plan,
            report=report,
            paths=paths,
            operator_export=protected,
            output=tmp_path,
            authorization_path=tmp_path / "auth.json",
            observed_at=now,
            now=lambda: clock[0],
        )
    assert protected.read_bytes() == b"PRIMARY_UNCHANGED"
    assert not (tmp_path / "parallel-operator-result.json").exists()
    assert not (tmp_path / "selected-parallel-operator-package.txt").exists()


def test_no_bet_deadline_retains_completed_research_and_terminal(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    plan = SimpleNamespace(
        plan_id="synthetic",
        drawing=1,
        drawing_id=1,
        publish_deadline=now + timedelta(seconds=30),
    )
    planpath = tmp_path / "plan.json"
    planpath.write_text("{}")
    final_input = tmp_path / "source" / "final-input.json"
    output = tmp_path / "output"
    status = output / "sidecar-status.json"

    def expire(**kwargs):
        path = kwargs["output_dir"]
        path.mkdir(parents=True)
        (path / "baseline-final-research-coupons.txt").write_text("RESEARCH ONLY")
        raise RuntimeDeadlineExceeded("test EV deadline")

    monkeypatch.setattr(sidecar, "execute_final_hybrid_comparison", expire)
    result = sidecar._execute_no_bet_research(
        plan=plan,
        plan_path=planpath,
        sports_path=tmp_path / "sports.json",
        output_root=output,
        final_input=final_input,
        status_path=status,
        started_at=now,
        observed_at=now,
        operator_reason="NO BET",
    )
    assert result.status == "SKIPPED_RUNTIME_DEADLINE"
    assert (
        output / "run-source/research-comparison/baseline-final-research-coupons.txt"
    ).read_text() == "RESEARCH ONLY"
    assert json.loads(status.read_text())["automatic_wagering"] is False


def test_progress_is_scoped_and_has_phase_cpu_counts():
    from toto_ai.ev.runtime import RuntimeBudget, checkpoint, phase, runtime_scope

    events = []
    with runtime_scope(RuntimeBudget(progress=events.append)):
        phase("control_ev")
        checkpoint("pairs", evaluated_pairs=12)
        phase("sports_ev")
    assert any(
        e["phase"] == "control_ev" and e["counts"].get("evaluated_pairs") == 12
        for e in events
    )
    assert all(
        e["wall_seconds"] >= 0 and e["cpu_seconds"] >= 0 and e["phase_cpu_seconds"] >= 0
        for e in events
    )
    count = len(events)
    checkpoint("outside")
    assert len(events) == count


def test_changed_primary_after_compute_blocks_companion(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    source = tmp_path / "package.csv"
    source.write_bytes(b"PRIMARY")
    (tmp_path / "final-input.json").write_text("{}")
    planpath = tmp_path / "plan.json"
    planpath.write_text("{}")
    plan = SimpleNamespace(
        output_dir=tmp_path,
        publish_deadline=now + timedelta(minutes=2),
        stake=30,
        plan_id="synthetic",
        drawing=1,
        drawing_id=1,
    )
    operator = {"run_id": "run", "source_package_path": str(source)}

    def export(*args, **kwargs):
        kwargs["destination"].write_bytes(b"EXPORTED_TEST")

    monkeypatch.setattr(sidecar, "export_operator_package", export)
    monkeypatch.setattr(sidecar, "_parse_operator_package", lambda *a: ("1" * 15,))
    monkeypatch.setattr(sidecar, "_parse_research_package", lambda *a: ("1" * 15,))
    paths = SimpleNamespace(baseline_package=source, uncertainty_package=source)
    monkeypatch.setattr(
        sidecar, "execute_final_hybrid_comparison", lambda **k: ({}, paths)
    )
    monkeypatch.setattr(
        sidecar, "_load_operator_result", lambda *a: {"decision": "NO BET"}
    )
    monkeypatch.setattr(
        sidecar,
        "_publish_parallel_selection",
        lambda **k: pytest.fail("published after primary changed"),
    )
    result = sidecar._execute(
        plan=plan,
        plan_path=planpath,
        sports_path=source,
        output_root=tmp_path / "out",
        operator=operator,
        status_path=tmp_path / "status.json",
        started_at=now,
        observed_at=now,
        parallel_authorization_path=tmp_path / "auth.json",
        clock=lambda: now,
    )
    assert result.status == "SKIPPED_PRIMARY_CHANGED"
    assert source.read_bytes() == b"PRIMARY"
