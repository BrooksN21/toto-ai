# G1 main integration — APPLIED; one Ruff blocker

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Exact accepted9-file patch applied,
not a new review/feature. Source review: ab34 G1_FINAL_INDEPENDENT_REVIEW.md ACCEPT.
Patch SHA256 `f22702a748bb7c1ad091405956d649b5255064f449ee2d16a49db65d2a5d2b5c`.

## Result

- All9 before hashes matched. `scripts/project-git apply --check
  --whitespace=error-all` PASS, then exact patch applied without staging/commit.
- All9 after hashes match author receipt before AND after tests.
- CLI applied only the2 approved hunks; never copied isolated cli.py. Existing
  main backfill wiring retained. Atomic cache candidate was not applied.
- **96 targeted main tests PASS in4.87s** (9 test files,25s bound): G1 caller,
  contract/acceptance, sidecar/retry, parallel challenger, settlement and scheduler
  readiness/status. All TotoAI runtime imports attest current main paths/hashes.
- Ruff on all9 changed files: **one I001**, at
  `tests/test_final_hybrid_g1_integration.py:1`. The new ParallelG1Config import
  is outside the main-config ordered first-party block. No noqa/config/source
  changes or silent import cleanup; exact accepted bytes remain unchanged.
  Thus integration is APPLIED, not fully lint-green or finalization-complete.
- Protected7 hashes unchanged: GOAL API, schedule collector,90min research helper,
  cache collector, primary scheduler, scheduler status, exact4998 scheduler plan.
  No live DB/provider/source collection, auth/seed/jobs, wrapper/LaunchAgent,
  scheduler prepare/reuse, setup, activation or push operation.
- Test writes restricted to disposable fixtures; network/SQLite prohibited;
  local worker subprocesses restricted to this Python. No owned process remains.

## Next / boundary

Only remaining implementation disposition: a separately authorized minimal
import-order cleanup of that test under current-main Ruff, followed by pertinent
verification. Do not reapply the9-file patch. Cache composition and operational
G1 flag/seed enablement remain separate; default-off integration is not activation.
Prepare/reuse still does not parse the standalone flag: do NOT rerun setup.
No claim of fresh final4998 refinement, Sports-v3 training or profitability.

Exact before/after/protected hashes, command outputs, runtime imports and audit
harness are in G1_MAIN_INTEGRATION_RECEIPT.json next to this handoff.
