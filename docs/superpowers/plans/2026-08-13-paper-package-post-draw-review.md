# Paper Package and Post-Draw Review Implementation Plan

> Implementation plan only. This plan does not authorize source changes,
> wagering, scheduler installation, remote publication, or activation of any
> production model.

This plan implements the approved
`docs/superpowers/specs/2026-08-13-paper-package-and-post-draw-review-design.md`
and the mandatory exact-format correction in the supplied context.

## Goal and invariants

Make every terminal scheduler calculation inspectable and close every drawing
with a durable, explicit review workflow while preserving the existing
finished-drawing settlement implementation and the actionable T-10 boundary.

- There is never automatic bet placement.
- `PLAY` remains governed only by the current scheduler-owned actionable
  `operator-result.json`, `.bet-ready`, and `operator-export` checks.
- `NO BET` paper output is non-actionable and is never accepted by
  `operator-export` or used to create `.bet-ready`.
- The copyable payload is **only** lines matching
  `^<stake>; [1X2](; [1X2]){14}$`, with `; ` as the delimiter, LF endings,
  final newline, exactly 15 outcomes, unique coupons, and source-package
  order. No header, Markdown, warning, rank, `gross_ev`, or `net_ev` may occur
  in the payload.
- Warnings (`PAPER / NO BET / DO NOT WAGER`) are emitted separately on
  `stderr` and/or in the status JSON.
- The historical drawing 4974 package remains available through this exact
  paper format, but is explicitly `actionable=false` and must be rejected by
  the actionable export path. The known historical source is
  `reports/rehearsal/evening-4974-recovery-20260813T1330Z/paper-package-4974-baltbet-format.txt`.
- Existing probability, cover, bank, stake, package-safety, and settlement
  definitions do not change.

## Files and interfaces

Primary implementation files:

- `src/toto_ai/runner/scheduler.py`: pure paper rendering/validation,
  atomic persistence, scheduler terminal integration, T-10 preservation.
- `src/toto_ai/operations/finished_draw.py`: durable post-draw plan/state,
  cadence, retry classification, review request, and postmortem lifecycle;
  continue to call `sync_finished_drawing`, `archive_package`, and
  `settle_archived_package` rather than duplicating settlement.
- `src/toto_ai/cli.py`: `paper-package-show` plus machine-readable post-draw
  plan/status/review transitions.
- `src/toto_ai/operations/` (new small helper module if needed): notification
  and immutable postmortem generation only; keep it separate from settlement.
- `tests/test_scheduler_atomic_final_end_to_end.py`,
  `tests/test_scheduler_last_known_good.py`,
  `tests/test_scheduler_operational_artifacts.py`: paper and actionable-boundary
  regressions.
- `tests/test_finished_lifecycle.py`,
  `tests/test_collector_lifecycle_v1.py`,
  `tests/test_offline_repair_classification_idempotency_v1.py`: post-draw
  schedule, retry, idempotency, review, and integrity tests.
- `memory-bank/ARCHITECTURE.md`, `CURRENT_STATE.md`, `DECISIONS.md`, and
  `ROADMAP.md`: update only as part of the later implementation, after each
  completed feature; do not change them during this planning task.

Recommended pure interfaces:

```python
def render_paper_package(*, source_package: Path, stake: int) -> str: ...
def validate_paper_package(
    text: str, *, source_package: Path, stake: int,
) -> PaperPackageSummary: ...
def persist_paper_package_artifacts(
    *, plan: SchedulerPlan, source_package: Path | None,
    decision: str, reason: str, completed_at: datetime,
) -> PaperPackageResult: ...
```

`PaperPackageResult` must bind drawing ID/number, scheduler `plan_id`,
decision/reason, `actionable=false`, source CSV path/hash when present, paper
text path/hash, count, stake, cost, probability-input hash, provenance, and
completion time. For package-free `NO BET`, it has no coupon/text path and
records the failed or missing stage.

Recommended post-draw interfaces:

```python
def build_post_draw_plan(..., ended_at: datetime, package_binding: ...): ...
def due_post_draw_attempts(plan, now: datetime) -> tuple[datetime, ...]: ...
def run_post_draw_plan(..., plan_path: Path, now: Callable[[], datetime]): ...
def write_review_request(settlement: Settlement, ...): ...
def transition_review_request(..., transition: Literal[...]): ...
def render_postmortem(..., settlement: Settlement, ...): ...
```

## Task 1 — Paper renderer and validator (TDD first)

**Files:** modify `src/toto_ai/runner/scheduler.py`; add focused tests in
`tests/test_scheduler_paper_package.py`; extend existing scheduler tests only
where the actionable boundary is involved.

