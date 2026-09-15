# Automated independent schedule consensus: Барнсли — Блэкпул

Reviewed at **2026-09-01T14:06:31.613708Z**.
Scheduled kickoff: **2026-09-02T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1ficud794rpd07gdi8u029`
  - evidence: `snapshots/auto/goal-api-v1-cmt1ficud794rpd07gdi8u029-28765ab54d9bc101.json` — SHA-256 `28765ab54d9bc101c052e9982afeff570fb646920e6e53ce5bee33f9ab5d3b68`
- Sofascore: https://www.sofascore.com/football/match/blackpool-barnsley/ysrb#id:16395406
  - provider: `sofascore-v1`; event: `16395406`
  - evidence: `snapshots/auto/sofascore-v1-16395406-00c2bdf4d71f7ef4.json` — SHA-256 `00c2bdf4d71f7ef4f8f8f4867a06b471c835c5e7908eadb62175ff28a3a60410`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
