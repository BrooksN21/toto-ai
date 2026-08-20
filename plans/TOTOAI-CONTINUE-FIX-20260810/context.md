# TOTOAI-CONTINUE-FIX-20260810 Investigation Report

## Scope/constraints

Static, local-only investigation of `/Users/turshevr/toto-ai`. No tests were rerun; no network, runtime, generated artifacts, source files, or repository state were modified. `AGENTS.md` and all seven `memory-bank/` files were read. The handoff evidence is authoritative.

## Git/PR/commit state

- Branch: `feature/initial-toto-ai`
- Local and `origin` tracking refs: `800b0daf2041d8980f1ccec2b4339a6975f332cd`
- No tracked or staged changes.
- Only pre-existing unrelated untracked evidence/plan directories were present.
- Commit `800b0da` changed the CLI, scheduler, tests, and memory; its message claims ledger path/hash plan binding and terminal integrity classification.
- Local metadata cannot establish whether GitHub PR #3 remains draft or determine current checks, reviews, or server state.

## Scheduler fix assessment and explicit merge verdict

Positive wiring is present:

- The scheduler resolves the default ledger under `plan.project_root` and supplies an absolute `--schedule-evidence-ledger`.
- `prepare-drawing` resolves and forwards the option.
- Scheduler subprocesses run with `plan.project_root` as `cwd`, making default resolution canonical.
- Tests cover generated argv and CLI forwarding.

The systemic guarantees claimed by the commit are absent:

- `SchedulerPlan` contains neither the ledger path nor its content/semantic hash.
- Ledger identity is excluded from `semantic_payload` and `plan_id`.
- Plan loading does not bind ledger identity.
- Execution re-derives a mutable default path instead of consuming a plan-bound path and hash.
- Replacing or changing ledger contents therefore leaves `plan_id` unchanged.
- Every nonzero `prepare-drawing` exit is classified as transient `preparation_unavailable`; missing, malformed, or mismatched ledger failures are not proven permanent integrity failures.

**Merge verdict: PR #3 is NOT ready to merge.** Exact forwarding is fixed, but immutable plan binding and permanent integrity classification remain incomplete.

Previous memory records 32 focused tests, 1,648 full tests, Ruff, diff-check, and a live non-betting 15/15 readiness check. This investigation did not rerun them.

## Drawing 4967 package evidence

The retrospective reports a completed frozen pre-cutoff model, 166 rejected candidates, zero uploadable coupons, and an expired/non-actionable drawing.

The manifest records:

- Decision: `NO BET`
- `model_supported=true`, `model_warning=null`
- Playable timing
- Matching probability-input hash `926af...` across safety and provenance/final input
- Package hash `6854f...`
- Uploadable coupons: `0`

This establishes internally consistent inputs, not probability calibration.

Extreme concentration among 166 coupons:

- Event 2, `X`: 166/166 = 100%
- Event 5, `2`: 163/166 = 98.1927710843%
- Event 6, `1`: 158/166 = 95.1807228916%
- Event 7, `X`: 158/166 = 95.1807228916%
- Event 12, `2`: 166/166 = 100%
- Event 14, `2`: 166/166 = 100%

All 17 material outcomes with zero exposure, using the inclusive `p >= 0.20` threshold:

- E1 `1`, p=.27
- E2 `1`, p=.30
- E2 `2`, p=.39
- E3 `2`, p=.35353535353535354
- E4 `1`, p=.42
- E5 `1`, p=.29
- E6 `2`, p=.40594059405940597
- E7 `1`, p=.2376237623762376
- E8 `2`, p=.494949494949495
- E9 `1`, p=.39
- E10 `1`, p=.45
- E11 `2`, p=.29
- E12 `1`, p=.39
- E12 `X`, p=.33
- E14 `1`, p=.37
- E14 `X`, p=.27
- E15 `1`, p=.38

Safety rejects maximum share `>= .95` and zero exposure for any outcome with probability `>= .20`; any violation produces `NO BET` and an empty uploadable package.

## Classification/root cause

Drawing 4967 was **correctly rejected under the current product contract**. There is no evidence of malformed or hash-drifted probability input, generator mathematics failure, or proven calibration quality.

