---
name: totoai-backtesting
description: Plan, run, or review a scoped offline backtest only when the request explicitly targets the verified TotoAI project. Do not select for other projects, generic backtesting explanations, explanation-only questions, live collection, model training, or operator and wagering actions.
---

# TotoAI backtesting

## Project and action boundary

This is a repo-local instruction wrapper, not another model or an authorization.
Bind the requested target to the repository containing this file at
`.agents/skills/totoai-backtesting/SKILL.md`; its root is three directories
above this skill directory. Use the supplied task cwd/project context, then
confirm the local [project metadata](../../../pyproject.toml) names `toto-ai`
and the local [AGENTS.md](../../../AGENTS.md) identifies TotoAI. A folder name
or a mention of TotoAI while working on another project is insufficient.
If the target is outside this repository or cannot be verified, stop this skill
and ask for the exact TotoAI target; do not search another project or the home
directory. Do not install or copy this skill into global discovery locations.

For an explanation-only question, including an explicit invocation of this
skill, answer from supplied context/documentation only: do not execute shell,
Git, tests, backtests, database, or network commands. Missing context warrants
a concise question, not an automatic investigation.

Follow the current local AGENTS.md and
[tooling policy](../../../memory-bank/TOOLING_POLICY.md). Planning or reviewing
a backtest does not authorize running it. Do not touch live databases, providers,
scheduler jobs, consent, operator packages, or global configuration.

## Backtest contract

Input for execution: an authorized offline scope, frozen input/artifact paths
and hashes, completed-drawing results, pre-draw availability/as-of evidence,
candidate/baseline definitions, budget/stake, bounded runtime, and an isolated
output destination. If a required fixture, binding, or execution authorization
is missing, state the gap and stop before execution; do not fabricate it or
fetch live replacements.

Read and apply the single canonical
[backtesting checklist](../../../skills/backtesting.md).
Use its existing commands and linked references only as needed for the approved
scope; the command names are not instructions to run them on activation.
Do not duplicate or redefine its category, coverage, provenance, or budget rules.

Keep generators blind to post-draw outcomes until their inputs and outputs are
frozen. Oracle/post-outcome diagnostics are diagnostic-only, not predictive
quality or ROI evidence. Preserve missing/rejected cases and denominators;
do not promote research outputs into actionable wagering artifacts.

Output for planning/review: the protocol or scoped findings and missing inputs,
without executing a backtest. Output for an authorized run: bounded reproducible
results and the canonical exports, with exact inputs, checks, failures,
limitations, and measured runtime. Do not claim profitability from a simulation.
