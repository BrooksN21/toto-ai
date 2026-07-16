# Task 6 Report: Safe Drawing Runner Acceptance Review Fixes

**Status:** Findings implemented and verified; independent review approval is
pending.

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
- Canonicalized suppressed terminal package summaries in JSON and Markdown:
  `NO BET`, no coupons, zero selected count/cost/payout, full unused bank, and
  absent modeled ROI.
- Added a real `run-drawing` command-boundary sentinel-key scenario with a
  chained provider failure. Output, recursive exception `str`/`repr`, SQLite,
  cache, and every scenario artifact are secret-free.
- Captured the complete real 15-row `EVInput`, independently normalized the
  TotoBrief BK matrix, and proved extreme external consensus versus complete
  fallback produces identical EV input and selected package output.
- Added a real SQLite/audit regression proving same-timestamp append order wins
  exact eligibility and audit deduplication while distinct timestamps remain
  primary.

## RED/GREEN

- RED: `6 failed, 10 passed` because suppressed manifests had `ev: null`.
- GREEN: focused report/end-to-end/storage regression `34 passed`.

## Verification

- `tests/test_runner_end_to_end.py`: 15 passed as part of the final suite.
- Review-focused runner/storage/audit/EV suite: 282 passed.
- Full pytest: 901 passed.
- Ruff: `All checks passed!`.
- `run-drawing`, `collect-external-odds`, and `ev-package` help smokes exited
  successfully.
- `git diff --check` passed.

## Constraints Preserved

- No probability, EV, payout, category, bank, stake, consensus, gate, or
  timing definition changed.
- External probabilities remain audit-only.
- The 30-drawing/450-event prospective gate remains `PENDING`.