The capability gap is the selector: it ranks coupons deterministically by EV, takes all eligible coupons, then truncates to the configured maximum without exposure or diversity constraints. The final safety gate correctly vetoes the resulting unsafe package but cannot construct a safe alternative.

Safety must remain the final publication veto.

## Minimal safe next implementation

Scheduler completion:

- Add canonical ledger path and content/semantic hash to `SchedulerPlan`, serialization, and `plan_id`.
- Make execution use the exact plan-bound path.
- Validate file presence, format, and hash before provider/package work.
- Classify missing, malformed, mismatched, or immutable-pin conflicts as permanent `SchedulerIntegrityError`.
- Keep network, quota, TLS, and refresh failures transient.
- Bump the schema if necessary; do not silently reinterpret schema v5.
- Fail legacy plans closed.

Package-selector follow-up:

- Preserve the unchanged final `evaluate_package_safety` veto.
- Add deterministic, bounded safety-aware repair/reselection over the complete EV ranking before publication.
- Begin with the top-EV package, replacing its lowest-ranked coupons with the highest-ranked eligible unselected coupons that reduce safety deficits.
- Preserve uniqueness, bank/stake limits, and minimum gross EV.
- Require exposure for every outcome with `p >= .20` and maximum shares strictly below `.95`.
- Use deterministic tie-breaking and bounded search.
- If no safe package is found, retain zero-cost `NO BET`.
- Do not claim global optimality or weaken safety.

For 166 coupons, strict `< .95` permits at most 157 occurrences of a dominant outcome; a count of 158 fails. A fixed event therefore needs at least nine alternatives, although one replacement may improve several events.

## Regression/backtest acceptance criteria

Scheduler regressions:

- `plan_id` changes when ledger path, bytes, or semantic hash changes.
- Path/hash serialize and round-trip exactly.
- Command path equals the plan-bound path.
- Changed, missing, or malformed ledger after plan creation fails before provider/package work and is permanent.
- Immutable pin conflicts are permanent.
- Transport refresh failures remain transient.
- Legacy schema fails closed.

Package regressions:

- Exact frozen Drawing 4967 package/probability fixture.
- Drawing 4952 unsafe fixture.
- Already-safe control remains unchanged.
- Infeasible synthetic input remains `NO BET`.
- `.20` probability boundary is inclusive.
- `.95` share boundary is rejected.
- N-dependent count arithmetic is correct.
- Deterministic ties and hashes.
- Uniqueness, budget, and minimum-EV invariants.
- Existing final-gate and tamper checks remain unchanged.

Backtest requirements:

- Use frozen pre-result chronological or walk-forward data and configuration.
- Prevent result access before package hashing.
- Compare the current unconstrained-selector-plus-veto baseline with the safety-aware selector.
- Measure safety-pass/`NO BET` rate, package size and cost, modeled EV loss, exposure, Hamming/category coverage, and realized 9–15 hits only after freezing.
- Predeclare non-inferiority and acceptance thresholds.
- Evaluate a blinded holdout and retain full provenance.
- Make no profitability claim without payout evidence.
- Before commit, run focused tests, full `pytest`, Ruff, and diff-check.

## Uncertainty

No network verification was performed, so current PR #3 status, reviews, checks, and remote divergence are unknown. Existing verification results were read from project memory but not independently reproduced. Input consistency is supported; probability calibration, safe-package feasibility for Drawing 4967, and profitability remain unproven.

## Files inspected

- `AGENTS.md`
- All `memory-bank/*.md`
- `.git/HEAD` and relevant local/remote refs
- Commit `800b0da` diff/stat
- `src/toto_ai/runner/scheduler.py`
- `src/toto_ai/cli.py`
- `src/toto_ai/package/audit.py`
- `src/toto_ai/ev/package.py`
- `src/toto_ai/ev/drawing.py`
- `src/toto_ai/runner/final_input.py`
- `tests/test_runner_scheduler.py`
- `tests/test_scheduler_operational_artifacts.py`
- `tests/test_sync_prepare_cli.py`
- `tests/test_systematic_resolution_e2e.py`
- `tests/test_package_audit.py`
- Specified retrospective manifest and report
- Scheduler plan, final input, and runner report as supporting frozen provenance