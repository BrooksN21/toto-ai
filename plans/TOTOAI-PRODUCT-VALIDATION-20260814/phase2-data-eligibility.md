# Phase 2 data-eligibility finding

Measured: 2026-08-14
Status: **CHRONOLOGY DEFECT CORRECTED / BLOCKING CONSTRAINT RECORDED**

## Strict benchmark result

The strict canary completed first on one and then three drawings. The complete
available strict run then evaluated all 13 eligible drawings with zero strategy
timeouts at bank/stake 4,980/30. Average best hits were EV/crowd 7.00, BK-only
9.00, Cover-13 8.46 and Cover-14 9.08. Cover-14 produced one 13+ result; no
strategy produced 14+ or 15. Cover-13 and Cover-14 spent only 660 and 2,700 on
average, so those variants are not equal-cost to the two 4,980 packages.

These numbers expose a large current EV-vs-BK diagnostic gap and prove the
strict runner works, but 13 drawings are too few for a winner or profitability
claim. The report remains
`STRICT_CHRONOLOGICAL_PIPELINE_EVIDENCE / NOT RELEASE EVIDENCE` at
`reports/research/strict-strategy-benchmark-20260814-all13/`.

## Full database audit

The strict read-only health contract was run over the complete local database:

- drawings: 2,216;
- finished: 2,214;
- current active: 1;
- strict chronological `historical_inventory` healthy: 13;
- `backtest_probability` healthy: 1,672;
- raw snapshot present: 485;
- drawings with a usable pre-deadline raw snapshot: 17;
- result snapshot present: 410;
- complete BK rows: 2,215;
- valid pool rows: 2,000;
- duplicate visible numbers: 0;
- visible-number gaps: 3,843 and 3,844. The upstream TotoBrief results listing
  itself skips from 3,842 to 3,845, so this is an upstream numbering gap, not a
  local ingestion loss.

The last-100 audit has 78 strict historical-inventory healthy drawings and 79
probability-backtest eligible drawings. It contains 17 finished drawings with
an incomplete result, five zero-pool drawings, one unsettled package, and the
current active drawing 4975 with expected missing results.

Evidence:

- `reports/research/data-health-all-20260814/data_health_v1.{json,csv,md}`
- `reports/research/data-health-20260814/data_health_v1.{json,csv,md}`

## Consequence for the approved benchmark

The first audit counted any raw snapshot as frozen evidence. A chronology audit
found that only 17 drawings have a raw snapshot captured at or before the
deadline and only 13 of those also have complete terminal results and the other
strict inputs. The other 385 previously reported `historical_inventory` rows
had only post-deadline raw snapshots. Contract version 1.2.0 now fails closed on
`missing_predeadline_raw_snapshot` and records the eligible count/timestamp.

The repository therefore cannot honestly produce a 100-drawing strict frozen
benchmark today. Missing historical pre-deadline snapshots cannot be recreated
retrospectively.

Phase 2 therefore has two explicitly separated evidence tiers:

1. **Strict chronological canary**
   - run 3–5 drawings first, then all currently eligible drawings (13);
   - use only as pipeline correctness evidence, not as a strategy verdict;
   - grow this tier only from genuinely pre-deadline future snapshots.
2. **Legacy probability diagnostic**
   - run 100, 500 and 1,000 `backtest_probability`-eligible drawings;
   - database rows are hash-frozen at experiment time, but many lack original
     raw/result snapshot chronology;
   - label every artifact `LEGACY_RETROSPECTIVE / NOT RELEASE EVIDENCE`;
   - use only to detect large strategy weaknesses and instability.

The prospective holdout gate is unchanged and is now the primary release
evidence path. Only packages frozen before future deadlines may contribute.

## Follow-up

- Add hash-bound upstream-gap evidence for visible numbers 3,843 and 3,844 so
  the health contract can distinguish a documented upstream numbering gap from
  a local ingestion loss. Public evidence:
  <https://totobrief.com/results/bbet?page=11>.
- Continue bounded reconciliation for incomplete finished drawings; never
  invent a result for postponed/cancelled events.
- Exclude zero-pool and incomplete-result rows from probability/package
  backtests and publish exact exclusion counts.
- Settle the drawing-4959 actionable package before using it for settlement
  metrics.
