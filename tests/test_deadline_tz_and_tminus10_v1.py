from __future__ import annotations

import json
import plistlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.runner.morning_dispatch import (
    MorningDispatchResult,
    MorningIdentityDriftError,
)
from toto_ai.runner.scheduler import (
    SCHEDULER_SCHEMA_VERSION,
    SchedulerIntegrityError,
    SimulatedSchedulerPhaseRunner,
    VirtualSchedulerClock,
    build_scheduler_plan,
    execute_scheduler_plan,
    load_scheduler_plan,
    prepare_scheduler_artifacts,
    verify_scheduler_artifacts,
)

UTC = timezone.utc
DRAWING_4961_DEADLINE = datetime(2026, 7, 31, 16, 0, tzinfo=UTC)


def _invoke_morning_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    deadline: str,
    *,
    expected_instant: datetime = DRAWING_4961_DEADLINE,
):
    captured: dict[str, object] = {}

    def fake_dispatch(_config, **kwargs):
        identity = kwargs["expected_identity"]
        captured["deadline"] = identity.deadline
        if identity.deadline != expected_instant:
            raise MorningIdentityDriftError("preflight deadline drift")
        return MorningDispatchResult(
            status="deferred",
            reason="test-only",
            record_path=tmp_path / "state.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
        )

    monkeypatch.setattr(cli, "dispatch_morning", fake_dispatch)
    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--stake",
            "30",
            "--env-file",
            str(tmp_path / ".env"),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--db",
            str(tmp_path / "toto.db"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--raw-cache-dir",
            str(tmp_path / "raw"),
            "--totobrief-rate-state",
            str(tmp_path / "request-state.json"),
            "--cache-root",
            str(tmp_path / "external-cache"),
            "--expected-drawing-id",
            "11993",
            "--expected-drawing-number",
            "4961",
            "--expected-fingerprint",
            "a" * 64,
            "--expected-deadline",
            deadline,
        ],
    )
    return result, captured


@pytest.mark.parametrize(
    "deadline",
    (
        "2026-07-31T16:00:00Z",
        "2026-07-31T16:00:00+00:00",
        "2026-07-31T19:00:00+03:00",
    ),
)
def test_4961_expected_deadline_accepts_aware_iso_and_normalizes_to_utc(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    deadline: str,
) -> None:
    result, captured = _invoke_morning_dispatch(monkeypatch, tmp_path, deadline)

    assert result.exit_code == 2, result.output
    assert captured["deadline"] == DRAWING_4961_DEADLINE


def test_4961_expected_deadline_mismatch_remains_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result, _captured = _invoke_morning_dispatch(
        monkeypatch,
        tmp_path,
        "2026-07-31T16:01:00Z",
    )

    assert result.exit_code == 3
    assert json.loads(result.output) == {
        "reason": "identity_drift",
        "status": "terminal",
    }


@pytest.mark.parametrize(
    "deadline",
    ("2026-07-31T16:00:00", "not-a-deadline"),
)
def test_expected_deadline_rejects_naive_or_malformed_values_clearly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    deadline: str,
) -> None:
    result, captured = _invoke_morning_dispatch(monkeypatch, tmp_path, deadline)

    assert result.exit_code != 0
    assert (
        "expected-deadline must be a timezone-aware ISO-8601 datetime"
        in result.output
    )
    assert captured == {}


def test_4961_scheduler_round_trips_deadline_and_triggers_at_t_minus_10(
    tmp_path: Path,
) -> None:
    plan = build_scheduler_plan(
        drawing=4961,
        drawing_id=11993,
        ended_at=DRAWING_4961_DEADLINE,
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    plist = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    loaded = load_scheduler_plan(artifacts.plan_path)

    assert SCHEDULER_SCHEMA_VERSION == 5
    assert payload["schema_version"] == 5
    assert payload["config"]["publication_lead_minutes"] == 10
    assert payload["config"]["trigger_offsets_minutes"] == [45, 30, 20, 16, 10]
    assert payload["target"]["ended_at"] == "2026-07-31T16:00:00Z"
    assert payload["deadlines"]["t_minus_10"] == "2026-07-31T15:50:00Z"
    assert "t_minus_12" not in payload["deadlines"]
    assert loaded.ended_at == DRAWING_4961_DEADLINE
    assert loaded.publish_deadline == datetime(2026, 7, 31, 15, 50, tzinfo=UTC)
    assert plist["StartCalendarInterval"][-1] == {
        "Year": 2026,
        "Month": 7,
        "Day": 31,
        "Hour": 18,
        "Minute": 50,
    }
    assert plist["Label"].startswith("com.totoai.production-scheduler.v5.")
    assert "scheduler-execute" in artifacts.wrapper_path.read_text(encoding="utf-8")


def test_schema_v5_status_is_bound_to_exact_t_minus_10_semantics(
    tmp_path: Path,
) -> None:
    plan = build_scheduler_plan(
        drawing=4961,
        drawing_id=11993,
        ended_at=DRAWING_4961_DEADLINE,
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    clock = VirtualSchedulerClock(plan.preflight_at)

    result = execute_scheduler_plan(
        plan,
        phase_runner=SimulatedSchedulerPhaseRunner(),
        now=clock.now,
        sleep=clock.sleep,
        run_id="schema-v5-status",
    )
    status = json.loads(result.status_path.read_text(encoding="utf-8"))

    assert status["schema_version"] == 5
    assert status["plan_id"] == plan.plan_id
    assert status["deadlines"]["t_minus_10"] == "2026-07-31T15:50:00Z"
    assert "t_minus_12" not in status["deadlines"]


def test_schema_v4_t_minus_12_plan_fails_closed_with_regenerate_diagnostic(
    tmp_path: Path,
) -> None:
    plan = build_scheduler_plan(
        drawing=4961,
        drawing_id=11993,
        ended_at=DRAWING_4961_DEADLINE,
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 4
    payload["config"].pop("publication_lead_minutes", None)
    payload["config"].pop("trigger_offsets_minutes", None)
    payload["deadlines"].pop("t_minus_10")
    payload["deadlines"]["t_minus_12"] = "2026-07-31T15:48:00Z"
    artifacts.plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"stale scheduler schema v4.*T-12.*regenerate schema v5",
    ):
        load_scheduler_plan(artifacts.plan_path)

    result = CliRunner().invoke(
        cli.app,
        ["scheduler-execute", "--plan", str(artifacts.plan_path), "--dry-run"],
    )
    assert result.exit_code != 0
    assert "stale scheduler schema v4" in result.output
    assert "regenerate schema v5" in result.output

    with pytest.raises(
        SchedulerIntegrityError,
        match=r"stale scheduler schema v4.*T-12.*regenerate schema v5",
    ):
        verify_scheduler_artifacts(plan)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("publication_lead_minutes", 12),
        ("trigger_offsets_minutes", [45, 30, 20, 16, 12]),
    ),
)
def test_schema_v5_trigger_semantics_are_identity_bound_and_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    plan = build_scheduler_plan(
        drawing=4961,
        drawing_id=11993,
        ended_at=DRAWING_4961_DEADLINE,
        bank=4980,
        output_dir=tmp_path / f"scheduler-{field}",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    payload["config"][field] = value
    artifacts.plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"scheduler trigger semantics.*regenerate schema v5",
    ):
        load_scheduler_plan(artifacts.plan_path)
