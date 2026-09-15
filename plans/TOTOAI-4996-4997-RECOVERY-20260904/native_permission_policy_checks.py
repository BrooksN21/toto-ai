"""Focused document checks for the owner's two-existing-task exception."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).parent
IDS = {
    "019f7afa-72e2-7403-85cd-d05f408a4ef3",
    "01a06e1d-e0b9-7310-ba37-53a418668354",
    "01a06e1d-f37f-7763-ac2a-86200d3318e3",
}


def block(path):
    text = (ROOT / path).read_text()
    return text.split(
        "### Existing native Codex tasks — owner authorization 2026-09-05\n", 1
    )[1].split(
        "Earlier cancellation/setup records are history, "
        "not broader task permissions.\n",
        1,
    )[0]


def test_both_policies_have_identical_narrow_scope():
    a = block("AGENTS.md")
    assert a == block("memory-bank/TOOLING_POLICY.md")
    assert set(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", a)) == IDS
    for name in ("ab34", "a7aa"):
        assert f"/Users/turshevr/.codex/worktrees/{name}/toto-ai" in a


def test_service_model_and_production_guards_remain_explicit():
    a = block("AGENTS.md")
    for required in (
        "send_message_to_thread",
        "read_thread",
        "wait_threads",
        "host `local`",
        "No other task IDs, new tasks/worktrees, fork, setup recreation",
        "no model/provider override",
        "No nested or model-backed SUBAGENTS",
        "Never include credentials",
        "prohibitions remain unchanged",
        "No production DB, jobs, scheduler",
        "consent or operator artifact changes",
        "Parent integrates only after review",
        "not\npermission to bypass it",
    ):
        assert required in a


def test_owner_quote_and_no_execution_claim():
    r = json.loads((BASE / "native-task-owner-authorization-20260905.json").read_text())
    assert r["owner_quote_verbatim"] == (
        "я владелец и я разрешаю тебе закоммитить разрешение "
        "на продолжение работы в дочерних ветках"
    )
    assert r["policy_commit_pending"] is True
    for k in (
        "remote_publication_authorized",
        "new_tasks_authorized",
        "external_models_authorized",
        "implementation_worker_committed",
    ):
        assert r[k] is False


def test_minimal_patch_excludes_preexisting_unrelated_policy_edits():
    patch = (BASE / "native-task-permission-only.patch").read_text()
    assert patch.count("--- a/") == 2
    additions = "\n".join(
        x[1:]
        for x in patch.splitlines()
        if x.startswith("+") and not x.startswith("+++")
    )
    assert "No Codex heartbeat is authorized" not in additions
    assert "highest-P(13+)" not in additions
    assert "Read the short" not in additions
    assert "Single-task execution" not in additions
    assert "No nested or model-backed SUBAGENTS" in additions


def test_stale_cancellation_not_current_policy():
    for path in ("AGENTS.md", "memory-bank/TOOLING_POLICY.md"):
        text = (ROOT / path).read_text()
        for old in (
            "The former native-task exception is withdrawn.",
            "Operations, review and model improvements "
            "remain in the single current task.",
            "The owner revoked the two-task split.",
        ):
            assert old not in text
