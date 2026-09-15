# Automated independent schedule consensus: Рубин — Ахмат

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202f6tlewt107c64fm5f1`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202f6tlewt107c64fm5f1-086ed3b634950af8.json` — SHA-256 `086ed3b634950af803882ef9d7434e0ff925939c2799cf719b91cad67c805952`
- Sofascore: https://www.sofascore.com/football/match/akhmat-grozny-rubin-kazan/IWsGcc#id:16390296
  - provider: `sofascore-v1`; event: `16390296`
  - evidence: `snapshots/auto/sofascore-v1-16390296-3a4ce0b2602cfdec.json` — SHA-256 `3a4ce0b2602cfdecb3d8e82e2e2835c4be0986488c156037ac28c6578d091932`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
