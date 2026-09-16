# TotoAI native Codex routing

Owner authorization: 2026-09-16, task `TOTOAI-RESUME-20260915`.
Machine-readable instruction policy: [native-codex-routing.json](../prompts/native-codex-routing.json).
This is **not a security sandbox** or an executable dispatcher. No automatic
cost router is installed or verified. AGENTS instructions let the parent choose
a role without asking the owner to switch models manually for every assignment.
Account-specific token savings are unknown; multiple workers can cost more.

## Activation and boundaries

Before any new worker: the owner-approved policy must be committed, the commit
exposed through a PR, and the parent must verify its callable native spawn
schema. Until then, no inference smoke test. No agent was launched by this job.
The main model is unchanged. Only the named parent operations task may dispatch;
verify its identity and canonical cwd `/Users/turshevr/toto-ai`. Workers keep
every shell call/write there. New user-owned tasks/worktrees are not authorized.
Existing named child tasks keep their own hosting model, cwd and scope; they
must not delegate. External LLMs, Claude/Anthropic/Eliza/proxies, Yandex/internal
services, provider/auth overrides, secrets and global settings remain forbidden.

## Routing and explicit native parameters

| Scope | `model` | `reasoning_effort` |
|---|---|---|
| Narrow routine (default): bounded reads, extraction, known checks | `gpt-5.6-luna` | `low` |
| Bounded implementation with precise acceptance tests | `gpt-5.6-terra` | `medium` |
| Complex mathematics, architecture, safety/critical review | `gpt-6-astra` | `high` |

Set both parameters explicitly on native `spawn_agent`, with
`fork_context=false`; do not rely on model inheritance. Do not pass provider,
API-key or authentication overrides. If the tool/fields are unavailable, stop
dispatch and return a concrete blocker, not a CLI/service/task-creation fallback.
The parent supplied the supported parameter metadata; this worker's tool
catalog has no native spawn entry, so this job did not independently execute it.
No Sol, GPT-5.5 or other worker model is approved. Criticality takes precedence
over the cheap default; escalate ambiguity to the parent before execution.

The parent counts all active delegated workers, including the two existing
user-owned children when active: at most **2**, no nested delegation. Assign
disjoint writes. This count and routing are instruction-enforced, not a verified
client hard limit. Each assignment has one bounded attempt and a stated time
bound; return progress within five minutes if still running. Failure returns
the exact blocker, last command/session and partial artifacts. Only the parent
may authorize one new, narrowed escalation assignment to an approved route;
never retry the same broad audit or launch a replacement while the old worker
is still active. No cancellation of unrelated healthy commands.

Handoff only: task ID, verified cwd, role, one goal, exact local input paths,
write scope, acceptance checks, time bound and return contract. Return changed
paths, actual checks, evidence and blockers. No full conversation/history fork,
secrets or unrelated repository content. Workers do not stage/push/publish or
touch production DB, jobs, consent or operator artifacts; the parent owns live
operations. A write-scope instruction does not create filesystem isolation.

## Installed support check / fallback

Status: **NOT_INSTALLED_SCHEMA_UNVERIFIED**. Read-only package metadata identified
CLI `@openai/codex` **0.154.0** and Codex app **26.623.141536**, build **4753**.
No schema was found at the checked package paths `config.schema.json`,
`schema/config.schema.json`, `schemas/config.schema.json`,
`dist/config.schema.json`, or app `Contents/Resources/config.schema.json` and
`Contents/Resources/app/config.schema.json`. This is not proof the build rejects
those keys: it means installed support was **not verified**. No LLM CLI ran,
no global configuration/credentials were read or changed, no broader scan ran.

The previously reviewed official docs describe project `.codex/config.toml`
`[agents]` keys `default_subagent_model`, `default_subagent_reasoning_effort`,
`max_concurrent_threads_per_session`, and project `.codex/agents/*.toml` roles.
No such config/roles were added: docs alone do not verify this installed build,
and the current environment also marks `.codex` read-only. The JSON above is
only a testable instruction record, **not** a Codex-consumed configuration.
Use explicit native parameters after the activation checks; do not claim TOML
enforcement. Project config, if later verified/approved, requires a trusted
project; role-specific overrides must not silently defeat this allowlist.

Previously reviewed sources (no new external call in this implementation):
- [Official subagent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Official project configuration](https://learn.chatgpt.com/docs/config-file/config-basic)
