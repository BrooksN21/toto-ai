from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_GIT = PROJECT_ROOT / "scripts" / "project-git"
HOME_GIT_GUARD = PROJECT_ROOT / "scripts" / "home-git-guard"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PROJECT_GIT), *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def test_project_git_is_pinned_to_repository_root(tmp_path: Path) -> None:
    result = _run("rev-parse", "--show-toplevel", cwd=tmp_path)

    assert result.returncode == 0
    assert Path(result.stdout.strip()).resolve() == PROJECT_ROOT


def test_project_git_rejects_ls_files(tmp_path: Path) -> None:
    result = _run("ls-files", cwd=tmp_path)

    assert result.returncode == 64
    assert "git ls-files is prohibited" in result.stderr


def test_project_git_rejects_repository_override(tmp_path: Path) -> None:
    result = _run("-C", str(tmp_path), "status", cwd=tmp_path)

    assert result.returncode == 64
    assert "repository override is prohibited" in result.stderr


def test_home_git_guard_rejects_status_at_home_repository(tmp_path: Path) -> None:
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    env = {**os.environ, "HOME": str(tmp_path)}

    result = subprocess.run(
        [str(HOME_GIT_GUARD), "status", "--short", "--untracked-files=no"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 64
    assert "repository root is HOME" in result.stderr


def test_home_git_guard_allows_status_in_nested_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    env = {**os.environ, "HOME": str(tmp_path)}

    result = subprocess.run(
        [str(HOME_GIT_GUARD), "status", "--short", "--untracked-files=no"],
        cwd=repository,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
