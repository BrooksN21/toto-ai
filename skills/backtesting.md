# Backtesting

Use this checklist for backtest commands.

Checklist:
- Select only finished BaltBet drawings with complete results.
- Use only information available before the drawing when testing generators.
- Report tested drawings, hit rates, package size, cost, and execution time.
- Separate brief containment from coupon/package hits.
- For long-running searches, expose progress, timeouts, partial exports, and
  per-drawing timing diagnostics.
- Before changing an expensive oracle search, inspect candidate workload:
  generated vs unique candidates, Cover Engine calls, cache hits/misses, variant
  sizes, and slowest candidates.
- When adding pruning, prove that the pruned candidate cannot improve the
  reported objective and keep regression tests against an unpruned/bruteforce
  comparison where practical.
- Export CSV and Markdown reports.
- Compare categories and budgets before drawing conclusions.

Current related commands:
- `backtest`
- `backtest-brief`
- `brief-oracle`
- `budget-oracle`

Related:
- [algorithm-review.md](algorithm-review.md)
- [../knowledge/cover_engine.md](../knowledge/cover_engine.md)
- [../knowledge/oracle_benchmarks.md](../knowledge/oracle_benchmarks.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
- [../prompts/backtest.md](../prompts/backtest.md)
