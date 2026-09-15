# Automated independent schedule consensus: Фулхэм — Кристал Пэлас

Reviewed at **2026-09-04T20:05:36.416599Z**.
Scheduled kickoff: **2026-09-05T14:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63iknof6vdt107qo3eo54r`
  - evidence: `snapshots/auto/goal-api-v1-cmt63iknof6vdt107qo3eo54r-40668d4a9397a63f.json` — SHA-256 `40668d4a9397a63f9c92f9f78ce3fe6214d7f411350ace117ecb87766dafd390`
- Sofascore: https://www.sofascore.com/football/match/fulham-crystal-palace/hsT#id:16363269
  - provider: `sofascore-v1`; event: `16363269`
  - evidence: `snapshots/auto/sofascore-v1-16363269-75e6fefec6a63af8.json` — SHA-256 `75e6fefec6a63af83d3425691b36a5ba119948a7093d12a26145ff4ebb2afc74`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
