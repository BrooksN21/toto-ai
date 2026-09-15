# Automated independent schedule consensus: Новара — Ливорно

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T18:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fi7f978n9pd0799dbqq3h`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fi7f978n9pd0799dbqq3h-1205fb5cb0854292.json` — SHA-256 `1205fb5cb0854292d20d93bae715e236403557d20f87340a10d97694aef45df8`
- Sofascore: https://www.sofascore.com/football/match/novara-us-livorno-1915/Bebsrfb#id:16866635
  - provider: `sofascore-v1`; event: `16866635`
  - evidence: `snapshots/auto/sofascore-v1-16866635-e67b0dafe11f5d70.json` — SHA-256 `e67b0dafe11f5d706a55c52496a1b58194625235fd8c9e832d4ca23efb012bea`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
