# Automated independent schedule consensus: Аль Файзали Харма — Аль Фатех

Reviewed at **2026-08-26T08:27:30.369205Z** for drawing 4987, event #15.

Scheduled kickoff: **2026-08-26T16:00:00Z**.

GOAL API and a separately fetched Sofascore event agree exactly on home/away orientation and UTC kickoff. This evidence is used only for schedule timing and does not alter sports probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp42x09af3pg075im3r193
- Sofascore: https://www.sofascore.com/football/match/al-faisaly-al-fateh/yvxsKvx#id:16629436
- GOAL matcher mode: `fuzzy_candidate_margin_0.118`
- Sofascore event ID: `16629436`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp42x09af3pg075im3r193-919237a37e5a54d8.json` — SHA-256 `919237a37e5a54d8ed9ed5820665e04a2615c45644d006966c5bbf4e72133616`
- `snapshots/auto/sofascore-search-cmsvp42x09af3pg075im3r193-f3223e68f7f981af.json` — SHA-256 `f3223e68f7f981af104bde39c22698f9832072925c316d12de0002c190a4e614`
- `snapshots/auto/sofascore-16629436-fa99652b2d563a31.json` — SHA-256 `fa99652b2d563a3196f32269841c5e0f0d968485d2aff5a353c0c2ab902acd12`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
