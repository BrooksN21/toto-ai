# Automated independent schedule consensus: Эльче — Реал Сосьедад

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T19:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202whtllnt107g9xjoh4q`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202whtllnt107g9xjoh4q-dd2c02a5f3ce5a59.json` — SHA-256 `dd2c02a5f3ce5a5976380d91fa0a2be8c35f5bf71414836fd670e9558f915525`
- Sofascore: https://www.sofascore.com/football/match/elche-real-sociedad/zgbsWgb#id:16416319
  - provider: `sofascore-v1`; event: `16416319`
  - evidence: `snapshots/auto/sofascore-v1-16416319-76d4bedf415a97c8.json` — SHA-256 `76d4bedf415a97c82c2f9c1493047efe7fbc4c857d581cce5e51ab6952d3eef4`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
