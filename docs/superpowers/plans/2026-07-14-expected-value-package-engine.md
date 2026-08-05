# Expected-Value Package Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mathematically verified engine that evaluates all 14,348,907 BaltBet coupons by modeled monetary EV and forms Research or Playable packages for any bank divisible by the stake.

**Architecture:** Add a focused `toto_ai.ev` package. Pure prize/crowd math and a small brute-force oracle establish correctness first; a NumPy ternary-convolution engine then computes the full EV surface. Package selection, fresh TotoBrief input, reporting, CLI, and chronological evaluation consume that surface without changing or truncating it.

**Tech Stack:** Python 3.10+, NumPy 1.24+, SQLAlchemy, requests, Typer, Rich, pytest, Ruff.

## Global Constraints

- Evaluate the complete `3^15 = 14,348,907` coupon space; no candidate truncation.
- Bank must be positive and exactly divisible by the configurable stake; stake defaults to 30 RUB.
- Research mode always reports top coupons; Playable mode returns `NO BET` when no coupon reaches the configured gross-EV threshold.
- Do not lower EV thresholds automatically or force full-bank utilization.
- Initial true probabilities are normalized TotoBrief `bk_*`; crowd probabilities are smoothed TotoBrief `pool_*` marginals under an explicitly reported independence assumption.
- `possible_winnings` is either explicit or `pool_sum * prize_fund_factor`; the default factor is 1.0 and must be disclosed.
- Historical modeled ROI is not observed ROI and must never be described as profitability evidence.
- A timeout or interruption may not return a partial result as `PLAY`.
- The old frozen hybrid holdout remains excluded from strategy selection.
- Run pytest and Ruff before every commit; update `memory-bank/CURRENT_STATE.md` for each meaningful commit.

---

## File Structure

New production files:

- `src/toto_ai/ev/models.py`: immutable input, configuration, surface, coupon, package, and backtest result types.
- `src/toto_ai/ev/prize.py`: bank validation, official category funds, pool normalization, and Jeffreys smoothing.
- `src/toto_ai/ev/reference.py`: independent brute-force EV oracle for small event counts.
- `src/toto_ai/ev/ternary.py`: base-3 indexing, Hamming kernels, ternary convolution, and exact full-space EV surface.
- `src/toto_ai/ev/package.py`: deterministic ranking, dynamic-bank package selection, decision, and derived brief.
- `src/toto_ai/ev/drawing.py`: fresh TotoBrief payload parsing and historical SQLite input loading.
- `src/toto_ai/ev/reports.py`: atomic package and modeled-backtest CSV/Markdown reports.
- `src/toto_ai/ev/backtest.py`: chronological threshold/bank evaluation with explicit frozen-holdout exclusion.
- `src/toto_ai/ev/benchmark.py`: full-space timing, memory, and sampled direct-sum verification.

Modified production files:

- `pyproject.toml`: declare NumPy directly.
- `src/toto_ai/cli.py`: add `benchmark-ev`, `ev-package`, and `backtest-ev`.

New tests mirror each production file under `tests/`.

---

### Task 1: Domain Models, Prize Funds, and Crowd Smoothing

**Files:**
- Create: `src/toto_ai/ev/__init__.py`
- Create: `src/toto_ai/ev/models.py`
- Create: `src/toto_ai/ev/prize.py`
- Create: `tests/test_ev_prize.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Produces: `EVConfig`, `EVInput`, `EVComponents`, `EVSurface`, `RankedCoupon`, `EVPackage`, `validate_bank()`, `category_funds()`, `normalize_triplet()`, and `smooth_crowd_matrix()`.
- Consumes: no new project interfaces.

- [ ] **Step 1: Write failing prize and validation tests**

```python
import math

import pytest

from toto_ai.ev.models import EVConfig
from toto_ai.ev.prize import category_funds, smooth_crowd_matrix, validate_bank


def test_category_funds_follow_official_cumulative_allocations():
    funds = category_funds(possible_winnings=1800.0, jackpot=1000.0)
    assert funds == {
        9: 800.0,
        10: 400.0,
        11: 200.0,
        12: 100.0,
        13: 100.0,
        14: 200.0,
        15: 1000.0,
    }


@pytest.mark.parametrize("bank", [4800, 6000, 9600])
def test_dynamic_bank_accepts_stake_multiples(bank):
    assert validate_bank(bank, 30) == bank // 30


def test_dynamic_bank_rejects_non_multiple():
    with pytest.raises(ValueError, match="divisible"):
        validate_bank(5000, 30)


def test_jeffreys_smoothing_makes_rounded_zero_positive():
    smoothed = smooth_crowd_matrix(((0.0, 0.4, 0.6),), 3_000_000.0, 30)
    assert all(value > 0 for value in smoothed[0])
    assert math.isclose(sum(smoothed[0]), 1.0)


