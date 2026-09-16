from dataclasses import replace

import pytest

from toto_ai.optimizer.robust_package import (
    ExposureConstraints,
    _package_satisfies_bounds,
)
from toto_ai.research.feasible_robust_exchange import (
    bind_repair_input,
    repair_from_feasible_seed,
)


def fixture(control=("XX",), candidates=("XX", "11", "22"), bounds=None):
    return bind_repair_input(
        source_input_sha256="a" * 64,
        control_coupons=control,
        candidates=candidates,
        probability_models={"a": ((0.8, 0.1, 0.1),) * 2, "b": ((0.7, 0.2, 0.1),) * 2},
        exposure_constraints=bounds
        or ExposureConstraints(((0, 0, 0),) * 2, ((len(control),) * 3,) * 2),
        bank=30 * len(control),
        stake=30,
        seed_material="p2-fixed",
        category=15,
    )


def run(spec, **kw):
    return repair_from_feasible_seed(
        spec,
        expected_input_sha256=spec.sha256,
        sample_count=200,
        max_candidates=20,
        max_proposals=100,
        max_accepted_changes=5,
        time_budget_seconds=5,
        **kw,
    )


def test_improvement_preserves_all_intermediate_states_and_original_input():
    spec = fixture()
    states = []
    r = run(spec, progress=states.append)
    assert r.selected_coupons == ("11",)
    assert r.final_objective > r.initial_objective
    assert r.retained_changes > 0
    assert r.input_sha256 == spec.sha256
    assert r.operator_compatible is False and r.automatic_wagering is False
    assert spec.control_coupons == ("XX",)
    previous = r.initial_objective
    for state in states:
        if state["phase"] != "accepted":
            continue
        coupons = state["coupons"]
        assert len(coupons) == len(set(coupons)) == spec.bank // spec.stake
        assert _package_satisfies_bounds(coupons, spec.exposure_constraints)
        assert state["objective"] > previous
        previous = state["objective"]
    again = run(spec)
    assert r.selected_coupons == again.selected_coupons
    assert r.accepted_changes == again.accepted_changes
    assert r.output_order_sha256 == again.output_order_sha256


def test_feasible_seed_remains_valid_when_greedy_prefix_would_dead_end():
    bounds = ExposureConstraints(((1, 0, 1),) * 2, ((1, 0, 1),) * 2)
    spec = fixture(("12", "21"), ("11", "12", "21"), bounds)
    r = run(spec)
    assert r.selected_coupons == spec.control_coupons
    assert r.retained_changes == 0
    assert r.reason == "NO_FEASIBLE_IMPROVEMENT"
    assert r.initial_objective == r.final_objective


def test_timeout_after_accepted_change_returns_exact_original_seed():
    spec = fixture()
    clock = [0.0]

    def progress(state):
        if state["phase"] == "accepted":
            clock[0] = 6.0

    r = run(spec, time_func=lambda: clock[0], progress=progress)
    assert r.timed_out
    assert r.selected_coupons == spec.control_coupons
    assert r.retained_changes == 0
    assert r.final_objective == r.initial_objective
    assert r.reason == "TIMEOUT_RETURN_CONTROL"


def test_tampered_input_or_wrong_expected_hash_fails_closed():
    spec = fixture()
    with pytest.raises(ValueError, match="binding"):
        run(replace(spec, bank=60))
    with pytest.raises(ValueError, match="binding"):
        repair_from_feasible_seed(spec, expected_input_sha256="b" * 64)
    changed = fixture(candidates=("XX", "11"))
    assert changed.sha256 != spec.sha256
    assert replace(spec, source_input_sha256="b" * 64).sha256 == spec.sha256
    with pytest.raises(ValueError, match="binding"):
        run(replace(spec, source_input_sha256="b" * 64))


def test_input_rejects_infeasible_seed_and_budget_mismatch():
    with pytest.raises(ValueError):
        fixture(
            ("11", "12"),
            ("11", "12"),
            ExposureConstraints(((1, 0, 1),) * 2, ((1, 0, 1),) * 2),
        )
    from dataclasses import asdict

    spec = fixture()
    kw = asdict(spec)
    kw.pop("sha256")
    kw["bank"] = 31
    kw["probability_models"] = dict(spec.probability_models)
    kw["exposure_constraints"] = spec.exposure_constraints
    with pytest.raises(ValueError):
        bind_repair_input(**kw)


