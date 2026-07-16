# Task 4 Report: Deterministic Runner Reports

## Status

Implemented and verified on `feature/initial-toto-ai` from `d99bbb7`.

## RED / GREEN

1. RED

   Command: `.venv/bin/python -m pytest -q tests/test_runner_reports.py`

   Result: exit 2 during collection with the expected
   `ModuleNotFoundError: No module named 'toto_ai.runner.reports'`.

2. First implementation check

   Command: `.venv/bin/python -m pytest -q tests/test_runner_reports.py`

   Result: exit 2 during collection. The default `RunnerReportLinks()` instance
   called `_normalize_paths` before that helper was defined. The helper was
   moved above the dataclass.

3. GREEN

   Command: `.venv/bin/python -m pytest -q tests/test_runner_reports.py`

   Result: `12 passed in 0.34s`.

4. Deterministic GREEN repeat

   Command: `.venv/bin/python -m pytest -q tests/test_runner_reports.py`

   Result: `12 passed in 0.37s`; repeated report bytes matched exactly.

5. Focused Ruff

   Command: `.venv/bin/python -m ruff check src/toto_ai/runner/reports.py tests/test_runner_reports.py`

   Initial result: one `B008` callable-default finding. Replaced the callable
   default with an immutable module-level empty-links singleton.

   Final result: `All checks passed!`.

6. Full pytest

   Command: `.venv/bin/python -m pytest -q`

   Result: `860 passed in 67.20s (0:01:07)`.

7. Full Ruff

   Command: `.venv/bin/python -m ruff check .`

   Result: `All checks passed!`.

## Files

- `src/toto_ai/runner/reports.py`
- `src/toto_ai/runner/__init__.py`
- `tests/test_runner_reports.py`
- `memory-bank/CURRENT_STATE.md`
- `.superpowers/sdd/task-4-report.md`

The pre-existing `.superpowers/sdd/task-3-report.md` verification sync was
included by the controller in the final fix commit after independently
confirming `848 passed in 45.95s`; it does not change Task 4 behavior.

## Self-Review

- Run identity is the first 12 lowercase SHA-256 characters over canonical
  target ID/number/deadline/fingerprint, preflight time, runner configuration,
  and literal `api-sports`.
- JSON uses sorted keys, compact separators, and ASCII encoding.
- The payload is explicit; no dataclass-wide serialization, NumPy arrays,
  probability matrices, cache paths, environment values, or diagnostic
  `top_coupons` can enter artifacts.
- `NO BET` forces an empty serialized coupon list. `PLAY` and `RESEARCH ONLY`
  use only `EVPackage.coupons`.
- Output/input collisions are resolved and rejected before directory or file
  writes.
- Both final artifacts use same-directory temporaries and backups. Existing
  pairs restore byte-for-byte after a second-install `KeyboardInterrupt`; new
  partial pairs are removed; temporary files are cleaned.
- Public exports are additive. Runner config, orchestration, result, collector,
  audit, timing, EV, category, budget, and probability definitions are
  unchanged.

## Concerns

- CLI construction and passing external/EV report links remain intentionally
  deferred to Task 5.

## Review Fix Wave: Final Provenance and Transaction Cleanup

Status: all Task 4 review findings fixed and verified from `6a93110`.

### RED / GREEN Evidence

1. Main RED

   Command: `.venv/bin/python -m pytest -q tests/test_runner_orchestration.py tests/test_runner_reports.py`

   Result: `13 failed, 50 passed in 75.71s`. Failures were the missing
   `final_fingerprint` field/propagation/serialization and missing exclusive
   transaction-write helpers. The lexical and symlink collision regressions
   already passed against the existing resolve-based rejection.

2. Timing-observation RED

   Command: `.venv/bin/python -m pytest -q tests/test_runner_orchestration.py::test_result_rejects_mismatched_final_fingerprint_with_checked_timing`

   Result: `1 failed in 40.91s`; a checked timing observation did not yet force
   the observed final fingerprint to match the preflight pin.

3. Focused GREEN

   Command: `.venv/bin/python -m pytest -q tests/test_runner_orchestration.py tests/test_runner_reports.py tests/test_runner_timing.py`

   Result: `115 passed in 0.34s`.

4. Focused Ruff

   Command: `.venv/bin/python -m ruff check src/toto_ai/runner/models.py src/toto_ai/runner/orchestration.py src/toto_ai/runner/reports.py tests/test_runner_orchestration.py tests/test_runner_reports.py`

   Result: `All checks passed!`.

5. Full pytest

   Command: `.venv/bin/python -m pytest -q`

   Result: `870 passed in 169.32s (0:02:49)`.

6. Full Ruff

   Command: `.venv/bin/python -m ruff check .`

   Result: `All checks passed!`.

### Review Fix Summary

- `DrawingRunnerResult.final_fingerprint` records `None` before final
  resolution, the observed mismatch fingerprint on a fail-closed target
  change, and the matching observed fingerprint before any later phase.
- Result validation rejects missing, malformed, unstarted, or post-final
  inconsistent provenance. JSON emits the field verbatim, including `null`.
- Report publication derives all four transaction paths from one token before
  writes, creates temp and backup files with exclusive mode, and unconditionally
  cleans every known path after interruptions or publication rollback.
- KeyboardInterrupt regressions cover partial temp writes and partial backup
  creation. Lexical and symlink aliases are rejected before output writes.
