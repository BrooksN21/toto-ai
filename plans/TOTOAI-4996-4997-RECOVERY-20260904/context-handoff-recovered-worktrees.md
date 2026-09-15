# Recovered worktree context — TOTOAI-4996-4997-RECOVERY-20260904

Saved: 2026-09-05T13:52:55.141432+03:00. Context worker `01a07102-7504-74d2-8ed2-147f9c2e3367`;
all shell cwd `/Users/turshevr/toto-ai`. CONTEXT ONLY; no implementation or new plan.
Read only current ACTIVE/registry and the two specified reports. No noon recovery,
wrapper test, source, DB, scheduler, app-task or Git re-audit. Copies plus this handoff
and provenance are the entire write scope; original worktrees remain untouched.

## Saved work exists; active author tasks are NOT known
- Review source: `/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904-PRE_PUSH_REVIEW.md`.
  Title/task key `TOTOAI-4996-4997-RECOVERY-20260904`; reviewed Sept4 MSK;
  file mtime2026-09-04T23:44:47.415751+03:00. No author thread ID stated.
  The only native task ID in it, `019f7afa-72e2-7403-85cd-d05f408a4ef3`, is the
  destination of a rejected historical delivery attempt, NOT the review author's ID.
- Models source: `/Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/MODEL_READINESS_REPORT.md`.
  Observed2026-09-04T23:35:25+03:00; file mtime23:36:30.451208+03:00.
  `TOTOAI-SPORTS-V3-MODEL-READINESS-20260904` is its directory label; no actual
  author native task/thread ID is recorded in the report.
- Model report states full baseline `a17e0771e5ad1d3dc4990ce917b6135c8f7168f2` for
  production and its checkout on Sept4. The review concerns the then-dirty MAIN
  production tree, not code changes in ab34, and gives no independent full commit ID.
  Current supplied wrapper handoff confirms both checkouts at a17e077 with no tracked
  modifications and these untracked saved reports. That verification was reused,
  not repeated. Frozen hashes/tables remain in the exact copies, not current-code claims.
- Current supplied app observation lists only the parent; creation was denied and
  split cancelled. Files prove saved work, not running/accessible author tasks.
  All three workstreams continue in the existing MAIN task; no setup/ACK retry.

## Exact recovered copies and byte provenance
1. `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/recovered-reports/TOTOAI-4996-4997-RECOVERY-20260904-PRE_PUSH_REVIEW.md`
   11825 bytes; SHA256 `8c2ddceb082d7c2b3ff44db02c7a4304831db45f15244a4f967d8341562ae8ac`.
2. `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/recovered-reports/MODEL_READINESS_REPORT.md`
   10245 bytes; SHA256 `6999e0e506aa37bb90fc6bfb330ede64e57776dc506f8b13c649d50a2ffe73b7`.
Provenance: `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/recovered-reports/provenance.json`.
Sources verified regular/non-symlink and read-only; copied bytes compare exactly;
source inode/size/mtime/ctime unchanged during transfer. No source deletion/move.

## Reusable review: findings already collected, not newly reproduced
Sept4 verdict: NOT SUITABLE TO COMMIT OR PUSH. Four P1 findings and one preexisting P2:
- **P1 stale replay reuse:** self-hashed same-plan output allegedly bypasses exact
  input/baseline package/result snapshot hashes and bank4980/stake30/count166/cost4980.
  Existing disposition: validate all bindings before reuse; stale-same-plan regression.
- **P1 canonical result identity:** fresh replay allegedly loads newest complete result
  rather than the exact primary `result_snapshot_sha256`. Existing disposition: bind
  snapshot hash AND actual15-outcome string; terminal-row counts alone are insufficient.
- **P1 generic retry calendar:** policy-transition JSON rewrite allegedly leaves the
  loaded calendar stale when discovered by `preflight_retry_child=true`. Existing
  disposition: reconcile via parent runner or preserve schedule identity; integration
  regressions for false→true and true→false. Explicitly leave loaded4997 jobs alone.
- **P1 self-contained change boundary:** dirty CLI/history_backfill/tests, missing fixture,
  committed storage/dirty domain semantic method, and ignored retrospective helpers
  are interdependent. Dirty-tree passing tests do not prove clean-checkout reproduction.
  Existing disposition: preserve coherent slices; never stage only tracked files or all
  unrelated work wholesale; clean-checkout verification before a later authorized commit.
- **P2 preexisting history backfill:** `init_db()` allegedly runs before snapshot validation,
  permitting DB creation/migration on all-rejected input despite zero-write audit.
  Existing disposition: validation-before-write and missing/old-schema DB regressions.

Exact candidate implementation evidence locations from that report (historical lines):
- `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py`
- `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/retrospective_smoke_checks.py`
- `/Users/turshevr/toto-ai/src/toto_ai/optimizer/quality_replay.py`
- `/Users/turshevr/toto-ai/src/toto_ai/runner/morning_dispatch.py`
- `/Users/turshevr/toto-ai/src/toto_ai/runner/preflight_retry_scheduler.py`
- `/Users/turshevr/toto-ai/src/toto_ai/cli.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/history_backfill.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/domain.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/storage.py`
- `/Users/turshevr/toto-ai/tests/test_sports_history_backfill.py`
- `/Users/turshevr/toto-ai/tests/fixtures/scheduler_status/drawing_4996_attempt_delivery.json`
These paths are pointers only; none was opened or modified in this slice.

