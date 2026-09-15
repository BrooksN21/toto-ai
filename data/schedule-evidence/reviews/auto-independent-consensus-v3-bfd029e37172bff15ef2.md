# Automated independent schedule consensus: Солихалл Мурс — Бэрроу

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qukqsqatt107mhw7bhlw`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qukqsqatt107mhw7bhlw-8b8e55024dab0145.json` — SHA-256 `8b8e55024dab0145ebbb8c3da0033472e88c29631c69af3019ea665bd03842bf`
- Sofascore: https://www.sofascore.com/football/match/solihull-moors-barrow-afc/XbsRid#id:16494317
  - provider: `sofascore-v1`; event: `16494317`
  - evidence: `snapshots/auto/sofascore-v1-16494317-23eea86daf4c88ac.json` — SHA-256 `23eea86daf4c88aca4368c17c46185d5e0067e135517b9ce00dff1222d510e11`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
