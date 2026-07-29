# Morning preanalysis: dynamic dispatcher addendum

## Implementation status — 2026-07-28

The drawing-neutral dispatcher, persistent state, lock, idempotent
per-drawing plan generation, timing-span policy, and late-dispatch guard are
implemented in the working tree. Verification is included in the current
`1407 passed` full suite, `278 passed` final focused suite, and two identical
`40 passed` rehearsals. No new LaunchAgent is installed. Drawing 4958 remains
the activation-disabled live drill before any manual installation.

## Scope

This addendum covers only the standalone repository
`/Users/turshevr/toto-ai`. It does not use Arcadia, Yandex, Gena, Startrek,
external memory, or automatic BaltBet interaction.

The morning process may collect data, prepare one exact drawing, and activate
the already designed schema-v4 evening scheduler. It must never upload or
place a bet. A person remains responsible for uploading any package marked
`BET READY`.

## Confirmed defect

The current recurring morning LaunchAgent is drawing-specific:

- label: `com.totoai.morning-preanalysis.4953`;
- wrapper command:
  `sync-prepare --open --expected-drawing-number 4953`;
- recurring triggers: `08:00` and `10:30` every day.

The same wrapper therefore failed successively when fresh page one selected
drawings 4954, 4955, 4956, 4957, and 4958. Retrying the same stale command
cannot recover.

The defect is systemic: a drawing identity is appropriate inside one immutable
per-drawing run, but not inside a recurring cross-day dispatcher.

At the initial review five obsolete plist files remained in
`~/Library/LaunchAgents`:

- `com.totoai.morning-preanalysis.4953.plist`;
- `com.totoai.production-scheduler.a28e7c2c9c77683e.plist`;
- `com.totoai.production-scheduler.df543a668bb7557a.plist`;
- `com.totoai.run-drawing-4947.plist`;
- `com.totoai.run-drawing-4950.plist`.

On 2026-07-28 all five exact labels were booted out and their plist files were
removed. Follow-up inspection found no installed or loaded TotoAI LaunchAgent.
Cleanup was label-specific; no wildcard removal was used.

## Selected design

### 1. Stable recurring dispatcher

Install exactly one generic recurring LaunchAgent:

```text
com.totoai.morning-dispatcher.v1
```

Its wrapper contains no drawing number, internal ID, deadline, or package
identity. At each configured morning time it invokes one command:

```text
toto-ai morning-dispatch ...
```

The dispatcher is short-lived and protected by one process lock. It may be
triggered more than once per day.

### 2. Resolve, validate, then pin

One dispatcher invocation:

1. fetches fresh TotoBrief page one once;
2. persists page-one status updates;
3. identifies the unique current candidate using the existing nearest-future
   deadline rule;
4. fails closed if the nearest candidate is ambiguous, has no positive visible
   number/internal ID, has no valid future deadline, or its identity conflicts
   with an existing run;
5. fetches and validates exactly one fresh detail payload for that identity;
6. requires exactly 15 ordered events and a matching number/ID/deadline;
7. runs systematic preparation from that same selected payload, without a
   second page-one selection;
8. writes a per-drawing dispatch record containing visible number, internal
   ID, deadline, drawing fingerprint, detail hash, preparation status, and
   eligibility;
9. only after readiness is `15/15` and eligibility is `playable`, builds one
   schema-v4 `SchedulerPlan` pinned to that exact identity.

The recurring dispatcher never passes an old
`--expected-drawing-number`. The expected number guard remains valid inside
the newly pinned per-drawing plan and its evening execution.

### 3. Drawing-span policy

The existing betting rule remains stricter than the provider search horizon:

- all 15 starts known and within at most two Moscow calendar days:
  `playable`;
- three through five Moscow calendar days: `multi_day`, record diagnostics but
  do not create or activate an evening scheduler;
- unresolved starts after the bounded five-day lookup horizon, or a confirmed
  span beyond five days: ineligible, fail closed, no evening scheduler;
