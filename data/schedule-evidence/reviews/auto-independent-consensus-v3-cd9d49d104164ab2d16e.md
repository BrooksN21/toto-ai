# Automated independent schedule consensus: Динамо Москва — Спартак Москва

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T15:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63ik37f6pzt107nmlrdaig`
  - evidence: `snapshots/auto/goal-api-v1-cmt63ik37f6pzt107nmlrdaig-a093ad76a563fb0c.json` — SHA-256 `a093ad76a563fb0cd7b6a35b81f087cc789bc5dcf5391a700fde4fca1a3728ad`
- Sofascore: https://www.sofascore.com/football/match/fc-spartak-moscow-dynamo-moscow/pWsyW#id:16390289
  - provider: `sofascore-v1`; event: `16390289`
  - evidence: `snapshots/auto/sofascore-v1-16390289-e5b2f38b16220aa4.json` — SHA-256 `e5b2f38b16220aa49a0b72f07ee471a4a4f5e20a70823aeaa873c7b615ebe9af`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
