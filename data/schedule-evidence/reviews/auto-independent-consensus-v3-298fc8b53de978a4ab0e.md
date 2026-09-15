# Automated independent schedule consensus: Тулуза — Лилль

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fijg779vepd079vi9p0tl`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fijg779vepd079vi9p0tl-d7a954a6cd0e5e44.json` — SHA-256 `d7a954a6cd0e5e44350be54f8f3806c05915943a84698ff4498ebb017ec9474e`
- Sofascore: https://www.sofascore.com/football/match/toulouse-lille/THsGI#id:16310945
  - provider: `sofascore-v1`; event: `16310945`
  - evidence: `snapshots/auto/sofascore-v1-16310945-d92c645d797322ef.json` — SHA-256 `d92c645d797322effab30164a8593060b8e270138a56f88a1521affb3781e65b`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
