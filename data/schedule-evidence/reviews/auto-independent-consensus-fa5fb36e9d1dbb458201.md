# Automated independent schedule consensus: Аль Шабаб Ахмади — Аль Джахра

Reviewed at **2026-08-26T08:45:21.282766Z** for drawing 4987, event #11.

Scheduled kickoff: **2026-08-26T15:45:00Z**.

GOAL API and a separately fetched Sofascore event agree on canonical home/away identities and exactly on UTC kickoff. This evidence is used only for schedule timing and does not alter probabilities.

- GOAL API: https://goal-api.com/#fixture-cmsxwg9epf4lvqg079lwojgpy
- Sofascore: https://www.sofascore.com/football/match/al-shabab-sc-al-jahra-sc/VBwsudx#id:16796336
- GOAL matcher mode: `fuzzy_candidate_margin_0.280`
- Sofascore event ID: `16796336`

## Frozen snapshots

- `snapshots/auto/goal-candidate-cmsxwg9epf4lvqg079lwojgpy-ffbff1f05c46ce95.json` — SHA-256 `ffbff1f05c46ce958a65b82ebfc0e21681d895924edb74a4e86d86ea728d05c6`
- `snapshots/auto/sofascore-search-cmsxwg9epf4lvqg079lwojgpy-5b99879582d4e9bf.json` — SHA-256 `5b99879582d4e9bf8fdc52ef175a036fe34837a5bd985f2778d3104c4b72c059`
- `snapshots/auto/sofascore-16796336-3b25c657dfe8d568.json` — SHA-256 `3b25c657dfe8d5689662ee9f2fc2326ab88629646f2e5533b07266a06fe0515e`

Conflicting, ambiguous, started, or late evidence remains fail-closed.
