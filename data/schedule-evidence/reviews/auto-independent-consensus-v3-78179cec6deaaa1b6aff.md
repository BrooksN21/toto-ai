# Automated independent schedule consensus: Суонси Сити — Рексхэм

Reviewed at **2026-09-04T18:38:03.334822Z**.
Scheduled kickoff: **2026-09-05T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/swansea-city-wrexham/obszb#id:16391654
  - provider: `sofascore-v1`; event: `16391654`
  - evidence: `snapshots/auto/sofascore-v1-16391654-44cd561a011dcece.json` — SHA-256 `44cd561a011dcece9d812112a8a81e9e267560b6e8149a41f85684a8766c84dc`
- TheSportsDB: https://www.thesportsdb.com/event/2501306
  - provider: `thesportsdb-v1`; event: `2501306`
  - evidence: `snapshots/auto/thesportsdb-v1-2501306-ba02d8828d4b12af.json` — SHA-256 `ba02d8828d4b12af3fb0c8cf12390fd5cfa9f603c6646252b6d87d835bae1cc9`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
