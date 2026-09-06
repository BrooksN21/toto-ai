"""G1 research-only exact maximin swaps; no I/O or production integration.

Probability rows and resolved exposure policy arrive as immutable, hash-bound
inputs. The source input hash is a caller-owned identity, not proof of external
authority. Nothing here fits probabilities, discovers inputs, or selects wagers.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field

from toto_ai.ev.package_quality import (
    ExactCategoryCoverage,
    exact_category_probabilities,
)
from toto_ai.optimizer.direct_package import neighbors_within_distance
from toto_ai.optimizer.robust_package import ExposureConstraints

EPSILON = 1e-12
POLICY_VERSION = "g1-exact-maximin-refinement-v2"
OUTCOMES = "1X2"
ModelMetrics = tuple[tuple[str, tuple[float, float, float]], ...]


class RefinementIntegrityError(ValueError):
    """Invalid input or clock; no candidate result is returned."""


@dataclass(frozen=True)
class RefinementBinding:
    """Bank is requested budget; omitted effective budget resolves to that bank."""

    input_sha256: str
    initial_package_sha256: str
    candidate_universe_sha256: str
    probability_models_sha256: str
    exposure_constraints_sha256: str
    bank: int
    stake: int
    coupon_capacity: int
    effective_budget: int | None = None


@dataclass(frozen=True)
class RefinementLimits:
    """Predeclared positive budgets; defaults are conservative, not hard ceilings."""

    max_swap_evaluations: int = 64
    max_accepted_swaps: int = 2
    time_budget_seconds: float = 5.0


@dataclass(frozen=True)
class RefinementResult:
    selected_coupons: tuple[str, ...]
    status: str
    reason: str
    initial_metrics: ModelMetrics | None
    final_metrics: ModelMetrics | None
    evaluated_swap_count: int
    accepted_swap_count: int
    provisional_swap_count: int
    rejected_constraint_swaps: int
    diagnostics_before: dict | None
    diagnostics_after: dict | None
    input_hashes: dict[str, str]
    budget_summary: dict[str, int]
    elapsed_seconds: float
    constraint_violation_count: int = field(default=0, init=False)
    evaluation_authorized: bool = field(default=False, init=False)
    activation_allowed: bool = field(default=False, init=False)
    operator_compatible: bool = field(default=False, init=False)
    automatic_wagering: bool = field(default=False, init=False)
    semantic_hash: str = field(default="", init=False)

    def __post_init__(self):
        payload = asdict(self)
        for key in ("elapsed_seconds", "semantic_hash"):
            payload.pop(key)
        object.__setattr__(self, "semantic_hash", _hash(payload))


def _check(condition, reason):
    if not condition:
        raise RefinementIntegrityError(reason)


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _coupons(values, label):
    _check(isinstance(values, Sequence) and not isinstance(values, (str, bytes)), label)
    result = tuple(values)
    _check(
        result
        and all(
            isinstance(c, str) and len(c) == 15 and not set(c) - set(OUTCOMES)
            for c in result
        ),
        label,
    )
    _check(len(set(result)) == len(result), "DUPLICATE_" + label)
    return result


def _exposures(coupons):
    return tuple(
        tuple(sum(c[i] == o for c in coupons) for o in OUTCOMES) for i in range(15)
    )


def _within_bounds(coupons, bounds):
    return all(
        bounds.lower_bounds[i][o] <= count <= bounds.upper_bounds[i][o]
        for i, row in enumerate(_exposures(coupons))
        for o, count in enumerate(row)
    )


def _validate(initial, candidates, models, bounds, binding, limits):
    initial, candidates = (
        _coupons(initial, "INITIAL_PACKAGE"),
        _coupons(candidates, "CANDIDATE_UNIVERSE"),
    )
    _check(set(initial) <= set(candidates), "INITIAL_OUTSIDE_UNIVERSE")
    _check(isinstance(models, Mapping) and models, "PROBABILITY_MODELS_REQUIRED")
    _check(all(isinstance(name, str) and name for name in models), "MODEL_IDENTITY")
    normalized = {}
    for name in sorted(models):
        raw = models[name]
        _check(isinstance(raw, Sequence) and len(raw) == 15, "MODEL_EVENT_COUNT")
        rows = []
        for row in raw:
            _check(isinstance(row, Sequence) and len(row) == 3, "PROBABILITY_ROW")
            _check(
                all(
                    isinstance(v, (float, int))
                    and not isinstance(v, bool)
                    and math.isfinite(v)
                    and v >= 0
                    for v in row
                ),
                "INVALID_PROBABILITY",
            )
            values = tuple(float(v) for v in row)
            _check(
                math.isclose(math.fsum(values), 1, abs_tol=1e-9, rel_tol=0),
                "UNNORMALIZED_PROBABILITY",
            )
            rows.append(values)
        normalized[name] = tuple(rows)
    _check(isinstance(bounds, ExposureConstraints), "TYPED_EXPOSURE_CONSTRAINTS")
    _check(
        isinstance(bounds.lower_bounds, Sequence)
        and isinstance(bounds.upper_bounds, Sequence),
        "EXPOSURE_BOUNDS_SEQUENCE",
    )
    _check(
        len(bounds.lower_bounds) == len(bounds.upper_bounds) == 15,
        "EXPOSURE_EVENT_COUNT",
    )
    for lower, upper in zip(bounds.lower_bounds, bounds.upper_bounds, strict=True):
        _check(
            isinstance(lower, Sequence) and isinstance(upper, Sequence),
            "EXPOSURE_ROW_SEQUENCE",
        )
        _check(len(lower) == len(upper) == 3, "EXPOSURE_OUTCOMES")
        _check(
            all(type(v) is int and 0 <= v <= len(initial) for v in (*lower, *upper)),
            "EXPOSURE_BOUNDS",
        )
        _check(
            all(lo <= hi for lo, hi in zip(lower, upper, strict=True))
            and sum(lower) <= len(initial) <= sum(upper),
            "INFEASIBLE_EXPOSURE_BOUNDS",
        )
    _check(_within_bounds(initial, bounds), "INITIAL_VIOLATES_EXPOSURE_BOUNDS")
    _check(isinstance(binding, RefinementBinding), "TYPED_INPUT_BINDING")
    effective_budget = (
        binding.bank if binding.effective_budget is None else binding.effective_budget
    )
    _check(
        all(
            type(v) is int and v > 0
            for v in (
                binding.bank,
                effective_budget,
                binding.stake,
                binding.coupon_capacity,
            )
        )
        and effective_budget <= binding.bank
        and binding.coupon_capacity == len(initial)
        and binding.coupon_capacity == effective_budget // binding.stake
        and binding.stake * len(initial) <= effective_budget,
        "BANK_STAKE_CAPACITY_BINDING",
    )
    budget_summary = {
        "requested_bank": binding.bank,
        "effective_budget": effective_budget,
        "stake": binding.stake,
        "coupon_capacity": binding.coupon_capacity,
        "coupon_count": len(initial),
        "cost": binding.stake * len(initial),
        "unused_effective_budget": effective_budget - binding.stake * len(initial),
    }
    actual = {
        "initial_package_sha256": _hash(initial),
        "candidate_universe_sha256": _hash(sorted(candidates)),
        "probability_models_sha256": _hash(normalized),
        "exposure_constraints_sha256": _hash(asdict(bounds)),
    }
    _check(
        _sha(binding.input_sha256)
        and all(
            _sha(getattr(binding, key)) and getattr(binding, key) == digest
            for key, digest in actual.items()
        ),
        "INPUT_HASH_BINDING",
    )
    _check(isinstance(limits, RefinementLimits), "TYPED_LIMITS")
    _check(
        type(limits.max_swap_evaluations) is int
        and limits.max_swap_evaluations > 0
        and type(limits.max_accepted_swaps) is int
        and limits.max_accepted_swaps > 0,
        "ITERATION_LIMITS",
    )
    _check(
        isinstance(limits.time_budget_seconds, (int, float))
        and not isinstance(limits.time_budget_seconds, bool)
        and math.isfinite(limits.time_budget_seconds)
        and limits.time_budget_seconds > 0,
        "TIME_BUDGET",
    )
    actual.update(
        input_sha256=binding.input_sha256,
        binding_sha256=_hash(asdict(binding)),
        budget_sha256=_hash(budget_summary),
        config_sha256=_hash(
            {"policy_version": POLICY_VERSION, "epsilon": EPSILON, **asdict(limits)}
        ),
    )
    frozen_bounds = ExposureConstraints(
        tuple(tuple(row) for row in bounds.lower_bounds),
        tuple(tuple(row) for row in bounds.upper_bounds),
    )
    return (
        initial,
        tuple(sorted(candidates)),
        normalized,
        frozen_bounds,
        actual,
        budget_summary,
    )


class _BudgetExhausted(Exception):
    pass


class _VerificationFailed(Exception):
    pass


class _Budget:
    def __init__(self, clock, seconds):
        _check(callable(clock), "INJECTED_CLOCK_REQUIRED")
        _check(
            isinstance(seconds, (int, float))
            and not isinstance(seconds, bool)
            and math.isfinite(seconds)
            and seconds > 0,
            "TIME_BUDGET",
        )
        self.clock, self.seconds = clock, seconds
        self.start = self._read()
        self.last = self.start

    def _read(self):
        now = self.clock()
        _check(
            isinstance(now, (int, float))
            and not isinstance(now, bool)
            and math.isfinite(now),
            "INVALID_CLOCK",
        )
        return float(now)

    def check(self):
        now = self._read()
        _check(now >= self.last, "NONMONOTONIC_CLOCK")
        self.last = now
        if now - self.start >= self.seconds:
            raise _BudgetExhausted("TIME_BUDGET")

    @property
    def elapsed(self):
        return self.last - self.start


def _diagnostics(coupons, budget):
    covered = [set(), set()]
    for coupon in coupons:
        budget.check()
        for index, radius in enumerate((2, 1)):
            covered[index].update(neighbors_within_distance(coupon, radius))
            budget.check()
    distances = Counter(
        sum(a != b for a, b in zip(left, right, strict=True))
        for index, left in enumerate(coupons)
        for right in coupons[index + 1 :]
    )
    exposures = _exposures(coupons)
    return {
        "unique_coupon_count": len(coupons),
        "covered_state_count_13": len(covered[0]),
        "covered_state_count_14": len(covered[1]),
        "covered_state_count_15": len(coupons),
        "ball_multiplicity_excess_13": len(coupons) * 451 - len(covered[0]),
        "ball_multiplicity_excess_14": len(coupons) * 31 - len(covered[1]),
        "minimum_hamming_distance": min(distances) if distances else None,
        "pairwise_hamming_histogram": tuple(sorted(distances.items())),
        "event_outcome_exposures": exposures,
        "per_event_max_exposure_fraction": tuple(
            max(row) / len(coupons) for row in exposures
        ),
        "maximum_exposure_fraction": max(max(row) for row in exposures) / len(coupons),
    }


def _objective(metrics):
    p13 = [p[0] for _, p in metrics]
    return min(p13), math.fsum(p13) / len(p13)


def _non_degrading(metrics, baseline):
    if tuple(name for name, _ in metrics) != tuple(name for name, _ in baseline):
        return False
    return all(
        math.isfinite(new) and new >= old - EPSILON
        for (name, values), (other, original) in zip(metrics, baseline, strict=True)
        for new, old in zip(values, original, strict=True)
    )


def _verify(current, caches, models, baseline, bounds, budget):
    if not _within_bounds(current, bounds):
        raise _VerificationFailed("FINAL_EXPOSURE_BOUNDS")
    full = []
    for name, probabilities in models.items():
        budget.check()
        values = exact_category_probabilities(current, probabilities)
        budget.check()
        incremental = caches[name].probabilities
        if any(
            not math.isfinite(value) or abs(value - cached) > EPSILON
            for value, cached in zip(values, incremental, strict=True)
        ):
            raise _VerificationFailed("INCREMENTAL_FULL_MISMATCH")
        full.append((name, values))
    metrics = tuple(full)
    if not _non_degrading(metrics, baseline):
        raise _VerificationFailed("FINAL_CATEGORY_DEGRADATION")
    return metrics


def refine_maximin_package(
    *,
    initial_coupons: Sequence[str],
    candidate_coupons: Sequence[str],
    probability_models: Mapping[str, Sequence[Sequence[float]]],
    exposure_constraints: ExposureConstraints,
    binding: RefinementBinding,
    limits: RefinementLimits,
    clock: Callable[[], float],
) -> RefinementResult:
    """Refine within one fixed universe; rollback all provisional work on failure.

    The caller supplies resolved legacy integer exposure bounds, including its
    control-relative concentration caps. This function never invents a policy.
    Bank is the unchanged requested budget, not package cost. Effective budget
    defaults to bank; an explicit smaller positive budget retains both identities.
    Capacity remains fixed to the initial package and effective_budget // stake.
    Positive declared iteration budgets may exceed the conservative 64/2 defaults.
    The injected clock is checked around each exact primitive and search step;
    it is cooperative, not an interrupt inside the existing primitive. A caller
    needing a hard process deadline must enforce it separately (tests use 25s).
    No 166-coupon performance or model-quality claim is made by this library.
    """
    _check(isinstance(limits, RefinementLimits), "TYPED_LIMITS")
    budget = _Budget(clock, limits.time_budget_seconds)
    initial, candidates, models, exposure_constraints, hashes, budget_summary = (
        _validate(
            initial_coupons,
            candidate_coupons,
            probability_models,
            exposure_constraints,
            binding,
            limits,
        )
    )
    current = initial
    baseline = final_metrics = before = after = None
    evaluated = accepted = rejected = 0
    status, reason = "UNCHANGED", "NO_ADMISSIBLE_IMPROVEMENT"
    caches = {}
    try:
        budget.check()
        before = _diagnostics(initial, budget)
        for name, probabilities in models.items():
            budget.check()
            caches[name] = ExactCategoryCoverage(initial, probabilities)
            budget.check()
        baseline = tuple((name, cache.probabilities) for name, cache in caches.items())
        current_metrics = baseline
        while accepted < limits.max_accepted_swaps:
            best = None
            current_objective = _objective(current_metrics)[0]
            incoming_coupons = tuple(c for c in candidates if c not in current)
            for outgoing in sorted(current):
                for incoming in incoming_coupons:
                    budget.check()
                    if evaluated >= limits.max_swap_evaluations:
                        raise _BudgetExhausted("EVALUATION_BUDGET")
                    evaluated += 1
                    trial = tuple(incoming if c == outgoing else c for c in current)
                    if not _within_bounds(trial, exposure_constraints):
                        rejected += 1
                        continue
                    projected = []
                    for name, cache in caches.items():
                        budget.check()
                        projected.append(
                            (name, cache.probabilities_after_swap(outgoing, incoming))
                        )
                        budget.check()
                    metrics = tuple(projected)
                    if not _non_degrading(metrics, baseline):
                        continue
                    worst, mean = _objective(metrics)
                    if worst <= current_objective + EPSILON:
                        continue
                    key = (-worst, -mean, outgoing, incoming)
                    if best is None or key < best[0]:
                        best = (key, trial, metrics, outgoing, incoming)
            if best is None:
                break
            _, trial, metrics, outgoing, incoming = best
            for cache in caches.values():
                budget.check()
                cache.apply_swap(outgoing, incoming)
                budget.check()
            current, current_metrics = trial, metrics
            accepted += 1
        final_metrics = _verify(
            current, caches, models, baseline, exposure_constraints, budget
        )
        if (
            accepted
            and _objective(final_metrics)[0] <= _objective(baseline)[0] + EPSILON
        ):
            raise _VerificationFailed("FINAL_OBJECTIVE_NOT_IMPROVED")
        after = before if current == initial else _diagnostics(current, budget)
        budget.check()
        if accepted:
            status, reason = "REFINED", "VERIFIED_EXACT_MAXIMIN_IMPROVEMENT"
    except _BudgetExhausted as exc:
        status, reason = "BUDGET_EXHAUSTED", str(exc)
    except _VerificationFailed as exc:
        status, reason = "VERIFICATION_FAILED", str(exc)
    success = status == "REFINED"
    selected = current if success else initial
    return RefinementResult(
        selected_coupons=selected,
        status=status,
        reason=reason,
        initial_metrics=baseline,
        final_metrics=final_metrics if success else baseline,
        evaluated_swap_count=evaluated,
        accepted_swap_count=accepted if success else 0,
        provisional_swap_count=accepted,
        rejected_constraint_swaps=rejected,
        diagnostics_before=before,
        diagnostics_after=after if success else before,
        input_hashes={**hashes, "selected_package_sha256": _hash(selected)},
        budget_summary=budget_summary,
        elapsed_seconds=budget.elapsed,
    )
