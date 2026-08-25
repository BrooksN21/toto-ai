from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from toto_ai.external_odds.matching import load_reviewed_alias_names
from toto_ai.external_odds.schedule_source_collector import (
    collect_schedule_source_candidates,
)
from toto_ai.external_odds.thesportsdb import (
    TheSportsDBClient,
    TheSportsDBConfig,
)

UTC = timezone.utc
SECRET = "collection-secret"
REVIEWED_ALIASES = load_reviewed_alias_names(
    "data/external-odds/team-aliases.json"
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _queue(
    tmp_path: Path,
    *,
    home_team: str = "Росарио Сентраль",
    away_team: str = "Тальерес",
) -> Path:
    payload = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-24T15:00:00Z",
        "identity": {
            "drawing_id": 12062,
            "drawing_number": 4985,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-24T16:00:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12062,
                "drawing_number": 4985,
                "target_fingerprint": "a" * 64,
                "event_order": 8,
                "target_event_id": 180008,
                "home_team": home_team,
                "away_team": away_team,
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        ],
    }
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _rapid_ledger(tmp_path: Path) -> Path:
    ledger_dir = tmp_path / "schedule-evidence"
    review = ledger_dir / "reviews" / "rapid.md"
    review.parent.mkdir(parents=True)
    review.write_text("Reviewed Rapid identity.\n", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "generated_at": "2026-08-24T15:00:00Z",
        "observations": [
            {
                "observation_id": "rapid-ledger-precedence",
                "sport": "football",
                "gender_age_class": "men-senior",
                "competition_aliases": ["Test competition"],
                "home_entity": "SK Rapid Wien",
                "home_aliases": ["Рапид Вена"],
                "away_entity": "Ledger Opponent",
                "away_aliases": ["Соперник из реестра"],
                "starts_at": "2026-08-25T18:30:00Z",
                "status": "scheduled",
                "conditional": False,
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-08-24T15:00:00Z",
                "review_document": "reviews/rapid.md",
                "review_document_sha256": hashlib.sha256(
                    review.read_bytes()
                ).hexdigest(),
                "claims": [
                    {
                        "source_name": "Official test source",
                        "role": "official",
                        "source_url": "https://example.com/rapid",
                    }
                ],
            }
        ],
    }
    path = ledger_dir / "ledger.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@dataclass
class FakeResponse:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url, *, params, timeout):
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected network call")
        return self.responses.pop(0)


def _fixture() -> dict[str, object]:
    return json.loads(
        Path("tests/fixtures/thesportsdb_v1_events.json").read_text(encoding="utf-8")
    )


def _scheduled_event(
    home_team: str,
    away_team: str,
    *,
    event_id: str = "4986-reviewed",
) -> dict[str, object]:
    return {
        "event": [
            {
                "idEvent": event_id,
                "strSport": "Soccer",
                "strLeague": "Drawing 4986 test fixtures",
                "strHomeTeam": home_team,
                "strAwayTeam": away_team,
                "strTimestamp": "2026-08-25T18:30:00Z",
                "strTime": "18:30:00",
                "strStatus": "Not Started",
            }
        ]
    }


@pytest.mark.parametrize(
    ("target_home", "target_away", "canonical_home", "canonical_away"),
    (
        ("Кардифф Сити", "Норвич", "Cardiff City", "Norwich City"),
        ("Блэкпул", "Линкольн Сити", "Blackpool", "Lincoln City"),
        (
            "Кембридж Юнайтед",
            "Миллуолл",
            "Cambridge United",
            "Millwall",
        ),
        ("Флитвуд", "Шрусбери Таун", "Fleetwood Town", "Shrewsbury Town"),
        ("Сток Сити", "Халл Сити", "Stoke City", "Hull City"),
        ("Саутгемптон", "Вест Хэм", "Southampton", "West Ham United"),
        (
            "Ноттингем Форест",
            "Лидс",
            "Nottingham Forest",
            "Leeds United",
        ),
    ),
)
def test_reviewed_aliases_resolve_previously_rejected_drawing_4986_pairs(
    tmp_path: Path,
    target_home: str,
    target_away: str,
    canonical_home: str,
    canonical_away: str,
) -> None:
    payload = _scheduled_event(canonical_home, canonical_away)
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(tmp_path, home_team=target_home, away_team=target_away),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases=REVIEWED_ALIASES,
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert [call["params"] for call in session.calls] == [
        {"e": f"{canonical_home}_vs_{canonical_away}"},
        {"e": f"{canonical_away}_vs_{canonical_home}"},
    ]
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "4986-reviewed"
    assert record["orientation"] == "same"
    assert record["ledger_eligible"] is False


