# Backtesting

Use this checklist for backtest commands.

Checklist:
- Select only finished BaltBet drawings with complete results.
- Use only information available before the drawing when testing generators.
- Report tested drawings, hit rates, package size, cost, and execution time.
- Separate brief containment from coupon/package hits.
- For long-running searches, expose progress, timeouts, partial exports, and
  per-drawing timing diagnostics.
- Export CSV and Markdown reports.
- Compare categories and budgets before drawing conclusions.

Current related commands:
- `backtest`
- `backtest-brief`
- `brief-oracle`
- `budget-oracle`

Related:
- [algorithm-review.md](algorithm-review.md)
- [../knowledge/oracle_benchmarks.md](../knowledge/oracle_benchmarks.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
- [../prompts/backtest.md](../prompts/backtest.md)
