from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing, TargetEvent
from toto_ai.external_odds.preparation import prepare_drawing
from toto_ai.external_odds.team_registry import backfill_accepted_matches

DEADLINE = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)
FETCHED_AT = DEADLINE - timedelta(minutes=30)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target(*, missing_pool_order: int | None = None, number: int = 4965):
    return TargetDrawing(
        drawing_id=12004,
        drawing_number=number,
        deadline=DEADLINE,
        fetched_at=FETCHED_AT,
        events=tuple(
            TargetEvent(
                drawing_id=12004,
                drawing_number=number,
                event_id=179163 + order,
                event_order=order,
                sport="football",
                championship="Test. Competition",
                starts_at=None,
                deadline=DEADLINE,
                home_team=f"Target Home {order}",
                away_team=f"Target Away {order}",
                home_team_en=None,
                away_team_en=None,
                bk_probabilities=(0.4, 0.3, 0.3),
                pool_probabilities=(
                    None if order == missing_pool_order else (0.35, 0.3, 0.35)
                ),
            )
            for order in range(15)
        ),
    )


def _candidates():
    return tuple(
        ProviderEvent(
            provider="api-sports",
            provider_event_id=f"fixture-{order}",
            sport="football",
            league="Competition",
            starts_at=DEADLINE + timedelta(hours=2),
            home_team=f"Provider Home {order}",
            away_team=f"Provider Away {order}",
            fetched_at=FETCHED_AT,
            payload_hash=f"hash-{order}",
            country="Test",
            provider_home_team_id=f"home-{order}",
            provider_away_team_id=f"away-{order}",
        )
        for order in range(13)
    )


def _seed(session_factory):
    assert backfill_accepted_matches(
        session_factory,
        [
            {
                "drawing_id": 12004,
                "target_event_id": 179163 + order,
                "provider_fixture_id": f"fixture-{order}",
                "sport": "football",
                "target_home": f"Target Home {order}",
                "target_away": f"Target Away {order}",
                "provider_home": f"Provider Home {order}",
                "provider_away": f"Provider Away {order}",
                "provider_home_team_id": f"home-{order}",
                "provider_away_team_id": f"away-{order}",
                "country": "Test",
                "league": "Competition",
                "reviewed": True,
            }
            for order in range(13)
        ],
    ) == 26


def test_thirteen_external_and_two_baseline_only_are_ready(session_factory):
    _seed(session_factory)
    result = prepare_drawing(
        _target(), _candidates(), session_factory=session_factory
    )

    assert result.status == "ready"
    assert result.mapped_count == 15
    assert result.external_coverage_count == 13
    assert result.baseline_only_event_orders == (13, 14)
    assert len(result.pins) == 15
    assert tuple(pin.event_order for pin in result.pins) == tuple(range(15))
    assert tuple(
        pin.effective_source_provider for pin in result.pins[13:]
    ) == ("totobrief-baseline", "totobrief-baseline")


def test_fourteen_complete_baseline_rows_cannot_publish(session_factory):
    _seed(session_factory)
    result = prepare_drawing(
        _target(missing_pool_order=14),
        _candidates(),
        session_factory=session_factory,
    )

    assert result.status == "unresolved"
    assert result.pins == ()


def test_conflicting_authoritative_drawing_identity_cannot_publish(session_factory):
    _seed(session_factory)
    prepare_drawing(_target(), _candidates(), session_factory=session_factory)

    with pytest.raises(ValueError, match="drawing number"):
        prepare_drawing(
            _target(number=4966),
            _candidates(),
            session_factory=session_factory,
        )
