# Automated independent schedule consensus: Ноттингем Форест — Тоттенхэм

Reviewed at **2026-09-04T18:34:39.074027Z**.
Scheduled kickoff: **2026-09-05T14:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/tottenham-hotspur-nottingham-forest/osI#id:16363638
  - provider: `sofascore-v1`; event: `16363638`
  - evidence: `snapshots/auto/sofascore-v1-16363638-b8bc498b94297dbf.json` — SHA-256 `b8bc498b94297dbf5f02a967c9c9b9d463e924bfbe0596ac5ef46ce79c56f7c6`
- TheSportsDB: https://www.thesportsdb.com/event/2494029
  - provider: `thesportsdb-v1`; event: `2494029`
  - evidence: `snapshots/auto/thesportsdb-v1-2494029-783c513e2bb43f5e.json` — SHA-256 `783c513e2bb43f5ecf30b27d831f0793a1149067390737cecbf96ca827a1f378`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
