import math
from datetime import datetime, timezone
from types import SimpleNamespace

from toto_ai.sports_stats.probabilities import (
    ShadowEventProbability,
    SportsShadowArtifact,
)
from toto_ai.sports_stats.v2 import (
    SportsV2Config,
    build_sports_v2_shadow_artifact,
    project_event_v2,
)


def _window(*, home: bool):
    return SimpleNamespace(
        requested_count=10,
        fixture_count=10,
        goals_for=16 if home else 13,
        goals_against=10 if home else 14,
        home_played=5,
        home_wins=4,
        home_draws=1,
        home_losses=0,
        home_goals_for=10,
        home_goals_against=3,
        away_played=5,
        away_wins=1,
        away_draws=2,
        away_losses=2,
        away_goals_for=5,
        away_goals_against=8,
    )


def _feature(*, status="complete", sport="football", venue_games=5, order=3):
    home = _window(home=True)
    away = _window(home=False)
    home.home_played = venue_games
    away.away_played = venue_games
    return SimpleNamespace(
        event_order=order,
        event_id=str(1000 + order),
        status=status,
        sport=sport,
        home_window=home,
        away_window=away,
    )


def test_sports_v2_projection_is_normalized_and_capped():
    projection = project_event_v2(
        feature=_feature(),
        bk_probabilities=(0.45, 0.30, 0.25),
    )

    assert projection.status == "research_projection"
    assert projection.fallback_reason is None
    assert math.isclose(sum(projection.poisson_probabilities), 1.0)
    assert math.isclose(sum(projection.candidate_probabilities), 1.0)
    assert 0.0 < projection.blend_weight <= 0.20
    assert projection.expected_home_goals is not None
    assert projection.expected_away_goals is not None


def test_sports_v2_falls_back_when_venue_history_is_too_small():
    bk = (0.45, 0.30, 0.25)

    projection = project_event_v2(
        feature=_feature(venue_games=1),
        bk_probabilities=bk,
    )

    assert projection.status == "bk_fallback"
    assert projection.fallback_reason == "insufficient_venue_history"
    assert projection.candidate_probabilities == bk
    assert projection.blend_weight == 0.0


def test_sports_v2_shrinks_strong_market_disagreement():
    feature = _feature()
    config = SportsV2Config(disagreement_limit=0.20)

    projection = project_event_v2(
        feature=feature,
        bk_probabilities=(0.05, 0.10, 0.85),
        config=config,
    )

    assert projection.disagreement >= config.disagreement_limit
    assert projection.blend_weight == 0.0
    assert projection.candidate_probabilities == (0.05, 0.10, 0.85)


def test_sports_v2_artifact_preserves_identity_and_base_fallbacks():
    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    features = tuple(_feature(order=order) for order in range(15))
    events = tuple(
        ShadowEventProbability(
            event_id=feature.event_id,
            event_order=order,
            bk_probabilities=(0.45, 0.30, 0.25),
            sports_probabilities=(0.50, 0.30, 0.20),
            candidate_blend_probabilities=(0.46, 0.30, 0.24),
            probability_source=(
                "totobrief_bk_fallback" if order == 4 else "sports_shadow"
            ),
            blend_weight=0.0 if order == 4 else 0.1,
            fallback_reason="target_fixture_missing" if order == 4 else None,
            features={},
            provenance={},
        )
        for order, feature in enumerate(features)
    )
    base = SportsShadowArtifact(
        schema_version=1,
        status="NOT_ACTIVATED",
        model_status="EXPERIMENTAL_UNTRAINED",
        model_definition="v1",
        drawing_id=12083,
        drawing_number=4992,
        drawing_fingerprint="a" * 64,
        generated_at=now,
        as_of=now,
        deadline=datetime(2026, 8, 30, 18, tzinfo=timezone.utc),
        snapshot_run_id="b" * 64,
        snapshot_content_sha256="b" * 64,
        authority_status="FROZEN_PRE_AS_OF",
        authority_fetched_at=now,
        authoritative_target_fingerprint="a" * 64,
        bk_snapshot_sha256="c" * 64,
        sports_coverage_count=14,
        fallback_count=1,
        validation_failures=(),
        events=events,
        artifact_sha256="d" * 64,
    )
    snapshot = SimpleNamespace(
        drawing_id=12083,
        drawing_number=4992,
        drawing_fingerprint="a" * 64,
        content_sha256="b" * 64,
        events=features,
    )

    artifact = build_sports_v2_shadow_artifact(
        snapshot=snapshot,
        base_artifact=base,
    )

    assert artifact.model_status == "EXPERIMENTAL_UNTRAINED_V2"
    assert artifact.sports_coverage_count == 14
    assert artifact.fallback_count == 1
    assert artifact.events[4].fallback_reason == "target_fixture_missing"
    assert artifact.events[4].candidate_blend_probabilities == (0.45, 0.30, 0.25)
    assert artifact.events[0].provenance["sports_model"].startswith(
        "sports-analytics-v2"
    )
    assert artifact.artifact_sha256 != "0" * 64