def test_ev_config_does_not_force_full_bank_use():
    config = EVConfig(bank=6000, stake=30, mode="playable", min_gross_ev=1.0)
    assert config.max_coupons == 200
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `../../.venv/bin/python -m pytest tests/test_ev_prize.py -q`

Expected: collection fails because `toto_ai.ev` does not exist.

- [ ] **Step 3: Implement immutable domain types**

Create `models.py` with these exact public fields:

```python
from dataclasses import dataclass
from typing import Literal

import numpy as np

ProbabilityMatrix = tuple[tuple[float, float, float], ...]
EVMode = Literal["research", "playable"]


@dataclass(frozen=True)
class EVConfig:
    bank: int
    stake: int = 30
    mode: EVMode = "research"
    min_gross_ev: float = 1.0
    prize_fund_factor: float = 1.0
    possible_winnings: float | None = None

    @property
    def max_coupons(self) -> int:
        return validate_config_bank(self.bank, self.stake)


@dataclass(frozen=True)
class EVInput:
    drawing_id: int
    drawing_number: int | None
    true_probabilities: ProbabilityMatrix
    crowd_probabilities: ProbabilityMatrix
    pool_sum: float
    jackpot: float
    possible_winnings: float
    probability_sources: tuple[str, ...]
    fetched_at: str


@dataclass(frozen=True)
class EVComponents:
    possible_winnings_ev_per_ruble: np.ndarray
    jackpot_ev_per_ruble: np.ndarray
    event_count: int
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float


@dataclass(frozen=True)
class EVSurface:
    gross_ev: np.ndarray
    event_count: int
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float


@dataclass(frozen=True)
class RankedCoupon:
    rank: int
    coupon: str
    gross_ev: float
    net_ev: float


@dataclass(frozen=True)
class EVPackage:
    decision: Literal["PLAY", "NO BET", "RESEARCH ONLY"]
    coupons: tuple[RankedCoupon, ...]
    cost: int
    unused_bank: int
    expected_payout: float
    modeled_roi: float | None
    derived_brief: tuple[str, ...]
```

Keep `validate_config_bank()` private in `models.py` and make it enforce the
same rule as `prize.validate_bank()` without importing `prize.py`, avoiding a
cycle.

- [ ] **Step 4: Implement official funds and smoothing**

Implement `prize.py` with exact ratios and finite/non-negative validation:

```python
def category_funds(possible_winnings: float, jackpot: float) -> dict[int, float]:
    _require_non_negative_finite("possible_winnings", possible_winnings)
    _require_non_negative_finite("jackpot", jackpot)
    return {
        9: possible_winnings * 8 / 18,
        10: possible_winnings * 4 / 18,
        11: possible_winnings * 2 / 18,
        12: possible_winnings / 18,
        13: possible_winnings / 18,
        14: possible_winnings / 18 + jackpot / 10,
        15: possible_winnings / 18 + jackpot * 9 / 10,
    }
```

`normalize_triplet()` rejects non-finite or negative values and a zero total.
`smooth_crowd_matrix()` first normalizes each row, computes
`N = pool_sum / stake`, applies `(N * value + 0.5) / (N + 1.5)`, and returns
normalized immutable rows.

- [ ] **Step 5: Run tests and quality checks**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_ev_prize.py -q
../../.venv/bin/python -m ruff check src/toto_ai/ev tests/test_ev_prize.py
```

Expected: all focused tests pass; Ruff reports `All checks passed!`.

- [ ] **Step 6: Update project state and commit**

Record Task 1 interfaces in `memory-bank/CURRENT_STATE.md`, then run the full
suite and commit:

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
git add src/toto_ai/ev tests/test_ev_prize.py memory-bank/CURRENT_STATE.md
git commit -m "Add expected value domain math"
```

Expected: 288 existing tests plus the new tests pass.

---

### Task 2: Independent Brute-Force EV Oracle

**Files:**
- Create: `src/toto_ai/ev/reference.py`
- Create: `tests/test_ev_reference.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `ProbabilityMatrix`, `category_funds()`, and smoothed crowd probabilities.
- Produces: `joint_distribution()`, `coupon_hits()`, `crowd_qualifying_stake()`, `coupon_payout()`, and `brute_force_gross_ev()`.

- [ ] **Step 1: Write exact small-space tests**

```python
import numpy as np

from toto_ai.ev.reference import brute_force_gross_ev, joint_distribution


def test_joint_distribution_uses_lexicographic_base_three_order():
    matrix = ((0.5, 0.3, 0.2), (0.6, 0.25, 0.15))
    result = joint_distribution(matrix)
    assert np.allclose(result[:3], [0.30, 0.125, 0.075])
    assert np.isclose(result.sum(), 1.0)


