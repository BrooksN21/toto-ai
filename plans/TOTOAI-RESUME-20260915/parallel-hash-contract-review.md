# Independent review: parallel report hash contract

- Task: TOTOAI-RESUME-20260915.
- Reviewed at: 2026-09-15T18:15:12.008138+03:00.
- Verdict: **PASS within the supplied hash-contract fix scope**. No blocking findings.
- Role: independent execution reviewer; no delegation, publication, operation or model calculation.
- Exact five source/test SHA-256 values match `parallel-hash-contract-fix.json` at completion; review excludes simultaneous C changes.

## Verified contract

1. Native StrategyResult writer (`src/toto_ai/optimizer/strategy_comparison.py:605`) is ordered UTF-8 with a terminating LF after each coupon. Both recomputed control and verified-primary reuse go through `_strategy_result`, preserving that domain. Comparison `_result_payload` (`src/toto_ai/sports_stats/final_hybrid_comparison.py:1039`) retains it and labels a separately computed ordered comma hash.
2. `src/toto_ai/package/hash_contract.py:29` validates BOTH distinct domains against exact ordered control coupons/archive. There is no accept-any-hash OR fallback. Legacy compatibility is limited to the known native schema-1/artifact-class with semantic fields absent; explicit null/unknown or partial metadata does not silently become legacy. Byte-level report/export hashes remain separate.
3. Delivery (`src/toto_ai/operations/scheduler_delivery.py:217`) preserves the sealed report, actual report bytes, immutable plan/drawing, final-input, archive, control bytes, selection and ranking checks. ASCII-space parsing matches native semicolon export; duplicate and empty operator packages are rejected.
4. `delivery_status` isolates parallel rejection and retains verified primary readiness; no release gate or deadline is weakened.

## Independent evidence

- Fresh bounded pytest: `tests/test_parallel_hash_contract.py tests/test_scheduler_delivery.py tests/test_scheduler_status.py`: **84 passed in 2.88 s**; exit 0.
- Fresh targeted Ruff on all five changed Python files: **PASS**.
- Eight additional memory-only negative checks passed: wrong legacy schema/class, partial metadata, explicit null, and comma/concatenated/non-terminated-LF substitutions.
- Native writer -> delivery positive tests: `tests/test_parallel_hash_contract.py:73`, current and legacy.
- Foreign final input/plan/report hash, coupon tamper, alternate hash and unknown semantics preserve only actionable primary: `tests/test_parallel_hash_contract.py:93`.
- Ordered multiple-coupon tamper/reorder including recomputed archive digest: `tests/test_parallel_hash_contract.py:102`.
- Native spaced export and duplicate rejection: `tests/test_parallel_hash_contract.py:126`; explicit-null rejection: line 139.
- Full input/report/archive/control substitution fixtures: `tests/test_scheduler_delivery.py:767`; primary-fallback regression also at lines 308, 379, 544.

## Activation handoff — not executed

Restart **only the already-running observer label** `com.totoai.status-watcher.v1.84b0f69e06487848` after parent-controlled publication/activation. `scheduler_status` imports `delivery_status` once, and its loop does not hot-reload; source publication alone cannot update an already-imported watcher.

Future scheduler/parallel CLI invocations are fresh Python processes and will load the new source. No plan, consent, evidence, package rewrite, scheduler label reinstall or generation restart is required for this patch. Do not interrupt an already-running generator merely to activate it. Parent should separately verify watcher freshness/PID and the same plan after activation.

## Limits

No operational 5007 validation, current process inventory, live package calculation, remote publication, code edits or watcher restart performed in this review. Existing runtime artifacts were not written. No PLAY or predictive-quality assertion. The author's unchanged 166-coupon archive4999 receipt was read but not independently replayed in this bounded review; independent tests above use synthetic temporary fixtures and native writer/parser functions. This is not a whole-evening runtime guarantee.
