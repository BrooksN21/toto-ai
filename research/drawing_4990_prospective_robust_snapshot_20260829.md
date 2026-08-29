# Drawing 4990 prospective BK/sports/robust snapshot

Status: **PROSPECTIVE RESEARCH ONLY / NOT ACTIVATED / NOT PROFITABILITY EVIDENCE**

All three packages were generated from the same immutable scheduler final
input captured at `2026-08-29T13:00:03.537688Z`, before results were known.
The scheduler itself terminalized `NO BET` because the real-money release gate
was closed. This report does not change that decision.

## Configuration

- Bank: 4,980 RUB.
- Stake: 30 RUB.
- Capacity: 166 unique coupons per package.
- Sports coverage: 14/15 events; one explicit event-local BK fallback.
- Baseline/sports candidate union: 331 unique coupons.
- Robust objective: maximum minimum sampled P(13+) across BK and sports.

## Exact modeled category probabilities

| Package / evaluation model | P(13+) | P(14+) | P(15) |
| --- | ---: | ---: | ---: |
| BK control under BK | 0.015651 | 0.001717 | 0.00008157 |
| BK control under sports | 0.015915 | 0.001740 | 0.00008231 |
| Sports control under BK | 0.014032 | 0.001464 | 0.00006583 |
| Sports control under sports | 0.020041 | 0.002239 | 0.00010615 |
| Robust under BK | **0.018534** | **0.002110** | **0.00009805** |
| Robust under sports | **0.022183** | **0.002591** | **0.00012253** |

Robust improves modeled P(13+) over both controls under each probability
model on this frozen prospective input. This is stronger model-robustness, not
proof that the probabilities are correct or that the package will win.

## Runtime and operational result

- Corrected T-40 refresh completed in 211 seconds and preserved a validated
  non-actionable 166-coupon LKG.
- T-30 final completed in 273 seconds without timeout.
- Research sidecar completed before T-10 after generating the two full control
  packages and the robust recombination.
- Scheduler terminal: `NO BET` (`quality_v2_real_money_release_gate_closed`).
- Sidecar terminal: `READY_RESEARCH_ONLY_NO_BET`.

Machine-readable comparison:
`reports/rehearsal/evening-4990-20260829T163000Z-recovery-20260829T1439/goal-hybrid-sidecar/output/run-final-01-20260829T130002969207Z-520601d2/research-comparison/comparison.json`.

The next valid step is post-draw settlement of all three frozen packages with
no retuning.
