# Automated independent schedule consensus: Сочи — Нижний Новгород

Reviewed at **2026-09-04T18:38:03.605915Z**.
Scheduled kickoff: **2026-09-05T14:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/pari-nizhny-novgorod-fc-sochi/JWseIFb#id:16491067
  - provider: `sofascore-v1`; event: `16491067`
  - evidence: `snapshots/auto/sofascore-v1-16491067-c72b523795ec8fd8.json` — SHA-256 `c72b523795ec8fd846d3e7f5deb21421f79c6264e83f5374692f725ed8f933e6`
- TheSportsDB: https://www.thesportsdb.com/event/2514842
  - provider: `thesportsdb-v1`; event: `2514842`
  - evidence: `snapshots/auto/thesportsdb-v1-2514842-823b917ed262d13b.json` — SHA-256 `823b917ed262d13b477acac3bed458ab92ac21e53f4cafd16e9f613e92c8ac8a`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
