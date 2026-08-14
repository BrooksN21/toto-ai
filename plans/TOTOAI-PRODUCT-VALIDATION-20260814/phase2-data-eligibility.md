# Phase 2 data-eligibility finding

Measured: 2026-08-14
Status: **BLOCKING CONSTRAINT RECORDED**

## Full database audit

The strict read-only health contract was run over the complete local database:

- drawings: 2,215;
- finished: 2,213;
- current active: 1;
- strict `historical_inventory` healthy: 398;
- `backtest_probability` healthy: 1,672;
- raw snapshot present: 484;
- result snapshot present: 410;
- complete BK rows: 2,215;
- valid pool rows: 2,000;
- duplicate visible numbers: 0;
- visible-number gaps: 3,843 and 3,844.

The last-100 audit has 78 strict historical-inventory healthy drawings and 79
probability-backtest eligible drawings. It contains 17 finished drawings with
an incomplete result, five zero-pool drawings, one unsettled package, and the
current active drawing 4975 with expected missing results.

Evidence:

- `reports/research/data-health-all-20260814/data_health_v1.{json,csv,md}`
- `reports/research/data-health-20260814/data_health_v1.{json,csv,md}`

## Consequence for the approved benchmark

The repository cannot honestly produce 500 or 1,000 **strict frozen-snapshot**
drawings today: only 398 satisfy the stronger historical inventory contract.
Missing old raw snapshots cannot be recreated retrospectively with a truthful
pre-deadline timestamp.

Phase 2 therefore has two explicitly separated evidence tiers:

1. **Strict frozen benchmark**
   - run 100 eligible drawings now;
   - optionally run the complete available strict set (currently 398);
   - use for the stronger historical claim, while still not claiming profit.
2. **Legacy probability diagnostic**
   - run 500 and 1,000 `backtest_probability`-eligible drawings;
   - database rows are hash-frozen at experiment time, but many lack original
     raw/result snapshot chronology;
   - label every artifact `LEGACY_RETROSPECTIVE / NOT RELEASE EVIDENCE`;
   - use only to detect large strategy weaknesses and instability.

The prospective holdout gate is unchanged. Only packages frozen before future
deadlines may contribute to prospective release evidence.

## Follow-up

- Determine whether visible numbers 3,843 and 3,844 are genuinely missing
  drawings or intentional numbering gaps in the upstream source.
- Continue bounded reconciliation for incomplete finished drawings; never
  invent a result for postponed/cancelled events.
- Exclude zero-pool and incomplete-result rows from probability/package
  backtests and publish exact exclusion counts.
- Settle the drawing-4959 actionable package before using it for settlement
  metrics.