def test_one_event_reference_ev_matches_direct_manual_sum():
    true = ((0.5, 0.3, 0.2),)
    crowd = ((0.4, 0.35, 0.25),)
    funds = {1: 90.0}
    result = brute_force_gross_ev(
        true_probabilities=true,
        crowd_probabilities=crowd,
        pool_sum=300.0,
        stake=30,
        category_funds_by_hits=funds,
        minimum_category=1,
    )
    assert np.allclose(result, [0.375, 0.2571428571428571, 0.24])


def test_cumulative_categories_add_for_higher_hit_coupon():
    true = ((1.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    crowd = ((0.5, 0.25, 0.25), (0.5, 0.25, 0.25))
    result = brute_force_gross_ev(
        true_probabilities=true,
        crowd_probabilities=crowd,
        pool_sum=120.0,
        stake=30,
        category_funds_by_hits={1: 60.0, 2: 60.0},
        minimum_category=1,
    )
    assert np.isclose(result[0], 8 / 3)
```

- [ ] **Step 2: Verify the tests fail**

Run: `../../.venv/bin/python -m pytest tests/test_ev_reference.py -q`

Expected: import failure for `toto_ai.ev.reference`.

- [ ] **Step 3: Implement the exhaustive oracle**

Use `itertools.product(range(3), repeat=event_count)` for both actual results
and coupons. Build distributions in C-order so index zero is all `1`, index one
changes the last event to `X`, and index two changes it to `2`.

The public calculation must follow this literal loop structure:

```python
for actual_index, actual in enumerate(states):
    actual_probability = true_joint[actual_index]
    qualifying_stake = {
        category: pool_sum
        * sum(
            crowd_joint[ticket_index]
            for ticket_index, ticket in enumerate(states)
            if coupon_hits(ticket, actual) >= category
        )
        for category in category_funds_by_hits
    }
    for coupon_index, coupon in enumerate(states):
        hits = coupon_hits(coupon, actual)
        payout = sum(
            category_funds_by_hits[category] * stake / qualifying_stake[category]
            for category in category_funds_by_hits
            if category <= hits
        )
        gross_ev[coupon_index] += actual_probability * payout / stake
```

Reject event counts above 8 to prevent accidental use of the reference path for
production 15-event calculations.

- [ ] **Step 4: Run focused tests and add randomized invariants**

Add a fixed-seed test over event counts 1 through 4 asserting finite,
non-negative EV and total probability mass 1. Then run:

```bash
../../.venv/bin/python -m pytest tests/test_ev_reference.py -q
../../.venv/bin/python -m ruff check src/toto_ai/ev/reference.py tests/test_ev_reference.py
```

Expected: all focused tests pass.

- [ ] **Step 5: Update state, run the full suite, and commit**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
git add src/toto_ai/ev/reference.py tests/test_ev_reference.py memory-bank/CURRENT_STATE.md
git commit -m "Add brute force expected value oracle"
```

---

### Task 3: Exact Ternary Full-Space Engine and Benchmark

**Files:**
- Create: `src/toto_ai/ev/ternary.py`
- Create: `src/toto_ai/ev/benchmark.py`
- Create: `tests/test_ev_ternary.py`
- Create: `tests/test_ev_benchmark.py`
- Modify: `pyproject.toml`
- Modify: `src/toto_ai/cli.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `EVInput`, `EVSurface`, `category_funds()`, and the reference oracle.
- Produces: `coupon_from_index()`, `index_from_coupon()`, `hamming_ball_kernel()`, `ternary_convolve()`, `compute_ev_components()`, `materialize_ev_surface()`, `compute_ev_surface()`, `benchmark_ev_engine()`, and CLI `benchmark-ev`.

- [ ] **Step 1: Declare NumPy directly and write transform tests**

Add `"numpy>=1.24"` to project dependencies. Create tests:

```python
import numpy as np

from toto_ai.ev.reference import brute_force_gross_ev
from toto_ai.ev.ternary import (
    compute_ev_surface,
    coupon_from_index,
    hamming_ball_kernel,
    index_from_coupon,
    ternary_convolve,
)


def test_base_three_coupon_index_round_trip():
    for index in range(3**4):
        assert index_from_coupon(coupon_from_index(index, 4)) == index


def test_hamming_kernel_counts_radius_two_ball():
    kernel = hamming_ball_kernel(event_count=4, minimum_hits=2)
    assert kernel.sum() == 1 + 4 * 2 + 6 * 4


def test_ternary_convolution_matches_direct_cyclic_convolution():
    left = np.arange(9, dtype=np.float64)
    right = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0])
    actual = ternary_convolve(left, right, event_count=2)
    expected = np.zeros(9)
    for a in range(9):
        for b in range(9):
            a_digits = divmod(a, 3)
            b_digits = divmod(b, 3)
            index = ((a_digits[0] + b_digits[0]) % 3) * 3 + (
                (a_digits[1] + b_digits[1]) % 3
            )
            expected[index] += left[a] * right[b]
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_exact_engine_matches_reference_for_four_events():
    true = ((0.5, 0.3, 0.2),) * 4
    crowd = ((0.4, 0.35, 0.25),) * 4
    funds = {2: 80.0, 3: 40.0, 4: 20.0}
    exact = compute_ev_surface(true, crowd, 1000.0, funds, 30, 2)
    reference = brute_force_gross_ev(true, crowd, 1000.0, 30, funds, 2)
    assert np.allclose(exact.gross_ev, reference, rtol=1e-10, atol=1e-12)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `../../.venv/bin/python -m pytest tests/test_ev_ternary.py -q`

