from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from toto_ai.external_odds.domain import OutcomeTriplet, ProviderMarket, TargetEvent

FOOTBALL_THREE_WAY = frozenset({"match winner", "1x2", "home draw away"})
HOCKEY_REGULATION_THREE_WAY = frozenset(
    {"home draw away", "match winner regulation time", "1x2 regulation time"}
)
MAXIMUM_ODDS_AGE = timedelta(hours=36)


@dataclass(frozen=True)
class BookmakerAssessment:
    market: ProviderMarket
    eligible: bool
    probabilities: OutcomeTriplet | None
    rejection_reason: str | None

    def __post_init__(self) -> None:
        if self.eligible:
            if self.probabilities is None or self.rejection_reason is not None:
                raise ValueError("eligible assessments require probabilities only")
            _require_probability_triplet(self.probabilities)
            return
        if self.probabilities is not None or self.rejection_reason is None:
            raise ValueError("rejected assessments require a rejection reason only")


@dataclass(frozen=True)
class ConsensusResult:
    probabilities: OutcomeTriplet | None
    eligible_bookmaker_count: int
    assessments: tuple[BookmakerAssessment, ...]
    fallback_reason: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.eligible_bookmaker_count, int)
            or isinstance(self.eligible_bookmaker_count, bool)
            or self.eligible_bookmaker_count < 0
        ):
            raise ValueError("eligible_bookmaker_count must be a non-negative integer")
        if self.probabilities is None:
            if self.fallback_reason is None:
                raise ValueError("missing probabilities require a fallback reason")
            return
        if self.fallback_reason is not None:
            raise ValueError("eligible consensus cannot include a fallback reason")
        _require_probability_triplet(self.probabilities)


def assess_market(
    target: TargetEvent,
    market: ProviderMarket,
    fetched_at: datetime,
    *,
    maximum_age: timedelta = MAXIMUM_ODDS_AGE,
    duplicate_keys: frozenset[tuple[str, str]] = frozenset(),
) -> BookmakerAssessment:
    _require_utc_datetime("fetched_at", fetched_at)
    _require_maximum_age(maximum_age)

    market_key = _market_key(target.sport, market.market_name)
    if market_key is None:
        return _rejected(
            market,
            "not regulation three-way"
            if target.sport == "hockey"
            else "not full-time three-way",
        )

    if (market.bookmaker_id, market_key) in duplicate_keys:
        return _rejected(market, "duplicate bookmaker market")

    prices = (market.home_price, market.draw_price, market.away_price)
    if any(price is None for price in prices):
        return _rejected(market, "missing outcomes")

    resolved_prices = tuple(float(price) for price in prices if price is not None)
    if any(not math.isfinite(price) or price <= 1.0 for price in resolved_prices):
        return _rejected(market, "invalid prices")

    if (
        market.updated_at > fetched_at
        or market.fetched_at > fetched_at
        or market.updated_at > market.fetched_at
    ):
        return _rejected(market, "future update timestamp")

    if fetched_at - market.updated_at > maximum_age:
        return _rejected(market, "stale prices")

    return BookmakerAssessment(
        market=market,
        eligible=True,
        probabilities=devig_decimal_prices(
            (
                resolved_prices[0],
                resolved_prices[1],
                resolved_prices[2],
            )
        ),
        rejection_reason=None,
    )


def devig_decimal_prices(prices: tuple[float, float, float]) -> OutcomeTriplet:
    if any(not math.isfinite(price) or price <= 1.0 for price in prices):
        raise ValueError("prices must be finite and greater than one")
    inverse = tuple(1.0 / price for price in prices)
    total = math.fsum(inverse)
    return _normalize_triplet(inverse, total)


def build_consensus(
    target: TargetEvent,
    markets: Sequence[ProviderMarket],
    fetched_at: datetime,
    *,
    minimum_bookmakers: int = 3,
    maximum_age: timedelta = MAXIMUM_ODDS_AGE,
) -> ConsensusResult:
    _require_utc_datetime("fetched_at", fetched_at)
    _require_maximum_age(maximum_age)
    if minimum_bookmakers < 1:
        raise ValueError("minimum_bookmakers must be positive")

    duplicate_keys = _duplicate_market_keys(target, markets)
    assessments = tuple(
        assess_market(
            target,
            market,
            fetched_at,
            maximum_age=maximum_age,
            duplicate_keys=duplicate_keys,
        )
        for market in markets
    )
    eligible = tuple(item for item in assessments if item.eligible)
    if len(eligible) < minimum_bookmakers:
        return ConsensusResult(
            probabilities=None,
            eligible_bookmaker_count=len(eligible),
            assessments=assessments,
            fallback_reason=f"fewer than {minimum_bookmakers} eligible bookmakers",
        )

    medians = tuple(
        statistics.median(item.probabilities[index] for item in eligible)
        for index in range(3)
    )
    probabilities = _normalize_triplet(medians, math.fsum(medians))
    return ConsensusResult(
        probabilities=probabilities,
        eligible_bookmaker_count=len(eligible),
        assessments=assessments,
        fallback_reason=None,
    )


def _duplicate_market_keys(
    target: TargetEvent,
    markets: Sequence[ProviderMarket],
) -> frozenset[tuple[str, str]]:
    counts = Counter[tuple[str, str]]()
    for market in markets:
        market_key = _market_key(target.sport, market.market_name)
        if market_key is None:
            continue
        counts[(market.bookmaker_id, market_key)] += 1
    return frozenset(key for key, count in counts.items() if count > 1)


def _market_key(sport: str, market_name: str) -> str | None:
    normalized_name = _normalize_market_name(market_name)
    if sport == "football":
        if normalized_name in FOOTBALL_THREE_WAY:
            return "football_three_way"
        return None
    if sport == "hockey":
        if normalized_name in HOCKEY_REGULATION_THREE_WAY:
            return "hockey_regulation_three_way"
        return None
    return None


def _normalize_market_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    collapsed = " ".join(normalized.split())
    if not collapsed:
        raise ValueError("market name must be non-empty")
    return collapsed


def _normalize_triplet(
    values: tuple[float, float, float],
    total: float,
) -> OutcomeTriplet:
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("triplet total must be finite and positive")
    return (
        values[0] / total,
        values[1] / total,
        values[2] / total,
    )


def _rejected(market: ProviderMarket, reason: str) -> BookmakerAssessment:
    return BookmakerAssessment(
        market=market,
        eligible=False,
        probabilities=None,
        rejection_reason=reason,
    )


def _require_probability_triplet(value: OutcomeTriplet) -> None:
    if not math.isclose(math.fsum(value), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("probabilities must sum to one")
    if any(not math.isfinite(item) or item <= 0.0 for item in value):
        raise ValueError("probabilities must be finite and positive")


def _require_utc_datetime(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")


def _require_maximum_age(value: timedelta) -> None:
    if not isinstance(value, timedelta) or value < timedelta(0):
        raise ValueError("maximum_age must be a non-negative timedelta")
