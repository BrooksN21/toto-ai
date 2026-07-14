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
  exact configuration hash. Interrupted partial work remains diagnostic.
- Reports separate modeled expected payout and modeled ROI from realized best
  hits and cumulative 9..15 indicators. A skip rate above 80% requires model
  review rather than automatic threshold reduction.
- Modeled payout uses expected crowd denominators. It is not observed bookmaker
  payout, and modeled ROI is not observed ROI or profitability evidence.

The next external-data step remains a separate provider-neutral design for
lawful prospective probability snapshots, event matching, source age and
confidence, consensus/de-vig logic, and explicit per-event TotoBrief BK
fallback. The old frozen hybrid holdout is not available for that development.

The complete design and formulas are in
[`2026-07-14-expected-value-package-engine-design.md`](../docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md).
