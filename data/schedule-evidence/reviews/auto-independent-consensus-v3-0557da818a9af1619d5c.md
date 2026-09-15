# Automated independent schedule consensus: Волунтари — ФК Арджеш

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T14:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt7202fftlf2t107nzlm5fp1`
  - evidence: `snapshots/auto/goal-api-v1-cmt7202fftlf2t107nzlm5fp1-238c2b9a3833d72c.json` — SHA-256 `238c2b9a3833d72c4da11a01b02bd4e21a31b715baa9ecf6fa194e53559c1acd`
- Sofascore: https://www.sofascore.com/football/match/fc-arges-pitesti-fc-voluntari/fKrswzW#id:16403875
  - provider: `sofascore-v1`; event: `16403875`
  - evidence: `snapshots/auto/sofascore-v1-16403875-8fc1d08512ee678f.json` — SHA-256 `8fc1d08512ee678f607d89495c60ac8f6f5425b8be323f5d5159057ee2f7a653`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
