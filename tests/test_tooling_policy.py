from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _policy_text() -> str:
    return "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("AGENTS.md", "memory-bank/TOOLING_POLICY.md")
    ).lower()


def test_external_model_execution_is_absolutely_denied() -> None:
    policy = _policy_text()

    required_terms = (
        "claude",
        "anthropic",
        "eliza",
        "external llm",
        "subagent",
        "proxy",
        "sdk",
        "cli",
    )
    assert all(term in policy for term in required_terms)
    assert "no runtime approval can override" in policy


def test_global_claude_distributed_skills_are_not_authorized() -> None:
    policy = _policy_text()

    assert "claude-plugins-official" in policy
    assert "project-local skills" in policy
