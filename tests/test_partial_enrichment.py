import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from toto_ai.db.models import (
    Base,
    DrawingPinSet,
    DrawingPinSetItem,
    DrawingPreparation,
)
from toto_ai.ev.drawing import ev_input_from_payload
from toto_ai.external_odds.collection import (
    ScheduleDateResult,
    _match_targets_from_pins,
)
from toto_ai.external_odds.domain import ProviderEvent, TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.preparation import (
    _baseline_probability_input_sha256,
    preparation_probability_sha256,
    prepare_drawing,
)
from toto_ai.external_odds.schedule_evidence import (
    ScheduleEvidenceIntegrityError,
    load_schedule_evidence_ledger,
)
from toto_ai.external_odds.team_registry import (
    backfill_accepted_matches,
    load_ready_pin_set,
)

DEADLINE = datetime(2026, 8, 4, 15, tzinfo=timezone.utc)
FETCHED_AT = DEADLINE - timedelta(minutes=30)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def _target(
    *,
    missing_pool_order: int | None = None,
    number: int = 4965,
    drawing_id: int = 12004,
    event_id_base: int = 179163,
):
    return TargetDrawing(
        drawing_id=drawing_id,
        drawing_number=number,
        deadline=DEADLINE,
        fetched_at=FETCHED_AT,
        events=tuple(
            TargetEvent(
                drawing_id=drawing_id,
                drawing_number=number,
                event_id=event_id_base + order,
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


def _candidates(*, event_orders: tuple[int, ...] = tuple(range(13))):
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
        for order in event_orders
    )


def _seed(
    session_factory,
    *,
    drawing_id: int = 12004,
    event_id_base: int = 179163,
    event_orders: tuple[int, ...] = tuple(range(13)),
):
    assert backfill_accepted_matches(
        session_factory,
        [
            {
                "drawing_id": drawing_id,
                "target_event_id": event_id_base + order,
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
            for order in event_orders
        ],
    ) == len(event_orders) * 2


def _empty_ledger(tmp_path: Path) -> Path:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": FETCHED_AT.isoformat(),
                "observations": [],
            }
        ),
        encoding="utf-8",
    )
    return ledger


def _schedule_evidence_ledger(
    tmp_path: Path,
    target: TargetDrawing,
    *,
    event_orders: tuple[int, ...],
    reversed_orders: tuple[int, ...] = (),
    starts_at_offset: timedelta = timedelta(hours=2),
) -> Path:
    review = tmp_path / "review.md"
    review.write_text("reviewed official schedule", encoding="utf-8")
    review_sha256 = hashlib.sha256(review.read_bytes()).hexdigest()
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": FETCHED_AT.isoformat(),
                "observations": [
                    {
                        "observation_id": f"event-{event_order}",
                        "sport": "football",
                        "gender_age_class": "men-senior",
                        "competition_aliases": [
                            target.events[event_order].championship
                        ],
                        "home_entity": (
                            target.events[event_order].away_team
                            if event_order in reversed_orders
                            else target.events[event_order].home_team
                        ),
                        "home_aliases": [
                            target.events[event_order].away_team
                            if event_order in reversed_orders
                            else target.events[event_order].home_team
                        ],
                        "away_entity": (
                            target.events[event_order].home_team
                            if event_order in reversed_orders
                            else target.events[event_order].away_team
                        ),
                        "away_aliases": [
                            target.events[event_order].home_team
                            if event_order in reversed_orders
                            else target.events[event_order].away_team
                        ],
                        "starts_at": (
                            DEADLINE + starts_at_offset
                        ).isoformat(),
                        "status": "scheduled",
                        "conditional": False,
                        "reviewer": "test-reviewer",
                        "reviewed_at": FETCHED_AT.isoformat(),
                        "review_document": review.name,
                        "review_document_sha256": review_sha256,
                        "claims": [
                            {
                                "source_name": "official",
                                "role": "official",
                                "source_url": "https://example.test/schedule",
                            }
                        ],
                    }
                    for event_order in event_orders
                ],
            }
        ),
        encoding="utf-8",
    )
    return ledger


