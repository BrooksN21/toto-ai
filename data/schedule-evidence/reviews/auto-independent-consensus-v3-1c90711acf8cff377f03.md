# Automated independent schedule consensus: Питерборо Юнайтед — Барнсли

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T18:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmtqjemvs75kxku07sp37pyox`
  - evidence: `snapshots/auto/goal-api-v1-cmtqjemvs75kxku07sp37pyox-82d382f8c982514f.json` — SHA-256 `82d382f8c982514f6daa98b986f6e31a32e294eb65b0e7ec0f37e25e55e2c969`
- Sofascore: https://www.sofascore.com/football/match/peterborough-united-barnsley/yseb#id:16950622
  - provider: `sofascore-v1`; event: `16950622`
  - evidence: `snapshots/auto/sofascore-v1-16950622-e393f1476066a000.json` — SHA-256 `e393f1476066a000b426cf7fbced534b484a4c75fd1a00b436148a194a3f9f5e`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
