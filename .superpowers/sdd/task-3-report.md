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

## Mathematical Review Fix

Status: DONE_WITH_CONCERNS

This section supersedes the original numerical-stability and benchmark
self-review statements above.

### Red Evidence

- Baseline focused suite before new regressions: `35 passed in 0.55s`.
- Numerical regression run: `5 failed, 26 passed in 0.22s`. Failures proved the
  absolute cutoff erased `1e-40`, material negatives were accepted, exact crowd
  DP was absent, a selected 15-event `1e-90` tail was unavailable, and the
  five-event extreme-positive surface failed denominator validation.
- Benchmark regression run: `3 failed, 42 passed in 1.28s`. Failures proved the
  scalar tail verifier and independent direct coupon verifier were absent and
  hash length incorrectly affected PASS.

### Fixes

- Replaced FFT crowd-tail recovery with chunked independent-marginal
  Poisson-binomial DP over every actual-result state and every requested
  category. Chunks bound temporary DP memory without truncating states.
- Changed `ternary_convolve()` to copy the real inverse result, preserve all
  positive values, clip only scale-bounded negative FFT noise, and raise on
  material negatives.
- Replaced larger-space benchmark self-checks with independent scalar sampled
  crowd tails and direct vectorized fixed-coupon sums over all actual-result
  states. The direct verifier uses literal official regular/jackpot
  coefficients and direct hit comparisons, not production DP, kernels,
  convolution, or category-fund maps.
- Removed hashes from the PASS predicate. Hashes remain output fingerprints;
  determinism tests compare repeated computations.
- Added a successful official-component path test without full-state
  allocation, literal official category expectations, arbitrary-fund oracle
  equivalence retention, and manageable extreme-positive regressions.

### Verification Evidence

- Focused pytest: `45 passed in 0.40s`.
- Full pytest: `417 passed in 5.54s`.
- Focused Ruff: `All checks passed!`.
- Full Ruff: `All checks passed!`.
- Small benchmark command:
  `PYTHONPATH=src ../../.venv/bin/python -m toto_ai.cli benchmark-ev --events 5 --samples 10`.
- Small benchmark result: 5 events, 243 coupons, `0.116300 s`, `62.84 MiB`
  peak resident memory, minimum denominator `1828.14404892`, maximum EV error
  `1.626e-19`, maximum sampled crowd-tail error `0.000e+00`, status `PASS`.

### Concerns

- The full 15-event benchmark was not run, per instruction. Runtime and peak
  memory of the exact chunked denominator DP plus full coupon FFT remain to be
  measured in Task 7 acceptance.
- Normal tests keep full-state computations at five events or fewer. The
  selected-state 15-event regression evaluates one tail only, and the
  larger-space branch composes helpers proven independently on small spaces.

### Fix Commit

`a459bbd30c65d383c24a57b781e0958f8beab859` —
`Fix exact EV numerical stability and verification`

## Final Task 3 Formula Fix

Status: DONE

### Red Evidence

The focused regression suite failed as intended before this fix: production DP
renormalized tolerance-accepted rows through `1 - p`, the C-order crowd joint
`R` was not materialized, and the scalar benchmark independently used `1 - p`.

### Fixes

- Production now materializes C-order Kronecker `Q` and `R`, verifies finite
  `R.sum()` mass within `1e-12`, stores that value as `crowd_mass`, and releases
  `R` before category work. The denominator DP does not use `R` and does not
  truncate states.
- Production Poisson-binomial DP, scalar benchmark tails, and direct benchmark
  coupon sums derive non-match mass from the other supplied row values via
  `row_sum - selected match`, never literal `1 - p`.
- Regressions use rows that are accepted within tolerance but do not sum
  bit-exactly to one. They prove agreement among production tails/surfaces, the
  brute-force reference, scalar benchmark tails, and direct benchmark coupon
  components; the existing tiny-positive checks remain intact.

### Verification Evidence

- Focused pytest: `48 passed in 0.44s`.
- Full pytest: `420 passed in 5.46s`.
- Five-event benchmark: 243 coupons, `0.121526 s`, `62.00 MiB` peak resident
  memory, maximum EV error `1.626e-19`, maximum sampled crowd-tail error
  `0.000e+00`, verification `PASS`.
- The 15-event benchmark was not run, as required.

### Concerns

The full 15-event runtime and peak memory acceptance measurement remains Task
7 work; this change did not run it.
