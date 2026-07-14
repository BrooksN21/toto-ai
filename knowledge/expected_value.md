# Expected Value

TotoAI's next optimizer ranks exact coupons by modeled monetary expected value,
not by average best hits or `13+` frequency alone.

Core definitions:

- True outcome probabilities initially come from normalized TotoBrief `bk_*`.
- Crowd coupon probabilities initially use normalized `pool_*` marginals and an
  explicit event-independence assumption.
- BaltBet categories are cumulative: a coupon with `h` hits participates in
  every category from 9 through `h`.
- The package bank is any positive multiple of the configurable stake.
- A playable run may return `NO BET`; it never lowers the EV threshold merely
  to spend the bank.
- Modeled EV is not observed ROI while historical winner and category-payout
  data are unavailable.

Historical evaluation contract:

- A validated frozen strategy manifest is mandatory; its final holdout IDs are
  excluded from the drawing query before any event or quote access.
- Historical input queries contain exactly 15 ordered BK/pool rows and do not
  select results. Package hashes for every factor, bank, and threshold are
  complete before actual results are loaded.
- One exact component build is reused per drawing. Each prize-fund factor has
  one complete coupon surface and ranking reused across all dynamic banks and
  thresholds; there are no candidate limits or timeout-derived rows.
- Checkpoints contain completed drawings only and are resumable solely under an
  exact configuration hash. Skip records and interrupted partial work remain
  diagnostic and are re-evaluated rather than treated as completed.
- Checkpoints deduplicate canonical ordered coupon payloads by package hash.
  Resume recomputes each SHA-256 using the production comma-separated encoding,
  matches payload counts to referencing rows, requires non-empty manifests for
  `PLAY` and the exact empty manifest/hash for `NO BET`, and rejects missing,
  duplicate, orphan, conflicting, malformed, or tampered manifests. Coupon
  payloads are checkpoint-only and do not expand final report rows.
- Each package manifest also stores canonical sorted unique `(drawing_id, bank,
  threshold, prize_fund_factor)` references. Resume derives those keys from the
  completed rows and requires exact per-hash equality, preventing valid
  equal-count package hashes from being swapped between row contexts. These
  references are checkpoint-only and are not part of the coupon hash.
- `last=N` counts the latest `N` drawings with valid inputs and complete actual
  results. Newer incomplete drawings do not displace older complete drawings,
  but their result values are still unavailable until packages and hashes exist.
- Historical Playable evaluation uses the live 1% self-dilution rule: exactly
  1% is supported and above 1% becomes an empty `NO BET`. Rows disclose the
  proposed cost ratio and support state.
- Reports separate modeled expected payout and modeled ROI from realized best
  hits and cumulative 9..15 indicators. A skip rate above 80% requires model
  review rather than automatic threshold reduction.
- Modeled payout uses expected crowd denominators. It is not observed bookmaker
  payout, and modeled ROI is not observed ROI or profitability evidence.
- Final and checkpoint artifact names include the full exact-configuration hash,
  which binds banks, thresholds, factors, stake, requested window, community,
  and forbidden frozen-manifest IDs.

The next external-data step remains a separate provider-neutral design for
lawful prospective probability snapshots, event matching, source age and
confidence, consensus/de-vig logic, and explicit per-event TotoBrief BK
fallback. The old frozen hybrid holdout is not available for that development.

The complete design and formulas are in
[`2026-07-14-expected-value-package-engine-design.md`](../docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md).
