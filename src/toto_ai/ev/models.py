"""Immutable domain models for the expected-value package engine."""

from dataclasses import dataclass
from typing import Literal

import numpy as np

ProbabilityMatrix = tuple[tuple[float, float, float], ...]
EVMode = Literal["research", "playable"]


def validate_config_bank(bank: int, stake: int) -> int:
    """Validate a bank without importing the prize helpers."""
    if stake <= 0:
        raise ValueError("stake must be positive")
    if bank <= 0:
        raise ValueError("bank must be positive")
    if bank % stake:
        raise ValueError("bank must be divisible by stake")
    return bank // stake


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
