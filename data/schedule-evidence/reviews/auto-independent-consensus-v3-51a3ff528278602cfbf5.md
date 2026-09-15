# Automated independent schedule consensus: Ригас Футбола Скола — Рига ФК

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T16:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fi7gb78nfpd07s7w5ajfi`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fi7gb78nfpd07s7w5ajfi-31d48a0d738b4285.json` — SHA-256 `31d48a0d738b4285f268feee583d6ecc757f40c0f8c7fd4e04ffac02c8b3c638`
- Sofascore: https://www.sofascore.com/football/match/riga-fc-rfs/tzCstXob#id:16869782
  - provider: `sofascore-v1`; event: `16869782`
  - evidence: `snapshots/auto/sofascore-v1-16869782-b1415cf51decbc77.json` — SHA-256 `b1415cf51decbc77357a2c5f8f4c21e2d68417f4fcd54cb76bc65bb32097ff3d`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
