# Automated independent schedule consensus: Петроджет — Тала Аль Гаиш

Reviewed at **2026-08-26T08:45:21.282766Z** for drawing 4987, event #9.

Scheduled kickoff: **2026-08-26T17:00:00Z**.

GOAL API and a separately fetched Sofascore event agree on canonical home/away identities and exactly on UTC kickoff. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp42qj9adzpg071ne7y3lh
- Sofascore: https://www.sofascore.com/football/match/petrojet-talaea-el-gaish/lwrsrwr#id:16738941
- GOAL matcher mode: `fuzzy_candidate_margin_0.439`
- Sofascore event ID: `16738941`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp42qj9adzpg071ne7y3lh-cc40fa20421d47bd.json` — SHA-256 `cc40fa20421d47bdda80a75ed38b5fc6e74e8f28884c2587539d870a1ae7c99b`
- `snapshots/auto/sofascore-search-cmsvp42qj9adzpg071ne7y3lh-ea0d81263e5ad831.json` — SHA-256 `ea0d81263e5ad831e5133ababca7c8af28fa4a0c8ff933683714a5e23521242c`
- `snapshots/auto/sofascore-16738941-12d156a7e946d050.json` — SHA-256 `12d156a7e946d050fad97e1146bacbcc40e1f4cd488a4e06ef026c9015b8aad9`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
