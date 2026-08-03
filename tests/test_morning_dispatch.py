from __future__ import annotations

import json
import os
import plistlib
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from toto_ai.runner.morning_dispatch import (
    MorningDispatchConfig,
    MorningPreparedDrawing,
    activate_scheduler_launch_agent,
    dispatch_morning,
)
from toto_ai.runner.scheduler import (
    SCHEDULER_LAUNCH_AGENT_FILENAME,
    SCHEDULER_WRAPPER_FILENAME,
    SchedulerIntegrityError,
    build_scheduler_plan,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
)

UTC = timezone.utc


def _env(path: Path) -> Path:
    path.write_text("API_SPORTS_KEY=test-only\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _config(tmp_path: Path) -> MorningDispatchConfig:
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
) -> MorningPreparedDrawing:
    return MorningPreparedDrawing(
        drawing_id=drawing_id,
        drawing_number=number,
        deadline=deadline,
        drawing_fingerprint=fingerprint,
        detail_sha256="b" * 64,
        preparation_status=status,
        mapped_count=mapped,
        eligibility_status=eligibility,
        span_days=span_days,
    )


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


def test_actual_4964_schema_v5_plan_candidate_label_is_installable(
    tmp_path: Path,
) -> None:
    production_plan = build_scheduler_plan(
        drawing=4964,
        drawing_id=12003,
        ended_at="2026-08-03T14:00:00Z",
        bank=4980,
        output_dir=(
            "/Users/turshevr/toto-ai/reports/rehearsal/"
            "evening-4964-20260803T140000Z"
        ),
        project_root="/Users/turshevr/toto-ai",
        db="/Users/turshevr/toto-ai/data/toto.db",
        aliases=(
            "/Users/turshevr/toto-ai/data/external-odds/team-aliases.json"
        ),
        reviewed_schedule_catalog=(
            "/Users/turshevr/toto-ai/data/reviewed-schedule/4964/catalog.json"
        ),
        reviewed_catalog_sha256=(
            "68e98c8f006ddca04e193a1d06d3f23d"
            "ef57e498f4c02c51d8a9e3c18062895a"
        ),
        env_file="/Users/turshevr/toto-ai/.env",
    )
    assert production_plan.plan_id == "9e4df82511c1e52a"

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

    assert candidate["Label"] == f"com.totoai.production-scheduler.v5.{plan.plan_id}"

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
    arbitrary_label = "com.totoai.production-scheduler.v5." + "0" * 16
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
    plans_before_retry = tuple(
        config.scheduler_root.rglob("scheduler-plan.json")
    )
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
            activate=lambda label, path: retried_activations.append(
                (label, path)
            ),
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


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            _prepared(
                number=4958,
                drawing_id=11986,
                deadline=datetime(2032, 1, 1, 17, 0, tzinfo=UTC),
                status="unresolved",
                mapped=14,
            ),
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
            "drawing_span_exceeds_five_days",
        ),
    ],
)
def test_ineligible_preparation_never_creates_evening_plan(
    tmp_path,
    evidence,
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

    assert result.status == "deferred"
    assert result.reason == reason
    assert result.plan_path is None
    assert not tuple(config.scheduler_root.rglob("scheduler-plan.json"))


def test_dispatch_after_t_minus_45_does_not_create_partial_schedule(tmp_path):
    config = _config(tmp_path)
    deadline = datetime(2032, 1, 1, 17, 0, tzinfo=UTC)
    result = dispatch_morning(
        config,
        observed_at=deadline - timedelta(minutes=44),
        now=lambda: deadline - timedelta(minutes=44),
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
    assert plist["Label"] == "com.totoai.morning-dispatcher.v1"


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
