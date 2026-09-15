# Automated independent schedule consensus: Уиган Атлетик — Милтон Кинс Донс

Reviewed at **2026-09-01T14:06:31.613708Z**.
Scheduled kickoff: **2026-09-02T18:45:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- Sofascore: https://www.sofascore.com/football/match/wigan-athletic-milton-keynes-dons/esZ#id:16872396
  - provider: `sofascore-v1`; event: `16872396`
  - evidence: `snapshots/auto/sofascore-v1-16872396-bbce23abb15a555c.json` — SHA-256 `bbce23abb15a555c40895266ec30a03eb4786fbc64eb865ed0bcd729fb80ed57`
- TheSportsDB: https://www.thesportsdb.com/event/2500735
  - provider: `thesportsdb-v1`; event: `2500735`
  - evidence: `snapshots/auto/thesportsdb-v1-2500735-ee0af95e6daac41a.json` — SHA-256 `ee0af95e6daac41a67428cf905d8b9a319560d05ab40bf0c8007402ef1aa85d9`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