Expected: import failure for `toto_ai.ev.ternary`.

- [ ] **Step 3: Implement indexing, kernels, and convolution**

Use outcome order `("1", "X", "2")`. Flat arrays use C-order shape
`(3,) * event_count`. Implement convolution as:

```python
def ternary_convolve(left, right, event_count):
    shape = (3,) * event_count
    left_fft = np.fft.fftn(np.asarray(left, dtype=np.float64).reshape(shape))
    right_fft = np.fft.fftn(np.asarray(right, dtype=np.float64).reshape(shape))
    result = np.fft.ifftn(left_fft * right_fft).real.reshape(-1)
    result[np.abs(result) < 1e-15] = 0.0
    return result
```

`hamming_ball_kernel()` sets one for base-3 vectors with at most
`event_count - minimum_hits` non-zero digits.

- [ ] **Step 4: Implement sequential category EV accumulation**

`compute_ev_components()` must:

1. validate matching matrices and category bounds;
2. create exact product arrays `Q` and `R` with repeated Kronecker products;
3. verify both masses within `1e-12` of one;
4. initialize float64 accumulators for possible-winnings EV per ruble and
   jackpot EV per ruble;
5. for each category in ascending order, build one kernel, compute
   `crowd_tail`, reject non-positive/non-finite values, compute
   `f = Q / (pool_sum * crowd_tail)`, convolve `f` with the same kernel, and add
   the unit-fund contribution to the two accumulators using the official
   regular-fund and jackpot coefficients;
6. release category temporaries before the next category;
7. return `EVComponents` with the two arrays and mass diagnostics.

`materialize_ev_surface(components, possible_winnings, jackpot)` performs only:

```python
gross_ev = (
    components.possible_winnings_ev_per_ruble * possible_winnings
    + components.jackpot_ev_per_ruble * jackpot
)
```

`compute_ev_surface()` is the convenience wrapper used by equivalence tests.
This separation lets sensitivity and dynamic-bank runs reuse the heavy exact
calculation.

Accept an optional callback with exact payload:

```python
{"phase": "category", "category": category, "elapsed": elapsed_seconds}
```

Do not add a timeout that returns a partial surface.

- [ ] **Step 5: Add sampled direct-sum verification and benchmark**

`benchmark_ev_engine(event_count=15, sample_count=20)` constructs deterministic
non-uniform matrices, runs the full engine, and records elapsed seconds and peak
resident memory when available. For event counts up to 8 it verifies the whole
surface against the independent brute-force oracle. For 15 events it verifies
probability mass, denominator bounds, deterministic hashes, and 20 fixed
coupon values by a vectorized direct sum over all actual-result states using
the category denominator arrays produced before coupon convolution. This does
not approximate or sample the actual-result space.

Add CLI:

```python
@app.command("benchmark-ev")
def benchmark_ev_command(
    events: int = typer.Option(15, min=1, max=15),
    samples: int = typer.Option(20, min=1),
) -> None:
    result = benchmark_ev_engine(event_count=events, sample_count=samples)
    print(_ev_benchmark_table(result))
```

The table prints event count, coupon count, elapsed time, peak memory, minimum
denominator, maximum sampled absolute error, and verification `PASS/FAIL`.

- [ ] **Step 6: Run equivalence and benchmark tests**

Use event counts no larger than 5 in normal pytest. The full 15-event benchmark
is a mandatory manual acceptance run in Task 7 rather than a routine unit test;
the ordinary suite still runs complete brute-force equivalence on small spaces.

Run:

```bash
../../.venv/bin/python -m pytest tests/test_ev_ternary.py tests/test_ev_benchmark.py -q
../../.venv/bin/python -m ruff check .
```

Expected: transform and reference equivalence pass.

