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
