import hashlib
import json
import os
import plistlib
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from toto_ai import cli
from toto_ai.api.detail_cache import write_drawing_detail_cache
from toto_ai.db.models import Drawing, DrawingEventPin
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.api_sports import FOOTBALL_BASE_URL, _cache_key
from toto_ai.runner.scheduler import (
    CommandSchedulerPhaseRunner,
    SchedulerError,
    SchedulerPhaseContext,
    build_scheduler_plan,
    load_scheduler_plan,
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
        project_root=tmp_path,
        db=tmp_path / "data" / "toto.db",
        aliases=tmp_path / "data" / "external-odds" / "team-aliases.json",
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
        cwd="/",
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
    assert launch_agent["WorkingDirectory"] == str(tmp_path)
    assert f"cd {tmp_path}" in wrapper_text


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
            "--project-root",
            str(tmp_path),
            "--db",
            str(tmp_path / "data" / "toto.db"),
            "--aliases",
            str(tmp_path / "data" / "aliases.json"),
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((output_dir / "scheduler-plan.json").read_text())
    assert payload["paths"]["env_file"] == str(env_file)
    assert Path(payload["paths"]["project_root"]).is_absolute()
    assert SECRET not in result.output


def test_legacy_schema_v1_plan_loads_with_inferred_absolute_project_root(
    tmp_path: Path,
):
    env_file = _env_file(tmp_path / ".env")
    artifacts = prepare_scheduler_artifacts(_plan(tmp_path, env_file))
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload["paths"].pop("project_root")
    payload["config"].pop("publication_lead_minutes")
    payload["config"].pop("trigger_offsets_minutes")
    semantic = {
        key: payload[key]
        for key in ("schema_version", "target", "config", "paths")
    }
    payload["plan_id"] = hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    artifacts.plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded = load_scheduler_plan(artifacts.plan_path)

    assert loaded.project_root == tmp_path
    assert loaded.drawing == 5001


def test_genuine_schema_v2_plan_hash_loads_without_new_safety_fields(
    tmp_path: Path,
):
    env_file = _env_file(tmp_path / ".env")
    artifacts = prepare_scheduler_artifacts(_plan(tmp_path, env_file))
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    payload["config"].pop("publication_lead_minutes")
    payload["config"].pop("trigger_offsets_minutes")
    for key in (
        "package_near_fixed_share",
        "package_low_probability_threshold",
        "package_material_probability_threshold",
    ):
        payload["config"].pop(key)
    semantic = {
        key: payload[key]
        for key in ("schema_version", "target", "config", "paths")
    }
    payload["plan_id"] = hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    artifacts.plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded = load_scheduler_plan(artifacts.plan_path)

    assert loaded.drawing_id == 12001
    assert loaded.actionable_safety_bound is False


def test_schema_v3_plan_preserves_declared_project_root(tmp_path: Path):
    project_root = tmp_path / "project"
    nested = project_root / "nested"
    nested.mkdir(parents=True)
    env_file = _env_file(project_root / ".env")
    plan = _plan(project_root, env_file)
    plan = replace(
        plan,
        output_dir=nested / "scheduler",
        db=nested / "data" / "toto.db",
        aliases=nested / "data" / "aliases.json",
    )
    artifacts = prepare_scheduler_artifacts(plan)
    payload = json.loads(artifacts.plan_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 3
    payload["config"].pop("publication_lead_minutes")
    payload["config"].pop("trigger_offsets_minutes")
    semantic = {
        key: payload[key]
        for key in ("schema_version", "target", "config", "paths")
    }
    payload["plan_id"] = hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    artifacts.plan_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded = load_scheduler_plan(artifacts.plan_path)

    assert loaded.source_schema_version == 3
    assert loaded.project_root == project_root.resolve(strict=True)
    assert loaded.project_root != nested.resolve(strict=True)


def test_schema_v2_rejects_filesystem_root_as_project_root(tmp_path: Path):
    with pytest.raises(ValueError, match="must not be filesystem root"):
        build_scheduler_plan(
            drawing=5001,
            drawing_id=12001,
            ended_at="2030-01-02T12:00:00Z",
            bank=4980,
            output_dir=tmp_path / "scheduler",
            project_root=Path("/"),
            db=tmp_path / "data" / "toto.db",
            aliases=tmp_path / "data" / "aliases.json",
        )


def test_schema_v2_rejects_symlinked_project_root(tmp_path: Path):
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(actual_root, target_is_directory=True)

    with pytest.raises(ValueError, match="project_root must not contain symlinks"):
        build_scheduler_plan(
            drawing=5001,
            drawing_id=12001,
            ended_at="2030-01-02T12:00:00Z",
            bank=4980,
            output_dir=linked_root / "reports" / "scheduler",
            project_root=linked_root,
            db=linked_root / "data" / "toto.db",
            aliases=linked_root / "data" / "aliases.json",
        )


def test_schema_v2_rejects_project_path_symlink_and_containment_escape(
    tmp_path: Path,
):
    project_root = tmp_path / "project"
    outside = tmp_path / "outside"
    project_root.mkdir()
    outside.mkdir()
    (project_root / "linked-data").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="database must not contain symlinks"):
        build_scheduler_plan(
            drawing=5001,
            drawing_id=12001,
            ended_at="2030-01-02T12:00:00Z",
            bank=4980,
            output_dir=project_root / "reports" / "scheduler",
            project_root=project_root,
            db=project_root / "linked-data" / "toto.db",
            aliases=project_root / "data" / "aliases.json",
        )

    with pytest.raises(ValueError, match="output_dir must be contained"):
        build_scheduler_plan(
            drawing=5001,
            drawing_id=12001,
            ended_at="2030-01-02T12:00:00Z",
            bank=4980,
            output_dir=outside / "scheduler",
            project_root=project_root,
            db=project_root / "data" / "toto.db",
            aliases=project_root / "data" / "aliases.json",
        )


def test_valid_schema_v2_plan_round_trips_with_resolved_project_root(
    tmp_path: Path,
):
    env_file = _env_file(tmp_path / ".env")
    artifacts = prepare_scheduler_artifacts(_plan(tmp_path, env_file))

    loaded = load_scheduler_plan(artifacts.plan_path)

    assert loaded.project_root == tmp_path.resolve(strict=True)
    assert loaded.output_dir.is_relative_to(loaded.project_root)
    assert loaded.db.is_relative_to(loaded.project_root)
    assert loaded.aliases.is_relative_to(loaded.project_root)


def test_evening_scheduler_preflight_succeeds_from_launchd_root_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project_root = tmp_path / "project"
    raw_cache = project_root / "data" / "raw"
    provider_cache = project_root / "data" / "external-cache" / "api-sports"
    aliases = project_root / "data" / "external-odds" / "team-aliases.json"
    db = project_root / "data" / "toto.db"
    provider_cache.mkdir(parents=True)
    aliases.parent.mkdir(parents=True)
    aliases.write_text('{"version":1,"aliases":{}}\n', encoding="utf-8")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    deadline = now + timedelta(days=2)
    local_date = deadline.astimezone(ZoneInfo("Europe/Moscow")).date()
    local_start = datetime.combine(
        local_date,
        datetime.min.time(),
        tzinfo=ZoneInfo("Europe/Moscow"),
    )
    first_date = local_start.astimezone(timezone.utc).date()
    event_date = first_date + timedelta(days=2)
    starts_at = datetime.combine(
        event_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    ) + timedelta(hours=12)
    target_payload = {
        "data": {
            "id": 12001,
            "number": 5001,
            "name": "baltbet-main",
            "status": "active",
            "ended_at": deadline.isoformat(),
            "events": [
                {
                    "id": 70001 + order,
                    "order": order,
                    "name": f"Home {order} — Away {order}",
                    "name_en": None,
                    "championship": "England. Premier League",
                    "sport": "football",
                    "start_at": None,
                    "quotes": {
                        "bk_win_1": 40,
                        "bk_draw": 30,
                        "bk_win_2": 30,
                        "pool_win_1": 40,
                        "pool_draw": 30,
                        "pool_win_2": 30,
                    },
                }
                for order in range(15)
            ],
        }
    }
    write_drawing_detail_cache(
        target_payload,
        drawing_id=12001,
        cache_dir=raw_cache,
        fetched_at=now,
        source="launchd-regression",
        allowed_root=project_root,
    )
    engine = init_db(db)
    factory = get_session_factory(engine)
    with factory() as session:
        session.add(
            Drawing(
                id=12001,
                number=5001,
                name="baltbet-main",
                status="active",
                ended_at=deadline.isoformat(),
            )
        )
        session.commit()
    engine.dispose()

    for requested_date in (
        first_date,
        first_date + timedelta(days=1),
        event_date,
    ):
        response = []
        if requested_date == event_date:
            response = [
                {
                    "fixture": {
                        "id": 90001 + order,
                        "date": starts_at.isoformat(),
                    },
                    "league": {
                        "name": "Premier League",
                        "country": "England",
                    },
                    "teams": {
                        "home": {"id": 100001 + order, "name": f"Home {order}"},
                        "away": {"id": 200001 + order, "name": f"Away {order}"},
                    },
                }
                for order in range(15)
            ]
        payload = {
            "errors": [],
            "results": len(response),
            "timestamp": int(now.timestamp()),
            "paging": {"current": 1, "total": 1},
            "response": response,
        }
        cache_key = _cache_key(
            FOOTBALL_BASE_URL,
            "/fixtures",
            {"date": requested_date.isoformat()},
        )
        (provider_cache / f"{cache_key}.json").write_text(
            json.dumps(
                {
                    "fetched_at": now.isoformat(),
                    "quota": {
                        "daily_limit": 100,
                        "daily_remaining": 90,
                        "minute_limit": 10,
                        "minute_remaining": 9,
                    },
                    "payload": payload,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    hook_dir = tmp_path / "http-blocker"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(
        "import requests.sessions\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('HTTP prohibited by launchd regression')\n"
        "requests.sessions.Session.request = blocked\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["API_SPORTS_KEY"] = "cache-only-test-key"
    env["PYTHONPATH"] = os.pathsep.join(
        item
        for item in (str(hook_dir), env.get("PYTHONPATH", ""))
        if item
    )
    plan = build_scheduler_plan(
        drawing=5001,
        drawing_id=12001,
        ended_at=deadline,
        bank=4980,
        output_dir=project_root / "reports" / "rehearsal" / "evening-5001",
        project_root=project_root,
        db=db,
        aliases=aliases,
    )
    context = SchedulerPhaseContext(
        phase="preflight",
        plan=plan,
        run_id="launchd-root",
        run_dir=plan.output_dir / "runs" / "5001" / "launchd-root",
        work_dir=(
            plan.output_dir
            / "runs"
            / "5001"
            / "launchd-root"
            / "work"
            / "preflight"
        ),
        scheduled_at=plan.preflight_at,
        started_at=plan.preflight_at,
    )
    monkeypatch.chdir("/")

    result = CommandSchedulerPhaseRunner(
        python_executable=sys.executable,
        environment=env,
        target_validator=lambda _plan, _started_at: None,
    )(context)

    assert result.status == "complete"
    engine = init_db(db)
    with get_session_factory(engine)() as session:
        assert session.query(DrawingEventPin).count() == 15
    engine.dispose()


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
        times=("08:00", "10:30"),
        retry_count=2,
        retry_delay_seconds=30.0,
        output_dir=output_dir,
        env_file=env_file,
        project_root=tmp_path,
        bank=4980,
        stake=30,
        python_command=sys.executable,
    )

    wrapper = artifacts.wrapper_path.read_text(encoding="utf-8")
    launch_agent = plistlib.loads(artifacts.launch_agent_path.read_bytes())
    assert "morning-dispatch" in wrapper
    assert "--expected-drawing-number" not in wrapper
    assert "4953" not in wrapper
    assert "scheduler-execute" not in wrapper
    assert "run-drawing" not in wrapper
    assert ".bet-ready" not in wrapper
    assert ".no-bet" not in wrapper
    assert launch_agent["ProgramArguments"] == [str(artifacts.wrapper_path)]
    assert launch_agent["Label"] == "com.totoai.morning-dispatcher.v1"
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
