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

## Absolute denylist

Do not use Yandex, Arcadia, or internal-only skills, services, connectors, MCP
servers, or endpoints. This includes all `gena-*` skills (including
`gena-submission-ci-flow`), `arc`, Arcanum, ArcCI, Startrek, all `ya-*`,
Monium, `abc`, `aisuite`, internal Docs/Wiki/Intrasearch/Staff/Sandbox/IDP/
Experiments/DataLens/Tanker/TMS clients, and `yandex-team.ru` endpoints.

Use `git`/`gh`; never use `arc`. The denylist remains prohibited even when a
tool is installed or globally advertised.

## Memory and data handling

TotoAI project memory is limited to `AGENTS.md`, `memory-bank/`, `knowledge/`,
`research/`, `prompts/`, and project-local skills. Other repository files are
task inputs, not durable memory. Global skills and unrelated memory stores are
not project memory.

Protect `.env` files and all credentials or secrets: never print, document,
commit, or transmit them. Never send repository content or derived private
project data to another external LLM or agent. Remote Git publication and
uploads are transmissions and therefore require explicit approval.