Other reusable review evidence: mixed ledger includes 8 recovery versus45 earlier
appends; watcher task-local snapshot was pre-authorization; Sportschau saved round
listing supports both events9/10 despite indirect URL. Do not refetch these sources.
Report says no tests rerun and isolated checkout lacked dirty production changes.

## Reusable model readiness: existing F3/P1, not a new feature plan
Done: frozen instruction/code/data hash tables, provider-source dispositions and
same-input/leakage contract saved. Status RESEARCH ONLY; NO MODEL RUN. No Sports v3
coverage auditor, fit, blending or package generation was performed by that report.

**Exact next incomplete step already specified: F3 / plan P1 read-only coverage auditor.**
Consume the explicit validate-only frozen history manifest for4990–4995; adapt exact
provider fixture/team identities and strictly pre-kickoff completed history to
`build_sports_v3_feature_table`; emit deterministic90-row source/feature coverage audit.
Existing failing-first cases:4990 SOURCE_REJECTED/BK fallback,4991 all-missing/BK
identity, deterministic rerun and input/hash/leakage guards. No DB/network/fitting.

Existing inputs/evidence (not re-read):
- `/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904/backfill-4990-4995-manifest.json`
  file SHA256 `07463e8831c8e1cbcd146b9243555c2efce72a160b4c527c3243573ade270e49`;
  semantic SHA256 `dd6151f61f4d3ab89a28eeea778fa0d02f7e96deb956ecb6c9742c076758ca77`.
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_features.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_feature_table.py`
The full report retains audit/aggregate/drawing-specific hashes, not invented paths
for unnamed audit files. Drawings4991–4995 source complete counts0,15,11,13,13;
missing15,0,4,2,2;4990 rejected deadline mismatch remains a scored BK fallback fold.

Remaining/blockers: reviewed self-contained persistence/history baseline not proven;
`minimum_prior_matches` must be predeclared (no saved production value), never inferred
from tests or chosen after coverage. Frozen request supports rolling_window10.
Source availability and non-null features stay separate; exact provider IDs, capture/
as_of checks and conflicting-duplicate rejection remain binding. Required90rows,
15orders/drawing, zero leakage/post-as_of/future-kickoff/duplicate violations and
stable hashes. Below70% full-feature coverage means no fitting/activation review.
F4/P2 A0–A5 follows P1; F5 only after probability gate; F6≥30 prospective drawings/
450events; F7 authoritative payouts. No automatic500/1000 replay.
Sports Analytics v3 is NOT optimizer quality-v3. The successful4996 four-package replay
therefore does NOT implement P1 or prove Sports v3 quality/profitability.4996 extension
must not tune this frozen4990–4995 contract after seeing its result.

## Superseded versus still relevant — narrow comparison only
Current evidence reused from ACTIVE/registry and supplied noon/wrapper handoffs:
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/noon-recovery-checkpoint.md`,
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/noon-recovery-report.md`,
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/worktree-wrapper-checkpoint.md`.
These three linked handoffs were NOT refetched.
- SUPERSEDED: waiting for first4996 noon run/hash-namespace repair. Current checkpoint
  records primary and one repaired replay complete,30focused tests+Ruff; no duplicate run.
- NOT PROVEN CLOSED: stale-replay-input and exact-result-snapshot review findings.
  A namespace fix/successful run alone does not establish those separate invariants;
  give them targeted disposition against already-saved repair/test evidence, not full audit.
- SUPERSEDED for INSPECTION: cannot attest linked checkout through Git. Main wrapper's
  verified `--registered-worktree <absolute>` read-only mode now works (52tests).
  NOT superseded: old own wrappers/dirty-dependent code baseline are unready for model work;
  the wrapper repair does not transfer missing code/data or validate experiment readiness.
- SUPERSEDED coordination/output direction: wait for another native task/child startup,
  or require a new worktree-local experiment. Split cancelled; main task retains all
  workstreams. Before future implementation, owner records main-local output scope in
  metadata; this transfer does not authorize experiments or outside-root writes.
- STILL RELEVANT as unverified review candidates: retry calendar regression gap,
  coherent baseline dependencies and rejected-input DB writes. Neither supplied completion
  addresses them. Preserve evidence; do not label them freshly reproduced current defects.
- Historical review no-commit verdict is not a new verdict on today's tree. No new
  commit/push permission or clean-checkout claim follows from either report or transfer.

## Candidate implementation handoff / exact next step (existing work only)
**Immediate owner step:** accept these recovered review/model artifacts into the single
main-task context, explicitly dispose the two retrospective binding findings against
already-saved noon repair evidence, and retain unresolved review items without re-auditing
all history. No additional task, worktree or report delivery service is needed.
**Existing review continuation:** after that disposition, generic retry-calendar
integration regression/disposition and coherent persistence/history baseline acceptance;
all changes/tests belong to a separately authorized implementation slice, not this worker.
**Existing model continuation:** once baseline accepted and `minimum_prior_matches`
predeclared, re-hash only handed-off inputs and implement P1 auditor with the saved
4990/4991/determinism gates. Do not jump to F4/F5 or copy old code ad hoc.
**Protected operational checkpoint:** Sept5 14:30MSK existing4997 scheduler/watcher;
immutable expiry16:20MSK. No runtime validation performed here; all4997 artifacts and
receipts untouched. Parent owns central ACTIVE/registry updates and prioritization.

Transfer complete; no active command, runtime mutation, experiment, Git operation,
external transmission, source deletion, publication or new-feature plan.
