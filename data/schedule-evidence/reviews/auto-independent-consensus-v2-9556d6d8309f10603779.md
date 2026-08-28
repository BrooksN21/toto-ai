# Automated independent schedule consensus: Кельн — Хоффенхайм

Reviewed at **2026-08-28T15:15:43.662952Z** for drawing 4990, event #7.

Scheduled kickoff: **2026-08-29T13:30:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp4gum9cfdpg07ty9ivgbo
- Sofascore: https://www.sofascore.com/football/match/1-fc-koln-tsg-hoffenheim/ubbswdb#id:16434022
- GOAL matcher mode: `fuzzy_candidate_margin_0.143`
- Sofascore event ID: `16434022`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp4gum9cfdpg07ty9ivgbo-ba3b7c0ee360243a.json` — SHA-256 `ba3b7c0ee360243a8b75caa09ea95f3b9ddc6cd04cdd4141e8a2a88a752740f9`
- `snapshots/auto/sofascore-search-cmsvp4gum9cfdpg07ty9ivgbo-4339cbbdc395a2ac.json` — SHA-256 `4339cbbdc395a2acd12c5c56086075e79300fd2f763b8fb8a7ad911e6355945f`
- `snapshots/auto/sofascore-16434022-2154c2fa1c8b2baf.json` — SHA-256 `2154c2fa1c8b2bafcf784dd3c1a20e981eaa1be013d8f3d55b72a7e6ad0cfc9a`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
