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

## Exact-generator event attribution, 4990-4992

The equal-bank historical replay now emits event-level attribution from the
same immutable final inputs and exact package generator. Results:

- BK top outcome correct: 21/45 events;
- Sports v2 top outcome correct: 20/45 events;
- Sports-v2 evidence coverage: 29/45 events;
- realized-outcome probability raised: 14/29 covered events;
- realized-outcome probability lowered: 15/29 covered events;
- no compared package reached 13+.

This sample is too small for a profitability conclusion, but it rejects
activation of the current v2 candidate. The next iteration must improve the
probability model through chronological walk-forward calibration before any
further package rearrangement is treated as a primary improvement.
