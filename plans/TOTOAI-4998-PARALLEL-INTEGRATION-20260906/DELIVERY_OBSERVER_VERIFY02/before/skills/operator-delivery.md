# Plan-bound operator delivery — local observer checklist

Use for the active parent's explicit operator-delivery task, not model research.
No release, consent, scheduler, deadline, package or probability mutation is granted.
This observer change does not reload existing watchers or install a process/channel.

## Canonical inputs and receipt

- Primary authority: `<plan.output_dir>/operator-result.json`.
- Parallel discovery: `<plan.output_dir>/parallel-challenger/output/sidecar-status.json`.
  Its `parallel_release` must equal the sealed companion at
  `parallel-challenger/output/run-<sidecar.run_id>/parallel-operator-result.json`.
  The run must match the current primary. Do not guess a root/output-level companion.
- `scheduler-status` returns the new `delivery` contract, read-only.
- The existing `scheduler-status-watch` writes that compact contract atomically to
  `delivery-ready.json` beside its configured `latest.json`, before the next sleep.
  Default operations location: `<plan.output_dir>/status-watch/delivery-ready.json`.
  Existing live LaunchAgents remain unchanged until a separate owner-approved rollout.

## Parent consumption — READY is not SENT

1. While explicitly assigned active delivery near the final window, poll the exact
   compact receipt/current native `scheduler-status`; check it BEFORE waiting on a
   worker. Do not wait for `wait_agent`/task completion, a process exit or final prose
   when the canonical artifact is already ready. Use bounded short checks (e.g.5s)
   while actively attending the window; do not create a hidden heartbeat/service.
2. Require the exact task drawing/plan; check local current time against `expires_at`
   on EVERY read. Require a fresh status/native-record read before delivery. A cached
   `actionable=true` is an observation at `observed_at`, NEVER a lease beyond T-10.
   Future/naive/malformed publication timestamps, mismatched expiry/records/hash/path,
   symlinks and stale run bindings are not actionable. Do not extend the deadline.
3. Read `events`: `READY_PRIMARY` and `READY_PARALLEL` carry stable `event_id`, exact
   record/package paths and SHA256s, publication/expiry, selected strategy,
   probability model and available hash-bound highest-P13 metadata. Events may remain
   as historical observations with `actionable=false`; the name READY alone is not
   release authority. Prefer `preferred_event_id` among currently actionable events;
   invalid optional parallel output must leave valid primary available.
4. Revalidate the exact native record/package bytes and current cutoff immediately
   before sending through the EXISTING authorized host/chat channel. Never synthesize,
   reorder or convert a research package. These receipts issue no new authorization.
5. Primary readiness does not wait for an optional sidecar ranking or process exit.
   If highest-P13 is not yet bound, its status is `NOT_YET_BOUND_DO_NOT_INFER`; send
   only the verified primary artifact promptly and explicitly mark ranking pending.
   Then obtain the existing exact computation separately; do not call position1 best.
   A parallel READY requires the native recorded ranking (criterion/model/probability/
   one-based position); a ranking is never inferred from package ordering.
6. Record actual delivery separately ONLY after successful host delivery, with its
   real timestamp, delivered event ID and channel/message evidence. Polling, stdout,
   `delivery_state=READY` or `delivery_confirmed=false` is NOT a sent acknowledgement.
   Preserve missed-window evidence; expired artifacts are never actionable/uploadable.

## Notification boundary

`TOTOAI_LOCAL_DELIVERY_READY_V1` explicitly says:
`notification_transport=LOCAL_FILES_AND_STDOUT_ONLY`, `requires_host_delivery=true`,
`delivery_confirmed=false`, `automatic_wagering=false`.
Python file/stdout changes cannot wake an idle Codex chat. The implementation provides
no remote notification transport, no chat heartbeat and no automatic wager. If the
parent cannot attend and no authorized host delivery channel exists, report that gap;
do not promise unattended notification. Deduplicate by event_id, not process exit.

The watcher keeps observing after primary PLAY until cutoff (or a native terminal
non-PLAY), so it can detect a subsequently published parallel result and expiry.
Existing30s polling can consume most of a56s release window; this code does not
silently modify installed intervals. Any operational interval/channel changes require
a separate approved job. Runtime optimization is a distinct Euler-owned task.
