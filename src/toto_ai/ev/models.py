"""Immutable domain models for the expected-value package engine."""

from dataclasses import dataclass
from typing import Literal

import numpy as np

ProbabilityMatrix = tuple[tuple[float, float, float], ...]
EVMode = Literal["research", "playable"]


def _immutable_array(value: np.ndarray) -> np.ndarray:
    array = np.array(value, copy=True)
    array.setflags(write=False)
    return array


def validate_config_bank(bank: int, stake: int) -> int:
    """Validate a bank without importing the prize helpers."""
    if type(stake) is not int or stake <= 0:
        raise ValueError("stake must be a positive int")
    if type(bank) is not int or bank <= 0:
        raise ValueError("bank must be a positive int")
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

    def __post_init__(self) -> None:
        validate_config_bank(self.bank, self.stake)

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "possible_winnings_ev_per_ruble",
            _immutable_array(self.possible_winnings_ev_per_ruble),
        )
        object.__setattr__(
            self,
            "jackpot_ev_per_ruble",
            _immutable_array(self.jackpot_ev_per_ruble),
        )


@dataclass(frozen=True)
class EVSurface:
    gross_ev: np.ndarray
    event_count: int
    probability_mass: float
    crowd_mass: float
    minimum_denominator: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "gross_ev", _immutable_array(self.gross_ev))


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
