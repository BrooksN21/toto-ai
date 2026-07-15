from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.external_odds.domain import ProviderMarket, TargetEvent


def consensus_module():
    return importlib.import_module("toto_ai.external_odds.consensus")


def aware_now() -> datetime:
    return datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def football_target() -> TargetEvent:
    now = aware_now()
    return TargetEvent(
        drawing_id=9000,
        drawing_number=5000,
        event_id=100,
        event_order=0,
        sport="football",
        championship="Premier League",
        starts_at=now + timedelta(hours=8),
        deadline=now + timedelta(hours=7, minutes=55),
        home_team="Home FC",
        away_team="Away FC",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.5, 0.25, 0.25),
    )


@pytest.fixture
def hockey_target() -> TargetEvent:
    now = aware_now()
    return TargetEvent(
        drawing_id=9000,
        drawing_number=5000,
        event_id=101,
        event_order=1,
        sport="hockey",
        championship="KHL",
        starts_at=now + timedelta(hours=9),
        deadline=now + timedelta(hours=8, minutes=55),
        home_team="СКА",
        away_team="ЦСКА",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.45, 0.22, 0.33),
    )


def provider_market(
    *,
    bookmaker_id: str = "book-1",
    name: str = "Match Winner",
    home_price: float | None = 2.0,
    draw_price: float | None = 4.0,
    away_price: float | None = 4.0,
    updated_at: datetime | None = None,
) -> ProviderMarket:
    return ProviderMarket(
        provider="api-sports",
        provider_event_id="42",
        bookmaker_id=bookmaker_id,
        market_name=name,
        updated_at=updated_at or (aware_now() - timedelta(hours=1)),
        fetched_at=aware_now(),
        payload_hash=f"hash-{bookmaker_id}-{name}",
        home_price=home_price,
        draw_price=draw_price,
        away_price=away_price,
    )


def three_valid_markets() -> tuple[ProviderMarket, ...]:
    return (
        provider_market(
            bookmaker_id="book-1",
            home_price=2.0,
            draw_price=4.0,
            away_price=4.0,
        ),
        provider_market(
            bookmaker_id="book-2",
            home_price=4.0,
            draw_price=2.0,
            away_price=4.0,
        ),
        provider_market(
            bookmaker_id="book-3",
            home_price=4.0,
            draw_price=4.0,
            away_price=2.0,
        ),
    )


def two_valid_markets() -> tuple[ProviderMarket, ...]:
    return three_valid_markets()[:2]


def test_devig_matches_hand_calculation():
    result = consensus_module().devig_decimal_prices((2.0, 4.0, 4.0))

    assert result == pytest.approx((0.5, 0.25, 0.25))


def test_hockey_two_way_moneyline_is_rejected(hockey_target: TargetEvent):
    result = consensus_module().assess_market(
        hockey_target,
        provider_market(name="Home/Away", draw_price=None),
        fetched_at=aware_now(),
    )

    assert result.eligible is False
    assert result.rejection_reason == "not regulation three-way"


def test_allowed_market_with_missing_outcome_is_rejected(
    football_target: TargetEvent,
):
    result = consensus_module().assess_market(
        football_target,
        provider_market(draw_price=None),
        fetched_at=aware_now(),
    )

    assert result.eligible is False
    assert result.rejection_reason == "missing outcomes"


def test_market_with_price_not_above_one_is_rejected(football_target: TargetEvent):
    result = consensus_module().assess_market(
        football_target,
        provider_market(home_price=1.0),
        fetched_at=aware_now(),
    )

    assert result.eligible is False
    assert result.rejection_reason == "invalid prices"


def test_future_and_stale_market_timestamps_are_rejected(football_target: TargetEvent):
    future = consensus_module().assess_market(
        football_target,
        provider_market(updated_at=aware_now() + timedelta(seconds=1)),
        fetched_at=aware_now(),
    )
    stale = consensus_module().assess_market(
        football_target,
        provider_market(updated_at=aware_now() - timedelta(hours=36, seconds=1)),
        fetched_at=aware_now(),
    )

    assert future.eligible is False
    assert future.rejection_reason == "future update timestamp"
    assert stale.eligible is False
    assert stale.rejection_reason == "stale prices"


