# Automated independent schedule consensus: Гленторан — Колрейн

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qui6sq9lt107p1gat2ag`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qui6sq9lt107p1gat2ag-d0d9fef0181f665f.json` — SHA-256 `d0d9fef0181f665f7c76ab8e38a2f06f9af48dbc73ce729504ee11ead556230b`
- Sofascore: https://www.sofascore.com/football/match/coleraine-fc-glentoran-fc/Edcsvfc#id:16396750
  - provider: `sofascore-v1`; event: `16396750`
  - evidence: `snapshots/auto/sofascore-v1-16396750-1db6a53195bcd49c.json` — SHA-256 `1db6a53195bcd49c0b2a557e6f13c3fc19231418abb2bb91aa4272afe25000d2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
