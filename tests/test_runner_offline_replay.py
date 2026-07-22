import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import toto_ai.cli as cli

ROOT = Path(__file__).resolve().parents[1]
TARGET_CACHE = ROOT / "tests/fixtures/drawing_4951_totobrief_target_cache.json"
SCHEDULE_CACHE = ROOT / "tests/fixtures/drawing_4951_api_sports_schedule.json"
REPLAY_AS_OF = "2026-07-21T15:41:00+00:00"
EXPECTED_FIXTURES = {"1492290", "1548164", "1547777"}
RUNNER = CliRunner()


class _ForbiddenEnvironment:
    def get(self, *_args, **_kwargs):
        raise AssertionError("offline replay read process environment")


def _args(tmp_path: Path, *extra: str) -> list[str]:
    replay_root = tmp_path / "isolated-replay"
    return [
        "run-drawing",
        "--offline-replay",
        "--drawing-id",
        "11968",
        "--target-cache",
        str(TARGET_CACHE),
        "--schedule-cache",
        str(SCHEDULE_CACHE),
        "--replay-as-of",
        REPLAY_AS_OF,
        "--replay-root",
        str(replay_root),
        "--mode",
        "research",
        "--bank",
        "4980",
        *extra,
    ]


def _forbid_live_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "os", SimpleNamespace(environ=_ForbiddenEnvironment()))
    monkeypatch.setattr(
        cli,
        "TotoBriefClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("offline replay instantiated TotoBriefClient")
        ),
    )
    monkeypatch.setattr(
        cli,
        "APISportsClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("offline replay instantiated APISportsClient")
        ),
    )


def _manifest(tmp_path: Path) -> dict[str, object]:
    manifests = tuple(
        (tmp_path / "isolated-replay/reports").glob("drawing_run_*.json")
    )
    assert len(manifests) == 1
    return json.loads(manifests[0].read_text(encoding="utf-8"))


def test_offline_replay_4951_runs_real_pipeline_without_network_or_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _forbid_live_inputs(monkeypatch)

    result = RUNNER.invoke(cli.app, _args(tmp_path))

    assert result.exit_code == 0, result.output
    assert "Decision: RESEARCH ONLY" in result.output
    assert "Preparation: ready 15/15" in result.output
    assert "Pinned revalidation: 15/15" in result.output
    manifest = _manifest(tmp_path)
    assert manifest["schema_version"] == 4
    assert manifest["decision"] == "RESEARCH ONLY"
    assert manifest["config"]["mode"] == "research"
    assert manifest["replay"] == {
        "actionable": False,
        "mode": "offline-replay",
        "provider": "api-sports",
        "replay_root": str((tmp_path / "isolated-replay").resolve()),
        "replay_as_of": "2026-07-21T15:41:00+00:00",
        "schedule_cache_path": str(SCHEDULE_CACHE.resolve()),
        "schedule_cache_sha256": hashlib.sha256(
            SCHEDULE_CACHE.read_bytes()
        ).hexdigest(),
        "schedule_payload_sha256": (
            "bcf8ca1e21a50415d164a39db21546406b9a2bfa99415b051d7d6d1032ec70a0"
        ),
        "target_cache_path": str(TARGET_CACHE.resolve()),
        "target_cache_sha256": hashlib.sha256(
            TARGET_CACHE.read_bytes()
        ).hexdigest(),
        "target_payload_sha256": (
            "f70f84c9deb54d0556e85f0475e88f66b5b24462691ce595d25398a1be49e779"
        ),
    }
    revalidation = manifest["collection"]["pinned_revalidation"]
    assert revalidation["expected_count"] == 15
    assert revalidation["matched_count"] == 15
    assert revalidation["ready_for_play"] is True

    with sqlite3.connect(
        tmp_path / "isolated-replay/replay.sqlite"
    ) as connection:
        rows = connection.execute(
            "SELECT provider_fixture_id, status FROM drawing_event_pins "
            "ORDER BY event_order"
        ).fetchall()
        preparation = connection.execute(
            "SELECT status, mapped_count FROM drawing_preparations"
        ).fetchone()
    assert len(rows) == 15
    assert all(status == "valid" for _, status in rows)
    assert EXPECTED_FIXTURES <= {fixture_id for fixture_id, _ in rows}
    assert preparation == ("ready", 15)

    marker_names = {".bet-ready", ".no-bet", ".failed"}
    assert not any(path.name in marker_names for path in tmp_path.rglob("*"))
    assert not tuple(tmp_path.rglob("*.csv"))
    assert {path.name for path in tmp_path.iterdir()} == {"isolated-replay"}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("--open",), "incompatible with --open"),
        (("--mode", "playable"), "requires --mode research"),
    ],
)
def test_offline_replay_rejects_incompatible_or_playable_mode(
    tmp_path: Path,
    args: tuple[str, ...],
    message: str,
):
    command = _args(tmp_path)
    if args[0] == "--mode":
        mode_index = command.index("--mode")
        command[mode_index + 1] = args[1]
    else:
        command.extend(args)

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert message in result.output


