# Automated independent schedule consensus: Ювентус — Милан

Reviewed at **2026-09-06T08:50:58.811679Z**.
Scheduled kickoff: **2026-09-06T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/ac-milan-juventus/MdbsRdb#id:16285004
  - provider: `sofascore-v1`; event: `16285004`
  - evidence: `snapshots/auto/sofascore-v1-16285004-8f5fefd10096fbe5.json` — SHA-256 `8f5fefd10096fbe536cb077937d2fef1009f50c3f31ad1800fd7a6a6fd0c4530`
- TheSportsDB: https://www.thesportsdb.com/event/2482161
  - provider: `thesportsdb-v1`; event: `2482161`
  - evidence: `snapshots/auto/thesportsdb-v1-2482161-3ad13a51cd65e7d5.json` — SHA-256 `3ad13a51cd65e7d5b9e177ca7441f7443059128099fa103c1756710eb8aa660a`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