@pytest.mark.parametrize(
    ("target_home", "target_away", "canonical_home", "canonical_away"),
    (
        ("Стивенидж", "Рединг", "Stevenage", "Reading"),
        ("ЛАСК Линц", "Селтик", "LASK", "Celtic"),
    ),
)
def test_reviewed_aliases_supply_canonical_query_names(
    tmp_path: Path,
    target_home: str,
    target_away: str,
    canonical_home: str,
    canonical_away: str,
) -> None:
    session = FakeSession([FakeResponse({"event": []}), FakeResponse({"event": []})])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    collect_schedule_source_candidates(
        _queue(tmp_path, home_team=target_home, away_team=target_away),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases=REVIEWED_ALIASES,
    )

    assert [call["params"] for call in session.calls] == [
        {"e": f"{canonical_home}_vs_{canonical_away}"},
        {"e": f"{canonical_away}_vs_{canonical_home}"},
    ]


def test_womens_variants_do_not_inherit_reviewed_mens_aliases(
    tmp_path: Path,
) -> None:
    payload = _scheduled_event("Cardiff City", "Norwich City")
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(
            tmp_path,
            home_team="Кардифф Сити (жен.)",
            away_team="Норвич (жен.)",
        ),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases=REVIEWED_ALIASES,
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    queries = [str(call["params"]["e"]) for call in session.calls]
    assert queries[0] != "Cardiff City_vs_Norwich City"
    assert all(query.count("Women") == 2 for query in queries)
    assert record["status"] == "not_found"


def test_unknown_low_score_pair_still_rejects(tmp_path: Path) -> None:
    payload = _scheduled_event("Cardiff City", "Norwich City", event_id="unrelated")
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(
            tmp_path,
            home_team="Неизвестный Альфа",
            away_team="Неизвестный Бета",
        ),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases=REVIEWED_ALIASES,
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert record["status"] == "not_found"
    assert record["candidate_ids"] == []


def test_collection_uses_existing_alias_orientation_matcher_without_promotion(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    session = FakeSession([FakeResponse(_fixture()), FakeResponse(_fixture())])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases={
            "Росарио Сентраль": "Rosario Central",
            "Тальерес": "Talleres de Córdoba",
        },
    )

    records = [
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    ]
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "1001"
    assert record["orientation"] == "reversed"
    assert record["source_status"] == "not_started"
    assert record["status_eligible"] is True
    assert record["ledger_eligible"] is False
    assert record["missing_requirements"] == ["official_source", "review"]
    assert result.candidate_count == 1
    assert result.unresolved_count == 0
    assert result.provider_statuses["thesportsdb-v1"]["status"] == "collected"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert report["ledger_mutated"] is False
    assert report["providers"]["thesportsdb-v1"]["candidate_count"] == 1
    assert SECRET not in result.report_path.read_text(encoding="utf-8")
    assert not tuple(tmp_path.rglob("ledger.json"))
    assert len(session.calls) == 2
    assert session.calls[0]["params"] == {
        "e": "Rosario Central_vs_Talleres de Córdoba"
    }
    assert session.calls[1]["params"] == {
        "e": "Talleres de Córdoba_vs_Rosario Central"
    }


