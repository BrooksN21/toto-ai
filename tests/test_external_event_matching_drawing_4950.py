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
from toto_ai.external_odds.matching import (
    load_aliases,
    match_event,
    normalize_team_name,
)

TARGET_PAIRS = (
    ("Ботев Пловдив", "Локомотив София"),
    ("Атлетико Сукре", "Атлетико Хуниорс"),
    ("Кеблавик", "Акранес"),
    ("Хафнарфьордюр", "Брейдаблик"),
    ("Гриндавик/Ньярдвик(ж)", "Троттур Рейкьявик(ж)"),
    ("Супер Нова", "Гробина"),
    ("Джвайя", "Аль Ахед Бейрут"),
    ("Аль-Ансар", "Неджме"),
    ("Такуари Асунсьон", "Депортиво Капиата"),
    ("Хунедоара", "Чиксереда"),
    ("Рапид Бухарест", "Сепси"),
    ("ТПС", "Ильвес"),
    ("Кальмар", "Мальме"),
    ("Норрбю", "Сундсваль"),
    ("Мушук Руна", "Оренсе"),
)

EXPECTED_PROVIDER_IDS = (
    "1551047",
    None,
    "1508810",
    "1508813",
    None,
    "1515888",
    "1593669",
    "1593670",
    "1586075",
    "1565183",
    "1565184",
    "1495737",
    "1494214",
    "1497627",
    "1519414",
)

REVIEWED_ALIASES = {
    "Джвайя": "Jwaaya FC",
    "Аль Ахед Бейрут": "Al Ahed",
    "Аль-Ансар": "Al Ansar",
    "Неджме": "Al Nejmeh",
    "Такуари Асунсьон": "Tacuary",
    "Депортиво Капиата": "Deportivo Capiata",
    "Рапид Бухарест": "Rapid",
    "Сепси": "Sepsi OSK Sfantu Gheorghe",
    "ТПС": "Turku PS",
    "Ильвес": "Ilves",
    "Кальмар": "Kalmar FF",
    "Мальме": "Malmo FF",
}

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "drawing_4950_api_sports_schedule.json"
)
_ALIASES_PATH = Path("data/external-odds/team-aliases.json")


def _provider_events() -> tuple[ProviderEvent, ...]:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
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
    deadline = datetime(2026, 7, 20, 14, 30, tzinfo=timezone.utc)
    targets = tuple(
        TargetEvent(
            drawing_id=11964,
            drawing_number=4950,
            event_id=178563 + order,
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
        drawing_id=11964,
        drawing_number=4950,
        deadline=deadline,
        fetched_at=datetime(2026, 7, 20, 13, 50, tzinfo=timezone.utc),
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


def test_real_drawing_4950_matches_exact_expected_provider_ids():
    target = _target_drawing()
    candidates = _provider_events()
    aliases = load_aliases(_ALIASES_PATH)

    decisions = tuple(
        match_event(event, candidates, aliases) for event in target.events
    )

    assert len(candidates) == 469
    assert tuple(
        decision.provider_event_id for decision in decisions
    ) == EXPECTED_PROVIDER_IDS
    assert tuple(
        order
        for order, decision in enumerate(decisions)
        if decision.status == "missing"
    ) == (1, 4)


def test_drawing_4950_reviewed_aliases_are_exact_provider_names():
    aliases = load_aliases(_ALIASES_PATH)
    expected = {
        normalize_team_name(source): normalize_team_name(provider)
        for source, provider in REVIEWED_ALIASES.items()
    }

    assert {source: aliases[source] for source in expected} == expected


def test_real_drawing_4950_collection_keeps_unresolved_timing_unknown():
    snapshot = build_external_collection(
        _target_drawing(),
        _ReplayProvider(),
        aliases=load_aliases(_ALIASES_PATH),
    )

    assert tuple(row.provider_event_id for row in snapshot.events) == (
        EXPECTED_PROVIDER_IDS
    )
    assert snapshot.eligibility.status == "unknown"
    assert snapshot.eligibility.span_days == 1
    assert snapshot.eligibility.totobrief_count == 0
    assert snapshot.eligibility.provider_count == 13
    assert snapshot.eligibility.missing_event_orders == (1, 4)