def test_offline_replay_rejects_naive_as_of(tmp_path: Path):
    command = _args(tmp_path)
    command[command.index("--replay-as-of") + 1] = "2026-07-21T15:41:00"

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "must be timezone-aware" in result.output


def test_offline_replay_rejects_wrong_drawing_identity(tmp_path: Path):
    command = _args(tmp_path)
    command[command.index("--drawing-id") + 1] = "11967"

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "target cache drawing id does not match" in result.output


def test_offline_replay_rejects_missing_cache_path(tmp_path: Path):
    command = _args(tmp_path)
    command[command.index("--target-cache") + 1] = str(tmp_path / "missing.json")

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "target cache could not be read" in result.output


def test_offline_replay_rejects_tampered_cache_hash(tmp_path: Path):
    schedule = json.loads(SCHEDULE_CACHE.read_text(encoding="utf-8"))
    schedule["events"][0]["home"] = "tampered"
    changed = tmp_path / "tampered-schedule.json"
    changed.write_text(json.dumps(schedule), encoding="utf-8")
    command = _args(tmp_path)
    command[command.index("--schedule-cache") + 1] = str(changed)

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "schedule cache payload SHA-256 mismatch" in result.output


def test_offline_replay_rejects_schedule_for_another_target(tmp_path: Path):
    schedule = json.loads(SCHEDULE_CACHE.read_text(encoding="utf-8"))
    schedule["drawing_number"] = 4950
    changed = tmp_path / "wrong-target-schedule.json"
    changed.write_text(json.dumps(schedule), encoding="utf-8")
    command = _args(tmp_path)
    command[command.index("--schedule-cache") + 1] = str(changed)

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "does not match exact target identity" in result.output


def test_offline_replay_rejects_stale_schedule_before_runner_output(
    tmp_path: Path,
):
    schedule = json.loads(SCHEDULE_CACHE.read_text(encoding="utf-8"))
    schedule["fetched_at"] = "2026-07-19T10:43:35+00:00"
    changed = tmp_path / "stale-schedule.json"
    changed.write_text(json.dumps(schedule), encoding="utf-8")
    command = _args(tmp_path)
    command[command.index("--schedule-cache") + 1] = str(changed)

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "pinned revalidation is not ready" in result.output
    assert "stale=" in result.output
    assert not (tmp_path / "isolated-replay/reports").exists()
    assert not any(
        path.name in {".bet-ready", ".no-bet", ".failed"}
        for path in tmp_path.rglob("*")
    )


def test_offline_replay_requires_root_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    command = _args(tmp_path)
    index = command.index("--replay-root")
    del command[index : index + 2]
    production_db = ROOT / "data/toto.db"
    before_db = hashlib.sha256(production_db.read_bytes()).hexdigest()
    before_reports = tuple(sorted(path.name for path in (ROOT / "reports").iterdir()))
    before_cache = tuple(
        sorted(path.name for path in (ROOT / "data/external-cache").iterdir())
    )
    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("database initialized before replay-root validation")
        ),
    )

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "requires --replay-root" in result.output
    assert hashlib.sha256(production_db.read_bytes()).hexdigest() == before_db
    assert tuple(
        sorted(path.name for path in (ROOT / "reports").iterdir())
    ) == before_reports
    assert tuple(
        sorted(path.name for path in (ROOT / "data/external-cache").iterdir())
    ) == before_cache
    assert not (tmp_path / "isolated-replay").exists()


@pytest.mark.parametrize(
    "unsafe_root",
    (ROOT, ROOT / "data/replays/4951", ROOT / "reports/replays/4951"),
)
def test_offline_replay_rejects_live_or_repository_roots_before_write(
    tmp_path: Path,
    unsafe_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    command = _args(tmp_path)
    command[command.index("--replay-root") + 1] = str(unsafe_root)
    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe replay initialized a database")
        ),
    )

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "replay root" in result.output


def test_offline_replay_rejects_symlink_escape_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    destination = tmp_path / "destination"
    destination.mkdir()
    symlink_root = tmp_path / "replay-link"
    symlink_root.symlink_to(destination, target_is_directory=True)
    command = _args(tmp_path)
    command[command.index("--replay-root") + 1] = str(symlink_root)
    monkeypatch.setattr(
        cli,
        "init_db",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("symlink replay initialized a database")
        ),
    )

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "must not traverse symlinks" in result.output
    assert tuple(destination.iterdir()) == ()


def test_offline_replay_rejects_output_override_outside_root(tmp_path: Path):
    command = _args(tmp_path, "--db", str(tmp_path / "escaped.sqlite"))

    result = RUNNER.invoke(cli.app, command)

    assert result.exit_code != 0
    assert "db must resolve under --replay-root" in result.output
    assert not (tmp_path / "escaped.sqlite").exists()