- no timing values are fabricated.

This preserves the prior decision not to bet multi-day drawings. Five days is
only the maximum discovery horizon, not permission to bet a five-day drawing.

### 4. Idempotency

The dispatch identity is:

```text
Moscow local date
+ drawing number
+ internal drawing ID
+ deadline
+ drawing fingerprint
```

Persistent state is written atomically beneath
`data/scheduler/morning-dispatch/` and records the generated plan ID and
managed LaunchAgent label.

Rules:

- the same drawing/day may retry incomplete preparation;
- once the same exact plan exists, later morning triggers verify and reuse it;
- the same drawing/day cannot generate a second plan or LaunchAgent;
- a conflicting identity or plan for the same drawing/day fails closed;
- a new drawing after the previous drawing closes gets a new run;
- concurrent triggers are serialized by a dispatcher lock;
- reports and prior package evidence are never deleted during cleanup.

### 5. Schema-v4 evening integration

For a ready playable drawing, the dispatcher creates a new isolated output
directory and calls the existing schema-v4 builders:

```text
build_scheduler_plan(...)
prepare_scheduler_artifacts(...)
```

The resulting plan must contain the exact number, internal ID, deadline,
bank/stake configuration, and five triggers:

```text
T-45, T-30, T-20, T-16, T-12
```

If the dispatcher runs too late to install the complete v4 schedule before
T-45, it records `late_dispatch` and does not activate a partial plan.

Activation is restricted to the generated, verified, project-owned plist.
The evening scheduler may produce a package and `.bet-ready`, but no code may
log in to BaltBet, upload coupons, or place a bet.

### 6. Managed cleanup lifecycle

Cleanup operates only on labels and plist paths explicitly recorded in
dispatcher state:

1. expired or terminal per-drawing scheduler jobs are booted out;
2. their installed plist copies are removed;
3. immutable plans, logs, packages, archives, and settlements remain;
4. the stable morning dispatcher remains installed;
5. unknown `com.totoai.*` jobs are reported, not deleted automatically.

One-time migration separately unloads and removes the five known obsolete
plist files listed above. It must finish before the generic dispatcher is
activated.

## Failure semantics

The dispatcher creates no evening job on:

- no current drawing;
- ambiguous current candidate;
- missing or conflicting identity/deadline;
- detail fetch/validation failure;
- preparation not ready 15/15;
- `multi_day` or `unknown` eligibility;
- provider failure or exhausted quota;
- late dispatch;
- state/plan/plist hash conflict.

These are non-betting diagnostic outcomes. They do not create `.bet-ready`,
`.no-bet`, package bytes, or a BaltBet request.

## Exact implementation files

### New

- `src/toto_ai/runner/morning_dispatch.py`
  - dispatcher domain records;
  - unique current-drawing resolution;
  - atomic state/lock and idempotency;
  - preparation-to-schema-v4 handoff;
  - managed activation and cleanup interfaces.
- `tests/test_morning_dispatch.py`
  - pure orchestration, identity, idempotency, eligibility, activation, and
    cleanup tests with injected page/detail/launchctl dependencies.

### Modify

- `src/toto_ai/operations/sync_prepare.py`
  - expose one fresh page-one/detail synchronization result that can be passed
    directly to preparation without reselecting the drawing;
  - reject ambiguous nearest candidates and conflicting identity.
- `src/toto_ai/runner/scheduler.py`
  - replace the drawing-specific recurring morning wrapper/plist renderer with
    the generic dispatcher candidate;
  - keep per-drawing schema-v4 artifact generation unchanged.
- `src/toto_ai/runner/__init__.py`
  - export the dispatcher interfaces.
- `src/toto_ai/cli.py`
  - add `morning-dispatch`;
  - change `morning-preanalysis-plan` to generate the generic candidate and
    remove the required expected drawing number.
- `tests/test_sync_prepare_operation.py`
  - nearest-candidate ambiguity and exact identity handoff.
