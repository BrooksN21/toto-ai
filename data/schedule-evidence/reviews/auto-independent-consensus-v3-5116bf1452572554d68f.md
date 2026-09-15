# Automated independent schedule consensus: Хегельманн Литауэн — Паневежис

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T15:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202j9tlgvt107u002owkd`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202j9tlgvt107u002owkd-6437ddbf040fcf4e.json` — SHA-256 `6437ddbf040fcf4e220e4db0e6f88e509cd4efc501f9c8fc1104d74cc0bdbb2a`
- Sofascore: https://www.sofascore.com/football/match/fk-panevezys-fc-hegelmann/JEtbsnfCb#id:16273121
  - provider: `sofascore-v1`; event: `16273121`
  - evidence: `snapshots/auto/sofascore-v1-16273121-9337d127e47646a1.json` — SHA-256 `9337d127e47646a1fd88a0ccb471cdb9dafdb08a62bfa511832a5dc7032b4826`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
