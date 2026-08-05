import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    DrawingEventPin,
    DrawingPreparation,
    TeamAlias,
    TeamEntity,
    TeamRegistryReview,
)
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing, TargetEvent
from toto_ai.external_odds.preparation import (
    fetch_preparation_schedule,
    preparation_probability_sha256,
    prepare_drawing,
)
from toto_ai.external_odds.team_registry import (
    backfill_accepted_matches,
    load_ready_drawing_pins,
    refresh_ready_drawing_preparation_evidence,
    seed_reviewed_alias_config,
)
from toto_ai.external_odds.team_resolution import (
    ResolutionContext,
    resolve_event_candidate,
)

NOW = datetime(2026, 7, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target(home="Спартак Москва", away="Зенит", *, starts_at=None):
    return TargetEvent(
        drawing_id=1,
        drawing_number=1,
        event_id=10,
        event_order=0,
        sport="football",
        championship="fixture",
        starts_at=starts_at,
        deadline=NOW,
        home_team=home,
        away_team=away,
        home_team_en=None,
        away_team_en=None,
        bk_probabilities=(0.4, 0.3, 0.3),
    )


def _candidate(
    fixture_id,
    home,
    away,
    *,
    starts_at=NOW + timedelta(hours=2),
    league="Premier League",
    country="Russia",
    home_id=None,
    away_id=None,
):
    return ProviderEvent(
        provider="api-sports",
        provider_event_id=fixture_id,
        sport="football",
        league=league,
        starts_at=starts_at,
        home_team=home,
        away_team=away,
        fetched_at=NOW,
        payload_hash=f"hash-{fixture_id}",
        country=country,
        provider_home_team_id=home_id,
        provider_away_team_id=away_id,
    )


def test_provider_ids_and_reviewed_registry_take_precedence(session_factory):
    backfill_accepted_matches(
        session_factory,
        [
            {
                "sport": "football",
                "target_home": "Спартак Москва",
                "target_away": "Зенит",
                "provider_home": "Spartak Moscow",
                "provider_away": "Zenit",
                "provider_home_team_id": "100",
                "provider_away_team_id": "200",
                "reason": "unique exact accepted historical pair",
                "reviewed": True,
            }
        ],
    )
    candidate = _candidate(
        "42",
        "Changed home display",
        "Changed away display",
        home_id="100",
        away_id="200",
    )
    result = resolve_event_candidate(
        _target(),
        (candidate,),
        session_factory=session_factory,
        context=ResolutionContext("api-sports"),
    )
    assert result.status == "matched"
    assert result.provider_event_id == "42"
    assert result.candidates[0].provider_id_count == 2


def test_transliteration_and_one_side_exact_need_unique_context(session_factory):
    transliterated = resolve_event_candidate(
        TargetEvent(
            **{
                **_target("Арарат-Армения", "Шамрок Роверс").__dict__,
                "championship": "Европа. Лига Чемпионов УЕФА",
            }
        ),
        (_candidate("1", "Ararat-Armenia", "Shamrock Rovers"),),
        session_factory=session_factory,
        context=ResolutionContext("api-sports", league="Premier League"),
    )
    one_side = resolve_event_candidate(
        _target("Насиональ Монтевидео", "Тигре"),
        (_candidate("2", "Club Nacional", "Tigre", country="Uruguay"),),
        session_factory=session_factory,
        context=ResolutionContext("api-sports", country="Uruguay"),
    )
    assert transliterated.status == "matched"
    assert one_side.status == "matched"
    assert "competition/date/orientation" in one_side.reason


def test_two_weak_shared_tokens_never_auto_accept_without_identity_context(
    session_factory,
):
    result = resolve_event_candidate(
        _target("Alpha United", "Beta Rovers"),
        (_candidate("weak", "Alpha City", "Beta Town"),),
        session_factory=session_factory,
        context=ResolutionContext("api-sports"),
    )

    assert result.status != "matched"
    assert result.provider_event_id is None


def test_prospective_unseen_teams_resolve_without_production_aliases(
    session_factory,
):
    result = resolve_event_candidate(
        TargetEvent(
            **{
                **_target("Quantum Athletic", "Nova Wanderers").__dict__,
                "championship": "Iceland Premier Division",
            }
        ),
        (
            _candidate(
                "future-1",
                "Quantum Athletic",
                "Nova Wanderers",
                league="Premier Division",
                country="Iceland",
                home_id="future-home",
                away_id="future-away",
            ),
        ),
        session_factory=session_factory,
        context=ResolutionContext("api-sports"),
    )

    assert result.status == "matched"
    assert result.provider_event_id == "future-1"


def test_preparation_schedule_fetch_is_progressive_and_isolates_date_failure(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}").__dict__,
                "event_id": 100 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    drawing = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=1), events)

    class Provider:
        def __init__(self):
            self.calls = []

        def fetch_schedule(self, sport, dates):
            requested = dates[0]
            self.calls.append((sport, requested))
            if len(self.calls) == 2:
                raise RuntimeError("future date unavailable")
            return (_candidate(f"fixture-{requested}", "Home", "Away"),)

    provider = Provider()
    result = fetch_preparation_schedule(
        drawing,
        provider,
        session_factory=session_factory,
        missing_start_horizon_days=3,
    )

    assert len(provider.calls) >= 3
    assert len(result.candidates) == len(provider.calls) - 1
    assert [item["status"] for item in result.diagnostics].count("failed") == 1
    assert result.diagnostics[1]["reason"] == "future date unavailable"


