# Automated independent schedule consensus: Богемианс 1905 — Яблонец

Reviewed at **2026-09-01T14:20:18.647316Z**.
Scheduled kickoff: **2026-09-02T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmsl1gmg0shx7oe07dhr3kmkd`
  - evidence: `snapshots/auto/goal-api-v1-cmsl1gmg0shx7oe07dhr3kmkd-1c5913e4209192b1.json` — SHA-256 `1c5913e4209192b197f9ace982221c5c6507226844b6c55b93bf2f6aef38adf5`
- Sofascore: https://www.sofascore.com/football/match/bohemians-praha-1905-fk-jablonec/fUsowc#id:16831437
  - provider: `sofascore-v1`; event: `16831437`
  - evidence: `snapshots/auto/sofascore-v1-16831437-47dfe6d8f36a79bc.json` — SHA-256 `47dfe6d8f36a79bc96e79a6bc67cad0501a904ec2cce9455c6acff7fee703cb8`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
