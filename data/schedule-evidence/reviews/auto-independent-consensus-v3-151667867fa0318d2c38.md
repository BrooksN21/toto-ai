# Automated independent schedule consensus: Андерлехт — Лион

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmtrytbai30dynt080y7rb3qk`
  - evidence: `snapshots/auto/goal-api-v1-cmtrytbai30dynt080y7rb3qk-eac71e43c185eb5b.json` — SHA-256 `eac71e43c185eb5baf6b2a9f8868d54b5cf9cd7a100eb703ce8ead0e229f9d2a`
- Sofascore: https://www.sofascore.com/football/match/rsc-anderlecht-olympique-lyonnais/ZHsaib#id:16945000
  - provider: `sofascore-v1`; event: `16945000`
  - evidence: `snapshots/auto/sofascore-v1-16945000-4ecba5c4a765c650.json` — SHA-256 `4ecba5c4a765c6503cd2e46aad0de1d08417742d91bcaca3a1f567a52ffcddea`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