def test_ambiguous_pair_is_not_promoted_and_is_for_review(session_factory):
    candidates = (
        _candidate("1", "Ararat-Armenia", "Shamrock Rovers"),
        _candidate("2", "Ararat-Armenia", "Shamrock Rovers"),
    )
    result = resolve_event_candidate(
        _target("Арарат-Армения", "Шамрок Роверс"),
        candidates,
        session_factory=session_factory,
        context=ResolutionContext("api-sports"),
    )
    assert result.status == "ambiguous"
    assert result.provider_event_id is None


def test_wrong_league_date_and_orientation_are_enforced(session_factory):
    target = _target("Home", "Away", starts_at=NOW + timedelta(hours=1))
    wrong = (
        _candidate("late", "Home", "Away", starts_at=NOW + timedelta(days=1)),
        _candidate("league", "Home", "Away", league="Wrong League"),
    )
    rejected = resolve_event_candidate(
        target,
        wrong,
        session_factory=session_factory,
        context=ResolutionContext("api-sports", league="Premier League"),
    )
    reversed_result = resolve_event_candidate(
        target,
        (_candidate("ok", "Away", "Home", starts_at=target.starts_at),),
        session_factory=session_factory,
        context=ResolutionContext("api-sports", league="Premier League"),
    )
    assert rejected.status == "missing"
    assert reversed_result.status == "matched"
    assert reversed_result.orientation == "reversed"


def test_seed_and_backfill_are_idempotent_and_skip_fuzzy_ambiguity(session_factory):
    aliases = {"Спартак": "Spartak Moscow"}
    seed_reviewed_alias_config(session_factory, aliases)
    seed_reviewed_alias_config(session_factory, aliases)
    skipped = backfill_accepted_matches(
        session_factory,
        [
            {
                "sport": "football",
                "target_home": "Maybe",
                "target_away": "Unknown",
                "provider_home": "Maybe FC",
                "provider_away": "Other",
                "reason": "fuzzy ambiguous suggestion",
            }
        ],
    )
    with session_factory() as session:
        assert session.scalar(select(func.count(TeamEntity.id))) == 1
        assert session.scalar(select(func.count(TeamAlias.id))) == 2
    assert skipped == 0


