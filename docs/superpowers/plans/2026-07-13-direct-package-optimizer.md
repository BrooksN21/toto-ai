# Direct Package Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and backtest a deterministic package optimizer that directly maximizes estimated `13+` probability under a 5000 RUB bank.

**Architecture:** Add a probability/candidate layer, a weighted scenario-coverage optimizer, and a strategy-comparison backtest. Package generation receives BK probabilities but never actual results; the backtest evaluates generated packages afterward on a fixed chronological development/holdout split.

**Tech Stack:** Python 3.10+, standard library (`heapq`, `math`, `random`, `statistics`, `csv`), SQLAlchemy, Typer, Rich, pytest, Ruff. Add no dependencies.

## Global Constraints

- Primary bank is 5000 RUB, stake is 30 RUB, and the package limit is `bank // stake` (166 coupons for 5000 RUB).
- Primary category is 13, meaning Hamming distance at most 2.
- Direct strategies use only normalized pre-drawing BK probabilities.
- Do not add Pinnacle, other external providers, pool-value scoring, or ML in
  v1; they are separate follow-up experiments after the holdout result.
- Actual results may enter evaluation only, never candidate generation, scenario generation, or package selection.
- Candidate and scenario generation must be deterministic for drawing ID, configuration, and seed.
- The eligible last-500 window is sorted oldest to newest: oldest 350 development, newest 150 holdout.
- All strategies must run on the same eligible drawings.
- No profitability claim is allowed from hit-rate evidence.
- Existing category, budget, and Cover Engine definitions must not change.

---

## File Structure

- Create `src/toto_ai/optimizer/coupon_probabilities.py`: normalized probability matrices, exact coupon probability, and deterministic k-best Cartesian search.
- Create `src/toto_ai/optimizer/coupon_candidates.py`: Monte Carlo scenario sampling and deterministic candidate diversification.
- Create `src/toto_ai/optimizer/direct_package.py`: Hamming-neighbour indexing, weighted greedy coverage, and validation coverage.
- Create `src/toto_ai/optimizer/strategy_backtest.py`: package strategy adapters, chronological backtest, paired metrics, bootstrap interval, and report export.
- Create `tests/test_coupon_probabilities.py`: probability and top-k tests.
- Create `tests/test_coupon_candidates.py`: deterministic scenario/candidate tests.
- Create `tests/test_direct_package.py`: optimizer correctness, tie-break, and budget tests.
- Create `tests/test_strategy_backtest.py`: leakage boundary, split, metrics, reports, and DB integration tests.
- Modify `src/toto_ai/cli.py`: add `backtest-strategies` and summary/progress rendering.
- Modify `memory-bank/ARCHITECTURE.md`, `memory-bank/CURRENT_STATE.md`, `memory-bank/ROADMAP.md`, `memory-bank/DECISIONS.md`, and `knowledge/cover_engine.md` after the experiment is implemented and verified.

---

### Task 1: Probability Matrix and Exact Top-K Coupons

**Files:**
- Create: `src/toto_ai/optimizer/coupon_probabilities.py`
- Create: `tests/test_coupon_probabilities.py`

**Interfaces:**
- Produces: `ProbabilityMatrix = tuple[tuple[float, float, float], ...]`
- Produces: `normalize_probability_matrix(rows) -> ProbabilityMatrix`
- Produces: `coupon_log_probability(coupon, probabilities) -> float`
- Produces: `top_probability_coupons(probabilities, limit) -> list[str]`
- Consumes: outcome order `("1", "X", "2")`.

- [ ] **Step 1: Write failing normalization and probability tests**

```python
import math
import pytest

from toto_ai.optimizer.coupon_probabilities import (
    coupon_log_probability,
    normalize_probability_matrix,
)


def test_normalize_probability_matrix_uses_fixed_outcome_order():
    matrix = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}, {"1": 2, "X": 3, "2": 5}]
    )

    assert matrix == ((0.5, 0.3, 0.2), (0.2, 0.3, 0.5))
    assert coupon_log_probability("12", matrix) == pytest.approx(
        math.log(0.5) + math.log(0.5)
    )


def test_normalize_probability_matrix_rejects_missing_or_non_positive_rows():
    with pytest.raises(ValueError, match="positive probabilities"):
        normalize_probability_matrix([{"1": 0, "X": 0, "2": 0}])
    with pytest.raises(ValueError, match="outcomes 1, X, and 2"):
        normalize_probability_matrix([{"1": 50, "X": 50}])
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_coupon_probabilities.py -q`

Expected: collection fails because `toto_ai.optimizer.coupon_probabilities` does not exist.

- [ ] **Step 3: Implement normalization and coupon probability**

