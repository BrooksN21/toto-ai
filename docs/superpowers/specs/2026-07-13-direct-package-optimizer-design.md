# Direct Package Optimizer Design

## Goal

Build and backtest a package optimizer that directly maximizes the estimated
probability that at least one coupon scores 13 or more correct outcomes.

The primary operating point is:

- bank: 5000 RUB
- stake: 30 RUB
- maximum coupons: 166
- category target: 13, equivalent to Hamming distance at most 2
- probability source for v1: pre-drawing BK probabilities stored by TotoAI

The optimizer must not use actual results while generating a package. Historical
results are used only for backtest evaluation.

## Why This Replaces Brief-First Optimization

The current baseline first selects singles, doubles, and triples, then covers
the resulting brief. Its historical result is weak: the selected brief often
excludes several actual outcomes and the package averages far below 13 hits.

For category 13, complete brief containment is not the real objective. The real
objective is the probability that at least one paid coupon lies within two
errors of the unknown result. The new optimizer therefore selects coupons
directly. A brief may be derived from the selected package for reporting or
external compatibility, but it does not constrain the search.

## Scope

### Included in v1

- Deterministic candidate coupon generation from BK probabilities.
- Probabilistic result-scenario sampling from the same BK probabilities.
- Greedy weighted maximum coverage under a coupon budget.
- Historical comparison against existing and simple baseline strategies.
- Reproducible CSV and Markdown reports.
- Main benchmark at 5000 RUB, with 3000 and 10000 RUB sensitivity runs.

### Excluded from v1

- Pinnacle or other external probability providers.
- Pool-based expected-payout optimization.
- Profitability claims or bankroll strategy.
- Live package generation for an open drawing.
- Machine learning and historical parameter fitting.

These are considered only after the direct optimizer improves holdout `13+`
results over the existing baseline.

## Strategies Compared

Every drawing uses the same BK probabilities, budget, stake, and result data for
evaluation.

1. `baseline_brief`: the existing Baseline Brief Generator and Cover Engine.
2. `top_probability`: the highest-probability exact coupons under the budget.
3. `weighted_coverage`: the proposed diversified package optimized for sampled
   probability mass within the category Hamming radius.

The simple `top_probability` strategy is required. It distinguishes gains from
diversification and category-aware coverage from gains caused merely by using
more coupons.

## Probability Model

For v1, the 15 event outcomes are treated as independent categorical variables
with normalized BK probabilities for `1`, `X`, and `2`.

For an exact result string `r`:

```text
P(r) = product(P_i(r_i)) for i in 1..15
```

Log probabilities are used internally. Missing, invalid, or non-positive BK
probabilities cause the drawing to be skipped with an explicit reason.

Independence is a documented baseline assumption, not a claim that football
events are perfectly independent.

## Candidate Coupon Generation

The candidate pool must combine probability and diversity without using actual
results:

- exact coupons produced by a deterministic k-best Cartesian-product search;
- unique coupons sampled from the BK probability distribution;
- bounded mutations around high-probability coupons when they add new
  candidates.

Generation is deterministic for a drawing and seed. Candidate limits are
configurable and reported. Duplicate coupons are removed before optimization.

The candidate pool must always contain the BK modal coupon and every coupon
selected by the `top_probability` baseline.

## Scenario Generation

Generate reproducible Monte Carlo result scenarios from BK probabilities and
aggregate duplicate scenarios into integer frequencies. A seed is derived from
the configured base seed and drawing ID.

The scenario set is split into:

- optimization scenarios, used to select coupons;
- validation scenarios, used only to estimate out-of-sample `P(13+)` for the
  selected package.

This split prevents the package's reported estimated probability from being
measured on the same Monte Carlo sample used for selection.

## Weighted Coverage Optimizer

A coupon covers a scenario when their Hamming distance is at most
`15 - category`. For category 13 this is two errors.

The optimizer greedily selects at most `bank // stake` coupons. At each step it
chooses the candidate covering the largest frequency mass of currently
uncovered optimization scenarios.

Tie-break order:

1. larger newly covered scenario mass;
2. larger exact coupon BK probability;
3. lexicographically smaller coupon.

Selection stops at the coupon limit or when no candidate adds coverage. The
optimizer may use compact integer encodings and bitsets, but these must not
change tie-break semantics.

## Backtest Design

Add a strategy-comparison command conceptually equivalent to:

```bash
python -m toto_ai.cli backtest-strategies \
  --db data/toto.db \
  --last 500 \
  --bank 5000 \
  --stake 30 \
  --category 13 \
  --seed 42
```

For each complete finished drawing:

1. Load only pre-drawing BK probabilities.
2. Generate each strategy package without actual results.
3. Evaluate packages against the stored result string.
4. Record runtime, candidate count, package size, cost, and skip reason.

The eligible last-500 window is sorted chronologically from oldest to newest.
The oldest 350 drawings form the development segment and the newest 150 form
the holdout segment. Algorithm and computational-parameter decisions may use
only the development segment. The holdout configuration is frozen before its
first complete run, and the split is printed in reports.

## Metrics

Primary acceptance metric:

- holdout `hit13_rate` for `weighted_coverage` versus `baseline_brief`.

Secondary metrics:

- `hit14_rate` and `hit15_rate`;
- average best coupon hits;
- average package size and cost;
- estimated validation-scenario `P(13+)`;
- optimization versus validation coverage gap;
- execution time and skipped/timed-out drawings.

Report paired per-drawing differences, not only aggregate rates. With limited
draw counts, confidence intervals or paired bootstrap intervals must accompany
the main `hit13_rate` comparison.

## Acceptance Criteria

The v1 experiment succeeds technically when:

- generation is deterministic for the same drawing, configuration, and seed;
- no actual result enters candidate generation or coupon selection;
- every package respects `bank // stake`;
- historical evaluation and reports are reproducible;
- all three strategies are evaluated on the same eligible drawings;
- unit tests and lint pass.

It succeeds as a strategy only when `weighted_coverage` has more holdout `13+`
hits than `baseline_brief` and does not reduce average best coupon hits. A 95%
paired bootstrap interval for the `hit13_rate` difference is reported. If that
interval includes zero, the result is labelled preliminary rather than proven.
If the point estimate does not improve, the implementation remains a research
baseline and must not become the live package generator.

## Reports

Export:

- one CSV row per drawing and strategy;
- one Markdown summary with aggregate and holdout metrics;
- the exact configuration, seed, eligible drawing count, and skip counts;
- sensitivity summaries for 3000, 5000, and 10000 RUB when requested.

Generated reports remain ignored artifacts unless an experiment is explicitly
chosen as durable research evidence.

## Follow-Up Sequence

Only after the v1 holdout comparison:

1. Add a probability-provider interface.
2. Integrate Pinnacle or another historical market source.
3. Re-run the same fixed benchmark without changing package optimization.
4. Consider pool-aware expected payout and Monte Carlo ROI objectives.
5. Add live open-drawing package generation after a strategy passes historical
   acceptance criteria.
