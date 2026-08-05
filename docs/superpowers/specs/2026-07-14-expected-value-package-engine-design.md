# Expected-Value Package Engine Design

## Context

The sealed BK-only hybrid experiment returned `STOP`. Optimizing average best
hits or observed `13+` frequency did not establish a profitable strategy. The
next engine therefore changes the objective from hit count to modeled monetary
expected value (EV).

This is a research system, not evidence of profit. Historical BaltBet data does
not contain complete observed category payouts and winner counts, so the first
version can validate its mathematics and modeled EV but cannot claim observed
ROI.

## Goal

For one 15-event BaltBet drawing, rank every one of the `3^15 = 14,348,907`
coupons by modeled monetary EV and form a package under any valid user bank.

The engine must:

- accept any positive bank divisible by the coupon stake;
- use 30 RUB only as the configurable default stake;
- evaluate the complete coupon space without candidate truncation;
- model cumulative BaltBet category payouts for 9 through 15 hits;
- distinguish research output from a playable recommendation;
- return `NO BET` when no coupon meets the playable EV threshold;
- disclose every probability, crowd, and prize-fund assumption.

## Non-Goals

The first implementation does not:

- place bets automatically;
- claim profitability from modeled EV;
- scrape Pinnacle or bypass access restrictions;
- infer missing external odds by silently dropping events or drawings;
- optimize a brief first and then expand it;
- reuse the frozen hybrid holdout for strategy selection.

## Inputs

### Drawing inputs

Each event requires ordered probabilities for `1`, `X`, and `2`:

- `q_i`: estimated true probabilities, initially normalized TotoBrief `bk_*`;
- `r_i`: estimated crowd selection probabilities from TotoBrief `pool_*`.

The drawing also requires:

- `pool_sum`;
- superprize/jackpot amount when available;
- bank;
- stake;
- probability-source metadata and timestamps.

All probability triplets are normalized. Missing or invalid `q_i`, `r_i`, or
`pool_sum` fails the EV calculation instead of substituting an undocumented
value.

### Dynamic bank

The bank is valid when it is positive and exactly divisible by the stake:

```text
max_coupons = bank / stake
```

Examples such as 4,800, 6,000, and 9,600 RUB are ordinary inputs. The engine is
not tuned to a fixed 5,000 or 10,000 RUB bank. A package may use less than the
available bank.

## Prize Model

The official BaltBet rules allocate the possible-winnings fund `V` as follows:

| Minimum hits | Fund |
| --- | ---: |
| 9 | `8/18 * V` |
| 10 | `4/18 * V` |
| 11 | `2/18 * V` |
| 12 | `1/18 * V` |
| 13 | `1/18 * V` |
| 14 | `1/18 * V + 1/10 * J` |
| 15 | `1/18 * V + 9/10 * J` |

`J` is the superprize. A coupon with `h` hits participates cumulatively in
categories 9 through `h`.

Source: `https://cdndocs.baltbet.ru/uni/docs/sd_GameRules.pdf?v5=`.

TotoBrief currently supplies `pool_sum` and jackpot data but not a separately
verified `V`. The engine therefore supports:

1. an explicit `possible_winnings` override; or
2. a documented proxy `V = pool_sum * prize_fund_factor`.

The default factor is `1.0`, is always printed in reports, and is never called
an exact observed prize fund. Research runs report sensitivity at factors
`0.70`, `0.80`, `0.90`, and `1.00` unless explicitly overridden.

## Probability Model

For actual result vector `y`:

```text
Q(y) = product(q_i[y_i])
```

The initial crowd model assumes independent event selections:

```text
R(t) = product(r_i[t_i])
```

Pool marginals do not identify the true joint distribution of submitted
coupons. Independence is therefore an explicit model assumption, not a fact.
Every report labels it and later backtests must include correlation stress
tests.

Rounded zero pool shares receive deterministic Jeffreys smoothing. With
`N = pool_sum / stake`, marginal pseudo-counts are:

```text
n_ij = N * r_ij
r'_ij = (n_ij + 0.5) / (N + 1.5)
```

This prevents zero expected winner denominators while making the adjustment
shrink as the pool grows.

## Coupon Expected Value

Let `H(a, b)` be the number of matching positions. For category `k`, expected
crowd stake qualifying under actual result `y` is:

```text
D_k(y) = pool_sum * sum_t R(t) * I[H(t, y) >= k]
```

For coupon `c`, its modeled payout under `y` is:

```text
P(c, y) = sum over k=9..H(c,y) of F_k * stake / D_k(y)
```

Its return multiple and net expected value are:

```text
gross_ev(c) = sum_y Q(y) * P(c,y) / stake
net_ev(c) = gross_ev(c) - 1
```

Package expected payout is additive in v1 because the package's own stakes are
not added to `D_k(y)`. The report shows `bank / pool_sum`; a run is marked
unsupported when this ratio exceeds 1%, because self-dilution may no longer be
negligible.

## Exact Full-Space Computation

No heuristic candidate list is allowed. The implementation evaluates all
`3^15` coupons exactly under the stated model.

The state space is encoded as vectors in `(Z3)^15`. For category `k`, define a
symmetric Hamming-ball kernel:

```text
K_k(d) = I[HammingWeight(d) <= 15-k]
```

Ternary convolution computes:

```text
crowd_tail_k = R * K_k
f_k(y) = Q(y) * F_k / (pool_sum * crowd_tail_k(y))
coupon_ev_k = f_k * K_k
gross_ev = sum_k coupon_ev_k
```

The engine uses an exact-to-floating-point ternary FFT/convolution
implementation, processes categories sequentially, and uses memory-mapped or
reused arrays where required. Performance work may change representation,
parallelism, or caching only when full-output equivalence remains within a
fixed numerical tolerance. It must never reduce the coupon space.

