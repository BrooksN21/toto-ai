# Automated independent schedule consensus: Баллимена — Каррик Рейнджерс

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qugisq8zt107qb0b58w9`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qugisq8zt107qb0b58w9-6c27172ebbe29f08.json` — SHA-256 `6c27172ebbe29f087f0c7fa2b17fdb925da563b73147c6c57fcb5c5632943bda`
- Sofascore: https://www.sofascore.com/football/match/carrick-rangers-ballymena-united/ufcsIKo#id:16396748
  - provider: `sofascore-v1`; event: `16396748`
  - evidence: `snapshots/auto/sofascore-v1-16396748-ec4fedd6a1aaafa5.json` — SHA-256 `ec4fedd6a1aaafa5cedcc576033a0c1bae5e244908678a5d2770cd6f7788f53d`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
