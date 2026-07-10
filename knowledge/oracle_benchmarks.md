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

Exports:
- `reports/budget_oracle_last_<N>.csv`
- `reports/budget_oracle_last_<N>.md`

Operational notes:
- `--max-candidates` is an explicit limit only; omitted means full search.
- `--timeout-per-drawing` keeps the best oracle candidate found so far.
- Partial CSV progress is written every 10 drawings.
- A timed-out row is usable as partial oracle evidence, not an exhaustive oracle
  optimum.

Related:
- [../skills/backtesting.md](../skills/backtesting.md)
- [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
