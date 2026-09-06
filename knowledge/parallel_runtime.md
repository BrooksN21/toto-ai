# Parallel final runtime: exact reuse and cooperative bounds

Task: TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Local implementation candidate;
independent review/publication are separate. No 4998 archive, authority, plan or
LaunchAgent is rewritten by this change.

## What the evidence establishes

The archived final sidecar spent 352.23s in control EV and 452.08s in sports EV.
G1 consumed 52.68s wall, not the preceding thirteen minutes. An offline cProfile
of the exact final input (166 coupons / 4980 / 30) reproduced the same control
coupon bytes and exact P13/P14/P15 in 84.44s, not 352s. Of that, 59.69s built the
full EV surface (7 convolutions, 47.74s), and 20.96s was quality repair.
The historical Background LaunchAgent/host slowdown is NOT causally isolated.

## Exact acceleration

`ExactCategoryCoverage` caches coverage-membership sets for swap proposals until
the next coverage mutation. It does not cache rounded totals or alter fsum,
candidate order/count, score, category, bank, RNG or tolerances. `_add` and
`_remove` invalidate the cache. Same-input full EV profiling retained all
40,960 swap evaluations; 84.44 -> 76.70s and repair 20.96 -> 14.93s. All result
fields except runtime were equal. These are instrumented foreground timings,
not a promise that the full production delay is fixed.

The final sidecar can reuse the scheduler primary ONLY after the existing full
native actionable export validation. The comparison revalidates the current
operator record/hash, source CSV/hash, canonical ordered coupons, native final
archive/hash, run/plan/drawing/input identity, probability and exact selection
configuration provenance, bank/stake/effective budget, and experimental consent
when applicable. Invalid or changed bindings fail closed; a loose TXT or a
claimed best coupon cannot enable reuse. Standalone research without that
record retains recomputation. Reuse changes no primary bytes or release gates.

## Bounded execution and evidence

An opt-in context-local runtime scope carries the absolute monotonic deadline
through EV, crowd chunks, FFT boundaries, full ranking, and repair loops.
Default EV callers have no added time limit. Native kernels remain cooperative:
a single in-flight NumPy call is checked on return, not forcibly interrupted.
Existing quality-v3/robust/G1 deadlines and complete candidate spaces remain.

`research-comparison/runtime-progress.json` and `.jsonl` contain actual phase,
checkpoint, wall/CPU, counters and remaining time; output is flushed. CPU is
the current process CPU, not inferred child CPU or proof of useful progress.
Completed research packages/ranking are retained before the next expensive
phase; a deadline failure never promotes an incomplete comparison.

Publication uses a fresh clock after validation and around its own writes.
If a write crosses expiry, only that newly created companion/package is
removed. Existing companions are immutable; the primary is never removed or
rewritten by the sidecar. Failed/expired optional work leaves the primary as
the unchanged fallback, subject to its own native expiry.

No watcher/notification transport, scheduler_status, priority/calendar or
operator authorization changes belong to this slice. Runtime checkpoints are
local evidence, not a claim of delivery into an idle chat.

## Runtime02 / PR-1 correction (pending independent rereview)

The frozen runtime01 compared the earlier export digest against a declared digest
and could miss replacement/deletion of current primary upload bytes. Runtime02
pins the original native-export digest, reopens the canonical run-scoped upload,
and invokes the existing native actionable validator at reuse and prepublication.
That validator retains expiry, authority, status/marker, source/CSV/archive and
durable-archive checks. Returned bytes, live record and upload are checked again;
no changed bytes receive a new trusted digest.

Before/after new companion writes, the actual sidecar route repeats the primary
check and verifies unchanged parallel authority. A lost primary raises a terminal
SKIPPED_PRIMARY_CHANGED, retains completed research, removes only newly created
optional publication files and never repairs/deletes the primary. No observer,
search-space, scoring, category, bank or runtime optimization changes are included.
Native-validator tests use genuine synthetic file contracts with an in-memory
archive DAO (no database); legacy reuse/selection fixtures explicitly stub native
validation. No live archive/job/authorization or long replay is run for this fix.
The previous timings remain historical evidence, not new runtime02 measurements.
