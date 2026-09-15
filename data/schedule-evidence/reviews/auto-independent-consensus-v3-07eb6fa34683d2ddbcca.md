# Automated independent schedule consensus: Кальяри — Лечче

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202hotlg3t107l3co59q3`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202hotlg3t107l3co59q3-db7c1aca89f65e31.json` — SHA-256 `db7c1aca89f65e316bba44cfb11a7b68bf893fcab171e1cd47e0673ae551dfef`
- Sofascore: https://www.sofascore.com/football/match/cagliari-lecce/Odbsueb#id:16284997
  - provider: `sofascore-v1`; event: `16284997`
  - evidence: `snapshots/auto/sofascore-v1-16284997-9356e6eb5d358a23.json` — SHA-256 `9356e6eb5d358a23052f15bee18bc33b9c2e6961febd098e51aadf0f6996381a`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
