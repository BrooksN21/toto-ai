# Automated independent schedule consensus: Депортиво Ла-Корунья — Севилья

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qvmesqlbt1071sbm3p1s`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qvmesqlbt1071sbm3p1s-ebb52a293319f4bc.json` — SHA-256 `ebb52a293319f4bca659810b3e68f96131875365cc039334476e9ffc464581ba`
- Sofascore: https://www.sofascore.com/football/match/sevilla-deportivo-de-la-coruna/HgbsIgb#id:16416343
  - provider: `sofascore-v1`; event: `16416343`
  - evidence: `snapshots/auto/sofascore-v1-16416343-68a6f8ad2daad744.json` — SHA-256 `68a6f8ad2daad744958a3c83f72a3350e2d3ab3d685f523b21d4816729402ed9`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