```python
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

OUTCOMES = ("1", "X", "2")
OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}
ProbabilityMatrix = tuple[tuple[float, float, float], ...]


def normalize_probability_matrix(
    rows: Sequence[Mapping[str, float]],
) -> ProbabilityMatrix:
    if not rows:
        raise ValueError("Probability matrix must contain at least one event.")
    normalized = []
    for row in rows:
        if any(outcome not in row for outcome in OUTCOMES):
            raise ValueError("Every event must contain outcomes 1, X, and 2.")
        values = tuple(float(row[outcome]) for outcome in OUTCOMES)
        total = sum(values)
        if total <= 0 or any(value <= 0 for value in values):
            raise ValueError("Every event must contain positive probabilities.")
        normalized.append(tuple(value / total for value in values))
    return tuple(normalized)


def coupon_log_probability(
    coupon: str,
    probabilities: ProbabilityMatrix,
) -> float:
    if len(coupon) != len(probabilities):
        raise ValueError("Coupon and probability matrix lengths must match.")
    try:
        return sum(
            math.log(row[OUTCOME_INDEX[outcome]])
            for outcome, row in zip(coupon, probabilities, strict=True)
        )
    except KeyError as error:
        raise ValueError("Coupon outcomes must be 1, X, or 2.") from error
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_coupon_probabilities.py -q`

Expected: 2 tests pass.

- [ ] **Step 5: Write failing deterministic top-k tests**

```python
from toto_ai.optimizer.coupon_probabilities import top_probability_coupons


def test_top_probability_coupons_returns_exact_probability_order():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}, {"1": 50, "X": 20, "2": 30}]
    )

    assert top_probability_coupons(probabilities, limit=4) == [
        "11",
        "12",
        "X1",
        "1X",
    ]


def test_top_probability_coupons_is_deterministic_on_ties():
    probabilities = normalize_probability_matrix(
        [{"1": 1, "X": 1, "2": 1}, {"1": 1, "X": 1, "2": 1}]
    )

    assert top_probability_coupons(probabilities, limit=4) == [
        "11",
        "12",
        "1X",
        "21",
    ]
```

- [ ] **Step 6: Run top-k tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_coupon_probabilities.py -q`

Expected: fails because `top_probability_coupons` is missing.

- [ ] **Step 7: Implement heap-based k-best Cartesian enumeration**

Implementation requirements:

```python
import heapq
import time


def top_probability_coupons(
    probabilities: ProbabilityMatrix,
    limit: int,
) -> list[str]:
    if limit < 0:
        raise ValueError("limit must be non-negative.")
    if limit == 0:
        return []

    ranked = tuple(
        tuple(
            sorted(
                zip(OUTCOMES, row, strict=True),
                key=lambda item: (-item[1], item[0]),
            )
        )
        for row in probabilities
    )

    def state_coupon(state: tuple[int, ...]) -> str:
        return "".join(ranked[position][rank][0] for position, rank in enumerate(state))

    def state_log_probability(state: tuple[int, ...]) -> float:
        return sum(
            math.log(ranked[position][rank][1])
            for position, rank in enumerate(state)
        )

    start = (0,) * len(probabilities)
    start_coupon = state_coupon(start)
    heap = [(-state_log_probability(start), start_coupon, start)]
    seen = {start}
    coupons = []

    while heap and len(coupons) < limit:
        _, coupon, state = heapq.heappop(heap)
        coupons.append(coupon)
        for position, rank in enumerate(state):
            if rank + 1 == len(OUTCOMES):
                continue
            next_state = list(state)
            next_state[position] += 1
            next_state_tuple = tuple(next_state)
            if next_state_tuple in seen:
                continue
            seen.add(next_state_tuple)
            next_coupon = state_coupon(next_state_tuple)
            heapq.heappush(
                heap,
                (
                    -state_log_probability(next_state_tuple),
                    next_coupon,
                    next_state_tuple,
                ),
            )
    return coupons
```

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_coupon_probabilities.py -q`

Expected: all tests pass.

```bash
git add src/toto_ai/optimizer/coupon_probabilities.py tests/test_coupon_probabilities.py
git commit -m "Add coupon probability utilities"
```

---

### Task 2: Deterministic Scenarios and Candidate Coupons

**Files:**
- Create: `src/toto_ai/optimizer/coupon_candidates.py`
- Create: `tests/test_coupon_candidates.py`

**Interfaces:**
- Consumes: `ProbabilityMatrix`, `coupon_log_probability`, and `top_probability_coupons` from Task 1.
- Produces: `sample_scenarios(probabilities, count, seed) -> dict[str, int]`
- Produces: `generate_candidate_coupons(probabilities, max_coupons, top_count, sample_count, mutation_limit, seed) -> list[str]`

- [ ] **Step 1: Write failing scenario tests**

```python
from toto_ai.optimizer.coupon_candidates import sample_scenarios
from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix


def test_sample_scenarios_is_deterministic_and_preserves_count():
    probabilities = normalize_probability_matrix(
        [{"1": 70, "X": 20, "2": 10}, {"1": 10, "X": 20, "2": 70}]
    )

    first = sample_scenarios(probabilities, count=100, seed=17)
    second = sample_scenarios(probabilities, count=100, seed=17)

    assert first == second
    assert sum(first.values()) == 100
    assert all(len(scenario) == 2 for scenario in first)
```

- [ ] **Step 2: Run and verify RED**

Run: `.venv/bin/python -m pytest tests/test_coupon_candidates.py -q`

Expected: missing module failure.

- [ ] **Step 3: Implement deterministic categorical sampling**

Use `random.Random(seed).random()` and explicit cumulative thresholds rather
than global random state:

