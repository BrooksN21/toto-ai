# Robust recombination canary summary: drawings 4987-4989

Status: **HISTORICAL RESEARCH ONLY / NOT ACTIVATED / NOT PROFITABILITY EVIDENCE**

Every package was selected from probability inputs frozen before results were
known. Actual outcomes were applied only afterward for settlement. All three
packages used the same 4,980-RUB bank and 166-coupon capacity.

## Modeled worst-case P(13+)

| Drawing | BK control | Sports control | Robust | Robust vs best control |
| ---: | ---: | ---: | ---: | ---: |
| 4987 | 0.000984 | 0.001065 | **0.001419** | +33.2% |
| 4988 | 0.001530 | 0.000860 | **0.001666** | +8.9% |
| 4989 | 0.008993 | 0.009469 | **0.011034** | +16.5% |

The maximin objective improved its declared cross-model metric on every frozen
input. This verifies the implementation direction, not predictive accuracy.

## Actual settlement

| Drawing | BK best | Sports best | Robust best | BK mean | Sports mean | Robust mean |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4987 | 7 | 5 | 7 | 4.560 | 3.373 | 4.139 |
| 4988 | 7 | 9 | 8 | 4.620 | 5.602 | 4.639 |
| 4989 | 11 | 10 | 11 | 6.054 | 6.060 | 6.253 |
| Average | 8.33 | 8.00 | **8.67** | **5.078** | 5.012 | 5.010 |

No package reached 13+ on any drawing. Robust best hits were never worse than
both controls, but robust mean hits did not beat the BK control on average.
Three drawings are far too few to distinguish signal from variance.

## Decision

- Keep robust recombination as the third equal-bank research candidate.
- Do not replace the scheduler's package strategy from this evidence.
- Generate the trio prospectively on drawing 4990 from one immutable final
  input, then settle all three without retuning.
- Continue until the predeclared prospective gate has enough complete drawings
  to compare calibration and category-hit outcomes.
