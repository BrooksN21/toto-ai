from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from toto_ai.runner.preflight_retry_scheduler import (
    install_preflight_retry_launch_agent,
    prepare_preflight_retry_artifacts,
    run_preflight_retry,
    verify_preflight_retry_launch_agent,
)

UTC = timezone.utc


class Result:
    def __init__(self, returncode: int, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


class FakeRunner:
    def __init__(self, morning: list[Result] | None = None) -> None:
        self.loaded = False
        self.bootstrap_count = 0
        self.morning = list(morning or [])
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command, **_kwargs):
        command = tuple(command)
        self.commands.append(command)
        if command[0] != "launchctl":
            return self.morning.pop(0)
        if command[1] == "print":
            return Result(0 if self.loaded else 113)
        if command[1] == "bootstrap":
            self.loaded = True
            self.bootstrap_count += 1
            return Result(0)
        if command[1] == "bootout":
            self.loaded = False
            return Result(0)
        raise AssertionError(command)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _plan(
    path: Path,
    *,
    command_suffix: tuple[str, ...] = (),
    activate_evening: bool = False,
) -> Path:
    identity = {
        "drawing_id": 11993,
        "drawing_number": 4961,
        "deadline": "2026-07-31T16:00:00Z",
        "drawing_fingerprint": (
            "b713fca373c9663e39da777bebcc3b4f"
            "c9754259e6ca3bea0db628776ae1fe37"
        ),
        "detail_sha256": "a" * 64,
    }
    env_file = path.parent / ".env"
    if not env_file.exists():
        env_file.write_text("API_SPORTS_KEY=test-key\n", encoding="utf-8")
        env_file.chmod(0o600)
    base = (
        sys.executable, "-m", "toto_ai.cli", "morning-dispatch",
        "--env-file", str(env_file),
        "--project-root", str(path.parent),
        "--expected-drawing-id", "11993",
        "--expected-drawing-number", "4961",
        "--expected-fingerprint", identity["drawing_fingerprint"],
        "--expected-deadline", identity["deadline"],
    ) + command_suffix
    payload = {
        "schema_version": 1,
        "plan_type": "passive_preflight_retry",
        "identity": identity,
        "created_at": "2026-07-31T09:00:00Z",
        "hard_stop": "2026-07-31T15:00:00Z",
        "passive": True,
        "activate_evening": activate_evening,
        "attempts": [
            {
                "scheduled_at": "2026-07-31T10:00:00Z",
                "command": list(base),
                "status": "planned",
            },
            {
                "scheduled_at": "2026-07-31T12:00:00Z",
                "command": list(base),
                "status": "planned",
            },
        ],
    }
    payload["plan_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _installed(tmp_path: Path, runner: FakeRunner):
    artifacts = prepare_preflight_retry_artifacts(_plan(tmp_path / "retry-plan.json"))
    root = tmp_path / "LaunchAgents"
    first = install_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=runner
    )
    second = install_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=runner
    )
    assert first["active"] is True and second["active"] is True
    assert runner.bootstrap_count == 1
    return artifacts, root


def test_due_attempts_execute_once_and_network_failure_remains_retryable(tmp_path):
    runner = FakeRunner([Result(2), Result(2)])
    artifacts = prepare_preflight_retry_artifacts(_plan(tmp_path / "retry-plan.json"))

    assert run_preflight_retry(
        artifacts.plan_path, now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=runner, launch_agents_root=tmp_path / "LaunchAgents",
    ) == 2
    assert run_preflight_retry(
        artifacts.plan_path, now=datetime(2026, 7, 31, 10, 2, tzinfo=UTC),
        command_runner=runner, launch_agents_root=tmp_path / "LaunchAgents",
    ) == 0
    assert run_preflight_retry(
        artifacts.plan_path, now=datetime(2026, 7, 31, 12, 1, tzinfo=UTC),
        command_runner=runner, launch_agents_root=tmp_path / "LaunchAgents",
    ) == 2
    executed = [item for item in runner.commands if item[0] != "launchctl"]
    assert len(executed) == 2


