# Task 1 Report

## Result

- Status: `DONE_WITH_CONCERNS`
- Commit: `59da2b2` (`Add expected value domain math`)
- Branch: `codex/hybrid-direct-package-experiment`

## Files Changed

- `src/toto_ai/ev/__init__.py`
- `src/toto_ai/ev/models.py`
- `src/toto_ai/ev/prize.py`
- `tests/test_ev_prize.py`
- `memory-bank/CURRENT_STATE.md`

## TDD Evidence

The required red command was run before production implementation:

```text
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
ERROR collecting tests/test_ev_prize.py
ModuleNotFoundError: No module named 'toto_ai.ev'
1 error in 0.17s
exit_code=2
```

## Verification

Focused tests:

```text
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
.......                                                                  [100%]
7 passed in 0.14s
```

Focused Ruff:

```text
../../.venv/bin/python -m ruff check src/toto_ai/ev tests/test_ev_prize.py
All checks passed!
```

Full tests:

```text
../../.venv/bin/python -m pytest -q
295 passed in 5.17s
```

Full Ruff:

```text
../../.venv/bin/python -m ruff check .
All checks passed!
```

## Concerns

The required `models.py` contract imports NumPy, but `pyproject.toml` does not
declare NumPy directly. That file is outside Task 1 ownership, and NumPy is
available in the current virtual environment through the existing dependency
set. A later task or dependency-maintenance change should declare it directly.

## Fix Review

- Status: `DONE_WITH_CONCERNS`
- Commit: `2aaac15` (`Fix expected value domain invariants`)
- Files changed:
  - `src/toto_ai/ev/__init__.py`
  - `src/toto_ai/ev/models.py`
  - `src/toto_ai/ev/prize.py`
  - `tests/test_ev_prize.py`
  - `memory-bank/CURRENT_STATE.md`
  - This review section was appended to `.superpowers/sdd/task-1-report.md`.

Focused tests:

```text
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
40 passed in 0.12s
```

Full tests:

```text
../../.venv/bin/python -m pytest -q
328 passed in 6.21s
```

Ruff:

```text
../../.venv/bin/python -m ruff check src/toto_ai/ev tests/test_ev_prize.py
All checks passed!

../../.venv/bin/python -m ruff check .
All checks passed!
```

Concerns:

- NumPy remains undeclared in `pyproject.toml` as required by the Task 3
  schedule; the current environment provides it, but dependency declaration
  remains a later task.

## Second Fix Wave

- Status: `DONE_WITH_CONCERNS`
- Scope: stake validation parity, deep immutable normalization, and
  buffer-level NumPy array immutability.

TDD red command:

```text
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
......FFFF.......................FFFFF..........                         [100%]
9 failed, 39 passed in 0.19s
```

Focused tests after implementation:

```text
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
................................................                         [100%]
48 passed in 0.16s
```

Focused Ruff:

```text
../../.venv/bin/python -m ruff check src/toto_ai/ev tests/test_ev_prize.py
All checks passed!
```

Full tests:

```text
../../.venv/bin/python -m pytest -q
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 64%]
........................................................................ [ 85%]
................................................                         [100%]
336 passed in 4.96s
```

Full Ruff:

```text
../../.venv/bin/python -m ruff check .
All checks passed!
```

Concerns:

- NumPy remains undeclared in `pyproject.toml` as required by the Task 3
  schedule; this fix wave intentionally does not edit that file.
