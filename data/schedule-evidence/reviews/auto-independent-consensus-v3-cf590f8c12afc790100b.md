# Automated independent schedule consensus: Андерлехт — Генк

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63intbf7qqt107adx5ih5t`
  - evidence: `snapshots/auto/goal-api-v1-cmt63intbf7qqt107adx5ih5t-16ed4591f1f1fb14.json` — SHA-256 `16ed4591f1f1fb14c46e042ac81b9a4453919173966fdbf464e85199f7e5a4e5`
- Sofascore: https://www.sofascore.com/football/match/rsc-anderlecht-krc-genk/Phbsaib#id:16361912
  - provider: `sofascore-v1`; event: `16361912`
  - evidence: `snapshots/auto/sofascore-v1-16361912-5de54e9b2a5874dc.json` — SHA-256 `5de54e9b2a5874dc01bef1be3f2417e4a960bacf18ee77e8482b87ad56a3ceaf`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
