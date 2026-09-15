# Automated independent schedule consensus: Райо Вальекано — Расинг Сантандер

Reviewed at **2026-09-04T20:05:36.416599Z**.
Scheduled kickoff: **2026-09-05T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63iszcf95tt107gqhayhcf`
  - evidence: `snapshots/auto/goal-api-v1-cmt63iszcf95tt107gqhayhcf-5d3509fb022b131c.json` — SHA-256 `5d3509fb022b131cb514c08001dfde00969cc8336ec41cf9d0a2ace7f962f711`
- Sofascore: https://www.sofascore.com/football/match/real-racing-club-rayo-vallecano/tgbsKgb#id:16416321
  - provider: `sofascore-v1`; event: `16416321`
  - evidence: `snapshots/auto/sofascore-v1-16416321-c25bb0e93d74a283.json` — SHA-256 `c25bb0e93d74a283748cd2b7ba2162ebc0b0b9e194db7935005ab6e27974b1ec`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
