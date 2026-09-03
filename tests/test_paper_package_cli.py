from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.cli import app
from toto_ai.runner.scheduler import (
    SchedulerIntegrityError,
    build_scheduler_plan,
    export_operator_package,
    load_paper_package,
    persist_paper_package_artifacts,
    prepare_scheduler_artifacts,
)

ENDED_AT = datetime(2032, 4, 5, 18, 0, tzinfo=timezone.utc)


def _plan(tmp_path: Path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "aliases.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data" / "toto.db").touch()
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4974,
        drawing_id=12026,
        ended_at=ENDED_AT,
        bank=4980,
        stake=30,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "aliases.json",
    )
    return prepare_scheduler_artifacts(plan).plan


def _source_package(path: Path, coupons: tuple[str, ...]) -> Path:
    rows = ["rank,coupon,gross_ev,net_ev"]
    for rank, coupon in enumerate(coupons, start=1):
        gross = 1.2 - rank / 1000
        rows.append(f"{rank},{coupon},{gross:.3f},{gross - 1:.3f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_persisted_no_bet_paper_package_is_hash_bound_and_cli_payload_is_clean(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    coupons = ("1X2" * 5, "2X1" * 5)
    source = _source_package(plan.output_dir / "attempts/a/package.csv", coupons)
    result = persist_paper_package_artifacts(
        plan,
        source_package=source,
        decision="NO BET",
        reason="quality gate closed",
        completed_at=plan.final_at,
        probability_input_sha256="a" * 64,
        provenance="FINAL_FRESH",
        expected_count=2,
        expected_cost=60,
    )

    assert result.actionable is False
    assert result.paper_path is not None and result.paper_path.is_file()
    assert result.source_package_path is not None
    assert result.count == 2
    assert result.cost == 60
    assert load_paper_package(plan) == result

    runner = CliRunner()
    invocation = runner.invoke(
        app,
        ["paper-package-show", "--plan", str(plan.output_dir / "scheduler-plan.json")],
    )

    assert invocation.exit_code == 0, invocation.stderr
    assert invocation.stdout.encode("utf-8") == result.paper_path.read_bytes()
    assert "PAPER / NO BET / DO NOT WAGER" in invocation.stderr
    assert "gross_ev" not in invocation.stdout
    assert "net_ev" not in invocation.stdout
    assert "PAPER" not in invocation.stdout


def test_paper_package_show_output_writes_only_identical_payload(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    source = _source_package(
        plan.output_dir / "attempts/a/package.csv",
        ("1" * 15, "X" * 15),
    )
    result = persist_paper_package_artifacts(
        plan,
        source_package=source,
        decision="NO BET",
        reason="paper only",
        completed_at=plan.final_at,
        probability_input_sha256="b" * 64,
        provenance="FINAL_FRESH",
        expected_count=2,
        expected_cost=60,
    )
    destination = tmp_path / "manual" / "paper.txt"

    runner = CliRunner()
    invocation = runner.invoke(
        app,
        [
            "paper-package-show",
            "--plan",
            str(plan.output_dir / "scheduler-plan.json"),
            "--output",
            str(destination),
        ],
    )

    assert invocation.exit_code == 0, invocation.stderr
    assert invocation.stdout == ""
    assert destination.read_bytes() == result.paper_path.read_bytes()
    assert "PAPER / NO BET / DO NOT WAGER" in invocation.stderr


def test_package_free_no_bet_has_no_coupon_payload(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    result = persist_paper_package_artifacts(
        plan,
        source_package=None,
        decision="NO BET",
        reason="no computed package",
        completed_at=plan.final_at,
        probability_input_sha256=None,
        provenance=None,
        expected_count=0,
        expected_cost=0,
    )

    assert result.paper_path is None
    assert result.source_package_path is None
    runner = CliRunner()
    invocation = runner.invoke(
        app,
        ["paper-package-show", "--plan", str(plan.output_dir / "scheduler-plan.json")],
    )
    assert invocation.exit_code != 0
    assert invocation.stdout == ""
    assert "no coupon payload" in invocation.stderr


@pytest.mark.parametrize("target", ("source", "paper", "result"))
def test_paper_binding_rejects_mutation(tmp_path: Path, target: str) -> None:
    plan = _plan(tmp_path)
    source = _source_package(
        plan.output_dir / "attempts/a/package.csv", ("2" * 15,)
    )
    result = persist_paper_package_artifacts(
        plan,
        source_package=source,
        decision="NO BET",
        reason="paper only",
        completed_at=plan.final_at,
        probability_input_sha256="c" * 64,
        provenance="FINAL_FRESH",
        expected_count=1,
        expected_cost=30,
    )
    if target == "source":
        assert result.source_package_path is not None
        result.source_package_path.write_bytes(
            result.source_package_path.read_bytes() + b" "
        )
    elif target == "paper":
        assert result.paper_path is not None
        result.paper_path.write_bytes(result.paper_path.read_bytes() + b"\n")
    else:
        result_path = plan.output_dir / "paper-package-result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload["reason"] = "tampered"
        result_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SchedulerIntegrityError):
        load_paper_package(plan)


def test_paper_result_is_never_accepted_by_actionable_operator_export(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path)
    source = _source_package(
        plan.output_dir / "attempts/a/package.csv", ("1" * 15,)
    )
    persist_paper_package_artifacts(
        plan,
        source_package=source,
        decision="NO BET",
        reason="paper only",
        completed_at=plan.final_at,
        probability_input_sha256="d" * 64,
        provenance="FINAL_FRESH",
        expected_count=1,
        expected_cost=30,
    )

    with pytest.raises(SchedulerIntegrityError, match="operator"):
        export_operator_package(
            plan,
            destination=tmp_path / "must-not-export.txt",
            observed_at=plan.final_at + timedelta(minutes=1),
        )
    assert not tuple(plan.output_dir.rglob(".bet-ready"))
