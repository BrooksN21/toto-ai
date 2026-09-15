# TOTOAI-4996-4997-RECOVERY-20260904 — noon context handoff

Completed: 2026-09-05T13:03:51.059963+03:00 (MSK). Evidence collected 2026-09-05 13:00:58–13:02:32 MSK.
Context worker actual ID: `01a07102-7504-74d2-8ed2-147f9c2e3367`.
Every shell cwd: `/Users/turshevr/toto-ai`. Explicit scoped context assignment;
not either pending review/models child. No parent ACK or child baseline invented.
Only this handoff was written; ACTIVE_PLAN/registry, source, DB, runtime, receipts,
LaunchAgents and packages untouched. No network, model/replay calculation, Git,
publication, heartbeat, descendant or job launch. All commands completed promptly.

## Immediate conclusion
- **4996 primary settlement DID run; it was not missed.** Persisted state is complete,
  an actual settled report exists, and canonical DB now has 15/15 resolved events.
- **4996 retrospective DID run but FAILED CLOSED**, not pending results:
  `ValueError: post-draw state package SHA-256 mismatch`. No replay was reached.
- **4997 evening scheduler, sidecar and local watcher remain loaded and not yet due.**
  Next operational checkpoint is Sept5 **14:30 MSK**, not noon. Deadline16:30;
  immutable release expiry16:20. Do not restart preparation/generation.

## 4996 primary: completion evidence, not an inferred exit code
Exact report:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/post-draw/postmortem.md`
mtime **2026-09-05T12:03:41.597132+03:00**. Reported metrics, copied without recalculation:
- Actual outcomes `X222XX2111112X2`; VOID `[]`.
- Best REALIZED hits **11/15**, package position **54**. This is post-draw realized
  ranking, NOT a pre-draw highest-P13 claim.
- Report distribution: 10 hits=4 coupons; 11 hits=1; 12/13/14/15 hits=0 each.
  Full distribution is in the report; no 13/14/15 category hit.
- Cost4980 RUB; known return and ROI **unknown_until_payouts** (`None`).
- Fixed misses `[]`; zero-exposure misses `[]`. No profitability conclusion.

State:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/post-draw/post-draw-state.json`
contains `status=complete`, `reason=SETTLEMENT_COMPLETE`, `attempts=1`,
`due_slot=2026-09-05T12:00:00+03:00`, same sole attempted slot;
`updated_at=2026-09-05T09:03:38.395667+00:00` (12:03:38 MSK),
file mtime12:03:41.617787 MSK. Actual report creation confirms more than a successful
launcher exit. Primary process exit code was NOT observed in this diagnosis.
State `result_snapshot_sha256=560bb970a2dc11cfd88b492c00237d9df308e9c1fd5d0b276cbe23a6141ff425`;
`settlement_sha256=939ffb1b050d53c848b540b160bfca15c87566a1b11ba9bc855b2b33c7d5efb7`.

At13:02:11, SQLite `file:/Users/turshevr/toto-ai/data/toto.db?mode=ro`,
`PRAGMA query_only=ON`, bounded queries only for drawing12096:
`drawings(id=12096,number=4996).status=finished`; events count15,
15 results in1/X/2, all15 `result_status=resolved`. No result refresh or settlement
calculation was invoked; no full DB/schema inventory.

`launchctl print gui/501/com.toto-ai.post-draw-12096` returned service not found.
This is consistent with completed-job cleanup, NOT proof of a missed run:
`/Users/turshevr/toto-ai/src/toto_ai/cli.py:1077-1082` explicitly calls
`cleanup_post_draw_launch_agent(plan)` for installed complete/blocked/exhausted jobs.
The retained primary plist has no stdout/stderr paths; no primary exit log was found
or invented. Do not reinstall or rerun completed settlement simply because its label
is absent. Saved historical retry slots are not currently loaded primary jobs.

