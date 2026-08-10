# Quality-v2 frozen comparison

> **Verification status.** Drawings 4967, 4969 and 4970 were refreshed from
> actual separately executed frozen nodes after the fail-closed/true-
> lexicographic hardening. Their old and safety-v1 values were preserved
> byte-for-byte, and each refreshed golden passed its separate rerun. The
> prospective 4971 quality-v2 row is retained as a marked
> historical snapshot and was not rerun during this verification.

This evaluation is `NO BET / TRAINING/PAPER` only. It is not evidence of
profitability or a real-money release. Finished results were read only after
all packages and hashes had been selected from pre-cutoff fixtures. Drawing
4971 remains prospective and has no observed result. No payout ROI is inferred
because authoritative payouts are absent.

## Objective and precision

After hard safety feasibility and non-worsening soft headroom, quality-v2
compares P(13+), P(14+), P(15), independently sampled P(9+), Hamming
diversity and robust log-EV lexicographically. Every tier uses its documented
numerical deadband; lower-priority gains cannot compensate for a meaningful
higher-priority loss. P(13+), P(14+) and P(15) are nested exact weighted
outcome unions and are never added. P(9+) uses the domain-separated
8,192-sample evaluation stream; its worst-case normal-approximation 95% error
is 0.0108276. Optimization uses a separate 2,048-sample stream.

## Summary

| Drawing | Selector | Public/structural status | Count/cost | Best / mean hits | 13/14/15 hit | Exposure min+ / max | Max share | Hamming min/mean/median | Close pairs | Effective patterns | P9+ | P13+ | P14+ | P15 | Modeled gross-EV payout |
|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4967 | old | NO BET | 166 / 4980 | 5 / 2.560241 | no/no/no | 3 / 166 | 100.000000% | 1/3.782183/4.0 | 2163 | 2.050232 | 23.132324% | 0.125436% | 0.012587% | 0.000585% | 240426.790078 |
| 4967 | safety-v1 | NO BET / legacy structural `PLAY` | 166 / 4980 | 5 / 2.385542 | no/no/no | 1 / 157 | 94.578313% | 1/3.984739/4.0 | 1987 | 2.117808 | 26.501465% | 0.134802% | 0.013179% | 0.000598% | 230204.682366 |
| 4967 | quality-v2 | NO BET / STRUCTURAL_PASS | 166 / 4980 | 7 / 2.518072 | no/no/no | 5 / 151 | 90.963855% | 1/4.620518/4.0 | 1177 | 2.368149 | 44.238281% | 0.248347% | 0.022406% | 0.000909% | 185206.318314 |
| 4969 | old | NO BET | 166 / 4980 | 8 / 5.427711 | no/no/no | 1 / 166 | 100.000000% | 1/3.533625/4.0 | 2374 | 1.966864 | 23.205566% | 0.120479% | 0.011923% | 0.000547% | 397868.942896 |
| 4969 | safety-v1 | NO BET / legacy structural `PLAY` | 166 / 4980 | 9 / 5.554217 | no/no/no | 1 / 157 | 94.578313% | 1/3.658196/4.0 | 2181 | 2.010099 | 24.633789% | 0.128697% | 0.012524% | 0.000561% | 382668.742159 |
| 4969 | quality-v2 | NO BET / STRUCTURAL_PASS | 166 / 4980 | 9 / 5.801205 | no/no/no | 5 / 152 | 91.566265% | 1/4.037240/4.0 | 1531 | 2.148655 | 32.446289% | 0.175200% | 0.017070% | 0.000745% | 313605.662676 |
| 4970 | old | NO BET | 166 / 4980 | 8 / 5.102410 | no/no/no | 3 / 166 | 100.000000% | 1/3.543702/4.0 | 2408 | 1.972640 | 20.617676% | 0.102161% | 0.010443% | 0.000503% | 594028.074045 |
| 4970 | safety-v1 | NO BET / legacy structural `PLAY` | 166 / 4980 | 8 / 5.186747 | no/no/no | 1 / 157 | 94.578313% | 1/3.537714/4.0 | 2291 | 1.973401 | 20.336914% | 0.106210% | 0.011070% | 0.000522% | 578167.696973 |
| 4970 | quality-v2 | NO BET / STRUCTURAL_PASS | 166 / 4980 | 9 / 5.222892 | no/no/no | 6 / 151 | 90.963855% | 1/4.026944/4.0 | 1392 | 2.154171 | 31.433105% | 0.168482% | 0.016493% | 0.000682% | 478795.506754 |
| 4971 | old | NO BET | 166 / 4980 | n/a | n/a | 2 / 166 | 100.000000% | 1/3.628258/4.0 | 2331 | 1.996650 | 27.185059% | 0.165291% | 0.017049% | 0.000815% | 67192.462809 |
| 4971 | safety-v1 | NO BET / legacy structural `PLAY` | 166 / 4980 | n/a | n/a | 1 / 157 | 94.578313% | 1/3.799270/4.0 | 2066 | 2.057582 | 28.662109% | 0.177896% | 0.018206% | 0.000859% | 64842.675823 |
| 4971 | quality-v2 | NO BET / STRUCTURAL_PASS (4971 stale) | 166 / 4980 | n/a | n/a | 5 / 151 | 90.963855% | 1/4.398613/4.0 | 1155 | 2.284749 | 42.236328% | 0.265480% | 0.025529% | 0.001085% | 54860.183770 |

