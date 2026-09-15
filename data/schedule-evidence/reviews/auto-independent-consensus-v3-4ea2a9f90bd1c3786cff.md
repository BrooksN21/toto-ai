# Automated independent schedule consensus: Портсмут — Кардифф Сити

Reviewed at **2026-09-04T18:38:03.224400Z**.
Scheduled kickoff: **2026-09-05T14:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/cardiff-city-portsmouth/cslb#id:16391649
  - provider: `sofascore-v1`; event: `16391649`
  - evidence: `snapshots/auto/sofascore-v1-16391649-8d6bc9e02d7a2d28.json` — SHA-256 `8d6bc9e02d7a2d28a4baa4cb0f783a711dadcc7982f81687df81d6b1fae8257f`
- TheSportsDB: https://www.thesportsdb.com/event/2501307
  - provider: `thesportsdb-v1`; event: `2501307`
  - evidence: `snapshots/auto/thesportsdb-v1-2501307-64e9821d45b6ffc9.json` — SHA-256 `64e9821d45b6ffc911a32cedfac1886a974ebc804fd9409c8471cbabf8258d97`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
