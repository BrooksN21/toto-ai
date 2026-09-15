# Automated independent schedule consensus: Браге — Сандвикенс

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qtq9sq1at1076hu60wau`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qtq9sq1at1076hu60wau-7d128bed485197e7.json` — SHA-256 `7d128bed485197e7ab2a9c0c8df1fd9b3f51f323dd777560aacfde5c9abd0a99`
- Sofascore: https://www.sofascore.com/football/match/sandvikens-if-ik-brage/CKsUL#id:15272371
  - provider: `sofascore-v1`; event: `15272371`
  - evidence: `snapshots/auto/sofascore-v1-15272371-caef60364b6ec710.json` — SHA-256 `caef60364b6ec710e658f0354855df8a35399ec9ffb136f9f51f11a96b1f5dce`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