```python
from __future__ import annotations

from collections import Counter
from random import Random

from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    coupon_log_probability,
    top_probability_coupons,
)


def sample_scenarios(
    probabilities: ProbabilityMatrix,
    count: int,
    seed: int,
) -> dict[str, int]:
    if count <= 0:
        raise ValueError("count must be positive.")
    rng = Random(seed)
    scenarios = Counter()
    for _ in range(count):
        outcomes = []
        for row in probabilities:
            draw = rng.random()
            cumulative = 0.0
            for outcome, probability in zip(OUTCOMES, row, strict=True):
                cumulative += probability
                if draw <= cumulative:
                    outcomes.append(outcome)
                    break
            else:
                outcomes.append(OUTCOMES[-1])
        scenarios["".join(outcomes)] += 1
    return dict(sorted(scenarios.items()))
```

- [ ] **Step 4: Run scenario test and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_coupon_candidates.py -q`

Expected: test passes.

- [ ] **Step 5: Write failing candidate generation tests**

```python
from toto_ai.optimizer.coupon_candidates import generate_candidate_coupons
from toto_ai.optimizer.coupon_probabilities import top_probability_coupons


def test_generate_candidates_contains_top_package_and_is_deterministic():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    expected_top = top_probability_coupons(probabilities, limit=3)

    first = generate_candidate_coupons(
        probabilities,
        max_coupons=3,
        top_count=5,
        sample_count=20,
        mutation_limit=8,
        seed=9,
    )
    second = generate_candidate_coupons(
        probabilities,
        max_coupons=3,
        top_count=5,
        sample_count=20,
        mutation_limit=8,
        seed=9,
    )

    assert first == second
    assert first[:3] == expected_top
    assert len(first) == len(set(first))
    assert "1111" in first
```

- [ ] **Step 6: Implement candidate union and deterministic ordering**

Use this exact implementation:

```python
def generate_candidate_coupons(
    probabilities: ProbabilityMatrix,
    max_coupons: int,
    top_count: int = 1000,
    sample_count: int = 3000,
    mutation_limit: int = 1000,
    seed: int = 42,
) -> list[str]:
    if max_coupons <= 0:
        raise ValueError("max_coupons must be positive.")
    if top_count < max_coupons:
        raise ValueError("top_count must be at least max_coupons.")

    top = top_probability_coupons(probabilities, limit=top_count)
    sampled = sample_scenarios(probabilities, count=sample_count, seed=seed)
    sampled_order = sorted(
        sampled,
        key=lambda coupon: (
            -sampled[coupon],
            -coupon_log_probability(coupon, probabilities),
            coupon,
        ),
    )

    mutations = set()
    for coupon in top:
        for position, current in enumerate(coupon):
            for replacement in OUTCOMES:
                if replacement == current:
                    continue
                mutations.add(
                    coupon[:position] + replacement + coupon[position + 1 :]
                )
    mutation_order = sorted(
        mutations,
        key=lambda coupon: (
            -coupon_log_probability(coupon, probabilities),
            coupon,
        ),
    )[:mutation_limit]

    ordered = [*top, *sampled_order, *mutation_order]
    return list(dict.fromkeys(ordered))
```

- [ ] **Step 7: Run Task 2 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_coupon_candidates.py -q`

Expected: all tests pass.

```bash
git add src/toto_ai/optimizer/coupon_candidates.py tests/test_coupon_candidates.py
git commit -m "Add deterministic coupon candidates"
```

---

### Task 3: Weighted Scenario-Coverage Package

**Files:**
- Create: `src/toto_ai/optimizer/direct_package.py`
- Create: `tests/test_direct_package.py`

**Interfaces:**
- Consumes: candidate coupons and scenario frequency dictionaries from Task 2.
- Consumes: `category_max_errors` from `toto_ai.optimizer.cover`.
- Produces: `DirectPackageResult(selected_coupons, covered_scenario_weight, total_scenario_weight, estimated_coverage, timed_out)`.
- Produces: `neighbors_within_distance(value, max_errors) -> iterator[str]`.
- Produces: `select_weighted_package(candidates, scenarios, probabilities, category, max_coupons, deadline, time_func) -> DirectPackageResult`.
- Produces: `estimate_package_coverage(coupons, scenarios, category) -> float`.

- [ ] **Step 1: Write failing neighbour tests**

```python
from toto_ai.optimizer.direct_package import neighbors_within_distance


def test_neighbors_within_distance_has_expected_radius_sizes():
    assert len(set(neighbors_within_distance("111", 0))) == 1
    assert len(set(neighbors_within_distance("111", 1))) == 7
    assert len(set(neighbors_within_distance("111", 2))) == 19
```

- [ ] **Step 2: Run and verify RED**

Run: `.venv/bin/python -m pytest tests/test_direct_package.py -q`

Expected: missing module failure.

- [ ] **Step 3: Implement bounded Hamming neighbours**

Use recursive mutation with increasing position indexes so each neighbour is
generated once:

