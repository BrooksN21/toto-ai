"""G1 synthetic-only contracts; 11 deterministic + 4 uncertain events."""

import copy
import hashlib
import importlib
import importlib.util
import itertools
import json
import math
from dataclasses import replace

import pytest

PREFIX = "1" * 11
OUTCOMES = "1X2"


def _coupon(suffix):
    return PREFIX + suffix


def _matrix(row):
    return ((1.0, 0.0, 0.0),) * 11 + (row,) * 4


def _models():
    return {"model-a": _matrix((0.1, 0.1, 0.8)), "model-b": _matrix((0.2, 0.2, 0.6))}


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _oracle(coupons, probabilities):
    totals = [0.0, 0.0, 0.0]
    for tail in itertools.product(range(3), repeat=4):
        digits = (0,) * 11 + tail
        actual = "".join(OUTCOMES[d] for d in digits)
        probability = math.prod(probabilities[i][d] for i, d in enumerate(digits))
        best_hits = max(
            sum(a == b for a, b in zip(actual, coupon, strict=True))
            for coupon in coupons
        )
        for index, threshold in enumerate((13, 14, 15)):
            if best_hits >= threshold:
                totals[index] += probability
    return tuple(totals)


def _oracle_best(initial, candidates, models):
    baseline = {name: _oracle(initial, p) for name, p in models.items()}
    objective = min(values[0] for values in baseline.values())
    best, best_key = initial, None
    for outgoing in sorted(initial):
        for incoming in sorted(set(candidates) - set(initial)):
            trial = tuple(incoming if c == outgoing else c for c in initial)
            metrics = {name: _oracle(trial, p) for name, p in models.items()}
            if any(
                metrics[m][i] < baseline[m][i] - 1e-12 for m in models for i in range(3)
            ):
                continue
            worst = min(values[0] for values in metrics.values())
            if worst <= objective + 1e-12:
                continue
            key = (
                -worst,
                -math.fsum(v[0] for v in metrics.values()) / len(models),
                outgoing,
                incoming,
            )
            if best_key is None or key < best_key:
                best, best_key = trial, key
    return best


def _api():
    name = "toto_ai.optimizer.exact_maximin_refinement"
    assert importlib.util.find_spec(name) is not None, "G1 implementation missing"
    return importlib.import_module(name)


def _inputs(initial=None, candidates=None, models=None, bounds=None, **limits):
    from toto_ai.optimizer.robust_package import ExposureConstraints

    api = _api()
    initial = (_coupon("1111"),) if initial is None else tuple(initial)
    candidates = (
        (*initial, _coupon("1112"), _coupon("2222"))
        if candidates is None
        else tuple(candidates)
    )
    models = _models() if models is None else models
    n = len(initial)
    if bounds is None:
        bounds = ExposureConstraints(((0, 0, 0),) * 15, ((n, n, n),) * 15)
    binding = api.RefinementBinding(
        input_sha256="a" * 64,
        initial_package_sha256=_hash(initial),
        candidate_universe_sha256=_hash(sorted(candidates)),
        probability_models_sha256=_hash(models),
        exposure_constraints_sha256=_hash(
            {"lower_bounds": bounds.lower_bounds, "upper_bounds": bounds.upper_bounds}
        ),
        bank=30 * n,
        stake=30,
        coupon_capacity=n,
    )
    return dict(
        initial_coupons=initial,
        candidate_coupons=candidates,
        probability_models=models,
        exposure_constraints=bounds,
        binding=binding,
        limits=api.RefinementLimits(max_accepted_swaps=1, **limits),
        clock=lambda: 0.0,
    )


def test_exact_swap_matches_81_state_oracle_and_changes_worst_model():
    inputs = _inputs()
    before = copy.deepcopy({k: v for k, v in inputs.items() if k != "clock"})
    result = _api().refine_maximin_package(**inputs)
    expected = _oracle_best(
        inputs["initial_coupons"],
        inputs["candidate_coupons"],
        inputs["probability_models"],
    )
    assert result.selected_coupons == expected == (_coupon("2222"),)
    initial, final = dict(result.initial_metrics), dict(result.final_metrics)
    assert min(initial, key=lambda m: initial[m][0]) == "model-a"
    assert min(final, key=lambda m: final[m][0]) == "model-b"
    for name, probabilities in inputs["probability_models"].items():
        assert final[name] == pytest.approx(_oracle(expected, probabilities), abs=1e-12)
        assert all(final[name][i] >= initial[name][i] - 1e-12 for i in range(3))
    assert result.accepted_swap_count == 1
    assert result.status == "REFINED"
    assert result.constraint_violation_count == 0
    assert {k: v for k, v in inputs.items() if k != "clock"} == before
    assert not result.evaluation_authorized and not result.activation_allowed
    assert not result.operator_compatible and not result.automatic_wagering


