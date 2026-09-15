# Automated independent schedule consensus: Алавес — Осасуна

Reviewed at **2026-09-06T09:17:39.179335Z**.
Scheduled kickoff: **2026-09-06T16:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt63inrpf7q6t107wh9n01ls`
  - evidence: `snapshots/auto/goal-api-v1-cmt63inrpf7q6t107wh9n01ls-1ee00165b991bccf.json` — SHA-256 `1ee00165b991bccf8cadff55cddf1434779662a6de21b7cb664fcffd9de0ad4b`
- Sofascore: https://www.sofascore.com/football/match/deportivo-alaves-osasuna/vgbsKhb#id:16416318
  - provider: `sofascore-v1`; event: `16416318`
  - evidence: `snapshots/auto/sofascore-v1-16416318-a52140a703b1c249.json` — SHA-256 `a52140a703b1c249e5d89cfe4e5e9d5e215e63c9b32748ca8aeba3ef53039bb2`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
