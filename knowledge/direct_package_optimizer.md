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

Related:
- [../memory-bank/CURRENT_STATE.md](../memory-bank/CURRENT_STATE.md)
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
- [cover_engine.md](cover_engine.md)
