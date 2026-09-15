# Automated independent schedule consensus: Либертад Лоха — Эмелек

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-04T00:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71z7awtdtkt107n3mgjsx3`
  - evidence: `snapshots/auto/goal-api-v1-cmt71z7awtdtkt107n3mgjsx3-b348f3e2cc75dc0b.json` — SHA-256 `b348f3e2cc75dc0b6df99debf063b1302de486f560cf08db8cb10d8ac45e6961`
- Sofascore: https://www.sofascore.com/football/match/libertad-emelec/ffcsCHhd#id:15502669
  - provider: `sofascore-v1`; event: `15502669`
  - evidence: `snapshots/auto/sofascore-v1-15502669-bc4f9ad7cd15fa97.json` — SHA-256 `bc4f9ad7cd15fa97214f93d11795f7bb650cd84a04350f2b40b9612f312ca7e0`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
