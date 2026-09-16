# P2 — inactive feasible-seed repair proof

Task TOTOAI-RESUME-20260915 · 2026-09-15T21:33:20.788478+03:00

## Scope and contract
- Only two new files: research helper and tests. No native optimizer/production default, scheduler, Sports, DB/raw, consent or ACTIVE_PLAN edits. P0/P1 source/tests remain byte-identical to their receipt.
- Input fingerprint binds source attribution, normalized probability models, candidate and control order, constraints, bank/stake, category and seed. The demo verifies source attribution against its immutable R1 input; the pure helper does not invent or certify source availability.
- Start from a complete feasible control. Deterministic one-out/one-in proposals; each accepted state remains uniqueN and within all integer exposure bounds. Search objective is lexicographic worst then mean sampled coverage. No calibrated-probability or independent/exact non-degradation promise.
- Explicit proposal/accepted/candidate/time limits and progress. Cooperative timeout returns the EXACT original control, even after earlier accepted swaps. No claim of global or multi-swap optimality.

## Tests
- RED reproduced before code. **10 new tests;36 combined tests PASS,0.42s; Ruff PASS.**
- Feasibility/cardinality/budget through every accepted intermediate state; tiny complete candidate universes; feasible-control greedy-dead-end counterexample; deterministic results; strict objective improvement; unchanged reason when no feasible improvement; timeout before/after acceptance; source/fingerprint/budget rejection.

## One frozen-input demonstration:4999
- No actual outcome labels read. Same327candidate union/control166/4980/30. **20accepted swaps;465proposals;11net new coupons,155sharedwithcontrol.**
- Stop:ACCEPTED_CHANGE_BUDGET_EXHAUSTED;search3.526s,totalwithbothindependent/exactevaluations5.014s. All21seed/acceptedstates independentlycheckedfeasible.
- Optimization worst/mean:[0.0082, 0.009366666666666667]→[0.0087, 0.009866666666666666]. Limits:10k samples/model,512candidatecap,2000proposals,20acceptedchanges,30ssearch;90souterdemobound.
|Model|ExactP13before%|ExactP13after%|Delta percentage points|Independentbefore%|Independentafter%|
|---|---:|---:|---:|---:|---:|
|bk|1.091493|1.110734|+0.019241|1.100|1.090|
|flatten_10|0.987851|1.004623|+0.016772|1.060|1.120|
|flatten_20|0.894435|0.909008|+0.014574|0.890|0.880|

**Small positive exact model delta, mixed independent sample changes. No proven real-world13+ gain.** This remains a known-input, unknown-quote-asof SCENARIO. No retuning or secondattempt performed. Original R1/truepredraw archives unchanged.

## Files
- `/Users/turshevr/toto-ai/src/toto_ai/research/feasible_robust_exchange.py`
- `/Users/turshevr/toto-ai/tests/test_feasible_robust_exchange.py`
- [Machine receipt/source hashes](/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/P2-feasible-seed-repair.json)
- [bound-input.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P2-feasible-seed-pilot-4999/bound-input.json)
- [result.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P2-feasible-seed-pilot-4999/result.json)
- [summary.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P2-feasible-seed-pilot-4999/summary.json)

## Handoff
Independent review is next. The module is not wired to any production caller. Publication/canonical-memory updates belong to the parent/finalizer. No running owned commands.
