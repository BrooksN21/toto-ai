# TotoBrief

TotoBrief is the current primary data source for TotoAI.

Stored data currently includes:
- BaltBet drawing history and statuses.
- Event names, championships, results, and scores.
- Pool probabilities.
- Bookmaker probabilities.
- Normalized odds where available.

Known data notes:
- Modern drawings may include `pool_*`, `bk_*`, and `norm_*` fields.
- Older drawings may include only pool fields.
- Some finished events may have missing result or score.
- Internal TotoBrief drawing id differs from public drawing number.
- Championship strings need whitespace normalization.

Related:
- [../memory-bank/DATA_NOTES.md](../memory-bank/DATA_NOTES.md)
- [../memory-bank/ARCHITECTURE.md](../memory-bank/ARCHITECTURE.md)
- [../prompts/research.md](../prompts/research.md)
