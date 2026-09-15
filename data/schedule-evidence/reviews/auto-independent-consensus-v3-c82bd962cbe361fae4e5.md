# Automated independent schedule consensus: Интер Турку — КуПС

Reviewed at **2026-08-30T14:57:53.777899Z**.
Scheduled kickoff: **2026-08-31T16:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmt1fhrpf76s1pd07l8i6qx2s`
  - evidence: `snapshots/auto/goal-api-v1-cmt1fhrpf76s1pd07l8i6qx2s-d106f99c8d0033e4.json` — SHA-256 `d106f99c8d0033e46681f5dc391ba536bf365887af6bca10a75f4a35bb564344`
- TheSportsDB: https://www.thesportsdb.com/event/2405336
  - provider: `thesportsdb-v1`; event: `2405336`
  - evidence: `snapshots/auto/thesportsdb-v1-2405336-2bdbfb8d5800956f.json` — SHA-256 `2bdbfb8d5800956fbf69af68fa36620c8fe0904c2912f0e28f9d3480788bbdbc`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
