from __future__ import annotations

import json
import os
import plistlib
import shlex
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from tests.schedule_evidence_helpers import write_empty_schedule_evidence_ledger
from toto_ai import cli
from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningDispatchResult,
    MorningExpectedIdentity,
    MorningPreparedDrawing,
    MorningUnresolvedEvent,
    _allows_deferred_reviewed_hash_transition,
    activate_scheduler_launch_agent,
    dispatch_morning,
)
from toto_ai.runner.scheduler import (
    MORNING_DEFERRED_EXIT_CODE,
    SCHEDULER_LAUNCH_AGENT_FILENAME,
    SCHEDULER_SCHEMA_VERSION,
    SCHEDULER_WRAPPER_FILENAME,
    SchedulerIntegrityError,
    SchedulerPhaseContext,
    build_run_drawing_phase_command,
    build_scheduler_plan,
    load_scheduler_plan,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
)
from toto_ai.runner.training_package import TrainingPackageDeferred

UTC = timezone.utc


def _env(path: Path) -> Path:
    path.write_text("API_SPORTS_KEY=test-only\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _config(tmp_path: Path) -> MorningDispatchConfig:
    write_empty_schedule_evidence_ledger(tmp_path)
    return MorningDispatchConfig(
        project_root=tmp_path,
        state_root=tmp_path / "data" / "scheduler" / "morning-dispatch",
        scheduler_root=tmp_path / "reports" / "rehearsal",
        env_file=_env(tmp_path / ".env"),
        bank=4980,
        stake=30,
    )


def _prepared(
    *,
    number: int,
    drawing_id: int,
    deadline: datetime,
    fingerprint: str = "a" * 64,
    status: str = "ready",
    mapped: int = 15,
    eligibility: str = "playable",
    span_days: int | None = 1,
    not_ready_reason: str | None = None,
    reviewed_catalog_hash: str | None = None,
) -> MorningPreparedDrawing:
    kwargs = dict(
        drawing_id=drawing_id,
        drawing_number=number,
        deadline=deadline,
        drawing_fingerprint=fingerprint,
        detail_sha256="b" * 64,
        preparation_status=status,
        mapped_count=mapped,
        eligibility_status=eligibility,
        span_days=span_days,
        reviewed_catalog_hash=reviewed_catalog_hash,
    )
    if not_ready_reason is not None:
        kwargs["not_ready_reason"] = not_ready_reason
    return MorningPreparedDrawing(**kwargs)


@pytest.mark.parametrize(
    ("span_days", "expected"),
    ((None, None), (0, None), (1, 1), (2, 2)),
)
def test_optional_morning_span_days_maps_no_known_starts_to_null(
    span_days,
    expected,
):
    assert cli._optional_morning_span_days(span_days) == expected


@pytest.mark.parametrize("span_days", (-1, True, 1.5, "1"))
def test_optional_morning_span_days_rejects_invalid_values(span_days):
    with pytest.raises(
        ValueError,
        match="eligibility span_days must be a non-negative integer",
    ):
        cli._optional_morning_span_days(span_days)


def test_activated_morning_dispatch_forwards_exact_reviewed_catalog_hash(
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    reviewed_catalog_hash = "c" * 64
    activations: list[tuple[str, Path]] = []

    result = dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: _prepared(
            number=4966,
            drawing_id=12007,
            deadline=now + timedelta(hours=10),
            reviewed_catalog_hash=reviewed_catalog_hash,
        ),
        activate=lambda label, path: activations.append((label, path)),
        python_command=sys.executable,
    )

    assert result.status == "scheduled"
    assert result.activation_status == "activated"
    assert len(activations) == 1
    plan = load_scheduler_plan(result.plan_path)
    context = SchedulerPhaseContext(
        phase="final",
        plan=plan,
        run_id="test-run",
        run_dir=tmp_path / "run",
        work_dir=tmp_path / "work",
        scheduled_at=now,
        started_at=now,
    )
    command = build_run_drawing_phase_command(
        context,
        python_executable=sys.executable,
    )
    option = command.index("--expected-reviewed-catalog-hash")
    assert command[option + 1] == reviewed_catalog_hash


def _zero_pool_bootstrap(
    *,
    deadline: datetime,
    fingerprint: str = "a" * 64,
) -> MorningPreparedDrawing:
    return _prepared(
        number=4965,
        drawing_id=12004,
        deadline=deadline,
        fingerprint=fingerprint,
        status="not_ready",
        mapped=0,
        eligibility="unknown",
        span_days=None,
        not_ready_reason="totobrief_pool_not_ready",
    )


def test_zero_pool_bootstrap_creates_identity_bound_retry_plan_before_import(
    tmp_path,
):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 3, 14, 6, 20, tzinfo=UTC)
    deadline = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)
    fingerprint = "559c7615626b624cdd5ebefa782c6b96593ff9fb4dfcdbd18a3e6155f3c17af8"

    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _zero_pool_bootstrap(
            deadline=deadline,
            fingerprint=fingerprint,
        ),
        python_command=sys.executable,
        expected_identity=MorningExpectedIdentity(
            drawing_id=12004,
            drawing_number=4965,
            deadline=deadline,
            drawing_fingerprint=fingerprint,
        ),
    )

    assert result.status == "deferred"
    assert result.reason == "totobrief_pool_not_ready"
    assert result.plan_path is None
    plan = json.loads(result.retry_plan_path.read_text(encoding="utf-8"))
    assert plan["identity"]["drawing_id"] == 12004
    assert plan["identity"]["drawing_number"] == 4965
    assert plan["identity"]["deadline"] == "2026-08-04T15:00:00Z"
    assert plan["identity"]["drawing_fingerprint"] == fingerprint
    assert plan["activate_evening"] is True
    assert [item["scheduled_at"] for item in plan["attempts"]] == [
        "2026-08-03T14:17:00Z",
        "2026-08-03T14:37:00Z",
        "2026-08-03T15:07:00Z",
        "2026-08-03T17:07:00Z",
        "2026-08-04T05:00:00Z",
        "2026-08-04T07:30:00Z",
        "2026-08-04T09:00:00Z",
        "2026-08-04T10:00:00Z",
        "2026-08-04T11:00:00Z",
        "2026-08-04T12:00:00Z",
        "2026-08-04T13:00:00Z",
    ]
    assert all("--activate" in item["command"] for item in plan["attempts"])
    assert all(
        "--preflight-retry-child" in item["command"] for item in plan["attempts"]
    )
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))


def test_timing_unknown_retry_plan_keeps_hourly_attempts_until_hard_stop(
    tmp_path,
):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 13, 14, 12, 40, tzinfo=UTC)
    deadline = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    prepared = MorningPreparedDrawing(
        drawing_id=12033,
        drawing_number=4975,
        deadline=deadline,
        drawing_fingerprint="c" * 64,
        detail_sha256="d" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        unresolved_events=(
            MorningUnresolvedEvent(
                event_order=8,
                target_event_id=179606,
                home_team="Анси",
                away_team="Родез",
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
            ),
        ),
        external_coverage_count=14,
        baseline_only_event_orders=(8,),
    )

    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: prepared,
        python_command=sys.executable,
    )

    plan = json.loads(result.retry_plan_path.read_text(encoding="utf-8"))
    assert plan["hard_stop"] == "2026-08-14T13:00:00Z"
    scheduled = [item["scheduled_at"] for item in plan["attempts"]]
    assert scheduled[-3:] == [
        "2026-08-14T10:00:00Z",
        "2026-08-14T11:00:00Z",
        "2026-08-14T12:00:00Z",
    ]


