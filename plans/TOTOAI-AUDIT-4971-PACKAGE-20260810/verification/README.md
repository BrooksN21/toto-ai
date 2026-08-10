# Quality-v2 verification

## Current release tier (2026-08-10)

Current collection is 1,713 tests: 1,700 default/release tests plus 13 marked
`heavy`/`research` tests. The default command completed with:

```text
1700 passed, 13 deselected in 103.71s (0:01:43)
real 104.19
```

Ruff and `git diff --check` are separate release gates. The marker policy and
exact default/heavy/all commands are in `docs/testing.md`.

## Last successful heavy evidence

The multi-minute suite was not rerun as part of the test-architecture change.
Its latest standalone successful outputs are retained:

- frozen 4967: `1 passed in 155.51s` (selector core 163.110503s captured when
  refreshing the artifact);
- frozen 4969: `1 passed in 89.07s` (core 87.664523s);
- frozen 4970: `1 passed in 89.21s` (core 86.505469s);
- full bank-4,980 four-sensitivity runtime: `1 passed in 299.58s`, measured
  299.254715s against a 360s budget.

A current small heavy fail-closed smoke was run after marker migration:

```text
tests/test_runner_offline_replay.py::test_offline_replay_rejects_stale_schedule_before_runner_output
1 passed in 13.20s
```

The older verbatim collection/partition files in this directory are preserved
as historical verification output; their 1,690-test total predates the current
review-hardening tests and marker split and must not be presented as current
full-suite verification.
