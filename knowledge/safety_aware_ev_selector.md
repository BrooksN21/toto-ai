# Safety-aware EV Selector

The playable EV selector now constructs a deterministic, constraint-feasible
coupon package before the existing final package-safety veto. Probability and
EV formulas are unchanged: only the choice of coupons after the complete EV
ranking changes.

## Selection contract

- The requested cardinality is `selection_budget // stake`; all coupons are
  unique and must pass the configured gross-EV threshold.
- For each event/outcome with true probability at or above the configured
  material threshold, selected exposure is at least one coupon.
- For every event/outcome, the largest permitted count is
  `ceil(near_fixed_share * coupon_count) - 1`. This preserves the safety
  policy's strict rejection boundary at `share >= near_fixed_share`.
- Avoiding fixed outcomes also preserves the existing low-probability fixed
  outcome rule. The independent final safety veto remains authoritative and
  unchanged.
- The deterministic candidate prefix starts at the larger of 32,768 coupons,
  128 candidates per requested coupon, and the requested cardinality. It
  expands fourfold when repair cannot find a feasible package, up to one
  million eligible coupons or the full eligible set.
- Repair starts from the highest-EV package. Each deterministic swap reduces
  total bound violation; ties choose the smallest gross-EV loss and then the
  stable complete-ranking order. A feasible one-swap improvement pass restores
  higher-ranked coupons whenever all constraints remain satisfied.
- The method is a deterministic constrained repair with one-swap local EV
  improvement, not a claim of a globally optimal integer-program solution.
  If it cannot prove a package through its bounded candidate universe, it
  returns coupon-free `NO BET` with explicit diagnostics rather than bypassing
  safety.

Diagnostics record pre/post event concentrations, repaired material outcomes,
outgoing/incoming coupons and ranks, gross-EV-sum delta, both package hashes,
candidate counts, the integer concentration cap, feasibility, and any
infeasibility reason.

## Frozen chronological evidence

The regression fixtures contain only pre-cutoff pool/BK quote inputs. Finished
results are stored separately and loaded by the test only after old and new
package hashes have been computed. Bank is 4,980 RUB and stake is 30 RUB for
this comparison, giving 166 coupons. These measurements are retrospective
selector evidence, not observed payout or profitability evidence.

| Drawing | Pre-cutoff capture | Old safety | Safe safety | Candidate prefix | Repairs / replacements | Modeled expected payout, old -> safe | Best hits, old -> safe | Mean hits, old -> safe |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 4967 | 2026-08-06 14:40:29Z, before 14:50Z | `NO BET` | `PLAY` | 131,072 | 17 / 18 | 240,426.790078 -> 230,204.682366 | 5 -> 5 | 2.560241 -> 2.385542 |
| 4969 | 2026-08-08 10:40:27Z, before 14:00Z | `NO BET` | `PLAY` | 32,768 | 11 / 18 | 397,868.942896 -> 382,668.742159 | 8 -> 9 | 5.427711 -> 5.554217 |
| 4970 | 2026-08-09 10:14:23Z, before 14:00Z | `NO BET` | `PLAY` | 32,768 | 12 / 16 | 594,028.074045 -> 578,167.696973 | 8 -> 8 | 5.102410 -> 5.186747 |

All three repaired packages contain exactly 166 unique coupons, pass the
unchanged final safety evaluator, and have maximum event/outcome exposure
157/166 (94.5783%), below the 95% rejection boundary. The old packages are
rejected for extreme concentration and missing material outcomes.

Drawing 4967 reproduces the exact old rejected package hash from the postmortem:
`6854f91e18616c34f7267c4c28bbb2be5853e249a4e8b8b26ee07276cecf0177`.
The repaired hash is
`3cf45fdeceee3cbec7f6380dfe5c643766865a181d78c8f289ab1096c44f4a34`.
The modeled expected-payout reduction is the cost of satisfying the safety
constraints under the unchanged EV surface; it is not an observed loss.

The three finished drawings are too small a sample for performance or profit
claims. Their actual outcomes were not used to tune or select coupons.
