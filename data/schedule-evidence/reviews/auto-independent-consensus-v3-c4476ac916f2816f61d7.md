# Automated independent schedule consensus: Эшторил — Арока

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T19:15:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63ij3pf6evt107grizcc2q`
  - evidence: `snapshots/auto/goal-api-v1-cmt63ij3pf6evt107grizcc2q-c3ca516f43b36a2b.json` — SHA-256 `c3ca516f43b36a2b3b53bea96b93221e5cdcfb20ad887007c1c316593a96ec7b`
- Sofascore: https://www.sofascore.com/football/match/fc-arouca-estoril-praia/aPbsCpk#id:16450882
  - provider: `sofascore-v1`; event: `16450882`
  - evidence: `snapshots/auto/sofascore-v1-16450882-8cc3190852ef860d.json` — SHA-256 `8cc3190852ef860da2bb4eba80bf2b503bdc1db27ed862eb4ef54275605bcb72`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
