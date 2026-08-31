from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

import toto_ai.cli as cli_module
import toto_ai.project_git as project_git_module
from toto_ai.project_git import ProjectGitError, run_project_git

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_GIT = PROJECT_ROOT / "scripts" / "project-git"
HOME_GIT_GUARD = PROJECT_ROOT / "scripts" / "home-git-guard"
PRODUCTION_GIT_HELPER = PROJECT_ROOT / "src" / "toto_ai" / "project_git.py"
_SUBPROCESS_FUNCTIONS = {
    "call",
    "check_call",
    "check_output",
    "Popen",
    "run",
}
_SHELL_PROGRAMS = {"bash", "dash", "sh", "zsh"}


def _static_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                assignments[node.target.id] = node.value
    return assignments


def _static_value(
    expression: ast.AST,
    assignments: dict[str, ast.AST],
    seen: frozenset[str] = frozenset(),
) -> object | None:
    if isinstance(expression, ast.Constant) and isinstance(
        expression.value, (str, bool)
    ):
        return expression.value
    if isinstance(expression, ast.Name):
        if expression.id in seen or expression.id not in assignments:
            return None
        return _static_value(
            assignments[expression.id],
            assignments,
            seen | {expression.id},
        )
    if isinstance(expression, (ast.List, ast.Tuple)):
        values = tuple(
            _static_value(item, assignments, seen) for item in expression.elts
        )
        return values if all(value is not None for value in values) else None
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        left = _static_value(expression.left, assignments, seen)
        right = _static_value(expression.right, assignments, seen)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
        if isinstance(left, tuple) and isinstance(right, tuple):
            return left + right
        return None
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Div):
        left = _static_value(expression.left, assignments, seen)
        right = _static_value(expression.right, assignments, seen)
        if isinstance(left, str) and isinstance(right, str):
            return str(Path(left) / right)
        return None
    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []
        for part in expression.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts.append(part.value)
                continue
            if isinstance(part, ast.FormattedValue):
                value = _static_value(part.value, assignments, seen)
                if isinstance(value, str):
                    parts.append(value)
                    continue
            return None
        return "".join(parts)
    if isinstance(expression, ast.Call) and len(expression.args) == 1:
        function_name = (
            expression.func.id if isinstance(expression.func, ast.Name) else ""
        )
        if function_name in {"Path", "str"}:
            value = _static_value(expression.args[0], assignments, seen)
            return value if isinstance(value, str) else None
    return None


def _subprocess_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    module_aliases: set[str] = set()
    function_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_FUNCTIONS:
                    function_aliases.add(alias.asname or alias.name)
    return module_aliases, function_aliases


def _is_subprocess_call(
    call: ast.Call,
    module_aliases: set[str],
    function_aliases: set[str],
) -> bool:
    if isinstance(call.func, ast.Name):
        return call.func.id in function_aliases
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr in _SUBPROCESS_FUNCTIONS
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in module_aliases
    )


def _is_git_program(value: object) -> bool:
    return isinstance(value, str) and Path(value).name in {"git", "project-git"}


def _shell_script_invokes_git(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return re.search(
        r"(?:^|[;&|]\s*|\bexec\s+|\bcommand\s+)(?:\S*/)?(?:project-)?git(?:\s|$)",
        value,
    ) is not None


def _command_invokes_git(command: object, *, shell: bool) -> bool:
    if isinstance(command, str):
        if shell:
            return _shell_script_invokes_git(command)
        try:
            tokens = shlex.split(command)
        except ValueError:
            return False
        return len(tokens) == 1 and _is_git_program(tokens[0])
    if not isinstance(command, tuple) or not command:
        return False
    if _is_git_program(command[0]):
        return True
    if (
        isinstance(command[0], str)
        and Path(command[0]).name in _SHELL_PROGRAMS
        and len(command) >= 3
        and command[1] == "-c"
    ):
        return _shell_script_invokes_git(command[2])
    return False


def _direct_subprocess_git_calls(source: str, filename: str = "<test>") -> list[int]:
    tree = ast.parse(source, filename=filename)
    assignments = _static_assignments(tree)
    module_aliases, function_aliases = _subprocess_aliases(tree)
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_subprocess_call(
            node, module_aliases, function_aliases
        ):
            continue
        if not node.args:
            continue
        command = _static_value(node.args[0], assignments)
        shell = any(
            keyword.arg == "shell"
            and _static_value(keyword.value, assignments) is True
            for keyword in node.keywords
        )
        if _command_invokes_git(command, shell=shell):
            violations.append(node.lineno)
    return violations


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


@pytest.mark.parametrize(
    "raw_arguments",
    [
        ("-C{path}", "status"),
        ("-C", "{path}", "status"),
        ("-ccore.worktree={path}", "status"),
        ("-c", "core.worktree={path}", "status"),
        ("--bare", "status"),
        ("--config-env=core.worktree=ROUTE", "status"),
        ("--config-env", "core.worktree=ROUTE", "status"),
        ("--git-dir={path}/.git", "status"),
        ("--git-dir", "{path}/.git", "status"),
        ("--namespace=escape", "status"),
        ("--namespace", "escape", "status"),
        ("--work-tree={path}", "status"),
        ("--work-tree", "{path}", "status"),
    ],
)
def test_project_git_rejects_repository_override(
    raw_arguments: tuple[str, ...],
    tmp_path: Path,
) -> None:
    arguments = tuple(argument.format(path=tmp_path) for argument in raw_arguments)
    result = _run(*arguments, cwd=tmp_path)

    assert result.returncode == 64
    assert "repository override is prohibited" in result.stderr


def test_project_git_sanitizes_repository_routing_environment(tmp_path: Path) -> None:
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    env = {
        **os.environ,
        "GIT_DIR": str(tmp_path / ".git"),
        "GIT_WORK_TREE": str(tmp_path),
        "GIT_COMMON_DIR": str(tmp_path / ".git"),
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
        "GIT_DISCOVERY_ACROSS_FILESYSTEM": "1",
    }

    result = subprocess.run(
        [str(PROJECT_GIT), "rev-parse", "--show-toplevel"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert Path(result.stdout.strip()).resolve() == PROJECT_ROOT


def test_production_git_helper_ignores_outer_home_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    nested_cwd = home / "workspace"
    nested_cwd.mkdir(parents=True)
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(home)],
        check=True,
        capture_output=True,
        text=True,
    )
    outer = subprocess.run(
        ["/usr/bin/git", "-C", str(nested_cwd), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(outer.stdout.strip()).resolve() == home

    monkeypatch.chdir(nested_cwd)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_DIR", str(home / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(home))
    monkeypatch.setenv("GIT_COMMON_DIR", str(home / ".git"))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(home))
    monkeypatch.setenv("GIT_DISCOVERY_ACROSS_FILESYSTEM", "1")

    resolved = run_project_git("rev-parse", "--show-toplevel")

    assert Path(resolved).resolve() == PROJECT_ROOT


@pytest.mark.parametrize(
    ("mismatch_index", "message"),
    [
        (0, "root mismatch"),
        (1, "directory mismatch"),
        (2, "common directory mismatch"),
    ],
)
def test_production_git_helper_fails_closed_on_repository_mismatch(
    mismatch_index: int,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], Path]] = []
    attestation = [
        str(PROJECT_ROOT),
        str(PROJECT_ROOT / ".git"),
        str(PROJECT_ROOT / ".git"),
    ]
    attestation[mismatch_index] = str(tmp_path)

    def mismatched_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(command), cwd))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(attestation),
            stderr="",
        )

    monkeypatch.setattr(project_git_module.subprocess, "run", mismatched_run)

    with pytest.raises(ProjectGitError, match=message):
        run_project_git("status", "--porcelain")

    assert len(calls) == 1
    assert calls[0][1] == PROJECT_ROOT