Delivery is a separate unfinished obligation:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/post-draw/review-delivery.json`
reports desktop transport `sent`, but `status=pending`, `receipt=null`,
`reason=OWNER_RECEIPT_REQUIRED`, `retryable=true`. Transport success is NOT owner receipt.

## 4996 retrospective: exact failure and binding handoff
Loaded exact label:
`com.totoai.post-draw-retrospective.v1.0d8c2cdfb10ef9c5` in gui/501.
At inspection: `state=not running`, `active count=0`, `runs=1`, **last exit code1**.
Loaded calendar: Sept5 12:05/15:05/18:05/21:05 and Sept6 00:05/03:05 MSK.
Next retry **2026-09-05T15:05:00+03:00**, not an automatic repair.

Status:
`/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/retrospective-status.json`
`observed_at=2026-09-05T12:19:52.540696+03:00`, `status=failed`,
`phase=FAIL_CLOSED`, blocker exactly `ValueError: post-draw state package SHA-256 mismatch`.
Exact stderr tail contains that same sole error:
`/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/logs/launchagent.stderr.log`
(53 bytes, mtime12:19:52.684420); stdout is empty (mtime12:19:51.842506).
Retrospective is research-only: `operator_compatible=false`, `automatic_wagering=false`;
comparison class `POST_DRAW_REPLAY_NOT_PRE_CUTOFF_SIDECAR`. Missing/unfinished prior
challengers remain missing/unfinished, not compared.

Exact current values (different representations must NOT be equated blindly):
1. Primary state above: `package_sha256=f227a5374aba05c758a8d15cf4d4c06b8989f52cf54eced672c371a4d592b27d`.
2. `/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/post-draw/post-draw-12096.json`:
   `package_binding.package_sha256=f227a5374aba05c758a8d15cf4d4c06b8989f52cf54eced672c371a4d592b27d`,
   `package_binding.source_bytes_sha256=906ca0c3e71e584771f41f7f7e239f7cb6d6873a3ee2411c695a6a6b047bdbf8`;
   binding kind `package`,166 coupons,cost4980,stake30.
3. `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/retrospective-plan-12096.json`:
   `issued_operator_package.package_sha256=42e6e55a1c6b7d642ad749257849e94e4216e57c6cacfa08d26fca74e9c44b37`;
   `bindings.baseline_package.file_sha256=906ca0c3e71e584771f41f7f7e239f7cb6d6873a3ee2411c695a6a6b047bdbf8`.
4. `/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/paper-package-result.json`:
   `paper_sha256=42e6e55a1c6b7d642ad749257849e94e4216e57c6cacfa08d26fca74e9c44b37`,
   `source_package_sha256=906ca0c3e71e584771f41f7f7e239f7cb6d6873a3ee2411c695a6a6b047bdbf8`,
   plan0d8c2cdfb10ef9c5, checkpoint61af14cb39d316d29f0c9f34.
5. Runner `/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py`
   lines300-304 pass `issued_operator_package.package_sha256` to `validate_primary_state`;
   lines198-202 verify state self-hash/identity and compare complete-state package hash
   against that argument. This is the exact failing comparison; no repair performed.

Retain yesterday's accepted evidence, do not recollect it:
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/IMPLEMENTATION_REPORT.md`
records legacy replay hash-encoding handling, nine binding checks, pending preflight
before primary state existed, runner hash
`4502a892ca86986149025a34f55de1f41385493ac512f95fcb51ce70304c8f1c`, retrospective plan hash
`7dbc403a1b530c17d02cd9d2d26ec0cab4fb98b880b72864504603920b7c1138`.
Canonical JSON/semantic package hashes and raw file-byte/paper hashes are distinct
namespaces. Values above are read evidence, not newly recomputed equivalence proofs.
Separate recovery worker must investigate that distinction while preserving immutable
source/control artifacts and guards; this context handoff does not authorize weakening
validation, editing stored hashes to match, or reconstructing an operator package.

