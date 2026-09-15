# Automated independent schedule consensus: Бромли — Лейтон Ориент

Reviewed at **2026-08-31T13:41:59.389355Z**.
Scheduled kickoff: **2026-09-01T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fi01f77ukpd07vkgf21vy`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fi01f77ukpd07vkgf21vy-96ca63bc3ecb1d93.json` — SHA-256 `96ca63bc3ecb1d93be8174fcab275a82c209923125f1e1cbe4cd91fae7a077db`
- Sofascore: https://www.sofascore.com/football/match/bromley-leyton-orient/IbsFd#id:16395421
  - provider: `sofascore-v1`; event: `16395421`
  - evidence: `snapshots/auto/sofascore-v1-16395421-b08a92fdd0e2e134.json` — SHA-256 `b08a92fdd0e2e13471aa8679f569821587351cb3e1172a15e31c30c7b609d1f4`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
