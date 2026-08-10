import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import Base, DrawingPreparation, TeamRegistryReview
from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import (
    ProviderEvent,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.matching import load_aliases, normalize_team_name
from toto_ai.external_odds.preparation import load_local_schedule, prepare_drawing
from toto_ai.external_odds.team_registry import (
    load_drawing_pins,
    seed_reviewed_alias_config,
)

pytestmark = [pytest.mark.heavy, pytest.mark.research]

TARGET_PAIRS = (
    ("Арарат-Армения", "Шамрок Роверс"),
    ("АГФ Орхус", "Лех Познань"),
    ("Тун", "Динамо Загреб"),
    ("Клаксвик", "Кауно Жальгирис"),
    ("Викингур Рейкьявик", "Хапоэль Беэр-Шева"),
    ("Флориана", "Дрита"),
    ("Атлетико Минейро", "Байя"),
    ("Аваи", "Америка Минейро"),
    ("Гремио Новоризонтино", "Крициума"),
    ("КяПа", "Клуби 04"),
    ("Фалкенберг", "Хельсингборг"),
    ("Росс Каунти", "ФК Данди"),
    ("Инвернесс", "Сент-Джонстон"),
    ("Либертад Лоха", "Дельфин"),
    ("Насиональ Монтевидео", "Тигре"),
)

CHAMPIONSHIPS = (
    *("Европа. Лига Чемпионов УЕФА. Квалификация",) * 5,
    "Европа. Лига конференций УЕФА. Квалификация",
    "Бразилия. Серия A",
    "Бразилия. Серия B",
    "Бразилия. Серия B",
    "Финляндия. 1-й дивизион",
    "Швеция. Суперэттан",
    "Шотландия. Кубок Лиги",
    "Шотландия. Кубок Лиги",
    "Эквадор. Серия A",
    "Южная Америка. Южноамериканский Кубок",
)

EXPECTED_PROVIDER_IDS = (
    "1589415",
    "1556501",
    "1556504",
    "1591934",
    "1589420",
    "1589428",
    "1492290",
    "1520781",
    "1520787",
    "1504266",
    "1497625",
    "1548164",
    "1548158",
    "1519419",
    "1547777",
)

REVIEWED_ALIASES = {
    "Атлетико Минейро": "Atletico-MG",
    "Байя": "Bahia",
    "Росс Каунти": "Ross County",
    "ФК Данди": "Dundee",
    "Насиональ Монтевидео": "Club Nacional",
    "Тигре": "Tigre",
}

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "drawing_4951_api_sports_schedule.json"
)


def _provider_events() -> tuple[ProviderEvent, ...]:
    return load_local_schedule(_FIXTURE_PATH)


def _target_drawing() -> TargetDrawing:
    deadline = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)
    targets = tuple(
        TargetEvent(
            drawing_id=11968,
            drawing_number=4951,
            event_id=32851 + order,
            event_order=order,
            sport="football",
            championship=CHAMPIONSHIPS[order],
            starts_at=None,
            deadline=deadline,
            home_team=home,
            away_team=away,
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.4, 0.3, 0.3),
        )
        for order, (home, away) in enumerate(TARGET_PAIRS)
    )
    return TargetDrawing(
        drawing_id=11968,
        drawing_number=4951,
        deadline=deadline,
        fetched_at=datetime(2026, 7, 21, 10, 43, tzinfo=timezone.utc),
        events=targets,
    )


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_prepare_real_drawing_4951_pins_all_targets_from_local_cache():
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["drawing_number"] == 4951
    candidates = load_local_schedule(_FIXTURE_PATH)
    session_factory = _session_factory()
    seed_reviewed_alias_config(
        session_factory, "data/external-odds/team-aliases.json"
    )

    result = prepare_drawing(
        _target_drawing(), candidates, session_factory=session_factory
    )

    assert result.status == "ready"
    assert result.mapped_count == 15
    assert result.unresolved_event_orders == ()
    assert tuple(pin.provider_fixture_id for pin in result.pins) == (
        EXPECTED_PROVIDER_IDS
    )
    assert result.pins[6].provider_fixture_id == "1492290"
    assert result.pins[11].provider_fixture_id == "1548164"
    assert result.pins[14].provider_fixture_id == "1547777"
    with session_factory() as session:
        assert session.query(TeamRegistryReview).count() == 0
        assert session.query(DrawingPreparation).one().mapped_count == 15


def test_drawing_4951_per_drawing_aliases_are_deliberately_absent():
    aliases = load_aliases("data/external-odds/team-aliases.json")
    assert all(
        normalize_team_name(source) not in aliases for source in REVIEWED_ALIASES
    )