def test_timing_unknown_retry_plan_uses_conservative_operational_cutoff(
    tmp_path,
):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 13, 14, 0, tzinfo=UTC)
    source_deadline = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    operational_cutoff = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    prepared = MorningPreparedDrawing(
        drawing_id=12033,
        drawing_number=4975,
        deadline=source_deadline,
        operational_cutoff=operational_cutoff,
        cutoff_evidence=tmp_path / "conservative-cutoff.json",
        cutoff_evidence_sha256="e" * 64,
        drawing_fingerprint="c" * 64,
        detail_sha256="d" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        unresolved_events=(
            MorningUnresolvedEvent(
                event_order=8,
                target_event_id=179606,
                home_team="Анси",
                away_team="Родез",
                resolution_status="timing_unknown",
                reason="baseline-only event start time is unavailable",
            ),
        ),
        external_coverage_count=14,
        baseline_only_event_orders=(8,),
    )

    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: prepared,
        python_command=sys.executable,
    )

    plan = json.loads(result.retry_plan_path.read_text(encoding="utf-8"))
    assert plan["hard_stop"] == "2026-08-14T09:00:00Z"
    assert all(
        item["scheduled_at"] < "2026-08-14T09:00:00Z" for item in plan["attempts"]
    )


def test_existing_retry_plan_is_atomically_tightened(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 13, 14, 0, tzinfo=UTC)
    deadline = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    unresolved = MorningUnresolvedEvent(
        event_order=8,
        target_event_id=179606,
        home_team="Анси",
        away_team="Родез",
        resolution_status="timing_unknown",
        reason="baseline-only event start time is unavailable",
    )
    initial = MorningPreparedDrawing(
        drawing_id=12033,
        drawing_number=4975,
        deadline=deadline,
        drawing_fingerprint="c" * 64,
        detail_sha256="d" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        unresolved_events=(unresolved,),
        external_coverage_count=14,
        baseline_only_event_orders=(8,),
    )
    first = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: initial,
        python_command=sys.executable,
    )
    tightened = replace(
        initial,
        operational_cutoff=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
        cutoff_evidence=tmp_path / "conservative-cutoff.json",
        cutoff_evidence_sha256="e" * 64,
    )

    second = dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=1),
        now=lambda: observed + timedelta(minutes=1),
        prepare_current=lambda _now: tightened,
        python_command=sys.executable,
    )
    payload = json.loads(second.retry_plan_path.read_text(encoding="utf-8"))

    assert second.retry_plan_path == first.retry_plan_path
    assert payload["hard_stop"] == "2026-08-14T09:00:00Z"
    assert payload["identity"]["operational_cutoff"] == "2026-08-14T10:00:00Z"


def test_existing_retry_plan_keeps_schedule_for_same_cutoff_refresh(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 13, 14, 0, tzinfo=UTC)
    deadline = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
    cutoff = datetime(2026, 8, 14, 10, 0, tzinfo=UTC)
    unresolved = MorningUnresolvedEvent(
        event_order=8,
        target_event_id=179606,
        home_team="Анси",
        away_team="Родез",
        resolution_status="timing_unknown",
        reason="baseline-only event start time is unavailable",
    )
    initial = MorningPreparedDrawing(
        drawing_id=12033,
        drawing_number=4975,
        deadline=deadline,
        operational_cutoff=cutoff,
        cutoff_evidence=tmp_path / "cutoff-first.json",
        cutoff_evidence_sha256="e" * 64,
        drawing_fingerprint="c" * 64,
        detail_sha256="d" * 64,
        preparation_status="ready",
        mapped_count=15,
        eligibility_status="unknown",
        span_days=None,
        unresolved_events=(unresolved,),
        external_coverage_count=14,
        baseline_only_event_orders=(8,),
    )
    first = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: initial,
        python_command=sys.executable,
    )
    refreshed = replace(
        initial,
        cutoff_evidence=tmp_path / "cutoff-refreshed.json",
        cutoff_evidence_sha256="f" * 64,
    )

    second = dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=1),
        now=lambda: observed + timedelta(minutes=1),
        prepare_current=lambda _now: refreshed,
        python_command=sys.executable,
    )
    payload = json.loads(second.retry_plan_path.read_text(encoding="utf-8"))

    assert second.retry_plan_path == first.retry_plan_path
    assert payload["identity"]["operational_cutoff"] == "2026-08-14T10:00:00Z"
    assert payload["identity"]["cutoff_evidence_sha256"] == "e" * 64
    assert payload["runner_version"] == 2


def test_zero_pool_retry_recovers_to_one_activated_evening_scheduler(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2026, 8, 3, 14, 6, tzinfo=UTC)
    deadline = datetime(2026, 8, 4, 15, 0, tzinfo=UTC)
    fingerprint = "559c7615626b624cdd5ebefa782c6b96593ff9fb4dfcdbd18a3e6155f3c17af8"
    activations: list[tuple[str, Path]] = []

    deferred = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _zero_pool_bootstrap(
            deadline=deadline,
            fingerprint=fingerprint,
        ),
        python_command=sys.executable,
    )
    ready = _prepared(
        number=4965,
        drawing_id=12004,
        deadline=deadline,
        fingerprint=fingerprint,
    )
    scheduled = dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=10),
        now=lambda: observed + timedelta(minutes=10),
        prepare_current=lambda _now: ready,
        activate=lambda label, path: activations.append((label, path)),
        python_command=sys.executable,
    )
    reused = dispatch_morning(
        config,
        observed_at=observed + timedelta(minutes=11),
        now=lambda: observed + timedelta(minutes=11),
        prepare_current=lambda _now: ready,
        activate=lambda label, path: activations.append((label, path)),
        python_command=sys.executable,
    )

    assert deferred.status == "deferred"
    assert scheduled.status == "scheduled"
    assert scheduled.activation_status == "activated"
    assert reused.status == "reused"
    assert reused.activation_status == "activated"
    assert len(activations) == 1
    assert len(tuple(config.scheduler_root.rglob("scheduler-plan.json"))) == 1


def test_dynamic_dispatcher_rolls_to_new_drawing_without_stale_identity(tmp_path):
    config = _config(tmp_path)
    day_one = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    day_two = day_one + timedelta(days=1)

    first = dispatch_morning(
        config,
        observed_at=day_one,
        now=lambda: day_one,
        prepare_current=lambda _now: _prepared(
            number=4953,
            drawing_id=11972,
            deadline=day_one + timedelta(hours=10),
        ),
        python_command=sys.executable,
    )
    second = dispatch_morning(
        config,
        observed_at=day_two,
        now=lambda: day_two,
        prepare_current=lambda _now: _prepared(
            number=4958,
            drawing_id=11986,
            deadline=day_two + timedelta(hours=10),
            fingerprint="c" * 64,
        ),
        python_command=sys.executable,
    )

    assert first.status == "scheduled"
    assert second.status == "scheduled"
    assert first.plan_id != second.plan_id
    assert json.loads(first.plan_path.read_text())["target"]["drawing"] == 4953
    assert json.loads(second.plan_path.read_text())["target"]["drawing"] == 4958


