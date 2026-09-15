"""PR-1: real native file/authority validation, with only the archive DAO faked."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_final_hybrid_runtime_contracts import primary as primary
from toto_ai.runner import scheduler
from toto_ai.sports_stats import final_hybrid_comparison as comparison
from toto_ai.sports_stats import final_hybrid_sidecar as sidecar

NATIVE_VALIDATE = scheduler._validated_actionable_operator_upload


@pytest.fixture
def native_primary(request, monkeypatch):
    seed = request.getfixturevalue("primary")
    monkeypatch.setattr(
        scheduler, "_validated_actionable_operator_upload", NATIVE_VALIDATE
    )
    plan, operator = seed["plan"], seed["operator"]
    run = seed["snapshot"].path.parent
    now = datetime.now(timezone.utc)
    published = scheduler._timestamp(now - timedelta(seconds=1))
    plan.drawing = plan.drawing_id = 1
    plan.stake = 30
    plan.requested_bank = 90
    plan.minimum_gross_ev = 1.0
    plan.db = "synthetic-no-database"
    operator.update(
        schema_version=3,
        profitability_proven=False,
        risk_acknowledged=False,
        expires_at=scheduler._timestamp(plan.publish_deadline),
        published_at=published,
        completed_at=published,
        selected_count=3,
        selected_cost=90,
        status_path=str(run / "status.json"),
        marker_path=str(run / ".bet-ready"),
    )
    source = (run / "package.csv").read_bytes()
    status = dict(
        plan_id=plan.plan_id,
        run_id=run.name,
        outcome="bet-ready",
        decision="PLAY",
        package_path=str(run / "package.csv"),
        published_at=published,
        completed_at=published,
        package_sha256=hashlib.sha256(source).hexdigest(),
        selected_count=3,
        selected_cost=90,
        effective_bank=90,
    )
    marker = dict(
        drawing=1,
        run_id=run.name,
        outcome="bet-ready",
        decision="PLAY",
        package_path=status["package_path"],
        status_path=str(run / "status.json"),
        completed_at=published,
        package_sha256=status["package_sha256"],
    )
    (run / "status.json").write_text(json.dumps(status))
    (run / ".bet-ready").write_text(json.dumps(marker))
    archive_path = run / "package-archive.json"
    archive = json.loads(archive_path.read_text())
    archive.pop("archive_manifest_sha256")
    archive["archived_at"] = published
    archive["archive_manifest_sha256"] = hashlib.sha256(
        comparison._canonical(archive)
    ).hexdigest()
    archive_path.write_text(json.dumps(archive))
    operator["archive_manifest_sha256"] = archive["archive_manifest_sha256"]
    operator["record_sha256"] = scheduler._operator_result_sha256(operator)
    (plan.output_dir / "operator-result.json").write_text(json.dumps(operator))
    row = SimpleNamespace(
        coupon_count=3,
        cost=90,
        source_bytes=source,
        provenance="pre_bet_runner",
        archived_at=published,
    )
    queries = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def scalars(self, query):
            queries.append(query)
            return SimpleNamespace(all=lambda: [row])

    # No engine or SQLite is opened; all native JSON/bytes/expiry checks are real.
    monkeypatch.setattr(
        scheduler, "init_db", lambda _: SimpleNamespace(dispose=lambda: None)
    )
    monkeypatch.setattr(scheduler, "get_session_factory", lambda _: Session)
    seed["native_queries"] = queries
    return seed


def validate(seed, **kwargs):
    comparison._validate_current_primary_upload(
        plan=seed["plan"],
        operator=seed["operator"],
        upload_sha256=seed["upload_sha256"],
        **kwargs,
    )


def test_native_current_validity_reuse_positive(native_primary):
    seed = native_primary
    validate(seed)
    assert len(seed["native_queries"]) == 1
    result = comparison._reuse_verified_control(
        **{k: v for k, v in seed.items() if k != "native_queries"}
    )
    assert result.coupons == seed["expected_coupons"]
    assert len(seed["native_queries"]) == 2


@pytest.mark.parametrize(
    "fault", ["replace", "delete", "symlink", "expiry", "marker", "authority", "source"]
)
def test_native_current_invalidity_fails_closed(native_primary, monkeypatch, fault):
    seed = native_primary
    operator, plan = seed["operator"], seed["plan"]
    upload = Path(operator["coupon_path"])
    if fault == "replace":
        upload.write_bytes(b"SUBSTITUTED")
    elif fault == "delete":
        upload.unlink()
    elif fault == "symlink":
        other = upload.with_suffix(".copy")
        other.write_bytes(upload.read_bytes())
        upload.unlink()
        upload.symlink_to(other)
    elif fault == "expiry":
        operator["expires_at"] = scheduler._timestamp(
            plan.publish_deadline + timedelta(seconds=1)
        )
    elif fault == "marker":
        Path(operator["marker_path"]).write_text("{}")
    elif fault == "source":
        Path(operator["source_package_path"]).unlink()
    else:
        operator["release_mode"] = "EXPERIMENTAL_MANUAL"

        def reject(_):
            raise scheduler.SchedulerError("synthetic authority revoked")

        monkeypatch.setattr(scheduler, "_validate_experimental_manual_release", reject)
    operator["record_sha256"] = scheduler._operator_result_sha256(operator)
    (plan.output_dir / "operator-result.json").write_text(json.dumps(operator))
    with pytest.raises(comparison.PrimaryControlInvalid, match="reuse"):
        validate(seed)
    assert operator["package_sha256"] == seed["upload_sha256"]


def test_native_validator_race_and_returned_bytes_cannot_bless_substitution(
    native_primary, monkeypatch
):
    seed = native_primary
    upload = Path(seed["operator"]["coupon_path"])
    original = upload.read_bytes()

    def swap(*a, **k):
        upload.write_bytes(b"SUBSTITUTED_DURING_VALIDATION")
        return original

    monkeypatch.setattr(scheduler, "_validated_actionable_operator_upload", swap)
    with pytest.raises(comparison.PrimaryControlInvalid, match="upload hash"):
        validate(seed)
    upload.write_bytes(original)
    monkeypatch.setattr(
        scheduler, "_validated_actionable_operator_upload", lambda *a, **k: b"WRONG"
    )
    with pytest.raises(
        comparison.PrimaryControlInvalid, match="changed during validation"
    ):
        validate(seed)


def test_native_validation_crossing_expiry_fails(native_primary, monkeypatch):
    seed = native_primary
    clock = [datetime.now(timezone.utc)]

    def expire(*a, **k):
        data = NATIVE_VALIDATE(*a, **k)
        clock[0] = seed["plan"].publish_deadline
        return data

    monkeypatch.setattr(scheduler, "_validated_actionable_operator_upload", expire)
    with pytest.raises(comparison.PrimaryControlInvalid, match="expired"):
        validate(seed, now=lambda: clock[0])


@pytest.mark.parametrize("mutation_phase", ["ranking", "package_write", "record_write"])
@pytest.mark.parametrize("fault", ["delete", "replace", "authority"])
def test_publish_rechecks_current_primary_and_removes_only_own_output(
    native_primary, monkeypatch, mutation_phase, fault
):
    seed = native_primary
    plan = seed["plan"]
    operator = seed["operator"]
    upload = Path(operator["coupon_path"])
    original_record = (plan.output_dir / "operator-result.json").read_bytes()
    source = Path(operator["source_package_path"])
    source_bytes = source.read_bytes()
    output = plan.output_dir / "optional"
    output.mkdir()
    coupons = seed["expected_coupons"]
    auth = {"record_sha256": "synthetic-auth"}
    monkeypatch.setattr(
        sidecar, "_validate_parallel_authorization", lambda *a: dict(auth)
    )
    monkeypatch.setattr(sidecar, "_parse_research_package", lambda *a: coupons)
    monkeypatch.setattr(sidecar, "_selected_refinement_lineage", lambda **k: None)

    mutations = []

    def mutate():
        mutations.append(mutation_phase)
        if fault == "delete":
            upload.unlink()
        elif fault == "replace":
            upload.write_bytes(b"SUBSTITUTED")
        else:
            auth["record_sha256"] = "CHANGED"

    def ranking(**k):
        if mutation_phase == "ranking":
            mutate()
        return {"package_position": 1}

    monkeypatch.setattr(sidecar, "_selected_coupon_ranking", ranking)
    real_write = sidecar._write_replace

    def write(path, data):
        real_write(path, data)
        if (mutation_phase == "package_write" and path.suffix == ".txt") or (
            mutation_phase == "record_write"
            and path.name == "parallel-operator-result.json"
        ):
            mutate()

    monkeypatch.setattr(sidecar, "_write_replace", write)
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
    paths = SimpleNamespace(
        sports_package=source,
        quality_v3_package=source,
        uncertainty_package=source,
        robust_package=source,
    )
    with pytest.raises(comparison.PrimaryControlInvalid):
        sidecar._publish_parallel_selection(
            plan=plan,
            report=report,
            paths=paths,
            operator_export=upload,
            output=output,
            authorization_path=output / "auth.json",
            observed_at=datetime.now(timezone.utc),
            validate_primary=lambda: validate(seed),
        )
    assert mutations == [mutation_phase]
    assert not (output / "parallel-operator-result.json").exists()
    assert not (output / "selected-parallel-operator-package.txt").exists()
    assert source.read_bytes() == source_bytes
    assert (plan.output_dir / "operator-result.json").read_bytes() == original_record


@pytest.mark.parametrize("fault", ["delete", "replace"])
def test_invalid_primary_during_reuse_returns_terminal_and_retains_research(
    native_primary, monkeypatch, fault
):
    seed = native_primary
    plan = seed["plan"]
    plan_path = plan.output_dir / "scheduler-plan.json"
    plan_path.write_text("{}")
    seed["snapshot"].path.write_text("{}")
    upload = Path(seed["operator"]["coupon_path"])
    original_record = (plan.output_dir / "operator-result.json").read_bytes()
    now = datetime.now(timezone.utc)

    def export(*a, **k):
        k["destination"].write_bytes(upload.read_bytes())

    def compute(**kwargs):
        output = kwargs["output_dir"]
        output.mkdir()
        (output / "partial-research.json").write_text('{"operator_compatible":false}')
        if fault == "delete":
            upload.unlink()
        else:
            upload.write_bytes(b"SUBSTITUTED")
        comparison._reuse_verified_control(
            **{k: v for k, v in seed.items() if k != "native_queries"}
        )
        pytest.fail("invalid reuse returned")

    monkeypatch.setattr(sidecar, "export_operator_package", export)
    monkeypatch.setattr(sidecar, "execute_final_hybrid_comparison", compute)
    monkeypatch.setattr(
        sidecar, "_publish_parallel_selection", lambda **k: pytest.fail("published")
    )
    result = sidecar._execute(
        plan=plan,
        plan_path=plan_path,
        sports_path=plan_path,
        output_root=plan.output_dir / "optional",
        operator=seed["operator"],
        status_path=plan.output_dir / "sidecar-status.json",
        started_at=now,
        observed_at=now,
        parallel_authorization_path=plan.output_dir / "auth.json",
        clock=lambda: now,
    )
    assert result.status == "SKIPPED_PRIMARY_CHANGED"
    assert (plan.output_dir / "operator-result.json").read_bytes() == original_record
    research = (
        plan.output_dir
        / "optional"
        / f"run-{seed['operator']['run_id']}"
        / "research-comparison"
        / "partial-research.json"
    )
    assert research.is_file()
    assert "primary unchanged" in result.reason
