# Drawing 4989 preliminary equal-input strategy comparison

Status: **RESEARCH/PAPER — NOT ACTIONABLE**

The comparison uses one activation-time frozen input captured at
`2026-08-28T08:40:27.517962Z`, input SHA-256
`8c77d3b27df2a2b52ab9e8f11c59ea5d85459f8a0221086b55d45c4771b4e8ee`,
bank 4,980 RUB and stake 30 RUB. No result data was available or used.

| Strategy | Coupons | Cost | P(13+) | P(14+) | P(15) |
|---|---:|---:|---:|---:|---:|
| EV_CROWD_CURRENT | 166 | 4,980 | 0.00326133 | 0.00033612 | 0.00001529 |
| BK_PROBABILITY_ONLY | 166 | 4,980 | 0.01112910 | 0.00164989 | 0.00011415 |
| TOTOBRIEF_STYLE_COVER_13 | 22 | 660 | 0.00279384 | 0.00026697 | 0.00001073 |
| TOTOBRIEF_STYLE_COVER_14 | 90 | 2,700 | 0.00803647 | 0.00091033 | 0.00004366 |
| COVER_14_BK_FILL | 166 | 4,980 | **0.01243595** | 0.00164730 | 0.00009811 |

`COVER_14_BK_FILL` has the highest modeled P(13+) on this input: about 3.81x
current EV/crowd and 11.74% above BK-only. BK-only is marginally higher on
P(14+) and materially higher on P(15), so no universal winner follows from
this one snapshot. The same comparison must be repeated on the evening final
input and settled after the drawing.

Generated artifacts remain under
`reports/research/strategy-comparison-4989-activation-input-20260828/`.
Modeled category probability is not observed profitability.
