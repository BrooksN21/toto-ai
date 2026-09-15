# Automated independent schedule consensus: Сивасспор — Мардин ББ

Reviewed at **2026-09-01T14:20:18.647316Z**.
Scheduled kickoff: **2026-09-02T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fi9e278wkpd07gqyt0bqu`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fi9e278wkpd07gqyt0bqu-5ddac89260acdb6e.json` — SHA-256 `5ddac89260acdb6edf4df05394a521360ffdada7d7f05436b6a76b0674a1eb4e`
- Sofascore: https://www.sofascore.com/football/match/mardin-1969-spor-sivasspor/BlbsFJtc#id:16490449
  - provider: `sofascore-v1`; event: `16490449`
  - evidence: `snapshots/auto/sofascore-v1-16490449-1130c9b88fd1a890.json` — SHA-256 `1130c9b88fd1a890577f2a5acf7ccfb9a89aaf2cb2e2edf218548e9e3d766aec`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
