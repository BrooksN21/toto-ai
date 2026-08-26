# Automated independent schedule consensus: Брэдфорд — Бернли

Reviewed at **2026-08-26T09:01:09.230992Z** for drawing 4987, event #3.

Scheduled kickoff: **2026-08-26T18:45:00Z**.

GOAL API and a separately fetched Sofascore event agree on canonical home/away identities and exactly on UTC kickoff. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp46nz9azypg07b5ktpwep
- Sofascore: https://www.sofascore.com/football/match/bradford-city-burnley/gsx#id:16798244
- GOAL matcher mode: `matched`
- Sofascore event ID: `16798244`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp46nz9azypg07b5ktpwep-5cb7132c2930663a.json` — SHA-256 `5cb7132c2930663ae16033bfee56ce053adc49aaf45e8b2f14b00851e63369c6`
- `snapshots/auto/sofascore-search-cmsvp46nz9azypg07b5ktpwep-113a8c0a2325cc4e.json` — SHA-256 `113a8c0a2325cc4ee92c1a168ef3fc5820fbf81524cb8146f0a7dbfdf75886e8`
- `snapshots/auto/sofascore-16798244-770510d6f3d3da35.json` — SHA-256 `770510d6f3d3da357b809a5547fd60dd159b1e7c0bd4e5e177f47796e0ed12b0`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
