# Corrected failed-cache independent rereview — REQUEST CHANGES

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Frozen full replacement only:
`f817f2d6a986c4c06c824500e0cb78441928a94a5db839197a1435eb1062368f`.
No application, candidate edits, API/DB/jobs/seed/authorization/main-memory changes.
Original rejected patch, prior report and exact8 independent probes preserved.

## What is fixed / verified

**All previous8 probes PASS**, including both previously failing recovery cases.
Eight additional candidate delta cases PASS: intact-claim crash recovery; hourly
120-request reservation cap/window reopening; conservative quota accounting;
terminal source budget; lock exclusion past lease expiry; truthful structured
status/CLI AST wiring; concurrent callers; terminal deadline. Total16 PASS.
Current module-only temporary overlay uses main for every other TotoAI import;
CLI is inspected as exact reconstructed AST, not executed. Existing safeguards
and main publication paths are not bypassed. Ruff4 PASS. Subprocess bounds25s
for tests/15s Ruff; network/SQLite/outside-temp test writes denied, zero attempted.

## Remaining P1: crash-safe publication missing

Two **new independent probes FAIL**. A process interruption immediately after
creating either `attempt.json` or `outcome.json`, before its first write, leaves
an empty final-name file. This is an actual reachable write window, injected
through Path.open on synthetic fixtures, not arbitrary corruption of a completed
artifact. At08:45, after the08:15 attempt lease expired, a recovered provider is
never called: parsing fails with JSONDecodeError at candidate lines207 /248.
The unknown-error adapter then marks that state non-retryable. Thus a narrower
crash path still produces permanent manual repair instead of unattended recovery.
The existing crash test interrupts only after a complete claim was written.
No live process was killed and no real artifact was damaged.

Smallest targeted correction: crash-safe immutable publication of retry control
records (claim/outcome and retry completion marker). Write complete records to a
separate staging name, publish atomically without overwriting committed evidence,
and reserve before any collection. Incomplete unpublished staging data must not
masquerade as a committed malformed record; preserve evidence, lock exclusion,
full unknown-request reservation and quota/cooldown accounting. Do NOT simply
ignore invalid committed JSON or weaken integrity checks. Extend fault injection
to claim/outcome/completion publication boundaries; rerun the exact previous8
plus focused delta cases, not broad119/183 suites.

## Independent current-main compatibility blocker

First strict manifest guard PASS4 targets/49 dependencies. Before testing, a
concurrent authorized source worker changed two dependencies; strict recheck
correctly blocked. We did not apply or waive that guard. Exact candidate target
before/after hashes still reconstruct; diagnostic tests used current main bytes:

- `src/toto_ai/sports_stats/goal_probe_research.py`:
  expected590d2eea… → actual73f2c05d…;
- `tests/test_goal_probe_research.py`:
  expected8d7b34f1… → actualc0cf0f85….

Current GOAL API026e3936… and collector51901ca5… remained as pinned. No further
file changes observed during the diagnostic run. A separately refreshed manifest
and guard are necessary before any adoption; this is not permission to overwrite
newer score-authority work or an independent acceptance of that work.

Final result: **2 FAIL /16 PASS**, Ruff4 PASS; no acceptance/live-refresh approval.
First own-probe E501 was fixed only in the review file; initial/final logs retained.
Next checkpoint: narrow atomic-publication correction and fresh dependency guard.

Artifacts in this directory:
- FAILED_GOAL_CACHE_CORRECTION_INDEPENDENT_REVIEW.json: full exact hashes,
  changed-dependency evidence, commands, audit harness, import attestation and logs.
- test_failed_goal_cache_correction_review.py: two independent publication-crash probes.
