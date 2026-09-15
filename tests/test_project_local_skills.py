"""Validate repo-local skill artifacts, not the probabilistic Codex selector."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "totoai-algorithm-review": "skills/algorithm-review.md",
    "totoai-backtesting": "skills/backtesting.md",
}


def _entry(name):
    return ROOT / ".agents" / "skills" / name / "SKILL.md"


@pytest.mark.parametrize("name", SKILLS)
def test_repo_skill_has_named_plain_yaml_entrypoint(name):
    path = _entry(name)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    header, body = text[4:].split("\n---\n", 1)
    # These instruction-only entrypoints deliberately use two plain YAML
    # scalars. The first-party validator separately parses their full YAML.
    fields = dict(line.split(": ", 1) for line in header.splitlines())
    assert set(fields) == {"name", "description"}
    assert fields["name"] == name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fields["name"])
    assert 0 < len(fields["description"]) <= 1024
    assert body.strip()
    assert not path.is_symlink()
    assert path.resolve().is_relative_to(ROOT.resolve())


@pytest.mark.parametrize("name,canonical", SKILLS.items())
def test_repo_skill_links_resolve_to_single_local_canonical_source(name, canonical):
    path = _entry(name)
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text())
    resolved = []
    for target in targets:
        assert not Path(target).is_absolute()
        assert "://" not in target
        linked = (path.parent / target).resolve()
        assert linked.is_relative_to(ROOT.resolve()), target
        assert linked.is_file(), target
        resolved.append(linked)
    assert resolved.count((ROOT / canonical).resolve()) == 1
    assert (ROOT / "AGENTS.md").resolve() in resolved
    assert (ROOT / "pyproject.toml").resolve() in resolved
    assert (ROOT / "memory-bank/TOOLING_POLICY.md").resolve() in resolved


@pytest.mark.parametrize("name", SKILLS)
def test_repo_skill_is_instruction_only_and_not_symlinked(name):
    directory = _entry(name).parent
    assert directory.resolve().is_relative_to((ROOT / ".agents/skills").resolve())
    assert not directory.is_symlink()
    assert not directory.parent.is_symlink()
    assert not directory.parent.parent.is_symlink()
    assert {child.name for child in directory.iterdir()} == {"SKILL.md"}
