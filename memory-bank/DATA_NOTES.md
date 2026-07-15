# Data Notes

- Around 2179 BaltBet drawings and 32685 events were collected initially.
- RAW JSON vs SQLite validation passed.
- Results and scores map correctly.
- Pool totals may equal 99, 100, or 101 due to rounding.
- Modern drawings may contain:
  - `pool_win_1`, `pool_draw`, `pool_win_2`
  - `bk_win_1`, `bk_draw`, `bk_win_2`
  - `norm_win_1`, `norm_draw`, `norm_win_2`
- Old drawings may contain only pool fields.
- Some finished events may have missing result/score in the TotoBrief API.
- Sport field is not directly provided and may require inference from
  championship.
- Championship strings require whitespace normalization.
- Cancelled, void, and missing-result events must be excluded from standard
  backtests.
- Prospective external odds collections are stored append-only in
  `external_collection_runs`, `external_event_dispositions`, and
  `external_bookmaker_quotes`. A complete collection always has 15 ordered
  event dispositions. Each disposition records either external consensus or an
  explicit TotoBrief BK fallback reason.
- External collection identity includes the fresh TotoBrief target snapshot,
  provider matching/market provenance, consensus configuration, and
  `fetched_at`; repeated identical snapshots are idempotent, while a different
  `fetched_at` creates a distinct immutable collection.
