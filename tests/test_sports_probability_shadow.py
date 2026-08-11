from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import log

from toto_ai.db.models import Event, Quote
from toto_ai.db.session import get_session_factory, init_db
from toto_ai.external_odds.domain import TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    SourceEvidence,
    build_event_snapshot,
    build_run_snapshot,
    canonical_sha256,
)
from toto_ai.sports_stats.features import build_team_window
from toto_ai.sports_stats.probabilities import (
    build_shadow_probability_artifact,
    load_shadow_probability_artifact,
    write_shadow_probability_artifact,
)
from toto_ai.sports_stats.shadow_operation import (
    evaluate_stored_sports_probability_shadow,
)

UTC = timezone.utc
CAPTURED = datetime(2026, 8, 1, 9, tzinfo=UTC)
AS_OF = CAPTURED + timedelta(minutes=5)
DEADLINE = CAPTURED + timedelta(hours=3)
START = DEADLINE + timedelta(hours=1)


def _evidence(order: int) -> SourceEvidence:
    return SourceEvidence(
        provider="api-sports",
        endpoint="/fixtures",
        request_fingerprint=f"{order + 1:064x}",
        payload_sha256=f"{order + 101:064x}",
        fetched_at=CAPTURED,
    )


def _fixture(
    order: int,
    suffix: str,
    home: str,
    away: str,
    goals: tuple[int, int],
) -> CompletedFixture:
    return CompletedFixture(
        provider_fixture_id=f"history-{order}-{suffix}",
        starts_at=CAPTURED - timedelta(days=2 + int(suffix)),
        status="FT",
        home_team_id=home,
        away_team_id=away,
        home_goals=goals[0],
        away_goals=goals[1],
        source=_evidence(order),
    )


def _target_pins_snapshot():
    events = tuple(
        TargetEvent(
            drawing_id=77,
            drawing_number=5077,
            event_id=7000 + order,
            event_order=order,
            sport="football",
            championship="Test",
            starts_at=START + timedelta(minutes=order),
            deadline=DEADLINE,
            home_team=f"Home {order}",
            away_team=f"Away {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.5, 0.3, 0.2),
        )
        for order in range(15)
    )
    target = TargetDrawing(
        drawing_id=77,
        drawing_number=5077,
        deadline=DEADLINE,
        fetched_at=AS_OF,
        events=events,
    )
    fingerprint = target_fingerprint(
        target.drawing_id,
        target.drawing_number,
        target.deadline,
        target.events,
    )
    pins = tuple(
        DrawingEventPinRecord(
            id=order + 1,
            drawing_id=77,
            drawing_fingerprint=fingerprint,
            target_event_id=str(7000 + order),
            event_order=order,
            provider="api-sports",
            canonical_home_team_id=9000 + order * 2,
            canonical_away_team_id=9001 + order * 2,
            provider_home_team_id=str(8000 + order * 2),
            provider_away_team_id=str(8001 + order * 2),
            provider_fixture_id=str(6000 + order),
            starts_at=(START + timedelta(minutes=order)).isoformat(),
            collection_id=None,
            provenance={"orientation": "same"},
            pin_hash=f"{order + 201:064x}",
            status="valid",
            created_at=CAPTURED.isoformat(),
            invalidated_at=None,
            invalidation_reason=None,
        )
        for order in range(15)
    )
    event_snapshots = []
    for order in range(15):
        home_id = str(8000 + order * 2)
        away_id = str(8001 + order * 2)
        if order == 1:
            home_window = away_window = None
            status = "missing"
            reasons = ("no_completed_fixtures",)
            sources = ()
        else:
            home_fixtures = (
                _fixture(order, "1", home_id, f"h-opponent-{order}", (2, 0)),
                _fixture(order, "2", f"h-opponent-2-{order}", home_id, (1, 1)),
            )
            away_fixtures = (
                _fixture(order, "3", f"a-opponent-{order}", away_id, (1, 0)),
                _fixture(order, "4", away_id, f"a-opponent-2-{order}", (0, 0)),
            )
            home_window = build_team_window(
                team_id=home_id,
                fixtures=home_fixtures,
                requested_count=10,
                target_starts_at=START + timedelta(minutes=order),
                target_fixture_id=str(6000 + order),
                as_of=AS_OF,
            )
            away_window = build_team_window(
                team_id=away_id,
                fixtures=away_fixtures,
                requested_count=10,
                target_starts_at=START + timedelta(minutes=order),
                target_fixture_id=str(6000 + order),
                as_of=AS_OF,
            )
            status = "partial"
            reasons = ("standings_unavailable",)
            sources = (_evidence(order),)
        event_snapshots.append(
            build_event_snapshot(
                schema_version=1,
                drawing_id=77,
                drawing_number=5077,
                drawing_fingerprint=fingerprint,
                event_id=str(7000 + order),
                event_order=order,
                sport="football",
                provider="api-sports",
                status=status,
                missing_reasons=reasons,
                captured_at=CAPTURED,
                as_of=AS_OF,
                deadline=DEADLINE,
                target_starts_at=START + timedelta(minutes=order),
                provider_fixture_id=str(6000 + order),
                canonical_home_team_id=9000 + order * 2,
                canonical_away_team_id=9001 + order * 2,
                provider_home_team_id=home_id,
                provider_away_team_id=away_id,
                league_id="39",
                season=2026,
                home_window=home_window,
                away_window=away_window,
                home_standing=None,
                away_standing=None,
                source_evidence=sources,
            )
        )
    snapshot = build_run_snapshot(
        drawing_id=77,
        drawing_number=5077,
        drawing_fingerprint=fingerprint,
        provider="api-sports",
        requested_history_size=10,
        captured_at=CAPTURED,
        as_of=AS_OF,
        deadline=DEADLINE,
        events=tuple(event_snapshots),
        requests_made=0,
        cache_hits=30,
    )
    return target, pins, snapshot


