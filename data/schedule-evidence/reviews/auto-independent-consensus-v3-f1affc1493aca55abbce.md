# Automated independent schedule consensus: Пинето Кальчо — Форли

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qw0wsqpht107fyp6vonv`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qw0wsqpht107fyp6vonv-44b27236d218af90.json` — SHA-256 `44b27236d218af90822eb3c653b8f378a78dc4bb71cc35be3d9fb87e427bd065`
- Sofascore: https://www.sofascore.com/football/match/pineto-forli/IfbsdAQb#id:16675063
  - provider: `sofascore-v1`; event: `16675063`
  - evidence: `snapshots/auto/sofascore-v1-16675063-1bec1d98bc7e1acc.json` — SHA-256 `1bec1d98bc7e1acc32233cde701ca8bc19a1c47ac7d23debf5004f4061aeb393`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
