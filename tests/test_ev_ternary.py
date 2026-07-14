import itertools
import math
import weakref

import numpy as np
import pytest

import toto_ai.ev.ternary as ternary_module
from toto_ai.ev.models import EVComponents, EVInput
from toto_ai.ev.reference import brute_force_gross_ev, joint_distribution
from toto_ai.ev.ternary import (
    compute_ev_components,
    compute_ev_surface,
    coupon_from_index,
    hamming_ball_kernel,
    index_from_coupon,
    materialize_ev_surface,
    ternary_convolve,
)


def test_base_three_coupon_index_round_trip_preserves_c_order():
    assert [coupon_from_index(index, 2) for index in range(9)] == [
        "11",
        "1X",
        "12",
        "X1",
        "XX",
        "X2",
        "21",
        "2X",
        "22",
    ]
    for index in range(3**4):
        assert index_from_coupon(coupon_from_index(index, 4)) == index


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: coupon_from_index(True, 2), "index must be an int"),
        (lambda: coupon_from_index(9, 2), "index must be in"),
        (lambda: coupon_from_index(0, 0), "event_count must be"),
        (lambda: index_from_coupon("1A"), "coupon outcomes"),
        (lambda: index_from_coupon(""), "at least one"),
    ],
)
def test_coupon_index_helpers_reject_invalid_domains(call, message):
    with pytest.raises(ValueError, match=message):
        call()


def test_hamming_kernel_counts_radius_two_ball():
    kernel = hamming_ball_kernel(event_count=4, minimum_hits=2)
    assert kernel.sum() == 1 + 4 * 2 + 6 * 4
    assert kernel.shape == (3**4,)
    assert kernel.dtype == np.float64


def test_hamming_kernel_uses_c_order_digits():
    kernel = hamming_ball_kernel(event_count=2, minimum_hits=1)
    np.testing.assert_array_equal(kernel, [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0])


def test_ternary_convolution_matches_direct_oriented_cyclic_convolution():
    left = np.arange(1, 10, dtype=np.float64)
    right = np.array([0.0, 2.0, 1.0, 4.0, 0.0, 3.0, 5.0, 7.0, 6.0])
    actual = ternary_convolve(left, right, event_count=2)
    expected = np.zeros(9)
    for left_index in range(9):
        for right_index in range(9):
            left_digits = divmod(left_index, 3)
            right_digits = divmod(right_index, 3)
            output_index = ((left_digits[0] + right_digits[0]) % 3) * 3 + (
                (left_digits[1] + right_digits[1]) % 3
            )
            expected[output_index] += left[left_index] * right[right_index]
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_ternary_convolution_preserves_legitimate_tiny_positive_values():
    left = np.zeros(9, dtype=np.float64)
    right = np.zeros(9, dtype=np.float64)
    left[0] = 1e-20
    right[0] = 1e-20

    actual = ternary_convolve(left, right, event_count=2)

    assert actual[0] > 0.0
    assert actual[0] == pytest.approx(1e-40, rel=1e-12, abs=0.0)


def test_ternary_convolution_rejects_material_negative_results():
    with pytest.raises(FloatingPointError, match="material negative"):
        ternary_convolve(
            np.array([1.0, -1.0, 0.0]),
            np.array([1.0, 0.0, 0.0]),
            event_count=1,
        )


def test_exact_crowd_tail_dp_preserves_all_tiny_positive_states():
    row = (0.999998, 0.000001, 0.000001)
    crowd = (row,) * 5

    tails = ternary_module._crowd_qualifying_probabilities(
        crowd,
        minimum_hits=5,
        chunk_size=17,
    )

    assert np.all(tails > 0.0)
    assert tails[-1] == pytest.approx(1e-30, rel=1e-12, abs=0.0)


def test_exact_crowd_tail_dp_preserves_supplied_nonmatch_mass_within_tolerance():
    crowd = (
        (0.4000000000004, 0.3500000000003, 0.2500000000002),
        (0.3000000000003, 0.4500000000004, 0.2500000000002),
        (0.5000000000005, 0.2000000000002, 0.3000000000002),
    )
    actual_index = 17
    actual = tuple(
        int(digit)
        for digit in np.unravel_index(actual_index, (3,) * len(crowd), order="C")
    )
    expected = sum(
        probability
        for probability, ticket in zip(
            joint_distribution(crowd),
            itertools.product(range(3), repeat=len(crowd)),
            strict=True,
        )
        if sum(left == right for left, right in zip(ticket, actual, strict=True)) >= 2
    )

    actual_tail = ternary_module._poisson_binomial_tails_for_indices(
        crowd,
        minimum_hits=2,
        actual_indices=np.array([actual_index], dtype=np.int64),
    )

    assert actual_tail[0] == pytest.approx(expected, rel=1e-14, abs=0.0)


