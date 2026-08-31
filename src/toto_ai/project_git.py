"""Repository-attested Git execution for TotoAI production code."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPOSITORY_ROUTING_ENVIRONMENT = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_DIR",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_QUARANTINE_PATH",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)
_ATTESTATION_ARGUMENTS = (
    "rev-parse",
    "--path-format=absolute",
    "--show-toplevel",
    "--git-dir",
    "--git-common-dir",
)


class ProjectGitError(RuntimeError):
    """Raised when repository-pinned Git execution cannot be trusted."""


def run_project_git(*arguments: str) -> str:
    """Run one Git command through the repository wrapper and return stdout."""
    if not arguments or any(
        not isinstance(argument, str) or not argument for argument in arguments
    ):
        raise ProjectGitError("Project Git arguments must be non-empty strings.")

    project_root, project_git, expected_git_dir = _resolve_project_paths()
    environment = _sanitized_git_environment()
    attestation = _invoke_project_git(
        project_root,
        project_git,
        _ATTESTATION_ARGUMENTS,
        environment,
    ).stdout
    _require_exact_repository(attestation, project_root, expected_git_dir)

    completed = _invoke_project_git(
        project_root,
        project_git,
        arguments,
        environment,
    )
    return completed.stdout.strip()


def _resolve_project_paths() -> tuple[Path, Path, Path]:
    try:
        module_path = Path(__file__).resolve(strict=True)
        project_root = module_path.parents[2]
        expected_module = project_root / "src" / "toto_ai" / "project_git.py"
        if expected_module.resolve(strict=True) != module_path:
            raise ProjectGitError("Project Git helper is outside the source tree.")

        project_git = project_root / "scripts" / "project-git"
        if project_git.is_symlink() or not project_git.is_file():
            raise ProjectGitError(
                "Project Git wrapper is missing or not a regular file."
            )
        if project_git.resolve(strict=True) != project_git:
            raise ProjectGitError("Project Git wrapper path is not canonical.")
        if not os.access(project_git, os.X_OK):
            raise ProjectGitError("Project Git wrapper is not executable.")

        expected_git_dir = project_root / ".git"
        if expected_git_dir.is_symlink() or not expected_git_dir.is_dir():
            raise ProjectGitError(
                "Project Git directory is missing or not a directory."
            )
        if expected_git_dir.resolve(strict=True) != expected_git_dir:
            raise ProjectGitError("Project Git directory path is not canonical.")
    except (IndexError, OSError, RuntimeError) as error:
        if isinstance(error, ProjectGitError):
            raise
        raise ProjectGitError("Unable to resolve the TotoAI project root.") from error
    return project_root, project_git, expected_git_dir


def _sanitized_git_environment() -> dict[str, str]:
    return {
        name: value
        for name, value in os.environ.items()
        if name not in _REPOSITORY_ROUTING_ENVIRONMENT
        and not name.startswith("GIT_CONFIG_KEY_")
        and not name.startswith("GIT_CONFIG_VALUE_")
    }


def _invoke_project_git(
    project_root: Path,
    project_git: Path,
    arguments: tuple[str, ...],
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(project_git), *arguments],
            cwd=project_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProjectGitError("Repository-pinned Git command failed.") from error


def _require_exact_repository(
    attestation: str,
    project_root: Path,
    expected_git_dir: Path,
) -> None:
    reported_paths = attestation.strip().splitlines()
    if len(reported_paths) != 3:
        raise ProjectGitError("Project Git repository attestation is malformed.")

    resolved_paths: list[Path] = []
    for reported_path in reported_paths:
        try:
            candidate = Path(reported_path)
            if not candidate.is_absolute():
                raise ProjectGitError(
                    "Project Git repository attestation is not absolute."
                )
            resolved_paths.append(candidate.resolve(strict=True))
        except (OSError, RuntimeError) as error:
            if isinstance(error, ProjectGitError):
                raise
            raise ProjectGitError(
                "Project Git repository attestation is invalid."
            ) from error

    reported_root, reported_git_dir, reported_common_dir = resolved_paths
    if reported_root != project_root:
        raise ProjectGitError("Project Git root mismatch; refusing command execution.")
    if reported_git_dir != expected_git_dir:
        raise ProjectGitError(
            "Project Git directory mismatch; refusing command execution."
        )
    if reported_common_dir != expected_git_dir:
        raise ProjectGitError(
            "Project Git common directory mismatch; refusing command execution."
        )
