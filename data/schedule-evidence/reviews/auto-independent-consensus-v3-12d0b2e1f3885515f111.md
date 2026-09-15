# Automated independent schedule consensus: Энфилд Таун — Дартфорд

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qul8sqb5t107vjhfp9b8`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qul8sqb5t107vjhfp9b8-07764e349c84cf65.json` — SHA-256 `07764e349c84cf6549b4ad6238021a3b6627ebe6fbabc00f6d01da67738a03b3`
- Sofascore: https://www.sofascore.com/football/match/enfield-town-dartford/weslht#id:16596267
  - provider: `sofascore-v1`; event: `16596267`
  - evidence: `snapshots/auto/sofascore-v1-16596267-738ed1281cd13430.json` — SHA-256 `738ed1281cd13430d5b614ebb9169753e7329628ff004d40a4b816febc9743a2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