- [ ] **Step 7: Run full verification, update state, and commit**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
git add pyproject.toml src/toto_ai/ev src/toto_ai/cli.py tests/test_ev_ternary.py tests/test_ev_benchmark.py memory-bank/CURRENT_STATE.md
git commit -m "Add exact ternary expected value engine"
```

---

### Task 4: Deterministic Dynamic-Bank Package Selection

**Files:**
- Create: `src/toto_ai/ev/package.py`
- Create: `tests/test_ev_package.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `EVConfig`, `EVSurface`, `RankedCoupon`, and `EVPackage`.
- Produces: `rank_coupon_indices()`, `select_ev_package()`, and `derive_brief()`.

- [ ] **Step 1: Write selection and `NO BET` tests**

```python
import numpy as np

from toto_ai.ev.models import EVConfig, EVSurface
from toto_ai.ev.package import rank_coupon_indices, select_ev_package
from toto_ai.ev.ternary import coupon_from_index


def surface(values):
    return EVSurface(
        gross_ev=np.array(values, dtype=np.float64),
        event_count=2,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=1.0,
    )


def test_research_mode_fills_comparison_package_even_below_one():
    package = select_ev_package(
        surface([0.8, 0.9, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]),
        EVConfig(bank=60, stake=30, mode="research"),
    )
    assert package.decision == "RESEARCH ONLY"
    assert [row.coupon for row in package.coupons] == ["1X", "11"]


def test_playable_mode_returns_no_bet_below_threshold():
    package = select_ev_package(
        surface([0.99] * 9),
        EVConfig(bank=60, stake=30, mode="playable", min_gross_ev=1.0),
    )
    assert package.decision == "NO BET"
    assert package.coupons == ()
    assert package.cost == 0


def test_playable_mode_does_not_spend_bank_on_low_ev_coupons():
    package = select_ev_package(
        surface([1.2, 1.1, 0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.93]),
        EVConfig(bank=90, stake=30, mode="playable", min_gross_ev=1.0),
    )
    assert len(package.coupons) == 2
    assert package.cost == 60
    assert package.unused_bank == 30


def test_equal_ev_uses_coupon_string_order():
    order = rank_coupon_indices(surface([1.0] * 9))
    assert [coupon_from_index(int(index), 2) for index in order[:3]] == [
        "11",
        "12",
        "1X",
    ]
```

- [ ] **Step 2: Verify tests fail**

Run: `../../.venv/bin/python -m pytest tests/test_ev_package.py -q`

Expected: import failure for `toto_ai.ev.package`.

- [ ] **Step 3: Implement complete deterministic ranking**

`rank_coupon_indices()` scans every EV value and returns one NumPy index array
containing the complete deterministic order. Primary key is descending gross
EV. Start with `np.lexsort((indices, -gross_ev))`; then reorder each maximal
contiguous run whose values are close to the run's first value under
`rtol=1e-12, atol=1e-15` by ascending index. This defines tolerance ties
without constructing 14 million Python dataclasses.

Only selected indices become `RankedCoupon` instances. Coupon conversion uses
`coupon_from_index()` from Task 3 and ranks remain one-based positions in the
complete index order.

- [ ] **Step 4: Implement Research and Playable selection**

Use this exact decision logic:

```python
order = rank_coupon_indices(surface)
if config.mode == "research":
    selected_indices = order[: config.max_coupons]
    decision = "RESEARCH ONLY"
else:
    eligible = order[surface.gross_ev[order] >= config.min_gross_ev]
    selected_indices = eligible[: config.max_coupons]
    decision = "PLAY" if selected_indices.size else "NO BET"
```

Materialize `selected_indices` as immutable `RankedCoupon` rows before building
the package.

Compute `expected_payout = sum(row.gross_ev * stake)`, modeled ROI as
`expected_payout / cost - 1` when cost is non-zero, and `unused_bank` exactly.
`derive_brief()` unions outcomes per position in order `1`, `X`, `2`; an empty
package returns 15 empty strings only when the caller supplies event count 15.

- [ ] **Step 5: Add threshold matrix tests**

Test thresholds `0.90`, `0.95`, `1.00`, and `1.05` against one fixed surface.
Assert selected counts are monotonic non-increasing and that the implementation
never mutates the configured threshold.

- [ ] **Step 6: Verify, update state, and commit**

```bash
../../.venv/bin/python -m pytest tests/test_ev_package.py -q
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
git add src/toto_ai/ev/package.py tests/test_ev_package.py memory-bank/CURRENT_STATE.md
git commit -m "Add dynamic bank EV package selection"
```

---

### Task 5: Fresh Drawing Input, Atomic Reports, and `ev-package` CLI

