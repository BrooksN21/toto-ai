from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.sports_stats.domain import (
    CompletedFixture,
    SourceEvidence,
    build_event_snapshot,
    build_run_snapshot,
)
from toto_ai.sports_stats.features import build_team_window

UTC = timezone.utc


def source(at: datetime) -> SourceEvidence:
    return SourceEvidence(
        provider="fake",
        endpoint="/fixtures",
        request_fingerprint="a" * 64,
        payload_sha256="b" * 64,
        fetched_at=at,
    )


def fixture(
    fixture_id: str,
    starts_at: datetime,
    home: str,
    away: str,
    goals: tuple[int, int],
) -> CompletedFixture:
    return CompletedFixture(
        provider_fixture_id=fixture_id,
        starts_at=starts_at,
        status="FT",
        home_team_id=home,
        away_team_id=away,
        home_goals=goals[0],
        away_goals=goals[1],
        source=source(datetime(2026, 7, 20, tzinfo=UTC)),
    )


def test_team_window_filters_target_and_future_and_aggregates_home_away():
    target = datetime(2026, 7, 30, 18, tzinfo=UTC)
    as_of = datetime(2026, 7, 29, 10, tzinfo=UTC)
    fixtures = (
        fixture("future", datetime(2026, 7, 29, 12, tzinfo=UTC), "10", "30", (9, 0)),
        fixture("target", target, "10", "20", (0, 0)),
        fixture("3", datetime(2026, 7, 27, tzinfo=UTC), "30", "10", (0, 2)),
        fixture("2", datetime(2026, 7, 25, tzinfo=UTC), "10", "40", (1, 1)),
        fixture("1", datetime(2026, 7, 20, tzinfo=UTC), "10", "50", (0, 1)),
    )

    window = build_team_window(
        team_id="10",
        fixtures=fixtures,
        requested_count=10,
        target_starts_at=target,
        target_fixture_id="target",
        as_of=as_of,
    )

    assert window.fixture_ids == ("3", "2", "1")
    assert (window.wins, window.draws, window.losses) == (1, 1, 1)
    assert (window.goals_for, window.goals_against) == (3, 2)
    assert (window.home_played, window.away_played) == (2, 1)
    assert (window.home_wins, window.home_draws, window.home_losses) == (0, 1, 1)
    assert (window.away_wins, window.away_draws, window.away_losses) == (1, 0, 0)
    assert window.last5_form_points == 4
    assert window.rest_days == 3.75


def test_team_window_is_unknown_when_no_requested_team_history_exists():
    target = datetime(2026, 7, 30, 18, tzinfo=UTC)

    window = build_team_window(
        team_id="10",
        fixtures=(
            fixture(
                "unrelated",
                datetime(2026, 7, 20, tzinfo=UTC),
                "30",
                "40",
                (1, 0),
            ),
        ),
        requested_count=10,
        target_starts_at=target,
        target_fixture_id="target",
        as_of=datetime(2026, 7, 29, 10, tzinfo=UTC),
    )

    assert window is None


