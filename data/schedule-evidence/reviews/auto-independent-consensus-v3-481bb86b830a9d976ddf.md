# Automated independent schedule consensus: Балтика — Локомотив Москва

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T17:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63inv6f7rpt107yzqkvn8v`
  - evidence: `snapshots/auto/goal-api-v1-cmt63inv6f7rpt107yzqkvn8v-b679a3920ff77817.json` — SHA-256 `b679a3920ff77817fcdd1bee555d67e7641a0c89cb2a1832e3fb6a2c3e595af0`
- Sofascore: https://www.sofascore.com/football/match/baltika-kaliningrad-lokomotiv-moscow/vWsrad#id:16390297
  - provider: `sofascore-v1`; event: `16390297`
  - evidence: `snapshots/auto/sofascore-v1-16390297-793bdfc124673230.json` — SHA-256 `793bdfc124673230c47c8608e07e0531a8c4183730e4218b6a2b32e8821b3d40`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
