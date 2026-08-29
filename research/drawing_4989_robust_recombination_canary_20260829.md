# Drawing 4989 robust recombination canary

Status: **HISTORICAL RESEARCH ONLY / NOT ACTIVATED / NOT PROFITABILITY EVIDENCE**

The maximin selector used only the frozen pre-result BK and sports probability
matrices plus the 330-coupon union of the two previously frozen equal-bank
packages. The completed result was used only after selection for settlement.

## Configuration

- Bank/capacity: 4,980 RUB / 166 coupons at 30 RUB.
- Candidate universe: 330 unique coupons.
- Objective: worst sampled P(13+) across BK and sports models.
- Samples: 8,192 per model.
- Result: `21122X1222XX2X1`.

## Modeled P(13+)

| Package | Under BK | Under sports |
| --- | ---: | ---: |
| BK control | 0.012023 | 0.008993 |
| Sports control | 0.009469 | 0.010248 |
| Robust recombination | **0.012465** | **0.011034** |

The robust package improved the minimum modeled P(13+) on this frozen input,
but this is one retrospective canary and the candidate universe already came
from two generated packages. It is not a global optimum.

## Actual settlement

| Package | Best hits | Mean hits | 13+ |
| --- | ---: | ---: | ---: |
| BK control | 11 | 6.054 | 0 |
| Sports control | 10 | 6.060 | 0 |
| Robust recombination | 11 | **6.253** | 0 |

The robust package tied the best BK coupon and improved mean hits, but still
failed to reach a prize category. Therefore it is not activation or profit
evidence. It must be generated prospectively on drawing 4990 from the same
immutable final input and then settled together with both controls.

Machine-readable evidence:
`reports/research/final-goal-hybrid-4989-postdeadline-20260828/robust-recombination-canary-20260829.json`.
