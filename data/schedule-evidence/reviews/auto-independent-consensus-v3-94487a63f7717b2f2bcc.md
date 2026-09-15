# Automated independent schedule consensus: Грэмио РС — Интернациональ РС

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T23:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71z79qtdt2t107nr3i6cam`
  - evidence: `snapshots/auto/goal-api-v1-cmt71z79qtdt2t107nr3i6cam-947db3402b55a514.json` — SHA-256 `947db3402b55a514f9dfa69e90c494d5029b1cc56ef1d8a42b9cea9db97b2ae2`
- Sofascore: https://www.sofascore.com/football/match/gremio-internacional/qOsBtc#id:16795431
  - provider: `sofascore-v1`; event: `16795431`
  - evidence: `snapshots/auto/sofascore-v1-16795431-dd26d7bc8c40633a.json` — SHA-256 `dd26d7bc8c40633aaf46582cf3d47e223e647f6294943fd39bff6d71e1e190fd`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
