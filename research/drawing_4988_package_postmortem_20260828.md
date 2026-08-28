# Drawing 4988 package postmortem

Status: settled retrospective evidence. The package is expired and is not
actionable for wagering.

## Immutable inputs

- Drawing: 4988 (`drawing_id=12071`).
- Frozen input captured: `2026-08-27T15:40:16.423749Z`.
- Package: 166 unique coupons, stake 30 RUB, cost 4,980 RUB.
- Package SHA-256:
  `0c2efcd84649fc772ba2f1bb0ef8fbd34cfab85aed3334ca24967aa76cd7e9dc`.
- Result: `1X1X21XX12X2121`.
- Result snapshot SHA-256:
  `62a24d563372b94c1acb0fdef55486215911738fdf58d692853db69e1be09177`.
- Settlement SHA-256:
  `f5e24c7dfd2126504a57ba64fd4a4cc8ac0dd443b66df6a2d5e1021e42bb8774`.

## Actual performance

- Best coupon: **8/15**; three coupons reached 8.
- Average hits: **5.404/15**.
- Hit distribution: 3=7, 4=33, 5=46, 6=49, 7=28, 8=3.
- 9+/13+/14+/15: **0/0/0/0**.
- The payout and ROI remain unrecorded until official payout evidence is
  available. The package did not reach nine correct outcomes.

The result itself was difficult under the frozen BK probabilities: five actual
outcomes were BK rank 1, six were rank 2, and four were rank 3. The exact
actual-result joint probability under the independent BK model was about
`2.98e-8`. This explains part of the miss, but it does not explain or excuse the
package construction defect below.

## Package construction defect

The current EV/crowd selector starts from the highest modeled-EV coupons and
uses only a small probability floor plus 12 local quality swaps. It does not
globally construct the package by the declared primary objective `P(13+)`.

Consequences in drawing 4988:

- Nine actual outcomes appeared in only 3.0%-7.8% of the 166 coupons.
- Several lower-BK-probability outcomes received 83%-91% exposure.
- The package's modeled `P(13+)` was `0.00339451`.
- A 166-coupon BK top-probability package on the same immutable input had
  modeled `P(13+) = 0.02167641`, about **6.4 times larger**.
- A full-bank Cover-14 plus non-duplicate BK-fill research construction had
  modeled `P(13+) = 0.02323722`.

The one-drawing actual scores do not select a winner: EV/crowd reached 8,
BK-only reached 7, and the Cover-14/BK-fill research construction reached 7.
The modeled and historical evidence nevertheless show that EV/crowd is the
wrong sole package when the primary objective is the chance of 13+.

This is not a new one-drawing inference. The existing 100-drawing legacy
diagnostic reports average best hits of 7.05 for EV/crowd versus 8.70 for
BK-only, while the strict 13-drawing pipeline diagnostic reports 7.00 versus
9.00. Neither dataset proves profitability, but both identify the same large
selector defect.

## Required response

1. Keep `EV_CROWD_CURRENT` as a shadow comparator, not the only operator
   candidate.
2. Generate a full-bank `BK_PROBABILITY_ONLY` control from the same final
   snapshot.
3. Add a full-bank `COVER_14_BK_FILL` challenger: preserve the exact Cover-14
   subset, then fill unused capacity with the highest-probability unique BK
   coupons.
4. Compare every package on identical frozen bytes, bank and stake using exact
   modeled `P(13+)`, `P(14+)`, `P(15)`, concentration, and post-draw actual
   hits.
5. Do not activate sports adjustments until their probability calibration
   beats or safely complements the market prior on frozen chronological data.
6. Do not tune thresholds to drawing 4988. Record 4988 as the first explicit
   failure row for the revised prospective comparison.

No result here proves positive expected return or guarantees a win.
