# Automated independent schedule consensus: Ракув — Гурник Забрже

Reviewed at **2026-09-02T14:13:46.197215Z**.
Scheduled kickoff: **2026-09-03T16:00:00Z**.

Two allowlisted independent providers match exact home/away 
orientation, acceptable pre-kickoff status and UTC kickoff within 
tolerance.

- GOAL API: https://goal-api.com
  - provider: `goal-api-v1`; event: `cmsp4mbpiu2hzpn06s3xrv2ii`
  - evidence: `snapshots/auto/goal-api-v1-cmsp4mbpiu2hzpn06s3xrv2ii-12f346e2b9efc031.json` — SHA-256 `12f346e2b9efc031648ebd3bdf30c8cc5cea40bee056f32a0db5e649c307520e`
- Sofascore: https://www.sofascore.com/football/match/rakow-czestochowa-gornik-zabrze/kmbstfo#id:16316984
  - provider: `sofascore-v1`; event: `16316984`
  - evidence: `snapshots/auto/sofascore-v1-16316984-86ff256a1fa1cb97.json` — SHA-256 `86ff256a1fa1cb97ff3157aee9068d24eac51f59bc0d2a0d1bdce4b004764cc5`

Single-source, fuzzy, reversed, ambiguous, late, started or 
conflicting evidence remains fail-closed.
