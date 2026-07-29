from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base, DrawingEventPin, DrawingPinSetItem
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import (
    ProviderEvent,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.preparation import prepare_drawing
from toto_ai.external_odds.team_registry import backfill_accepted_matches
from toto_ai.external_odds.team_resolution import ResolutionContext

UTC = timezone.utc
DEADLINE = datetime(2026, 7, 29, 16, tzinfo=UTC)
EVALUATED_AT = DEADLINE - timedelta(hours=1)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target() -> TargetDrawing:
    events = []
    for order in range(15):
        iceland = order == 14
        events.append(
            TargetEvent(
                drawing_id=11988,
                drawing_number=4959,
                event_id=5000 + order,
                event_order=order,
                sport="football",
                championship=(
                    "Исландия. 3-й дивизион"
                    if iceland
                    else "США. National League"
                ),
                starts_at=None,
                deadline=DEADLINE,
                home_team=(
                    "КВ Вестурбеяр" if iceland else f"Target Home {order}"
                ),
                away_team=(
                    "Рейнир Сандгерди" if iceland else f"Target Away {order}"
                ),
                home_team_en=None,
                away_team_en=None,
                bk_probabilities=(0.4, 0.3, 0.3),
            )
        )
    return TargetDrawing(
        drawing_id=11988,
        drawing_number=4959,
        deadline=DEADLINE,
        fetched_at=EVALUATED_AT,
        events=tuple(events),
    )


def _candidates() -> tuple[ProviderEvent, ...]:
    regular = tuple(
        ProviderEvent(
            provider="api-sports",
            provider_event_id=f"fixture-{order}",
            sport="football",
            league="National League",
            starts_at=DEADLINE + timedelta(hours=2),
            home_team=f"Provider Home {order}",
            away_team=f"Provider Away {order}",
            fetched_at=EVALUATED_AT,
            payload_hash=f"hash-{order}",
            country="United States",
            provider_home_team_id=f"home-{order}",
            provider_away_team_id=f"away-{order}",
        )
        for order in range(14)
    )
    observed_iceland = ProviderEvent(
        provider="api-sports",
        provider_event_id="iceland-top-flight",
        sport="football",
        league="Úrvalsdeild",
        starts_at=DEADLINE + timedelta(hours=2),
        home_team="Valur",
        away_team="Vikingur Reykjavik",
        fetched_at=EVALUATED_AT,
        payload_hash="hash-iceland",
        country="Iceland",
        provider_home_team_id="valur",
        provider_away_team_id="vikingur",
    )
    return regular + (observed_iceland,)


def _seed(session_factory) -> None:
    rows = [
        {
            "drawing_id": 11988,
            "target_event_id": 5000 + order,
            "provider_fixture_id": f"fixture-{order}",
            "sport": "football",
            "target_home": f"Target Home {order}",
            "target_away": f"Target Away {order}",
            "provider_home": f"Provider Home {order}",
            "provider_away": f"Provider Away {order}",
            "provider_home_team_id": f"home-{order}",
            "provider_away_team_id": f"away-{order}",
            "country": "USA",
            "league": "National League",
            "reviewed": True,
        }
        for order in range(14)
    ]
    assert backfill_accepted_matches(session_factory, rows) == 28


def _catalog(tmp_path: Path, target: TargetDrawing, *, one_source=False) -> Path:
    claims = []
    for name, role in (
        ("official.json", "official"),
        ("independent.json", "independent"),
    ):
        snapshot = tmp_path / name
        snapshot.write_text('{"scheduled":true}', encoding="utf-8")
        claims.append(
            {
                "source_name": name.removesuffix(".json"),
                "role": role,
                "source_url": f"https://example.test/{name}",
                "snapshot_path": name,
                "snapshot_sha256": hashlib.sha256(
                    snapshot.read_bytes()
                ).hexdigest(),
                "captured_at": "2026-07-29T14:30:00Z",
                "home_name": "KV Vesturbaer",
                "away_name": "Reynir Sandgerdi",
                "competition": "Iceland 3. Deild",
                "sport": "football",
                "gender_age_class": "men-senior",
                "starts_at": "2026-07-29T18:00:00Z",
                "status": "scheduled",
                "native_fixture_id": None,
                "native_home_team_id": None,
                "native_away_team_id": None,
            }
        )
    payload = {
        "schema_version": 1,
        "catalog_id": "generic-reviewed",
        "generated_at": "2026-07-29T14:40:00Z",
        "records": [
            {
                "evidence_id": "reviewed-evidence-1",
                "drawing_id": target.drawing_id,
                "drawing_number": target.drawing_number,
                "target_fingerprint": target_fingerprint(
                    target.drawing_id,
                    target.drawing_number,
                    target.deadline,
                    target.events,
                ),
                "event_order": 14,
                "target_event_id": 5014,
                "reviewer": "operator",
                "reviewed_at": "2026-07-29T14:40:00Z",
                "claims": claims[:1] if one_source else claims,
            }
        ],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _contexts(target: TargetDrawing) -> dict[int, ResolutionContext]:
    return {
        event.event_order: ResolutionContext(
            provider="api-sports",
            country=("Iceland" if event.event_order == 14 else "USA"),
            league=(
                "3-й дивизион"
                if event.event_order == 14
                else "National League"
            ),
            sport="football",
            competition=event.championship,
            derived=True,
        )
        for event in target.events
    }


def test_preparation_atomically_publishes_14_api_plus_one_reviewed(
    session_factory, tmp_path: Path
) -> None:
    target = _target()
    _seed(session_factory)

    result = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        event_contexts=_contexts(target),
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": "2026-07-29",
                "status": "success",
                "reason": None,
            },
        ),
        reviewed_schedule_catalog=_catalog(tmp_path, target),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "ready"
    assert result.mapped_count == 15
    assert result.eligibility.status == "playable"
    assert len(result.pins) == 15
    assert result.pins[14].effective_source_provider == "reviewed-schedule"
    assert result.pins[14].provider_fixture_id is None
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 15
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0


