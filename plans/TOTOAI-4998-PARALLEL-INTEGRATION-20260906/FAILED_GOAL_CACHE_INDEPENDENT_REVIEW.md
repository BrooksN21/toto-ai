# Independent failed-GOAL-cache review — REQUEST CHANGES

Task `TOTOAI-4998-PARALLEL-INTEGRATION-20260906`. Review only; candidate not applied.

## Blocking finding

**P1 — one-ever retry is a permanent recovery dead end.** Candidate
`src/toto_ai/sports_stats/goal_probe_collection.py:86–87,111–116` rejects every
subsequent call after either a failed retry report or an interrupted/exceptional
retry claim. The900-second cooldown only gates the first retry; it never restores
eligibility. A recovered provider and later time therefore cannot recover the
same drawing/output root without manual intervention. This changes “cached failure
forever” into “one chance, then failure forever”; it does not meet the requested
systematic unattended preparation requirement. A different new drawing/root gets
its own allowance; the finding is not a global lock across drawings.

Two independent no-network probes simulate a failed source / exception at08:15,
then provider recovery at09:00 for the same original08:00 marker. Both expected
recovery tests FAIL, before invoking the recovered provider stub:
- `GOAL probe retry exhausted: source failed`;
- `GOAL probe retry already claimed; no usable replacement cache`.

**P2 — consumer status remains misleading.** Current main
`src/toto_ai/cli.py:4444–4453` records `PAPER_ONLY_COLLECTION_FAILED`,
`retryable=true`, primary unaffected for all exceptions. The newly permanent
claim condition is therefore advertised as retryable even when no later call can
attempt collection. This is a candidate/current-consumer contract mismatch,
not an allegation that the candidate edited CLI. Raw failed records are retained,
but a crashed attempt remains `RESERVED_ONCE` without terminal error/next-retry
state. The explicit new-output manual route does not resolve automatic recovery.

## Smallest targeted revision and acceptance probes

Keep the same ensure boundary, immutable original/capture files and successful
replacement reuse. Replace the lifetime single claim with narrowly scoped
append-only attempt generations: one live exclusive attempt, explicit bounded
in-progress lease, outcome and next-eligible time. After transient failure or
expired interrupted attempt, allow one fresh attempt per eligible invocation,
with cooldown measured from the latest attempt. Do not run an internal retry loop,
reset provider quota, or erase failed evidence. Enforce request and cumulative
quota/window limits; actual terminal limits must be explicitly non-retryable.
Expose retryable/terminal reason and next-retry time honestly to the existing
caller (a narrow caller adjustment may require separately assigned scope).

Required probes: failure → cooldown/no-call → provider recovery/new immutable
capture; interrupted claim → still-active/no-duplicate → expired/recoverable;
concurrent callers get one attempt; quota/budget gates survive failed attempts;
terminal status is not retryable; successful/full/partial/zero-match reuse retains
original capture timestamps and hashes. No arbitrary recapture time can label
old bytes fresh. Do not just increase a lifetime retry count or delete claims.

## Evidence and retained safeguards

- Exact patch SHA256:
  `3780eefccbabbb39b37c7de5bc69651fcc8c8decd43f5bef7bd068f26c4409fa`.
- Read-only verifier:3 targets/49 dependencies, expected HEAD
  `1a42f35561416393d5e9068fde330ca54e7466e7`, READY_FOR_MAIN_APPLY mechanically;
  **that is byte compatibility, not review acceptance**. Before/dependency hashes
  remained unchanged after the first test run; no source-writing command was used.
- Reconstructed exact candidate module only; every other imported TotoAI module
  came from main, including GOAL026e3936… and collector51901ca5….
- **2 failed,6 passed** independent tests;25-second subprocess bound.
  Six passes cover valid full/partial/zero-match/partial-conflicts reuse, exact
  900-second boundary, caller budget propagation, old-byte immutability, truthful
  capture-time reuse and hash-corruption rejection.
- Ruff3 PASS: exact candidate module, exact candidate tests and own review probes.
  First own-probe formatting diagnostics were fixed only in the reviewer file;
  both initial and final logs remain in JSON. Candidate bytes unchanged.
- Network/SQLite/live writes forbidden by audit harness; no blocked action was
  attempted in the completed test runs. One formatting-rerun setup encountered
  audit-denied dir_fd-relative cleanup of reused temporary pytest fixtures; its
 8 setup errors/log are retained separately. A new disposable basetemp resolved
  the harness issue without weakening the guard; final2 FAIL/6 PASS reproduced.
  Writes during tests confined to disposable synthetic fixtures.
  No DB, jobs, authorization, pinned seeds, main memory, Git index or source edits.

This review does not independently approve the separately reviewed GOAL quarantine
implementation and does not claim fresh real-world coverage. No API refresh or
main adoption is authorized by this verdict. Next checkpoint: corrected candidate
and the focused recovery probes, not another historical suite.

Artifacts (same directory): `FAILED_GOAL_CACHE_INDEPENDENT_REVIEW.json` contains
hash manifest, exact harness, commands, import attestation and full logs;
`test_failed_goal_cache_independent_review.py` contains independent review probes.
