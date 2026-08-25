# Agent Instructions

## Project and memory boundary

This repository has its own persistent project memory. It is local to the
TotoAI pet project and must never be mixed with personal knowledge bases, team
knowledge bases, global catalogs, or any other external memory source.

The only authorized project-memory sources are:

- `AGENTS.md`;
- `memory-bank/`;
- `knowledge/`;
- `research/`;
- `prompts/`;
- project-local skills stored in this repository.

Other repository files may be read as task inputs, but they are not persistent
project memory. Globally installed skills are not TotoAI memory and are not
authorized for engineering work unless explicitly allowlisted below.

Before making changes:
- Read all files in `memory-bank/`.
- Treat `memory-bank/` as the source of project context for TotoAI.
- Do not use user-local or globally installed skills, personal or team
  knowledge bases, chat memory, or unrelated memory stores as project memory.

## Tool and service authorization

The global skill, plugin, MCP, connector, or tool catalog is discovery metadata,
not authorization. A tool or service is authorized only when it is explicitly
allowlisted here. Ask the user for explicit approval before using any
non-allowlisted skill or service. Approval is not an exception to the absolute
denylist below.

Allowed without additional approval, subject to task scope and the security
rules below:

- local filesystem, shell, and project commands operating inside this
  repository;
- project-local skills stored in this repository;
- `openai-docs` for public OpenAI documentation;
- browser access to public sites and public web research;
- public sports and public data APIs;
- `git` and public `gh` workflows. These are the only authorized VCS CLIs.

Repository enumeration safety:

- Never run `git ls-files`, directly or indirectly, for this repository.
- Never use a whole-repository inventory as a default discovery step.
- Inspect only task-relevant paths with bounded commands such as targeted
  `rg`, `git diff -- <paths>`, or `git status --short --untracked-files=no`.
- Before starting a potentially long command, state what will run and use a
  bounded timeout or an interactive progress indicator.

## Absolute external-model prohibition

Never invoke, run, route to, authenticate to, or request inference from Claude,
Anthropic APIs, Anthropic SDKs or CLIs, Eliza, or any other external LLM, model,
agent, coding assistant, or model proxy. This prohibition applies both directly
and indirectly, including through plugins, MCP servers, connectors, wrappers,
skills, SDKs, CLIs, environment-configured model overrides, and subagents.

Never transmit repository content, task prompts, file paths, Git state, diffs,
derived project data, or secrets to an external LLM or agent. A read-only,
context-only, planning, review, or research task is not an exception. Tool
catalog visibility, installation state, prior use, and user approval do not
authorize external-model execution. No runtime approval can override this
prohibition; changing it requires the project owner to deliberately edit and
commit this policy.

TotoAI work may use only the model already hosting the current Codex task plus
local repository tools and the explicitly allowlisted non-LLM public services.
Do not start model-backed subagents. Static instruction files distributed under
`claude-plugins-official` and all other global third-party skill bundles are not
authorized; use project-local skills instead.

Never invoke, query, install, authenticate to, or transmit data to any
Yandex-, Arcadia-, or internal-only skill or service, even when it appears in a
global catalog. The denylist includes:

- every `gena-*` skill, including `gena-submission-ci-flow`;
- `arc`, Arcanum/`arcanum-client`, ArcCI/`arcci-client`, Startrek/
  `startrek-client`, and every `ya-*` tool or skill;
- Monium, `abc`, `aisuite`, `docs-client`, `wiki-client`, Intrasearch,
  Staff/`staff-api-mcp`, Sandbox/`sandbox-mcp`, IDP/`idp-client`,
  Experiments/`exp-client`, DataLens/`datalens-client`, Tanker/
  `tanker-client`, and TMS/`tms-client`;
- all other Yandex or Arcadia internal MCP servers, plugins, connectors,
  services, and endpoints, including `yandex-team.ru` and its subdomains.

Use `git`/`gh`; never use `arc`. Local Git inspection is allowed. Any push,
upload, PR creation, or other operation that transmits repository content to a
remote service requires explicit user approval.

## Secrets and external transmission

- Treat `.env`, credentials, tokens, cookies, private keys, and secret-bearing
  configuration as protected. Do not print, quote, persist in documentation,
  commit, or transmit them.
- Read a protected secret only when the user-approved task strictly requires
  it, and pass it only to the intended allowlisted public service without
  exposing its value.
- Never send repository contents, patches, prompts containing repository
  contents, or derived private project data to another external LLM or agent.
  The external-model prohibition above has no runtime approval exception.
- Public web research must use public queries and public sources; do not place
  private repository content into search queries, URLs, forms, or browser
  sessions.

The concise durable version of this boundary is
[`memory-bank/TOOLING_POLICY.md`](memory-bank/TOOLING_POLICY.md).

Maintenance rules:
- After every completed feature, update the project knowledge base first:
  `memory-bank/`, `knowledge/`, `skills/`, or `prompts/` as relevant.
- Update `memory-bank/CURRENT_STATE.md` after every meaningful commit.
- Update `memory-bank/DECISIONS.md` when architecture or mathematical
  definitions change.
- Update `memory-bank/ROADMAP.md` when a phase or task is completed.
- Do not silently change category, cover, budget, or probability definitions.
- Never manually synthesize, copy, display, or recommend a BaltBet upload
  package from research reports or expired artifacts. Operator-facing coupons
  may come only from the current scheduler-owned `operator-result.json` before
  its bound T-10 deadline; after T-10 they are expired.
- Run pytest and ruff before committing.
- Keep answers and implementation notes concise.
- Do not claim profitability without backtest evidence.
