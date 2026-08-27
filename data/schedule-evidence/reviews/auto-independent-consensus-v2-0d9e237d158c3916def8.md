# Automated independent schedule consensus: Нанси — Дюнкерк

Reviewed at **2026-08-27T16:22:10.135314Z** for drawing 4989, event #7.

Scheduled kickoff: **2026-08-28T18:00:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp48hu9b7npg07juu816q2
- Sofascore: https://www.sofascore.com/football/match/usl-dunkerque-nancy/AIstNc#id:16386258
- GOAL matcher mode: `fuzzy_candidate_margin_0.190`
- Sofascore event ID: `16386258`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp48hu9b7npg07juu816q2-7f5333fc651458a8.json` — SHA-256 `7f5333fc651458a822c95dafaa15d6070f85160f5d2950fbe8ddd200baa6bdb9`
- `snapshots/auto/sofascore-search-cmsvp48hu9b7npg07juu816q2-3322bcfe0813b903.json` — SHA-256 `3322bcfe0813b903e13171ea4887e89209d838f3ade0bf1d0d02b43bef0c89b8`
- `snapshots/auto/sofascore-16386258-2b8c2f1ba82a2e1c.json` — SHA-256 `2b8c2f1ba82a2e1cfb31efcaa7d6901f7c1401b345316d1afcf9e026da40a1d8`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
