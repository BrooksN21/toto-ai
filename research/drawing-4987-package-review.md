# Drawing 4987 package review

Date reviewed: 2026-08-27.

## Evidence

- Drawing: BaltBet 4987, internal ID 12068, finished with 15 resolved events.
- Actual result: `1 X X 2 1 1 1 2 2 2 1 2 X 2 X`.
- Frozen package timestamp: 2026-08-26 10:00:18 UTC (13:00:18 MSK).
- Both inputs contain 166 unique research coupons at a nominal 30 RUB stake
  (4,980 RUB each).
- The files are explicitly `PAPER_ONLY_NOT_ACTIVATED`; they were not terminal
  scheduler/operator packages.
- Frozen file hashes match their manifest.

## Result

| Package | Best coupon | Mean hits | Median hits | 13+ | 14+ | 15 |
|---|---:|---:|---:|---:|---:|---:|
| BK baseline | 7/15 | 4.5602 | 5 | 0 | 0 | 0 |
| GOAL sports shadow | 5/15 | 3.3735 | 3 | 0 | 0 | 0 |

The two packages overlap on five coupons. Their union contains 327 unique
coupons, but its best result is still only 7/15. Neither package reached even
9 correct outcomes, so this comparison produced no winning category.

## Critical misses

The actual outcome had zero representation in these events:

- baseline: events 5, 9, 11 and 15;
- sports shadow: events 5, 8, 9 and 11.

Several other actual outcomes received negligible representation. Baseline
used the actual outcome only once in event 8 and twice in event 10. Sports
shadow used it once in events 3 and 15, twice in event 10, and three times in
events 7 and 14.

This concentration made a high-category result impossible once a few locked
or nearly locked outcomes failed. In particular, both packages selected `1`
in all 166 coupons for event 9, while the result was `2`, and selected `2` in
all 166 coupons for event 11, while the result was `1`.

## Sports-shadow assessment

The sports candidate was experimental and untrained. It changed several event
probabilities materially despite a low blend weight. Harmful examples include:

- event 3: actual `X`; baseline exposed `X` in 142 coupons, sports in one;
- event 8: actual `2`; baseline exposed `2` once, sports zero times;
- event 14: actual `2`; baseline exposed `2` in 49 coupons, sports in three;
- event 15: actual `X`; baseline exposed `X` zero times, sports once.

It improved event 12 exposure (`2`) from 58 to 140 coupons, but this was not
enough to offset the other changes. On this drawing the sports shadow was
strictly worse than the baseline. One drawing cannot establish calibration,
but it is sufficient evidence that this sports model must remain shadow-only.

## Interpretation and next research requirement

The package optimizer was selecting modeled expected value against the crowd,
not merely the most likely football outcome. Therefore a bookmaker top outcome
could still receive zero coupons. The pre-drawing modeled expected payout and
ROI fields were explicitly unvalidated model outputs, not profit forecasts.

Before any activation, test risk constraints prospectively and historically:

1. prohibit zero exposure unless a robust, predeclared confidence rule is met;
2. cap event-level concentration when no outcome has strong multi-source
   consensus;
3. report exposure floors and locked events before package release;
4. compare constrained and unconstrained packages on untouched drawings;
5. keep sports probabilities shadow-only until they beat BK baseline on a
   sufficient prospective sample with calibration evidence.

Source calculation artifacts remain under
`reports/research/goal-sports-dual-package-4987/actual-results-evaluation.*`.
