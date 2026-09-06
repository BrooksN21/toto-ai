"""Synthetic Git metadata, no worktree creation/deletion or fixture Git commands."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    # Git recognizes an unborn repository with this minimal on-disk metadata.
    main = tmp_path / "main"
    meta = main / ".git"
    (meta / "objects").mkdir(parents=True)
    (meta / "refs/heads").mkdir(parents=True)
    (meta / "HEAD").write_text("ref: refs/heads/main\n")
    (meta / "config").write_text("[core]\nrepositoryformatversion=0\nbare=false\n")
    (main / "scripts").mkdir()
    wrapper = main / "scripts/project-git"
    shutil.copyfile(ROOT / "scripts/project-git", wrapper)
    wrapper.chmod(0o755)
    child = tmp_path / "existing-child"
    child.mkdir()
    registration = meta / "worktrees/arbitrary-registration-name"
    registration.mkdir(parents=True)
    (registration / "HEAD").write_text("ref: refs/heads/main\n")
    (registration / "commondir").write_text("../..\n")
    (registration / "gitdir").write_text(f"{child}/.git\n")
    (child / ".git").write_text(f"gitdir: {registration}\n")
    return main, child, registration, wrapper


def run(repository, *args, target=None, env=None):
    _, child, _, wrapper = repository
    return subprocess.run(
        [str(wrapper), "--registered-worktree", str(target or child), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def test_registered_worktree_attests_without_installing_its_wrapper(repository):
    result = run(repository, "rev-parse", "--show-toplevel")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(repository[1])
    assert not (repository[1] / "scripts/project-git").exists()


def test_status_is_read_only_and_scoped_to_child(repository):
    (repository[1] / "child-only.txt").write_text("not a secret")
    result = run(repository, "status", "--short", "--untracked-files=normal")
    assert result.returncode == 0, result.stderr
    assert "child-only.txt" in result.stdout
    assert "scripts/" not in result.stdout
    assert not (repository[2] / "index").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-backlink",
        "wrong-common",
        "symlink-dotgit",
        "symlink-registration",
        "missing-registration",
        "copied-dotgit",
        "symlink-target",
        "home",
    ],
)
def test_registration_or_canonical_identity_mismatch_rejected(
    repository, tmp_path, mutation
):
    main, child, registration, _ = repository
    target = child
    if mutation == "wrong-backlink":
        (registration / "gitdir").write_text(f"{main}/.git\n")
    elif mutation == "wrong-common":
        (registration / "commondir").write_text("../../../..\n")
    elif mutation == "symlink-dotgit":
        original = child / "original-gitfile"
        (child / ".git").rename(original)
        (child / ".git").symlink_to(original)
    elif mutation == "symlink-registration":
        real = registration.with_name("real-registration")
        registration.rename(real)
        registration.symlink_to(real, target_is_directory=True)
    elif mutation == "missing-registration":
        (registration / "gitdir").unlink()
    elif mutation == "copied-dotgit":
        target = tmp_path / "disguised-repo"
        target.mkdir()
        shutil.copyfile(child / ".git", target / ".git")
    elif mutation == "symlink-target":
        target = tmp_path / "alias"
        target.symlink_to(child, target_is_directory=True)
    else:
        target = Path.home()
    result = run(repository, "rev-parse", "--show-toplevel", target=target)
    assert result.returncode == 64, result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("ls-files",),
        ("-C", "/", "status"),
        ("--git-dir=/", "status"),
        ("-c", "core.worktree=/", "status"),
        ("add", "."),
        ("worktree", "remove", "ignored"),
        ("diff", "--output=/tmp/not-allowed"),
    ],
)
def test_registered_mode_preserves_overrides_and_write_prohibition(repository, args):
    assert run(repository, *args).returncode == 64


def test_environment_cannot_redirect_registered_worktree(repository):
    env = dict(
        os.environ,
        GIT_DIR=str(Path.home() / ".git"),
        GIT_COMMON_DIR=str(Path.home() / ".git"),
        GIT_WORK_TREE=str(Path.home()),
    )
    result = run(repository, "rev-parse", "--show-toplevel", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(repository[1])
