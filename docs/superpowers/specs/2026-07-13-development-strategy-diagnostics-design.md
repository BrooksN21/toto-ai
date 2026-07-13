# Development Strategy Diagnostics Design

## Goal

Add a read-only diagnostic command that explains why `weighted_coverage`
improves average best hits but does not currently beat `top_probability` on
13+ hits. The command must analyze only the frozen development segment and must
not change, rank, or select strategies.

## Command

```bash
python -m toto_ai.cli diagnose-strategies \
  --db data/toto.db \
  --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json \
  --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv
```

Bank, stake, category, drawing IDs, holdout size, and strategy configuration
come from the manifest. They are not accepted as independent overrides.

## Data Boundary

The manifest drawing order defines the chronological split. The command uses
only the first `last - holdout_size` drawing IDs. It must not load holdout events,
quotes, results, or CSV rows into the diagnostic calculation.

The command regenerates packages for development drawings because the frozen
CSV does not contain coupon strings. Before using a regenerated package, it
must compare its SHA-256 package hash with the corresponding frozen CSV row.
Any missing row, duplicate strategy row, unexpected strategy, or hash mismatch
fails the command. This preserves the original experiment despite running the
diagnostic from a later documentation/diagnostic commit.

Actual results are loaded only after all three packages for a development
drawing have been generated and hash-verified. Recomputed best-hit and 13/14/15
fields must also equal the frozen CSV values; disagreement fails closed.

## Drawing-Level Metrics

For each development drawing and strategy:

- best hits and nearest Hamming distance to the actual result
- hit13, hit14, and hit15
- package size and cost
- frozen estimated scenario coverage
- minimum, median, mean, and maximum coupon log probability
- mean pairwise Hamming distance within the package

For the `top_probability` versus `weighted_coverage` pair:

- best-hit difference
- package intersection size and Jaccard overlap
- mean log probability of coupons unique to each package
- whether neither, both, only top, or only weighted reached 13+

## Aggregate Report

The Markdown summary includes:

- complete best-hit distributions from 0 through 15
- paired weighted-versus-top wins, ties, and losses
- the four-cell paired 13+ transition table
- average and quantiles of best-hit differences
- average package overlap, coupon probability, and package diversity
- average estimated coverage and observed 13+ rate by strategy
- simple calibration tables that group frozen estimated coverage into fixed
  half-percentage-point bins from 0% through 5%, plus a 5%+ bin, and compare it
  with observed 13+ frequency

Difference quantiles are p25, p50, and p75. A mean unique-coupon probability is
reported as unavailable when the corresponding unique set is empty.

The report describes evidence but does not declare a strategy winner or propose
new optimizer parameters.

## Exports

- `reports/strategy_diagnostics_development_last_<N>_bank_<BANK>.csv`
- `reports/strategy_diagnostics_development_last_<N>_bank_<BANK>.md`

The CSV contains one row per development drawing with paired top/weighted
metrics and strategy-prefixed structural fields.

## Error Handling

Fail before writing final reports when:

- the manifest or frozen CSV is invalid
- the CSV does not exactly contain one row per strategy for every development
  drawing
- package hashes differ from the frozen experiment
- package generation times out or returns an invalid package set
- a development drawing no longer has complete eligible data

No partial report is treated as a valid diagnostic result.

## Testing

Tests must prove:

- holdout IDs are excluded before database loading and CSV selection
- package generation precedes development-result loading
- package hash mismatch fails closed
- duplicate or missing frozen rows fail closed
- paired transitions, distributions, overlap, probability, and diversity
  metrics are correct on deterministic fixtures
- report output is deterministic
- CLI help and a small end-to-end fixture work

Production strategy generation code remains unchanged.
