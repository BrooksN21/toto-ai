# Automated independent schedule consensus: Падерборн — Фрайбург

Reviewed at **2026-09-04T18:38:03.514722Z**.
Scheduled kickoff: **2026-09-05T13:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/sc-paderborn-07-sc-freiburg/Nabslbb#id:16434024
  - provider: `sofascore-v1`; event: `16434024`
  - evidence: `snapshots/auto/sofascore-v1-16434024-a3e0596c448fa6d3.json` — SHA-256 `a3e0596c448fa6d36a3c194e0812d4a28b337f57b4f21c37de40bc49e9c52f74`
- TheSportsDB: https://www.thesportsdb.com/event/2508350
  - provider: `thesportsdb-v1`; event: `2508350`
  - evidence: `snapshots/auto/thesportsdb-v1-2508350-4b50c125b1ae46a0.json` — SHA-256 `4b50c125b1ae46a0160d8b88f5b405d68656375403bdd96ac96900e09a3e598a`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
