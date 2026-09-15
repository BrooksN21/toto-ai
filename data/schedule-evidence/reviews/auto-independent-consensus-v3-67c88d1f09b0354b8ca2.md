# Automated independent schedule consensus: Хиберниан — Хартс

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fijgr79vgpd07q9v0bdiq`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fijgr79vgpd07q9v0bdiq-a0316b7269977392.json` — SHA-256 `a0316b72699773924ab77112260782a11b5d5207f2b4650c2b1583f4ce97bd67`
- Sofascore: https://www.sofascore.com/football/match/hibernian-heart-of-midlothian/dXseX#id:16362004
  - provider: `sofascore-v1`; event: `16362004`
  - evidence: `snapshots/auto/sofascore-v1-16362004-c2df5817c98cab88.json` — SHA-256 `c2df5817c98cab880bfbc76b7e5b4131165da7b61e11070c7eaa66482e584750`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
