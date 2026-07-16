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
- Current/open event `start_at` may be null. TotoAI may recover missing starts
  from provider schedule metadata, but never changes the TotoBrief event value.
- Rare holiday/off-season drawings can span several days. They remain useful
  historical observations, while playable package generation requires all 15
  effective starts to be known within at most two inclusive Moscow calendar
  dates. Confirmed multi-day or unresolved timing is `NO BET`.
- Stored timing eligibility is bound to drawing ID and a canonical fingerprint
  of the exact fresh TotoBrief target. A stale or different target cannot reuse
  an earlier playable verdict.

Related:
- [../memory-bank/DATA_NOTES.md](../memory-bank/DATA_NOTES.md)
- [../memory-bank/ARCHITECTURE.md](../memory-bank/ARCHITECTURE.md)
- [../prompts/research.md](../prompts/research.md)