## Existing entrypoints — identified, NOT executed
Primary exact generated entrypoint:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4996-20260904T163000Z/post-draw/post-draw-12096.sh`
executes `.venv/bin/python -m toto_ai.cli post-draw-run --plan` with the exact primary
JSON above. **No primary catch-up is needed**; settlement is complete. This diagnosis
has not independently proven all rerun/idempotence behavior and does not recommend rerunning it.

Retrospective exact generated entrypoint:
`/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.sh`
executes `/Users/turshevr/toto-ai/.venv/bin/python`
`/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/run-retrospective-12096.py`
`--plan /Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/retrospective-plan-12096.json`.
It checks primary binding before replay, and checks for the existing replay report
before launching replay (runner lines326-328). Do not invoke it unchanged to clear
this deterministic error; repair/test and any subsequent execution belong to the
separate authorized recovery worker, subject to the 4997 production resource window.

## 4997 live loaded schedules versus older stored status
Labels derived from the saved implementation handoff and verified via exact launchctl
queries, not assumed. All three at inspection: `not running`, `runs=0`, no exit yet,
working directory `/Users/turshevr/toto-ai`:
- `com.totoai.production-scheduler.v9.45b72ac58a45958b`:
  Sept5 **14:30,15:00,15:30,15:40,15:50,16:00,16:12,16:20 MSK**.
- `com.totoai.parallel-sidecar.v1.45b72ac58a45958b`: Sept5 **16:00 MSK**.
- `com.totoai.status-watcher.v1.45b72ac58a45958b`: Sept5 **14:30 MSK**;
  canonical local `scheduler-status-watch`, interval30 seconds. No chat heartbeat.
Current-user `ps` returned0; exact task command/path filtering found no active task
processes. The only later match was this diagnostic shell PID30683, not a worker.
No owned active PID/session exists to resume. Launchctl also reports active count0.
`kern.boottime` reports Sept4 21:53:57 local; this does not establish a noon reboot or
sleep/wake chronology. Persisted run timestamps establish that noon work happened.

Plan:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/scheduler-plan.json`:
plan45b72ac58a45958b/drawing4997/id12100/bank4980/stake30;
ended_at and operational_cutoff13:30Z=16:30MSK; t_minus_10=13:20Z=16:20MSK.
No scheduler-state.json/operator-result.json/parallel-operator-result.json exists at
the output root; no parallel output directory was present. No final PLAY is claimed.
Bound sidecar shell waits900s for primary, minimum runtime240s; its referenced frozen
sports-seed file exists. No generation or result comparison was invoked.

Existing timing acceptance:
`/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/preflight/drawing-12100-20260905T133000Z-fe49b1ba85febf3a/RESOLVED.json`
`status=RESOLVED: READY 15/15`, resolved_at2026-09-04T20:09:12.440578Z.
Its reviewed_catalog_hash77d6c83566fda9241dc60243d54470d0e24d05b271a7108bdbcacce9f2bb7093
and cutoff_evidence_sha256c62c84bf52f60666cbcc764fc4d17430eb930ffc4d8c575f325e339027f2fda4
match the saved scheduler plan. Historical implementation report records playable,
unresolved=[]; this is existing accepted evidence, not a new public timing audit.
Old retry-plan planned slots are superseded by RESOLVED and active evening jobs.

Watcher snapshot:
`/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/status-watch/latest.json`
is **old**, observed2026-09-04T23:15:12.400085+03:00. It says scheduled, next14:30,
blocker=null, primary and all4 challengers pending, no operator result,
manual_wager_request.state=experimental_manual_authorized, action_required=false.
The loaded calendars were checked now; this snapshot was NOT regenerated.

Immutable consent receipts read, NOT changed or reauthorized:
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/experimental-manual-release-authorization.json`:
  record_sha256f315191e2e6b24f4c8db2de83190e8a7f47fed59dbe5691181a9f651e46e81d9.
- `/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/parallel-challenger/parallel-release-authorization.json`:
  record_sha25662845d157ce795957375755cd9fad71a242a5676069134853a139c649bc464b9.
Both current records match4997/id12100/plan45b72ac58a45958b/bank4980/stake30,
expire2026-09-05T13:20:00Z, risk_acknowledged=true, automatic_wagering=false,
profitability_proven=false. Primary selection_context_sha256 matches the scheduler.
Yesterday's canonical receipt self-hash verification remains the retained evidence;
no hash recalculation or runtime authorization CLI was run here. These receipts are
not a PLAY and never authorize automatic wagering.

## Safe next actions / remaining / boundary
1. Parent/recovery worker: use this saved handoff for the exact retrospective binding
   failure; investigate/repair/test in its authorized scope, preserving prior evidence
   and all immutable4996 artifacts/4997 receipts. Primary settlement is already complete.
2. Parent: address owner receipt for the real4996 report separately; do not conflate
   desktop notification sent, settlement complete and retrospective complete.
3. **Next operational checkpoint14:30 MSK Sept5**: observe existing4997 scheduler/local
   watcher; no duplicate jobs/heartbeat/manual regeneration. Next retrospective retry15:05;
   later4997 final+sidecar16:00, immutable expiry16:20. No automatic chat wakeup promised.
4. Remaining: retrospective comparison blocked by the exact mismatch, receipt pending,
   authoritative payouts/ROI unknown, final4997 PLAY/NO_BET and comparison not yet due.
5. No source fix, tests, runtime recovery, new settlement, replay, package release or
   publication was performed. Parent owns central ACTIVE_PLAN updates and later workflow.
