# Safety-aware EV Selector

The playable EV selector now constructs a deterministic, constraint-feasible
coupon package before the existing final package-safety veto. Probability and
EV formulas are unchanged: only the choice of coupons after the complete EV
ranking changes.

## Selection contract

- The requested cardinality is `selection_budget // stake`; all coupons are
  unique and must pass the configured gross-EV threshold.
- Every event/outcome receives the continuous target
  `K * exposure_floor_scale * p**exposure_floor_exponent`, where `K` is the
  package size. The enforced integer minimum is the mathematical floor of that
  target. Defaults are scale `0.15` and exponent `1.0`; requiring scale in
  `(0, 1]` and exponent at least one makes each event's three minima
  sum-feasible. There is no special branch or cliff at probability `0.20`.
- For every event/outcome, the largest permitted count is
  `ceil(near_fixed_share * coupon_count) - 1`. This preserves the safety
  policy's strict rejection boundary at `share >= near_fixed_share`.
- A configurable soft maximum subtracts
  `ceil(concentration_headroom_share * K)` from the hard maximum, without
  crossing a lower exposure bound. Repair minimizes hard violation first and
  soft-headroom violation second. Remaining headroom violations are explicit
  diagnostics; the independent hard concentration veto is unchanged.
- Avoiding fixed outcomes also preserves the existing low-probability fixed
  outcome rule. The independent final safety veto remains authoritative and
  unchanged.
- The deterministic candidate prefix starts at the larger of 32,768 coupons,
  128 candidates per requested coupon, and the requested cardinality. It
  expands fourfold when repair cannot find a feasible package, up to one
  million eligible coupons or the full eligible set.
- Repair starts from the highest-EV package. Each deterministic swap reduces
  total bound violation; ties choose the smallest gross-EV loss and then the
  stable complete-ranking order. A feasible one-swap improvement pass restores
  higher-ranked coupons whenever all constraints remain satisfied.
- The method is a deterministic constrained repair with one-swap local EV
  improvement, not a claim of a globally optimal integer-program solution.
  If it cannot prove a package through its bounded candidate universe, it
  returns coupon-free `NO BET` with explicit diagnostics rather than bypassing
  safety.

After hard safety feasibility and non-worsening soft-headroom repair,
deterministic bounded swaps improve package quality. The true lexicographic
order is P(13+), P(14+), P(15), independently sampled P(9+), Hamming
diversity, and finally robust `sum(log1p(coupon gross EV))`. Each probability
tier has an explicit `1e-12` deadband by default; diversity and robust EV have
their own `1e-12` deadbands. A lower-priority gain cannot compensate for a
meaningful loss at any higher tier. Stable complete-ranking order resolves an
otherwise exact tie. No weighted category score remains.

The category terms are probabilities of package-level unions over modeled
outcomes. They are not sums of per-coupon probabilities. `P(13+)`, `P(14+)`,
and `P(15)` are exact weighted unions of Hamming balls with radii 2, 1, and 0.
`P(9+)` uses deterministic Monte Carlo: the default reporting run has 8,192
samples and worst-case normal-approximation 95% sampling error `0.0108276`.
The seed is derived from the frozen probability snapshot/input, schedule
ledger and scheduler-plan hashes. Optimization uses the domain-separated
`quality-v2-optimization` 2,048-sample stream; accepted swaps are independently
re-evaluated with the `quality-v2-evaluation` 8,192-sample stream. The two
seeds and stream names are reported and never share RNG state.

Diagnostics record all lower targets/bounds, pre/post event concentrations,
headroom violations, replacements, gross and robust-EV deltas, diversity and
distance distribution, exact/Monte-Carlo category probabilities, both package
hashes, candidate counts, feasibility and objective values. The diagnostic
payload hashes and binds the exact probability snapshot, normalized probability
input, schedule-evidence ledger bytes/semantic identity, canonical schema-v7
scheduler-plan bytes, and the complete quality-v2 configuration. Arbitrary
digest strings, arbitrary plan files, missing artifacts, symlinks, or mutated
bytes fail closed.

The canonical bound selection context also records mode, bank, stake,
requested coupon capacity, effective budget/capacity, minimum gross EV,
concentration and probability thresholds, safety/provenance flags, and the
nested quality-v2 policy. Selector provenance, schema-v7 SchedulerPlan, runner
manifest, and diagnostics must agree on both the exact canonical object and its
SHA-256. Missing fields, self-consistent forged values, and runtime drift fail
closed.

Quality-v2 is **paper-only**. Structural feasibility is reported only as
`STRUCTURAL_PASS`; every top-level CLI, runner, report, manifest and scheduler
decision remains `NO BET`, with coupons confined to explicitly labelled
`TRAINING/PAPER` fields and `real_money_actionable=false`. No trusted local
prospective-evidence registry currently exists, so self-declared IDs or hashes
cannot open the release gate.

