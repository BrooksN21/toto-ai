# Automated independent schedule consensus: Райо Вальекано — Эспаньол

Reviewed at **2026-09-15T13:27:14.614060Z**.
Scheduled kickoff: **2026-09-15T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qvopsqm0t107diw00tzy`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qvopsqm0t107diw00tzy-564a1d345e0ab753.json` — SHA-256 `564a1d345e0ab7536ac62b32c5a7f8e80e9e64e1fa2ecccfea4b4e6ce649ddae`
- Sofascore: https://www.sofascore.com/football/match/rayo-vallecano-espanyol/ogbstgb#id:16416345
  - provider: `sofascore-v1`; event: `16416345`
  - evidence: `snapshots/auto/sofascore-v1-16416345-0c69102d026f7808.json` — SHA-256 `0c69102d026f7808a7d6d397c905de01cd2b7d4d6a74adef9639b6f0039a361e`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
