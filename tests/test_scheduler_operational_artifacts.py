import json
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.runner.scheduler import (
    SchedulerError,
    build_scheduler_plan,
    prepare_morning_preanalysis_artifacts,
    prepare_scheduler_artifacts,
)

SECRET = "scheduler-operational-test-secret"


def _env_file(path: Path, content: str = f"API_SPORTS_KEY={SECRET}\n") -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path


def _plan(tmp_path: Path, env_file: Path):
    return build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at="2030-01-02T12:00:00Z",
        bank=4980,
        output_dir=tmp_path / "reports" / "rehearsal" / "evening-5001",
        env_file=env_file,
    )


def test_scheduler_wrapper_securely_sources_env_and_plist_only_runs_wrapper(
    tmp_path,
):
    env_file = _env_file(tmp_path / ".env")
    artifacts = prepare_scheduler_artifacts(_plan(tmp_path, env_file))

    completed = subprocess.run(
        [str(artifacts.wrapper_path), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["target"]["drawing"] == 5001
    plan_text = artifacts.plan_path.read_text(encoding="utf-8")
    wrapper_text = artifacts.wrapper_path.read_text(encoding="utf-8")
    plist_text = artifacts.launch_agent_path.read_text(encoding="utf-8")
    assert SECRET not in plan_text + wrapper_text + plist_text
    assert "API_SPORTS_KEY" not in plan_text + plist_text
    assert "umask 077" in wrapper_text
    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]


def test_scheduler_plan_cli_accepts_secure_env_file(tmp_path):
    env_file = _env_file(tmp_path / ".env")
    output_dir = tmp_path / "reports" / "rehearsal" / "evening-cli"

    result = CliRunner().invoke(
        cli.app,
        [
            "scheduler-plan",
            "--drawing",
            "5001",
            "--drawing-id",
            "12001",
            "--ended-at",
            "2030-01-02T12:00:00Z",
            "--bank",
            "4980",
            "--output-dir",
            str(output_dir),
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((output_dir / "scheduler-plan.json").read_text())
    assert payload["paths"]["env_file"] == str(env_file)
    assert SECRET not in result.output


@pytest.mark.parametrize("mode", (0o644, 0o604, 0o700))
def test_scheduler_generation_rejects_env_file_with_broad_mode(tmp_path, mode):
    env_file = _env_file(tmp_path / ".env")
    env_file.chmod(mode)

    with pytest.raises(SchedulerError, match="mode.*0600"):
        prepare_scheduler_artifacts(_plan(tmp_path, env_file))


def test_scheduler_generation_rejects_symlink_env_file(tmp_path):
    actual = _env_file(tmp_path / "actual.env")
    env_file = tmp_path / ".env"
    env_file.symlink_to(actual)

    with pytest.raises(SchedulerError, match="must not be a symlink"):
        prepare_scheduler_artifacts(_plan(tmp_path, env_file))


def test_scheduler_generation_rejects_missing_env_file(tmp_path):
    env_file = tmp_path / "missing.env"

    with pytest.raises(SchedulerError, match="existing regular file"):
        prepare_scheduler_artifacts(_plan(tmp_path, env_file))


def test_scheduler_wrapper_rejects_missing_key_without_leakage(tmp_path):
    env_file = _env_file(tmp_path / ".env", "OTHER_SECRET=do-not-print\n")
    artifacts = prepare_scheduler_artifacts(_plan(tmp_path, env_file))

    completed = subprocess.run(
        [str(artifacts.wrapper_path), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "API_SPORTS_KEY is required" in completed.stderr
    assert "do-not-print" not in completed.stdout + completed.stderr


def test_morning_preanalysis_artifacts_are_isolated_and_non_betting(tmp_path):
    env_file = _env_file(tmp_path / ".env")
    output_dir = tmp_path / "reports" / "rehearsal" / "morning-4953"

    artifacts = prepare_morning_preanalysis_artifacts(
        expected_drawing_number=4953,
        times=("08:00", "10:30"),
        retry_count=2,
        retry_delay_seconds=30.0,
        output_dir=output_dir,
        env_file=env_file,
        project_root=tmp_path,
        python_command=sys.executable,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert "sync-prepare" in wrapper
    assert "--expected-drawing-number 4953" in wrapper
    assert "scheduler-execute" not in wrapper
    assert "run-drawing" not in wrapper
    assert ".bet-ready" not in wrapper
    assert ".no-bet" not in wrapper
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    assert launch_agent["StartCalendarInterval"] == [
        {"Hour": 8, "Minute": 0},
        {"Hour": 10, "Minute": 30},
    ]
    assert launch_agent["StandardOutPath"].startswith(str(output_dir / "logs"))
    assert SECRET not in wrapper + artifacts.launch_agent_path.read_text()


def test_morning_preanalysis_cli_generates_without_network(tmp_path):
    env_file = _env_file(tmp_path / ".env")
    output_dir = tmp_path / "reports" / "rehearsal" / "morning-cli"

    result = CliRunner().invoke(
        cli.app,
        [
            "morning-preanalysis-plan",
            "--expected-drawing-number",
            "4953",
            "--env-file",
            str(env_file),
            "--at",
            "08:00",
            "--at",
            "10:30",
            "--retry-count",
            "2",
            "--retry-delay-seconds",
            "30",
            "--output-dir",
            str(output_dir),
            "--project-root",
            str(tmp_path),
            "--python-executable",
            sys.executable,
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / "run-morning-preanalysis.sh").is_file()
    assert (output_dir / "totoai-morning-preanalysis.plist").is_file()
    assert SECRET not in result.output
