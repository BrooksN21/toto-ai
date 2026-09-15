# Automated independent schedule consensus: ТПС — СИК

Reviewed at **2026-09-07T14:51:46.127757Z** for drawing 5000, event #14.

Scheduled kickoff: **2026-09-08T15:00:00Z**.

GOAL API and a separately fetched Sofascore event independently match the target orientation and agree exactly on UTC kickoff. Canonical spelling variants are retained as aliases. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmtlap0dzhunjlh06atuhy5ek
- Sofascore: https://www.sofascore.com/football/match/sjk-turun-palloseura/eVsVXi#id:16985891
- GOAL matcher mode: `fuzzy_candidate_margin_0.330`
- Sofascore event ID: `16985891`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmtlap0dzhunjlh06atuhy5ek-0b648a6ae536ba5b.json` — SHA-256 `0b648a6ae536ba5b99c89b1dd25007d6ad6c67f8d0442e6c78fae18263818992`
- `snapshots/auto/sofascore-search-cmtlap0dzhunjlh06atuhy5ek-91516e7044319de6.json` — SHA-256 `91516e7044319de6e776cf2cdc61274c909558032ae5ae713c8046040ce7602f`
- `snapshots/auto/sofascore-16985891-1e6f1e61cbef2665.json` — SHA-256 `1e6f1e61cbef26659037d9d003d8da7bfdcf945669af99c541683dad69962197`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