def test_same_drawing_is_idempotent_and_activates_once(tmp_path):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4958,
        drawing_id=11986,
        deadline=now + timedelta(hours=10),
    )
    activations: list[tuple[str, Path]] = []

    def activate(label: str, plist_path: Path) -> None:
        activations.append((label, plist_path))

    first = dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: evidence,
        activate=activate,
        python_command=sys.executable,
    )
    second = dispatch_morning(
        config,
        observed_at=now + timedelta(minutes=30),
        now=lambda: now + timedelta(minutes=30),
        prepare_current=lambda _now: evidence,
        activate=activate,
        python_command=sys.executable,
    )

    assert first.status == "scheduled"
    assert second.status == "reused"
    assert first.plan_id == second.plan_id
    assert len(activations) == 1
    assert second.activation_status == "activated"
    candidate = plistlib.loads(first.launch_agent_path.read_bytes())
    expected_label = candidate["Label"]
    record = json.loads(first.record_path.read_text(encoding="utf-8"))
    assert activations[0] == (expected_label, first.launch_agent_path)
    assert first.launch_agent_label == expected_label
    assert second.launch_agent_label == expected_label
    assert record["launch_agent_label"] == expected_label


def test_actual_4964_current_plan_candidate_label_is_installable(
    tmp_path: Path,
) -> None:
    production_plan = build_scheduler_plan(
        drawing=4964,
        drawing_id=12003,
        ended_at="2026-08-03T14:00:00Z",
        bank=4980,
        output_dir=(
            "/Users/turshevr/toto-ai/reports/rehearsal/evening-4964-20260803T140000Z"
        ),
        project_root="/Users/turshevr/toto-ai",
        db="/Users/turshevr/toto-ai/data/toto.db",
        aliases=("/Users/turshevr/toto-ai/data/external-odds/team-aliases.json"),
        reviewed_schedule_catalog=(
            "/Users/turshevr/toto-ai/data/reviewed-schedule/4964/catalog.json"
        ),
        reviewed_catalog_sha256=(
            "68e98c8f006ddca04e193a1d06d3f23def57e498f4c02c51d8a9e3c18062895a"
        ),
        env_file="/Users/turshevr/toto-ai/.env",
    )
    assert len(production_plan.plan_id) == 16
    assert production_plan.schedule_evidence_ledger_sha256 is not None

    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4964,
        drawing_id=12003,
        ended_at="2026-08-03T14:00:00Z",
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    candidate_path = artifacts.launch_agent_path
    candidate = plistlib.loads(candidate_path.read_bytes())
    calls: list[tuple[str, ...]] = []

    def command_runner(command, **_kwargs):
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0, stderr="")

    assert candidate["Label"] == (
        f"com.totoai.production-scheduler.v{SCHEDULER_SCHEMA_VERSION}.{plan.plan_id}"
    )

    activate_scheduler_launch_agent(
        candidate["Label"],
        candidate_path,
        launch_agents_root=tmp_path / "LaunchAgents",
        command_runner=command_runner,
    )

    installed = tmp_path / "LaunchAgents" / f"{candidate['Label']}.plist"
    assert installed.read_bytes() == candidate_path.read_bytes()
    assert calls == [
        (
            "launchctl",
            "bootstrap",
            f"gui/{os.getuid()}",
            str(installed),
        )
    ]


@pytest.mark.parametrize(
    "tamper",
    (
        lambda payload: payload.__setitem__("schema_version", 4),
        lambda payload: payload.__setitem__("plan_id", "0" * 16),
        lambda payload: payload["target"].__setitem__("drawing", 4965),
        lambda payload: payload["target"].__setitem__(
            "ended_at", "2032-01-01T17:01:00Z"
        ),
    ),
)
def test_scheduler_installer_rejects_tampered_plan_identity(
    tmp_path: Path,
    tamper,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4964,
        drawing_id=12003,
        ended_at=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    candidate = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    tampered = deepcopy(payload)
    tamper(tampered)
    artifacts.plan_path.write_text(
        json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises((ValueError, SchedulerIntegrityError)):
        activate_scheduler_launch_agent(
            candidate["Label"],
            artifacts.launch_agent_path,
            launch_agents_root=tmp_path / "LaunchAgents",
            command_runner=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0, stderr=""
            ),
        )

    assert not (tmp_path / "LaunchAgents").exists()


def test_scheduler_installer_rejects_arbitrary_matching_candidate_label(
    tmp_path: Path,
) -> None:
    write_empty_schedule_evidence_ledger(tmp_path)
    plan = build_scheduler_plan(
        drawing=4964,
        drawing_id=12003,
        ended_at=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
        bank=4980,
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        db=tmp_path / "toto.db",
        aliases=tmp_path / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    candidate = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    arbitrary_label = (
        f"com.totoai.production-scheduler.v{SCHEDULER_SCHEMA_VERSION}." + "0" * 16
    )
    candidate["Label"] = arbitrary_label
    artifacts.launch_agent_path.write_bytes(
        plistlib.dumps(candidate, fmt=plistlib.FMT_XML, sort_keys=True)
    )

    with pytest.raises((ValueError, SchedulerIntegrityError)):
        activate_scheduler_launch_agent(
            arbitrary_label,
            artifacts.launch_agent_path,
            launch_agents_root=tmp_path / "LaunchAgents",
            command_runner=lambda *_args, **_kwargs: SimpleNamespace(
                returncode=0, stderr=""
            ),
        )

    assert not (tmp_path / "LaunchAgents").exists()


def test_activation_failure_persists_generated_state_and_retry_reuses_artifacts(
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4958,
        drawing_id=11986,
        deadline=now + timedelta(hours=10),
    )
    activations: list[tuple[str, Path]] = []

    def activate(label: str, plist_path: Path) -> None:
        activations.append((label, plist_path))
        if len(activations) == 1:
            raise RuntimeError("temporary launchctl bootstrap failure")

    with pytest.raises(RuntimeError, match="temporary launchctl"):
        dispatch_morning(
            config,
            observed_at=now,
            now=lambda: now,
            prepare_current=lambda _now: evidence,
            activate=activate,
            python_command=sys.executable,
        )

    records = tuple(config.state_root.glob("*.json"))
    assert len(records) == 1
    persisted = json.loads(records[0].read_text(encoding="utf-8"))
    assert persisted["status"] == "scheduled"
    assert persisted["activation_status"] == "generated"
    plans_before_retry = tuple(config.scheduler_root.rglob("scheduler-plan.json"))
    assert len(plans_before_retry) == 1

    recovered = dispatch_morning(
        config,
        observed_at=now + timedelta(minutes=1),
        now=lambda: now + timedelta(minutes=1),
        prepare_current=lambda _now: evidence,
        activate=activate,
        python_command=sys.executable,
    )

    assert recovered.status == "reused"
    assert recovered.activation_status == "activated"
    assert len(activations) == 2
    assert tuple(config.scheduler_root.rglob("scheduler-plan.json")) == (
        plans_before_retry
    )


@pytest.mark.parametrize(
    "artifact_name",
    (
        "scheduler-plan.json",
        SCHEDULER_WRAPPER_FILENAME,
        SCHEDULER_LAUNCH_AGENT_FILENAME,
    ),
)
def test_activation_retry_rejects_tampered_scheduler_artifact(
    tmp_path,
    artifact_name,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4958,
        drawing_id=11986,
        deadline=now + timedelta(hours=10),
    )
    activation_calls = 0

    def fail_first_activation(_label: str, _plist_path: Path) -> None:
        nonlocal activation_calls
        activation_calls += 1
        raise RuntimeError("temporary launchctl bootstrap failure")

    with pytest.raises(RuntimeError, match="temporary launchctl"):
        dispatch_morning(
            config,
            observed_at=now,
            now=lambda: now,
            prepare_current=lambda _now: evidence,
            activate=fail_first_activation,
            python_command=sys.executable,
        )

    record_path = next(config.state_root.glob("*.json"))
    persisted = json.loads(record_path.read_text(encoding="utf-8"))
    plan_path = Path(persisted["plan_path"])
    artifact_path = plan_path.parent / artifact_name
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")
    retried_activations: list[tuple[str, Path]] = []

    with pytest.raises(
        SchedulerIntegrityError,
        match="artifact.*conflicts",
    ):
        dispatch_morning(
            config,
            observed_at=now + timedelta(minutes=1),
            now=lambda: now + timedelta(minutes=1),
            prepare_current=lambda _now: evidence,
            activate=lambda label, path: retried_activations.append((label, path)),
            python_command=sys.executable,
        )

    assert activation_calls == 1
    assert retried_activations == []
    persisted_after = json.loads(record_path.read_text(encoding="utf-8"))
    assert persisted_after["activation_status"] == "generated"


def test_existing_exact_artifacts_are_reused_after_crash_before_record_write(
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4958,
        drawing_id=11986,
        deadline=now + timedelta(hours=10),
    )
    output_dir = config.scheduler_root / (
        f"evening-{evidence.drawing_number}-"
        f"{evidence.deadline.strftime('%Y%m%dT%H%M%SZ')}"
    )
    from toto_ai.runner.scheduler import (
        build_scheduler_plan,
        prepare_scheduler_artifacts,
    )

    plan = build_scheduler_plan(
        drawing=evidence.drawing_number,
        drawing_id=evidence.drawing_id,
        ended_at=evidence.deadline,
        bank=config.bank,
        stake=config.stake,
        output_dir=output_dir,
        project_root=config.project_root,
        db=config.db,
        aliases=config.aliases,
        timing_overrides=config.timing_overrides,
        schedule_evidence_ledger=config.schedule_evidence_ledger,
        env_file=config.env_file,
    )
    prepare_scheduler_artifacts(plan, python_command=sys.executable)

    result = dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: evidence,
        python_command=sys.executable,
    )

    assert result.status == "scheduled"
    assert result.plan_id == plan.plan_id
    assert len(tuple(config.scheduler_root.rglob("scheduler-plan.json"))) == 1


def test_same_multi_day_drawing_next_morning_reuses_exact_plan(tmp_path):
    config = _config(tmp_path)
    first_morning = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4958,
        drawing_id=11986,
        deadline=first_morning + timedelta(days=1, hours=10),
        span_days=2,
    )

    first = dispatch_morning(
        config,
        observed_at=first_morning,
        now=lambda: first_morning,
        prepare_current=lambda _now: evidence,
        python_command=sys.executable,
    )
    second = dispatch_morning(
        config,
        observed_at=first_morning + timedelta(days=1),
        now=lambda: first_morning + timedelta(days=1),
        prepare_current=lambda _now: evidence,
        python_command=sys.executable,
    )

    assert first.status == "scheduled"
    assert second.status == "reused"
    assert second.plan_id == first.plan_id
    assert second.record_path == first.record_path
    assert len(tuple(config.scheduler_root.rglob("scheduler-plan.json"))) == 1


