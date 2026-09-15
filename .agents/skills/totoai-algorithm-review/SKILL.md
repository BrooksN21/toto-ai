---
name: totoai-algorithm-review
description: Review probability, brief, cover, or package algorithm changes only for requests explicitly targeting the verified TotoAI project. Do not select for other repositories, generic algorithm reviews, explanation-only questions, backtest execution, or operator and wagering actions.
---

# TotoAI algorithm review

## Project and action boundary

This is a repo-local instruction wrapper, not another model or an authorization.
Bind the requested target to the repository containing this file at
`.agents/skills/totoai-algorithm-review/SKILL.md`; its root is three directories
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

For an actual review, follow the current local AGENTS.md and
[tooling policy](../../../memory-bank/TOOLING_POLICY.md). This skill grants no
additional tools, providers, mutations, publication, or operational authority.
A review request does not authorize implementing fixes.

## Review contract

Input: the specific TotoAI change or artifact, its exact baseline, intended
objective, and available tests/evidence. Ask only for a missing input that
prevents the requested review; do not invent bindings or probabilities.

Read and apply the single canonical
[algorithm-review checklist](../../../skills/algorithm-review.md).
Do not copy or redefine its mathematical, category, coverage, or budget rules
here. Follow linked references only for an uncertainty relevant to this review.

Distinguish code correctness, equivalent implementation, predictive quality,
and package coverage. Oracle/post-outcome diagnostics are not evidence of
predictive quality or actual ROI. Report only measured or bound evidence.

Output: a concise scoped verdict with actionable findings and exact locations,
checks performed, and explicit unverified limits. Run only relevant bounded
checks authorized for this review; do not turn the task into a broader cleanup,
model experiment, operator delivery, or backtest.
