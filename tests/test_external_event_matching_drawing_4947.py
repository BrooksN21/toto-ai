import json
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.collection import build_external_collection
from toto_ai.external_odds.domain import (
    ProviderEvent,
    QuotaState,
    TargetDrawing,
    TargetEvent,
)
from toto_ai.external_odds.matching import match_event

TARGET_PAIRS = (
    ("Сан Лоренцо", "Депортиво Риестра"),
    ("Депортиво Майпу", "Сан Мартин Тукуман"),
    ("Альмиранте Браун", "Эстудиантес Касерос"),
    ("Атлетико Митре", "Расинг Кордоба"),
    ("Ферро Каррил Оэсте", "Колон СФ"),
    ("Сьюдад де Боливар", "Олл Бойз"),
    ("Дефенсорес де Камбасерес", "Хенераль Ламадрид"),
    ("Депортиво Эспаньол", "Викториано Аренас"),
    ("Атлетико Лугано", "Спортиво Барракас"),
    ("Юпанки", "Аргентино Росарио"),
    ("Америка Минейро", "Сеара"),
    ("Форталеза", "Гремио Новоризонтино"),
    ("Лондрина", "Ботафого СП"),
    ("Волунтари", "Ботошани"),
    ("Дельфин", "Макара"),
)

EXPECTED_PROVIDER_IDS = (
    "1540061",
    "1498660",
    "1498651",
    "1498652",
    "1498661",
    "1498656",
    "1499997",
    "1499998",
    "1500003",
    "1500005",
    "1520770",
    "1520774",
    "1520776",
    "1565186",
    "1519409",
)


def _provider_events() -> tuple[ProviderEvent, ...]:
    payload = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "drawing_4947_api_sports_schedule.json"
        ).read_text(encoding="utf-8")
    )
    fetched_at = datetime.fromisoformat(payload["fetched_at"])
    return tuple(
        ProviderEvent(
            provider="api-sports",
            provider_event_id=event["id"],
            sport="football",
            league=event["league"],
            starts_at=datetime.fromisoformat(event["date"]),
            home_team=event["home"],
            away_team=event["away"],
            fetched_at=fetched_at,
            payload_hash=f"hash-{event['id']}",
        )
        for event in payload["events"]
    )


def _target_drawing() -> TargetDrawing:
    deadline = datetime(2026, 7, 17, 15, 30, tzinfo=timezone.utc)
    targets = tuple(
        TargetEvent(
            drawing_id=11957,
            drawing_number=4947,
            event_id=20000 + order,
            event_order=order,
            sport="football",
            championship="real drawing fixture",
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
        drawing_id=11957,
        drawing_number=4947,
        deadline=deadline,
        fetched_at=datetime(2026, 7, 17, 15, 10, tzinfo=timezone.utc),
        events=targets,
    )


class _ReplayProvider:
    provider_name = "api-sports"

    def __init__(self) -> None:
        self.events = _provider_events()
        self.requests_made = 0
        self.cache_hits = 0
        self.quota_state = QuotaState(100, 100, 10, 10)

    def fetch_schedule(self, sport, dates):
        self.requests_made += 1
        requested_dates = set(dates)
        return tuple(
            event
            for event in self.events
            if event.sport == sport and event.starts_at.date() in requested_dates
        )

    def fetch_event_markets(self, sport, provider_event_id):
        self.requests_made += 1
        return ()


def test_real_drawing_4947_matches_all_events_without_start_or_english_names():
    target = _target_drawing()
    candidates = _provider_events()

    decisions = tuple(
        match_event(event, candidates, aliases={}) for event in target.events
    )

    assert tuple(decision.status for decision in decisions) == ("matched",) * 15
    assert tuple(
        decision.provider_event_id for decision in decisions
    ) == EXPECTED_PROVIDER_IDS


def test_real_drawing_4947_collection_recovers_playable_effective_times():
    snapshot = build_external_collection(
        _target_drawing(),
        _ReplayProvider(),
        aliases={},
    )

    assert tuple(row.match_status for row in snapshot.events) == ("matched",) * 15
    assert tuple(row.provider_event_id for row in snapshot.events) == (
        EXPECTED_PROVIDER_IDS
    )
    assert snapshot.eligibility.status == "playable"
    assert snapshot.eligibility.totobrief_count == 0
    assert snapshot.eligibility.provider_count == 15
    assert snapshot.eligibility.missing_event_orders == ()
