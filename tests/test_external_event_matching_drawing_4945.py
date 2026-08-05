import json
from datetime import datetime, timezone
from pathlib import Path

from toto_ai.external_odds.domain import ProviderEvent, TargetEvent
from toto_ai.external_odds.matching import load_aliases, match_event

TARGET_PAIRS = (
    ("Англия", "Аргентина"),
    ("Аттерт Биссен", "Клаксвик"),
    ("Дечич", "ФК Лиепая"),
    ("Вестманнаэйяр(ж)", "Валюр(ж)"),
    ("Майами ФК", "Инди Элевен"),
    ("Готэм(ж)", "Вашингтон Спирит(ж)"),
    ("Полония Варшава", "Злин"),
    ("Рапид Вена", "Панатинаикос"),
    ("Зальцбург", "Истанбул Башакшехир"),
    ("Липно Стешев", "Уния Сважендз"),
    ("Кордоба", "Орландо Пайретс"),
    ("Локарно", "Парадисо"),
    ("Либертад Лоха", "Текнико Университарио"),
    ("Леонес дель Норте", "Депортиво Куэнка"),
    ("Универсидад Католика Кито", "ЛДУ Кито"),
)

EXPECTED_PROVIDER_IDS = (
    "1586077",
    "1554375",
    "1554421",
    None,
    "1493574",
    "1508465",
    "1554959",
    "1583324",
    "1560619",
    "1584856",
    "1584860",
    None,
    "1519403",
    "1519402",
    "1519407",
)


def test_real_drawing_4945_preserves_thirteen_matches_and_two_safe_misses():
    payload = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "drawing_4945_api_sports_schedule.json"
        ).read_text(encoding="utf-8")
    )
    fetched_at = datetime.fromisoformat(payload["fetched_at"])
    candidates = tuple(
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
    deadline = datetime(2026, 7, 15, 15, 0, tzinfo=timezone.utc)
    targets = tuple(
        TargetEvent(
            drawing_id=11953,
            drawing_number=4945,
            event_id=19000 + order,
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
    aliases = load_aliases("data/external-odds/team-aliases.json")

    decisions = tuple(match_event(target, candidates, aliases) for target in targets)

    assert tuple(
        decision.provider_event_id for decision in decisions
    ) == EXPECTED_PROVIDER_IDS
    assert tuple(decision.status for decision in decisions).count("matched") == 13
    assert tuple(decision.status for decision in decisions).count("missing") == 2