## Exact event exposures

Counts are ordered `1/X/2`; every row sums to 166.

### Drawing 4967

| Event | old | safety-v1 | quality-v2 |
|---:|---:|---:|---:|
| 1 | 0/57/109 | 1/55/110 | 6/26/134 |
| 2 | 0/166/0 | 1/157/8 | 7/146/13 |
| 3 | 138/28/0 | 143/22/1 | 150/8/8 |
| 4 | 0/54/112 | 1/45/120 | 10/22/134 |
| 5 | 0/3/163 | 1/8/157 | 7/8/151 |
| 6 | 158/8/0 | 157/8/1 | 143/8/15 |
| 7 | 0/158/8 | 1/157/8 | 5/137/24 |
| 8 | 93/73/0 | 101/64/1 | 102/52/12 |
| 9 | 0/40/126 | 1/32/133 | 9/25/132 |
| 10 | 0/80/86 | 1/72/93 | 17/59/90 |
| 11 | 17/149/0 | 15/150/1 | 18/141/7 |
| 12 | 0/0/166 | 1/8/157 | 10/9/147 |
| 13 | 75/12/79 | 69/10/87 | 72/8/86 |
| 14 | 0/0/166 | 1/8/157 | 9/6/151 |
| 15 | 0/26/140 | 1/20/145 | 13/7/146 |

### Drawing 4969

| Event | old | safety-v1 | quality-v2 |
|---:|---:|---:|---:|
| 1 | 143/23/0 | 146/19/1 | 144/8/14 |
| 2 | 44/118/4 | 38/125/3 | 34/125/7 |
| 3 | 0/165/1 | 1/157/8 | 9/145/12 |
| 4 | 0/0/166 | 1/8/157 | 11/5/150 |
| 5 | 153/11/2 | 155/10/1 | 150/8/8 |
| 6 | 100/18/48 | 106/15/45 | 119/7/40 |
| 7 | 0/88/78 | 1/95/70 | 9/97/60 |
| 8 | 23/143/0 | 21/144/1 | 9/141/16 |
| 9 | 2/1/163 | 8/1/157 | 14/6/146 |
| 10 | 0/10/156 | 1/8/157 | 10/7/149 |
| 11 | 37/35/94 | 33/29/104 | 23/13/130 |
| 12 | 144/10/12 | 146/9/11 | 152/7/7 |
| 13 | 0/0/166 | 1/8/157 | 10/7/149 |
| 14 | 13/153/0 | 11/154/1 | 13/145/8 |
| 15 | 0/30/136 | 1/26/139 | 9/13/144 |

