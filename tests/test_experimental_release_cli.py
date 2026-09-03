from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai.cli import app
from toto_ai.runner.scheduler import (
    build_scheduler_plan,
    prepare_scheduler_artifacts,
)


def _plan(tmp_path):
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=datetime(2030, 1, 2, 12, tzinfo=timezone.utc),
        bank=4980,
        stake=30,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.sqlite",
        aliases=tmp_path / "aliases.json",
    )
    return plan, prepare_scheduler_artifacts(plan)


def test_experimental_release_cli_requires_explicit_acknowledgement(tmp_path):
    _plan_value, artifacts = _plan(tmp_path)

    result = CliRunner().invoke(
        app,
        ["experimental-release-authorize", "--plan", str(artifacts.plan_path)],
    )

    assert result.exit_code == 2
    assert "explicit unvalidated manual-risk acknowledgement" in result.output


def test_experimental_release_cli_writes_plan_bound_non_wagering_record(tmp_path):
    plan, artifacts = _plan(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "experimental-release-authorize",
            "--plan",
            str(artifacts.plan_path),
            "--acknowledge-unvalidated-manual-risk",
        ],
    )

    assert result.exit_code == 0, result.output
    path = plan.output_dir / "experimental-manual-release-authorization.json"
    payload = json.loads(path.read_text())
    assert payload["plan_id"] == artifacts.plan.plan_id
    assert payload["drawing"] == plan.drawing
    assert payload["requested_bank"] == 4980
    assert payload["risk_acknowledged"] is True
    assert payload["profitability_proven"] is False
    assert payload["automatic_wagering"] is False
    assert "profitability is unproven" in result.output