def test_same_drawing_retries_deferred_preparation_without_duplicate_plan(
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    deadline = now + timedelta(hours=10)

    deferred = dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: _prepared(
            number=4958,
            drawing_id=11986,
            deadline=deadline,
            status="unresolved",
            mapped=14,
        ),
        python_command=sys.executable,
    )
    scheduled = dispatch_morning(
        config,
        observed_at=now + timedelta(minutes=30),
        now=lambda: now + timedelta(minutes=30),
        prepare_current=lambda _now: _prepared(
            number=4958,
            drawing_id=11986,
            deadline=deadline,
            fingerprint="c" * 64,
        ),
        python_command=sys.executable,
    )
    reused = dispatch_morning(
        config,
        observed_at=now + timedelta(hours=1),
        now=lambda: now + timedelta(hours=1),
        prepare_current=lambda _now: _prepared(
            number=4958,
            drawing_id=11986,
            deadline=deadline,
            fingerprint="c" * 64,
        ),
        python_command=sys.executable,
    )

    assert deferred.status == "deferred"
    assert scheduled.status == "scheduled"
    assert reused.status == "reused"
    assert scheduled.plan_id == reused.plan_id
    assert len(tuple(config.scheduler_root.rglob("scheduler-plan.json"))) == 1


def test_prepared_artifact_free_record_accepts_validated_reviewed_hash(
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    deadline = now + timedelta(hours=10)
    fingerprint = "a" * 64

    prepared = dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: _prepared(
            number=4966,
            drawing_id=12007,
            deadline=deadline,
            fingerprint=fingerprint,
            eligibility="unknown",
            span_days=None,
        ),
        python_command=sys.executable,
    )
    scheduled = dispatch_morning(
        config,
        observed_at=now + timedelta(minutes=30),
        now=lambda: now + timedelta(minutes=30),
        prepare_current=lambda _now: _prepared(
            number=4966,
            drawing_id=12007,
            deadline=deadline,
            fingerprint=fingerprint,
            reviewed_catalog_hash="c" * 64,
        ),
        python_command=sys.executable,
    )

    assert prepared.status == "prepared"
    assert scheduled.status == "scheduled"
    assert scheduled.record_path == prepared.record_path
    assert len(tuple(config.scheduler_root.rglob("scheduler-plan.json"))) == 1
    persisted = json.loads(scheduled.record_path.read_text(encoding="utf-8"))
    assert persisted["identity"]["reviewed_catalog_hash"] == "c" * 64


@pytest.mark.parametrize(
    "mutation",
    (
        lambda prior, _evidence: prior.__setitem__("status", "scheduled"),
        lambda prior, _evidence: prior.__setitem__("activation_status", "activated"),
        lambda prior, _evidence: prior.__setitem__("plan_id", "plan-id"),
        lambda prior, _evidence: prior.__setitem__("package_path", "/tmp/package.csv"),
        lambda prior, _evidence: prior["identity"].__setitem__(
            "drawing_fingerprint", "d" * 64
        ),
        lambda prior, _evidence: prior["identity"].__setitem__("drawing_id", 12008),
        lambda prior, _evidence: prior["identity"].__setitem__(
            "deadline", "2032-01-01T18:00:00Z"
        ),
    ),
)
def test_deferred_reviewed_hash_transition_rejects_unsafe_state_or_identity(
    mutation,
):
    evidence = _prepared(
        number=4966,
        drawing_id=12007,
        deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
        reviewed_catalog_hash="c" * 64,
    )
    prior = {
        "status": "deferred",
        "activation_status": "not_requested",
        "plan_id": None,
        "plan_path": None,
        "launch_agent_path": None,
        "launch_agent_label": None,
        "identity": {
            **evidence.identity_payload(),
            "reviewed_catalog_hash": None,
        },
    }
    mutation(prior, evidence)

    assert not _allows_deferred_reviewed_hash_transition(prior, evidence)


def test_deferred_artifact_free_record_accepts_reviewed_hash_advancement():
    evidence = _prepared(
        number=4966,
        drawing_id=12007,
        deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
        reviewed_catalog_hash="c" * 64,
    )
    prior = {
        "status": "deferred",
        "activation_status": "not_requested",
        "plan_id": None,
        "plan_path": None,
        "launch_agent_path": None,
        "launch_agent_label": None,
        "identity": {
            **evidence.identity_payload(),
            "reviewed_catalog_hash": "b" * 64,
        },
    }

    assert _allows_deferred_reviewed_hash_transition(prior, evidence)


