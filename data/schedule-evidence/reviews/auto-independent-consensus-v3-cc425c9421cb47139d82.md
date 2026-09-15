# Automated independent schedule consensus: Милан — Бенфика

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmtrytbag30dwnt08tl1o7y91`
  - evidence: `snapshots/auto/goal-api-v1-cmtrytbag30dwnt08tl1o7y91-e795c460c77626e9.json` — SHA-256 `e795c460c77626e9da34ef162deb8b7c71666eb83637b100e8739997a4edb2c0`
- Sofascore: https://www.sofascore.com/football/match/benfica-ac-milan/Rdbsgkb#id:16943965
  - provider: `sofascore-v1`; event: `16943965`
  - evidence: `snapshots/auto/sofascore-v1-16943965-73a3026ce4e1a618.json` — SHA-256 `73a3026ce4e1a618120faeceee864a8a8f57b185e03a5d23ef6cd4a639dec1ab`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
