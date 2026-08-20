# Phase 1 implementation inventory

Prepared: 2026-08-14
Status: **READY TO START AFTER DRAWING 4975 TERMINAL STATE**

This is a read-only implementation inventory. It does not change the current
package objective or the live drawing-4975 scheduler.

## Existing reusable components

| Planned strategy | Existing implementation | Gap |
|---|---|---|
| `EV_CROWD_CURRENT` | `toto_ai.ev` package builder and the scheduler's current EV/pool path | Expose through the same frozen-input strategy result contract |
| `BK_PROBABILITY_ONLY` | `optimizer.coupon_probabilities.top_probability_coupons` and historical `top_probability` strategy | Add current-drawing wrapper, manifest and identical comparison metrics |
| `TOTOBRIEF_STYLE_COVER` | `optimizer.brief.build_baseline_brief`, `optimizer.cover.greedy_cover`, `verify_cover_package` | Run category 13 and 14 as explicit strategy variants under the same bank/as-of |

The existing `backtest-strategies` command already compares
`baseline_brief`, `top_probability`, and `weighted_coverage` on frozen
historical inputs. It does **not** yet compare the current production
EV/crowd package against the two planned controls, and its report contract is
not the common per-drawing manifest required by the active plan.

## Minimal implementation sequence

1. Introduce immutable `StrategyInput` containing drawing/fingerprint,
   pre-deadline probability and pool rows, `as_of`, bank, stake, and category.
2. Introduce immutable `StrategyResult` containing strategy/version IDs,
   coupons, cost, unused bank, hashes, runtime, fallback, and probability
   metrics.
3. Write thin adapters around the three existing engines; do not rewrite their
   mathematics.
4. Add exact input-equality validation before comparison.
5. Add package invariants: unique coupons, exact 15 signs, cost <= bank,
   deterministic hashes, no future evidence.
6. Require exact Cover verification for category 13 and category 14 variants.
7. Add a current/frozen comparison command that writes JSON/CSV/Markdown plus
   the four package files: EV, BK-only, Cover-13, Cover-14.
8. Reuse this contract in the 100/500/1000 historical benchmark rather than
   creating another strategy implementation.

## Tests required before completion

- identical snapshot, `as_of`, bank, stake and event order across strategies;
- pool cannot affect `BK_PROBABILITY_ONLY` or Cover brief probability;
- BK changes do affect all probability-based strategies;
- category 13/14 Cover packages verify exactly against their declared brief;
- dynamic banks use exactly `bank // stake` as capacity and never exceed bank;
- duplicate coupons and future timestamps fail closed;
- deterministic rerun produces identical package/config hashes;
- current EV strategy is byte-equivalent to the scheduler-owned builder for the
  same frozen input.

## Non-goals

- no sports-shadow activation;
- no parameter tuning on drawing 4975;
- no profitability claim;
- no automatic wager placement;
- no replacement of existing historical baselines before the equal-input
  benchmark exists.