- `tests/test_scheduler_operational_artifacts.py`
  - generic label/wrapper, no embedded drawing, no betting command, secure env.
- `tests/test_runner_scheduler.py`
  - generated per-drawing plan remains schema v4 with five exact triggers.
- `README.md`
  - replace the stale drawing-specific recurring example.
- `memory-bank/ARCHITECTURE.md`
- `memory-bank/CURRENT_STATE.md`
- `memory-bank/DECISIONS.md`
- `memory-bank/ROADMAP.md`
  - update only after implementation and operational drill pass.

No database schema change is required for the first implementation. Dispatcher
state is small, operational, atomic JSON; package/result evidence remains in
the existing database.

## Required tests

1. Day one selects and pins drawing 4953; a later day selects and pins 4958
   without regenerating the recurring wrapper.
2. The generic wrapper/plist contains no drawing number or
   `--expected-drawing-number`.
3. Two morning triggers for the same drawing/day create one plan and one
   managed evening job.
4. Concurrent invocations create one dispatch transition.
5. Multiple candidates tied at the nearest deadline fail with no preparation,
   plan, or job.
6. No candidate, null visible number, invalid deadline, page/detail mismatch,
   and changed fingerprint all fail closed.
7. The exact detail used for preparation is the identity pinned into the v4
   plan; no second page/detail selection occurs.
8. Ready 15/15 plus at-most-two-day timing creates a v4 plan.
9. Three-to-five-day `multi_day`, greater-than-five-day, and unresolved timing
   create no plan.
10. Unresolved preparation can retry at the second morning trigger without
    duplicating state.
11. A successful plan has T-45/T-30/T-20/T-16/T-12 triggers and cannot be
    activated after T-45.
12. Fake launchctl verifies bootstrap/bootout idempotency and project-owned
    label/path restrictions.
13. Expired jobs are removed while reports and package archives remain.
14. No morning path invokes `run-drawing`, writes betting markers, uploads
    coupons, or contacts BaltBet.
15. Existing atomic-final end-to-end, research, offline replay, settlement,
    Ruff, and full pytest gates remain green.

## Operational migration

1. Finish and commit the currently uncommitted schema-v4 atomic-final change
   after its focused/full verification and documentation correction.
2. Implement the dispatcher in a separate commit.
3. Network-free acceptance:
   - dynamic 4953-to-4958 rollover;
   - duplicate morning triggers;
   - ambiguity/no-draw/multi-day;
   - v4 five-trigger plan;
   - activation and cleanup with fake launchctl.
4. Unload any still-loaded obsolete labels with `launchctl bootout`.
5. Remove only the five known obsolete plist files from
   `~/Library/LaunchAgents`.
6. Generate one generic morning dispatcher candidate in a new output
   directory.
7. Run one live morning drill with activation disabled. Verify exact selected
   number/ID/deadline, readiness, eligibility, plan schema/ID, and all five
   local trigger times.
8. Only after that drill, copy/bootstrap the generic dispatcher plist.
9. Verify it with `launchctl print gui/$UID/com.totoai.morning-dispatcher.v1`.
10. After the first real drawing, verify morning state, five evening ticks,
    package decision, manual-upload time, result sync, and settlement.

## Acceptance criteria

The change is accepted only when all conditions hold:

1. A recurring morning artifact contains no stale drawing identity.
2. Each invocation freshly resolves one deterministic current drawing and
   pins its number, internal ID, deadline, and fingerprint.
3. Ambiguity, no drawing, preparation failure, and ineligible timing create no
   evening job.
4. Same drawing/day execution is idempotent under retries and concurrency.
5. A ready drawing produces exactly one schema-v4 plan with five triggers.
6. No partial schedule is activated after T-45.
7. Cleanup touches only state-owned jobs and never deletes evidence.
8. No automatic BaltBet upload or bet placement exists.
9. The stale 4953 recurring job and four obsolete scheduler jobs are removed
   before activation.
10. Focused tests, full pytest, Ruff, and `git diff --check` pass.
