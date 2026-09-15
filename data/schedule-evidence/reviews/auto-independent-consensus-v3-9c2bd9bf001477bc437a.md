# Automated independent schedule consensus: Фортуна Кельн — Веен

Reviewed at **2026-09-15T17:16:02.294119Z**.
Scheduled kickoff: **2026-09-16T17:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt71qwdusqtst107yhu2szq6`
  - evidence: `snapshots/auto/goal-api-v1-cmt71qwdusqtst107yhu2szq6-f8947cf64bd22862.json` — SHA-256 `f8947cf64bd228623c791f05695d1b9f489ee7b4c88e271f60d082ab6ecc70c9`
- Sofascore: https://www.sofascore.com/football/match/sc-fortuna-koln-sv-wehen-wiesbaden/XbbsIdb#id:16596628
  - provider: `sofascore-v1`; event: `16596628`
  - evidence: `snapshots/auto/sofascore-v1-16596628-97d5496654aee4eb.json` — SHA-256 `97d5496654aee4eb6eb0c13472db0e753268b829daf9d1b944ec0cf07a283cba`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