def _replace_feature(feature, **changes):
    candidate = replace(feature, feature_sha256="0" * 64, **changes)
    return replace(
        candidate,
        feature_sha256=canonical_sha256(candidate.canonical_payload()),
    )


def test_shadow_artifact_uses_sports_history_but_never_activates():
    target, pins, snapshot = _target_pins_snapshot()

    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=pins,
        as_of=AS_OF,
    )

    assert artifact.status == "NOT_ACTIVATED"
    assert artifact.model_status == "EXPERIMENTAL_UNTRAINED"
    assert artifact.sports_coverage_count == 14
    assert artifact.fallback_count == 1
    assert artifact.events[0].probability_source == "sports_shadow"
    assert artifact.events[0].sports_probabilities != (0.5, 0.3, 0.2)
    assert artifact.events[0].candidate_blend_probabilities != (
        0.5,
        0.3,
        0.2,
    )
    assert artifact.events[0].features["home_fixture_count"] == 2
    assert artifact.events[0].provenance["feature_sha256"] == (
        snapshot.events[0].feature_sha256
    )
    assert artifact.events[1].fallback_reason == "sports_history_missing"
    assert artifact.events[1].sports_probabilities == (0.5, 0.3, 0.2)
    assert artifact.events[1].candidate_blend_probabilities == (0.5, 0.3, 0.2)