def test_prepare_persists_ambiguous_event_to_review_queue(session_factory):
    labels = (
        "Atlas",
        "Borealis",
        "Cygnus",
        "Draco",
        "Equinox",
        "Fenix",
        "Gemini",
        "Helios",
        "Indigo",
        "Jupiter",
        "Kepler",
        "Lynx",
        "Meteor",
        "Nova",
        "Orion",
    )
    targets = tuple(
        _target(f"{labels[order]} Home", f"{labels[order]} Away")
        if order == 0
        else TargetEvent(
            **{
                **_target(
                    f"{labels[order]} Home", f"{labels[order]} Away"
                ).__dict__,
                "event_id": 10 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    drawing = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=1), targets)
    candidates = tuple(
        _candidate(
            str(order), f"{labels[order]} Home", f"{labels[order]} Away"
        )
        for order in range(15)
    ) + (_candidate("duplicate", "Atlas Home", "Atlas Away"),)

    result = prepare_drawing(
        drawing,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )

    assert result.mapped_count == 0
    assert result.pins == ()
    assert result.unresolved_event_orders == (0,)
    with session_factory() as session:
        review = session.scalar(select(TeamRegistryReview))
        assert review is not None
        assert review.event_order == 0
        assert review.status == "pending"
        assert review.resolution_reason
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0

    retry = prepare_drawing(
        drawing,
        candidates[:-1],
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    assert retry.status == "ready"
    assert retry.mapped_count == 15
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 15


def test_prepare_reused_pins_accept_newer_bk_probability_drift(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(
                    f"Home {order}", f"Away {order}"
                ).__dict__,
                "event_id": 100 + order,
                "event_order": order,
                "bk_probabilities": (
                    (40 / 101, 31 / 101, 30 / 101)
                    if order == 14
                    else (0.4, 0.3, 0.3)
                ),
            }
        )
        for order in range(15)
    )
    original = TargetDrawing(
        1, 1, NOW, NOW - timedelta(hours=2), events
    )
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )
    prepared = prepare_drawing(
        original,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    assert prepared.status == "ready"
    original_pin_hashes = tuple(pin.pin_hash for pin in prepared.pins)
    original_fingerprint = prepared.drawing_fingerprint
    with session_factory() as session:
        stored = session.scalar(select(DrawingPreparation))
        assert stored is not None
        original_summary = json.loads(stored.readiness_summary)

    refreshed_events = (
        *events[:-1],
        TargetEvent(
            **{
                **events[-1].__dict__,
                "bk_probabilities": (0.42, 0.30, 0.28),
            }
        ),
    )
    refreshed = TargetDrawing(
        1, 1, NOW, NOW - timedelta(hours=1), refreshed_events
    )
    new_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in refreshed.events)
    )

    result = prepare_drawing(
        refreshed,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )

    with session_factory() as session:
        preparation = session.scalar(select(DrawingPreparation))
        assert preparation is not None
        summary = json.loads(preparation.readiness_summary)
        assert summary["probability_input_sha256"] == new_hash
        assert summary["target_fetched_at"] == refreshed.fetched_at.isoformat()
        assert summary["probability_outcome_order"] == ["1", "X", "2"]
        assert summary["market_evidence_version"] == 2
        assert len(summary["market_evidence_history"]) == 2
    assert new_hash != original_summary["probability_input_sha256"]
    assert result.drawing_fingerprint == original_fingerprint
    assert (
        tuple(
            pin.pin_hash
            for pin in load_ready_drawing_pins(
                session_factory,
                drawing_id=refreshed.drawing_id,
                drawing_fingerprint=original_fingerprint,
                provider="api-sports",
                expected_probability_sha256=new_hash,
                as_of=NOW,
            )
        )
        == original_pin_hashes
    )


