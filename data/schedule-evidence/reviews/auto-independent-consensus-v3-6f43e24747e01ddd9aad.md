# Automated independent schedule consensus: Бостон Юнайтед — Уокинг

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qujmsqa9t107skhdd7y6`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qujmsqa9t107skhdd7y6-238bf84de6c70ede.json` — SHA-256 `238bf84de6c70ede3671600497e791c07fee6477b03036bfa3e88777028f26d5`
- Sofascore: https://www.sofascore.com/football/match/woking-boston-united/zcsDc#id:16494314
  - provider: `sofascore-v1`; event: `16494314`
  - evidence: `snapshots/auto/sofascore-v1-16494314-1da43a90973a8a76.json` — SHA-256 `1da43a90973a8a76bf661cc01fd978f8a8c62347e2be03807c2f66a05f126413`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
