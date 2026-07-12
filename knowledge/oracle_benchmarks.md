# Oracle Benchmarks

Oracle benchmarks use actual results after the fact. They are research tools,
not playable prediction methods.

Implemented commands:
- `brief-oracle`: finds the smallest BK-ranked oracle brief that contains the
  actual result string.
- `budget-oracle`: searches oracle candidate briefs, runs the Cover Engine under
  a user budget, and compares best coupon hits against the baseline generator.

Current budget-oracle outputs:
- Oracle average best hits.
- Oracle hit13/hit14/hit15 counts and rates.
- Average singles, doubles, triples.
- Average package size and cost.
- Baseline generator average best hits.
- Oracle vs baseline hit gap.
- Progress state for long runs.
- Per-drawing timing diagnostics.
- Processed, skipped, and timed-out counts.
- Optional workload diagnostics via `--profile-workload`:
  - generated and unique candidate counts
  - Cover Engine calls
  - cache hits and misses
  - average and maximum brief variant count
  - average Cover Engine call duration
  - slowest 10 candidate briefs
  - candidates pruned by cost lower bound, dominance, and incumbent bound
  - Cover Engine calls after pruning

Exports:
- `reports/budget_oracle_last_<N>.csv`
- `reports/budget_oracle_last_<N>.md`

Operational notes:
- `--max-candidates` is an explicit limit only; omitted means full search.
- `--timeout-per-drawing` keeps the best oracle candidate found so far.
- Partial CSV progress is written every 10 drawings.
- A timed-out row is usable as partial oracle evidence, not an exhaustive oracle
  optimum.
- Workload profiling is observational only and must not alter oracle scoring,
  candidate order, or default search space.
- Candidate evaluation sorts by potential best hits descending, lower-bound cost
  ascending, brief size ascending, and original order.
- Incumbent pruning is branch-and-bound over the oracle objective. It uses
  potential hit count, theoretical lower-bound cost, brief size, and original
  order to skip candidates that cannot beat the current best.
- Dominance pruning is applied for the real greedy Cover Engine only. It relies
  on position-wise subset dominance and preserved actual-result coverage.
- Local smoke on `data/toto.db`: `budget-oracle --last 3 --bank 10000 --stake 30
  --category 13 --no-progress --profile-workload` completed in about 0.73s,
  reducing 2112 unique candidates to 3 Cover Engine calls after pruning.

Related:
- [../skills/backtesting.md](../skills/backtesting.md)
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
