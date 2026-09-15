# Automated independent schedule consensus: Широки Бриег — Сараево

Reviewed at **2026-09-01T14:20:18.647316Z**.
Scheduled kickoff: **2026-09-02T18:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fi77l78mrpd07pz1370ft`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fi77l78mrpd07pz1370ft-a0c3f8b9e2cd525a.json` — SHA-256 `a0c3f8b9e2cd525a94201a6d85b780dae44818ab73649bcef0d5c82e86778a34`
- Sofascore: https://www.sofascore.com/football/match/nk-siroki-brijeg-fk-sarajevo/MecsOec#id:16458959
  - provider: `sofascore-v1`; event: `16458959`
  - evidence: `snapshots/auto/sofascore-v1-16458959-1f009b4a3fd2a7e2.json` — SHA-256 `1f009b4a3fd2a7e296162d6c2f5e725205bce524d5ff3204b6a1e3c141ab3464`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
