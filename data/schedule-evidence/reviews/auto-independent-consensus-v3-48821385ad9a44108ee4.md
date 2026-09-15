# Automated independent schedule consensus: Эспаньол — Севилья

Reviewed at **2026-09-06T08:50:58.811679Z**.
Scheduled kickoff: **2026-09-06T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/sevilla-espanyol/ogbsIgb#id:16416323
  - provider: `sofascore-v1`; event: `16416323`
  - evidence: `snapshots/auto/sofascore-v1-16416323-61bf548117709144.json` — SHA-256 `61bf5481177091448df55d7c8477c4d6b67c3b16ff0d5fd808eaaf3199b0742b`
- TheSportsDB: https://www.thesportsdb.com/event/2506203
  - provider: `thesportsdb-v1`; event: `2506203`
  - evidence: `snapshots/auto/thesportsdb-v1-2506203-687b7c62d1f744c6.json` — SHA-256 `687b7c62d1f744c65f8a7d6dd2e28e1529d0f18e75d9f5772e61915257ca48f9`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