def _readiness_summary_for_assertion(prepared, target):
    probability_hash = preparation_probability_sha256(
        tuple(event.bk_probabilities for event in target.events)
    )
    with_probability_evidence = {
        "status": prepared.status,
        "mapped_count": prepared.mapped_count,
        "unresolved_event_orders": prepared.unresolved_event_orders,
        "eligibility": prepared.eligibility.__dict__,
        "events": [event.__dict__ for event in prepared.events],
        "schedule_diagnostics": prepared.schedule_diagnostics,
        "target_fetched_at": target.fetched_at.isoformat(),
        "probability_input_sha256": probability_hash,
        "market_probability_input_sha256": None,
        "probability_outcome_order": ["1", "X", "2"],
        "market_evidence_version": 1,
        "market_evidence_history": [
            {
                "version": 1,
                "target_fetched_at": target.fetched_at.isoformat(),
                "probability_input_sha256": probability_hash,
                "market_probability_input_sha256": None,
                "probability_outcome_order": ["1", "X", "2"],
            }
        ],
    }
    return json.dumps(
        with_probability_evidence,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def test_refresh_probability_evidence_is_monotonic_and_equal_time_fail_closed(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}").__dict__,
                "event_id": 100 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    target = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=2), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )
    prepared = prepare_drawing(
        target,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    newer_at = NOW - timedelta(hours=1)
    newer_summary = json.loads(_readiness_summary_for_assertion(prepared, target))
    newer_summary["target_fetched_at"] = newer_at.isoformat()
    refresh_ready_drawing_preparation_evidence(
        session_factory,
        drawing_id=1,
        drawing_fingerprint=prepared.drawing_fingerprint,
        provider="api-sports",
        readiness_summary=json.dumps(newer_summary),
    )
    with session_factory() as session:
        row = session.scalar(select(DrawingPreparation))
        assert row is not None
        after_newer = (row.readiness_summary, row.updated_at)

    older_summary = dict(newer_summary)
    older_summary["target_fetched_at"] = target.fetched_at.isoformat()
    with pytest.raises(ValueError, match="older probability evidence"):
        refresh_ready_drawing_preparation_evidence(
            session_factory,
            drawing_id=1,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            readiness_summary=json.dumps(older_summary),
        )

    refresh_ready_drawing_preparation_evidence(
        session_factory,
        drawing_id=1,
        drawing_fingerprint=prepared.drawing_fingerprint,
        provider="api-sports",
        readiness_summary=json.dumps(newer_summary),
    )
    mismatched = dict(newer_summary)
    mismatched["probability_input_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="conflicting probability evidence"):
        refresh_ready_drawing_preparation_evidence(
            session_factory,
            drawing_id=1,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            readiness_summary=json.dumps(mismatched),
        )

    wrong_outcome_order = dict(newer_summary)
    wrong_outcome_order["target_fetched_at"] = (
        newer_at + timedelta(minutes=1)
    ).isoformat()
    wrong_outcome_order["probability_outcome_order"] = ["2", "X", "1"]
    with pytest.raises(ValueError, match="outcome order"):
        refresh_ready_drawing_preparation_evidence(
            session_factory,
            drawing_id=1,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            readiness_summary=json.dumps(wrong_outcome_order),
        )

    invalid_hash = dict(newer_summary)
    invalid_hash["target_fetched_at"] = (
        newer_at + timedelta(minutes=1)
    ).isoformat()
    invalid_hash["probability_input_sha256"] = "not-a-hash"
    with pytest.raises(ValueError, match="invalid ready preparation evidence"):
        refresh_ready_drawing_preparation_evidence(
            session_factory,
            drawing_id=1,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            readiness_summary=json.dumps(invalid_hash),
        )

    with session_factory() as session:
        row = session.scalar(select(DrawingPreparation))
        assert row is not None
        assert (row.readiness_summary, row.updated_at) == after_newer


def test_concurrent_probability_refresh_keeps_newest_evidence(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'registry.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}").__dict__,
                "event_id": 100 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    target = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=3), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )
    prepared = prepare_drawing(
        target,
        candidates,
        session_factory=factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    base = json.loads(_readiness_summary_for_assertion(prepared, target))
    older = {**base, "target_fetched_at": (NOW - timedelta(hours=2)).isoformat()}
    newer = {
        **base,
        "target_fetched_at": (NOW - timedelta(hours=1)).isoformat(),
    }

    def refresh(summary):
        try:
            refresh_ready_drawing_preparation_evidence(
                factory,
                drawing_id=1,
                drawing_fingerprint=prepared.drawing_fingerprint,
                provider="api-sports",
                readiness_summary=json.dumps(summary),
            )
        except ValueError:
            pass

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(refresh, (newer, older)))

    with factory() as session:
        row = session.scalar(select(DrawingPreparation))
        assert row is not None
        summary = json.loads(row.readiness_summary)
        assert summary["target_fetched_at"] == newer["target_fetched_at"]
        assert (
            summary["probability_input_sha256"]
            == newer["probability_input_sha256"]
        )
    engine.dispose()


def test_probability_refresh_rejects_tampered_market_evidence_history(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}").__dict__,
                "event_id": 100 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    target = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=2), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )
    prepared = prepare_drawing(
        target,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    with session_factory.begin() as session:
        row = session.scalar(select(DrawingPreparation))
        assert row is not None
        summary = json.loads(row.readiness_summary)
        summary["market_evidence_history"][0]["probability_input_sha256"] = "bad"
        row.readiness_summary = json.dumps(summary)

    newer_summary = json.loads(_readiness_summary_for_assertion(prepared, target))
    newer_summary["target_fetched_at"] = (NOW - timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="invalid stored ready preparation evidence"):
        refresh_ready_drawing_preparation_evidence(
            session_factory,
            drawing_id=1,
            drawing_fingerprint=prepared.drawing_fingerprint,
            provider="api-sports",
            readiness_summary=json.dumps(newer_summary),
        )


@pytest.mark.parametrize(
    "invalid_probabilities",
    [
        (0.42, 0.30),
        (0.42, 0.30, 0.30),
    ],
)
def test_prepare_reused_pins_reject_invalid_probabilities_without_partial_update(
    session_factory,
    invalid_probabilities,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(
                    f"Home {order}", f"Away {order}"
                ).__dict__,
                "event_id": 100 + order,
                "event_order": order,
            }
        )
        for order in range(15)
    )
    target = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=2), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )
    prepared = prepare_drawing(
        target,
        candidates,
        session_factory=session_factory,
        event_contexts={
            order: ResolutionContext("api-sports", league="Premier League")
            for order in range(15)
        },
    )
    with session_factory() as session:
        before = session.scalar(select(DrawingPreparation))
        assert before is not None
        before_summary = before.readiness_summary
        before_updated_at = before.updated_at
    before_pin_hashes = tuple(pin.pin_hash for pin in prepared.pins)

    object.__setattr__(
        target.events[-1], "bk_probabilities", invalid_probabilities
    )
    object.__setattr__(target, "fetched_at", NOW - timedelta(hours=1))

    with pytest.raises(ValueError, match="preparation probabilities"):
        prepare_drawing(
            target,
            candidates,
            session_factory=session_factory,
            event_contexts={
                order: ResolutionContext("api-sports", league="Premier League")
                for order in range(15)
            },
        )

    with session_factory() as session:
        after = session.scalar(select(DrawingPreparation))
        assert after is not None
        assert after.readiness_summary == before_summary
        assert after.updated_at == before_updated_at
        assert tuple(
            session.scalars(
                select(DrawingEventPin.pin_hash).order_by(
                    DrawingEventPin.event_order
                )
            )
        ) == before_pin_hashes


