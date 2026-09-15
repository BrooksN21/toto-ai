# Automated independent schedule consensus: Хетафе — Сельта

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202ritljat107sdtqn9k9`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202ritljat107sdtqn9k9-de39e62a0c7001c4.json` — SHA-256 `de39e62a0c7001c414988f1ce9bf86ad4d887473bb15318a50f105749031f6d3`
- Sofascore: https://www.sofascore.com/football/match/getafe-celta-vigo/wgbsjhb#id:16416348
  - provider: `sofascore-v1`; event: `16416348`
  - evidence: `snapshots/auto/sofascore-v1-16416348-618cd26875d5f067.json` — SHA-256 `618cd26875d5f0673f7cbbdce0ea59477ae42d58fbcb102219c7fe9c40164caf`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
