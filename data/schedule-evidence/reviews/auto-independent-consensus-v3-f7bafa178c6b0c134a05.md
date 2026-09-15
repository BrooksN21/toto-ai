# Automated independent schedule consensus: Локомотив Пловдив — Черно Море

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T16:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63ikxrf6y7t107cph9tumz`
  - evidence: `snapshots/auto/goal-api-v1-cmt63ikxrf6y7t107cph9tumz-1805830c6f790c98.json` — SHA-256 `1805830c6f790c98406af97bc799064da773fcf22c0c94c3bba500a811ef27af`
- Sofascore: https://www.sofascore.com/football/match/cherno-more-varna-lokomotiv-plovdiv/xpbsFpb#id:16295820
  - provider: `sofascore-v1`; event: `16295820`
  - evidence: `snapshots/auto/sofascore-v1-16295820-214a150ae40d1d4e.json` — SHA-256 `214a150ae40d1d4e637e3ec9f5d216e9fa9179222ab33b301a83e578cd2bb286`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
