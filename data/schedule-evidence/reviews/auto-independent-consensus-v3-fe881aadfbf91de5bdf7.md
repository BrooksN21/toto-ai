# Automated independent schedule consensus: Реал Сосьедад — Сельта

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fijd279v2pd07jzzt5rcp`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fijd279v2pd07jzzt5rcp-2cea9b7a60d3343a.json` — SHA-256 `2cea9b7a60d3343a3d74a9b3bf29cf9aadab26e10d63599ac613e0db792c8535`
- Sofascore: https://www.sofascore.com/football/match/real-sociedad-celta-vigo/wgbszgb#id:16416340
  - provider: `sofascore-v1`; event: `16416340`
  - evidence: `snapshots/auto/sofascore-v1-16416340-9a4696c2a8cb35ca.json` — SHA-256 `9a4696c2a8cb35cae24f4f60aa8292197c6bc705d9f86f3ee50f87ffb4976e79`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
