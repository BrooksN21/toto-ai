# Automated independent schedule consensus: Тоттенхэм — Ньюкасл

Reviewed at **2026-08-28T15:15:43.662952Z** for drawing 4990, event #1.

Scheduled kickoff: **2026-08-29T16:30:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsvp4w9g9eqypg07pj0k5uk2
- Sofascore: https://www.sofascore.com/football/match/newcastle-united-tottenham-hotspur/IO#id:16363256
- GOAL matcher mode: `fuzzy_candidate_margin_0.178`
- Sofascore event ID: `16363256`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsvp4w9g9eqypg07pj0k5uk2-51b31342e9319f60.json` — SHA-256 `51b31342e9319f60cb3a769b093e4e6fb7c064236189b268104659e33862c794`
- `snapshots/auto/sofascore-search-cmsvp4w9g9eqypg07pj0k5uk2-177c337508ebf594.json` — SHA-256 `177c337508ebf59494a4d3016533f096fda79c9ac10595bfd9bad8cb4b4a3b43`
- `snapshots/auto/sofascore-16363256-f38d9a9a933cb43a.json` — SHA-256 `f38d9a9a933cb43abf640152fe69bf1b1a0e55bb2922ecbe1f32865344203d1a`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
