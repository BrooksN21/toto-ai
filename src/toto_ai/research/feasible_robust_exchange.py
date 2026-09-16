"""Inactive bounded feasible one-out/one-in repair; no operational caller.

Objective: lexicographic (worst sampled category coverage, mean coverage).
These are optimization-sample metrics, never calibrated win probabilities.
Only complete feasible packages are accepted. Timeout returns ORIGINAL control.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass

import numpy as np

from toto_ai.optimizer.coupon_candidates import sample_scenarios
from toto_ai.optimizer.cover import category_max_errors
from toto_ai.optimizer.robust_package import (
    ExposureConstraints,
    _build_workload,
    _model_seed,
    _normalize_exposure_constraints,
    _normalize_models,
    _package_satisfies_bounds,
    _validate_candidates,
)


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _coupon_hash(coupons):
    return hashlib.sha256("\n".join(coupons).encode()).hexdigest()


@dataclass(frozen=True)
class RepairInput:
    source_input_sha256: str
    control_coupons: tuple[str, ...]
    candidates: tuple[str, ...]
    probability_models: tuple
    exposure_constraints: ExposureConstraints
    bank: int
    stake: int
    seed_material: str
    category: int
    sha256: str


@dataclass(frozen=True)
class AcceptedSwap:
    proposal: int
    position_1based: int
    removed: str
    added: str
    objective: tuple[float, float]
    package_order_sha256: str


@dataclass(frozen=True)
class RepairResult:
    input_sha256: str
    source_input_sha256: str
    selected_coupons: tuple[str, ...]
    output_order_sha256: str
    bank: int
    stake: int
    reason: str
    timed_out: bool
    proposals: int
    retained_changes: int
    accepted_changes: tuple[AcceptedSwap, ...]
    initial_objective: tuple[float, float] | None
    final_objective: tuple[float, float] | None
    training_seed_material: str
    sample_count: int
    wall_seconds: float
    objective_protocol: str = "LEXICOGRAPHIC_WORST_MEAN_SAMPLED_CATEGORY_V1"
    scope: str = "INACTIVE_RESEARCH_FEASIBLE_EXCHANGE_NOT_NATIVE_EQUIVALENT"
    operator_compatible: bool = False
    automatic_wagering: bool = False


def _validate_normalized_models(models):
    """Validate bound values without changing even one hashed float bit."""
    if not isinstance(models, tuple) or len(models) < 2:
        raise ValueError("at least two frozen probability models required")
    names = []
    event_count = None
    for item in models:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("frozen named probability model required")
        name, matrix = item
        if not isinstance(name, str) or not name:
            raise ValueError("nonempty model name required")
        names.append(name)
        if not isinstance(matrix, tuple) or not 1 <= len(matrix) <= 15:
            raise ValueError("frozen probability matrix needs1..15events")
        if event_count is None:
            event_count = len(matrix)
        if len(matrix) != event_count:
            raise ValueError("probability model event counts must match")
        for row in matrix:
            if (
                not isinstance(row, tuple)
                or len(row) != 3
                or any(
                    type(v) is not float or not math.isfinite(v) or v <= 0 for v in row
                )
            ):
                raise ValueError("three finite positive bound probabilities required")
            # Three IEEE754 divisions may sum one or two ULPs from1. This is
            # only a semantic unit-mass check: do not round or renormalize.
            # The caller's exact SHA check still rejects even one-ULP tampering.
            if abs(math.fsum(row) - 1.0) > 2 * math.ulp(1.0):
                raise ValueError("bound probabilities must already be normalized")
    if names != sorted(set(names)):
        raise ValueError("bound model names must be sorted and unique")
    return models


def bind_repair_input(
    *,
    source_input_sha256,
    control_coupons,
    candidates,
    probability_models,
    exposure_constraints,
    bank,
    stake,
    seed_material,
    category=13,
):
    # Normalize external values exactly once. Both initial binding and repair
    # then validate/hash this identical immutable representation.
    return _bind_normalized_repair_input(
        source_input_sha256=source_input_sha256,
        control_coupons=control_coupons,
        candidates=candidates,
        probability_models=_normalize_models(probability_models),
        exposure_constraints=exposure_constraints,
        bank=bank,
        stake=stake,
        seed_material=seed_material,
        category=category,
    )


def _bind_normalized_repair_input(
    *,
    source_input_sha256,
    control_coupons,
    candidates,
    probability_models,
    exposure_constraints,
    bank,
    stake,
    seed_material,
    category=13,
):
    if (
        not isinstance(source_input_sha256, str)
        or len(source_input_sha256) != 64
        or set(source_input_sha256) - set("0123456789abcdef")
    ):
        raise ValueError("source input SHA256 required")
    if (
        type(bank) is not int
        or type(stake) is not int
        or stake <= 0
        or bank <= 0
        or bank % stake
        or not 1 <= bank // stake <= 1000
    ):
        raise ValueError("explicit integer bank/stake and1..1000coupons required")
    if not isinstance(seed_material, str) or not seed_material:
        raise ValueError("nonempty seed required")
    if type(category) is not int or category not in (13, 14, 15):
        raise ValueError("category must be13/14/15")
    models = _validate_normalized_models(probability_models)
    events = len(models[0][1])
    if not 1 <= events <= 15:
        raise ValueError("1..15events required")
    control = tuple(control_coupons)
    pool = tuple(dict.fromkeys((*candidates, *control)))
    if len(control) != bank // stake or len(set(control)) != len(control):
        raise ValueError("control must have N unique coupons at exact budget")
    _validate_candidates(pool, events)
    bounds = _normalize_exposure_constraints(
        exposure_constraints, event_count=events, package_size=len(control)
    )
    if bounds is None or not _package_satisfies_bounds(control, bounds):
        raise ValueError("complete feasible seed and explicit constraints required")
    # Freeze nested values, including caller-provided list bounds.
    bounds = ExposureConstraints(
        tuple(tuple(v) for v in bounds.lower_bounds),
        tuple(tuple(v) for v in bounds.upper_bounds),
    )
    data = dict(
        source_input_sha256=source_input_sha256,
        control_coupons=control,
        candidates=pool,
        probability_models=models,
        exposure_constraints=bounds,
        bank=bank,
        stake=stake,
        seed_material=seed_material,
        category=category,
    )
    draft = RepairInput(**data, sha256="")
    payload = asdict(draft)
    payload.pop("sha256")
    return RepairInput(**data, sha256=_digest(payload))


def repair_from_feasible_seed(
    spec: RepairInput,
    *,
    expected_input_sha256: str,
    sample_count=10000,
    max_candidates=512,
    max_proposals=2000,
    max_accepted_changes=20,
    time_budget_seconds=30,
    progress=None,
    time_func=time.perf_counter,
):
    if not isinstance(spec, RepairInput):
        raise ValueError("typed input binding required")
    payload = asdict(spec)
    stored = payload.pop("sha256")
    if stored != expected_input_sha256 or stored != _digest(payload):
        raise ValueError("research input binding mismatch")
    # Revalidation also rejects a correctly rehashed but invalid mutable input.
    data = dict(payload)
    data["probability_models"] = spec.probability_models
    data["exposure_constraints"] = spec.exposure_constraints
    if _bind_normalized_repair_input(**data).sha256 != stored:
        raise ValueError("input binding mismatch")
    for name, value, ceiling in (
        ("sample", sample_count, 100000),
        ("candidate", max_candidates, 1000),
        ("proposal", max_proposals, 50000),
        ("accepted", max_accepted_changes, 1000),
    ):
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ValueError(f"{name} budget must be1..{ceiling}")
    if len(spec.candidates) > max_candidates:
        raise ValueError("candidate budget exceeded")
    if (
        not isinstance(time_budget_seconds, (int, float))
        or not math.isfinite(time_budget_seconds)
        or not 0 < time_budget_seconds <= 60
    ):
        raise ValueError("time budget must be(0,60]")
    start = time_func()
    deadline = start + time_budget_seconds
    training_seed = spec.seed_material + "\0feasible-exchange-v1"
    pool = spec.candidates
    idx = {c: i for i, c in enumerate(pool)}
    selected = [idx[c] for c in spec.control_coupons]
    original = list(selected)
    accepted = []
    proposals = 0
    initial = None
    current = None

    def notify(phase, **detail):
        if progress is not None:
            progress(dict(phase=phase, proposals=proposals, **detail))

    def finish(reason, timeout=False):
        chosen = original if timeout else selected
        coupons = tuple(pool[i] for i in chosen)
        assert len(coupons) == len(set(coupons)) == spec.bank // spec.stake
        assert _package_satisfies_bounds(coupons, spec.exposure_constraints)
        return RepairResult(
            stored,
            spec.source_input_sha256,
            coupons,
            _coupon_hash(coupons),
            spec.bank,
            spec.stake,
            reason,
            timeout,
            proposals,
            0 if timeout else len(accepted),
            tuple(accepted),
            initial,
            initial if timeout else current,
            training_seed,
            sample_count,
            max(0.0, time_func() - start),
        )

    workloads = []
    for name, probabilities in spec.probability_models:
        if time_func() >= deadline:
            return finish("TIMEOUT_RETURN_CONTROL", True)
        notify("preparing_model", model=name)
        scenarios = sample_scenarios(
            probabilities, sample_count, _model_seed(training_seed, name)
        )
        work = _build_workload(
            model_name=name,
            probabilities=probabilities,
            candidates=pool,
            candidate_index=idx,
            scenarios=scenarios,
            max_errors=category_max_errors(spec.category),
            deadline=deadline,
            time_func=time_func,
        )
        if work is None:
            return finish("TIMEOUT_RETURN_CONTROL", True)
        workloads.append(work)
    covers = [
        [np.fromiter(s, dtype=np.intp) for s in w.candidate_to_scenarios]
        for w in workloads
    ]
    weights = [np.asarray(w.weights, dtype=np.int64) for w in workloads]
    coverage_counts = []
    for indexes, w in zip(covers, weights, strict=True):
        counts = np.zeros(len(w), dtype=np.int16)
        for candidate in selected:
            counts[indexes[candidate]] += 1
        coverage_counts.append(counts)

    def key(counts):
        values = [int(w[c > 0].sum()) for c, w in zip(counts, weights, strict=True)]
        return min(values), sum(values)

    def objective(k):
        return k[0] / sample_count, k[1] / (sample_count * len(workloads))

    current_key = key(coverage_counts)
    initial = current = objective(current_key)
    digits = np.array([["1X2".index(o) for o in c] for c in pool], dtype=np.int8)
    exposure = np.stack([(digits[selected] == j).sum(0) for j in range(3)], 1)
    lo = np.asarray(spec.exposure_constraints.lower_bounds)
    hi = np.asarray(spec.exposure_constraints.upper_bounds)
    onehot = np.eye(3, dtype=np.int16)[digits]
    order = sorted(
        range(len(pool)),
        key=lambda i: (
            hashlib.sha256((spec.seed_material + "\0" + pool[i]).encode()).digest(),
            pool[i],
        ),
    )
    positions = sorted(
        range(len(selected)),
        key=lambda i: hashlib.sha256(
            (spec.seed_material + "\0slot\0" + str(i)).encode()
        ).digest(),
    )
    notify("seed_verified", coupons=spec.control_coupons, objective=initial)
    while len(accepted) < max_accepted_changes:
        improved = False
        for incoming in order:
            if incoming in selected:
                continue
            for position in positions:
                if time_func() >= deadline:
                    return finish("TIMEOUT_RETURN_CONTROL", True)
                if proposals >= max_proposals:
                    return finish("PROPOSAL_BUDGET_EXHAUSTED")
                proposals += 1
                outgoing = selected[position]
                candidate_exposure = exposure - onehot[outgoing] + onehot[incoming]
                if proposals % 100 == 0:
                    notify("searching", accepted=len(accepted))
                if np.any(candidate_exposure < lo) or np.any(candidate_exposure > hi):
                    continue
                next_counts = []
                for counts, indexes in zip(coverage_counts, covers, strict=True):
                    candidate_counts = counts.copy()
                    candidate_counts[indexes[outgoing]] -= 1
                    candidate_counts[indexes[incoming]] += 1
                    next_counts.append(candidate_counts)
                next_key = key(next_counts)
                if next_key <= current_key:
                    continue
                # A complete feasible state is the only accepted transition.
                candidate_selected = list(selected)
                candidate_selected[position] = incoming
                coupons = tuple(pool[i] for i in candidate_selected)
                if not _package_satisfies_bounds(coupons, spec.exposure_constraints):
                    raise AssertionError("incremental exposure verification failed")
                selected = candidate_selected
                exposure = candidate_exposure
                coverage_counts = next_counts
                current_key = next_key
                current = objective(next_key)
                accepted.append(
                    AcceptedSwap(
                        proposals,
                        position + 1,
                        pool[outgoing],
                        pool[incoming],
                        current,
                        _coupon_hash(coupons),
                    )
                )
                notify(
                    "accepted",
                    iteration=len(accepted),
                    coupons=coupons,
                    objective=current,
                )
                improved = True
                break
            if improved:
                break
        if time_func() >= deadline:
            return finish("TIMEOUT_RETURN_CONTROL", True)
        if not improved:
            return finish(
                "NO_FEASIBLE_IMPROVEMENT" if not accepted else "LOCAL_ONE_SWAP_OPTIMUM"
            )
    if time_func() >= deadline:
        return finish("TIMEOUT_RETURN_CONTROL", True)
    return finish("ACCEPTED_CHANGE_BUDGET_EXHAUSTED")
