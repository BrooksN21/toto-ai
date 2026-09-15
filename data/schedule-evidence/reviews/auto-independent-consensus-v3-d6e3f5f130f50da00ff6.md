# Automated independent schedule consensus: Килмарнок — Сент-Миррен

Reviewed at **2026-09-01T14:06:31.613708Z**.
Scheduled kickoff: **2026-09-02T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1ficqd794jpd07foi3l6gs`
  - evidence: `snapshots/auto/goal-api-v1-cmt1ficqd794jpd07foi3l6gs-187fc8618897de7f.json` — SHA-256 `187fc8618897de7f48bebbb2183a30279a6fe3f9e111e06c835eee08290b6719`
- Sofascore: https://www.sofascore.com/football/match/st-mirren-kilmarnock/XWsjX#id:16362006
  - provider: `sofascore-v1`; event: `16362006`
  - evidence: `snapshots/auto/sofascore-v1-16362006-907a53fb69db6f37.json` — SHA-256 `907a53fb69db6f3715df9509ea0ebf636bc0497d9a21729ec02ce0b221852f2f`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
