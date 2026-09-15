# Automated independent schedule consensus: Гроссето — Кампобассо

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qw09sqp9t107khzpis0o`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qw09sqp9t107khzpis0o-ecf0684f80d04375.json` — SHA-256 `ecf0684f80d0437501b291b9ef57e0aee1f75375af20981aba967212bfbe379e`
- Sofascore: https://www.sofascore.com/football/match/campobasso-fc-grosseto/Kfbsbwhd#id:16675033
  - provider: `sofascore-v1`; event: `16675033`
  - evidence: `snapshots/auto/sofascore-v1-16675033-a2c0584d6b324dbb.json` — SHA-256 `a2c0584d6b324dbb9d9ba8dae4ce2410c3706fc85244ec3fb347e52a2f97dd56`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
