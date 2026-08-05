import math

import numpy as np
import pytest

from toto_ai.ev import CROWD_JOINT_MODEL
from toto_ai.ev.models import (
    EVComponents,
    EVConfig,
    EVInput,
    EVPackage,
    EVSurface,
    RankedCoupon,
    validate_config_bank,
)
from toto_ai.ev.prize import (
    category_funds,
    normalize_triplet,
    smooth_crowd_matrix,
    validate_bank,
)


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


@pytest.mark.parametrize("stake", [True, 30.0, 0, -30])
def test_smooth_crowd_matrix_rejects_invalid_stake_domain(stake):
    with pytest.raises(ValueError, match="stake must be a positive int"):
        smooth_crowd_matrix(((0.2, 0.3, 0.5),), 3000.0, stake)


def test_ev_config_does_not_force_full_bank_use():
    config = EVConfig(bank=6000, stake=30, mode="playable", min_gross_ev=1.0)
    assert config.max_coupons == 200
    assert isinstance(config.max_coupons, int)


@pytest.mark.parametrize("bank", [0, -30, True, False, 6000.0, "6000"])
def test_ev_config_rejects_invalid_bank_at_construction(bank):
    with pytest.raises(ValueError):
        EVConfig(bank=bank)


@pytest.mark.parametrize("stake", [0, -30, True, False, 30.0, "30"])
def test_ev_config_rejects_invalid_stake_at_construction(stake):
    with pytest.raises(ValueError):
        EVConfig(bank=6000, stake=stake)


def test_ev_config_rejects_non_divisible_bank_at_construction():
    with pytest.raises(ValueError, match="divisible"):
        EVConfig(bank=5000, stake=30)


@pytest.mark.parametrize(
    ("bank", "stake"),
    [
        (0, 30),
        (-30, 30),
        (True, 30),
        (6000.0, 30),
        (6000, 0),
        (6000, -30),
        (6000, True),
        (6000, 30.0),
        (5000, 30),
    ],
)
def test_bank_validators_have_matching_domain_rules(bank, stake):
    for validator in (validate_config_bank, validate_bank):
        with pytest.raises(ValueError) as error:
            validator(bank, stake)
        assert str(error.value) in {
            "bank must be a positive int",
            "stake must be a positive int",
            "bank must be divisible by stake",
        }


def test_ev_arrays_are_defensive_copies_and_read_only():
    possible_winnings = np.array([1.0, 2.0])
    jackpot = np.array([3.0, 4.0])
    gross_ev = np.array([5.0, 6.0])
    components = EVComponents(possible_winnings, jackpot, 2, 1.0, 1.0, 0.5)
    surface = EVSurface(gross_ev, 2, 1.0, 1.0, 0.5)

    possible_winnings[0] = 99.0
    jackpot[0] = 99.0
    gross_ev[0] = 99.0

    np.testing.assert_array_equal(components.possible_winnings_ev_per_ruble, [1.0, 2.0])
    np.testing.assert_array_equal(components.jackpot_ev_per_ruble, [3.0, 4.0])
    np.testing.assert_array_equal(surface.gross_ev, [5.0, 6.0])

    for array in (
        components.possible_winnings_ev_per_ruble,
        components.jackpot_ev_per_ruble,
        surface.gross_ev,
    ):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array[0] = 100.0
        with pytest.raises(ValueError):
            array.setflags(write=True)


def test_ev_input_deep_normalizes_collection_inputs():
    true_probabilities = [[0.2, 0.3, 0.5]]
    crowd_probabilities = [[0.4, 0.4, 0.2]]
    probability_sources = ["bk", "pool"]
    ev_input = EVInput(
        drawing_id=1,
        drawing_number=None,
        true_probabilities=true_probabilities,
        crowd_probabilities=crowd_probabilities,
        pool_sum=3000.0,
        jackpot=1000.0,
        possible_winnings=500.0,
        probability_sources=probability_sources,
        fetched_at="2026-07-14T00:00:00Z",
    )

    true_probabilities[0][0] = 99.0
    true_probabilities.append([0.1, 0.2, 0.7])
    crowd_probabilities[0][0] = 99.0
    probability_sources[0] = "changed"
    probability_sources.append("new")

    assert ev_input.true_probabilities == ((0.2, 0.3, 0.5),)
    assert ev_input.crowd_probabilities == ((0.4, 0.4, 0.2),)
    assert ev_input.probability_sources == ("bk", "pool")


@pytest.mark.parametrize("field", ["true_probabilities", "crowd_probabilities"])
def test_ev_input_rejects_probability_rows_without_three_outcomes(field):
    values = {
        "true_probabilities": ((0.2, 0.3, 0.5),),
        "crowd_probabilities": ((0.2, 0.3, 0.5),),
    }
    values[field] = ((0.2, 0.8),)

    with pytest.raises(ValueError, match="exactly three values"):
        EVInput(
            drawing_id=1,
            drawing_number=None,
            true_probabilities=values["true_probabilities"],
            crowd_probabilities=values["crowd_probabilities"],
            pool_sum=3000.0,
            jackpot=1000.0,
            possible_winnings=500.0,
            probability_sources=("bk",),
            fetched_at="2026-07-14T00:00:00Z",
        )


def test_ev_package_deep_normalizes_collection_inputs():
    coupons = [RankedCoupon(1, "111111111111111", 1.2, 0.2)]
    derived_brief = ["1", "X"]
    package = EVPackage(
        decision="PLAY",
        coupons=coupons,
        cost=30,
        unused_bank=0,
        expected_payout=36.0,
        modeled_roi=0.2,
        derived_brief=derived_brief,
    )

    coupons.clear()
    derived_brief[0] = "2"
    derived_brief.append("X")

    assert package.coupons == (RankedCoupon(1, "111111111111111", 1.2, 0.2),)
    assert package.derived_brief == ("1", "X")


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_category_funds_reject_non_finite_or_negative_inputs(value):
    with pytest.raises(ValueError):
        category_funds(value, 100.0)
    with pytest.raises(ValueError):
        category_funds(100.0, value)


@pytest.mark.parametrize(
    "values",
    [
        (1.0, 2.0),
        (1.0, 2.0, 3.0, 4.0),
        (0.0, 0.0, 0.0),
        (-1.0, 1.0, 1.0),
        (float("nan"), 1.0, 1.0),
        (float("inf"), 1.0, 1.0),
    ],
)
def test_normalize_triplet_rejects_invalid_or_zero_values(values):
    with pytest.raises(ValueError):
        normalize_triplet(values)


def test_crowd_joint_model_contract_is_stable():
    assert CROWD_JOINT_MODEL == "independent_event_marginals"