def test_exact_union_is_not_sum_of_single_coupon_probabilities():
    models = {"uniform": _matrix((1 / 3, 1 / 3, 1 / 3))}
    initial = tuple(_coupon(s) for s in ("1111", "111X", "1112"))
    result = _api().refine_maximin_package(**_inputs(initial, initial, models))
    actual = dict(result.initial_metrics)["uniform"]
    assert actual[0] == pytest.approx(19 / 27, abs=1e-12)
    assert sum(_oracle((coupon,), models["uniform"])[0] for coupon in initial) > 1.0
    assert actual == pytest.approx(_oracle(initial, models["uniform"]), abs=1e-12)
    assert result.selected_coupons == initial
    assert result.diagnostics_before["minimum_hamming_distance"] == 1
    assert result.diagnostics_before["unique_coupon_count"] == 3


def test_better_single_coupon_can_reduce_union_and_must_be_rejected():
    model = _matrix((0.6, 0.2, 0.2))
    initial = (_coupon("1111"), _coupon("2222"))
    alternative = (initial[0], _coupon("111X"))
    assert _oracle((alternative[1],), model)[2] > _oracle((initial[1],), model)[2]
    assert _oracle(alternative, model)[0] < _oracle(initial, model)[0]
    result = _api().refine_maximin_package(
        **_inputs(initial, (*initial, alternative[1]), {"m": model})
    )
    assert result.selected_coupons == initial and result.accepted_swap_count == 0


def test_better_p13_cannot_pay_for_lower_p15():
    model = _matrix((0.6, 0.2, 0.2))
    initial = (_coupon("1111"), _coupon("111X"))
    alternative = (initial[0], _coupon("2222"))
    assert _oracle(alternative, model)[0] > _oracle(initial, model)[0]
    assert _oracle(alternative, model)[2] < _oracle(initial, model)[2]
    result = _api().refine_maximin_package(
        **_inputs(initial, (*initial, alternative[1]), {"m": model})
    )
    assert result.selected_coupons == initial


def test_candidate_order_model_order_and_equal_objectives_have_canonical_ties():
    models = {"m": _matrix((0.1, 0.45, 0.45))}
    candidates = tuple(_coupon(s) for s in ("1111", "2222", "XXXX"))
    a = _api().refine_maximin_package(**_inputs(candidates[:1], candidates, models))
    b = _api().refine_maximin_package(
        **_inputs(candidates[:1], candidates[::-1], models)
    )
    assert a.selected_coupons == b.selected_coupons == (_coupon("2222"),)
    assert a.semantic_hash == b.semantic_hash
    inputs = _inputs()
    one = _api().refine_maximin_package(**inputs)
    inputs["probability_models"] = dict(
        reversed(list(inputs["probability_models"].items()))
    )
    assert _api().refine_maximin_package(**inputs).semantic_hash == one.semantic_hash


def test_sub_epsilon_gain_is_not_accepted():
    models = {"m": _matrix((1 / 3 - 1e-14, 1 / 3, 1 / 3 + 1e-14))}
    initial, incoming = _coupon("1111"), _coupon("2222")
    gain = _oracle((incoming,), models["m"])[0] - _oracle((initial,), models["m"])[0]
    assert 0 < gain < 1e-12
    result = _api().refine_maximin_package(
        **_inputs((initial,), (initial, incoming), models)
    )
    assert result.selected_coupons == (initial,)


