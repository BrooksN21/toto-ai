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
  provider matching/market provenance, consensus configuration, external
  observation `fetched_at`, and TotoBrief `target_fetched_at`; repeated
  identical snapshots are idempotent, while a different observation or target
  fetch time creates a distinct immutable collection.
- Matched event rows retain the provider schedule event `payload_hash` and
  `fetched_at`, plus candidate IDs and match reason. Quote rows retain provider
  market `payload_hash` and `fetched_at`. Exact duplicate bookmaker/market
  keys are represented by one ineligible quote with `source_count`, a
  deterministic aggregate hash, and canonical JSON provenance containing each
  source hash, fetch/update time, and price triplet.
- `external_collection_runs.requests_made` is actual provider HTTP attempts,
  including retries and paginated page fetches. Cache hits are stored
  separately in `cache_hits` and are not requests.
- Live TotoBrief drawing 4945 (`id=11953`) returned `start_at = null` and
  `name_en = null` for all 15 events. API-Sports free fixtures access on
  2026-07-15 covered only 2026-07-14 through 2026-07-16.
- The first complete current-drawing API-Sports snapshot matched 11 of 15 events
  and produced 11 three-bookmaker-or-better consensuses (73.33%). Two events
  were absent from the provider window and two exact pairs were present only in
  reversed team order. No ambiguous match was consumed.
