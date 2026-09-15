# Automated independent schedule consensus: ОФК Белград — ИМТ Нови Белграде

Reviewed at **2026-09-06T15:51:04.946467Z**.
Scheduled kickoff: **2026-09-07T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63irehf8uyt107yqwo2ztn`
  - evidence: `snapshots/auto/goal-api-v1-cmt63irehf8uyt107yqwo2ztn-d003f1ecab1717fa.json` — SHA-256 `d003f1ecab1717fa7a59ed223d01244fda0c80c00323e9dd2624ba207fa04a9c`
- Sofascore: https://www.sofascore.com/football/match/fk-imt-beograd-ofk-beograd/ddcsBnyc#id:16326443
  - provider: `sofascore-v1`; event: `16326443`
  - evidence: `snapshots/auto/sofascore-v1-16326443-10f5a1353f62dafa.json` — SHA-256 `10f5a1353f62dafa86ffed7402794695789cd015342b5baeeb0c65eb9093884e`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