def test_budget_does_not_silently_expand_or_truncate_candidates():
    spec = fixture()
    with pytest.raises(ValueError, match="candidate"):
        repair_from_feasible_seed(
            spec, expected_input_sha256=spec.sha256, max_candidates=1
        )
    r = repair_from_feasible_seed(
        spec,
        expected_input_sha256=spec.sha256,
        sample_count=20,
        max_proposals=1,
        max_accepted_changes=1,
        time_budget_seconds=5,
    )
    assert r.proposals <= 1
    assert len(r.selected_coupons) == 1


@pytest.mark.parametrize("control", [("11", "XX"), ("12", "21"), ("1X", "X1")])
def test_small_complete_universe_invariants_for_every_accepted_transition(control):
    from itertools import product

    pool = tuple("".join(c) for c in product("1X2", repeat=2))
    spec = fixture(control, pool)
    states = []
    result = run(spec, progress=states.append)
    assert result.final_objective >= result.initial_objective
    previous = result.initial_objective
    for state in states:
        if state["phase"] != "accepted":
            continue
        assert len(state["coupons"]) == len(set(state["coupons"])) == 2
        assert _package_satisfies_bounds(state["coupons"], spec.exposure_constraints)
        assert state["objective"] > previous
        previous = state["objective"]


def test_timeout_before_workload_returns_verified_control_without_scoring():
    spec = fixture()
    ticks = iter([0.0, 10.0, 10.0])
    result = run(spec, time_func=lambda: next(ticks))
    assert result.timed_out and result.selected_coupons == spec.control_coupons
    assert result.retained_changes == 0 and result.proposals == 0
    assert result.initial_objective is None and result.final_objective is None


def test_valid_bound_probability_roundoff_is_not_re_normalized():
    import math

    raw = (0.05893253780321972, 0.8679916827767922, 0.25372046235690526)
    spec = bind_repair_input(
        source_input_sha256="a" * 64,
        control_coupons=("1",),
        candidates=("1", "X", "2"),
        probability_models={"a": (raw,), "b": ((0.6, 0.2, 0.2),)},
        exposure_constraints=ExposureConstraints(((0, 0, 0),), ((1, 1, 1),)),
        bank=30,
        stake=30,
        seed_material="review",
        category=15,
    )
    assert math.fsum(spec.probability_models[0][1][0]) != 1.0
    assert (
        spec.sha256
        == "20b18372e387c41555497852f12a4d1cc958d7da78b4048a83882455c920040c"
    )
    original_models = spec.probability_models
    original_hash = spec.sha256
    result = run(spec)
    assert result.input_sha256 == original_hash
    assert spec.probability_models == original_models
    assert spec.sha256 == original_hash


def test_even_one_ulp_probability_tamper_retains_hash_rejection():
    import math

    spec = fixture()
    name, rows = spec.probability_models[0]
    changed_row = (math.nextafter(rows[0][0], 1.0), *rows[0][1:])
    changed_models = ((name, (changed_row, *rows[1:])), *spec.probability_models[1:])
    with pytest.raises(ValueError, match="binding"):
        run(replace(spec, probability_models=changed_models))


@pytest.mark.parametrize("mutation", ["models", "bank", "source"])
def test_rehashed_semantically_invalid_input_still_rejected(mutation):
    from dataclasses import asdict

    from toto_ai.research.feasible_robust_exchange import _digest

    spec = fixture()
    if mutation == "models":
        spec = replace(
            spec,
            probability_models=(
                ("a", ((1.0, 1.0, 1.0),) * 2),
                ("b", ((0.6, 0.2, 0.2),) * 2),
            ),
        )
    elif mutation == "bank":
        spec = replace(spec, bank=60)
    else:
        spec = replace(spec, source_input_sha256="z" * 64)
    payload = asdict(spec)
    payload.pop("sha256")
    spec = replace(spec, sha256=_digest(payload))
    with pytest.raises(ValueError):
        run(spec)


def test_model_normalization_happens_once_not_during_repair(monkeypatch):
    from toto_ai.research import feasible_robust_exchange as module

    original = module._normalize_models
    calls = []

    def track(models):
        calls.append(models)
        return original(models)

    monkeypatch.setattr(module, "_normalize_models", track)
    spec = fixture()
    run(spec)
    assert len(calls) == 1