@pytest.mark.parametrize("kind", ["floor", "cap"])
def test_resolved_exposure_floors_and_caps_block_otherwise_improving_swap(kind):
    from toto_ai.optimizer.robust_package import ExposureConstraints

    lower, upper = [(0, 0, 0)] * 15, [(1, 1, 1)] * 15
    if kind == "floor":
        lower[-1] = (1, 0, 0)
    else:
        upper[-1] = (1, 1, 0)
    bounds = ExposureConstraints(tuple(lower), tuple(upper))
    initial = (_coupon("1111"),)
    result = _api().refine_maximin_package(
        **_inputs(initial, (*initial, _coupon("2222")), bounds=bounds)
    )
    assert result.selected_coupons == initial
    assert result.constraint_violation_count == 0
    assert result.rejected_constraint_swaps == 1


@pytest.mark.parametrize(
    "field",
    [
        "input_sha256",
        "initial_package_sha256",
        "candidate_universe_sha256",
        "probability_models_sha256",
        "exposure_constraints_sha256",
        "bank",
        "stake",
        "coupon_capacity",
    ],
)
def test_input_binding_and_capacity_mismatch_fail_before_any_result(field):
    inputs = _inputs()
    value = (
        "invalid"
        if field == "input_sha256"
        else "0" * 64
        if field.endswith("sha256")
        else 0
    )
    inputs["binding"] = replace(inputs["binding"], **{field: value})
    with pytest.raises(_api().RefinementIntegrityError):
        _api().refine_maximin_package(**inputs)


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate_initial",
        "duplicate_candidate",
        "invalid_coupon",
        "wrong_length",
        "nan",
        "negative",
        "unnormalized",
        "wrong_event_count",
        "bad_bound",
        "initial_violates_bound",
    ],
)
def test_malformed_input_never_returns_a_refined_package(damage):
    from toto_ai.optimizer.robust_package import ExposureConstraints

    inputs = _inputs()
    if damage == "duplicate_initial":
        inputs["initial_coupons"] *= 2
    elif damage == "duplicate_candidate":
        inputs["candidate_coupons"] *= 2
    elif damage in ("invalid_coupon", "wrong_length"):
        inputs["candidate_coupons"] = (
            *inputs["candidate_coupons"],
            "A" * 15 if damage == "invalid_coupon" else "1",
        )
    elif damage in ("nan", "negative", "unnormalized", "wrong_event_count"):
        rows = list(inputs["probability_models"]["model-a"])
        rows[-1] = (
            (float("nan"), 0.5, 0.5)
            if damage == "nan"
            else (-0.1, 0.5, 0.6)
            if damage == "negative"
            else (0.1, 0.1, 0.1)
        )
        inputs["probability_models"]["model-a"] = (
            rows[:-1] if damage == "wrong_event_count" else rows
        )
    else:
        bound = (2, 0, 0) if damage == "bad_bound" else (0, 1, 0)
        inputs["exposure_constraints"] = ExposureConstraints(
            (bound,) * 15, ((1, 1, 1),) * 15
        )
    with pytest.raises(_api().RefinementIntegrityError):
        _api().refine_maximin_package(**inputs)


