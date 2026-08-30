import hashlib
import json
from datetime import datetime, timezone

import pytest

from toto_ai.external_odds.domain import TargetEvent
from toto_ai.external_odds.independent_schedule_consensus import (
    promote_goal_sofascore_consensus,
    promote_independent_schedule_consensus,
)
from toto_ai.external_odds.schedule_evidence import (
    load_schedule_evidence_ledger,
    resolve_schedule_evidence,
)

UTC = timezone.utc
CAPTURED_AT = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 8, 26, 18, 0, tzinfo=UTC)


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _queue(tmp_path):
    payload = {
        "schema_version": 1,
        "queue_type": "reviewed_schedule_evidence",
        "created_at": "2026-08-26T08:00:00Z",
        "identity": {
            "drawing_id": 12068,
            "drawing_number": 4987,
            "drawing_fingerprint": "a" * 64,
            "deadline": "2026-08-26T18:45:00Z",
            "detail_sha256": "b" * 64,
            "reviewed_catalog_hash": None,
        },
        "records": [
            {
                "status": "awaiting_review",
                "drawing_id": 12068,
                "drawing_number": 4987,
                "target_fingerprint": "a" * 64,
                "event_order": 4,
                "target_event_id": 180127,
                "home_team": "Чако Фор Эвер",
                "away_team": "Сан Мигель",
                "championship": "Аргентина. Примера Насьональ",
                "source_fixture_id": None,
                "requirements": {},
                "template": {},
            }
        ],
    }
    payload["queue_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path, payload


def _source_report(tmp_path, queue, *, starts_at=KICKOFF):
    goal = {
        "status": "independent_candidate",
        "drawing_id": 12068,
        "drawing_number": 4987,
        "target_fingerprint": "a" * 64,
        "event_order": 4,
        "target_event_id": 180127,
        "home_team": "Чако Фор Эвер",
        "away_team": "Сан Мигель",
        "source_name": "GOAL API",
        "source_provider": "goal-api-v1",
        "source_role": "independent",
        "source_url": "https://goal-api.com",
        "source_event_id": "goal-7001",
        "home_name": "Chaco For Ever",
        "away_name": "San Miguel",
        "canonical_home_name": "Chaco For Ever",
        "canonical_away_name": "San Miguel",
        "orientation": "same",
        "match_mode": "matched",
        "competition": "Primera Nacional",
        "starts_at": starts_at.isoformat().replace("+00:00", "Z"),
        "source_status": "scheduled",
        "status_eligible": True,
        "captured_at": "2026-08-26T08:00:00Z",
    }
    payload = {
        "schema_version": 2,
        "status": "CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE",
        "queue_path": str(tmp_path / "queue.json"),
        "queue_sha256": queue["queue_sha256"],
        "drawing_id": 12068,
        "drawing_number": 4987,
        "captured_at": "2026-08-26T08:00:00Z",
        "candidate_count": 1,
        "unresolved_count": 0,
        "ledger_mutated": False,
        "providers": {},
        "records": [goal],
    }
    payload["report_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    path = tmp_path / "source.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _ledger(tmp_path):
    root = tmp_path / "schedule-evidence"
    root.mkdir()
    path = root / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-08-26T08:00:00Z",
                "observations": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _sofa_event(*, kickoff=KICKOFF):
    return {
        "id": 8001,
        "slug": "chaco-for-ever-san-miguel",
        "customId": "abc123",
        "startTimestamp": int(kickoff.timestamp()),
        "status": {"type": "notstarted"},
        "homeTeam": {
            "name": "CSYD Chaco For Ever",
            "fieldTranslations": {
                "nameTranslation": {
                    "ru": "Чако Фор Эвер",
                    "ar": "تشاكو فور إيفر",
                }
            },
        },
        "awayTeam": {
            "name": "San Miguel",
            "fieldTranslations": {"nameTranslation": {"ru": "Сан Мигель"}},
        },
        "tournament": {"name": "Primera Nacional"},
    }


def _fetcher(*, sofa_kickoff=KICKOFF):
    event = _sofa_event(kickoff=sofa_kickoff)

    def fetch(url):
        if "/search/all" in url:
            return {"results": [{"type": "event", "entity": event}]}
        if url.endswith("/api/v1/event/8001"):
            return {"event": event}
        raise AssertionError(f"unexpected URL: {url}")

    return fetch


def _add_sofascore_source_record(
    source_path,
    *,
    away_name="San Miguel",
    starts_at=KICKOFF,
):
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["records"].append(
        {
            "status": "independent_candidate",
            "drawing_id": 12068,
            "drawing_number": 4987,
            "target_fingerprint": "a" * 64,
            "event_order": 4,
            "target_event_id": 180127,
            "home_team": "Чако Фор Эвер",
            "away_team": "Сан Мигель",
            "source_name": "Sofascore",
            "source_provider": "sofascore-v1",
            "source_role": "independent",
            "source_url": (
                "https://www.sofascore.com/football/match/"
                "chaco-for-ever-san-miguel/abc123#id:8001"
            ),
            "source_event_id": 8001,
            "home_name": "CSYD Chaco For Ever",
            "away_name": away_name,
            "canonical_home_name": "Chaco For Ever",
            "canonical_away_name": "San Miguel",
            "orientation": "same",
            "match_mode": "matched",
            "source_status": "not_started",
            "status_eligible": True,
            "starts_at": starts_at.isoformat().replace("+00:00", "Z"),
            "captured_at": "2026-08-26T08:00:00Z",
        }
    )
    payload["candidate_count"] = 2
    payload.pop("report_sha256")
    payload["report_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    source_path.write_text(json.dumps(payload), encoding="utf-8")


def _add_thesportsdb_source_record(
    source_path,
    *,
    starts_at=KICKOFF,
    orientation="same",
    match_mode="matched",
    source_status="not_started",
    source_url="https://www.thesportsdb.com/event/9001",
    source_event_id="9001",
    home_name="Chaco For Ever",
    canonical_home_name="Chaco For Ever",
):
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["records"].append(
        {
            "status": "independent_candidate",
            "drawing_id": 12068,
            "drawing_number": 4987,
            "target_fingerprint": "a" * 64,
            "event_order": 4,
            "target_event_id": 180127,
            "home_team": "Чако Фор Эвер",
            "away_team": "Сан Мигель",
            "source_name": "TheSportsDB",
            "source_provider": "thesportsdb-v1",
            "source_role": "independent",
            "source_url": source_url,
            "source_event_id": source_event_id,
            "home_name": home_name,
            "away_name": "San Miguel",
            "canonical_home_name": canonical_home_name,
            "canonical_away_name": "San Miguel",
            "orientation": orientation,
            "match_mode": match_mode,
            "competition": "Primera Nacional",
            "starts_at": starts_at.isoformat().replace("+00:00", "Z"),
            "source_status": source_status,
            "status_eligible": source_status in {"scheduled", "not_started"},
            "captured_at": "2026-08-26T08:00:00Z",
        }
    )
    payload["candidate_count"] = len(payload["records"])
    payload.pop("report_sha256")
    payload["report_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    source_path.write_text(json.dumps(payload), encoding="utf-8")


def test_collected_sofascore_identity_bridges_canonical_spelling_variant(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["records"][0]["home_name"] = "Chaco For Ever"
    payload.pop("report_sha256")
    payload["report_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    source.write_text(json.dumps(payload), encoding="utf-8")
    _add_sofascore_source_record(source)
    ledger = _ledger(tmp_path)

    result = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 1
    observation = load_schedule_evidence_ledger(ledger).observations[0]
    assert "San Miguel" in observation.away_aliases


def test_exact_goal_thesportsdb_consensus_promotes_with_both_provenances(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    _add_thesportsdb_source_record(source)
    ledger = _ledger(tmp_path)

    result = promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 1
    observation = load_schedule_evidence_ledger(ledger).observations[0]
    assert {claim.source_name for claim in observation.claims} == {
        "GOAL API",
        "TheSportsDB",
    }
    review = observation.review_document.read_text(encoding="utf-8")
    assert "goal-api-v1" in review
    assert "thesportsdb-v1" in review
    assert review.count("SHA-256") == 2


def test_single_independent_source_does_not_promote_without_second_evidence(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    ledger = _ledger(tmp_path)

    result = promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=lambda _url: (_ for _ in ()).throw(ValueError("unavailable")),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert json.loads(ledger.read_text())["observations"] == []


@pytest.mark.parametrize(
    "overrides",
    (
        {"match_mode": "fuzzy_candidate_margin_0.9"},
        {"orientation": "reversed"},
        {"starts_at": KICKOFF.replace(minute=6)},
        {"source_status": "finished"},
        {"source_url": "https://goal-api.com/event/9001"},
    ),
)
def test_non_strict_independent_pair_never_promotes(tmp_path, overrides):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    _add_thesportsdb_source_record(source, **overrides)
    ledger = _ledger(tmp_path)

    result = promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert json.loads(ledger.read_text())["observations"] == []


def test_duplicate_provider_candidates_are_ambiguous_and_never_promote(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    _add_thesportsdb_source_record(source)
    _add_thesportsdb_source_record(source, source_event_id="9002")
    ledger = _ledger(tmp_path)

    result = promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert json.loads(ledger.read_text())["observations"] == []


def test_short_team_token_subset_does_not_match_longer_team(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    _add_thesportsdb_source_record(
        source,
        home_name="Chaco",
        canonical_home_name="Chaco",
    )
    ledger = _ledger(tmp_path)

    result = promote_independent_schedule_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert json.loads(ledger.read_text())["observations"] == []


def test_collected_sofascore_kickoff_conflict_fails_closed(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    _add_sofascore_source_record(
        source,
        starts_at=KICKOFF.replace(minute=6),
    )
    ledger = _ledger(tmp_path)

    result = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert result.unresolved_count == 1
    assert json.loads(ledger.read_text())["observations"] == []


def test_exact_goal_sofascore_consensus_promotes_and_resolves(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    ledger = _ledger(tmp_path)

    first = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )
    second = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert first.promoted_count == 1
    assert second.existing_count == 1
    loaded = load_schedule_evidence_ledger(ledger)
    observation = loaded.observations[0]
    assert "Аргентина. Примера Насьональ" in observation.competition_aliases
    assert observation.observation_id.startswith("independent-consensus-v2-")
    assert {claim.source_name for claim in observation.claims} == {
        "GOAL API",
        "Sofascore event",
    }
    target = TargetEvent(
        drawing_id=12068,
        drawing_number=4987,
        event_id=180127,
        event_order=4,
        sport="football",
        championship="Аргентина. Примера Насьональ",
        starts_at=None,
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        home_team="Чако Фор Эвер",
        away_team="Сан Мигель",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )
    assert (
        resolve_schedule_evidence(
            target,
            loaded,
            evaluated_at=CAPTURED_AT,
        ).state
        == "RESOLVED"
    )


def test_legacy_observation_without_target_competition_is_superseded(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    ledger = _ledger(tmp_path)
    promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )
    raw = json.loads(ledger.read_text(encoding="utf-8"))
    raw["observations"][0]["observation_id"] = "independent-consensus-legacy"
    raw["observations"][0]["competition_aliases"] = ["Primera Nacional"]
    ledger.write_text(json.dumps(raw), encoding="utf-8")

    repaired = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(),
        captured_at=CAPTURED_AT,
    )

    assert repaired.promoted_count == 1
    loaded = load_schedule_evidence_ledger(ledger)
    assert len(loaded.observations) == 2
    target = TargetEvent(
        drawing_id=12068,
        drawing_number=4987,
        event_id=180127,
        event_order=4,
        sport="football",
        championship="Аргентина. Примера Насьональ",
        starts_at=None,
        deadline=datetime(2026, 8, 26, 18, 45, tzinfo=UTC),
        home_team="Чако Фор Эвер",
        away_team="Сан Мигель",
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )
    assert (
        resolve_schedule_evidence(
            target,
            loaded,
            evaluated_at=CAPTURED_AT,
        ).state
        == "RESOLVED"
    )


def test_kickoff_conflict_does_not_mutate_ledger(tmp_path):
    queue_path, queue = _queue(tmp_path)
    source = _source_report(tmp_path, queue)
    ledger = _ledger(tmp_path)

    result = promote_goal_sofascore_consensus(
        queue_path,
        source_candidates_path=source,
        output_dir=tmp_path / "out",
        schedule_evidence_ledger=ledger,
        fetch_json=_fetcher(sofa_kickoff=KICKOFF.replace(minute=5)),
        captured_at=CAPTURED_AT,
    )

    assert result.promoted_count == 0
    assert result.unresolved_count == 1
    assert json.loads(ledger.read_text())["observations"] == []
