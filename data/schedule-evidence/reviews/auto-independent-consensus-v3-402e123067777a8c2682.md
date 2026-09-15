# Automated independent schedule consensus: Эребру — Эстерсунд

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T17:05:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202t7tlk2t107fo153ns3`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202t7tlk2t107fo153ns3-c0b747ef9cafb731.json` — SHA-256 `c0b747ef9cafb731f70c6940b17d73311999f11bd9f8130652b2e3399761c3e1`
- Sofascore: https://www.sofascore.com/football/match/ostersunds-fk-orebro-sk/tKsLL#id:15272358
  - provider: `sofascore-v1`; event: `15272358`
  - evidence: `snapshots/auto/sofascore-v1-15272358-0c8910dca64b58e1.json` — SHA-256 `0c8910dca64b58e1f69cd4848b07a2c527c9e7553433e72b96fcc8da2d3ad4c6`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
