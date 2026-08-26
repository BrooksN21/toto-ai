# Automated independent schedule consensus: Осане — Люн Осло

Reviewed at **2026-08-26T08:27:30.369205Z** for drawing 4987, event #14.

Scheduled kickoff: **2026-08-26T17:00:00Z**.

GOAL API and a separately fetched Sofascore event agree exactly on home/away orientation and UTC kickoff. This evidence is used only for schedule timing and does not alter sports probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp42rc9ae5pg07hpwtvu6r
- Sofascore: https://www.sofascore.com/football/match/asane-lyn-fk/hnsHn#id:15265874
- GOAL matcher mode: `fuzzy_candidate_margin_0.181`
- Sofascore event ID: `15265874`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp42rc9ae5pg07hpwtvu6r-74eb787a7f50e048.json` — SHA-256 `74eb787a7f50e0484becf73fc7acf504f047a0f14ed5ce5d4bab26d49a39e714`
- `snapshots/auto/sofascore-search-cmsvp42rc9ae5pg07hpwtvu6r-5a561a6c0c3330f2.json` — SHA-256 `5a561a6c0c3330f24611034d44d51643c97749b1505d64ed50a2284a44036e34`
- `snapshots/auto/sofascore-15265874-c27820fe9f5275f1.json` — SHA-256 `c27820fe9f5275f1afe8deb2aee3eb1cd128db472bda71a4d96a85411efa9cdf`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