def test_prepare_drawing_4951_is_idempotent():
    session_factory = _session_factory()
    seed_reviewed_alias_config(
        session_factory, "data/external-odds/team-aliases.json"
    )
    first = prepare_drawing(
        _target_drawing(), _provider_events(), session_factory=session_factory
    )
    second = prepare_drawing(
        _target_drawing(), _provider_events(), session_factory=session_factory
    )
    assert tuple(pin.pin_hash for pin in second.pins) == tuple(
        pin.pin_hash for pin in first.pins
    )


def test_ready_preparation_rejects_changed_provider_identity():
    session_factory = _session_factory()
    seed_reviewed_alias_config(
        session_factory, "data/external-odds/team-aliases.json"
    )
    target = _target_drawing()
    candidates = _provider_events()
    prepare_drawing(target, candidates, session_factory=session_factory)
    changed = tuple(
        replace(event, provider_home_team_id="changed-team")
        if event.provider_event_id == EXPECTED_PROVIDER_IDS[0]
        else event
        for event in candidates
    )

    with pytest.raises(ValueError, match="conflicts with changed provider data"):
        prepare_drawing(target, changed, session_factory=session_factory)


def test_collection_uses_pins_despite_display_changes_and_rejects_stale_target():
    session_factory = _session_factory()
    seed_reviewed_alias_config(
        session_factory, "data/external-odds/team-aliases.json"
    )
    target = _target_drawing()
    prepared = prepare_drawing(
        target, _provider_events(), session_factory=session_factory
    )

    class ChangedDisplayProvider:
        provider_name = "api-sports"
        quota_state = QuotaState(100, 100, 10, 10)
        requests_made = 0
        cache_hits = 0

        def fetch_schedule(self, sport, dates):
            self.requests_made += 1
            requested = set(dates)
            return tuple(
                replace(
                    event,
                    home_team=f"changed home {event.provider_event_id}",
                    away_team=f"changed away {event.provider_event_id}",
                )
                for event in _provider_events()
                if event.starts_at.date() in requested
            )

        def fetch_event_markets(self, sport, provider_event_id):
            self.requests_made += 1
            return ()

    snapshot = build_external_collection(
        target,
        ChangedDisplayProvider(),
        aliases={},
        prepared_pins=prepared.pins,
        now=lambda: datetime(2026, 7, 21, 12, tzinfo=timezone.utc),
    )
    assert tuple(row.provider_event_id for row in snapshot.events) == (
        EXPECTED_PROVIDER_IDS
    )
    assert {row.matcher_version for row in snapshot.events} == {
        "systematic-team-pin-v1"
    }

    changed_events = (
        replace(target.events[0], home_team="Changed"),
        *target.events[1:],
    )
    changed_target = replace(target, events=changed_events)
    with pytest.raises(ValueError, match="stale drawing pins"):
        load_drawing_pins(
            session_factory,
            drawing_id=changed_target.drawing_id,
            drawing_fingerprint=target_fingerprint(
                changed_target.drawing_id,
                changed_target.drawing_number,
                changed_target.deadline,
                changed_target.events,
            ),
            provider="api-sports",
        )


def test_pinned_collection_fails_closed_when_schedule_revalidation_is_stale():
    session_factory = _session_factory()
    seed_reviewed_alias_config(
        session_factory, "data/external-odds/team-aliases.json"
    )
    target = _target_drawing()
    prepared = prepare_drawing(
        target, _provider_events(), session_factory=session_factory
    )
    market_calls = []

    class StaleProvider:
        provider_name = "api-sports"
        quota_state = QuotaState(100, 100, 10, 10)
        requests_made = 0
        cache_hits = 0

        def fetch_schedule(self, sport, dates):
            requested = set(dates)
            return tuple(
                replace(
                    event,
                    fetched_at=datetime(2026, 7, 19, 12, tzinfo=timezone.utc),
                )
                for event in _provider_events()
                if event.starts_at.date() in requested
            )

        def fetch_event_markets(self, sport, provider_event_id):
            market_calls.append(provider_event_id)
            return ()

    snapshot = build_external_collection(
        target,
        StaleProvider(),
        aliases={},
        prepared_pins=prepared.pins,
        now=lambda: datetime(2026, 7, 21, 16, tzinfo=timezone.utc),
    )

    assert market_calls == []
    assert all(event.match_status == "provider_failure" for event in snapshot.events)
    assert all(
        event.fallback_reason
        == "pinned fixture revalidation schedule is stale; refresh schedule cache"
        for event in snapshot.events
    )
