# Pre-push review — TOTOAI-4996-4997-RECOVERY-20260904

Reviewed: 2026-09-04 (Europe/Moscow)  
Scope: read-only review of the actual uncommitted production tree at
`/Users/turshevr/toto-ai`; no fixes, staging, commit, push, scheduler mutation,
database write, or operational rerun was performed.

## Verdict

**NOT SUITABLE TO COMMIT OR PUSH.** The recovery contains three runtime contract
defects that require disposition, and the dirty tree is not a self-contained
commit boundary. The reported `2348 passed, 13 deselected` and Ruff result were
obtained from the dirty production tree and do not prove clean-checkout
reproducibility.

## Must-fix findings

### [P1] Existing retrospective output is accepted without the bound inputs or equal-input contract

Files:

- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py:206`
- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py:326`
- `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/retrospective_smoke_checks.py:16`

`validate_replay_report()` verifies the report self-hash, schema, drawing/plan,
four strategy names and safety flags, but does not verify:

- `inputs.final_input_sha256`, `probability_input_sha256`,
  `sports_artifact_sha256`, or `scheduler_plan_sha256` against the plan bindings;
- the baseline package hash against the issued quality-v2 archive;
- bank `4980`, stake `30`, coupon count `166`, or equal cost `4980`;
- the exact terminal result snapshot used for settlement.

`main()` skips generation whenever
`reports/research/4996-equal-input-replay/historical-hybrid-replay.json` already
exists, so a self-consistent stale report for the same drawing/plan is accepted
as completion. The smoke regression proves the gap: it deliberately constructs
a report with none of the inputs/bank/stake/equal-cost fields and asserts that
validation succeeds.

Reproduction/evidence: place that self-hashed minimal report at the expected
output path; `validate_replay_report()` accepts it and `main()` does not invoke
the replay. This violates the advertised exact equal-input/hash-bound
retrospective contract.

Required disposition: validate every producer input/hash and equal-budget field
before reusing a report; bind quality-v2 package bytes and the terminal result
snapshot. Add a failing regression for a stale same-plan report. This must be
resolved before the scheduled 4996 retrospective is relied upon.

### [P1] Fresh retrospective settlement is not bound to the canonical primary result snapshot

Files:

- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py:144`
- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py:192`
- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py:293`
- `/Users/turshevr/toto-ai/src/toto_ai/optimizer/quality_replay.py:264`

The primary state contains `result_snapshot_sha256`, but the runner validates
only its self-hash, drawing identity, status and package hash. It separately
checks that current `events` rows are terminal, then the replay loads the latest
complete `DrawingResultSnapshot` by drawing number. Neither path requires that
the replayed `actual` came from the snapshot named by the completed primary
state.

Reproduction/evidence: after a completed primary state, a later complete result
snapshot for the same drawing can become the replay loader's newest row while
the primary state still binds the earlier hash. The runner accepts both and can
settle a different result than the canonical post-draw run.

Required disposition: load and verify the exact
`primary.result_snapshot_sha256`, derive/compare the 15-outcome string from that
snapshot, and require the replay report to carry the same hash and actual value.
Do not use mutable/current terminal counts as the identity binding.

### [P1] Retry policy transition rewrites the plan but a retry child does not reconcile the loaded calendar

Files:

- `/Users/turshevr/toto-ai/src/toto_ai/runner/morning_dispatch.py:1057`
- `/Users/turshevr/toto-ai/src/toto_ai/runner/morning_dispatch.py:1081`
- `/Users/turshevr/toto-ai/src/toto_ai/cli.py:4625`
- `/Users/turshevr/toto-ai/src/toto_ai/runner/preflight_retry_scheduler.py:230`

The change correctly integrity-checks the old plan and atomically rebuilds it
when `activate_evening` changes. It does not guarantee that launchd will execute
the new attempt schedule. A transition discovered by a command launched from
the retry job has `preflight_retry_child=true`; the CLI explicitly suppresses
`prepare/install_preflight_retry_launch_agent()` for that child, and
`run_preflight_retry()` does not re-prepare or reinstall after the child returns.
The comment that the installer reconciles the loaded calendar is therefore not
true for the path that most naturally discovers the transition.

Reproduction/evidence: generate/install a non-activating retry plan, then let a
due retry child observe all remaining events as `timing_unknown`. The JSON plan
is replaced with activating commands and newly computed times, but the loaded
plist retains the old `StartCalendarInterval`; new earlier/different attempts
can be missed. Existing unit tests call `_update_preflight_escalation()`
directly and never assert candidate/installed/loaded calendar reconciliation.

Required disposition: make the parent retry runner safely reconcile the plan
and loaded calendar after a non-terminal child, or preserve calendar identity
across policy changes. Add an integration-level regression covering both
false→true and true→false transitions. Do not touch the already loaded 4997
primary/sidecar/watcher as part of that generic fix.

### [P1] The dirty tree is not a self-contained commit and cannot be validated by staging tracked files alone

Files/dependencies:

- `/Users/turshevr/toto-ai/src/toto_ai/cli.py:379` imports untracked
  `src/toto_ai/sports_stats/history_backfill.py`;
- tracked `/Users/turshevr/toto-ai/tests/test_scheduler_status.py:23` reads the
  untracked fixture
  `tests/fixtures/scheduler_status/drawing_4996_attempt_delivery.json`;
- committed `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/storage.py:46`
  calls `semantic_persistence_sha256()`, which is absent from `HEAD` and exists
  only in dirty `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/domain.py:469`;
- untracked `tests/test_sports_history_backfill.py` is the primary regression
  suite for the tracked CLI import;
- the retrospective runner/plan are ignored by `.gitignore` (`reports/`) and
  their smoke check lives outside ordinary `tests/` collection.

Evidence: production status shows the import/module/fixture/test split above;
`HEAD:src/toto_ai/sports_stats/domain.py` has no
`semantic_persistence_sha256`. A tracked-only commit would either fail CLI
import/tests or retain the already committed storage method dependency without
its implementation.

Required disposition: define separate coherent commits and verify each from a
clean checkout. At minimum, keep the preexisting storage/domain pair together;
keep CLI/history-backfill/tests together; include the scheduler-status fixture
with its test; and replace or deliberately version the ignored retrospective
implementation with an ordinary tested source artifact. Do not stage the tree
wholesale.

## Non-recovery / preexisting finding

### [P2] Rejected history-backfill input can mutate/create the database while the audit reports zero writes

File: `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/history_backfill.py:121`

This is preexisting unrelated work, not part of the retry repair.
`init_db(database)` runs before `_build_snapshot()` validates any manifest
snapshot. `init_db()` creates tables and applies missing-column migrations. A
valid outer manifest containing only an invalid snapshot can therefore create
or alter the database, then return a rejected audit with
`database_writes=inserted_count=0`.

Required disposition before committing the history-backfill slice: validate a
snapshot fully before opening the write-capable database, and either report
schema initialization/migration as a write or prohibit it in this importer.
Add a regression for non-`validate_only` all-rejected input against a missing
and an old-schema database.

## Change-set separation

Recovery-specific implementation/evidence:

- `src/toto_ai/runner/morning_dispatch.py` and the five new retry-policy tests
  in `tests/test_morning_dispatch.py`;
- bounded recovery checkpoint/guidance and the exact archived ACTIVE_PLAN;
- eight `prepared-recovery-4997-event-*.json` records plus their exact frozen
  snapshots;
- task handoff/evidence under
  `plans/TOTOAI-4996-4997-RECOVERY-20260904/`;
- ignored operational 4996 retrospective and 4997 scheduler/authorization
  receipts.

Preexisting unrelated dirty work:

- sports history backfill CLI/module/tests;
- semantic sports persistence method needed by committed storage;
- scheduler-status state-history changes and their fixture;
- pool-immaturity parsing, `com.cy` publisher handling and their tests;
- earlier schedule-evidence reviews/snapshots.

The ledger change is mixed: `HEAD` has 163 observations and the working file has
216. Only the final eight are this recovery's manual 4997 records; the preceding
45 appended observations are earlier work. All 53 appended ledger entries refer
to currently untracked review documents. Treating the 2,136-line ledger append
as one recovery change would silently bundle unrelated historical evidence.

## Verified read-only operational consistency

- Current 4997 scheduler plan is `45b72ac58a45958b`, drawing 4997/id12100,
  bank 4980, stake 30, deadline 2026-09-05 16:30 MSK, T-10 16:20 MSK.
- Primary and parallel authorization receipts bind the same identifiers and
  expire at T-10; `automatic_wagering=false` and
  `profitability_proven=false`.
- The current ignored watcher `latest.json` reports authorization present and
  `blocker=null`. The task-local `scheduler-status-4997.json` is an older
  pre-authorization snapshot; if committed as evidence it should be named or
  documented as such to avoid being mistaken for current state.
- The archived ACTIVE_PLAN hash matches
  `20116a609f62429441be5eb51d9818c11da06583cd92db95fcca100571aae24f`.
- The Sportschau snapshot used for recovery events 9/10 is a full La Liga round
  listing and does contain separate exact rows for Athletic Club—Atlético
  Madrid (14:15Z) and Rayo Vallecano—Racing Santander (16:30Z). Its event-9 URL
  is indirect/misleading, but the saved bytes do support the event-9 timing;
  this is not classified as false evidence.

## Verification limits and next checkpoint

No tests were rerun because this review was required to keep production
read-only, and the isolated worktree does not contain the dirty production
change set. The existing dirty-tree results are useful regression evidence but
not a clean-checkout proof.

Next concrete checkpoint: operational owner decides whether to repair/rebind
the 4996 retrospective before its first 2026-09-05 12:05 MSK run. After that,
fix and integration-test retry calendar reconciliation, then split the
preexisting slices and run clean-checkout focused/full verification before any
commit. Push/PR remains separately unauthorized; stored `origin/main` freshness
was not revalidated.

Automatic delivery note: a concise `send_message_to_thread` handoff to task
`019f7afa-72e2-7403-85cd-d05f408a4ef3` was attempted once and rejected by the
host policy because it classified repository-derived findings/paths as a
prohibited cross-task model transmission. No retry or workaround was attempted;
the operational owner must open this report directly or explicitly resolve the
policy boundary.
