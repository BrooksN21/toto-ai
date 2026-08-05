# Hybrid Direct Package Experiment Design

## Background

The frozen Direct Package Optimizer experiment showed that `weighted_coverage`
usually improves the nearest coupon but does not improve the observed 13+ rate
over `top_probability`. Development diagnostics identified the structural
trade-off:

- top probability average pairwise Hamming distance: 3.491
- weighted coverage average pairwise Hamming distance: 7.496
- top probability mean coupon log probability: -13.682
- weighted coverage mean coupon log probability: -14.729

The hybrid experiment tests whether retaining a fixed high-probability core and
using weighted coverage only for the remaining package capacity improves 13+
without tuning against the frozen holdout.

## Goal

Select at most one hybrid core fraction on the frozen 350-drawing development
segment. The primary objective is 13+ hit count at bank 5000 RUB, stake 30 RUB,
and category 13.

This experiment does not optimize payout or ROI, does not use external odds,
and does not establish profitability. A passing candidate is only eligible for
a later prospective evaluation.

## Fixed Experiment Configuration

All strategy settings, drawing IDs, chronological order, and development split
come from the existing frozen manifest. The experiment adds only these fixed
core fractions:

```text
0.50, 0.75, 0.90
```

They are protocol constants, not CLI tuning options. With 166 available
coupons, core size is `ceil(max_coupons * core_fraction)`:

| Core fraction | Core coupons | Weighted-fill coupons |
| --- | ---: | ---: |
| 0.50 | 83 | 83 |
| 0.75 | 125 | 41 |
| 0.90 | 150 | 16 |

## Hybrid Package Selection

For one drawing:

1. Build the exact top-probability coupon ordering with the existing normalized
   BK probability matrix.
2. Copy the first `core_size` coupons into the package.
3. Generate the existing deterministic weighted candidate set and optimization
   scenarios once for the drawing.
4. Mark every optimization scenario covered by the core as already covered.
5. Fill the remaining capacity by the existing marginal weighted-coverage
   rule, excluding coupons already in the core.
6. Keep the existing deterministic tie-break: marginal scenario weight, coupon
   log probability, then coupon string.

The three fractions reuse the same candidates and scenarios but have isolated
selection state. Every completed package contains exactly `max_coupons` unique
coupons unless the drawing fails closed. Existing `top_probability` and
`weighted_coverage` behavior remains unchanged.

## Development Evaluation Command

```bash
python -m toto_ai.cli evaluate-hybrid \
  --db data/toto.db \
  --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json \
  --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv
```

The command accepts no bank, stake, category, fold-count, core-fraction, seed,
or optimizer overrides. It opens the existing SQLite database in enforced
read-only mode.

## Data Boundary and Evaluation Order

Only the first `last - holdout_size` IDs from the manifest are available to the
experiment. Holdout CSV rows, events, quotes, and results are never loaded.

For every development drawing, execution order is:

1. Load pre-drawing events, quotes, and BK probabilities without event results.
2. Regenerate the frozen top-probability package.
3. Generate all three hybrid packages.
4. Validate package names, lengths, uniqueness, budget, and timeout state.
5. Verify the regenerated top package SHA-256 against the frozen development
   CSV row.
6. Only then load the actual development result.
7. Recompute and verify frozen top best-hit and 13/14/15 fields.
8. Score all hybrid packages.

Any failure occurs before final reports are written.

## Chronological Stability Check

The 350 development drawings are kept in manifest order and divided into five
contiguous folds of exactly 70 drawings. The implementation rejects a manifest
whose development count cannot be divided equally into five folds.

For `top_probability` and every hybrid fraction, report:

- total and per-fold 13+/14+/15 counts
- total and per-fold average best hits
- package cost and size
- package mean coupon log probability
- package mean pairwise Hamming distance
- top/hybrid intersection and Jaccard overlap
- runtime and timeout state

## GO/STOP Rule

A hybrid fraction passes only when all conditions hold:

1. Its total development 13+ count is at least the top-probability count plus
   two.
2. Its per-fold 13+ count is not below top probability in at least four of five
   folds.
3. Its total average best hits is not below top probability.
4. No evaluated drawing is skipped, invalid, or timed out.

If no fraction passes, the result is `STOP`; no fraction is selected and direct
package optimizer tuning ends. The next project direction becomes external
probability data, pool behavior, and payout/ROI modeling.

If multiple fractions pass, select one deterministically by:

1. higher total 13+ count
2. more folds with strictly higher 13+ count than top probability
3. more folds not below top probability
4. higher total average best hits
5. higher average package mean coupon log probability
6. larger core fraction

A `GO` result means only that the selected fraction may be frozen for a new
prospective evaluation. It is not a proven winner and the old holdout is not
reused.

## Reports

Exports:

- `reports/hybrid_evaluation_development_last_<N>_bank_<BANK>.csv`
- `reports/hybrid_evaluation_development_last_<N>_bank_<BANK>.md`

The CSV contains one row per development drawing and evaluated strategy. The
Markdown report contains configuration, fold tables, aggregate comparisons,
package structure metrics, failure counts, the GO/STOP rule evaluation, and an
explicit development-only disclaimer.

Generated hybrid reports are ignored by Git.

## Error Handling

Fail without a valid final report when:

- manifest or frozen CSV validation fails
- development IDs are duplicated or not divisible into five equal folds
- a holdout ID reaches any database loader
- the top package hash or frozen result fields differ
- any package is duplicated, malformed, over budget, incomplete, or timed out
- required pre-drawing data or a development result is incomplete
- report output cannot be written atomically

## Testing

Tests must prove:

- core sizes use ceiling and equal 83, 125, and 150 for 166 coupons
- core coupons are the exact top-probability prefix
- weighted fill accounts for scenarios already covered by the core
- packages are unique, deterministic, complete, and within budget
- existing weighted and top selectors remain byte-for-byte unchanged
- candidates and scenarios are reused across fractions without shared mutable
  selection state
- holdout IDs never reach input or result loaders
- top hash verification precedes result loading
- five chronological folds are exact and deterministic
- every GO condition and deterministic tie-break is covered
- STOP selects no fraction
- CLI uses a read-only database and exports deterministic reports

## Scope Control

This task adds one hybrid selector and one development evaluator. It does not
add ML, new candidate generators, external providers, payout estimation,
automatic betting, or more core fractions.
