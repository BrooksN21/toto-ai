# Automated independent schedule consensus: Сабадель — Кордоба

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T18:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202tdtlk6t107x75swkpa`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202tdtlk6t107x75swkpa-0821147bda96b2f0.json` — SHA-256 `0821147bda96b2f0a83bf1db52698219edd463cf7f227d96956e8e0b35ac1a78`
- Sofascore: https://www.sofascore.com/football/match/ce-sabadell-cordoba/ahbsKLj#id:16418278
  - provider: `sofascore-v1`; event: `16418278`
  - evidence: `snapshots/auto/sofascore-v1-16418278-06412fc5d3856b44.json` — SHA-256 `06412fc5d3856b445455a1a6349572ea1adbcbd2d60c52e4410f0401dc5ac4d2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
