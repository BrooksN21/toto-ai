# Automated independent schedule consensus: Вестерло — Зюлте-Варегем

Reviewed at **2026-08-29T14:06:31.159347Z** for drawing 4991, event #12.

Scheduled kickoff: **2026-08-30T17:15:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp4j609cslpg07lzbgh00r
- Sofascore: https://www.sofascore.com/football/match/sv-zulte-waregem-kvc-westerlo/ThbsIib#id:16361904
- GOAL matcher mode: `fuzzy_candidate_margin_0.255`
- Sofascore event ID: `16361904`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp4j609cslpg07lzbgh00r-4d4fdf883fd9d686.json` — SHA-256 `4d4fdf883fd9d6864ce5e691030262e6c2a250dddd50af7a3eb0050df34550be`
- `snapshots/auto/sofascore-search-cmsvp4j609cslpg07lzbgh00r-c11e6b4505dcc619.json` — SHA-256 `c11e6b4505dcc619c8f14404032100cda414e75d3b17ee4cb7bd0413e66010b2`
- `snapshots/auto/sofascore-16361904-2427c6f5c389b5f2.json` — SHA-256 `2427c6f5c389b5f2a6eb76c3167d1dc8bce9bc3e88c23c43322e7c071c61bfbf`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
