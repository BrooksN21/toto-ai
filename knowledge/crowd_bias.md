# Crowd Bias

Current implemented analytics compare pool probabilities against bookmaker
probabilities.

Available diagnostics:
- `research` includes crowd vs bookmaker accuracy and value buckets.
- `inspect-events` shows event-level pool top, BK top, and hit flags.
- `calibration` includes pool calibration and pool-vs-BK bias.
- `brief-oracle` records pool/BK top disagreement and actual outcomes that
  contradicted both tops.

Open research themes from the roadmap:
- Pool vs BK bias.
- Draw underestimation.
- Favorite overestimation.
- Crowd calibration.

Related:
- [bookmaker_calibration.md](bookmaker_calibration.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
- [../prompts/research.md](../prompts/research.md)
