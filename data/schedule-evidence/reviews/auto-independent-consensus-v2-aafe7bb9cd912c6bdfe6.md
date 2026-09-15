# Automated independent schedule consensus: Оулу — СИК

Reviewed at **2026-08-30T13:31:22.240925Z** for drawing 4992, event #13.

Scheduled kickoff: **2026-08-31T16:00:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmt1fhrl476rjpd07umqsl4a5
- Sofascore: https://www.sofascore.com/football/match/sjk-ac-oulu/occsVXi#id:15272824
- GOAL matcher mode: `fuzzy_candidate_margin_0.288`
- Sofascore event ID: `15272824`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmt1fhrl476rjpd07umqsl4a5-a70dc7f0c89bd932.json` — SHA-256 `a70dc7f0c89bd93265e0fa769cfc2a8152aefec8d0cc7cdbbb5d1332c0f4c190`
- `snapshots/auto/sofascore-search-cmt1fhrl476rjpd07umqsl4a5-d26f272e6c995f71.json` — SHA-256 `d26f272e6c995f7158d23df461e86445993fed8a7dc3e756485778a62ac5e809`
- `snapshots/auto/sofascore-15272824-904b6713a8cc6a3e.json` — SHA-256 `904b6713a8cc6a3ebc8d6c21b35f5c36168caa6d5618163d7676d72388568154`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