def test_runtime_accepts_same_drawing_monotonic_evidence_refresh(tmp_path):
    runner = FakeRunner([Result(2), Result(2)])
    plan_path = _plan(tmp_path / "retry-plan.json")
    initial = json.loads(plan_path.read_text(encoding="utf-8"))
    initial["identity"].update(
        {
            "operational_cutoff": "2026-07-31T14:00:00Z",
            "cutoff_evidence_sha256": "a" * 64,
            "reviewed_catalog_hash": None,
        }
    )
    initial.pop("plan_sha256")
    initial["plan_sha256"] = hashlib.sha256(_canonical(initial)).hexdigest()
    plan_path.write_text(json.dumps(initial), encoding="utf-8")
    artifacts = prepare_preflight_retry_artifacts(plan_path)
    assert run_preflight_retry(
        artifacts.plan_path,
        now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=runner,
        launch_agents_root=tmp_path / "LaunchAgents",
    ) == 2
    refreshed = json.loads(plan_path.read_text(encoding="utf-8"))
    refreshed["identity"].update(
        {
            "operational_cutoff": "2026-07-31T13:30:00Z",
            "cutoff_evidence_sha256": "b" * 64,
            "detail_sha256": "c" * 64,
            "reviewed_catalog_hash": "d" * 64,
        }
    )
    refreshed.pop("plan_sha256")
    refreshed["plan_sha256"] = hashlib.sha256(_canonical(refreshed)).hexdigest()
    plan_path.write_text(json.dumps(refreshed), encoding="utf-8")

    assert run_preflight_retry(
        artifacts.plan_path,
        now=datetime(2026, 7, 31, 12, 1, tzinfo=UTC),
        command_runner=runner,
        launch_agents_root=tmp_path / "LaunchAgents",
    ) == 2
    runtime = json.loads(
        (tmp_path / "retry-runtime.json").read_text(encoding="utf-8")
    )
    assert runtime["identity"] == refreshed["identity"]
    assert set(runtime["executed"]) == {
        "2026-07-31T10:00:00Z",
        "2026-07-31T12:00:00Z",
    }


def test_runtime_rejects_relaxed_operational_cutoff(tmp_path):
    runner = FakeRunner([Result(2)])
    plan_path = _plan(tmp_path / "retry-plan.json")
    initial = json.loads(plan_path.read_text(encoding="utf-8"))
    initial["identity"]["operational_cutoff"] = "2026-07-31T14:00:00Z"
    initial.pop("plan_sha256")
    initial["plan_sha256"] = hashlib.sha256(_canonical(initial)).hexdigest()
    plan_path.write_text(json.dumps(initial), encoding="utf-8")
    artifacts = prepare_preflight_retry_artifacts(plan_path)
    assert run_preflight_retry(
        artifacts.plan_path,
        now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=runner,
        launch_agents_root=tmp_path / "LaunchAgents",
    ) == 2
    relaxed = json.loads(plan_path.read_text(encoding="utf-8"))
    relaxed["identity"]["operational_cutoff"] = "2026-07-31T14:30:00Z"
    relaxed.pop("plan_sha256")
    relaxed["plan_sha256"] = hashlib.sha256(_canonical(relaxed)).hexdigest()
    plan_path.write_text(json.dumps(relaxed), encoding="utf-8")

    with pytest.raises(ValueError, match="runtime identity drift"):
        run_preflight_retry(
            plan_path,
            now=datetime(2026, 7, 31, 12, 1, tzinfo=UTC),
            command_runner=runner,
            launch_agents_root=tmp_path / "LaunchAgents",
        )


def test_retry_emits_structured_child_status_for_launchd_logs(tmp_path, capsys):
    runner = FakeRunner(
        [
            Result(
                2,
                '{"status":"deferred","reason":"timing_unknown",'
                '"unresolved_event_orders":[4,8]}',
            )
        ]
    )
    artifacts = prepare_preflight_retry_artifacts(_plan(tmp_path / "retry-plan.json"))

    code = run_preflight_retry(
        artifacts.plan_path,
        now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=runner,
        launch_agents_root=tmp_path / "LaunchAgents",
    )

    assert code == 2
    observed = json.loads(capsys.readouterr().out)
    assert observed == {
        "preflight_retry": {
            "scheduled_at": "2026-07-31T10:00:00Z",
            "returncode": 2,
            "child_result": {
                "status": "deferred",
                "reason": "timing_unknown",
                "unresolved_event_orders": [4, 8],
            },
        }
    }


@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        (Result(0, '{"status":"scheduled","reason":"ready"}'), 0),
        (Result(3, '{"status":"terminal","reason":"identity_drift"}'), 3),
        (Result(2, '{"status":"deferred","reason":"drawing_not_playable"}'), 2),
        (
            Result(
                2,
                '{"status":"deferred",'
                '"reason":"drawing_span_exceeds_five_days"}',
            ),
            2,
        ),
    ],
)
def test_ready_drift_and_terminal_no_bet_cleanup(tmp_path, result, expected_code):
    runner = FakeRunner([result])
    artifacts, root = _installed(tmp_path, runner)

    assert run_preflight_retry(
        artifacts.plan_path, now=datetime(2026, 7, 31, 10, 1, tzinfo=UTC),
        command_runner=runner, launch_agents_root=root,
    ) == expected_code
    assert runner.loaded is False
    assert not (root / f"{artifacts.label}.plist").exists()


