# Automated independent schedule consensus: Хапоэль Тель-Авив — Бейтар Иерусалим

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T17:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmsp4mdgiu2v4pn06dt69pin9`
  - evidence: `snapshots/auto/goal-api-v1-cmsp4mdgiu2v4pn06dt69pin9-d81b0c03055e516f.json` — SHA-256 `d81b0c03055e516f264c2fbd2ed078882911e64062bb29492041f53ba5907617`
- Sofascore: https://www.sofascore.com/football/match/hapoel-tel-aviv-beitar-jerusalem/eecsWhc#id:16364301
  - provider: `sofascore-v1`; event: `16364301`
  - evidence: `snapshots/auto/sofascore-v1-16364301-cf9c983cad4b8187.json` — SHA-256 `cf9c983cad4b818717a0bb38035533f47b5f753d2e39962d568a83c4f6389acb`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