def test_prepare_default_context_rejects_same_pair_from_wrong_league(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}", starts_at=NOW).__dict__,
                "event_id": 100 + order,
                "event_order": order,
                "championship": "Бразилия. Серия A",
            }
        )
        for order in range(15)
    )
    drawing = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=1), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            starts_at=NOW,
            league="Serie B" if order == 0 else "Serie A",
            country="Brazil",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )

    result = prepare_drawing(
        drawing,
        candidates,
        session_factory=session_factory,
    )

    assert result.status == "unresolved"
    assert result.mapped_count == 0
    assert result.unresolved_event_orders == (0,)
    assert result.events[0].status != "matched"
    assert result.events[0].provider_fixture_id is None
    assert result.pins == ()
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0


def test_failed_required_date_blocks_otherwise_complete_preparation(
    session_factory,
):
    events = tuple(
        TargetEvent(
            **{
                **_target(f"Home {order}", f"Away {order}", starts_at=NOW).__dict__,
                "event_id": 200 + order,
                "event_order": order,
                "championship": "Бразилия. Серия A",
            }
        )
        for order in range(15)
    )
    drawing = TargetDrawing(1, 1, NOW, NOW - timedelta(hours=1), events)
    candidates = tuple(
        _candidate(
            str(order),
            f"Home {order}",
            f"Away {order}",
            starts_at=NOW,
            league="Serie A",
            country="Brazil",
            home_id=f"home-{order}",
            away_id=f"away-{order}",
        )
        for order in range(15)
    )

    result = prepare_drawing(
        drawing,
        candidates,
        session_factory=session_factory,
        schedule_diagnostics=(
            {
                "sport": "football",
                "date": NOW.date().isoformat(),
                "status": "failed",
                "reason": "required date unavailable",
            },
        ),
    )

    assert all(event.status == "matched" for event in result.events)
    assert result.status == "unresolved"
    assert result.mapped_count == 0
    assert result.unresolved_event_orders == tuple(range(15))
    assert result.pins == ()
    with session_factory() as session:
        assert session.scalar(select(func.count(DrawingEventPin.id))) == 0