```python
from __future__ import annotations

import heapq
from dataclasses import dataclass
from collections.abc import Iterator

from toto_ai.optimizer.coupon_probabilities import (
    OUTCOMES,
    ProbabilityMatrix,
    coupon_log_probability,
)
from toto_ai.optimizer.cover import category_max_errors


def neighbors_within_distance(value: str, max_errors: int) -> Iterator[str]:
    chars = list(value)
    yield value

    def mutate(start: int, remaining: int) -> Iterator[str]:
        if remaining == 0:
            return
        for position in range(start, len(chars)):
            original = chars[position]
            for replacement in OUTCOMES:
                if replacement == original:
                    continue
                chars[position] = replacement
                yield "".join(chars)
                yield from mutate(position + 1, remaining - 1)
            chars[position] = original

    yield from mutate(0, max_errors)
```

- [ ] **Step 4: Run neighbour test and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_direct_package.py -q`

Expected: test passes.

- [ ] **Step 5: Write failing weighted-selection tests**

```python
from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix
from toto_ai.optimizer.direct_package import (
    estimate_package_coverage,
    select_weighted_package,
)


def test_weighted_package_selects_largest_new_mass_then_probability():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 3
    )
    scenarios = {"111": 40, "XXX": 35, "222": 25}

    result = select_weighted_package(
        candidates=["XXX", "111", "222"],
        scenarios=scenarios,
        probabilities=probabilities,
        category=15,
        max_coupons=2,
    )

    assert result.selected_coupons == ["111", "XXX"]
    assert result.covered_scenario_weight == 75
    assert result.estimated_coverage == 0.75


def test_weighted_package_respects_coupon_limit_and_validation_is_exact():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 3
    )
    result = select_weighted_package(
        candidates=["111", "XXX", "222"],
        scenarios={"111": 1, "XXX": 1, "222": 1},
        probabilities=probabilities,
        category=15,
        max_coupons=1,
    )

    assert len(result.selected_coupons) == 1
    assert estimate_package_coverage(
        result.selected_coupons,
        {"111": 2, "XXX": 1},
        category=15,
    ) == 2 / 3
```

- [ ] **Step 6: Implement inverted scenario coverage and lazy heap**

The implementation must:

1. Deduplicate candidates while preserving order.
2. Build `candidate_index = {coupon: index}`.
3. For every scenario, enumerate `neighbors_within_distance` and append only
   matching candidates to `scenario_to_candidates` and
   `candidate_to_scenarios`.
4. Initialize each score as the sum of frequencies of its covered scenarios.
5. Use heap entries
   `(-score, -coupon_log_probability, coupon, version, candidate_index)`.
6. On selection, mark newly covered scenarios and decrement every affected
   unselected candidate score, pushing a new versioned heap entry.
7. Ignore stale heap entries whose version differs.

Required result type and implementation:

```python
@dataclass(frozen=True)
class DirectPackageResult:
    selected_coupons: list[str]
    covered_scenario_weight: int
    total_scenario_weight: int
    estimated_coverage: float
    timed_out: bool


