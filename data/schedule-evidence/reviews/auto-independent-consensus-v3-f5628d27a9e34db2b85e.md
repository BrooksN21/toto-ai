# Automated independent schedule consensus: Миллуолл — Рексхэм

Reviewed at **2026-09-01T14:06:31.613708Z**.
Scheduled kickoff: **2026-09-02T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fid5x795fpd07g0jt1w5y`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fid5x795fpd07g0jt1w5y-7b427e6b710f950d.json` — SHA-256 `7b427e6b710f950d6a1c61f964f6304c2edbea800191fe55fca8d9f7bbbf5cf6`
- Sofascore: https://www.sofascore.com/football/match/wrexham-millwall/Asob#id:16391642
  - provider: `sofascore-v1`; event: `16391642`
  - evidence: `snapshots/auto/sofascore-v1-16391642-c66ce18366dcf411.json` — SHA-256 `c66ce18366dcf411a44a98acfacbea1ab5b235fc7f12ff7ddd474ed77b88321b`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
