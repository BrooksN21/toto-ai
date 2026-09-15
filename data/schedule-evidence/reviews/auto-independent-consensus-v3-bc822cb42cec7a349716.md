# Automated independent schedule consensus: Гавр — Брест

Reviewed at **2026-09-04T18:38:03.706232Z**.
Scheduled kickoff: **2026-09-05T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/stade-brestois-le-havre/mIspJ#id:16310938
  - provider: `sofascore-v1`; event: `16310938`
  - evidence: `snapshots/auto/sofascore-v1-16310938-5b54f15196795ba5.json` — SHA-256 `5b54f15196795ba50f176e35cd680781c2ad1837c84c36bb8e4b01323822ec2c`
- TheSportsDB: https://www.thesportsdb.com/event/2489487
  - provider: `thesportsdb-v1`; event: `2489487`
  - evidence: `snapshots/auto/thesportsdb-v1-2489487-9f4dfb209b0e5ef7.json` — SHA-256 `9f4dfb209b0e5ef70741ba19befb3268c690f3fefd195ef8c4cb83c0d0d3e448`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
