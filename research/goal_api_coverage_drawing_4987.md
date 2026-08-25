# GOAL API coverage canary — drawing 4987

Date: 2026-08-25. Candidate-only research; no scheduler, ledger, probability,
package or wager path was authorized.

## Target and transport

- TotoBrief visible drawing: 4987; internal ID: 12068.
- Local detail synchronization: 15/15 events.
- TotoBrief `ended_at`: `2026-08-26T18:45:00Z`.
- GOAL endpoint: documented paginated `GET /v1/fixtures/date/:date`.
- Requests: 37 across the bounded six-date window.
- Final observed quota: 883/1,000 daily requests.
- Stable explicit TotoAI user agent used; the bearer key was not persisted.

## Coverage

All fifteen TotoBrief pairs exist in the frozen GOAL fixture responses and the
candidate matcher resolves **15/15**. Exact/reviewed matching resolves eight;
the deterministic cross-script candidate lane resolves seven naming variants,
including `Bradford City`, `Atletico Atlanta`, `El Gaish`,
`National Bank Egypt`, `Al Shabab`, `Asane` and `Al-Faisaly`.

This fuzzy lane is discovery-only. Its records remain
`ledger_eligible=false` and require an official source plus review.

## Blocking timing finding

Only events 1 and 2 start after TotoBrief `ended_at`; event 3 starts exactly at
it. Events 4 through 15 start between 15:45Z and 18:30Z, before that value.
Therefore the collector reports:

- matched identities: 15/15;
- ordinary independent candidates: 3/15;
- `timing_conflict`: 12/15.

The conflict must not be interpreted as permission to move the betting
deadline. It shows either that `ended_at` has different semantics for this
drawing or one source carries incorrect timing. Until independently resolved,
4987 is not scheduler-ready and no package should be authorized from this
canary.

An independent Sofascore search cross-check reproduced the exact GOAL kickoff
for five representative fixtures spanning the window: Viking—Dinamo Zagreb,
Bradford City—Burnley, Acassuso—San Telmo, National Bank of Egypt—Zamalek and
Al Faisaly—Al-Fateh. This makes a GOAL-only clock error unlikely, but does not
establish the operational semantics of TotoBrief `ended_at`.

The current official BaltBet rules resolve the operational side: a
`Балтсистема` wager must be placed before the earliest event in its event set.
Therefore the conservative acceptance boundary for 4987 is no later than the
independently confirmed earliest kickoff `2026-08-26T15:45:00Z`
(`18:45 MSK`), and T-10 is `18:35 MSK`. TotoBrief `ended_at` cannot be used as
the betting cutoff for this drawing.

Official rule source:

`https://cdndocs.baltbet.ru/uni/docs/sd_GameRules.pdf?v5=`

Machine-readable replay report:

`reports/canary/goal-api-4987/output-v3/schedule-source-candidates.json`

## Next evidence

1. Add a scheduler-owned conservative cutoff that can only move the TotoBrief
   timestamp earlier, based on independently confirmed earliest kickoff.
2. Keep the drawing fail-closed whenever the earliest kickoff is unresolved or
   sources disagree.
3. Continue the predeclared ten-consecutive-drawing bake-off; one 15/15 source
   observation does not prove permanent coverage or profitability.
