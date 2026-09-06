from __future__ import annotations

import math
import time

import numpy as np
import pytest

from toto_ai.ev import ternary
from toto_ai.ev.models import EVInput
from toto_ai.ev.package_quality import ExactCategoryCoverage


def test_expired_ev_budget_stops_before_component_work():
    from toto_ai.ev.runtime import RuntimeBudget, runtime_scope

    ev_input = EVInput(
        drawing_id=1,
        drawing_number=1,
        true_probabilities=((0.5, 0.3, 0.2),) * 9,
        crowd_probabilities=((0.4, 0.3, 0.3),) * 9,
        pool_sum=1000,
        jackpot=0,
        possible_winnings=500,
        probability_sources=("test",) * 9,
        fetched_at=None,
    )
    with runtime_scope(RuntimeBudget(deadline=time.perf_counter() - 1)):
        with pytest.raises(TimeoutError, match="deadline"):
            ternary.compute_ev_components(ev_input)


def test_budget_expires_inside_crowd_chunks_and_resets(monkeypatch):
    from toto_ai.ev.runtime import RuntimeBudget, runtime_scope

    calls = []

    def stop_after_first(*args):
        calls.append(1)
        budget.deadline = time.perf_counter() - 1
        return np.ones(len(args[-1]))

    monkeypatch.setattr(
        ternary, "_poisson_binomial_tails_for_validated_indices", stop_after_first
    )
    budget = RuntimeBudget(deadline=time.perf_counter() + 100)
    with runtime_scope(budget), pytest.raises(TimeoutError):
        ternary._crowd_qualifying_probabilities(((0.4, 0.3, 0.3),) * 3, 2, 5)
    assert len(calls) == 1
    ternary._crowd_qualifying_probabilities(((0.4, 0.3, 0.3),) * 3, 2, 5)
    assert len(calls) > 1


def _old_swap(coverage, outgoing, incoming):
    result = []
    for radius, (out, inc) in enumerate(
        zip(coverage._balls(outgoing), coverage._balls(incoming), strict=True)
    ):
        removed = math.fsum(
            coverage._state_probability(s)
            for s in out - inc
            if coverage._counts[radius].get(s) == 1
        )
        added = math.fsum(
            coverage._state_probability(s)
            for s in inc - out
            if coverage._counts[radius].get(s, 0) == 0
        )
        result.append(coverage._masses[radius] - removed + added)
    return tuple(result)


def test_swap_cache_is_exact_and_invalidated():
    coverage = ExactCategoryCoverage(
        ("1" * 15, "1" * 14 + "X", "2" * 15), ((0.5, 0.3, 0.2),) * 15
    )
    pairs = [("1" * 15, "1X" * 7 + "1"), ("2" * 15, "X" * 15)]
    for _ in range(2):
        for outgoing, incoming in pairs:
            assert coverage.probabilities_after_swap(outgoing, incoming) == _old_swap(
                coverage, outgoing, incoming
            )
    assert coverage._swap_mass_cache
    coverage.apply_swap(*pairs[0])
    assert not coverage._swap_mass_cache
    for outgoing, incoming in pairs:
        assert coverage.probabilities_after_swap(outgoing, incoming) == _old_swap(
            coverage, outgoing, incoming
        )
