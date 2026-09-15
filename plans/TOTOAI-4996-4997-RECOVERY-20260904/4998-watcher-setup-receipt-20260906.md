# 4998 local watcher — LOADED / SCHEDULED / VERIFIED

Task TOTOAI-4996-4997-RECOVERY-20260904. Worker 01a0760b-b663-7e21-8c46-69d9d0cc83f7.
Completed 2026-09-06T12:43:49.778937+03:00 in `/Users/turshevr/toto-ai`.

## Exact setup
- Plan `c1d243f5b6ca48f3`, drawing4998/id12102; bank4980/stake30.
  Plan: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/scheduler-plan.json`.
- Label **com.totoai.status-watcher.v1.c1d243f5b6ca48f3**; launchctl bootstrap exit0 and exact-label print exit0.
- Installed **September6,16:30MSK**, interval30seconds, RunAtLoad=false. Observed state **not running**, runs0, never exited; no watcher PID yet. Calendar descriptor independently matched2026/9/6/16:30; system local offset matches MSK.
- Existing4997 plist configuration rebound to4998; existing `scheduler-status-watch` unchanged. Native launchctl installed only this new watcher; primary-only installer was not misused. No new implementation, wrapper or policy changes.
- Duplicate gate: exact service absent, destination absent, no same-plan Python watcher process before setup.
- Installed plist: `/Users/turshevr/Library/LaunchAgents/com.totoai.status-watcher.v1.c1d243f5b6ca48f3.plist`. SHA256 `ad47a95d8a90e36656025e168af2ec1647260c6af1d3f83dba41f685588511ff` equals prepared candidate.
- Existing primary/parallel generated+installed plist hashes, plan, evidence ledger and inspected watcher/CLI source bytes unchanged.

## Persisted local status
- Latest: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/status-watch/latest.json`.
- History: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/status-watch/history.jsonl`.
- Runtime stdout: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/status-watch/stdout.log`.
- Runtime stderr: `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/status-watch/stderr.log`.
- Existing helper one-iteration smoke succeeded at **2026-09-06T12:42:42.166296+03:00**. This is setup smoke, not the future launchd run. Status `scheduled`, next16:30MSK, highest_p13_single_coupon=null; no fabricated best coupon or model calculation. The helper reads only computed plan-bound sidecar/comparison fields, never first row.
- Canonical JSON is readable local status; no new Markdown-renderer implementation or chat transport was added.

## Lifecycle and boundaries
- Production FINAL_FRESH/LAST_KNOWN_GOOD_DEGRADED are nonterminal; watcher keeps observing the parallel sidecar. Existing NO_BET terminal at planned **18:20MSK expiry** ends it; earlier terminal NO_BET also ends it.
- Existing watcher has **no independent wall-clock hard stop** if the scheduler never emits terminal evidence. This limit is disclosed, not silently fixed with new code. Parent checks actual expiry when due.
- No primary/parallel restarts, manual preflight, wagering, model runs, releaseauthorization, heartbeat or other job control. Exact-plan release consent remains for parent/owner.
- Local watcher **cannot wake or send messages into an idle Codex chat**; parent handles active-turn delivery.

## Process ownership / next checkpoint
- Preparation PID76336 exit0; installer PID76464 exit0. No owned running processes or unified-exec sessions. Watcher PID=null until scheduled start.
- **Next16:30MSK:** parent verifies this label has started and latest.json advances, alongside the already scheduled primary. Final/parallel18:00MSK; expiry18:20MSK. Do not create a second watcher or restart primary/parallel.
- Machine receipt: `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/4998-watcher-setup-receipt-20260906.json`.
- Historical note: first setup wrapper used nonexistent `SchedulerPlan.bank`; it failed before writes/job actions. Validation was corrected to existing serializedconfig.requested_bank/stake; project code untouched.
