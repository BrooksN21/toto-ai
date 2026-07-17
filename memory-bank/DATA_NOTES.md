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
- A safe-runner pass that reaches T-5 remains a complete immutable 15-event
  observation. No later provider request/page/retry starts; the current and
  remaining unresolved events use the explicit `safety stop reached` fallback,
  and prospective orchestration records `stop_reason="safety_stop"`.
- Live TotoBrief drawing 4945 (`id=11953`) returned `start_at = null` and
  `name_en = null` for all 15 events. API-Sports free fixtures access on
  2026-07-15 covered only 2026-07-14 through 2026-07-16.
- The first complete current-drawing API-Sports snapshot matched 11 of 15 events
  and produced 11 three-bookmaker-or-better consensuses (73.33%). Two events
  were absent from the provider window and two exact pairs were present only in
  reversed team order. No ambiguous match was consumed.
- Matcher v3 re-collected drawing 4945 with 13 of 15 unique exact matches and
  external consensuses (86.67%): 11 same-orientation and 2 explicitly reversed
  pairs. The reversed pairs were Lipno Steszew - Unia Swarzedz and Cordoba -
  Orlando Pirates. Vestmannaeyjar W - Valur W and Locarno - Paradiso remained
  explicit TotoBrief BK fallbacks because API-Sports returned no exact pair.
  The audit remains `PENDING` only because fewer than 30 drawings and 450
  events have been collected.
- A fresh two-pass collection for drawing 4945 completed in 68.66 seconds. The
  final pass used five provider requests and ten cache hits; the invocation
  recorded 16 actual HTTP attempts in total because one attempt reached the
  minute-limit boundary. Daily remaining quota moved from 52 to 37, consistent
  with 15 successful provider responses. The final snapshot retained 13/15
  consensuses and two non-retryable missing-provider fallbacks.
- The final T-15 collection for drawing 4945 pinned the target at
  `2026-07-15T14:45:01.458409+00:00` and completed its second pass at
  `2026-07-15T14:46:09.812836+00:00`, 13 minutes 50 seconds before the
  `2026-07-15T15:00:00+00:00` deadline. It finished in 69.04 seconds with two
  passes, 15 HTTP attempts, ten cache hits, 13/15 external consensuses, two
  missing-provider fallbacks, two reversed exact matches, and zero ambiguous
  matches. Daily quota remaining was 32. This proves the manual T-15 protocol
  on one live drawing; it does not satisfy the 30-drawing/450-event gate.
- TotoBrief event `start_at` may be null. Missing-start prospective collection
  begins with a two-Moscow-date schedule window and may expand through day five
  only after a stable unique exact-pair miss. Known TotoBrief starts keep their
  explicit schedule dates even outside that missing-start horizon.
- Timing eligibility uses the inclusive `Europe/Moscow` calendar span. Exactly
  15 known effective starts spanning at most two dates are `playable`; a known
  span above two dates is `multi_day`; unresolved starts are `unknown` unless
  the known subset already proves `multi_day`.
- Multi-day and unresolved snapshots remain valid historical/research data but
  are not playable. Exact drawing ID plus target fingerprint is required for a
  stored eligibility verdict; legacy, missing, malformed, or mismatched timing
  provenance fails closed.
- Safe runner acceptance can persist a base and an expansion snapshot at an
  identical deterministic observation timestamp. Latest SQLite reads resolve
  such ties by append order, preserving the final completed pass rather than
  treating a collection-content hash as chronology.
- Scheduled drawing 4947 (`id=11957`) exposed the missing production contract:
  TotoBrief returned null event starts and English names, while API-Sports
  returned 1096 fixtures containing all 15 target pairs. Matcher v3 produced
  0/15 because its exact path had no aliases for the new Cyrillic team names;
  the runner correctly failed closed with zero coupons and zero cost.
- Matcher v4 replay over the complete saved drawing-4947 schedule resolves the
  exact 15 expected provider IDs and yields 15 provider-derived effective
  starts with `eligibility=playable`. Replay over drawing 4945 preserves its
  previous 13 exact/alias matches and two provider-missing fallbacks, providing
  a false-positive regression. These two observations are not coverage-gate or
  profitability evidence.