def test_invalid_reviewed_evidence_keeps_zero_authoritative_pins(
    session_factory, tmp_path: Path
) -> None:
    target = _target()
    _seed(session_factory)

    result = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        event_contexts=_contexts(target),
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": "2026-07-29",
                "status": "success",
                "reason": None,
            },
        ),
        reviewed_schedule_catalog=_catalog(
            tmp_path, target, one_source=True
        ),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "unresolved"
    assert result.pins == ()
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 0
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0


def test_reviewed_fallback_cannot_mask_provider_date_failure(
    session_factory, tmp_path: Path
) -> None:
    target = _target()
    _seed(session_factory)

    result = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        event_contexts=_contexts(target),
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": "2026-07-29",
                "status": "failed",
                "reason": "quota exhausted",
            },
        ),
        reviewed_schedule_catalog=_catalog(tmp_path, target),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "unresolved"
    assert result.pins == ()
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 0


def test_final_revalidation_is_per_pin_and_never_fetches_reviewed_market(
    session_factory, tmp_path: Path
) -> None:
    target = _target()
    _seed(session_factory)
    catalog = _catalog(tmp_path, target)
    prepared = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        event_contexts=_contexts(target),
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": "2026-07-29",
                "status": "success",
                "reason": None,
            },
        ),
        reviewed_schedule_catalog=catalog,
        evaluated_at=EVALUATED_AT,
    )

    class Provider:
        provider_name = "api-sports"
        quota_state = QuotaState(None, None, None, None)

        def __init__(self):
            self.market_ids = []

        def fetch_schedule(self, sport, dates):
            return _candidates()

        def fetch_event_markets(self, sport, provider_event_id):
            self.market_ids.append(provider_event_id)
            return ()

    provider = Provider()
    snapshot = build_external_collection(
        target,
        provider,
        {},
        prepared_pins=prepared.pins,
        reviewed_schedule_catalog=str(catalog),
        now=lambda: EVALUATED_AT,
    )

    assert snapshot.pinned_revalidation is not None
    assert snapshot.pinned_revalidation.ready_for_play is True
    assert snapshot.pinned_revalidation.matched_count == 15
    assert len(provider.market_ids) == 14
    assert None not in provider.market_ids
    assert snapshot.events[14].probability_source == "totobrief_bk_fallback"
    assert "reviewed schedule-only" in (snapshot.events[14].fallback_reason or "")


def test_final_revalidation_fails_closed_on_catalog_toctou(
    session_factory, tmp_path: Path
) -> None:
    target = _target()
    _seed(session_factory)
    catalog = _catalog(tmp_path, target)
    prepared = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        event_contexts=_contexts(target),
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": "2026-07-29",
                "status": "success",
                "reason": None,
            },
        ),
        reviewed_schedule_catalog=catalog,
        evaluated_at=EVALUATED_AT,
    )
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    payload["catalog_id"] = "changed-after-preflight"
    catalog.write_text(json.dumps(payload), encoding="utf-8")

    class Provider:
        provider_name = "api-sports"
        quota_state = QuotaState(None, None, None, None)

        def fetch_schedule(self, sport, dates):
            return _candidates()

        def fetch_event_markets(self, sport, provider_event_id):
            return ()

    snapshot = build_external_collection(
        target,
        Provider(),
        {},
        prepared_pins=prepared.pins,
        reviewed_schedule_catalog=str(catalog),
        now=lambda: EVALUATED_AT,
    )

    assert snapshot.pinned_revalidation is not None
    assert snapshot.pinned_revalidation.ready_for_play is False
    assert snapshot.pinned_revalidation.matched_count == 14
    assert snapshot.pinned_revalidation.provider_failure_event_orders == (14,)