**Files:**
- Create: `src/toto_ai/ev/drawing.py`
- Create: `src/toto_ai/ev/reports.py`
- Create: `tests/test_ev_drawing.py`
- Create: `tests/test_ev_reports.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_api_inspector.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `TotoBriefClient`, EV math, full surface, and package selection.
- Produces: `resolve_open_drawing_from_api()`, `ev_input_from_payload()`, `build_open_ev_package()`, `write_ev_package_reports()`, and CLI `ev-package`.

- [ ] **Step 1: Write payload validation tests**

Create a 15-event fixture whose quote triplets are non-uniform and assert:

```python
def test_payload_becomes_ordered_ev_input(open_drawing_payload):
    result = ev_input_from_payload(
        open_drawing_payload,
        fetched_at="2026-07-14T12:00:00+00:00",
        stake=30,
        prize_fund_factor=0.9,
        possible_winnings=None,
        jackpot_override=None,
    )
    assert result.drawing_number == 5000
    assert len(result.true_probabilities) == 15
    assert result.possible_winnings == result.pool_sum * 0.9
    assert result.probability_sources == ("totobrief_bk",) * 15
```

Add failures for 14 events, duplicate/missing event orders, missing pool sum,
missing jackpot without override, invalid BK/pool rows, and simultaneous
explicit possible winnings plus a non-default prize factor.

Add an API resolver test with multiple `active`/`expected` rows and assert it
chooses the nearest future `ended_at`, without consulting SQLite.

- [ ] **Step 2: Write report atomicity and disclosure tests**

Assert package CSV contains `rank,coupon,gross_ev,net_ev`, and Markdown contains:

```text
crowd joint model: independent event marginals
possible winnings source: pool_sum proxy
prize fund factor: 0.900000
modeled ROI is not observed ROI
decision: NO BET
```

Inject failure on the second final-path replacement and assert both previous
artifacts are restored byte-for-byte, following the tested hybrid report
pattern.

- [ ] **Step 3: Implement strict fresh-payload parsing**

`ev_input_from_payload()` sorts by `order`, requires exactly orders 0 through
14, normalizes BK rows, smooths pool rows, validates pool/jackpot, resolves
possible winnings, and records a source for every event. It does not read event
results.

`resolve_open_drawing_from_api()` calls `client.drawings("baltbet-main", 1)`,
filters `active`/`expected` rows whose parsed `ended_at` is in the future, and
chooses the minimum `(ended_at, id)`. It fails when page one contains no
playable drawing; it never falls back to a stale local drawing.

`build_open_ev_package()` receives an already resolved drawing ID and a client,
calls `drawing_info()` immediately, timestamps receipt in UTC, computes the
surface, selects the package, and returns input/surface/package plus sensitivity
summaries for factors 0.70, 0.80, 0.90, and 1.00. Reuse linear category
components rather than rerunning unrelated payload work.

Calculate `self_dilution_ratio = package.cost / pool_sum`. When it exceeds
`0.01`, mark the run `model_supported=false`; Playable mode must suppress
`PLAY` to `NO BET`, while Research mode still emits diagnostics with the
unsupported warning. Add tests for both modes at the exact 1% boundary and
immediately above it.

- [ ] **Step 4: Implement atomic reports**

Create deterministic paths:

```text
reports/ev_package_<drawing_number>_<mode>_bank_<bank>.csv
reports/ev_package_<drawing_number>_<mode>_bank_<bank>.md
```

Render both files fully before publication, reject input/output path collisions,
and publish them with the rollback-safe pair algorithm already tested in
`hybrid_evaluation.py`. Include model assumptions, timestamps, bank ratio,
decision, selected count, cost, unused bank, expected payout, modeled ROI,
derived brief, top 20 diagnostics, self-dilution ratio/support status, and
sensitivity table.

- [ ] **Step 5: Add `ev-package` CLI**

Use exact options:

```python
@app.command("ev-package")
def ev_package_command(
    open: bool = typer.Option(False),  # noqa: A002
    mode: str = typer.Option("research"),
    bank: int = typer.Option(...),
    stake: int = typer.Option(30),
    min_gross_ev: float = typer.Option(1.0),
    prize_fund_factor: float = typer.Option(1.0),
    possible_winnings: float | None = typer.Option(None),
    jackpot: float | None = typer.Option(None),
) -> None:
```

Require `--open`, resolve its ID from the current TotoBrief drawing list, fetch
fresh API data, show Rich progress by EV phase/category, and print decision,
input snapshot, package
summary, top 20 coupons, and report paths. Convert controlled failures to
`typer.BadParameter`. Never print `PLAY` after an interrupted calculation.

- [ ] **Step 6: Verify command behavior**

Run:

```bash
../../.venv/bin/python -m pytest tests/test_ev_drawing.py tests/test_ev_reports.py tests/test_api_inspector.py -q
../../.venv/bin/python -m toto_ai.cli ev-package --help
../../.venv/bin/python -m ruff check .
```

Expected: tests pass and help lists every specified option.

- [ ] **Step 7: Update architecture/state and commit**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
git add src/toto_ai/ev src/toto_ai/cli.py tests memory-bank/ARCHITECTURE.md memory-bank/CURRENT_STATE.md
git commit -m "Add fresh drawing EV package command"
```