1. Add failing unit tests before implementation:
   - valid 15-outcome coupons render as `stake; outcome; ...` with exactly one
     coupon per line, final LF, and no extra fields;
   - rank/EV source columns are discarded from the display text while source
     coupon order is preserved;
   - zero coupons produce an empty paper payload, not a warning line;
   - malformed stake, wrong outcome count/alphabet, duplicate coupon, CR/NUL,
     missing final newline, wrong order, wrong count, and wrong implied cost
     all fail closed;
   - package 4974's existing historical paper artifact validates and is
     explicitly non-actionable.
2. Run the focused test file and record the expected RED failure.
3. Implement the renderer from the already validated source `package.csv`,
   reusing `_parse_package_source`/`_validate_baltbet_upload` where their
   semantics apply. Keep `_render_baltbet_upload` unchanged for actionable
   publication unless a shared pure helper can prove byte-for-byte equivalent
   behavior.
4. Implement strict validation with the exact regular shape, UTF-8/LF/final
   newline checks, 15 outcomes, uniqueness, source-order equality, count, and
   cost checks. Reject symlinks, foreign paths, unbound source files, and hash
   drift before reading a package for display.
5. Run the focused tests and confirm GREEN before wiring the scheduler.

## Task 2 — Durable paper artifacts and `paper-package-show`

**Files:** modify `src/toto_ai/runner/scheduler.py` and `src/toto_ai/cli.py`;
add `tests/test_paper_package_cli.py` and scheduler integration tests.

1. Write failing tests for both terminal cases:
   - computed `NO BET` persists a hash-bound research/source CSV plus exact
     paper text and `paper-package-result.json`;
   - package-free `NO BET` persists a result with reason/stage, no coupon
     payload, and no fake package path;
   - a terminal `PLAY` has its ordinary actionable result and exactly one
     paper summary only if a validated paper view is intentionally exposed;
   - persistence is atomic and restart/idempotency-safe;
   - mutating source bytes, result JSON, paper bytes, plan identity,
     probability hash, drawing identity, or referenced path is rejected.
2. Run the new tests to confirm RED.
3. Add persistence after the final validated scheduler decision, not after a
   merely ranked candidate. Use the existing run directory, contained regular
   files, temp-file-plus-`os.replace` writes, SHA-256s, and identity checks.
   Write the paper text/result only after the source package is validated; a
   package-free result is written independently and remains coupon-free.
4. Add `paper-package-show --plan <scheduler-plan.json> [--output PATH]`:
   - load and validate the v6 plan and all paper/result/source bindings;
   - print only exact coupon lines to stdout, or write only those lines to the
     explicit output file;
   - print terminal summary and `PAPER / NO BET / DO NOT WAGER` to `stderr`;
   - never select, reorder, repair, or alter coupons;
   - reject expired, foreign, tampered, symlinked, missing, or unbound data.
5. Add CLI tests asserting stdout contains no header/diagnostic/EV/warning and
   stderr contains the warning; test `--output` has identical bytes and no
   stdout payload. Verify `operator-export` still rejects this artifact.
6. Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_scheduler_paper_package.py tests/test_paper_package_cli.py \
  tests/test_scheduler_atomic_final_end_to_end.py -q
