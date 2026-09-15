# Automated independent schedule consensus: ФК Копенгаген — Нордсьелланд

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fiig679qzpd07xdrbw46j`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fiig679qzpd07xdrbw46j-eb32797ac2688578.json` — SHA-256 `eb32797ac2688578a7bcfb3572edd0c3e58cccfded29371546dc022848576caf`
- Sofascore: https://www.sofascore.com/football/match/fc-nordsjaelland-fc-kobenhavn/JAsRA#id:16278686
  - provider: `sofascore-v1`; event: `16278686`
  - evidence: `snapshots/auto/sofascore-v1-16278686-2accf7bda306e096.json` — SHA-256 `2accf7bda306e09626b93fb9342a76b2de74d8beed3f8e2a8ec45cea822e8923`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
