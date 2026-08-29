# Drawing 4987 robust recombination canary

Status: **HISTORICAL RESEARCH ONLY / NOT ACTIVATED / NOT PROFITABILITY EVIDENCE**

Frozen pre-result as-of: `2026-08-26T10:00:18.237832+00:00`. Actual outcomes were applied only after package selection.

## Configuration

- Bank/capacity: 4,980 RUB / 166 coupons at 30 RUB.
- Candidate universe: 327 unique coupons.
- Sports coverage/fallback: 15/0.
- Samples: 8,192 per model; runtime: 2.05s; timed out: `False`.
- Actual: `1XX211122212X2X`.

## Modeled P(13+)

| Package | Under BK | Under sports | Worst |
| --- | ---: | ---: | ---: |
| BK control | 0.000984 | 0.001071 | 0.000984 |
| Sports control | 0.001065 | 0.002670 | 0.001065 |
| Robust recombination | 0.001419 | 0.002715 | 0.001419 |

## Actual settlement

| Package | Best hits | Mean hits | 13+ | 14+ | 15 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BK control | 7 | 4.560 | 0 | 0 | 0 |
| Sports control | 5 | 3.373 | 0 | 0 | 0 |
| Robust recombination | 7 | 4.139 | 0 | 0 | 0 |

This single retrospective canary is diagnostic only. It does not prove profitability and cannot activate the strategy.

Machine-readable evidence: `reports/research/goal-sports-dual-package-4987/robust-recombination-canary-4987-20260829.json`.
