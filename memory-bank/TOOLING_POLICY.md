# Tooling Policy

This policy is the durable TotoAI tool and service boundary. `AGENTS.md`
contains the operational instructions.

## Allowlist

- Local repository files, shell commands, and project commands.
- Project-local skills stored in this repository.
- `openai-docs` for public OpenAI documentation.
- Public-site browser use, public web research, and public sports/data APIs.
- Local, generic `superpowers:*` engineering skills that respect this policy.
- `git` and public `gh` workflows; no other VCS CLI is authorized.

Catalog visibility is not authorization. User approval is required before any
non-allowlisted skill or service is used.

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
project data to another external agent or service without explicit user
approval. Remote Git publication and uploads are transmissions and therefore
also require explicit approval.
