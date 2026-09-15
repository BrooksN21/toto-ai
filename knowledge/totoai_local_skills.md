# TotoAI project-local Codex skills

C7 adds two thin discovery entrypoints in `.agents/skills/`:
`totoai-algorithm-review` and `totoai-backtesting`. Their single canonical
procedures remain [algorithm review](../skills/algorithm-review.md) and
[backtesting](../skills/backtesting.md); neither checklist is copied or changed.

These are project-local instructions, not models, plugins, background jobs, or
permissions. Use them only for a request explicitly targeting the verified
TotoAI repository. A TotoAI mention in another project is not sufficient.
Explicit invocation outside that boundary stops; it does not install anything.
Explanatory questions never authorize commands, tests, database access or runs.
Backtest planning/review is separate from execution authorization.

## Validation scope

The focused test checks the two on-disk entrypoints, their names/frontmatter,
relative links, one canonical source per skill, and absence of scripts/symlinks.
The first-party validator was attempted but its PyYAML dependency is absent
from the installed Python. macOS Ruby/Psych instead parsed both complete YAML
headers and checked their required string fields; no dependency was installed.
These checks are not a test of the live Codex selector, a sandbox, or a guarantee
against prompt misrouting. The following cases were walked through manually by the
already-hosting task model; no subagent or additional inference service ran.

| Request and target context | Expected selection/action |
| --- | --- |
| Verified TotoAI: review this exact package-optimizer diff against its baseline | algorithm-review; scoped review, no implicit fix |
| Verified TotoAI: check whether this cover change preserves category semantics | algorithm-review; use canonical definitions |
| Another repository: review its algorithm, inspired by TotoAI | neither; do not cross the project boundary |
| Explicit algorithm skill mention, but target repository unknown | stop and ask for the exact TotoAI target |
| Explain TotoAI category 13; no review requested | no automatic skill selection or commands; explanation only even if explicitly invoked |
| Verified TotoAI: plan a frozen offline backtest | backtesting; protocol only, no run |
| Verified TotoAI: run this authorized frozen backtest with bounded runtime and isolated outputs | backtesting; validate inputs before the authorized run |
| Verified TotoAI: review this existing backtest report | backtesting; review only, no rerun |
| Explain backtesting in general | neither; no commands |
| Explicit backtesting skill mention in another project | stop; no run or global installation |
| TotoAI: run a backtest, but required fixtures/as-of bindings are absent | identify missing inputs and stop before execution |
| TotoAI: use an oracle result as proof of predictive quality or actual ROI | retain diagnostic-only distinction; do not endorse the claim |
| TotoAI: prepare or upload an operator wagering package | neither; C7 grants no operational authority |

The names/descriptions provide discovery hints; the body carries the project
and action boundary. Default implicit discovery is retained for these two
stable workflows. No optional UI metadata, dependency connectors, or executable
helpers are needed.

## Integration boundary

Apply only the two new SKILL.md files, the focused structural test, and this
note. Do not copy an old worktree snapshot or modify global discovery/settings.
Local discovery in the Codex UI is not independently observed by these tests;
if necessary, verify it in the target TotoAI task after separate integration.

C7 is packaging, not the C6 code-simplification task. Earlier runtime/observer
work primarily added hardening and removed repeated computation; no general
code-pruning completion or predictive-quality gain is claimed.

Format reference: [official Build skills](https://learn.chatgpt.com/docs/build-skills).
