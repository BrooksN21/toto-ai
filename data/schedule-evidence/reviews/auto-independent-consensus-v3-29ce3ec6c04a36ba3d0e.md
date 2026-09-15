# Automated independent schedule consensus: Малага — Леванте

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63inrwf7q8t107w5bpqjj8`
  - evidence: `snapshots/auto/goal-api-v1-cmt63inrwf7q8t107w5bpqjj8-c1d3ed401597277a.json` — SHA-256 `c1d3ed401597277a302991089ad71c57b98cdaaf5ed927e5123884918144bc2a`
- Sofascore: https://www.sofascore.com/football/match/levante-ud-malaga-cf/FgbsZgb#id:16416320
  - provider: `sofascore-v1`; event: `16416320`
  - evidence: `snapshots/auto/sofascore-v1-16416320-c85e6770dc40de08.json` — SHA-256 `c85e6770dc40de08b76c9c0695115dea081934d341f0eae071d5ef316daeea0e`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
