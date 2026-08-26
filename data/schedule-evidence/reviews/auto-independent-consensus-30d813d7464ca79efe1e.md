# Automated independent schedule consensus: Патронато — Атланта

Reviewed at **2026-08-26T08:45:21.282766Z** for drawing 4987, event #6.

Scheduled kickoff: **2026-08-26T18:30:00Z**.

GOAL API and a separately fetched Sofascore event agree on canonical home/away identities and exactly on UTC kickoff. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmrjvxmzl0xzyo8074ypghbvo
- Sofascore: https://www.sofascore.com/football/match/atlanta-patronato/QzrsZAw#id:16853881
- GOAL matcher mode: `fuzzy_candidate_margin_0.316`
- Sofascore event ID: `16853881`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmrjvxmzl0xzyo8074ypghbvo-c1a24023bb321f23.json` — SHA-256 `c1a24023bb321f2302ef70419a5359c7ffbdab97fe349e6ff36a01f1faf7fac8`
- `snapshots/auto/sofascore-search-cmrjvxmzl0xzyo8074ypghbvo-4a8de766b2f4d6c5.json` — SHA-256 `4a8de766b2f4d6c519671b17a9241e69eef4f8f9b8944d31149bd0a6c376031a`
- `snapshots/auto/sofascore-16853881-093489145083b23f.json` — SHA-256 `093489145083b23f2fc6a9930877e7548578beea8127448c452d95760e86354c`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
