# Automated independent schedule consensus: Брэдфорд — Бернли

Reviewed at **2026-08-26T08:27:30.369205Z** for drawing 4987, event #3.

Scheduled kickoff: **2026-08-26T18:45:00Z**.

GOAL API and a separately fetched Sofascore event agree exactly on home/away orientation and UTC kickoff. This evidence is used only for schedule timing and does not alter sports probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp46nz9azypg07b5ktpwep
- Sofascore: https://www.sofascore.com/football/match/bradford-city-burnley/gsx#id:16798244
- GOAL matcher mode: `fuzzy_candidate_margin_0.146`
- Sofascore event ID: `16798244`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp46nz9azypg07b5ktpwep-af41fa3fc1f6b17d.json` — SHA-256 `af41fa3fc1f6b17d3fb7c8979142fabf4d76d102e7e00b9108917044a7838b97`
- `snapshots/auto/sofascore-search-cmsvp46nz9azypg07b5ktpwep-113a8c0a2325cc4e.json` — SHA-256 `113a8c0a2325cc4ee92c1a168ef3fc5820fbf81524cb8146f0a7dbfdf75886e8`
- `snapshots/auto/sofascore-16798244-770510d6f3d3da35.json` — SHA-256 `770510d6f3d3da357b809a5547fd60dd159b1e7c0bd4e5e177f47796e0ed12b0`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