---

### Task 6: Chronological Modeled-EV Backtest

**Files:**
- Create: `src/toto_ai/ev/backtest.py`
- Create: `tests/test_ev_backtest.py`
- Modify: `src/toto_ai/ev/reports.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `knowledge/expected_value.md`

**Interfaces:**
- Consumes: historical `Drawing/Event/Quote`, exact EV surface, package selection, actual result normalization, and frozen strategy manifest parsing.
- Produces: `EVBacktestConfig`, `EVBacktestRow`, `EVBacktestResult`, `load_frozen_holdout_ids()`, `run_ev_backtest()`, `write_ev_backtest_reports()`, and CLI `backtest-ev`.

- [ ] **Step 1: Write eligibility and holdout-boundary tests**

```python
def test_backtest_excludes_every_frozen_holdout_id(session):
    forbidden = frozenset({901, 902})
    result = run_ev_backtest(
        session,
        last=3,
        banks=(4800, 6000, 9600),
        thresholds=(0.90, 0.95, 1.00, 1.05),
        stake=30,
        forbidden_drawing_ids=forbidden,
        surface_builder=fake_surface_builder,
    )
    assert not set(result.drawing_ids) & forbidden


def test_one_surface_is_reused_across_banks_and_thresholds(session):
    calls = []

    def builder(ev_input, progress_callback=None):
        calls.append(ev_input.drawing_id)
        return fixed_surface()

    run_ev_backtest(
        session,
        last=2,
        banks=(4800, 6000, 9600),
        thresholds=(0.90, 0.95, 1.00, 1.05),
        stake=30,
        forbidden_drawing_ids=frozenset({901, 902}),
        surface_builder=builder,
    )
    assert len(calls) == 2
```

Add tests for incomplete results, invalid probability inputs, monotonic selected
counts by threshold, exact bank caps, `NO BET` rows, and skip-rate alert above
80%.

- [ ] **Step 2: Verify tests fail**

Run: `../../.venv/bin/python -m pytest tests/test_ev_backtest.py -q`

Expected: import failure for `toto_ai.ev.backtest`.

- [ ] **Step 3: Implement explicit backtest configuration and rows**

Use immutable types with these fields:

```python
@dataclass(frozen=True)
class EVBacktestConfig:
    banks: tuple[int, ...]
    thresholds: tuple[float, ...]
    stake: int
    prize_fund_factors: tuple[float, ...] = (0.7, 0.8, 0.9, 1.0)


@dataclass(frozen=True)
class EVBacktestRow:
    drawing_id: int
    drawing_number: int | None
    bank: int
    threshold: float
    prize_fund_factor: float
    decision: str
    selected_coupons: int
    cost: int
    unused_bank: int
    package_expected_payout: float
    package_modeled_roi: float | None
    best_hits: int | None
    hit_9: bool
    hit_10: bool
    hit_11: bool
    hit_12: bool
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_hash: str
```

The result also stores processed/skipped IDs, elapsed time, and per-threshold
summary rows.

- [ ] **Step 4: Implement chronological evaluation without candidate limits**

`load_frozen_holdout_ids()` uses the existing validated manifest loader, reads
`holdout_size`, and returns the final `holdout_size` IDs from the manifest's
ordered `drawing_ids`. Reject zero/invalid sizes and duplicate IDs.

Select complete finished drawings in chronological order, remove the resulting
holdout IDs before any event query, and never load those excluded events.
For each remaining drawing:

1. load exactly 15 ordered events/quotes without results;
2. build one exact `EVComponents` object;
3. materialize and rank one full EV surface per prize-fund factor;
4. reuse that factor's ranking across every bank and threshold;
5. load the actual result only after package hashes/inputs are complete;
6. calculate realized hit indicators;
7. checkpoint partial CSV every completed drawing.

No timeout may convert partial computation into a valid row. Interrupted runs
retain diagnostic checkpoints and are resumable by exact configuration hash.

- [ ] **Step 5: Implement summaries and reports**

For every bank/threshold/factor report drawing count, PLAY count, NO BET count,
skip rate, average selected coupons, average bank utilization, average modeled
EV/ROI, best-hit average, and hit 9 through 15 rates. Add
`model_review_required=true` when skip rate exceeds 80%.

Markdown must state that modeled payout uses expected crowd denominators and is
not observed bookmaker payout or observed ROI.

- [ ] **Step 6: Add `backtest-ev` CLI**

```python
@app.command("backtest-ev")
def backtest_ev_command(
    db: str = typer.Option("data/toto.db"),
    last: int = typer.Option(100, min=1),
    banks: str = typer.Option("4800,6000,9600"),
    thresholds: str = typer.Option("0.90,0.95,1.00,1.05"),
    stake: int = typer.Option(30),
    frozen_manifest: str = typer.Option(...),
) -> None:
```

Parse comma-separated values deterministically, show drawing/category progress
and ETA, load forbidden holdout IDs before opening drawing events, print the
threshold summary, and write CSV/Markdown reports.

- [ ] **Step 7: Verify focused and full behavior**

```bash
../../.venv/bin/python -m pytest tests/test_ev_backtest.py tests/test_ev_reports.py -q
../../.venv/bin/python -m toto_ai.cli backtest-ev --help
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
```

Expected: all tests pass and help includes the required frozen manifest.

- [ ] **Step 8: Update project knowledge and commit**

Record implementation status, model limitations, and next external-provider
design in the listed memory/knowledge files, then commit:

```bash
git add src/toto_ai/ev src/toto_ai/cli.py tests/test_ev_backtest.py memory-bank knowledge/expected_value.md
git commit -m "Add modeled EV backtest"
```

---

### Task 7: End-to-End Mathematical and Operational Acceptance

**Files:**
- Create: `tests/test_ev_end_to_end.py`
- Modify: `README.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DECISIONS.md` only if implementation changed an approved definition.

**Interfaces:**
- Consumes: the entire EV pipeline.
- Produces: reproducible acceptance evidence and documented operator workflow.

- [ ] **Step 1: Add end-to-end tests**

Use a deterministic 15-event payload and an injected tiny-event engine for fast
CLI orchestration tests. Assert:

```python
def test_playable_pipeline_can_return_honest_no_bet(tmp_path, payload):
    result = run_ev_pipeline(
        payload=payload,
        config=EVConfig(bank=6000, stake=30, mode="playable", min_gross_ev=9.0),
        report_dir=tmp_path,
        surface_builder=fixed_surface_builder,
    )
    assert result.package.decision == "NO BET"
    assert result.package.cost == 0
    assert result.csv_path.exists()
    assert "modeled ROI is not observed ROI" in result.markdown_path.read_text()


