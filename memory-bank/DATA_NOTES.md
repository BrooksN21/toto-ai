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