def test_accumulation_materializes_and_releases_full_crowd_joint_before_tail_dp(
    monkeypatch,
):
    true = ((0.5, 0.3, 0.2),) * 3
    crowd = ((0.4, 0.35, 0.25),) * 3
    original_joint_distribution = ternary_module._joint_distribution
    original_crowd_tails = ternary_module._crowd_qualifying_probabilities
    crowd_joint_ref = None
    joint_matrices = []

    def track_joint_distribution(matrix):
        nonlocal crowd_joint_ref
        joint = original_joint_distribution(matrix)
        joint_matrices.append(matrix)
        if matrix == crowd:
            crowd_joint_ref = weakref.ref(joint)
        return joint

    def verify_crowd_released(*args, **kwargs):
        assert crowd_joint_ref is not None
        assert crowd_joint_ref() is None
        return original_crowd_tails(*args, **kwargs)

    monkeypatch.setattr(ternary_module, "_joint_distribution", track_joint_distribution)
    monkeypatch.setattr(
        ternary_module,
        "_crowd_qualifying_probabilities",
        verify_crowd_released,
    )

    surface = compute_ev_surface(
        true,
        crowd,
        1_000.0,
        {2: 10.0},
        30,
        2,
    )

    assert joint_matrices == [true, crowd]
    assert surface.crowd_mass == pytest.approx(
        joint_distribution(crowd).sum(),
        abs=1e-15,
    )


def test_selected_state_tail_dp_supports_fifteen_tiny_marginals():
    row = (0.999998, 0.000001, 0.000001)
    all_twos_index = 3**15 - 1

    tails = ternary_module._poisson_binomial_tails_for_indices(
        (row,) * 15,
        minimum_hits=15,
        actual_indices=np.array([all_twos_index], dtype=np.int64),
    )

    assert tails[0] > 0.0
    assert tails[0] == pytest.approx(1e-90, rel=1e-12, abs=0.0)


def test_exact_engine_handles_tiny_positive_marginals_on_full_small_space():
    row = (0.999998, 0.000001, 0.000001)
    probabilities = (row,) * 5

    surface = compute_ev_surface(
        probabilities,
        probabilities,
        100.0,
        {5: 10.0},
        10,
        5,
    )

    assert np.all(np.isfinite(surface.gross_ev))
    assert np.all(surface.gross_ev > 0.0)
    np.testing.assert_allclose(surface.gross_ev, 0.1, rtol=1e-10, atol=0.0)


