# Task 1 Report: Immutable Runner Domain and UTC Timing

## Status

`DONE`

## Implementation

- Added immutable `DrawingRunnerConfig` with the existing strict divisible-bank
  validation, default stake `30`, default mode `playable`, and validated T-20 /
  T-5 settings.
- Added `PinnedDrawing` and `pin_drawing()` using the canonical deterministic
  target fingerprint and strict lowercase SHA-256 fingerprint validation.
- Added immutable UTC-only `RunnerSchedule`, exact runner-window boundaries,
  and injected-clock waiting that rechecks wall time after every bounded sleep.
- Added public exports from `toto_ai.runner`.

## Files

- `src/toto_ai/runner/__init__.py`
- `src/toto_ai/runner/models.py`
- `src/toto_ai/runner/timing.py`
- `tests/test_runner_timing.py`
- `memory-bank/CURRENT_STATE.md`

## TDD Evidence

RED, before runner implementation:

```text
.venv/bin/python -m pytest -q tests/test_runner_timing.py
ModuleNotFoundError: No module named 'toto_ai.runner'
1 error during collection
```

GREEN:

```text
.venv/bin/python -m pytest -q tests/test_runner_timing.py
50 passed in 0.14s

.venv/bin/python -m ruff check src/toto_ai/runner tests/test_runner_timing.py
All checks passed!
```

## Full Verification

```text
.venv/bin/python -m pytest -q
796 passed in 7.92s

.venv/bin/python -m ruff check .
All checks passed!

git diff --check
exit code 0
```

## Self-Review

- Public interfaces and defaults match the task brief.
- UTC validation, strict integer handling, canonical target pinning, exact
  T-20/T-5 boundaries, sleep clamping, wall-clock jumps, and no-sleep terminal
  states are covered by focused tests.
- No category, cover, budget, stake, probability, or fingerprint definition
  was changed.
- Diff scope is limited to the assigned runner package, timing tests, and the
  required current-state record and task report.

## Concerns

None.

## Reviewed Defect Fix Evidence

RED, after adding the regression test and before the model fix:

```text
.venv/bin/python -m pytest -q tests/test_runner_timing.py -k valid_but_wrong_fingerprint
F                                                                        [100%]
FAILED tests/test_runner_timing.py::test_pinned_drawing_rejects_valid_but_wrong_fingerprint
E       Failed: DID NOT RAISE ValueError
1 failed, 50 deselected in 0.13s
```

GREEN, after validating the canonical target fingerprint in
`PinnedDrawing.__post_init__`:

```text
.venv/bin/python -m pytest -q tests/test_runner_timing.py
51 passed in 0.13s

.venv/bin/python -m ruff check src/toto_ai/runner/models.py tests/test_runner_timing.py
All checks passed!
```

`pin_drawing()` behavior is unchanged. The fix rejects a valid lowercase
64-character digest unless it exactly equals `target_fingerprint(...)` for the
provided target.
