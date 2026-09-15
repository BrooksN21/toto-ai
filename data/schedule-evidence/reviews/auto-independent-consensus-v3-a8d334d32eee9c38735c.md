# Automated independent schedule consensus: Болонья — Сассуоло

Reviewed at **2026-09-06T08:50:58.811679Z**.
Scheduled kickoff: **2026-09-06T16:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/sassuolo-bologna/KdbsTfb#id:16284978
  - provider: `sofascore-v1`; event: `16284978`
  - evidence: `snapshots/auto/sofascore-v1-16284978-b558b71baed7ac8c.json` — SHA-256 `b558b71baed7ac8c325f70d9bc6e742258aa4905eee342f58d264680b7556b52`
- TheSportsDB: https://www.thesportsdb.com/event/2482163
  - provider: `thesportsdb-v1`; event: `2482163`
  - evidence: `snapshots/auto/thesportsdb-v1-2482163-13bf531d31627e05.json` — SHA-256 `13bf531d31627e058750b857196537d44fa45b6326cafb453876f925c520fde8`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