def test_event_and_run_hashes_are_canonical_and_content_sensitive():
    captured = datetime(2026, 7, 29, 9, tzinfo=UTC)
    as_of = captured + timedelta(minutes=2)
    deadline = datetime(2026, 7, 29, 12, tzinfo=UTC)
    events = tuple(
        build_event_snapshot(
            schema_version=1,
            drawing_id=1,
            drawing_number=5000,
            drawing_fingerprint="c" * 64,
            event_id=str(order + 1),
            event_order=order,
            sport="football",
            provider="fake",
            status="missing",
            missing_reasons=("provider_error",),
            captured_at=captured,
            as_of=as_of,
            deadline=deadline,
            target_starts_at=deadline + timedelta(hours=1),
            provider_fixture_id=None,
            canonical_home_team_id=None,
            canonical_away_team_id=None,
            provider_home_team_id=None,
            provider_away_team_id=None,
            league_id=None,
            season=None,
            home_window=None,
            away_window=None,
            home_standing=None,
            away_standing=None,
            source_evidence=(),
        )
        for order in range(15)
    )
    first = build_run_snapshot(
        drawing_id=1,
        drawing_number=5000,
        drawing_fingerprint="c" * 64,
        provider="fake",
        requested_history_size=10,
        captured_at=captured,
        as_of=as_of,
        deadline=deadline,
        events=events,
        requests_made=0,
        cache_hits=0,
    )
    second = build_run_snapshot(
        drawing_id=1,
        drawing_number=5000,
        drawing_fingerprint="c" * 64,
        provider="fake",
        requested_history_size=10,
        captured_at=captured,
        as_of=as_of,
        deadline=deadline,
        events=events,
        requests_made=0,
        cache_hits=0,
    )

    assert first == second
    assert first.run_id == first.content_sha256
    assert len({event.feature_sha256 for event in events}) == 15

    replayed = build_event_snapshot(
        **{
            **{
                key: value
                for key, value in events[0].__dict__.items()
                if key != "feature_sha256"
            },
            "captured_at": captured + timedelta(minutes=10),
            "as_of": as_of + timedelta(minutes=10),
        }
    )
    assert replayed.feature_sha256 == events[0].feature_sha256


def test_non_complete_feature_requires_explicit_missing_reason():
    captured = datetime(2026, 7, 29, 9, tzinfo=UTC)
    with pytest.raises(ValueError, match="requires missing reasons"):
        build_event_snapshot(
            schema_version=1,
            drawing_id=1,
            drawing_number=5000,
            drawing_fingerprint="c" * 64,
            event_id="1",
            event_order=0,
            sport="football",
            provider="fake",
            status="missing",
            missing_reasons=(),
            captured_at=captured,
            as_of=captured,
            deadline=captured + timedelta(hours=1),
            target_starts_at=captured + timedelta(hours=2),
            provider_fixture_id=None,
            canonical_home_team_id=None,
            canonical_away_team_id=None,
            provider_home_team_id=None,
            provider_away_team_id=None,
            league_id=None,
            season=None,
            home_window=None,
            away_window=None,
            home_standing=None,
            away_standing=None,
            source_evidence=(),
        )


def test_run_rejects_any_event_identity_or_boundary_mismatch():
    captured = datetime(2026, 7, 29, 9, tzinfo=UTC)
    as_of = captured + timedelta(minutes=2)
    deadline = datetime(2026, 7, 29, 12, tzinfo=UTC)
    events = tuple(
        build_event_snapshot(
            schema_version=1,
            drawing_id=1,
            drawing_number=5000,
            drawing_fingerprint="c" * 64,
            event_id=str(order + 1),
            event_order=order,
            sport="football",
            provider="fake",
            status="missing",
            missing_reasons=("provider_error",),
            captured_at=captured,
            as_of=as_of,
            deadline=deadline,
            target_starts_at=deadline + timedelta(hours=1),
            provider_fixture_id=None,
            canonical_home_team_id=None,
            canonical_away_team_id=None,
            provider_home_team_id=None,
            provider_away_team_id=None,
            league_id=None,
            season=None,
            home_window=None,
            away_window=None,
            home_standing=None,
            away_standing=None,
            source_evidence=(),
        )
        for order in range(15)
    )
    mismatches = (
        {"drawing_number": 5001},
        {"drawing_fingerprint": "d" * 64},
        {"provider": "other"},
        {"captured_at": captured + timedelta(seconds=1)},
        {"as_of": as_of + timedelta(seconds=1)},
        {"deadline": deadline + timedelta(seconds=1)},
    )

    for values in mismatches:
        bad_events = (replace(events[0], **values), *events[1:])
        with pytest.raises(ValueError, match="event .* mismatch"):
            build_run_snapshot(
                drawing_id=1,
                drawing_number=5000,
                drawing_fingerprint="c" * 64,
                provider="fake",
                requested_history_size=10,
                captured_at=captured,
                as_of=as_of,
                deadline=deadline,
                events=bad_events,
                requests_made=0,
                cache_hits=0,
            )
