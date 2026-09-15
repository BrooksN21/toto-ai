# Automated independent schedule consensus: Хоффенхайм — Боруссия Дортмунд

Reviewed at **2026-09-04T18:38:03.420628Z**.
Scheduled kickoff: **2026-09-05T13:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/borussia-dortmund-tsg-hoffenheim/ubbsydb#id:16434019
  - provider: `sofascore-v1`; event: `16434019`
  - evidence: `snapshots/auto/sofascore-v1-16434019-b3c1623c80606a0a.json` — SHA-256 `b3c1623c80606a0a2e8d373fbafd458ab6b426af9aed7f156acda793c2a6b639`
- TheSportsDB: https://www.thesportsdb.com/event/2508344
  - provider: `thesportsdb-v1`; event: `2508344`
  - evidence: `snapshots/auto/thesportsdb-v1-2508344-17dc7a025c9e3084.json` — SHA-256 `17dc7a025c9e3084ce3bcb8296213ead1a35f58f79896e35c072ce61e510961d`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
