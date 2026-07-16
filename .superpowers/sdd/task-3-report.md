# Task 3 Report

## Status

Provider-neutral runner orchestration is complete and ready to commit with the
required subject `Add safe drawing runner orchestration`.

## RED

Command:

```text
.venv/bin/python -m pytest -q tests/test_runner_orchestration.py
```

Result: expected collection error because `DrawingRunnerResult` was not yet
exported from `toto_ai.runner`.

Self-review added two further RED regressions. They proved the terminal model
initially accepted `PLAY` with non-playable timing and accepted later phase
timestamps with `final_started_at=None`.

## GREEN

- Focused orchestration: `32 passed in 8.95s`.
- Focused timing/orchestration: `83 passed in 0.25s`.
- Focused Ruff: `All checks passed!`.
- Full pytest: `838 passed in 20.99s`.
- Full Ruff: `All checks passed!`.

No test uses real network, filesystem, or sleep behavior.

## Files

- `src/toto_ai/runner/models.py`: immutable terminal result and invariants.
- `src/toto_ai/runner/orchestration.py`: injected runner state machine.
- `src/toto_ai/runner/__init__.py`: public result and orchestration exports.
- `tests/test_runner_orchestration.py`: phase, cutoff, decision, and invariant coverage.
- `memory-bank/CURRENT_STATE.md`: completed Task 3 state and verification.
- `.superpowers/sdd/task-3-report.md`: this report.

## Self-Review

- Confirmed phase order is preflight, wait, final resolve, collect, timing,
  audit, and EV.
- Confirmed exact final target comparison covers ID, number, deadline, and
  fingerprint before provider access.
- Confirmed T-5 is inclusive before every bound phase and after EV; late EV
  output is discarded with `ev_run=None` in Playable and Research modes.
- Confirmed timing vetoes still retain audit diagnostics but skip EV in
  Playable mode.
- Confirmed coverage `PENDING` cannot enter the package builder input or alter
  its decision.
- Confirmed ordinary zero-cost EV-threshold `NO BET` retains diagnostics only,
  with no selected package coupons or cost.
- Tightened terminal invariants for exact playable timing and contiguous phase
  timestamps after dedicated failing regressions.

## Concerns

None. CLI, report publication, filesystem, and real provider wiring remain
intentionally outside Task 3 ownership.

## Review Fix Wave

### RED

Command:

```text
.venv/bin/python -m pytest -q tests/test_runner_orchestration.py
```

Result: `8 failed, 34 passed in 2.61s`.

- Five synchronous progress callbacks advanced the injected clock to T-5 after
  notification and still started final resolve, collection, timing, audit, or
  EV work.
- Success and fail-closed invalid terminal records emitted `complete` before
  `DrawingRunnerResult` validation raised.
- `PLAY` accepted an attached EV run with matching fingerprint but `unknown`
  EV timing.

### GREEN And Verification

- Added post-notification cutoff checks immediately before all five bound
  phases; the matching dependency callback is not invoked at T-5.
- Constructed and validated terminal results before `complete` for successful
  and fail-closed exits.
- `PLAY` now requires the runner timing and attached EV-run timing to be exact
  `playable`.
- Coverage non-interference is covered for `GO`, `PENDING`, and `STOP`; early
  target-mismatch, cutoff, and timing-veto exits assert their progress phases.
- Focused timing/orchestration pytest: `93 passed in 0.28s`.
- Focused Ruff: `All checks passed!`.
- Full pytest: `848 passed`.
- Full Ruff: `All checks passed!`.
