import hashlib
import json
import plistlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from toto_ai.db.models import Drawing
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.operations.finished_draw import (
    cleanup_post_draw_launch_agent,
    due_post_draw_attempts,
    install_post_draw_launch_agent,
    load_post_draw_plan,
    prepare_post_draw_scheduler_artifacts,
)


@dataclass
class _Completed:
    returncode: int
    stderr: str = ""


class _Launchctl:
    def __init__(self):
        self.loaded: set[str] = set()
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command, **_kwargs):
        command = tuple(command)
        self.calls.append(command)
        if command[1] == "print":
            return _Completed(0 if command[2] in self.loaded else 1)
        if command[1] == "bootstrap":
            payload = plistlib.loads(Path(command[3]).read_bytes())
            self.loaded.add(f"{command[2]}/{payload['Label']}")
            return _Completed(0)
        if command[1] == "bootout":
            self.loaded.discard(command[2])
            return _Completed(0)
        raise AssertionError(command)


def _database(tmp_path, *, ended_at):
    db = tmp_path / "toto.db"
    factory = get_session_factory(init_db(db))
    with factory.begin() as session:
        session.add(
            Drawing(
                id=12000,
                number=5000,
                name="baltbet-main",
                status="finished",
                ended_at=ended_at,
            )
        )
    return db


@pytest.mark.parametrize(
    ("ended_at", "first_due"),
    (
        ("2026-08-13T20:59:59+03:00", "2026-08-14T12:00:00+03:00"),
        ("2026-08-13T22:30:00-04:00", "2026-08-14T12:00:00+03:00"),
        ("2026-08-13T23:59:59+00:00", "2026-08-14T12:00:00+03:00"),
    ),
)
def test_post_draw_plan_uses_next_moscow_calendar_day(tmp_path, ended_at, first_due):
    db = _database(tmp_path, ended_at=ended_at)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join("1X2" * 5) + "\n")

    plan_path, _wrapper, _plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=12000,
        drawing_number=None,
        ended_at=ended_at,
        package_file=package,
        stake=30,
        db=db,
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=6,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )

    plan = load_post_draw_plan(plan_path)
    assert plan["schema_version"] == 2
    assert plan["timezone"] == "Europe/Moscow"
    assert plan["first_run_at"] == first_due
    assert plan["due_slots"][0] == first_due
    due = [datetime.fromisoformat(value) for value in plan["due_slots"]]
    assert [
        (right - left).total_seconds()
        for left, right in zip(due, due[1:], strict=False)
    ] == [10_800] * 5
    assert plan["expires_at"] == plan["due_slots"][-1]


def test_post_draw_plan_is_hash_bound_idempotent_and_launchd_is_candidate_only(
    tmp_path,
):
    ended_at = "2026-08-13T18:00:00+00:00"
    db = _database(tmp_path, ended_at=ended_at)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join("1" * 15) + "\n")
    kwargs = dict(
        drawing_id=12000,
        drawing_number=None,
        ended_at=ended_at,
        package_file=package,
        stake=30,
        db=db,
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=3,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )

    paths = prepare_post_draw_scheduler_artifacts(**kwargs)
    original = paths[0].read_bytes()
    assert prepare_post_draw_scheduler_artifacts(**kwargs) == paths
    assert paths[0].read_bytes() == original
    plan = load_post_draw_plan(paths[0])
    assert plan["plan_sha256"] == hashlib.sha256(
        json.dumps(
            {key: value for key, value in plan.items() if key != "plan_sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert plan["automatic_wagering"] is False
    assert "launchctl" not in paths[1].read_text()
    assert "post-draw-run --plan" in paths[1].read_text()
    with paths[2].open("rb") as source:
        plist = plistlib.load(source)
    assert isinstance(plist["StartCalendarInterval"], list)
    assert len(plist["StartCalendarInterval"]) == 3

    package.write_text("30; " + "; ".join("2" * 15) + "\n")
    with pytest.raises(ValueError, match="conflicts with immutable"):
        prepare_post_draw_scheduler_artifacts(**kwargs)


def test_post_draw_launch_agent_installs_verifies_and_cleans_exact_candidate(
    tmp_path,
):
    ended_at = "2026-08-13T18:00:00+00:00"
    db = _database(tmp_path, ended_at=ended_at)
    package = tmp_path / "package.txt"
    package.write_text("30; " + "; ".join("1" * 15) + "\n")
    plan, _wrapper, plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=12000,
        drawing_number=None,
        ended_at=ended_at,
        package_file=package,
        stake=30,
        db=db,
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=3,
        initial_delay_seconds=0,
        max_delay_seconds=0,
        automation_installation=True,
    )
    runner = _Launchctl()
    launch_agents = tmp_path / "LaunchAgents"

    status = install_post_draw_launch_agent(
        plan,
        plist,
        launch_agents_root=launch_agents,
        command_runner=runner,
    )

    assert status["active"] is True
    installed = launch_agents / "com.toto-ai.post-draw-12000.plist"
    assert installed.read_bytes() == plist.read_bytes()
    assert load_post_draw_plan(plan)["automation_installation"] is True

    cleanup_post_draw_launch_agent(
        plan,
        launch_agents_root=launch_agents,
        command_runner=runner,
    )
    assert not installed.exists()
    assert not runner.loaded


def test_package_free_no_bet_plan_has_due_slot_selection(tmp_path):
    ended_at = "2026-08-13T18:00:00+00:00"
    db = _database(tmp_path, ended_at=ended_at)
    result = tmp_path / "paper-package-result.json"
    result.write_text('{"decision":"NO BET","actionable":false,"count":0}\n')

    plan_path, _wrapper, _plist = prepare_post_draw_scheduler_artifacts(
        drawing_id=12000,
        drawing_number=None,
        ended_at=ended_at,
        package_file=None,
        paper_result_file=result,
        stake=30,
        db=db,
        state_file=tmp_path / "state.json",
        output_dir=tmp_path / "scheduler",
        project_root=tmp_path,
        python_executable="/usr/bin/python3",
        max_attempts=3,
        initial_delay_seconds=0,
        max_delay_seconds=0,
    )
    plan = load_post_draw_plan(plan_path)
    assert plan["package_binding"]["kind"] == "package_free_no_bet"
    assert plan["package_binding"]["coupon_count"] == 0
    assert due_post_draw_attempts(
        plan,
        now=datetime.fromisoformat(plan["due_slots"][1]),
        attempted_slots=(plan["due_slots"][0],),
    ) == (plan["due_slots"][1],)