def test_hard_stop_cleans_without_executing_a_retry(tmp_path):
    runner = FakeRunner()
    artifacts, root = _installed(tmp_path, runner)

    assert run_preflight_retry(
        artifacts.plan_path, now=datetime(2026, 7, 31, 15, 0, tzinfo=UTC),
        command_runner=runner, launch_agents_root=root,
    ) == 0
    assert runner.loaded is False
    assert not [item for item in runner.commands if item[0] != "launchctl"]


def test_status_requires_exact_install_and_load_and_terminal_has_no_next_run(tmp_path):
    runner = FakeRunner()
    artifacts, root = _installed(tmp_path, runner)
    status = verify_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=runner,
        now=datetime(2026, 7, 31, 9, 30, tzinfo=UTC), terminal=True,
    )
    assert status["installed_verified"] is True
    assert status["loaded_verified"] is True
    assert status["active"] is False
    assert status["next_run"] is None


def test_forbidden_activation_or_betting_is_rejected(tmp_path):
    with pytest.raises(
        ValueError,
        match="passive retry command cannot activate evening scheduler",
    ):
        prepare_preflight_retry_artifacts(
            _plan(tmp_path / "retry-plan.json", command_suffix=("--activate",))
        )


def test_bootstrap_retry_allows_exact_evening_activation_and_reinstall_is_idempotent(
    tmp_path,
):
    runner = FakeRunner()
    artifacts = prepare_preflight_retry_artifacts(
        _plan(
            tmp_path / "retry-plan.json",
            command_suffix=("--activate",),
            activate_evening=True,
        )
    )
    root = tmp_path / "LaunchAgents"

    first = install_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=runner
    )
    second = install_preflight_retry_launch_agent(
        artifacts, launch_agents_root=root, command_runner=runner
    )

    assert first["active"] is True
    assert second["active"] is True
    assert runner.bootstrap_count == 1


def test_same_identity_plan_refresh_replaces_and_reloads_launch_agent(tmp_path):
    runner = FakeRunner()
    plan_path = _plan(tmp_path / "retry-plan.json")
    initial = prepare_preflight_retry_artifacts(plan_path)
    root = tmp_path / "LaunchAgents"
    install_preflight_retry_launch_agent(
        initial,
        launch_agents_root=root,
        command_runner=runner,
    )
    initial_candidate = initial.candidate_path.read_bytes()
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["attempts"][0]["scheduled_at"] = "2026-07-31T10:30:00Z"
    payload.pop("plan_sha256")
    payload["plan_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    refreshed = prepare_preflight_retry_artifacts(plan_path)
    status = install_preflight_retry_launch_agent(
        refreshed,
        launch_agents_root=root,
        command_runner=runner,
    )

    assert refreshed.candidate_path.read_bytes() != initial_candidate
    assert status["active"] is True
    assert runner.bootstrap_count == 2
    assert any(command[1] == "bootout" for command in runner.commands)
    assert (root / f"{refreshed.label}.plist").read_bytes() == (
        refreshed.candidate_path.read_bytes()
    )


def test_changed_identity_cannot_replace_existing_retry_artifacts(tmp_path):
    plan_path = _plan(tmp_path / "retry-plan.json")
    prepare_preflight_retry_artifacts(plan_path)
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["identity"]["drawing_fingerprint"] = "c" * 64
    for attempt in payload["attempts"]:
        command = attempt["command"]
        option = command.index("--expected-fingerprint")
        command[option + 1] = "c" * 64
    payload.pop("plan_sha256")
    payload["plan_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    plan_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identity conflicts"):
        prepare_preflight_retry_artifacts(plan_path)


def test_retry_wrapper_loads_secure_env_and_fails_before_command_when_key_missing(
    tmp_path,
):
    plan = _plan(tmp_path / "retry-plan.json")
    payload = json.loads(plan.read_text(encoding="utf-8"))
    env_file = tmp_path / "missing-key.env"
    env_file.write_text("OTHER_VALUE=present\n", encoding="utf-8")
    env_file.chmod(0o600)
    for attempt in payload["attempts"]:
        command = attempt["command"]
        command[command.index("--env-file") + 1] = str(env_file)
    payload.pop("plan_sha256")
    payload["plan_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    plan.write_text(json.dumps(payload), encoding="utf-8")

    artifacts = prepare_preflight_retry_artifacts(plan)
    completed = subprocess.run(
        (str(artifacts.wrapper_path),),
        check=False,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "")},
    )

    assert completed.returncode == 78
    assert "API_SPORTS_KEY is required" in completed.stderr