`DrawingRunnerResult` is itself a public safety boundary: manually constructing
top-level or package-level `PLAY` immediately produces `NO BET` with empty
actionable fields. Direct report writing and aggregate publication repeat the
enforcement. Coupons may remain only in explicit `TRAINING/PAPER` fields and
never cause wager-ready EV artifacts to be emitted.

The lower-level `write_ev_package_reports` API uses the same shared EV-run
sanitizer. A legacy/injected `PLAY` therefore produces a header-only coupon CSV
and a `NO BET` Markdown report. If coupons are retained for audit, they are
listed only under **Training/Paper Coupons** with an explicit non-wager label.
An already valid `NO BET`/`STRUCTURAL_PASS` training package is preserved.

The exact exposure floor uses IEEE-754 evaluation followed by mathematical
`floor`, with no hidden epsilon. This named boundary policy is bound into the
configuration hash and tested directly.

Dynamic cardinality is `bank // stake`. Regressions cover 4,980/30 (166),
9,960/30 (332), and 2,500/25 (100), always with exact unique paper coupons.
Adding coupons to an explicitly nested package cannot reduce any modeled union
probability. Independent bank optimizations are deterministic but are not
claimed to be strict package prefixes of one another; cross-bank comparisons
must therefore report both package hashes and measured union probabilities.

## Frozen chronological evidence

The regression fixtures contain only pre-cutoff pool/BK quote inputs. Finished
results are stored separately and loaded by the test only after old and new
package hashes have been computed. Bank is 4,980 RUB and stake is 30 RUB for
this comparison, giving 166 coupons. These measurements are retrospective
selector evidence, not observed payout or profitability evidence.

| Drawing | Pre-cutoff capture | Old safety | Safe safety | Candidate prefix | Repairs / replacements | Modeled expected payout, old -> safe | Best hits, old -> safe | Mean hits, old -> safe |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 4967 | 2026-08-06 14:40:29Z, before 14:50Z | `NO BET` | `PLAY` | 131,072 | 17 / 18 | 240,426.790078 -> 230,204.682366 | 5 -> 5 | 2.560241 -> 2.385542 |
| 4969 | 2026-08-08 10:40:27Z, before 14:00Z | `NO BET` | `PLAY` | 32,768 | 11 / 18 | 397,868.942896 -> 382,668.742159 | 8 -> 9 | 5.427711 -> 5.554217 |
| 4970 | 2026-08-09 10:14:23Z, before 14:00Z | `NO BET` | `PLAY` | 32,768 | 12 / 16 | 594,028.074045 -> 578,167.696973 | 8 -> 8 | 5.102410 -> 5.186747 |

All three repaired packages contain exactly 166 unique coupons, pass the
unchanged final safety evaluator, and have maximum event/outcome exposure
157/166 (94.5783%), below the 95% rejection boundary. The old packages are
rejected for extreme concentration and missing material outcomes.

Drawing 4967 reproduces the exact old rejected package hash from the postmortem:
`6854f91e18616c34f7267c4c28bbb2be5853e249a4e8b8b26ee07276cecf0177`.
The repaired hash is
`3cf45fdeceee3cbec7f6380dfe5c643766865a181d78c8f289ab1096c44f4a34`.
The modeled expected-payout reduction is the cost of satisfying the safety
constraints under the unchanged EV surface; it is not an observed loss.

The three finished drawings are too small a sample for performance or profit
claims. Their actual outcomes were not used to tune or select coupons.

## Quality-v2 frozen evaluation

The exact old/safety-v1/quality-v2 comparison, including all 15 event exposure
rows, package hashes, Hamming distributions, modeled P(9+/13+/14+/15), observed
best/mean hits where available, runtime, and the prospective 4971 diagnostics,
is stored as a **historical pre-review-blocker snapshot** in
`plans/TOTOAI-AUDIT-4971-PACKAGE-20260810/quality-v2-frozen-comparison.md`.
Machine-readable rows are stored beside it. Every evaluated variant has 166
unique coupons at bank 4,980 and stake 30. The 4967/4969/4970 quality-v2 rows
were refreshed from separate actual frozen-node executions against the final
lexicographic/provenance contract; old and safety-v1 values were preserved.
Drawing 4971 has no result, was not tuned against future outcomes, and its
retained quality-v2 row is explicitly marked as a stale historical prospective
snapshot because this verification intentionally reran only the three finished
golden nodes.

The concrete drawing-4967 findings, implementation points, tests and remaining
predictive limitations are mapped in
`plans/TOTOAI-AUDIT-4971-PACKAGE-20260810/4967-package-defect-checklist.md`.
The refreshed 4967 golden subsequently passed a separate full recomputation,
but its best observed score remains only 7/15. This is structural evidence,
not a claim that predictive quality is solved.

The three frozen recomputations, real 4951 offline replay, and full bank-4,980
sensitivity build are marked `heavy`/`research` and are opt-in/nightly. The
default release suite validates the same safety, objective, provenance and
golden contracts without rebuilding the full `3**15` surfaces. Commands and
marker policy are documented in `docs/testing.md`.
