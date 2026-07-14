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

The complete design and formulas are in
[`2026-07-14-expected-value-package-engine-design.md`](../docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md).