Long calculations show phase, category, elapsed time, and memory use. A timeout
or interruption never returns a partial package as playable; it returns a
failed diagnostic run.

Small-dimensional brute force is the independent mathematical oracle. Full
15-event runs verify probability mass, non-negative denominators, stable
ranking, and sampled direct-sum EV values.

## Package Modes

### Research mode

Research mode always ranks and exports the best coupons, even when all have
`gross_ev < 1`. It reports package outcomes for thresholds:

```text
0.90, 0.95, 1.00, 1.05
```

For comparison it may also show the top `max_coupons` package, but must label a
negative modeled edge clearly.

### Playable mode

Playable mode selects, in deterministic EV order, only coupons satisfying the
configured minimum gross EV. The default threshold is `1.00`.

- The package size is at most `bank / stake`.
- The full bank is not forced into action.
- If no coupon passes, the result is `NO BET`.
- The threshold is never lowered automatically to manufacture a bet.
- The top candidates are still displayed for diagnosis.

Threshold research reports hit rate, modeled payout, modeled ROI, selected
coupon count, bank utilization, and skip rate. If more than 80% of eligible
drawings are skipped, the result triggers probability/crowd/prize-model review;
it does not justify lowering the threshold by itself.

## Output

Planned commands:

```bash
python -m toto_ai.cli ev-package --open \
  --mode research \
  --bank 6000 \
  --stake 30 \
  --prize-fund-factor 1.0

python -m toto_ai.cli ev-package --open \
  --mode playable \
  --bank 6000 \
  --stake 30 \
  --min-gross-ev 1.0

python -m toto_ai.cli backtest-ev \
  --db data/toto.db \
  --banks 4800,6000,9600 \
  --thresholds 0.90,0.95,1.00,1.05
```

`--possible-winnings` and `--prize-fund-factor` are mutually exclusive. The
open-drawing command fetches a fresh TotoBrief snapshot immediately before
calculation and records its timestamp; a saved package is not treated as a
permanent recommendation after its input snapshot changes.

The open-drawing command will export:

- exact selected coupons and per-coupon EV;
- package expected payout, modeled ROI, cost, and unused bank;
- derived display brief formed by the union of selected outcomes per position;
- probability source and fallback per event;
- pool, prize-fund factor/override, jackpot, and crowd-model assumptions;
- threshold, mode, and `PLAY` or `NO BET` decision;
- sensitivity results.

The derived brief is descriptive only. Its Cartesian product may contain
coupons not selected by the optimizer, so the exact package CSV remains the
betting artifact.

## Historical Evaluation

Historical reports separate three concepts:

1. probability quality: log loss, Brier score, and calibration;
2. modeled strategy quality: modeled EV and threshold behavior;
3. realized hit outcomes: 9 through 15 hits for selected coupons.

Because historical category payouts and winner counts are absent, modeled ROI
is not observed ROI. Profitability requires prospective storage of pre-close
inputs and actual category payout/winner data from a lawful source. No GO claim
may be based only on modeled ROI.

Backtests are chronological and compare dynamic banks across stake multiples,
including 4,800, 6,000, and 9,600 RUB. The old frozen hybrid holdout remains
closed.

## External Probability Providers

Direct Pinnacle API access is not assumed, and prohibited scraping is out of
scope. The EV engine consumes a provider-neutral probability interface.

The first lawful external-provider experiment will evaluate API-Sports
(API-Football and API-Hockey) because its documented coverage is broader than
the previously considered The Odds API mapping. External data is applied per
event:

1. match by sport, kickoff, normalized teams, and league;
2. require a recorded confidence threshold;
3. de-vig and aggregate a market consensus with outlier controls;
4. use the external probability when accepted;
5. otherwise fall back to TotoBrief BK for that event.

A missing external match never silently drops the entire drawing. Reports show
coverage, match confidence, source age, and fallback reason for all 15 events.
Because short historical windows are common, accepted odds are stored
prospectively before each drawing closes.

External collection and event matching require a separate design and
implementation cycle after the EV core is verified.

## Failure Handling

Fail closed without a playable package when:

- bank is not a positive stake multiple;
- the drawing does not contain exactly 15 ordered events;
- required pool, probability, or prize inputs are invalid;
- probability normalization or total-mass checks fail;
- any expected winner denominator is non-positive or non-finite;
- FFT and brute-force verification disagree beyond tolerance;
- output artifacts cannot be written atomically.

Research mode may still emit diagnostics for a failed playable decision, but
must not label it `PLAY`.

## Testing and Acceptance

Tests must prove:

- exact official category-fund and cumulative-payout calculations;
- dynamic bank validation and package caps;
- crowd smoothing and probability normalization;
- brute-force EV correctness for small event counts;
- ternary convolution equivalence to brute force;
- all `3^15` coupons are ranked without pruning;
- deterministic tie-breaking by coupon string when EV values are equal within
  `rtol=1e-12` and `atol=1e-15`;
- research threshold and playable `NO BET` behavior;
- no automatic threshold lowering;
- correct prize-factor sensitivity;
- package cost never exceeds bank;
- external-provider fallback never causes a silent drawing omission;
- reports disclose every model assumption and source.

Initial acceptance is mathematical and operational: exact full-space results,
reproducibility, and complete assumption reporting. Profitability acceptance is
deferred until lawful prospective payout data exists.

## Implementation Sequence

1. Add pure prize, crowd, and brute-force EV reference models.
2. Add the exact ternary convolution engine and benchmark it against the
   reference model.
3. Add research/playable package selection for arbitrary banks.
4. Add deterministic reports, sensitivity analysis, and CLI commands.
5. Add chronological modeled-EV backtests without reopening the old holdout.
6. Design and implement prospective external odds collection separately.
