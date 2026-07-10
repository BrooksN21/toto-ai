# Bookmaker Calibration

Implemented command:

```bash
python -m toto_ai.cli calibration --db data/toto.db
```

Current research measures:
- Bookmaker reliability by 5 percentage-point bins for outcomes `1`, `X`, `2`.
- Pool reliability with the same bins.
- Brier score.
- Log loss.
- Expected Calibration Error.
- Pool vs bookmaker bias.
- Draw calibration.
- Favorite calibration for BK probabilities `>= 60%`.
- Underdog calibration for BK probabilities `<= 25%`.

Exports:
- `reports/calibration.md`
- `reports/calibration.csv`
- `reports/reliability.csv`

Related:
- [../memory-bank/CURRENT_STATE.md](../memory-bank/CURRENT_STATE.md)
- [crowd_bias.md](crowd_bias.md)
- [../skills/research.md](../skills/research.md)
