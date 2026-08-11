# Drawing 4971 frozen-package evaluation

Checkpoint date: 2026-08-11. Scope: local read-only post-result scoring only.
No selector, optimizer, package regeneration, network call, database write, or
VCS publication was performed.

## Result and evidence

- Synced SQLite drawing: internal ID `12023`, visible number `4971`, status
  `finished`.
- Complete immutable result snapshot:
  `1ed61433d073b77a2bb6b461993fa3d3c9212b6e1fe5e78e57749371f6822815`,
  retrieved `2026-08-11T07:37:18.978446+00:00`.
- Actual outcomes: **`X2111X111X121X2`** (15/15 resolved).
- All compared artifacts were frozen before the result. The result was used
  only for scoring; no selection step was run.
- All scenarios use 166 coupons, bank 4,980 RUB, and stake 30 RUB.

`13+` and `14+` below are cumulative category counts; `15` is exact.

| Frozen scenario | Package SHA-256 | Best | Mean | Median | 13+ | 14+ | 15 | Scoring status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| old / pre-repair | `f52a9e6813909b4f123b66386425629daace51ee62ad12d29946a4526abce4fb` | 7 | 5.036145 | 5 | 0 | 0 | 0 | exact; reconstructed only by reversing the frozen logged swaps, then hash-verified |
| safety-v1 | `3f3c6a5033a2c504d7c85e129271e655c299db312220088e0a8eadc40574302e` | 7 | 4.981928 | 5 | 0 | 0 | 0 | exact from frozen coupon list |
| quality-v2 paper | `ccbc6dce78168c9fe6676df9545a4c356bffb688139f08607a55fc8dec382a1c` | n/a | **5.144578** | n/a | n/a | n/a | n/a | mean exact from frozen exposure marginals; coupon list absent |

Exact nonzero hit distributions:

- old: 3 hits `10`, 4 hits `42`, 5 hits `60`, 6 hits `40`, 7 hits `14`;
- safety-v1: 3 hits `11`, 4 hits `47`, 5 hits `58`, 6 hits `34`, 7 hits `16`.

## Actual-outcome exposure by event

Each cell is `coupon count (share of 166)`. `LOW` means a nonzero share below
5%, matching the existing drawing-4967 postmortem convention.

| Event | Actual | old | safety-v1 | quality-v2 |
|---:|:---:|---:|---:|---:|
| 1 | `X` | 0 (0.00%) **ZERO** | 1 (0.60%) **LOW** | 6 (3.61%) **LOW** |
| 2 | `2` | 166 (100.00%) | 157 (94.58%) | 151 (90.96%) |
| 3 | `1` | 0 (0.00%) **ZERO** | 1 (0.60%) **LOW** | 8 (4.82%) **LOW** |
| 4 | `1` | 0 (0.00%) **ZERO** | 1 (0.60%) **LOW** | 6 (3.61%) **LOW** |
| 5 | `1` | 0 (0.00%) **ZERO** | 1 (0.60%) **LOW** | 10 (6.02%) |
| 6 | `X` | 40 (24.10%) | 32 (19.28%) | 17 (10.24%) |
| 7 | `1` | 166 (100.00%) | 157 (94.58%) | 149 (89.76%) |
| 8 | `1` | 52 (31.33%) | 48 (28.92%) | 45 (27.11%) |
| 9 | `1` | 102 (61.45%) | 117 (70.48%) | 140 (84.34%) |
| 10 | `X` | 24 (14.46%) | 20 (12.05%) | 9 (5.42%) |
| 11 | `1` | 156 (93.98%) | 157 (94.58%) | 149 (89.76%) |
| 12 | `2` | 6 (3.61%) **LOW** | 8 (4.82%) **LOW** | 15 (9.04%) |
| 13 | `1` | 4 (2.41%) **LOW** | 5 (3.01%) **LOW** | 15 (9.04%) |
| 14 | `X` | 2 (1.20%) **LOW** | 1 (0.60%) **LOW** | 7 (4.22%) **LOW** |
| 15 | `2` | 118 (71.08%) | 121 (72.89%) | 127 (76.51%) |

Exposure summary:

| Scenario | Zero actual-outcome events | LOW actual-outcome events (<5%) | Actual token-hits / mean |
|---|---|---|---:|
| old | 1, 3, 4, 5 | 12, 13, 14 | 836 / 5.036145 |
| safety-v1 | none | 1, 3, 4, 5, 12, 13, 14 | 827 / 4.981928 |
| quality-v2 | none | 1, 3, 4, 14 | 854 / 5.144578 |

## Did the drawing-4967 structural remediations help?

**Structurally, yes; predictively, not yet proven.** On the finished 4971
outcome, quality-v2 removes all four old zero-exposure actual outcomes, removes
all actual-outcome cells at one coupon or less, reduces sub-5% actual exposures
from seven events to four, and raises exposure-derived mean hits from
`5.036145` (old) / `4.981928` (safety-v1) to `5.144578`. Its frozen ex-ante
structure also reduced maximum concentration `166 -> 151`, raised minimum
positive all-outcome exposure `2 -> 5`, and reduced close Hamming pairs
`2331 -> 1155` versus old.

This does **not** establish improved tail performance or profitability. The
scoreable old and safety-v1 packages both peaked at only 7/15 with zero 13+.
The quality-v2 coupon list was not retained in the frozen package artifact, so
its best, median, and 13+/14+/15 counts cannot be recovered from marginals and
the package hash. Regenerating it would violate the frozen prospective
boundary and was deliberately not done.

## Blocker

The frozen quality-v2 4971 record preserves package hash, cardinality, exposure
matrix, Hamming aggregates, modeled probabilities, and provenance, but not the
166 coupon strings. Consequently this checkpoint can compute its mean exactly
(`sum(actual-outcome exposures) / 166`) but cannot compute order-dependent hit
distribution statistics. A complete post-result settlement requires the
original hash-verifiable coupon payload; post-result regeneration is not an
acceptable substitute.

This remains `NO BET / TRAINING/PAPER`; no payout or profitability claim is
made.
