# Automated independent schedule consensus: По — Сошо

Reviewed at **2026-09-03T16:18:29.659830Z**.
Scheduled kickoff: **2026-09-04T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71za7htekrt107x2fumt2x`
  - evidence: `snapshots/auto/goal-api-v1-cmt71za7htekrt107x2fumt2x-0dde7fced03c303f.json` — SHA-256 `0dde7fced03c303f77c0a0601b981b9a9173a44e6c657884cf45d57a7a403cf4`
- Sofascore: https://www.sofascore.com/football/match/pau-fc-sochaux/hIsKI#id:16386185
  - provider: `sofascore-v1`; event: `16386185`
  - evidence: `snapshots/auto/sofascore-v1-16386185-54d85ca45604cfdb.json` — SHA-256 `54d85ca45604cfdbe70a4d11357d6fe748bdeb6bee94ac31d5a6519b4e899065`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
