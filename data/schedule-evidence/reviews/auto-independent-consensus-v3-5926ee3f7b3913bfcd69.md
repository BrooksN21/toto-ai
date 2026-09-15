# Automated independent schedule consensus: Родина — Рубин

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T15:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qvzbsqoxt10755h3iv31`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qvzbsqoxt10755h3iv31-c59f7166b57eacf6.json` — SHA-256 `c59f7166b57eacf6a2b1e46af6e2b90d2676a645b31636d4039eac6ec9ed0128`
- Sofascore: https://www.sofascore.com/football/match/rodina-moscow-rubin-kazan/IWsZdEc#id:16395115
  - provider: `sofascore-v1`; event: `16395115`
  - evidence: `snapshots/auto/sofascore-v1-16395115-e2f00fd4665b857d.json` — SHA-256 `e2f00fd4665b857dc3049540ce049d43476703a11da1384da5be3616915d0a63`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