def test_existing_schedule_evidence_pin_survives_provider_plan_gap(
    session_factory,
    tmp_path: Path,
):
    target = _target()
    _seed(session_factory)
    ledger = _schedule_evidence_ledger(
        tmp_path,
        target,
        event_orders=(13, 14),
        starts_at_offset=timedelta(days=1, hours=2),
    )
    diagnostics = (
        {
            "sport": "football",
            "date": DEADLINE.date().isoformat(),
            "status": "success",
            "reason": None,
        },
        {
            "sport": "football",
            "date": (DEADLINE + timedelta(days=1)).date().isoformat(),
            "status": "failed",
            "reason": "provider plan gap",
        },
    )

    first = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        schedule_diagnostics=diagnostics,
        evaluated_at=FETCHED_AT,
    )
    repeated = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        schedule_diagnostics=diagnostics,
        evaluated_at=FETCHED_AT,
    )

    assert first.status == repeated.status == "ready"
    assert repeated.eligibility.status == "playable"
    assert repeated.baseline_only_event_orders == ()
    assert tuple(
        pin.effective_source_provider for pin in repeated.pins[13:]
    ) == ("schedule-evidence", "schedule-evidence")


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


def test_unused_schedule_evidence_ledger_does_not_bind_reviewed_hash(
    session_factory,
    tmp_path: Path,
):
    ledger = _empty_ledger(tmp_path)
    _seed(session_factory)

    result = prepare_drawing(
        _target(),
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=FETCHED_AT,
    )

    assert result.status == "ready"
    assert result.baseline_only_event_orders == (13, 14)
    assert all(
        pin.effective_source_provider != "schedule-evidence"
        for pin in result.pins
    )
    with session_factory() as session:
        pin_set = session.scalar(select(DrawingPinSet))
        assert pin_set is not None
        assert pin_set.reviewed_catalog_hash is None


def test_new_schedule_evidence_upgrades_existing_baseline_only_pin_set(
    session_factory,
    tmp_path: Path,
):
    target = _target()
    _seed(session_factory)
    morning = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
    )
    assert morning.eligibility.status == "unknown"
    assert morning.baseline_only_event_orders == (13, 14)

    ledger = _schedule_evidence_ledger(
        tmp_path,
        target,
        event_orders=(13, 14),
    )
    refreshed = prepare_drawing(
        target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=FETCHED_AT,
    )

    assert refreshed.status == "ready"
    assert refreshed.eligibility.status == "playable"
    assert refreshed.baseline_only_event_orders == ()
    assert tuple(
        pin.effective_source_provider for pin in refreshed.pins[13:]
    ) == ("schedule-evidence", "schedule-evidence")
    with session_factory() as session:
        pin_set = session.scalar(select(DrawingPinSet))
        assert pin_set is not None
        assert pin_set.reviewed_catalog_hash is not None