def select_weighted_package(
    candidates: list[str],
    scenarios: dict[str, int],
    probabilities: ProbabilityMatrix,
    category: int,
    max_coupons: int,
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> DirectPackageResult:
    if max_coupons < 0:
        raise ValueError("max_coupons must be non-negative.")
    if any(len(coupon) != len(probabilities) for coupon in candidates):
        raise ValueError("Candidate and probability lengths must match.")
    if any(weight <= 0 for weight in scenarios.values()):
        raise ValueError("Scenario weights must be positive.")

    unique_candidates = list(dict.fromkeys(candidates))
    scenario_items = sorted(scenarios.items())
    total_weight = sum(weight for _, weight in scenario_items)
    if not unique_candidates or not scenario_items or max_coupons == 0:
        return DirectPackageResult([], 0, total_weight, 0.0, False)

    max_errors = category_max_errors(category)
    candidate_index = {
        coupon: index for index, coupon in enumerate(unique_candidates)
    }
    candidate_to_scenarios = [set() for _ in unique_candidates]
    scenario_to_candidates = []

    for scenario_index, (scenario, _) in enumerate(scenario_items):
        if deadline is not None and time_func() >= deadline:
            return DirectPackageResult([], 0, total_weight, 0.0, True)
        matches = sorted(
            {
                candidate_index[neighbor]
                for neighbor in neighbors_within_distance(scenario, max_errors)
                if neighbor in candidate_index
            }
        )
        scenario_to_candidates.append(matches)
        for index in matches:
            candidate_to_scenarios[index].add(scenario_index)

    weights = [weight for _, weight in scenario_items]
    scores = [
        sum(weights[scenario] for scenario in covered)
        for covered in candidate_to_scenarios
    ]
    log_probabilities = [
        coupon_log_probability(coupon, probabilities)
        for coupon in unique_candidates
    ]
    versions = [0] * len(unique_candidates)
    selected_indexes = set()
    selected_order = []
    covered_scenarios = set()
    heap = [
        (
            -scores[index],
            -log_probabilities[index],
            coupon,
            versions[index],
            index,
        )
        for index, coupon in enumerate(unique_candidates)
    ]
    heapq.heapify(heap)

    timed_out = False
    while heap and len(selected_indexes) < max_coupons:
        if deadline is not None and time_func() >= deadline:
            timed_out = True
            break
        negative_score, _, _, version, index = heapq.heappop(heap)
        if index in selected_indexes or version != versions[index]:
            continue
        if -negative_score <= 0:
            break

        selected_indexes.add(index)
        selected_order.append(index)
        newly_covered = candidate_to_scenarios[index] - covered_scenarios
        for scenario_index in newly_covered:
            covered_scenarios.add(scenario_index)
            weight = weights[scenario_index]
            for affected in scenario_to_candidates[scenario_index]:
                if affected in selected_indexes:
                    continue
                scores[affected] -= weight
                versions[affected] += 1
                heapq.heappush(
                    heap,
                    (
                        -scores[affected],
                        -log_probabilities[affected],
                        unique_candidates[affected],
                        versions[affected],
                        affected,
                    ),
                )

    selected = [unique_candidates[index] for index in selected_order]
    covered_weight = sum(weights[index] for index in covered_scenarios)
    return DirectPackageResult(
        selected_coupons=selected,
        covered_scenario_weight=covered_weight,
        total_scenario_weight=total_weight,
        estimated_coverage=covered_weight / total_weight,
        timed_out=timed_out,
    )
```

When the deadline expires, retain the partial selected package and return
`timed_out=True`. The strategy backtest excludes that drawing for all strategies
and records the timeout; a holdout run with any timeout is operationally
inconclusive.

For validation, avoid all-pairs distance checks:

```python
def estimate_package_coverage(
    coupons: list[str],
    scenarios: dict[str, int],
    category: int,
) -> float:
    coupon_set = set(coupons)
    max_errors = category_max_errors(category)
    total = sum(scenarios.values())
    if total == 0:
        return 0.0
    covered = sum(
        weight
        for scenario, weight in scenarios.items()
        if any(
            neighbor in coupon_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        )
    )
    return covered / total
```

- [ ] **Step 7: Add deterministic tie-break regression**

```python
def test_weighted_package_uses_probability_then_lexical_tie_breaks():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    result = select_weighted_package(
        candidates=["X1", "1X", "22"],
        scenarios={"X1": 1, "1X": 1, "22": 1},
        probabilities=probabilities,
        category=15,
        max_coupons=1,
    )
    assert result.selected_coupons == ["1X"]
```

- [ ] **Step 8: Run Task 3 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_direct_package.py -q`

Expected: all tests pass.

```bash
git add src/toto_ai/optimizer/direct_package.py tests/test_direct_package.py
git commit -m "Add weighted direct package optimizer"
```

---

### Task 4: Strategy Packages and Leakage Boundary

**Files:**
- Create: `src/toto_ai/optimizer/strategy_backtest.py`
- Create: `tests/test_strategy_backtest.py`

**Interfaces:**
- Consumes: Tasks 1-3 and existing `build_baseline_brief`.
- Produces: `StrategyConfig` with fixed defaults.
- Produces: `StrategyPackage(strategy, coupons, estimated_coverage, candidate_count, runtime_seconds, timed_out)`.
- Produces: `build_packages_for_probabilities(probabilities, analyses, drawing_id, config, baseline_builder=build_baseline_brief) -> list[StrategyPackage]`.
- Critical boundary: this function has no result-string parameter.

- [ ] **Step 1: Write failing strategy-package tests**

```python
from toto_ai.optimizer.strategy_backtest import (
    StrategyConfig,
    build_packages_for_probabilities,
)
from toto_ai.optimizer.coupon_probabilities import (
    normalize_probability_matrix,
    top_probability_coupons,
)


def test_strategy_package_builder_has_no_actual_result_input():
    import inspect

    assert "result" not in inspect.signature(
        build_packages_for_probabilities
    ).parameters


def test_strategy_packages_share_budget_and_top_coupons():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    config = StrategyConfig(
        bank=90,
        stake=30,
        category=13,
        seed=42,
        top_count=5,
        candidate_samples=20,
        mutation_limit=10,
        optimization_samples=30,
        validation_samples=40,
    )

    packages = build_packages_for_probabilities(
        probabilities=probabilities,
        analyses=[],
        drawing_id=7,
        config=config,
        baseline_builder=lambda *args, **kwargs: {
            "selected_coupons": ["1111"],
            "cost": 30,
        },
    )

    by_name = {package.strategy: package for package in packages}
    assert set(by_name) == {
        "baseline_brief",
        "top_probability",
        "weighted_coverage",
    }
    assert by_name["top_probability"].coupons == top_probability_coupons(
        probabilities, limit=3
    )
    assert all(len(package.coupons) <= 3 for package in packages)
```

- [ ] **Step 2: Run and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_backtest.py -q`

Expected: missing module failure.

- [ ] **Step 3: Implement fixed strategy configuration and package adapters**

Use these exact defaults:

```python
@dataclass(frozen=True)
class StrategyConfig:
    bank: int = 5000
    stake: int = 30
    category: int = 13
    seed: int = 42
    top_count: int = 1000
    candidate_samples: int = 3000
    mutation_limit: int = 1000
    optimization_samples: int = 2000
    validation_samples: int = 5000
    timeout_per_drawing: float | None = 30.0

    @property
    def max_coupons(self) -> int:
        return self.bank // self.stake


@dataclass(frozen=True)
class StrategyPackage:
    strategy: str
    coupons: list[str]
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    timed_out: bool
```

`build_packages_for_probabilities` must:

- validate `bank`, `stake`, category, and `top_count >= max_coupons`;
- call the existing baseline builder with `analyses`, category, bank, and stake;
- select `max_coupons` exact coupons for `top_probability`;
- derive independent seeds as `config.seed ^ drawing_id ^ 0xA5A5` for
  optimization, `^ 0x5A5A` for validation, and `^ 0xC3C3` for candidate
  sampling;
- generate candidates including all top-probability coupons;
- select weighted coupons from optimization scenarios;
- estimate all three strategies on the same validation scenarios;
- return packages in fixed strategy order.

- [ ] **Step 4: Run Task 4 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_strategy_backtest.py -q`

Expected: leakage and package tests pass.

```bash
git add src/toto_ai/optimizer/strategy_backtest.py tests/test_strategy_backtest.py
git commit -m "Add comparable package strategies"
```

---

### Task 5: Chronological Historical Backtest

**Files:**
- Modify: `src/toto_ai/optimizer/strategy_backtest.py`
- Modify: `tests/test_strategy_backtest.py`

**Interfaces:**
- Produces: `StrategyBacktestRow` and `StrategyBacktestResult`.
- Produces: `select_eligible_strategy_drawings(session, last, community) -> list[Drawing]`.
- Produces: `split_development_holdout(drawings, holdout_size) -> dict[int, str]`.
- Produces: `run_strategy_backtest(session, last, holdout_size, config, community, progress_callback=None) -> StrategyBacktestResult`.
- Reuses: `select_complete_finished_drawings`, `build_result_string`, and `best_coupon_hits` from `brief_backtest.py`.

- [ ] **Step 1: Write failing chronological split test**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from toto_ai.db.models import Base, Drawing


def test_split_development_holdout_sorts_oldest_to_newest():
    drawings = [
        Drawing(id=3, number=1003),
        Drawing(id=1, number=1001),
        Drawing(id=4, number=1004),
        Drawing(id=2, number=1002),
    ]

    assert split_development_holdout(drawings, holdout_size=1) == {
        1: "development",
        2: "development",
        3: "development",
        4: "holdout",
    }
```

- [ ] **Step 2: Write failing DB integration and common-eligibility test**

```python
def test_run_strategy_backtest_uses_same_eligible_drawings_for_all_strategies():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_strategy_drawing(session, 1, 1001, "1" * 15, include_bk=True)
        _add_strategy_drawing(session, 2, 1002, "X" * 15, include_bk=False)
        result = run_strategy_backtest(
            session,
            last=2,
            holdout_size=0,
            config=StrategyConfig(
                bank=90,
                stake=30,
                category=15,
                top_count=3,
                candidate_samples=10,
                mutation_limit=5,
                optimization_samples=20,
                validation_samples=20,
            ),
            package_builder=_package_builder_stub,
        )

    assert result.summary["eligible_drawings"] == 1
    assert result.summary["skipped_drawings"] == 1
    assert len(result.rows) == 3
    assert {row.drawing_number for row in result.rows} == {1001}
```

- [ ] **Step 3: Run and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_backtest.py -q`

Expected: split/runner symbols are missing.

- [ ] **Step 4: Implement row/result types and runner**

```python
@dataclass(frozen=True)
class StrategyBacktestRow:
    drawing_id: int
    drawing_number: int | None
    segment: str
    strategy: str
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    package_hash: str


@dataclass(frozen=True)
class StrategyBacktestResult:
    rows: list[StrategyBacktestRow]
    summary: dict[str, object]
    config: StrategyConfig
```

Runner rules:

1. Query finished drawings newest-first and keep scanning until exactly `last`
   drawings have 15 supported results and complete usable pool/BK quotes. Sort
   that eligible set oldest-first before splitting; do not first truncate and
   then skip missing quotes.
2. Load all 15 events and quotes ordered by `event_order`.
3. Build `EventBriefAnalysis` values for the baseline and normalize the same BK
   values for direct strategies.
4. If any strategy cannot be generated or times out, exclude the drawing for
   all strategies and increment a single skip/timeout reason. A holdout run with
   any timeout is marked operationally inconclusive.
5. Build all packages before calling `build_result_string(events)` or evaluating
   hits. Keep these as visibly separate blocks in the function.
6. Add exactly three rows per evaluated drawing. Compute `package_hash` as
   SHA-256 of the comma-joined ordered coupons.
7. Emit progress after each drawing with drawing number, index/total, eligible,
   skipped, elapsed time, and ETA.

- [ ] **Step 5: Add explicit leakage-order regression**

Monkeypatch `build_result_string` to append `"result"` to a call log and the
package builder to append `"packages"`; assert the order is
`["packages", "result"]`.

- [ ] **Step 6: Run Task 5 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_strategy_backtest.py -q`

Expected: all strategy runner tests pass.

```bash
git add src/toto_ai/optimizer/strategy_backtest.py tests/test_strategy_backtest.py
git commit -m "Add direct strategy backtest"
```

---

### Task 6: Paired Metrics, Holdout Decision, and Reports

**Files:**
- Modify: `src/toto_ai/optimizer/strategy_backtest.py`
- Modify: `tests/test_strategy_backtest.py`

**Interfaces:**
- Produces: `paired_bootstrap_hit13(rows, seed=42, samples=10000) -> dict[str, float]`.
- Produces: `summarize_strategy_backtest(rows, config, development_count, holdout_count, skipped) -> dict[str, object]`.
- Produces: `write_strategy_backtest_reports(result, last, report_dir="reports") -> tuple[Path, Path]`.

- [ ] **Step 1: Write failing paired-summary test**

```python
def test_summary_uses_holdout_paired_hit13_difference_and_status():
    rows = [
        _strategy_row(1, "holdout", "baseline_brief", best_hits=12),
        _strategy_row(1, "holdout", "top_probability", best_hits=12),
        _strategy_row(1, "holdout", "weighted_coverage", best_hits=13),
        _strategy_row(2, "holdout", "baseline_brief", best_hits=13),
        _strategy_row(2, "holdout", "top_probability", best_hits=12),
        _strategy_row(2, "holdout", "weighted_coverage", best_hits=13),
    ]

    summary = summarize_strategy_backtest(
        rows,
        config=StrategyConfig(bank=5000, stake=30, category=13),
        development_count=0,
        holdout_count=2,
        skipped=0,
        bootstrap_samples=200,
        bootstrap_seed=7,
    )

    assert summary["holdout"]["weighted_coverage"]["hit13_count"] == 2
    assert summary["holdout"]["baseline_brief"]["hit13_count"] == 1
    assert summary["paired_hit13_difference_pp"] == 50.0
    assert summary["strategy_status"] in {"preliminary", "proven"}
```

- [ ] **Step 2: Implement deterministic paired bootstrap**

```python
def paired_bootstrap_hit13(
    rows: list[StrategyBacktestRow],
    seed: int = 42,
    samples: int = 10000,
) -> dict[str, float]:
    holdout = [row for row in rows if row.segment == "holdout"]
    by_key = {(row.drawing_id, row.strategy): row for row in holdout}
    drawing_ids = sorted({row.drawing_id for row in holdout})
    paired = [
        (
            int(by_key[(drawing_id, "weighted_coverage")].hit_13),
            int(by_key[(drawing_id, "baseline_brief")].hit_13),
        )
        for drawing_id in drawing_ids
    ]
    if not paired:
        return {"difference_pp": 0.0, "ci_low_pp": 0.0, "ci_high_pp": 0.0}

    rng = Random(seed)
    differences = []
    for _ in range(samples):
        sample = [paired[rng.randrange(len(paired))] for _ in paired]
        differences.append(
            100 * sum(weighted - baseline for weighted, baseline in sample) / len(sample)
        )
    differences.sort()
    observed = 100 * sum(w - b for w, b in paired) / len(paired)
    return {
        "difference_pp": round(observed, 4),
        "ci_low_pp": round(differences[int(0.025 * (samples - 1))], 4),
        "ci_high_pp": round(differences[int(0.975 * (samples - 1))], 4),
    }
```

Status rules:

- `rejected`: weighted holdout hit13 count is not greater than baseline, or
  weighted average best hits is lower.
- `preliminary`: point estimate passes, but bootstrap lower bound is `<= 0`.
- `proven`: point estimate passes and bootstrap lower bound is `> 0`.
- `not_evaluated`: no holdout rows.

- [ ] **Step 3: Write failing report export test**

```python
def test_write_strategy_reports_contains_configuration_and_rows(tmp_path):
    result = _strategy_result_fixture()
    csv_path, markdown_path = write_strategy_backtest_reports(
        result,
        last=500,
        report_dir=tmp_path,
    )

    assert csv_path.name == "strategy_backtest_last_500_bank_5000.csv"
    assert markdown_path.name == "strategy_backtest_last_500_bank_5000.md"
    assert "weighted_coverage" in csv_path.read_text()
    markdown = markdown_path.read_text()
    assert "Strategy Backtest" in markdown
    assert "holdout" in markdown
    assert "seed" in markdown
```

- [ ] **Step 4: Implement CSV/Markdown report output**

CSV columns:

```text
drawing_id,drawing_number,segment,strategy,best_hits,hit_13,hit_14,hit_15,
package_size,package_cost,estimated_coverage,candidate_count,runtime_seconds,
package_hash
```

Markdown sections:

1. Configuration and deterministic seed.
2. Eligibility and chronological split.
3. Development strategy table.
4. Holdout strategy table.
5. Paired hit13 difference and 95% interval.
6. Strategy status with the exact acceptance rule.
7. Skip reasons and timing.

- [ ] **Step 5: Run Task 6 tests and commit**

Run: `.venv/bin/python -m pytest tests/test_strategy_backtest.py -q`

Expected: all tests pass.

```bash
git add src/toto_ai/optimizer/strategy_backtest.py tests/test_strategy_backtest.py
git commit -m "Add paired strategy evaluation reports"
```

---

### Task 7: CLI, Smoke Benchmark, and Project Memory

**Files:**
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_strategy_backtest.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `knowledge/cover_engine.md`

**Interfaces:**
- Adds CLI command `backtest-strategies`.
- Uses `run_strategy_backtest` and `write_strategy_backtest_reports` from Tasks 5-6.

- [ ] **Step 1: Add CLI command with explicit research controls**

Add imports and this command shape to `src/toto_ai/cli.py`:

```python
@app.command("backtest-strategies")
def backtest_strategies(
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    last: int = typer.Option(500, help="Latest complete drawings to test."),
    holdout: int = typer.Option(150, help="Newest eligible holdout drawings."),
    bank: int = typer.Option(5000, help="Positive integer package budget."),
    stake: int = typer.Option(30, help="Stake per coupon."),
    category: int = typer.Option(13, help="Target category: 13, 14, or 15."),
    seed: int = typer.Option(42, help="Deterministic base seed."),
    top_count: int = typer.Option(1000, help="Exact top-probability candidates."),
    candidate_samples: int = typer.Option(3000, help="Candidate scenario samples."),
    mutation_limit: int = typer.Option(1000, help="Maximum mutation candidates."),
    optimization_samples: int = typer.Option(2000, help="Optimization scenarios."),
    validation_samples: int = typer.Option(5000, help="Validation scenarios."),
    timeout_per_drawing: float = typer.Option(
        30.0,
        help="Maximum package-generation time per drawing.",
    ),
) -> None:
    """Compare baseline and direct package strategies on historical drawings."""
```

Construct `StrategyConfig`, run inside the repository's standard Rich progress
context, convert `ValueError` to `typer.BadParameter`, write reports, and print:

- eligible/skipped/development/holdout counts;
- one row per strategy for holdout hit13/hit14/hit15 and average best hits;
- paired hit13 difference and interval;
- strategy status;
- report paths.

- [ ] **Step 2: Add CLI help smoke test**

Use Typer's `CliRunner` only if it is already available through Typer; otherwise
test the command function with monkeypatched runner/report functions. Assert the
command is registered under `backtest-strategies` and default bank is 5000.

- [ ] **Step 3: Run focused and full verification**

```bash
.venv/bin/python -m pytest \
  tests/test_coupon_probabilities.py \
  tests/test_coupon_candidates.py \
  tests/test_direct_package.py \
  tests/test_strategy_backtest.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Expected: all tests and Ruff pass.

- [ ] **Step 4: Run a small deterministic CLI smoke benchmark**

```bash
.venv/bin/python -m toto_ai.cli backtest-strategies \
  --db data/toto.db \
  --last 10 \
  --holdout 3 \
  --bank 5000 \
  --stake 30 \
  --category 13 \
  --seed 42 \
  --top-count 200 \
  --candidate-samples 300 \
  --mutation-limit 200 \
  --optimization-samples 300 \
  --validation-samples 500
```

Run the identical command twice and compare `package_hash`, hit metrics,
estimated coverage, candidate counts, and costs after excluding runtime fields.
They must match. Every package must contain at most 166 coupons and cost at most
4980 RUB.

- [ ] **Step 5: Performance gate before the holdout run**

Run one drawing with production defaults. Record total runtime. If it exceeds
30 seconds, profile before running 500 drawings; do not reduce search/sample
defaults silently. Any performance change must preserve deterministic package
output on the one-drawing fixture.

- [ ] **Step 6: Freeze configuration and run the last-500 experiment once**

```bash
.venv/bin/python -m toto_ai.cli backtest-strategies \
  --db data/toto.db \
  --last 500 \
  --holdout 150 \
  --bank 5000 \
  --stake 30 \
  --category 13 \
  --seed 42
```

Do not tune parameters after reading holdout results. If the run is interrupted,
fix operational reliability using development drawings, restore the same frozen
configuration, and rerun the complete benchmark.

- [ ] **Step 7: Run bank sensitivity without changing optimizer parameters**

Repeat the last-500 command for `--bank 3000` and `--bank 10000`. Keep seed,
candidate generation, scenario counts, split, and category unchanged.

- [ ] **Step 8: Update project-local memory with measured evidence**

Record:

- implementation modules and CLI in `ARCHITECTURE.md`;
- exact test count, Ruff result, smoke runtime, and last-500 result in
  `CURRENT_STATE.md`;
- completion status and the next evidence-driven task in `ROADMAP.md`;
- any frozen parameter or acceptance changes in `DECISIONS.md`;
- distinction between uniform brief coverage and direct weighted scenario
  coverage in `knowledge/cover_engine.md`.

Do not write that the strategy is profitable. Use `rejected`, `preliminary`, or
`proven` exactly as produced by the holdout report.

- [ ] **Step 9: Final verification and commit**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
git add src/toto_ai/cli.py tests/test_strategy_backtest.py \
  memory-bank/ARCHITECTURE.md memory-bank/CURRENT_STATE.md \
  memory-bank/ROADMAP.md memory-bank/DECISIONS.md knowledge/cover_engine.md
git commit -m "Add direct package strategy benchmark"
```

Expected: clean worktree, all tests pass, Ruff passes, and reports contain the
fixed development/holdout split and strategy status.