def test_shadow_probabilities_use_home_and_away_venue_windows():
    target, pins, snapshot = _target_pins_snapshot()
    original = build_shadow_probability_artifact(
        target=target, snapshot=snapshot, pins=pins, as_of=AS_OF
    )
    feature = snapshot.events[0]
    assert feature.home_window is not None and feature.away_window is not None
    changed_home = replace(
        feature.home_window,
        home_wins=0,
        home_draws=0,
        home_losses=feature.home_window.home_played,
    )
    changed_away = replace(
        feature.away_window,
        away_wins=feature.away_window.away_played,
        away_draws=0,
        away_losses=0,
    )
    changed_feature = _replace_feature(
        feature,
        home_window=changed_home,
        away_window=changed_away,
    )
    changed_snapshot = build_run_snapshot(
        drawing_id=snapshot.drawing_id,
        drawing_number=snapshot.drawing_number,
        drawing_fingerprint=snapshot.drawing_fingerprint,
        provider=snapshot.provider,
        requested_history_size=snapshot.requested_history_size,
        captured_at=snapshot.captured_at,
        as_of=snapshot.as_of,
        deadline=snapshot.deadline,
        events=(changed_feature, *snapshot.events[1:]),
        requests_made=snapshot.requests_made,
        cache_hits=snapshot.cache_hits,
    )
    changed = build_shadow_probability_artifact(
        target=target, snapshot=changed_snapshot, pins=pins, as_of=AS_OF
    )

    assert original.events[0].features["model_feature_scope"] == "venue"
    assert original.events[0].provenance["model_feature_scope"] == "venue"
    assert original.events[0].provenance["aggregate_fallback_used"] is False
    assert (
        original.events[0].provenance["sports_model"]
        == "jeffreys_smoothed_venue_wdl"
    )
    assert changed.events[0].sports_probabilities != (
        original.events[0].sports_probabilities
    )
    assert (
        changed.events[0].sports_probabilities[2]
        > changed.events[0].sports_probabilities[0]
    )


def test_shadow_falls_back_when_required_venue_history_is_unavailable():
    target, pins, snapshot = _target_pins_snapshot()
    feature = snapshot.events[0]
    assert feature.home_window is not None
    no_home_venue = replace(
        feature.home_window,
        home_played=0,
        home_wins=0,
        home_draws=0,
        home_losses=0,
        home_goals_for=0,
        home_goals_against=0,
        away_played=feature.home_window.fixture_count,
        away_wins=feature.home_window.wins,
        away_draws=feature.home_window.draws,
        away_losses=feature.home_window.losses,
    )
    changed_feature = _replace_feature(feature, home_window=no_home_venue)
    changed_snapshot = build_run_snapshot(
        drawing_id=snapshot.drawing_id,
        drawing_number=snapshot.drawing_number,
        drawing_fingerprint=snapshot.drawing_fingerprint,
        provider=snapshot.provider,
        requested_history_size=snapshot.requested_history_size,
        captured_at=snapshot.captured_at,
        as_of=snapshot.as_of,
        deadline=snapshot.deadline,
        events=(changed_feature, *snapshot.events[1:]),
        requests_made=snapshot.requests_made,
        cache_hits=snapshot.cache_hits,
    )
    artifact = build_shadow_probability_artifact(
        target=target, snapshot=changed_snapshot, pins=pins, as_of=AS_OF
    )

    assert artifact.events[0].fallback_reason == "venue_history_missing"
    assert artifact.events[0].probability_source == "totobrief_bk_fallback"
    assert artifact.events[0].features["model_feature_scope"] == "non_venue_unavailable"
    assert (
        artifact.events[0].provenance["model_feature_scope"]
        == "non_venue_unavailable"
    )
    assert artifact.events[0].provenance["aggregate_fallback_used"] is False
    assert artifact.events[0].provenance["sports_model"] is None


def test_shadow_artifact_falls_back_per_event_on_orientation_mismatch():
    target, pins, snapshot = _target_pins_snapshot()
    bad_pin = replace(
        pins[0],
        provider_home_team_id=pins[0].provider_away_team_id,
        provider_away_team_id=pins[0].provider_home_team_id,
    )

    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=(bad_pin, *pins[1:]),
        as_of=AS_OF,
    )

    assert artifact.events[0].fallback_reason == "orientation_mismatch"
    assert artifact.events[0].candidate_blend_probabilities == (
        0.5,
        0.3,
        0.2,
    )
    assert artifact.events[2].probability_source == "sports_shadow"


def test_shadow_artifact_requires_explicit_same_orientation():
    target, pins, snapshot = _target_pins_snapshot()
    missing_orientation = replace(pins[0], provenance={"orientation": None})

    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=(missing_orientation, *pins[1:]),
        as_of=AS_OF,
    )

    assert artifact.events[0].fallback_reason == "orientation_missing"
    assert artifact.events[0].probability_source == "totobrief_bk_fallback"


