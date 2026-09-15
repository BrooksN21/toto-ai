# Automated independent schedule consensus: Гренобль — Анси

Reviewed at **2026-09-03T16:18:29.659830Z**.
Scheduled kickoff: **2026-09-04T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71za6ltekjt10799jxn37y`
  - evidence: `snapshots/auto/goal-api-v1-cmt71za6ltekjt10799jxn37y-496c1b9ecbe91c14.json` — SHA-256 `496c1b9ecbe91c1400c79814957d12b8b7610172b291c747b5e14b8b2df7013a`
- Sofascore: https://www.sofascore.com/football/match/annecy-fc-grenoble-foot-38/wIsUrJb#id:16386170
  - provider: `sofascore-v1`; event: `16386170`
  - evidence: `snapshots/auto/sofascore-v1-16386170-2bcdff50a826dbac.json` — SHA-256 `2bcdff50a826dbac8092bb5492c69f064634c29bd7d9f65b75a8ba05e4f25bf2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