### Drawing 4970

| Event | old | safety-v1 | quality-v2 |
|---:|---:|---:|---:|
| 1 | 0/0/166 | 8/1/157 | 16/6/144 |
| 2 | 8/14/144 | 7/11/148 | 19/6/141 |
| 3 | 0/8/158 | 1/8/157 | 9/7/150 |
| 4 | 118/48/0 | 119/46/1 | 121/34/11 |
| 5 | 14/152/0 | 10/155/1 | 9/143/14 |
| 6 | 141/8/17 | 144/7/15 | 139/7/20 |
| 7 | 24/13/129 | 19/13/134 | 13/9/144 |
| 8 | 0/130/36 | 1/133/32 | 9/128/29 |
| 9 | 0/39/127 | 1/36/129 | 10/23/133 |
| 10 | 0/0/166 | 1/8/157 | 8/7/151 |
| 11 | 147/19/0 | 149/16/1 | 149/9/8 |
| 12 | 159/7/0 | 157/8/1 | 151/8/7 |
| 13 | 136/27/3 | 140/23/3 | 146/13/7 |
| 14 | 20/146/0 | 18/147/1 | 10/146/10 |
| 15 | 105/53/8 | 109/50/7 | 113/45/8 |

### Drawing 4971 (prospective; quality-v2 stale)

| Event | old | safety-v1 | quality-v2 |
|---:|---:|---:|---:|
| 1 | 166/0/0 | 157/1/8 | 147/6/13 |
| 2 | 0/0/166 | 1/8/157 | 7/8/151 |
| 3 | 0/4/162 | 1/8/157 | 8/10/148 |
| 4 | 0/154/12 | 1/153/12 | 6/138/22 |
| 5 | 0/79/87 | 1/71/94 | 10/55/101 |
| 6 | 0/40/126 | 1/32/133 | 10/17/139 |
| 7 | 166/0/0 | 157/8/1 | 149/6/11 |
| 8 | 52/20/94 | 48/13/105 | 45/6/115 |
| 9 | 102/30/34 | 117/20/29 | 140/13/13 |
| 10 | 0/24/142 | 1/20/145 | 13/9/144 |
| 11 | 156/10/0 | 157/8/1 | 149/9/8 |
| 12 | 160/0/6 | 157/1/8 | 146/5/15 |
| 13 | 4/4/158 | 5/4/157 | 15/7/144 |
| 14 | 82/2/82 | 90/1/75 | 86/7/73 |
| 15 | 48/0/118 | 44/1/121 | 32/7/127 |

## Runtime and release gate

- 4967: quality-v2 selector/node core 163.110503s; fixture wall 164.07s; headroom violations 0; top-level `NO BET`; `real_money_actionable=false`; refreshed actual frozen node.
- 4969: quality-v2 selector/node core 87.664523s; fixture wall 88.23s; headroom violations 0; top-level `NO BET`; `real_money_actionable=false`; refreshed actual frozen node.
- 4970: quality-v2 selector/node core 86.505469s; fixture wall 87.0s; headroom violations 0; top-level `NO BET`; `real_money_actionable=false`; refreshed actual frozen node.
- 4971: quality-v2 selector/node core 54.232534s; fixture wall 113.20381s; headroom violations 0; top-level `NO BET`; `real_money_actionable=false`; historical stale prospective row.

All variants retain exactly 166 unique coupons at bank 4,980 and stake 30.
The unchanged independent safety evaluator still vetoes the concentrated old
packages. Refreshed quality-v2 packages are structurally feasible with zero
soft-headroom violations, but the public decision remains `NO BET` and no
retrospective row establishes a betting edge.

The safety-v1 `PLAY` cells above are immutable legacy structural-evaluator
values, not public decisions or release evidence. Current public and
machine-consumable top-level decisions are always `NO BET`; current feasible
quality-v2 artifacts use `STRUCTURAL_PASS` and `TRAINING/PAPER` instead.
