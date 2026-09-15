# Automated independent schedule consensus: Базель — Сьон

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T18:30:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fijbc79uqpd07w6weeioo`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fijbc79uqpd07w6weeioo-c16ed1c3de323659.json` — SHA-256 `c16ed1c3de32365962c9c7a8889f24f3a0cc66d963172c8605e821b3ae739be2`
- Sofascore: https://www.sofascore.com/football/match/basel-fc-sion/cZsbab#id:16357077
  - provider: `sofascore-v1`; event: `16357077`
  - evidence: `snapshots/auto/sofascore-v1-16357077-941b340c4790e22c.json` — SHA-256 `941b340c4790e22c65f6d98d382b6872dfa3c21c188d46f35e87d49b55b5ac34`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