def test_drawing_4967_atomically_upgrades_four_persisted_baseline_pins(
    session_factory,
    tmp_path: Path,
):
    drawing_id = 12010
    event_id_base = 179253
    external_orders = tuple(order for order in range(15) if order not in {1, 8, 13, 14})
    target = _target(
        number=4967,
        drawing_id=drawing_id,
        event_id_base=event_id_base,
    )
    original_bk = tuple(event.bk_probabilities for event in target.events)
    _seed(
        session_factory,
        drawing_id=drawing_id,
        event_id_base=event_id_base,
        event_orders=external_orders,
    )
    morning = prepare_drawing(
        target,
        _candidates(event_orders=external_orders),
        session_factory=session_factory,
    )
    assert morning.status == "ready"
    assert morning.eligibility.status == "unknown"
    assert morning.baseline_only_event_orders == (1, 8, 13, 14)
    old_by_order = {pin.event_order: pin for pin in morning.pins}

    ledger = _schedule_evidence_ledger(
        tmp_path,
        target,
        event_orders=(1, 8, 13, 14),
        reversed_orders=(13,),
    )
    refreshed = prepare_drawing(
        target,
        tuple(
            replace(
                candidate,
                fetched_at=FETCHED_AT + timedelta(hours=1),
                payload_hash=f"refreshed-{candidate.payload_hash}",
            )
            for candidate in _candidates(event_orders=external_orders)
        ),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=FETCHED_AT,
    )

    assert refreshed.status == "ready"
    assert refreshed.eligibility.status == "playable"
    assert refreshed.baseline_only_event_orders == ()
    refreshed_by_order = {pin.event_order: pin for pin in refreshed.pins}
    assert tuple(
        refreshed_by_order[order].pin_hash for order in external_orders
    ) == tuple(old_by_order[order].pin_hash for order in external_orders)
    assert tuple(
        refreshed_by_order[order].effective_source_provider
        for order in (1, 8, 13, 14)
    ) == ("schedule-evidence",) * 4
    reversed_pin = refreshed_by_order[13]
    assert reversed_pin.provenance["orientation"] == "reversed"
    assert reversed_pin.provider_fixture_id is None
    assert reversed_pin.provider_home_team_id is None
    assert reversed_pin.provider_away_team_id is None
    assert (
        reversed_pin.canonical_home_team_id
        == old_by_order[13].canonical_home_team_id
    )
    assert (
        reversed_pin.canonical_away_team_id
        == old_by_order[13].canonical_away_team_id
    )
    assert tuple(event.bk_probabilities for event in target.events) == original_bk
    final_decisions = _match_targets_from_pins(
        target,
        (
            ScheduleDateResult(
                sport="football",
                requested_date=DEADLINE.date(),
                events=_candidates(event_orders=external_orders),
                error=None,
            ),
        ),
        refreshed.pins,
        observed_at=FETCHED_AT,
        schedule_evidence_ledger=load_schedule_evidence_ledger(ledger),
    )
    assert all(
        decision.decision.status == "matched"
        for decision in final_decisions.values()
    )
    assert final_decisions[13].decision.orientation == "reversed"
    assert final_decisions[13].decision.provider_event_id is None
    with session_factory() as session:
        pin_sets = tuple(session.scalars(select(DrawingPinSet)))
        assert len(pin_sets) == 1
        assert pin_sets[0].reviewed_catalog_hash is not None


def test_drawing_4967_rejects_ambiguous_schedule_ledger_without_mutation(
    session_factory,
    tmp_path: Path,
):
    drawing_id = 12010
    event_id_base = 179253
    external_orders = tuple(order for order in range(15) if order not in {1, 8, 13, 14})
    target = _target(
        number=4967,
        drawing_id=drawing_id,
        event_id_base=event_id_base,
    )
    _seed(
        session_factory,
        drawing_id=drawing_id,
        event_id_base=event_id_base,
        event_orders=external_orders,
    )
    morning = prepare_drawing(
        target,
        _candidates(event_orders=external_orders),
        session_factory=session_factory,
    )
    old_pin_set_id = morning.pins[0].pin_set_id

    ledger = _schedule_evidence_ledger(
        tmp_path,
        target,
        event_orders=(1, 8, 13, 14),
        reversed_orders=(13,),
    )
    document = json.loads(ledger.read_text(encoding="utf-8"))
    conflicting = {
        **document["observations"][0],
        "observation_id": "event-1-conflicting-kickoff",
        "starts_at": (DEADLINE + timedelta(hours=3)).isoformat(),
    }
    document["observations"].append(conflicting)
    ledger.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ScheduleEvidenceIntegrityError,
        match="conflicting authoritative schedule identity",
    ):
        prepare_drawing(
            target,
            _candidates(event_orders=external_orders),
            session_factory=session_factory,
            schedule_evidence_ledger=ledger,
            evaluated_at=FETCHED_AT,
        )

    with session_factory() as session:
        pin_set = session.scalar(select(DrawingPinSet))
        assert pin_set is not None
        assert pin_set.pin_set_id == old_pin_set_id
        assert session.scalar(select(func.count(DrawingPinSet.pin_set_id))) == 1
        assert session.scalar(select(func.count(DrawingPinSetItem.id))) == 15


