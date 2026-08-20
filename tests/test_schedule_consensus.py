import hashlib
import json
from datetime import datetime, timezone

from toto_ai.external_odds.schedule_consensus import promote_uefa_sofascore_consensus

CAPTURED_AT = datetime(2026, 8, 20, 8, 30, tzinfo=timezone.utc)
KICKOFF = "2026-08-20T18:45:00Z"


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _queue(tmp_path, *, home="Хартс", away="Рапид Вена"):
    payload = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-20T08:00:00Z",
        "identity": {
            "drawing_id": 12050,
            "drawing_number": 4981,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-20T15:00:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12050,
                "drawing_number": 4981,
                "target_fingerprint": "a" * 64,
                "event_order": 6,
                "target_event_id": 179859,
                "home_team": home,
                "away_team": away,
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


def _ledger(tmp_path):
    root = tmp_path / "schedule-evidence"
    root.mkdir()
    path = root / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-20T08:00:00Z",
                "observations": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _uefa_event():
    return {
        "id": 2049254,
        "status": "UPCOMING",
        "competitionPhase": "QUALIFYING",
        "kickOffTime": {"dateTime": KICKOFF},
        "competition": {
            "age": "ADULT",
            "sex": "MALE",
            "sportsType": "FOOTBALL",
            "metaData": {"name": "UEFA Conference League"},
            "translations": {
                "name": {
                    "EN": "UEFA Conference League",
                    "RU": "Лига конференций УЕФА",
                }
            },
        },
        "homeTeam": {
            "id": "50120",
            "internationalName": "Hearts",
            "translations": {
                "displayName": {
                    "EN": "Hearts",
                    "RU": "Хартс",
                    "ZH": "哈茨",
                },
                "displayOfficialName": {
                    "EN": "Heart of Midlothian FC",
                    "RU": "Хартс",
                },
                "shortName": {"EN": "Hearts", "RU": "Хартс"},
            },
        },
        "awayTeam": {
            "id": "50042",
            "internationalName": "SK Rapid",
            "translations": {
                "displayName": {"EN": "SK Rapid", "RU": "Рапид В"},
                "displayOfficialName": {
                    "EN": "SK Rapid Wien",
                    "RU": "Рапид Вена",
                },
                "shortName": {"EN": "Rapid Wien", "RU": "Рапид"},
            },
        },
    }


def _sofascore_event(*, kickoff=1787251500):
    return {
        "id": 16717079,
        "name": "Heart of Midlothian - SK Rapid Wien",
        "slug": "heart-of-midlothian-sk-rapid-wien",
        "customId": "abc123",
        "startTimestamp": kickoff,
        "status": {"type": "notstarted"},
        "homeTeam": {
            "id": 2353,
            "name": "Heart of Midlothian",
            "fieldTranslations": {
                "nameTranslation": {"ru": "Харт оф Мидлотиан"}
            },
        },
        "awayTeam": {
            "id": 2055,
            "name": "SK Rapid Wien",
            "fieldTranslations": {"nameTranslation": {"ru": "Рапид Вена"}},
        },
        "tournament": {
            "name": "UEFA Europa Conference League, Qualification Playoff"
        },
    }


def _fetcher(*, sofa_kickoff=1787251500):
    official = _uefa_event()
    independent = _sofascore_event(kickoff=sofa_kickoff)

    def fetch(url):
        if "match.uefa.com/v5/matches?" in url:
            return [official]
        if url.endswith("/v5/matches/2049254/"):
            return official
        if "sofascore.com/api/v1/search/all" in url:
            return {"results": [{"type": "event", "entity": independent}]}
        if url.endswith("/api/v1/event/16717079"):
            return {"event": independent}
        raise AssertionError(f"unexpected URL: {url}")

    return fetch


def test_exact_consensus_promotes_hash_bound_observation_idempotently(tmp_path):
    queue = _queue(tmp_path)
    ledger = _ledger(tmp_path)

    first = promote_uefa_sofascore_consensus(
        queue,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )
    second = promote_uefa_sofascore_consensus(
        queue,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert first.promoted_count == 1
    assert first.unresolved_count == 0
    assert second.promoted_count == 0
    assert second.existing_count == 1
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    assert len(payload["observations"]) == 1
    observation = payload["observations"][0]
    assert observation["starts_at"] == KICKOFF
    assert observation["gender_age_class"] == "men-senior"
    assert observation["reviewer"] == "automated-exact-consensus-v1"
    assert {item["role"] for item in observation["claims"]} == {
        "official",
        "independent",
    }
    review = ledger.parent / observation["review_document"]
    assert review.is_file()
    assert hashlib.sha256(review.read_bytes()).hexdigest() == observation[
        "review_document_sha256"
    ]
    assert tuple((ledger.parent / "snapshots" / "auto").glob("*.json"))


def test_kickoff_disagreement_fails_closed_without_ledger_mutation(tmp_path):
    queue = _queue(tmp_path)
    ledger = _ledger(tmp_path)

    result = promote_uefa_sofascore_consensus(
        queue,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(sofa_kickoff=1787251560),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert result.unresolved_count == 1
    assert result.records[0]["status"] == "kickoff_conflict"
    assert json.loads(ledger.read_text())["observations"] == []


def test_target_must_exactly_match_an_official_localized_alias(tmp_path):
    queue = _queue(tmp_path, home="Харт")
    ledger = _ledger(tmp_path)

    result = promote_uefa_sofascore_consensus(
        queue,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert result.records[0]["status"] == "official_not_found"
    assert json.loads(ledger.read_text())["observations"] == []
