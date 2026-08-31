# Sports Analytics v2

Status: research-only, not activated for operator packages.

## Goal

Use pre-match sports evidence as a bounded residual correction to bookmaker
probabilities. The market remains the anchor. A missing or weak sports event
falls back locally to the exact BK row and never blocks the 15-match package.

## First implementation

`sports-analytics-v2-poisson-venue-shrunk-v1` combines:

- home-team home W/D/L and away-team away W/D/L;
- venue goals scored/conceded with team-level empirical priors;
- an independent-Poisson W/D/L projection;
- sample-size confidence;
- disagreement shrinkage when sports and BK strongly disagree;
- a hard sports blend cap of 20%.

The implementation is in `src/toto_ai/sports_stats/v2.py`.

## Activation gate

Do not activate from one drawing. Required evidence:

1. immutable pre-match `as_of` inputs only;
2. chronological walk-forward comparison against unchanged BK;
3. no worse multiclass log loss, Brier score, or calibration beyond declared
   tolerances;
4. package-level P13/P14/P15 comparison under equal bank and coupon count;
5. no degradation of package safety/concentration;
6. prospective settlement on at least the declared release sample.

Until that gate passes, v2 may produce diagnostics and shadow packages only.