def test_shadow_artifact_fails_closed_for_global_fingerprint_mismatch():
    target, pins, snapshot = _target_pins_snapshot()
    changed_events = (
        replace(target.events[0], home_team="Changed Home"),
        *target.events[1:],
    )
    changed_target = replace(target, events=changed_events)

    artifact = build_shadow_probability_artifact(
        target=changed_target,
        snapshot=snapshot,
        pins=pins,
        as_of=AS_OF,
    )

    assert "drawing_fingerprint_mismatch" in artifact.validation_failures
    assert (
        "authoritative_target_fingerprint_mismatch"
        in artifact.validation_failures
    )
    assert artifact.sports_coverage_count == 0
    assert artifact.fallback_count == 15
    assert {event.fallback_reason for event in artifact.events} == {
        "drawing_fingerprint_mismatch"
    }


def test_frozen_artifact_binds_authoritative_target_and_embedded_bk(tmp_path):
    target, pins, snapshot = _target_pins_snapshot()
    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=pins,
        as_of=AS_OF,
    )

    path = write_shadow_probability_artifact(artifact, report_dir=tmp_path)
    loaded = load_shadow_probability_artifact(path)

    assert loaded == artifact
    assert loaded.authority_status == "FROZEN_PRE_AS_OF"
    assert loaded.authority_fetched_at == target.fetched_at
    assert loaded.authoritative_target_fingerprint == snapshot.drawing_fingerprint
    assert loaded.bk_snapshot_sha256
    assert path.name.endswith(f"{artifact.artifact_sha256[:16]}.json")


def test_missing_independent_authority_fails_closed():
    _target, pins, snapshot = _target_pins_snapshot()

    from toto_ai.sports_stats.probabilities import (
        build_shadow_probability_artifact_from_snapshot,
    )

    artifact = build_shadow_probability_artifact_from_snapshot(
        snapshot=snapshot,
        pins=pins,
        bk_probabilities=((0.5, 0.3, 0.2),) * 15,
        as_of=AS_OF,
        expected_fingerprint=snapshot.drawing_fingerprint,
    )

    assert "authoritative_target_unavailable" in artifact.validation_failures
    assert artifact.sports_coverage_count == 0


def test_late_authoritative_target_fails_closed():
    target, pins, snapshot = _target_pins_snapshot()
    late_target = replace(target, fetched_at=AS_OF + timedelta(seconds=1))

    artifact = build_shadow_probability_artifact(
        target=late_target,
        snapshot=snapshot,
        pins=pins,
        as_of=AS_OF,
    )

    assert "authoritative_target_unavailable" in artifact.validation_failures
    assert artifact.authority_status == "UNAVAILABLE"
    assert artifact.sports_coverage_count == 0


def test_oos_evaluator_uses_frozen_artifact_bk_not_mutable_quotes(tmp_path):
    target, pins, snapshot = _target_pins_snapshot()
    artifact = build_shadow_probability_artifact(
        target=target,
        snapshot=snapshot,
        pins=pins,
        as_of=AS_OF,
    )
    report_dir = tmp_path / "reports"
    write_shadow_probability_artifact(artifact, report_dir=report_dir)
    engine = init_db(tmp_path / "toto.db")
    factory = get_session_factory(engine)
    with factory.begin() as session:
        for order in range(15):
            session.add(
                Event(
                    drawing_id=77,
                    event_order=order,
                    name=f"Home {order} - Away {order}",
                    championship="Test",
                    sport="football",
                    result="1",
                    result_status="finished",
                    score="1:0",
                )
            )
            session.add(
                Quote(
                    drawing_id=77,
                    event_order=order,
                    bk_win_1=1.0,
                    bk_draw=49.0,
                    bk_win_2=50.0,
                    pool_win_1=1.0,
                    pool_draw=49.0,
                    pool_win_2=50.0,
                )
            )

    result, _paths = evaluate_stored_sports_probability_shadow(
        db=str(tmp_path / "toto.db"),
        last=1,
        report_dir=str(report_dir),
        minimum_drawings=30,
        minimum_events=450,
        minimum_sports_coverage=0.70,
        calibration_tolerance=0.02,
    )

    assert result.metrics["bk"].log_loss == -log(0.5)
