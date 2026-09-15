# Automated independent schedule consensus: Бодрумспор — Эрокспор

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fiicv79qhpd07jpd6p5us`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fiicv79qhpd07jpd6p5us-ef6f35c147d13ce9.json` — SHA-256 `ef6f35c147d13ce986f4cfc15b8acaa342d8357e81d289607c414ee2ab4eca4b`
- Sofascore: https://www.sofascore.com/football/match/esenler-erokspor-bodrum-fk/PXFbsFZec#id:16490450
  - provider: `sofascore-v1`; event: `16490450`
  - evidence: `snapshots/auto/sofascore-v1-16490450-fb50d018ae39a0ff.json` — SHA-256 `fb50d018ae39a0ff2322d5a8539df08d83066459c341ae411969a39f8981e97a`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