def test_duplicate_bookmaker_market_records_are_rejected(
    football_target: TargetEvent,
):
    result = consensus_module().build_consensus(
        football_target,
        (
            provider_market(bookmaker_id="book-1", name="Match Winner"),
            provider_market(bookmaker_id="book-1", name="1X2"),
            provider_market(bookmaker_id="book-2", name="1X2"),
            provider_market(bookmaker_id="book-3", name="Home/Draw/Away"),
        ),
        aware_now(),
    )

    assert result.eligible_bookmaker_count == 2
    assert result.fallback_reason == "fewer than 3 eligible bookmakers"
    assert result.assessments[0].rejection_reason == "duplicate bookmaker market"
    assert result.assessments[1].rejection_reason == "duplicate bookmaker market"


def test_three_book_median_consensus_is_normalized(football_target: TargetEvent):
    result = consensus_module().build_consensus(
        football_target,
        three_valid_markets(),
        aware_now(),
    )

    assert result.eligible_bookmaker_count == 3
    assert result.probabilities == pytest.approx((1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0))
    assert sum(result.probabilities) == pytest.approx(1.0)
    assert result.fallback_reason is None


def test_consensus_devigs_each_book_before_component_median(
    football_target: TargetEvent,
):
    raw_implied_probabilities = (
        (0.70, 0.25, 0.15),
        (0.55, 0.40, 0.25),
        (0.45, 0.20, 0.40),
    )
    assert tuple(map(sum, raw_implied_probabilities)) == pytest.approx(
        (1.10, 1.20, 1.05)
    )
    markets = tuple(
        provider_market(
            bookmaker_id=f"book-{index}",
            home_price=1.0 / implied[0],
            draw_price=1.0 / implied[1],
            away_price=1.0 / implied[2],
        )
        for index, implied in enumerate(raw_implied_probabilities, start=1)
    )

    result = consensus_module().build_consensus(
        football_target,
        markets,
        aware_now(),
    )

    expected_devigged = (
        (7.0 / 11.0, 5.0 / 22.0, 3.0 / 22.0),
        (11.0 / 24.0, 1.0 / 3.0, 5.0 / 24.0),
        (3.0 / 7.0, 4.0 / 21.0, 8.0 / 21.0),
    )
    for assessment, expected in zip(
        result.assessments,
        expected_devigged,
        strict=True,
    ):
        assert assessment.probabilities == pytest.approx(expected)

    per_book_devig_then_median = (121.0 / 236.0, 15.0 / 59.0, 55.0 / 236.0)
    raw_inverse_median_then_normalize = (11.0 / 21.0, 5.0 / 21.0, 5.0 / 21.0)
    assert result.probabilities == pytest.approx(per_book_devig_then_median)
    assert result.probabilities != pytest.approx(raw_inverse_median_then_normalize)


def test_hockey_regulation_three_way_builds_consensus(hockey_target: TargetEvent):
    markets = tuple(
        provider_market(
            bookmaker_id=f"book-{index}",
            name="Match Winner - Regulation Time",
        )
        for index in range(1, 4)
    )

    result = consensus_module().build_consensus(
        hockey_target,
        markets,
        aware_now(),
    )

    assert result.probabilities == pytest.approx((0.5, 0.25, 0.25))
    assert result.eligible_bookmaker_count == 3
    assert all(assessment.eligible for assessment in result.assessments)
    assert result.fallback_reason is None


def test_two_books_produce_explicit_fallback(football_target: TargetEvent):
    result = consensus_module().build_consensus(
        football_target,
        two_valid_markets(),
        aware_now(),
    )

    assert result.probabilities is None
    assert result.fallback_reason == "fewer than 3 eligible bookmakers"
