# 4997 operational checkpoint — read-only readiness

Task TOTOAI-4996-4997-RECOVERY-20260904. Observed September5 14:07–14:09MSK.
Plan45b72ac58a45958b, drawing4997/id12100, bank4980/stake30.
**SCHEDULED: local prerequisites pass, successful end-to-end run NOT yet proven.**

## Actual launchd state
All three exact gui/501 jobs loaded, not running, runs0, never exited.
Installed plists byte-equal prepared candidates; workingdir /Users/turshevr/toto-ai.
- com.totoai.production-scheduler.v9.45b72ac58a45958b:
  Sept5 14:30,15:00,15:30,15:40,15:50,16:00,16:12,16:20MSK.
- com.totoai.status-watcher.v1.45b72ac58a45958b:14:30MSK, interval30seconds.
- com.totoai.parallel-sidecar.v1.45b72ac58a45958b:16:00MSK,
  wait900seconds/minimumruntime240seconds, same exact schedulerplan and frozen sportsseed.
Main/sidecar shell scripts exist, executable, shellsyntax passes; venvPython executable.
load_scheduler_plan succeeds (schema9 supported, current source bindings validated).
Canonical plan_id also independently recomputed. Aliases/ledger/cutoffevidence/DB exist.
.env metadata only: regular, not symlink, ownercurrent,0600; no secrets read.
Both receiptbytehash+selfhash verified unchanged; stateexperimental_manual_authorized,
action_required=false; no additional permission request needed. Closure16:30,T-10expiry16:20.

## Current status
Fresh read-only scheduler_status at14:08:45:phase scheduled; lastattemptnull;
quality-v2/sports-shadow/quality-v3/robust pending; selectedstrategy/bestcouponnull;
operator_result_ready=false;blocker=null;nextcheckpoint14:30 t_minus_120.
Sportsseed validates4997/12100;coverage11/15,fallback4;artifact1a773c4b20b2aa67213e3f9458433cb095a10b6ab3128c5778e66fcd9e01b797.
No current executionerror observed; logs absent because these loadedjobs have runs0.
Network/provider/quota/credentialusability/runtime not tested, no API/manualcalculation.
No guarantee of PLAY, on-time result or profit from this static readiness check.

## Watcher output and delivery LIMITS
Boundroot /Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z
- status-watch/latest.json: atomic JSON updated every30seconds while observer runs.
- status-watch/history.jsonl and status-watch/stdout.log: JSON on changedstatus only.
- status-watch/stderr.log: failure details.
Existing latest.json is Sept4 23:15:12, NOT today's automaticrun; remains untouched.
The watcher does NOT write a separate readable Russian/Markdown report. Parent can
render the JSON into readable chat status; this local watcher cannot wake idle chat.
**Observed lifecycle limit:** operations/scheduler_status.py:terminal is driven by
primary PLAY/NO_BET, watcher returns immediately on it. Parallelstatus may appear
later and thus be missed by this observer. This is a status-delivery risk, not a new
launch/runtimeerror. Do not claim continuous all-model observation after primaryterminal.
No changes made; parent must explicitly observe sidecar after primary publication.

Exact loaded watcher command (documented only, NOT executed here):
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli scheduler-status-watch --plan /Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/scheduler-plan.json --latest /Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/status-watch/latest.json --history /Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/status-watch/history.jsonl --interval-seconds 30
Safe non-waiting artifact read from projectcwd:
/Users/turshevr/toto-ai/.venv/bin/python -m json.tool /Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/status-watch/latest.json

## Exact paths to observe from14:30
/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/status-watch/latest.json
/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/logs/scheduler.stdout.log
/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/logs/scheduler.stderr.log
/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/operator-result.json
/Users/turshevr/toto-ai/reports/rehearsal/evening-4997-20260905T133000Z/parallel-challenger/output/sidecar-status.json
Output records not present before execution; no package or bestcoupon fabricated.

## Remaining earlier fixes / coordination
4996 stale reuse fixed/integrated; fresh exact-result generator follow-up OPEN (unsafe
regeneration blocked). OtherOPEN:retry-calendar reconciliation/coherent persistence
baseline/rejected-backfill DB-write defect; SportsF3/P1 auditor awaitsbaseline and
minimum_prior_matches contract. None implies a freshly reproduced4997error here.
Current owner direction: THIS parent operations chat owns drawpreparation; original
review/models worktrees recovered separately. This contextjob did not create/resume
any task or edit sourceworktrees; existing outdated splitmetadata is historical only.

## Handoff
NEXT14:30MSK:parent read exact watcherstatus and scopedlaunchctl states after dueevent;
report actualattempt/phase/error, not merely that jobsareloaded. Then next15:00MSK.
No code/runtime/consent/scheduler/DB mutations, no manualjobs,API,heartbeat,publication.
Only this checkpoint+JSON evidence written in mainplans. No ongoing ownedprocess.
