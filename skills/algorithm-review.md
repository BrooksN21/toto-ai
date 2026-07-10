# Algorithm Review

Use this checklist before changing probability, brief, cover, or package logic.

Checklist:
- State the objective being optimized.
- Confirm whether the change affects prediction quality, cover quality, or both.
- Preserve category definitions:
  - Category 13: maximum Hamming distance 2.
  - Category 14: maximum Hamming distance 1.
  - Category 15: exact match.
- Confirm that budget is user-defined and stake is configurable.
- Add or update tests for edge cases and rerun pytest/ruff.
- Update [../memory-bank/DECISIONS.md](../memory-bank/DECISIONS.md) if a
  mathematical definition changes.

Related:
- [../memory-bank/PROJECT_PHILOSOPHY.md](../memory-bank/PROJECT_PHILOSOPHY.md)
- [backtesting.md](backtesting.md)
