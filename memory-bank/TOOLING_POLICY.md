# Tooling Policy

This policy is the durable TotoAI tool and service boundary. `AGENTS.md`
contains the operational instructions.

## Allowlist

- Local repository files, shell commands, and project commands.
- Project-local skills stored in this repository.
- `openai-docs` for public OpenAI documentation.
- Public-site browser use, public web research, and public sports/data APIs.
- `git` and public `gh` workflows; no other VCS CLI is authorized.

## Repository enumeration safety

`git ls-files` is prohibited in TotoAI because repository-wide index
enumeration has repeatedly caused disruptive long-running Codex operations.
Do not use it directly, from shell substitutions, or through helper scripts.
`$HOME` is itself a Git work tree, so a bare Git command started from the wrong
directory can enumerate the entire home directory. TotoAI Git commands must
therefore use `scripts/project-git`; the wrapper pins operations to the TotoAI
root, rejects `ls-files`, and rejects `-C`/work-tree overrides. Shell tool calls
must also set `/Users/turshevr/toto-ai` as their explicit working directory.
Production Python code must use `toto_ai.project_git.run_project_git`, which
derives the exact project root, invokes that wrapper with the project root as
`cwd`, and fails closed unless the wrapper reports the same canonical Git
top-level. Direct production Git command literals outside that helper are
prohibited.
Do not perform whole-repository inventory by default. Use bounded,
task-specific path inspection (`rg` on named directories,
`scripts/project-git diff -- <paths>`, or
`scripts/project-git status --short --untracked-files=no`) and put an explicit
timeout or progress indicator around potentially long work.

Catalog visibility is not authorization. User approval is required before any
non-allowlisted skill or service is used.

## Absolute external-model prohibition

Claude, Anthropic APIs, Anthropic SDKs and CLIs, Eliza, and every other external
LLM, model, agent, coding assistant, or model proxy are absolutely denied.
They must not be invoked directly or indirectly through plugins, MCP servers,
connectors, wrappers, skills, SDKs, CLIs, model overrides, or subagents.

Repository content, task prompts, file paths, Git state, diffs, derived project
data, and secrets must never be transmitted to an external LLM or agent.
Read-only, context-only, planning, review, and research tasks are not
exceptions. No runtime approval can override this prohibition. A future change
requires the project owner to deliberately edit and commit this policy.

Only the model already hosting the current Codex task may perform model
inference for TotoAI. Model-backed subagents are prohibited. Static global
instruction bundles distributed under `claude-plugins-official` and other
third-party global skill bundles are not authorized; use project-local skills.

### Existing native Codex tasks — owner authorization 2026-09-05

The owner's deliberate policy-edit/commit instruction supersedes the earlier
single-task cancellation ONLY for the following existing user-owned tasks:
- Parent operations: `019f7afa-72e2-7403-85cd-d05f408a4ef3`,
  `/Users/turshevr/toto-ai`.
- Review: `01a06e1d-e0b9-7310-ba37-53a418668354`,
  `/Users/turshevr/.codex/worktrees/ab34/toto-ai`.
- Models: `01a06e1d-f37f-7763-ac2a-86200d3318e3`,
  `/Users/turshevr/.codex/worktrees/a7aa/toto-ai`.

Only that parent may resume/read/monitor those two task IDs using the native
Codex app `send_message_to_thread`, `read_thread`, and `wait_threads` tools on
host `local`. No other task IDs, new tasks/worktrees, fork, setup recreation,
or alternative service/tool to bypass a denied action are authorized.
Each task uses only its already-hosting Codex model; no model/provider override.
No nested or model-backed SUBAGENTS may be started inside any of these tasks.
This narrowly permits same-project minimal handoffs and local repository data
between these existing native task contexts, not external-model inference or
transmission. Never include credentials, tokens, secret files, or unrelated data.
The absolute external-LLM/proxy/Claude/Anthropic/Eliza and Yandex/internal-service
prohibitions remain unchanged; no remote upload or push is authorized here.

Parent retains exclusive production operations, including drawing 4997.
Children must first acknowledge their exact task ID, verified own cwd and scope.
They may write only own reports and explicitly assigned code in the listed own
worktree; production inspection is read-only. No production DB, jobs, scheduler,
catalog, consent or operator artifact changes. Child shell cwd is its verified
own worktree (this narrowly qualifies any main-cwd-only instruction); Git still
requires a correctly attested project wrapper, never bare Git or git ls-files.
Wrapper/baseline or filesystem permission failures block that operation, not
permission to bypass it. Parent integrates only after review and separate scope
approval. No worktree deletion or copying to children is authorized by this edit.
Earlier cancellation/setup records are history, not broader task permissions.

## Absolute denylist

Do not use Yandex, Arcadia, or internal-only skills, services, connectors, MCP
servers, or endpoints. This includes all `gena-*` skills (including
`gena-submission-ci-flow`), `arc`, Arcanum, ArcCI, Startrek, all `ya-*`,
Monium, `abc`, `aisuite`, internal Docs/Wiki/Intrasearch/Staff/Sandbox/IDP/
Experiments/DataLens/Tanker/TMS clients, and `yandex-team.ru` endpoints.

Use `git`/`gh`; never use `arc`. The denylist remains prohibited even when a
tool is installed or globally advertised.

## Recovery and local observation

Read the short `memory-bank/ACTIVE_PLAN.md` first, then its literal next command.
Read linked historical memory only for a specific uncertainty; do not restart a
full audit on compaction. All unfinished obligations remain in its hash-bound
archive. Validate exact live state when needed, not unchanged historical facts.
The owner removed chat heartbeats: use only the local plan-bound Python watcher.
It cannot wake an idle chat; do not promise unattended chat delivery. Bound long
commands reasonably and show progress; no blanket 30-second no-output rule.

## Memory and data handling

TotoAI project memory is limited to `AGENTS.md`, `memory-bank/`, `knowledge/`,
`research/`, `prompts/`, and project-local skills. Other repository files are
task inputs, not durable memory. Global skills and unrelated memory stores are
not project memory.

Protect `.env` files and all credentials or secrets: never print, document,
commit, or transmit them. Never send repository content or derived private
project data to another external LLM or agent. Remote Git publication and
uploads are transmissions and therefore require explicit approval.

## Pre-cutoff operator package boundary

An actionable manual package may come from the scheduler-owned
`operator-result.json` or a plan-bound `parallel-operator-result.json`
companion before T-10. The companion requires an actionable scheduler PLAY,
the same immutable final input/bank/stake for every candidate, a predeclared
non-degradation and safety selector, immutable pre-T-10 experimental
authorization, and exact package hashes. It must fall back to the scheduler
control on every error. Automatic wagering remains prohibited.

## Post-cutoff research package inspection

Research/rehearsal/simulation packages are never wagering artifacts and may
not be shown before their exact scheduler-bound operational cutoff. After that
cutoff, the project owner may explicitly request an exact package for read-only
analysis only. The file bytes must match the SHA-256 in their hash-bound
sidecar/result record and must bind the same drawing, plan and immutable final
input. The record must confirm `operator_compatible=false` and
`automatic_wagering=false`. Display must retain the research representation
and carry `POST-CUTOFF RESEARCH ONLY — NOT FOR WAGERING OR UPLOAD`; conversion
to BaltBet upload syntax remains prohibited.
