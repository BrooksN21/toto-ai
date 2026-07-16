# Task 6 Report: Safe Drawing Runner Acceptance

## Delivered

- Added `tests/test_runner_end_to_end.py` with deterministic fake clock and
  sleeper coverage through real runner orchestration, prospective collection,
  SQLite persistence/read-only timing lookup, audit, EV boundary, and reports.
- Added network guards for sockets, `requests`, and installed `httpx` entry
  points; no test uses real sleep or a betting interface.
- Covered T-21/T-19/T-5 behavior, target mutation, 15 dispositions, exact
  fingerprint binding, day-five expansion, multi-day/unresolved vetoes,
  fallback/PENDING non-interference, retry and EV cutoffs, banks
  4800/6000/9600, deterministic bytes, secret-bearing provider failure
  sanitation, and report rollback/interruption.
- Fixed equal-timestamp snapshot ordering in SQLite: latest reads now use
  append-order `rowid` before collection-ID order, so a final progressive pass
  cannot lose to its base pass under deterministic clocks.

## Verification

- `tests/test_runner_end_to_end.py`: 13 passed.
- Required focused suite: 237 passed.
- Full pytest: 898 passed.
- Ruff: `All checks passed!`.
- `run-drawing`, `collect-external-odds`, and `ev-package` help smokes exited
  successfully.
- `git diff --check` passed.

## Constraints Preserved

- No probability, EV, payout, category, bank, stake, consensus, gate, or
  timing definition changed.
- External probabilities remain audit-only.
- The 30-drawing/450-event prospective gate remains `PENDING`.
