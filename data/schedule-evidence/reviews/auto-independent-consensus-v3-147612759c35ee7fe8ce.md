# Automated independent schedule consensus: Вальядолид — Андорра ФК

Reviewed at **2026-09-04T20:05:36.416599Z**.
Scheduled kickoff: **2026-09-05T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63it0xf961t107qqdcj6ue`
  - evidence: `snapshots/auto/goal-api-v1-cmt63it0xf961t107qqdcj6ue-4f051df113baffd4.json` — SHA-256 `4f051df113baffd4e5bb35634a810eeb1d375c54e47e369cf4a4d995a2ca9e66`
- Sofascore: https://www.sofascore.com/football/match/fc-andorra-real-valladolid/GgbswXEc#id:16418282
  - provider: `sofascore-v1`; event: `16418282`
  - evidence: `snapshots/auto/sofascore-v1-16418282-8f7892d8c43129bc.json` — SHA-256 `8f7892d8c43129bcf0adaa35df996abc914bc312f5405b0642d51e5450949006`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
