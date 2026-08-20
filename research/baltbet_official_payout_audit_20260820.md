# BaltBet Official Payout Audit — 2026-08-20

## Evidence boundary

- Primary source: current public BaltBet game rules, versioned public PDF:
  <https://cdndocs.baltbet.ru/uni/docs/sd_GameRules.pdf?v5=>
- Reviewed on: 2026-08-20.
- Relevant clauses: 4.2.1 (BaltSystem definition, prize allocation and void
  handling) and 9.1 (winning-bet definition).
- This note records a rules-to-code audit. It is not observed payout evidence
  and does not authorize wagering.

## Rules summarized

The official rules define every selected 15-outcome combination as a separate
BaltSystem variant. A variant participates cumulatively in every achieved
category from 9 through its final hit count.

The regular `Possible winnings` fund is split by category as follows:

| Minimum hits | Share of Possible winnings | Additional Superprize share |
| --- | ---: | ---: |
| 9 | 8/18 | 0 |
| 10 | 4/18 | 0 |
| 11 | 2/18 | 0 |
| 12 | 1/18 | 0 |
| 13 | 1/18 | 0 |
| 14 | 1/18 | 1/10 |
| 15 | 1/18 | 9/10 |

Within each category, the category fund is divided proportionally between all
qualifying stakes. If an event is void under the rule's twelve-hour condition,
every selected outcome for that event wins. A drawing with at least four void
events is refunded. A drawing containing one to three void events excludes the
Superprize from its prize fund.

## Code alignment

`src/toto_ai/ev/prize.py::category_funds()` exactly implements the published
8/18, 4/18, 2/18, 1/18, 1/18, 1/18+1/10 and 1/18+9/10 allocation.
`src/toto_ai/ev/reference.py::coupon_payout()` applies the cumulative-category
rule. Finished-result scoring treats a reviewed void event as correct for every
coupon outcome.

## Unresolved evidence gaps

1. TotoBrief `drawing-info` exposes `pool_sum` and `jackpot`, but no separate
   `Possible winnings` field in the stored payloads. TotoAI currently discloses
   and uses `pool_sum * prize_fund_factor` as a proxy.
2. All 420 result snapshots currently stored in `data/toto.db` have
   `payments = null`. Therefore actual per-category payouts and observed ROI
   cannot be reconstructed from the current database.
3. The total qualifying stake in each category is not published in the stored
   data. TotoAI estimates it from independent event-level pool marginals. This
   is an explicit model assumption, not an observed joint distribution.
4. The code must verify the special no-Superprize calculation for drawings
   with one to three void events before modeled payout can be used for those
   drawings.

## Consequence for strategy evaluation

Gross EV and modeled ROI are useful research scores, but they are not observed
profitability evidence. Until lawful pre-deadline `Possible winnings` evidence
and post-draw category payout evidence are captured, strategy comparisons must
report probability/hits separately and must not select a release winner from
modeled EV alone.

The next payout-data task is to identify a stable public or operator-provided
read-only source for the displayed `Possible winnings` and final category
coefficients. Manual package upload remains outside TotoAI; no account or bet
automation is introduced by this audit.