def test_ledger_alias_wins_supplied_conflict_without_suppressing_other_aliases(
    tmp_path: Path,
) -> None:
    payload = _scheduled_event(
        "SK Rapid Wien",
        "FC Salzburg",
        event_id="rapid-ledger-wins",
    )
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(
            tmp_path,
            home_team="Рапид Вена",
            away_team="Зальцбург",
        ),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        schedule_evidence_ledger=_rapid_ledger(tmp_path),
        thesportsdb_client=client,
        team_aliases={
            "Рапид Вена": "Rapid Vienna",
            "Зальцбург": "FC Salzburg",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "rapid-ledger-wins"
    assert [call["params"] for call in session.calls] == [
        {"e": "SK Rapid Wien_vs_FC Salzburg"},
        {"e": "FC Salzburg_vs_SK Rapid Wien"},
    ]
    diagnostics = result.provider_statuses["thesportsdb-v1"][
        "alias_conflicts_skipped"
    ]
    assert diagnostics == {
        "count": 1,
        "normalized_alias_keys": ["рапид вена"],
        "truncated": False,
    }
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["providers"]["thesportsdb-v1"][
        "alias_conflicts_skipped"
    ] == diagnostics
    assert "Rapid Vienna" not in json.dumps(record, ensure_ascii=False)


def test_same_value_ledger_and_supplied_alias_is_not_a_conflict(
    tmp_path: Path,
) -> None:
    payload = _scheduled_event("SK Rapid Wien", "FC Salzburg")
    session = FakeSession([FakeResponse(payload), FakeResponse(payload)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        _queue(
            tmp_path,
            home_team="Рапид Вена",
            away_team="Зальцбург",
        ),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        schedule_evidence_ledger=_rapid_ledger(tmp_path),
        thesportsdb_client=client,
        team_aliases={
            "Рапид Вена": "SK Rapid Wien",
            "Зальцбург": "FC Salzburg",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert record["status"] == "independent_candidate"
    assert result.provider_statuses["thesportsdb-v1"][
        "alias_conflicts_skipped"
    ] == {
        "count": 0,
        "normalized_alias_keys": [],
        "truncated": False,
    }


def test_collection_queries_reverse_orientation_when_forward_search_is_empty(
    tmp_path: Path,
) -> None:
    queue = _queue(tmp_path)
    session = FakeSession(
        [
            FakeResponse({"event": []}),
            FakeResponse(_fixture()),
        ]
    )
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases={
            "Росарио Сентраль": "Rosario Central",
            "Тальерес": "Talleres de Córdoba",
        },
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert record["status"] == "independent_candidate"
    assert record["source_event_id"] == "1001"
    assert record["orientation"] == "reversed"
    assert record["ledger_eligible"] is False
    assert result.provider_statuses["thesportsdb-v1"]["ledger_mutated"] is False
    assert len(session.calls) == 2


def test_collection_preserves_womens_markers_and_rejects_mens_alias(
    tmp_path: Path,
) -> None:
    queue = _queue(
        tmp_path,
        home_team="Челси (жен.)",
        away_team="Арсенал (жен.)",
    )
    session = FakeSession([FakeResponse({"event": []}), FakeResponse({"event": []})])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
        team_aliases={
            "Челси (жен.)": "Chelsea",
            "Арсенал (жен.)": "Arsenal Women",
        },
    )

    first_query = str(session.calls[0]["params"]["e"])
    assert first_query != "Chelsea_vs_Arsenal Women"
    assert first_query.count("Women") == 2


def test_independent_latin_names_are_lookup_only_and_never_promote(
    tmp_path: Path,
) -> None:
    queue = _queue(
        tmp_path,
        home_team="Дом (жен.)",
        away_team="Гости (жен.)",
    )
    starts_at = int(datetime(2026, 8, 25, 18, 30, tzinfo=UTC).timestamp())
    sofascore = {
        "results": [
            {
                "type": "event",
                "entity": {
                    "id": 7001,
                    "customId": "hint-only",
                    "slug": "chelsea-women-arsenal-women",
                    "startTimestamp": starts_at,
                    "tournament": {"name": "Women League"},
                    "homeTeam": {
                        "name": "Chelsea Women",
                        "sport": {"slug": "football"},
                        "fieldTranslations": {
                            "nameTranslation": {"ru": "Дом (жен.)"}
                        },
                    },
                    "awayTeam": {
                        "name": "Arsenal Women",
                        "fieldTranslations": {
                            "nameTranslation": {"ru": "Гости (жен.)"}
                        },
                    },
                },
            }
        ]
    }
    thesportsdb = {
        "event": [
            {
                "idEvent": "8001",
                "strSport": "Soccer",
                "strLeague": "Women League",
                "strHomeTeam": "Chelsea Women",
                "strAwayTeam": "Arsenal Women",
                "strTimestamp": "2026-08-25T18:30:00Z",
                "strTime": "18:30:00",
                "strStatus": "Not Started",
            }
        ]
    }
    session = FakeSession([FakeResponse(thesportsdb), FakeResponse(thesportsdb)])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    result = collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: sofascore,
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
    )

    record = next(
        item
        for item in result.records
        if item.get("source_provider") == "thesportsdb-v1"
    )
    assert session.calls[0]["params"] == {
        "e": "Chelsea Women_vs_Arsenal Women"
    }
    assert record["status"] == "not_found"
    assert record["ledger_eligible"] is False
    assert result.provider_statuses["thesportsdb-v1"]["ledger_mutated"] is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["ledger_mutated"] is False
    assert SECRET not in json.dumps(report, sort_keys=True)


def test_forward_reverse_query_strings_are_deduplicated(tmp_path: Path) -> None:
    queue = _queue(tmp_path, home_team="Same Team", away_team="Same Team")
    session = FakeSession([FakeResponse({"event": []})])
    client = TheSportsDBClient(
        SECRET,
        session=session,
        cache_dir=tmp_path / "out" / "thesportsdb-v1",
        now=lambda: datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
    )

    collect_schedule_source_candidates(
        queue,
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_client=client,
    )

    assert [call["params"] for call in session.calls] == [
        {"e": "Same Team_vs_Same Team"}
    ]


def test_collection_can_explicitly_disable_thesportsdb(tmp_path: Path) -> None:
    result = collect_schedule_source_candidates(
        _queue(tmp_path),
        output_dir=tmp_path / "out",
        fetch_json=lambda _url: {"results": []},
        captured_at=datetime(2026, 8, 24, 16, 5, tzinfo=UTC),
        thesportsdb_config=TheSportsDBConfig(api_key=None),
    )

    status = result.provider_statuses["thesportsdb-v1"]
    assert status == {
        "status": "disabled_missing_key",
        "config_key": "THESPORTSDB_API_KEY",
        "candidate_count": 0,
        "alias_conflicts_skipped": {
            "count": 0,
            "normalized_alias_keys": [],
            "truncated": False,
        },
        "ledger_mutated": False,
    }
    assert result.candidate_count == 0
    assert result.unresolved_count == 1
    assert all(
        item.get("source_provider") != "thesportsdb-v1" for item in result.records
    )