def test_scheduled_record_rejects_reviewed_hash_mutation(tmp_path):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    deadline = now + timedelta(hours=10)

    dispatch_morning(
        config,
        observed_at=now,
        now=lambda: now,
        prepare_current=lambda _now: _prepared(
            number=4966,
            drawing_id=12007,
            deadline=deadline,
        ),
        python_command=sys.executable,
    )

    with pytest.raises(ValueError, match="morning dispatch identity conflict"):
        dispatch_morning(
            config,
            observed_at=now + timedelta(minutes=30),
            now=lambda: now + timedelta(minutes=30),
            prepare_current=lambda _now: _prepared(
                number=4966,
                drawing_id=12007,
                deadline=deadline,
                reviewed_catalog_hash="c" * 64,
            ),
            python_command=sys.executable,
        )


@pytest.mark.parametrize(
    ("evidence", "status", "reason"),
    [
        (
            _prepared(
                number=4958,
                drawing_id=11986,
                deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
                status="unresolved",
                mapped=14,
            ),
            "deferred",
            "ACTION REQUIRED: unresolved 1/15",
        ),
        (
            _prepared(
                number=4958,
                drawing_id=11986,
                deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
                eligibility="multi_day",
                span_days=4,
            ),
            "prepared",
            "drawing_not_playable",
        ),
        (
            _prepared(
                number=4958,
                drawing_id=11986,
                deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
                eligibility="unknown",
                span_days=6,
            ),
            "deferred",
            "drawing_span_exceeds_five_days",
        ),
    ],
)
def test_ineligible_preparation_never_creates_evening_plan(
    tmp_path,
    evidence,
    status,
    reason,
):
    config = _config(tmp_path)
    result = dispatch_morning(
        config,
        observed_at=datetime(2032, 1, 1, 7, 0, tzinfo=UTC),
        now=lambda: datetime(2032, 1, 1, 7, 0, tzinfo=UTC),
        prepare_current=lambda _now: evidence,
        python_command=sys.executable,
    )

    assert result.status == status
    assert result.reason == reason
    assert result.plan_path is None
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))


def test_ready_non_playable_morning_is_preserved_as_prepared(tmp_path):
    config = _config(tmp_path)
    observed = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)

    result = dispatch_morning(
        config,
        observed_at=observed,
        now=lambda: observed,
        prepare_current=lambda _now: _prepared(
            number=4972,
            drawing_id=12024,
            deadline=observed + timedelta(hours=11),
            eligibility="unknown",
            span_days=1,
        ),
        python_command=sys.executable,
    )

    assert result.status == "prepared"
    assert result.reason == "drawing_not_playable"
    assert result.plan_path is None
    assert result.activation_status == "not_requested"
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))
    record = json.loads(result.record_path.read_text(encoding="utf-8"))
    assert record["status"] == "prepared"
    assert record["preparation"] == {
        "baseline_only_event_orders": [],
        "external_coverage_count": 15,
        "eligibility_status": "unknown",
        "mapped_count": 15,
        "not_ready_reason": None,
        "span_days": 1,
        "status": "ready",
        "unresolved": [],
    }
    assert record["playability"] == {
        "playable": False,
        "reason": "drawing_not_playable",
        "span_days": 1,
        "status": "unknown",
    }


def test_prepared_morning_cli_result_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="prepared",
            reason="drawing_not_playable",
            record_path=tmp_path / "prepared.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(tmp_path / ".env"),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "prepared"
    assert payload["training_package"] is None


