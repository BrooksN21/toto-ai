from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.runner import preflight_retry_rehearsal as rehearsal


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def _retry_plan(tmp_path: Path) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text("API_SPORTS_KEY=test-only\n", encoding="utf-8")
    env_file.chmod(0o600)
    identity = {
        "drawing_id": 11993,
        "drawing_number": 4961,
        "deadline": "2026-07-31T16:00:00Z",
        "drawing_fingerprint": "b713fca373c9663e" + "0" * 48,
        "detail_sha256": "a" * 64,
    }
    command = [
        sys.executable,
        "-m",
        "toto_ai.cli",
        "morning-dispatch",
        "--env-file",
        str(env_file),
        "--project-root",
        str(tmp_path),
        "--expected-drawing-id",
        "11993",
        "--expected-drawing-number",
        "4961",
        "--expected-fingerprint",
        str(identity["drawing_fingerprint"]),
        "--expected-deadline",
        str(identity["deadline"]),
    ]
    payload = {
        "schema_version": 1,
        "plan_type": "passive_preflight_retry",
        "identity": identity,
        "created_at": "2026-07-31T09:00:00Z",
        "hard_stop": "2026-07-31T15:00:00Z",
        "passive": True,
        "activate_evening": False,
        "attempts": [
            {
                "scheduled_at": "2026-07-31T10:00:00Z",
                "command": command,
                "status": "planned",
            },
            {
                "scheduled_at": "2026-07-31T12:00:00Z",
                "command": command,
                "status": "planned",
            },
        ],
    }
    payload["plan_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "retry-plan.json"
    path.write_bytes(_canonical(payload) + b"\n")
    return path


def test_rehearsal_cli_builds_exact_config(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_run(config):
        captured["config"] = config
        return {"status": "PASS", "drawing_number": config.drawing_number}

    monkeypatch.setattr(rehearsal, "run_preflight_retry_rehearsal", fake_run)
    result = CliRunner().invoke(
        cli.app,
        [
            "preflight-retry-rehearsal",
            "--db",
            str(tmp_path / "toto.db"),
            "--target-cache",
            str(tmp_path / "target.json"),
            "--schedule-cache",
            str(tmp_path / "schedule-1.json"),
            "--schedule-cache",
            str(tmp_path / "schedule-2.json"),
            "--aliases",
            str(tmp_path / "aliases.json"),
            "--reviewed-schedule-catalog",
            str(tmp_path / "catalog.json"),
            "--output-root",
            str(tmp_path / "output"),
            "--drawing-id",
            "11993",
            "--drawing-number",
            "4961",
            "--at",
            "2026-07-31T09:11:00+00:00",
            "--failed-schedule-date",
            "2026-08-02",
            "--failed-schedule-date",
            "2026-08-03",
            "--bank",
            "4980",
            "--stake",
            "30",
        ],
    )

    assert result.exit_code == 0, result.output
    config = captured["config"]
    assert config.drawing_id == 11993
    assert config.drawing_number == 4961
    assert config.bank == 4980
    assert config.stake == 30
    assert tuple(value.isoformat() for value in config.failed_schedule_dates) == (
        "2026-08-02",
        "2026-08-03",
    )
    assert config.schedule_caches == (
        tmp_path / "schedule-1.json",
        tmp_path / "schedule-2.json",
    )
    assert json.loads(result.output)["status"] == "PASS"


def test_rehearsal_exercises_retry_failures_without_external_side_effects(
    tmp_path: Path,
) -> None:
    plan = _retry_plan(tmp_path)

    lifecycle = rehearsal._exercise_retry_lifecycle(
        plan, root=tmp_path / "retry-branches"
    )
    missing_key = rehearsal._exercise_missing_key(
        plan, root=tmp_path / "missing-key"
    )
    transport = rehearsal._exercise_transport_failure(tmp_path / "transport")

    assert set(lifecycle.values()) == {"PASS"}
    assert missing_key == {"status": "PASS", "exit_code": 78}
    assert transport == {"status": "PASS", "attempts": 2}
    assert not tuple(tmp_path.rglob("*.bet-ready"))


def test_reviewed_inputs_are_copied_and_forbidden_outputs_are_detected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    catalog = source / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    snapshot = source / "official.txt"
    snapshot.write_text("reviewed evidence\n", encoding="utf-8")

    copied = rehearsal._copy_reviewed_catalog(
        catalog, tmp_path / "isolated/reviewed"
    )

    assert copied.read_bytes() == catalog.read_bytes()
    assert (copied.parent / snapshot.name).read_bytes() == snapshot.read_bytes()
    assert rehearsal._forbidden_outputs(tmp_path / "isolated") == ()
    forbidden = tmp_path / "isolated/package.csv"
    forbidden.write_text("coupon\n", encoding="utf-8")
    assert rehearsal._forbidden_outputs(tmp_path / "isolated") == (
        str(forbidden),
    )