def test_research_pipeline_uses_dynamic_bank_cap(tmp_path, payload):
    result = run_ev_pipeline(
        payload=payload,
        config=EVConfig(bank=9600, stake=30, mode="research"),
        report_dir=tmp_path,
        surface_builder=fixed_surface_builder,
    )
    assert len(result.package.coupons) <= 320
    assert result.package.cost <= 9600
```

Also assert report hashes are deterministic, assumptions are complete, and a
simulated interrupted surface build creates no `PLAY` report.

- [ ] **Step 2: Document the exact operator workflow**

Add a concise README section with:

```bash
python -m toto_ai.cli benchmark-ev --events 15 --samples 20
python -m toto_ai.cli ev-package --open --mode research --bank 6000 --stake 30
python -m toto_ai.cli ev-package --open --mode playable --bank 6000 --stake 30 --min-gross-ev 1.0
python -m toto_ai.cli backtest-ev --db data/toto.db --last 100 --banks 4800,6000,9600 --thresholds 0.90,0.95,1.00,1.05 --frozen-manifest reports/strategy_experiment_manifest_last_500_exclude_10.json
```

State plainly that `PLAY` is model output, not a profit guarantee, and that the
current prize/crowd model remains experimental.

- [ ] **Step 3: Run complete acceptance verification**

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/python -m ruff check .
../../.venv/bin/python -m toto_ai.cli benchmark-ev --events 5 --samples 10
../../.venv/bin/python -m toto_ai.cli ev-package --help
../../.venv/bin/python -m toto_ai.cli backtest-ev --help
```

Expected: all tests and Ruff pass; benchmark verification is `PASS`; both CLI
commands show documented options.

- [ ] **Step 4: Run the full 15-event benchmark**

```bash
../../.venv/bin/python -m toto_ai.cli benchmark-ev --events 15 --samples 20
```

Expected: all 14,348,907 coupons are evaluated, sampled direct-sum verification
passes within the configured tolerance, and elapsed/memory metrics are saved in
`memory-bank/CURRENT_STATE.md`. Do not replace this run with a smaller space to
save resources.

- [ ] **Step 5: Update memory and commit acceptance artifacts**

Mark the implemented portions complete in ROADMAP, record verification in
CURRENT_STATE, and commit:

```bash
git add README.md tests/test_ev_end_to_end.py memory-bank
git commit -m "Verify expected value package workflow"
```

---

## Deferred Separate Design

API-Sports collection, external event matching, consensus/de-vig logic,
prospective odds storage, and event-level TotoBrief fallback are intentionally
not implemented by this plan. They form the next independent subsystem after
the EV core passes full-space mathematical acceptance. The provider-neutral
source fields in `EVInput` are the only compatibility boundary required here.
