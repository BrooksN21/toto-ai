# Drawing 4988 robust recombination canary

Status: **HISTORICAL RESEARCH ONLY / NOT ACTIVATED / NOT PROFITABILITY EVIDENCE**

Frozen pre-result as-of: `2026-08-27T08:06:36.926731+00:00`. Actual outcomes were applied only after package selection.

## Configuration

- Bank/capacity: 4,980 RUB / 166 coupons at 30 RUB.
- Candidate universe: 309 unique coupons.
- Sports coverage/fallback: 15/0.
- Samples: 8,192 per model; runtime: 2.05s; timed out: `False`.
- Actual: `1X1X21XX12X2121`.

## Modeled P(13+)

| Package | Under BK | Under sports | Worst |
| --- | ---: | ---: | ---: |
| BK control | 0.001530 | 0.002604 | 0.001530 |
| Sports control | 0.000860 | 0.003346 | 0.000860 |
| Robust recombination | 0.001666 | 0.003424 | 0.001666 |

## Actual settlement

| Package | Best hits | Mean hits | 13+ | 14+ | 15 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BK control | 7 | 4.620 | 0 | 0 | 0 |
| Sports control | 9 | 5.602 | 0 | 0 | 0 |
| Robust recombination | 8 | 4.639 | 0 | 0 | 0 |

This single retrospective canary is diagnostic only. It does not prove profitability and cannot activate the strategy.

Machine-readable evidence: `reports/research/goal-sports-dual-package-4988-v2/robust-recombination-canary-4988-20260829.json`.
