# Automated independent schedule consensus: Рединг — Мансфилд Таун

Reviewed at **2026-09-01T14:20:18.647316Z**.
Scheduled kickoff: **2026-09-02T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fifni79dvpd07n5bl0j0x`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fifni79dvpd07n5bl0j0x-c7f9b87eb12295ba.json` — SHA-256 `c7f9b87eb12295bac9cc5d1b2baa09c2dc783676c683436753516e212ffc1284`
- Sofascore: https://www.sofascore.com/football/match/mansfield-town-reading/Dsvb#id:16395412
  - provider: `sofascore-v1`; event: `16395412`
  - evidence: `snapshots/auto/sofascore-v1-16395412-5a57fcfdb4b67444.json` — SHA-256 `5a57fcfdb4b67444bd747fdad2a7e4779c30c95ad501005858a7d113bb92dd5c`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
