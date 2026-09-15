# Automated independent schedule consensus: Бернли — Мидлсбро

Reviewed at **2026-09-01T14:06:31.613708Z**.
Scheduled kickoff: **2026-09-02T19:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fifry79e1pd07emkae96w`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fifry79e1pd07emkae96w-87dd9832f88e878c.json` — SHA-256 `87dd9832f88e878caf7c039119731904e330192254f38c0edad880bc05cf056b`
- Sofascore: https://www.sofascore.com/football/match/middlesbrough-burnley/gsL#id:16391641
  - provider: `sofascore-v1`; event: `16391641`
  - evidence: `snapshots/auto/sofascore-v1-16391641-7037060239074a6c.json` — SHA-256 `7037060239074a6c73e4f6653e7afbf3d7764bc5ec1edc1c7b7667335c86c718`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
