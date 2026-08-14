import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from toto_ai.external_odds.api_sports import ProviderPlanUnavailable
from toto_ai.external_odds.domain import QuotaState, TargetDrawing, TargetEvent
from toto_ai.external_odds.eligibility import target_fingerprint
from toto_ai.external_odds.team_registry import DrawingEventPinRecord
from toto_ai.sports_stats.collection import collect_sports_stats
from toto_ai.sports_stats.domain import (
    CompletedFixture,
    ProviderFixtureContext,
    SourceEvidence,
    StandingRow,
)
from toto_ai.sports_stats.reports import write_sports_stats_reports

UTC = timezone.utc


class FakeProvider:
    provider_name = "api-sports"
    quota_state = QuotaState(100, 90, 10, 9)
    requests_made = 4
    cache_hits = 1

    def __init__(
        self,
        *,
        fail_standings=False,
        fail_history_with_plan=False,
        empty_history=False,
    ):
        self.fail_standings = fail_standings
        self.fail_history_with_plan = fail_history_with_plan
        self.empty_history = empty_history
        self.history_calls = []

    def fetch_target_fixture(self, fixture_id, **kwargs):
        order = int(fixture_id) - 1000
        return ProviderFixtureContext(
            provider_fixture_id=fixture_id,
            starts_at=TARGET_START + timedelta(minutes=order),
            home_team_id=str(2000 + order * 2),
            away_team_id=str(2001 + order * 2),
            league_id="39",
            season=2026,
            standings_supported=True,
            source=evidence(),
        )

    def fetch_completed_fixtures(
        self,
        team_id,
        season,
        *,
        cutoff,
        limit,
        target_fixture_id,
        **kwargs,
    ):
        self.history_calls.append((team_id, season))
        if self.fail_history_with_plan:
            raise ProviderPlanUnavailable("not available")
        if self.empty_history:
            return ()
        return (
            CompletedFixture(
                provider_fixture_id=f"old-{team_id}",
                starts_at=cutoff - timedelta(days=4),
                status="FT",
                home_team_id=team_id,
                away_team_id=f"opponent-{team_id}",
                home_goals=2,
                away_goals=1,
                source=evidence(),
            ),
        )

    def fetch_standings(self, league_id, season, **kwargs):
        if self.fail_standings:
            raise RuntimeError("unavailable")
        return tuple(
            StandingRow(
                team_id=str(team_id),
                rank=index + 1,
                points=3,
                played=1,
                wins=1,
                draws=0,
                losses=0,
                goals_for=2,
                goals_against=1,
                source=evidence(),
            )
            for index, team_id in enumerate(range(2000, 2030))
        )


CAPTURED = datetime(2026, 7, 29, 9, tzinfo=UTC)
DEADLINE = datetime(2026, 7, 29, 12, tzinfo=UTC)
TARGET_START = datetime(2026, 7, 29, 13, tzinfo=UTC)


def evidence():
    return SourceEvidence(
        provider="api-sports",
        endpoint="/fixtures",
        request_fingerprint="a" * 64,
        payload_sha256="b" * 64,
        fetched_at=CAPTURED,
    )


def target_and_pins():
    events = tuple(
        TargetEvent(
            drawing_id=99,
            drawing_number=5002,
            event_id=5000 + order,
            event_order=order,
            sport="hockey" if order == 14 else "football",
            championship="Test",
            starts_at=TARGET_START + timedelta(minutes=order),
            deadline=DEADLINE,
            home_team=f"Home {order}",
            away_team=f"Away {order}",
            home_team_en=None,
            away_team_en=None,
            bk_probabilities=(0.4, 0.3, 0.3),
        )
        for order in range(15)
    )
    target = TargetDrawing(
        drawing_id=99,
        drawing_number=5002,
        deadline=DEADLINE,
        fetched_at=CAPTURED,
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
            drawing_id=99,
            drawing_fingerprint=fingerprint,
            target_event_id=str(5000 + order),
            event_order=order,
            provider="api-sports",
            canonical_home_team_id=3000 + order * 2,
            canonical_away_team_id=3001 + order * 2,
            provider_home_team_id=str(2000 + order * 2),
            provider_away_team_id=str(2001 + order * 2),
            provider_fixture_id=str(1000 + order),
            starts_at=(TARGET_START + timedelta(minutes=order)).isoformat(),
            collection_id=None,
            provenance={},
            pin_hash="c" * 64,
            status="valid",
            created_at=CAPTURED.isoformat(),
            invalidated_at=None,
            invalidation_reason=None,
        )
        for order in range(15)
    )
    return target, pins


