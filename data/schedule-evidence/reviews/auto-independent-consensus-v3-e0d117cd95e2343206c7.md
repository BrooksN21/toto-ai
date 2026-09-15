# Automated independent schedule consensus: Мюнстер — Саарбрюкен

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qweysqu8t107crd29dbe`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qweysqu8t107crd29dbe-0aebb46771d5c988.json` — SHA-256 `0aebb46771d5c988e83273f320b34ac6237038d8e904b21ced4f603fee1ca9c6`
- Sofascore: https://www.sofascore.com/football/match/preussen-munster-1-fc-saarbrucken/ebbsPbb#id:16596621
  - provider: `sofascore-v1`; event: `16596621`
  - evidence: `snapshots/auto/sofascore-v1-16596621-70c87c3528af5377.json` — SHA-256 `70c87c3528af53772f0c822f71ce2a763cdd9c950aa9ef323ece2668c13748a6`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
