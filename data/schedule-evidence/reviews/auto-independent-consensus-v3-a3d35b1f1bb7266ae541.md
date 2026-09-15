# Automated independent schedule consensus: Лаваль — Ред Стар

Reviewed at **2026-09-03T16:18:29.659830Z**.
Scheduled kickoff: **2026-09-04T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71za6oteklt107e3v9unik`
  - evidence: `snapshots/auto/goal-api-v1-cmt71za6oteklt107e3v9unik-5988a23a24bf4c51.json` — SHA-256 `5988a23a24bf4c51722de687fc4b046caa5597532769bddb2c350af46100896a`
- Sofascore: https://www.sofascore.com/football/match/red-star-fc-stade-lavallois/yIszhw#id:16386184
  - provider: `sofascore-v1`; event: `16386184`
  - evidence: `snapshots/auto/sofascore-v1-16386184-23b94ec9d83aae76.json` — SHA-256 `23b94ec9d83aae7695c3d34d97e621c7157ba259b93d1cda5981fcfd162472a2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