@pytest.mark.parametrize("event_count", range(1, 5))
def test_arbitrary_fund_engine_matches_reference_oracle(event_count):
    rng = np.random.default_rng(800 + event_count)
    true = tuple(tuple(row) for row in rng.dirichlet([3.0, 2.0, 1.0], event_count))
    crowd = tuple(tuple(row) for row in rng.dirichlet([2.0, 3.0, 4.0], event_count))
    minimum_category = max(1, event_count - 2)
    funds = {
        category: float((event_count - category + 1) * 25)
        for category in range(minimum_category, event_count + 1)
    }

    exact = compute_ev_surface(
        true,
        crowd,
        10_000.0,
        funds,
        30,
        minimum_category,
    )
    reference = brute_force_gross_ev(
        true,
        crowd,
        10_000.0,
        30,
        funds,
        minimum_category,
    )

    assert np.allclose(exact.gross_ev, reference, rtol=1e-10, atol=1e-12)
    assert exact.event_count == event_count
    assert math.isclose(exact.probability_mass, 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert math.isclose(exact.crowd_mass, 1.0, rel_tol=0.0, abs_tol=1e-12)
    assert exact.minimum_denominator > 0


def test_progress_callback_is_ordered_and_has_exact_payload():
    payloads = []
    compute_ev_surface(
        ((0.5, 0.3, 0.2),) * 4,
        ((0.4, 0.35, 0.25),) * 4,
        1_000.0,
        {2: 80.0, 3: 40.0, 4: 20.0},
        30,
        2,
        progress_callback=payloads.append,
    )

    assert [payload["category"] for payload in payloads] == [2, 3, 4]
    assert all(set(payload) == {"phase", "category", "elapsed"} for payload in payloads)
    assert all(payload["phase"] == "category" for payload in payloads)
    assert [payload["elapsed"] for payload in payloads] == sorted(
        payload["elapsed"] for payload in payloads
    )


def test_callback_interruption_propagates_without_a_partial_surface():
    def interrupt(_payload):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        compute_ev_surface(
            ((0.5, 0.3, 0.2),) * 3,
            ((0.4, 0.35, 0.25),) * 3,
            1_000.0,
            {1: 80.0, 2: 40.0, 3: 20.0},
            30,
            1,
            progress_callback=interrupt,
        )


def test_materialize_surface_reuses_owned_component_arrays():
    components = EVComponents(
        possible_winnings_ev_per_ruble=np.array([0.1, 0.2, 0.3]),
        jackpot_ev_per_ruble=np.array([0.01, 0.02, 0.03]),
        event_count=1,
        probability_mass=1.0,
        crowd_mass=1.0,
        minimum_denominator=12.0,
    )

    surface = materialize_ev_surface(components, possible_winnings=180.0, jackpot=10.0)

    np.testing.assert_allclose(surface.gross_ev, [18.1, 36.2, 54.3])
    assert not surface.gross_ev.flags.writeable
    assert surface.probability_mass == components.probability_mass
    assert surface.crowd_mass == components.crowd_mass
    assert surface.minimum_denominator == components.minimum_denominator


def test_official_components_reject_non_production_event_count():
    ev_input = EVInput(
        drawing_id=1,
        drawing_number=2,
        true_probabilities=((0.5, 0.3, 0.2),) * 5,
        crowd_probabilities=((0.4, 0.35, 0.25),) * 5,
        pool_sum=1_000.0,
        jackpot=100.0,
        possible_winnings=500.0,
        probability_sources=("test",) * 5,
        fetched_at="2026-07-14T00:00:00Z",
    )

    with pytest.raises(ValueError, match="official categories require 9..15 events"):
        compute_ev_components(ev_input)


def test_official_components_success_path_without_full_state_allocation(monkeypatch):
    captured = {}

    def fake_accumulate_categories(**kwargs):
        captured.update(kwargs)
        return ternary_module._AccumulationResult(
            arrays=(np.array([0.5]), np.array([0.25])),
            probability_mass=1.0,
            crowd_mass=1.0,
            minimum_denominator=2.0,
            crowd_tail_samples=None,
        )

    monkeypatch.setattr(
        ternary_module,
        "_accumulate_categories",
        fake_accumulate_categories,
    )
    ev_input = EVInput(
        drawing_id=1,
        drawing_number=2,
        true_probabilities=((0.5, 0.3, 0.2),) * 9,
        crowd_probabilities=((0.4, 0.35, 0.25),) * 9,
        pool_sum=1_000.0,
        jackpot=100.0,
        possible_winnings=500.0,
        probability_sources=("test",) * 9,
        fetched_at="2026-07-14T00:00:00Z",
    )

    components = compute_ev_components(ev_input)

    np.testing.assert_array_equal(
        components.possible_winnings_ev_per_ruble,
        [0.5],
    )
    np.testing.assert_array_equal(components.jackpot_ev_per_ruble, [0.25])
    assert captured["coefficient_maps"] == ({9: 8 / 18}, {9: 0.0})
    assert captured["crowd_sample_indices"] is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"pool_sum": 0.0}, "pool_sum must be finite and positive"),
        ({"pool_sum": math.inf}, "pool_sum must be finite and positive"),
        ({"pool_sum": "invalid"}, "pool_sum must be finite and positive"),
        ({"stake": True}, "stake must be a positive int"),
        ({"minimum_category": 0}, "minimum_category must be a positive int"),
        ({"category_funds_by_hits": {4: 1.0}}, "category 4 must be in 1..3"),
        ({"category_funds_by_hits": {1: -1.0}}, "category funds"),
        ({"category_funds_by_hits": {1: None}}, "category funds"),
    ],
)
def test_arbitrary_fund_engine_validates_inputs(kwargs, message):
    arguments = {
        "true_probabilities": ((0.5, 0.3, 0.2),) * 3,
        "crowd_probabilities": ((0.4, 0.35, 0.25),) * 3,
        "pool_sum": 1_000.0,
        "category_funds_by_hits": {1: 10.0},
        "stake": 30,
        "minimum_category": 1,
    }
    arguments.update(kwargs)
    with pytest.raises(ValueError, match=message):
        compute_ev_surface(**arguments)


def test_engine_rejects_zero_category_denominator():
    with pytest.raises(ValueError, match="category 1 denominator"):
        compute_ev_surface(
            ((1.0, 0.0, 0.0),),
            ((1.0, 0.0, 0.0),),
            100.0,
            {1: 10.0},
            10,
            1,
        )
