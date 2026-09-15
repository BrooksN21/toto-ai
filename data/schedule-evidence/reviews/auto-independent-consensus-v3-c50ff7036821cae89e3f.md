# Automated independent schedule consensus: Шеффилд Юнайтед — Норвич

Reviewed at **2026-09-04T20:05:36.416599Z**.
Scheduled kickoff: **2026-09-05T14:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63ikktf6ult107nulwds7d`
  - evidence: `snapshots/auto/goal-api-v1-cmt63ikktf6ult107nulwds7d-da9ed5c80d22a5a5.json` — SHA-256 `da9ed5c80d22a5a50fab1f98a907a0c5fddcdf216307833af4bfc8812282153b`
- Sofascore: https://www.sofascore.com/football/match/norwich-city-sheffield-united/psnf#id:16391652
  - provider: `sofascore-v1`; event: `16391652`
  - evidence: `snapshots/auto/sofascore-v1-16391652-357a480b9f74641c.json` — SHA-256 `357a480b9f74641c3f691e6bebd072477543f1d0cc61fb04418aad22d3935621`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
