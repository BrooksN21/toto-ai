# Automated independent schedule consensus: Хапоэль Беэр-Шева — Маккаби Тель-Авив

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T17:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63iswzf95et107i32uxdsh`
  - evidence: `snapshots/auto/goal-api-v1-cmt63iswzf95et107i32uxdsh-eb7bf24ffcbf03d3.json` — SHA-256 `eb7bf24ffcbf03d370b4588a47ea65f7cd3f54ae28e7089eb58aee0debf551ec`
- Sofascore: https://www.sofascore.com/football/match/hapoel-beer-sheva-maccabi-tel-aviv/Ydcscec#id:16364235
  - provider: `sofascore-v1`; event: `16364235`
  - evidence: `snapshots/auto/sofascore-v1-16364235-3fc9517552235236.json` — SHA-256 `3fc951755223523691992fd823313e28f9ce5c88a76b660133160e0e40c837e9`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
