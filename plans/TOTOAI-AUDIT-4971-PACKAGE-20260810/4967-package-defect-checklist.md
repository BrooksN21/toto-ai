# Drawing 4967 package-defect checklist

This is a structural remediation checklist, not a predictive-quality claim.
The frozen quality-v2 package's observed best result is still only **7/15**;
there is no proven edge and every current release decision is `NO BET`.

| Original finding | Implementation | Contract/evidence | Status |
|---|---|---|---|
| Material outcomes had zero/one coupon | Continuous configurable `floor(K*s*p**alpha)` exposure bounds, per-event feasibility checks, global fail-closed repair | `test_continuous_exposure_floor_is_monotonic_and_sum_feasible`, threshold/boundary and infeasible tests; 4967 golden minimum exposure 5 | **PASS (structural)** |
| Many events crowded at hard cap 157/166 | Existing hard veto retained; configurable soft headroom is optimized before quality and violations are reported | headroom selector test; 4967 maximum 151/166 with zero headroom violations | **PASS** |
| Pathological close-Hamming clustering | Deterministic incremental swap repair penalizes close pairs and reports distance distribution/effective pattern count | diversity, deterministic, incremental-equivalence and fast golden tests; close pairs 2163→1177, mean distance 3.782183→4.620518 | **PASS (measured on frozen package)** |
| Objective did not represent high-hit package outcomes | After safety/headroom, true lexicographic P13+→P14+→P15→independent-MC P9+→diversity→robust EV, with explicit deadbands | comparator hierarchy/no-compensation tests and category-union tests | **PASS (modeled objective only)** |
| Probability 0.20 created a selection cliff | No 0.20 selector branch; named IEEE-754-then-floor boundary policy | monotonic/metamorphic checks at 0.199999/0.20/0.200001 and epsilon-boundary test | **PASS** |
| Unvalidated payout assumptions could imply action | Gross payout remains a model diagnostic only; no trusted prospective evidence registry exists | CLI/runner/report/scheduler release-gate tests and 4967 golden honesty test | **PASS: `NO BET`, `TRAINING/PAPER`** |
| Package was not bound to exact inputs/config | Snapshot/input/ledger/plan bytes and semantic hashes plus a canonical selection context bind bank, stake, requested/effective capacity, EV threshold, concentration thresholds, safety/provenance flags, and complete quality-v2 config/RNG/release protocol | `test_bound_selection_context_mismatch_fails_closed`, incomplete-plan, SchedulerPlan/manifest mismatch, provenance mutation, and golden hash contracts | **PASS (exact equality + hash; fail closed)** |
| Bank/count behavior was fixed to 166 | Exact count is `bank // stake`; regressions cover 4980/30=166, 9960/30=332 and 2500/25=100 | dynamic-count test and explicit nested-set category monotonicity test | **PASS**, with limitation below |
| Structural success or a legacy injected package could be exposed as wager-ready `PLAY` | Current top-level/public decision is always `NO BET`; feasibility is `STRUCTURAL_PASS`; coupons are paper artifacts. One shared EV-run sanitizer protects direct EV CSV/Markdown export, `DrawingRunnerResult`, runner report publication, orchestration and CLI. Actionable coupon CSV remains header-only; retained rows appear only in a labelled training/paper Markdown section | `test_direct_ev_writer_sanitizes_injected_play_to_training_paper`, legitimate `STRUCTURAL_PASS` writer regression, model/direct runner writer, publication, CLI/orchestration/manifest/scheduler contracts | **PASS (EV + runner report boundaries fail closed)** |

## Explicit limitations

- Independent optimization at two bank sizes is deterministic but is **not**
  guaranteed to produce strict prefix-nested packages. Monotonic category-union
  probability is guaranteed and tested for explicitly nested coupon sets; it
  must not be inferred for unrelated optimized hashes.
- The frozen 4967 result (best 7, mean 2.518072, no 13/14/15 hit) is poor.
  Structural repair and larger modeled category unions do not establish
  calibration, profitability, or a real-money release basis.
- Full-surface frozen recomputation and full bank-4,980 sensitivity timing are
  retained as opt-in/nightly `heavy` research tests. Release tests consume
  their hash-bound golden artifacts without rebuilding `3**15` surfaces.