def test_reused_morning_cli_still_collects_goal_shadow(monkeypatch, tmp_path):
    config = _config(tmp_path)
    observed = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    evidence = _prepared(
        number=4988,
        drawing_id=12071,
        deadline=observed + timedelta(hours=12),
    )

    monkeypatch.setattr(
        cli,
        "_prepare_current_for_morning",
        lambda **_kwargs: evidence,
    )

    def reused_dispatch(_config, *, observed_at, prepare_current, **_kwargs):
        prepare_current(observed_at)
        return MorningDispatchResult(
            status="reused",
            reason="ready",
            record_path=tmp_path / "ready.json",
            plan_id="plan",
            plan_path=None,
            launch_agent_path=None,
            activation_status="activated",
        )

    monkeypatch.setattr(cli, "dispatch_morning", reused_dispatch)
    monkeypatch.setattr(cli, "load_goal_api_key", lambda _path: "goal-secret")
    monkeypatch.setattr(
        cli,
        "ensure_goal_probe_input",
        lambda **_kwargs: SimpleNamespace(
            event_count=15,
            history_source_count=30,
            sports_eligible_count=15,
            request_count=0,
            quota_daily_remaining=900,
            captured_at=observed,
            coverage_summary_path=tmp_path / "coverage-summary.json",
            reused=True,
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(config.env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
            "--goal-shadow-auto",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "reused"
    assert payload["sports_shadow"]["status"] == ("PAPER_ONLY_COVERAGE_PROBE_READY")
    assert payload["sports_shadow"]["reused"] is True
    assert payload["sports_shadow"]["package_influence"] == "NONE"


def test_ready_morning_cli_ensures_scheduler_owned_training_package(
    monkeypatch,
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    plan = build_scheduler_plan(
        drawing=4982,
        drawing_id=12054,
        ended_at=now + timedelta(hours=10),
        bank=4980,
        stake=30,
        output_dir=config.scheduler_root / "evening-4982",
        project_root=config.project_root,
        db=config.db,
        aliases=config.aliases,
        env_file=config.env_file,
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="scheduled",
            reason="ready",
            record_path=tmp_path / "ready.json",
            plan_id=plan.plan_id,
            plan_path=artifacts.plan_path,
            launch_agent_path=artifacts.launch_agent_path,
            activation_status="generated",
        ),
    )
    calls: list[tuple[str, Path, Path]] = []

    def ensure_training(
        loaded_plan,
        *,
        morning_record_path,
        input_cache_dir,
        generated_at,
    ):
        del generated_at
        calls.append(
            (
                loaded_plan.plan_id,
                Path(morning_record_path),
                Path(input_cache_dir),
            )
        )
        root = loaded_plan.output_dir / "training-package"
        return SimpleNamespace(
            result_path=root / "training-package-result.json",
            input_path=root / "input" / "final-input.json",
            paper_path=root / "checkpoints" / "abc" / "training-paper-package.txt",
            diagnostics_path=(
                root / "checkpoints" / "abc" / "training-quality-v2.json"
            ),
            requested_bank=4980,
            effective_budget=660,
            selected_count=22,
            selected_cost=660,
            unused_requested_bank=4320,
            bank_usage_reason="pool_cap",
            source_archive_path=(
                loaded_plan.project_root
                / "data"
                / "raw"
                / "archive"
                / "drawing_12054"
                / "a.json"
            ),
            source_archive_snapshot_sha256="a" * 64,
            package_sha256="d" * 64,
            actionable=False,
            mode="TRAINING_PAPER",
            pipeline="production_quality_v2_ev",
            structural_status="STRUCTURAL_PASS",
        )

    monkeypatch.setattr(
        cli,
        "ensure_scheduler_training_package",
        ensure_training,
        raising=False,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(config.env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert calls == [(plan.plan_id, tmp_path / "ready.json", tmp_path / "data" / "raw")]
    assert payload["training_package"] == {
        "actionable": False,
        "bank_usage_reason": "pool_cap",
        "diagnostics_path": str(
            plan.output_dir
            / "training-package"
            / "checkpoints"
            / "abc"
            / "training-quality-v2.json"
        ),
        "effective_budget": 660,
        "input_path": str(
            plan.output_dir / "training-package" / "input" / "final-input.json"
        ),
        "mode": "TRAINING_PAPER",
        "package_sha256": "d" * 64,
        "pipeline": "production_quality_v2_ev",
        "paper_path": str(
            plan.output_dir
            / "training-package"
            / "checkpoints"
            / "abc"
            / "training-paper-package.txt"
        ),
        "requested_bank": 4980,
        "result_path": str(
            plan.output_dir / "training-package" / "training-package-result.json"
        ),
        "selected_cost": 660,
        "selected_count": 22,
        "source_archive_path": str(
            tmp_path / "data" / "raw" / "archive" / "drawing_12054" / "a.json"
        ),
        "source_archive_snapshot_sha256": "a" * 64,
        "status": "ready",
        "structural_status": "STRUCTURAL_PASS",
        "unused_requested_bank": 4320,
    }


def test_training_failure_preserves_successful_morning_activation(
    monkeypatch,
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    plan = build_scheduler_plan(
        drawing=4982,
        drawing_id=12054,
        ended_at=now + timedelta(hours=10),
        bank=4980,
        stake=30,
        output_dir=config.scheduler_root / "evening-4982",
        project_root=config.project_root,
        db=config.db,
        aliases=config.aliases,
        env_file=config.env_file,
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="scheduled",
            reason="ready",
            record_path=tmp_path / "ready.json",
            plan_id=plan.plan_id,
            plan_path=artifacts.plan_path,
            launch_agent_path=artifacts.launch_agent_path,
            activation_status="activated",
        ),
    )
    monkeypatch.setattr(
        cli,
        "ensure_scheduler_training_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("quality-v2 training failed")
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(config.env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
            "--activate",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "scheduled"
    assert payload["activation_status"] == "activated"
    assert payload["training_package"] == {
        "error": "ValueError: quality-v2 training failed",
        "status": "failed",
    }


def test_training_pool_capacity_deferral_preserves_morning_activation(
    monkeypatch,
    tmp_path,
):
    config = _config(tmp_path)
    now = datetime(2032, 1, 1, 7, 0, tzinfo=UTC)
    plan = build_scheduler_plan(
        drawing=4982,
        drawing_id=12054,
        ended_at=now + timedelta(hours=10),
        bank=4980,
        stake=30,
        output_dir=config.scheduler_root / "evening-4982",
        project_root=config.project_root,
        db=config.db,
        aliases=config.aliases,
        env_file=config.env_file,
    )
    artifacts = prepare_scheduler_artifacts(plan, python_command=sys.executable)
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="scheduled",
            reason="ready",
            record_path=tmp_path / "ready.json",
            plan_id=plan.plan_id,
            plan_path=artifacts.plan_path,
            launch_agent_path=artifacts.launch_agent_path,
            activation_status="activated",
        ),
    )
    monkeypatch.setattr(
        cli,
        "ensure_scheduler_training_package",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TrainingPackageDeferred(
                "current pool supports only 180 RUB / 6 coupons"
            )
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(config.env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(config.state_root),
            "--scheduler-root",
            str(config.scheduler_root),
            "--activate",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "scheduled"
    assert payload["activation_status"] == "activated"
    assert payload["training_package"] == {
        "detail": "current pool supports only 180 RUB / 6 coupons",
        "reason": "pool_supported_capacity_infeasible",
        "status": "deferred",
    }


def test_morning_dispatch_forwards_env_file_to_immediate_preparation(
    monkeypatch,
    tmp_path,
):
    env_file = _env(tmp_path / ".env")
    captured: dict[str, Path] = {}

    def prepare_current_for_morning(*, observed_at, env_file, **_kwargs):
        captured["env_file"] = env_file
        return _prepared(
            number=4982,
            drawing_id=12054,
            deadline=observed_at + timedelta(hours=10),
        )

    def dispatch(_config, *, observed_at, prepare_current, **_kwargs):
        prepare_current(observed_at)
        return MorningDispatchResult(
            status="prepared",
            reason="drawing_not_playable",
            record_path=tmp_path / "prepared.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
        )

    monkeypatch.setattr(
        cli,
        "_prepare_current_for_morning",
        prepare_current_for_morning,
    )
    monkeypatch.setattr(cli, "dispatch_morning", dispatch)

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == {"env_file": env_file}


def test_deferred_activated_cli_installs_identity_bound_retry_job(
    monkeypatch,
    tmp_path,
):
    retry_plan = tmp_path / "retry-plan.json"
    retry_plan.write_text("{}\n", encoding="utf-8")
    artifacts = SimpleNamespace(label="com.totoai.preflight-retry.12033.c" * 1)
    installed: list[object] = []
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="deferred",
            reason="ACTION REQUIRED: timing unknown 1/15",
            record_path=tmp_path / "deferred.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
            retry_plan_path=retry_plan,
        ),
    )
    monkeypatch.setattr(
        cli,
        "prepare_preflight_retry_artifacts",
        lambda path: artifacts if path == retry_plan else None,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "install_preflight_retry_launch_agent",
        lambda value: (
            installed.append(value) or {"active": True, "label": artifacts.label}
        ),
        raising=False,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(tmp_path / ".env"),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--activate",
        ],
    )

    assert result.exit_code == MORNING_DEFERRED_EXIT_CODE, result.output
    payload = json.loads(result.output)
    assert payload["retry_scheduler"]["active"] is True
    assert installed == [artifacts]


def test_retry_child_never_reinstalls_its_own_launch_agent(monkeypatch, tmp_path):
    retry_plan = tmp_path / "retry-plan.json"
    retry_plan.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="deferred",
            reason="ACTION REQUIRED: timing unknown 1/15",
            record_path=tmp_path / "deferred.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
            retry_plan_path=retry_plan,
        ),
    )
    monkeypatch.setattr(
        cli,
        "prepare_preflight_retry_artifacts",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("retry child must not regenerate its own artifacts")
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(tmp_path / ".env"),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--activate",
            "--preflight-retry-child",
        ],
    )

    assert result.exit_code == MORNING_DEFERRED_EXIT_CODE, result.output
    assert json.loads(result.output)["retry_scheduler"] is None


def test_ready_dispatch_cleans_obsolete_preflight_retry_job(monkeypatch, tmp_path):
    env_file = _env(tmp_path / ".env")
    evidence = _prepared(
        number=4990,
        drawing_id=12077,
        deadline=datetime(2026, 8, 29, 16, 30, tzinfo=UTC),
    )
    state_root = tmp_path / "state"
    deadline = evidence.deadline.strftime("%Y%m%dT%H%M%SZ")
    retry_plan = (
        state_root
        / "preflight"
        / (
            f"drawing-{evidence.drawing_id}-{deadline}-"
            f"{evidence.drawing_fingerprint[:16]}"
        )
        / "retry-plan.json"
    )
    retry_plan.parent.mkdir(parents=True)
    retry_plan.write_text("{}\n", encoding="utf-8")
    artifacts = SimpleNamespace(label="com.totoai.preflight-retry.12077.test")
    cleaned: list[object] = []

    monkeypatch.setattr(
        cli,
        "_prepare_current_for_morning",
        lambda **_kwargs: evidence,
    )

    def dispatch(_config, *, observed_at, prepare_current, **_kwargs):
        assert prepare_current(observed_at) == evidence
        return MorningDispatchResult(
            status="scheduled",
            reason="ready",
            record_path=tmp_path / "scheduled.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="activated",
        )

    monkeypatch.setattr(cli, "dispatch_morning", dispatch)
    monkeypatch.setattr(
        cli,
        "prepare_preflight_retry_artifacts",
        lambda path, *, write: (
            artifacts if path == retry_plan and write is False else None
        ),
    )
    monkeypatch.setattr(
        cli,
        "cleanup_preflight_retry_launch_agent",
        lambda value: cleaned.append(value),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(state_root),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--activate",
        ],
    )

    assert result.exit_code == 0, result.output
    assert cleaned == [artifacts]
    payload = json.loads(result.output)
    assert payload["retry_scheduler"] == {
        "active": False,
        "label": artifacts.label,
        "reason": "drawing_ready",
    }


