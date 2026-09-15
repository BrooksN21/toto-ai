# Runtime candidate — frozen for independent review

Task: `TOTOAI-4998-PARALLEL-INTEGRATION-20260906`. Frozen 2026-09-06T18:47:59.099993+03:00. No publication/self-ACCEPT.

Patch SHA256: `ce96d1f2f2888eb77359cb659a7ed59846b66c3b9d407cfb56300baf60cc97de`

## work_summary

- Exact coverage-membership cache removes repeat membership scans in unchanged quality-repair states; same original masses/fsum, candidate evaluations, order and all scoring/category/budget definitions.
- Optional-work control now reuses ordered primary coupons only after native actionable export + strict revalidation of current operator/hash, CSV/archive/input/plan/bank/config/provenance/consent. Category metrics are independently recomputed. No arbitrary TXT cache and no source probabilities inferred from report rows.
- Deadline now reaches EV crowd chunks, FFT boundaries, full ranking and repair loops through an opt-in context-local scope. Defaults remain unbounded for unrelated callers; no selection-budget cuts. Phase/checkpoint wall+CPU/counts persist and flush locally.
- Completed research packages/ranking survive later failure. Both PLAY and NO_BET deadline exits write terminal status. Fresh primary is checked again before publication; publication rechecks clock around its own writes and removes only its newly-created late artifacts. Primary is never changed.

## Exact measurements — not a19-minute-fixed claim

| Measurement | Before | Candidate |
|---|---:|---:|
| Exact final4998 control EV, cProfile wall |84.439s|76.697s|
| Same quality-repair wall |20.958s|14.932s|
| Swap evaluations |40960|40960|

Every StrategyResult field except runtime was identical, including ordered coupons/hash and exact P13/P14/P15. Dominant original sampled work:7 FFT convolutions47.743s plus crowd DP11.367s; repair20.926s cumulative.

One complete genuine final-input offline research comparison: **198.859s**, parent CPU165.923s; control70.969s, Sports70.154s, quality-v3 18.223s, robust4.489s, G1 wall32.384s. N166, quality-v3 candidates14120, union465,4models. G1 REFINED,49634 evaluations,1swap, engine30.771s; selected family remains quality-v3. Sports-shadow remains rejected by policy for BK P13/P14/P15, concentration and worst-model non-improvement; raw candidate eligible flags are NOT final policy eligibility.

**No primary cache was used in that replay:** both EV calls were really recomputed. No post-expiry actionable operator was reconstructed or authority validator bypassed to claim a live reuse measurement. Reuse positive fixture uses synthetic native CSV/hash records and mocks the provenance validator; malformed bindings/provenance and live-clock publication races have focused regressions. Full live same-input authorization/reuse path still needs independent assessment; its avoided EV call is contract-tested, not measured under original Background execution.

The historical launch was Background, included106.887s waiting for primary,804.309s serial EV and G1 timeout52.684s. Foreground replay differs in QoS/host state and G1 completes instead of timing out. Exact cause/share of historical6–8x slowdown is not established; **do not label198.859s an apples-to-apples end-to-end speedup caused entirely by this patch**. All control/Sports bytes+P13/P14/P15 and quality-v3 package match archived final; refined robust/full reports need not match historical G1 fallback.

## Verification

- Initial red:5 failures. Additional NO_BET deadline reproducer:1 failure. Final focused command: **58 PASS in1.86s**; Ruff10filesPASS.
- Logs: `runtime-fix/red-tests.log`, `no-bet-red.log`, `final-tests.log`, `final-ruff.log`.
- Profile: `runtime-fix/profile_ev.py before baseline180`, then `after baseline180`; cProfile `.prof` and JSON/log receipts retained. Both actual processes exit0.
- Full replay: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<task>/runtime-fix/guard:src .venv/bin/python -u <task>/runtime-fix/full_replay.py`; deadline360s/outer420s,10s progress, exit0. Guard blocks API/DB/protected writes and allows only native local G1 subprocess. No operator generation/publisher was called.
- Final focused pytest paths: runtime-budget, runtime-contract, G1 integration, sidecar, plus6 specific existing EV/strategy/quality/ranking tests. Exact shell command is in this task history; no broad100/500/full-suite loop.
- Last post-replay deltas are NO_BET timeout handling, fresh-primary recheck and extra counters/cooperative checks; scoped tests cover them. No further long runs per owner.

## Changed paths

- `src/toto_ai/sports_stats/final_hybrid_comparison.py`
- `src/toto_ai/optimizer/strategy_comparison.py`
- `src/toto_ai/sports_stats/final_hybrid_sidecar.py`
- `src/toto_ai/ev/ternary.py`
- `src/toto_ai/ev/package.py`
- `src/toto_ai/ev/package_quality.py`
- `tests/test_final_hybrid_g1_integration.py`
- `src/toto_ai/ev/runtime.py`
- `tests/test_ev_runtime_budget.py`
- `tests/test_final_hybrid_runtime_contracts.py`
- `knowledge/parallel_runtime.md`

## Immutable review inputs / limits

- `PARALLEL_RUNTIME_IMPLEMENTATION.patch` and `PARALLEL_RUNTIME_IMPLEMENTATION_MANIFEST.json` (exact before/after hashes and dependency hashes). Standalone frozen files under `runtime-fix/candidate/`.
- Full receipt: `runtime-fix/full-replay-20260906T154104Z/receipt.json`; measured source hashes retained separately. Research-only, never for wagering/upload.
- Five protected plan/consent/sourceCSV/final-input file hashes match prior verified evidence. No4998 archives/DB/LaunchAgent/wrapper/calendar changes. No source outside assigned runtime/EV/test scope; knowledge note only.
- Deadline remains cooperative during a single native NumPy kernel; cutoff publication checks remain independent. This is not a hard OS CPU-preemption guarantee.
- `scheduler_status.py` and DELIVERY/OBSERVABILITY fixes are untouched. Reported7 delivery negative-test failures belong to Leibniz; no cross-edit/acceptance claim.
- No active owned process/session; no stage/commit/push/PR. Next: independent review of this exact frozen candidate, then separately authorized finalization.