def test_evaluation_budget_exhaustion_discards_unfinished_best_proposal():
    inputs = _inputs(max_swap_evaluations=1)
    result = _api().refine_maximin_package(**inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.selected_coupons == inputs["initial_coupons"]
    assert result.evaluated_swap_count == 1 and result.accepted_swap_count == 0


def test_injected_clock_timeout_after_provisional_swap_rolls_back(monkeypatch):
    api = _api()
    inputs = _inputs()
    inputs["limits"] = api.RefinementLimits(max_accepted_swaps=2, time_budget_seconds=1)
    expired = False
    original = api.ExactCategoryCoverage.apply_swap

    def apply_and_expire(self, outgoing, incoming):
        nonlocal expired
        original(self, outgoing, incoming)
        expired = True

    monkeypatch.setattr(api.ExactCategoryCoverage, "apply_swap", apply_and_expire)
    inputs["clock"] = lambda: 2.0 if expired else 0.0
    result = api.refine_maximin_package(**inputs)
    assert expired  # a real provisional change was reached before timeout
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.selected_coupons == inputs["initial_coupons"]
    assert result.accepted_swap_count == 0


def test_full_exact_verification_failure_discards_candidate(monkeypatch):
    api = _api()
    original = api.exact_category_probabilities

    def wrong_full_evaluation(coupons, probabilities):
        actual = original(coupons, probabilities)
        return (actual[0] - 0.01, *actual[1:])

    monkeypatch.setattr(api, "exact_category_probabilities", wrong_full_evaluation)
    inputs = _inputs()
    result = api.refine_maximin_package(**inputs)
    assert result.status == "VERIFICATION_FAILED"
    assert result.selected_coupons == inputs["initial_coupons"]
    assert result.accepted_swap_count == 0


def test_two_swap_limit_and_full_recheck_preserve_each_model_category():
    initial = (_coupon("1111"), _coupon("111X"))
    candidates = (*initial, _coupon("2222"), _coupon("222X"), _coupon("22X2"))
    inputs = _inputs(initial, candidates)
    inputs["limits"] = _api().RefinementLimits(max_accepted_swaps=2)
    result = _api().refine_maximin_package(**inputs)
    assert 0 < result.accepted_swap_count <= 2
    assert result.evaluated_swap_count <= 64
    for name, p in inputs["probability_models"].items():
        final = dict(result.final_metrics)[name]
        assert final == pytest.approx(_oracle(result.selected_coupons, p), abs=1e-12)
        assert all(final[i] >= _oracle(initial, p)[i] - 1e-12 for i in range(3))


def test_runtime_path_has_no_io_network_db_environment_or_subprocess(monkeypatch):
    import builtins
    import os
    import socket
    import sqlite3
    import subprocess

    inputs = _inputs()
    api = _api()

    def forbidden(*args, **kwargs):
        raise AssertionError("G1 attempted external or environment access")

    with monkeypatch.context() as guard:
        for obj, name in (
            (builtins, "open"),
            (os, "open"),
            (os, "getenv"),
            (socket, "socket"),
            (sqlite3, "connect"),
            (subprocess, "Popen"),
        ):
            guard.setattr(obj, name, forbidden)
        result = api.refine_maximin_package(**inputs)
    assert result.status == "REFINED"


def test_hash_bound_constraints_are_snapshotted_before_clock_can_change_caller_lists():
    from toto_ai.optimizer.robust_package import ExposureConstraints

    upper = [[1, 1, 1] for _ in range(15)]
    upper[-1][2] = 0
    bounds = ExposureConstraints([[0, 0, 0] for _ in range(15)], upper)
    initial = (_coupon("1111"),)
    inputs = _inputs(initial, (*initial, _coupon("2222")), bounds=bounds)
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls == 2:  # after the input hash was checked
            upper[-1][2] = 1
        return 0.0

    inputs["clock"] = clock
    result = _api().refine_maximin_package(**inputs)
    assert result.selected_coupons == initial
    assert result.rejected_constraint_swaps == 1


@pytest.mark.parametrize(
    "tail, incoming, guarded_index",
    [
        ("111X", "1XX1", 2),
        ("112X", "1X1X", 1),
    ],
)
def test_each_high_category_guard_is_independently_necessary(
    tail, incoming, guarded_index
):
    probabilities = ((1.0, 0.0, 0.0),) * 11 + (
        (0.5, 0.3, 0.2),
        (0.5, 0.2, 0.3),
        (0.3, 0.6, 0.1),
        (0.2, 0.2, 0.6),
    )
    initial = (_coupon("1111"), _coupon(tail))
    trial = (initial[0], _coupon(incoming))
    old, new = _oracle(initial, probabilities), _oracle(trial, probabilities)
    assert new[0] > old[0]
    assert new[guarded_index] < old[guarded_index]
    assert new[3 - guarded_index] >= old[3 - guarded_index]
    result = _api().refine_maximin_package(
        **_inputs(initial, (*initial, trial[1]), {"m": probabilities})
    )
    assert result.selected_coupons == initial


def test_evaluation_exhaustion_after_accepted_round_rolls_back_entire_run():
    inputs = _inputs(max_swap_evaluations=2)
    inputs["limits"] = replace(inputs["limits"], max_accepted_swaps=2)
    result = _api().refine_maximin_package(**inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.provisional_swap_count == 1
    assert result.accepted_swap_count == 0
    assert result.selected_coupons == inputs["initial_coupons"]
    assert result.final_metrics == result.initial_metrics


def test_better_worst_case_cannot_hide_another_models_p13_loss():
    initial = (_coupon("1111"), _coupon("2222"))
    trial = (initial[0], _coupon("111X"))
    models = {"a": _matrix((0.3, 0.6, 0.1)), "b": _matrix((0.6, 0.2, 0.2))}
    before = {name: _oracle(initial, p) for name, p in models.items()}
    after = {name: _oracle(trial, p) for name, p in models.items()}
    assert min(v[0] for v in after.values()) > min(v[0] for v in before.values())
    assert after["b"][0] < before["b"][0]
    assert all(after[name][i] > before[name][i] for name in models for i in (1, 2))
    result = _api().refine_maximin_package(
        **_inputs(initial, (*initial, trial[1]), models)
    )
    assert result.selected_coupons == initial


@pytest.mark.parametrize("clock_values", [(0.0, float("nan")), (1.0, 0.0), (False,)])
def test_invalid_or_backward_clock_fails_closed(clock_values):
    values = iter(clock_values)
    inputs = _inputs()
    inputs["clock"] = lambda: next(values)
    with pytest.raises(_api().RefinementIntegrityError):
        _api().refine_maximin_package(**inputs)


def test_deadline_equality_returns_baseline_without_inventing_metrics():
    values = iter((0.0, 1.0))
    inputs = _inputs()
    inputs["clock"] = lambda: next(values)
    inputs["limits"] = replace(inputs["limits"], time_budget_seconds=1)
    result = _api().refine_maximin_package(**inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.selected_coupons == inputs["initial_coupons"]
    assert result.initial_metrics is None and result.final_metrics is None


@pytest.mark.parametrize(
    "limits,valid",
    [
        ({"max_swap_evaluations": 65}, True),
        ({"max_swap_evaluations": True}, False),
        ({"max_accepted_swaps": 3}, True),
        ({"time_budget_seconds": float("inf")}, False),
    ],
)
def test_predeclared_iteration_and_time_limits_are_enforced(limits, valid):
    inputs = _inputs()
    inputs["limits"] = replace(inputs["limits"], **limits)
    if valid:
        result = _api().refine_maximin_package(**inputs)
        assert result.status == "REFINED"
        assert result.evaluated_swap_count <= inputs["limits"].max_swap_evaluations
        assert result.accepted_swap_count <= inputs["limits"].max_accepted_swaps
    else:
        with pytest.raises(_api().RefinementIntegrityError):
            _api().refine_maximin_package(**inputs)


@pytest.mark.parametrize(
    "capacity,candidate_count,model_count", [(1, 3, 2), (2, 8, 3), (8, 32, 3)]
)
def test_synthetic_size_runtime_observation(capacity, candidate_count, model_count):
    import statistics
    import time

    tails = ["".join(row) for row in itertools.product(OUTCOMES, repeat=4)]
    candidates = tuple(_coupon(tail) for tail in tails[:candidate_count])
    models = {
        "a": _matrix((0.1, 0.1, 0.8)),
        "b": _matrix((0.2, 0.2, 0.6)),
        "c": _matrix((0.3, 0.3, 0.4)),
    }
    models = dict(list(models.items())[:model_count])
    inputs = _inputs(candidates[:capacity], candidates, models)
    inputs["limits"] = _api().RefinementLimits(max_accepted_swaps=2)
    inputs["clock"] = time.perf_counter
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        result = _api().refine_maximin_package(**inputs)
        runs.append(time.perf_counter() - start)
        assert len(result.selected_coupons) == capacity
        assert result.evaluated_swap_count <= 64
        assert result.accepted_swap_count <= 2
        assert result.constraint_violation_count == 0
    print(
        "G1_SYNTHETIC_RUNTIME="
        + json.dumps(
            {
                "capacity": capacity,
                "candidate_count": candidate_count,
                "model_count": model_count,
                "runs_seconds": runs,
                "median_seconds": statistics.median(runs),
                "last_status": result.status,
                "last_evaluated_swaps": result.evaluated_swap_count,
                "last_accepted_swaps": result.accepted_swap_count,
                "coupon_166_measured": False,
            },
            sort_keys=True,
        )
    )


@pytest.mark.parametrize("evaluations,rounds", [(166, 1), (64, 3), (166, 3)])
def test_reviewfix_r1_predeclared_limits_are_not_synthetic_ceiling(evaluations, rounds):
    api = _api()
    initial = (_coupon("1111"),)
    data = _inputs(initial, (*initial, _coupon("2222")))
    data["limits"] = api.RefinementLimits(
        max_swap_evaluations=evaluations, max_accepted_swaps=rounds
    )
    result = api.refine_maximin_package(**data)
    assert result.status == "REFINED" and result.accepted_swap_count == 1
    assert result.evaluated_swap_count <= 2
    for name, rows in data["probability_models"].items():
        assert dict(result.final_metrics)[name] == pytest.approx(
            _oracle(result.selected_coupons, rows), abs=1e-12
        )
    assert api.RefinementLimits().max_swap_evaluations == 64
    assert api.RefinementLimits().max_accepted_swaps == 2
    assert not result.evaluation_authorized and not result.activation_allowed


@pytest.mark.parametrize("field", ["max_swap_evaluations", "max_accepted_swaps"])
@pytest.mark.parametrize("value", [0, -1, True, 1.0, "3", None])
def test_reviewfix_r1_iteration_limits_require_positive_nonboolean_integers(
    field, value
):
    data = _inputs()
    data["limits"] = replace(data["limits"], **{field: value})
    with pytest.raises(_api().RefinementIntegrityError, match="ITERATION_LIMITS"):
        _api().refine_maximin_package(**data)


@pytest.mark.parametrize(
    "evaluations,expected_status", [(27, "REFINED"), (26, "BUDGET_EXHAUSTED")]
)
def test_reviewfix_r1_three_round_control_flow_and_whole_run_rollback(
    monkeypatch, evaluations, expected_status
):
    api = _api()
    initial = tuple(_coupon(t) for t in ("1111", "111X", "1112"))
    incoming = tuple(_coupon(t) for t in ("2222", "222X", "2221"))
    data = _inputs(initial, (*initial, *incoming))
    data["limits"] = api.RefinementLimits(
        max_swap_evaluations=evaluations, max_accepted_swaps=3
    )
    calls = {"projected": 0, "applied": 0, "verified": 0}

    def metrics(coupons):
        gain = sum(c in incoming for c in coupons) * 0.1
        return (0.2 + gain, 0.1 + gain, 0.01 + gain)

    class StubCoverage:
        def __init__(self, coupons, probabilities):
            self.coupons = tuple(coupons)
            self.probabilities = metrics(coupons)

        def probabilities_after_swap(self, outgoing, incoming):
            calls["projected"] += 1
            return metrics(
                tuple(incoming if c == outgoing else c for c in self.coupons)
            )

        def apply_swap(self, outgoing, incoming):
            calls["applied"] += 1
            self.coupons = tuple(incoming if c == outgoing else c for c in self.coupons)
            self.probabilities = metrics(self.coupons)

    def full(coupons, probabilities):
        calls["verified"] += 1
        return metrics(coupons)

    monkeypatch.setattr(api, "ExactCategoryCoverage", StubCoverage)
    monkeypatch.setattr(api, "exact_category_probabilities", full)
    monkeypatch.setattr(
        api, "_diagnostics", lambda coupons, budget: {"stub_only": True}
    )
    result = api.refine_maximin_package(**data)
    assert result.status == expected_status
    assert result.evaluated_swap_count == evaluations
    assert calls["projected"] == evaluations * len(data["probability_models"])
    if expected_status == "REFINED":
        assert set(result.selected_coupons) == set(incoming)
        assert result.accepted_swap_count == result.provisional_swap_count == 3
        assert calls["applied"] == 6 and calls["verified"] == 2
        assert dict(result.final_metrics)["model-a"] == metrics(incoming)
    else:
        assert result.reason == "EVALUATION_BUDGET"
        assert result.selected_coupons == initial
        assert result.accepted_swap_count == 0 and result.provisional_swap_count == 2
        assert calls["applied"] == 4 and calls["verified"] == 0
        assert result.final_metrics == result.initial_metrics


def test_reviewfix_r1_declared_budget_is_configuration_hash_bound():
    api = _api()
    data = _inputs()
    base = api.refine_maximin_package(**data)
    for field, value in (("max_swap_evaluations", 166), ("max_accepted_swaps", 3)):
        changed = data | {"limits": replace(data["limits"], **{field: value})}
        result = api.refine_maximin_package(**changed)
        assert (
            result.input_hashes["config_sha256"] != base.input_hashes["config_sha256"]
        )
        assert (
            result.input_hashes["binding_sha256"] == base.input_hashes["binding_sha256"]
        )


@pytest.mark.parametrize(
    "bank,effective",
    [(30, None), (31, None), (50, None), (59, None), (100, 31), (100, 50), (31, 31)],
)
@pytest.mark.parametrize("has_alternative", [False, True])
def test_reviewfix_r2_requested_effective_and_spent_budget_are_distinct(
    bank, effective, has_alternative
):
    from dataclasses import asdict

    api = _api()
    initial = (_coupon("1111"),)
    candidates = (*initial, _coupon("2222")) if has_alternative else initial
    data = _inputs(initial, candidates)
    data["binding"] = replace(data["binding"], bank=bank, effective_budget=effective)
    before = copy.deepcopy(data["binding"])
    result = api.refine_maximin_package(**data)
    resolved = bank if effective is None else effective
    expected = {
        "requested_bank": bank,
        "effective_budget": resolved,
        "stake": 30,
        "coupon_capacity": 1,
        "coupon_count": 1,
        "cost": 30,
        "unused_effective_budget": resolved - 30,
    }
    assert result.budget_summary == expected
    assert result.status == ("REFINED" if has_alternative else "UNCHANGED")
    assert data["binding"] == before and data["binding"].bank == bank
    assert result.input_hashes["budget_sha256"] == _hash(expected)
    assert result.input_hashes["binding_sha256"] == _hash(asdict(before))
    assert result.budget_summary["cost"] <= resolved <= bank
    for name, rows in data["probability_models"].items():
        assert dict(result.final_metrics)[name] == pytest.approx(
            _oracle(result.selected_coupons, rows), abs=1e-12
        )


@pytest.mark.parametrize(
    "field", ["bank", "effective_budget", "stake", "coupon_capacity"]
)
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "30"])
def test_reviewfix_r2_invalid_budget_types_and_values_fail_closed(field, value):
    data = _inputs()
    data["binding"] = replace(data["binding"], effective_budget=30)
    data["binding"] = replace(data["binding"], **{field: value})
    with pytest.raises(
        _api().RefinementIntegrityError, match="BANK_STAKE_CAPACITY_BINDING"
    ):
        _api().refine_maximin_package(**data)


@pytest.mark.parametrize(
    "bank,effective,capacity",
    [
        (29, None, 1),
        (60, None, 1),
        (31, 32, 1),
        (100, 29, 1),
        (100, 60, 1),
        (60, 60, 2),
    ],
)
def test_reviewfix_r2_capacity_overspend_and_requested_bank_guards(
    bank, effective, capacity
):
    data = _inputs()
    data["binding"] = replace(
        data["binding"], bank=bank, effective_budget=effective, coupon_capacity=capacity
    )
    with pytest.raises(
        _api().RefinementIntegrityError, match="BANK_STAKE_CAPACITY_BINDING"
    ):
        _api().refine_maximin_package(**data)


def test_reviewfix_r2_binding_preserves_remainder_identity_even_when_cost_matches():
    api = _api()
    data = _inputs()
    results = []
    for bank, effective in ((31, None), (50, None), (100, 31), (100, 50)):
        binding = replace(data["binding"], bank=bank, effective_budget=effective)
        results.append(api.refine_maximin_package(**(data | {"binding": binding})))
    assert len({r.input_hashes["binding_sha256"] for r in results}) == 4
    assert len({r.input_hashes["budget_sha256"] for r in results}) == 4
    assert len({r.semantic_hash for r in results}) == 4
    assert len({r.selected_coupons for r in results}) == 1
    assert all(r.budget_summary["cost"] == 30 for r in results)


def test_reviewfix_r2_budget_ledger_survives_whole_run_rollback():
    api = _api()
    data = _inputs(max_swap_evaluations=1)
    data["binding"] = replace(data["binding"], bank=100, effective_budget=50)
    result = api.refine_maximin_package(**data)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.selected_coupons == data["initial_coupons"]
    assert result.budget_summary["requested_bank"] == 100
    assert result.budget_summary["effective_budget"] == 50
    assert result.budget_summary["cost"] == 30
    assert result.budget_summary["unused_effective_budget"] == 20
    assert result.input_hashes["budget_sha256"] == _hash(result.budget_summary)
