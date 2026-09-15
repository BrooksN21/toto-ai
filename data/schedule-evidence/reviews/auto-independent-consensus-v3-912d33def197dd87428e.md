# Automated independent schedule consensus: Вест Хэм — Фулхэм

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmtqjen2y75mwku07vj2kjvni`
  - evidence: `snapshots/auto/goal-api-v1-cmtqjen2y75mwku07vj2kjvni-788ddb60c6bb9606.json` — SHA-256 `788ddb60c6bb9606519829010b1367579c8871120aa50c4c2eef69f8b67b6048`
- Sofascore: https://www.sofascore.com/football/match/fulham-west-ham-united/MsT#id:16950635
  - provider: `sofascore-v1`; event: `16950635`
  - evidence: `snapshots/auto/sofascore-v1-16950635-b0b2befe8ed01eb6.json` — SHA-256 `b0b2befe8ed01eb67ffaf4e074619df8e53c72af68c6f94c20fe1aed3e2898ed`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