def test_deferred_activated_cli_runs_independent_and_exact_consensus_collectors(
    monkeypatch,
    tmp_path,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    env_file = _env(tmp_path / ".env")
    retry_plan = tmp_path / "retry-plan.json"
    retry_plan.write_text("{}\n", encoding="utf-8")
    queue = tmp_path / "review-queue.json"
    queue.write_text("{}\n", encoding="utf-8")
    missing_aliases = tmp_path / "missing-team-aliases.json"
    calls: list[tuple[str, Path]] = []
    collector_aliases: list[dict[str, str]] = []
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="deferred",
            reason="ACTION REQUIRED: timing unknown 1/15",
            record_path=tmp_path / "deferred.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
            retry_plan_path=retry_plan,
            review_queue_path=queue,
        ),
    )
    monkeypatch.setattr(
        cli,
        "prepare_preflight_retry_artifacts",
        lambda _path: SimpleNamespace(label="retry-label"),
    )
    monkeypatch.setattr(
        cli,
        "install_preflight_retry_launch_agent",
        lambda _value: {"active": True},
    )
    monkeypatch.setattr(
        cli,
        "collect_schedule_source_candidates",
        lambda path, **kwargs: (
            collector_aliases.append(kwargs["team_aliases"])
            or calls.append(("independent", Path(path)))
            or SimpleNamespace(
                status="CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
                candidate_count=1,
                unresolved_count=0,
                report_path=tmp_path / "independent.json",
            )
        ),
    )
    monkeypatch.setattr(
        cli,
        "promote_uefa_sofascore_consensus",
        lambda path, **_kwargs: (
            calls.append(("consensus", Path(path)))
            or SimpleNamespace(
                status="CONSENSUS_PROMOTED",
                promoted_count=1,
                existing_count=0,
                unresolved_count=0,
                report_path=tmp_path / "consensus.json",
                ledger_semantic_hash="c" * 64,
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "promote_independent_schedule_consensus",
        lambda path, **_kwargs: (
            calls.append(("independent_consensus", Path(path)))
            or SimpleNamespace(
                status="CONSENSUS_PROMOTED",
                promoted_count=1,
                existing_count=0,
                unresolved_count=0,
                report_path=tmp_path / "independent-consensus.json",
                ledger_semantic_hash="d" * 64,
            )
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
            "--aliases",
            str(missing_aliases),
            "--activate",
        ],
    )

    assert result.exit_code == MORNING_DEFERRED_EXIT_CODE, result.output
    payload = json.loads(result.output)
    assert calls == [
        ("independent", queue),
        ("consensus", queue),
        ("independent_consensus", queue),
    ]
    assert collector_aliases == [{}]
    assert payload["source_collector"]["independent"]["candidate_count"] == 1
    assert payload["source_collector"]["consensus"]["promoted_count"] == 1
    assert payload["source_collector"]["independent_consensus"]["promoted_count"] == 1


def test_deferred_unactivated_cli_runs_source_collectors_without_installing(
    monkeypatch,
    tmp_path,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    env_file = _env(tmp_path / ".env")
    retry_plan = tmp_path / "retry-plan.json"
    retry_plan.write_text("{}\n", encoding="utf-8")
    queue = tmp_path / "review-queue.json"
    queue.write_text("{}\n", encoding="utf-8")
    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        cli,
        "dispatch_morning",
        lambda *_args, **_kwargs: MorningDispatchResult(
            status="deferred",
            reason="ACTION REQUIRED: timing unknown 1/15",
            record_path=tmp_path / "deferred.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
            retry_plan_path=retry_plan,
            review_queue_path=queue,
        ),
    )
    monkeypatch.setattr(
        cli,
        "install_preflight_retry_launch_agent",
        lambda _value: (_ for _ in ()).throw(
            AssertionError("unactivated rehearsal must not install LaunchAgent")
        ),
    )
    monkeypatch.setattr(
        cli,
        "collect_schedule_source_candidates",
        lambda path, **_kwargs: (
            calls.append(("independent", Path(path)))
            or SimpleNamespace(
                status="CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
                candidate_count=1,
                unresolved_count=0,
                report_path=tmp_path / "independent.json",
            )
        ),
    )
    monkeypatch.setattr(
        cli,
        "promote_uefa_sofascore_consensus",
        lambda path, **_kwargs: (
            calls.append(("consensus", Path(path)))
            or SimpleNamespace(
                status="CONSENSUS_PROMOTED",
                promoted_count=1,
                existing_count=0,
                unresolved_count=0,
                report_path=tmp_path / "consensus.json",
                ledger_semantic_hash="c" * 64,
            )
        ),
    )
    monkeypatch.setattr(
        cli,
        "promote_independent_schedule_consensus",
        lambda path, **_kwargs: (
            calls.append(("independent_consensus", Path(path)))
            or (_ for _ in ()).throw(ValueError("strict independent failure"))
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == MORNING_DEFERRED_EXIT_CODE, result.output
    payload = json.loads(result.output)
    assert calls == [
        ("independent", queue),
        ("consensus", queue),
        ("independent_consensus", queue),
    ]
    assert payload["retry_scheduler"] is None
    assert payload["source_collector"]["independent"]["candidate_count"] == 1
    assert payload["source_collector"]["consensus"]["promoted_count"] == 1
    assert payload["source_collector"]["independent_consensus"] == {
        "status": "INDEPENDENT_CONSENSUS_FAILED",
        "error": "ValueError: strict independent failure",
        "ledger_mutated": False,
    }


@pytest.mark.parametrize(
    ("promoted_count", "existing_count", "initial_ledger_hash"),
    ((1, 0, None), (0, 1, "b" * 64)),
)
def test_consensus_evidence_reprepares_before_final_dispatch(
    monkeypatch,
    tmp_path,
    promoted_count,
    existing_count,
    initial_ledger_hash,
):
    write_empty_schedule_evidence_ledger(tmp_path)
    env_file = _env(tmp_path / ".env")
    queue = tmp_path / "review-queue.json"
    queue.write_text("{}\n", encoding="utf-8")
    unresolved = MorningUnresolvedEvent(
        event_order=0,
        target_event_id=1,
        home_team="Home",
        away_team="Away",
        resolution_status="timing_unknown",
        reason="baseline-only event start time is unavailable",
    )
    initial = replace(
        _prepared(
            number=4987,
            drawing_id=12068,
            deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
            status="not_ready",
            mapped=14,
            eligibility="unknown",
            span_days=None,
            reviewed_catalog_hash=initial_ledger_hash,
        ),
        unresolved_events=(unresolved,),
    )
    refreshed = _prepared(
        number=4987,
        drawing_id=12068,
        deadline=initial.deadline,
    )
    prepare_calls: list[datetime] = []
    dispatch_evidence: list[MorningPreparedDrawing] = []

    def prepare_current_for_morning(*, observed_at, **_kwargs):
        prepare_calls.append(observed_at)
        return initial if len(prepare_calls) == 1 else refreshed

    def dispatch(_config, *, observed_at, prepare_current, **_kwargs):
        evidence = prepare_current(observed_at)
        dispatch_evidence.append(evidence)
        if len(dispatch_evidence) == 1:
            return MorningDispatchResult(
                status="deferred",
                reason="ACTION REQUIRED: timing unknown 1/15",
                record_path=tmp_path / "deferred.json",
                plan_id=None,
                plan_path=None,
                launch_agent_path=None,
                activation_status="not_requested",
                review_queue_path=queue,
            )
        return MorningDispatchResult(
            status="prepared",
            reason="drawing_not_playable",
            record_path=tmp_path / "prepared.json",
            plan_id=None,
            plan_path=None,
            launch_agent_path=None,
            activation_status="not_requested",
        )

    monkeypatch.setattr(
        cli,
        "_prepare_current_for_morning",
        prepare_current_for_morning,
    )
    monkeypatch.setattr(cli, "dispatch_morning", dispatch)
    monkeypatch.setattr(
        cli,
        "collect_schedule_source_candidates",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
            candidate_count=1,
            unresolved_count=0,
            report_path=tmp_path / "independent.json",
        ),
    )
    monkeypatch.setattr(
        cli,
        "derive_conservative_cutoff",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("no cutoff")),
    )
    monkeypatch.setattr(
        cli,
        "promote_uefa_sofascore_consensus",
        lambda *_args, **_kwargs: SimpleNamespace(
            status=("CONSENSUS_PROMOTED" if promoted_count else "CONSENSUS_PARTIAL"),
            promoted_count=promoted_count,
            existing_count=existing_count,
            unresolved_count=0,
            report_path=tmp_path / "consensus.json",
            ledger_semantic_hash="c" * 64,
        ),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-dispatch",
            "--bank",
            "4980",
            "--env-file",
            str(env_file),
            "--project-root",
            str(tmp_path),
            "--state-root",
            str(tmp_path / "state"),
            "--scheduler-root",
            str(tmp_path / "scheduler"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(prepare_calls) == 2
    assert dispatch_evidence == [initial, refreshed]
    assert json.loads(result.output)["status"] == "prepared"


def test_reviewed_alias_names_load_existing_valid_catalog(tmp_path):
    aliases = tmp_path / "team-aliases.json"
    aliases.write_text(
        json.dumps(
            {
                "version": 1,
                "aliases": {"Бавария": "FC Bayern München"},
            }
        ),
        encoding="utf-8",
    )

    assert cli.load_reviewed_alias_names(aliases) == {"Бавария": "FC Bayern München"}


def test_reviewed_alias_names_reject_existing_malformed_catalog(tmp_path):
    aliases = tmp_path / "team-aliases.json"
    aliases.write_text("{\n", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        cli.load_reviewed_alias_names(aliases)


def test_reviewed_alias_names_propagates_unreadable_catalog(
    monkeypatch,
    tmp_path,
):
    aliases = tmp_path / "team-aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    original_read_text = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == aliases:
            raise PermissionError("alias catalog unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)

    with pytest.raises(PermissionError, match="alias catalog unreadable"):
        cli.load_reviewed_alias_names(aliases)


def test_dispatch_after_t_minus_50_does_not_create_partial_schedule(tmp_path):
    config = _config(tmp_path)
    deadline = datetime(2032, 1, 1, 17, 0, tzinfo=UTC)
    result = dispatch_morning(
        config,
        observed_at=deadline - timedelta(minutes=49),
        now=lambda: deadline - timedelta(minutes=49),
        prepare_current=lambda _now: _prepared(
            number=4958,
            drawing_id=11986,
            deadline=deadline,
        ),
        python_command=sys.executable,
    )

    assert result.status == "deferred"
    assert result.reason == "late_dispatch"
    assert result.plan_path is None


def test_dispatch_rechecks_time_after_network_preparation(tmp_path):
    config = _config(tmp_path)
    deadline = datetime(2032, 1, 1, 17, 0, tzinfo=UTC)
    preparation_started_at = deadline - timedelta(hours=2)
    preparation_completed_at = deadline - timedelta(minutes=44)
    preparation_observations = []

    result = dispatch_morning(
        config,
        observed_at=preparation_started_at,
        prepare_current=lambda observed: (
            preparation_observations.append(observed)
            or _prepared(
                number=4958,
                drawing_id=11986,
                deadline=deadline,
            )
        ),
        now=lambda: preparation_completed_at,
        python_command=sys.executable,
    )

    assert preparation_observations == [preparation_started_at]
    assert result.status == "deferred"
    assert result.reason == "late_dispatch"
    assert result.plan_path is None
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))


def test_generic_morning_artifacts_contain_no_drawing_identity(tmp_path):
    config = _config(tmp_path)
    output = config.scheduler_root / "morning-dispatcher"

    artifacts = prepare_morning_preanalysis_artifacts(
        times=("08:00", "10:30"),
        retry_count=2,
        retry_delay_seconds=30.0,
        output_dir=output,
        env_file=config.env_file,
        project_root=config.project_root,
        bank=config.bank,
        stake=config.stake,
        python_command=sys.executable,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert "morning-dispatch" in wrapper
    assert "--expected-drawing-number" not in wrapper
    assert "4953" not in wrapper
    assert "run-drawing" not in wrapper
    assert "--activate" not in wrapper
    assert "--training-category" not in wrapper
    assert f'[ "$status" -eq {MORNING_DEFERRED_EXIT_CODE} ]' in wrapper
    assert "exit 0" in wrapper
    assert plist["Label"] == "com.totoai.morning-dispatcher.v1"
    assert plist["StartInterval"] == 900


def test_generic_morning_artifacts_require_explicit_evening_activation(tmp_path):
    config = _config(tmp_path)
    output = config.scheduler_root / "morning-dispatcher"

    artifacts = prepare_morning_preanalysis_artifacts(
        times=("08:00",),
        retry_count=0,
        retry_delay_seconds=0.0,
        output_dir=output,
        env_file=config.env_file,
        project_root=config.project_root,
        bank=config.bank,
        stake=config.stake,
        activate_evening=True,
        python_command=sys.executable,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    assert "morning-dispatch" in wrapper
    assert "--activate" in wrapper
    assert "export THESPORTSDB_API_KEY" in wrapper
    assert "export THESPORTSDB_BASE_URL" in wrapper
    assert "123" not in wrapper


def test_generated_morning_command_matches_current_cli_contract(tmp_path):
    config = _config(tmp_path)
    output = config.scheduler_root / "morning-dispatcher-contract"
    reviewed_catalog = tmp_path / "data" / "reviewed-schedule.json"

    artifacts = prepare_morning_preanalysis_artifacts(
        times=("08:00",),
        retry_count=0,
        retry_delay_seconds=0.0,
        output_dir=output,
        env_file=config.env_file,
        project_root=config.project_root,
        bank=config.bank,
        stake=config.stake,
        activate_evening=True,
        reviewed_schedule_catalog=reviewed_catalog,
        python_command=sys.executable,
    )

    wrapper_lines = artifacts.wrapper_path.read_text(encoding="utf-8").splitlines()
    command_line = next(line for line in wrapper_lines if line.startswith("  if "))
    command = command_line.removeprefix("  if ").removesuffix("; then")
    argv = shlex.split(command)
    assert argv[:4] == [sys.executable, "-m", "toto_ai.cli", "morning-dispatch"]
    assert "--goal-shadow-auto" in argv

    result = CliRunner().invoke(cli.app, [*argv[3:], "--help"])

    assert result.exit_code == 0, result.output
    assert "No such option" not in result.output

    stale_result = CliRunner().invoke(
        cli.app,
        [*argv[3:], "--training-category", "13", "--help"],
    )
    assert stale_result.exit_code == 2
    assert "No such option: --training-category" in stale_result.output
