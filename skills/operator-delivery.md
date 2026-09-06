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


## Review correction02 — trust boundary

Paths containing `..` or a symlink ancestor are rejected before normalization.
Receipt/latest writes pin each directory with `O_DIRECTORY|O_NOFOLLOW`, create an
exclusive no-follow temporary, fsync it and replace relative to the pinned directory
FD; existing links/non-regular destinations are refused. History append also uses
no-follow directory-relative open. This verifies filesystem calls, not a claim of
power-loss proof or hostile-root-process immunity.

Parallel readiness additionally verifies the current primary control-copy bytes,
canonical run source/archive, native final-input snapshot (payload/probability hashes),
report file/seal/input binding, selection/package identity and exact recorded ranking.
Any failure leaves a verified primary available. The native primary-ranking schema
has no drawing fields: validate its actual plan-file, final-input, probability-input,
archive and operator-package bindings instead of inventing extra required fields.
Missing/invalid ranking remains pending, never a reason to delay the primary.

The independent candidate01 suite is preserved unchanged in the review02 evidence.
Source-owned equivalents retain its safety assertions, with a complete native fixture,
idempotent creation of the now-existing input directory, and an `os.replace` directory-FD
spy instead of a `Path.replace` implementation-specific spy. A proof with dummy hashes
and no input chain must be rejected, even if an old positive fixture expected acceptance.
Candidate02 still requires independent rereview and separate rollout/publication.


## Review correction03 — history append race (DO-1b only)

A pathname stat before open is insufficient: `O_NOFOLLOW` does not reject hardlinks.
Before appending, validate the **opened descriptor** with `fstat`: regular file,
exactly one link, same device/inode as the intended existing entry and the current
entry in the pinned directory. A missing history is created exclusively, so a raced
entry cannot be adopted. Nonblocking open avoids waiting on a substituted special
file. Failed validation closes the descriptor before writing; it neither truncates,
removes nor repairs the substituted entry or protected authority. Directory pinning
and the receipt/latest atomic writer remain unchanged. DO-2/3/4 are not reopened.
This correction remains a frozen candidate pending separate independent review;
it does not operate or reload the live watcher and does not confirm chat delivery.