def test_dynamic_bk_and_pool_refresh_reuses_pins_and_drives_latest_ev_input(
    session_factory,
    tmp_path: Path,
):
    _seed(session_factory)
    ledger = _empty_ledger(tmp_path)
    morning_target = _target()
    morning = prepare_drawing(
        morning_target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=FETCHED_AT,
    )
    morning_pin_hashes = tuple(pin.pin_hash for pin in morning.pins)
    evening_target = replace(
        morning_target,
        fetched_at=FETCHED_AT + timedelta(hours=1),
        events=tuple(
            replace(
                event,
                bk_probabilities=(0.29, 0.29, 0.42),
                pool_probabilities=(0.2, 0.4, 0.4),
            )
            if event.event_order == 13
            else replace(event, pool_probabilities=(0.2, 0.4, 0.4))
            for event in morning_target.events
        ),
    )

    evening = prepare_drawing(
        evening_target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=evening_target.fetched_at,
    )

    assert evening.status == "ready"
    assert tuple(pin.pin_hash for pin in evening.pins) == morning_pin_hashes
    with session_factory() as session:
        preparation = session.scalar(select(DrawingPreparation))
        assert preparation is not None
        summary = json.loads(preparation.readiness_summary)
    assert summary["target_fetched_at"] == evening_target.fetched_at.isoformat()
    assert summary["probability_input_sha256"] == preparation_probability_sha256(
        tuple(event.bk_probabilities for event in evening_target.events)
    )
    assert summary["baseline_probability_input_sha256"] == (
        _baseline_probability_input_sha256(evening_target)
    )
    assert summary["probability_outcome_order"] == ["1", "X", "2"]
    assert summary["market_evidence_version"] == 2
    assert len(summary["market_evidence_history"]) == 2

    decisions = _match_targets_from_pins(
        evening_target,
        (
            ScheduleDateResult(
                sport="football",
                requested_date=(DEADLINE + timedelta(hours=2)).date(),
                events=_candidates(),
                error=None,
            ),
        ),
        evening.pins,
        observed_at=evening_target.fetched_at,
    )
    assert tuple(decisions) == tuple(range(15))
    assert all(item.decision.status == "matched" for item in decisions.values())

    payload = {
        "data": {
            "id": evening_target.drawing_id,
            "number": evening_target.drawing_number,
            "pool_sum": 3_000_000,
            "jackpot": 0,
            "events": [
                {
                    "id": event.event_id,
                    "order": event.event_order,
                    "quotes": {
                        "bk_win_1": 29 if event.event_order == 13 else 40,
                        "bk_draw": 29 if event.event_order == 13 else 30,
                        "bk_win_2": 42 if event.event_order == 13 else 30,
                        "pool_win_1": 20,
                        "pool_draw": 40,
                        "pool_win_2": 40,
                    },
                }
                for event in evening_target.events
            ],
        }
    }
    ev_input = ev_input_from_payload(
        payload,
        fetched_at=evening_target.fetched_at.isoformat(),
        stake=30,
        prize_fund_factor=1.0,
        possible_winnings=None,
        jackpot_override=None,
    )
    assert ev_input.crowd_probabilities[13] == pytest.approx(
        (0.2, 0.4, 0.4), abs=5e-6
    )
    assert ev_input.true_probabilities[13] == pytest.approx(
        (0.29, 0.29, 0.42), abs=5e-6
    )


def test_participant_identity_drift_stays_fail_closed(
    session_factory,
    tmp_path: Path,
):
    _seed(session_factory)
    ledger = _empty_ledger(tmp_path)
    morning_target = _target()
    prepared = prepare_drawing(
        morning_target,
        _candidates(),
        session_factory=session_factory,
        schedule_evidence_ledger=ledger,
        evaluated_at=FETCHED_AT,
    )
    changed = replace(
        morning_target,
        fetched_at=FETCHED_AT + timedelta(hours=1),
        events=(
            replace(morning_target.events[0], home_team="Different Home"),
            *morning_target.events[1:],
        ),
    )

    changed_fingerprint = target_fingerprint(
        changed.drawing_id,
        changed.drawing_number,
        changed.deadline,
        changed.events,
    )
    assert changed_fingerprint != prepared.drawing_fingerprint
    with pytest.raises(ValueError, match="ready drawing preparation is missing"):
        load_ready_pin_set(
            session_factory,
            drawing_id=changed.drawing_id,
            drawing_fingerprint=changed_fingerprint,
        )


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
