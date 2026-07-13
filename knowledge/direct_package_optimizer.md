# Direct Package Optimizer

The Direct Package Optimizer selects concrete 15-outcome coupons under a bank
without requiring a brief to define the search space.

V1 inputs:
- normalized pre-drawing BK probabilities only
- configurable bank, stake, and target category
- deterministic seed and candidate-generation settings

Compared strategies:
- `baseline_brief`: existing brief-first Cover Engine package
- `top_probability`: highest joint-probability coupons
- `weighted_coverage`: greedy weighted coverage of sampled result scenarios,
  followed by deterministic high-probability budget filling

Evaluation protocol:
- freeze exact drawing IDs, protocol/data hashes, and clean Git code version
- use a chronological development/holdout split
- generate packages before loading actual results
- compare paired holdout hit13/hit14/hit15 and average best hits
- any holdout timeout, generation failure, or invalid package makes the result
  operationally inconclusive

First frozen retrospective result at bank 5000 RUB, stake 30 RUB, category 13:
- 350 development and 150 holdout drawings
- no operational failures
- holdout hit13: baseline 2, top probability 6, weighted coverage 5
- holdout average best hits: 8.59, 8.86, and 10.23 respectively
- weighted-vs-baseline hit13 difference: +2.00 percentage points
- paired 95% interval: [-0.6667, 5.3333]

Conclusion:
- no strategy has proven superiority
- weighted coverage improves the average best coupon score but currently does
  not maximize the observed 13+ count
- further tuning belongs on development data; the frozen holdout must not be
  reused as a tuning target
- these results do not establish profitability

Development-only structural diagnostic:
- Packages for all 350 development drawings were regenerated and matched the
  frozen package hashes before actual results were loaded.
- Weighted coverage beat top probability on best hits in 260 drawings, tied in
  74, and lost in 16; the mean best-hit gain was 1.394.
- This translated to only one weighted-only 13+ transition, versus three
  top-only transitions. Both strategies hit 13+ together three times.
- Weighted coverage was much more diverse: average pairwise Hamming distance
  7.496 versus 3.491 for top probability.
- It also selected lower-probability coupons: average coupon log probability
  -14.729 versus -13.682.
- The average package intersection was only 11.36 of 166 coupons, with Jaccard
  overlap 0.0356.

Development interpretation:
- The v1 weighted objective over-trades coupon probability for diversity. This
  improves the nearest coupon without reliably crossing the 13+ threshold.
- The next candidate should preserve a high-probability core or probability
  floor and add controlled diversity around it.
- No strategy is selected from this diagnostic. Any candidate change must be
  chosen on development data and evaluated on a new untouched window.

Related:
- [../memory-bank/CURRENT_STATE.md](../memory-bank/CURRENT_STATE.md)
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
- [cover_engine.md](cover_engine.md)