def test_collection_produces_15_audit_rows_and_explicit_market_fallback():
    target, pins = target_and_pins()
    provider = FakeProvider()

    result = collect_sports_stats(
        target,
        pins,
        provider,
        history_size=10,
        now=lambda: CAPTURED,
    )

    assert len(result.events) == 15
    assert result.complete_count == 14
    assert result.unsupported_count == 1
    assert result.events[14].missing_reasons == ("unsupported_sport",)
    assert result.events[0].home_window.fixture_count == 1
    assert result.events[0].home_window.rest_days > 0
    assert len(provider.history_calls) == 28


def test_collection_keeps_mixed_schedule_only_pin_as_explicit_missing_fallback():
    target, pins = target_and_pins()
    pins = (
        replace(
            pins[0],
            provider="schedule-evidence",
            source_provider="schedule-evidence",
            provider_fixture_id=None,
            source_fixture_id=None,
            provider_home_team_id=None,
            provider_away_team_id=None,
            schedule_only=True,
        ),
        *pins[1:],
    )
    provider = FakeProvider()

    result = collect_sports_stats(
        target,
        pins,
        provider,
        history_size=10,
        now=lambda: CAPTURED,
    )

    assert len(result.events) == 15
    assert result.events[0].status == "missing"
    assert result.events[0].missing_reasons == ("preparation_not_ready",)
    assert result.events[0].provider_fixture_id is None
    assert all(call[0] != "2000" for call in provider.history_calls)


def test_missing_standings_is_partial_not_zero_or_drawing_failure():
    target, pins = target_and_pins()

    result = collect_sports_stats(
        target,
        pins,
        FakeProvider(fail_standings=True),
        now=lambda: CAPTURED,
    )

    assert result.partial_count == 14
    assert result.unsupported_count == 1
    assert result.events[0].home_standing is None
    assert "standings_unavailable" in result.events[0].missing_reasons


@pytest.mark.parametrize(
    ("provider", "reason"),
    [
        (FakeProvider(fail_history_with_plan=True), "provider_plan_unavailable"),
        (FakeProvider(empty_history=True), "no_completed_fixtures"),
    ],
)
def test_unknown_history_never_becomes_a_numeric_zero_window(provider, reason):
    target, pins = target_and_pins()

    result = collect_sports_stats(
        target,
        pins,
        provider,
        now=lambda: CAPTURED,
    )

    event = result.events[0]
    assert event.status == "partial"
    assert event.home_window is None
    assert event.away_window is None
    assert reason in event.missing_reasons


def test_unknown_history_report_is_blank_and_deterministic(tmp_path):
    target, pins = target_and_pins()
    result = collect_sports_stats(
        target,
        pins,
        FakeProvider(fail_history_with_plan=True),
        now=lambda: CAPTURED,
    )

    first_paths = write_sports_stats_reports(result, report_dir=tmp_path)
    first_bytes = tuple(path.read_bytes() for path in first_paths)
    second_paths = write_sports_stats_reports(result, report_dir=tmp_path)

    assert first_paths == second_paths
    assert tuple(path.read_bytes() for path in second_paths) == first_bytes
    with first_paths[1].open(newline="", encoding="utf-8") as source:
        first_row = next(csv.DictReader(source))
    assert first_row["home_history_available"] == "False"
    assert first_row["away_history_available"] == "False"
    assert first_row["home_fixture_count"] == ""
    assert first_row["away_fixture_count"] == ""
    assert first_row["home_wdl"] == ""
    assert first_row["away_wdl"] == ""
    assert "provider_plan_unavailable" in first_row["missing_reasons"]
    markdown = first_paths[2].read_text(encoding="utf-8")
    assert "0-0-0" not in markdown


def test_prospective_collection_fails_closed_after_deadline():
    target, pins = target_and_pins()

    with pytest.raises(ValueError, match="after the drawing deadline"):
        collect_sports_stats(
            target,
            pins,
            FakeProvider(),
            now=lambda: DEADLINE,
        )
