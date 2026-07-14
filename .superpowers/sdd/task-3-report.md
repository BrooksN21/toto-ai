# Task 3 Report

Status: DONE

## Red Evidence

Command:

```bash
../../.venv/bin/python -m pytest tests/test_ev_ternary.py tests/test_ev_benchmark.py -q
```

Result: collection failed with two expected `ModuleNotFoundError` errors for
`toto_ai.ev.ternary` and `toto_ai.ev.benchmark` before production code existed.

## Implementation

- `src/toto_ai/ev/ternary.py`: C-order indexing, Hamming kernels, oriented
  ternary convolution, sequential exact EV accumulation, reusable official
  components, materialization, and arbitrary-fund convenience surface.
- `src/toto_ai/ev/benchmark.py`: deterministic inputs, full small-space oracle
  verification, larger-space fixed-coupon direct sums, hashes, and resource
  diagnostics.
- `tests/test_ev_ternary.py`: transform orientation, oracle equivalence,
  validation, callback interruption, component materialization, and ownership.
- `tests/test_ev_benchmark.py`: deterministic benchmark diagnostics,
  validation, full-oracle verification, and CLI output.
- `pyproject.toml`: direct `numpy>=1.24` dependency.
- `src/toto_ai/cli.py`: `benchmark-ev` command and Rich diagnostics table.
- `memory-bank/CURRENT_STATE.md`: Task 3 state, API choice, and evidence.

## API Choice

The convenience API is explicit:

```python
compute_ev_surface(
    true_probabilities,
    crowd_probabilities,
    pool_sum,
    category_funds_by_hits,
    stake,
    minimum_category,
    progress_callback=None,
)
```

It accepts the oracle's arbitrary category-fund mapping. Production
`compute_ev_components(EVInput, progress_callback=None)` remains restricted to
official 9..15 coefficients and returns separate regular-prize and jackpot unit
arrays.

## Verification

- Focused pytest: `35 passed in 0.36s`.
- Full pytest: `407 passed in 5.47s`.
- Focused Ruff: `All checks passed!`.
- Full Ruff: `All checks passed!`.
- CLI help: exit 0; `--events` range 1..15 and positive `--samples` shown.
- Small CLI benchmark: 5 events, 243 coupons, 0.160828 s, 65.88 MiB peak,
  minimum denominator 1828.14404892, maximum absolute error `1.897e-19`,
  verification `PASS`.
- The virtualenv editable install targets the main checkout, so CLI smoke
  commands used `PYTHONPATH=src` to execute this worktree's source.
- The 15-event benchmark was not run, as required; it remains Task 7 acceptance.

## Self-Review

- Numerical tolerance: full surfaces use `rtol=1e-10`, `atol=1e-12`; input and
  product masses require absolute error at most `1e-12`; tiny FFT residuals
  below `1e-15` are zeroed.
- Validation: strict integer domains reject booleans; matrices, masses, funds,
  pool, categories, dimensions, and every denominator fail closed.
- Memory ownership: categories release kernel, tail, denominator, weighted
  probability, and convolution temporaries before progress advances; returned
  arrays are copied into the existing immutable domain models.
- Determinism: inputs, sample indices, C-order layout, direct-sum orientation,
  and rounded little-endian hashes are fixed. Repeated small runs produce equal
  samples and hashes.

## Commit

`Add exact ternary expected value engine` (hash reported in the final handoff).

## Concerns

None for Task 3 acceptance. Full 15-event runtime and peak memory remain
deliberately unmeasured until Task 7.