```

## Task 3 — T-10 and historical 4974 safety regression

**Files:** modify scheduler tests; add a fixture only if the existing 4974
artifact cannot be exercised without copying it; do not add an operator export.

1. Write failing tests proving the 4974 paper text is readable and validates,
   has 166 unique lines and implied cost 4,980, but cannot create `.bet-ready`,
   cannot become `operator-result.json` with `actionable=true`, and is rejected
   by `operator-export`.
2. Write failing T-10 tests proving cleanup removes actionable
   `package.csv`/archive/upload surfaces as currently specified but retains
   paper text, `paper-package-result.json`, and audit diagnostics.
3. Implement only the minimum scheduler publication wiring needed to preserve
   these boundaries. Do not relax `_publish_actionable_operator_result`,
   `_remove_actionable_publication_artifacts`, `_validate_baltbet_upload`, or
   the final fresh-network gate.
4. Run the focused scheduler suite and the existing operator-export tests.

## Task 4 — Post-draw plan with next-day Moscow cadence

**Files:** modify `src/toto_ai/operations/finished_draw.py` and
`src/toto_ai/cli.py`; add `tests/test_post_draw_schedule.py`.

1. Write failing tests for an ended drawing at multiple UTC offsets around
   midnight. The first due time must be **12:00 Europe/Moscow on the next
   calendar day after the drawing deadline**, followed by 15:00, 18:00, 21:00,
   00:00, then every three hours until the existing bounded expiry. Test DST/
   timezone-aware inputs with `zoneinfo.ZoneInfo("Europe/Moscow")`, and ensure
   the schedule is derived from the local calendar date, not `ended_at + N`
   seconds.
2. Test that every terminal scheduler decision creates one non-betting plan
   bound to the final paper/actionable package identity/hash, or to an explicit
   package-free `NO BET` identity. Recreating the plan is idempotent; a changed
   final hash is an integrity conflict.
3. Implement a versioned durable post-draw plan JSON and extend
   `prepare_post_draw_scheduler_artifacts()` to render a wrapper/LaunchAgent
   candidate with the exact cadence. Nothing is installed automatically.
   Preserve the existing bounded-expiry policy and make due-attempt selection
   deterministic and restart-safe.
4. Add/adjust `post-draw-plan` and `post-draw-run` options so the runner can
   execute one due slot from the durable plan without requiring a package file
   for package-free `NO BET`. Keep old package arguments compatible only when
   their identity can be proven.
5. Verify exact JSON, launchd calendar entries, no automatic wagering, and
   idempotent repeated invocation.

## Task 5 — Reuse settlement lifecycle and classify retries

**Files:** modify `src/toto_ai/operations/finished_draw.py`; add lifecycle
tests.

1. Add RED tests for incomplete results (`PENDING_RESULTS`), postponed events,
   accepted authoritative VOID events, transport failures with typed error and
   unchanged prior snapshots, and identity/hash/terminal conflicts becoming
   `REVIEW_BLOCKED_INTEGRITY` without automatic retry.
2. Adapt `run_post_draw`/`_run_post_draw_locked` to use the plan's package
   binding and due slot. On each attempt call `sync_finished_drawing`, then
   `settle_archived_package`; call existing archive helpers when a package is
   present. Do not introduce a second hit/VOID/payout algorithm.
3. Persist schema-versioned state containing attempt slot, typed error,
   drawing/package/result/settlement hashes, and status. Preserve immutable
   snapshots and make completed settlement idempotent across process restarts.
4. For package-free `NO BET`, still synchronize and settle drawing data when
   possible, while producing a package-free review explanation. Missing results
   remain pending; only the existing reviewed-VOID contract makes a VOID
   terminal.
5. Run focused lifecycle tests, then the complete existing finished lifecycle
   suite.

## Task 6 — Review request, user transitions, and postmortem

**Files:** modify `src/toto_ai/operations/finished_draw.py` and `src/toto_ai/cli.py`;
add `tests/test_post_draw_review.py` and, if needed, a project-local
notification helper test.

1. Write RED tests that 15/15 settlement creates `review-request.json` with
   drawing/package identity, settlement hash, best hits/coupon ranks,
   category 13/14/15 counts, fixed/zero-exposure misses, VOID orders, known
   return/ROI status, `AWAITING_USER_REVIEW`, and `requested_at`.
2. Test advisory notification success/failure: notification failure is
   recorded but leaves the durable state awaiting review and never retries or
   changes settlement.
3. Implement explicit machine-readable commands (names may follow the
   existing CLI convention) for status, accept, decline, and completed
   postmortem. Enforce transitions only:
   `AWAITING_USER_REVIEW -> REVIEW_REQUESTED` or `REVIEW_SKIPPED`, then
   `REVIEW_COMPLETE` only with an immutable Markdown path/hash.
4. Add status integration that lists every unacknowledged request and asks
   exactly `Разбираем пакет тиража N?`; no request may become reviewed silently.
5. Generate a deterministic Markdown postmortem comparing actual result/VOID,
   best coupon/hit distribution, exposure, BK/pool/Pin/sports-shadow/selected
   probabilities, fixed and zero-exposure misses, estimated EV versus official
   payout, and concrete errors. State that one drawing cannot establish
   causality or profitability. Hash the final bytes and reject edits.
6. Run review tests and verify package-free NO BET has a valid review path.

## Task 7 — Verification and local handoff

Run focused suites after each task, then:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m ruff check .
PYTHONPATH=src .venv/bin/python -m toto_ai.cli paper-package-show --help
PYTHONPATH=src .venv/bin/python -m toto_ai.cli post-draw-plan --help
PYTHONPATH=src .venv/bin/python -m toto_ai.cli post-draw-run --help
git diff --check
git status --short
```

Inspect all paper bytes with a strict parser in a test, including final LF,
UTF-8, no CR/NUL, 15 outcomes, uniqueness, order, and cost. Run the existing
operator-export, scheduler, and finished-lifecycle suites again after Ruff.
During a later implementation, update the relevant memory-bank files before
each feature is considered complete; do not modify or publish memory as part
of this planning task. No push, PR, external service, automatic LaunchAgent
installation, or wager placement is part of this plan.
