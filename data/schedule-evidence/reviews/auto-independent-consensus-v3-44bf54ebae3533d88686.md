# Automated independent schedule consensus: Удинезе — Лацио

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202uotlktt10760b9ptkq`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202uotlktt10760b9ptkq-77206a830590d3e0.json` — SHA-256 `77206a830590d3e063854eddcf351c1eb0fb3372cdb6ce81f8489e4b2a3eb9d0`
- Sofascore: https://www.sofascore.com/football/match/lazio-udinese/VdbsZdb#id:16285006
  - provider: `sofascore-v1`; event: `16285006`
  - evidence: `snapshots/auto/sofascore-v1-16285006-6287d3522a3fa947.json` — SHA-256 `6287d3522a3fa947be793b26e116eb4647881cb05e1ef114a0f1cf82e7e71d92`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
