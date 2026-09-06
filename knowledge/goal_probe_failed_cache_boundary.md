# Failed GOAL probe cache recovery

A persisted marker proves immutable captured bytes, not provider success.
Explicit source_failed captures must never be returned as fresh/reusable.

Successful full, partial, partial-conflicts and zero-match captures are reused
with their original timestamps and verified file hashes. Original current.json,
captures and failed attempts are never overwritten or deleted.

A failed original marker owns a hash-bound append-only retry ledger:
failed-cache-retry/<original-marker-sha256>/attempts/<generation>/.
Each generation has an exclusive immutable attempt.json reservation, a separate
current.json if capture finished, and an outcome.json for normal success/failure.
A crashed process leaves its reservation intact; after the 900-second lease,
a later caller appends expired.json and may make one new attempt. The legacy
one-shot root attempt is also counted and can recover without deleting evidence.

A local POSIX file lock remains held across collection. It excludes overlapping
callers even after the lease time; the OS releases it on process death.
Each invocation makes at most one new collection, never an internal retry loop.
The existing caller cadence remains responsible for subsequent invocations.

Cooldown is 900 seconds from the latest claim/capture completion/outcome.
Every attempt reserves the full caller request_budget (1..120), including
exceptions/crashes with unknown usage. Reservations remain in quota accounting:
no more than 120 retry requests may be reserved in any rolling hour. This is a
separate fixed retry allowance, never enlarged by changing caller budgets.
If a reservation would cross that allowance, the error supplies the earliest
window-release time. All reservations also reduce the initial observed remaining
provider quota; each later quota observation can tighten that bound. Unknown
quota is not invented; the rolling allowance and provider client's own quota
enforcement remain active. Recorded source budget exhaustion and insufficient
known quota are terminal, not silently reset. There is no automatic quota reset.

The existing paper-only CLI error status now consumes structured retryable,
retry_reason and next_retry_at fields. Terminal limits and unknown integrity/
validation errors are not advertised as retryable. No CLI flag, scheduler,
provider refresh, DB operation, pin change, model gate, or wagering authority is
introduced. Existing drawing-deadline and GoalAPIClient request safeguards remain.

Tests use synthetic fixtures only: exact independent recovery/safety probes,
latest cooldown, immutable evidence, crash lease, active-lock exclusion, rolling
request allowance, quota reservations, terminal status and CLI wiring.

Claim and outcome publication is crash-safe: complete fsynced bytes are linked
atomically from same-directory append-only .pending staging files. Link creation
never replaces existing evidence. Incomplete unpublished staging is not a claim
and cannot precede provider requests; interrupted outcomes retain the full claim
reservation and use existing lease recovery. Other record formats are unchanged.

Durability amendment: after file fsync and exclusive hard-link publication, sync
the final-name directory then each ancestor bottom-up through the existing cache
output root. Directory-sync errors propagate before collector entry or outcome
acknowledgement. This verifies filesystem calls/order, not real power-loss behavior.
