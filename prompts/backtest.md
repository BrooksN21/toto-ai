# Backtest Prompt

Use this prompt shape for TotoAI backtesting tasks.

```text
Implement backtest: <name>

CLI:
python -m toto_ai.cli <command> --db data/toto.db --last <N>

Requirements:
- Use only pre-match data for generated predictions or packages.
- Exclude drawings with incomplete results.
- Report containment, best coupon hits, hit13/hit14/hit15, cost, and timing.
- Export CSV and Markdown reports.
- Add tests and run pytest/ruff.
- Update project knowledge.
```

Related:
- [../skills/backtesting.md](../skills/backtesting.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
