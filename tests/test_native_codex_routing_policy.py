"""Static policy contracts, not proof of runtime routing or billing savings."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "prompts/native-codex-routing.json"


def _policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def test_only_three_owner_approved_models_and_efforts():
    policy = _policy()
    assert policy["routes"] == {
        "routine": {"model": "gpt-5.6-luna", "reasoning_effort": "low"},
        "bounded_code": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
        "critical": {"model": "gpt-6-astra", "reasoning_effort": "high"},
    }
    assert policy["default_route"] == "routine"
    assert policy["change_main_model"] is False


def test_native_dispatch_is_project_bound_and_not_a_client_config():
    policy = _policy()
    assert policy["kind"] == "instruction_policy_not_native_client_config"
    assert policy["project_root"] == "/Users/turshevr/toto-ai"
    assert policy["dispatcher_task_id"] == "019f7afa-72e2-7403-85cd-d05f408a4ef3"
    assert policy["dispatch_transport"] == "native_codex_spawn_agent_only"
    assert policy["runtime_enforcement"] == "parent_checked_instructions"
    assert policy["client_config_status"] == "NOT_INSTALLED_SCHEMA_UNVERIFIED"


def test_activation_requires_commit_pr_and_callable_native_schema():
    assert _policy()["activation_requires"] == [
        "owner_policy_commit",
        "pull_request_exposes_commit",
        "parent_verifies_callable_native_spawn_schema",
    ]


def test_bounded_isolated_handoffs_and_no_nested_workers():
    policy = _policy()
    assert policy["max_concurrent_workers"] == 2
    assert policy["concurrency_includes_existing_child_tasks"] is True
    assert policy["fork_context"] is False
    assert policy["nested_delegation"] is False
    assert policy["max_attempts_per_worker_assignment"] == 1
    assert policy["unavailable_tool_action"] == "report_blocker_no_alternate_transport"
    assert policy["allowed_handoff_fields"] == [
        "task_id", "verified_cwd", "role", "goal", "input_paths",
        "write_scope", "acceptance_checks", "time_bound", "return_contract",
    ]


@pytest.mark.parametrize(
    "field",
    ["external_models", "provider_auth_overrides", "global_changes",
     "new_user_owned_tasks", "new_worktrees", "automatic_wagering"],
)
def test_existing_prohibitions_remain_false(field):
    assert _policy()["permissions"][field] is False


@pytest.mark.parametrize("path", ["AGENTS.md", "memory-bank/TOOLING_POLICY.md"])
def test_both_policy_entrypoints_preserve_denials_and_link_routing(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    for term in (
        "Native Codex routing — owner authorization 2026-09-16",
        "NATIVE_CODEX_ROUTING.md", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-astra",
        "Claude", "Eliza", "Yandex", "No runtime approval can override",
        "01a06e1d-e0b9-7310-ba37-53a418668354",
        "01a06e1d-f37f-7763-ac2a-86200d3318e3",
    ):
        assert term in text
    assert "Do not start model-backed subagents." not in text
    assert "Model-backed subagents are prohibited." not in text


def test_routing_guide_explains_non_enforcement_and_explicit_parameters():
    text = " ".join(
        (ROOT / "memory-bank/NATIVE_CODEX_ROUTING.md")
        .read_text(encoding="utf-8")
        .split()
    )
    for term in (
        "NOT_INSTALLED_SCHEMA_UNVERIFIED", "fork_context=false",
        "model", "reasoning_effort", "not a security sandbox",
        "No automatic cost router", "No agent was launched",
    ):
        assert term in text