def test_production_git_helper_sanitizes_every_subprocess_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_environments: list[dict[str, str]] = []
    outputs = iter(
        (
            "\n".join(
                (
                    str(PROJECT_ROOT),
                    str(PROJECT_ROOT / ".git"),
                    str(PROJECT_ROOT / ".git"),
                )
            ),
            "clean",
        )
    )

    def capture_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        captured_environments.append(env)
        return subprocess.CompletedProcess(command, 0, stdout=next(outputs), stderr="")

    for name in project_git_module._REPOSITORY_ROUTING_ENVIRONMENT:
        monkeypatch.setenv(name, "hostile")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/escape")
    monkeypatch.setattr(project_git_module.subprocess, "run", capture_run)

    assert run_project_git("status", "--porcelain") == "clean"
    assert len(captured_environments) == 2
    for environment in captured_environments:
        assert not (
            project_git_module._REPOSITORY_ROUTING_ENVIRONMENT & environment.keys()
        )
        assert not any(
            name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
            for name in environment
        )


def test_git_code_version_uses_project_git_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    outputs = iter(("abc123", ""))

    def fake_project_git(*arguments: str) -> str:
        calls.append(arguments)
        return next(outputs)

    monkeypatch.setattr(cli_module, "run_project_git", fake_project_git)

    assert cli_module._git_code_version() == "abc123"
    assert calls == [
        ("rev-parse", "HEAD"),
        ("status", "--porcelain"),
    ]


def test_production_sources_have_no_direct_git_command_literals() -> None:
    violations: list[str] = []
    for path in sorted((PROJECT_ROOT / "src" / "toto_ai").rglob("*.py")):
        if path == PRODUCTION_GIT_HELPER:
            continue
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(PROJECT_ROOT)
        violations.extend(
            f"{relative}:{line}"
            for line in _direct_subprocess_git_calls(source, filename=str(path))
        )

    assert violations == []


@pytest.mark.parametrize(
    "source",
    [
        'import subprocess\nsubprocess.run(["git", "status"])',
        (
            'import subprocess\ntool = "gi" + "t"\n'
            'command = [tool, "status"]\nsubprocess.run(command)'
        ),
        (
            'import subprocess\ntool = "git"\ncommand = f"{tool} status"\n'
            "subprocess.run(command, shell=True)"
        ),
        (
            'from subprocess import check_output as execute\n'
            'execute(("/usr/bin/git", "status"))'
        ),
        (
            'import subprocess\nscript = "echo safe; git status"\n'
            'subprocess.run(["/bin/sh", "-c", script])'
        ),
    ],
)
def test_static_git_guard_detects_direct_constructed_and_shell_calls(
    source: str,
) -> None:
    assert _direct_subprocess_git_calls(source)


@pytest.mark.parametrize(
    "source",
    [
        'DATA = {"provider": "git"}',
        'from pathlib import Path\nMARKER = Path(".git")',
        (
            'import subprocess\npayload = "git"\n'
            'subprocess.run(["printf", "%s", payload])'
        ),
        'import subprocess\nsubprocess.run(["echo", "project-git"])',
    ],
)
def test_static_git_guard_ignores_unrelated_git_data(source: str) -> None:
    assert _direct_subprocess_git_calls(source) == []


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
